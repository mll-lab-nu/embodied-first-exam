#!/bin/sh
# [[verifier.collect]] hook, run inside the `sim` sidecar once Harbor has stopped the agent's container. The trial is
# graded by its LIVE episode, the one the agent ran, with no grading replay (owner 2026-10-17).
#   1. `rcb_limited.py end` (the shared first half, docs/protocol/standard_mode.md §13.3): SIGUSR1 to the service, which ends
#      the episode, writes trajectory.npz + episode.json (the live result: AM-Bench's success check after every control
#      step; the end-state hash) and exits, releasing the GPU. It waits through a crash-recovery resume (no PID file until
#      the service is ready again), signals only the newest service process, resends every 30 s, and exits 2 when
#      final.json already holds the verdict (the service gave up: after crashes, or because the frozen instance did not
#      rebuild to its recorded hash at the episode's start, `instance_mismatch`): that verdict stays.
#   2. final.json = the live record (episode.json) + `graded_by` "live", `replays` 0, `finalized`: written whole (a
#      temporary file + rename) BEFORE the video, with `video_pending` true. The live episode's own GPU faults (PhysX
#      kernels that failed to launch, CUDA out of memory: rcb_ambench.GPU_FAULT, counted in the service's output) make it
#      no verdict on the agent (`infra_error` = 1): its physics ran without some of its kernels.
#   3. the video: ONE `film` pass (the tooling's CLI: the recorded rows in a fresh process, the onboard cameras drawn by
#      the render worker) into replay.mp4, after the verdict. It decides nothing: no success or hash of it is compared,
#      it is not run again, and its failure or its time limit costs the video only (`video` false), never infra. The
#      live service does not film: rendering inside the physics process makes AM-Bench's GPU physics timing-dependent,
#      and its cameras are drawn by a second Isaac process only when the agent asks for a frame.
# Time: the hook has HOOK_BUDGET_S (task.toml's [[verifier.collect]] timeout_sec; keep the two equal): the episode end
# (up to RCB_COLLECT_END_TIMEOUT_S = 2700 s through a resume) + the film (at most FILM_LIMIT_S: an Isaac start and the
# render worker's, 1.5-6 min, + at most one episode, 7200 control steps of the longest task at 10-15 steps/s) + a margin.
# Before 2026-10-17 this hook also replayed the trajectory in two camera-free fresh processes (7200 s budget).
set -u
SRV="${RCB_SRV:-/srv}"; DATA="${RCB_DATA:-/data}"; TOOL="${RCB_TOOL:?}"; INSTANCE="${RCB_INSTANCE:?}"
HOOK_BUDGET_S="${RCB_COLLECT_TIMEOUT_S:-4800}"; FILM_LIMIT_S="${RCB_FILM_LIMIT_S:-1800}"; T0=$(date +%s)
python "$SRV/rcb_limited.py" end "$DATA" --timeout "${RCB_COLLECT_END_TIMEOUT_S:-2700}"; rc=$?
case "$rc" in
    0) echo "[finalize] episode dumped: graded by the live episode (no replay)" ;;
    2) echo "[finalize] final.json already holds the verdict (the service gave up); kept" ;;
    *) echo "[finalize] the service did not end and exit in time (rc $rc): its episode.json decides if it dumped one, else infra" ;;
esac
END_RC="$rc" python - <<'PY'
import importlib.util, json, os
d = os.environ.get("RCB_DATA", "/data"); p = os.path.join(d, "final.json"); rc = os.environ.get("END_RC")
def read(name):
    try:
        v = json.load(open(os.path.join(d, name)))
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}
live = {"graded_by": "live", "replays": 0, "video": False, "video_pending": True, "video_source": "render"}
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
    try:   # the live episode's own GPU faults (the service's output; the render worker logs elsewhere: RCB_RENDER_LOG)
        spec = importlib.util.spec_from_file_location("rcb_ambench", os.environ["RCB_TOOL"]); M = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(M)
        # run.sh appends every start of the service to server.log: only the episode's physics counts, i.e. from the
        # service's marker (printed before EP.begin) to the end of that start (run.sh's "[sim] service exited" line);
        # a start that died while building the scene (a CUDA out-of-memory there, then restarted) never printed it
        MARK, EXIT = "[rcb] the episode's physics starts", "[sim] service exited ("
        n, on = 0, False
        for line in open(os.path.join(d, "server.log"), errors="replace"):
            if MARK in line:
                on = True; continue
            if line.startswith(EXIT):
                on = False; continue
            if on:
                n += M.count_gpu_faults(line)
        out["live_gpu_faults"] = n
    except Exception as exc:
        out["live_gpu_faults"] = 0; print(f"[finalize] could not count the live episode's GPU faults: {exc!r}")
    if out["live_gpu_faults"] and not out.get("infra_error"):
        out["infra_error"] = 1
        out["error"] = (f"infrastructure: the live episode logged {out['live_gpu_faults']} GPU fault(s) (rcb_ambench.GPU_FAULT): "
                        "its physics ran without some of its GPU kernels")
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
# the video: one film pass, after the verdict, only when the service left a trajectory
left=$(( T0 + HOOK_BUDGET_S - 60 - $(date +%s) )); limit=$FILM_LIMIT_S
if [ "$left" -lt "$limit" ]; then limit=$left; fi
frc=none
if [ "$limit" -ge 120 ] && [ -s "$DATA/trajectory.npz" ]; then
    RCB_SESSION_LOG= timeout -k 30 "$limit" python "$TOOL" film --instance "$INSTANCE" --traj "$DATA/trajectory.npz" --video "$DATA/replay.mp4" > "$DATA/film.json" 2> "$DATA/film.log"; frc=$?
fi
echo "[finalize] film exit $frc (limit ${limit} s)"
FRC="$frc" python - <<'PY'
import json, os
d = os.environ.get("RCB_DATA", "/data"); p = os.path.join(d, "final.json")
try:
    out = json.load(open(p))
    if not isinstance(out, dict): raise ValueError("not an object")
except Exception as exc:
    print(f"[finalize] final.json unreadable, video fields not added: {exc!r}"); raise SystemExit
res = {}
try:
    for line in open(os.path.join(d, "film.json")):
        if line.strip().startswith("{"):
            res = json.loads(line)
except Exception:
    pass
mp4 = os.path.join(d, "replay.mp4")
ok = os.environ.get("FRC") == "0" and bool(res.get("film")) and os.path.isfile(mp4) and os.path.getsize(mp4) > 0
out.update({"video": ok, "video_pending": False})
if not ok:
    out["video_error"] = f"the film pass gave no video (exit {os.environ.get('FRC')})"
tmp = f"{p}.{os.getpid()}.tmp"
with open(tmp, "w") as f:
    json.dump(out, f); f.flush(); os.fsync(f.fileno())
os.replace(tmp, p)
print(json.dumps({k: out.get(k) for k in ("success", "infra_error", "live_gpu_faults", "video", "video_error")}))
PY
exit 0
