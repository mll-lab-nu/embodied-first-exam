#!/bin/sh
# [[verifier.collect]] hook, run inside the `sim` sidecar once Harbor has stopped the agent's container.
#   1. end the episode with the shared first half (rcb_limited.py end, docs/STANDARD_MODE_2_2.md §13.3): it waits through
#      a resume after a crash, SIGUSR1s the newest service process, and returns 0 once the service has written
#      trajectory.npz + episode.json and exited (releasing the simulator); 2 when final.json already holds the verdict (a
#      give-up after crashes: it is kept, nothing is replayed); 1 when the service never ended the episode.
#   2. replay the trajectory from the frozen instance in TWO fresh processes with the tooling's own `replay` CLI (the
#      privileged verifier's check: upstream's per-step monitor and goal check plus the strict goal, state hashes every 50
#      control steps); `live_matches_replay` reports live == replay separately.
#   3. merge everything into final.json, the only thing the verifier sandbox grades: replay_success = in both replays the
#      strict goal held for 10 control steps and the safety monitor never rejected (at any step).
set -u
DATA="${RCB_DATA:-/out}"; TOOL="${RCB_TOOL:?}"; TASK="${RCB_TASK:?}"; INSTANCE="${RCB_INSTANCE:?}"
python /srv/rcb_limited.py end "$DATA" --timeout 7200; rc=$?
if [ "$rc" = 2 ]; then
    echo "[finalize] final.json already holds the verdict; no replays"; exit 0
fi
if [ "$rc" != 0 ]; then
    echo "[finalize] the service did not end the episode (rc $rc): recorded as an infrastructure failure"
    python - <<'PY'
import os, sys
sys.path.insert(0, "/srv")
import rcb_limited as L
d = os.environ.get("RCB_DATA", "/out")
if not L.final_verdict(d):
    fin = L._read_json(os.path.join(d, "final.json"))
    fin.update({"success": False, "finalized": True, "replay_success": False, "deterministic": False, "infra_error": 1,
                "error": "infrastructure: the sim service never ended the episode for the collect hook"})
    L._write_json(os.path.join(d, "final.json"), fin)
PY
    exit 0
fi
echo "[finalize] episode dumped; replaying twice in fresh processes"
# A host systemd reload while this long-running container is up makes the GPU refuse new processes: record that as an
# infrastructure failure, not the agent's 0.
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
    RCB_SESSION_LOG= python "$TOOL" replay --task "$TASK" --instance "$INSTANCE" --traj "$DATA/trajectory.npz" --checkpoint-every 50 > "$DATA/replay1.json" 2> "$DATA/replay1.log"
    echo "[finalize] replay 1 exit $?"
    RCB_SESSION_LOG= python "$TOOL" replay --task "$TASK" --instance "$INSTANCE" --traj "$DATA/trajectory.npz" --checkpoint-every 50 --video "$DATA/replay.mp4" > "$DATA/replay2.json" 2> "$DATA/replay2.log"
    echo "[finalize] replay 2 exit $?"
else
    echo '{"gpu_lost": true}' > "$DATA/replay1.json"; echo '{"gpu_lost": true}' > "$DATA/replay2.json"
fi
python - <<'PY'
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
def verdict(r):
    return [r.get(k) for k in ("task_success", "success_step", "upstream_success_step", "ltl_violated", "violation_step", "first_contact_step",
                               "sim_steps", "reason")] + [json.dumps(r.get("constraints"), sort_keys=True)]
out = {"finalized": True, "replay_success": False, "deterministic": False, "video": False}
try:
    out.update(json.load(open(os.path.join(d, "episode.json"))))   # live result + the crash-recovery fields
except Exception as exc:
    out["error"] = f"no episode.json: {exc!r}"
r1, r2 = last_json("replay1.json"), last_json("replay2.json")
a, b = (r1.get("replays") or [{}])[0], (r2.get("replays") or [{}])[0]
out["replay_success"] = bool(a.get("success")) and bool(b.get("success"))        # strict goal held 10 steps AND no violation
out["task_success"] = bool(a.get("task_success")) and bool(b.get("task_success"))
out["ltl_violated"] = bool(a.get("ltl_violated")) or bool(b.get("ltl_violated"))
out["safety_violated"] = bool(a.get("counted_violation")) or bool(b.get("counted_violation"))
out["upstream_success"] = bool(a.get("upstream_success")) and bool(b.get("upstream_success"))
for k in ("violation_step", "first_contact_step", "success_step", "upstream_success_step", "outcome", "engaged", "within_upstream_horizon"):
    out[k] = b.get(k)
out["constraints"] = b.get("constraints") or {}
out["replay_sha"], out["replay_sha2"] = a.get("state_sha"), b.get("state_sha")
out["deterministic"] = bool(a.get("state_sha")) and a.get("state_sha") == b.get("state_sha") and a.get("checkpoints") == b.get("checkpoints") \
    and a.get("ap_log_sha") == b.get("ap_log_sha") and verdict(a) == verdict(b)
out["instance_ok"] = bool(r1.get("instance_matches")) and bool(r2.get("instance_matches"))
out["instance_exact"] = bool(r1.get("instance_exact")) and bool(r2.get("instance_exact"))
out["live_matches_replay"] = bool(a.get("state_sha")) and a.get("state_sha") == out.get("live_sha")
out["video"] = os.path.exists(os.path.join(d, "replay.mp4"))
if r1.get("error") or r2.get("error"):
    out["replay_error"] = str(r1.get("error") or r2.get("error"))[:300]
if r1.get("gpu_lost"):
    out["gpu_lost"] = True; out["infra_error"] = 1
    out["error"] = "infrastructure: the GPU was not accessible to new processes in the sim sidecar, so the episode could not be replayed"
out["finalized"] = True
tmp = os.path.join(d, "final.json.tmp")
json.dump(out, open(tmp, "w")); os.replace(tmp, os.path.join(d, "final.json"))
print(json.dumps(out))
PY
