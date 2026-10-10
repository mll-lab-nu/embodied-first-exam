#!/bin/sh
# [[verifier.collect]] hook, run inside the `sim` sidecar once Harbor has stopped the agent's container.
#   1. end the episode with the shared first half (rcb_limited.py end, docs/STANDARD_MODE.md §13.3): it waits through
#      a resume after a crash (no PID file until the service is ready again), SIGUSR1s the process that wrote the newest
#      startups.jsonl line, and returns 0 once the service has written trajectory.npz + episode.json (live result,
#      final-state hash) and exited, releasing the simulator; 2 when final.json already holds the verdict (the service
#      gave up after crashes: it is kept, nothing is replayed); 1 when the service never ended the episode.
#   2. replay the trajectory from the frozen instance in TWO fresh processes with the tooling's own `replay` CLI (the
#      privileged verifier's check): on Isaac only the first replay in a process is bit-exact, so determinism is fresh
#      process == fresh process; `live_matches_replay` reports live == replay separately.
#      Each replay may run until the hook's own deadline (BUDGET_S below = task.toml's collect timeout_sec, less a
#      margin for step 3); a replay that is killed there, dies or prints no result is recorded (replay_error,
#      infra_error = 1: the trajectory is the service's own record, so that is never the agent's failure).
#   3. merge everything into final.json (written atomically), the only thing the verifier sandbox grades.
set -u
DATA="${RCB_DATA:-/out}"; TOOL="${RCB_TOOL:?}"; TASK="${RCB_TASK:?}"; INSTANCE="${RCB_INSTANCE:?}"
T0=$(date +%s)
BUDGET_S="${RCB_COLLECT_BUDGET_S:-37800}"   # = [[verifier.collect]] timeout_sec of the sim hook in task.toml
MARGIN_S=600                                # kept for the merge (ffprobe of the video, writing final.json)
MIN_S="${RCB_REPLAY_MIN_S:-60}"             # a replay always gets this long, however little is left
left() { l=$((BUDGET_S - MARGIN_S - ($(date +%s) - T0))); [ "$l" -lt "$MIN_S" ] && l="$MIN_S"; echo "$l"; }
# timeout's exit codes: 124 = out of time, 137 = it did not stop on SIGTERM within 30 s and was killed
if command -v timeout >/dev/null 2>&1; then limited() { timeout -k 30 "$(left)" "$@"; }; else limited() { "$@"; }; fi
# A resume replays the episode so far at ~14-20 control steps/s (a long episode: up to an hour), hence the long wait.
python /srv/rcb_limited.py end "$DATA" --timeout 7200; rc=$?
if [ "$rc" = 2 ]; then
    echo "[finalize] final.json already holds the verdict; no replays"; exit 0
fi
if [ "$rc" != 0 ]; then
    echo "[finalize] the service did not end the episode (rc $rc): recorded as an infrastructure failure"
    python - <<'PY'
import json, os, sys
sys.path.insert(0, "/srv")
import rcb_limited as L
d = os.environ.get("RCB_DATA", "/out")
if not L.final_verdict(d):
    fin = L._read_json(os.path.join(d, "final.json"))
    fin.update({"success": False, "finalized": True, "replay_success": False, "deterministic": False, "infra_error": 1,
                "error": "infrastructure: the sim service never ended the episode for the collect hook"})
    L._write_json(os.path.join(d, "final.json"), fin)   # atomic (tmp + rename)
PY
    exit 0
fi
echo "[finalize] episode dumped; replaying twice in fresh processes"
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
    export RCB_SESSION_LOG=    # the replays' own sessions are not the agent's
    limited python "$TOOL" replay --task "$TASK" --instance "$INSTANCE" --traj "$DATA/trajectory.npz" --video "$DATA/replay.mp4" > "$DATA/replay1.json" 2> "$DATA/replay1.log"
    RC1=$?; echo "[finalize] replay 1 exit $RC1"
    limited python "$TOOL" replay --task "$TASK" --instance "$INSTANCE" --traj "$DATA/trajectory.npz" > "$DATA/replay2.json" 2> "$DATA/replay2.log"
    RC2=$?; echo "[finalize] replay 2 exit $RC2"
else
    echo '{"gpu_lost": true}' > "$DATA/replay1.json"; echo '{"gpu_lost": true}' > "$DATA/replay2.json"; RC1=0; RC2=0
fi
RCB_REPLAY_RC="$RC1 $RC2" python - <<'PY'
import json, os
d = os.environ.get("RCB_DATA", "/out")
def last_json(name):
    out = {}
    try:
        for line in open(os.path.join(d, name)):
            if line.strip().startswith("{"): out = json.loads(line)
    except Exception:
        pass
    return out
out = {"finalized": True, "replay_success": False, "deterministic": False, "video": False}
try:
    out.update(json.load(open(os.path.join(d, "episode.json"))))   # live result + the crash-recovery fields
except Exception as exc:               # the service exited without its record: nothing to hold against the agent
    out["error"] = f"infrastructure: no episode.json: {exc!r}"; out["infra_error"] = 1
r1, r2 = last_json("replay1.json"), last_json("replay2.json")
a, b = (r1.get("replays") or [{}])[0], (r2.get("replays") or [{}])[0]
out["replay_success"] = bool(a.get("success")) and bool(b.get("success"))
out["q_score"] = b.get("q_score") if b.get("q_score") is not None else a.get("q_score")   # progress: the challenge's q_score
out["replay_sha"], out["replay_sha2"] = a.get("state_sha"), b.get("state_sha")
out["deterministic"] = bool(a.get("state_sha")) and a.get("state_sha") == b.get("state_sha")
out["live_matches_replay"] = bool(a.get("state_sha")) and a.get("state_sha") == out.get("live_sha")
# a video counts when it decodes, not when the file exists: a replay that crashes leaves a file behind (board 0051)
def playable(p):
    import subprocess
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                            "stream=nb_read_packets", "-of", "csv=p=0", p], capture_output=True, text=True, timeout=300)
        return r.returncode == 0 and int((r.stdout.strip() or "0").split(",")[0]) > 0
    except Exception:
        return False
out["video"] = os.path.exists(os.path.join(d, "replay.mp4")) and playable(os.path.join(d, "replay.mp4"))
if r1.get("gpu_lost"):
    out["gpu_lost"] = True; out["infra_error"] = 1
    out["error"] = "infrastructure: the GPU was not accessible to new processes in the sim sidecar, so the episode could not be replayed"
else:
    # a replay that did not run to its result (the process died: an Isaac crash, out of memory; it ran out of time; it
    # printed no JSON or an error) says nothing about the agent: the trajectory is the service's own record
    rcs = (os.environ.get("RCB_REPLAY_RC") or "").split() + ["?", "?"]
    why = {"124": ", out of time", "137": ", killed"}
    errs = [f"replay {i}: " + (str(r["error"])[:200] if r.get("error") else f"no result (exit {rc}{why.get(rc, '')})")
            for i, (r, o, rc) in enumerate(((r1, a, rcs[0]), (r2, b, rcs[1])), 1) if r.get("error") or not o.get("state_sha")]
    if errs:
        out["replay_error"] = "; ".join(errs); out["infra_error"] = 1
        out.setdefault("error", "infrastructure: a fresh-process replay of the recorded trajectory did not run to its result (" + out["replay_error"] + ")")
    elif r1.get("instance_matches") is False or r2.get("instance_matches") is False:
        # the frozen scene did not rebuild to the recorded one in a replay process (decided before the first action)
        out["instance_ok"] = 0; out["infra_error"] = 1
        out.setdefault("error", "infrastructure: the frozen instance did not rebuild to the recorded one in a replay process")
out["finalized"] = True
tmp = os.path.join(d, "final.json.tmp")
json.dump(out, open(tmp, "w")); os.replace(tmp, os.path.join(d, "final.json"))
print(json.dumps(out))
PY
