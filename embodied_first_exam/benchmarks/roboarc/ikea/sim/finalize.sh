#!/bin/sh
# [[verifier.collect]] hook of the IKEA MuJoCo standard tasks (scripts/ikea_mujoco/standard/finalize.sh, copied unchanged),
# run inside the `sim` sidecar once Harbor has stopped the agent's container.
#   1. `rcb_limited.py end` (the shared first half): SIGUSR1 to the service, which ends the episode (judging it as it
#      stands: the terminal rules and the 1.0 s settled check on the live simulator), writes trajectory.npz and
#      episode.json (the live verdict, final-state hash, live_rows), closes the live video and exits. It waits through a
#      crash-recovery resume and exits 2 when final.json already holds the verdict (the service gave up after crashes,
#      or the instance mismatched at start).
#   2. final.json = episode.json + finalized, graded by the live episode (owner, 2026-10-17). No
#      grading replay runs, here or in the verifier; the video is the live recording (live.mp4, cam_high).
set -u
DATA="${RCB_DATA:-/data}"
python /srv/rcb_limited.py end "$DATA" --timeout "${RCB_COLLECT_END_TIMEOUT_S:-5400}"; rc=$?
RC="$rc" python - <<'PY'
import json, os
d = os.environ.get("RCB_DATA", "/data"); rc = os.environ.get("RC")
out = {}
try:
    out = json.load(open(os.path.join(d, "final.json")))
except Exception:
    pass
if rc == "0":
    try:
        out.update(json.load(open(os.path.join(d, "episode.json"))))
    except Exception as exc:
        out.update(success=False, infra_error=1, error=f"no episode.json: {exc!r}")
elif rc != "2":
    out.update(success=False, infra_error=1, error="collect hook: the sim service did not end and dump the episode in time")
out["finalized"] = True
out["success"] = bool(out.get("success")) and not out.get("gave_up")
out.setdefault("live_success", out["success"])
out.update(graded_by="live", replays=0, state_sha=out.get("live_sha"))
videos = [f for f in ("live.mp4", *(f"live.{i}.mp4" for i in range(2, 8))) if os.path.isfile(os.path.join(d, f))]
out.update(video=videos[0] if videos else None, video_segments=videos, video_pending=False, video_source="live")
tmp = os.path.join(d, "final.json.tmp")
with open(tmp, "w") as f:                 # written whole and synced, then renamed: a killed hook never leaves half a file
    json.dump(out, f); f.flush(); os.fsync(f.fileno())
os.replace(tmp, os.path.join(d, "final.json"))
print(json.dumps(out))
PY
