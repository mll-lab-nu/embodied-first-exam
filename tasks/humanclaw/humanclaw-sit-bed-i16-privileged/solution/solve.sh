#!/bin/bash
# Reference solution: the navmesh oracle (shortest path to the target, turn-and-walk, then sit for an interaction
# episode, then stop) with the privileged tools. First the actions it found on the reference GPU (actions.json), checked
# by a local replay; the physics is chaotic and the motion model's GPU arithmetic differs between GPU models, so where
# that replay fails the oracle runs again, closed loop, on this machine (oracle.py, a few minutes).
set -e
mkdir -p /app/output
python - <<'PY'
import json, numpy as np
a = np.array(json.load(open("/solution/actions.json")), dtype=np.float64).reshape(-1, 2)
np.savez("/app/output/trajectory.npz", actions=a)
PY
python /opt/tools/hc_tools.py replay /app/output/trajectory.npz --json /tmp/oracle_replay.json > /tmp/oracle_replay.log 2>&1 || true
if ! python -c "import json,sys; sys.exit(0 if json.load(open('/tmp/oracle_replay.json'))['success'] else 1)" 2>/dev/null; then
  echo "the stored actions do not succeed on this GPU: running the oracle closed loop"
  python /solution/oracle.py /app/instance.json /tmp/oracle.json > /tmp/oracle.log 2>&1
  python - <<'PY'
import json, numpy as np
o = json.load(open("/tmp/oracle.json"))
print("closed-loop oracle:", "success" if o["success"] else "failure", len(o["actions"]), "actions")
np.savez("/app/output/trajectory.npz", actions=np.array(o["actions"], dtype=np.float64).reshape(-1, 2))
PY
fi
