"""Privileged-mode verifier (separate sandbox, no network): replays /app/output/trajectory.npz from the frozen instance
(tests/instance.json, the copy both twins share, with this task's goal.json restored) in two fresh processes (rcb_ispatialgym.py replay). success = both replays
succeed (upstream's geometric success at some control step; the replay stops there) and end in the same state, from a
start that rebuilt as frozen. Numeric-only reward.json (docs/PROTOCOL.md Appendix H.1, H.4).

bad_trajectory: no readable (T, 23) float array `actions`, a non-finite value, or more rows than the episode's control
steps (facts.json max_steps): score 0, no infrastructure error. infra_error (no verdict on the agent): a replay died, timed out or printed no result, goal.json did not restore upstream's
TRO, or the start did not rebuild as frozen (instance_ok 0)."""
import json, os, subprocess, traceback
import numpy as np

LOG, TRAJ, INST, TOOL = "/logs/verifier", "/app/output/trajectory.npz", "/tests", "/tests/rcb_ispatialgym.py"


def write(ok, out):
    open(f"{LOG}/reward.txt", "w").write("1\n" if ok else "0\n"); json.dump(out, open(f"{LOG}/reward.json", "w")); print(out)


def replay(i, timeout_s):
    args = ["python", TOOL, "replay", "--instance", INST, "--traj", TRAJ] + (["--video", f"{LOG}/replay.mp4"] if i == 1 else [])
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout_s)
        open(f"{LOG}/replay{i}.log", "w").write(r.stderr[-200000:])
        lines = [ln for ln in r.stdout.splitlines() if ln.startswith("{")]
        return json.loads(lines[-1]) if lines else {"error": f"no result (exit {r.returncode})"}
    except subprocess.TimeoutExpired as e:
        open(f"{LOG}/replay{i}.log", "w").write((e.stderr or b"").decode(errors="replace")[-200000:] if isinstance(e.stderr, bytes) else (e.stderr or "")[-200000:])
        return {"error": f"timed out after {timeout_s} s"}


os.makedirs(LOG, exist_ok=True)
facts = json.load(open(f"{INST}/facts.json"))
max_rows = int(facts["max_steps"])
# per replay: a scene load and every row, with margin (the instruction states the same formula)
timeout_s = max(2400, int(1500 + max_rows * facts["hold"]["step_s"] * 1.5))
base = {"success": 0, "deterministic": 0, "missing_trajectory": 0, "bad_trajectory": 0, "infra_error": 0, "sim_error": 0,
        "grader_error": 0, "n_actions": 0, "sim_steps": 0, "rows": 0, "max_rows": max_rows}
if not os.path.isfile(TRAJ):
    write(False, {**base, "missing_trajectory": 1}); raise SystemExit
try:
    a = np.load(TRAJ, allow_pickle=False)["actions"]
    if a.ndim != 2 or a.shape[1] != 23 or a.shape[0] > max_rows or not np.all(np.isfinite(a)):
        raise ValueError(f"actions {a.shape}")
except Exception:  # noqa: BLE001 -- the agent's file: not readable as a trajectory is its own failure
    traceback.print_exc()
    write(False, {**base, "bad_trajectory": 1}); raise SystemExit
r1, r2 = replay(1, timeout_s), replay(2, timeout_s)
if r1.get("error") or r2.get("error") or not r1.get("replays") or not r2.get("replays"):
    write(False, {**base, "rows": int(len(a)), "infra_error": 1, "grader_error": 1}); raise SystemExit
x, y = r1["replays"][0], r2["replays"][0]
det = bool(x.get("state_sha")) and x.get("state_sha") == y.get("state_sha")
inst_ok = bool(r1.get("instance_matches")) and bool(r2.get("instance_matches"))
if not inst_ok:
    write(False, {**base, "rows": int(len(a)), "instance_ok": 0, "infra_error": 1, "grader_error": 1}); raise SystemExit
ok = bool(x.get("success")) and bool(y.get("success")) and det
write(ok, {**base, "n_actions": int(len(a)), "sim_steps": int(x.get("steps") or 0), "success": int(ok), "replay_success": int(bool(x.get("success")) and bool(y.get("success"))),
           "deterministic": int(det), "instance_ok": int(inst_ok), "rows": int(len(a)), "steps": int(x.get("steps") or 0),
           "success_step": int(x.get("success_step") or 0), "symbolic_success": int(bool(x.get("symbolic_success")))})
