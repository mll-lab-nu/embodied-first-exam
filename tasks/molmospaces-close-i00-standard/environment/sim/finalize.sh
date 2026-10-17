#!/bin/sh
# [[verifier.collect]] hook, run inside the `sim` sidecar once Harbor has stopped the agent's container.
#   1. `rcb_limited.py end` (docs/STANDARD_MODE.md §13.3): SIGUSR1 to the service, which ends the episode if the
#      agent had not (reason "timeout"), writes trajectory.npz + episode.json (live verdict, final-state hash) and exits.
#      It exits 2 when final.json already holds the verdict (the service gave up after crashes): that verdict stays.
#   2. replay the trajectory from the frozen instance in TWO fresh processes (`rcb_molmospaces.py replay`, the privileged
#      verifier's replay): determinism = fresh process == fresh process; live_matches_replay = live == replay.
#   3. merge everything into final.json, the only thing the verifier sandbox grades;
#   4. a third replay renders replay.mp4, after the verdict is on disk (it never changes it).
# final.json is always written whole and renamed into place (a hook ended mid-write never leaves half a file). A replay
# that takes longer than its limit is ended (a replay takes 20-120 s, over 500 s on a loaded host; replay 1 gets half
# the time left before this hook's own deadline, replay 2 and the video replay what is left then: task.toml gives the
# hook 1800 s): it then has no result, which is recorded as replay_failed + infra_error, not as the agent's 0, in a
# finalized final.json.
set -u
DATA="${RCB_DATA:-/data}"; TOOL="${RCB_TOOL:?}"; INSTANCE="${RCB_INSTANCE:?}"
T0=$(date +%s); HOOK_BUDGET_S="${RCB_HOOK_BUDGET_S:-1740}"   # task.toml's collect timeout_sec (1800) minus a margin
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
if not isinstance(out, dict):
    out = {}
out.update({"finalized": True, "success": False, "replay_success": False, "deterministic": False, "infra_error": 1,
            "error": "collect hook: the sim service did not end and dump the episode in time"})
with open(p + ".tmp", "w") as f:
    json.dump(out, f)
os.replace(p + ".tmp", p)
print(json.dumps(out))
PY
    exit 0
fi
replay() {  # <n> <k> [--video FILE]: one replay in a fresh process, its result in $DATA/replay<n>.json; limit: 1/k of
    n=$1; k=$2; shift 2   # the time left before the hook's deadline (k = the replays still to grade, so they share it)
    left=$(( (T0 + HOOK_BUDGET_S - $(date +%s)) / k ))
    if [ "$left" -lt 20 ]; then
        echo "[finalize] replay $n: no time left before the hook's deadline"; return
    fi
    limit=""; command -v timeout > /dev/null 2>&1 && limit="timeout -k 10 $left"
    RCB_SESSION_LOG= $limit python "$TOOL" replay --instance "$INSTANCE" --traj "$DATA/trajectory.npz" --out "$DATA/replay$n.json" \
        "$@" > /dev/null 2> "$DATA/replay$n.log"
    echo "[finalize] replay $n exit $? (limit $left s; 124 or 137: ended at the limit, no result)"
}
echo "[finalize] episode dumped; replaying twice in fresh processes"
rm -f "$DATA/replay1.json" "$DATA/replay2.json" "$DATA/replay3.json" "$DATA/replay1.log" "$DATA/replay2.log" "$DATA/replay3.log"
replay 1 2
# no second replay once the first gave no result (the verdict is replay_failed + infra_error anyway): the time goes to the video
if [ -s "$DATA/replay1.json" ]; then replay 2 1; else echo "[finalize] replay 2: skipped, replay 1 gave no result"; fi
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
if not (a.get("state_sha") and b.get("state_sha")):  # a replay process died (e.g. the GPU ran out of memory): not the agent's 0
    out.update({"replay_failed": 1, "infra_error": 1,
                "error": "a replay process gave no result (replay1.log / replay2.log)"})
elif not (a.get("instance_ok") and b.get("instance_ok")):  # the image no longer builds the frozen start: not the agent's 0
    out.update({"instance_mismatch": 1, "infra_error": 1, "error": "a replay did not start in the instance's t = 0 state"})
out["finalized"] = True
p = os.path.join(d, "final.json")
with open(p + ".tmp", "w") as f:
    json.dump(out, f); f.flush(); os.fsync(f.fileno())
os.replace(p + ".tmp", p)
print(json.dumps(out))
PY
replay 3 1 --video "$DATA/replay.mp4"
python - <<'PY'
import json, os
d = os.environ.get("RCB_DATA", "/data")
try:
    shown = json.load(open(os.path.join(d, "replay3.json"))).get("video")
except (OSError, ValueError):
    shown = False
if shown:   # the verdict is on disk: only `video` is added, in a copy renamed into place (never a half-written final.json)
    p = os.path.join(d, "final.json")
    try:
        out = json.load(open(p)); out["video"] = True
        with open(p + ".tmp", "w") as f:
            json.dump(out, f); f.flush(); os.fsync(f.fileno())
        os.replace(p + ".tmp", p)
    except (OSError, ValueError, TypeError) as exc:
        print(f"[finalize] video flag not recorded: {exc!r}")
PY
