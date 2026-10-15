"""Authoring controller (Sharpa Wave on the Marvin right arm): closed-loop scripted battery swap, recorded as
open-loop actuator rows.

The controller reads simulator state only to plan its next motor targets: fingertip inverse kinematics over the
right arm's seven joints plus the finger joints (collision margins against the remote, tray, cells and table), and
straight-line hand-root motions between key postures (damped-least-squares arm IK every control). Each row adds the
gravity/bias torque of every actuated joint divided by its servo gain (a feed-forward on plain position targets) and
a proportional finger boost. The recorded rows are plain actuator targets that replay without the controller.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

os.environ.setdefault("MUJOCO_GL", "egl")
import mujoco
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation, Slerp

from runtime import Session

HERE = Path(__file__).resolve().parent
sys.path.append(str(HERE.parents[1] / "shared"))
import arm_ik  # noqa: E402  (authoring-only helper)
import arm_rig  # noqa: E402

FINGERS = ("thumb", "index", "middle", "ring", "pinky")
FINGER_COUNTS = {"thumb": 5, "index": 4, "middle": 4, "ring": 4, "pinky": 5}
CURLED = {"middle": [1.3, 0.0, 1.5, 0.9], "ring": [1.3, 0.0, 1.5, 0.9], "pinky": [0.1, 1.3, 0.0, 1.5, 0.9]}
PITCH = 0.45  # fingers pitched down from horizontal (natural for an arm reaching forward and down to a table)


def hand_rotation(fingers_dir, palm_dir):
    """Wave hand frame: fingers +Z, palm normal +X, thumb +Y."""
    z = np.asarray(fingers_dir, float)
    z /= np.linalg.norm(z)
    x = np.asarray(palm_dir, float)
    x -= z * (x @ z)
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    return np.column_stack([x, y, z])


def yaw_rotation(yaw, pitch=PITCH):
    """Palm down, fingers along heading ``yaw`` pitched down by ``pitch``, thumb to the left of the fingers."""
    f = np.array([np.cos(yaw) * np.cos(pitch), np.sin(yaw) * np.cos(pitch), -np.sin(pitch)])
    palm = np.array([-np.cos(yaw) * np.sin(pitch), -np.sin(yaw) * np.sin(pitch), -np.cos(pitch)])
    return hand_rotation(f, palm)


class Controller:
    tip_axis_sign = 1.0  # +1: the fingertip geom's z axis points out of the fingertip (Sharpa capsules)

    def __init__(self, session: Session, log=print):
        self.s = session
        self.m = session.model
        self.d = session.data
        self.log = log
        m = self.m
        self.scratch = mujoco.MjData(m)
        self.gains = m.actuator_gainprm[:, 0].copy()
        self.lo, self.hi = m.actuator_ctrlrange.T.copy()
        self.target = session.hold_action().copy()
        self.phases = []
        lay = arm_rig.layout(m)
        self.WRIST = list(range(lay["arm"]["right"].start, lay["arm"]["right"].stop))
        f0 = lay["fingers"]["right"].start
        self.ACT, k = {}, f0
        for f in FINGERS:
            self.ACT[f] = list(range(k, k + FINGER_COUNTS[f]))
            k += FINGER_COUNTS[f]
        self.release_slice = slice(f0, f0 + 9)  # thumb + index
        self.finger_cols = np.arange(lay["fingers"]["left"].start, lay["fingers"]["right"].stop)
        self.tip = {f: m.geom(f"right_{f}_fingertip_collision").id for f in FINGERS}
        self.hand_body = m.body("right_hand_C_MC").id
        right = arm_rig.hand_body_ids(m, "right")
        self.hand_geoms = [g for g in range(m.ngeom) if int(m.geom_bodyid[g]) in right and m.geom_contype[g]]
        own = session.checker.geom_owner
        self.obstacle = {}
        for g in range(m.ngeom):
            if own[g] in ("remote", "tray", "old_cell", "new_cell") and (m.geom_contype[g] or m.geom_conaffinity[g]):
                self.obstacle.setdefault(own[g], []).append(g)
        self.obstacle["table"] = [m.geom("table").id]
        self.ik = arm_ik.ArmIK(m, "right", body="right_hand_C_MC")
        self.max_ik_err = (0.0, 0.0)

    # ------------------------------------------------------------------------------------------ kinematics
    def fk(self, q):
        d = self.scratch
        d.qpos[:] = self.d.qpos
        d.qpos[self.s.qadr] = q
        mujoco.mj_kinematics(self.m, d)
        mujoco.mj_comPos(self.m, d)
        return d

    def pose(self, q):
        d = self.fk(q)
        return d.xpos[self.hand_body].copy(), d.xmat[self.hand_body].reshape(3, 3).copy()

    def at_pose(self, q, pos=None, R=None, dp=None):
        """``q`` with the arm joints re-solved so the hand root reaches ``pos`` (or its pose + ``dp``) and ``R``."""
        p0, R0 = self.pose(q)
        pos = (p0 if pos is None else np.asarray(pos, float)) + (0 if dp is None else np.asarray(dp, float))
        R = R0 if R is None else R
        out = np.asarray(q, float).copy()
        best = None
        for seed in (out[self.WRIST], self.target[self.WRIST]):
            arm, ep, er = self.ik.solve(pos, R, q0=seed, qpos=self.d.qpos, iters=300)
            if best is None or ep + 0.1 * er < best[1] + 0.1 * best[2]:
                best = (arm, ep, er)
        arm, ep, er = best
        if ep > 0.001 or er > 0.01:
            arm2, ep2, er2 = self.arm_lsq(pos, R, out)
            if ep2 + 0.1 * er2 < ep + 0.1 * er:
                arm, ep, er = arm2, ep2, er2
        if ep > 0.003 or er > 0.03:
            self.log(f"  warning: arm IK error {ep * 1000:.1f} mm / {er:.3f} rad")
        out[self.WRIST] = arm
        return out

    def arm_lsq(self, pos, R, q):
        """Bounded least-squares arm IK for a hand-root pose (more robust than DLS far from the seed)."""
        q = np.asarray(q, float).copy()
        lo, hi = self.lo[self.WRIST] + 0.02, self.hi[self.WRIST] - 0.02

        def residual(values):
            q[self.WRIST] = values
            d = self.fk(q)
            return np.concatenate([(d.xpos[self.hand_body] - pos) * 100,
                                   (d.xmat[self.hand_body].reshape(3, 3) - R).ravel() * 0.5,
                                   (values - x0) * 0.002])

        x0 = np.clip(q[self.WRIST], lo + 1e-6, hi - 1e-6)
        fit = least_squares(residual, x0, bounds=(lo, hi), max_nfev=400)
        p, Rn = self.pose(np.r_[q[: self.WRIST[0]], fit.x, q[self.WRIST[-1] + 1:]])
        return fit.x, float(np.linalg.norm(p - pos)), float(np.linalg.norm(arm_ik.rot_error(R, Rn)))

    def solve(self, tips, seed, variable, R_hand=None, rot_weight=0.5, avoid=(), avoid_margin=0.002, allow=(),
              reg=0.01, max_nfev=200, pad=False, tip_axis=None, axis_weight=2.0):
        """Least-squares IK: ``tips`` = {finger: world point for the fingertip capsule centre (or pad centre)}."""
        m = self.m
        q = np.asarray(seed, float).copy()
        variable = np.asarray(variable)
        lo, hi = self.lo[variable].copy(), self.hi[variable].copy()
        lo[np.isin(variable, self.WRIST)] += 0.02
        hi[np.isin(variable, self.WRIST)] -= 0.02
        initial = q[variable].copy()
        obstacles = [g for name in avoid for g in self.obstacle[name]]
        checked = [g for g in self.hand_geoms if not any(m.geom(g).name.startswith(f"right_{f}_fingertip") for f in allow)]

        def residual(values):
            q[variable] = values
            d = self.fk(q)
            errors = []
            for finger, point in tips.items():
                errors.extend((self.tip_point(d, finger, pad) - point) * 100)
            for finger, axis in (tip_axis or {}).items():
                g = self.tip[finger]
                errors.extend((self.tip_axis_sign * d.geom_xmat[g].reshape(3, 3)[:, 2] - axis) * axis_weight)
            if R_hand is not None:
                R = d.xmat[self.hand_body].reshape(3, 3)
                errors.extend((R - R_hand).ravel() * rot_weight)
            for gid in checked:
                for ob in obstacles:
                    dist = mujoco.mj_geomDistance(m, d, gid, ob, 0.02, None)
                    errors.append(min(0.0, dist - avoid_margin) * 300)
            errors.extend((values - initial) * reg)
            return np.asarray(errors)

        x0 = np.clip(initial, lo + 1e-6, hi - 1e-6)
        fit = least_squares(residual, x0, bounds=(lo + 1e-9, hi - 1e-9), max_nfev=max_nfev)
        q[variable] = fit.x
        d = self.fk(q)
        err = {f: float(np.linalg.norm(self.tip_point(d, f, pad) - p)) for f, p in tips.items()}
        return q, err, fit.cost

    def tip_point(self, d, finger, pad):
        """Capsule centre, or (pad=True) the centre of its distal hemisphere (the fingertip pad)."""
        g = self.tip[finger]
        if not pad:
            return d.geom_xpos[g]
        return d.geom_xpos[g] + self.m.geom_size[g, 1] * d.geom_xmat[g].reshape(3, 3)[:, 2]

    # ------------------------------------------------------------------------------------------ execution
    default_boost = 2.0

    def execute(self, target, count, phase, boost=None, cartesian=True):
        """Blend to ``target`` over ``count`` controls: the hand root moves on a straight line (slerp rotation),
        the arm joints come from IK at every control, the other columns blend linearly (smoothstep timing)."""
        boost = self.default_boost if boost is None else boost
        s = self.s
        start = self.target.copy()
        target = np.asarray(target, float).copy()
        if cartesian:
            p0, R0 = self.pose(start)
            p1, R1 = self.pose(target)
            slerp = Slerp([0, 1], Rotation.from_matrix([R0, R1]))
        arm = start[self.WRIST].copy()
        for ratio in np.linspace(0, 1, count + 1)[1:]:
            if s.done:
                break
            blend = ratio * ratio * (3 - 2 * ratio)
            row = start + (target - start) * blend
            if cartesian:
                p = p0 + (p1 - p0) * blend
                R = slerp([blend]).as_matrix()[0]
                arm, ep, er = self.ik.solve(p, R, q0=arm, qpos=self.d.qpos, iters=60)
                if ep > 0.002 or er > 0.02:
                    arm, ep, er = self.arm_lsq(p, R, row)
                self.max_ik_err = (max(self.max_ik_err[0], ep), max(self.max_ik_err[1], er))
                row[self.WRIST] = arm
            self.target = row
            action = self.target + self.d.qfrc_bias[s.dofs] / self.gains
            cols = self.finger_cols
            action[cols] += boost * (self.target[cols] - self.d.qpos[s.qadr[cols]])
            # stay 1e-5 inside the native bounds so float32-rounded rows stay valid
            action = np.clip(action, self.lo + 1e-5, self.hi - 1e-5)
            s.step(action)
            self.phases.append(phase)
        f = s.features()
        self.log(f"[{s.steps:5d}] {phase:32s} stage={f['stage']} cover={f['cover_slide_m']:.4f} "
                 f"tab={f['tab_depth_m'] * 1000:.2f}mm hand={f['hand_contacts']} fail={f['failure']} "
                 f"remote_disp={f['remote_displacement_m']:.4f}")
        return f

    def hold(self, count, phase, boost=None):
        return self.execute(self.target.copy(), count, phase, boost, cartesian=False)

    def body_pos(self, name):
        return self.d.xpos[self.m.body(name).id].copy()

    def body_axis(self, name, k=2):
        return self.d.xmat[self.m.body(name).id].reshape(3, 3)[:, k].copy()

    def remote_yaw(self):
        Rr = self.d.xmat[self.m.body("remote").id].reshape(3, 3)
        return float(np.arctan2(Rr[1, 0], Rr[0, 0]))


# ---------------------------------------------------------------------------------------------- task phases
TIP_R = 0.008


def base_seed(c, q=None):
    seed = (c.target if q is None else q).copy()
    seed[c.ACT["thumb"]] = [0.3, 0.0, 0.3, 0.0, 0.5]
    seed[c.ACT["index"]] = [1.2, 0.0, 1.0, 0.6]
    for f, v in CURLED.items():
        seed[c.ACT[f]] = v
    return seed


TAB_LOCAL = np.array([-0.06, 0.0, 0.019])  # thumb-tab top centre in the remote frame with the door shut


def tab_point(c, opened):
    """World position of the thumb-tab top centre with the door ``opened`` metres open."""
    Rr = c.d.xmat[c.m.body("remote").id].reshape(3, 3)
    return c.body_pos("remote") + Rr @ (TAB_LOCAL + np.array([-opened, 0, 0]))


def tab_depth(c):
    return float(c.d.qpos[c.m.jnt_qposadr[c.m.joint("tab_depth").id]])


def press_tab(c, q_pre, steps=40, step_dz=0.0006, want=0.0036, max_extra=0.008, phase="press the tab"):
    """Lower the pressing finger (hand root straight down) until the latch tab is ``want`` deep (closed loop)."""
    q = q_pre.copy()
    c.execute(q, steps, phase)
    extra = 0.0
    while tab_depth(c) < want and extra < max_extra and not c.s.done:
        q = c.at_pose(q, dp=(0, 0, -step_dz))
        extra += step_dz
        c.execute(q, 4, phase)
    c.hold(6, phase)
    c.log(f"  tab depth {tab_depth(c) * 1000:.2f} mm after {extra * 1000:.1f} mm extra")
    return q


def door_press_postures(c, opened, seed, press=0.0045, pitch=0.75):
    """Index pad over / pressed into the latch tab (fingers pitched down toward +x, palm down)."""
    tab = tab_point(c, opened)
    R = yaw_rotation(c.remote_yaw(), pitch)
    var = c.WRIST + c.ACT["index"]
    pre = tab + np.array([0.0, 0.0, 0.012 + TIP_R])
    down = tab + np.array([0.0, 0.0, -press + TIP_R])
    axis = {"index": np.array([0.35, 0.0, -0.94]) / np.linalg.norm([0.35, 0.0, -0.94])}
    q_pre, e1, _ = c.solve({"index": pre}, seed, var, R_hand=R, rot_weight=0.2, avoid=("remote",), allow=("index",),
                           pad=True, tip_axis=axis)
    q_down, e2, _ = c.solve({"index": down}, q_pre, var, R_hand=R, rot_weight=0.2, allow=("index",), pad=True,
                            tip_axis=axis)
    c.log(f"door press ik pre={e1} down={e2}")
    return q_pre, q_down


def slide_posture(c, q, opened_to, pitch=0.75):
    """The pressing posture moved along with the door to ``opened_to`` (fingertip IK; the index pad keeps its depth)."""
    d = c.fk(q)
    pad = c.tip_point(d, "index", True)
    tab_now = tab_point(c, float(c.d.qpos[c.s.checker.cover_qadr]))
    target = tab_point(c, opened_to) + (pad - tab_now)
    axis = {"index": np.array([0.35, 0.0, -0.94]) / np.linalg.norm([0.35, 0.0, -0.94])}
    q2, e, _ = c.solve({"index": target}, q, c.WRIST + c.ACT["index"], R_hand=yaw_rotation(c.remote_yaw(), pitch),
                       rot_weight=0.2, allow=("index",), pad=True, tip_axis=axis)
    c.log(f"slide posture ik {e}")
    return q2


def phase_open_cover(c, travel=0.080):
    seed = base_seed(c)
    q_pre, q_down = door_press_postures(c, 0.0, seed)
    above = c.at_pose(q_pre, dp=(0, 0, 0.08))
    c.execute(above, 70, "approach above the door")
    c.execute(q_pre, 50, "finger over the latch tab")
    q = press_tab(c, q_down, phase="press the latch tab")
    push = slide_posture(c, q, travel)
    c.execute(push, 160, "slide the door open")
    c.hold(15, "door open")
    lift = c.at_pose(push, dp=(0, 0, 0.06))
    c.execute(lift, 40, "lift off the door")
    return lift


def pinch_targets(center, across, clearance, dz):
    """Pad centres: thumb on the +across side, index on the -across side of a cell centre."""
    across = np.asarray(across, float)
    up = np.array([0, 0, dz])
    return {"thumb": center + (0.007 + 0.00943 + clearance) * across + up,
            "index": center - (0.007 + 0.00806 + clearance) * across + up}


def pad_pinch(c, name, yaw, dz, open_clear, squeeze, tilt, avoid, seed, pitch=PITCH, rot_weight=0.4):
    """Thumb/index pad pinch across a lying cell: open and closed postures (IK, collision margins)."""
    var = c.WRIST + c.ACT["thumb"] + c.ACT["index"]
    cell = c.body_pos(name)
    R = yaw_rotation(yaw, pitch)
    across = np.array([-np.sin(yaw), np.cos(yaw), 0.0])
    down = np.array([0, 0, -1.0])
    # fingertip capsules nearly vertical, tilted slightly toward the cell: pads meet it just above its equator
    axes = {"thumb": down * np.cos(tilt) - across * np.sin(tilt), "index": down * np.cos(tilt) + across * np.sin(tilt)}
    q_open, e1, _ = c.solve(pinch_targets(cell, across, open_clear, dz), seed, var, R_hand=R, rot_weight=rot_weight,
                            avoid=tuple(avoid) + (name,), avoid_margin=0.0008, pad=True, tip_axis=axes)
    q_close, e2, _ = c.solve(pinch_targets(cell, across, squeeze, dz), q_open, var, R_hand=R, rot_weight=rot_weight,
                             avoid=tuple(avoid), avoid_margin=0.0003, allow=("thumb", "index"), pad=True,
                             tip_axis=axes)
    c.log(f"{name} pinch ik open={e1} close={e2} rot dev {np.linalg.norm(c.pose(q_close)[1] - R):.3f}")
    return q_open, q_close


def phase_old_to_tray(c, start, release_clearance=0.004, squeeze=-0.006, lower_steps=110, pitch=1.2, rot_weight=1.5):
    q_open, q_close = pad_pinch(c, "old_cell", c.remote_yaw(), 0.0025, 0.004, squeeze, 0.12, ("remote",),
                                base_seed(c, start), pitch=pitch, rot_weight=rot_weight)
    above = c.at_pose(q_open, dp=(0, 0, 0.06))
    c.execute(above, 60, "over the old cell")
    c.execute(q_open, 60, "fingers beside the old cell")
    c.execute(q_close, 40, "pinch the old cell")
    c.hold(30, "stabilize the pinch")
    up = c.at_pose(q_close, dp=(0, 0, 0.07))
    c.execute(up, 60, "lift the old cell")
    tray = c.body_pos("tray")
    floor_top = tray[2] + 0.003
    d = tray - c.body_pos("old_cell")
    carry = c.at_pose(up, dp=(d[0], d[1], 0.0))
    c.execute(carry, 120, "carry to the tray")
    c.hold(20, "settle over the tray")
    d = tray - c.body_pos("old_cell")
    carry = c.at_pose(carry, dp=(d[0], d[1], (floor_top + 0.007 + release_clearance) - c.body_pos("old_cell")[2]))
    c.execute(carry, lower_steps, "lower into the tray")
    c.hold(20, "settle in the tray")
    release = carry.copy()
    release[c.release_slice] = q_open[c.release_slice]
    c.execute(release, 40, "open the pinch")
    c.hold(30, "let the old cell rest")
    away = c.at_pose(release, dp=(0, 0, 0.08))
    c.execute(away, 50, "withdraw from the tray")
    return away


def rotate_about(c, q, center, delta):
    """``q`` with the whole hand turned by ``delta`` (rad) about a vertical axis through ``center``."""
    p, R = c.pose(q)
    Rz = Rotation.from_euler("z", delta).as_matrix()
    return c.at_pose(q, pos=center + Rz @ (p - center), R=Rz @ R)


def cell_yaw(c, name):
    axis = c.body_axis(name)
    return float(np.arctan2(axis[1], axis[0]))


def wrap(a):
    return float(np.angle(np.exp(1j * a)))


def phase_new_pick(c, start, dz=0.003, squeeze=-0.003, tilt=0.3, pitch=1.2, rot_weight=1.5):
    yaw = cell_yaw(c, "new_cell")
    q_open, q_close = pad_pinch(c, "new_cell", yaw, dz, 0.006, squeeze, tilt, ("table",), base_seed(c, start),
                                pitch=pitch, rot_weight=rot_weight)
    above = c.at_pose(q_open, dp=(0, 0, 0.07))
    c.execute(above, 90, "over the new cell")
    c.execute(q_open, 60, "fingers beside the new cell")
    c.execute(q_close, 40, "pinch the new cell")
    c.hold(30, "stabilize the pinch")
    up = c.at_pose(q_close, dp=(0, 0, 0.07))
    c.execute(up, 60, "lift the new cell")
    return up, q_open


def phase_new_seat(c, up, q_open, yaw_steps=120, carry_steps=(70, 25, 25), lower=((0.012, 50), (0.0, 50)),
                   release_dz=0.0025, release_clear=0.003, release_tilt=0.12, withdraw_steps=70):
    s = c.s
    remote = c.body_pos("remote")
    Rr = c.d.xmat[c.m.body("remote").id].reshape(3, 3)
    slot = remote + Rr @ np.asarray(s.config["slot_center_local"])
    # turn the hand so the cell's + end points along the remote's +x (toward the gold contact)
    carry = rotate_about(c, up, c.body_pos("new_cell"), wrap(c.remote_yaw() - cell_yaw(c, "new_cell")))
    c.execute(carry, yaw_steps, "turn the cell: + end to the gold contact")
    for steps in carry_steps:
        d = slot - c.body_pos("new_cell")
        carry = c.at_pose(carry, dp=(d[0], d[1], 0.0))
        c.execute(carry, steps, "carry over the slot")
        carry = rotate_about(c, carry, c.body_pos("new_cell"), wrap(c.remote_yaw() - cell_yaw(c, "new_cell")))
    for offset, steps in lower:
        cell = c.body_pos("new_cell")
        carry = c.at_pose(carry, dp=(0, 0, (slot[2] + offset) - cell[2]))
        c.execute(carry, steps, "lower into the slot")
    c.hold(20, "settle in the slot")
    # Release inside the narrow (source-width) cavity: open the pads only slightly, to a posture that clears the
    # cavity walls (IK with collision margins), then withdraw straight up.
    # The arm stays where it is; only the thumb and index open, to pads 3 mm clear of the cell and clear of the walls.
    cell = c.body_pos("new_cell")
    yaw = c.remote_yaw()
    across = np.array([-np.sin(yaw), np.cos(yaw), 0.0])
    q_rel, e, _ = c.solve(pinch_targets(cell, across, release_clear, release_dz), c.target.copy(),
                          c.ACT["thumb"] + c.ACT["index"], avoid=("remote", "new_cell"), avoid_margin=0.0005, pad=True)
    c.log(f"release ik {e}")
    c.execute(q_rel, 40, "release the new cell", cartesian=False)
    c.hold(30, "let the new cell seat")
    away = c.at_pose(c.target, dp=(0, 0, 0.07))
    c.execute(away, withdraw_steps, "withdraw from the slot")
    return away


def phase_close_cover(c, start, overshoot=0.003):
    s = c.s
    opened = float(c.d.qpos[s.checker.cover_qadr])
    q_pre, q_down = door_press_postures(c, opened, base_seed(c, start))
    above = c.at_pose(q_pre, dp=(0, 0, 0.08))
    c.execute(above, 80, "move over the open door's tab")
    c.execute(q_pre, 50, "finger over the latch tab")
    q = press_tab(c, q_down, phase="press the latch tab")
    push = slide_posture(c, q, -overshoot)
    c.execute(push, 160, "slide the door shut")
    c.hold(15, "door shut, tab pressed")
    lift = c.at_pose(push, dp=(0, 0, 0.05))
    c.execute(lift, 40, "release the tab: hook behind the stop")
    away = c.at_pose(lift, dp=(0, 0, 0.08))
    c.execute(away, 60, "hand clear of the remote")
    return away


def make_demo(output, slack_rows=150, log=print, seat_kw=None, tray_kw=None):
    """Run the scripted controller from the frozen reset and save the executed rows plus hold rows."""
    s = Session()
    c = Controller(s, log=log)
    t0 = time.time()
    c.hold(25, "settle")
    q = phase_open_cover(c)
    q = phase_old_to_tray(c, q, **(tray_kw or {}))
    up, q_open = phase_new_pick(c, q)
    q = phase_new_seat(c, up, q_open, **(seat_kw or {}))
    q = phase_close_cover(c, q)
    c.hold(120, "released hold")
    status = s.status()
    actions = np.asarray(s.actions)
    success_step = s.steps if s.success else None
    # Slack: the episode ends at success; extra hold rows keep the hand still if a replay succeeds later.
    rows = np.concatenate([actions, np.repeat(actions[-1:], slack_rows, axis=0)]) if len(actions) else actions
    phases = np.asarray(c.phases + ["hold (slack)"] * slack_rows)[: len(rows)]
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    s.save_trajectory(rows, out)
    np.savez_compressed(out.with_suffix(".phases.npz"), phases=phases)
    summary = {
        "success": bool(s.success), "success_step": success_step, "rows": int(len(rows)),
        "executed_rows": int(len(actions)), "reason": status["reason"], "stage_steps": status.get("stage_steps"),
        "final_sha": s.state_sha(), "seconds": round(time.time() - t0, 1),
        "max_arm_ik_error": {"m": c.max_ik_err[0], "rad": c.max_ik_err[1]},
    }
    out.with_suffix(".live.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
    log(json.dumps(summary, default=str))
    s.close()
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--slack-rows", type=int, default=150)
    args = parser.parse_args()
    make_demo(args.out, args.slack_rows)
