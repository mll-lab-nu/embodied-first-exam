"""Planner protocol and the default straight-line interpolation planner.

A planner turns ``(q0, ee_targets)`` into a stream of end-effector targets (and,
when it can, the joint trajectory behind them). The :class:`MoveL` primitive streams
one row of ``ee_traj`` per control tick, so every planner must produce poses that are
already timed at the control rate (:data:`tactilelab_tasks.core.types.CONTROL_DT`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Optional, Protocol, runtime_checkable

import numpy as np

from . import math as m
from .types import CONTROL_DT, ArmIndex


@dataclass
class PlanResult:
    """Output of :meth:`Planner.plan`.

    Attributes:
        success: False when no plan was found (``ee_traj`` is then empty).
        ee_traj: ``(T, 14)`` end-effector targets, env frame, one row per control
            tick. Arms that were not requested hold NaN.
        joint_traj: ``(T, 16)`` joint targets when the planner works in joint space,
            else None.
        dt: seconds between rows (always the control tick).
        info: free-form diagnostics (planning time, attempts, ...).
    """

    success: bool
    ee_traj: np.ndarray
    joint_traj: Optional[np.ndarray] = None
    dt: float = CONTROL_DT
    info: Optional[dict] = None

    @property
    def num_steps(self) -> int:
        return int(self.ee_traj.shape[0])


@runtime_checkable
class Planner(Protocol):
    """Anything that plans arm motions for :class:`tactilelab_tasks.core.policy.MoveL`."""

    def plan(
        self,
        q0: np.ndarray,
        ee_current: Dict[int, np.ndarray],
        ee_targets: Dict[int, np.ndarray],
        **kwargs,
    ) -> PlanResult:
        """Plan from the current state to per-arm pose targets.

        Args:
            q0: ``(16,)`` current joint positions in the canonical order.
            ee_current: ``{ArmIndex: pose7}`` current end-effector poses, env frame.
            ee_targets: ``{ArmIndex: pose7}`` goals, env frame; arms absent from the
                dict are left alone (NaN in the output).
        """
        ...

    def update_obstacles(self, obstacles: list) -> None:
        """Optional: refresh the collision world (no-op for planners without one)."""
        ...


class InterpPlanner:
    """Straight-line interpolation in pose space (the default ``MoveL`` mode).

    Positions are interpolated linearly and orientations by slerp after sign-aligning
    the goal quaternion to the start hemisphere, over ``steps`` ticks. With
    ``speed > 0`` the step count grows to ``ceil(dist / (speed * dt))`` when the move
    would otherwise be faster than ``speed`` m/s.
    """

    def __init__(self, steps: int = 120, speed: float = 0.0, dt: float = CONTROL_DT, slerp: bool = True):
        self.steps = int(steps)
        self.speed = float(speed)
        self.dt = float(dt)
        self.slerp = bool(slerp)

    def plan(
        self, q0, ee_current, ee_targets, steps: Optional[int] = None, speed: Optional[float] = None, **kwargs
    ) -> PlanResult:
        n = int(self.steps if steps is None else steps)
        v = float(self.speed if speed is None else speed)
        n = max(1, n)
        if v > 0.0:
            dist = max(
                float(np.linalg.norm(np.asarray(ee_targets[a])[:3] - np.asarray(ee_current[a])[:3])) for a in ee_targets
            )
            n = max(n, int(math.ceil(dist / (v * self.dt))))
        traj = np.full((n, 14), np.nan, dtype=np.float64)
        for arm, goal in ee_targets.items():
            arm = int(arm)
            start = np.asarray(ee_current[arm], dtype=np.float64)
            goal = np.asarray(goal, dtype=np.float64).copy()
            goal[3:7] = m.quat_sign_align(goal[3:7], start[3:7])
            for i in range(n):
                alpha = (i + 1) / n
                traj[i, 7 * arm : 7 * arm + 7] = m.pose_interp(start, goal, alpha, slerp=self.slerp)
        return PlanResult(True, traj, None, self.dt, {"planner": "interp", "steps": n})

    def update_obstacles(self, obstacles: list) -> None:  # noqa: D401 - protocol no-op
        """Interpolation ignores obstacles."""
        return None


class SnapPlanner:
    """Emit the goal immediately (one row): the fallback when a planner fails."""

    def plan(self, q0, ee_current, ee_targets, **kwargs) -> PlanResult:
        traj = np.full((1, 14), np.nan, dtype=np.float64)
        for arm, goal in ee_targets.items():
            traj[0, 7 * int(arm) : 7 * int(arm) + 7] = np.asarray(goal, dtype=np.float64)
        return PlanResult(True, traj, None, CONTROL_DT, {"planner": "snap"})

    def update_obstacles(self, obstacles: list) -> None:
        return None


__all__ = ["Planner", "PlanResult", "InterpPlanner", "SnapPlanner", "ArmIndex"]
