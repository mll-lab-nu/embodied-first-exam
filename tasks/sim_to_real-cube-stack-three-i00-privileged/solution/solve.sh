#!/bin/bash
# Oracle: replay the scripted IK controller's recorded targets (solution/oracle_yam.py, run offline on this instance).
set -e
mkdir -p /app/output
python - <<'PY'
import numpy as np, rcb_yam as ry
A = np.load("/solution/oracle_targets.npy"); s = ry.Session("/app/instance.json"); print(s.replay(A))
s.save_trajectory(A, "/app/output/trajectory.npz", meta={"source": "oracle replay (scripted IK)"})
PY
cp /solution/oracle_yam.py /app/output/gen.py
