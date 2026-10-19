#!/bin/sh
# [[verifier.collect]] hook, run inside the `sim` sidecar once the agent's container is stopped (the `main` hook's kill -9 -1).
# The verdict is the live episode's (docs/protocol/README.md H.4; owner, 2026-10-17, board 0151); nothing is replayed to grade it.
#   1. `rcb_limited.py end --wait-key video_done` (the first half every eai-standard/2.2 hook shares): SIGUSR1 to the service
#      process that runs now (it may be resuming after a crash: no PID file until it is ready again). The service ends the
#      episode, commits a stroke still in progress, scores its live main sheet with the graders' rcb_brush_strict.py (the
#      picture rule and the process rules) and writes final.json with the verdict ("graded_by": "live"); then it renders the
#      recorded trajectory once into replay.mp4 and sets "video_done". Exit 2: final.json holds the verdict (or the service's
#      give-up after crashes), with its video or with the hook's time up for the video.
#   2. A verdict on disk stands; if its video was still rendering when the time below ran out, only the video is lost
#      (video_error). Without a verdict there is no verdict on the agent: an infrastructure failure (infra_error = 1), never
#      the agent's 0. final.json is always written whole (temporary file + rename).
set -u
DATA="${RCB_DATA:-/data}"
python /srv/rcb_limited.py end "$DATA" --wait-key video_done --timeout 2700; rc=$?
echo "[finalize] rcb_limited end: rc $rc"
python - <<'PY'
import json, os
p = os.path.join(os.environ.get("RCB_DATA", "/data"), "final.json")
try:
    out = json.load(open(p))
except Exception:  # noqa: BLE001
    out = {}
if not isinstance(out, dict):
    out = {}
if out.get("finalized") and (out.get("graded_by") == "live" or out.get("gave_up")):
    if out.get("gave_up") or out.get("video_done"):
        raise SystemExit(0)                  # the verdict and its video (or the give-up): as the service wrote them
    out.update({"video_pending": False, "video_done": True, "video_error": "the collect hook's time ran out while the video rendered"})
else:
    out.update({"finalized": True, "infra_error": 1,
                "error": "infrastructure: the sim service did not end the episode and write its verdict for the collect hook"})
with open(p + ".hook.tmp", "w") as f:
    json.dump(out, f)
os.replace(p + ".hook.tmp", p); print(json.dumps(out))
PY
exit 0
