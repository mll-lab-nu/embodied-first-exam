#!/bin/sh
# [[verifier.collect]] hook, run inside the `sim` sidecar once Harbor has stopped the agent's container.
#   1. `rcb_limited.py end` (the first half every eai-standard/2.2 hook shares): SIGUSR1 to the service process that runs now (it
#      may be resuming after a crash: no PID file until it is ready again); the service ends the episode, commits a stroke still
#      in progress, writes trajectory.npz + episode.json (live canvas hash) and exits. Exit 2: final.json already holds the verdict
#      (the service gave up after crashes): keep it, no replays. Exit 1: the service never dumped the episode (infrastructure).
#   2. replay the trajectory from the frozen instance in TWO fresh processes with the tooling's own `replay` CLI (the privileged
#      verifier's check) and score the replayed canvas; determinism = fresh process == fresh process, `live_matches_replay`
#      compares the live episode with the replay.
#   3. merge everything into final.json, the only thing the verifier sandbox grades. The score is computed only here: the agent
#      never sees it. final.json is always written whole (temporary file + rename): the verifier never reads half of one, and a
#      final.json that is missing or has no verdict is graded as an infrastructure failure, not as the agent's 0.
set -u
DATA="${RCB_DATA:-/data}"; TOOL="${RCB_TOOL:?}"; TASK="${RCB_TASK:?}"; INSTANCE="${RCB_INSTANCE:?}"
python /srv/rcb_limited.py end "$DATA" --timeout 1500; rc=$?
if [ "$rc" = 2 ]; then
    echo "[finalize] final.json already holds the verdict (the service gave up); no replays"; exit 0
fi
if [ "$rc" != 0 ]; then
    echo "[finalize] the service did not dump the episode in time (rc $rc)"
    python - <<'PY'
import json, os
p = os.path.join(os.environ.get("RCB_DATA", "/data"), "final.json")
try:
    out = json.load(open(p))
except Exception:  # noqa: BLE001
    out = {}
out.update({"finalized": True, "replay_success": False, "deterministic": False, "infra_error": 1,
            "error": "infrastructure: the sim service did not end and dump the episode for the collect hook"})
with open(p + ".hook.tmp", "w") as f:
    json.dump(out, f)
os.replace(p + ".hook.tmp", p); print(json.dumps(out))
PY
    exit 0
fi
echo "[finalize] episode dumped; replaying twice in fresh processes"
# A host systemd reload while this long-running container is up (a snap or apt update, with Docker's systemd cgroup driver) makes
# the GPU refuse processes started afterwards. SAPIEN needs a Vulkan device even to build the scene, so the replays cannot run:
# record that as an infrastructure failure (gpu_lost), not the agent's 0.
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
    RCB_SESSION_LOG= python "$TOOL" replay --instance "$INSTANCE" --traj "$DATA/trajectory.npz" --video "$DATA/replay.mp4" --canvas-out "$DATA/canvas.png" > "$DATA/replay1.json" 2> "$DATA/replay1.log"
    echo "[finalize] replay 1 exit $?"
    RCB_SESSION_LOG= RCB_RENDER=0 python "$TOOL" replay --instance "$INSTANCE" --traj "$DATA/trajectory.npz" > "$DATA/replay2.json" 2> "$DATA/replay2.log"
    echo "[finalize] replay 2 exit $?"
else
    echo '{"gpu_lost": true}' > "$DATA/replay1.json"; echo '{"gpu_lost": true}' > "$DATA/replay2.json"
fi
python - <<'PY'
import json, os
d = os.environ.get("RCB_DATA", "/data"); inst = json.load(open(os.environ["RCB_INSTANCE"]))
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
out["success_rule"] = {k: float(v) for k, v in inst["target"]["success"].items()}
out["replay_success"] = bool(a.get("success")) and bool(b.get("success"))   # rcb_brush.is_success on each replayed main sheet
out["replay_sha"], out["replay_sha2"] = a.get("state_sha"), b.get("state_sha")
out["deterministic"] = bool(a.get("state_sha")) and a.get("state_sha") == b.get("state_sha")
out["live_matches_replay"] = bool(a.get("state_sha")) and a.get("state_sha") == out.get("live_sha")
out["instance_exact"] = bool(r1.get("instance_exact")) and bool(r2.get("instance_exact"))
out["replay_error"] = not (a and b)
out["metrics"] = {k: v for k, v in a.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}
out["video"] = os.path.exists(os.path.join(d, "replay.mp4"))
if r1.get("gpu_lost"):
    out["gpu_lost"] = True
    out["error"] = "infrastructure: the GPU was not accessible to new processes in the sim sidecar, so the episode could not be replayed"
out["finalized"] = True
p = os.path.join(d, "final.json")
with open(p + ".hook.tmp", "w") as f:
    json.dump(out, f)
os.replace(p + ".hook.tmp", p)
print(json.dumps(out))
PY
