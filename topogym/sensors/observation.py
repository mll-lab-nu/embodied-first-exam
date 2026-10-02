"""One immutable observation per episode state, shared by all consumers."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Mapping, Any
import numpy as np

from topogym.utils.snapshots import freeze
from topogym.sensors.camera_info import pinhole_intrinsics, pose_metadata
from topogym.sensors.cameras import update_dynamic_camera


@dataclass(frozen=True)
class SensorFrame:
    episode_id: str
    branch_id: int
    state_id: int
    physics_step: int
    sim_time_s: float
    rgb: Mapping[str, np.ndarray]
    camera_metadata: Mapping[str, Any]
    depth: Mapping[str, np.ndarray] = field(default_factory=dict)


class SensorSuite:
    def __init__(self, world, robot, *, enable_rgb=False, enable_depth=False, observation_mode="JOINT"):
        self.world, self.robot = world, robot
        self.enable_rgb = bool(enable_rgb)
        self.enable_depth = bool(enable_depth)
        self.observation_mode = observation_mode
        self._key = None
        self._observation = None
        self._frame = None
        self._proprioception = None
        self._rendered = False

    def invalidate(self):
        self._key = self._observation = self._frame = self._proprioception = None
        self._rendered = False

    def proprioception(self):
        """Owner-only same-sample robot measurements, before policy filtering."""
        if self._proprioception is None:
            raise RuntimeError("Sample observations before reading proprioception")
        return self._proprioception

    def depth_frame(self):
        """Add geometrical z-depth at the cached RGB state; never step physics.

        RGB remains Nyx. Genesis' geometric raster depth is an explicitly
        separate modality, sharing the same camera rig and live scene.
        """
        if not self.enable_depth or self._frame is None:
            raise RuntimeError("Depth must be enabled and observations sampled")
        if self._frame.depth:
            return self._frame
        depths = {}
        for name, camera in self.world.cameras.items():
            output = camera.render(rgb=False, depth=True)
            depth = output[1]
            if hasattr(depth, "detach"):
                depth = depth.detach().cpu().numpy()
            value = np.asarray(depth, dtype=np.float32).copy()
            if value.shape != self._frame.rgb[name].shape[:2]:
                raise RuntimeError("Depth and RGB image shapes differ")
            value[~np.isfinite(value) | (value <= 0) | (value > min(float(camera.far), 65.535))] = 0
            depths[name] = value
        self._frame = replace(self._frame, depth=freeze(depths))
        return self._frame

    def sample(self, *, episode_id, branch_id, state_id, task, rgb=True):
        """``rgb=False`` skips the camera pass (the sample then has no RGB); a later ``rgb=True`` sample of the same state
        renders it, re-reading the same robot and task measurements."""
        key = (episode_id, branch_id, state_id)
        render = bool(rgb) and self.enable_rgb
        if self._key == key and (self._rendered or not render):
            return self._observation, self._frame
        rgb, calibration = {}, {}
        if render:
            # Nyx caches by engine tick; our identity also includes the branch.
            # Invalidate the whole rig before its first read (one shared pass).
            for camera in self.world.cameras.values():
                invalidate = getattr(camera, "invalidate_frame", None)
                if invalidate is not None:
                    invalidate()
            for name, camera in self.world.cameras.items():
                update_dynamic_camera(camera)
                output = camera.render(rgb=True)
                pixels = output[0] if isinstance(output, (tuple, list)) else output
                if hasattr(pixels, "detach"):
                    pixels = pixels.detach().cpu().numpy()
                pixels = np.asarray(pixels)
                if pixels.dtype != np.uint8 or pixels.ndim != 3 or pixels.shape[2] != 3:
                    raise ValueError(f"Camera {name} must produce HxWx3 uint8 RGB")
                rgb[name] = freeze(pixels)
                calibration[name] = dict(
                    **pinhole_intrinsics(camera.res, camera.fov),
                    **pose_metadata(camera.transform))
        self._frame = SensorFrame(episode_id, branch_id, state_id, self.world.physics_step,
                                  self.world.sim_time_s, freeze(rgb), freeze(calibration))
        measured = self.robot.observe()
        self._proprioception = freeze(dict(state=dict(
            episode_id=episode_id, branch_id=branch_id, state_id=state_id,
            physics_step=self.world.physics_step, sim_time_s=self.world.sim_time_s), robot=measured))
        robot = {}
        for name, values in measured.items():
            selected = ("joint_position_rad", "joint_velocity_rad_s") if self.observation_mode == "JOINT" else (
                "tcp_position_world_m", "tcp_orientation_wxyz")
            robot[name] = {k: np.asarray(v, dtype=np.float64) for k, v in values.items()
                           if k in selected or k.startswith("finger_position_")}
        self._observation = freeze(dict(
            state=dict(episode_id=episode_id, branch_id=branch_id, state_id=state_id,
                       physics_step=self.world.physics_step, sim_time_s=self.world.sim_time_s),
            robot=robot, task=task.observe(), rgb=rgb, cameras=calibration))
        self._key, self._rendered = key, render
        return self._observation, self._frame


def observation_spec(action, config, scene):
    groups = {}
    for name, g in action["groups"].items():
        unit = "m" if g["gripper_field"].endswith("_m") else "rad"
        fields = ({"joint_position_rad": [len(g["arm_joint_names"])],
                   "joint_velocity_rad_s": [len(g["arm_joint_names"])]}
                  if config.observation_mode == "JOINT" else
                  {"tcp_position_world_m": [3], "tcp_orientation_wxyz": [4]})
        fields[f"finger_position_{unit}"] = [2]
        groups[name] = dict(fields=fields, dtype="float64", coordinate_frame="world",
                            arm_joint_names=g["arm_joint_names"])
    return dict(mode=config.observation_mode, groups=groups,
                state_fields=["episode_id", "branch_id", "state_id", "physics_step", "sim_time_s"],
                rgb={name: dict(shape=[int(c.res[1]), int(c.res[0]), 3], dtype="uint8")
                     for name, c in scene.env.cameras.items()},
                camera_metadata="pinhole intrinsics and world extrinsics", task="task-declared public measurements")
