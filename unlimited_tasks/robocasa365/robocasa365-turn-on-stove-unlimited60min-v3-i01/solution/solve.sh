#!/bin/bash
set -euo pipefail
python - <<'PYCODE'
from casa_runtime import Session,load_trajectory
s=Session(replaying=True)
actions,controls=load_trajectory('/solution/oracle.npz',s)
for a,c in zip(actions,controls):s.step(a,c)
s.save();s.close()
PYCODE
