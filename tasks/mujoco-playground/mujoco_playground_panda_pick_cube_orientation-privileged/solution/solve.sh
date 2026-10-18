#!/bin/bash
# Oracle: replay the scripted IK controller's recorded targets (solution/oracle_ik.py, run offline on this instance).
set -e
mkdir -p /app/output
python - <<'PY'
import numpy as np, rcb_panda as rp
A = np.load("/solution/oracle_targets.npy"); s = rp.Session("/app/instance.json"); print(s.replay(A))
s.save_trajectory(A, "/app/output/trajectory.npz", meta={"source": "oracle replay (scripted IK)"})
PY
cp /solution/oracle_ik.py /app/output/gen.py
