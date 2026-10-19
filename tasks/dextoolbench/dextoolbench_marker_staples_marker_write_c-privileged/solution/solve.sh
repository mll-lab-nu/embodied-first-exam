#!/bin/bash
# Oracle: replay SimToolReal's pretrained policy's joint targets (recorded offline with scripts/dtb_mk_oracle.py in this
# exact scene; the policy itself is never shipped) and hand them in as the trajectory.
set -e
mkdir -p /app/output
python - <<'PY'
import numpy as np, rcb_dtb
A = np.load("/solution/oracle_targets.npy")
s = rcb_dtb.Session("/app/instance.json"); r = s.replay(A); print(r)
s.save_trajectory(A, "/app/output/trajectory.npz", meta={"source": "oracle replay"})
PY
cp /solution/solve.sh /app/output/gen.py
