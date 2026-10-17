"""Authoring-only (wave 3): run the wave-2 floating-stage controller (tools/controller.py) on the Marvin arm rig.

The old controller is unchanged; ``arm_port.StageProxy`` converts each old row (two six-axis wrist-stage targets +
fingers) into Marvin arm joint targets by IK of the old hand-root pose (old floating model, ``floating_scene.py`` +
``floating_task.json``) and records the executed arm-rig rows (plain motor targets, replayed open loop).

    python tools/arm_author.py --init                    # IK start pose of both arms -> task.json initial_targets
    python tools/arm_author.py --hand sharpa --out rows.npz [--slack 200]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE), str(HERE.parents[2] / "shared")]

import numpy as np  # noqa: E402

import arm_port  # noqa: E402
import floating_scene  # noqa: E402
from runtime import Session  # noqa: E402
from scene import arm_rig  # noqa: E402

OLD_CONFIG = json.loads((HERE / "floating_task.json").read_text())
REST = {"left": [0.5, -0.6, 0.0, -1.5, 0.3, 0.1, 0.5], "right": [-0.5, -0.6, 0.0, -1.5, -0.3, -0.1, -0.5]}
# Controller parameters of the arm oracle (wave 3): the palms grip the top 9 cm of the side rails (z0 = +0.10 m: the
# Marvin wrist link, 28 mm proud of the palm surface, must clear the frame's top edge), a more flexed thumb keeps the
# thumb base in front of the ring clips, and the hands withdraw upward after the release.
ARM_PARAMS = {"sharpa": {"z0": 0.10, "withdraw_dz": 0.04, "thumb_fe": 1.0},
              "wuji": {"z0": 0.10, "withdraw_dz": 0.04, "thumb_fe": 1.0}}


def rename(old):
    if old.startswith("l_hand_"):
        return "left_" + old[len("l_hand_"):]
    if old.startswith("r_hand_"):
        return "right_" + old[len("r_hand_"):]
    return old


def old_model(hand):
    model, _ = floating_scene.build(OLD_CONFIG, hand)
    return model


def sides():
    return {side: dict(stage_joints=[f"{side[0]}_wrist_{a}" for a in ("x", "y", "z", "rx", "ry", "rz")],
                       old_root=f"{side[0]}_hand_palm", new_root=f"{side[0]}_wrist_stage") for side in ("left", "right")}


def proxy(session, hand, **kw):
    om = old_model(hand)
    return arm_port.StageProxy(session, om, sides(), rename, np.zeros(om.nu), arm_rig.ARM_JOINTS, arm_rig.PARK,
                               rest=kw.pop("rest", None), **kw)


def init_pose(hand="sharpa", params=None):
    """Arm joint targets that put each hand root where the controller's first row puts it (start x0, z0)."""
    import controller as C
    p = {**C.Controller.DEFAULTS, **(params or {})}
    squeeze = p["open_in"] - 0.03
    wrist = {"left": [p["x0"], -squeeze, p["z0"], 0, 0, 0], "right": [p["x0"], squeeze, p["z0"], 0, 0, 0]}
    s = Session(hand=hand)
    om = old_model(hand)
    out = {}
    import mujoco
    for side, spec in sides().items():
        fk = arm_port.StageFK(om, spec["stage_joints"], spec["old_root"])
        pos, R = fk(np.asarray(wrist[side], dtype=float))
        ik = arm_port.ArmIK(s.model, arm_rig.ARM_JOINTS[side], spec["new_root"], rest=REST[side])
        best = None
        for seed in [REST[side]] + [list(np.random.default_rng(k).uniform(ik.lo, ik.hi)) for k in range(30)]:
            q, ep, er = ik.solve(pos, R, q0=np.asarray(seed), qpos=s.data.qpos, iters=400, null_gain=0.0)
            score = ep + 0.05 * er + 0.001 * float(np.linalg.norm(q - np.asarray(REST[side])))
            if best is None or score < best[0]:
                best = (score, q, ep, er)
        _, q, ep, er = best
        # polish with the null-space pull toward REST
        q, ep, er = ik.solve(pos, R, q0=q, qpos=s.data.qpos, iters=400)
        print(side, "start ik err mm/deg", round(ep * 1000, 3), round(np.degrees(er), 3), np.round(q, 4).tolist())
        for name, value in zip(arm_rig.ARM_JOINTS[side], q):
            out[name + "_target"] = float(value)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hand", default="sharpa")
    ap.add_argument("--out")
    ap.add_argument("--log")
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--params", default=None, help="controller parameters (default: ARM_PARAMS[hand])")
    ap.add_argument("--slack", type=int, default=200)
    args = ap.parse_args()
    if args.init:
        targets = init_pose(args.hand, json.loads(args.params) if args.params else ARM_PARAMS[args.hand])
        path = HERE.parent / "task.json"
        config = json.loads(path.read_text())
        for hand in ("sharpa", "wuji"):
            config["initial_targets"][hand] = targets
        path.write_text(json.dumps(config, indent=1) + "\n")
        return
    import controller as C
    s = Session(hand=args.hand)
    px = proxy(s, args.hand, rest=REST)
    c = C.Controller(px, json.loads(args.params) if args.params else ARM_PARAMS[args.hand])
    st = c.run()
    print(json.dumps({k: v for k, v in st.items() if k != "features"}, default=str))
    errs = np.array([[v[2] for v in e.values()] for e in px.log if e])
    if len(errs):
        print("tracking err mm: max", np.round(errs.max(0) * 1000, 2).tolist(), "mean", np.round(errs.mean(0) * 1000, 2).tolist())
    for entry in c.log[-3:]:
        print(entry)
    if args.log:
        Path(args.log).write_text("\n".join(json.dumps(e, default=str) for e in c.log) + "\n")
        Path(args.log).with_suffix(".track.json").write_text(json.dumps(px.log))
    if args.out:
        rows = np.array(px.rows)
        if st["success"]:
            rows = np.concatenate([rows, np.repeat(rows[-1:], args.slack, 0)])
        s.save_trajectory(rows, args.out)
        print("saved", rows.shape)


if __name__ == "__main__":
    main()
