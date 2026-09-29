"""Test-only rigid cube task registered for the lifetime of a context manager."""
from contextlib import contextmanager
from copy import deepcopy

import numpy as np

from topogym.tasks.base import TaskDefinition, TaskSpec, EntitySpec


class CubeTransferTask(TaskDefinition):
    task_id = "cube_transfer"
    model_revision = "cube_transfer_v1"
    defaults = {"stable_duration_s": .5, "size_m": .04, "mass_kg": .05,
                "start_xy": [-.10, -.10], "target_xy": [-.10, .10], "jitter_m": .005}

    def declare(self, asset_dir, table_height_m):
        self.table_z = table_height_m
        self.start = np.array([*self.config["start_xy"], table_height_m+self.config["size_m"]/2])
        self.start[:2] += self.rng.uniform(-self.config["jitter_m"], self.config["jitter_m"], 2)
        self.target = np.array([*self.config["target_xy"], self.start[2]])
        self.lifted = self.transported = False
        self.peak_clearance = self.airborne_distance = 0.
        self.held_time_s = 0.
        self.held_once = False
        self._held_anchor = None
        side = self.config["size_m"]
        return TaskSpec((EntitySpec("cube", "box", None, position_m=tuple(self.start),
            material={"rho": self.config["mass_kg"]/side**3, "friction": 1.},
            morph_options={"size": (side, side, side)},
            surface={"color": (.85, .25, .12), "roughness": .6}),
            EntitySpec("target_marker", "box", None,
                position_m=(self.target[0], self.target[1], table_height_m+.0005), fixed=True,
                morph_options={"size": (.06, .06, .001), "collision": False},
                surface={"color": (.18, .65, .30), "roughness": .8})))

    def evaluate_state(self, state):
        body = state["bodies"]["cube"]
        position = np.asarray(body["position_m"])
        # Rotated cube's lowest corner; do not assume an upright box.
        from scipy.spatial.transform import Rotation
        q = np.asarray(body["quaternion_wxyz"])
        rotation = Rotation.from_quat(q[[1, 2, 3, 0]]).as_matrix()
        half_z = np.abs(rotation[2]).sum()*self.config["size_m"]/2
        clearance = float(position[2]-half_z-self.table_z)
        arm = state["articulations"]["robot"]
        hand = arm["links"]["hand"]
        hand_q = np.asarray(hand["quaternion_wxyz"])
        tcp = np.asarray(hand["position_m"]) + Rotation.from_quat(hand_q[[1, 2, 3, 0]]).apply([0, 0, .1029])
        fingers = [float(np.asarray(arm["joints"][name]["position"])[0])
                   for name in ("finger_joint1", "finger_joint2")]
        opened = max(abs(x) for x in fingers) < .08
        withdrawn = np.linalg.norm(tcp-position) >= .05
        speed = float(np.linalg.norm(body["linear_velocity_m_s"]))
        angular_speed = float(np.linalg.norm(body["angular_velocity_rad_s"]))
        error = float(np.linalg.norm(position[:2]-self.target[:2]))
        reached = (self.lifted and self.transported and opened and withdrawn and error <= .02
                   and abs(clearance) <= .003 and speed <= .01 and angular_speed <= .1)
        failure = "cube_fell" if position[2] < self.table_z-.05 else None
        metrics = dict(clearance_m=clearance, target_error_m=error, linear_speed_m_s=speed,
                       angular_speed_rad_s=angular_speed, gripper_open=opened, withdrawn=bool(withdrawn),
                       lifted=self.lifted, transported=self.transported,
                       peak_clearance_m=self.peak_clearance, airborne_distance_m=self.airborne_distance,
                       cube_position_m=position.tolist(), tcp_position_m=tcp.tolist(), fingers=fingers,
                       held_once=self.held_once, held_time_s=self.held_time_s,
                       relative_position_m=Rotation.from_quat(hand_q[[1, 2, 3, 0]]).inv().apply(position-tcp).tolist())
        return bool(reached), failure, metrics

    def update(self, state, physics_dt_s):
        _, _, metrics = self.evaluate_state(state)
        clearance = metrics["clearance_m"]
        relative = np.asarray(metrics["relative_position_m"])
        candidate = clearance >= .05 and not metrics["gripper_open"] and np.linalg.norm(relative) <= .07
        if candidate:
            if self._held_anchor is None or np.linalg.norm(relative-self._held_anchor) > .01:
                self._held_anchor = relative.copy()
                self.held_time_s = 0.
            else:
                self.held_time_s += physics_dt_s
        else:
            self._held_anchor = None
            self.held_time_s = 0.
        held = self.held_time_s + 1e-12 >= .2
        self.held_once |= held
        self.peak_clearance = max(self.peak_clearance, clearance)
        self.lifted |= held
        if held:
            distance = float(np.linalg.norm(np.asarray(metrics["cube_position_m"])[:2]-self.start[:2]))
            self.airborne_distance = max(self.airborne_distance, distance)
            self.transported |= distance >= .15
        return super().update(state, physics_dt_s)

    def get_state(self):
        state = super().get_state()
        state["transfer"] = dict(lifted=self.lifted, transported=self.transported,
                                 peak_clearance=self.peak_clearance, airborne_distance=self.airborne_distance,
                                 held_time_s=self.held_time_s, held_once=self.held_once,
                                 _held_anchor=deepcopy(self._held_anchor))
        return state

    def set_state(self, state):
        super().set_state(state)
        for key, value in state["transfer"].items():
            setattr(self, key, deepcopy(value))

    def observe(self):
        # Public task setup, not a live object pose oracle.
        return dict(cube_initial_position_m=self.start.tolist(), target_position_m=self.target.tolist(),
                    cube_size_m=self.config["size_m"], table_height_m=self.table_z)


@contextmanager
def register_cube_transfer():
    from topogym.config import registry, variation_records
    from topogym.config.registry import TaskRegistration
    old_records = variation_records.RECORDS
    if CubeTransferTask.task_id in registry._TASKS:
        raise RuntimeError("Test task already registered")
    implementation = "topogym.benchmark.fixtures.cube_transfer:CubeTransferTask"
    registry._TASKS[CubeTransferTask.task_id] = TaskRegistration(
        CubeTransferTask.task_id, implementation, "rigid", "panda_robotiq")
    variation_records.RECORDS = (*old_records, dict(task_id=CubeTransferTask.task_id, variation_id="base",
        aliases=[], status="integrated", implementation=implementation, family_id="test", difficulty=None,
        model_revision=CubeTransferTask.model_revision, reason=None, validation="test_only", pool="test"))
    try:
        yield
    finally:
        del registry._TASKS[CubeTransferTask.task_id]
        variation_records.RECORDS = old_records
