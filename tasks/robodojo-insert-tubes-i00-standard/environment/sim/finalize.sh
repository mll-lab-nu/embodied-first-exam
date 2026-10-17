#!/bin/sh
# [[verifier.collect]] hook, run inside the `sim` sidecar once Harbor has stopped the agent's container. The trial is
# graded by its LIVE episode, the one the agent ran, with no grading replay (owner 2026-10-17, board 0150/0151).
#   1. `rcb_limited.py end` (the shared first half, docs/STANDARD_MODE.md §13.3): SIGUSR1 to the service, which ends
#      the episode, writes trajectory.npz + episode.json (the live result: RoboDojo's check, after every action; the
#      end-state hash), takes the video's last frame and exits. It waits through a crash-recovery resume (no PID file
#      until the service is ready again), signals only the newest service process, resends every 30 s, and exits 2 when
#      final.json already holds the verdict (the service gave up: after crashes, or because the frozen instance did not
#      rebuild to its recorded state hash at the episode's start, `instance_mismatch`): that verdict stays.
#   2. final.json = the live record (episode.json) + `graded_by` "live", `replays` 0, `finalized`: written whole (a
#      temporary file + rename) BEFORE the video, with `video_pending` true, so the verifier never reads a half-written
#      one and nothing the video does can change or delay the verdict.
#   3. the video: `live_video.py encode` (CPU only, no simulator) turns the frames the service took during the live
#      episode (live_video/, from renders the agent's own calls made) into live.mp4; final.json gets
#      the video fields. A failed or slow encode costs the video only (`video` false), never the verdict, never infra.
# Time: the hook has HOOK_BUDGET_S (task.toml's [[verifier.collect]] timeout_sec; keep the two equal): the episode end
# (up to RCB_COLLECT_END_TIMEOUT_S = 2700 s through a resume, which replays the journal first at ~7-11 actions/s) +
# the encode (at most VIDEO_LIMIT_S; at most 3001 frames, live_video.MAX_FRAMES) + a margin. Before 2026-10-17 this hook
# also replayed the trajectory once in a fresh Isaac process (10800 s budget; two replays and 18000 s before 2026-10-12),
# and a task graded by verdict (instance.json "determinism": "verdict") had that replay recorded without deciding.
set -u
SRV="${RCB_SRV:-/srv}"; DATA="${RCB_DATA:-/data}"
HOOK_BUDGET_S="${RCB_COLLECT_TIMEOUT_S:-3600}"; VIDEO_LIMIT_S="${RCB_VIDEO_LIMIT_S:-600}"; T0=$(date +%s)
python "$SRV/rcb_limited.py" end "$DATA" --timeout "${RCB_COLLECT_END_TIMEOUT_S:-2700}"; rc=$?
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
live = {"graded_by": "live", "replays": 0, "video": False, "video_pending": True, "video_source": "live"}
if rc == "2":
    # the service's own verdict (a give-up: after crashes, or instance_mismatch at the start): kept as it is
    out = {**live, **read("final.json")}
elif rc == "0" or os.path.isfile(os.path.join(d, "episode.json")):
    # rc 1 with episode.json on disk: the service dumped the episode (its verdict is complete) but did not exit in time
    # (e.g. a render of the video's last frame that hangs): the live record still decides
    out = {**live, "finalized": True, **({} if rc == "0" else {"service_exit_timed_out": True})}
    try:
        ep = json.load(open(os.path.join(d, "episode.json")))
        if not isinstance(ep, dict): raise ValueError("not an object")
        out.update(ep)
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
# the video: one encode, after the verdict
left=$(( T0 + HOOK_BUDGET_S - 60 - $(date +%s) )); limit=$VIDEO_LIMIT_S
if [ "$left" -lt "$limit" ]; then limit=$left; fi
vrc=none
if [ "$limit" -ge 30 ]; then
    if command -v timeout >/dev/null 2>&1; then
        timeout -k 10 "$limit" python "$SRV/live_video.py" encode "$DATA" > "$DATA/video.json" 2> "$DATA/video.log"; vrc=$?
    else
        python "$SRV/live_video.py" encode "$DATA" > "$DATA/video.json" 2> "$DATA/video.log"; vrc=$?
    fi
fi
echo "[finalize] video encode exit $vrc (limit ${limit} s)"
VRC="$vrc" python - <<'PY'
import json, os
d = os.environ.get("RCB_DATA", "/data"); p = os.path.join(d, "final.json")
try:
    out = json.load(open(p))
    if not isinstance(out, dict): raise ValueError("not an object")
except Exception as exc:
    print(f"[finalize] final.json unreadable, video fields not added: {exc!r}"); raise SystemExit
res = {}
try:
    for line in open(os.path.join(d, "video.json")):
        if line.strip().startswith("{"):
            res = json.loads(line)
except Exception:
    pass
mp4 = os.path.join(d, "live.mp4")
ok = bool(res.get("video")) and os.path.isfile(mp4) and os.path.getsize(mp4) > 0
out.update({"video": ok, "video_pending": False, "video_frames": int(res.get("frames") or 0), "video_every_steps": res.get("every")})
if not ok:
    out["video_error"] = str(res.get("error") or f"no result from the encode (exit {os.environ.get('VRC')})")[:300]
tmp = f"{p}.{os.getpid()}.tmp"
with open(tmp, "w") as f:
    json.dump(out, f); f.flush(); os.fsync(f.fileno())
os.replace(tmp, p)
print(json.dumps({k: out.get(k) for k in ("success", "infra_error", "video", "video_frames", "video_every_steps", "video_error")}))
PY
exit 0
