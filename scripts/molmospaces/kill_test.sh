#!/usr/bin/env bash
# Crash-recovery acceptance test for one MolmoSpaces standard task (docs/STANDARD_MODE_2_2.md §13; resume class exact),
# without an agent: run the task's sim service in a container of eai-molmospaces with the restart policy of its compose
# file, drive it with the shared client (a few joint_position chunks), kill -9 the service between two calls, check that
# it resumed the SAME episode exactly, end it with `done`, run the collect hook (finalize.sh) and check final.json:
# the live run equals both fresh-process replays and the resume is counted.
#   usage: scripts/molmospaces/kill_test.sh [task dir]     (default tasks/molmospaces-pick-i00-standard)
# Needs the eai-molmospaces image, docker with the NVIDIA runtime.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
TASK=$(cd "${1:-$ROOT/tasks/molmospaces-pick-i00-standard}" && pwd)
IMAGE=$(awk '$1 == "image:" {print $2; exit}' "$TASK/environment/docker-compose.yaml")
UNITS=$(sed -n 's/^ *RCB_ACTION_UNITS: //p' "$TASK/environment/docker-compose.yaml" |
        python3 -c 'import json, sys; print(json.load(sys.stdin).replace("$$", "$"))')
NAME="rcb-molmospaces-kill-$$"
dk() { if docker ps >/dev/null 2>&1; then docker "$@"; else sg docker -c "docker $(printf '%q ' "$@")"; fi; }
trap 'dk rm -f "$NAME" >/dev/null 2>&1 || true' EXIT
dk run -d --name "$NAME" --gpus all --restart on-failure:6 -w /tmp \
   -v "$TASK/environment/sim:/srv:ro" -v "$ROOT/scripts/eai_standard:/client:ro" \
   -e RCB_INSTANCE=/srv/instance.json -e RCB_TOOL=/srv/rcb_molmospaces.py -e RCB_DATA=/data -e PYTHONPATH=/srv \
   -e RCB_ACTION_UNITS="$UNITS" -e RCB_SESSION_LOG= "$IMAGE" sh /srv/run.sh >/dev/null
drive() {  # one phase of the client, inside the container (the service is localhost:8000 there)
  dk exec -i "$NAME" env PYTHONPATH=/client python - "$1" <<'PY'
import sys, numpy as np
from rcb_client import Robot
r = Robot("http://localhost:8000"); r.wait_ready()
if sys.argv[1] == "act":                # hold the measured joints (the first one nudged), grippers open, two chunks
    spec = r.spec(); lim = spec["action_types"]["joint_position"]["limits"]
    q = r.get_obs().meta["proprio"]["now"][:len(spec["kinematics"]["joint_names"])]
    row = np.array(list(q) + [lo for name, (lo, hi) in lim.items() if name.endswith("gripper")])
    row[0] += 0.05
    r.submit("joint_position", np.tile(row, (10, 1))); r.submit("joint_position", np.tile(row, (10, 1)))
else:
    r.submit("done", [])
print(r.status())
PY
}
until dk exec "$NAME" test -f /data/server.pid 2>/dev/null; do sleep 2; done
echo "[kill_test] before: $(drive act)"
pid=$(dk exec "$NAME" cat /data/server.pid); restarts=$(dk inspect -f '{{.RestartCount}}' "$NAME")
dk exec "$NAME" sh -c "kill -9 $pid"
echo "[kill_test] killed the service (pid $pid); waiting for the restart"
until [ "$(dk inspect -f '{{.RestartCount}}' "$NAME")" -gt "$restarts" ] && dk exec "$NAME" test -f /data/server.pid 2>/dev/null; do sleep 2; done
echo "[kill_test] after:  $(drive done)"
dk exec "$NAME" sh /srv/finalize.sh > /dev/null
dk exec "$NAME" cat /data/final.json | python3 -c '
import json, sys
d = json.load(sys.stdin)
want = {"deterministic": True, "live_matches_replay": True, "resumes": 1, "resume_state_mismatch": 0, "reason": "done"}
bad = {k: d.get(k) for k, v in want.items() if d.get(k) != v}
print(json.dumps({k: d.get(k) for k in ("success", "replay_success", "deterministic", "live_matches_replay", "resumes", "sim_startups", "control_steps", "reason")}))
print("[kill_test]", "PASS" if not bad else f"FAIL {bad}")
sys.exit(1 if bad else 0)'
