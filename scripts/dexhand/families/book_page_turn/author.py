"""Authoring controller (not shipped to tasks): closed-loop scripted Sharpa page turn recorded as open-loop rows.

The index fingertip catches the springback fore-edge of leaf 2 from just below its bottom corner, then the whole
hand rotates rigidly about the spine axis so the fingertip carries the board up and pushes it past vertical; the
board falls onto the left stack under its binding damping; the hand lifts away and holds still. The controller only
reads simulator state to place the wrist (an integral correction for the stage's gravity sag); every executed row is
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

from runtime import Session

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
        # Spine axis point (leaf-2 hinge) and the bottom fore-edge corner of leaf 2 after the settle.
        self.hinge = d.xpos[self.leaf].copy()
        Rl = d.xmat[self.leaf].reshape(3, 3)
        self.corner = self.hinge + Rl @ np.array([0.1524, 0.0, -0.0006])

    def tip_radius(self):
        if self.profile["capsule"]:
            return self.s.model.geom_size[self.tip_geom, 0]
        return self.profile["radius"]

    def tip_point(self, data):
        g = self.tip_geom
        if not self.profile["capsule"]:
            return data.geom_xpos[g].copy()
        R = data.geom_xmat[g].reshape(3, 3)
        half = self.s.model.geom_size[g, 1]
        ends = [data.geom_xpos[g] + R[:, 2] * half, data.geom_xpos[g] - R[:, 2] * half]
        mcp = data.xpos[self.s.model.body(self.profile["proximal"]).id]
        return max(ends, key=lambda e: np.linalg.norm(e - mcp))

    def tip_offset(self):
        """Distal fingertip-sphere centre in the hand-root frame for the chosen finger targets."""
        m = self.s.model
        d = mujoco.MjData(m)
        d.qpos[:] = self.s.data.qpos
        d.qpos[self.s.qadr[6:]] = self.fingers
        mujoco.mj_forward(m, d)
        hb = m.body("right_hand_C_MC").id
        R = d.xmat[hb].reshape(3, 3)
        return R.T @ (self.tip_point(d) - d.xpos[hb])

    def wrist_targets(self, tip, R_hand):
        root = tip - R_hand @ self.offset
        R_wrist = R_hand @ R_MOUNT.T
        e = Rot.from_matrix(R_wrist).as_euler("XYZ")
        candidates = [e, np.array([e[0] + np.pi, np.pi - e[1], e[2] + np.pi])]
        options = []
        for c in candidates:
            c = (c + np.pi) % (2 * np.pi) - np.pi
            if self.prev_euler is not None:
                c = self.prev_euler + ((c - self.prev_euler + np.pi) % (2 * np.pi) - np.pi)
            options.append(c)
        if self.prev_euler is None:
            best = min(options, key=lambda c: np.abs(c).max())
        else:
            best = min(options, key=lambda c: np.abs(c - self.prev_euler).sum())
        self.prev_euler = best
        return np.r_[root + self.corr, best]

    def command(self, tip, R_hand, phase, correct=True, fingers=None):
        s = self.s
        row = np.empty(s.action_dim)
        row[:6] = self.wrist_targets(tip, R_hand)
        row[6:] = self.fingers if fingers is None else fingers
        row = np.clip(row, s.lo, s.hi)
        s.step(row)
        self.rows.append(row)
        self.phases.append(phase)
        if correct:
            err = tip - self.tip_point(s.data)
            self.corr += self.p["integral_gain"] * err
            self.corr = np.clip(self.corr, -0.02, 0.02)
        # Keep planning after the episode ended (rows are then not executed) unless asked to stop early.
        return s.done and self.p.get("stop_at_done", False)

    def run(self):
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
        R_start = s.data.xmat[s.model.body("right_hand_C_MC").id].reshape(3, 3).copy()
        # 1. Move to the hover point (orientation slerp to the approach orientation).
        rots = Rot.from_matrix(np.stack([R_start, R0]))
        slerp = Slerp([0, 1], rots)
        k = n(p["t_hover"])
        for i in range(k):
            u = smooth((i + 1) / k)
            if self.command(start + (hover - start) * u, slerp([u]).as_matrix()[0], "reach"):
                return
        for segment, target, seconds in (("descend", pre, p["t_descend"]), ("approach", contact, p["t_approach"])):
            a = self.tip_point(s.data) * 0 + (hover if segment == "descend" else pre)
            k = n(seconds)
            for i in range(k):
                u = smooth((i + 1) / k)
                if self.command(a + (target - a) * u, R0, segment):
                    return
        # 2. Carry the board: rotate the hand rigidly about the spine axis.
        axis_point = np.array([0.0, 0.0, self.hinge[2]])
        # While rising, the fingertip also scoops toward the spine so it ends up under the board (robust to small
        # radial offsets of the catch).
        radial = np.array([1.0, 0.0, 0.0])
        Rl = s.data.xmat[self.leaf].reshape(3, 3)
        under = self.hinge + Rl @ np.array([0.1524 - p["under_inset"], 0.0, -(0.0006 + r + p["under_gap"])])
        under[1] = contact[1]
        k = n(p["t_turn"])
        for i in range(k):
            phi = p["phi_max"] * smooth((i + 1) / k)
            scoop = p["scoop"] * smooth(phi / p["scoop_angle"])
            # Optional slide under the raised board (between under_start and under_end radians of rotation).
            blend = p["under_blend"] * smooth((phi - p["under_start"]) / (p["under_end"] - p["under_start"]))
            tip = axis_point + turn(phi) @ (contact - axis_point - scoop * radial + blend * (under - contact))
            if self.command(tip, turn(phi) @ R0, "turn", correct=False):
                return
        # 3. Back away from the falling board (up and toward the fore-edge side), then park palm-up.
        tip_now = axis_point + turn(p["phi_max"]) @ (contact - axis_point - p["scoop"] * radial
                                                     + p["under_blend"] * (under - contact))
        R_end = turn(p["phi_max"]) @ R0
        away = tip_now + np.array(p["retreat"])
        k = n(p["t_retreat"])
        for i in range(k):
            u = smooth((i + 1) / k)
            if self.command(tip_now + (away - tip_now) * u, R_end, "retreat", correct=False):
                return
        park = np.array(p["park"])
        slerp = Slerp([0, 1], Rot.from_matrix(np.stack([R_end, R0])))
        k = n(p["t_park"])
        for i in range(k):
            u = smooth((i + 1) / k)
            if self.command(away + (park - away) * u, slerp([u]).as_matrix()[0], "park", correct=False):
                return
        k = n(p["t_hold"])
        for i in range(k):
            if self.command(park, R0, "release hold", correct=False):
                return


DEFAULT = {
    "pitch": 0.30,
    "yaw": 0.06,
    "below_corner": 0.0044,
    "penetration": 0.0015,
    "standoff": 0.012,
    "integral_gain": 0.25,
    "t_hover": 1.2,
    "t_descend": 0.8,
    "t_approach": 0.8,
    "t_turn": 3.0,
    "phi_max": 2.2,
    "scoop": 0.0,
    "scoop_angle": 0.5,
    "under_blend": 0.0,
    "under_start": 0.35,
    "under_end": 0.8,
    "under_inset": 0.015,
    "under_gap": 0.0005,
    "retreat": [0.05, 0.0, 0.05],
    "t_retreat": 0.6,
    "park": [0.26, 0.0, 0.42],
    "t_park": 1.6,
    "t_hold": 3.0,
    "extra_hold_rows": 100,
}


# Per-hand overrides of DEFAULT (found by a small physics sweep over catch height and pitch for the Wuji fingertip).
HAND_DEFAULTS = {"sharpa": {}, "wuji": {"pitch": 0.15, "below_corner": 0.004, "under_blend": 1.0}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hand", default="sharpa")
    parser.add_argument("--params", default="{}")
    parser.add_argument("--out")
    parser.add_argument("--park-targets", action="store_true", help="print the wrist targets of the park pose")
    args = parser.parse_args()
    params = {**DEFAULT, **HAND_DEFAULTS[args.hand], **json.loads(args.params)}
    s = Session(hand=args.hand)
    c = Controller(s, params)
    if args.park_targets:
        R0 = turn(params["pitch"]) @ rot_z(-params["yaw"]) @ R_BASE
        c.corr[:] = 0
        print(json.dumps([float(v) for v in c.wrist_targets(np.array(params["park"]), R0)]))
        return
    c.run()
    rows = np.asarray(c.rows)
    phases = list(c.phases)
    # Slack: hold the final (released, parked) targets for extra rows; the episode ends at success anyway.
    extra = int(params.get("extra_hold_rows", 0))
    if extra:
        rows = np.vstack([rows, np.repeat(rows[-1:], extra, axis=0)])
        phases += ["release hold"] * extra
    st = s.status()
    summary = {k: st[k] for k in ("success", "reason", "stage", "steps", "max_target_angle_deg", "target_angle_deg",
                                  "max_other_leaf_change_deg", "hand_book_contacts", "book_shift_m", "failure_detail")}
    summary["rows"] = len(rows)
    print(json.dumps(summary))
    if args.out:
        out = Path(args.out)
        s.save_trajectory(rows, out)
        np.savez_compressed(out.with_name(out.stem + ".phases.npz"), actions=rows, hand=np.array(s.hand),
                            task=np.array(s.task), phases=np.array(phases))
    s.close()

if __name__ == "__main__":
    main()
