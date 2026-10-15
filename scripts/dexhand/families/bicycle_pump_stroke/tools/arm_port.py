#!/usr/bin/env python3
"""Authoring only: the Marvin-arm pump witness, built from the accepted wave-2 floating-stage episode.

  arm_port.py poses --hand sharpa --old <wave-2 bicycle_pump_stroke folder> --out poses_sharpa.npz
      (the wave-2 family = scripts/dexhand/families/bicycle_pump_stroke at commit b686803d4 with scripts/dexhand/shared;
      records the old hand-root world pose + finger targets after every control of its accepted 6-stroke witness)
  arm_port.py ready --hand sharpa --poses poses_sharpa.npz        # writes initial_targets[hand] into task.json
  arm_port.py author --hand sharpa --poses poses_sharpa.npz --out solution/trajectory.npz

The T50 world frame already places the robot stand at the origin (bench top z = 0.70), so old world poses are used
as they are. ``author`` keeps the old approach and grip, repeats one full old stroke cycle until the task's required
count (28) is reached, then the old release and withdrawal, and drives the arm with arm_ik.track (closed loop: IK from
the measured arm state + joint integral for servo sag). Only the commanded rows are saved; they replay open loop.
"""

from __future__ import annotations

import argparse
import importlib
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

# Old witness segments (control indices of the recorded poses): approach + grip, first stroke, a steady stroke
# cycle (top to top), release + withdrawal.
APPROACH, FIRST, CYCLE, RELEASE = (0, 120), (120, 220), (220, 320), 720


def poses(hand, old, out):
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


def ready(hand, poses_path):
    cfg_path = HERE / "task.json"
    cfg = json.loads(cfg_path.read_text())
    z = np.load(poses_path)
    s = Session(hand=hand)
    ik = arm_ik.ArmIK(s.model, "right")
    q, ep, er = ik.solve_best(z["pos"][0], z["mat"][0])
    print("ready IK", round(ep * 1000, 3), "mm", round(er, 5), "rad", q.round(3))
    row = arm_rig.default_targets(s.model, arm_pose={"right": q}, fingers={"right": z["fingers"][0]})
    cfg["initial_targets"][hand] = [round(float(x), 6) for x in row]
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n")


def interp(a, b, n):
    """n poses from pose a (exclusive) to pose b (inclusive): smoothstep position, slerp rotation."""
    from scipy.spatial.transform import Rotation, Slerp

    (pa, Ra, fa), (pb, Rb, fb) = a, b
    slerp = Slerp([0, 1], Rotation.from_matrix(np.stack([Ra, Rb])))
    out = []
    for i in range(1, n + 1):
        t = i / n
        u = t * t * (3 - 2 * t)
        out.append((pa + (pb - pa) * u, slerp([u]).as_matrix()[0], fa + (fb - fa) * u))
    return out


def head_phase(s, start, args):
    """Hand-root waypoints: point the index finger down beside the open thumb lock, push the head onto the stem by
    pushing the upright lever toward the rim, hook over the lever and swing it down to the closed position."""
    import mujoco
    from scene import LEVER_CLOSED, LEVER_PIVOT_LOCKED, STEM_AXIS, HEAD_TRAVEL

    m = s.model
    nf = len(start[2])
    point = np.zeros(nf)            # index pointing, the other fingers curled into a fist, thumb tucked
    if s.hand == "sharpa":
        point[0:5] = [1.2, 0.0, 0.6, 0.0, 0.6]
        for f0 in (9, 13):
            point[f0:f0 + 4] = [1.5, 0.0, 1.5, 1.2]
        point[17:22] = [0.2, 1.5, 0.0, 1.5, 1.2]
        tip = m.geom("right_index_fingertip_collision").id
    else:
        point[0:4] = [0.8, 0.0, 0.8, 0.8]
        for f0 in (8, 12, 16):
            point[f0:f0 + 4] = [1.4, 0.0, 1.4, 1.2]
        tip = m.geom("r_wuji_r_index_finger_tip_sensor_frame_collision1").id
    # Index fingertip offset in the hand-root frame with this finger pose (kinematics only).
    d = mujoco.MjData(m)
    d.qpos[:] = s.data.qpos
    lay = arm_rig.layout(m)
    cols = np.arange(m.nu)[lay["fingers"]["right"]]
    d.qpos[s.qadr[cols]] = point
    mujoco.mj_kinematics(m, d)
    root = m.body("wrist_stage").id
    R0, p0 = d.xmat[root].reshape(3, 3), d.xpos[root]
    offset = R0.T @ (d.geom_xpos[tip] - p0)
    pad = 0.008
    # Hand orientation: fingers down (-z), palm facing the rim (-x), thumb +y.
    R = np.column_stack([(-1.0, 0, 0), (0, 1.0, 0), (0, 0, -1.0)])
    pivot = LEVER_PIVOT_LOCKED + STEM_AXIS * HEAD_TRAVEL      # the lever hinge at reset (head out)
    top = pivot + np.array([0, 0, args.lever_len])            # where the finger meets the upright lever

    def at(tip_pos, fingers=point):
        return (np.asarray(tip_pos, float) - R @ offset, R, fingers)

    wp = []
    behind = top + np.array([pad + 0.004, 0, 0])               # index pad just on the hub side of the lever
    wp += interp(start, at(behind + np.array([0.0, 0, 0.08]), start[2]), 70)
    wp += interp(wp[-1], at(behind + np.array([0.0, 0, 0.08])), 30)
    wp += interp(wp[-1], at(behind - np.array([0, 0, args.press_depth])), 40)
    push = behind - np.array([0, 0, args.press_depth]) - STEM_AXIS * (HEAD_TRAVEL + args.push_extra)
    wp += interp(wp[-1], at(push), args.push_steps)
    wp += [wp[-1]] * 10
    # Swing: lift over the lever top, come down on its rim side and sweep along the closing arc.
    pivot_seated = LEVER_PIVOT_LOCKED
    over = pivot_seated + np.array([-(pad + 0.006), 0, args.lever_len + 0.03])
    wp += interp(wp[-1], at(push + np.array([0, 0, 0.03])), 20)
    wp += interp(wp[-1], at(over), 25)
    radius = args.lever_len + 0.004
    arc = []
    for k in range(1, args.swing_steps + 1):
        a = -0.25 + (LEVER_CLOSED + args.swing_over + 0.25) * k / args.swing_steps   # finger angle from vertical
        rr = radius + pad
        arc.append(pivot_seated + np.array([rr * np.sin(a) - (pad + 0.004) * np.cos(a), 0,
                                             rr * np.cos(a) + (pad + 0.004) * np.sin(a)]))
    wp += interp(wp[-1], at(arc[0]), 25)
    for q in arc[1:]:
        wp.append(at(q))
    wp += [wp[-1]] * 10
    wp += interp(wp[-1], at(wp[-1][0] + R @ offset + np.array([0.02, 0, 0.10])), 40)
    return wp


def build_sequence(z, strokes, deep, segments):
    approach, first, cycle, release = segments
    pos, mat, fingers = z["pos"], z["mat"], z["fingers"]
    idx = list(range(*approach)) + list(range(*first)) + list(range(*cycle)) * (strokes - 1) + list(
        range(release, len(pos)))
    P, R, F = pos[idx].copy(), mat[idx].copy(), fingers[idx].copy()
    top = float(pos[cycle[0], 2])
    bottom = float(pos[cycle[0]:cycle[1], 2].min())
    stroke = np.zeros(len(idx), dtype=bool)
    stroke[approach[1] - approach[0]: len(idx) - (len(pos) - release)] = True
    frac = np.clip((top - P[:, 2]) / (top - bottom), 0.0, 1.0)
    P[stroke, 2] -= deep * frac[stroke]      # press a little past the old bottom: the arm lags the stage
    return P, R, F


def author(hand, poses_path, out, strokes=28, deep=0.01, hold_extra=300, ki=0.25, segments=None, head=None):
    s = Session(hand=hand)
    z = np.load(poses_path)
    segs = segments or (APPROACH, FIRST, CYCLE, RELEASE)
    pos, mat, fingers = build_sequence(z, strokes, deep, segs)
    if head is not None:
        # Connect the head first: from the start pose to the head and lever, then over to the pump's approach.
        first = (pos[0], mat[0], fingers[0])
        hp = head_phase(s, first, head)
        k0 = head.join_index
        up = (np.array([hp[-1][0][0], hp[-1][0][1], max(pos[k0][2], 1.30)]), hp[-1][1], hp[-1][2])
        hp += interp(hp[-1], up, 50)                                   # straight up, clear of the pump's handle
        hp += interp(hp[-1], (pos[k0], mat[k0], fingers[k0]), 70)
        pos = np.concatenate([np.array([w[0] for w in hp]), pos[k0 + 1:]])
        mat = np.concatenate([np.array([w[1] for w in hp]), mat[k0 + 1:]])
        fingers = np.concatenate([np.array([w[2] for w in hp]), fingers[k0 + 1:]])
    n = len(pos)

    def targets(session, k):
        if k >= n - 1 + hold_extra:
            return None
        i = min(k + 1, n - 1)
        return {"pos": pos[i], "R": mat[i], "fingers": fingers[min(k, n - 1)]}

    rows, log = arm_ik.track(s, targets, side="right", ki=ki)
    st = s.status()
    errs = np.array([[e["pos_err"], e["rot_err"]] for e in log])
    success_step = s.steps
    rows = np.asarray(rows)
    if s.success:
        rows = np.concatenate([rows, np.repeat(rows[-1:], 150, axis=0)])   # >= 50 rows of slack after success
    s.save_trajectory(rows, out)
    summary = {"hand": hand, "reason": st["reason"], "success_step": success_step, "rows": int(len(rows)),
               "strokes": st.get("strokes"), "connected": st.get("head_connected"),
               "connect_control": st.get("connect_control"), "state_sha": s.state_sha(),
               "track_pos_err_mean_m": float(errs[:, 0].mean()), "track_pos_err_max_m": float(errs[:, 0].max()),
               "track_rot_err_mean_rad": float(errs[:, 1].mean()), "track_rot_err_max_rad": float(errs[:, 1].max())}
    print(json.dumps(summary))
    return summary


def main():
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=("poses", "ready", "author"))
    p.add_argument("--hand", default="sharpa", choices=("sharpa", "wuji"))
    p.add_argument("--old")
    p.add_argument("--poses")
    p.add_argument("--out")
    p.add_argument("--strokes", type=int, default=28)
    p.add_argument("--deep", type=float, default=0.01)
    p.add_argument("--hold-extra", type=int, default=300)
    p.add_argument("--ki", type=float, default=0.25)
    p.add_argument("--segments", type=int, nargs=7, help="approach0 approach1 first0 first1 cycle0 cycle1 release")
    p.add_argument("--no-head", action="store_true", help="old start state: head already locked (no connect phase)")
    p.add_argument("--lever-len", type=float, default=0.020, help="contact height on the upright lever above its hinge")
    p.add_argument("--press-depth", type=float, default=0.004)
    p.add_argument("--push-extra", type=float, default=0.004)
    p.add_argument("--push-steps", type=int, default=50)
    p.add_argument("--swing-steps", type=int, default=60)
    p.add_argument("--swing-over", type=float, default=0.0, help="sweep past the closed angle (rad)")
    p.add_argument("--join-index", type=int, default=60, help="old pose index where the pump approach resumes")
    a = p.parse_args()
    if a.cmd == "poses":
        poses(a.hand, a.old, a.out)
    elif a.cmd == "ready":
        ready(a.hand, a.poses)
    else:
        segs = None
        if a.segments:
            v = a.segments
            segs = ((v[0], v[1]), (v[2], v[3]), (v[4], v[5]), v[6])
        author(a.hand, a.poses, a.out, a.strokes, a.deep, a.hold_extra, a.ki, segs, None if a.no_head else a)


if __name__ == "__main__":
    main()
