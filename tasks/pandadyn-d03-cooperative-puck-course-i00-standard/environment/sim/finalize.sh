#!/bin/sh
# [[verifier.collect]] hook, run inside the `sim` sidecar once the agent's processes are stopped (task.toml: the monitor's
# seal, then `kill -9 -1` in the agent's container, then this).
# The verdict is the live episode's (owner, 2026-10-17, board 0151; docs/benchmarks/pandadyn.md "Grading"): nothing is
# replayed to grade it.
#   1. `rcb_limited.py end` (the shared first half, docs/STANDARD_MODE.md §13.3): SIGUSR1 to the service, which ends
#      the episode, writes trajectory.npz + episode.json (the live result: the task's event ledger as the episode ended,
#      the final state hash) and exits, releasing the simulator. It waits through a crash-recovery resume (no PID file
#      until the service is ready again), signals only the newest service process, resends every 30 s, and exits 2 when
#      final.json already holds the verdict (the service gave up after crashes, or refused a scene that did not rebuild
#      the frozen start): that verdict stays.
#   2. the verdict: episode.json merged into final.json with "finalized": true, "graded_by": "live", "replays": 0 and
#      success = the live success, in one atomic write (a temporary file + rename: the verifier never reads a half-written
#      one). No episode.json or no trajectory.npz (the service could not dump the episode it ran) is the infrastructure's
#      failure: infra_error = 1, no verdict on the agent.
#   3. the video, for people only: one more process rebuilds the frozen scene and films the trajectory (render_video,
#      overview camera, 25 fps) into replay.mp4 + replay.last.png; "video_pending" is true while it runs. It never touches
#      the verdict: a failed, slow or killed render (a lost GPU, its time limit, the hook's deadline) costs only the video.
#      `video_matches_live` records whether the filmed run ended in the live state hash (the determinism witness the
#      grading replays used to give); it decides nothing.
# Time: the hook has HOOK_BUDGET_S (task.toml's [[verifier.collect]] timeout_sec; keep the two equal): the episode's end
# (up to RCB_COLLECT_END_TIMEOUT_S, 900 s, through a resume that replays the journal: at most the task's horizon, 3500
# control steps, ~40-150 per second), the verdict (a second), then the video with what is left minus MERGE_MARGIN_S
# (a scene build, 5-15 s, + at most 3500 filmed control steps: 1-3 min measured).
set -u
DATA="${RCB_DATA:-/data}"; TOOL="${RCB_TOOL:?}"; INSTANCE="${RCB_INSTANCE:?}"; SRV="${RCB_SRV:-/srv}"
HOOK_BUDGET_S="${RCB_COLLECT_TIMEOUT_S:-2400}"; MERGE_MARGIN_S="${RCB_MERGE_MARGIN_S:-60}"; VIDEO_MIN_S="${RCB_VIDEO_MIN_S:-30}"
T0=$(date +%s)
export DATA TOOL INSTANCE
python "$SRV/rcb_limited.py" end "$DATA" --timeout "${RCB_COLLECT_END_TIMEOUT_S:-900}"; rc=$?
# 2. the verdict (rc 0: the dump; rc 2: the service's own verdict, kept; anything else: the service never dumped)
RC="$rc" python - <<'PY'
import json, os
d = os.environ["DATA"]; rc = os.environ["RC"]; p = os.path.join(d, "final.json")
def load(name):
    try:
        v = json.load(open(os.path.join(d, name)))
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}
out = load("final.json")
live = {"graded_by": "live", "replays": 0, "video": False, "video_pending": False, "video_source": "render"}
if rc == "2":
    # the service's own record (a give-up after crashes, a refused start): its success and infra_error stand
    for k, v in live.items():
        out.setdefault(k, v)
    out["live_success"] = bool(out.get("success"))
    if str(out.get("reason") or "").startswith("instance_mismatch"):
        out["instance_mismatch"] = True
    print("[finalize] final.json already holds the service's verdict; nothing to render")
elif rc != "0":
    out.update({**live, "finalized": True, "success": False, "live_success": False, "infra_error": 1,
                "error": "collect hook: the sim service did not end and dump the episode in time"})
    print(f"[finalize] the service did not end and dump the episode in time (rc {rc}): an infrastructure failure")
else:
    ep = load("episode.json")
    out.update(ep)
    ok = bool(ep.get("success")) and ep.get("reason") != "error"   # a simulator error is never a success (server.py finish)
    out.update({**live, "finalized": True, "success": ok, "live_success": ok,
                "state_sha": ep.get("live_sha")})
    if not ep:
        out.update({"success": False, "infra_error": 1, "dump_error": "no episode.json",
                    "error": "infrastructure: the service ended without writing the live result (episode.json)"})
    elif not os.path.exists(os.path.join(d, "trajectory.npz")):
        out.update({"success": False, "infra_error": 1, "dump_error": "no trajectory.npz",
                    "error": "infrastructure: the service ended without saving the episode's trajectory"})
    else:
        out["video_pending"] = True                 # announced with the verdict: the video is rendered next
tmp = f"{p}.{os.getpid()}.tmp"
with open(tmp, "w") as f:
    json.dump(out, f); f.flush(); os.fsync(f.fileno())
os.replace(tmp, p)
PY
# 3. the video (only after a dump with a verdict: video_pending)
if grep -q '"video_pending": true' "$DATA/final.json" 2>/dev/null; then
    left=$(( T0 + HOOK_BUDGET_S - MERGE_MARGIN_S - $(date +%s) ))
    rm -f "$DATA/replay.tmp.mp4" "$DATA/replay.tmp.last.png"
    if [ "$left" -ge "$VIDEO_MIN_S" ]; then
        echo "[finalize] verdict written; rendering the video (at most ${left} s)"
        TO=""; command -v timeout >/dev/null 2>&1 && TO="timeout -k 20 $left"
        RCB_SESSION_LOG= $TO python - > "$DATA/video.json" 2>> "$DATA/video.log" <<'PY'
import json, os, sys, time
t0 = time.time()
tool = os.environ["TOOL"]; d = os.environ["DATA"]
sys.path.insert(0, os.path.dirname(os.path.abspath(tool)))
import rcb_pandadyn as M
M.SESSION_LOG = ""
s = M.Session(os.environ["INSTANCE"])
A = M.load_trajectory(os.path.join(d, "trajectory.npz"), s.task, s.dim)
tmp = os.path.join(d, "replay.tmp.mp4")
st = s.render_video(A, tmp, fps=25, camera="overview")
from PIL import Image
Image.fromarray(s.render_frame("overview")).save(os.path.join(d, "replay.tmp.last.png"))
os.replace(os.path.join(d, "replay.tmp.last.png"), os.path.join(d, "replay.last.png"))
os.replace(tmp, os.path.join(d, "replay.mp4"))
print(json.dumps({"video_ok": True, "video_sha": st["state_sha"], "video_s": round(time.time() - t0, 1)}), flush=True)
s.close()
PY
        echo "[finalize] video pass exit $?"
    else
        echo "[finalize] no time left for the video"
    fi
    python - <<'PY'
import json, os
d = os.environ["DATA"]; p = os.path.join(d, "final.json")
out = json.load(open(p))
v = {}
try:
    for line in open(os.path.join(d, "video.json")):
        if line.strip().startswith("{"):
            v = json.loads(line)
except Exception:
    pass
mp4 = os.path.join(d, "replay.mp4")
ok = bool(v.get("video_ok")) and os.path.exists(mp4) and os.path.getsize(mp4) > 0
# video fields only: the verdict above is final
out.update({"video": ok, "video_pending": False})
if ok:
    out["video_matches_live"] = v.get("video_sha") == out.get("live_sha"); out["video_s"] = v.get("video_s")
else:
    out["video_error"] = "the video pass gave no video (video.log)"
tmp = f"{p}.{os.getpid()}.tmp"
with open(tmp, "w") as f:
    json.dump(out, f); f.flush(); os.fsync(f.fileno())
os.replace(tmp, p)
PY
fi
cat "$DATA/final.json"
