#!/usr/bin/env bash
# End-to-end check of one AutoBio standard task on the CPU, without Harbor (scripts/autobio/kill_test.sh plus):
#  1. malformed requests over raw HTTP -> 400 each, nothing executed, the episode still open;
#  2. the reference rows through the client with a kill -9 of the service half way (resume), `done`;
#  3. the service's own unfinalized final.json through tests/grade.py -> infra_error 1 (no verdict yet);
#  4. the collect hook (finalize.sh: limited replays, atomic final.json), then tests/grade.py -> reward 1.
set -euo pipefail
ROOT=$1; TASK=$(cd "${2:-$ROOT/tasks/autobio-pickup-i00-standard}" && pwd); OUT=$3; mkdir -p "$OUT"
IMAGE=$(awk '$1 == "image:" {print $2; exit}' "$TASK/environment/docker-compose.yaml")
NAME="rcb-autobio-e2e-s2-$$"
trap 'docker rm -f "$NAME" >/dev/null 2>&1 || true' EXIT
docker run -d --name "$NAME" --restart on-failure:6 --cpus 4 -w /tmp \
   -v "$TASK/environment/sim:/srv:ro" -v "$ROOT/scripts/eai_standard:/client:ro" -v "$TASK/solution:/solution:ro" \
   -e RCB_INSTANCE=/srv/instance.json -e RCB_TOOL=/srv/rcb_autobio.py -e RCB_DATA=/data -e PYTHONPATH=/srv \
   -e RCB_SESSION_LOG= "$IMAGE" sh /srv/run.sh >/dev/null
docker exec "$NAME" pip install -q --no-cache-dir requests >/dev/null 2>&1 || true
until docker exec "$NAME" test -f /data/server.pid 2>/dev/null; do sleep 2; done
echo "[e2e] service ready"
docker exec -i "$NAME" python - <<'PY'
import json, requests
U = "http://localhost:8000"
row = [[0.0] * 7]
bad_submit = [{"dt": None, "note": 5}, {"dt": "0.002"}, {"dt": [0.002]}, {"dt": 1e999}, {"dt": 0.003}, {"video_fps": 0}, {"video_fps": None, "cameras": 5},
              {"cameras": "wrist_cam"}, {"note": {"a": 1}}, {"note": 7}, {"interpolate": None}, {"video": []}, {"depth": {"x": 1}}, {"type": None},
              {"type": ["joint_position"]}, {"type": "done", "cameras": 3}, {"type": "done", "note": 9}, {"actions": [[0.0] * 6]}, {"actions": [[float("nan")] * 7]}]
bad_observe = [{"seconds": None, "cameras": 5}, {"seconds": "1"}, {"seconds": [1]}, {"seconds": -1}, {"seconds": 1e999}, {"seconds": 31}, {"video_fps": -3},
               {"video": 5}, {"depth": 9}, {"note": 5, "seconds": float("nan")}]
errs = []
for b in bad_submit:
    body = {"type": "joint_position", "actions": row, "video": "none", **b}
    r = requests.post(U + "/submit", data=json.dumps(body), timeout=120)   # json.dumps writes NaN / Infinity as Python's json reads them
    if r.status_code != 400: errs.append(("submit", b, r.status_code, r.text[:120]))
for b in bad_observe:
    r = requests.post(U + "/observe", data=json.dumps({"video": "none", **b}), timeout=120)
    if r.status_code != 400: errs.append(("observe", b, r.status_code, r.text[:120]))
st = requests.get(U + "/status").json()
ok = requests.post(U + "/observe", data=json.dumps({"seconds": None, "video": "none"}), timeout=120)   # null = the default: still a 200
print("[e2e] malformed requests:", len(bad_submit) + len(bad_observe), "sent; not 400:", errs, "| status after:", st, "| observe(seconds=null):", ok.status_code)
assert not errs and st["control_steps"] == 0 and not st["done"] and ok.status_code == 200, "malformed requests must be 400 and execute nothing"
PY
drive() {
  docker exec -i "$NAME" env PYTHONPATH=/client python - "$1" <<'PY'
import sys, numpy as np
from rcb_client import EpisodeOver, Robot
A = np.load("/solution/oracle.npz")["actions"].astype(np.float64)
r = Robot("http://localhost:8000"); st = r.wait_ready()
i = int(st["control_steps"]); stop = len(A) // 2 if sys.argv[1] == "first" else len(A)
while i < stop and not st.get("done"):
    try:
        res = r.submit("joint_position", A[i:min(i + 1000, stop)], dt=0.002, interpolate="hold", video="none", note="e2e")
    except EpisodeOver:
        break
    i = int(res.meta["control_steps"])
    if res.meta["done"]:
        break
if sys.argv[1] == "rest" and not r.status()["done"]:
    r.submit("done", [])
print(r.status())
PY
}
echo "[e2e] first half: $(drive first)"
pid=$(docker exec "$NAME" cat /data/server.pid); restarts=$(docker inspect -f '{{.RestartCount}}' "$NAME")
docker exec "$NAME" sh -c "kill -9 $pid"
until [ "$(docker inspect -f '{{.RestartCount}}' "$NAME")" -gt "$restarts" ] && docker exec "$NAME" test -f /data/server.pid 2>/dev/null; do sleep 2; done
echo "[e2e] rest:       $(drive rest)"
grade() {  # <label>: tests/grade.py on a copy of /data, in the verifier's base image
  rm -rf "$OUT/$1"; mkdir -p "$OUT/$1/data" "$OUT/$1/log"
  for f in final.json trajectory.npz episode.jsonl replay.mp4; do docker cp "$NAME:/data/$f" "$OUT/$1/data/$f" >/dev/null 2>&1 || true; done
  RCB_DATA="$OUT/$1/data" RCB_VERIFIER_LOG_DIR="$OUT/$1/log" python3 -B "$TASK/tests/grade.py" > /dev/null
  echo "[e2e] grade ($1): reward $(cat "$OUT/$1/log/reward.txt") $(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print({k: d.get(k) for k in ("success","live_success","replay_success","deterministic","finalized","no_verdict","infra_error","grader_error","replay_failed","resumes","agent_done","sim_steps","video_rendered")})' "$OUT/$1/log/reward.json")"
}
grade before_hook
t0=$(date +%s); docker exec "$NAME" sh /srv/finalize.sh | grep "^\[finalize\]" || true; echo "[e2e] collect hook took $(( $(date +%s) - t0 )) s"
docker exec "$NAME" sh -c 'ls /data; cat /data/replay1.rc /data/replay2.rc /data/replay3.rc'
grade after_hook
python3 - "$OUT" <<'PY'
import json, sys
o = sys.argv[1]
b = json.load(open(f"{o}/before_hook/log/reward.json")); a = json.load(open(f"{o}/after_hook/log/reward.json")); f = json.load(open(f"{o}/after_hook/data/final.json"))
ok = (b["success"], b["infra_error"], b["no_verdict"]) == (0, 1, 1) and (a["success"], a["infra_error"], a["grader_error"], a["deterministic"], a["resumes"]) == (1, 0, 0, 1, 1) \
     and f.get("replay_rc") == [0, 0] and f.get("live_matches_replay") is True and f.get("video") is True
print("[e2e]", "PASS" if ok else "FAIL", {k: f.get(k) for k in ("success", "replay_success", "deterministic", "live_matches_replay", "replay_rc", "video", "resumes", "reason", "control_steps")})
sys.exit(0 if ok else 1)
PY
