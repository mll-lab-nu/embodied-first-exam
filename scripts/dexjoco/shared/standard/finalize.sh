#!/bin/sh
# [[verifier.collect]] hook, run inside the `sim` sidecar once Harbor has stopped the agent's container.
#   1. `rcb_limited.py end` (docs/STANDARD_MODE.md §13.3): SIGUSR1 to the service, which ends the episode if the
#      agent had not (reason "timeout"), writes trajectory.npz + episode.json (live verdict, final-state hash) and exits.
#      It exits 2 when final.json already holds the verdict (the service gave up after crashes): that verdict stays.
#   2. replay the trajectory from the frozen instance in TWO fresh processes (`rcb_dexjoco.py replay`, the privileged
#      verifier's replay): determinism = fresh process == fresh process; live_matches_replay = live == replay.
#   3. merge everything into final.json, the only thing the verifier sandbox grades (`finalized`: the verdict is in);
#   4. a third replay renders replay.mp4, after the verdict is on disk (it never changes it).
# Time: the hook has RCB_COLLECT_BUDGET_S (the task's [[verifier.collect]] timeout_sec). The recorded episode has no step
# cap; a replay steps the physics the live episode stepped, without rendering or waiting for the agent, so the two
# replays together need at most twice the time the service spent stepping. They run one after the other (side by side
# they are no faster: the sidecar has 4 CPUs and each process runs OpenBLAS on OPENBLAS_NUM_THREADS = 4 threads, the
# count the service ran with, which the result depends on). A replay still running a minute before the budget ends is
# stopped: a replay without a result is an infrastructure failure (infra_error = 1), never the agent's 0. The video
# gets what is left, at most RCB_COLLECT_VIDEO_MAX_S, and is stopped at that. final.json is always written whole
# (temporary file + rename). A replay that ran fewer than 4 OpenBLAS threads (fewer than 4 CPUs visible to the sidecar;
# the service itself refuses to start an episode like that) is no verdict either: too_few_cpus = 1, infra_error = 1.
set -u
DATA="${RCB_DATA:-/data}"; TOOL="${RCB_TOOL:?}"; INSTANCE="${RCB_INSTANCE:?}"; TASK="${RCB_TASK:?}"
RCB_HOOK_T0="$(date +%s)"; export RCB_HOOK_T0
python /srv/rcb_limited.py end "$DATA" --timeout "${RCB_COLLECT_END_TIMEOUT_S:-900}"; rc=$?
if [ "$rc" = 2 ]; then
    echo "[finalize] final.json already holds the verdict; no replay"; exit 0
fi
RCB_END_RC="$rc" python - <<'PY'
import json, os, subprocess, sys, time

d = os.environ.get("RCB_DATA", "/data")
tool, instance, task = os.environ["RCB_TOOL"], os.environ["RCB_INSTANCE"], os.environ["RCB_TASK"]
t0 = float(os.environ.get("RCB_HOOK_T0") or time.time())
hard = t0 + float(os.environ.get("RCB_COLLECT_BUDGET_S") or 7200) - 60.0   # everything is done a minute early
video_max = float(os.environ.get("RCB_COLLECT_VIDEO_MAX_S") or 1200)
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


def start(n, *extra):
    """One replay in a fresh process, its result in replay<n>.json, its output in replay<n>.log."""
    env = dict(os.environ, RCB_SESSION_LOG="")
    log = open(os.path.join(d, f"replay{n}.log"), "w")
    return subprocess.Popen([sys.executable, tool, "replay", "--task", task, "--instance", instance,
                             "--traj", os.path.join(d, "trajectory.npz"), "--repeat", "1",
                             "--out", os.path.join(d, f"replay{n}.json"), *extra],
                            stdout=subprocess.DEVNULL, stderr=log, env=env)


def wait(procs, deadline):
    """Wait for every process until `deadline`; kill what is still running then. Returns the names that timed out."""
    late = []
    for n, p in procs.items():
        try:
            p.wait(timeout=max(0.0, deadline - time.time()))
        except subprocess.TimeoutExpired:
            p.kill(); p.wait(); late.append(n)
        print(f"[finalize] replay {n} exit {p.returncode}" + (" (stopped: out of time)" if n in late else ""), flush=True)
    return late


if os.environ.get("RCB_END_RC") != "0":
    print("[finalize] the service did not end and dump the episode in time: an infrastructure failure", flush=True)
    out = read("final.json")
    out.update({"finalized": True, "success": False, "replay_success": False, "deterministic": False, "infra_error": 1,
                "error": "collect hook: the sim service did not end and dump the episode in time"})
    write_final(out)
    sys.exit(0)

print("[finalize] episode dumped; replaying twice in fresh processes", flush=True)
for n in (1, 2, 3):
    try:
        os.remove(os.path.join(d, f"replay{n}.json"))
    except OSError:
        pass
late = wait({1: start(1)}, hard - 30.0)
late = late or wait({2: start(2)}, hard - 30.0)   # no second replay once the first ran out of time
out = {"replay_success": False, "deterministic": False, "video": False}
ep = read("episode.json")
if ep:
    out.update(ep)
else:
    out["error"] = "no episode.json"
a, b = read("replay1.json"), read("replay2.json")
out["replay_success"] = bool(a.get("success")) and bool(b.get("success"))
out["replay_sha"], out["replay_sha2"] = a.get("state_sha"), b.get("state_sha")
out["deterministic"] = bool(a.get("state_sha")) and a.get("state_sha") == b.get("state_sha")
out["live_matches_replay"] = bool(a.get("state_sha")) and a.get("state_sha") == out.get("live_sha")
if not (a.get("state_sha") and b.get("state_sha")):  # a replay process died (it crashed or ran out of time): not the agent's 0
    out.update({"replay_failed": 1, "infra_error": 1, "replay_timed_out": int(bool(late)),
                "error": ("a replay did not finish inside the collect hook's time" if late
                          else "a replay process gave no result (replay1.log / replay2.log)")})
elif not (a.get("instance_ok") and b.get("instance_ok")):  # the image no longer builds the frozen start: not the agent's 0
    out.update({"instance_mismatch": 1, "infra_error": 1, "error": "a replay did not start in the instance's t = 0 state"})
if not (a.get("threads_ok", 1) and b.get("threads_ok", 1)) or out.get("threads_ok", 1) == 0:
    # the live episode or a replay ran fewer than 4 OpenBLAS threads: other numerics than the references', no verdict
    out.update({"too_few_cpus": 1, "infra_error": 1, "replay_blas_threads": [a.get("blas_threads"), b.get("blas_threads")],
                "error": "fewer than 4 OpenBLAS threads (fewer than 4 CPUs visible to the sim sidecar)"})
if not ep:  # the service's own record of the live episode is unreadable: no verdict on the agent
    out["infra_error"] = 1
out["finalized"] = True
write_final(out)   # the verdict: nothing below changes it

left = min(video_max, hard - time.time() - 15.0)
if left < 60.0:
    print("[finalize] no time left for replay.mp4", flush=True)
    sys.exit(0)
mp4 = os.path.join(d, "replay.mp4")
# the video stops itself 30 s before its time is up (the frames so far stay playable); the kill is the backstop
if wait({3: start(3, "--video", mp4, "--video-deadline-s", str(int(left - 30.0)))}, time.time() + left):
    try:
        os.remove(mp4)   # a file cut off mid-write does not play
    except OSError:
        pass
if read("replay3.json").get("video"):
    out["video"] = True
    write_final(out)
PY
exit 0
