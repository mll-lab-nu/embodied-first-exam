"""Regenerate the successful Wuji Hand 2.2 essential_cube_layer trajectory (motor targets only).

Runs the thumb-drag controller of run_turn.py (IK helper thumb_turn.py) once with the accepted
parameters (no search). The cube rests on the open Wuji palm (neutral reset); the thumb pad lands on the top face of
the passive layer and drags it about the layer axis: +90 deg, back to 0, +90 deg again, then holds. The contact angle is
driven by an integral law on the measured layer angle; at the end of the reachable arc the pad lifts, moves back and
lands again (ratchet). Other fingers keep their reset targets; the six wrist targets stay at the locked pose.
Only actuator target rows are produced (Session.step); no object pose, weld, force or predicate is touched.
Output: trajectory.npz (actions + hand + task, via Session.save_trajectory).

Usage (pinned MuJoCo 3.4.0 env, or inside ghcr.io/mll-lab-nu/eai-dexhand:0.2.0):
    PYTHONPATH=<task>/environment python wuji_gen.py --out <file>
It rewrites ../solution/wuji/trajectory.npz byte for byte.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))   # run_turn.py, thumb_turn.py
import run_turn  # noqa: E402

# Accepted parameters (run "d1" of the authoring sweep; IK clearance model margin 0.015 m in thumb_turn.py).
ACCEPTED = ["--steps", "1500", "--alpha-range", "130", "170", "--clearance", "0.003", "--rlift", "0.008",
            "--move-clearance", "0.006",
            "--phi0", "130", "--quiet"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="/app/output/trajectory.npz")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        summary = run_turn.main(["--out", tmp] + ACCEPTED)
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(tmp) / "trajectory.npz", out)
        rows = np.load(Path(tmp) / "rows.npy")
    print("status", summary["status"])
    print("rows", rows.shape, "rows_sha256(<f8)", hashlib.sha256(np.ascontiguousarray(rows, "<f8").tobytes()).hexdigest())
    print("file_sha256", hashlib.sha256(out.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
