"""Scripted skills of the rigid assembly tasks: grasp, insert, screw.

Each skill is a :class:`tactilelab_tasks.core.policy.PhaseBase` that runs a small
state machine on top of the two primitives ``MoveL`` (free-space legs, streamed
along an interpolated path) and ``Gripper`` (open / close with settle detection).
The contact-rich legs (lateral servo, descent ramp, screw followers) emit one
end-effector target per control tick, i.e. a one-step snap ``MoveL`` each tick.

All skills read object poses from the task (privileged state, the same signals
the scripted experts use); none of them reads the tactile images.

Skill summaries
---------------
``GraspSkill``
    label library -> clearance / pad-centre filters -> optional random subset ->
    candidate closest to the current wrist orientation; pre-grasp (backed off
    along the tool axis) -> descent -> close -> settle -> retrieval (world +Z).
``InsertSkill``
    preinsert (tip hovering ``preinsert_clearance`` above the hole) -> align
    (lateral servo until centred for ``hold_centered_steps``) -> descent ramp
    with a press ceiling (``d_cmd <= d_measured + press_allowance``), lateral /
    yaw followers past the capture depth, grip-slip compensation, stall unlock
    sweep, jam detection -> release in place (or when seated) -> retreat.
``ScrewSkill``
    three followers while turning: ``psi_cmd = max(psi_cmd, min(psi_cmd + yaw_rate,
    psi_meas + yaw_bias))``, ``d_cmd = d_meas + engage_press``, lateral pass-through;
    REWIND (open -> recenter -> unwind -> re-close) on wind budget / slip / thread
    jump / rotation stall / feed stall; ASSEMBLED on a feed stall at depth.
``ExtractSkill``
    the insert stroke reversed: the part starts captured in a bore (a rack), the
    grip and orientation are frozen as they are, the depth ramps from the live value
    up and out of the bore under a pull ceiling (``d_cmd >= d_measured -
    press_allowance``) with the lateral follower, then one fast lift once the tip
    has cleared the entry; finishes still held.
``PushSkill``
    staged push of a released part along a world axis toward ``push_target``:
    approach (raised, behind the push start) -> prepush (axis staging point) ->
    stroke at ``speed`` m/tick with the waypoint never more than ``lead_max`` ahead
    of the measured hand (quasi-static press); a stage ends on the axis target, an
    object coordinate, an axis alignment, a press-gated object stall or its step
    budget; exit corridors (retreat, lift) between stages and before the finish.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from ..core import math as m
from ..core.policy import Gripper, Hold, MoveL, PhaseBase, ee_pose, joint_pos
from ..core.types import CONTROL_DT, GRIPPER_CLOSE, GRIPPER_OPEN, Action, ObsDict
from . import geometry as G

__all__ = ["GraspSkill", "InsertSkill", "ScrewSkill", "ReachSkill", "ExtractSkill", "PushSkill", "SkillBase"]

_TICK_HZ = 1.0 / CONTROL_DT


def _cfg(d: Dict[str, Any], key: str, default):
    v = d.get(key, default)
    return default if v is None else v


# --------------------------------------------------------------------------- base
class SkillBase(PhaseBase):
    """Common machinery: right-arm action helpers and sub-phase delegation."""

    name = "skill"

    def __init__(self, task, cfg: Optional[Dict[str, Any]] = None, part: int = 0, verbose: bool = True):
        self.task = task
        self.cfg = dict(cfg or {})
        self.part = int(part)
        self.verbose = verbose
        self.result: str = ""
        self.state: str = ""
        self._finished = False
        self._sub: Optional[PhaseBase] = None
        self._t = 0
        self._grip = GRIPPER_OPEN

    # -- helpers
    def log(self, msg: str) -> None:
        if self.verbose:
            print(f"[{self.name}] {msg}", flush=True)

    def act(self, pose7: Optional[np.ndarray], grip: int, gap: Optional[float] = None) -> Action:
        """Action: right arm to ``pose7`` (None = hold), left arm held, right gripper ``grip``."""
        ee = np.full(14, np.nan)
        if pose7 is not None:
            ee[:7] = np.asarray(pose7, dtype=np.float64).reshape(7)
        g = np.array([int(grip), GRIPPER_OPEN], dtype=np.int64)
        gg = None
        if gap is not None:
            gg = np.full(2, np.nan)
            gg[0] = float(gap)
        self._grip = int(grip)
        return Action(ee, g, gg)

    def hold(self, grip: Optional[int] = None) -> Action:
        return self.act(None, self._grip if grip is None else grip)

    def set_state(self, state: str, msg: str = "") -> None:
        self.state = state
        self.log(f"part {self.part} -> {state}" + (f" ({msg})" if msg else ""))

    def finish(self, result: str) -> None:
        self.result = result
        self._finished = True
        self.log(f"part {self.part} finished: {result}")

    def run_sub(self, sub: PhaseBase, obs: ObsDict, info: dict) -> None:
        self._sub = sub
        sub.start(obs, info)

    def sub_done(self, obs: ObsDict, info: dict) -> bool:
        return self._sub is not None and self._sub.done(obs, info)

    def sub_step(self, obs: ObsDict, info: dict) -> Action:
        a = self._sub.step(obs, info)
        a.gripper = np.array([self._grip, GRIPPER_OPEN], dtype=np.int64)
        return a

    @staticmethod
    def _with_grip(action: Action, grip: int) -> Action:
        action.gripper = np.array([int(grip), GRIPPER_OPEN], dtype=np.int64)
        return action

    # -- phase API
    def start(self, obs: ObsDict, info: dict) -> None:
        self._t = 0
        self._finished = False
        self.result = ""
        self.task.set_active_part(self.part)

    def done(self, obs: ObsDict, info: dict) -> bool:
        return self._finished

    @property
    def done_reason(self) -> Optional[str]:
        return self.result or None


# --------------------------------------------------------------------------- reach / rehome
class ReachSkill(SkillBase):
    """Fly the right arm back to the episode-start pose (rotated toward the part)."""

    name = "reach"

    def __init__(self, task, cfg=None, part: int = 0, skip_tol: float = 0.02, **kw):
        super().__init__(task, cfg, part, **kw)
        self.skip_tol = float(skip_tol)

    def start(self, obs, info):
        super().start(obs, info)
        home = self.task.home_eef_pose(self.part)
        cur = ee_pose(obs, 0)
        if float(np.linalg.norm(cur[:3] - home[:3])) <= self.skip_tol:
            self.finish("already home")
            return
        self.run_sub(
            MoveL(
                home,
                "right",
                steps=int(_cfg(self.cfg, "steps", 120)),
                speed=float(_cfg(self.cfg, "speed", 0.3)),
                converge=True,
                tol=(0.004, 0.03),
                timeout=400,
                name="rehome",
            ),
            obs,
            info,
        )
        self.set_state("rehome")

    def step(self, obs, info) -> Action:
        self._t += 1
        if self._finished:
            return self.hold()
        if self.sub_done(obs, info):
            self.finish("rehomed")
            return self.hold()
        return self.sub_step(obs, info)


# --------------------------------------------------------------------------- grasp
class GraspSkill(SkillBase):
    """Grasp the part from its annotated end-effector label library.

    Config keys (``grasp`` block): ``pre_grasp_offset`` (0.15), ``retrieval_offset``
    (0.3), ``label_sample`` (0 = deterministic best, K = random subset of K labels),
    ``axis_offset_max`` (jaw-axis clearance filter, None = off), ``pad_center_local`` /
    ``pad_center_tol`` / ``pad_offset`` (pad-centre filter), ``pre_grasp_steps`` (120),
    ``grasp_steps`` (120), ``close_settle`` (30), ``speed`` (0.3 m/s cap),
    ``lateral_weight`` (20: penalty per metre of pad-centre offset from the part axis,
    so the part lands inside the gel field of view), ``finger_vel_limit`` /
    ``finger_effort_limit`` (episode-wide gentle jaws applied before the close; 0 =
    stock drive, restored by the task at reset), ``finger_stiffness`` / ``finger_damping``
    (finger PD override; a very stiff gain saturates the drive = constant-force jaw).
    """

    name = "grasp"

    def __init__(self, task, cfg=None, part: int = 0, skip_lift: bool = False, seed: int = 0, **kw):
        super().__init__(task, cfg, part, **kw)
        self.skip_lift = bool(skip_lift)
        self.seed = int(seed)
        self.grasp_pose: Optional[np.ndarray] = None
        self.label_index: int = -1

    # -- candidate selection
    def select(self, obs: ObsDict) -> np.ndarray:
        c = self.cfg
        lib = self.task.grasp_candidates(self.part)
        if len(lib) == 0:
            raise RuntimeError(f"part {self.part}: no grasp labels")
        obj = self.task.held_pose(self.part)
        idx = np.arange(len(lib))
        local = lib
        keep = G.pad_center_filter(
            local,
            c.get("pad_center_local"),
            float(_cfg(c, "pad_offset", 0.1777)),
            float(_cfg(c, "pad_center_tol", 0.02)),
        )
        local, idx = local[keep], idx[keep]
        world = G.candidates_world(local, obj)
        keep = G.clearance_filter(world, obj, c.get("axis_offset_max"))
        world, idx = world[keep], idx[keep]
        k = int(_cfg(c, "label_sample", 0))
        if 0 < k < len(world):
            rng = np.random.default_rng(self.seed * 1000 + self.part)
            pick = np.sort(rng.choice(len(world), size=k, replace=False))
            world, idx = world[pick], idx[pick]
        cur = ee_pose(obs, 0)
        up = np.array([0.0, 0.0, 1.0])
        axis = m.quat_rotate(obj[3:7], [0.0, 0.0, 1.0])
        pad_off = float(_cfg(c, "pad_offset", 0.1777))
        w_lat = float(_cfg(c, "lateral_weight", 20.0))
        cost = []
        for w in world:
            tool_z = m.quat_rotate(w[3:7], [0.0, 0.0, 1.0])
            pad = w[:3] + tool_z * pad_off - obj[:3]
            lat = pad - axis * float(
                np.dot(pad, axis)
            )  # pad centre off the part axis -> part leaves the gel field of view
            cost.append(
                m.quat_distance(w[3:7], cur[3:7])
                + 2.0 * max(0.0, float(np.dot(tool_z, up)))
                + w_lat * float(np.linalg.norm(lat))
            )
        best = int(np.argmin(cost))
        self.label_index = int(idx[best])
        self.log(
            f"part {self.part}: {len(lib)} labels, {len(world)} candidates after filters, picked label {self.label_index}"
        )
        return world[best]

    def start(self, obs, info):
        super().start(obs, info)
        c = self.cfg
        self.grasp_pose = self.select(obs)
        self.pre_pose = G.pose_backward_along_z(self.grasp_pose, float(_cfg(c, "pre_grasp_offset", 0.15)))
        self.lift_pose = G.pose_up(self.grasp_pose, float(_cfg(c, "retrieval_offset", 0.3)))
        vel_lim, eff_lim = float(_cfg(c, "finger_vel_limit", 0.0)), float(_cfg(c, "finger_effort_limit", 0.0))
        if (vel_lim > 0.0 or eff_lim > 0.0) and hasattr(self.task, "set_finger_limits"):
            self.task.set_finger_limits(vel_lim, eff_lim)
            self.log(f"gentle jaws: finger velocity {vel_lim} m/s, effort {eff_lim} N (0 = stock)")
        k_f, d_f = float(_cfg(c, "finger_stiffness", 0.0)), float(_cfg(c, "finger_damping", 0.0))
        if (k_f > 0.0 or d_f > 0.0) and hasattr(self.task, "set_finger_gains"):
            self.task.set_finger_gains(k_f, d_f)
            self.log(f"finger gains: stiffness {k_f}, damping {d_f} (constant-force jaw when the drive saturates)")
        self._grip = GRIPPER_OPEN
        self._begin_pre(obs, info)

    def _begin_pre(self, obs, info):
        self.set_state("pre_grasp")
        self.run_sub(
            MoveL(
                self.pre_pose,
                "right",
                steps=int(_cfg(self.cfg, "pre_grasp_steps", 120)),
                speed=float(_cfg(self.cfg, "speed", 0.3)),
                converge=True,
                tol=(0.004, 0.03),
                timeout=int(_cfg(self.cfg, "pre_grasp_timeout", 400)),
                name="pre_grasp",
            ),
            obs,
            info,
        )

    def step(self, obs, info) -> Action:
        self._t += 1
        if self._finished:
            return self.hold()
        c = self.cfg
        if self.state == "pre_grasp":
            if self.sub_done(obs, info):
                self.set_state("grasp", self._sub.done_reason or "")
                self.run_sub(
                    MoveL(
                        self.grasp_pose,
                        "right",
                        steps=int(_cfg(c, "grasp_steps", 120)),
                        converge=True,
                        tol=(0.002, 0.02),
                        timeout=300,
                        name="grasp",
                    ),
                    obs,
                    info,
                )
            return self.sub_step(obs, info)
        if self.state == "grasp":
            if self.sub_done(obs, info):
                self.set_state("close", self._sub.done_reason or "")
                self._grip = GRIPPER_CLOSE
                self.run_sub(Gripper("close", "right", timeout=int(_cfg(c, "close_timeout", 30))), obs, info)
            return self.sub_step(obs, info)
        if self.state == "close":
            if self.sub_done(obs, info):
                self.set_state("settle")
                self.run_sub(Hold(int(_cfg(c, "close_settle", 30))), obs, info)
            return self.sub_step(obs, info)
        if self.state == "settle":
            if self.sub_done(obs, info):
                if self.skip_lift:
                    self.finish("grasped in place")
                    return self.hold()
                self.set_state("retrieval")
                self.run_sub(
                    MoveL(
                        self.lift_pose,
                        "right",
                        steps=int(_cfg(c, "retrieval_steps", 120)),
                        speed=float(_cfg(c, "speed", 0.3)),
                        converge=True,
                        tol=(0.005, 0.03),
                        timeout=400,
                        name="retrieval",
                    ),
                    obs,
                    info,
                )
            return self.sub_step(obs, info)
        if self.state == "retrieval":
            if self.sub_done(obs, info):
                self.finish("grasped")
                return self.hold()
            return self.sub_step(obs, info)
        return self.hold()


# --------------------------------------------------------------------------- insert
INSERT_DEFAULTS: Dict[str, Any] = {
    "preinsert_clearance": 0.025,
    "preinsert_max_steps": 900,
    "preinsert_steps": 120,
    "preinsert_speed": 0.2,
    "insert_stop_depth": None,
    "seat_margin": 0.006,
    "retract_height": 0.0,
    "insert_max_steps": 3000,
    "insert_descent_substeps": 80,
    "insert_yaw_offset_deg": 0.0,
    "closing_align_dir": None,
    "closing_axis_local": [1.0, 0.0, 0.0],
    "align_tol_deg": 6.0,
    "axis_abort_deg": 15.0,
    "align_max_steps": 300,
    "hold_centered_steps": 8,
    "lateral_gain": 0.6,
    "lateral_step_max": 0.004,
    "lateral_deadband": 0.0015,
    "lateral_deadband_inbore": None,
    "servo_track_thresh": 0.03,
    "hold_decay": 0.9,
    "press_allowance": 0.003,
    "lateral_freeze_depth": 0.002,
    "lateral_follow": False,
    "lateral_follow_alpha": 0.05,
    "yaw_follow_alpha": 0.0,
    "unlock_sweep": False,
    "unlock_e": 0.0004,
    "unlock_sweep_dps": -30.0,
    "unlock_break": 0.0005,
    "unlock_max_sweeps": 2.0,
    "hold_stall_window": 20,
    "hold_stall_eps": 0.0003,
    "release_min_depth": None,
    "erode_jam": 0.0,
    "slip_jam": 0.006,
    "grip_slip_comp": False,
    "end_held": False,
    "end_held_release": False,
    "release_vel_limit": 0.0,
    "press_effort": 0.0,
    "press_effort_rest": 0.0,
    "seat_margin_success": 0.002,
    "success_xy": 0.006,
    "success_axis_deg": 12.0,
    "release_depth_line": None,
    "release_dwell_steps": 10,
    "finish_wait_release": False,
    "finish_wait_max": 600,
    "abort_retract": 0.08,
    "yaw_reclock": False,
    "reclock_dps": 2.0,
    "reclock_break": 0.001,
    "reclock_min_depth": -0.010,
    "reclock_max_depth": 0.018,
    "reclock_press": 0.0005,
    "max_reclocks": 100,
    "reclock_erode": 0.002,
    "reclock_lift": 0.0025,
    "reclock_step_deg": 1.0,
    "reclock_tilt_pause_deg": 4.0,
    "reclock_tilt_cancel_deg": 4.0,
    "reclock_region_deg": 15.0,
    "reclock_neighbor": None,
    "reclock_pitch_deg": 9.0,
    "track_print_every": 60,
    # descent shaping and the stop-depth release doors (plug, drawer)
    "descent_ease_pow": 1.0,
    "release_at_stop": False,
    "release_seated_free": False,
    "eef_stop_axial": 0.0,
    "fingertip_stop_axial": 0.0,
    "fingertip_offset": 0.195,
}


class InsertSkill(SkillBase):
    """Insert the held part into its slot (see the module docstring).

    Release doors beyond the seated check: ``release_depth_line`` (measured depth past
    the line for ``release_dwell_steps``), ``release_at_stop`` (the release waits until
    the depth has dwelt ``release_dwell_steps`` ticks within ``seat_margin`` of
    ``insert_stop_depth``), ``release_seated_free`` (with ``release_at_stop``: reaching
    that band, or the clearance stop below, opens the gate on its own), and the
    clearance stops ``eef_stop_axial`` / ``fingertip_stop_axial`` (the wrist, or the
    fingertips ``fingertip_offset`` down the tool axis, this close to the hole plane
    along the bore axis turn the live depth into the stop depth so the hand never
    rams the target's face). ``descent_ease_pow`` > 1 slows the ramp toward its end.
    """

    name = "insert"

    def __init__(self, task, cfg=None, part: int = 0, **kw):
        merged = dict(INSERT_DEFAULTS)
        merged.update({k: v for k, v in (cfg or {}).items()})
        super().__init__(task, merged, part, **kw)
        c = self.cfg
        self.p = {k: c[k] for k in INSERT_DEFAULTS}
        db_in = c.get("lateral_deadband_inbore")
        self.p["lateral_deadband_inbore"] = float(c["lateral_deadband"]) if db_in is None else float(db_in)
        self._closing_align_dir = (
            None
            if c.get("closing_align_dir") is None
            else np.asarray(c["closing_align_dir"], dtype=np.float64) / np.linalg.norm(c["closing_align_dir"])
        )
        self._closing_axis_local = np.asarray(c.get("closing_axis_local") or [1.0, 0.0, 0.0], dtype=np.float64)

    # -- geometry helpers
    def _geo(self):
        return self.task.geometry(self.part)

    def _desired_object_quat(self, geo) -> np.ndarray:
        """Align the held part's full frame to the target frame (axis + cross-section yaw)."""
        target_q = self.task.target_pose(self.part)[3:7]
        minus_z = m.quat_rotate(target_q, [0.0, 0.0, -1.0])
        target_q = m.quat_mul(G.quat_align(minus_z, geo["n_w"]), target_q)
        axis_local = self.task.held_axis(self.part).direction
        target_q = m.quat_mul(target_q, G.quat_align(axis_local, [0.0, 0.0, -1.0]))
        yaw_off = float(self.p["insert_yaw_offset_deg"])
        if self._closing_align_dir is not None:
            if self._closing_align_offset is None:
                n_w = geo["n_w"]
                held_q = self.task.held_pose(self.part)[3:7]
                eef_q = self.task.eef_pose()[3:7]
                closing_w = m.quat_rotate(eef_q, self._closing_axis_local)
                closing_obj = m.quat_rotate(m.quat_conjugate(held_q), closing_w)
                cp = m.quat_rotate(target_q, closing_obj)
                cp = cp - np.dot(cp, n_w) * n_w
                dp = self._closing_align_dir - np.dot(self._closing_align_dir, n_w) * n_w
                if np.linalg.norm(cp) < 1e-6 or np.linalg.norm(dp) < 1e-6:
                    self._closing_align_offset = yaw_off
                else:
                    cp /= np.linalg.norm(cp)
                    dp /= np.linalg.norm(dp)
                    delta = math.degrees(math.atan2(float(np.dot(n_w, np.cross(cp, dp))), float(np.dot(cp, dp))))
                    self._closing_align_offset = (delta + 90.0) % 180.0 - 90.0
                    self.log(f"closing-align offset {self._closing_align_offset:+.1f} deg")
            yaw_off = self._closing_align_offset
        if self._closing_align_dir is not None or abs(yaw_off) > 1e-6:
            if abs(yaw_off) > 1e-6:
                target_q = m.quat_mul(m.quat_from_axis_angle(geo["n_w"], math.radians(yaw_off)), target_q)
            return m.quat_normalize(target_q)
        held_q = self.task.held_pose(self.part)[3:7]
        cand2 = m.quat_mul(m.quat_from_axis_angle(geo["n_w"], math.pi), target_q)
        return m.quat_normalize(cand2 if abs(np.dot(cand2, held_q)) > abs(np.dot(target_q, held_q)) else target_q)

    def _live_t_e2o(self) -> np.ndarray:
        return G.relative_pose(self.task.eef_pose(), self.task.held_pose(self.part))

    def _eef_for_depth(self, d_along: float, geo, t_e2o, q_des) -> np.ndarray:
        target_tip = geo["top_w"] + geo["n_w"] * float(d_along)
        obj = G.object_pose_for_tip(target_tip, q_des, self.tip_offset)
        return G.eef_from_object(obj, t_e2o)

    # -- lifecycle
    def start(self, obs, info):
        super().start(obs, info)
        p = self.p
        self.tip_offset = self.task.held_axis(self.part).head.copy()
        self._closing_align_offset = None
        self._insert_step = 0
        self._aligned = False
        self._descent_step = 0
        self._centered = 0
        self._lat_offset = np.zeros(3)
        self._last_cmd: Optional[np.ndarray] = None
        self._t_e2o_frozen = None
        self._q_des_frozen = None
        self._depth_hist: List[float] = []
        self._jammed = False
        self._stop_settle = 0
        self._depth_max = 0.0
        self._last_signed = 0.0
        self._last_axis = 0.0
        self._last_slip = 0.0
        self._unlock_on = False
        self._unlock_az = math.radians(135.0)
        self._unlock_total = 0.0
        self._unlock_ref = 0.0
        self._release_settle = 0
        self._depth_line_settle = 0
        self._finish_waited = 0
        self._aborting = False
        self._abort_reason = ""
        self._press_boosted = False
        self._yawu_on = False
        self._yawu_locked = 0.0
        self._yawu_target = None
        self._yawu_ref = 0.0
        self._yawu_dir = 1.0
        self._yawu_hist: List[float] = []
        self._reclocks = 0
        self._release_cap_on = False
        self._eef_stop_hit = False
        self._grip = GRIPPER_CLOSE
        geo = self._geo()
        target_tip = geo["top_w"] - geo["n_w"] * float(p["preinsert_clearance"])
        q_des = self._desired_object_quat(geo)
        pre = G.eef_from_object(G.object_pose_for_tip(target_tip, q_des, self.tip_offset), self._live_t_e2o())
        self.set_state("preinsert")
        self.run_sub(
            MoveL(
                pre,
                "right",
                steps=int(p["preinsert_steps"]),
                speed=float(p["preinsert_speed"]),
                converge=True,
                tol=(0.003, 0.02),
                timeout=int(p["preinsert_max_steps"]),
                name="preinsert",
            ),
            obs,
            info,
        )

    # -- phases
    def step(self, obs, info) -> Action:
        self._t += 1
        if self._finished:
            return self.hold()
        if self.state == "preinsert":
            if self.sub_done(obs, info):
                self.set_state("insert", self._sub.done_reason or "")
                return self._insert_tick(obs)
            return self.sub_step(obs, info)
        if self.state == "insert":
            return self._insert_tick(obs)
        if self.state == "open":
            if not self.sub_done(obs, info):
                return self.sub_step(obs, info)
            if self.p["finish_wait_release"] and not self._aborting and not self.task.finish_release_done():
                self._finish_waited += 1
                if self._finish_waited <= int(self.p["finish_wait_max"]):
                    return self.hold()
            self._clear_release_cap()
            self._begin_leave(obs, info)
            return self.hold() if self._sub is None else self.sub_step(obs, info)
        if self.state == "leave":
            if self._sub is None or self.sub_done(obs, info):
                if self._aborting:
                    self.finish(f"aborted: {self._abort_reason}")
                elif self.p["end_held"]:
                    self.finish("released, standing")
                else:
                    self.finish("released, leave complete")
                return self.hold()
            return self.sub_step(obs, info)
        return self.hold()

    def _begin_open(self, reason: str) -> None:
        self._restore_press_effort()
        self._apply_release_cap()
        self.task.note_finish_release()
        self._grip = GRIPPER_OPEN
        self.set_state("open", reason)
        self._pending_open = True

    def _begin_leave(self, obs, info) -> None:
        self.set_state("leave")
        h = float(self.p["abort_retract"]) if self._aborting else float(self.p["retract_height"])
        if h > 1e-6:
            target = G.pose_up(ee_pose(obs, 0), h)
            self.run_sub(
                MoveL(
                    target, "right", steps=120, speed=0.1, converge=True, tol=(0.005, 0.05), timeout=400, name="leave"
                ),
                obs,
                info,
            )
        else:
            self._sub = None

    def _abort(self, reason: str, obs, info) -> Action:
        self._aborting = True
        self._abort_reason = reason
        self.log(f"ABORT ({reason}) - releasing and leaving")
        self._begin_open(reason)
        self.run_sub(Gripper("open", "right", timeout=30), obs, info)
        return self.sub_step(obs, info)

    # -- finger limits
    def _apply_release_cap(self) -> None:
        v = float(self.p["release_vel_limit"])
        if v > 0.0 and not self._release_cap_on:
            self.task.set_finger_limits(v, 0.0)
            self._release_cap_on = True

    def _clear_release_cap(self) -> None:
        if self._release_cap_on:
            self.task.restore_finger_limits()
            self._release_cap_on = False

    def _restore_press_effort(self) -> None:
        if self._press_boosted and float(self.p["press_effort_rest"]) > 0.0:
            self._press_boosted = False
            self.task.set_finger_limits(0.0, float(self.p["press_effort_rest"]))

    # -- the per-tick insert controller
    def _insert_tick(self, obs) -> Action:
        p = self.p
        geo = self._geo()
        n_w, top_w, bore = geo["n_w"], geo["top_w"], float(geo["depth"])
        held = self.task.held_pose(self.part)
        axis_now = m.quat_rotate(held[3:7], self.task.held_axis(self.part).direction)
        axis_ang = G.angle_between_deg(axis_now, n_w)
        tip_live = held[:3] + m.quat_rotate(held[3:7], self.tip_offset)
        signed_live, lateral_live, lat_vec = G.signed_depth_lateral(tip_live, top_w, n_w)
        self._last_signed, self._last_axis = signed_live, axis_ang
        self._insert_step += 1
        eef_now = self.task.eef_pose()
        tracking = self._last_cmd is None or float(np.linalg.norm(eef_now[:3] - self._last_cmd[:3])) <= float(
            p["servo_track_thresh"]
        )
        step_max = float(p["lateral_step_max"])

        def clamp(v):
            nrm = float(np.linalg.norm(v))
            return v * (step_max / (nrm + 1e-9)) if nrm > step_max else v

        def servo(decay: float, db: float):
            if lateral_live > db and tracking:
                self._lat_offset = self._lat_offset * decay + clamp(-float(p["lateral_gain"]) * lat_vec)

        obs_info: dict = {}
        if axis_ang > float(p["axis_abort_deg"]) and self._insert_step > 1:
            return self._abort(f"tilt {axis_ang:.1f} deg > {p['axis_abort_deg']}", obs, obs_info)

        if not self._aligned:
            servo(float(p["hold_decay"]), float(p["lateral_deadband"]))
            if axis_ang <= float(p["align_tol_deg"]) and lateral_live <= float(p["lateral_deadband"]):
                self._centered += 1
            else:
                self._centered = 0
            if self._centered >= int(p["hold_centered_steps"]) or self._insert_step >= int(p["align_max_steps"]):
                self._aligned = True
                self._descent_step = 0
                self._t_e2o_frozen = self._live_t_e2o()
                self._q_des_frozen = self._desired_object_quat(geo)
                how = "centered" if self._centered >= int(p["hold_centered_steps"]) else f"timeout@{self._insert_step}"
                self.log(f"ALIGN frozen ({how}) axis={axis_ang:.1f} deg lat={lateral_live * 1e3:.1f} mm")
                if float(p["press_effort"]) > 0.0 and not self._press_boosted:
                    self._press_boosted = True
                    self.task.set_finger_limits(0.0, float(p["press_effort"]))
            cmd = self._eef_for_depth(
                -float(p["preinsert_clearance"]), geo, self._live_t_e2o(), self._desired_object_quat(geo)
            )
            cmd[:3] += self._lat_offset
            self._last_cmd = cmd.copy()
            return self.act(cmd, GRIPPER_CLOSE)

        # ---- clearance stops: the wrist / fingertips reach the hole plane -> stop here
        if (float(p["eef_stop_axial"]) > 0.0 or float(p["fingertip_stop_axial"]) > 0.0) and not self._eef_stop_hit:
            eef_ax = float(np.dot(eef_now[:3] - top_w, n_w))
            why = None
            if float(p["eef_stop_axial"]) > 0.0 and eef_ax >= -float(p["eef_stop_axial"]):
                why = f"wrist {eef_ax * 1e3:+.1f} mm within {float(p['eef_stop_axial']) * 1e3:.0f} mm of the hole plane"
            elif float(p["fingertip_stop_axial"]) > 0.0:
                tips = eef_now[:3] + m.quat_rotate(eef_now[3:7], [0.0, 0.0, 1.0]) * float(p["fingertip_offset"])
                tip_ax = float(np.dot(tips - top_w, n_w))
                if tip_ax >= -float(p["fingertip_stop_axial"]):
                    why = f"fingertips {tip_ax * 1e3:+.1f} mm within {float(p['fingertip_stop_axial']) * 1e3:.0f} mm of the hole plane"
            if why is not None:
                self._eef_stop_hit = True
                self.p["insert_stop_depth"] = float(signed_live)
                self.log(f"CLEARANCE STOP: {why} - stop depth -> {signed_live * 1e3:.1f} mm")

        # ---- descent ramp with the press ceiling
        n_sub = max(1, int(p["insert_descent_substeps"]))
        start_d = -float(p["preinsert_clearance"])
        stop = p["insert_stop_depth"]
        target_d = float(stop) if stop is not None else bore - float(p["seat_margin"])
        alpha = min(1.0, self._descent_step / n_sub)
        ease = float(p["descent_ease_pow"])
        if ease != 1.0:
            alpha = 1.0 - (1.0 - alpha) ** ease
        d_along = start_d + alpha * (target_d - start_d)
        press = (
            float(p["reclock_press"])
            if (self._yawu_on and p["reclock_press"] is not None)
            else float(p["press_allowance"])
        )
        d_along = min(d_along, signed_live + press)
        if self._yawu_on and self._yawu_target is not None and float(p["reclock_lift"]) > 0.0:
            d_along = min(d_along, self._yawu_ref - float(p["reclock_lift"]))
        if p["grip_slip_comp"] and self._t_e2o_frozen is not None:
            obj_pred = m.pose_compose(eef_now, self._t_e2o_frozen)
            tip_pred = obj_pred[:3] + m.quat_rotate(obj_pred[3:7], self.tip_offset)
            slip_ax = float(np.dot(tip_pred - tip_live, n_w))
            self._last_slip = slip_ax
            if slip_ax > 0.0:
                d_along += min(slip_ax, 0.004)
            if slip_ax > float(p["slip_jam"]) and not self._jammed:
                self.log(f"SLIP-JAM: pads slid {slip_ax * 1e3:.1f} mm at depth {signed_live * 1e3:.1f} mm")
                self._jammed = True
        self._depth_max = max(self._depth_max, signed_live)
        freeze = float(p["lateral_freeze_depth"])
        if (
            float(p["erode_jam"]) > 0.0
            and not self._jammed
            and signed_live > freeze
            and self._depth_max - signed_live > float(p["erode_jam"])
        ):
            self.log(f"EROSION-JAM: depth {signed_live * 1e3:.1f} mm fell below peak {self._depth_max * 1e3:.1f} mm")
            self._jammed = True
        self._descent_step += 1
        if p["release_depth_line"] is not None:
            self._depth_line_settle = (
                self._depth_line_settle + 1 if signed_live >= float(p["release_depth_line"]) else 0
            )
        stop_band = None
        if p["release_at_stop"] and stop is not None:
            stop_band = float(stop) - float(p["seat_margin"])
            self._release_settle = self._release_settle + 1 if signed_live >= stop_band else 0

        # ---- stall / stop detection (end_held)
        if p["end_held"] and not self._jammed:
            if stop is not None and signed_live >= float(stop) - 0.0005:
                self._stop_settle += 1
                if self._stop_settle >= 10:
                    self._jammed = True
                    self.log(f"stop depth reached: {signed_live * 1e3:.1f} mm")
            else:
                self._stop_settle = 0
            self._depth_hist.append(signed_live)
            if len(self._depth_hist) > int(p["hold_stall_window"]):
                self._depth_hist.pop(0)
                advanced = self._depth_hist[-1] - self._depth_hist[0]
                if advanced < float(p["hold_stall_eps"]) and signed_live > 0.002 and not self._unlock_on:
                    if p["unlock_sweep"] and self._unlock_total < float(p["unlock_max_sweeps"]) * 2 * math.pi:
                        self._unlock_on = True
                        self._unlock_ref = signed_live
                        self._depth_hist.clear()
                        self.log(f"UNLOCK sweep on at depth {signed_live * 1e3:.1f} mm")
                    else:
                        self._jammed = True
                        self.log(f"stall at depth {signed_live * 1e3:.1f} mm -> jam")
        if self._unlock_on:
            step_a = math.radians(float(p["unlock_sweep_dps"])) * CONTROL_DT
            self._unlock_az += step_a
            self._unlock_total += abs(step_a)
            if signed_live - self._unlock_ref >= float(p["unlock_break"]):
                self._unlock_on = False
                self._depth_hist.clear()
                self.log(f"UNLOCK key found at depth {signed_live * 1e3:.1f} mm")
            elif self._unlock_total >= float(p["unlock_max_sweeps"]) * 2 * math.pi:
                self._unlock_on = False
                self._jammed = True
                self.log("UNLOCK budget spent -> jam")

        # ---- gear reclock (tooth phase search on stall)
        if p["yaw_reclock"]:
            self._reclock_tick(signed_live, axis_ang)

        # ---- lateral servo below the capture depth
        if signed_live <= freeze:
            servo(
                float(p["hold_decay"]),
                float(p["lateral_deadband_inbore"]) if signed_live > -0.0 else float(p["lateral_deadband"]),
            )

        # ---- orientation command
        q_des = self._q_des_frozen
        if self._yawu_locked != 0.0:
            q_des = m.quat_mul(m.quat_from_axis_angle(n_w, math.radians(self._yawu_locked)), q_des)
        if float(p["yaw_follow_alpha"]) > 0.0 and signed_live > freeze:
            twist = G.twist_about(held[3:7], q_des, n_w)
            q_des = m.quat_mul(m.quat_from_axis_angle(n_w, (1.0 - float(p["yaw_follow_alpha"])) * twist), q_des)
        cmd = self._eef_for_depth(d_along, geo, self._t_e2o_frozen, q_des)
        if p["lateral_follow"] and signed_live > freeze:
            cmd[:3] += lat_vec * (1.0 - float(p["lateral_follow_alpha"]))
            if self._unlock_on:
                cmd[:3] -= lat_vec * (1.0 - float(p["lateral_follow_alpha"]))
                e = float(p["unlock_e"])
                cmd[0] += e * math.cos(self._unlock_az)
                cmd[1] += e * math.sin(self._unlock_az)
        else:
            cmd[:3] += self._lat_offset
        self._last_cmd = cmd.copy()
        if int(p["track_print_every"]) > 0 and self._insert_step % int(p["track_print_every"]) == 1:
            self.log(
                f"step={self._insert_step} depth={signed_live * 1e3:+.2f}/{bore * 1e3:.1f} mm lat={lateral_live * 1e3:.2f} mm axis={axis_ang:.1f} deg d_cmd={d_along * 1e3:+.1f} mm slip={self._last_slip * 1e3:+.1f} mm"
            )

        # ---- release decisions
        act = self.act(cmd, GRIPPER_CLOSE)
        if p["end_held"]:
            if self._jammed:
                rmd = p["release_min_depth"]
                if rmd is not None and signed_live < float(rmd):
                    return self._abort(
                        f"jam at {signed_live * 1e3:.1f} mm < release_min_depth {float(rmd) * 1e3:.1f} mm",
                        obs,
                        obs_info,
                    )
                if p["end_held_release"]:
                    self._begin_open(f"releasing at depth {signed_live * 1e3:.1f} mm")
                    self.run_sub(Gripper("open", "right", timeout=30), obs, obs_info)
                    return self.sub_step(obs, obs_info)
                self.finish("held at jam")
                return self.hold()
        else:
            seated = (
                signed_live >= bore - float(p["seat_margin_success"])
                and lateral_live <= float(p["success_xy"])
                and axis_ang <= float(p["success_axis_deg"])
            )
            line_ok = p["release_depth_line"] is not None and self._depth_line_settle >= int(p["release_dwell_steps"])
            stop_ok = (
                stop_band is not None
                and p["release_seated_free"]
                and (self._eef_stop_hit or self._depth_max >= stop_band)
            )
            if seated or line_ok or stop_ok:
                pressed_out = self._insert_step >= int(
                    p["insert_max_steps"]
                )  # held at the stop for the whole insert budget
                if stop_band is not None and self._release_settle < int(p["release_dwell_steps"]) and not pressed_out:
                    if self._insert_step % 60 == 0:
                        self.log(
                            f"pressing to the stop: depth {signed_live * 1e3:+.2f} mm, peak {self._depth_max * 1e3:+.2f} mm, release band >= {stop_band * 1e3:.2f} mm"
                        )
                    return act  # gate open, but the bottom dwell is not met yet
                why = (
                    "seated"
                    if seated
                    else (f"past the {float(p['release_depth_line']) * 1e3:.1f} mm line" if line_ok else "at the stop")
                )
                if stop_band is not None:
                    why += (
                        f" (dwelt {self._release_settle} ticks within the stop band)"
                        if not pressed_out
                        else " (pressed at the stop for the whole insert budget)"
                    )
                self._begin_open(f"{why} at depth {signed_live * 1e3:.1f} mm")
                self.run_sub(Gripper("open", "right", timeout=30), obs, obs_info)
                return self.sub_step(obs, obs_info)
        if self._insert_step >= int(p["insert_max_steps"]):
            return self._abort("insert stalled (max steps)", obs, obs_info)
        return act

    # -- gear tooth-phase reclock
    def _live_clocking(self) -> float:
        """Signed turn (deg) that puts the held gear's teeth into the neighbour's gaps."""
        p = self.p
        neighbor = p.get("reclock_neighbor")
        if not neighbor:
            return 0.0
        base = self.task.target_pose(self.part)
        large = self.task.object_pose(str(neighbor))
        held = self.task.held_pose(self.part)
        th_base = G.yaw_deg(base[3:7])
        th_l = G.yaw_deg(large[3:7]) - th_base
        th_m = G.yaw_deg(held[3:7]) - th_base
        pitch = float(p["reclock_pitch_deg"])
        sol0 = -4.5 - 1.5 * th_l
        k = round((th_m - sol0) / pitch)
        return float(sol0 + k * pitch - th_m)

    def _reclock_tick(self, signed_live: float, axis_ang: float) -> None:
        p = self.p
        self._yawu_hist.append(signed_live)
        if len(self._yawu_hist) > int(p["hold_stall_window"]):
            self._yawu_hist.pop(0)
            stalled = self._yawu_hist[-1] - self._yawu_hist[0] < float(p["hold_stall_eps"])
            if (
                stalled
                and not self._yawu_on
                and float(p["reclock_min_depth"]) < signed_live < float(p["reclock_max_depth"])
                and self._reclocks < int(p["max_reclocks"])
            ):
                self._reclocks += 1
                turn = self._live_clocking()
                rg = float(p["reclock_region_deg"])
                step_deg = float(p["reclock_step_deg"])
                if abs(turn) > 1e-3 and self._reclocks == 1:
                    self._yawu_dir = 1.0 if turn > 0.0 else -1.0
                nxt = self._yawu_locked + self._yawu_dir * step_deg
                if abs(nxt) > rg + 1e-6:
                    self._yawu_dir = -self._yawu_dir
                    nxt = self._yawu_locked + self._yawu_dir * step_deg
                self._yawu_target = max(-rg, min(rg, nxt))
                self._yawu_on = True
                self._yawu_ref = signed_live
                self._yawu_hist.clear()
                self.log(
                    f"RECLOCK {self._reclocks}/{p['max_reclocks']} at depth {signed_live * 1e3:.1f} mm: hint {turn:+.1f} deg -> {self._yawu_target:+.1f} deg"
                )
        if self._yawu_on and self._yawu_target is not None:
            rate = float(p["reclock_dps"]) * CONTROL_DT
            err = self._yawu_target - self._yawu_locked
            if axis_ang > float(p["reclock_tilt_cancel_deg"]):
                self._yawu_on, self._yawu_target = False, None
                self._yawu_hist.clear()
                self.log(f"RECLOCK cancelled: tilt {axis_ang:.1f} deg")
            elif signed_live - self._yawu_ref >= float(p["reclock_break"]):
                self._yawu_on, self._yawu_target = False, None
                self._yawu_hist.clear()
                self.log(f"RECLOCK breakthrough at {self._yawu_locked:+.1f} deg depth {signed_live * 1e3:.1f} mm")
            elif (self._yawu_ref - float(p["reclock_lift"])) - signed_live > float(p["reclock_erode"]):
                self._yawu_on, self._yawu_target = False, None
                self._yawu_hist.clear()
                self.log("RECLOCK cancelled: depth eroded during the turn")
            elif abs(err) <= rate:
                self._yawu_locked = self._yawu_target
                self._yawu_on, self._yawu_target = False, None
                self._yawu_hist.clear()
            elif axis_ang <= float(p["reclock_tilt_pause_deg"]):
                self._yawu_locked += max(-rate, min(rate, err))


# --------------------------------------------------------------------------- screw
SCREW_DEFAULTS: Dict[str, Any] = {
    "pitch": 0.0092,
    "yaw_rate_deg": 0.4,
    "tighten_sign": 1,
    "assembled_margin": 0.005,
    "max_steps": 6000,
    "engage_press": 0.002,
    "yaw_bias_deg": 4.0,
    "max_turn_deg": 300.0,
    "handoff_steps": 120,
    "finish_wait_release": True,
    "finish_wait_max": 600,
    "finish_rise": 0.0,
    "erode_regrasp": 0.003,
    "rewind_enable": True,
    "rewind_wrist_joint": "J1_6_joint",
    "rewind_dps": 90.0,
    "rewind_dps_cartesian": 45.0,
    "rewind_aloft_rise": 0.06,
    "recenter_mps": 0.08,
    "recenter_tol": 0.003,
    "rewind_lift_mps": 0.05,
    "rewind_abort_tilt_deg": 15.0,
    "rewind_close_steps": 100,
    "rewind_min_depth": 0.012,
    "rewind_max_sink": 0.006,
    "max_rewinds": 6,
    "max_thread_jumps": 1,
    "grip_source": "label",
    "pad_tip_local": 0.195,
    "grip_hand_local": 0.195,
    "entry_acquire": True,
    "acquire_settle_steps": 60,
    "sym_order": 4,
    "label_sym_snap": False,
    "finger_vel_limit": 0.025,
    "finger_effort_limit": 10.0,
    "slip_regrasp": 0.005,
    "rot_stall_window": 60,
    "rot_stall_eps_deg": 1.0,
    "stall_min_depth": 0.012,
    "gate_stall_window": 180,
    "gate_stall_eps": 0.0003,
    "stall_fold_wind_deg": 120.0,
    "slow_rewind_wind_deg": 0.0,
    "slow_rewind_window": 180,
    "slow_rewind_eps_deg": 8.0,
    "soft_start_steps": 120,
    "success_angle_deg": 0.0,
    "success_angle_tol_deg": 3.0,
    "drive_deeper": True,
    "debug_print_every": 60,
}


class ScrewSkill(SkillBase):
    """Turn the held part into its thread until it stops (see the module docstring)."""

    name = "screw"

    def __init__(self, task, cfg=None, part: int = 0, **kw):
        merged = dict(SCREW_DEFAULTS)
        merged.update({k: v for k, v in (cfg or {}).items()})
        super().__init__(task, merged, part, **kw)
        self.p = {k: merged[k] for k in SCREW_DEFAULTS}

    # -- helpers
    def _geo(self):
        return self.task.geometry(self.part)

    def _depth(self, geo, held) -> float:
        tip = held[:3] + m.quat_rotate(held[3:7], self.tip_offset)
        return float(np.dot(tip - geo["top_w"], geo["n_w"]))

    def _live_t_e2o(self) -> np.ndarray:
        return G.relative_pose(self.task.eef_pose(), self.task.held_pose(self.part))

    def _rebase_grip(self) -> None:
        geo0 = self._geo()
        held0 = self.task.held_pose(self.part)
        eef0 = self.task.eef_pose()
        q0 = held0[3:7].copy()
        axis_w = m.quat_rotate(q0, self.tip_offset)
        axis_w /= np.linalg.norm(axis_w) + 1e-9
        q_align = G.quat_align(axis_w, geo0["n_w"])
        self._q0_raw = q0
        w = max(-1.0, min(1.0, float(q_align[0])))
        self._align_angle = 2.0 * math.acos(w)
        s = math.sqrt(max(1.0 - w * w, 1e-12))
        self._align_axis = q_align[1:4] / s if s > 1e-6 else geo0["n_w"].copy()
        self._q_obj0 = m.quat_mul(q_align, q0)
        self._twist_prev = 0.0
        self._psi_cmd = 0.0
        self._psi_meas = 0.0
        self._psi_hist: List[float] = []
        self._rot_hist: List[float] = []
        d0 = self._depth(geo0, held0)
        self._d0 = d0
        self._prog_peak = self._fwd * d0
        self._last_depth = d0
        self._grip_ref = float(np.linalg.norm(eef0[:3] - held0[:3]))
        self._t_e2o_frozen = self._live_t_e2o()
        self._q_eef0 = eef0[3:7].copy()
        self._eef_z0 = float(eef0[2])
        self._grip_h = float(np.dot(eef0[:3] - held0[:3], -axis_w))
        if self._q_ref0 is not None:
            t = G.twist_about(eef0[3:7], self._q_ref0, geo0["n_w"])
            self._wind_at_grip = self._sign * t
        else:
            self._wind_at_grip = 0.0
        self._wrist_out = False
        self._regrasp_reason = None
        self._feed_hist: List[float] = []
        self._soft_start_at = self._steps
        self._soft_start_done = False

    def _select_label(self, held: np.ndarray) -> Optional[np.ndarray]:
        """Label whose executed fingertips land closest to the graspable-segment middle."""
        lib = self.task.grasp_candidates(self.part)
        if len(lib) == 0:
            return None
        axis = self.task.held_axis(self.part)
        u = axis.direction
        mid = axis.grasp_mid if axis.grasp_mid is not None else 0.5 * (axis.tail + axis.head)
        s_mid = float(np.dot(mid - axis.head, u))
        s_tip = np.array([float(np.dot(lp[:3] - axis.head, u)) for lp in lib]) + float(self.p["pad_tip_local"])
        dist = np.abs(s_tip - s_mid)
        cutoff = float(dist.min()) + 0.005
        best, best_d = None, -2.0
        for i, lp in enumerate(lib):
            if dist[i] > cutoff:
                continue
            q_c = m.quat_mul(held[3:7], lp[3:7])
            d = abs(float(np.dot(q_c, self._q_ref0)))
            if d > best_d:
                best_d, best = d, lp
        return None if best is None else best.copy()

    def _label_target(self, held: np.ndarray, axis_w: np.ndarray):
        """Selected label snapped onto the live part axis, with the fingertip floor."""
        lp = self._label_sel
        p_w = held[:3] + m.quat_rotate(held[3:7], lp[:3])
        q_w = m.quat_mul(held[3:7], lp[3:7])
        a_w = held[:3] + m.quat_rotate(held[3:7], self.tip_offset)
        t = float(np.dot(p_w - a_w, axis_w))
        axis = self.task.held_axis(self.part)
        if axis.grasp_mid is not None:
            m_w = held[:3] + m.quat_rotate(held[3:7], axis.grasp_mid)
            t_floor = float(np.dot(m_w - a_w, axis_w)) - float(self.p["pad_tip_local"])
            if t > t_floor:
                t = t_floor
        pos_t = a_w + t * axis_w
        y_lab = m.quat_rotate(q_w, [0.0, 1.0, 0.0])
        n_sym = int(self.p["sym_order"])
        if self.p["label_sym_snap"] and n_sym >= 2:
            y_ref = m.quat_rotate(self._q_ref0, [0.0, 1.0, 0.0])
            best, best_dot = y_lab, -2.0
            for k in range(n_sym):
                cand = m.quat_rotate(m.quat_from_axis_angle(axis_w, 2.0 * math.pi * k / n_sym), y_lab)
                dk = float(np.dot(cand, y_ref))
                if dk > best_dot:
                    best_dot, best = dk, cand
            y_lab = best
        return pos_t, G.frame_from_axis_y(axis_w, y_lab)

    def _grip_quat(self, held: np.ndarray, axis_w: np.ndarray) -> np.ndarray:
        """Constructed re-grip orientation: tool +Z = live axis, jaws on the nearest symmetric face."""
        y_ref = m.quat_rotate(self._q_ref0, [0.0, 1.0, 0.0])
        best, best_dot = None, -2.0
        n_sym = max(2, int(self.p["sym_order"]))
        for k in range(n_sym):
            ang = 2.0 * math.pi * k / n_sym
            n = m.quat_rotate(held[3:7], [math.cos(ang), math.sin(ang), 0.0])
            d = float(np.dot(n, y_ref))
            if d > best_dot:
                best_dot, best = d, n
        return G.frame_from_axis_y(axis_w, best)

    def _regrip_target(self, held: np.ndarray, axis_w: np.ndarray):
        if self._label_sel is not None:
            pos_t, q_grip = self._label_target(held, axis_w)
        else:
            grip_h = float(self.p["grip_hand_local"]) if float(self.p["grip_hand_local"]) > 0.0 else self._grip_h
            pos_t = held[:3] - axis_w * grip_h
            if float(self.p["grip_hand_local"]) <= 0.0:
                z_floor = self._eef_z0 - float(self.p["rewind_max_sink"])
                if pos_t[2] < z_floor:
                    pos_t = pos_t.copy()
                    pos_t[2] = z_floor
            q_grip = self._grip_quat(held, axis_w)
        if self._rewind_quarter:
            q_rot = m.quat_from_axis_angle(axis_w, -self._sign * math.pi / 2.0)
            pos_t = held[:3] + m.quat_rotate(q_rot, pos_t - held[:3])
            q_grip = m.quat_normalize(m.quat_mul(q_rot, q_grip))
        if self._unwind_yaw_bias is not None and self._rewind_phase is not None:
            q_grip = m.quat_normalize(m.quat_mul(m.quat_from_axis_angle(axis_w, self._unwind_yaw_bias), q_grip))
        return pos_t, q_grip

    def _pick_unwind_bias(self, q_grip, axis_w, wound: float) -> float:
        """Choose the yaw-equivalent re-grip variant that rotates against the accumulated wind."""
        delta = G.twist_about(q_grip, self._rewind_q, axis_w)
        n_sym = max(2, int(self.p["sym_order"]))
        step = 2.0 * math.pi / n_sym
        if abs(wound) > math.radians(20.0):
            kmax = int(math.ceil(2.0 * 2.0 * math.pi / step))
            cands = [delta + k * step for k in range(-kmax, kmax + 1)]
            against = [d for d in cands if d * wound < 0.0]
            pool = against if against else cands
            chosen = min(pool, key=lambda c: abs(c + wound))
        else:
            cands = []
            for k in range(n_sym):
                d = delta + k * step
                d = (d + math.pi) % (2 * math.pi) - math.pi
                cands.append(d)
            chosen = min(cands, key=abs)
        folded = (chosen + math.pi) % (2 * math.pi) - math.pi
        self._unwind_twist_rem = chosen if abs(chosen) > math.pi else 0.0
        bias = (folded - delta + math.pi) % (2 * math.pi) - math.pi
        self.log(
            f"UNWIND direction: wound {math.degrees(wound):+.0f} deg, chosen {math.degrees(chosen):+.0f} deg (bias {math.degrees(bias):+.0f})"
        )
        return bias

    # -- lifecycle
    def start(self, obs, info):
        super().start(obs, info)
        p = self.p
        self.task.clear_finish_release()
        self._sign = float(p["tighten_sign"])
        self._fwd = 1.0 if p["drive_deeper"] else -1.0
        self.tip_offset = self.task.held_axis(self.part).head.copy()
        self._steps = 0
        self._psi_total = 0.0
        self._assembled = False
        self._thread_jumps = 0
        self._rewinds_used = 0
        self._rewind_phase: Optional[str] = None
        self._rewind_counter = 0
        self._rewind_q = None
        self._rewind_eef = None
        self._rewind_cmd = None
        self._rewind_z = 0.0
        self._rewind_xy = None
        self._rewind_quarter = False
        self._rewind_quarter_req = False
        self._rewind_entry_depth = 0.0
        self._rewind_aloft = False
        self._unwind_yaw_bias = None
        self._unwind_twist_rem = 0.0
        self._rc_pos = None
        self._handoff_counter = None
        self._handoff_eef = None
        self._finish_phase: Optional[str] = None
        self._finish_counter = 0
        self._finish_eef = None
        self._finish_z = 0.0
        self._finish_z_target = 0.0
        self._finish_waited = 0
        self._last_tilt = 0.0
        self._last_depth = 0.0
        self._bore_depth = 0.0
        self._acquire_settle_left = 0
        self._settle_eef = None
        self._label_sel = None
        self._q_ref0 = self.task.eef_pose()[3:7].copy()
        self._fingers_gentle = False
        self._grip = GRIPPER_CLOSE
        self._rebase_grip()
        if float(p["finger_vel_limit"]) > 0.0 or float(p["finger_effort_limit"]) > 0.0:
            self.task.set_finger_limits(float(p["finger_vel_limit"]), float(p["finger_effort_limit"]))
            self._fingers_gentle = True
        if p["entry_acquire"] and p["rewind_enable"]:
            self._label_sel = (
                self._select_label(self.task.held_pose(self.part)) if p["grip_source"] == "label" else None
            )
            self._rewind_phase = "center"
            self._rewind_counter = 300
            self._rewind_q = self.task.eef_pose()[3:7].copy()
            self._rewind_z = float(self.task.eef_pose()[2])
            self._rewind_entry_depth = self._last_depth
            self._acquire_settle_left = int(p["acquire_settle_steps"])
            self._settle_eef = self.task.eef_pose().copy()
            self._grip = GRIPPER_OPEN
            self.set_state("acquire")
        else:
            self.set_state("screw")

    def _exit(self, result: str) -> None:
        if self._fingers_gentle:
            self.task.restore_finger_limits()
            self._fingers_gentle = False
        self.finish(result)

    # -- per tick
    def step(self, obs, info) -> Action:
        self._t += 1
        if self._finished:
            return self.hold()
        p = self.p
        geo = self._geo()
        held = self.task.held_pose(self.part)
        d = self._depth(geo, held)
        self._steps += 1
        self._last_depth = d
        self._bore_depth = float(geo["depth"])
        axis_now = m.quat_rotate(held[3:7], self.tip_offset)
        axis_now /= np.linalg.norm(axis_now) + 1e-9
        self._last_tilt = G.angle_between_deg(axis_now, geo["n_w"])

        if self._handoff_counter is not None:
            if self._handoff_counter > 0:
                self._handoff_counter -= 1
                return self.act(self._handoff_eef, GRIPPER_OPEN)
            self._exit(f"failed: wrist budget ({self._regrasp_reason or 'wind spent'})")
            return self.hold()

        if self._acquire_settle_left > 0:
            self._acquire_settle_left -= 1
            return self.act(self._settle_eef, GRIPPER_OPEN)

        if self._finish_phase is not None:
            return self._finish_tick()

        # measured tightening progress (unwrapped twist of the part about the hole axis)
        twist_raw = G.twist_about(held[3:7], self._q_obj0, geo["n_w"])
        delta = (twist_raw - self._twist_prev + math.pi) % (2 * math.pi) - math.pi
        self._twist_prev = twist_raw
        self._psi_meas += self._sign * delta
        self._psi_total += self._sign * delta

        if self._rewind_phase is not None:
            return self._rewind_step(geo, d, held)

        # ---- followers
        rate = math.radians(float(p["yaw_rate_deg"]))
        self._psi_cmd = max(
            self._psi_cmd, min(self._psi_cmd + rate, self._psi_meas + math.radians(float(p["yaw_bias_deg"])))
        )
        angle_mode = float(p["success_angle_deg"]) > 0.0
        if angle_mode:
            self._psi_cmd = min(self._psi_cmd, math.radians(float(p["success_angle_deg"])))
            d_cmd = (
                self._d0 + float(p["pitch"]) * (self._psi_meas / (2.0 * math.pi)) + float(p["engage_press"])
                if float(p["pitch"]) > 0.0
                else self._d0
            )
        else:
            d_cmd = d + float(p["engage_press"])
        tip = held[:3] + m.quat_rotate(held[3:7], self.tip_offset)
        lat = (tip - geo["top_w"]) - geo["n_w"] * d
        wind_used = math.degrees(self._psi_cmd) + max(0.0, math.degrees(self._wind_at_grip))
        if wind_used >= float(p["max_turn_deg"]) and (not angle_mode or float(p["pitch"]) > 0.0):
            self._wrist_out = True
        # slow crawl
        if float(p["slow_rewind_wind_deg"]) > 0.0 and not angle_mode:
            self._psi_hist.append(math.degrees(self._psi_cmd))
            if len(self._psi_hist) > int(p["slow_rewind_window"]):
                self._psi_hist.pop(0)
                advanced = self._psi_hist[-1] - self._psi_hist[0]
                if (
                    wind_used > float(p["slow_rewind_wind_deg"])
                    and advanced < float(p["slow_rewind_eps_deg"])
                    and self._regrasp_reason is None
                    and not self._wrist_out
                ):
                    self._regrasp_reason = f"slow crawl ({advanced:.0f} deg per {p['slow_rewind_window']} ticks)"
                    self._psi_hist.clear()
        # rotation stall
        if not angle_mode:
            self._rot_hist.append(math.degrees(self._psi_meas))
            if len(self._rot_hist) > int(p["rot_stall_window"]):
                self._rot_hist.pop(0)
                span = max(self._rot_hist) - min(self._rot_hist)
                if (
                    span < float(p["rot_stall_eps_deg"])
                    and self._regrasp_reason is None
                    and d < self._bore_depth - float(p["assembled_margin"])
                    and d > float(p["stall_min_depth"])
                ):
                    self._rewind_quarter_req = True
                    self._regrasp_reason = f"rotation stalled at {wind_used:.0f} deg wind; quarter re-grip"
                    self._rot_hist.clear()
        # grip slip
        grip_now = float(np.linalg.norm(self.task.eef_pose()[:3] - held[:3]))
        slip = abs(grip_now - (self._grip_ref or grip_now))
        if slip > float(p["slip_regrasp"]) and self._regrasp_reason is None and not angle_mode:
            self._regrasp_reason = f"grip slipped {slip * 1e3:.1f} mm"
        # thread jump
        prog = self._fwd * d
        self._prog_peak = max(self._prog_peak, prog)
        if self._prog_peak - prog > float(p["erode_regrasp"]) and self._regrasp_reason is None and not angle_mode:
            self._regrasp_reason = f"thread jumped ({prog * 1e3:.1f} < peak {self._prog_peak * 1e3:.1f} mm)"
        # feed stall -> assembled / rewind
        self._feed_hist.append(d)
        if len(self._feed_hist) > int(p["gate_stall_window"]):
            self._feed_hist.pop(0)
            stalled = (max(self._feed_hist) - min(self._feed_hist) < float(p["gate_stall_eps"])) and not angle_mode
            if stalled and self._regrasp_reason is None:
                if d >= self._bore_depth - float(p["assembled_margin"]):
                    self._start_finish()
                    self.log(
                        f"ASSEMBLED at depth {d * 1e3:.1f} / {self._bore_depth * 1e3:.1f} mm - tightened to a stop"
                    )
                elif d > float(p["stall_min_depth"]) and wind_used >= float(p["stall_fold_wind_deg"]):
                    self._regrasp_reason = f"feed stall at {wind_used:.0f} deg wind"
                    self._feed_hist.clear()
        if (
            angle_mode
            and math.degrees(self._psi_total) >= float(p["success_angle_deg"]) - float(p["success_angle_tol_deg"])
            and self._finish_phase is None
        ):
            self._start_finish()
            self.log(f"ANGLE reached: {math.degrees(self._psi_total):.0f} deg")

        # ---- command
        alpha = min(1.0, (self._steps - self._soft_start_at) / max(1, int(p["soft_start_steps"])))
        if alpha < 1.0 or not self._soft_start_done:
            # uprighting a leaning part rides it up the thread a little; judge thread jumps from the settled grip
            self._prog_peak = max(self._prog_peak - float(p["erode_regrasp"]), self._fwd * d)
            if alpha >= 1.0:
                self._soft_start_done = True
        q_base = (
            m.quat_mul(m.quat_from_axis_angle(self._align_axis, self._align_angle * alpha), self._q0_raw)
            if alpha < 1.0
            else self._q_obj0
        )
        q_des = m.quat_mul(m.quat_from_axis_angle(geo["n_w"], self._sign * self._psi_cmd), q_base)
        target_tip = geo["top_w"] + lat + geo["n_w"] * d_cmd
        obj_pos = target_tip - m.quat_rotate(q_des, self.tip_offset)
        eef_cmd = G.eef_from_object(np.concatenate([obj_pos, q_des]), self._t_e2o_frozen)
        if int(p["debug_print_every"]) > 0 and self._steps % int(p["debug_print_every"]) == 1:
            self.log(
                f"step={self._steps} psi_cmd={math.degrees(self._psi_cmd):+.1f} psi_meas={math.degrees(self._psi_meas):+.1f} depth={d * 1e3:+.2f}/{self._bore_depth * 1e3:.1f} mm lat={np.linalg.norm(lat) * 1e3:.2f} mm slip={slip * 1e3:.1f} mm tilt={self._last_tilt:.1f} deg rewinds={self._rewinds_used}"
            )

        # ---- end-of-grip handling
        if self._finish_phase is not None:
            return self._finish_tick()
        if self._wrist_out or self._regrasp_reason is not None:
            reason = self._regrasp_reason or "wind spent"
            if (
                "thread jumped" in reason
                and int(p["max_thread_jumps"]) > 0
                and self._thread_jumps >= int(p["max_thread_jumps"])
            ):
                self._handoff_counter = int(p["handoff_steps"])
                self._handoff_eef = self.task.eef_pose().copy()
                self._regrasp_reason = f"thread jump cap: {reason}"
                self.log("THREAD JUMP CAP - failing the episode")
                return self.act(self._handoff_eef, GRIPPER_OPEN)
            if (
                p["rewind_enable"]
                and self._rewinds_used < int(p["max_rewinds"])
                and self._last_depth > float(p["rewind_min_depth"])
                and self._last_tilt <= float(p["rewind_abort_tilt_deg"])
            ):
                self._start_rewind(reason)
                return self._rewind_step(geo, d, held)
            self._handoff_counter = int(p["handoff_steps"])
            self._handoff_eef = self.task.eef_pose().copy()
            self._regrasp_reason = reason
            self.log(f"HANDOFF ({reason}) - jaws open in place")
            return self.act(self._handoff_eef, GRIPPER_OPEN)
        if self._steps >= int(p["max_steps"]):
            if self._bore_depth > 0.0 and self._last_depth >= self._bore_depth - float(p["assembled_margin"]):
                self._start_finish()
                self.log("max steps at qualified depth - finishing as assembled")
                return self._finish_tick()
            self._exit("failed: screw max steps")
            return self.hold()
        return self.act(eef_cmd, GRIPPER_CLOSE)

    # -- finish
    def _start_finish(self) -> None:
        self._finish_phase = "open"
        self._finish_counter = int(self.p["handoff_steps"])
        self._finish_eef = self.task.eef_pose().copy()
        self._feed_hist = []
        self.task.note_finish_release()

    def _finish_tick(self) -> Action:
        p = self.p
        if self._finish_phase == "open":
            self._finish_counter -= 1
            if self._finish_counter <= 0 and p["finish_wait_release"] and not self.task.finish_release_done():
                self._finish_waited += 1
                if self._finish_waited <= int(p["finish_wait_max"]):
                    return self.act(self._finish_eef, GRIPPER_OPEN)
            if self._finish_counter <= 0:
                self._finish_phase = "rise"
                self._finish_z = float(self.task.eef_pose()[2])
                self._finish_z_target = self._finish_z + float(p["finish_rise"])
            return self.act(self._finish_eef, GRIPPER_OPEN)
        step_z = float(p["rewind_lift_mps"]) * CONTROL_DT
        self._finish_z = min(self._finish_z + step_z, self._finish_z_target)
        cmd = self._finish_eef.copy()
        cmd[2] = self._finish_z
        if self._finish_z >= self._finish_z_target - 0.005:
            self._assembled = True
            self._exit("assembled")
        return self.act(cmd, GRIPPER_OPEN)

    # -- rewind
    def _start_rewind(self, reason: str) -> None:
        self._rc_pos = None
        self._unwind_yaw_bias = None
        self._unwind_twist_rem = 0.0
        self._rewind_quarter = self._rewind_quarter_req
        self._rewind_quarter_req = False
        self._rewinds_used += 1
        if "thread jumped" in reason:
            self._thread_jumps += 1
        self._wrist_out = False
        self._regrasp_reason = None
        self._rewind_phase = "open"
        self._rewind_counter = int(self.p["handoff_steps"])
        self._rewind_eef = self.task.eef_pose().copy()
        self._rewind_q = self._rewind_eef[3:7].copy()
        self._label_sel = (
            self._select_label(self.task.held_pose(self.part)) if self.p["grip_source"] == "label" else None
        )
        self._rewind_entry_depth = self._last_depth
        self._rewind_aloft = not self.task.wrist_override(str(self.p["rewind_wrist_joint"]), None)
        self.log(
            f"REWIND {self._rewinds_used}/{self.p['max_rewinds']} ({reason}) - part at {math.degrees(self._psi_meas):.0f} deg; {'aloft' if self._rewind_aloft else 'in-place'} unwind"
        )

    def _rewind_step(self, geo, d: float, held: np.ndarray) -> Action:
        p = self.p
        axis_w = m.quat_rotate(held[3:7], self.tip_offset)
        axis_w /= np.linalg.norm(axis_w) + 1e-9
        pos_t, q_grip = self._regrip_target(held, axis_w)
        target = np.concatenate([pos_t, q_grip])
        if self._last_tilt > float(p["rewind_abort_tilt_deg"]):
            self.log(f"REWIND ABORT - part toppled ({self._last_tilt:.0f} deg)")
            self._rewind_phase = None
            self._regrasp_reason = "part toppled during re-grip"
            self._handoff_counter = int(p["handoff_steps"])
            self._handoff_eef = self.task.eef_pose().copy()
            return self.act(self._handoff_eef, GRIPPER_OPEN)
        rise = float(p["rewind_aloft_rise"]) if self._rewind_aloft else 0.0
        hover = pos_t - axis_w * rise  # above the grip height along the part axis (-axis = up)

        def z_ramp(pos_target):
            step_z = float(p["rewind_lift_mps"]) * CONTROL_DT
            dz = float(pos_target[2]) - self._rewind_z
            self._rewind_z += max(-step_z, min(step_z, dz))
            out = pos_target.copy()
            out[2] = self._rewind_z
            return out

        if self._rewind_phase == "open":
            self._rewind_counter -= 1
            if self._rewind_counter <= 0:
                self._rewind_phase = "recenter"
                self._rewind_counter = 120 + int(rise / max(float(p["recenter_mps"]), 1e-3) * _TICK_HZ)
                self._rewind_z = float(self.task.eef_pose()[2])
            return self.act(self._rewind_eef, GRIPPER_OPEN)
        if self._rewind_phase == "recenter":
            self._rewind_counter -= 1
            tool_z = m.quat_rotate(self._rewind_q, [0.0, 0.0, 1.0])
            q_tgt = m.quat_normalize(m.quat_mul(G.quat_align(tool_z, axis_w), self._rewind_q))
            step_r = math.radians(float(p["rewind_dps"])) * CONTROL_DT
            q_rel = m.quat_mul(q_tgt, m.quat_conjugate(self._rewind_q))
            if q_rel[0] < 0.0:
                q_rel = -q_rel
            ang = 2.0 * math.acos(max(-1.0, min(1.0, float(q_rel[0]))))
            if ang <= step_r:
                self._rewind_q = q_tgt
            else:
                ax = q_rel[1:4] / (np.linalg.norm(q_rel[1:4]) + 1e-9)
                self._rewind_q = m.quat_normalize(m.quat_mul(m.quat_from_axis_angle(ax, step_r), self._rewind_q))
            tilt = G.angle_between_deg(m.quat_rotate(self._rewind_q, [0.0, 0.0, 1.0]), axis_w)
            eefp = self.task.eef_pose()
            if float(p["recenter_mps"]) > 0.0:
                if self._rc_pos is None:
                    self._rc_pos = eefp[:3].copy()
                dv = hover - self._rc_pos
                dn = float(np.linalg.norm(dv))
                step = float(p["recenter_mps"]) * CONTROL_DT
                self._rc_pos = self._rc_pos + dv * (step / dn) if dn > step else hover.copy()
                pos_cmd = self._rc_pos
            else:
                pos_cmd = hover
            pos_err = float(np.linalg.norm(eefp[:3] - hover))
            if pos_err <= float(p["recenter_tol"]) and tilt <= 1.5:
                self._rewind_phase = "unwind"
                self._rewind_counter = 600
                self._rewind_xy = hover[:2].copy()
                self._rewind_z = float(hover[2])
                self._unwind_yaw_bias = self._pick_unwind_bias(
                    q_grip, axis_w, self._sign * (self._psi_cmd + self._wind_at_grip)
                )
                self.log(f"RECENTER done (err {pos_err * 1e3:.1f} mm, tilt {tilt:.1f} deg) - unwinding")
            elif self._rewind_counter <= 0:
                self.log(f"RECENTER failed (err {pos_err * 1e3:.1f} mm, tilt {tilt:.1f} deg) - handing off")
                self._rewind_phase = None
                self._regrasp_reason = "recenter failed"
                self._handoff_counter = int(p["handoff_steps"])
                self._handoff_eef = self.task.eef_pose().copy()
                return self.act(self._handoff_eef, GRIPPER_OPEN)
            return self.act(np.concatenate([pos_cmd, self._rewind_q]), GRIPPER_OPEN)
        if self._rewind_phase == "unwind":
            pos_cmd = np.concatenate([self._rewind_xy, [self._rewind_z]])
            step_r = (
                math.radians(float(p["rewind_dps_cartesian"] if self._rewind_aloft else p["rewind_dps"])) * CONTROL_DT
            )
            self._rewind_counter -= 1
            if abs(self._unwind_twist_rem) > 1e-9:
                dd = (
                    self._unwind_twist_rem
                    if abs(self._unwind_twist_rem) <= step_r
                    else math.copysign(step_r, self._unwind_twist_rem)
                )
                self._rewind_q = m.quat_normalize(m.quat_mul(m.quat_from_axis_angle(axis_w, dd), self._rewind_q))
                self._unwind_twist_rem -= dd
                return self.act(np.concatenate([pos_cmd, self._rewind_q]), GRIPPER_OPEN)
            q_rel = m.quat_mul(q_grip, m.quat_conjugate(self._rewind_q))
            if q_rel[0] < 0.0:
                q_rel = -q_rel
            ang = 2.0 * math.acos(max(-1.0, min(1.0, float(q_rel[0]))))
            if ang <= step_r or self._rewind_counter <= 0:
                self._rewind_q = q_grip.copy()
                self._rewind_phase = "center"
                self._rewind_counter = 300
                self._rewind_z = float(self.task.eef_pose()[2])
                self.log("UNWIND done - descending onto the part")
            else:
                ax = q_rel[1:4] / (np.linalg.norm(q_rel[1:4]) + 1e-9)
                self._rewind_q = m.quat_normalize(m.quat_mul(m.quat_from_axis_angle(ax, step_r), self._rewind_q))
            return self.act(np.concatenate([pos_cmd, self._rewind_q]), GRIPPER_OPEN)
        if self._rewind_phase == "center":
            self._rewind_counter -= 1
            err = float(np.linalg.norm(self.task.eef_pose()[:3] - pos_t))
            if err < 0.002 or self._rewind_counter <= 0:
                self._rewind_phase = "close"
                self._rewind_counter = int(p["rewind_close_steps"])
                self._rewind_cmd = target.copy()
                self.log(f"CENTER done (err {err * 1e3:.1f} mm) - closing")
            return self.act(np.concatenate([z_ramp(pos_t), q_grip]), GRIPPER_OPEN)
        # close
        self._rewind_counter -= 1
        if self._rewind_counter <= 0:
            pop = self._fwd * (self._rewind_entry_depth - d) * 1e3
            self._rewind_phase = None
            self._grip = GRIPPER_CLOSE
            self._rebase_grip()
            self.set_state("screw", f"fresh grip at depth {d * 1e3:.1f} mm (pop {pop:+.1f} mm)")
        return self.act(self._rewind_cmd, GRIPPER_CLOSE)


# --------------------------------------------------------------------------- extract
EXTRACT_DEFAULTS: Dict[str, Any] = {
    "clearance": 0.01,
    "retrieve": 0.10,
    "substeps": 300,
    "max_steps": 1500,
    "press_allowance": 0.003,
    "lateral_freeze_depth": 0.002,
    "lateral_follow": True,
    "lateral_follow_alpha": 0.05,
    "lateral_gain": 0.6,
    "lateral_step_max": 0.004,
    "lateral_deadband": 0.0015,
    "servo_track_thresh": 0.03,
    "hold_decay": 0.9,
    "lift_steps": 120,
    "lift_speed": 0.3,
    "lift_tol": 0.02,
    "track_print_every": 30,
}


class ExtractSkill(SkillBase):
    """Pull the held part out of the bore it starts in (the insert stroke reversed).

    The task must provide ``extract_geometry()`` (the held part's insertion geometry
    against the bore it is parked in). No align hold: the bore enforces the
    alignment, so the grip transform and the part orientation are frozen as they
    are at the start and the depth alone is ramped from the live value toward
    ``-retrieve`` over ``substeps`` ticks, never commanding higher than the measured
    tip minus ``press_allowance`` (a bound part is pulled gently, not sprung). The
    lateral follower (or, within ``lateral_freeze_depth`` of the entry, the lateral
    servo) keeps the hand on the part. Once the tip is ``clearance`` above the entry
    one fast lift of ``retrieve`` ends the skill, still held.
    """

    name = "extract"

    def __init__(self, task, cfg=None, part: int = 0, **kw):
        merged = dict(EXTRACT_DEFAULTS)
        merged.update({k: v for k, v in (cfg or {}).items()})
        super().__init__(task, merged, part, **kw)
        self.p = {k: merged[k] for k in EXTRACT_DEFAULTS}

    def start(self, obs, info):
        super().start(obs, info)
        self.tip_offset = self.task.held_axis(self.part).head.copy()
        self._grip = GRIPPER_CLOSE
        self._t_e2o = G.relative_pose(self.task.eef_pose(), self.task.held_pose(self.part))
        self._q_frozen = self.task.held_pose(self.part)[3:7].copy()
        self._d0: Optional[float] = None
        self._step = 0
        self._lat_offset = np.zeros(3)
        self._last_cmd: Optional[np.ndarray] = None
        self._lift_z = 0.0
        self.set_state("extract")

    def step(self, obs, info) -> Action:
        self._t += 1
        if self._finished:
            return self.hold()
        if self.state == "lift":
            if self.sub_done(obs, info):
                z = float(ee_pose(obs, 0)[2])
                if z >= self._lift_z - float(self.p["lift_tol"]):
                    self.finish(f"extracted: held, lifted to z={z:.3f}")
                else:
                    self.finish(
                        f"extracted: held, lift short (z={z:.3f} vs {self._lift_z:.3f}; {self._sub.done_reason})"
                    )
                return self.hold()
            return self.sub_step(obs, info)
        return self._extract_tick(obs, info)

    def _extract_tick(self, obs, info) -> Action:
        p = self.p
        geo = self.task.extract_geometry()
        n_w, top_w = geo["n_w"], geo["top_w"]
        held = self.task.held_pose(self.part)
        tip_live = held[:3] + m.quat_rotate(held[3:7], self.tip_offset)
        signed_live, lateral_live, lat_vec = G.signed_depth_lateral(tip_live, top_w, n_w)
        axis_ang = G.angle_between_deg(m.quat_rotate(held[3:7], self.task.held_axis(self.part).direction), n_w)
        if self._d0 is None:
            self._d0 = signed_live
            self.log(
                f"part {self.part}: start depth {signed_live * 1e3:+.1f} mm in the bore, exit line {-float(p['clearance']) * 1e3:+.1f} mm"
            )
        self._step += 1
        eef_now = self.task.eef_pose()
        tracking = self._last_cmd is None or float(np.linalg.norm(eef_now[:3] - self._last_cmd[:3])) <= float(
            p["servo_track_thresh"]
        )
        freeze = float(p["lateral_freeze_depth"])
        if signed_live <= freeze and lateral_live > float(p["lateral_deadband"]) and tracking:
            step_max = float(p["lateral_step_max"])
            v = -float(p["lateral_gain"]) * lat_vec
            nrm = float(np.linalg.norm(v))
            if nrm > step_max:
                v = v * (step_max / (nrm + 1e-9))
            self._lat_offset = self._lat_offset * float(p["hold_decay"]) + v
        alpha = min(1.0, self._step / max(1, int(p["substeps"])))
        d_along = self._d0 + alpha * (-float(p["retrieve"]) - self._d0)
        d_along = max(d_along, signed_live - float(p["press_allowance"]))  # pull ceiling
        target_tip = top_w + n_w * d_along
        cmd = G.eef_from_object(G.object_pose_for_tip(target_tip, self._q_frozen, self.tip_offset), self._t_e2o)
        if p["lateral_follow"] and signed_live > freeze:
            cmd[:3] += lat_vec * (1.0 - float(p["lateral_follow_alpha"]))
        else:
            cmd[:3] += self._lat_offset
        self._last_cmd = cmd.copy()
        if int(p["track_print_every"]) > 0 and self._step % int(p["track_print_every"]) == 1:
            self.log(
                f"step={self._step} depth={signed_live * 1e3:+.2f} mm lat={lateral_live * 1e3:.2f} mm axis={axis_ang:.1f} deg d_cmd={d_along * 1e3:+.1f} mm"
            )
        if signed_live <= -float(p["clearance"]):
            lift = ee_pose(obs, 0).copy()
            lift[2] += float(p["retrieve"])
            self._lift_z = float(lift[2])
            self.set_state(
                "lift",
                f"cleared the bore (tip {-signed_live * 1e3:.1f} mm above the entry), lifting {float(p['retrieve']) * 1e3:.0f} mm",
            )
            self.run_sub(
                MoveL(
                    lift,
                    "right",
                    steps=int(p["lift_steps"]),
                    speed=float(p["lift_speed"]),
                    converge=True,
                    tol=(0.01, 0.05),
                    timeout=400,
                    name="extract_lift",
                ),
                obs,
                info,
            )
            return self.sub_step(obs, info)
        if self._step >= int(p["max_steps"]):
            self.finish(f"aborted: extract timeout at depth {signed_live * 1e3:+.1f} mm (bound in the bore?)")
            return self.hold()
        return self.act(cmd, GRIPPER_CLOSE)


# --------------------------------------------------------------------------- joint-space moves
class JointInterpPlanner:
    """Joint-space move of the right arm, streamed as end-effector targets.

    The goal joints come from an offline Pink IK solve seeded with the current joints,
    each continuous joint wrapped into [-pi, pi] (an unwound wrist), so the arm takes
    the short way round instead of winding a joint into its limit; the move is a
    linear interpolation in joint space, and every row is the forward kinematics of
    the interpolated joints (the action rows stay end-effector targets).
    """

    WRAP = (0, 3, 4, 5)  # right-arm joints with +-2pi travel (J1_1, J1_4, J1_5, J1_6)

    def __init__(self, base_pose: np.ndarray, joint_speed: float = 0.8, iters: int = 800, tol=(0.001, 0.005)):
        from ..backends.ik_pink import PinkIK

        self.ik = PinkIK()
        self.base = np.asarray(base_pose, dtype=np.float64).reshape(7)
        self.joint_speed = float(joint_speed)
        self.iters = int(iters)
        self.tol = (float(tol[0]), float(tol[1]))

    def _solve(self, seed: np.ndarray, goal_base: np.ndarray):
        q = seed.copy()
        self.ik.reset(q)
        err = (1.0, 1.0)
        for i in range(self.iters):
            q = self.ik.solve(q, [goal_base, None])
            if i % 20 == 19:
                err = m.pose_error(self.ik.fk(q, "J1_6"), goal_base)
                if err[0] < self.tol[0] and err[1] < self.tol[1]:
                    break
        return q, err

    def plan(self, q0, ee_current, ee_targets, **kwargs):
        from ..core.planner import PlanResult

        q_now = np.asarray(q0, dtype=np.float64).reshape(-1)[:12].copy()
        goal_base = m.pose_relative(self.base, np.asarray(ee_targets[0], dtype=np.float64).reshape(7))
        seed = q_now.copy()
        seed[list(self.WRAP)] = (seed[list(self.WRAP)] + math.pi) % (2.0 * math.pi) - math.pi
        best = None
        for s in (seed, q_now):
            q, err = self._solve(s, goal_base)
            if err[0] < 5 * self.tol[0] and err[1] < 5 * self.tol[1]:
                cost = float(np.abs(q[:6] - q_now[:6]).max())
                if best is None or cost < best[1]:
                    best = (q, cost)
        if best is None:
            return PlanResult(False, np.zeros((0, 14)), info={"planner": "joint_interp", "error": "no IK solution"})
        q_goal = best[0]
        n = max(30, int(math.ceil(best[1] / (self.joint_speed * CONTROL_DT))))
        traj = np.full((n, 14), np.nan, dtype=np.float64)
        for i in range(n):
            qi = q_now.copy()
            qi[:6] = q_now[:6] + (q_goal[:6] - q_now[:6]) * (i + 1) / n
            traj[i, :7] = m.pose_compose(self.base, self.ik.fk(qi, "J1_6"))
        return PlanResult(
            True, traj, None, CONTROL_DT, {"planner": "joint_interp", "steps": n, "max_joint_move": best[1]}
        )


# --------------------------------------------------------------------------- push
PUSH_DEFAULTS: Dict[str, Any] = {
    "axis": 0,
    "push_target": 0.0,
    "start_local": [0.0, 0.0, 0.19],
    "axis_local": [0.0, -1.0, 0.0],
    "yaw_world_deg": 0.0,
    "base_quat": None,
    "pre_push_offset": 0.015,
    "approach_raise": 0.12,
    "approach_back": 0.02,
    "lead_max": 0.008,
    "done_tol": 0.008,
    "stage_floor": 1,
    "stages": [],
    "speed": 0.0004,
    "steps": 1800,
    "gripper": 0.0,
    "approach_steps": 120,
    "approach_speed": 0.1,
    "hop_tol": 0.008,
    "track_print_every": 60,
    "joint_approach": False,
}


class PushSkill(SkillBase):
    """Staged push of the (released) part along a world axis (see the module docstring).

    Config keys: ``axis`` (0/1/2, the world axis of ``push_target``), ``push_target``
    (object coordinate to reach), ``start_local`` (push start of the hand in the
    part frame), ``base_quat`` (absolute wrist orientation for the push; None = the
    current wrist) and ``yaw_world_deg`` on top of it, ``axis_local`` (the part's own
    slide axis for ``direction: object_axis`` stages), ``pre_push_offset`` /
    ``approach_raise`` / ``approach_back`` (staging geometry), ``lead_max``,
    ``stages`` (list of dicts: ``start_local``, ``speed`` [m/tick], ``steps``,
    ``gripper`` (0 open / 1 closed), ``direction`` (``world`` | ``object_axis``),
    ``end_obj_coord``, ``end_align_deg`` / ``end_align_ticks``, ``stall_ticks`` /
    ``stall_min_coord``, ``exit_retreat`` / ``exit_lift`` (corridor before a
    re-approach), ``done_retreat`` / ``done_lift`` (corridor before the finish)),
    ``stage_floor`` (1-based first stage to run). Without ``stages`` the top-level
    ``speed`` / ``steps`` / ``gripper`` make a single stage.
    """

    name = "push"

    def __init__(self, task, cfg=None, part: int = 0, **kw):
        merged = dict(PUSH_DEFAULTS)
        merged.update({k: v for k, v in (cfg or {}).items()})
        super().__init__(task, merged, part, **kw)
        self.p = {k: merged[k] for k in PUSH_DEFAULTS}
        stages = [dict(s) for s in (self.p["stages"] or [])]
        self.stages: List[Dict[str, Any]] = (
            stages if stages else [{"speed": self.p["speed"], "steps": self.p["steps"], "gripper": self.p["gripper"]}]
        )

    # -- geometry
    def _obj(self) -> np.ndarray:
        return self.task.held_pose(self.part)

    def _coord(self, obj: np.ndarray) -> float:
        """Signed progress of the part along the push axis (positive toward the target)."""
        return float(obj[self._axis]) * self._sign

    def _object_axis_world(self) -> np.ndarray:
        d = m.quat_rotate(self._obj()[3:7], np.asarray(self.p["axis_local"], dtype=np.float64))
        d[2] = 0.0
        n = float(np.linalg.norm(d))
        return d / n if n > 1e-9 else self._world_dir.copy()

    def _push_quat(self, obs) -> np.ndarray:
        q = (
            ee_pose(obs, 0)[3:7].copy()
            if self.p["base_quat"] is None
            else m.quat_normalize(np.asarray(self.p["base_quat"], dtype=np.float64))
        )
        yaw = float(self._st.get("yaw", self.p["yaw_world_deg"]))
        if abs(yaw) > 1e-6:
            q = m.quat_normalize(m.quat_mul(m.quat_from_axis_angle([0.0, 0.0, 1.0], math.radians(yaw)), q))
        return q

    def _start_pos(self) -> np.ndarray:
        obj = self._obj()
        return obj[:3] + m.quat_rotate(
            obj[3:7], np.asarray(self._st.get("start_local", self.p["start_local"]), dtype=np.float64)
        )

    def _grip_of_stage(self) -> int:
        return GRIPPER_CLOSE if float(self._st.get("gripper", self.p["gripper"])) >= 0.5 else GRIPPER_OPEN

    # -- lifecycle
    def start(self, obs, info):
        super().start(obs, info)
        self._axis = int(self.p["axis"])
        obj = self._obj()
        self._sign = 1.0 if float(self.p["push_target"]) >= float(obj[self._axis]) else -1.0
        self._world_dir = np.zeros(3)
        self._world_dir[self._axis] = self._sign
        self._target = float(self.p["push_target"]) * self._sign
        self._hops: List[np.ndarray] = []
        self._hop_quat: Optional[np.ndarray] = None
        self._after_hops = "approach"
        self._stage_i = -1
        self._st: Dict[str, Any] = {}
        self.log(
            f"part {self.part}: push axis {self._axis} {'+' if self._sign > 0 else '-'} from {float(obj[self._axis]):.4f} toward {float(self.p['push_target']):.4f}, {len(self.stages)} stage(s), floor {int(self.p['stage_floor'])}"
        )
        self._apply_stage(
            min(max(0, int(self.p["stage_floor"]) - 1), len(self.stages) - 1), obs, info, from_running=False
        )

    def _apply_stage(self, i: int, obs, info, from_running: bool) -> None:
        st = self.stages[i]
        self._stage_i, self._st = i, st
        self._dir = (
            self._object_axis_world() if str(st.get("direction", "world")) == "object_axis" else self._world_dir.copy()
        )
        self._stall_ref: Optional[float] = None
        self._stall_count = 0
        self._align_count = 0
        self._offset = 0.0
        self._pinned = False
        self._push_steps = 0
        self._grip = self._grip_of_stage()
        self.log(
            f"STAGE {i + 1}/{len(self.stages)}: speed {float(st.get('speed', self.p['speed'])) * 1e3:.2f} mm/tick, budget {int(st.get('steps', self.p['steps']))} ticks, dir {np.round(self._dir, 2).tolist()}, jaws {'closed' if self._grip == GRIPPER_CLOSE else 'open'}"
        )
        hops = []
        if from_running:
            hops = self._corridor(obs, float(st.get("exit_retreat", 0.0)), float(st.get("exit_lift", 0.0)))
        if hops:
            self._after_hops = "approach"
            self._begin_hops(hops, obs, info, "stage-exit corridor")
        else:
            self._begin_approach(obs, info)

    def _corridor(self, obs, retreat: float, lift: float) -> List[np.ndarray]:
        hops: List[np.ndarray] = []
        if retreat <= 0.0 and lift <= 0.0:
            return hops
        wp = ee_pose(obs, 0)[:3].copy()
        if retreat > 0.0:
            wp = wp - self._world_dir * retreat
            hops.append(wp.copy())
        if lift > 0.0:
            wp = wp + np.array([0.0, 0.0, lift])
            hops.append(wp.copy())
        self._hop_quat = ee_pose(obs, 0)[3:7].copy()
        return hops

    def _begin_hops(self, hops: List[np.ndarray], obs, info, why: str) -> None:
        self._hops = list(hops)
        self.set_state("corridor", f"{why}: {len(hops)} hop(s)")
        self._next_hop(obs, info)

    def _next_hop(self, obs, info) -> None:
        target = np.concatenate([self._hops[0], self._hop_quat])
        self.run_sub(
            MoveL(
                target,
                "right",
                steps=60,
                speed=float(self.p["approach_speed"]),
                converge=True,
                tol=(float(self.p["hop_tol"]), 0.1),
                timeout=300,
                name="hop",
            ),
            obs,
            info,
        )

    def _begin_approach(self, obs, info) -> None:
        start = self._start_pos()
        q = self._push_quat(obs)
        self._prepush = np.concatenate([start - self._dir * float(self.p["pre_push_offset"]), q])
        target = self._prepush.copy()
        target[:3] = (
            target[:3]
            - self._dir * float(self.p["approach_back"])
            + np.array([0.0, 0.0, float(self.p["approach_raise"])])
        )
        self.set_state("approach", f"raised staging {np.round(target[:3], 4).tolist()}")
        if self.p["joint_approach"]:  # joint-space approach: the wrist unwinds instead of jamming at a joint limit
            planner = JointInterpPlanner(self.task.scene.base_pose)
            self.run_sub(
                MoveL(
                    target,
                    "right",
                    mode="motiongen",
                    planner=planner,
                    steps=int(self.p["approach_steps"]),
                    speed=float(self.p["approach_speed"]),
                    converge=True,
                    tol=(0.01, 0.05),
                    timeout=900,
                    name="push_approach_joint",
                ),
                obs,
                info,
            )
            return
        self.run_sub(
            MoveL(
                target,
                "right",
                steps=int(self.p["approach_steps"]),
                speed=float(self.p["approach_speed"]),
                converge=True,
                tol=(0.01, 0.05),
                timeout=600,
                name="push_approach",
            ),
            obs,
            info,
        )

    def _begin_prepush(self, obs, info) -> None:
        self.set_state("prepush", f"axis staging {np.round(self._prepush[:3], 4).tolist()}")
        self.run_sub(
            MoveL(
                self._prepush,
                "right",
                steps=int(self.p["approach_steps"]),
                speed=float(self.p["approach_speed"]),
                converge=True,
                tol=(0.005, 0.05),
                timeout=400,
                name="push_prepush",
            ),
            obs,
            info,
        )

    def _begin_push(self, obs) -> None:
        cur = ee_pose(obs, 0)
        self._start_eef_pos = cur[:3].copy()
        self._start_eef_quat = cur[3:7].copy()
        self._offset = 0.0
        self._push_steps = 0
        self._pinned = False
        self.set_state("push", f"stroke from {np.round(cur[:3], 4).tolist()}")

    def _stage_done(self, why: str, obs, info) -> Action:
        nxt = self._stage_i + 1
        if nxt < len(self.stages):
            self.log(f"STAGE {self._stage_i + 1} done ({why}) - entering stage {nxt + 1}")
            self._apply_stage(nxt, obs, info, from_running=True)
            return self.sub_step(obs, info)
        self.log(f"STAGE {self._stage_i + 1} done ({why}) - all stages complete")
        hops = self._corridor(obs, float(self._st.get("done_retreat", 0.0)), float(self._st.get("done_lift", 0.0)))
        if hops:
            self._after_hops = "finish"
            self._begin_hops(hops, obs, info, "park-exit corridor")
            return self.sub_step(obs, info)
        self._finish_push()
        return self.hold()

    def _finish_push(self) -> None:
        obj = self._obj()
        reached = self._coord(obj) >= self._target - float(self.p["done_tol"])
        self.finish(
            f"pushed: {float(obj[self._axis]):.4f} vs target {float(self.p['push_target']):.4f} ({'reached' if reached else 'short'})"
        )

    # -- per tick
    def step(self, obs, info) -> Action:
        self._t += 1
        if self._finished:
            return self.hold()
        if self.state == "corridor":
            if self.sub_done(obs, info):
                self._hops.pop(0)
                if self._hops:
                    self._next_hop(obs, info)
                elif self._after_hops == "finish":
                    self._finish_push()
                    return self.hold()
                else:
                    self._begin_approach(obs, info)
            return self.sub_step(obs, info)
        if self.state == "approach":
            if self.sub_done(obs, info):
                self.log(f"approach done: {self._sub.done_reason}")
                self._begin_prepush(obs, info)
            return self.sub_step(obs, info)
        if self.state == "prepush":
            if self.sub_done(obs, info):
                self.log(f"prepush done: {self._sub.done_reason}")
                self._begin_push(obs)
                return self._push_tick(obs, info)
            return self.sub_step(obs, info)
        if self.state == "push":
            return self._push_tick(obs, info)
        return self.hold()

    def _push_tick(self, obs, info) -> Action:
        st = self._st
        obj = self._obj()
        coord_w = self._coord(obj)
        if coord_w >= self._target:
            return self._stage_done("axis target reached", obs, info)
        if "end_obj_coord" in st:
            end = min(float(st["end_obj_coord"]) * self._sign, self._target)
            if coord_w >= end:
                return self._stage_done("depth reached", obs, info)
        if "end_align_deg" in st:
            ang = G.angle_between_deg(self._object_axis_world(), self._world_dir)
            self._align_count = self._align_count + 1 if ang <= float(st["end_align_deg"]) else 0
            if self._align_count >= int(st.get("end_align_ticks", 15)):
                return self._stage_done(f"axis aligned ({ang:.2f} deg for {self._align_count} ticks)", obs, info)
        stall_lim = int(st.get("stall_ticks", 0))
        if stall_lim > 0:
            coord = float(np.dot(obj[:3], self._dir))
            min_c = st.get("stall_min_coord")
            if ("speed" in st and not self._pinned) or (min_c is not None and coord < float(min_c)):
                self._stall_ref, self._stall_count = coord, 0  # free air, or not deep enough to count
            elif self._stall_ref is None or coord > self._stall_ref + 0.001:
                self._stall_ref, self._stall_count = coord, 0
            else:
                self._stall_count += 1
                if self._stall_count >= stall_lim:
                    return self._stage_done(f"object stalled {self._stall_count} ticks at {coord:.4f}", obs, info)
        # stroke: the waypoint advances at `speed`, clamped to lead_max ahead of the measured hand
        eef = ee_pose(obs, 0)
        prog = float(np.dot(eef[:3] - self._start_eef_pos, self._dir))
        want = self._offset + float(st.get("speed", self.p["speed"]))
        cap = prog + float(self.p["lead_max"])
        self._pinned = want > cap
        self._offset = min(want, cap)
        cmd = np.concatenate([self._start_eef_pos + self._dir * self._offset, self._start_eef_quat])
        self._push_steps += 1
        if int(self.p["track_print_every"]) > 0 and self._push_steps % int(self.p["track_print_every"]) == 1:
            self.log(
                f"S{self._stage_i + 1} tick={self._push_steps} offset={self._offset * 1e3:.1f} mm prog={prog * 1e3:.1f} mm lead={(self._offset - prog) * 1e3:.1f} mm obj={float(obj[self._axis]):.4f} {'pressing' if self._pinned else 'free'}"
            )
        if self._push_steps >= int(st.get("steps", self.p["steps"])):
            return self._stage_done("steps budget spent", obs, info)
        return self.act(cmd, self._grip)
