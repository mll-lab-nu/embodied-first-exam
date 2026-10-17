#!/usr/bin/env python3
"""Authoring only: port the accepted wave-2 floating-stage boot-brushing episode onto the Marvin right arm.

  arm_port.py poses --hand sharpa --old <wave-2 family folder> --out poses_sharpa.npz
      (the wave-2 family = scripts/dexhand/families/boot_sole_brush at commit b686803d4 with its scripts/dexhand/shared;
      records the old hand-root world pose + finger targets after every control of its accepted witness)
  arm_port.py author --hand sharpa --poses poses_sharpa.npz --base X Y Z --yaw DEG --out DIR [--write-task]
      (solves the initial arm pose, drives the arm session with arm_ik.track toward the recorded hand-root poses,
      appends slack rows; writes DIR/<hand>.npz, DIR/author_<hand>.json, DIR/task.marvin.<hand>.json and, with
      --write-task, the base pose and initial targets into task.json)
  arm_port.py replay --hand sharpa --traj rows.npz [--task DIR/task.marvin.<hand>.json]   # fresh-process replay

The scene keeps the wave-2 world coordinates, so the recorded old world poses are used as they are. The arm is driven
closed loop (IK from the measured arm state + a joint integral for servo sag, as in arm_ik.track); only the commanded
rows are saved and they replay open loop.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parents[1]

FAMILY_CODE = r"""
import json, sys
import numpy as np
sys.path.insert(0, '.')
from runtime import Session
hand, out = sys.argv[1], sys.argv[2]
s = Session(hand=hand)
rows = np.load('solution/trajectory.npz' if hand == 'sharpa' else 'solution/wuji/trajectory.npz')['actions']
m, d = s.model, s.data
root = m.body('right_hand_C_MC').id
names = [m.actuator(i).name for i in range(m.nu)]
pos, mat, ctrl = [], [], []
def grab():
    pos.append(d.xpos[root].copy()); mat.append(d.xmat[root].reshape(3, 3).copy()); ctrl.append(d.ctrl.copy())
s.reset(); grab()
for r in rows:
    s.step(r); grab()
    if s.done:
        break
st = s.status()
print('old episode:', st['reason'], 'after', s.steps, 'controls')
np.savez(out, pos=np.array(pos), mat=np.array(mat), ctrl=np.array(ctrl), names=np.array(names),
         reason=st['reason'], steps=s.steps)
"""


def poses(a):
    """Run the old family code in its own folder (fresh process) and record the hand-root world poses."""
    out = a.out.resolve()
    subprocess.run([sys.executable, "-c", FAMILY_CODE, a.hand, str(out)], cwd=a.old, check=True)


def _session_modules():
    sys.path.insert(0, str(HERE))
    sys.path.append(str(HERE.parents[1] / "shared"))
    os.chdir(HERE)
    from runtime import Session  # noqa: E402
    import arm_ik  # noqa: E402
    import arm_rig  # noqa: E402
    return Session, arm_ik, arm_rig


def author(a):
    Session, arm_ik, arm_rig = _session_modules()
    import scene

    rec = np.load(a.poses)
    pos, mat, ctrl, names_old = rec["pos"], rec["mat"], rec["ctrl"], [str(n) for n in rec["names"]]
    print("recorded old episode:", str(rec["reason"]), "after", int(rec["steps"]), "controls,", len(pos), "poses")
    cfg = copy.deepcopy(json.loads((HERE / "task.json").read_text()))
    cfg["rig"] = "marvin"
    cfg["marvin"] = {"base_pos": [float(v) for v in a.base], "base_yaw": float(np.radians(a.yaw))}
    model = scene.build(cfg, a.hand)[0]
    lay = arm_rig.layout(model)
    names = lay["names"]
    ik = arm_ik.ArmIK(model, "right")
    q0, ep, er = ik.solve_best(pos[a.seed_from], mat[a.seed_from])
    # Branch choice: the multi-start solution at control ``seed_from`` (the highest brushing poses), continued back to
    # the reset pose with warm-started IK, so the whole episode stays on one IK branch.
    for i in range(a.seed_from - 1, -1, -1):
        q0, ep, er = ik.solve(pos[i], mat[i], q0=q0)
    if a.q0:
        # explicit warm start for the reset pose (e.g. the Sharpa episode's initial arm pose, to stay on its branch)
        q0, ep, er = ik.solve(pos[0], mat[0], q0=np.array(a.q0))
    print(f"initial right: IK {ep:.1e} m {er:.1e} rad, q {np.round(q0, 3)}")
    row0 = arm_rig.default_targets(model, arm_pose={"right": q0})
    old_idx = {n: i for i, n in enumerate(names_old)}
    finger_cols = [(i, old_idx[n]) for i, n in enumerate(names) if n in old_idx]
    for i, j in finger_cols:
        row0[i] = ctrl[0][j]
    cfg["initial_targets"] = dict(cfg["initial_targets"])
    cfg["initial_targets"][a.hand] = [round(float(x), 6) for x in row0]
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / f"task.marvin.{a.hand}.json").write_text(json.dumps(cfg, indent=1))
    s = Session(config=cfg, hand=a.hand)
    print("arm session: nu", s.model.nu, "robot", s.robot)
    right = lay["fingers"]["right"]
    fcols = [(i, old_idx[names[i]]) for i in range(right.start, right.stop)]
    n = len(pos)
    # Optional re-timing: each --seg A B F plays the old controls A..B F times slower (positions interpolated
    # linearly, rotations and finger targets from the nearest earlier old control).
    knots_new, knots_old = [0.0], [0.0]
    for A, B, F in sorted(a.seg or []):
        knots_new.append(knots_new[-1] + (A - knots_old[-1]))
        knots_old.append(A)
        knots_new.append(knots_new[-1] + (B - A) * F)
        knots_old.append(B)
    knots_new.append(knots_new[-1] + (n + a.hold) - knots_old[-1])
    knots_old.append(n + a.hold)

    def targets(session, k):
        t = float(np.interp(k + 1, knots_new, knots_old))
        if k + 1 >= knots_new[-1]:
            return None
        i0 = min(int(t), n - 1)
        i1 = min(i0 + 1, n - 1)
        w = min(t - int(t), 1.0) if i0 < n - 1 else 0.0
        fingers = np.array([ctrl[i0][j] for _, j in fcols])
        lift = np.array([0.0, 0.0, a.dz if t >= a.dz_from else 0.0])
        return {"pos": (1 - w) * pos[i0] + w * pos[i1] + lift, "R": mat[i0], "fingers": fingers}

    t0 = time.time()
    rows, log = arm_ik.track(s, targets, side="right", ki=a.ki)
    st = s.status()
    e = np.array([[x["pos_err"], x["rot_err"]] for x in log])
    a.out.mkdir(parents=True, exist_ok=True)
    np.save(a.out / f"log_{a.hand}.npy", np.array([[x["pos_err"], x["rot_err"], x["ik_pos_err"], x["ik_rot_err"]]
                                                   for x in log]))
    print(f"arm episode: {st.get('reason')} after {s.steps} controls ({st.get('failure_detail')}) | tracking pos err "
          f"mean {e[:, 0].mean():.4f} max {e[:, 0].max():.4f} m, rot mean {e[:, 1].mean():.4f} max {e[:, 1].max():.4f} "
          f"rad | {time.time() - t0:.1f} s")
    if st.get("success") and a.slack:
        rows = np.vstack([rows, np.repeat(rows[-1:], a.slack, axis=0)])
    s.save_trajectory(rows, a.out / f"{a.hand}.npz")
    worst = int(np.argmax(e[:, 0]))
    (a.out / f"author_{a.hand}.json").write_text(json.dumps({
        "reason": st.get("reason"), "failure_detail": st.get("failure_detail"), "steps": int(s.steps),
        "rows": int(len(rows)), "state_sha": s.state_sha(), "base": list(a.base), "yaw_deg": a.yaw,
        "initial_ik": [float(ep), float(er)],
        "tracking": {"pos_err_mean": float(e[:, 0].mean()), "pos_err_max": float(e[:, 0].max()),
                     "pos_err_max_at": worst, "rot_err_mean": float(e[:, 1].mean()),
                     "rot_err_max": float(e[:, 1].max())},
        "stage": st.get("stage"), "clods_brushed": st.get("clods_brushed"), "clods_in_tray": st.get("clods_in_tray")},
        indent=1))
    if a.write_task and st.get("success"):
        task = json.loads((HERE / "task.json").read_text())
        task["rig"] = cfg["rig"]
        task["marvin"] = cfg["marvin"]
        task["initial_targets"][a.hand] = cfg["initial_targets"][a.hand]
        (HERE / "task.json").write_text(json.dumps(task, indent=2) + "\n")
        print("task.json updated")


def replay(a):
    Session, _, _ = _session_modules()
    cfg = json.loads(Path(a.task).read_text()) if a.task else None
    s = Session(config=cfg, hand=a.hand)
    rows = np.load(a.traj)["actions"]
    if a.float32:
        rows = rows.astype(np.float32).astype(np.float64)
    st = s.replay(rows)
    print(json.dumps({"hand": a.hand, "reason": st.get("reason"), "steps": s.steps, "state_sha": s.state_sha(),
                      "rows": int(len(rows)), "detail": st.get("failure_detail")}))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=("poses", "author", "replay"))
    p.add_argument("--hand", default="sharpa")
    p.add_argument("--old", type=Path)
    p.add_argument("--poses", type=Path)
    p.add_argument("--base", type=float, nargs=3, default=(0.147, -0.591, 0.1))
    p.add_argument("--yaw", type=float, default=90.0, help="degrees")
    p.add_argument("--out", type=Path)
    p.add_argument("--hold", type=int, default=300)
    p.add_argument("--slack", type=int, default=150)
    p.add_argument("--seg", type=float, nargs=3, action="append")
    p.add_argument("--seed-from", type=int, default=221)
    p.add_argument("--q0", type=float, nargs=7)
    p.add_argument("--dz", type=float, default=0.0, help="lift every hand target by dz (m) from old control dz_from")
    p.add_argument("--dz-from", type=float, default=345.0)
    p.add_argument("--ki", type=float, default=0.25)
    p.add_argument("--traj", type=Path)
    p.add_argument("--task", type=Path)
    p.add_argument("--float32", action="store_true")
    p.add_argument("--write-task", action="store_true")
    a = p.parse_args()
    for k in ("old", "poses", "out", "traj", "task"):
        if getattr(a, k) is not None:
            setattr(a, k, getattr(a, k).resolve())
    {"poses": poses, "author": author, "replay": replay}[a.cmd](a)


if __name__ == "__main__":
    main()
