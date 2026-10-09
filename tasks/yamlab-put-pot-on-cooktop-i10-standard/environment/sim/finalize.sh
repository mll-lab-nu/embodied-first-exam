#!/bin/sh
# [[verifier.collect]] hook, run inside the `sim` sidecar once Harbor has stopped the agent's container.
#   1. `rcb_limited.py end` (the shared first half, docs/STANDARD_MODE_2_2.md §13.3): SIGUSR1 to the service, which ends
#      the episode, writes trajectory.npz + episode.json (live result, final-state hash) and exits, releasing the
#      simulator. It waits through a crash-recovery resume (no PID file until the service is ready again), signals only
#      the newest service process, resends every 30 s, and exits 2 when final.json already holds the verdict (the
#      service gave up after crashes): that verdict stays, nothing is replayed.
#   2. replay the trajectory from the frozen instance in TWO fresh processes with the tooling's own `replay` CLI (the
#      privileged verifier's check): on Isaac only the first replay in a process is bit-exact, so determinism is fresh
#      process == fresh process; `live_matches_replay` reports live == replay separately.
#   3. merge everything into final.json, the only thing the verifier sandbox grades.
set -u
DATA="${RCB_DATA:-/data}"; TOOL="${RCB_TOOL:?}"; TASK="${RCB_TASK:?}"; INSTANCE="${RCB_INSTANCE:?}"
# A resume replays the whole episode first (~15-20 control steps/s); the two replays below need as long again each.
python /srv/rcb_limited.py end "$DATA" --timeout "${RCB_COLLECT_END_TIMEOUT_S:-2700}"; rc=$?
if [ "$rc" = 2 ]; then
    echo "[finalize] final.json already holds the verdict; no replay"; exit 0
fi
if [ "$rc" != 0 ]; then
    echo "[finalize] the service did not end and dump the episode in time (rc $rc): an infrastructure failure"
    python - <<'PY'
import json, os
d = os.environ.get("RCB_DATA", "/data"); p = os.path.join(d, "final.json")
try:
    out = json.load(open(p))
except Exception:
    out = {}
out.update({"finalized": True, "success": False, "replay_success": False, "deterministic": False, "infra_error": 1,
            "error": "collect hook: the sim service did not end and dump the episode in time"})
json.dump(out, open(p, "w"))
print(json.dumps(out))
PY
    exit 0
fi
echo "[finalize] episode dumped; replaying twice in fresh processes"
# A host systemd reload while this long-running container is up (a snap or apt update, with Docker's systemd cgroup
# driver) makes the GPU refuse processes started afterwards: record that as an infrastructure failure, not the agent's 0.
if python - <<'PY'
import os, sys
for dev in ("/dev/nvidiactl", "/dev/nvidia0"):
    if os.path.exists(dev):
        try:
            open(dev, "rb").close()
        except OSError as exc:
            print(f"[finalize] cannot open {dev}: {exc}", file=sys.stderr); sys.exit(1)
PY
then
    RCB_SESSION_LOG= python "$TOOL" replay --task "$TASK" --instance "$INSTANCE" --traj "$DATA/trajectory.npz" --video "$DATA/replay.mp4" > "$DATA/replay1.json" 2> "$DATA/replay1.log"
    echo "[finalize] replay 1 exit $?"
    RCB_SESSION_LOG= python "$TOOL" replay --task "$TASK" --instance "$INSTANCE" --traj "$DATA/trajectory.npz" > "$DATA/replay2.json" 2> "$DATA/replay2.log"
    echo "[finalize] replay 2 exit $?"
else
    echo '{"gpu_lost": true}' > "$DATA/replay1.json"; echo '{"gpu_lost": true}' > "$DATA/replay2.json"
fi
python - <<'PY'
import json, os
d = os.environ.get("RCB_DATA", "/data")
def last_json(name):
    out = {}
    try:
        for line in open(os.path.join(d, name)):
            if line.strip().startswith("{"): out = json.loads(line)
    except Exception:
        pass
    return out
out = {"finalized": True, "replay_success": False, "deterministic": False, "video": False}
try:
    out.update(json.load(open(os.path.join(d, "episode.json"))))
except Exception as exc:
    out["error"] = f"no episode.json: {exc!r}"
r1, r2 = last_json("replay1.json"), last_json("replay2.json")
a, b = (r1.get("replays") or [{}])[0], (r2.get("replays") or [{}])[0]
out["replay_success"] = bool(a.get("success")) and bool(b.get("success"))
out["replay_sha"], out["replay_sha2"] = a.get("state_sha"), b.get("state_sha")
out["deterministic"] = bool(a.get("state_sha")) and a.get("state_sha") == b.get("state_sha")
out["live_matches_replay"] = bool(a.get("state_sha")) and a.get("state_sha") == out.get("live_sha")
out["video"] = os.path.exists(os.path.join(d, "replay.mp4"))
if r1.get("gpu_lost"):
    out["gpu_lost"] = True; out["infra_error"] = 1
    out["error"] = "infrastructure: the GPU was not accessible to new processes in the sim sidecar, so the episode could not be replayed"
out["finalized"] = True
json.dump(out, open(os.path.join(d, "final.json"), "w"))
print(json.dumps(out))
PY
