#!/usr/bin/env python3
"""Authoring only: prove that the packaged scene preserves the accepted T17 physics bit for bit.

1. Raw physics: compile the packaged Sharpa scene, reset to its keyframe and execute all 8,850 accepted rows
   (``mj_step`` + ``mj_forward``, exactly like the accepted audit). Every qpos/qvel must equal the recorded trace
   exactly, and the initial/final integration-state digests must equal the accepted audit's digests.
2. Packaged predicate: ``Session.replay`` of ``solution/trajectory.npz`` must succeed (the episode ends when the 2 s
   released hold completes), with every executed state equal to the recorded trace.
3. Two fresh-process ``replay.py`` runs of the oracle must both succeed with identical ``state_sha``.

Writes a JSON report (``--out``). Needs the repository asset folders (or the image paths):
DEXHAND_ASSET_DIR=images/dexhand/assets/hand DEXHAND_TIANJI_DIR=images/everyday_dexterity/assets/tianji
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

FAMILY = Path(__file__).resolve().parents[1]
REPO = FAMILY.parents[3]
TRIAL = REPO.parent / "artifacts/scene-expansion-50/evidence/pot_transfer/trial-14"
os.environ.setdefault("DEXHAND_ASSET_DIR", str(REPO / "images/dexhand/assets/hand"))
os.environ.setdefault("DEXHAND_TIANJI_DIR", str(REPO / "images/everyday_dexterity/assets/tianji"))
sys.path[:0] = [str(FAMILY), str(REPO / "scripts/dexhand/shared")]

import mujoco  # noqa: E402
import numpy as np  # noqa: E402

from runtime import STATE, Session, build  # noqa: E402

ACCEPTED_INITIAL = "00ac17f0114d1291559153500ceb2ac3d32d084518b2853b4771c64f1815dbb1"
ACCEPTED_FINAL = "5bcddef8f382025f542e2529d4a866fe43b7f1ba876f292c9c059d4f8654e7da"


def digest(model, data) -> str:
    state = np.empty(mujoco.mj_stateSize(model, STATE))
    mujoco.mj_getState(model, data, state, STATE)
    return hashlib.sha256(state.astype("<f8").tobytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    trace = dict(np.load(TRIAL / "trajectory.npz", allow_pickle=False))
    with np.load(FAMILY / "solution/trajectory.npz", allow_pickle=False) as archive:
        oracle = np.asarray(archive["actions"])
        oracle_hand = str(archive["hand"])
    report = {"oracle_rows": int(len(oracle)), "oracle_hand": oracle_hand,
              "oracle_equals_accepted_actions": bool(np.array_equal(oracle, trace["actions"]))}

    # 1. raw physics, all accepted rows
    started = time.time()
    model, _xml, _ = build("sharpa")
    data = mujoco.MjData(model)
    mujoco.mj_resetDataKeyframe(model, data, 0)
    mujoco.mj_forward(model, data)
    initial = digest(model, data)
    state0 = np.empty(mujoco.mj_stateSize(model, STATE))
    mujoco.mj_getState(model, data, state0, STATE)
    qerr = verr = 0.0
    for step, row in enumerate(oracle, 1):
        data.ctrl[:] = row
        mujoco.mj_step(model, data)
        mujoco.mj_forward(model, data)
        qerr = max(qerr, float(np.max(np.abs(data.qpos - trace["qpos"][step]))))
        verr = max(verr, float(np.max(np.abs(data.qvel - trace["qvel"][step]))))
    report["raw_physics"] = {
        "initial_sha": initial,
        "initial_matches_accepted": initial == ACCEPTED_INITIAL,
        "initial_state_equals_recorded": bool(np.array_equal(state0, trace["initial_state"])),
        "final_sha": digest(model, data),
        "final_matches_accepted": digest(model, data) == ACCEPTED_FINAL,
        "steps": int(len(oracle)),
        "max_abs_qpos_error": qerr,
        "max_abs_qvel_error": verr,
        "wall_s": round(time.time() - started, 1),
    }

    # 2. packaged predicate in this process (states compared with the recorded trace while the episode runs)
    started = time.time()
    session = Session(hand="sharpa")
    qerr = verr = 0.0
    for row in oracle:
        status = session.step(row)
        qerr = max(qerr, float(np.max(np.abs(session.data.qpos - trace["qpos"][session.steps]))))
        verr = max(verr, float(np.max(np.abs(session.data.qvel - trace["qvel"][session.steps]))))
        if status["done"]:
            break
    report["session"] = {**status, "max_abs_qpos_error": qerr, "max_abs_qvel_error": verr,
                         "state_sha": session.state_sha(), "physics_sha": session.physics_sha(),
                         "features": session.features(), "wall_s": round(time.time() - started, 1)}

    # 3. two fresh processes through the packaged replay CLI
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(FAMILY), str(REPO / "scripts/dexhand/shared")]))
    replays = []
    for index in (1, 2):
        out = args.out.with_name(args.out.stem + f"-replay{index}.json")
        started = time.time()
        subprocess.run([sys.executable, str(FAMILY / "replay.py"), "--task", "pot_shelf_transfer", "--traj",
                        str(FAMILY / "solution/trajectory.npz"), "--out", str(out)], check=True, env=env,
                       stdout=subprocess.DEVNULL)
        result = json.loads(out.read_text())
        replays.append({k: result[k] for k in ("success", "state_sha", "steps", "stage", "reason", "hand",
                                                "bad_trajectory")} | {"wall_s": round(time.time() - started, 1),
                                                                      "json": str(out)})
    report["fresh_replays"] = replays
    report["pass"] = bool(
        report["oracle_equals_accepted_actions"]
        and report["raw_physics"]["initial_matches_accepted"]
        and report["raw_physics"]["initial_state_equals_recorded"]
        and report["raw_physics"]["final_matches_accepted"]
        and report["raw_physics"]["max_abs_qpos_error"] == 0.0
        and report["raw_physics"]["max_abs_qvel_error"] == 0.0
        and report["session"]["success"]
        and report["session"]["max_abs_qpos_error"] == 0.0
        and all(r["success"] for r in replays)
        and replays[0]["state_sha"] == replays[1]["state_sha"] == report["session"]["state_sha"]
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True, default=float) + "\n")
    print(json.dumps({"pass": report["pass"], "raw": report["raw_physics"], "session_steps": status["steps"],
                      "replays": replays}, indent=1, default=float))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
