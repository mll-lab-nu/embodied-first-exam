#!/usr/bin/env python3
"""Authoring only: port the accepted wave-2 floating-stage jar episode onto the Marvin right arm.

  arm_port.py poses --hand sharpa --old <wave-2 family folder> --out poses_sharpa.npz
      (the wave-2 family = scripts/dexhand/families/jar_lid_open at commit b686803d4 with scripts/dexhand/shared;
      records the old hand-root world pose + finger targets after every control of its accepted witness)
  arm_port.py ready --hand sharpa --poses poses_sharpa.npz        # writes initial_targets[hand] into task.json
  arm_port.py author --hand sharpa --poses poses_sharpa.npz --out solution/trajectory.npz

The old episode ran with the worktop at z = 0.30 and the jar at the origin; the arm scene keeps every object and
the hand-to-jar relation but stands the worktop at a table height for the robot, so old poses are shifted by
``OLD_TO_NEW`` (jar origin difference). ``author`` drives the arm session with arm_ik.track toward the shifted old
hand-root poses (closed loop: IK from the measured arm state + joint integral for servo sag), then holds the final
pose; only the commanded rows are saved and they replay open loop.
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
import arm_ik  # noqa: E402
import arm_rig  # noqa: E402

OLD_JAR = np.array([0.0, 0.0, 0.30])   # wave-2 jar origin (worktop top at z = 0.30)


def poses(hand, old, out):
    """Replay the wave-2 floating-stage witness in its own (old) family code and record the hand-root poses."""
    import importlib
    old = Path(old).resolve()
    sys.path.insert(0, str(old))
    for name in ("runtime", "scene", "checker"):
        sys.modules.pop(name, None)
    old_runtime = importlib.import_module("runtime")
    s = old_runtime.Session(hand=hand)
    rows = np.load(old / ("solution/trajectory.npz" if hand == "sharpa" else "solution/wuji/trajectory.npz"))["actions"]
    m, d = s.model, s.data
    stage = m.body("wrist_stage").id
    child = [i for i in range(m.nbody) if m.body_parentid[i] == stage][0]
    P, R, F = [d.xpos[child].copy()], [d.xmat[child].reshape(3, 3).copy()], [s.initial_targets[6:].copy()]
    for r in rows:
        s.step(r)
        P.append(d.xpos[child].copy())
        R.append(d.xmat[child].reshape(3, 3).copy())
        F.append(np.asarray(r[6:]).copy())
        if s.done:
            break
    print("old episode", s.status()["reason"], s.steps)
    np.savez(out, pos=np.array(P), mat=np.array(R), fingers=np.array(F), steps=s.steps)


def shift(cfg):
    return np.array([*cfg["jar_xy"], cfg["table_z"]]) - OLD_JAR


def ready(hand, poses_path):
    cfg_path = HERE / "task.json"
    cfg = json.loads(cfg_path.read_text())
    z = np.load(poses_path)
    s = Session(hand=hand)
    ik = arm_ik.ArmIK(s.model, "right")
    pos = z["pos"][0] + shift(cfg)
    q, ep, er = ik.solve_best(pos, z["mat"][0])
    print("ready IK", round(ep * 1000, 3), "mm", round(er, 5), "rad", q.round(3))
    row = arm_rig.default_targets(s.model, arm_pose={"right": q}, fingers={"right": z["fingers"][0]})
    cfg["initial_targets"][hand] = [round(float(x), 6) for x in row]
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n")


def rot_z(a):
    c, s_ = np.cos(a), np.sin(a)
    return np.array([[c, -s_, 0.0], [s_, c, 0.0], [0.0, 0.0, 1.0]])


def retime(pos, mat, fingers, axis, twist=(150, 330), slow=2, extra=0.12, slow_end=None):
    """Slow the unscrewing part of the old episode down (the arm servos lag fast wrist turns) and turn the grip
    ``extra`` rad further about the jar axis from the twist on (the arm loses part of the stage's turn)."""
    P, R, F = [], [], []
    for i in range(len(pos)):
        a = extra * float(np.clip((i - twist[0]) / (twist[1] - twist[0]), 0.0, 1.0))
        Rz = rot_z(a)
        for _ in range(slow if twist[0] - 10 <= i <= (slow_end or twist[1] + 10) else 1):
            P.append(axis + Rz @ (pos[i] - axis))
            R.append(Rz @ mat[i])
            F.append(fingers[i])
    return np.array(P), np.array(R), np.array(F)


def author(hand, poses_path, out, hold_extra=300, ki=0.25, slow=2, extra=0.12, twist=(150, 330), slow_end=None):
    s = Session(hand=hand)
    z = np.load(poses_path)
    off = shift(s.config)
    axis = np.array([*s.config["jar_xy"], 0.0])
    pos, mat, fingers = retime(z["pos"] + off, z["mat"], z["fingers"], axis, twist, slow, extra, slow_end)
    n = len(pos)

    def targets(session, k):
        if k >= n - 1 + hold_extra:
            return None
        i = min(k + 1, n - 1)
        return {"pos": pos[i], "R": mat[i], "fingers": fingers[min(k, n - 1)] if k < n - 1 else fingers[-1]}

    rows, log = arm_ik.track(s, targets, side="right", ki=ki)
    st = s.status()
    errs = np.array([[e["pos_err"], e["rot_err"]] for e in log])
    success_step = s.steps
    rows = np.asarray(rows)
    if s.success:
        rows = np.concatenate([rows, np.repeat(rows[-1:], 150, axis=0)])   # >= 50 rows of slack after success
    s.save_trajectory(rows, out)
    summary = {"hand": hand, "reason": st["reason"], "success_step": success_step, "rows": int(len(rows)),
               "state_sha": s.state_sha(), "track_pos_err_mean_m": float(errs[:, 0].mean()),
               "track_pos_err_max_m": float(errs[:, 0].max()), "track_rot_err_mean_rad": float(errs[:, 1].mean()),
               "track_rot_err_max_rad": float(errs[:, 1].max())}
    print(json.dumps(summary))
    big = [(e["k"], round(e["pos_err"], 3), round(e["rot_err"], 3)) for e in log if e["pos_err"] > 0.015]
    if big:
        print("large tracking errors (k, m, rad):", big[:3], "...", big[-3:], "count", len(big))
    return summary


def main():
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=("poses", "ready", "author"))
    p.add_argument("--old", help="wave-2 family folder (poses)")
    p.add_argument("--hand", default="sharpa", choices=("sharpa", "wuji"))
    p.add_argument("--poses")
    p.add_argument("--out")
    p.add_argument("--hold-extra", type=int, default=300)
    p.add_argument("--ki", type=float, default=0.25)
    p.add_argument("--slow", type=int, default=2)
    p.add_argument("--extra", type=float, default=0.12)
    p.add_argument("--twist", type=int, nargs=2, default=[150, 330])
    p.add_argument("--slow-end", type=int, default=None, help="last old control of the slowed part")
    a = p.parse_args()
    if a.cmd == "poses":
        poses(a.hand, a.old, a.out)
    elif a.cmd == "ready":
        ready(a.hand, a.poses)
    else:
        author(a.hand, a.poses, a.out, a.hold_extra, a.ki, a.slow, a.extra, tuple(a.twist), a.slow_end)


if __name__ == "__main__":
    main()
