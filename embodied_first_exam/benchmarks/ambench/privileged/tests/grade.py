"""Verifier entry point: replay /app/output/trajectory.npz from the frozen instance and write Harbor rewards.

    python /tests/grade.py --instance /tests/instance.json --traj /app/output/trajectory.npz --repeat 2

Writes /logs/verifier/reward.txt (1/0), reward.json (numeric fields only — Harbor rejects strings), and a
human-viewable video /logs/verifier/replay.mp4 (the robot's two onboard cameras) plus replay.last.png, filmed AFTER the
verdict by a third process (`rcb_ambench.py film`: the same rows, the cameras drawn by the tooling's render worker; the video
never enters the reward).
Replays `--repeat` times, each in its own FRESH process (`rcb_ambench.py replay`). Success requires EVERY replay to
complete the task (AM-Bench's own `_get_success`), so a trajectory whose success does not repeat in a fresh process
cannot pass (`deterministic` = the replays agree on the outcome). The end-state hashes are compared and reported
(`state_identical`) but do not decide: with the tooling's five synchronizations every replay outside Harbor ended in the
frozen state (29 of 29 clean runs), yet under Harbor two of six runs did not (docs/benchmarks/ambench.md, Determinism),
in the last bits, the outcome unchanged. The frozen scene rebuilt here from tests/instance.json must also match the
recorded one (`instance_ok`: the exact state hash of the seeded reset).

Whose failure a 0 is (every path writes a reward; `deterministic`, `grader_error` and `infra_error` are always present):
- the agent's: no file (`missing_trajectory`), another task's trajectory (`wrong_task`), a file that is not a
  trajectory (`bad_trajectory`: not an npz, no `task` / `actions` entry, pickled or object arrays, the wrong shape, NaN/inf,
  more than MAX_STEPS rows, a row whose quaternion has zero or non-finite length: `bad_quaternion_rows`; also when the
  replay CLI itself reports `bad_trajectory`), or a replay that does not complete the task;
- the verifier's (`grader_error` = 1, with `infra_error` = 1: no verdict on the agent): a replay process that ends
  without a result (Isaac died) or runs out of its time limit (`replay_timed_out`), a replay whose output reports a GPU
  fault (`replay_gpu_fault`: PhysX kernels that failed to launch or CUDA out of memory, rcb_ambench.GPU_FAULT; PhysX steps
  on without them, so that run is not the trajectory's physics), the rebuilt frozen scene not matching the recorded
  instance (`instance_ok` = 0: the host, not the trajectory), or any other error in this script. A replay without a
  result or with a GPU fault is run once more first.
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys, time, traceback
import numpy as np

LOG_DIR = os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier")
# Wall-clock limit of ONE replay process, scaled with the rows that can run (time limits only; the verdict rules do not
# depend on them). The grader accepts up to MAX_STEPS rows, but the episode ends at the task's own episode length (15-60 s
# here: at most 7199 control steps), so later rows never run. Measured on an RTX 4090 host: Isaac start + scene build
# 1.5-6 min (the upper end with other Isaac jobs on the GPU; the verifier's first start also compiles the shaders into its
# fresh Kit cache), then 20+ control steps/s (camera-free; Harbor: CabinetPickPlace's 2752 steps in ~135 s per replay,
# start included). The allowance is REPLAY_STARTUP_S for the start plus the runnable rows at REPLAY_MIN_RATE control
# steps/s (the same for the filming process, whose time-out only ends the video), never below REPLAY_FLOOR_S; task.toml's
# [verifier] timeout_sec is four such limits (two replays, one rerun, the film), so a replay that is too slow ends here
# with a written reward (`replay_timed_out`), never with Harbor killing the verifier.
REPLAY_FLOOR_S, REPLAY_STARTUP_S, REPLAY_MIN_RATE = 1800.0, 1500.0, 4.0


def replay_timeout(n_steps: int) -> float:
    return max(REPLAY_FLOOR_S, REPLAY_STARTUP_S + n_steps / REPLAY_MIN_RATE)


def load_trajectory(path: str, family: str, action_dim: int, max_steps: int, bad_quaternion_rows=None):
    """(actions, None), or (None, reward fields) when the file is not a gradable trajectory of this task. Everything
    here is the agent's deliverable: a file that cannot be read is the agent's 0 (`bad_trajectory`), not a grader error."""
    try:
        d = np.load(path, allow_pickle=False)              # not an npz / a bare .npy / pickled content: ValueError, OSError, ...
        task = str(d["task"])                              # no `task` entry: KeyError; an object array: ValueError
    except Exception as exc:  # noqa: BLE001
        print(f"[grade] unreadable trajectory: {exc!r}", file=sys.stderr, flush=True)
        return None, {"bad_trajectory": 1}
    if task != family:
        return None, {"wrong_task": 1}
    try:
        acts = np.asarray(d["actions"], dtype=np.float32)
    except Exception as exc:  # noqa: BLE001
        print(f"[grade] unreadable actions: {exc!r}", file=sys.stderr, flush=True)
        return None, {"bad_trajectory": 1}
    if acts.ndim != 2 or acts.shape[1] != action_dim or acts.shape[0] > max_steps or not np.all(np.isfinite(acts)):
        return None, {"bad_trajectory": 1, "n_actions": int(acts.shape[0]) if acts.ndim == 2 else 0}
    nq = bad_quaternion_rows(acts) if bad_quaternion_rows is not None else 0
    if nq:                                                 # AM-Bench's controller cannot use a zero-length quaternion
        print(f"[grade] {nq} row(s) with a zero-length or non-finite quaternion", file=sys.stderr, flush=True)
        return None, {"bad_trajectory": 1, "bad_quaternion_rows": nq, "n_actions": int(acts.shape[0])}
    return acts, None


def write(ok: bool, out: dict) -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    open(os.path.join(LOG_DIR, "reward.txt"), "w").write("1\n" if ok else "0\n")
    json.dump(out, open(os.path.join(LOG_DIR, "reward.json"), "w"))
    print(json.dumps(out), flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", required=True)
    ap.add_argument("--traj", default="/app/output/trajectory.npz"); ap.add_argument("--repeat", type=int, default=2)
    ap.add_argument("--no-video", action="store_true"); ap.add_argument("--video-fps", type=int, default=30)
    a = ap.parse_args()
    # Agent interaction cost from the tooling's append-only log (whole debugging history, not just the deliverable).
    # The log lives in the agent's container, so these fields are SELF-REPORTED cost accounting, not evidence
    # (agent_cost_self_reported = 1); the parser must survive any content the agent may have written there.
    cost = {"agent_sessions": 0, "agent_resets": 0, "agent_sim_steps": 0, "agent_records": 0, "agent_replays": 0, "agent_cost_self_reported": 1}
    try:
        with open("/app/output/rcb_session_log.jsonl") as f:
            for i, line in enumerate(f):
                if i > 200_000 or len(line) > 10_000: break
                try:
                    e = json.loads(line); ev = e.get("ev") if isinstance(e, dict) else None
                    if ev == "session_start": cost["agent_sessions"] += 1
                    elif ev == "reset": cost["agent_resets"] += 1
                    elif ev == "session_end": cost["agent_sim_steps"] += min(int(float(e.get("sim_steps", 0) or 0)), 10**9)
                    elif ev == "record": cost["agent_records"] += 1
                    elif ev == "replay": cost["agent_replays"] += 1
                except Exception:  # noqa: BLE001 — one bad line must not sink the verdict
                    continue
    except Exception:  # noqa: BLE001
        pass
    os.environ["RCB_SESSION_LOG"] = ""  # the verifier's own sessions must not be counted
    ZERO = {"success": 0, "deterministic": 0, "grader_error": 0, "infra_error": 0}     # an early exit: the agent's 0
    ERR = {"success": 0, "deterministic": 0, "grader_error": 1, "infra_error": 1}      # no verdict on the agent
    if not os.path.isfile(a.traj):
        write(False, {**ZERO, "missing_trajectory": 1, **cost}); return 0
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # the verifier's own copy of the tooling
        from rcb_ambench import MAX_STEPS, ACTION_DIM, bad_quaternion_rows, count_gpu_faults
        inst = json.load(open(a.instance)); env_id = inst["env_id"]
        acts, bad = load_trajectory(a.traj, env_id, ACTION_DIM, MAX_STEPS, bad_quaternion_rows)
        if bad is not None:
            write(False, {**ZERO, **bad, **cost}); return 0
        tool = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rcb_ambench.py")
        runnable = min(int(acts.shape[0]), int(round(float(inst["episode_length_s"]) * int(inst["control_hz"]))))
        t0 = time.time(); runs = []
        attempts = []; faults = []
        for i in range(a.repeat):
            limit = replay_timeout(runnable)
            for attempt in (1, 2):                         # a process without a result (Isaac died, or a GPU fault) runs once more
                cmd = [sys.executable, tool, "replay", "--instance", a.instance, "--traj", a.traj]
                try:
                    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace", timeout=limit,
                                       env={**os.environ, "RCB_SESSION_LOG": ""})
                    stdout, run = p.stdout, {"error": f"replay process rc={p.returncode}"}
                    sys.stderr.write(p.stderr); sys.stderr.flush()
                except subprocess.TimeoutExpired as exc:
                    print(f"[grade] replay {i + 1} exceeded its {limit:.0f} s limit ({len(acts)} rows)", file=sys.stderr, flush=True)
                    write(False, {**ERR, "replay_timed_out": 1, "replay_timeout_s": round(limit, 1), "n_actions": int(len(acts)),
                                  "replay_wall_s": round(time.time() - t0, 1), **cost}); return 0
                for line in stdout.splitlines():               # the last JSON object the CLI printed (Isaac writes to stdout too)
                    if line.startswith("{"):
                        try:
                            v = json.loads(line)
                        except ValueError:
                            continue
                        if isinstance(v, dict): run = v
                n_fault = count_gpu_faults(p.stderr) + count_gpu_faults(stdout)
                print(f"[grade] replay {i + 1}: {json.dumps(run)[:800]} gpu_faults={n_fault}", file=sys.stderr, flush=True)
                attempts.append(attempt)
                if n_fault and "replays" in run:           # the physics ran without some of its GPU kernels: not this trajectory's
                    run = {"error": f"{n_fault} GPU fault(s) in the replay's output (rcb_ambench.GPU_FAULT)", "gpu_faults": n_fault}
                if "replays" in run or run.get("bad_trajectory") or attempt == 2:
                    break
                print(f"[grade] replay {i + 1} gave no result ({run.get('error')}): running it once more", file=sys.stderr, flush=True)
            faults.append(int(run.get("gpu_faults", 0)))
            runs.append(run)
            if "error" in run:                             # no verdict either way (or the agent's, below): the next replay is not run
                break
        if any(r.get("bad_trajectory") for r in runs):   # the replay CLI refused the rows: the agent's input, a verdict
            print(f"[grade] the replay refused the trajectory: {[r.get('error') for r in runs]}", file=sys.stderr, flush=True)
            write(False, {**ZERO, "bad_trajectory": 1, "n_actions": int(len(acts)), **cost}); return 0
        outs = [(r.get("replays") or [{}])[0] for r in runs]
        if any("error" in r or not o for r, o in zip(runs, outs)):
            print(f"[grade] a replay process gave no result: {[r.get('error') for r in runs]}", file=sys.stderr, flush=True)
            write(False, {**ERR, "replay_failed": 1, "replay_gpu_fault": int(any(faults)), "n_actions": int(len(acts)),
                          "replay_wall_s": round(time.time() - t0, 1), **cost}); return 0
        replay_wall = round(time.time() - t0, 1)
        all_success = all(o.get("success") for o in outs)
        state_identical = len({o.get("state_sha") for o in outs}) == 1          # reported; does not decide (module doc)
        deterministic = len({bool(o.get("success")) for o in outs}) == 1         # the verdict repeats in every fresh process
        instance_ok = all(bool(r.get("instance_matches")) for r in runs)
        ok = all_success and instance_ok
        out = {"success": int(ok), "all_success": int(all_success), "deterministic": int(deterministic),
               "state_identical": int(state_identical), "determinism_checked": int(len(outs) > 1),
               "instance_ok": int(instance_ok), "n_actions": int(len(acts)), "replays": len(outs),
               "sim_steps": int(outs[0].get("control_steps") or 0), "sim_time_s": float(outs[0].get("sim_time_s") or 0.0),
               "timed_out": int(outs[-1].get("end_reason") == "timeout"),
               "replay_wall_s": replay_wall, "replay_timeout_s": round(limit, 1),
               # the rebuilt frozen scene is not the recorded one: this host, not the trajectory (no verdict on the agent)
               "grader_error": int(not instance_ok), "infra_error": int(not instance_ok),
               "replay_retries": int(sum(x - 1 for x in attempts)), "replay_gpu_fault": 0, **cost}
        write(ok, out)                                     # the verdict is written before the illustration is filmed
        film = {}
        if not a.no_video:                                 # an illustration after the verdict: never part of the reward
            try:
                p = subprocess.run([sys.executable, tool, "film", "--instance", a.instance, "--traj", a.traj, "--video",
                                    os.path.join(LOG_DIR, "replay.mp4"), "--fps", str(a.video_fps)], stdout=subprocess.PIPE,
                                   stderr=sys.stderr, text=True, timeout=replay_timeout(runnable), env={**os.environ, "RCB_SESSION_LOG": ""})
                for line in p.stdout.splitlines():
                    if line.startswith("{"):
                        try:
                            film = json.loads(line).get("film") or {}
                        except (ValueError, AttributeError):
                            pass
            except Exception as exc:  # noqa: BLE001 — a time-out or a crash only costs the video
                print(f"[grade] filming failed: {exc!r}"[:300], file=sys.stderr, flush=True)
        out.update(video_rendered=int(os.path.isfile(os.path.join(LOG_DIR, "replay.mp4"))),
                   video_episode_success=int(bool(film.get("success"))))
        write(ok, out)
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        write(False, {**ERR, **cost})
    return 0


if __name__ == "__main__":
    sys.exit(main())
