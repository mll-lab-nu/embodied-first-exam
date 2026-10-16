#!/usr/bin/env bash
# Crash-recovery acceptance test for one RoboDojo standard task (docs/STANDARD_MODE.md §13; resume class exact).
# RoboDojo has no oracle, so the test runs a DRIVER (not a solution: 12 joint_position chunks of small arm motions through
# the task's own client) as Harbor's oracle on a copy of the task, kills -9 the sim service in the middle of the episode
# (once N calls are checkpointed, while the next call runs), and checks that the service resumed the same episode exactly
# (state hash = the checkpointed one), the driver carried on, the episode was graded as usual (finalized, no infrastructure
# error), and the live run still equals its fresh-process replay (live_matches_replay, deterministic). The driver
# does not solve the task: the reward's `success` is not part of the check.
#   usage: scripts/robodojo/kill_test.sh [task dir] [jobs dir] [N checkpoints before the kill]
#   default: tasks/robodojo-general-pickup-i00-standard, $PWD/jobs/kill_test, 4
# Needs the eai-robodojo image on the host (images/robodojo/BUILD_ONLY), harbor and docker. Isaac needs 5-8 GB of GPU memory
# and hangs instead of exiting when the GPU runs out of it: run this on a GPU with room for two Isaac processes.
set -uo pipefail
SRC="${1:-tasks/robodojo-general-pickup-i00-standard}"; JOBS="$(mkdir -p "${2:-$PWD/jobs/kill_test}" && cd "${2:-$PWD/jobs/kill_test}" && pwd)"
N="${3:-4}"
D="docker"; docker ps >/dev/null 2>&1 || D="sg docker -c"
dk() { if [ "$D" = docker ]; then docker "$@"; else sg docker -c "docker $(printf '%q ' "$@")"; fi; }
TASK="$(mktemp -d)/$(basename "$SRC")"; cp -r "$SRC" "$TASK"; mkdir -p "$TASK/solution"
cat > "$TASK/solution/solve.sh" <<'SH'
#!/bin/bash
# kill-test driver (not a solution): 12 joint_position chunks of small arm motions through the client
python3 - <<'PY'
import sys, time, numpy as np
sys.path.insert(0, "/opt/tools")
from rcb_client import Robot
r = Robot(timeout=3000)
for k in range(12):
    while True:
        try:
            obs = r.get_obs(); break
        except Exception as e:
            print("waiting for the service:", repr(e)[:120], flush=True); r.wait_ready(); time.sleep(2)
    now = np.asarray(obs.meta["proprio"]["now"])
    a0 = np.concatenate([now[0:6], [1.0], now[7:13], [1.0]])
    A = np.repeat(a0[None], 25, 0); A[:, 1] += 0.15 * np.sin(np.linspace(0, np.pi, 25)) * (1 if k % 2 else -1)
    try:
        res = r.submit("joint_position", A, dt=0.04, video="none")
        print("chunk", k, res.meta.get("control_steps"), flush=True)
    except Exception as e:
        print("chunk", k, "failed:", repr(e)[:120], flush=True); r.wait_ready()
print("status", r.status(), flush=True)
PY
SH
python3 "$(dirname "$0")/../stamp_mtimes.py" --full "$TASK" >/dev/null || exit 1   # Harbor builds from a stamped copy (issue #258)
job="kill-$(basename "$TASK")-$(date +%m%d-%H%M%S)"
echo "[kill_test] $TASK -> $JOBS/$job (kill after $N checkpoints)"
harbor run -y -p "$TASK" -a oracle -o "$JOBS" --job-name "$job" > "$JOBS/$job.harbor.log" 2>&1 &
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
for _ in $(seq 3600); do k="$(count checkpoint)"; [ "${k:-0}" -ge "$N" ] && break; sleep 1; done
sleep 0.5
before="$(dk exec "$c" sh -c 'tail -3 /data/episode.jsonl')"
pid="$(dk exec "$c" cat /data/server.pid | tr -d '\r')"
echo "[kill_test] $(count checkpoint) checkpoints; kill -9 service pid $pid"; echo "$before" | cut -c1-200
dk exec "$c" sh -c "kill -9 $pid"
wait "$hp"; echo "[kill_test] harbor exited $?"
T="$JOBS/$job/$trial"
python3 - "$T" <<'PY'
import json, sys, pathlib
t = pathlib.Path(sys.argv[1])
rw = json.load(open(t / "verifier/reward.json"))
ev = [json.loads(l) for l in open(t / "artifacts/data/episode.jsonl") if l.strip().startswith("{")]
rs = [e for e in ev if e.get("ev") == "resumed"]
ck = sum(1 for e in ev if e.get("ev") == "checkpoint")
n_submit = sum(1 for e in ev if e.get("ev") == "submit")
want = {"finalized": 1, "deterministic": 1, "live_matches_replay": 1, "resumes": 1, "sim_startups": 2, "resume_state_mismatch": 0, "infra_error": 0}
bad = {k: rw.get(k) for k, v in want.items() if rw.get(k) != v}
print(json.dumps({"reward": rw, "resumed": rs, "checkpoints": ck, "submits": n_submit}, indent=1))
# the killed call is answered with an error and rolled back to the last checkpoint; the driver's 11 other chunks all ran
ok = not bad and len(rs) == 1 and rs[0].get("exact") is True and n_submit == 11
print("[kill_test]", "PASS" if ok else f"FAIL {bad} resumed={rs}")
sys.exit(0 if ok else 1)
PY
