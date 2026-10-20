#!/bin/sh
# [[verifier.collect]] hook, run inside the `sim` sidecar once Harbor has stopped the agent's container. The verdict is
# the live episode's (owner 2026-10-17): nothing is replayed.
#   1. end the episode with the shared first half (rcb_limited.py end, docs/protocol/standard_mode.md §13.3): it waits through a
#      resume, SIGUSR1s the service, and returns 0 once the service has written trajectory.npz + episode.json, closed
#      the live video (live.mp4) and exited (releasing the GPU); 2 when final.json already holds the verdict (a give-up:
#      after crashes, or a frozen start that did not rebuild); 1 when the service never ended the episode. With rc 1 an
#      episode.json the service did dump (it ended the episode, then did not exit in time) is still the live verdict;
#      only without one is it an infrastructure failure.
#   2. merge episode.json (the live episode's result: upstream's success under settle-eval, judged at every control step
#      it ran) into final.json (written atomically), the only file the verifier sandbox grades. The video is checked for
#      playability and never decides anything.
#   3. only when the live video (live.mp4) is missing or does not play: ONE video-only pass, a fresh-process render of
#      trajectory.npz (`rcb_ispatialgym.py replay --video`) after the verdict; its success and hash are not read, it is
#      not retried, and a render that fails or runs out of the hook's time loses only the video.
set -u
DATA="${RCB_DATA:-/out}"
SRV="${RCB_SRV:-/srv}"
T0=$(date +%s)
BUDGET_S="${RCB_COLLECT_BUDGET_S:-4200}"   # = [[verifier.collect]] timeout_sec of the sim hook in task.toml
END_S="${RCB_END_TIMEOUT_S:-3600}"         # the episode's end, through a resume (a scene load + the journal)
python "$SRV/rcb_limited.py" end "$DATA" --timeout "$END_S"; rc=$?
if [ "$rc" = 2 ]; then
    echo "[finalize] final.json already holds the verdict (a give-up)"; exit 0
fi
# a late exit's episode.json counts only when the newest service start wrote it (never a stale one from before a crash)
if [ "$rc" != 0 ] && [ -s "$DATA/episode.json" ] && python - <<'PY'
import json, os, sys
d = os.environ.get("RCB_DATA", "/out")
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
    echo "[finalize] the service did not end the episode (rc $rc): recorded as an infrastructure failure"
    RCB_SRV="$SRV" python - <<'PY'
import os, sys
sys.path.insert(0, os.environ.get("RCB_SRV", "/srv"))
import rcb_limited as L
d = os.environ.get("RCB_DATA", "/out")
if not L.final_verdict(d):
    fin = L._read_json(os.path.join(d, "final.json"))
    fin.update({"success": False, "live_success": False, "finalized": True, "graded_by": "live", "replays": 0, "infra_error": 1,
                "video": False, "video_pending": False,
                "error": "infrastructure: the sim service never ended the episode for the collect hook"})
    L._write_json(os.path.join(d, "final.json"), fin)
PY
    exit 0
fi
echo "[finalize] episode dumped; final.json from the live episode (no replay)"
RCB_END_RC="$rc" python - <<'PY'
import json, os, subprocess
d = os.environ.get("RCB_DATA", "/out")
out = {"finalized": True, "graded_by": "live", "replays": 0, "video": False, "video_pending": False,
       "end_timed_out": os.environ.get("RCB_END_RC", "0") != "0"}   # the service dumped but did not exit in time
try:
    ep = json.load(open(os.path.join(d, "episode.json")))
    if not isinstance(ep, dict): raise ValueError("episode.json is not an object")
    out.update(ep)
    out["live_success"] = bool(ep.get("success"))
except Exception as exc:
    out.update({"success": False, "live_success": False, "infra_error": 1, "error": f"infrastructure: no episode.json: {exc!r}"})
out["graded_by"], out["replays"] = "live", 0
out["state_sha"] = out.get("live_sha")
out["trajectory"] = os.path.exists(os.path.join(d, "trajectory.npz"))
def playable(p):
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                            "stream=nb_read_packets", "-of", "csv=p=0", p], capture_output=True, text=True, timeout=120)
        return r.returncode == 0 and int((r.stdout.strip() or "0").split(",")[0]) > 0
    except Exception:
        return False
v = os.path.join(d, "live.mp4")
out["video"] = os.path.exists(v) and playable(v)
out["video_source"] = "live" if out["video"] else None
out["video_pending"] = not out["video"] and out["trajectory"]
out["finalized"] = True
tmp = os.path.join(d, "final.json.tmp")
json.dump(out, open(tmp, "w")); os.replace(tmp, os.path.join(d, "final.json"))
print(json.dumps(out))
PY
python - <<'PY' || exit 0
import json, os, sys
sys.exit(0 if json.load(open(os.path.join(os.environ.get("RCB_DATA", "/out"), "final.json"))).get("video_pending") else 1)
PY
# 3. the video-only pass (no playable live video): the hook's remaining time less 330 s (the merge below: ffprobe up to
# 120 s), one attempt; not while a service that did not exit may still hold the simulator (rc 1)
left=$((BUDGET_S - 330 - ($(date +%s) - T0)))
if [ "$rc" = 0 ] && [ "$left" -ge 60 ] && [ -n "${RCB_TOOL:-}" ] && [ -n "${RCB_INSTANCE:-}" ]; then
    echo "[finalize] no playable live video: one video-only render ($left s)"
    limit=""; command -v timeout >/dev/null 2>&1 && limit="timeout -k 30 $left"
    $limit python "$RCB_TOOL" replay --instance "$RCB_INSTANCE" --traj "$DATA/trajectory.npz" --video "$DATA/replay.mp4" > "$DATA/video.json" 2> "$DATA/video.log"
    echo "[finalize] video render exit $?"
else
    echo "[finalize] video render skipped ($left s left)"
fi
python - <<'PY'
import json, os, subprocess
d = os.environ.get("RCB_DATA", "/out")
def playable(p):
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                            "stream=nb_read_packets", "-of", "csv=p=0", p], capture_output=True, text=True, timeout=120)
        return r.returncode == 0 and int((r.stdout.strip() or "0").split(",")[0]) > 0
    except Exception:
        return False
p = os.path.join(d, "final.json")       # the verdict is on disk: only the video fields change
try:
    out = json.load(open(p))
except Exception as exc:
    print(f"[finalize] video fields: final.json unreadable: {exc!r}"); raise SystemExit(0)
v = os.path.join(d, "replay.mp4")
out["video"] = os.path.exists(v) and playable(v)
out["video_source"] = "render" if out["video"] else None
out["video_pending"] = False
tmp = p + ".tmp"
json.dump(out, open(tmp, "w")); os.replace(tmp, p)
print(json.dumps({k: out[k] for k in ("video", "video_source")}))
PY
