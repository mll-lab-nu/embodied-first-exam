#!/usr/bin/env bash
# Crash-recovery acceptance test for one Panda Dynamic Scenes standard task (the shared service layer, rcb_service.py;
# since board 0153): run the task's oracle with Harbor, kill -9 the sim service in the middle of the episode (once N
# submit calls are checkpointed, while the next call runs), and check that the service resumed the same episode (its
# journal replayed to the logged state hash, else it gives up: resume_failed), the oracle carried on, and the last
# episode was graded as usual (live) with its resets and a video.
#   usage: scripts/pandadyn/kill_test.sh [task dir] [jobs dir] [N checkpoints before the kill]
#   default: tasks/pandadyn-s02-plate-catch-transport-release-i00-standard, $PWD/jobs/kill_test, 4
# Needs the eai-pandadyn image on the host (images/pandadyn/), harbor and docker.
set -uo pipefail
TASK="${1:-tasks/pandadyn-s02-plate-catch-transport-release-i00-standard}"; JOBS="$(mkdir -p "${2:-$PWD/jobs/kill_test}" && cd "${2:-$PWD/jobs/kill_test}" && pwd)"
TASK="$(python3 "$(dirname "$0")/../stamp_mtimes.py" stage "$TASK" "$(mktemp -d)")" || exit 1   # Harbor builds from a stamped copy (issue #258)
N="${3:-4}"
D="docker"; docker ps >/dev/null 2>&1 || D="sg docker -c"
dk() { if [ "$D" = docker ]; then docker "$@"; else sg docker -c "docker $(printf '%q ' "$@")"; fi; }
job="kill-$(basename "$TASK")-$(date +%m%d-%H%M%S)"
echo "[kill_test] $TASK -> $JOBS/$job (kill after $N checkpoints)"
harbor run -p "$TASK" -a oracle -y -o "$JOBS" --job-name "$job" > "$JOBS/$job.harbor.log" 2>&1 &
hp=$!
trial=""; for _ in $(seq 600); do trial="$(ls -d "$JOBS/$job"/*__* 2>/dev/null | head -1)"; [ -n "$trial" ] && break; sleep 2; done
[ -n "$trial" ] || { echo "[kill_test] no trial dir"; exit 1; }
trial="$(basename "$trial")"
proj="$(python3 -c 'import re,sys; n=(sys.argv[1]+"__env").lower(); n=n if re.match("^[a-z0-9]",n) else "0"+n; print(re.sub(r"[^a-z0-9_-]","-",n))' "$trial")"
c=""; for _ in $(seq 900); do
  c="$(dk ps -q --filter "label=com.docker.compose.project=$proj" --filter "label=com.docker.compose.service=sim" | head -1)"; [ -n "$c" ] && break; sleep 2
done
[ -n "$c" ] || { echo "[kill_test] no sim container for project $proj"; exit 1; }
echo "[kill_test] trial $trial, sim container $c"
count() { dk exec "$c" sh -c "grep -c '\"ev\": \"$1\"' /data/episode.jsonl 2>/dev/null || true" | tr -d '\r'; }
for _ in $(seq 3600); do k="$(count submit)"; [ "${k:-0}" -ge "$N" ] && break; sleep 1; done
sleep 0.5
before="$(dk exec "$c" sh -c 'tail -3 /data/episode.jsonl')"
pid="$(dk exec "$c" cat /data/server.pid | tr -d '\r')"
echo "[kill_test] $(count submit) submit checkpoints; kill -9 service pid $pid"; echo "$before" | cut -c1-200
dk exec "$c" sh -c "kill -9 $pid"
wait "$hp"; echo "[kill_test] harbor exited $?"
T="$JOBS/$job/$trial"
python3 - "$T" <<'PY'
import json, sys, pathlib
t = pathlib.Path(sys.argv[1])
rw = json.load(open(t / "verifier/reward.json"))
ev = [json.loads(l) for l in open(t / "artifacts/data/episode.jsonl") if l.strip().startswith("{")]
rs = [e for e in ev if e.get("ev") == "resumed"]
ck = sum(1 for e in ev if e.get("ev") == "submit")
want = {"success": 1, "graded_by_live": 1, "replays": 0, "video_rendered": 1, "sim_startups": 2, "infra_error": 0,
        "resets": rw.get("reset_budget")}
bad = {k: rw.get(k) for k, v in want.items() if rw.get(k) != v}
print(json.dumps({"reward": rw, "resumed": rs, "submit_checkpoints": ck}, indent=1))
ok = not bad and len(rs) == 1
print("[kill_test]", "PASS" if ok else f"FAIL {bad} resumed={rs}")
sys.exit(0 if ok else 1)
PY
