#!/usr/bin/env bash
# Crash-recovery acceptance test for one LabUtopia standard task (docs/STANDARD_MODE.md §13; resume class exact),
# without an agent: run the task's sim service in a container of eai-labutopia with the restart policy of its compose
# file, stream the first part of the task's reference rows through the shared client, kill -9 the service between two
# calls, check that it resumed the SAME episode, stream the rest, run the collect hook (finalize.sh) and check
# final.json: success, the live run equal to both fresh-process replays, and the resume counted.
#   usage: scripts/labutopia/kill_test.sh [task dir]     (default tasks/labutopia-pick-i00-standard)
# Needs the eai-labutopia image, docker with the NVIDIA Container Toolkit and an RTX-class GPU. The service's first
# start prepares the scene (5 to 15 minutes); the restart after the kill takes about 20 s.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
TASK=$(cd "${1:-$ROOT/tasks/labutopia-pick-i00-standard}" && pwd)
IMAGE=$(awk '$1 == "image:" {print $2; exit}' "$TASK/environment/docker-compose.yaml")
NAME="rcb-labutopia-kill-$$"
dk() { if docker ps >/dev/null 2>&1; then docker "$@"; else sg docker -c "docker $(printf '%q ' "$@")"; fi; }
trap 'dk rm -f "$NAME" >/dev/null 2>&1 || true' EXIT
dk run -d --name "$NAME" --restart on-failure:6 --gpus all --shm-size 8g -w /tmp \
   -v "$TASK/environment/sim:/srv:ro" -v "$ROOT/scripts/eai_standard:/client:ro" -v "$TASK/solution:/solution:ro" \
   -e RCB_INSTANCE=/srv/instance.json -e RCB_TOOL=/srv/rcb_labutopia.py -e RCB_DATA=/data -e PYTHONPATH=/srv \
   -e RCB_STARTUP_TIMEOUT_S=2400 -e RCB_SESSION_LOG= "$IMAGE" sh /srv/run.sh >/dev/null
drive() {  # one phase of the client, inside the container (the service is localhost:8000 there)
  dk exec -i "$NAME" env PYTHONPATH=/client python - "$1" <<'PY'
import sys, numpy as np
from rcb_client import EpisodeOver, Robot
A = np.load("/solution/oracle.npz")["actions"].astype(np.float64)
r = Robot("http://localhost:8000"); st = r.wait_ready()
i = int(st["control_steps"]); stop = len(A) // 2 if sys.argv[1] == "first" else len(A)
while i < stop and not st.get("done"):
    try:
        res = r.submit("joint_position_velocity", A[i:min(i + 120, stop)], dt=1.0 / 60, interpolate="hold", video="none")
    except EpisodeOver:
        break
    i = int(res.meta["control_steps"])
    if res.meta["done"]:
        break
print(r.status())
PY
}
echo "[kill_test] waiting for the service (the first start prepares the scene)"
until dk exec "$NAME" test -f /data/server.pid 2>/dev/null; do sleep 5; done
echo "[kill_test] first half: $(drive first)"
pid=$(dk exec "$NAME" cat /data/server.pid); restarts=$(dk inspect -f '{{.RestartCount}}' "$NAME")
dk exec "$NAME" sh -c "kill -9 $pid"
echo "[kill_test] killed the service (pid $pid); waiting for the restart"
until [ "$(dk inspect -f '{{.RestartCount}}' "$NAME")" -gt "$restarts" ] && dk exec "$NAME" test -f /data/server.pid 2>/dev/null; do sleep 2; done
echo "[kill_test] rest:       $(drive rest)"
dk exec "$NAME" sh /srv/finalize.sh > /dev/null
dk exec "$NAME" cat /data/final.json | python3 -c '
import json, sys
d = json.load(sys.stdin)
want = {"success": True, "replay_success": True, "deterministic": True, "live_matches_replay": True, "resumes": 1, "resume_state_mismatch": 0}
bad = {k: d.get(k) for k, v in want.items() if d.get(k) != v}
print(json.dumps({k: d.get(k) for k in ("success", "replay_success", "deterministic", "live_matches_replay", "resumes", "sim_startups", "control_steps", "reason", "live_sha", "replay_sha")}))
print("[kill_test]", "PASS" if not bad else f"FAIL {bad}")
sys.exit(1 if bad else 0)'
