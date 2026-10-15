"""Verifier entry point: replay /app/output/trajectory.npz from the frozen instance and write Harbor rewards.

    python /tests/grade.py --instance /tests/instance.json --traj /app/output/trajectory.npz --repeat 2

Writes /logs/verifier/reward.txt (1/0), reward.json (numeric fields only: Harbor rejects strings), and a human-viewable
replay video /logs/verifier/replay.mp4 (the overview camera) plus replay.last.png. Replays `--repeat` times, each in its
own FRESH process (`rcb_pandadyn.py replay`), so fresh process == fresh process is the determinism check. Success
requires every replay to complete the task (the task's own event ledger: every phase in order, no failure, no safety-limit
violation) AND all final-state hashes to agree, so a lucky non-deterministic run cannot pass. Each replay process also
rebuilds the frozen scene from tests/instance.json and checks it against the recorded start (`instance_ok`: exact state
hash; physics is CPU PhysX).

Whose failure a 0 is (every path writes a reward; `deterministic`, `grader_error` and `infra_error` are always present):
- the agent's: no file (`missing_trajectory`), another task's trajectory (`wrong_task`), a file that is not a trajectory
  (`bad_trajectory`: not an npz, no `task` / `actions` entry, pickled or object arrays, the wrong shape, NaN/inf, more than
  MAX_ROWS rows), or a replay that does not complete the task or is not deterministic;
- the verifier's (`grader_error` = 1, with `infra_error` = 1: no verdict on the agent): a replay process that ends without a
  result or runs out of its time limit (`replay_timed_out`), the rebuilt frozen scene not matching the recorded instance
  (`instance_ok` = 0: the host, not the trajectory), or any other error in this script.
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys, time, traceback
import numpy as np

LOG_DIR = os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier")
# Wall-clock limit of ONE replay process (time limits only; the verdict rules do not depend on them). A replay builds the
# scene in ~5-15 s and runs ~40-150 control steps/s (CPU PhysX at 1000 Hz, one or two arms); a trajectory has at most
# MAX_ROWS rows. The allowance is REPLAY_STARTUP_S + rows / REPLAY_MIN_RATE, several times what a replay takes here;
# task.toml's [verifier] timeout_sec fits two replays of a MAX_ROWS-row trajectory, the video and the overhead.
REPLAY_STARTUP_S, REPLAY_MIN_RATE = 300.0, 10.0


def replay_timeout(n_rows: int) -> float:
    return REPLAY_STARTUP_S + n_rows / REPLAY_MIN_RATE


def load_trajectory(path: str, task: str, dim: int, max_rows: int):
    """(rows, None), or (None, reward fields) when the file is not a gradable trajectory of this task. Everything here is
    the agent's deliverable: a file that cannot be read is the agent's 0 (`bad_trajectory`), not a grader error."""
    try:
        d = np.load(path, allow_pickle=False)              # not an npz / a bare .npy / pickled content: ValueError, OSError, ...
        name = str(d["task"])                              # no `task` entry: KeyError; an object array: ValueError
    except Exception as exc:  # noqa: BLE001
        print(f"[grade] unreadable trajectory: {exc!r}", file=sys.stderr, flush=True)
        return None, {"bad_trajectory": 1}
    if name != task:
        return None, {"wrong_task": 1}
    try:
        acts = np.asarray(d["actions"], dtype=np.float64)
    except Exception as exc:  # noqa: BLE001
        print(f"[grade] unreadable actions: {exc!r}", file=sys.stderr, flush=True)
        return None, {"bad_trajectory": 1}
    if acts.ndim != 2 or acts.shape[1] != dim or acts.shape[0] > max_rows or not np.all(np.isfinite(acts)):
        return None, {"bad_trajectory": 1, "n_actions": int(acts.shape[0]) if acts.ndim == 2 else 0}
    return acts, None


def write(ok: bool, out: dict) -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    open(os.path.join(LOG_DIR, "reward.txt"), "w").write("1\n" if ok else "0\n")
    json.dump(out, open(os.path.join(LOG_DIR, "reward.json"), "w"))
    print(json.dumps(out), flush=True)


def self_reported_cost() -> dict:
    """Agent interaction cost from the tooling's append-only log (/app/output/rcb_session_log.jsonl). The log lives in the
    agent's container, so these fields are SELF-REPORTED cost accounting, not evidence (agent_cost_self_reported = 1); the
    parser must survive any content the agent may have written there."""
    cost = {"agent_sessions": 0, "agent_resets": 0, "agent_sim_steps": 0, "agent_replays": 0, "agent_cost_self_reported": 1}
    try:
        with open("/app/output/rcb_session_log.jsonl") as f:
            for i, line in enumerate(f):
                if i > 200_000 or len(line) > 10_000:
                    break
                try:
                    e = json.loads(line); ev = e.get("ev") if isinstance(e, dict) else None
                    if ev == "session_start": cost["agent_sessions"] += 1
                    elif ev == "reset": cost["agent_resets"] += 1
                    elif ev == "session_end": cost["agent_sim_steps"] += min(int(float(e.get("sim_steps", 0) or 0)), 10**9)
                    elif ev == "replay": cost["agent_replays"] += 1
                except Exception:  # noqa: BLE001 -- one bad line must not sink the verdict
                    continue
    except Exception:  # noqa: BLE001
        pass
    return cost


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", required=True); ap.add_argument("--traj", default="/app/output/trajectory.npz")
    ap.add_argument("--repeat", type=int, default=2); ap.add_argument("--no-video", action="store_true")
    a = ap.parse_args()
    cost = self_reported_cost()
    os.environ["RCB_SESSION_LOG"] = ""  # the verifier's own sessions must not be counted
    ZERO = {"success": 0, "deterministic": 0, "grader_error": 0, "infra_error": 0}     # an early exit: the agent's 0
    ERR = {"success": 0, "deterministic": 0, "grader_error": 1, "infra_error": 1}      # no verdict on the agent
    if not os.path.isfile(a.traj):
        write(False, {**ZERO, "missing_trajectory": 1, **cost}); return 0
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, here)                                # the verifier's own copy of the tooling
        from rcb_pandadyn import MAX_ROWS
        inst = json.load(open(a.instance))
        acts, bad = load_trajectory(a.traj, inst["task"], int(inst["action_dim"]), MAX_ROWS)
        if bad is not None:
            write(False, {**ZERO, **bad, **cost}); return 0
        tool = os.path.join(here, "rcb_pandadyn.py")
        t0 = time.time(); runs = []; limit = replay_timeout(int(acts.shape[0]))
        for i in range(a.repeat):
            cmd = [sys.executable, tool, "replay", "--instance", a.instance, "--traj", a.traj]
            try:
                p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=sys.stderr, text=True, timeout=limit, env={**os.environ, "RCB_SESSION_LOG": ""})
            except subprocess.TimeoutExpired:
                print(f"[grade] replay {i + 1} exceeded its {limit:.0f} s limit ({len(acts)} rows)", file=sys.stderr, flush=True)
                write(False, {**ERR, "replay_timed_out": 1, "replay_timeout_s": round(limit, 1), "n_actions": int(len(acts)),
                              "replay_wall_s": round(time.time() - t0, 1), **cost}); return 0
            run = {"error": f"replay process rc={p.returncode}"}
            for line in p.stdout.splitlines():             # the last JSON object the CLI printed
                if line.startswith("{"):
                    try:
                        v = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(v, dict) and "replays" in v:
                        run = v
            runs.append(run)
        outs = [(r.get("replays") or [{}])[0] for r in runs]
        if any("error" in r or not o.get("state_sha") for r, o in zip(runs, outs)):
            print(f"[grade] a replay process gave no result: {[r.get('error') for r in runs]}", file=sys.stderr, flush=True)
            write(False, {**ERR, "replay_failed": 1, "n_actions": int(len(acts)), "replay_wall_s": round(time.time() - t0, 1), **cost}); return 0
        all_success = all(bool(o.get("success")) for o in outs)
        deterministic = len({o.get("state_sha") for o in outs}) == 1
        instance_ok = all(bool(r.get("instance_matches")) for r in runs)
        ok = all_success and deterministic and instance_ok
        last = outs[-1]
        out = {"success": int(ok), "all_success": int(all_success), "deterministic": int(deterministic), "replays": len(outs),
               "instance_ok": int(instance_ok), "n_actions": int(len(acts)), "executed_rows": int(last.get("executed_rows") or 0),
               "sim_steps": int(last.get("control_steps") or 0), "physics_steps": int(last.get("control_steps") or 0) * 10,
               "sim_time_s": float(last.get("sim_time_s") or 0.0), "phases_done": int(last.get("phase") or 0),
               "valid": int(bool(last.get("valid"))), "replay_wall_s": round(time.time() - t0, 1), "replay_timeout_s": round(limit, 1),
               # the rebuilt frozen scene is not the recorded one: this host, not the trajectory (no verdict on the agent)
               "grader_error": int(not instance_ok), "infra_error": int(not instance_ok), **cost}
        print(f"[grade] end_reason={last.get('end_reason')} phase={last.get('phase_name')}", file=sys.stderr, flush=True)
        write(ok, {**out, "video_rendered": 0})
        if not a.no_video and instance_ok:                 # the verdict is written; the video never changes it
            video = os.path.join(LOG_DIR, "replay.mp4")
            try:
                subprocess.run([sys.executable, tool, "replay", "--instance", a.instance, "--traj", a.traj, "--video", video],
                               stdout=subprocess.DEVNULL, stderr=sys.stderr, timeout=2 * limit, env={**os.environ, "RCB_SESSION_LOG": ""})
            except Exception as exc:  # noqa: BLE001
                print(f"[grade] video: {exc!r}", file=sys.stderr, flush=True)
            if os.path.isfile(video) and os.path.getsize(video) > 0:
                write(ok, {**out, "video_rendered": 1})
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        write(False, {**ERR, **cost})
    return 0


if __name__ == "__main__":
    sys.exit(main())
