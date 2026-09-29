"""Pick up and place a cube with one low-level action per act(obs).

This reference requires unlimited world observations. It is not a vision model.
The generator is private policy state: yielding an action never steps the Env.
"""
import math
import numpy as np
from scipy.spatial.transform import Rotation, Slerp


class CubePickPlacePolicy:
    def __init__(self, *, cube_entity_id="cube", place_entity_id=None,
                 part="all", pickup_position_world_m=None, grasp_offset_m=(0., 0., 0.),
                 speed_scale=1.):
        if part not in {"all", "pickup", "transfer"}:
            raise ValueError("part must be all, pickup or transfer")
        if not math.isfinite(speed_scale) or speed_scale <= 0:
            raise ValueError("speed_scale must be positive")
        if part == "transfer" and pickup_position_world_m is None:
            raise ValueError("A transfer segment requires the original pickup position")
        self.cube_entity_id, self.place_entity_id = cube_entity_id, place_entity_id
        self.part, self.speed_scale = part, speed_scale
        self.pickup_position = None if pickup_position_world_m is None else np.array(pickup_position_world_m, dtype=float)
        self.grasp_offset = np.array(grasp_offset_m, dtype=float)
        for vector in (self.grasp_offset, self.pickup_position):
            if vector is not None and (vector.shape != (3,) or not np.isfinite(vector).all()):
                raise ValueError("Positions must have three finite coordinates")
        self.phase = "created"

    def initialize(self, context):
        spec = context["action_spec"]
        if spec["robot_id"] != "panda_robotiq" or spec["mode"] != "EE_ABS":
            raise ValueError("This reference supports panda_robotiq with EE_ABS")
        if context["mode"] != "unlimited" or "world" not in context["observation_spec"]["privileged_fields"]:
            raise ValueError("This reference needs authorized world observations")
        self.arm = spec["arms"][0]
        group = spec["groups"][self.arm]
        self.gripper_field = group["gripper_field"]
        self.opened, self.closed = group["gripper_limits"]
        self.dt = context["timing_spec"]["control_dt_s"]
        self._program = None
        self.phase = "ready"
        self.final_reason = None

    def act(self, obs):
        self.obs = obs
        if self._program is None:
            self._program = self._actions()
        try:
            return next(self._program)
        except StopIteration:
            self.phase = "done"
            return None

    def on_segment_end(self, obs, result):
        self.final_reason = result["reason"]

    def _position(self):
        return np.asarray(self.obs["robot"][self.arm]["tcp_position_world_m"])

    def _cube_position(self):
        return np.asarray(self.obs["privileged"]["world"]["bodies"][self.cube_entity_id]["position_m"])

    def _time(self):
        return self.obs["state"]["sim_time_s"]

    def _hold(self, seconds):
        start = self._time()
        while self._time() - start < seconds - 1e-9:
            yield {}

    def _move(self, target, seconds, phase):
        self.phase = phase
        origin = self._position().copy()
        q0 = np.asarray(self.obs["robot"][self.arm]["tcp_orientation_wxyz"])
        downward = np.array([0., 1., 0., 0.])
        rotations = Rotation.from_quat(np.array([q0, downward])[:, [1, 2, 3, 0]])
        slerp = Slerp([0., 1.], rotations)
        duration, start = seconds / self.speed_scale, self._time()
        while True:
            t = min(1., (self._time() - start + self.dt) / duration)
            u = t*t*(3.-2.*t)
            yield {self.arm: dict(position_world_m=(origin+u*(target-origin)).tolist(),
                orientation_wxyz=slerp(u).as_quat()[[3, 0, 1, 2]].tolist(),
                **{self.gripper_field: self.grip})}
            if t >= 1.-1e-9:
                break
        settled = self._time()
        while np.linalg.norm(self._position()-target) >= .003:
            if self._time() - settled >= .6 - 1e-9:
                raise RuntimeError("Reference policy could not reach its stage target")
            yield {}

    def _actions(self):
        if self.pickup_position is None:
            self.pickup_position = self._cube_position().copy()
        start = self.pickup_position + self.grasp_offset
        target = self.pickup_position.copy()
        if self.place_entity_id is not None:
            marker = self.obs["privileged"]["world"]["bodies"][self.place_entity_id]
            target[:2] = np.asarray(marker["position_m"])[:2]
        self.grip = self.closed if self.part == "transfer" else self.opened
        if self.part != "transfer":
            self.phase = "open"
            yield {self.arm: {self.gripper_field: self.opened}}
            yield from self._hold(.3)
            yield from self._move(start+[0, 0, .14], 1.5, "approach")
            yield from self._move(start+[0, 0, .005], 1., "descend")
            self.phase, self.grip = "close", self.closed
            yield {self.arm: {self.gripper_field: self.closed}}
            yield from self._hold(3.)
            yield from self._move(start+[0, 0, .10], 1., "lift")
            self.phase = "hold"
            yield from self._hold(.25)
            if self._cube_position()[2] - self.pickup_position[2] < .05:
                raise RuntimeError("Reference policy failed to lift the cube")
            if self.part == "pickup":
                return
        if self.place_entity_id is not None:
            yield from self._move(target+[0, 0, .10], 1.5, "transfer")
        yield from self._move(target+[0, 0, .005], 1., "lower")
        self.phase, self.grip = "release", self.opened
        yield {self.arm: {self.gripper_field: self.opened}}
        yield from self._hold(2.)
        yield from self._move(target+[0, 0, .12], 1., "retreat")
        yield from self._hold(.8)
