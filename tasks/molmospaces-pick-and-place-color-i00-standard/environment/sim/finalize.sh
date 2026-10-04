#!/bin/sh
# [[verifier.collect]] hook, run inside the `sim` sidecar once Harbor has stopped the agent's container.
#   1. `rcb_limited.py end` (docs/STANDARD_MODE_2_2.md §13.3): SIGUSR1 to the service, which ends the episode if the
#      agent had not (reason "timeout"), writes trajectory.npz + episode.json (live verdict, final-state hash) and exits.
#      It exits 2 when final.json already holds the verdict (the service gave up after crashes): that verdict stays.
#   2. replay the trajectory from the frozen instance in TWO fresh processes (`rcb_molmospaces.py replay`, the privileged
#      verifier's replay): determinism = fresh process == fresh process; live_matches_replay = live == replay.
#   3. merge everything into final.json, the only thing the verifier sandbox grades.
set -u
DATA="${RCB_DATA:-/data}"; TOOL="${RCB_TOOL:?}"; INSTANCE="${RCB_INSTANCE:?}"
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
echo "[finalize] episode dumped; replaying twice in fresh processes"
RCB_SESSION_LOG= python "$TOOL" replay --instance "$INSTANCE" --traj "$DATA/trajectory.npz" --video "$DATA/replay.mp4" > "$DATA/replay1.json" 2> "$DATA/replay1.log"
echo "[finalize] replay 1 exit $?"
RCB_SESSION_LOG= python "$TOOL" replay --instance "$INSTANCE" --traj "$DATA/trajectory.npz" > "$DATA/replay2.json" 2> "$DATA/replay2.log"
echo "[finalize] replay 2 exit $?"
python - <<'PY'
import json, os
d = os.environ.get("RCB_DATA", "/data")
def last_json(name):
    """The replay's result: the last stdout line that is a JSON object (upstream prints other text, a multi-line JSON
    block included, e.g. its pinned asset versions)."""
    out = {}
    try:
        lines = open(os.path.join(d, name)).read().splitlines()
    except OSError:
        return out
    for line in lines:
        try:
            v = json.loads(line)
        except ValueError:
            continue
        out = v if isinstance(v, dict) else out
    return out
out = {"replay_success": False, "deterministic": False, "video": False}
try:
    out.update(json.load(open(os.path.join(d, "episode.json"))))
except Exception as exc:
    out["error"] = f"no episode.json: {exc!r}"
a, b = last_json("replay1.json"), last_json("replay2.json")
out["replay_success"] = bool(a.get("success")) and bool(b.get("success"))
out["replay_sha"], out["replay_sha2"] = a.get("state_sha"), b.get("state_sha")
out["deterministic"] = bool(a.get("state_sha")) and a.get("state_sha") == b.get("state_sha")
out["live_matches_replay"] = bool(a.get("state_sha")) and a.get("state_sha") == out.get("live_sha")
if not (a.get("state_sha") and b.get("state_sha")):  # a replay process died (e.g. the GPU ran out of memory): not the agent's 0
    out.update({"replay_failed": 1, "infra_error": 1,
                "error": "a replay process gave no result (replay1.log / replay2.log)"})
out["video"] = os.path.exists(os.path.join(d, "replay.mp4"))
out["finalized"] = True
json.dump(out, open(os.path.join(d, "final.json"), "w"))
print(json.dumps(out))
PY
