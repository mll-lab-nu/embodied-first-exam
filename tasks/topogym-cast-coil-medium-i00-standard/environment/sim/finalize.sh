#!/bin/sh
# [[verifier.collect]] hook, run inside the `sim` sidecar once Harbor has stopped the agent's container.
#   1. `rcb_limited.py end` (the shared first half, docs/rcb/STANDARD_MODE_2_2.md §13.3): SIGUSR1 to the service, which ends
#      the episode, writes trajectory.npz + episode.json (live result, final-state hash, live_rows) and exits, releasing its
#      GPU. It waits through a crash-recovery resume (no PID file until the service is ready again), signals only the newest
#      service process, resends every 30 s, and exits 2 when final.json already holds the verdict (the service gave up after
#      crashes): that verdict stays, nothing is replayed.
#   2. ONE fresh-process replay of the live rows from the frozen instance (replay.py), rendering replay.mp4 during that
#      replay: two passes in all, the live episode and this replay. It runs on the sidecar's GPU after the live service has
#      exited, so it takes the place of the live simulator there (Nyx renders only in a container that sees one GPU: a
#      second GPU in the sidecar segfaults it, 2026-10-01).
#   3. merge everything into final.json, the only thing the verifier sandbox grades. TopoGym's GPU physics is not
#      bit-deterministic: `deterministic` (= live_matches_replay) is reported, not required.
set -u
DATA="${RCB_DATA:-/data}"; TASK="${RCB_TASK:?}"; INSTANCE="${RCB_INSTANCE:?}"
python /srv/rcb_limited.py end "$DATA" --timeout "${RCB_COLLECT_END_TIMEOUT_S:-3600}"; rc=$?
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
echo "[finalize] episode dumped; one fresh-process replay with the video"
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
    python /srv/replay.py --data "$DATA" --task "$TASK" --instance "$INSTANCE" --video "$DATA/replay.mp4" > "$DATA/replay.json" 2> "$DATA/replay.log"
    echo "[finalize] replay exit $?"
else
    echo '{"gpu_lost": true}' > "$DATA/replay.json"
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
out = {"replay_success": None, "deterministic": False, "video": False}
try:
    out.update(json.load(open(os.path.join(d, "episode.json"))))
except Exception as exc:
    out["error"] = f"no episode.json: {exc!r}"
r = last_json("replay.json")
a = (r.get("replays") or [None])[0]
if isinstance(a, dict):                  # a replay result (None: the replay process failed -> grader_error, not the agent's 0)
    out["replay_success"] = bool(a.get("success"))
    out["replay_sha"] = a.get("state_sha"); out["replay_episode_end"] = a.get("episode_end")
    out["deterministic"] = out["live_matches_replay"] = bool(a.get("state_sha")) and a.get("state_sha") == out.get("live_sha")
    out["replay_wall_s"] = r.get("wall_s"); out["instance_exact"] = r.get("instance_exact"); out["instance_matches"] = r.get("instance_matches")
elif r.get("error"):
    out["error"] = f"replay: {r['error']}"
out["video"] = bool(r.get("video")) and os.path.exists(os.path.join(d, "replay.mp4"))
if r.get("gpu_lost"):
    out["gpu_lost"] = True; out["infra_error"] = 1
    out["error"] = "infrastructure: the GPU was not accessible to new processes in the sim sidecar, so the episode could not be replayed"
out["finalized"] = True
json.dump(out, open(os.path.join(d, "final.json"), "w"))
print(json.dumps(out))
PY
