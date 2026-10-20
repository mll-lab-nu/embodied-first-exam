#!/bin/sh
# [[verifier.collect]] hook, run inside the `sim` sidecar once Harbor has stopped the agent's container.
#   1. `rcb_limited.py end` (docs/protocol/standard_mode.md §13.3): SIGUSR1 to the service, which ends the episode if the
#      agent had not (reason "timeout"), writes trajectory.npz + episode.json (the live verdict: DexJoCo's own success
#      check on the episode the service ran, the final-state hash) and exits. It exits 2 when final.json already holds
#      the verdict (the service gave up: after crashes, or at the start: too few CPUs, a scene that did not build to the
#      frozen instance): that verdict stays.
#   2. write final.json from episode.json: the verdict is the live episode's (owner, 2026-10-17; graded_by
#      = "live", replays = 0). Nothing is replayed to grade it: DexJoCo's episode ends at the first success, so there is
#      no settle window after it that a replay would have added (docs/benchmarks/dexjoco.md, Grading).
#   3. one video-only pass (`video.py`, a fresh process): the trajectory rendered from the frozen instance into
#      replay.mp4, after the verdict is on disk ("video_pending" while it runs). It never changes the verdict: a video
#      that fails or runs out of time loses only the video.
# Time: the hook has RCB_COLLECT_BUDGET_S (the task's [[verifier.collect]] timeout_sec). The video steps the physics the
# live episode stepped and renders at most ~1500 frames; it gets what is left of the budget, at most
# RCB_COLLECT_VIDEO_MAX_S, and is stopped at that. final.json is always written whole (temporary file + rename).
set -u
DATA="${RCB_DATA:-/data}"; INSTANCE="${RCB_INSTANCE:?}"; TASK="${RCB_TASK:?}"
RCB_SRV="${RCB_SRV:-/srv}"; export RCB_SRV   # the task's sim/ directory (tests point it elsewhere)
RCB_HOOK_T0="$(date +%s)"; export RCB_HOOK_T0
python "$RCB_SRV/rcb_limited.py" end "$DATA" --timeout "${RCB_COLLECT_END_TIMEOUT_S:-900}"; rc=$?
if [ "$rc" = 2 ]; then
    echo "[finalize] final.json already holds the verdict (the service gave up); nothing to add"; exit 0
fi
RCB_END_RC="$rc" python - <<'PY'
import json, os, subprocess, sys, time

d = os.environ.get("RCB_DATA", "/data")
instance, task = os.environ["RCB_INSTANCE"], os.environ["RCB_TASK"]
t0 = float(os.environ.get("RCB_HOOK_T0") or time.time())
hard = t0 + float(os.environ.get("RCB_COLLECT_BUDGET_S") or 5400) - 60.0   # everything is done a minute early
video_max = float(os.environ.get("RCB_COLLECT_VIDEO_MAX_S") or 4500)
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


LIVE = {"graded_by": "live", "replays": 0, "video": False, "video_source": "render"}
if os.environ.get("RCB_END_RC") != "0":
    print("[finalize] the service did not end and dump the episode in time: an infrastructure failure", flush=True)
    out = read("final.json")
    out.update({**LIVE, "finalized": True, "success": False, "live_success": False, "video_pending": False,
                "infra_error": 1, "error": "collect hook: the sim service did not end and dump the episode in time"})
    write_final(out)
    sys.exit(0)

ep = read("episode.json")
out = {**ep, **LIVE}
out["live_success"] = bool(ep.get("success"))
out["success"] = out["live_success"]   # the verdict: DexJoCo's own success check on the live episode
if not ep:  # the service's own record of the live episode is unreadable: no verdict on the agent
    out.update({"infra_error": 1, "error": "no episode.json"})
elif ep.get("instance_ok") is False:   # the scene did not start in the frozen instance (the service refuses that at
    out.update({"instance_mismatch": 1, "infra_error": 1,   # its start; this is the backstop): not the agent's 0
                "error": "the live episode did not start in the instance's t = 0 state"})
if out.get("threads_ok", 1) == 0:
    # the live episode ran fewer than 4 OpenBLAS threads: other numerics than the references', no verdict
    out.update({"too_few_cpus": 1, "infra_error": 1,
                "error": "fewer than 4 OpenBLAS threads (fewer than 4 CPUs visible to the sim sidecar)"})
out["finalized"] = True
left = min(video_max, hard - time.time() - 15.0)
have_traj = os.path.exists(os.path.join(d, "trajectory.npz"))
out["video_pending"] = bool(have_traj and left >= 60.0)
write_final(out)   # the verdict: nothing below changes it
if not out["video_pending"]:
    print("[finalize] no trajectory or no time left for replay.mp4", flush=True)
    sys.exit(0)

mp4 = os.path.join(d, "replay.mp4")
for f in (mp4, os.path.join(d, "video.json")):
    try:
        os.remove(f)
    except OSError:
        pass
# the video stops itself 30 s before its time is up (the frames so far stay playable); the kill is the backstop
log = open(os.path.join(d, "video.log"), "w")
p = subprocess.Popen([sys.executable, os.path.join(os.environ.get("RCB_SRV") or "/srv", "video.py"),
                      "--task", task, "--instance", instance, "--traj", os.path.join(d, "trajectory.npz"),
                      "--out", mp4, "--json", os.path.join(d, "video.json"), "--deadline-s", str(int(left - 30.0))],
                     stdout=log, stderr=subprocess.STDOUT, env=dict(os.environ, RCB_SESSION_LOG=""))
try:
    p.wait(timeout=left)
except subprocess.TimeoutExpired:
    p.kill(); p.wait()
    try:
        os.remove(mp4)   # a file cut off mid-write does not play
    except OSError:
        pass
print(f"[finalize] video exit {p.returncode}", flush=True)
out["video"] = bool(read("video.json").get("video")) and os.path.exists(mp4)
out["video_pending"] = False
write_final(out)
PY
exit 0
