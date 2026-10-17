"""Privileged-mode verifier (separate sandbox, no network): replays /app/output/trajectory.npz from the frozen instance
(tests/instance.json, the copy both twins share, with this task's goal.json restored) in two fresh processes (rcb_ispatialgym.py replay). success = both replays
succeed (upstream's geometric success at some control step; the replay stops there) and end in the same state, from a
start that rebuilt as frozen. Numeric-only reward.json (docs/PROTOCOL.md Appendix H.1, H.4).

bad_trajectory: no readable (T, 23) float array `actions`, a value that is not a finite float32 (the simulator steps
float32), more rows than the episode's control steps (facts.json max_steps), or a file larger than that many rows: score 0, no infrastructure error.
sim_error: the start rebuilt as frozen in both replays and the rows then failed to step at the same step in both (the
trajectory's own outcome): score 0, no infrastructure error. infra_error (no verdict on the agent): a replay died, timed
out or printed no result, goal.json did not restore upstream's TRO, the start did not rebuild as frozen (instance_ok 0),
or the grader itself failed. The replay video never decides (rcb_ispatialgym.py _Video): `video_rendered` reports it."""
import json, os, subprocess, traceback, zipfile
import numpy as np

LOG, TRAJ, INST, TOOL = "/logs/verifier", "/app/output/trajectory.npz", "/tests", "/tests/rcb_ispatialgym.py"


def write(ok, out):
    open(f"{LOG}/reward.txt", "w").write("1\n" if ok else "0\n"); json.dump(out, open(f"{LOG}/reward.json", "w")); print(out)


def replay(i, timeout_s):
    args = ["python", TOOL, "replay", "--instance", INST, "--traj", TRAJ] + (["--video", f"{LOG}/replay.mp4"] if i == 1 else [])
    try:
        r = subprocess.run(args, capture_output=True, text=True, errors="replace", timeout=timeout_s)
        open(f"{LOG}/replay{i}.log", "w").write(r.stderr[-200000:])
        lines = [ln for ln in r.stdout.splitlines() if ln.startswith("{")]
        for ln in reversed(lines):          # the result is the last JSON line; a log line may also start with "{"
            try:
                d = json.loads(ln)
            except ValueError:
                continue
            if isinstance(d, dict) and "replays" in d:
                return d
        return {"error": f"no result (exit {r.returncode})"}
    except subprocess.TimeoutExpired as e:
        open(f"{LOG}/replay{i}.log", "w").write((e.stderr or b"").decode(errors="replace")[-200000:] if isinstance(e.stderr, bytes) else (e.stderr or "")[-200000:])
        return {"error": f"timed out after {timeout_s} s"}


def main():
    facts = json.load(open(f"{INST}/facts.json"))
    max_rows = int(facts["max_steps"])
    # per replay: a scene load and every row, with margin (the instruction states the same formula)
    timeout_s = max(2400, int(1500 + max_rows * facts["hold"]["step_s"] * 1.5))
    base = {"success": 0, "deterministic": 0, "missing_trajectory": 0, "bad_trajectory": 0, "infra_error": 0, "sim_error": 0,
            "grader_error": 0, "n_actions": 0, "sim_steps": 0, "rows": 0, "max_rows": max_rows}
    if not os.path.isfile(TRAJ):
        write(False, {**base, "missing_trajectory": 1}); return
    try:
        # sizes first: an npz whose header declares a huge array would be allocated by np.load before any shape check
        if os.path.getsize(TRAJ) > 64 << 20:
            raise ValueError(f"trajectory.npz is {os.path.getsize(TRAJ)} bytes")
        with zipfile.ZipFile(TRAJ) as z:
            if z.getinfo("actions.npy").file_size > max_rows * 23 * 16 + 4096:
                raise ValueError("actions.npy is larger than max_rows x 23 numbers")
        a = np.load(TRAJ, allow_pickle=False)["actions"]
        if a.ndim != 2 or a.shape[1] != 23 or a.shape[0] > max_rows or not np.issubdtype(a.dtype, np.number):
            raise ValueError(f"actions {a.shape} {a.dtype}")
        with np.errstate(over="ignore", invalid="ignore"):
            if not np.all(np.isfinite(a.astype(np.float32))):
                raise ValueError("a value that is not a finite float32")
    except Exception:  # noqa: BLE001 -- the agent's file: not readable as a trajectory is its own failure
        traceback.print_exc()
        write(False, {**base, "bad_trajectory": 1}); return
    r1, r2 = replay(1, timeout_s), replay(2, timeout_s)
    video = int(os.path.isfile(f"{LOG}/replay.mp4") and os.path.getsize(f"{LOG}/replay.mp4") > 0 and not r1.get("video_error"))
    inst_ok = bool(r1.get("instance_matches")) and bool(r2.get("instance_matches"))
    e1, e2 = r1.get("step_error"), r2.get("step_error")
    if inst_ok and e1 and e2 and e1 == e2:        # the rows fail to step, at the same step in two fresh processes
        write(False, {**base, "rows": int(len(a)), "n_actions": int(len(a)), "instance_ok": 1, "sim_error": 1, "steps": int(e1.get("step") or 0),
                      "video_rendered": video}); return
    if r1.get("error") or r2.get("error") or not r1.get("replays") or not r2.get("replays"):
        write(False, {**base, "rows": int(len(a)), "infra_error": 1, "grader_error": 1}); return
    x, y = r1["replays"][0], r2["replays"][0]
    det = bool(x.get("state_sha")) and x.get("state_sha") == y.get("state_sha")
    if not inst_ok:
        write(False, {**base, "rows": int(len(a)), "instance_ok": 0, "infra_error": 1, "grader_error": 1}); return
    ok = bool(x.get("success")) and bool(y.get("success")) and det
    write(ok, {**base, "n_actions": int(len(a)), "sim_steps": int(x.get("steps") or 0), "success": int(ok), "replay_success": int(bool(x.get("success")) and bool(y.get("success"))),
               "deterministic": int(det), "instance_ok": int(inst_ok), "rows": int(len(a)), "steps": int(x.get("steps") or 0),
               "success_step": int(x.get("success_step") or 0), "symbolic_success": int(bool(x.get("symbolic_success"))),
               "video_rendered": video})


os.makedirs(LOG, exist_ok=True)
try:
    main()
except Exception:  # noqa: BLE001 -- the grader's own failure is never the agent's 0
    traceback.print_exc()
    write(False, {"success": 0, "deterministic": 0, "infra_error": 1, "grader_error": 1})
