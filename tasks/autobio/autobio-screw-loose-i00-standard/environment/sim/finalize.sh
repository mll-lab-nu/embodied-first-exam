#!/bin/sh
# [[verifier.collect]] hook, run inside the `sim` sidecar once Harbor has stopped the agent's container. The trial is
# graded by its LIVE episode, the one the agent ran, with no grading replay (docs/protocol/invariants.md H.4).
#   1. `rcb_limited.py end` (embodied_first_exam/standard/README.md#what-a-shared-layer-task-declares): SIGUSR1 to the service, which ends the episode if the
#      agent had not (reason "timeout"), writes trajectory.npz + episode.json (the live verdict, the end-state hash) and
#      exits. It exits 2 when final.json already holds the verdict (the service gave up after crashes): that verdict stays.
#   2. final.json = the live record (episode.json) + `graded_by` "live", `replays` 0, `finalized`: written whole (a
#      temporary file + rename) BEFORE the video, with `video_pending` true, so nothing the video does can change or
#      delay the verdict. A live episode that did not start in the instance's recorded state (`instance_ok_live` false)
#      is an infrastructure failure, not the agent's 0.
#   3. the video: one replay of the recorded trajectory from the frozen instance (`rcb_autobio.py replay --video`), after the
#      verdict is on disk; a failed or slow replay costs the video only (`video` false), never the verdict.
set -u
DATA="${RCB_DATA:-/data}"; TOOL="${RCB_TOOL:-/srv/rcb_autobio.py}"; INSTANCE="${RCB_INSTANCE:-/srv/instance.json}"
# Time. The hook has HOOK_BUDGET_S (its [[verifier.collect]] timeout_sec in task.toml; keep the two equal):
#   3000 s = 900 (the end of the episode, through a resume) + the video replay (at most 1800 s) + 300 s of margin.
HOOK_BUDGET_S="${RCB_COLLECT_BUDGET_S:-3000}"; VIDEO_TIMEOUT_S="${RCB_VIDEO_TIMEOUT_S:-1800}"; MARGIN_S=300
T0=$(date +%s)
python /srv/rcb_limited.py end "$DATA" --timeout "${RCB_COLLECT_END_TIMEOUT_S:-900}"; rc=$?
case "$rc" in
    0) echo "[finalize] episode dumped: graded by the live episode (no replay)" ;;
    2) echo "[finalize] final.json already holds the verdict (the service gave up); kept" ;;
    *) echo "[finalize] the service did not end and exit in time (rc $rc): its episode.json decides if it dumped one, else infra" ;;
esac
END_RC="$rc" python - <<'PY'
import json, os
d = os.environ.get("RCB_DATA", "/data"); p = os.path.join(d, "final.json"); rc = os.environ.get("END_RC")
def read(name):
    try:
        v = json.load(open(os.path.join(d, name)))
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}
live = {"graded_by": "live", "replays": 0, "video": False, "video_pending": True, "video_source": "replay"}
if rc == "2":
    # the service's own verdict (a give-up after crashes): kept as it is
    out = {**live, **read("final.json")}
elif rc == "0" or os.path.isfile(os.path.join(d, "episode.json")):
    # rc 1 with episode.json on disk: the service dumped the episode (its verdict is complete) but did not exit in time
    out = {**live, "finalized": True, **({} if rc == "0" else {"service_exit_timed_out": True})}
    try:
        ep = json.load(open(os.path.join(d, "episode.json")))
        if not isinstance(ep, dict): raise ValueError("not an object")
        out.update(ep)
        if not ep.get("instance_ok_live"):
            # the scene the agent was served is not the frozen instance: no verdict on the agent
            out.update({"success": False, "instance_mismatch": 1, "infra_error": 1,
                        "error": "the live episode did not start in the instance's recorded state"})
    except Exception as exc:
        # the service's record of the live episode is missing: no verdict either way
        out.update({"success": False, "infra_error": 1, "error": f"infrastructure: no episode.json ({exc!r})"})
else:
    out = {**read("final.json"), **live, "finalized": True, "success": False, "infra_error": 1,
           "error": "collect hook: the sim service did not end and dump the episode in time"}
out["live_success"] = bool(out.get("success"))
out["finalized"] = bool(out.get("finalized"))
tmp = f"{p}.{os.getpid()}.tmp"
with open(tmp, "w") as f:
    json.dump(out, f); f.flush(); os.fsync(f.fileno())
os.replace(tmp, p)
print(json.dumps(out))
PY
# The video, with what is left of the hook's time (the verdict is on disk; nothing below can change it).
left=$(( HOOK_BUDGET_S - MARGIN_S - ($(date +%s) - T0) )); [ "$left" -gt "$VIDEO_TIMEOUT_S" ] && left=$VIDEO_TIMEOUT_S
rm -f "$DATA/replay3.json"
if [ -f "$DATA/trajectory.npz" ] && [ "$left" -ge 120 ]; then
    if command -v timeout > /dev/null 2>&1; then
        RCB_SESSION_LOG= timeout -k 30 "$left" python "$TOOL" replay --instance "$INSTANCE" --traj "$DATA/trajectory.npz" \
            --out "$DATA/replay3.json" --video "$DATA/replay.mp4" > /dev/null 2> "$DATA/replay3.log"; vrc=$?
    else
        RCB_SESSION_LOG= python "$TOOL" replay --instance "$INSTANCE" --traj "$DATA/trajectory.npz" \
            --out "$DATA/replay3.json" --video "$DATA/replay.mp4" > /dev/null 2> "$DATA/replay3.log"; vrc=$?
    fi
    echo "[finalize] video replay exit $vrc (limit $left s)"
else
    echo "[finalize] no video replay ($left s left)"
fi
python - <<'PY'
import json, os
d = os.environ.get("RCB_DATA", "/data"); p = os.path.join(d, "final.json")
try:
    out = json.load(open(p))
    if not isinstance(out, dict): raise ValueError("not an object")
except Exception as exc:
    print(f"[finalize] final.json unreadable, video fields not added: {exc!r}"); raise SystemExit
try:
    shown = bool(json.load(open(os.path.join(d, "replay3.json"))).get("video"))
except (OSError, ValueError, AttributeError):
    shown = False
mp4 = os.path.join(d, "replay.mp4")
ok = shown and os.path.isfile(mp4) and os.path.getsize(mp4) > 0
out.update({"video": ok, "video_pending": False})
if not ok:
    out["video_error"] = "the video replay gave no video (replay3.log)"
tmp = f"{p}.{os.getpid()}.tmp"
with open(tmp, "w") as f:
    json.dump(out, f); f.flush(); os.fsync(f.fileno())
os.replace(tmp, p)
PY
exit 0
