"""Scripted expert of the dough / plug tasks: a dict script executed with the ``MoveL`` / ``Gripper`` primitives.

A *script* (``softbody_geom.dough_pinch.pinch_script``, ``dough_expert.fill_script``, ``plug_pad_scene.plug_pad_script``) is a
list of steps::

    {"op": "open" | "close", "label": str, ["pickup": True], ["stop_width": m]}
    {"op": "move", "xyz": [x, y, z], "yaw": rad, "label": str, ["free": True], ["measure_grip": True]}
    {"op": "wait", "ticks": n}
    {"op": "hold_width", "ticks": n, "width": m}

``move`` waypoints are poses of the *working frame*: the pad-pair frame (direct-sensor tasks: ``xyz`` = the centre between
the gel pads, ``yaw`` = the closing-axis direction) or the tool frame (``xyz`` = the tool's working face, ``yaw`` about z,
tool +z up).  :class:`DoughScriptPolicy` converts them to end-effector targets from the live pad poses (``obs["privileged"]
["pad_poses"]``) or the grip transform, and runs

1. ``init``: hold for ``init_limit`` ticks (the dough settles),
2. the script, one phase per step; a ``move`` that ends more than ``reach_tol`` from its waypoint is repeated up to
   ``max_retries`` times; a ``close`` with ``pickup`` grasps the tool standing in its rack for real and the following
   ``measure_grip`` move records the tool-in-hand pose, which the later waypoints use (tolerances ``grip_tol_mm`` /
   ``grip_tol_deg``),
3. ``settle``: hold until the task reports success or ``settle_ticks`` have passed.

``phase_id`` is 0 during ``init``, ``1 + step index`` during the script and ``len(script) + 1`` while settling.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence

import numpy as np

from ..core import math as m
from ..core.policy import DemoPolicy, Gripper, Hold, MoveL, PhaseBase, ee_pose
from ..core.types import GRIPPER_CLOSE, GRIPPER_OPEN, Action
from ..softbody_geom import dough_expert as ex
from ..softbody_geom import tools as tl
from . import pads as pd
from .scene import build_dough_scene

MOVE_DEFAULTS: Dict[str, Any] = {
    "steps": 60,
    "speed": 0.07,
    "tol": (0.002, 0.01),
    "timeout": 900,
    "stall_patience": 20,
    "stall_move_thresh": 0.0005,
}
"""``MoveL`` settings of the scripted expert (linear interpolation at 0.07 m/s, converge to 2 mm / 0.01)."""
GRIPPER_DEFAULTS: Dict[str, Any] = {"timeout": 40, "settle_threshold": 1e-4}


from .base import grip_to_tool  # noqa: E402,F401  (scene geometry, shared with the task)


class _HoldWidth(PhaseBase):
    """Bang-bang hold of the binary gripper at a gel-face gap: close while wider than ``width``, open while narrower."""

    def __init__(self, ticks: int, width: float, gap_fn: Callable[[dict], float], name: str = "hold_width"):
        self.ticks, self.width, self.gap_fn, self.name = int(ticks), float(width), gap_fn, name
        self._t = 0
        self.command = GRIPPER_CLOSE

    def start(self, obs, info):
        self._t = 0

    def step(self, obs, info) -> Action:
        self._t += 1
        self.command = GRIPPER_CLOSE if self.gap_fn(obs) > self.width else GRIPPER_OPEN
        grip = MoveL._previous_gripper(info)
        grip[0] = self.command
        return Action(np.full(14, np.nan), grip)

    def done(self, obs, info) -> bool:
        return self._t >= self.ticks


class _StopClose(Gripper):
    """A ``close`` that ends as soon as the gel faces are within ``stop_width`` of each other (or the fingers settle)."""

    def __init__(self, stop_width: float, gap_fn: Callable[[dict], float], **kw):
        super().__init__("close", "right", **kw)
        self.stop_width, self.gap_fn = float(stop_width), gap_fn

    def done(self, obs, info) -> bool:
        if self.gap_fn(obs) <= self.stop_width:
            self._done_reason = "stop width reached"
            return True
        return super().done(obs, info)


class DoughScriptPolicy(DemoPolicy):
    """Runs the task's dict script.  Subclasses set :attr:`SCRIPT` (``(plan, params) -> steps``) and may override
    :meth:`build_plan`.

    ``cfg["task"]`` is the task block (also the script's parameter source), ``cfg["policy"]`` the expert settings
    (``init_limit``, ``settle_ticks``, ``reach_tol``, ``max_retries``, ``grip_tol_mm``, ``grip_tol_deg``, ``move``, ``gripper``,
    plus script parameters such as ``hover`` / ``dwell_ticks`` / ``lift_z`` that override the task block's).
    """

    SCRIPT: Optional[Callable[[Dict[str, Any], Dict[str, Any]], List[Dict[str, Any]]]] = None

    def __init__(self, cfg: Optional[dict] = None, task=None, planner=None, verbose: bool = False, **_: Any):
        super().__init__(cfg)
        self.task = task  # optional; the policy reads everything it needs from the observation
        self.planner = planner  # unused: the dough scripts are straight-line interpolations
        self.p: Dict[str, Any] = dict(self.cfg.get("task") or {})
        self.pol: Dict[str, Any] = dict(self.cfg.get("policy") or {})
        self.params: Dict[str, Any] = {**self.p, **{k: v for k, v in self.pol.items() if k not in ("move", "gripper")}}
        self.direct = bool(self.p.get("direct_pads", False))
        self.init_limit = int(self.pol.get("init_limit", 30))
        self.settle_ticks = int(self.pol.get("settle_ticks", 120))
        self.reach_tol = float(self.pol.get("reach_tol", 0.012))
        self.max_retries = int(self.pol.get("max_retries", 2))
        self.grip_tol_mm = float(self.pol.get("grip_tol_mm", 15.0))
        self.grip_tol_deg = float(self.pol.get("grip_tol_deg", 12.0))
        self.move_kw = {**MOVE_DEFAULTS, **(self.pol.get("move") or {})}
        self.move_kw["tol"] = tuple(float(v) for v in self.move_kw["tol"])
        self.grip_kw = {**GRIPPER_DEFAULTS, **(self.pol.get("gripper") or {})}
        cols = self.p.get("colliders") or pd.PAD_COLLIDERS
        self.pad_half_z = float(cols[0]["half"][2])
        self.verbose = bool(verbose)
        self.script: List[Dict[str, Any]] = []
        self.plan: Dict[str, Any] = {}
        self.fail_reason: Optional[str] = None
        self._reset_state()

    # ------------------------------------------------------------------ plan / script
    def build_plan(self, obs, info) -> Dict[str, Any]:
        """Env-frame geometry for the script: the sidecar scene's ``info`` + ``anchor`` + ``kind`` (+ ``tool_start`` for tool tasks)."""
        sc = build_dough_scene(self.p)
        plan = dict(sc.info, anchor=np.asarray(sc.anchor, dtype=np.float64).tolist(), kind=sc.kind)
        for k in ("pinch_offsets", "keep_offsets"):
            if k in sc.extra:
                plan[k] = list(sc.extra[k])
        if not self.direct:
            plan["tool_start"] = np.asarray(obs["privileged"]["tool_pose"], dtype=np.float64).tolist()
        return plan

    def build_script(self, obs, info) -> List[Dict[str, Any]]:
        if self.SCRIPT is None:
            raise NotImplementedError("set SCRIPT or override build_script")
        self.plan = self.build_plan(obs, info)
        return list(self.SCRIPT(self.plan, self.params))

    @property
    def phase_names(self) -> List[str]:
        return ["init"] + [str(s.get("label", s["op"])) for s in self.script] + ["settle"]

    # ------------------------------------------------------------------ lifecycle
    def _reset_state(self) -> None:
        self.stage = "init"
        self.count = 0
        self.idx = 0
        self.phase: Optional[PhaseBase] = None
        self.grip = np.array([GRIPPER_OPEN, GRIPPER_OPEN], dtype=np.int64)
        self.grip_rel = None
        self._pickup = False
        self.retries = 0
        self.fail_reason = None

    def reset(self, obs, info) -> None:
        super().reset(obs, info)
        self._reset_state()
        self.script = self.build_script(obs, info)

    def act(self, obs, info, t: int):
        info = dict(info)
        info["last_action"] = self.last_action
        n = len(self.script)
        if self.stage == "init":
            self.count += 1
            if self.count >= self.init_limit:
                self.stage = "run"
                self._begin_step(obs, info)
            act = Action.hold(self.grip)
            self.last_action = act
            return act, 0, False
        if self.stage == "run":
            for _ in range(n + 2):  # several zero-length steps may finish in one tick
                assert self.phase is not None
                if not self.phase.done(obs, info):
                    break
                if self.verbose:
                    print(
                        f"[dough policy] step {self.idx + 1}/{n} '{self.script[self.idx].get('label')}' done: {self.phase.done_reason}"
                    )
                advance = self._finish_step(obs, info)
                if self.stage != "run":
                    break
                if advance:
                    self.idx += 1
                    self.retries = 0
                    if self.idx >= n:
                        self.stage = "settle"
                        self.count = 0
                        break
                self._begin_step(obs, info)
            if self.stage == "run":
                act = self.phase.step(obs, info)
                self.last_action = act
                return act, self.idx + 1, False
        if self.stage == "settle":
            self.count += 1
            act = Action.hold(self.grip)
            self.last_action = act
            done = bool(info.get("success", False)) or self.count >= self.settle_ticks
            return act, n + 1, done
        act = Action.hold(self.grip)  # failed
        self.last_action = act
        return act, min(self.idx, n - 1) + 1, True

    # ------------------------------------------------------------------ steps
    def _gap(self, obs) -> float:
        return pd.pad_face_gap(np.asarray(obs["privileged"]["pad_poses"], dtype=np.float64), self.pad_half_z)

    def _begin_step(self, obs, info) -> None:
        step = self.script[self.idx]
        op = step["op"]
        label = str(step.get("label", op))
        if step.get("pickup"):
            self._pickup = True
        if op == "move":
            self.phase = MoveL(
                lambda o, i, s=step: self._eef_target(s, o),
                "right",
                mode="interp",
                converge=True,
                gripper=self.grip.copy(),
                name=label,
                **self.move_kw,
            )
        elif op in ("open", "close"):
            self.grip[0] = GRIPPER_CLOSE if op == "close" else GRIPPER_OPEN
            if op == "close" and step.get("stop_width") is not None:
                self.phase = _StopClose(float(step["stop_width"]), self._gap, name=label, **self.grip_kw)
            else:
                self.phase = Gripper(op, "right", name=label, **self.grip_kw)
        elif op == "wait":
            self.phase = Hold(int(step.get("ticks", 0)), gripper=self.grip.copy(), name=label)
        elif op == "hold_width":
            self.phase = _HoldWidth(int(step.get("ticks", 0)), float(step["width"]), self._gap, name=label)
        else:
            raise ValueError(f"unknown script op {op!r}")
        self.phase.start(obs, info)

    def _finish_step(self, obs, info) -> bool:
        """Checks after a phase ended; True = advance to the next step, False = the step is repeated."""
        step = self.script[self.idx]
        if step["op"] == "hold_width":
            self.grip[0] = self.phase.command
        if step["op"] == "move":
            err = self._reach_error(step, obs)
            if err > self.reach_tol:
                self.retries += 1
                if self.verbose:
                    print(f"[dough policy] '{step.get('label')}' stopped {1e3 * err:.0f} mm short (try {self.retries})")
                if self.retries > self.max_retries:
                    self._fail(f"{step.get('label')}: target not reached ({1e3 * err:.0f} mm off)")
                return False
            if step.get("measure_grip"):
                self._measure_grip(obs)
        return True

    def _fail(self, reason: str) -> None:
        self.fail_reason = reason
        self.stage = "failed"
        if self.verbose:
            print(f"[dough policy] failed: {reason}")

    # ------------------------------------------------------------------ frames
    def _eef_target(self, step, obs) -> np.ndarray:
        yaw = float(step.get("yaw", -0.5 * np.pi if self.direct else 0.0))
        if self.direct:
            pads = np.asarray(obs["privileged"]["pad_poses"], dtype=np.float64)
            return pd.eef_for_pad_mid(pads, ee_pose(obs, 0), step["xyz"], yaw)
        if self.grip_rel is not None and not step.get("free"):
            rel_pos, rel_q = self.grip_rel
        else:
            rel_pos, rel_q = self.nominal_grip()
        pos, q = ex.eef_for_tool(step["xyz"], yaw, rel_pos, rel_q)
        return np.concatenate([pos, q])

    def nominal_grip(self):
        return grip_to_tool(
            str(self.p.get("tool_kind", "scraper_tool")),
            self.p.get("eef_to_grip", (0.0, 0.0, 0.177)),
            float(self.p.get("tool_yaw_deg", 0.0)),
        )

    def _reach_error(self, step, obs) -> float:
        if self.direct:
            mid = pd.mid_pose_wxyz(np.asarray(obs["privileged"]["pad_poses"], dtype=np.float64))
            return float(np.linalg.norm(mid[:3] - np.asarray(step["xyz"], dtype=np.float64)))
        if step.get("free") or self._pickup:  # the tool is not in the hand yet / may creep in the grip: check the hand
            return float(np.linalg.norm(ee_pose(obs, 0)[:3] - self._eef_target(step, obs)[:3]))
        tool = np.asarray(obs["privileged"]["tool_pose"], dtype=np.float64)
        return float(np.linalg.norm(tool[:3] - np.asarray(step["xyz"], dtype=np.float64)))

    def _measure_grip(self, obs) -> None:
        """Tool-in-hand pose now (after the pickup lift); the later waypoints use it instead of the nominal grip."""
        eef = ee_pose(obs, 0)
        tool = np.asarray(obs["privileged"]["tool_pose"], dtype=np.float64)
        rel = m.pose_relative(eef, tool)
        nom_pos, nom_q = self.nominal_grip()
        dpos = 1e3 * (rel[:3] - nom_pos)
        dang = float(np.degrees(m.quat_diff_angle(rel[3:7], nom_q)))
        if self.verbose:
            print(f"[dough policy] measured grip vs nominal: dpos {np.round(dpos, 1).tolist()} mm, dang {dang:.1f} deg")
        if float(np.linalg.norm(dpos)) > self.grip_tol_mm or dang > self.grip_tol_deg:
            self.grip_rel = None
            self._fail(
                f"tool not held as planned after the pickup ({np.linalg.norm(dpos):.0f} mm / {dang:.0f} deg off the nominal grip)"
            )
            return
        self.grip_rel = (rel[:3].copy(), rel[3:7].copy())


__all__ = ["DoughScriptPolicy", "grip_to_tool", "MOVE_DEFAULTS", "GRIPPER_DEFAULTS"]
