#!/bin/sh
# [[verifier.collect]] hook, run inside the `sim` sidecar once Harbor has stopped the agent's container.
#   1. `rcb_limited.py end` (docs/STANDARD_MODE.md §13.3): SIGUSR1 to the service, which ends the episode if the
#      agent had not (reason "timeout"), writes trajectory.npz + episode.json (live verdict, final-state hash) and exits.
#      It exits 2 when final.json already holds the verdict (the service gave up after crashes): that verdict stays.
#   2. replay the trajectory from the frozen instance in TWO fresh processes (`rcb_labutopia.py replay`, the privileged
#      verifier's replay): on Isaac Sim only a fresh process repeats an episode bit for bit, so determinism = fresh
#      process == fresh process; live_matches_replay = live == replay.
#   3. merge everything into final.json, the only thing the verifier sandbox grades (written whole: temporary file,
#      then rename);
#   4. a third replay renders replay.mp4, after the verdict is on disk (it never changes it).
set -u
DATA="${RCB_DATA:-/data}"; TOOL="${RCB_TOOL:-/srv/rcb_labutopia.py}"; INSTANCE="${RCB_INSTANCE:-/srv/instance.json}"
# Time. The hook has HOOK_BUDGET_S (its [[verifier.collect]] timeout_sec in task.toml; the generator checks the two agree):
#   9000 s = 2700 (the end of the episode, through a resume) + 2 x 2400 (the verdict replays: under a minute to start
#   without the renderer, then at most 36000 rows at about 200 control steps/s = 180 s; the limit is ten times that,
#   the privileged grader's)
#   + the video replay, which gets what is left (at most 1800 s) + 300 s of margin.
# A replay that passes its limit is killed (`timeout`) and recorded as a replay without a result: replay_failed,
# infra_error = 1 -- the trajectory was recorded by the service, so a replay that cannot run is never the agent's 0.
HOOK_BUDGET_S="${RCB_COLLECT_BUDGET_S:-9000}"; REPLAY_TIMEOUT_S="${RCB_REPLAY_TIMEOUT_S:-2400}"
VIDEO_TIMEOUT_S="${RCB_VIDEO_TIMEOUT_S:-1800}"; MARGIN_S=300
T0=$(date +%s)
# The service may still be starting (its first start prepares the scene, 5 to 27 minutes) or resuming after a crash.
python /srv/rcb_limited.py end "$DATA" --timeout "${RCB_COLLECT_END_TIMEOUT_S:-2700}"; rc=$?
if [ "$rc" = 2 ]; then
    echo "[finalize] final.json already holds the verdict; no replay"; exit 0
fi
if [ "$rc" != 0 ]; then
    echo "[finalize] the service did not end and dump the episode in time (rc $rc): an infrastructure failure"
    python - <<'PY'
import json, os
d = os.environ.get("RCB_DATA", "/data"); p = os.path.join(d, "final.json")
try:
    out = json.load(open(p))
    assert isinstance(out, dict)
except Exception:
    out = {}
out.update({"finalized": True, "success": False, "replay_success": False, "deterministic": False, "infra_error": 1,
            "error": "collect hook: the sim service did not end and dump the episode in time"})
json.dump(out, open(p + ".tmp", "w")); os.replace(p + ".tmp", p)   # atomic: a kill never leaves half a final.json
print(json.dumps(out))
PY
    exit 0
fi
replay() {  # <n> <limit s> [--video FILE]: one replay in a fresh process; its result in $DATA/replay<n>.json, its exit
    n=$1; lim=$2; shift 2   # status in $DATA/replay<n>.rc (124 / 137: it ran into its limit)
    if command -v timeout > /dev/null 2>&1; then
        RCB_SESSION_LOG= timeout -k 30 "$lim" python "$TOOL" replay --instance "$INSTANCE" --traj "$DATA/trajectory.npz" \
            --out "$DATA/replay$n.json" "$@" > /dev/null 2> "$DATA/replay$n.log"
    else
        RCB_SESSION_LOG= python "$TOOL" replay --instance "$INSTANCE" --traj "$DATA/trajectory.npz" \
            --out "$DATA/replay$n.json" "$@" > /dev/null 2> "$DATA/replay$n.log"
    fi
    rrc=$?; echo "$rrc" > "$DATA/replay$n.rc"
    echo "[finalize] replay $n exit $rrc (limit $lim s)"
}
echo "[finalize] episode dumped; replaying twice in fresh processes"
rm -f "$DATA/replay1.json" "$DATA/replay2.json" "$DATA/replay3.json" "$DATA/replay1.rc" "$DATA/replay2.rc" "$DATA/replay3.rc"
# A host systemd reload while this long-running container is up (a snap or apt update, with Docker's systemd cgroup
# driver) makes the GPU refuse processes started afterwards: that is recorded as an infrastructure failure, not as the
# agent's 0 (the same check as RoboLab's hook).
rm -f "$DATA/gpu_lost"
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
    replay 1 "$REPLAY_TIMEOUT_S"
    replay 2 "$REPLAY_TIMEOUT_S"
else
    touch "$DATA/gpu_lost"
fi
python - <<'PY'
import json, os
d = os.environ.get("RCB_DATA", "/data")
def result(name):
    try:
        v = json.load(open(os.path.join(d, name)))
    except (OSError, ValueError):
        return {}
    return v if isinstance(v, dict) else {}
def rc(n):
    try:
        return int(open(os.path.join(d, f"replay{n}.rc")).read().strip())
    except (OSError, ValueError):
        return None
out = {"replay_success": False, "deterministic": False, "video": False}
no_episode = None
try:
    ep = json.load(open(os.path.join(d, "episode.json")))
    assert isinstance(ep, dict), "episode.json is not an object"
    out.update(ep)
except Exception as exc:
    no_episode = f"no episode.json: {exc!r}"
a, b = result("replay1.json"), result("replay2.json")
out["replay_success"] = bool(a.get("success")) and bool(b.get("success"))
out["replay_score"] = float(min(a.get("score") or 0.0, b.get("score") or 0.0))
out["replay_sha"], out["replay_sha2"] = a.get("state_sha"), b.get("state_sha")
out["deterministic"] = bool(a.get("state_sha")) and a.get("state_sha") == b.get("state_sha")
out["live_matches_replay"] = bool(a.get("state_sha")) and a.get("state_sha") == out.get("live_sha")
out["replay_rc"] = [rc(1), rc(2)]   # the record; a result on disk counts whatever the exit status (it is written before the
                                    # simulator shuts down)
out["replay_start_exact"] = bool(a.get("start_exact")) and bool(b.get("start_exact"))
if os.path.exists(os.path.join(d, "gpu_lost")):
    out.update({"gpu_lost": 1, "replay_failed": 1, "infra_error": 1,
                "error": "the GPU was not accessible to new processes in the sim sidecar: the episode could not be replayed"})
elif not (a.get("state_sha") and b.get("state_sha")):  # a replay process died (it crashed or timed out): not the agent's 0
    timed_out = any(r in (124, 137) for r in out["replay_rc"])
    out.update({"replay_failed": 1, "infra_error": 1, "replay_timed_out": int(timed_out),
                "error": "a replay process gave no result" + (" within its time limit" if timed_out else "")
                         + f" (exit status {out['replay_rc']}; replay1.log / replay2.log)"})
elif not (a.get("instance_ok") and b.get("instance_ok")):  # the image no longer builds the frozen start: not the agent's 0
    out.update({"instance_mismatch": 1, "infra_error": 1, "error": "a replay did not start in the instance's t = 0 state"})
if no_episode:  # the service's own record of the live episode is unreadable: no verdict on the agent
    out.update({"success": False, "infra_error": 1, "error": no_episode})
out["finalized"] = True
p = os.path.join(d, "final.json")
json.dump(out, open(p + ".tmp", "w")); os.replace(p + ".tmp", p)   # atomic: a kill never leaves half a final.json
print(json.dumps(out))
PY
# The video, with what is left of the hook's time (the verdict is on disk; nothing below can change it).
left=$(( HOOK_BUDGET_S - MARGIN_S - ($(date +%s) - T0) )); [ "$left" -gt "$VIDEO_TIMEOUT_S" ] && left=$VIDEO_TIMEOUT_S
if [ ! -e "$DATA/gpu_lost" ] && [ "$left" -ge 120 ]; then
    replay 3 "$left" --video "$DATA/replay.mp4"
else
    echo "[finalize] no video replay ($left s left)"
fi
python - <<'PY'
import json, os
d = os.environ.get("RCB_DATA", "/data")
try:
    shown = json.load(open(os.path.join(d, "replay3.json"))).get("video")
except (OSError, ValueError, AttributeError):
    shown = False
if shown:
    p = os.path.join(d, "final.json"); out = json.load(open(p)); out["video"] = True
    json.dump(out, open(p + ".tmp", "w")); os.replace(p + ".tmp", p)
PY
