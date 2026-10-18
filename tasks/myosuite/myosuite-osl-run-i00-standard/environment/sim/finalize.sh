#!/bin/sh
# [[verifier.collect]] hook, run inside the `sim` sidecar once Harbor has stopped the agent's container.
#   1. `rcb_limited.py end` (docs/protocol/standard_mode.md §13.3): SIGUSR1 to the service, which ends the episode if the
#      agent had not (reason "timeout"), writes trajectory.npz + episode.json (the live verdict, the final-state hash)
#      and exits. It exits 2 when final.json already holds the verdict (the service gave up: after crashes, or at the
#      start on a scene that is not the frozen instance): that verdict stays.
#   2. the verdict is the live episode's (owner, 2026-10-17, board 0151): episode.json's success, the task's rule as the
#      service applied it to the steps it ran (its hold / track windows are part of that rule). Nothing is replayed to
#      grade it. final.json gets graded_by = "live", replays = 0, finalized = true: the only thing the verifier grades.
#   3. ONE render pass of the trajectory from the frozen instance in a fresh process (video.py) draws replay.mp4, after
#      the verdict is on disk (video_pending while it runs): it checks nothing, and a render that fails or runs out of
#      time loses only the video, never the verdict.
# Time: the hook has RCB_COLLECT_BUDGET_S (the task's [[verifier.collect]] timeout_sec). The render steps the physics of
# the graded episode once (no agent thinking time, ~1500 frames at most) and gets what is left of the budget, less a
# minute; it stops itself 30 s before that (the frames so far stay playable) and is killed at it.
# final.json is always written to a temporary file and renamed: the verifier never reads half of one, and a hook killed
# mid-write leaves the previous one (not finalized: tests/grade.py books that as infra_error, not as the agent's 0).
set -u
DATA="${RCB_DATA:-/data}"; SRV="${RCB_SRV:-/srv}"; export SRV   # RCB_SRV: for the tests only
RCB_HOOK_T0="$(date +%s)"; export RCB_HOOK_T0
python "$SRV/rcb_limited.py" end "$DATA" --timeout "${RCB_COLLECT_END_TIMEOUT_S:-900}"; rc=$?
if [ "$rc" = 2 ]; then
    echo "[finalize] final.json already holds the verdict"; exit 0
fi
RCB_END_RC="$rc" python - <<'PY'
import json, os, subprocess, sys, time

d = os.environ.get("RCB_DATA", "/data")
srv = os.environ.get("SRV", "/srv")
instance = os.environ.get("RCB_INSTANCE", os.path.join(srv, "instance.npz"))
t0 = float(os.environ.get("RCB_HOOK_T0") or time.time())
hard = t0 + float(os.environ.get("RCB_COLLECT_BUDGET_S") or 1800) - 60.0   # everything is done a minute early
final = os.path.join(d, "final.json")


def read(name):
    try:
        with open(os.path.join(d, name)) as f:
            v = json.load(f)
    except (OSError, ValueError):
        return {}
    return v if isinstance(v, dict) else {}


def write_final(out):
    tmp = final + ".hook.tmp"
    with open(tmp, "w") as f:
        json.dump(out, f)
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp, final)
    print(json.dumps(out), flush=True)


if os.environ.get("RCB_END_RC") != "0":
    print("[finalize] the service did not end and dump the episode in time: an infrastructure failure", flush=True)
    out = read("final.json")
    out.update({"finalized": True, "success": False, "graded_by": "live", "replays": 0, "infra_error": 1,
                "error": "collect hook: the sim service did not end and dump the episode in time"})
    write_final(out)
    sys.exit(0)

ep = read("episode.json")
out = dict(ep)
out.update({"graded_by": "live", "replays": 0, "live_success": bool(ep.get("success")), "success": bool(ep.get("success")),
            "state_sha": ep.get("live_sha"), "video": False, "video_pending": True, "video_source": "render"})
if not ep:  # the service's own record of the live episode is unreadable: no verdict on the agent
    out.update({"success": False, "infra_error": 1, "video_pending": False, "error": "no episode.json"})
out["finalized"] = True
write_final(out)   # the verdict: nothing below changes it
if not ep:
    sys.exit(0)

left = hard - time.time()
mp4, res = os.path.join(d, "replay.mp4"), os.path.join(d, "video.json")
ok = False
if left < 60.0:
    print("[finalize] no time left for replay.mp4", flush=True)
else:
    print(f"[finalize] verdict written; rendering replay.mp4 (at most {left:.0f} s)", flush=True)
    for f in (mp4, res):
        try:
            os.remove(f)
        except OSError:
            pass
    with open(os.path.join(d, "video.log"), "w") as log:
        p = subprocess.Popen([sys.executable, os.path.join(srv, "video.py"), "--instance", instance, "--traj",
                              os.path.join(d, "trajectory.npz"), "--out", mp4, "--result", res,
                              "--deadline-s", str(int(left - 30.0))],
                             stdout=subprocess.DEVNULL, stderr=log, env=dict(os.environ, RCB_SESSION_LOG=""))
        try:
            p.wait(timeout=left)
        except subprocess.TimeoutExpired:
            p.kill(); p.wait()
            print("[finalize] the video render ran out of time", flush=True)
    ok = bool(read("video.json").get("video")) and os.path.isfile(mp4)
    if not ok:
        try:
            os.remove(mp4)   # a file cut off mid-write does not play
        except OSError:
            pass
out.update({"video": ok, "video_pending": False})
write_final(out)
PY
exit 0
