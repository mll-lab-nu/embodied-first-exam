"""Authoring only: the Marvin-rig reset of pancake_serve, frozen into task.json initial_qpos/initial_targets[hand].

The right Wave sits on the right Marvin flange (mount body "wrist_stage"). The wave-2 reset (hand holding the turner
in a settled contact grasp, palm down above the counter) is transferred: arm joints from IK for the same hand-root
pose, the same finger joints/targets and object poses; then the scene integrates freely while a closed-loop arm
correction (IK + joint integral, motor targets only) removes the servo sag, and the settled state (zero velocity) with
its final targets is frozen. Episodes start from it with no state writes.

    python tools/make_reset_arm.py --legacy <wave-2 task.json> --hand sharpa [--write]
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
for _parent in HERE.parents:
    if (_parent / "shared/arm_ik.py").is_file():
        sys.path.append(str(_parent / "shared"))
        break

import mujoco  # noqa: E402

import arm_ik  # noqa: E402
import arm_rig  # noqa: E402
from runtime import Session  # noqa: E402

SEEDS = [np.array(s, dtype=float) for s in (
    [-0.6, -0.9, 0.0, -1.4, 0.0, 0.0, 0.0], [-1.0, -1.2, 0.5, -1.0, 0.5, 0.0, 0.0],
    [0.0, -1.5, -0.5, -1.8, 0.0, 0.0, 0.0], [-1.5, -0.6, 0.8, -1.2, -0.8, 0.3, 0.3],
    [-0.3, -0.5, 0.3, -1.6, 0.3, 0.0, 0.0], [-1.2, -1.0, -0.4, -1.5, 0.9, 0.2, -0.2],
    [-0.488, -0.159, -0.351, -2.176, -2.193, 0.6, 0.977])]
MARVIN = {"base_pos": [0.0, 0.0, 0.0], "base_yaw": 0.0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--legacy", required=True)
    ap.add_argument("--hand", default="sharpa")
    ap.add_argument("--settle", type=float, default=1.5)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    legacy = json.loads(Path(a.legacy).read_text())
    old = Session(config=legacy, hand=a.hand)
    om, od = old.model, old.data
    root_name = "right_hand_C_MC"
    hb = om.body(root_name).id
    pos, R = od.xpos[hb].copy(), od.xmat[hb].reshape(3, 3).copy()
    cfg = copy.deepcopy(json.loads((HERE / "task.json").read_text()))
    cfg["rig"], cfg["marvin"] = "marvin", MARVIN
    from scene import build

    model, _ = build(cfg, hand=a.hand)
    data = mujoco.MjData(model)
    ik = arm_ik.ArmIK(model, "right")
    best = None
    for seed in SEEDS:
        q, ep, er = ik.solve(pos, R, q0=seed, iters=400)
        if best is None or ep + 0.05 * er < best[0]:
            best = (ep + 0.05 * er, q, ep, er)
    q = best[1]
    print("IK err %.1e m %.1e rad" % (best[2], best[3]), q.round(3).tolist())
    lay = arm_rig.layout(model)
    row = arm_rig.default_targets(model, arm_pose={"right": q})
    # copy every non-stage joint by name (fingers, free bodies, turner bend joints) and the finger targets by name
    for j in range(om.njnt):
        name = om.joint(j).name
        if name.startswith("wrist_"):
            continue
        try:
            nj = model.joint(name).id
        except KeyError:
            continue
        n = {0: 7, 1: 4, 2: 1, 3: 1}[int(om.jnt_type[j])]
        data.qpos[model.jnt_qposadr[nj]:model.jnt_qposadr[nj] + n] = od.qpos[om.jnt_qposadr[j]:om.jnt_qposadr[j] + n]
    for i in range(om.nu):
        name = om.actuator(i).name
        try:
            row[model.actuator(name).id] = old.initial_targets[i]
        except KeyError:
            pass
    for side in ("left", "right"):
        data.qpos[arm_rig.arm_qpos_index(model, side)] = row[lay["arm"][side]]
    lo, hi = model.actuator_ctrlrange.T
    row = np.clip(row, lo, hi)
    data.ctrl[:] = row
    mujoco.mj_forward(model, data)
    substeps = round(cfg["control_dt"] / cfg["physics_dt"])
    bias = np.zeros(7)
    qadr = arm_rig.arm_qpos_index(model, "right")
    mount = model.body("wrist_stage").id
    for k in range(int(a.settle / cfg["control_dt"])):
        q_meas = data.qpos[qadr].copy()
        q_star, _, _ = ik.solve(pos, R, q0=row[lay["arm"]["right"]] - bias, qpos=data.qpos)
        bias = np.clip(bias + 0.25 * (q_star - q_meas), -0.25, 0.25)
        row[lay["arm"]["right"]] = np.clip(q_star + bias, lo[lay["arm"]["right"]], hi[lay["arm"]["right"]])
        row = row.astype(np.float32).astype(np.float64)
        data.ctrl[:] = row
        for _ in range(substeps):
            mujoco.mj_step(model, data)
    data.qvel[:] = 0
    mujoco.mj_forward(model, data)
    print("hand-root error after settle %.4f m" % np.linalg.norm(data.xpos[mount] - pos))
    t = model.body("turner").id
    print("turner", data.xpos[t].round(4).tolist(), "old", od.xpos[om.body("turner").id].round(4).tolist())
    if a.write:
        out = json.loads((HERE / "task.json").read_text())
        out["rig"], out["marvin"] = "marvin", MARVIN
        out.setdefault("initial_qpos", {})[a.hand] = [float(v) for v in data.qpos]
        out.setdefault("initial_targets", {})[a.hand] = [float(v) for v in row]
        (HERE / "task.json").write_text(json.dumps(out, indent=1) + "\n")
        print("wrote", a.hand)


if __name__ == "__main__":
    main()
