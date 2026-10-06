#!/bin/sh
# [[verifier.collect]] hook, run inside the `sim` sidecar once Harbor has stopped the agent's container.
#   1. `rcb_limited.py end` (docs/STANDARD_MODE_2_2.md §13.3): SIGUSR1 to the service, which ends the episode if the
#      agent had not (reason "timeout"), writes trajectory.npz + episode.json (live verdict, final-state hash) and exits.
#      It exits 2 when final.json already holds the verdict (the service gave up after crashes): that verdict stays.
#   2. replay the trajectory from the frozen instance in TWO fresh processes (`rcb_myosuite.py replay`, the privileged
#      verifier's replay): determinism = fresh process == fresh process; live_matches_replay = live == replay.
#   3. merge everything into final.json, the only thing the verifier sandbox grades;
#   4. a third replay renders replay.mp4, after the verdict is on disk (it never changes it).
set -u
DATA="${RCB_DATA:-/data}"; TOOL="${RCB_TOOL:-/srv/rcb_myosuite.py}"; INSTANCE="${RCB_INSTANCE:-/srv/instance.npz}"
python /srv/rcb_limited.py end "$DATA" --timeout "${RCB_COLLECT_END_TIMEOUT_S:-900}"; rc=$?
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
replay() {  # <n> [--video FILE]: one replay in a fresh process, its result in $DATA/replay<n>.json
    n=$1; shift
    RCB_SESSION_LOG= python "$TOOL" replay --instance "$INSTANCE" --traj "$DATA/trajectory.npz" --out "$DATA/replay$n.json" \
        "$@" > /dev/null 2> "$DATA/replay$n.log"
    echo "[finalize] replay $n exit $?"
}
echo "[finalize] episode dumped; replaying twice in fresh processes"
rm -f "$DATA/replay1.json" "$DATA/replay2.json" "$DATA/replay3.json"
replay 1
replay 2
python - <<'PY'
import json, os
d = os.environ.get("RCB_DATA", "/data")
def result(name):
    try:
        v = json.load(open(os.path.join(d, name)))
    except (OSError, ValueError):
        return {}
    return v if isinstance(v, dict) else {}
out = {"replay_success": False, "deterministic": False, "video": False}
try:
    out.update(json.load(open(os.path.join(d, "episode.json"))))
except Exception as exc:
    out["error"] = f"no episode.json: {exc!r}"
a, b = result("replay1.json"), result("replay2.json")
out["replay_success"] = bool(a.get("success")) and bool(b.get("success"))
out["replay_sha"], out["replay_sha2"] = a.get("state_sha"), b.get("state_sha")
out["deterministic"] = bool(a.get("state_sha")) and a.get("state_sha") == b.get("state_sha")
out["live_matches_replay"] = bool(a.get("state_sha")) and a.get("state_sha") == out.get("live_sha")
if not (a.get("state_sha") and b.get("state_sha")):  # a replay process died (it crashed or timed out): not the agent's 0
    out.update({"replay_failed": 1, "infra_error": 1,
                "error": "a replay process gave no result (replay1.log / replay2.log)"})
elif not (a.get("instance_ok") and b.get("instance_ok")):  # the image no longer builds the frozen start: not the agent's 0
    out.update({"instance_mismatch": 1, "infra_error": 1, "error": "a replay did not start in the instance's t = 0 state"})
out["finalized"] = True
json.dump(out, open(os.path.join(d, "final.json"), "w"))
print(json.dumps(out))
PY
replay 3 --video "$DATA/replay.mp4"
python - <<'PY'
import json, os
d = os.environ.get("RCB_DATA", "/data")
try:
    shown = json.load(open(os.path.join(d, "replay3.json"))).get("video")
except (OSError, ValueError):
    shown = False
if shown:
    p = os.path.join(d, "final.json"); out = json.load(open(p)); out["video"] = True; json.dump(out, open(p, "w"))
PY
