"""Verifier entry point: replay /app/output/trajectory.npz from the frozen instance and write Harbor rewards.

    python /tests/grade.py --family insert_hdmi --instance /tests/instance.json --traj /app/output/trajectory.npz

Writes /logs/verifier/reward.txt (1/0), reward.json (numeric fields only — Harbor rejects strings), and a
human-viewable replay video /logs/verifier/replay.mp4 (when rendered).
Replays `--repeat` times, each in its own FRESH process (`rcb_tactilelab.py replay`): on Isaac, only the first replay in a
process is bit-exact (env.reset_to does not restore every PhysX internal), so fresh process == fresh process is the
determinism check. Success requires every replay to complete the task AND all final-state hashes to agree, so a lucky
non-deterministic run cannot pass. The frozen scene rebuilt here from tests/instance.json must also match
the recorded one (`instance_ok`: exact state hash, or every object / joint pose within tolerance on another host).

Whose failure a 0 is (every path writes a reward; `deterministic`, `grader_error` and `infra_error` are always present):
- the agent's: no file (`missing_trajectory`), another family's trajectory (`wrong_family`), a file that is not a
  trajectory (`bad_trajectory`: not an npz, no `task` / `actions` entry, pickled or object arrays, the wrong shape, NaN/inf,
  more than MAX_STEPS rows, inf anywhere, NaN in a gripper column), or a replay that does not complete the task or is not deterministic;
- the verifier's (`grader_error` = 1, with `infra_error` = 1: no verdict on the agent): a replay process that ends
  without a result (Isaac died) or runs out of its time limit (`replay_timed_out`), the rebuilt frozen scene not matching
  the recorded instance (`instance_ok` = 0: the host, not the trajectory), or any other error in this script.
"""

from __future__ import annotations
import argparse, json, os, subprocess, sys, time, traceback
import numpy as np

LOG_DIR = os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier")
# Wall-clock limit of ONE replay process, scaled with the trajectory (time limits only; the verdict rules do not depend on
# them). The grader accepts up to MAX_STEPS rows, and a trajectory that never reaches the goal is replayed to its last row.
# Measured: Isaac start + scene build ~2 min, replays ~15-20 control steps/s; the allowance is
# REPLAY_STARTUP_S for the start plus half the nominal rate (REPLAY_MIN_RATE control steps/s), never below the old flat
# 1800 s. task.toml's [verifier] timeout_sec fits two replays of a MAX_STEPS-row trajectory plus overhead, so a
# replay that is too slow ends here with a written reward (`replay_timed_out`), never with Harbor killing the verifier.
REPLAY_FLOOR_S, REPLAY_STARTUP_S, REPLAY_MIN_RATE = 1800.0, 900.0, 4.0


def replay_timeout(n_steps: int) -> float:
    return max(REPLAY_FLOOR_S, REPLAY_STARTUP_S + n_steps / REPLAY_MIN_RATE)


def load_trajectory(path: str, family: str, action_dim: int, max_steps: int):
    """(actions, None), or (None, reward fields) when the file is not a gradable trajectory of this family. Everything
    here is the agent's deliverable: a file that cannot be read is the agent's 0 (`bad_trajectory`), not a grader error."""
    try:
        d = np.load(path, allow_pickle=False)  # not an npz / a bare .npy / pickled content: ValueError, OSError, ...
        task = str(d["task"])  # no `task` entry: KeyError; an object array: ValueError
    except Exception as exc:  # noqa: BLE001
        print(f"[grade] unreadable trajectory: {exc!r}", file=sys.stderr, flush=True)
        return None, {"bad_trajectory": 1}
    if task != family:
        return None, {"wrong_family": 1}
    try:
        acts = np.asarray(d["actions"], dtype=np.float64)
    except Exception as exc:  # noqa: BLE001
        print(f"[grade] unreadable actions: {exc!r}", file=sys.stderr, flush=True)
        return None, {"bad_trajectory": 1}
    if (
        acts.ndim != 2
        or acts.shape[1] != action_dim
        or acts.shape[0] > max_steps
        or np.any(np.isinf(acts))
        or not np.all(np.isfinite(acts[:, 14:16]))
    ):  # NaN = hold / no gap override
        return None, {"bad_trajectory": 1, "n_actions": int(acts.shape[0]) if acts.ndim == 2 else 0}
    return acts, None


def write(ok: bool, out: dict) -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    open(os.path.join(LOG_DIR, "reward.txt"), "w").write("1\n" if ok else "0\n")
    json.dump(out, open(os.path.join(LOG_DIR, "reward.json"), "w"))
    print(json.dumps(out), flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", required=True)
    ap.add_argument("--instance", required=True)
    ap.add_argument("--traj", default="/app/output/trajectory.npz")
    ap.add_argument("--repeat", type=int, default=2)
    ap.add_argument("--no-video", action="store_true")
    ap.add_argument("--video-fps", type=int, default=15)
    a = ap.parse_args()
    # Agent interaction cost from the tooling's append-only log (whole debugging history, not just the deliverable).
    # The log lives in the agent's container, so these fields are SELF-REPORTED cost accounting, not evidence
    # (agent_cost_self_reported = 1); the parser must survive any content the agent may have written there.
    cost = {
        "agent_sessions": 0,
        "agent_resets": 0,
        "agent_sim_steps": 0,
        "agent_records": 0,
        "agent_replays": 0,
        "agent_cost_self_reported": 1,
    }
    try:
        with open("/app/output/rcb_session_log.jsonl") as f:
            for i, line in enumerate(f):
                if i > 200_000 or len(line) > 10_000:
                    break
                try:
                    e = json.loads(line)
                    ev = e.get("ev") if isinstance(e, dict) else None
                    if ev == "session_start":
                        cost["agent_sessions"] += 1
                    elif ev == "reset":
                        cost["agent_resets"] += 1
                    elif ev == "session_end":
                        cost["agent_sim_steps"] += min(int(float(e.get("sim_steps", 0) or 0)), 10**9)
                    elif ev == "record":
                        cost["agent_records"] += 1
                    elif ev == "replay":
                        cost["agent_replays"] += 1
                except Exception:  # noqa: BLE001 — one bad line must not sink the verdict
                    continue
    except Exception:  # noqa: BLE001
        pass
    os.environ["RCB_SESSION_LOG"] = ""  # the verifier's own sessions must not be counted
    ZERO = {"success": 0, "deterministic": 0, "grader_error": 0, "infra_error": 0}  # an early exit: the agent's 0
    ERR = {"success": 0, "deterministic": 0, "grader_error": 1, "infra_error": 1}  # no verdict on the agent
    if not os.path.isfile(a.traj):
        write(False, {**ZERO, "missing_trajectory": 1, **cost})
        return 0
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # the verifier's own copy of the tooling
        from rcb_tactilelab import MAX_STEPS, ACTION_DIM

        acts, bad = load_trajectory(a.traj, a.family, ACTION_DIM, MAX_STEPS)
        if bad is not None:
            write(False, {**ZERO, **bad, **cost})
            return 0
        tool = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rcb_tactilelab.py")
        t0 = time.time()
        runs = []
        limit = replay_timeout(int(acts.shape[0]))
        for i in range(a.repeat):
            video = (
                os.path.join(LOG_DIR, "replay.mp4") if (i == a.repeat - 1 and not a.no_video) else None
            )  # never affects the verdict
            cmd = [sys.executable, tool, "replay", "--task", a.family, "--instance", a.instance, "--traj", a.traj] + (
                ["--video", video, "--fps", str(a.video_fps)] if video else []
            )
            try:
                p = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=sys.stderr,
                    text=True,
                    timeout=limit,
                    env={**os.environ, "RCB_SESSION_LOG": ""},
                )
            except subprocess.TimeoutExpired:
                print(
                    f"[grade] replay {i + 1} exceeded its {limit:.0f} s limit ({len(acts)} rows)",
                    file=sys.stderr,
                    flush=True,
                )
                write(
                    False,
                    {
                        **ERR,
                        "replay_timed_out": 1,
                        "replay_timeout_s": round(limit, 1),
                        "n_actions": int(len(acts)),
                        "replay_wall_s": round(time.time() - t0, 1),
                        **cost,
                    },
                )
                return 0
            run = {"error": f"replay process rc={p.returncode}"}
            for line in p.stdout.splitlines():  # the last JSON object the CLI printed (Isaac writes to stdout too)
                if line.startswith("{"):
                    try:
                        v = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(v, dict):
                        run = v
            runs.append(run)
        outs = [(r.get("replays") or [{}])[0] for r in runs]
        if any("error" in r or not o for r, o in zip(runs, outs)):
            print(
                f"[grade] a replay process gave no result: {[r.get('error') for r in runs]}",
                file=sys.stderr,
                flush=True,
            )
            write(
                False,
                {
                    **ERR,
                    "replay_failed": 1,
                    "n_actions": int(len(acts)),
                    "replay_wall_s": round(time.time() - t0, 1),
                    **cost,
                },
            )
            return 0
        all_success = all(o.get("success") for o in outs)
        deterministic = len({o.get("state_sha") for o in outs}) == 1
        instance_ok = all(bool(r.get("instance_matches")) for r in runs)
        ok = all_success and deterministic and instance_ok
        out = {
            "success": int(ok),
            "all_success": int(all_success),
            "deterministic": int(deterministic),
            "instance_ok": int(instance_ok),
            "instance_exact": int(all(bool(r.get("instance_exact")) for r in runs)),
            "n_actions": int(len(acts)),
            "sim_steps": int(outs[0].get("sim_steps") or 0),
            "final_reward": float(outs[-1].get("progress") or 0.0),
            "replay_wall_s": round(time.time() - t0, 1),
            "replay_timeout_s": round(limit, 1),
            # the rebuilt frozen scene is not the recorded one: this host, not the trajectory (no verdict on the agent)
            "grader_error": int(not instance_ok),
            "infra_error": int(not instance_ok),
            "video_rendered": int(os.path.isfile(os.path.join(LOG_DIR, "replay.mp4"))),
            **cost,
        }
        write(ok, out)
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        write(False, {**ERR, **cost})
    return 0


if __name__ == "__main__":
    sys.exit(main())
