"""Authoring-only closed-loop controller that produces the oracle rows (never shipped to the agent or verifier).

The controller reads privileged simulator state (bin / vacuum poses) to choose the next wrist-stage and finger
targets; only those targets are recorded. The rows are then an ordinary open-loop trajectory that the
deterministic simulator replays bit for bit.

Phases: poke the release button with the index finger (the freed bin tips forward onto the counter edge), lift the
finger, power-grasp the bin's nozzle, lift the bin out over the lower lip and carry it away, bring it back into the
lower seat (tabs first), rotate it closed about the lower tabs until the latch tooth snaps behind the catch, open the
hand, retract, hold.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation as Rot

from runtime import Session


def unit(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


class Author:
    def __init__(self, hand="sharpa", log=print):
        self.s = Session(hand=hand)
        self.m, self.d = self.s.model, self.s.data
        self.log = log
        self.origin = np.asarray(self.s.config["wrist_stage"]["origin"], float)
        self.root = self.m.body("right_hand_C_MC").id if hand == "sharpa" else self.m.body("right_hand_C_MC").id
        self.vac, self.bin = self.s.checker.vac, self.s.checker.bin
        self.Rv0 = self.d.xmat[self.vac].reshape(3, 3).copy()
        self.pv0 = self.d.xpos[self.vac].copy()
        self.ctrl = self.s.hold_action()
        names = self.s.actuator_names
        cols = lambda pred: np.array([i for i, n in enumerate(names) if pred(n)])  # noqa: E731
        self.RF = cols(lambda n: n.startswith(("right_", "r_wuji_")))  # right fingers
        self.LW = cols(lambda n: n.startswith("left_wrist_"))  # left stage
        self.LF = cols(lambda n: n.startswith(("left_", "l_wuji_")) and not n.startswith("left_wrist_"))
        self.lroot = self.m.body("left_hand_C_MC").id if self.s.hand == "sharpa" else self.m.body("left_hand_C_MC").id
        self.lorigin = np.asarray(self.s.config["left_wrist_stage"]["origin"], float)
        self.fingers = self.ctrl[self.RF].copy()
        self.lo, self.hi = self.m.actuator_ctrlrange.T
        self.euler = self.ctrl[3:6].copy()
        self.integ_cap, self.integ_r_cap = 0.02, 0.3

    # ------------------------------------------------------------------ frames
    def L(self, p):
        """Vacuum-local point -> world (reset vacuum frame)."""
        return self.pv0 + self.Rv0 @ np.asarray(p, float)

    def Ld(self, v):
        return self.Rv0 @ np.asarray(v, float)

    def hand_pose(self):
        return self.d.xpos[self.root].copy(), self.d.xmat[self.root].reshape(3, 3).copy()

    def bin_pose(self):
        return self.d.xpos[self.bin].copy(), self.d.xmat[self.bin].reshape(3, 3).copy()

    def R0(self):
        return np.array([[0, 0, 1], [0, 1, 0], [-1, 0, 0]], float)

    def wrist_from_root(self, pos, R_root):
        """Wrist-stage targets that put the hand root at ``pos`` with orientation ``R_root``."""
        R_e = R_root @ self.R0().T
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            a, b, c = Rot.from_matrix(R_e).as_euler("XYZ")
        best = None
        # both XYZ solution families, every 2*pi branch: keep the one closest to the current command
        for base in (np.array([a, b, c]), np.array([a + np.pi, np.pi - b, c + np.pi])):
            for k in np.ndindex(3, 3, 3):
                cand = base + (np.array(k) - 1) * 2 * np.pi
                if np.all(np.abs(cand) <= 3.2) and (best is None or np.linalg.norm(cand - self.euler)
                                                     < np.linalg.norm(best - self.euler)):
                    best = cand
        return np.r_[pos - self.origin, best]

    @staticmethod
    def frame(f, t):
        """Root orientation with fingers along ``f`` and thumb side along ``t`` (palm = -(f x t))."""
        f = unit(f)
        t = unit(t - (t @ f) * f)
        dorsal = np.cross(f, t)
        # canonical hand at zero euler: fingers +x, thumb +y, dorsal +z (palm -z) => R_e = [f t dorsal]
        R_e = np.column_stack([f, t, dorsal])
        return R_e @ np.array([[0, 0, 1], [0, 1, 0], [-1, 0, 0]], float)

    def tip_offset(self, fingers, site):
        """Fingertip site offset from the root (root frame) for a finger posture."""
        m, d = self.m, mujoco.MjData(self.m)
        d.qpos[:] = self.d.qpos
        d.qpos[self.s.qadr[self.RF]] = fingers
        mujoco.mj_kinematics(m, d)
        R = d.xmat[self.root].reshape(3, 3)
        return R.T @ (d.site_xpos[m.site(site).id] - d.xpos[self.root])

    # ------------------------------------------------------------------ stepping
    def step(self, wrist=None, fingers=None):
        if wrist is not None:
            self.ctrl[:6] = wrist
            self.euler = np.asarray(wrist[3:6], float)
        if fingers is not None:
            self.ctrl[self.RF] = fingers
        self.ctrl = np.clip(self.ctrl, self.lo, self.hi)
        st = self.s.step(self.ctrl.copy())
        return st

    def move(self, wrist=None, fingers=None, steps=25, settle=0):
        w0, f0 = self.ctrl[:6].copy(), self.ctrl[self.RF].copy()
        w1 = w0 if wrist is None else np.asarray(wrist, float)
        f1 = f0 if fingers is None else np.asarray(fingers, float)
        st = None
        for i in range(1, steps + 1):
            a = i / steps
            a = a * a * (3 - 2 * a)
            st = self.step(w0 + (w1 - w0) * a, f0 + (f1 - f0) * a)
            if self.s.done:
                return st
        for _ in range(settle):
            st = self.step()
            if self.s.done:
                return st
        return st

    def info(self, tag):
        st = self.s.status()
        self.log(f"[{self.s.steps:5d}] {tag}: stage={st['stage']} seat={st['seat_distance_m']:.4f}m/"
                 f"{st['seat_angle_rad']:.3f}rad button={st['button_travel_m']*1000:.2f}mm "
                 f"catch={st['catch_behind_tooth_m']*1000:.2f}mm hand={st['hand_contacts']}{st['hand_contact_fingers']} "
                 f"body={st['body_displacement_m']*1000:.1f}mm fail={st['failure']}")
        return st

    # ------------------------------------------------------------------ left hand: hold the vacuum by its handle
    GRIP = (0.11, 0.0, 0.0889)  # on the handle grip axis (vacuum frame); grip axis (0.88, 0, -0.47), radius 14 mm
    LEFT_WRAP = np.array([1.2, 0.0, 0.6, 0.0, 0.6, 1.5, 0, 1.4, 1.0, 1.5, 0, 1.4, 1.0, 1.5, 0, 1.4, 1.0,
                          0.1, 1.5, 0, 1.4, 1.0])
    LEFT_OPEN = np.array([0.6, 0.0, 0.2, 0.0, 0.2, 0.2, 0, 0.2, 0.1, 0.2, 0, 0.2, 0.1, 0.2, 0, 0.2, 0.1,
                          0.0, 0.2, 0, 0.2, 0.1])

    def left_frame(self):
        """Left root over the grip: palm down onto it, fingers across it toward the vacuum's right (-y)."""
        g = unit(self.Ld([0.88, 0, -0.47]))
        f = unit(self.Ld([0, -1, 0]))
        x = np.cross(g, f)  # palm normal (points down onto the grip)
        if x[2] > 0:
            x = -x
        return np.column_stack([x, np.cross(f, x), f])

    def left_hold_root(self, up=0.055, back=0.09):
        R = self.left_frame()
        return self.L(self.GRIP) - R[:, 0] * up - R[:, 2] * back, R

    def left_wrist(self, pos, R):
        """Left-stage targets that put the left hand root at ``pos`` with orientation ``R`` (hand at identity)."""
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            a, b, c = Rot.from_matrix(R).as_euler("XYZ")
        cur = self.ctrl[self.LW][3:6]
        best = None
        for base in (np.array([a, b, c]), np.array([a + np.pi, np.pi - b, c + np.pi])):
            for k in np.ndindex(3, 3, 3):
                cand = base + (np.array(k) - 1) * 2 * np.pi
                if np.all(np.abs(cand) <= 3.2) and (best is None or np.linalg.norm(cand - cur)
                                                     < np.linalg.norm(best - cur)):
                    best = cand
        return np.r_[np.asarray(pos, float) - self.lorigin, best]

    def left_move(self, pos=None, R=None, lfingers=None, steps=30, settle=0):
        w0, f0 = self.ctrl[self.LW].copy(), self.ctrl[self.LF].copy()
        w1 = w0 if pos is None else self.left_wrist(pos, R)
        f1 = f0 if lfingers is None else np.asarray(lfingers, float)
        st = None
        for i in range(1, steps + 1):
            a = i / steps
            a = a * a * (3 - 2 * a)
            self.ctrl[self.LW] = w0 + (w1 - w0) * a
            self.ctrl[self.LF] = f0 + (f1 - f0) * a
            st = self.step()
            if self.s.done:
                return st
        for _ in range(settle):
            st = self.step()
        return st

    def left_hold(self, press=0.0):
        """The left hand takes a hook grip on the handle grip and keeps holding the vacuum down."""
        root, R = self.left_hold_root()
        wrap = self.LEFT_WRAP if self.s.hand == "sharpa" else np.full(len(self.LF), 1.2)
        opened = self.LEFT_OPEN if self.s.hand == "sharpa" else np.zeros(len(self.LF))
        # from the start pose (fingers up, beside the right hand): turn in place and rise first, then travel
        target = self.left_wrist(root - R[:, 0] * 0.08, R)
        start = self.ctrl[self.LW].copy()
        mid = np.r_[start[:3] + np.array([0.0, 0.08, 0.05]), target[3:]]
        self.left_move(mid[:3] + self.lorigin, Rot.from_euler("XYZ", mid[3:]).as_matrix(), opened, steps=40)
        self.left_move(root - R[:, 0] * 0.08, R, steps=40, settle=5)
        self.left_move(root, R, steps=40, settle=5)
        self.left_move(root + R[:, 0] * press, R, wrap, steps=40, settle=15)
        self.info("left hand holds the handle")
        # the grip settles the vacuum by a few mm: plan the right hand's moves in the held vacuum's frame
        self.Rv0 = self.d.xmat[self.vac].reshape(3, 3).copy()
        self.pv0 = self.d.xpos[self.vac].copy()
        return root, R

    def left_release(self, root, R):
        self.left_move(lfingers=np.zeros(len(self.LF)), steps=30, settle=10)  # unhook: fingers straight
        self.left_move(root - R[:, 0] * 0.03 - R[:, 2] * 0.04, R, steps=30)  # up and back along the fingers
        self.left_move(root - R[:, 0] * 0.10 - R[:, 2] * 0.06, R, steps=30, settle=5)
        self.info("left hand released")

    # ------------------------------------------------------------------ phases
    POKE = np.array([0.9, 0.0, 0.6, 0, 0.8, 0, 0, 0, 0, 1.5, 0, 1.6, 1.2, 1.5, 0, 1.6, 1.2, 0.1, 1.5, 0, 1.6, 1.2])
    POKE_WUJI = np.array([0.8, 0, 0.6, 0.6, 0, 0, 0, 0, 1.5, 0, 1.8, 1.2, 1.5, 0, 1.8, 1.2, 1.5, 0, 1.8, 1.2])

    def poke(self, x_local=0.020):
        """Index finger presses the release button until the tooth clears the catch; the bin tips onto the counter."""
        # index pointing forward-down along the vacuum's +x (clear of the left hand's thumb on the handle)
        R = self.frame(self.Ld([np.cos(1.2), 0, 0]) + np.array([0, 0, -np.sin(1.2)]), self.Ld([0, 1, 0]))
        poke = self.POKE if self.s.hand == "sharpa" else self.POKE_WUJI
        site = "right_index_fingertip" if self.s.hand == "sharpa" else "r_wuji_r_index_finger_tip"
        off = self.tip_offset(poke, site)
        root = self.L([x_local, 0, 0.073 + 0.012 + 0.04]) - R @ off
        self.move(self.wrist_from_root(root + np.array([0, 0, 0.1]), R), poke, steps=50, settle=5)
        self.move(self.wrist_from_root(root, R), steps=30, settle=5)
        z = 0.0
        for _ in range(110):
            if self.s.status()["button_travel_m"] < 0.0059 and z > -0.075:
                z -= 0.0008
            self.step(self.wrist_from_root(root + np.array([0, 0, z]), R))
        self.info("pressed")
        for k in range(30):
            self.step(self.wrist_from_root(root + np.array([0, 0, z + 0.05 * min(1, (k + 1) / 15)]), R))
        for _ in range(25):
            self.step()
        self.info("released")
        return R, root

    def bin_frame_world(self, p_local):
        pb, Rb = self.bin_pose()
        return pb + Rb @ np.asarray(p_local, float)

    def calm_branch(self, R_root):
        """The XYZ Euler stage angles of hand-root orientation ``R_root`` with the largest margin to the limits."""
        import warnings
        R_e = R_root @ self.R0().T
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            a, b, c = Rot.from_matrix(R_e).as_euler("XYZ")
        cands = []
        for base in (np.array([a, b, c]), np.array([a + np.pi, np.pi - b, c + np.pi])):
            for k in np.ndindex(3, 3, 3):
                cand = base + (np.array(k) - 1) * 2 * np.pi
                if np.all(np.abs(cand) <= 3.2):
                    cands.append(cand)
        return min(cands, key=lambda e: float(np.max(np.abs(e))))

    def root_target(self):
        """Commanded root pose (from the current wrist command)."""
        w = self.ctrl[:6]
        R_e = Rot.from_euler("XYZ", w[3:6]).as_matrix()
        return self.origin + w[:3], R_e @ self.R0()

    def goto(self, pos, R, steps=30, fingers=None, settle=0):
        """Move the commanded root pose to (pos, R): linear position, slerp orientation, smoothstep timing."""
        from scipy.spatial.transform import Slerp
        p0, R0 = self.root_target()
        slerp = Slerp([0, 1], Rot.from_matrix([R0, R]))
        f0 = self.ctrl[self.RF].copy()
        f1 = f0 if fingers is None else np.asarray(fingers, float)
        st = None
        for i in range(1, steps + 1):
            a = i / steps
            a = a * a * (3 - 2 * a)
            Ri = slerp([a]).as_matrix()[0]
            st = self.step(self.wrist_from_root(p0 + (pos - p0) * a, Ri), f0 + (f1 - f0) * a)
            if self.s.done:
                return st
        for _ in range(settle):
            st = self.step()
            if self.s.done:
                return st
        return st

    # ------------------------------------------------------------------ bin servo
    def vac_frame(self, current=False):
        # The reset vacuum frame (targets never follow a dragged vacuum body), a frozen snapshot, or the current one.
        if isinstance(current, tuple):
            return current[0].copy(), current[1].copy()
        if current:
            return self.d.xpos[self.vac].copy(), self.d.xmat[self.vac].reshape(3, 3).copy()
        return self.pv0.copy(), self.Rv0.copy()

    def bin_rel(self):
        """Bin pose in the (current) vacuum frame."""
        pv, Rv = self.vac_frame()
        pb, Rb = self.bin_pose()
        return Rv.T @ (pb - pv), Rv.T @ Rb

    def servo_bin(self, path, steps, ki=0.15, kr=0.5, kri=0.08, fingers=None, settle=0, point=(0.0, 0.0, 0.0),
                  current=False):
        """Drive the grasped bin along ``path(a) -> (p_rel, R_rel)`` (reset vacuum frame), a in [0, 1].

        ``p_rel`` is the desired position of the bin-local ``point``. Each control: T_HB from the measured hand
        and bin poses; hand command = desired bin pose composed with T_HB^-1, plus integral corrections of the
        point position and bin orientation errors (gravity sag, grasp compliance, contact loads).
        """
        point = np.asarray(point, float)
        integ = np.zeros(3)
        integ_r = np.zeros(3)
        st = None
        f0 = self.ctrl[self.RF].copy()
        f1 = f0 if fingers is None else np.asarray(fingers, float)
        for i in range(1, steps + settle + 1):
            a = min(1.0, i / steps)
            a = a * a * (3 - 2 * a)
            pv, Rv = self.vac_frame(current)
            p_rel, R_rel = path(a)
            Rb_des = Rv @ R_rel
            pb_des = pv + Rv @ p_rel - Rb_des @ point
            ph, Rh = self.hand_pose()
            pb, Rb = self.bin_pose()
            T_p = Rh.T @ (pb - ph)
            T_R = Rh.T @ Rb
            err = (pb_des + Rb_des @ point) - (pb + Rb @ point)
            integ += ki * err
            n = np.linalg.norm(integ)
            if n > self.integ_cap:
                integ *= self.integ_cap / n
            Rerr = Rot.from_matrix(Rb_des @ Rb.T).as_rotvec()
            integ_r += kri * Rerr
            n = np.linalg.norm(integ_r)
            if n > self.integ_r_cap:
                integ_r *= self.integ_r_cap / n
            Rb_cmd = Rot.from_rotvec(kr * Rerr + integ_r).as_matrix() @ Rb_des
            Rh_cmd = Rb_cmd @ T_R.T
            ph_cmd = pb_des + Rb_des @ point - Rb_cmd @ point + integ - Rh_cmd @ T_p
            st = self.step(self.wrist_from_root(ph_cmd, Rh_cmd), f0 + (f1 - f0) * a)
            if self.s.done:
                return st
        return st

    def bin_point_rel(self, point, current=False):
        pv, Rv = self.vac_frame(current)
        pb, Rb = self.bin_pose()
        return Rv.T @ (pb + Rb @ np.asarray(point, float) - pv), Rv.T @ Rb


# ---------------------------------------------------------------------- the authored episode
OPEN_UNDER = np.array([0.0, 0.0, 0.0, 0, 0.0, -0.1, 0, 0, 0, -0.1, 0, 0, 0, -0.1, 0, 0, 0, 0, -0.1, 0, 0, 0])
OPEN_UNDER_WUJI = np.array([0.0, 0, 0, 0, -0.1, 0, 0, 0, -0.1, 0, 0, 0, -0.1, 0, 0, 0, -0.1, 0, 0, 0])
TAB = (-0.009, 0.0, -0.047)  # midpoint of the bin's lower tabs (bin frame)


def wrap_grasp(mcp=1.55, thumb=0.8, hand="sharpa", pip=1.4, dip=1.0):
    f = [mcp, 0, pip, dip]
    if hand == "wuji":
        return np.array([thumb, 0, 0.5, 0.5, *f, *f, *f, *f])
    return np.array([thumb, 0.0, 0.5, 0, 0.5, *f, *f, *f, 0.1, *f])


def author(params=None, hand="sharpa", log=print):
    """Run the closed-loop authoring controller; returns (Author, marks)."""
    P = dict(bx=-0.185, px=0.045, pz=0.075, mcp=1.55, thumb=0.8, load=0.006, up=0.002, out=0.025,
             over=0.02, pre_tilt=0.14, hold_rows=150, close_icap=0.01, engage_x=-0.002, engage_z=0.0)
    P.update(params or {})
    A = Author(hand=hand, log=log)
    open_under = OPEN_UNDER if A.s.hand == "sharpa" else OPEN_UNDER_WUJI
    marks = {}
    lroot, lR = A.left_hold()
    marks["left_hold"] = A.s.steps
    A.poke()
    marks["released"] = A.s.steps
    # underhand power grasp around the nozzle (approach from in front of the nozzle tip, below its axis)
    pb, Rb = A.bin_pose()
    bar = pb + Rb @ np.array([P["bx"], 0, -0.018])
    R = A.frame(Rb @ np.array([0, -1, 0.0]), Rb @ np.array([-1, 0, 0.0]))
    root = bar - R @ np.array([P["px"], 0, P["pz"]])
    p0, R0 = A.root_target()
    A.goto(p0 + np.array([0, 0, 0.10]), R0, steps=25)
    pre = root - R @ np.array([0.08, 0, 0])
    pre1 = pre + Rb @ np.array([-0.13, 0, 0])
    # free-space transit in stage-joint space onto the Euler branch with the most margin to the +-3.2 rad stage
    # limits (a Cartesian slerp from the forward poke would otherwise wrap a wrist joint during the bin servo)
    A.euler = A.calm_branch(R)
    A.move(A.wrist_from_root(np.array([pre1[0], pre1[1], p0[2] + 0.10]), R), open_under, steps=60)
    A.goto(pre1, R, steps=40)
    A.goto(pre, R, steps=40, settle=5)
    A.goto(root, R, steps=30, settle=5)
    A.move(fingers=wrap_grasp(P["mcp"], P["thumb"], A.s.hand, P.get("pip", 1.4), P.get("dip", 1.0)), steps=30, settle=10)
    pr, Rr = A.root_target()
    A.goto(pr + np.array([0, 0, P["load"]]), Rr, steps=15, settle=5)
    A.info("grasped")
    marks["grasped"] = A.s.steps
    # remove: slide the tabs off the lower ledges, then lift the bin away
    FR = A.vac_frame(True)
    p_tip, R_tip = A.bin_point_rel(TAB, FR)
    p1 = p_tip + np.array([-P["out"], 0, P["up"]])
    A.servo_bin(lambda a: (p_tip + (p1 - p_tip) * a, R_tip), 40, point=TAB, settle=10, current=FR)
    away = p1 + np.array([-0.03, 0, 0.05])
    A.servo_bin(lambda a: (p1 + (away - p1) * a, R_tip), 36, point=TAB, settle=15, current=FR)
    A.info("removed")
    marks["removed"] = A.s.steps
    # reinstall: back onto the ledges (tabs first), then rotate the top closed past the seat until the latch snaps
    from scipy.spatial.transform import Slerp

    seat_p = np.array(A.s.config["checker"]["seat_pos"])
    seat_R = np.array(A.s.config["checker"]["seat_rot"]).reshape(3, 3)
    tab_seat = seat_p + seat_R @ np.array(TAB)
    if P.get("pre_tilt"):
        # aligned re-entry: hover the tabs in front of their ledges with a small tilt, slide them in, then close
        R_pre = Rot.from_rotvec([0, -P["pre_tilt"], 0]).as_matrix() @ seat_R
        hover = tab_seat + np.array([-P.get("hover_x", 0.025), 0, P.get("hover_z", 0.004)])
        engaged = tab_seat + np.array([-P.get("engage_x", 0.001), 0, P.get("engage_z", 0.0005)])
        A.servo_bin(lambda a: (away + (hover - away) * a, Slerp([0, 1], Rot.from_matrix([R_tip, R_pre]))([a]).as_matrix()[0]),
                    50, point=TAB, settle=10, current=FR)
        A.servo_bin(lambda a: (hover + (engaged - hover) * a, R_pre), 30, point=TAB, settle=10, current=FR)
        A.info("on ledges")
        start_p, start_R = engaged, R_pre
    else:
        A.servo_bin(lambda a: (away + (p1 - away) * a, R_tip), 40, point=TAB, settle=5, current=FR)
        A.servo_bin(lambda a: (p1 + (p_tip - p1) * a, R_tip), 40, point=TAB, settle=10, current=FR)
        A.info("on ledges")
        start_p, start_R = p_tip, R_tip
    # close: rotate about the tabs past the seat orientation, then back to the seat (bounded push)
    A.integ_cap, A.integ_r_cap = P.get("close_icap", 0.003), P.get("close_ricap", 0.05)
    tilt = Rot.from_matrix(start_R @ seat_R.T).as_rotvec()
    R_end = Rot.from_rotvec(Rot.from_matrix(seat_R @ start_R.T).as_rotvec() * (1 + P["over"] / max(1e-6, abs(tilt[1]))))
    sl = Slerp([0, 1], Rot.from_matrix([start_R, (R_end * Rot.from_matrix(start_R)).as_matrix()]))
    A.servo_bin(lambda a: (start_p + (tab_seat - start_p) * a, sl([a]).as_matrix()[0]), P.get("close_ramp", 50),
                point=TAB, settle=10, current=FR)
    A.servo_bin(lambda a: (tab_seat, seat_R), 20, point=TAB, settle=10, current=FR)
    if P.get("nudge_y"):
        # centre the latched bin across its seat (it has lateral play): push toward the vacuum's -y, then back
        nudge = np.array([0, -P["nudge_y"], 0])
        A.servo_bin(lambda a: (tab_seat + nudge * a, seat_R), 20, point=TAB, settle=10, current=FR)
        A.servo_bin(lambda a: (tab_seat + nudge * (1 - a), seat_R), 15, point=TAB, settle=5, current=FR)
    A.info("latched")
    marks["latched"] = A.s.steps
    # let go: open the hand, drop it below the nozzle, pull it out in front of the nozzle, hold still
    A.move(fingers=open_under, steps=25, settle=10)
    pr, Rr = A.root_target()
    A.goto(pr - R @ np.array([0.06, 0, 0]), Rr, steps=30)
    pr, Rr = A.root_target()
    A.goto(pr + Rb @ np.array([-0.15, 0, 0]), Rr, steps=40)
    A.info("hand clear")
    A.left_release(lroot, lR)
    marks["clear"] = A.s.steps
    hold = A.ctrl.copy()
    rows = [np.asarray(r, float) for r in A.s.actions]
    while not A.s.done and len(rows) < A.s.max_control_steps:
        A.s.step(hold)
        rows.append(hold.copy())
    marks["done"] = A.s.steps
    rows += [hold.copy()] * P["hold_rows"]
    A.rows = np.asarray(rows)
    A.info("end")
    return A, marks


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--hand", default="sharpa")
    parser.add_argument("--params", default="{}")
    args = parser.parse_args()
    A, marks = author(json.loads(args.params), hand=args.hand)
    st = A.s.status()
    print(json.dumps({"marks": marks, "reason": st["reason"], "rows": len(A.rows)}))
    A.s.save_trajectory(A.rows, args.out)
