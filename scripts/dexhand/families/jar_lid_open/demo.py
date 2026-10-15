"""Authoring controller (Sharpa Wave): closed-loop scripted lid opening, recorded as open-loop actuator rows.

The controller reads Session state (lid turn, contacts) to decide when to stop twisting and when to release, but
only the commanded rows are saved; a fresh replay of the rows reproduces the episode bit for bit.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")
import mujoco
import numpy as np

from grasp import grasp_pose
from runtime import Session

ANGLES = {"thumb": math.radians(180), "index": math.radians(40), "middle": 0.0, "ring": math.radians(-40)}


class Recorder:
    def __init__(self, session):
        self.s = session
        self.rows = []
        self.phases = []
        self.target = session.hold_action()
        m = session.model
        self.dofs = m.jnt_dofadr[m.actuator_trnid[:, 0]]
        self.gains = m.actuator_gainprm[:, 0].copy()
        self.lo, self.hi = m.actuator_ctrlrange.T

    def command(self, target):
        s = self.s
        action = target + s.data.qfrc_bias[self.dofs] / self.gains
        return np.clip(action, self.lo, self.hi)

    def move(self, target, count, phase, until=None):
        start = self.target.copy()
        target = np.asarray(target, dtype=float)
        for i in range(1, count + 1):
            if self.s.done:
                return False
            r = i / count
            blend = r * r * (3 - 2 * r)
            self.target = start + (target - start) * blend
            row = self.command(self.target)
            self.s.step(row)
            self.rows.append(row)
            self.phases.append(phase)
            if until is not None and until():
                return True
        return False

    def hold(self, count, phase):
        return self.move(self.target.copy(), count, phase)


def wrist_for(lid_xy, offset_xy, yaw):
    c, s_ = math.cos(yaw), math.sin(yaw)
    ox, oy = offset_xy
    return np.array([lid_xy[0] + c * ox - s_ * oy, lid_xy[1] + s_ * ox + c * oy])


def run(args):
    s = Session(hand=args.hand)
    m, d = s.model, s.data
    rec = Recorder(s)
    lid0 = d.xpos[m.body("lid").id].copy()
    seed = np.asarray(s.config["initial_targets"][s.hand], dtype=float).copy()
    if s.hand == "sharpa":
        seed[6:11] = [1.2, 0.0, 0.3, 0.0, 0.3]
        seed[11:23] = [0.6, 0, 0.8, 0.6] * 3
    else:
        seed[6:10] = args.wuji_thumb
        seed[10:22] = list(args.wuji_finger) * 3
    angles = ANGLES if args.angles is None else dict(zip(("thumb", "index", "middle", "ring"),
                                                         np.radians(args.angles)))
    grasp, cost, err = grasp_pose(s, lid0, angles, height=args.height, radius_offset=-0.001, seed=seed)
    if args.joint_squeeze:
        # Weak servos: command the fingertips well inside the skirt (no collision terms) so the position error
        # becomes a grip force; the wrist stays at the grasp pose.
        squeeze, _, _ = grasp_pose(s, lid0, angles, height=args.height, radius_offset=-args.squeeze, seed=grasp,
                                   collide=False, fix_wrist=True)
    else:
        squeeze, _, _ = grasp_pose(s, lid0, angles, height=args.height, radius_offset=-args.squeeze, seed=grasp)
    pre, _, _ = grasp_pose(s, lid0, angles, height=args.height + 0.006, radius_offset=0.014, seed=grasp)
    print("grasp cost", cost, {k: round(v * 1000, 2) for k, v in err.items()}, flush=True)
    offset = grasp[:2] - lid0[:2]
    above = pre.copy()
    above[2] += 0.05
    rec.move(above, 60, "approach above the lid")
    rec.move(pre, 40, "descend around the lid")
    rec.move(grasp, 25, "close fingers on the lid skirt")
    rec.move(squeeze, 25, "squeeze")
    rec.hold(10, "settle grasp")
    print("after grasp", {k: v for k, v in s.features().items() if k in ("turn_rad", "lid_hand_contact", "failure")},
          flush=True)
    # Twist counter-clockwise about the lid axis until the checker's seated turn passes the target.
    twisted = squeeze.copy()
    turn_target = args.turn
    steps = args.twist_steps
    fingers = slice(6, 23) if s.hand == "sharpa" else slice(6, 22)
    if not args.ratchet:
        for i in range(1, steps + 1):
            yaw = (args.twist_max or turn_target * 1.15) * i / steps
            q = squeeze.copy()
            q[5] = yaw
            q[:2] = wrist_for(lid0[:2], offset, yaw)
            rec.move(q, 1, "twist the lid open")
            twisted = q
            if s.checker.turn >= turn_target or s.done:
                break
    else:
        # Ratchet: twist a stroke, open the fingers, turn the hand back, regrasp, repeat.
        for stroke in range(args.strokes):
            for i in range(1, steps + 1):
                yaw = args.ratchet * i / steps
                q = squeeze.copy()
                q[5] = yaw
                q[:2] = wrist_for(lid0[:2], offset, yaw)
                rec.move(q, 1, "twist the lid open")
                twisted = q
                if s.checker.turn >= turn_target or s.done:
                    break
            if s.checker.turn >= turn_target or s.done:
                break
            opened = rec.target.copy()
            opened[fingers] = pre[fingers]
            rec.move(opened, 20, "regrasp: open the fingers")
            back = opened.copy()
            back[5] = 0.0
            back[:2] = wrist_for(lid0[:2], offset, 0.0)
            rec.move(back, 30, "regrasp: turn the hand back")
            rec.move(grasp, 20, "regrasp: close the fingers")
            rec.move(squeeze, 20, "regrasp: squeeze")
            print("stroke", stroke, "turn", round(s.checker.turn, 3), flush=True)
        if args.regrasp_before_lift:
            # Re-seat the fingers at the current wrist turn before lifting (the last stroke ends slipping).
            yaw = float(rec.target[5])

            def turned(pose):
                out = pose.copy()
                out[5] = yaw
                out[:2] = wrist_for(lid0[:2], offset, yaw)
                return out

            opened = rec.target.copy()
            opened[fingers] = pre[fingers]
            rec.move(opened, 20, "regrasp: open the fingers")
            rec.move(turned(grasp), 20, "regrasp: close the fingers")
            hold_pose = squeeze
            if args.lift_squeeze is not None:
                hold_pose, _, _ = grasp_pose(s, lid0, angles, height=args.height, radius_offset=-args.lift_squeeze,
                                             seed=grasp, collide=False, fix_wrist=True)
            rec.move(turned(hold_pose), 20, "regrasp: squeeze")
            twisted = turned(hold_pose)
    rec.hold(10, "lid unscrewed")
    print("after twist", {k: v for k, v in s.features().items() if k in ("turn_rad", "stage", "failure", "jar_slide_m")},
          flush=True)
    lifted = twisted.copy()
    lifted[2] += args.lift
    rec.move(lifted, 60, "lift the lid clear")
    rec.hold(10, "lid lifted")
    print("after lift", {k: v for k, v in s.features().items() if k in ("turn_rad", "stage", "failure",
                                                                         "lid_clearance_above_rim_m")}, flush=True)
    place = lifted.copy()
    place[:2] += np.asarray(args.place) - lid0[:2]
    if args.tilt:
        # Tilt the hand about its lateral axis (finger side down) so the lid, not the thumb base, meets the worktop.
        from scipy.spatial.transform import Rotation

        yaw = place[5]
        rot = Rotation.from_euler("z", yaw) * Rotation.from_euler("y", args.tilt)
        place[3:6] = rot.as_euler("XYZ")
    rec.move(place, 90, "carry the lid aside")
    lid_body = m.body("lid").id
    down = place.copy()
    down[2] = twisted[2] - (lid0[2] - (s.config["table_z"] + 0.0018)) - args.drop_margin
    owner = s.checker.owner

    def touched_down():
        # Stop lowering once the lid or any part of the hand reaches the worktop.
        for c in d.contact[: d.ncon]:
            pair = {int(owner[c.geom1]), int(owner[c.geom2])}
            if 4 in pair and (2 in pair or 3 in pair):
                return True
        return False

    rec.move(down, 120, "lower the lid to the worktop", until=touched_down)
    # Hold the reached height (no pressing into the worktop).
    rec.target[2] = d.qpos[s.qadr[2]] + 0.001
    rec.hold(10, "lid on the worktop")
    print("after lower", {k: v for k, v in s.features().items() if k in ("stage", "failure", "lid_on_worktop",
                                                                          "lid_tilt_rad")},
          "lid z", d.xpos[lid_body][2], flush=True)
    release = rec.target.copy()
    release[fingers] = pre[fingers]
    rec.move(release, 40, "open the fingers")
    up = release.copy()
    up[2] += args.withdraw
    up[:2] -= 0.04 * np.array([math.cos(up[5]), math.sin(up[5])])
    rec.move(up, 75, "withdraw the hand")
    for _ in range(200):
        if s.done:
            break
        rec.hold(1, "hold released")
    print("final", json.dumps({k: v for k, v in s.status().items() if k not in ("positions",)}), flush=True)
    success_step = s.steps
    # Slack: keep holding after success (the episode ends at success; these rows are never executed in a replay
    # that succeeds, but they keep the oracle successful under tiny perturbations).
    rows = list(rec.rows) + [rec.rows[-1]] * args.slack
    phases = list(rec.phases) + ["hold released (slack)"] * args.slack
    return s, np.asarray(rows), phases, success_step


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    p.add_argument("--height", type=float, default=0.012)
    p.add_argument("--squeeze", type=float, default=0.002)
    p.add_argument("--turn", type=float, default=1.15)
    p.add_argument("--twist-steps", type=int, default=150)
    p.add_argument("--ratchet", type=float, default=0.0, help="wrist turn per regrasp stroke (rad); 0 = one stroke")
    p.add_argument("--strokes", type=int, default=6)
    p.add_argument("--regrasp-before-lift", action="store_true")
    p.add_argument("--joint-squeeze", action="store_true")
    p.add_argument("--lift-squeeze", type=float, default=None, help="grip depth used for lifting (m)")
    p.add_argument("--twist-max", type=float, default=None, help="largest wrist turn (rad); default 1.15 x --turn")
    p.add_argument("--lift", type=float, default=0.07)
    p.add_argument("--drop-margin", type=float, default=0.02)
    p.add_argument("--place", type=float, nargs=2, default=[0.12, -0.12])
    p.add_argument("--slack", type=int, default=150)
    p.add_argument("--withdraw", type=float, default=0.15)
    p.add_argument("--tilt", type=float, default=0.15)
    p.add_argument("--hand", default="sharpa", choices=["sharpa", "wuji"])
    p.add_argument("--wuji-thumb", type=float, nargs=4, default=[0.5, -0.8, 0.5, 0.5])
    p.add_argument("--wuji-finger", type=float, nargs=4, default=[0.9, 0.0, 1.1, 0.8])
    p.add_argument("--angles", type=float, nargs=4, help="thumb, index, middle, ring contact angles (deg)")
    a = p.parse_args()
    session, rows, phases, success_step = run(a)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    session.save_trajectory(rows, out)
    np.save(out.with_suffix(".phases.npy"), np.asarray(phases))
    print("rows", len(rows), "success_step", success_step, "saved", out)
