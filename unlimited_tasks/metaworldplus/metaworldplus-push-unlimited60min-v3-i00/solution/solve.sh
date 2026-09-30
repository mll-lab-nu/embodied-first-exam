#!/bin/bash
set -euo pipefail
python - <<'PYCODE'
from mw_runtime import Session,load_trajectory
s=Session()
for a in load_trajectory('/solution/oracle.npz',s.instance_sha):s.step(a)
s.save()
s.close()
PYCODE
