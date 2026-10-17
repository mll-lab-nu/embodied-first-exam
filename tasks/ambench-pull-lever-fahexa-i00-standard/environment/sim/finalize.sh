#!/bin/sh
# [[verifier.collect]] hook, run inside the `sim` sidecar once Harbor has stopped the agent's container.
#   1. `rcb_limited.py end` (the shared first half, docs/STANDARD_MODE.md §13.3): SIGUSR1 to the service, which ends
#      the episode, writes trajectory.npz + episode.json (live result, final-state hash) and exits, releasing the
#      simulator. It waits through a crash-recovery resume (no PID file until the service is ready again), signals only
#      the newest service process, resends every 30 s, and exits 2 when final.json already holds the verdict (the
#      service gave up after crashes): that verdict stays, nothing is replayed.
#   2. replay the trajectory from the frozen instance in TWO fresh processes with the tooling's own `replay` CLI (the
#      privileged verifier's check, camera-free like the live service's physics; on Isaac only the first replay in a
#      process is bit-exact): `deterministic` = both fresh processes reach the same outcome; their end-state hashes
#      (`state_identical`) and live == replay (`live_matches_replay`) are reported, never decisive (a rare race leaves
#      the last bits different under Harbor; docs/benchmarks/ambench.md, Determinism). Then the `film` CLI draws the
#      same rows through the render worker into replay.mp4 (an illustration: it never decides anything, and its time
#      limit only costs the video).
#   3. merge everything into final.json, the only thing the verifier sandbox grades. final.json is always replaced
#      atomically (a temporary file + rename), so the verifier never reads a half-written one.
# A replay is the infrastructure's job: the trajectory was recorded by this trusted service. A replay process that ends
# without a result (Isaac died at startup, out of memory, its time limit) is retried once when it did not time out; if it
# still has no result, final.json says `replay_error` and `infra_error` = 1 (no verdict on the agent), never a silent 0.
# Time: the hook has HOOK_BUDGET_S (task.toml's [[verifier.collect]] timeout_sec; keep the two equal). Each replay gets
# what is left before that deadline, minus MERGE_MARGIN_S for step 3, shared between the replays still to run: a replay
# that is too slow is ended here and recorded, instead of Harbor killing the hook and leaving an unfinalized final.json.
set -u
DATA="${RCB_DATA:-/data}"; TOOL="${RCB_TOOL:?}"; INSTANCE="${RCB_INSTANCE:?}"
HOOK_BUDGET_S="${RCB_COLLECT_TIMEOUT_S:-7200}"; MERGE_MARGIN_S=300; T0=$(date +%s)
# A resume replays the whole episode first (~10-15 control steps/s); the two replays below need about as long each.
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
    if not isinstance(out, dict): out = {}
except Exception:
    out = {}
out.update({"finalized": True, "success": False, "replay_success": False, "deterministic": False, "infra_error": 1,
            "error": "collect hook: the sim service did not end and dump the episode in time"})
tmp = f"{p}.{os.getpid()}.tmp"
with open(tmp, "w") as f:
    json.dump(out, f); f.flush(); os.fsync(f.fileno())
os.replace(tmp, p)
print(json.dumps(out))
PY
    exit 0
fi
echo "[finalize] episode dumped; replaying twice in fresh processes"
rm -f "$DATA/replay1.json" "$DATA/replay2.json" "$DATA/replay1.rc" "$DATA/replay2.rc" "$DATA/replay1.gpu" "$DATA/replay2.gpu"

has_result() {   # the replay CLI printed its result line (a crash at Isaac's shutdown after that line still counts)
    grep -q '"state_sha"' "$1" 2>/dev/null
}

gpu_faults() {   # gpu_faults <file>...: the lines reporting a GPU fault (rcb_ambench.GPU_FAULT: PhysX kernels that failed to
                 # launch, CUDA out of memory) in a process's output; PhysX steps on without them, so such a run is not a replay
    python - "$TOOL" "$@" <<'PY'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("rcb_ambench", sys.argv[1]); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
n = 0
for f in sys.argv[2:]:
    try:
        n += m.count_gpu_faults(open(f, errors="replace").read())
    except OSError:
        pass
print(n)
PY
}

run_replay() {   # run_replay <n> <replays still to run, this one included> [extra replay arguments]
    n=$1; share=$2; shift 2
    for attempt in 1 2; do
        left=$(( T0 + HOOK_BUDGET_S - MERGE_MARGIN_S - $(date +%s) ))
        limit=$(( left / share ))
        if [ "$limit" -lt 60 ]; then
            echo "[finalize] replay $n: no time left before the hook's deadline"; echo "124 0 $limit" > "$DATA/replay$n.rc"; return
        fi
        t_start=$(date +%s)
        if command -v timeout >/dev/null 2>&1; then
            RCB_SESSION_LOG= timeout -k 30 "$limit" python "$TOOL" replay --instance "$INSTANCE" --traj "$DATA/trajectory.npz" "$@" > "$DATA/replay$n.json" 2> "$DATA/replay$n.try.log"
        else
            RCB_SESSION_LOG= python "$TOOL" replay --instance "$INSTANCE" --traj "$DATA/trajectory.npz" "$@" > "$DATA/replay$n.json" 2> "$DATA/replay$n.try.log"
        fi
        rrc=$?; took=$(( $(date +%s) - t_start ))
        cat "$DATA/replay$n.try.log" >> "$DATA/replay$n.log"
        nf=$(gpu_faults "$DATA/replay$n.try.log" "$DATA/replay$n.json"); nf=${nf:-0}
        echo "$rrc $took $limit" > "$DATA/replay$n.rc"                 # exit code, seconds it ran, its limit
        echo "$nf" > "$DATA/replay$n.gpu"                               # GPU faults in this attempt's output
        echo "[finalize] replay $n attempt $attempt exit $rrc after ${took} s (limit ${limit} s), GPU faults $nf"
        if has_result "$DATA/replay$n.json" && [ "$nf" = 0 ]; then return; fi
        if has_result "$DATA/replay$n.json"; then
            echo "[finalize] replay $n ran with $nf GPU fault(s): not a replay of the trajectory" >> "$DATA/replay$n.log"; continue
        fi
        # out of time (124, or 137 when it had to be killed at the limit): a second attempt would be too. Any other end
        # without a result (a crash at Isaac's start, the out-of-memory killer's 137) gets one more attempt.
        if [ "$rrc" = 124 ] || { [ "$rrc" = 137 ] && [ "$took" -ge "$limit" ]; }; then return; fi
        echo "[finalize] replay $n ended without a result" >> "$DATA/replay$n.log"
    done
}

# A host systemd reload while this long-running container is up (a snap or apt update, with Docker's systemd cgroup
# driver) makes the GPU refuse processes started afterwards: record that as an infrastructure failure, not the agent's 0.
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
    : > "$DATA/replay1.log"; : > "$DATA/replay2.log"
    run_replay 1 3
    if has_result "$DATA/replay1.json" && [ "$(cat "$DATA/replay1.gpu" 2>/dev/null)" = 0 ]; then
        run_replay 2 2
    else
        echo "[finalize] replay 1 gave no result: replay 2 not run (no verdict either way)"
    fi
    # the illustration: the same rows drawn by the render worker (never decides; a time-out or a crash only costs it)
    left=$(( T0 + HOOK_BUDGET_S - MERGE_MARGIN_S - $(date +%s) ))
    if has_result "$DATA/replay1.json" && [ "$left" -gt 300 ]; then
        RCB_SESSION_LOG= timeout -k 30 "$left" python "$TOOL" film --instance "$INSTANCE" --traj "$DATA/trajectory.npz" --video "$DATA/replay.mp4" > "$DATA/film.json" 2>> "$DATA/film.log" || echo "[finalize] filming failed (exit $?): no video"
    fi
else
    echo '{"gpu_lost": true}' > "$DATA/replay1.json"; echo '{"gpu_lost": true}' > "$DATA/replay2.json"
fi
python - <<'PY'
import json, os
d = os.environ.get("RCB_DATA", "/data")
def last_json(name):
    out = {}
    try:
        for line in open(os.path.join(d, name)):
            if line.strip().startswith("{"):
                try:
                    v = json.loads(line)
                except ValueError:
                    continue
                if isinstance(v, dict): out = v
    except Exception:
        pass
    return out
def exit_info(n):
    """(exit code, timed out) of replay n's last attempt; (None, False) when it was never run."""
    try:
        rc, took, limit = (int(x) for x in open(os.path.join(d, f"replay{n}.rc")).read().split()[:3])
        return rc, rc == 124 or (rc == 137 and took >= limit)
    except Exception:
        return None, False
def result(r):
    """The replay's own result (the first entry of `replays`), or None when the process printed none."""
    reps = r.get("replays")
    ok = isinstance(reps, list) and reps and isinstance(reps[0], dict) and reps[0].get("state_sha")
    return reps[0] if ok else None
out = {"finalized": True, "replay_success": False, "deterministic": False, "video": False}
errors = []
try:
    ep = json.load(open(os.path.join(d, "episode.json")))
    if not isinstance(ep, dict): raise ValueError("not an object")
    out.update(ep)
except Exception as exc:
    errors.append(f"no episode.json: {exc!r}")
def faults(n):
    """GPU faults in replay n's last attempt (rcb_ambench.GPU_FAULT); 0 when it was never run."""
    try:
        return int(open(os.path.join(d, f"replay{n}.gpu")).read().split()[0])
    except Exception:
        return 0
r1, r2 = last_json("replay1.json"), last_json("replay2.json")
gpu = [faults(1), faults(2)]
out["replay_gpu_faults"] = gpu
a, b = (result(r1) if not gpu[0] else None), (result(r2) if not gpu[1] else None)   # a run with GPU faults is no replay
gpu_lost = bool(r1.get("gpu_lost"))
out["replay_rc"] = [exit_info(1)[0], exit_info(2)[0]]
if not gpu_lost:
    for n, r, res in ((1, r1, a), (2, r2, b)):
        if res is None:
            rc, timed_out = exit_info(n)
            why = "not run" if rc is None else f"exit code {rc}" + (", its time limit" if timed_out else "")
            if gpu[n - 1]: why += f", {gpu[n - 1]} GPU fault(s) in its output"
            errors.append(f"replay {n} gave no result ({why}" + (f": {str(r['error'])[:200]}" if r.get("error") else "") + ")")
            if timed_out: out["replay_timed_out"] = True
            if n == 1: break                    # replay 2 is not run after a replay 1 without a result
if any(isinstance(r, dict) and r.get("instance_matches") is False for r in (r1, r2)):
    out["instance_mismatch"] = True                 # this host rebuilt another start than the frozen one: no verdict on the agent
    errors.append("the rebuilt scene differs from the frozen instance (instance_matches false)")
out["replay_success"] = bool(a and a.get("success")) and bool(b and b.get("success"))
out["replay_sha"], out["replay_sha2"] = (a or {}).get("state_sha"), (b or {}).get("state_sha")
out["state_identical"] = bool(a and b) and a["state_sha"] == b["state_sha"]   # reported, does not decide (ambench.md)
out["deterministic"] = bool(a and b) and bool(a.get("success")) == bool(b.get("success"))   # the outcome repeats
out["live_matches_replay"] = bool(a) and a["state_sha"] == out.get("live_sha")
try:   # the live episode's own GPU faults (the service's output; the render worker logs elsewhere: RCB_RENDER_LOG)
    import importlib.util
    spec = importlib.util.spec_from_file_location("rcb_ambench", os.environ["RCB_TOOL"]); M = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(M)
    out["live_gpu_faults"] = M.count_gpu_faults(open(os.path.join(d, "server.log"), errors="replace").read())
except Exception as exc:
    out["live_gpu_faults"] = 0; print(f"[finalize] could not count the live episode's GPU faults: {exc!r}")
if out["live_gpu_faults"] and a and b and bool(out.get("success")) != out["replay_success"]:
    # the live physics ran without some of its GPU kernels and ended otherwise than the trajectory's faithful replays
    errors.append(f"the live episode logged {out['live_gpu_faults']} GPU fault(s) and its outcome differs from the replays'")
elif out["live_gpu_faults"] and not out.get("success"):
    # the agent acted in closed loop on faulted physics: a failed live episode is not a verdict on the agent, even when
    # its replays fail too (the agent's later rows answered states the faithful physics never reaches)
    errors.append(f"the live episode logged {out['live_gpu_faults']} GPU fault(s) and did not succeed")
mp4 = os.path.join(d, "replay.mp4")
out["video"] = os.path.exists(mp4) and os.path.getsize(mp4) > 0
film = (last_json("film.json").get("film") or {})
out["video_episode_success"] = bool(film.get("success")); out["video_matches_replay"] = bool(a) and film.get("state_sha") == a.get("state_sha")
try:   # instance.json "determinism": "verdict" = PhysX does not replay this task bit for bit: the live episode decides
    verdict_mode = json.load(open(os.environ.get("RCB_INSTANCE", "/srv/instance.json"))).get("determinism") == "verdict"
except Exception:
    verdict_mode = False
out["determinism_verdict_mode"] = verdict_mode
out["graded_by"] = "live" if verdict_mode else "replay"
if gpu_lost:
    out["gpu_lost"] = True
    if not verdict_mode:
        out["infra_error"] = 1
        out["error"] = "infrastructure: the GPU was not accessible to new processes in the sim sidecar, so the episode could not be replayed"
elif errors:
    out["replay_error"] = "; ".join(errors)
    if not verdict_mode:
        # the trajectory is the trusted service's own record: a replay (or a dump) that produced nothing is not the agent's 0
        out["infra_error"] = 1
        out["error"] = "infrastructure: the episode could not be replayed to a verdict: " + out["replay_error"]
if verdict_mode and out.get("live_gpu_faults"):
    # graded by its live episode, whose physics ran without some of its GPU kernels: no verdict on the agent
    out["infra_error"] = 1
    out["error"] = (f"infrastructure: the live episode, which decides this task, logged {out['live_gpu_faults']} GPU fault(s) "
                    "(rcb_ambench.GPU_FAULT)")
out["finalized"] = True
p = os.path.join(d, "final.json"); tmp = f"{p}.{os.getpid()}.tmp"
with open(tmp, "w") as f:
    json.dump(out, f); f.flush(); os.fsync(f.fileno())
os.replace(tmp, p)
print(json.dumps(out))
PY
