"""Authoring controller (Sharpa Wave): pinch the leaning spoon, stir three revolutions, set it back, release.

Closed-loop on Session state (spoon pose relative to the wrist stage); the executed rows are saved as an
open-loop trajectory that the fresh-process replay reproduces exactly.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the family folder (runtime, scene, checker, replay)

os.environ.setdefault("MUJOCO_GL", "egl")
import mujoco
import numpy as np
from scipy.spatial.transform import Rotation, Slerp

from runtime import Session
from scene import COFFEE_Z

HERE = Path(__file__).resolve().parent

# Pinch found by kinematic IK (thumb pad above, index pad below the handle, 150 mm from the bowl centre).
GRASP = [0.36135, -0.06433, 0.96667, -1.98548, 0.58991, 1.1555, 1.65046, 0.08041, -0.5236, 0.3491, 0.0, 1.39493,
         -0.09912, 0.0, 0.0, 1.3, 0.0, 1.4, 1.0, 1.4, 0.0, 1.5, 1.1, 0.0, 1.4, 0.0, 1.5, 1.1]
THUMB_CLOSE = {"right_thumb_CMC_FE": 0.25, "right_thumb_IP": 0.25}
INDEX_CLOSE = {"right_index_MCP_FE": 0.18, "right_index_PIP": 0.15}
THUMB_OPEN = {"right_thumb_CMC_FE": -0.45}
INDEX_OPEN = {"right_index_MCP_FE": -0.55}
HAND_SPECS = {
    "sharpa": {"grasp": GRASP, "thumb_close": THUMB_CLOSE, "index_close": INDEX_CLOSE, "thumb_open": THUMB_OPEN,
               "index_open": INDEX_OPEN,
               "tips": ("right_thumb_fingertip_collision", "right_index_fingertip_collision")},
}


def pose_of(session, body):
    d = session.data
    b = session.model.body(body).id
    return d.xpos[b].copy(), d.xmat[b].reshape(3, 3).copy()


class Controller:
    def __init__(self, session, args):
        self.s = session
        self.args = args
        self.rows = []
        self.phases = []
        self.names = session.actuator_names
        m = session.model
        self.dofs = m.jnt_dofadr[m.actuator_trnid[:, 0]]
        self.gains = m.actuator_gainprm[:, 0]
        self.target = session.hold_action()
        self.stage_body = m.body("wrist_stage").id

    def with_fingers(self, base, *changes):
        q = np.array(base, dtype=float)
        for change in changes:
            for k, v in change.items():
                q[self.names.index(k)] += v
        return np.clip(q, *self.s.model.actuator_ctrlrange.T)

    def send(self, target, phase):
        s = self.s
        if s.done:
            return False
        self.target = np.clip(target, *s.model.actuator_ctrlrange.T)
        action = self.target.copy()
        # Gravity/bias feed-forward on the wrist stage only (same as the hamburger authoring controller).
        action[:6] += s.data.qfrc_bias[self.dofs[:6]] / self.gains[:6]
        action = np.clip(action, *s.model.actuator_ctrlrange.T)
        s.step(action)
        self.rows.append(action)
        self.phases.append(phase)
        return not s.done

    def move(self, target, count, phase):
        start = self.target.copy()
        for r in np.linspace(0, 1, count + 1)[1:]:
            b = r * r * (3 - 2 * r)
            if not self.send(start + (np.asarray(target) - start) * b, phase):
                return False
        return True

    def hold(self, count, phase):
        for _ in range(count):
            if not self.send(self.target, phase):
                return False
        return True

    # ---- pinch-point commands (the pinched spoon hangs like a pendulum below the thumb-index pinch) -------
    def pinch_point(self):
        m, d = self.s.model, self.s.data
        tips = [m.geom(n).id for n in getattr(self, "tips", HAND_SPECS["sharpa"]["tips"])]
        return d.geom_xpos[tips].mean(axis=0)

    def pinch_rel(self):
        d = self.s.data
        pw, Rw = d.xpos[self.stage_body].copy(), d.xmat[self.stage_body].reshape(3, 3).copy()
        return Rw.T @ (self.pinch_point() - pw)

    def wrist_for_pinch(self, point, rel, euler):
        Rw = Rotation.from_euler("XYZ", euler).as_matrix()
        return np.r_[point - Rw @ rel, euler]

    def pinch_path(self, points, phase, rel=None, euler=None):
        rel = self.pinch_rel() if rel is None else rel
        euler = self.target[3:6].copy() if euler is None else euler
        for point in points:
            q = self.target.copy()
            q[:6] = self.wrist_for_pinch(point, rel, euler)
            if not self.send(q, phase):
                return False
        return True

    # ---- object-centric wrist commands -----------------------------------------------------------
    def relative(self):
        ps, Rs = pose_of(self.s, "spoon")
        pw, Rw = self.s.data.xpos[self.stage_body].copy(), self.s.data.xmat[self.stage_body].reshape(3, 3).copy()
        return Rw.T @ (ps - pw), Rw.T @ Rs

    def wrist_for(self, p_spoon, R_spoon, rel):
        p_rel, R_rel = rel
        Rw = R_spoon @ R_rel.T
        pw = p_spoon - Rw @ p_rel
        euler = Rotation.from_matrix(Rw).as_euler("XYZ")
        cur = self.target[3:6]
        euler = cur + (euler - cur + np.pi) % (2 * np.pi) - np.pi
        return np.r_[pw, euler]

    def spoon_path(self, p0, R0, p1, R1, count, phase, fingers=None, closed_loop=True):
        slerp = Slerp([0, 1], Rotation.from_matrix([R0, R1]))
        base = self.target.copy() if fingers is None else np.asarray(fingers, dtype=float)
        rel0 = self.relative()
        for r in np.linspace(0, 1, count + 1)[1:]:
            b = r * r * (3 - 2 * r)
            p = p0 + (p1 - p0) * b
            Rm = slerp([b]).as_matrix()[0]
            rel = self.relative() if closed_loop else rel0
            q = base.copy()
            q[:6] = self.wrist_for(p, Rm, rel)
            if not self.send(q, phase):
                return False
        return True


def run(args):
    s = Session(hand="sharpa")
    c = Controller(s, args)
    names = s.actuator_names
    grasp = np.array(GRASP)
    grasp[:6] = np.asarray(GRASP[:6]) + np.asarray(args.grasp_offset)
    pre = c.with_fingers(grasp, THUMB_OPEN, INDEX_OPEN)
    e1 = np.array([1.0, 0, 0])
    approach = pre.copy()
    approach[:3] -= args.approach * e1
    high = approach.copy()
    high[2] += 0.06
    ok = c.move(high, 60, "reach above the spoon")
    ok = ok and c.move(approach, 40, "lower beside the handle")
    ok = ok and c.move(pre, 40, "slide fingers around the handle")
    closed = c.with_fingers(grasp, {k: v * args.squeeze for k, v in THUMB_CLOSE.items()},
                            {k: v * args.squeeze for k, v in INDEX_CLOSE.items()})
    ok = ok and c.move(closed, 30, "pinch the handle")
    ok = ok and c.hold(15, "pinch the handle")
    log = lambda tag: print(tag, json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in s.features().items()
                                             if k in ("stage", "revolutions", "bowl_cup_frame", "bowl_submerged",
                                                      "spoon_fingers", "hand_spoon_contacts", "failure",
                                                      "failure_detail", "cup_tilt_deg", "cup_slide_m", "steps")}), flush=True)
    log("grasped")
    cup = s.data.xpos[s.model.body("cup").id].copy()
    ps0, Rs0 = pose_of(s, "spoon")
    # Stir pose: bowl at radius r about the cup axis, spoon tilted by args.tilt toward -y.
    R_stir = Rotation.from_euler("x", args.tilt).as_matrix()
    z_bowl = cup[2] + args.bowl_z
    r = args.radius
    start_angle = np.pi / 2
    p_start = cup + np.array([r * np.cos(start_angle), r * np.sin(start_angle), 0])
    p_start[2] = z_bowl
    lift = ps0.copy()
    lift[2] = max(ps0[2], z_bowl) + 0.004
    ok = ok and c.spoon_path(ps0, Rs0, lift, Rs0, 20, "lift the bowl off the cup floor")
    ok = ok and c.spoon_path(lift, Rs0, p_start, R_stir, 60, "raise the spoon upright in the coffee")
    log("upright")
    turns = args.turns
    n = int(args.rows_per_turn * turns)
    rel = c.relative()
    for i in range(1, n + 1):
        if not ok:
            break
        a = start_angle + 2 * np.pi * turns * (i / n)
        p = cup + np.array([r * np.cos(a), r * np.sin(a), 0])
        p[2] = z_bowl
        q = c.target.copy()
        q[:6] = c.wrist_for(p, R_stir, c.relative() if args.closed_loop else rel)
        ok = c.send(q, "stir")
        if i % 50 == 0:
            log(f"stir {i}")
    log("stirred")
    # Set the spoon back to its starting lean (bowl on the floor, handle on the rim), then release.
    rest_p = np.asarray(s.config["spoon_pos"][:3])
    rest_R = Rotation.from_quat(np.r_[s.config["spoon_pos"][4:7], s.config["spoon_pos"][3]]).as_matrix()
    above_rest = rest_p.copy()
    above_rest[2] += 0.006
    pc, Rc = pose_of(s, "spoon")
    ok = ok and c.spoon_path(pc, Rc, above_rest, rest_R, 70, "lean the spoon on the rim")
    ok = ok and c.spoon_path(above_rest, rest_R, rest_p + np.array([0, 0, 0.001]), rest_R, 20, "lean the spoon on the rim")
    log("leaned")
    release = c.with_fingers(c.target, THUMB_OPEN, INDEX_OPEN)
    ok = ok and c.move(release, 30, "release the spoon")
    away = release.copy()
    away[:3] -= 0.05 * e1
    away[2] += 0.02
    ok = ok and c.move(away, 40, "withdraw the hand")
    up = away.copy()
    up[2] += 0.10
    ok = ok and c.move(up, 40, "withdraw the hand")
    log("withdrawn")
    while not s.done and len(c.rows) < s.max_control_steps:
        c.send(c.target, "hold")
    log("end")
    st = s.status()
    print("RESULT", st["reason"], st["steps"], json.dumps(st.get("failure_detail")))
    return s, c


def smooth(r):
    r = np.clip(r, 0, 1)
    return r * r * (3 - 2 * r)


def run_pendulum(args):
    hand = getattr(args, "hand", "sharpa")
    spec = HAND_SPECS[hand]
    THUMB_OPEN, INDEX_OPEN = spec["thumb_open"], spec["index_open"]
    THUMB_CLOSE, INDEX_CLOSE = spec["thumb_close"], spec["index_close"]
    s = Session(hand=hand)
    c = Controller(s, args)
    c.tips = spec["tips"]
    grasp = np.array(spec["grasp"])
    grasp[:6] = np.asarray(spec["grasp"][:6]) + np.asarray(args.grasp_offset)
    pre = c.with_fingers(grasp, THUMB_OPEN, INDEX_OPEN)
    e1 = np.array([1.0, 0, 0])
    approach = pre.copy()
    approach[:3] -= args.approach * e1
    high = approach.copy()
    high[2] += 0.06
    ok = c.move(high, 60, "reach above the spoon")
    ok = ok and c.move(approach, 40, "lower beside the handle")
    ok = ok and c.move(pre, 40, "slide fingers around the handle")
    closed = c.with_fingers(grasp, {k: v * args.squeeze for k, v in THUMB_CLOSE.items()},
                            {k: v * args.squeeze for k, v in INDEX_CLOSE.items()})
    ok = ok and c.move(closed, 30, "pinch the handle")
    ok = ok and c.hold(15, "pinch the handle")
    log = lambda tag: print(tag, json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in s.features().items()
                                             if k in ("stage", "revolutions", "bowl_cup_frame", "bowl_submerged",
                                                      "spoon_fingers", "hand_spoon_contacts", "failure",
                                                      "failure_detail", "cup_tilt_deg", "cup_slide_m", "steps")}), flush=True)
    log("grasped")
    m, d = s.model, s.data
    cup = d.xpos[m.body("cup").id].copy()
    rel = c.pinch_rel()
    euler = c.target[3:6].copy()
    p0 = c.pinch_point()
    L = float(np.linalg.norm(p0 - d.site_xpos[m.site("bowl_center").id]))
    hz = cup[2] + args.bowl_z + L
    center = np.array([cup[0], cup[1], hz])
    # Raise the pinch over the cup axis; the spoon swings upright about the pinch.
    n = args.upright_rows
    pts = [p0 + (center - p0) * smooth(i / n) for i in range(1, n + 1)]
    ok = ok and c.pinch_path(pts, "raise the spoon upright in the coffee", rel, euler)
    ok = ok and c.pinch_path([center] * args.settle_rows, "let the spoon settle", rel, euler)
    # Closed-loop depth correction: put the hanging bowl centre at the requested depth.
    bowl = d.site_xpos[m.site("bowl_center").id]
    target_z = cup[2] + args.bowl_z
    for _ in range(2):
        center = center + np.array([0, 0, target_z - bowl[2]])
        ok = ok and c.pinch_path([center] * 25, "let the spoon settle", rel, euler)
    log("upright")
    if args.variant == "knock":
        # Negative example: drag the spoon sideways through the cup wall (knocks the cup).
        side = center + np.array([0.12, 0.0, 0.0])
        ok = ok and c.pinch_path([center + (side - center) * smooth(i / 60) for i in range(1, 61)], "knock the cup", rel, euler)
        while not s.done and len(c.rows) < 900:
            c.send(c.target, "hold")
        log("knocked")
        return s, c
    turns, rpt, r = args.turns, args.rows_per_turn, args.radius
    total = int(rpt * turns)
    a0 = args.start_angle
    pts = []
    for i in range(1, total + 1):
        t = i / total
        a = a0 + 2 * np.pi * turns * t
        rad = r * smooth(i / (0.5 * rpt)) * (1 - smooth((i - total + 0.5 * rpt) / (0.5 * rpt)))
        pts.append(center + np.array([rad * np.cos(a), rad * np.sin(a), 0]))
    # Closed-loop stirring: the pinch drives the hanging spoon like a pendulum pivot; feedback on the bowl
    # position (proportional + velocity damping) keeps the bowl on the circle and at the requested depth.
    bowl_site = m.site("bowl_center").id
    prev_bowl = d.site_xpos[bowl_site].copy()
    z_cmd = center[2]
    for i, point in enumerate(pts):
        if not ok:
            break
        bowl = d.site_xpos[bowl_site].copy()
        vel = (bowl - prev_bowl) / s.control_dt
        prev_bowl = bowl
        desired = point[:2]
        cmd = desired + args.kp * (desired - bowl[:2]) - args.kd * vel[:2]
        z_cmd += args.kz * (target_z - bowl[2])
        ok = c.pinch_path([np.r_[cmd, z_cmd]], "stir three turns", rel, euler)
        if (i + 1) % 50 == 0:
            log(f"stir {i + 1}")
    center = np.r_[center[:2], z_cmd]
    ok = ok and c.pinch_path([center] * args.settle_rows, "stop stirring", rel, euler)
    log("stirred")
    if args.variant == "midair":
        # Negative example: open the pinch while the bowl hangs in the coffee (drop into the mug, then re-grasp).
        ok = ok and c.move(c.with_fingers(c.target, THUMB_OPEN, INDEX_OPEN), 8, "let go mid-air")
        ok = ok and c.move(c.with_fingers(c.target, {k: -v for k, v in THUMB_OPEN.items()},
                                          {k: -v for k, v in INDEX_OPEN.items()}), 8, "catch again")
        while not s.done and len(c.rows) < 1300:
            c.send(c.target, "hold")
        log("midair")
        return s, c
    if args.variant == "drop":
        # Negative example: lift the spoon out of the cup, carry it over the worktop and let go mid-air.
        up = center + np.array([0, 0, 0.16])
        ok = ok and c.pinch_path([center + (up - center) * smooth(i / 60) for i in range(1, 61)], "lift the spoon out", rel, euler)
        over = up + np.array([-0.16, -0.10, 0.0])
        ok = ok and c.pinch_path([up + (over - up) * smooth(i / 60) for i in range(1, 61)], "carry it over the worktop", rel, euler)
        ok = ok and c.move(c.with_fingers(c.target, THUMB_OPEN, INDEX_OPEN), 20, "let go mid-air")
        while not s.done and len(c.rows) < 1400:
            c.send(c.target, "hold")
        log("dropped")
        return s, c
    # Lower the bowl to the cup floor and lean the spoon toward the rim, then release.
    low = center + np.array([0, 0, -(args.bowl_z - args.rest_bowl_z)])
    n = 40
    ok = ok and c.pinch_path([center + (low - center) * smooth(i / n) for i in range(1, n + 1)], "lower the bowl", rel, euler)
    lean = low + np.asarray(args.lean)
    ok = ok and c.pinch_path([low + (lean - low) * smooth(i / 60) for i in range(1, 61)], "lean the spoon on the rim", rel, euler)
    log("leaned")
    release = c.with_fingers(c.target, THUMB_OPEN, INDEX_OPEN)
    ok = ok and c.move(release, 25, "release the spoon")
    away = release.copy()
    away[:3] += np.asarray(args.retreat)
    ok = ok and c.move(away, 50, "withdraw the hand")
    log("withdrawn")
    while not s.done and len(c.rows) < s.max_control_steps:
        c.send(c.target, "hold")
    log("end")
    st = s.status()
    print("RESULT", st["reason"], st["steps"], json.dumps(st.get("failure_detail")))
    return s, c


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path)
    p.add_argument("--grasp-offset", type=float, nargs=6, default=[0, 0, 0, 0, 0, 0])
    p.add_argument("--approach", type=float, default=0.04)
    p.add_argument("--squeeze", type=float, default=1.0)
    p.add_argument("--tilt", type=float, default=0.15)
    p.add_argument("--bowl-z", type=float, default=0.032)
    p.add_argument("--radius", type=float, default=0.018)
    p.add_argument("--turns", type=float, default=3.4)
    p.add_argument("--rows-per-turn", type=float, default=110)
    p.add_argument("--closed-loop", type=int, default=1)
    p.add_argument("--extra-hold", type=int, default=60)
    p.add_argument("--mode", default="pendulum")
    p.add_argument("--variant", default="", choices=["", "drop", "knock", "midair"])
    p.add_argument("--kp", type=float, default=0.5)
    p.add_argument("--kd", type=float, default=0.12)
    p.add_argument("--kz", type=float, default=0.2)
    p.add_argument("--upright-rows", type=int, default=80)
    p.add_argument("--settle-rows", type=int, default=50)
    p.add_argument("--start-angle", type=float, default=0.0)
    p.add_argument("--rest-bowl-z", type=float, default=0.026)
    p.add_argument("--lean", type=float, nargs=3, default=[0.0, -0.045, -0.02])
    p.add_argument("--retreat", type=float, nargs=3, default=[-0.06, -0.02, 0.10])
    args = p.parse_args()
    s, c = (run_pendulum if args.mode == "pendulum" else run)(args)
    if args.out:
        rows = np.asarray(c.rows)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        s.save_trajectory(rows, args.out)
        np.save(args.out.with_suffix(".phases.npy"), np.asarray(c.phases))
        print("saved", args.out, rows.shape)
