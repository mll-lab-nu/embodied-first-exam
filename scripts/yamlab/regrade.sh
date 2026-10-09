#!/usr/bin/env bash
# Re-grade a finished YAMLab trial with the CURRENT version of its task, in fresh processes (PROTOCOL §2.7, the review's
# determinism check). Run it on the host the trial ran on: CPU PhysX is bit-exact on one host, not necessarily across hosts.
#   privileged: the task's own verifier (tests/test.sh: tests/grade.py --repeat 2, two fresh-process replays) on the
#               trial's /app/output/ -> <out>/reward.json
#   standard:   the sim tooling's replay CLI twice (two fresh processes) on the episode the service recorded
#               (artifacts/data/trajectory.npz) -> <out>/regrade.json: both succeed, both end in the same state, and
#               that state is the recorded live one (live_sha in artifacts/data/final.json)
#   usage: scripts/yamlab/regrade.sh <task dir> <trial dir> <out dir>
#   env: RCB_GPUS (docker --gpus value, default all); RCB_NETWORK (docker --network, e.g. none: grade offline)
set -euo pipefail
TASK="$(cd "$1" && pwd)"; TRIAL="$(cd "$2" && pwd)"; mkdir -p "$3"; OUT="$(cd "$3" && pwd)"
IMG="$(sed -n 's/^FROM //p' "$TASK/tests/Dockerfile" | head -1)"
case "$(basename "$TASK")" in *-standard) MODE=standard; IMG="$(sed -n 's/^ *image: //p' "$TASK/environment/docker-compose.yaml" | head -1)";; *) MODE=privileged;; esac
FAM="$(sed -n 's/^family = "\(.*\)"$/\1/p' "$TASK/task.toml" | head -1)"
run() { if docker ps >/dev/null 2>&1; then docker "$@"; else sg docker -c "docker $(printf '%q ' "$@")"; fi; }
echo "[regrade] $MODE $FAM: $(basename "$TRIAL") on $IMG -> $OUT"
if [ "$MODE" = privileged ]; then
  [ -f "$TRIAL/artifacts/app/output/trajectory.npz" ] || { echo "[regrade] no artifacts/app/output/trajectory.npz"; exit 1; }
  run run --rm --gpus "${RCB_GPUS:-all}" --network "${RCB_NETWORK:-bridge}" --shm-size 8g -e PYTHONPATH=/tests -w /tests -v "$TASK/tests:/tests:ro" \
    -v "$TRIAL/artifacts/app/output:/app/output:ro" -v "$OUT:/logs/verifier" "$IMG" bash -c "bash /tests/test.sh; chown -R $(id -u):$(id -g) /logs/verifier"
  cat "$OUT/reward.json"; echo
else
  D="$TRIAL/artifacts/data"; [ -f "$D/trajectory.npz" ] || { echo "[regrade] no artifacts/data/trajectory.npz"; exit 1; }
  run run --rm --gpus "${RCB_GPUS:-all}" --network "${RCB_NETWORK:-bridge}" --shm-size 8g -e RCB_SESSION_LOG= -e PYTHONPATH=/srv -w /tmp -v "$TASK/environment/sim:/srv:ro" \
    -v "$D:/old:ro" -v "$OUT:/out" "$IMG" bash -c "for i in 1 2; do python /srv/rcb_yamlab.py replay --task $FAM --instance /srv/instance.json \
      --traj /old/trajectory.npz > /out/replay\$i.json 2> /out/replay\$i.log; done; chown -R $(id -u):$(id -g) /out"
  python3 - "$D/final.json" "$OUT" <<'PY'
import json, sys
fin = json.load(open(sys.argv[1])); out = sys.argv[2]
def last(p):
    r = {}
    for line in open(p):
        if line.strip().startswith("{"): r = json.loads(line)
    return (r.get("replays") or [{}])[0]
a, b = last(f"{out}/replay1.json"), last(f"{out}/replay2.json")
res = {"success": int(bool(a.get("success")) and bool(b.get("success"))), "deterministic": int(bool(a.get("state_sha")) and a.get("state_sha") == b.get("state_sha")),
       "matches_recorded_live": int(a.get("state_sha") == fin.get("live_sha")), "matches_recorded_replay": int(a.get("state_sha") == fin.get("replay_sha")),
       "state_sha": a.get("state_sha"), "recorded_live_sha": fin.get("live_sha"), "n_actions": fin.get("n_actions")}
json.dump(res, open(f"{out}/regrade.json", "w")); print(json.dumps(res))
PY
fi
