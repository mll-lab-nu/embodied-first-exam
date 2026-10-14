"""Reproduce the Wuji Hand 2.2 essential_held_joystick authoring rows (../solution/wuji/trajectory.npz).

Two deterministic authoring stages, both sending only the 26 Wuji actuator targets (wrist targets locked):
1. ctrl.py (60 rows): thumb approach onto the joystick's flat cap (kinematic IK in a separate MjData) while middle
   and ring MCP ramp to a light 0.3 rad curl that props the shell.
2. mpc.py: thumb joint targets chosen by short physics rollouts from snapshots of the authoring session
   (finite-difference Jacobian of the measured gimbal angles), committed 4 control steps at a time, until the checker
   reports success (left, front, right, back, center, terminal hold).
Run with the task's runtime importable (MuJoCo 3.4.0, DEXHAND_ASSET_DIR / WUJI_ASSET_DIR set):
    PYTHONPATH=tasks/dexhand-essential-held-joystick-i00-privileged/environment python wuji_gen.py --out <dir>
It writes <dir>/mpc/actions.npy and prints the rows' sha256 (eb51d40e..., the rows of ../solution/wuji/trajectory.npz).
"""
import argparse, hashlib, subprocess, sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
WORK = HERE   # ctrl.py, mpc.py and snap.py sit next to this script

ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
a = ap.parse_args()
out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
py = sys.executable
subprocess.run([py, str(WORK / "ctrl.py"), "--out", str(out / "prefix"), "--press", "0.006", "--ki", "0.002", "--kp", "0.0",
                "--curl", "MFJ0=0.3,RFJ0=0.3", "--max", "60"], check=True, cwd=WORK)
subprocess.run([py, str(WORK / "mpc.py"), "--prefix", str(out / "prefix" / "actions.npy"), "--prefix-rows", "60",
                "--out", str(out / "mpc")], check=True, cwd=WORK)
actions = np.load(out / "mpc" / "actions.npy")
print("rows", len(actions), "sha256(actions float64)", hashlib.sha256(np.ascontiguousarray(actions, dtype=np.float64).tobytes()).hexdigest())
