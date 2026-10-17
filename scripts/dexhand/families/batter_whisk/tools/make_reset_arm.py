"""Authoring only: the Marvin-rig reset of batter_whisk, frozen into task.json reset_state[<hand>].

The source (T49) starts with the whisk standing in the bowl, head in the batter. Without a hand that pose is not
statically stable (the heavy handle tips the whisk over the rim), so the whisk is released from the source pose,
tilted 3 deg toward ``--azimuth``, and the scene integrates freely for ``--settle`` s with both arms holding their
ready pose (palms down above the counter, fingers open). The settled state (velocities zeroed) is the reset: the
whisk rests against the bowl rim with its handle end on the counter. Episodes start from it with no state writes.

    python tools/make_reset_arm.py --hand sharpa [--write]
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tools"))

import mujoco  # noqa: E402

import armlib  # noqa: E402
from scene import build  # noqa: E402

SEEDS = [np.array(s, dtype=float) for s in (
    [-0.6, -0.9, 0.0, -1.4, 0.0, 0.0, 0.0], [-1.0, -1.2, 0.5, -1.0, 0.5, 0.0, 0.0],
    [0.0, -1.5, -0.5, -1.8, 0.0, 0.0, 0.0], [-1.5, -0.6, 0.8, -1.2, -0.8, 0.3, 0.3],
    [-0.3, -0.5, 0.3, -1.6, 0.3, 0.0, 0.0], [-1.2, -1.0, -0.4, -1.5, 0.9, 0.2, -0.2])]
MIRROR = np.array([-1, 1, -1, 1, -1, 1, -1.0])  # right-arm joint vector -> mirror-image left-arm vector
# Ready poses (world): hand roots above the counter near the robot, palms down, fingers pointing forward (+x).
READY = {"right": ([0.30, -0.30, 0.90], ([0, 0, -1.0], [0, 1.0, 0])),
         "left": ([0.30, 0.30, 0.90], ([0, 0, -1.0], [0, 1.0, 0]))}  # left Wave: y axis = -thumb


def best_ik(ik, pos, R, seeds):
    best = None
    for seed in seeds:
        mirrored = seed if ik.side == "right" else seed * MIRROR
        q, ep, er = ik.solve(np.asarray(pos, float), R, q0=mirrored, iters=400)
        cost = ep + 0.05 * er
        if best is None or cost < best[0]:
            best = (cost, q, ep, er)
    return best[1], best[2], best[3]


def ready_targets(model):
    import arm_rig

    arms = {}
    for side, (pos, (palm, index)) in READY.items():
        ik = armlib.arm_ik.ArmIK(model, side)
        R = armlib.frame(palm, index)
        q, ep, er = best_ik(ik, pos, R, SEEDS)
        print(side, "ready IK err %.1e m %.1e rad" % (ep, er), q.round(3).tolist())
        arms[side] = q
    lo, hi = model.actuator_ctrlrange.T
    lay = arm_rig.layout(model)
    row = arm_rig.default_targets(model, arm_pose=arms)
    for side in ("left", "right"):
        row[lay["fingers"][side]] = np.clip(0.0, lo[lay["fingers"][side]], hi[lay["fingers"][side]])
    return row


def settle(config, hand, azimuth, settle_s=3.0):
    model, _ = build(config, hand=hand)
    data = mujoco.MjData(model)
    import arm_rig

    row = ready_targets(model)
    lay = arm_rig.layout(model)
    for side in ("left", "right"):
        data.qpos[arm_rig.arm_qpos_index(model, side)] = row[lay["arm"][side]]
    for i in range(14, model.nu):
        data.qpos[model.jnt_qposadr[model.actuator_trnid[i, 0]]] = row[i]
    data.ctrl[:] = row
    jid = model.joint("whisk_free").id
    qa = model.jnt_qposadr[jid]
    bq = model.jnt_qposadr[model.joint("bowl_free").id]
    tilt = math.radians(3.0)
    axis = np.array([math.sin(tilt) * math.cos(azimuth), math.sin(tilt) * math.sin(azimuth), math.cos(tilt)])
    v = np.cross([0, 0, 1.0], axis)
    s = np.linalg.norm(v)
    half = math.asin(s) / 2
    data.qpos[qa:qa + 3] = data.qpos[bq:bq + 3] + [0, 0, 0.009]  # source: wire tip 9 mm above the bowl origin
    data.qpos[qa + 3:qa + 7] = np.r_[math.cos(half), v / s * math.sin(half)]
    mujoco.mj_forward(model, data)
    for _ in range(int(settle_s / model.opt.timestep)):
        mujoco.mj_step(model, data)
    data.qvel[:] = 0
    mujoco.mj_forward(model, data)
    return model, data, row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hand", default="sharpa")
    parser.add_argument("--azimuth", type=float, default=-math.pi / 2 - 0.35,
                        help="direction (rad, world) toward which the whisk tips from the source pose")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    path = HERE / "task.json"
    config = json.loads(path.read_text())
    model, data, row = settle(config, args.hand, args.azimuth)
    w = model.body("whisk").id
    R = data.xmat[w].reshape(3, 3)
    print("whisk tip", data.xpos[w].round(4).tolist(), "axis", R[:, 2].round(4).tolist())
    contacts = sorted({(model.geom(c.geom1).name.split("_")[0], model.geom(c.geom2).name.split("_")[0])
                       for c in data.contact[:data.ncon]})
    print("contacts", contacts)
    record = {"qpos": [float(v) for v in data.qpos], "ctrl": [float(v) for v in row]}
    if args.write:
        config.setdefault("reset_state", {})[args.hand] = record
        path.write_text(json.dumps(config, indent=1) + "\n")
        print("wrote reset_state", args.hand)


if __name__ == "__main__":
    main()
