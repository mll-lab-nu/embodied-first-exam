"""Authoring-only (wave 3): run the wave-2 floating-stage controller (tools/author.py) on the Marvin arm rig.

``arm_port.StageProxy`` converts each old row (two six-axis wrist-stage targets + fingers) into Marvin arm joint
targets by IK of the old hand-root pose (old floating model: ``floating_scene.py`` + ``floating_task.json``) and records
the executed arm-rig rows (plain motor targets, replayed open loop). The left counterhold is the wave-2 grasp rotated
by ``L_ROT`` about the cup's vertical axis (``author.py`` ``l_rot``), so that the left arm reaches it from the robot's
side; the cup is rotationally symmetric, so it is the same grasp.

    python tools/arm_author.py --init                    # IK start pose of both arms -> task.json initial_targets
    python tools/arm_author.py --hand sharpa --out rows.npz [--extra-hold 100]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE), str(HERE.parents[2] / "shared")]

import numpy as np  # noqa: E402
from scipy.spatial.transform import Rotation  # noqa: E402

import arm_port  # noqa: E402
from runtime import Session  # noqa: E402
from scene import arm_rig  # noqa: E402
import floating_scene  # noqa: E402

OLD_CONFIG = json.loads((HERE / "floating_task.json").read_text())
L_ROT = float(np.pi / 2)
REST = {"left": [0.5, -0.6, 0.0, -1.5, 0.3, 0.1, 0.5], "right": [-0.5, -0.6, 0.0, -1.5, -0.3, -0.1, -0.5]}
SEEDS = {"left": [[0.5, -0.6, 0.0, -1.5, 0.3, 0.1, 0.5], [0.0, -0.3, 0.0, -1.9, 0.0, 0.6, -1.5]],
         "right": [[-0.5, -0.6, 0.0, -1.5, -0.3, -0.1, -0.5], [0.0, -0.3, 0.0, -1.9, 0.0, 0.6, 1.5]]}


def old_initial(hand):
    """The wave-2 start targets with the left stage pose rotated by L_ROT about the grinder axis."""
    row = np.asarray(OLD_CONFIG["initial_targets"][hand], dtype=float).copy()
    Rz = Rotation.from_euler("z", L_ROT)
    centre = np.array([0.45, 0.0, 0.0])
    p = row[6:9]
    row[6:9] = centre + Rz.apply(p - centre) * [1, 1, 0] + [0, 0, p[2]]
    row[9:12] = (Rz * Rotation.from_euler("XYZ", row[9:12])).as_euler("XYZ")
    return row


def old_model(hand):
    model, _ = floating_scene.build(OLD_CONFIG, None, hand)
    return model


def sides():
    return {side: dict(stage_joints=[f"{side}_wrist_{a}" for a in ("x", "y", "z", "rx", "ry", "rz")],
                       old_root=f"{side}_hand_C_MC", new_root=f"{side}_wrist_stage") for side in ("left", "right")}


PROXY = {"ki": 0.0, "bias_limit": 0.03}
KI_CRANK = {"left": 0.0, "right": 0.0}  # optional joint integral per arm while cranking (authoring experiments)
CONFIG = None  # task.json (with an in-process start pose when --fresh-init is given)


def make_proxy(hand, session=None):
    s = session or Session(hand=hand, config=CONFIG)
    om = old_model(hand)
    lo, hi = om.actuator_ctrlrange.T.copy()
    return arm_port.StageProxy(s, om, sides(), lambda name: name, old_initial(hand), arm_rig.ARM_JOINTS,
                               arm_rig.PARK, rest=REST, extra={"lo": lo, "hi": hi}, **PROXY)


def init_pose(hand="sharpa"):
    s = Session(hand=hand, config=CONFIG)
    om = old_model(hand)
    start = old_initial(hand)
    names = [om.actuator(i).name for i in range(om.nu)]
    out = {}
    for side, spec in sides().items():
        fk = arm_port.StageFK(om, spec["stage_joints"], spec["old_root"])
        wrist = [start[names.index(j + "_act")] for j in spec["stage_joints"]]
        pos, R = fk(np.asarray(wrist))
        ik = arm_port.ArmIK(s.model, arm_rig.ARM_JOINTS[side], spec["new_root"], rest=REST[side])
        best = None
        for seed in SEEDS[side] + [list(np.random.default_rng(k).uniform(ik.lo, ik.hi)) for k in range(20)]:
            q, ep, er = ik.solve(pos, R, q0=np.asarray(seed), qpos=s.data.qpos, iters=400)
            score = ep + 0.05 * er
            if best is None or score < best[0] - 1e-4:
                best = (score, q, ep, er)
        _, q, ep, er = best
        print(side, "start ik err mm/deg", round(ep * 1000, 3), round(np.degrees(er), 3), np.round(q, 4).tolist())
        for name, value in zip(arm_rig.ARM_JOINTS[side], q):
            out[name + "_target"] = float(value)
    return out


def main():
    global L_ROT, CONFIG
    ap = argparse.ArgumentParser()
    ap.add_argument("--hand", default="sharpa")
    ap.add_argument("--out")
    ap.add_argument("--log")
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--param", action="append", default=[])
    ap.add_argument("--extra-hold", type=int, default=100)
    ap.add_argument("--ki", type=float, default=PROXY["ki"])
    ap.add_argument("--bias-limit", type=float, default=PROXY["bias_limit"])
    ap.add_argument("--l-rot", type=float, default=L_ROT)
    ap.add_argument("--fresh-init", action="store_true", help="solve the start pose in-process (do not use task.json's)")
    ap.add_argument("--ki-crank-left", type=float, default=0.0)
    args = ap.parse_args()
    L_ROT = args.l_rot
    CONFIG = json.loads((HERE.parent / "task.json").read_text())
    if args.fresh_init:
        CONFIG["initial_targets"] = {h: init_pose(h) for h in ("sharpa",)} | {"wuji": {}}
    if args.init:
        targets = init_pose(args.hand)
        path = HERE.parent / "task.json"
        config = json.loads(path.read_text())
        for hand in ("sharpa", "wuji"):
            config["initial_targets"][hand] = targets
        path.write_text(json.dumps(config, indent=2) + "\n")
        return
    PROXY.update(ki=args.ki, bias_limit=args.bias_limit)
    import author
    from search_episode import params
    holder = {}

    def factory(hand="sharpa"):
        holder["px"] = make_proxy(hand)
        return holder["px"]

    author.Session = factory
    x = json.loads((HERE / "oracle_params.json").read_text())["x"]
    kw = params(x)
    kw["l_rot"] = L_ROT
    for item in args.param:
        k, v = item.split("=", 1)
        kw[k] = json.loads(v)
    a = author.Author(args.hand, **kw)
    if args.ki_crank_left:
        px = holder["px"]
        emit = a.emit

        def gated(values, phase):
            if phase == "crank" and px.ki == 0.0:
                px.ki, px.bias_limit = args.ki_crank_left, 0.05
                px.active_ki = ("left",)
            return emit(values, phase)

        a.emit = gated
    st = a.run(verbose=True)
    px = holder["px"]
    st = px.s.status()
    print(json.dumps({k: st.get(k) for k in ("success", "reason", "steps", "stage", "net_clockwise_deg",
                                             "failure_detail")}, default=str))
    errs = np.array([[v[2] for v in e.values()] for e in px.log if e])
    rots = np.array([[v[3] for v in e.values()] for e in px.log if e])
    if len(errs):
        print("tracking err mm: max", np.round(errs.max(0) * 1000, 2).tolist(), "mean",
              np.round(errs.mean(0) * 1000, 2).tolist(), "rot deg max", np.round(np.degrees(rots.max(0)), 2).tolist())
    if args.log:
        Path(args.log).write_text(json.dumps({"track": px.log, "phases": a.phases}))
    if args.out:
        rows = np.array(px.rows)
        if st["success"]:
            rows = np.concatenate([rows, np.repeat(rows[-1:], args.extra_hold, 0)])
        px.s.save_trajectory(rows, args.out)
        print("saved", rows.shape)


if __name__ == "__main__":
    main()
