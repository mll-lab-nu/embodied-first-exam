"""Optional cuRobo MotionGen plugin behind the :class:`tactilelab_tasks.core.planner.Planner` protocol.

Uses the cuRobo v2 ``MotionPlanner`` with the packaged ``xtrainer_gsmini.yml``
(collision spheres for the GelSight-Mini fingers, tool frames ``J1_6`` / ``J2_6``,
fingers locked at 0): 32 IK seeds, 4 trajectory-optimisation seeds, self-collision
on, collision activation distance 0.025 m, position tolerance 5 mm, up to 2 attempts.
The optimised trajectory (interpolation dt 0.025 s) is re-timed to the 60 Hz control
tick so that streaming one waypoint per tick plays the motion at real speed, and
converted with cuRobo's forward kinematics into end-effector poses in the env frame
(the idle arm holds its current pose).

cuRobo is imported lazily; :func:`available` reports whether it can be used so
callers can fall back to :class:`tactilelab_tasks.core.planner.InterpPlanner`.
"""

from __future__ import annotations

import copy
import os
import time
from typing import Dict, List, Optional

import numpy as np

from ..core import math as m
from ..core.planner import PlanResult
from ..core.types import CONTROL_DT, EE_LINKS, JOINT_NAMES

ASSET_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "robots", "xtrainer_gsmini"
)
DEFAULT_YML = os.path.join(ASSET_DIR, "curobo", "xtrainer_gsmini.yml")
CUROBO_INTERPOLATION_DT = 0.025


def available() -> bool:
    """True if cuRobo v2 and a CUDA device are importable."""
    try:
        import torch

        if not torch.cuda.is_available():
            return False
        from curobo.motion_planner import MotionPlannerCfg  # noqa: F401

        return True
    except Exception:
        return False


def load_robot_cfg(yml_path: str = DEFAULT_YML) -> dict:
    """Load the robot yml and make its relative asset paths absolute."""
    import yaml

    with open(yml_path) as fh:
        doc = yaml.safe_load(fh)
    root = os.path.dirname(os.path.abspath(yml_path))
    kin = doc["robot_cfg"]["kinematics"]
    for key in ("asset_root_path", "urdf_path"):
        val = kin.get(key)
        if isinstance(val, str) and not os.path.isabs(val):
            kin[key] = os.path.normpath(os.path.join(root, val))
    return doc


def _resample(traj: np.ndarray, dt_in: float, dt_out: float) -> np.ndarray:
    """Linearly re-time a ``(T, D)`` trajectory from ``dt_in`` to ``dt_out`` keeping its duration."""
    T = traj.shape[0]
    if T <= 1:
        return traj.copy()
    duration = (T - 1) * dt_in
    n = max(1, int(np.ceil(duration / dt_out)))
    t_in = np.arange(T) * dt_in
    t_out = np.minimum(np.arange(1, n + 1) * dt_out, duration)
    return np.stack([np.interp(t_out, t_in, traj[:, d]) for d in range(traj.shape[1])], axis=1)


class CuroboPlanner:
    """cuRobo MotionGen for the X-Trainer arms (optional plugin).

    Args:
        base_pose: robot base pose7 in the env frame (targets are converted to the
            base frame for cuRobo and FK results back to the env frame).
        robot_yml: path of the cuRobo robot configuration.
        device: CUDA device string.
        tick_dt: control tick the plans are re-timed to.
        num_ik_seeds / num_trajopt_seeds / collision_activation_distance /
        position_tolerance / max_attempts: planner settings.
    """

    def __init__(
        self,
        base_pose: np.ndarray,
        robot_yml: str = DEFAULT_YML,
        device: str = "cuda:0",
        tick_dt: float = CONTROL_DT,
        num_ik_seeds: int = 32,
        num_trajopt_seeds: int = 4,
        collision_activation_distance: float = 0.025,
        position_tolerance: float = 0.005,
        max_attempts: int = 2,
        warmup: bool = True,
    ):
        import torch
        from curobo.motion_planner import MotionPlanner, MotionPlannerCfg
        from curobo.types import DeviceCfg

        self.base_pose = np.asarray(base_pose, dtype=np.float64).reshape(7)
        self.tick_dt = float(tick_dt)
        self.max_attempts = int(max_attempts)
        self.device = torch.device(device)
        self.robot_cfg = load_robot_cfg(robot_yml)
        device_cfg = DeviceCfg(device=self.device, dtype=torch.float32)
        cfg = MotionPlannerCfg.create(
            robot=copy.deepcopy(self.robot_cfg["robot_cfg"]),
            device_cfg=device_cfg,
            scene_model=None,
            collision_cache={"cuboid": 10, "mesh": 500},
            num_ik_seeds=int(num_ik_seeds),
            num_trajopt_seeds=int(num_trajopt_seeds),
            position_tolerance=float(position_tolerance),
            self_collision_check=True,
            use_cuda_graph=False,
            optimizer_collision_activation_distance=float(collision_activation_distance),
            max_goalset=1,
        )
        self.planner = MotionPlanner(cfg)
        self.joint_names: List[str] = list(self.planner.joint_names)
        self._canon_idx = [list(JOINT_NAMES).index(n) if n in JOINT_NAMES else None for n in self.joint_names]
        self.tool_frames = list(EE_LINKS)
        self.interpolation_dt = CUROBO_INTERPOLATION_DT
        if warmup:
            try:
                self.planner.warmup()
            except Exception:
                pass

    # ------------------------------------------------------------------ helpers
    def _joint_state(self, q16: np.ndarray):
        import torch
        from curobo.types import JointState

        q = np.zeros(len(self.joint_names), dtype=np.float32)
        for i, ci in enumerate(self._canon_idx):
            if ci is not None:
                q[i] = q16[ci]
        return JointState.from_position(
            torch.as_tensor(q, device=self.device).view(1, -1), joint_names=self.joint_names
        )

    def _to_base(self, pose_env: np.ndarray) -> np.ndarray:
        return m.pose_relative(self.base_pose, pose_env)

    def _to_env(self, pose_base: np.ndarray) -> np.ndarray:
        return m.pose_compose(self.base_pose, pose_base)

    def fk(self, q16: np.ndarray) -> Dict[int, np.ndarray]:
        """Env-frame tool poses from cuRobo's kinematics."""
        ks = self.planner.compute_kinematics(self._joint_state(q16))
        out = {}
        for i, frame in enumerate(self.tool_frames):
            p = ks.tool_poses[frame] if isinstance(ks.tool_poses, dict) else ks.tool_poses.get_link_pose(frame)
            pos = p.position.reshape(-1, 3)[0].detach().cpu().numpy()
            quat = p.quaternion.reshape(-1, 4)[0].detach().cpu().numpy()
            out[i] = self._to_env(m.pose_from_pos_quat(pos, quat))
        return out

    # ------------------------------------------------------------------ Planner protocol
    def plan(
        self, q0: np.ndarray, ee_current: Dict[int, np.ndarray], ee_targets: Dict[int, np.ndarray], **kwargs
    ) -> PlanResult:
        import torch
        from curobo.types import GoalToolPose, Pose

        q0 = np.asarray(q0, dtype=np.float64).reshape(16)
        goals_base = {}
        current_fk = self.fk(q0)
        for i, frame in enumerate(self.tool_frames):
            goal_env = ee_targets.get(i)
            if goal_env is None or m.is_nan_pose(goal_env):
                goal_env = current_fk[i]
            goals_base[frame] = self._to_base(np.asarray(goal_env, dtype=np.float64))
        pose_dict = {
            f: Pose(
                position=torch.as_tensor(p[:3], dtype=torch.float32, device=self.device).view(1, 3),
                quaternion=torch.as_tensor(p[3:7], dtype=torch.float32, device=self.device).view(1, 4),
            )
            for f, p in goals_base.items()
        }
        goal = GoalToolPose.from_poses(pose_dict, ordered_tool_frames=self.tool_frames)
        t0 = time.time()
        result = self.planner.plan_pose(
            goal, self._joint_state(q0), max_attempts=self.max_attempts, enable_graph_attempt=0
        )
        elapsed = time.time() - t0
        ok = result is not None and result.success is not None and bool(result.success.reshape(-1)[0].item())
        if not ok or result.interpolated_trajectory is None:
            return PlanResult(False, np.zeros((0, 14)), info={"planner": "curobo", "time": elapsed, "status": "failed"})
        it = result.interpolated_trajectory
        names = list(it.joint_names) if it.joint_names is not None else list(self.joint_names)
        traj = it.position.reshape(-1, len(names))  # (batch * horizon, dof), batch = 1
        if result.interpolated_last_tstep is not None:
            last = int(result.interpolated_last_tstep.reshape(-1)[0].item())
            traj = traj[: max(2, last + 1)]
        traj = traj.detach().cpu().numpy().astype(np.float64)
        # cuRobo interpolates at a fixed dt (0.025 s); re-time to the control tick
        traj60 = _resample(traj, self.interpolation_dt, self.tick_dt)
        # joint trajectory in canonical order (joints missing from the result keep q0)
        joint_traj = np.tile(q0, (traj60.shape[0], 1))
        for i, n in enumerate(names):
            if n in JOINT_NAMES:
                joint_traj[:, list(JOINT_NAMES).index(n)] = traj60[:, i]
        ee_traj = np.full((traj60.shape[0], 14), np.nan)
        requested = [i for i in range(2) if i in ee_targets and not m.is_nan_pose(ee_targets[i])]
        for k in range(traj60.shape[0]):
            poses = self.fk(joint_traj[k])
            for i in requested:
                ee_traj[k, 7 * i : 7 * i + 7] = poses[i]
        return PlanResult(
            True,
            ee_traj,
            joint_traj,
            self.tick_dt,
            {"planner": "curobo", "time": elapsed, "steps": int(traj60.shape[0]), "curobo_steps": int(traj.shape[0])},
        )

    def update_obstacles(self, obstacles: list) -> None:
        """Replace the collision world with cuboids ``{"name", "pose": pose7 env, "dims": (x, y, z)}``.

        Best effort: silently ignored when the installed cuRobo does not expose
        ``SceneCfg.create`` with the cuboid dictionary format.
        """
        try:
            try:
                from curobo.scene import Scene as SceneCfg
            except ImportError:  # older layouts
                from curobo.scene import SceneCfg

            cub = {}
            for o in obstacles:
                p = self._to_base(np.asarray(o["pose"], dtype=np.float64))
                cub[o["name"]] = {"dims": [float(x) for x in o["dims"]], "pose": [float(x) for x in p]}
            self.planner.update_world(SceneCfg.create({"cuboid": cub}))
        except Exception as exc:  # pragma: no cover - depends on cuRobo version
            print(f"[curobo_planner] update_obstacles skipped: {exc!r}")


__all__ = ["CuroboPlanner", "available", "load_robot_cfg", "DEFAULT_YML"]
