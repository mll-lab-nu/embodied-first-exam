#!/usr/bin/env python3
"""Authoring only (not shipped): port the floating-stage oracle onto the Marvin right arm (wave 3).

1. ``demo.py`` authors the closed-loop oracle on the old six-axis wrist stage (``tools/floating_task.json``).
2. This script replays those rows on the stage, records the world pose of the hand root (``right_hand_C_MC``) and the
   finger targets after every control, and drives the arm-rig task (``task.json``, ``rig: marvin``) toward them with
   ``arm_ik.track`` (IK from the measured arm state + a joint integral for servo sag), each recorded pose held for
   ``--slow`` controls. The executed rows (plus ``--slack`` copies of the last row) are the arm oracle.

  python tools/arm_port.py --float-rows out/float/trajectory.npz --out solution/trajectory.npz [--write-initial]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.append(str(HERE.parents[1] / "shared"))

from runtime import Session  # noqa: E402
import scene  # noqa: E402
import arm_rig  # noqa: E402
import arm_ik  # noqa: E402

SEEDS = [np.array(s, dtype=float) for s in (
    [-0.6, -0.9, 0.0, -1.4, 0.0, 0.0, 0.0], [-1.0, -1.2, 0.5, -1.0, 0.5, 0.0, 0.0],
    [0.0, -1.5, -0.5, -1.8, 0.0, 0.0, 0.0], [-1.5, -0.6, 0.8, -1.2, -0.8, 0.3, 0.3],
    [-0.3, -0.5, 0.3, -1.6, 0.3, 0.0, 0.0], [-1.2, -1.0, -0.4, -1.5, 0.9, 0.2, -0.2])]


def floating_poses(rows, hand):
    old = Session(config=json.loads((HERE / "tools/floating_task.json").read_text()), hand=hand)
    body = old.model.body("right_hand_C_MC").id
    poses = [(old.data.xpos[body].copy(), old.data.xmat[body].reshape(3, 3).copy(), old.initial_targets[6:].copy())]
    for r in rows:
        old.step(r)
        poses.append((old.data.xpos[body].copy(), old.data.xmat[body].reshape(3, 3).copy(), np.asarray(r[6:]).copy()))
        if old.done:
            break
    print("floating episode:", old.status()["reason"], "after", old.steps, "controls", flush=True)
    return poses


def initial_targets(config, pose, fingers_by_hand):
    """Arm joint targets for the floating start pose of the hand root (best of several IK seeds)."""
    out = {}
    q_best = None
    for hand, fingers in fingers_by_hand.items():
        model, _ = scene.build(config, hand=hand)
        if q_best is None:
            ik = arm_ik.ArmIK(model, "right")
            best = None
            for seed in SEEDS:
                q, ep, er = ik.solve(pose[0], pose[1], q0=seed, iters=400)
                cost = ep + 0.05 * er + 1e-3 * float(np.sum((q - SEEDS[0]) ** 2))
                if best is None or cost < best[0]:
                    best = (cost, q, ep, er)
            q_best = best[1]
            print("initial IK error %.2e m, %.2e rad" % (best[2], best[3]), flush=True)
        row = arm_rig.default_targets(model, arm_pose={"right": q_best}, fingers={"right": fingers})
        out[hand] = [round(float(x), 6) for x in row]
    return out


def float32_rows(model):
    lo, hi = model.actuator_ctrlrange.T

    def round32(row):
        r32 = np.asarray(row, dtype=np.float64).astype(np.float32)
        r32 = np.where(r32 > hi, np.nextafter(hi.astype(np.float32), np.float32(-np.inf)), r32)
        r32 = np.where(r32 < lo, np.nextafter(lo.astype(np.float32), np.float32(np.inf)), r32)
        return r32.astype(np.float64)

    return round32


def track_floating(rows, hand="sharpa", slow=2, hold=0, ki=0.25, session=None):
    """Arm rows (float32-exact, executed) that follow the hand-root poses of floating-stage ``rows``; returns
    (rows, status, tracking errors). The arm session stops at the first success or failure."""
    poses = floating_poses(rows, hand)
    s = session or Session(hand=hand)
    s.reset()
    round32 = float32_rows(s.model)
    step = s.step
    s.step = lambda row: step(round32(row))
    n = len(poses)

    def targets(session, k):
        j = k // slow
        if j >= n - 1 + hold:
            return None
        p, R, f = poses[min(j + 1, n - 1)]
        return {"pos": p, "R": R, "fingers": f}

    try:
        arm_rows, log = arm_ik.track(s, targets, side="right", ki=ki)
    finally:
        s.step = step
    err = np.array([[e["pos_err"], e["rot_err"]] for e in log])
    return np.array([round32(r) for r in arm_rows]), s.status(), err


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--float-rows", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--hand", default="sharpa")
    ap.add_argument("--slow", type=int, default=2)
    ap.add_argument("--hold", type=int, default=300)
    ap.add_argument("--slack", type=int, default=100)
    ap.add_argument("--ki", type=float, default=0.25)
    ap.add_argument("--write-initial", action="store_true", help="recompute task.json initial_targets (both hands)")
    a = ap.parse_args()
    rows = np.load(a.float_rows)["actions"]
    poses = floating_poses(rows, a.hand)
    task_path = HERE / "task.json"
    config = json.loads(task_path.read_text())
    if a.write_initial:
        floating = json.loads((HERE / "tools/floating_task.json").read_text())
        fingers = {h: np.asarray(floating["initial_targets"][h][6:]) for h in ("sharpa", "wuji")}
        config["initial_targets"] = initial_targets(config, poses[0], fingers)
        task_path.write_text(json.dumps(config, indent=2) + "\n")
    s = Session(hand=a.hand)
    n = len(poses)
    lo, hi = s.model.actuator_ctrlrange.T
    step = s.step

    def round32(row):
        r32 = np.asarray(row, dtype=np.float64).astype(np.float32)
        r32 = np.where(r32 > hi, np.nextafter(hi.astype(np.float32), np.float32(-np.inf)), r32)
        r32 = np.where(r32 < lo, np.nextafter(lo.astype(np.float32), np.float32(np.inf)), r32)
        return r32.astype(np.float64)

    s.step = lambda row: step(round32(row))  # execute exactly the float32 rows that are saved

    def targets(session, k):
        j = k // a.slow
        if j >= n - 1 + a.hold:
            return None
        p, R, f = poses[min(j + 1, n - 1)]
        return {"pos": p, "R": R, "fingers": f}

    arm_rows, log = arm_ik.track(s, targets, side="right", ki=a.ki)
    st = s.status()
    err = np.array([[e["pos_err"], e["rot_err"]] for e in log])
    print("arm episode:", st["reason"], "after", s.steps, "controls; tracking pos mean %.4f max %.4f m, rot mean %.4f "
          "max %.4f rad" % (err[:, 0].mean(), err[:, 0].max(), err[:, 1].mean(), err[:, 1].max()), flush=True)
    # Rows are float32-exact (what the public client sends) and stay inside the native bounds.
    out_rows = np.array([round32(r) for r in arm_rows])
    out_rows = np.vstack([out_rows, np.repeat(out_rows[-1:], a.slack, axis=0)])
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    s.save_trajectory(out_rows, a.out)
    print(json.dumps({"rows": int(len(out_rows)), "success_step": s.steps, "reason": st["reason"]}))


if __name__ == "__main__":
    main()
