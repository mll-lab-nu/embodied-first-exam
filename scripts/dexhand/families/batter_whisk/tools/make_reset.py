"""Authoring only: settle the pre-held whisk grasp and freeze it as task.json reset_state[<hand>].

The whisk is placed upright at task.json ``whisk_pos`` (wire tip; handle axis through the wrist-stage origin) and
held fixed only while the fingers close on it (authoring step, never part of an episode); then it is released,
the hand holds it under gravity for ``--settle`` seconds with the wrist stage at its zero targets, and the
resulting joint positions (velocities zeroed) are written as the frozen reset. Episodes start from that
state with no pinning, welds or state writes.

    python tools/make_reset.py --hand sharpa --grasp '[...]' [--write]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import mujoco  # noqa: E402

from scene import build  # noqa: E402


def settle(config, hand, fingers, offset=(0.0, 0.0), close_s=0.8, settle_s=1.5):
    model, _ = build(config, hand=hand)
    data = mujoco.MjData(model)
    lo, hi = model.actuator_ctrlrange.T
    ctrl = np.zeros(model.nu)
    ctrl[:3] = config["stage"]["origin"]  # the grip point at reset (world)
    ctrl[6:] = np.clip(fingers, lo[6:], hi[6:])
    slides = [model.jnt_qposadr[model.joint(n).id] for n in ("wrist_x", "wrist_y", "wrist_z")]
    data.qpos[slides] = ctrl[:3]
    jid = model.joint("whisk_free").id
    qa, va = model.jnt_qposadr[jid], model.jnt_dofadr[jid]
    data.qpos[qa:qa + 2] += offset
    mujoco.mj_forward(model, data)
    pinned = data.qpos[qa:qa + 7].copy()
    n_close = int(close_s / model.opt.timestep)
    for k in range(n_close + 100):
        a = min(1.0, k / n_close)
        data.ctrl[:6] = ctrl[:6]
        data.ctrl[6:] = a * ctrl[6:]
        mujoco.mj_step(model, data)
        data.qpos[qa:qa + 7] = pinned
        data.qvel[va:va + 6] = 0
    data.ctrl[:] = ctrl
    for _ in range(int(settle_s / model.opt.timestep)):
        mujoco.mj_step(model, data)
    return model, data, ctrl


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hand", default="sharpa")
    parser.add_argument("--grasp", required=True, help="JSON list of finger targets (native actuator order)")
    parser.add_argument("--offset", default="[0, 0]", help="whisk x/y offset from the grip point (hand-specific)")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    path = HERE / "task.json"
    config = json.loads(path.read_text())
    model, data, ctrl = settle(config, args.hand, np.asarray(json.loads(args.grasp), dtype=float),
                                np.asarray(json.loads(args.offset), dtype=float))
    whisk = model.body("whisk").id
    stage = model.body("wrist_stage").id
    print("whisk xpos", data.xpos[whisk].round(4).tolist(), "stage", data.xpos[stage].round(4).tolist())
    record = {"qpos": [float(v) for v in data.qpos], "ctrl": [float(v) for v in ctrl]}
    if args.write:
        config.setdefault("reset_state", {})[args.hand] = record
        path.write_text(json.dumps(config, indent=1) + "\n")
        print("wrote reset_state", args.hand)


if __name__ == "__main__":
    main()
