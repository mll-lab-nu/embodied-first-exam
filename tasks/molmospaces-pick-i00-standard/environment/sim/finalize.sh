#!/bin/sh
# [[verifier.collect]] hook, run inside the `sim` sidecar once Harbor has stopped the agent's container. The verdict is
# the live episode's (owner 2026-10-17, board 0150/0151): nothing is replayed to grade it.
#   1. `rcb_limited.py end` (docs/protocol/standard_mode.md §13.3): SIGUSR1 to the service, which ends the episode if the
#      agent had not (reason "timeout"), writes trajectory.npz + episode.json (live verdict, final-state hash) and exits.
#      It exits 2 when final.json already holds the verdict (a give-up: after crashes, or a frozen start that did not
#      rebuild): that verdict stays. Any other non-zero exit with an episode.json the service did dump (it ended the
#      episode, then did not exit in time) still has the live verdict; only without one is it infrastructure.
#   2. merge episode.json into final.json (finalized, graded_by "live", replays 0, video_pending), the only thing the
#      verifier sandbox grades;
#   3. ONE video-only pass renders replay.mp4 from trajectory.npz in a fresh process (`rcb_molmospaces.py replay
#      --video`), after the verdict is on disk: its success and state hash are not read, it is not retried, and a render
#      that fails or runs out of time loses only the video (video false, video_pending false).
# final.json is always written whole and renamed into place (a hook ended mid-write never leaves half a file). The video
# pass gets all the time left before the hook's own deadline (RCB_HOOK_BUDGET_S; task.toml gives the hook 1800 s): a
# render of the whole horizon takes 20-120 s, over 500 s on a loaded host.
set -u
DATA="${RCB_DATA:-/data}"; TOOL="${RCB_TOOL:?}"; INSTANCE="${RCB_INSTANCE:?}"
T0=$(date +%s); HOOK_BUDGET_S="${RCB_HOOK_BUDGET_S:-1740}"   # task.toml's collect timeout_sec (1800) minus a margin
python /srv/rcb_limited.py end "$DATA" --timeout "${RCB_COLLECT_END_TIMEOUT_S:-900}"; rc=$?
if [ "$rc" = 2 ]; then
    echo "[finalize] final.json already holds the verdict (a give-up)"; exit 0
fi
# a late exit's episode.json counts only when the newest service start wrote it (never a stale one from before a crash)
if [ "$rc" != 0 ] && [ -s "$DATA/episode.json" ] && python - <<'PY'
import json, os, sys
d = os.environ.get("RCB_DATA", "/data")
try:
    ep = json.load(open(os.path.join(d, "episode.json")))
    last = json.loads([x for x in open(os.path.join(d, "startups.jsonl")) if x.strip()][-1])
    sys.exit(0 if ep.get("pid") is not None and ep.get("pid") == last.get("pid") else 1)
except Exception:
    sys.exit(1)
PY
then
    echo "[finalize] the service dumped its episode but did not exit in time (rc $rc): final.json from its episode.json"
elif [ "$rc" != 0 ]; then
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
out.update({"finalized": True, "success": False, "live_success": False, "graded_by": "live", "replays": 0, "infra_error": 1,
            "video": False, "video_pending": False,
            "error": "collect hook: the sim service did not end and dump the episode in time"})
with open(p + ".tmp", "w") as f:
    json.dump(out, f)
os.replace(p + ".tmp", p)
print(json.dumps(out))
PY
    exit 0
fi
echo "[finalize] episode dumped; final.json from the live episode (no replay)"
rm -f "$DATA/video.json" "$DATA/video.log"
RCB_END_RC="$rc" python - <<'PY'
import json, os
d = os.environ.get("RCB_DATA", "/data")
out = {"video": False, "video_pending": True, "video_source": None,
       "end_timed_out": os.environ.get("RCB_END_RC", "0") != "0"}   # the service dumped but did not exit in time
try:
    ep = json.load(open(os.path.join(d, "episode.json")))
    if not isinstance(ep, dict):
        raise ValueError("episode.json is not an object")
    out.update(ep)
    out["live_success"] = bool(ep.get("success"))
except Exception as exc:  # the service exited without its live record: no verdict on the agent
    out.update({"success": False, "live_success": False, "infra_error": 1, "video_pending": False,
                "error": f"no episode.json: {exc!r}"})
out.update({"finalized": True, "graded_by": "live", "replays": 0, "state_sha": out.get("live_sha")})
p = os.path.join(d, "final.json")
with open(p + ".tmp", "w") as f:
    json.dump(out, f); f.flush(); os.fsync(f.fileno())
os.replace(p + ".tmp", p)
print(json.dumps(out))
PY
left=$(( T0 + HOOK_BUDGET_S - $(date +%s) ))
if [ "$rc" = 0 ] && [ -s "$DATA/trajectory.npz" ] && [ "$left" -ge 20 ]; then   # not while a late service may still run
    limit=""; command -v timeout > /dev/null 2>&1 && limit="timeout -k 10 $left"
    RCB_SESSION_LOG= $limit python "$TOOL" replay --instance "$INSTANCE" --traj "$DATA/trajectory.npz" --out "$DATA/video.json" \
        --video "$DATA/replay.mp4" > /dev/null 2> "$DATA/video.log"
    echo "[finalize] video pass exit $? (limit $left s; 124 or 137: ended at the limit, no video)"
else
    echo "[finalize] video pass: skipped (no trajectory, or $left s left)"
fi
python - <<'PY'
import json, os
d = os.environ.get("RCB_DATA", "/data")
try:
    shown = bool(json.load(open(os.path.join(d, "video.json"))).get("video"))
except (OSError, ValueError, AttributeError):
    shown = False
p = os.path.join(d, "final.json")   # the verdict is on disk: only the video fields change, in a copy renamed into place
try:
    out = json.load(open(p)); out["video"] = shown and os.path.exists(os.path.join(d, "replay.mp4")); out["video_pending"] = False
    out["video_source"] = "render" if out["video"] else None
    with open(p + ".tmp", "w") as f:
        json.dump(out, f); f.flush(); os.fsync(f.fileno())
    os.replace(p + ".tmp", p)
except (OSError, ValueError, TypeError) as exc:
    print(f"[finalize] video flag not recorded: {exc!r}")
PY
