#!/bin/sh
# [[verifier.collect]] hook, run inside the `sim` sidecar once Harbor has stopped the agent's container (as BEHAVIOR-1K's).
#   1. end the episode with the shared first half (rcb_limited.py end, docs/STANDARD_MODE.md §13.3): it waits through a
#      resume, SIGUSR1s the service, and returns 0 once the service has written trajectory.npz + episode.json and exited
#      (releasing the GPU); 2 when final.json already holds the verdict (a give-up after crashes); 1 when the service never
#      ended the episode.
#   2. replay the trajectory from the frozen instance in TWO fresh processes (rcb_ispatialgym.py replay): on Isaac only the
#      first episode in a process is bit-exact, so determinism is fresh process == fresh process; live_matches_replay
#      reports live == replay apart. A replay that dies, runs out of time or prints no result is an infrastructure failure.
#   3. merge everything into final.json (written atomically), the only file the verifier sandbox grades.
set -u
DATA="${RCB_DATA:-/out}"; TOOL="${RCB_TOOL:?}"; INSTANCE="${RCB_INSTANCE:?}"
T0=$(date +%s)
BUDGET_S="${RCB_COLLECT_BUDGET_S:-10800}"   # = [[verifier.collect]] timeout_sec of the sim hook in task.toml
MARGIN_S=300
MIN_S="${RCB_REPLAY_MIN_S:-60}"
left() { l=$((BUDGET_S - MARGIN_S - ($(date +%s) - T0))); [ "$l" -lt "$MIN_S" ] && l="$MIN_S"; echo "$l"; }
if command -v timeout >/dev/null 2>&1; then limited() { timeout -k 30 "$(left)" "$@"; }; else limited() { "$@"; }; fi
python /srv/rcb_limited.py end "$DATA" --timeout 3600; rc=$?
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
    L._write_json(os.path.join(d, "final.json"), fin)
PY
    exit 0
fi
echo "[finalize] episode dumped; replaying twice in fresh processes"
limited python "$TOOL" replay --instance "$INSTANCE" --traj "$DATA/trajectory.npz" --video "$DATA/replay.mp4" > "$DATA/replay1.json" 2> "$DATA/replay1.log"
RC1=$?; echo "[finalize] replay 1 exit $RC1"
limited python "$TOOL" replay --instance "$INSTANCE" --traj "$DATA/trajectory.npz" > "$DATA/replay2.json" 2> "$DATA/replay2.log"
RC2=$?; echo "[finalize] replay 2 exit $RC2"
RCB_REPLAY_RC="$RC1 $RC2" python - <<'PY'
import json, os
d = os.environ.get("RCB_DATA", "/out")
def last_json(name):
    out = {}
    try:
        for line in open(os.path.join(d, name), errors="replace"):
            if line.strip().startswith("{"):
                try:
                    j = json.loads(line)
                except ValueError:
                    continue
                if isinstance(j, dict) and "replays" in j: out = j
    except Exception:
        pass
    return out
out = {"finalized": True, "replay_success": False, "deterministic": False, "video": False}
try:
    out.update(json.load(open(os.path.join(d, "episode.json"))))
except Exception as exc:
    out["error"] = f"infrastructure: no episode.json: {exc!r}"; out["infra_error"] = 1
r1, r2 = last_json("replay1.json"), last_json("replay2.json")
a, b = (r1.get("replays") or [{}])[0], (r2.get("replays") or [{}])[0]
out["replay_success"] = bool(a.get("success")) and bool(b.get("success"))
out["replay_symbolic_success"] = bool(a.get("symbolic_success"))
out["replay_success_step"] = a.get("success_step")
out["replay_sha"], out["replay_sha2"] = a.get("state_sha"), b.get("state_sha")
out["deterministic"] = bool(a.get("state_sha")) and a.get("state_sha") == b.get("state_sha")
out["live_matches_replay"] = bool(a.get("state_sha")) and a.get("state_sha") == out.get("live_sha")
def playable(p):
    import subprocess
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                            "stream=nb_read_packets", "-of", "csv=p=0", p], capture_output=True, text=True, timeout=300)
        return r.returncode == 0 and int((r.stdout.strip() or "0").split(",")[0]) > 0
    except Exception:
        return False
out["video"] = os.path.exists(os.path.join(d, "replay.mp4")) and playable(os.path.join(d, "replay.mp4"))
rcs = (os.environ.get("RCB_REPLAY_RC") or "").split() + ["?", "?"]
why = {"124": ", out of time", "137": ", killed"}
errs = [f"replay {i}: " + (str(r["error"])[:200] if r.get("error") else f"no result (exit {rc}{why.get(rc, '')})")
        for i, (r, o, rc) in enumerate(((r1, a, rcs[0]), (r2, b, rcs[1])), 1) if r.get("error") or not o.get("state_sha")]
if errs:
    out["replay_error"] = "; ".join(errs); out["infra_error"] = 1
    out.setdefault("error", "infrastructure: a fresh-process replay of the recorded trajectory did not run to its result (" + out["replay_error"] + ")")
elif r1.get("instance_matches") is False or r2.get("instance_matches") is False:
    out["instance_ok"] = 0; out["infra_error"] = 1
    out.setdefault("error", "infrastructure: the frozen instance did not rebuild to the recorded one in a replay process")
out["finalized"] = True
tmp = os.path.join(d, "final.json.tmp")
json.dump(out, open(tmp, "w")); os.replace(tmp, os.path.join(d, "final.json"))
print(json.dumps(out))
PY
