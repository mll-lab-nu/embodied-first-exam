#!/usr/bin/env python3
"""Authoring check: the packaged scene reproduces the accepted native episode bit for bit.

Runs the packaged Session on the oracle rows (solution/trajectory.json + parts) until the predicate ends the episode, records the verdict,
then executes the remaining accepted rows with plain native steps and compares the integration-state hash with the
accepted run's final hash (and the initial hash before the first step). Writes a JSON report.

    PYTHONPATH=<family>:<scripts/dexhand/shared> DEXHAND_ASSET_DIR=... python tools/bitexact.py --out report.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import mujoco
import numpy as np

from runtime import Session

FAMILY = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--traj", type=Path, help="an .npz with `actions` (default: the packaged oracle parts)")
    args = parser.parse_args()
    if args.traj:
        with np.load(args.traj, allow_pickle=False) as archive:
            actions = np.asarray(archive["actions"], dtype=np.float64)
    else:
        import sys

        sys.path.insert(0, str(FAMILY.parents[1] / "shared/solution"))
        from solution_parts import load

        actions = load(FAMILY / "solution")[0]
    start = time.time()
    session = Session()
    source = json.loads((FAMILY / "provenance.json").read_text())
    initial = session.physics_sha()
    status = session.replay(actions)
    verdict = session.features()
    latched_at = session.steps
    state_sha = session.state_sha()
    # Continue the accepted rows after the latch with plain native steps (no predicate), as the accepted run did;
    # the hold rows appended after the accepted rows are not part of the accepted run.
    for row in actions[latched_at : int(source["native_steps"])]:
        session.data.ctrl[:] = row
        mujoco.mj_step(session.model, session.data)
    final = session.physics_sha()
    report = {
        "rows": int(len(actions)),
        "initial_physics_sha": initial,
        "initial_matches_accepted": initial == source["native_initial_state_sha256"],
        "final_physics_sha_after_all_rows": final,
        "final_matches_accepted": final == source["native_final_state_sha256"],
        "status_at_latch": status,
        "latched_after_steps": latched_at,
        "state_sha_at_latch": state_sha,
        "verdict": verdict,
        "seconds": time.time() - start,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: report[k] for k in ("initial_matches_accepted", "final_matches_accepted", "latched_after_steps",
                                             "seconds")}, sort_keys=True))
    print(json.dumps(status, sort_keys=True))
    session.close()
    return 0 if report["initial_matches_accepted"] and report["final_matches_accepted"] and status["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
