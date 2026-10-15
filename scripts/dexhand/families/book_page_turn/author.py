"""Authoring controller (not shipped to tasks): closed-loop scripted page turn on the Marvin right arm, recorded as
open-loop rows.

All boards lie flat. The index fingertip presses lightly on leaf 2's fore-edge face just above the board below it,
then the whole hand turns about the measured binding hinge: fingertip friction on the edge face lifts only the top
board, carries it past vertical, and the board falls onto the left stack under its binding damping; the hand backs
away and parks. Hand poses are planned in the canonical book frame (spine along +y through the origin, right-hand
stack toward +x, i.e. the wave-2 layout) and mapped to the world through the book's start pose; the right arm follows
them through damped-least-squares IK (arm_ik.track, closed loop on the measured arm state). Every executed row is
recorded and later replayed open loop.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation as Rot, Slerp

import sys
sys.path.append(str(Path(__file__).resolve().parents[2] / "shared"))
from runtime import Session
import arm_ik
import arm_rig

R_MOUNT = Rot.from_quat([0, 0.7071067811865476, 0, 0.7071067811865476], scalar_first=True).as_matrix()
# Hand frame columns in world for a palm-up hand whose fingers point at the spine (-x): palm normal +z, radial +y.
R_BASE = np.array([[0.0, 0.0, -1.0], [0.0, 1.0, 0.0], [1.0, 0.0, 0.0]])
# Sharpa finger targets: thumb tucked, index straight, middle/ring/pinky curled into the palm.
SHARPA_FINGERS = [1.0, 0.0, 0.7, 0.0, 0.8, 0.0, 0.0, 0.0, 0.0, 1.3, 0.0, 1.5, 0.9, 1.3, 0.0, 1.5, 0.9, 0.1, 1.3, 0.0, 1.5, 0.9]
# Wuji finger targets (THJ0-3, FFJ0-3, MFJ0-3, RFJ0-3, LFJ0-3): index straight, middle/ring/pinky curled.
WUJI_FINGERS = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.3, 0.2, 1.4, 0.0, 1.6, 1.2, 1.4, 0.0, 1.6, 1.2, 1.4, 0.0, 1.6, 1.2]
PROFILES = {
    "sharpa": {"tip_geom": "right_index_fingertip_collision", "capsule": True, "proximal": "right_index_PP",
               "fingers": SHARPA_FINGERS},
    "wuji": {"tip_geom": "r_wuji_r_index_finger_tip_sensor_frame_collision1", "capsule": False,
             "proximal": "r_wuji_r_index_finger_proximal", "fingers": WUJI_FINGERS, "radius": 0.008},
}


def rot_z(angle):
    c, s = np.cos(angle), np.sin(angle)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def rot_y(angle):
    c, s = np.cos(angle), np.sin(angle)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def turn(phi):
    """Rotation about the spine direction (0, -1, 0) by ``phi`` (the leaf-opening direction)."""
    return rot_y(-phi)


def smooth(u):
    u = np.clip(u, 0.0, 1.0)
    return u * u * u * (10 - 15 * u + 6 * u * u)


class Controller:
    def __init__(self, session, params):
        self.s = session
        self.p = dict(params)
        m = session.model
        self.profile = PROFILES[session.hand]
        self.tip_geom = m.geom(self.profile["tip_geom"]).id
        self.leaf = m.body("leaf_2").id
        self.fingers = np.asarray(self.p.get("fingers", self.profile["fingers"]), dtype=float)
        self.prev_euler = None
        self.corr = np.zeros(3)
        self.rows = []
        self.phases = []
        self.offset = self.tip_offset()
        d = session.data
        # Canonical book frame C (the wave-2 layout: spine along +y through the origin at the old desk height, right
        # stack toward +x) -> world: p_W = B (p_C - o_C) + o_W, from the book's frozen start pose.
        cfg = session.config
        yaw = np.radians(cfg.get("book_yaw_deg", 0.0))
        self.B = rot_z(yaw)
        self.o_C = np.array([0.0, 0.0, 0.30 + cfg["book"]["spine_origin_height_m"]])
        self.o_W = np.array([cfg["book_xy"][0], cfg["book_xy"][1], cfg["table_z"] + cfg["book"]["spine_origin_height_m"]])
        # Spine axis point (leaf-2 hinge) and the bottom fore-edge corner of leaf 2 after the settle (frame C).
        self.hinge = self.to_C(d.xpos[self.leaf])
        Rl = self.R_to_C(d.xmat[self.leaf].reshape(3, 3))
        self.corner = self.hinge + Rl @ np.array([0.1524, 0.0, -0.0006])
        self.pending = None
        self.phi = 0.0
        self.left_phase = "in"
        self.left_out_k = 0
        if self.p.get("left_stop"):
            self.left_setup()

    def to_C(self, p):
        return self.B.T @ (np.asarray(p) - self.o_W) + self.o_C

    def to_W(self, p):
        return self.B @ (np.asarray(p) - self.o_C) + self.o_W

    def R_to_C(self, R):
        return self.B.T @ R

    def R_to_W(self, R):
        return self.B @ R

    def leaf_pose_C(self):
        d = self.s.data
        return self.to_C(d.xpos[self.leaf]), self.R_to_C(d.xmat[self.leaf].reshape(3, 3))

    def tip_radius(self):
        if self.profile["capsule"]:
            return self.s.model.geom_size[self.tip_geom, 0]
        return self.profile["radius"]

    def tip_world(self, data):
        g = self.tip_geom
        if not self.profile["capsule"]:
            return data.geom_xpos[g].copy()
        R = data.geom_xmat[g].reshape(3, 3)
        half = self.s.model.geom_size[g, 1]
        ends = [data.geom_xpos[g] + R[:, 2] * half, data.geom_xpos[g] - R[:, 2] * half]
        mcp = data.xpos[self.s.model.body(self.profile["proximal"]).id]
        return max(ends, key=lambda e: np.linalg.norm(e - mcp))

    def tip_point(self, data):
        """Distal fingertip-sphere centre in the book frame C."""
        return self.to_C(self.tip_world(data))

    def tip_offset(self):
        """Distal fingertip-sphere centre in the hand-root frame for the chosen finger targets."""
        m = self.s.model
        d = mujoco.MjData(m)
        d.qpos[:] = self.s.data.qpos
        d.qpos[self.s.qadr[arm_rig.layout(m)["fingers"]["right"]]] = self.fingers
        mujoco.mj_forward(m, d)
        hb = m.body("right_hand_C_MC").id
        R = d.xmat[hb].reshape(3, 3)
        return R.T @ (self.tip_world(d) - d.xpos[hb])

    def hand_target(self, tip, R_hand, fingers=None):
        """World pose of the hand root (right_hand_C_MC == the flange mount) for a fingertip target in frame C."""
        R_W = self.R_to_W(R_hand)
        tip_W = self.to_W(tip + self.corr)
        return {"pos": tip_W - R_W @ self.offset, "R": R_W,
                "fingers": self.fingers if fingers is None else np.asarray(fingers, float)}

    def left_setup(self):
        """Left index fingertip offset (left hand frame) and the stop pose at the left stack's fore-edge."""
        m = self.s.model
        d = mujoco.MjData(m)
        d.qpos[:] = self.s.data.qpos
        lay = arm_rig.layout(m)
        d.qpos[self.s.qadr[lay["fingers"]["left"]]] = self.fingers
        mujoco.mj_forward(m, d)
        if self.profile["capsule"]:  # Sharpa Wave: distal end of the index fingertip capsule
            g = m.geom("left_index_fingertip_collision").id
            R = d.geom_xmat[g].reshape(3, 3)
            half = m.geom_size[g, 1]
            mcp = d.xpos[m.body("left_index_PP").id]
            ends = [d.geom_xpos[g] + R[:, 2] * half, d.geom_xpos[g] - R[:, 2] * half]
            tip = max(ends, key=lambda e: np.linalg.norm(e - mcp))
            r = m.geom_size[g, 0]
        else:  # Wuji Hand 2.2: the fingertip collision geom centre
            g = m.geom("l_wuji_l_index_finger_tip_sensor_frame_collision1").id
            tip = d.geom_xpos[g].copy()
            r = self.profile["radius"]
        hb = m.body("left_hand_C_MC").id
        self.left_offset = d.xmat[hb].reshape(3, 3).T @ (tip - d.xpos[hb])
        p = self.p
        # Stop in frame C: just outside the left stack's fore-edge (x = -0.1524), fingertip pointing down.
        # Fingertip sphere centre stop_h above the desk, touching the top fore-edge corner of the left stack
        # (leaf 1 top face, 3.4 mm above the spine origin).
        z_c = self.o_C[2] - 0.0006 + p["stop_h"]
        dz = z_c - (self.o_C[2] + 0.0034)
        stop_C = np.array([-0.1524 - p["stop_gap"] - np.sqrt(max(r * r - dz * dz, 0.0)), 0.0, z_c])
        self.left_stop = self.to_W(stop_C)
        # Left hand frame (columns: palm normal, thumb side, fingers): fingers down, palm toward the book.
        palm = self.B @ np.array([1.0, 0.0, 0.0])
        fingers = np.array([0.0, 0.0, -1.0])
        self.left_R = np.column_stack([palm, np.cross(fingers, palm), fingers])
        self.left_start = d.xpos[hb].copy(), d.xmat[hb].reshape(3, 3).copy()
        # Joint-space reach from the parked pose to above the stop (IK seeded for an elbow-out solution).
        ik = arm_ik.ArmIK(m, "left")
        above = self.left_stop + np.array([0.0, 0.0, 0.05])
        best = None
        for seed in ([0.0, -0.97, 0.14, -1.39, -0.16, 0.78, -1.38], [0.6, 0.9, 0.0, -1.4, 0.0, 0.0, 0.0],
                     [0.0, -1.2, 0.0, -1.2, 0.0, 0.5, -1.2]):
            q, ep, er = ik.solve(above - self.left_R @ self.left_offset, self.left_R, q0=np.array(seed), iters=400)
            if best is None or ep + 0.05 * er < best[0]:
                best = (ep + 0.05 * er, q)
        self.left_q_park = np.array(arm_rig.PARK["left"], dtype=float)
        self.left_q_above = best[1]
        # Waypoint well above the desk (the hanging arm must not sweep under the desk edge).
        mid = self.B @ np.array([-0.30, 0.0, 0.0]) + np.array([self.o_W[0] - 0.20, 0.0, self.o_W[2] + 0.30])
        q_mid, _, _ = ik.solve(mid - self.left_R @ self.left_offset, self.left_R, q0=best[1], iters=400)
        self.left_q_mid = q_mid
        # First waypoint beside the stand, above desk height and outside the desk's footprint, so the arm rising from
        # its parked pose never sweeps under the desk or through its front legs.
        side = np.array([0.02, 0.48, self.o_W[2] + 0.25])
        q_side, _, _ = ik.solve(side - self.left_R @ self.left_offset, self.left_R, q0=q_mid, iters=400)
        self.left_q_side = q_side
        # Cartesian reach path of the left fingertip (IK warm-started step by step from the parked arm): out sideways
        # beside the stand (y = 0.42, outside the desk's footprint), up beside it, over the desk, above the stop. The
        # forearm then never sweeps under the desk edge.
        pos0, R0 = self.left_start
        tip0 = pos0 + R0 @ self.left_offset
        out_low = np.array([tip0[0] - 0.03, 0.42, tip0[2] + 0.15])
        way = [tip0, out_low, side, mid, above]
        seg = np.array([0.25, 0.20, 0.30, 0.25])
        n = int(self.p["left_reach"])
        rot_path = Slerp([0, 1], Rot.from_matrix(np.stack([R0, self.left_R])))
        q = self.left_q_park.copy()
        self.left_reach_q = []
        for i in range(n):
            u = smooth((i + 1) / n)
            c = np.cumsum(seg) / seg.sum()
            j = int(np.searchsorted(c, u, side="left")); j = min(j, len(seg) - 1)
            u0 = 0.0 if j == 0 else c[j - 1]
            t = (u - u0) / (c[j] - u0)
            tip = way[j] + (way[j + 1] - way[j]) * t
            R = rot_path([min(1.0, u / c[1])]).as_matrix()[0]
            q, _, _ = ik.solve(tip - R @ self.left_offset, R, q0=q, iters=100)
            self.left_reach_q.append(q.copy())

    def left_target(self, k):
        """Left-arm stop schedule (global control index k)."""
        p = self.p
        pos0, R0 = self.left_start
        above = self.left_stop + np.array([0.0, 0.0, 0.05])
        n_reach, n_down = p["left_reach"], p["left_down"]
        if self.left_phase == "out":
            # Let go: first straight away from the stack's fore-edge (so fingertip friction cannot drag leaf 1 up),
            # then up and outward, clear of the right hand's retreat.
            u = min(1.0, (k - self.left_out_k) / p["left_out"])
            away = self.B @ np.array([-p["left_clear"], 0.0, 0.0])
            rest = self.B @ np.array(p["left_out_dir"]) - away
            tip = self.left_stop + smooth(u / 0.35) * away + smooth((u - 0.35) / 0.65) * rest
            phase = "stop release"
        elif k < n_reach:
            return {"q": self.left_reach_q[k], "fingers": self.fingers, "free": True}
        elif k < n_reach + n_down:
            u = smooth((k - n_reach + 1) / n_down)
            tip = above + (self.left_stop - above) * u
            phase = "stop approach"
        else:
            tip = self.left_stop
            phase = "stop hold"
        return {"pos": tip - self.left_R @ self.left_offset, "R": self.left_R, "fingers": self.fingers,
                "free": phase != "stop hold"}

    def targets(self, session, k):
        """arm_ik.track callback: integral fingertip correction for the last command, then the next target."""
        if self.pending is not None:
            tip, correct = self.pending
            if correct:
                err = tip - self.tip_point(session.data)
                if self.p.get("tangential_only"):
                    # never integrate along the board toward the hinge (that is the contact preload direction)
                    u = self.leaf_pose_C()[1][:, 0]
                    err = err - (err @ u) * u
                self.corr = np.clip(self.corr + self.p["integral_gain"] * err, -0.02, 0.02)
        try:
            tip, R_hand, phase, correct, fingers = next(self.gen)
        except StopIteration:
            return None
        self.pending = (tip, correct)
        self.phases.append(phase)
        out = self.hand_target(tip, R_hand, fingers)
        if self.p.get("left_stop"):
            if self.left_phase != "out" and phase == "turn" and self.phi >= self.p["left_release_phi"]:
                self.left_phase, self.left_out_k = "out", k
            out["left"] = self.left_target(k)
        return out

    def command(self, tip, R_hand, phase, correct=True, fingers=None):
        return (tip, R_hand, phase, correct, fingers)

    def plan(self):
        p, s = self.p, self.s
        gamma = p["pitch"]
        R0 = turn(gamma) @ rot_z(-p["yaw"]) @ R_BASE
        r = self.tip_radius()
        dz = p["below_corner"]
        contact = np.array([self.corner[0] + np.sqrt(r * r - dz * dz) - p["penetration"], 0.0, self.corner[2] - dz])
        pre = contact + np.array([p["standoff"], 0.0, 0.0])
        hover = pre + np.array([0.02, 0.0, 0.04])
        start = self.tip_point(s.data)
        n = lambda seconds: max(1, int(round(seconds / s.control_dt)))
        R_start = self.R_to_C(s.data.xmat[s.model.body("right_hand_C_MC").id].reshape(3, 3))
        # 1. Move to the hover point (orientation slerp to the approach orientation).
        rots = Rot.from_matrix(np.stack([R_start, R0]))
        slerp = Slerp([0, 1], rots)
        k = n(p["t_hover"])
        for i in range(k):
            u = smooth((i + 1) / k)
            yield self.command(start + (hover - start) * u, slerp([u]).as_matrix()[0], "reach")
        # Free-space approach to 1 mm outside the edge (the arm's sag integral converges there), then a short press
        # to the preloaded contact with the integral frozen.
        near = contact + np.array([p["penetration"] + 0.001, 0.0, 0.0])
        for segment, a, target, seconds in (("descend", hover, pre, p["t_descend"]),
                                            ("approach", pre, near, p["t_approach"])):
            k = n(seconds)
            for i in range(k):
                u = smooth((i + 1) / k)
                yield self.command(a + (target - a) * u, R0, segment)
        for i in range(n(p["t_settle"])):
            yield self.command(near, R0, "approach")
        k = n(p["t_press"])
        for i in range(k):
            u = smooth((i + 1) / k)
            yield self.command(near + (contact - near) * u, R0, "press")
        # 2. Turn the board: the fingertip keeps its light preload on leaf 2's fore-edge face (just above leaf 3) while
        # the hand turns about the measured binding hinge; fingertip friction on the edge face lifts only the top
        # board and carries it past vertical.
        radial = np.array([1.0, 0.0, 0.0])
        k = n(p["t_turn"])
        tip = contact
        for i in range(k):
            phi = p["phi_max"] * smooth((i + 1) / k)
            self.phi = phi
            scoop = p["scoop"] * smooth(phi / p["scoop_angle"])
            hinge_now = self.leaf_pose_C()[0]
            tip = hinge_now + turn(phi) @ (contact - self.hinge - scoop * radial)
            # The hand turns only by hand_turn * phi (the arm's wrist range); only the fingertip sphere touches.
            hand_phi = p["hand_turn"] * phi + max(0.0, phi - p["late_start"]) * (p["hand_turn_late"] - p["hand_turn"])
            yield self.command(tip, turn(hand_phi) @ R0, "turn", correct=True)
        # 3. Back away from the falling board (up and toward the fore-edge side), then park palm-up.
        tip_now = tip
        R_end = turn(p["hand_turn"] * p["phi_max"]
                     + max(0.0, p["phi_max"] - p["late_start"]) * (p["hand_turn_late"] - p["hand_turn"])) @ R0
        away = tip_now + np.array(p["retreat"])
        k = n(p["t_retreat"])
        for i in range(k):
            u = smooth((i + 1) / k)
            yield self.command(tip_now + (away - tip_now) * u, R_end, "retreat", correct=False)
        park = np.array(p["park"])
        slerp = Slerp([0, 1], Rot.from_matrix(np.stack([R_end, R0])))
        k = n(p["t_park"])
        for i in range(k):
            u = smooth((i + 1) / k)
            yield self.command(away + (park - away) * u, slerp([u]).as_matrix()[0], "park", correct=False)
        k = n(p["t_hold"])
        for i in range(k):
            yield self.command(park, R0, "release hold", correct=False)


DEFAULT = {
    "pitch": 0.30,
    "yaw": 0.06,
    # Fingertip sphere centre 1.5 mm above leaf 2's top face (2.7 mm above its bottom fore-edge corner): it mainly loads
    # leaf 2's fore-edge (it brushes leaves 3-5 by <= 1.4 mm; they move < 0.003 deg).
    "below_corner": -0.0027,
    "penetration": 0.0045,
    "standoff": 0.012,
    "integral_gain": 0.0,
    "t_hover": 1.6,
    "t_descend": 0.8,
    "t_approach": 0.8,
    "t_settle": 0.6,
    "t_press": 0.3,
    "t_turn": 4.0,
    "phi_max": 2.2,
    "hand_turn": 0.45,
    "hand_turn_late": 0.45,  # optional steeper hand turn after late_start (rad of board turn)
    "late_start": 1.0,
    "scoop": 0.0,
    "scoop_angle": 0.5,
    "retreat": [0.05, 0.0, 0.05],
    "t_retreat": 0.6,
    "park": [0.26, 0.0, 0.42],
    "t_park": 1.6,
    "t_hold": 3.0,
    "extra_hold_rows": 100,
    "ff": 1.0,
    "left_stop": True,
    "stop_gap": 0.0003,
    "stop_h": 0.0085,
    "left_reach": 110,
    "left_down": 40,
    "left_out": 60,
    "left_clear": 0.03,
    "left_out_dir": [-0.12, 0.0, 0.15],
    "left_release_phi": 1.75,
    "ki_phases": ["reach", "descend", "approach", "retreat", "park", "release hold"],
}


# Per-hand overrides of DEFAULT.
HAND_DEFAULTS = {"sharpa": {}, "wuji": {"pitch": 0.4, "penetration": 0.0065, "hand_turn": 0.6, "hand_turn_late": 0.9, "late_start": 0.9, "phi_max": 2.0,
                                       "extra_hold_rows": 200}}
# Right-arm IK seeds (elbow out and down) for the start pose.
SEEDS = [np.array(v, dtype=float) for v in (
    [-0.6, -0.9, 0.0, -1.4, 0.0, 0.0, 0.0], [-1.0, -1.2, 0.5, -1.0, 0.5, 0.0, 0.0],
    [0.0, -1.5, -0.5, -1.8, 0.0, 0.0, 0.0], [-1.5, -0.6, 0.8, -1.2, -0.8, 0.3, 0.3],
    [-0.3, -0.5, 0.3, -1.6, 0.3, 0.0, 0.0], [-1.2, -1.0, -0.4, -1.5, 0.9, 0.2, -0.2],
    [0.3, -0.3, 1.2, -1.5, -1.5, 0.0, 0.0], [-0.5, -0.4, 1.5, -1.8, -2.0, 0.3, 0.5])]


def initial_row(session, params, start_root_C, R_C):
    """IK row for the start pose (written into task.json initial_targets)."""
    ctrl = Controller(session, params)
    pos_W, R_W = ctrl.to_W(start_root_C), ctrl.R_to_W(R_C)
    ik = arm_ik.ArmIK(session.model, "right")
    best = None
    for seed in SEEDS:
        q, ep, er = ik.solve(pos_W, R_W, q0=seed, qpos=session.data.qpos, iters=400)
        cost = ep + 0.05 * er
        if best is None or cost < best[0]:
            best = (cost, q, ep, er)
    print("initial IK error %.2e m %.2e rad" % (best[2], best[3]), "q", np.round(best[1], 3).tolist())
    row = arm_rig.default_targets(session.model, arm_pose={"right": best[1]}, fingers={"right": ctrl.fingers})
    return row


def track(session, ctrl, ki=0.25, bias_limit=0.25, free_phases=("reach", "descend")):
    """arm_ik.track with a phase-gated joint integral: the integral (servo sag compensation) only adapts while the
    hand is in free space; it is frozen while the fingertip touches the book so a preloaded contact target never
    winds it up into a large push."""
    m, d = session.model, session.data
    lay = arm_rig.layout(m)
    ik = arm_ik.ArmIK(m, "right")
    sl = lay["arm"]["right"]
    sll = lay["arm"]["left"]
    ikl = arm_ik.ArmIK(m, "left")
    bias_l = np.zeros(7)
    row = np.array(d.ctrl, dtype=float)
    ql_prev = row[sll].copy()
    lo, hi = m.actuator_ctrlrange.T
    bias = np.zeros(7)
    q_prev = row[sl].copy()
    q_star_prev = None
    ff_gain = float(ctrl.p.get("ff", 0.0)) * 48.0 / 700.0
    rows, log = [], []
    k = 0
    while not session.done:
        target = ctrl.targets(session, k)
        if target is None:
            break
        if "left" in target:
            lt = target["left"]
            qlm = d.qpos[ikl.qadr].copy()
            if "q" in lt:
                ql_star = np.asarray(lt["q"], float)
            else:
                ql_star, _, _ = ikl.solve(lt["pos"], lt["R"], q0=ql_prev, qpos=d.qpos)
            if lt["free"]:
                bias_l = np.clip(bias_l + ki * (ql_star - qlm), -bias_limit, bias_limit)
            ql_prev = ql_star
            row[sll] = np.clip(ql_star + bias_l, lo[sll], hi[sll])
            row[lay["fingers"]["left"]] = lt["fingers"]
        q_meas = d.qpos[ik.qadr].copy()
        q_star, ep, er = ik.solve(target["pos"], target["R"], q0=(q_prev - bias) if q_star_prev is None else q_star_prev,
                                  qpos=d.qpos)
        if ctrl.phases[-1] in free_phases:
            bias = np.clip(bias + ki * (q_star - q_meas), -bias_limit, bias_limit)
        # Velocity feed-forward: a position servo (kp, kv) lags a moving target by (kv / kp) * qdot.
        ff = 0.0 if q_star_prev is None else ff_gain * (q_star - q_star_prev) / session.control_dt
        q_star_prev = q_star
        q_cmd = np.clip(q_star + bias + ff, lo[sl], hi[sl])
        row[sl] = q_cmd
        row[lay["fingers"]["right"]] = target["fingers"]
        row = np.clip(row, lo, hi)
        session.step(row.copy())
        rows.append(row.copy())
        p_now, R_now = ik.fk(d.qpos[ik.qadr], qpos=d.qpos)
        log.append({"k": k, "ik_pos_err": ep, "ik_rot_err": er, "pos_err": float(np.linalg.norm(target["pos"] - p_now)),
                    "rot_err": float(np.linalg.norm(arm_ik.rot_error(target["R"], R_now)))})
        q_prev = q_cmd
        k += 1
    return np.array(rows), log


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hand", default="sharpa")
    parser.add_argument("--params", default="{}")
    parser.add_argument("--out")
    parser.add_argument("--ki", type=float, default=0.25)
    parser.add_argument("--init-row", action="store_true",
                        help="print the IK start row for task.json initial_targets (start pose given by --start)")
    parser.add_argument("--start", default="[0.443, -0.042, 0.476, 0.0, -0.3, 3.08]",
                        help="start pose as the wave-2 wrist-stage targets (frame C)")
    args = parser.parse_args()
    params = {**DEFAULT, **HAND_DEFAULTS[args.hand], **json.loads(args.params)}
    s = Session(hand=args.hand)
    if args.init_row:
        w6 = np.array(json.loads(args.start), float)
        R_stage = Rot.from_euler("XYZ", w6[3:]).as_matrix()
        R_C = R_stage @ R_MOUNT
        row = initial_row(s, params, w6[:3], R_C)
        print(json.dumps([round(float(v), 6) for v in row]))
        return
    c = Controller(s, params)
    c.gen = c.plan()
    rows, log = track(s, c, ki=args.ki, free_phases=set(params["ki_phases"]))
    rows = np.asarray(rows)
    phases = list(c.phases)[: len(rows)]
    errs = np.array([e["pos_err"] for e in log]) if log else np.zeros(1)
    # Slack: hold the final (released, parked) targets for extra rows; the episode ends at success anyway.
    extra = int(params.get("extra_hold_rows", 0))
    if extra and len(rows):
        rows = np.vstack([rows, np.repeat(rows[-1:], extra, axis=0)])
        phases += ["release hold"] * extra
    st = s.status()
    summary = {k: st.get(k) for k in ("success", "reason", "stage", "steps", "max_target_angle_deg",
                                      "target_angle_deg", "max_other_leaf_change_deg", "hand_book_contacts",
                                      "book_shift_m", "failure_detail")}
    summary["rows"] = len(rows)
    summary["track_err_mean_max_mm"] = [round(float(errs.mean()) * 1000, 1), round(float(errs.max()) * 1000, 1)]
    print(json.dumps(summary))
    by = {}
    for e, ph in zip(log, phases):
        b = by.setdefault(ph, [0, 0.0, 0.0, 0.0, 0.0])
        b[0] += 1
        b[1] = max(b[1], e["ik_pos_err"]); b[2] = max(b[2], e["ik_rot_err"]); b[3] = max(b[3], e["pos_err"]); b[4] = max(b[4], e["rot_err"])
    for ph, b in by.items():
        print(f"  {ph:14s} n={b[0]:4d} ik_pos {b[1]*1000:6.1f} mm ik_rot {b[2]:.3f} rad | track pos {b[3]*1000:6.1f} mm rot {b[4]:.3f}")
    if args.out:
        out = Path(args.out)
        s.save_trajectory(rows, out)
        np.savez_compressed(out.with_name(out.stem + ".phases.npz"), actions=rows, hand=np.array(s.hand),
                            task=np.array(s.task), phases=np.array(phases))
    s.close()


if __name__ == "__main__":
    main()
