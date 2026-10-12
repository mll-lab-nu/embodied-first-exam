#!/bin/sh
# [[verifier.collect]] hook, run inside the `sim` sidecar once Harbor has stopped the agent's container.
#   1. `rcb_limited.py end` (the shared first half, docs/STANDARD_MODE.md §13.3): SIGUSR1 to the service, which ends
#      the episode, writes trajectory.npz + episode.json (live result, final-state hash) and exits, releasing the
#      simulator. It waits through a crash-recovery resume (no PID file until the service is ready again), signals only
#      the newest service process, resends every 30 s, and exits 2 when final.json already holds the verdict (the
#      service gave up after crashes): that verdict stays, nothing is replayed.
#   2. replay the trajectory from the frozen instance ONCE, in a fresh process, with the tooling's own `replay` CLI (the
#      privileged verifier's check; one replay since the owner's decision of 2026-10-12, two before): one successful
#      replay is enough, success = live success AND replay success (tests/grade.py). On Isaac only the first replay in a
#      process is bit-exact, hence the fresh process. What the replay is compared with is the live episode:
#      `live_matches_replay` = `state_identical` = `deterministic` = the replay ended in the live episode's state; reported,
#      never deciding. The replay also films replay.mp4; the tooling never lets the filming decide the replay's result.
#      A task whose physics does not replay bit for bit (instance.json "determinism": "verdict": GPU PhysX particles and
#      cloth, make_toast_random) is graded by the LIVE episode instead (`graded_by` "live", success = live_success; the
#      task is standard-only): its replay still runs and is reported (`replay_success`, `state_identical`,
#      `deterministic`: the replay reaches the live episode's verdict), and a replay that gives no result is recorded
#      (`replay_error`) without voiding the live verdict.
#   3. merge everything into final.json, the only thing the verifier sandbox grades. final.json is always replaced
#      atomically (a temporary file + rename), so the verifier never reads a half-written one.
# A replay is the infrastructure's job: the trajectory was recorded by this trusted service. A replay process that ends
# without a result (Isaac died at startup, out of memory, its time limit: Isaac does not exit after a fatal GPU error, it
# waits on a crash dialog, so only the time limit ends it) is run once more, unless the hook's own deadline ended it; if
# it still has no result, final.json says `replay_error` and `infra_error` = 1 (no verdict on the agent), never a silent 0.
# Time: the hook has HOOK_BUDGET_S (task.toml's [[verifier.collect]] timeout_sec; keep the two equal): 10800 s = the
# episode end (up to 2700 s through a resume) + ONE replay of up to 7200 s + 900 s; 18000 s with two replays, before
# 2026-10-12. The replay has the privileged verifier's allowance for a trajectory of its length (tests/grade.py
# replay_timeout: max(1800 s, 1200 s + actions / 2.5), 7200 s for the 15,000 actions an episode may have), and never more
# than what is left before the hook's deadline minus MERGE_MARGIN_S for step 3. Before 2026-10-12 a replay had its share
# of the whole remaining budget whatever the episode's length, so a hung Isaac held the hook for hours; now it is ended
# after the allowance and the replay is run once more if time is left. A replay that is too slow is ended here and
# recorded, instead of Harbor killing the hook and leaving an unfinalized final.json. An episode whose length cannot be
# read (no n_actions in episode.json) keeps the whole remaining budget.
set -u
DATA="${RCB_DATA:-/data}"; TOOL="${RCB_TOOL:?}"; TASK="${RCB_TASK:?}"; INSTANCE="${RCB_INSTANCE:?}"
HOOK_BUDGET_S="${RCB_COLLECT_TIMEOUT_S:-10800}"; MERGE_MARGIN_S=300; T0=$(date +%s)
# one replay's allowance: the same three numbers as tests/grade.py of the privileged twin (scripts/robodojo/tests checks)
REPLAY_FLOOR_S="${RCB_REPLAY_FLOOR_S:-1800}"; REPLAY_STARTUP_S="${RCB_REPLAY_STARTUP_S:-1200}"; REPLAY_MIN_RATE="${RCB_REPLAY_MIN_RATE:-2.5}"
# A resume replays the whole episode first (~7-11 actions/s); the replay below needs as long again.
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
rm -f "$DATA/replay1.json" "$DATA/replay2.json" "$DATA/replay1.rc" "$DATA/replay2.rc"   # replay2.*: none is written any more
# BOX: the replay's allowance in whole seconds for this episode's length; 0 = unknown (the whole remaining budget).
BOX=$(REPLAY_FLOOR_S="$REPLAY_FLOOR_S" REPLAY_STARTUP_S="$REPLAY_STARTUP_S" REPLAY_MIN_RATE="$REPLAY_MIN_RATE" python - <<'PY'
import json, math, os
try:
    n = json.load(open(os.path.join(os.environ.get("RCB_DATA", "/data"), "episode.json")))["n_actions"]
    if isinstance(n, bool) or not isinstance(n, int) or n < 0: raise ValueError(n)
    print(int(math.ceil(max(float(os.environ["REPLAY_FLOOR_S"]),
                            float(os.environ["REPLAY_STARTUP_S"]) + n / float(os.environ["REPLAY_MIN_RATE"])))))
except Exception:
    print(0)
PY
) || BOX=0
case "$BOX" in ''|*[!0-9]*) BOX=0 ;; esac
echo "[finalize] episode dumped; replaying once in a fresh process (allowance ${BOX} s; 0 = what is left of the hook's budget)"

has_result() {   # the replay CLI printed its result line (a crash at Isaac's shutdown after that line still counts)
    grep -q '"state_sha"' "$1" 2>/dev/null
}

run_replay() {   # run_replay <n> <replays still to run, this one included> [extra replay arguments]
    n=$1; share=$2; shift 2
    for attempt in 1 2; do
        left=$(( T0 + HOOK_BUDGET_S - MERGE_MARGIN_S - $(date +%s) ))
        limit=$(( left / share ))
        if [ "$limit" -lt 60 ]; then
            echo "[finalize] replay $n: no time left before the hook's deadline"
            # a first attempt that never ran is recorded as out of time; after a first attempt its own record stays
            if [ "$attempt" = 1 ]; then echo "124 0 $limit" > "$DATA/replay$n.rc"; fi
            return
        fi
        boxed=0   # 1: this attempt is limited by the replay's own allowance, not by the hook's deadline
        if [ "$BOX" -gt 0 ] && [ "$limit" -gt "$BOX" ]; then limit=$BOX; boxed=1; fi
        t_start=$(date +%s)
        if command -v timeout >/dev/null 2>&1; then
            RCB_SESSION_LOG= timeout -k 30 "$limit" python "$TOOL" replay --task "$TASK" --instance "$INSTANCE" --traj "$DATA/trajectory.npz" "$@" > "$DATA/replay$n.json" 2>> "$DATA/replay$n.log"
        else
            RCB_SESSION_LOG= python "$TOOL" replay --task "$TASK" --instance "$INSTANCE" --traj "$DATA/trajectory.npz" "$@" > "$DATA/replay$n.json" 2>> "$DATA/replay$n.log"
        fi
        rrc=$?; took=$(( $(date +%s) - t_start ))
        echo "$rrc $took $limit" > "$DATA/replay$n.rc"                 # exit code, seconds it ran, its limit
        echo "[finalize] replay $n attempt $attempt exit $rrc after ${took} s (limit ${limit} s)"
        if has_result "$DATA/replay$n.json"; then return; fi
        # out of time (124, or 137 when it had to be killed at the limit) at the hook's own deadline: a second attempt
        # would be too. Out of its own allowance with time left (a hung Isaac), and any other end without a result (a
        # crash at Isaac's start, the out-of-memory killer's 137), gets one more attempt.
        if [ "$rrc" = 124 ] || { [ "$rrc" = 137 ] && [ "$took" -ge "$limit" ]; }; then
            if [ "$boxed" != 1 ]; then return; fi
        fi
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
    : > "$DATA/replay1.log"
    run_replay 1 1 --video "$DATA/replay.mp4"       # the one replay: the whole remaining budget, filmed
    has_result "$DATA/replay1.json" || echo "[finalize] the replay gave no result (no verdict either way)"
else
    echo '{"gpu_lost": true}' > "$DATA/replay1.json"
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
errors = []            # the replays (no verdict on the agent when the replays decide)
episode_error = None   # no live record at all: never a verdict on the agent, whoever decides
try:
    ep = json.load(open(os.path.join(d, "episode.json")))
    if not isinstance(ep, dict): raise ValueError("not an object")
    out.update(ep)
except Exception as exc:
    episode_error = f"no episode.json: {exc!r}"
# ONE replay (the owner's decision of 2026-10-12; two before, replay2.json and `replay_sha2`): the list below has one entry
r1 = last_json("replay1.json")
a = result(r1)
gpu_lost = bool(r1.get("gpu_lost"))
out["replays"] = 1
out["replay_rc"] = [exit_info(1)[0]]
if not gpu_lost:
    for n, r, res in ((1, r1, a),):
        if res is None:
            rc, timed_out = exit_info(n)
            why = "not run" if rc is None else f"exit code {rc}" + (", its time limit" if timed_out else "")
            errors.append(f"replay {n} gave no result ({why}" + (f": {str(r['error'])[:200]}" if r.get("error") else "") + ")")
            if timed_out: out["replay_timed_out"] = True
live_success = bool(out.get("success"))   # episode.json's `success`: the live episode's (False when there is no record)
out["replay_success"] = bool(a and a.get("success"))
out["replay_sha"] = (a or {}).get("state_sha")
# what the one replay is compared with is the live episode: did it end in the live episode's state? Reported under the
# three names readers know (`live_matches_replay`, `state_identical`, `deterministic`); the verdict does not need it
out["live_matches_replay"] = bool(a) and a["state_sha"] == out.get("live_sha")
out["state_identical"] = out["live_matches_replay"]
try:   # instance.json "determinism": "verdict" = the physics does not replay bit for bit: the live episode decides
    verdict_mode = json.load(open(os.environ.get("RCB_INSTANCE", "/srv/instance.json"))).get("determinism") == "verdict"
except Exception:
    verdict_mode = False
out["determinism_verdict_mode"] = verdict_mode
out["graded_by"] = "live" if verdict_mode else "replay"
# graded by the live episode: `deterministic` = the replay reached the live episode's verdict (its end state differs by design)
out["deterministic"] = (bool(a) and bool(a.get("success")) == live_success) if verdict_mode else out["state_identical"]
# The live episode started from the frozen instance (the service is strict). A replay whose fresh process rebuilt the
# layout to another state (this GPU / driver does not reset the task reproducibly) cannot be compared with it: no verdict
# on the agent, an infrastructure failure. Not for a task graded by verdict, whose resets differ by design.
out["instance_exact"] = bool(a) and r1.get("instance_exact") is not False
if not verdict_mode and a and not out["instance_exact"]:
    out["instance_mismatch"] = True
    errors.append(f"the replay did not start from the frozen instance (rebuilt state {r1.get('instance_sha')})")
mp4 = os.path.join(d, "replay.mp4")
out["video"] = bool(a) and r1.get("video_ok") is not False and os.path.exists(mp4) and os.path.getsize(mp4) > 0
if episode_error:
    # the service's own record of the live episode is missing: no verdict either way
    out["infra_error"] = 1; out["error"] = "infrastructure: " + episode_error
if gpu_lost:
    out["gpu_lost"] = True
    if not verdict_mode:
        out["infra_error"] = 1
        out["error"] = "infrastructure: the GPU was not accessible to new processes in the sim sidecar, so the episode could not be replayed"
elif errors:
    out["replay_error"] = "; ".join(errors)
    if not verdict_mode:
        # the trajectory is the trusted service's own record: a replay that produced nothing is not the agent's 0
        out["infra_error"] = 1
        out["error"] = "infrastructure: the episode could not be replayed to a verdict: " + out["replay_error"]
out["finalized"] = True
p = os.path.join(d, "final.json"); tmp = f"{p}.{os.getpid()}.tmp"
with open(tmp, "w") as f:
    json.dump(out, f); f.flush(); os.fsync(f.fileno())
os.replace(tmp, p)
print(json.dumps(out))
PY
