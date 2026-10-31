"""Scripted demonstration policies.

A :class:`DemoPolicy` maps ``(obs, info, t)`` to ``(Action, phase_id, done)``. Most
policies are a :class:`PhasedPolicy`: an ordered list of phases, each a small object
with ``start / step / done``. Two primitives cover almost everything:

* :class:`MoveL` - move one arm (or both) to a pose along a planned path, streaming
  one target per tick; done when the end-effector is within tolerance, when it stalls
  or when it times out.
* :class:`Gripper` - open / close / set a gap; done when the fingers have settled.

Observations are read through the keys of ``Task.get_observation``
(``joint_pos``, ``ee_pos_right`` ...), so the primitives work with any backend.
"""

from __future__ import annotations

import math
from typing import Callable, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

from . import math as m
from .planner import InterpPlanner, Planner, PlanResult, SnapPlanner
from .types import (
    CONTROL_DT,
    GRIPPER_CLOSE,
    GRIPPER_OPEN,
    GRIPPER_WIDTH_OFFSET,
    Action,
    ArmIndex,
    ObsDict,
)

ARM_NAMES = {"right": int(ArmIndex.RIGHT), "left": int(ArmIndex.LEFT)}
_EE_KEYS = {0: ("ee_pos_right", "ee_quat_right"), 1: ("ee_pos_left", "ee_quat_left")}
_FINGER_SLICES = {0: slice(12, 14), 1: slice(14, 16)}

PoseLike = Union[np.ndarray, Sequence[float], Callable[[ObsDict, dict], np.ndarray]]


def ee_pose(obs: ObsDict, arm: int) -> np.ndarray:
    """Current end-effector pose7 of ``arm`` from the policy observation."""
    pk, qk = _EE_KEYS[int(arm)]
    p = obs["policy"]
    return np.concatenate(
        [np.asarray(p[pk], dtype=np.float64).reshape(3), np.asarray(p[qk], dtype=np.float64).reshape(4)]
    )


def joint_pos(obs: ObsDict) -> np.ndarray:
    return np.asarray(obs["policy"]["joint_pos"], dtype=np.float64).reshape(16)


def _arms(arm: Union[str, int, Sequence]) -> List[int]:
    if isinstance(arm, str):
        if arm == "both":
            return [0, 1]
        return [ARM_NAMES[arm]]
    if isinstance(arm, (int, np.integer)):
        return [int(arm)]
    return [int(a) if not isinstance(a, str) else ARM_NAMES[a] for a in arm]


# --------------------------------------------------------------------------- phases
class PhaseBase:
    """One step of a scripted policy. Subclasses implement ``start/step/done``."""

    name: str = "phase"

    def start(self, obs: ObsDict, info: dict) -> None:  # noqa: D401
        """Called once when the phase becomes active."""

    def step(self, obs: ObsDict, info: dict) -> Action:
        raise NotImplementedError

    def done(self, obs: ObsDict, info: dict) -> bool:
        raise NotImplementedError

    @property
    def done_reason(self) -> Optional[str]:
        return getattr(self, "_done_reason", None)


class MoveL(PhaseBase):
    """Move arm(s) to pose target(s) along a planned path.

    Args:
        target: pose7 (env frame), ``{arm: pose7}`` for several arms, or a callable
            ``(obs, info) -> pose7 | dict`` evaluated at ``start`` (live targets).
        arm: ``"right" | "left" | "both"`` or an :class:`ArmIndex`; ignored when
            ``target`` is a dict.
        mode: ``"interp"`` (default, :class:`InterpPlanner`) or ``"motiongen"``
            (``planner`` argument, falls back to interp when the plan fails).
        steps: interpolation ticks (interp mode).
        speed: optional speed limit in m/s (interp mode; 0 = off).
        tol: ``(translation [m], quaternion chordal distance)`` done thresholds.
        timeout: ticks before giving up.
        stall_patience: consecutive ticks with < ``stall_move_thresh`` m of motion
            that count as a stall (after the stream ended); 0 disables.
        converge: when False (default) the phase ends as soon as the last planned
            waypoint has been emitted; when True it waits for ``tol`` (or stall /
            timeout).
        gripper: gripper command to hold during the move, ``[right, left]`` or None
            to keep the previous command.
        planner: planner for ``mode="motiongen"``.
    """

    def __init__(
        self,
        target: PoseLike,
        arm: Union[str, int] = "right",
        mode: str = "interp",
        steps: int = 120,
        speed: float = 0.0,
        tol: Tuple[float, float] = (0.001, 0.001),
        timeout: int = 300,
        stall_patience: int = 10,
        stall_move_thresh: Optional[float] = 0.0005,
        converge: bool = False,
        gripper: Optional[Sequence[int]] = None,
        planner: Optional[Planner] = None,
        name: str = "move",
    ):
        self.target_spec = target
        self.arm_spec = arm
        self.mode = mode
        self.steps = int(steps)
        self.speed = float(speed)
        self.tol = (float(tol[0]), float(tol[1]))
        self.timeout = int(timeout)
        self.stall_patience = int(stall_patience)
        self.stall_move_thresh = float(stall_move_thresh) if stall_move_thresh is not None else 0.5 * self.tol[0]
        self.converge = bool(converge)
        self.gripper = None if gripper is None else np.asarray(gripper, dtype=np.int64).reshape(2)
        self.planner = planner
        self.name = name
        self._interp = InterpPlanner(steps=self.steps, speed=self.speed)
        self._plan: Optional[PlanResult] = None
        self._targets: Dict[int, np.ndarray] = {}
        self._i = 0
        self._t = 0
        self._stall_prev = None
        self._stall_count = 0
        self._done_reason: Optional[str] = None
        self._last_action: Optional[Action] = None

    # -- helpers
    def resolve_targets(self, obs: ObsDict, info: dict) -> Dict[int, np.ndarray]:
        spec = self.target_spec(obs, info) if callable(self.target_spec) else self.target_spec
        if isinstance(spec, dict):
            return {_arms(k)[0]: np.asarray(v, dtype=np.float64).reshape(7) for k, v in spec.items()}
        arms = _arms(self.arm_spec)
        spec = np.asarray(spec, dtype=np.float64)
        if spec.size == 14:
            return {0: spec[:7].copy(), 1: spec[7:].copy()}
        if len(arms) != 1:
            raise ValueError("a single pose7 target needs a single arm")
        return {arms[0]: spec.reshape(7)}

    @property
    def targets(self) -> Dict[int, np.ndarray]:
        return self._targets

    # -- phase API
    def start(self, obs: ObsDict, info: dict) -> None:
        self._targets = self.resolve_targets(obs, info)
        current = {a: ee_pose(obs, a) for a in self._targets}
        q0 = joint_pos(obs)
        plan = None
        if self.mode == "motiongen" and self.planner is not None:
            try:
                plan = self.planner.plan(q0, current, self._targets)
            except Exception as exc:  # planner failure is not fatal
                plan = PlanResult(False, np.zeros((0, 14)), info={"error": repr(exc)})
            if not plan.success or plan.num_steps == 0:
                plan = None
        if plan is None:
            if self.mode == "snap":
                plan = SnapPlanner().plan(q0, current, self._targets)
            else:
                plan = self._interp.plan(q0, current, self._targets)
        self._plan = plan
        self._i = 0
        self._t = 0
        self._stall_prev = None
        self._stall_count = 0
        self._done_reason = None

    def step(self, obs: ObsDict, info: dict) -> Action:
        assert self._plan is not None, "MoveL.step before start"
        row = self._plan.ee_traj[min(self._i, self._plan.num_steps - 1)]
        if self._i < self._plan.num_steps:
            self._i += 1
        self._t += 1
        grip = self.gripper if self.gripper is not None else self._previous_gripper(info)
        act = Action(row.copy(), grip)
        self._last_action = act
        return act

    def streaming(self) -> bool:
        """True while planned waypoints are still being emitted."""
        return self._plan is not None and self._i < self._plan.num_steps

    def errors(self, obs: ObsDict) -> Dict[int, Tuple[float, float]]:
        """Per-arm ``(translation, quaternion distance)`` to the goal."""
        out = {}
        for a, goal in self._targets.items():
            cur = ee_pose(obs, a)
            out[a] = (float(np.linalg.norm(cur[:3] - goal[:3])), m.quat_distance(cur[3:7], goal[3:7]))
        return out

    def done(self, obs: ObsDict, info: dict) -> bool:
        if self._plan is None:
            return False
        if self.streaming():
            return False
        if not self.converge:
            self._done_reason = "stream finished"
            return True
        if self._t >= self.timeout:
            self._done_reason = f"timeout ({self._t} >= {self.timeout})"
            return True
        errs = self.errors(obs)
        if self.stall_patience > 0:
            first = min(self._targets)
            cur = ee_pose(obs, first)[:3]
            if self._stall_prev is None:
                self._stall_prev = cur
                self._stall_count = 0
            else:
                moved = float(np.linalg.norm(cur - self._stall_prev))
                if moved < self.stall_move_thresh:
                    self._stall_count += 1
                else:
                    self._stall_count = 0
                    self._stall_prev = cur
                if self._stall_count >= self.stall_patience:
                    self._done_reason = f"stalled (<{self.stall_move_thresh:.4f} m for {self._stall_count} ticks)"
                    return True
        for a, (dp, dq) in errs.items():
            if dp >= self.tol[0] or dq >= self.tol[1]:
                return False
        self._done_reason = "reached " + ", ".join(
            f"arm{a}: {dp * 1e3:.2f} mm / {dq:.4f}" for a, (dp, dq) in errs.items()
        )
        return True

    @staticmethod
    def _previous_gripper(info: dict) -> np.ndarray:
        prev = info.get("last_action")
        if isinstance(prev, Action):
            return prev.gripper.copy()
        return np.array([GRIPPER_OPEN, GRIPPER_OPEN], dtype=np.int64)


class Gripper(PhaseBase):
    """Open / close one gripper (or set a finger gap) and wait for the fingers to settle.

    Args:
        command: ``"open"``, ``"close"``, 0/1, or a float gap in metres.
        arm: ``"right" | "left"``.
        timeout: minimum ticks before the done check passes (default 30 at 60 Hz).
        settle_threshold: ``|dq_fingers|`` per tick below which the fingers count as
            settled (default 1e-4 m).
        hold_timeout: ticks after which the phase ends even if the fingers still move
            (default ``6 * timeout``).
    """

    def __init__(
        self,
        command: Union[str, int, float] = "close",
        arm: Union[str, int] = "right",
        timeout: int = 30,
        settle_threshold: float = 1e-4,
        hold_timeout: Optional[int] = None,
        name: Optional[str] = None,
    ):
        self.arm = _arms(arm)[0]
        self.gap: Optional[float] = None
        if isinstance(command, str):
            self.command = GRIPPER_CLOSE if command == "close" else GRIPPER_OPEN
        elif isinstance(command, (int, np.integer)):
            self.command = int(command)
        else:
            self.gap = float(command)
            self.command = GRIPPER_CLOSE if self.gap < GRIPPER_WIDTH_OFFSET else GRIPPER_OPEN
        self.timeout = int(timeout)
        self.settle_threshold = float(settle_threshold)
        self.hold_timeout = int(hold_timeout) if hold_timeout is not None else 6 * self.timeout
        self.name = name or ("close" if self.command == GRIPPER_CLOSE else "open")
        self._t = 0
        self._prev = None
        self._done_reason = None

    def start(self, obs: ObsDict, info: dict) -> None:
        self._t = 0
        self._prev = joint_pos(obs)[_FINGER_SLICES[self.arm]].copy()
        self._done_reason = None

    def step(self, obs: ObsDict, info: dict) -> Action:
        self._t += 1
        prev = info.get("last_action")
        grip = (
            prev.gripper.copy() if isinstance(prev, Action) else np.array([GRIPPER_OPEN, GRIPPER_OPEN], dtype=np.int64)
        )
        grip[self.arm] = self.command
        gap = None
        if self.gap is not None:
            gap = np.full(2, np.nan)
            gap[self.arm] = self.gap
        return Action(np.full(14, np.nan), grip, gap)

    def done(self, obs: ObsDict, info: dict) -> bool:
        q = joint_pos(obs)[_FINGER_SLICES[self.arm]]
        settled = self._prev is not None and float(np.linalg.norm(q - self._prev)) < self.settle_threshold
        self._prev = q.copy()
        if self._t >= self.timeout and settled:
            self._done_reason = "settled"
            return True
        if self._t >= self.hold_timeout:
            self._done_reason = "hold timeout"
            return True
        return False


class Hold(PhaseBase):
    """Hold both arms (and the last gripper command) for ``steps`` ticks."""

    def __init__(self, steps: int = 30, gripper: Optional[Sequence[int]] = None, name: str = "hold"):
        self.steps = int(steps)
        self.gripper = None if gripper is None else np.asarray(gripper, dtype=np.int64).reshape(2)
        self.name = name
        self._t = 0

    def start(self, obs, info):
        self._t = 0

    def step(self, obs, info) -> Action:
        self._t += 1
        grip = self.gripper if self.gripper is not None else MoveL._previous_gripper(info)
        return Action(np.full(14, np.nan), grip)

    def done(self, obs, info) -> bool:
        return self._t >= self.steps


# --------------------------------------------------------------------------- policies
class DemoPolicy:
    """Base class: ``act(obs, info, t) -> (action, phase_id, done)``."""

    def __init__(self, cfg: Optional[dict] = None):
        self.cfg = dict(cfg or {})
        self.last_action: Optional[Action] = None

    def reset(self, obs: ObsDict, info: dict) -> None:
        self.last_action = None

    def act(self, obs: ObsDict, info: dict, t: int) -> Tuple[Action, int, bool]:
        raise NotImplementedError

    @property
    def phase_names(self) -> List[str]:
        return []


class PhasedPolicy(DemoPolicy):
    """A fixed sequence of phases; ``phase_id`` is the index of the active phase.

    Subclasses either pass ``phases`` to the constructor or override
    :meth:`build_phases` (called at every ``reset``, so phases may read the
    observation for live targets).
    """

    def __init__(self, phases: Optional[Sequence[PhaseBase]] = None, cfg: Optional[dict] = None, verbose: bool = False):
        super().__init__(cfg)
        self._phases_arg = list(phases) if phases is not None else None
        self.phases: List[PhaseBase] = []
        self.idx = 0
        self.verbose = verbose
        self._started = False

    def build_phases(self, obs: ObsDict, info: dict) -> List[PhaseBase]:
        if self._phases_arg is None:
            raise NotImplementedError("pass phases= or override build_phases")
        return list(self._phases_arg)

    @property
    def phase_names(self) -> List[str]:
        return [p.name for p in self.phases]

    def reset(self, obs: ObsDict, info: dict) -> None:
        super().reset(obs, info)
        self.phases = self.build_phases(obs, info)
        self.idx = 0
        self._started = False

    def act(self, obs: ObsDict, info: dict, t: int) -> Tuple[Action, int, bool]:
        info = dict(info)
        info["last_action"] = self.last_action
        if self.idx >= len(self.phases):
            return (
                Action.hold(self.last_action.gripper if self.last_action else (GRIPPER_OPEN, GRIPPER_OPEN)),
                len(self.phases) - 1,
                True,
            )
        phase = self.phases[self.idx]
        if not self._started:
            phase.start(obs, info)
            self._started = True
        # advance through phases that are already done (e.g. zero-length)
        while phase.done(obs, info) and self._started:
            if self.verbose:
                print(f"[policy] phase {self.idx} '{phase.name}' done: {phase.done_reason}")
            self.idx += 1
            if self.idx >= len(self.phases):
                act = Action.hold(self.last_action.gripper if self.last_action else (GRIPPER_OPEN, GRIPPER_OPEN))
                self.last_action = act
                return act, len(self.phases) - 1, True
            phase = self.phases[self.idx]
            phase.start(obs, info)
        act = phase.step(obs, info)
        self.last_action = act
        return act, self.idx, False


__all__ = ["DemoPolicy", "PhasedPolicy", "PhaseBase", "MoveL", "Gripper", "Hold", "ee_pose", "joint_pos", "ARM_NAMES"]
