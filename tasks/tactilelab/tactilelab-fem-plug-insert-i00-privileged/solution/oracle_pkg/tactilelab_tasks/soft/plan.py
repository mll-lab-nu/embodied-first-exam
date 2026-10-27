"""Step plans: the scripted experts of the soft tasks as a :class:`tactilelab_tasks.core.policy.DemoPolicy`.

A plan is a list of :class:`Step` objects.  Each step issues one primitive of :mod:`tactilelab_tasks.core.policy` (a
:class:`MoveL` of the right hand or a :class:`Gripper` command), or nothing (a pure wait), optionally preceded and followed
by idle ticks (the cloth settles, the IK converges).  The plan is built lazily after a short init window, so the stage
targets can read the live soft body; ``on_done`` hooks may insert follow-up steps (a refine move toward a target the arm
fell short of) or end the attempt.

:class:`StepPolicy` runs the plan and turns task-space pinch-frame targets (the centre of the two gel pads and the frame's
rotation) into hand poses with :meth:`tactilelab_tasks.soft.base.SoftTask.eef_pose_for_mid`.  Idle ticks keep commanding the
last streamed hand pose, so the IK keeps converging while the plan waits.

Policy numbers (``cfg["policy"]``)::

    init_limit: 5              idle ticks before the plan is built
    final_hold: 30             ticks of the verdict wait
    reach_tol: 0.004           m; a move is re-issued (refined) when the pinch centre ends further from its target
    max_refine: 2              refine moves per step (a step may override)
    settle_ticks_move: 25      default idle ticks after a move
    move: {steps: 120, speed: 0.04, tol: [0.002, 0.02], timeout: 300}   MoveL parameters
    gripper_timeout: 30        ticks a gripper command waits for the fingers
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

from ..core.policy import DemoPolicy, Gripper, MoveL, PhaseBase
from ..core.types import GRIPPER_CLOSE, GRIPPER_OPEN, Action, ObsDict
from ..softbody_geom import spec

__all__ = ["Step", "StepPolicy", "SNAP", "MOTIONGEN", "INTERP", "mode_name"]

SNAP, MOTIONGEN, INTERP = 0, 1, 2
"""Move modes : snap to the goal, collision-free plan, linear interpolation."""
_MODE_NAMES = {SNAP: "snap", MOTIONGEN: "motiongen", INTERP: "interp"}


def mode_name(mode: Union[int, str]) -> str:
    return _MODE_NAMES[int(mode)] if not isinstance(mode, str) else mode


@dataclass
class Step:
    """One primitive (or pure wait) of a plan.

    Attributes:
        name: phase label (``phase_names`` of the policy, recorded in the dataset).
        build: returns the primitive to run (a :class:`PhaseBase`) or None for an idle-only step.  Evaluated once when the
            step starts, so it may read the live scene.
        on_start: side effect right before ``build``.
        on_done: called when the primitive (and the post idle) finished.  Return None to continue, a list of steps to run
            next (refines / retries), or ``"abort:<reason>"`` to end the plan as failed.
        pre_idle / post_idle: idle ticks before the primitive / after it finished.
    """

    name: str
    build: Callable[[], Optional[PhaseBase]]
    on_start: Optional[Callable[[], None]] = None
    on_done: Optional[Callable[[], Union[None, str, List["Step"]]]] = None
    pre_idle: int = 0
    post_idle: int = 0


class StepPolicy(DemoPolicy):
    """Runs a :class:`Step` plan on a :class:`tactilelab_tasks.soft.base.SoftTask`; subclasses implement :meth:`build_plan`."""

    def __init__(self, task, cfg: Optional[dict] = None, planner=None, verbose: bool = False):
        if isinstance(task, dict) and not isinstance(cfg, dict):  # the registry convention ``Policy(cfg, task)``
            task, cfg = cfg, task
        super().__init__(cfg)
        self.task = task
        p = dict((cfg or {}).get("policy", {}))
        self.p = p
        self.init_limit = int(p.get("init_limit", 5))
        self.final_hold = int(p.get("final_hold", 30))
        self.reach_tol = float(p.get("reach_tol", 0.004))
        self.max_refine = int(p.get("max_refine", 2))
        self.settle_ticks_move = int(p.get("settle_ticks_move", 25))
        mv = dict(p.get("move", {}))
        self.move_steps = int(mv.get("steps", 120))
        self.move_speed = float(mv.get("speed", 0.04))
        self.move_tol = tuple(float(v) for v in mv.get("tol", (0.002, 0.02)))
        self.move_timeout = int(mv.get("timeout", 300))
        self.gripper_timeout = int(p.get("gripper_timeout", 30))
        self.planner = planner
        self.verbose = bool(verbose)
        self.plan: List[Step] = []
        self.idx = 0
        self.aborted: Optional[str] = None
        self.log: List[str] = []
        self._stage = "new"
        self._left = 0
        self._phase: Optional[PhaseBase] = None
        self._started = False
        self._init_count = 0
        self._done = False
        self._hold_targets: List[Optional[np.ndarray]] = [None, None]
        self._gripper = np.array([GRIPPER_OPEN, GRIPPER_OPEN], dtype=np.int64)
        self._gap: Optional[np.ndarray] = None

    # ------------------------------------------------------------------ subclass API
    def build_plan(self) -> List[Step]:
        raise NotImplementedError

    def _log(self, msg: str) -> None:
        self.log.append(msg)
        if self.verbose:
            print(f"[{type(self).__name__}] {msg}", flush=True)

    @property
    def phase_names(self) -> List[str]:
        return [s.name for s in self.plan]

    @property
    def phase(self) -> str:
        if self.aborted is not None:
            return "aborted"
        if self._done:
            return "done"
        return self.plan[self.idx].name if self.plan and self.idx < len(self.plan) else "init"

    # ------------------------------------------------------------------ run
    def reset(self, obs: ObsDict, info: dict) -> None:
        super().reset(obs, info)
        self.plan = []
        self.idx = 0
        self.aborted = None
        self.log = []
        self._stage = "new"
        self._left = 0
        self._phase = None
        self._started = False
        self._init_count = 0
        self._done = False
        self._hold_targets = [None, None]
        self._gripper = np.array([GRIPPER_OPEN, GRIPPER_OPEN], dtype=np.int64)
        self._gap = None
        if not getattr(self.task, "settling", False):
            # the task settles the soft body inside its reset, so the live scene is already there to plan on
            self.plan = list(self.build_plan())

    def _hold(self) -> Action:
        ee = np.full(14, np.nan)
        for a in range(2):
            if self._hold_targets[a] is not None:
                ee[7 * a : 7 * a + 7] = self._hold_targets[a]
        return Action(ee, self._gripper.copy(), None if self._gap is None else self._gap.copy())

    def _emit(self, act: Action) -> Action:
        """Remember the streamed targets / gripper state so idle ticks keep commanding them."""
        for a in range(2):
            tgt = act.arm(a)
            if not np.isnan(tgt).any():
                self._hold_targets[a] = tgt.copy()
            elif self._hold_targets[a] is not None:
                act.ee_target[7 * a : 7 * a + 7] = self._hold_targets[a]
        self._gripper = act.gripper.copy()
        if act.gripper_gap is not None:
            gap = self._gap.copy() if self._gap is not None else np.full(2, np.nan)
            for a in range(2):
                if np.isfinite(act.gripper_gap[a]):
                    gap[a] = act.gripper_gap[a]
            self._gap = gap
        if (
            self._stage == "run"
            and isinstance(self._phase, Gripper)
            and self._phase.gap is None
            and self._gap is not None
        ):
            self._gap[self._phase.arm] = np.nan  # a binary open / close ends the remembered gap of that arm
        if self._gap is not None:
            act.gripper_gap = self._gap.copy()
        self.last_action = act
        return act

    def act(self, obs: ObsDict, info: dict, t: int) -> Tuple[Action, int, bool]:
        info = dict(info)
        info["last_action"] = self.last_action
        if self._done or self.aborted is not None:
            return self._emit(self._hold()), max(len(self.plan) - 1, 0), True
        if self._init_count < self.init_limit or getattr(self.task, "settling", False):
            self._init_count += 1
            return self._emit(self._hold()), -1, False
        if not self.plan:
            self.plan = list(self.build_plan())
            self.idx, self._stage = 0, "new"
            if not self.plan:
                self._done = True
                return self._emit(self._hold()), 0, True
        while self.idx < len(self.plan):
            step = self.plan[self.idx]
            if self._stage == "new":
                self._enter(step)
            if self._stage == "pre":
                if self._left > 0:
                    self._left -= 1
                    return self._emit(self._hold()), self.idx, False
                self._stage = "run" if self._phase is not None else "post"
                self._left = step.post_idle if self._stage == "post" else 0
                continue
            if self._stage == "run":
                if not self._started:
                    self._phase.start(obs, info)
                    self._started = True
                if self._phase.done(obs, info):
                    if self.verbose:
                        self._log(f"{step.name}: {self._phase.done_reason}")
                    self._stage, self._left = "post", step.post_idle
                    continue
                return self._emit(self._phase.step(obs, info)), self.idx, False
            if self._left > 0:
                self._left -= 1
                return self._emit(self._hold()), self.idx, False
            finished = self._complete(step)
            if finished:
                return self._emit(self._hold()), min(self.idx, len(self.plan) - 1), True
        self._done = True
        return self._emit(self._hold()), len(self.plan) - 1, True

    def _enter(self, step: Step) -> None:
        self._log(f"stage {step.name} ({self.idx + 1}/{len(self.plan)})")
        if step.on_start is not None:
            step.on_start()
        self._phase = step.build()
        self._started = False
        self._left = step.pre_idle
        self._stage = "pre"

    def _complete(self, step: Step) -> bool:
        """Advance after a step finished; True when the plan ended (success or abort)."""
        outcome = step.on_done() if step.on_done is not None else None
        if isinstance(outcome, str) and outcome.startswith("abort:"):
            self.aborted = outcome[6:]
            self._log(f"aborted after {step.name}: {self.aborted}")
            return True
        if isinstance(outcome, list):
            self.plan[self.idx + 1 : self.idx + 1] = outcome
        self.idx += 1
        self._stage = "new"
        self._phase = None
        if self.idx >= len(self.plan):
            self._done = True
            self._log("plan complete")
            return True
        return False

    # ------------------------------------------------------------------ primitives
    def R_pinch(self, approach: Sequence[float], normal: Sequence[float]) -> np.ndarray:
        """Pinch-frame rotation (env frame) with the hand's approach axis along ``approach`` and the closing axis along
        ``normal``."""
        a_loc = self.task.approach_axis_in_mid()
        Bl = spec.frame_from_axes(a_loc, np.array([0.0, 0.0, 1.0]))
        Bw = spec.frame_from_axes(approach, normal)
        return Bw @ Bl.T

    def move_mid(
        self,
        mode: Union[int, str],
        mid_pos: Sequence[float],
        R_mid: np.ndarray,
        converge: Optional[bool] = None,
        name: str = "move",
        **kw,
    ) -> MoveL:
        """A :class:`MoveL` of the right hand that brings the pinch frame to ``(mid_pos, R_mid)``."""
        mode_s = mode_name(mode)
        pose = self.task.eef_pose_for_mid(mid_pos, R_mid)
        steps = int(kw.pop("steps", self.move_steps))
        speed = float(kw.pop("speed", self.move_speed))
        # the converge timeout counts from the end of the streamed path (a long slow move must not time out while streaming)
        dist = float(np.linalg.norm(self.task.eef_pose()[:3] - pose[:3]))
        stream = max(steps, int(np.ceil(dist / (speed / 60.0)))) if speed > 0.0 else steps
        return MoveL(
            pose,
            "right",
            mode=mode_s,
            steps=steps,
            speed=speed,
            tol=kw.pop("tol", self.move_tol),
            timeout=kw.pop("timeout", self.move_timeout) + stream,
            converge=bool(mode_s != "interp") if converge is None else bool(converge),
            planner=self.planner,
            name=name,
            **kw,
        )

    def hand(self, what: str, gap: Optional[float] = None) -> Gripper:
        if what == "close" and gap is not None:
            return Gripper(float(gap), "right", timeout=self.gripper_timeout, name="close")
        return Gripper(what, "right", timeout=self.gripper_timeout, name=what)

    # ------------------------------------------------------------------ steps
    def step_move(
        self,
        name: str,
        mode: Union[int, str],
        pos_fn: Callable[[], Sequence[float]],
        R_fn: Callable[[], np.ndarray],
        refine: Optional[int] = None,
        tol: Optional[float] = None,
        track: bool = False,
        converge: Optional[bool] = None,
        **kw,
    ) -> Step:
        """A pinch-frame move.  When it ends, the pinch centre is compared with the target: a miss by more than ``tol``
        re-issues the move (at most ``refine`` times; the streamed IK target is tracked with a lag).  ``track`` compares
        with ``pos_fn()`` re-evaluated now, for a target that moves while the arm goes."""
        refine = self.max_refine if refine is None else int(refine)
        tol = self.reach_tol if tol is None else float(tol)
        kw.setdefault("post_idle", self.settle_ticks_move)
        holder: Dict[str, Any] = {}

        def build():
            holder["target"] = np.asarray(pos_fn(), dtype=np.float64)
            return self.move_mid(mode, holder["target"], R_fn(), converge=converge, name=name)

        def on_done():
            c, _ = self.task.mid_frame()
            target = np.asarray(pos_fn(), dtype=np.float64) if track else holder["target"]
            err = float(np.linalg.norm(c - target))
            if err > tol and refine > 0:
                self._log(
                    f"{name}: {1e3 * err:.1f} mm from the {'current ' if track else ''}target, refining ({refine} left)"
                )
                return [
                    self.step_move(
                        f"{name}_refine", INTERP, pos_fn, R_fn, refine=refine - 1, tol=tol, track=track, **kw
                    )
                ]
            if err > 3 * tol:
                self._log(f"{name}: ended {1e3 * err:.1f} mm from the target")
            return None

        return Step(name=name, build=build, on_done=on_done, **kw)

    def step_hand(self, name: str, what: str, gap: Optional[float] = None, **kw) -> Step:
        """``what`` = ``close`` / ``open``.  ``gap`` (m, with ``close``): a partial open - the fingers stop at that gel-face
        gap instead of swinging fully open (:meth:`SoftTask.set_gripper_gap`).  A plain ``close`` uses the task's calibrated
        pinch close when it has one (:meth:`SoftTask.pinch_close_gap`)."""

        def build():
            if what == "close" and gap is not None:
                return self.hand("close", self.task.set_gripper_gap(float(gap)))
            if what == "close":
                g = self.task.pinch_close_gap()
                if g is not None:
                    self._log(
                        f"{name}: close to a joint gap of {1e3 * g:.2f} mm (thickness {1e3 * self.task.grasp_thickness():.2f} mm)"
                    )
                return self.hand("close", g)
            return self.hand("open")

        return Step(name=name, build=build, **kw)

    def step_wait(self, name: str, ticks: int, on_done: Optional[Callable[[], Any]] = None) -> Step:
        return Step(name=name, build=lambda: None, post_idle=int(ticks), on_done=on_done)

    def verdict_step(self) -> Step:
        """Last step: wait ``final_hold`` ticks, then ask the task for the verdict."""

        def done():
            ok = bool(self.task.is_success())
            reason = getattr(self.task, "truncation_reason", None)
            vals = {
                k: (
                    round(float(v), 4)
                    if np.ndim(v) == 0
                    else np.round(np.asarray(v, dtype=np.float64).ravel()[:6], 4).tolist()
                )
                for k, v in self.task.metrics().items()
                if k != "truncated"
            }
            self._log(
                f"verdict: {'success' if ok else 'FAILED'}" + (f" ({reason})" if reason else "") + f" metrics {vals}"
            )
            return None if ok else "abort:the task did not confirm success" + (f" ({reason})" if reason else "")

        return Step(name="verdict", build=lambda: None, post_idle=self.final_hold, on_done=done)
