#!/bin/sh
# [[verifier.collect]] hook, run inside the `sim` sidecar once Harbor has stopped the agent's container.
# The live episode is the verdict (owner 2026-10-17): no grading replay runs.
#   1. `rcb_limited.py end` (the shared first half, docs/protocol/standard_mode.md §13.3): SIGUSR1 to the service, which ends
#      the episode (judged as it stands), writes trajectory.npz + episode.json (the live verdict, its review / forcing /
#      instability evidence, final-state hash, live_rows) and exits, releasing its GPU. It waits through a crash-recovery
#      resume (no PID file until the service is ready again), signals only the newest service process, resends every
#      30 s, and exits 2 when final.json already holds the verdict (the service gave up after crashes, or the instance
#      mismatched at start): that verdict stays.
#   2. final.json = episode.json + finalized, graded_by "live", replays 0, video_pending: written BEFORE any video work,
#      so a slow, failing or killed video pass loses only the video.
#   3. ONE video-only pass (replay.py): a fresh-process replay of the live rows from the frozen instance on the sidecar's
#      GPU (the live service has exited; Nyx renders only in a container that sees one GPU), rendering replay.mp4, and
#      for a live success held for review the frames around its live review events. It never changes the verdict: only
#      the video fields of final.json are updated from its record (replay.video.json).
set -u
DATA="${RCB_DATA:-/data}"; TASK="${RCB_TASK:?}"; INSTANCE="${RCB_INSTANCE:?}"
python /srv/rcb_limited.py end "$DATA" --timeout "${RCB_COLLECT_END_TIMEOUT_S:-3600}"; rc=$?
RC="$rc" python - <<'PY'
import json, os, sys
d = os.environ.get("RCB_DATA", "/data"); rc = os.environ["RC"]; p = os.path.join(d, "final.json")
sys.path.insert(0, "/srv")
from rcb_topogym import atomic_json
try:
    out = json.load(open(p))
except Exception:
    out = {}
episode = None
if rc in ("0", "1"):
    try:
        episode = json.load(open(os.path.join(d, "episode.json")))
    except Exception as exc:
        err = exc
if episode is not None:
    out.update(episode)
    if rc == "1":       # the episode was dumped but the service did not exit in time: the live verdict stands, no video
        out["service_exit_timed_out"] = True
    if not os.path.isfile(os.path.join(d, "trajectory.npz")):   # evidence only: the verdict is the live record's
        out["dump_error"] = out.get("dump_error") or "no trajectory.npz"
elif rc == "0":
    out.update(success=False, infra_error=1, error=f"no episode.json: {err!r}")
elif rc != "2":
    out.update(success=False, infra_error=1, error="collect hook: the sim service did not end and dump the episode in time")
# A simulator breakdown without forcing in the live episode (rcb_topogym.SIMULATOR_INSTABILITY) is an infrastructure
# failure: never the agent's success, never the task's failure (a breakdown right after forcing is the agent's
# "forced_breakdown: ...").
if out.get("reason") == "simulator_instability":
    out["simulator_instability"] = True; out["infra_error"] = 1
    from rcb_topogym import breakdown_words
    ev = out.get("instability")
    out.setdefault("error", "simulator_instability: " + (breakdown_words(ev) if isinstance(ev, dict) else "a simulator breakdown"))
# live_success: the live episode's own success; success: the verdict (no infrastructure failure, not held for review)
out["live_success"] = bool(out.get("success")) and not out.get("gave_up")
out["held_for_review"] = out["live_success"] and isinstance(out.get("review"), dict)
out["success"] = out["live_success"] and not out.get("infra_error") and not out["held_for_review"]
out.update(finalized=True, graded_by="live", replays=0, state_sha=out.get("live_sha"))
for k, v in (("video", False), ("video_source", "render"), ("video_pending", rc == "0"),
             ("media_status", "pending" if rc == "0" else "none")):
    out.setdefault(k, v)


def finite(v):   # a non-finite number (NaN, inf) would make atomic_json refuse the record: null instead
    import math
    if isinstance(v, float) and not math.isfinite(v):
        return None
    if isinstance(v, dict):
        return {k: finite(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [finite(x) for x in v]
    return v


atomic_json(p, finite(out))
print(json.dumps(out))
PY
if [ "$rc" != 0 ]; then
    echo "[finalize] rc $rc: final.json holds the verdict; no video pass"; exit 0
fi
video_merge() {   # replay.video.json -> the video fields of final.json (never the verdict); safe to repeat
python - <<'PY'
import json, os, sys
d = os.environ.get("RCB_DATA", "/data"); p = os.path.join(d, "final.json")
sys.path.insert(0, "/srv")
from rcb_topogym import atomic_json
out = json.load(open(p))


def finite(v):   # as in the verdict step: no non-finite number reaches atomic_json
    import math
    if isinstance(v, float) and not math.isfinite(v):
        return None
    if isinstance(v, dict):
        return {k: finite(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [finite(x) for x in v]
    return v



try:
    r = json.load(open(os.path.join(d, "replay.video.json")))
except Exception:
    r = {}
done = os.path.isfile(os.path.join(d, ".replay_rc"))
out["video"] = bool(r.get("video")) and os.path.exists(os.path.join(d, "replay.mp4"))
out["media_status"] = r.get("media_status") or ("error" if done else "pending")
out["video_pending"] = not done
for k in ("video_error", "review_frames", "review_frames_error"):
    if r.get(k) is not None:
        out[k] = r[k]
out["video_wall_s"] = r.get("wall_s")
if os.environ.get("GPU_LOST"):
    out.update(video_pending=False, media_status="error",
               video_error="the GPU was not accessible to new processes in the sim sidecar: no video (the verdict stands)")
atomic_json(p, finite(out))
print(json.dumps({k: out.get(k) for k in ("success", "video", "media_status", "video_pending")}))
PY
}
# A host systemd reload while this long-running container is up (a snap or apt update, with Docker's systemd cgroup
# driver) makes the GPU refuse processes started afterwards: the video is lost, the verdict stands.
if python - <<'PY'
import os, sys
for dev in ("/dev/nvidiactl", "/dev/nvidia0"):
    if os.path.exists(dev):
        try:
            open(dev, "rb").close()
        except OSError as exc:
            print(f"[finalize] cannot open {dev}: {exc}", file=sys.stderr); sys.exit(1)
PY
then
    echo "[finalize] verdict written; one video-only pass"
    rm -f "$DATA/.replay_rc"
    { python /srv/replay.py --data "$DATA" --task "$TASK" --instance "$INSTANCE" --video "$DATA/replay.mp4" > "$DATA/replay.json" 2> "$DATA/replay.log"
      echo "$?" > "$DATA/.replay_rc"; } &
    seen=""
    while [ ! -f "$DATA/.replay_rc" ]; do
        now="$(cksum "$DATA/replay.video.json" 2>/dev/null)"
        if [ -n "$now" ] && [ "$now" != "$seen" ]; then
            seen="$now"; video_merge > /dev/null
        fi
        sleep 2
    done
    wait
    echo "[finalize] video pass exit $(cat "$DATA/.replay_rc" 2>/dev/null)"
    video_merge
else
    GPU_LOST=1 video_merge
fi
