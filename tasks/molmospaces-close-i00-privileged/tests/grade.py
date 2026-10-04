"""Verifier: replay /app/output/trajectory.npz from the frozen instance and write Harbor's rewards.

    python /tests/grade.py --instance /tests/instance.json --traj /app/output/trajectory.npz

Two replays, each in its own fresh process (`rcb_molmospaces.py replay`: upstream's episode, one Task.step per row until
upstream ends the episode, upstream's judge_success on the final state). success = both replays succeed and end in the
same state. Writes /logs/verifier/reward.txt (1/0), reward.json (numbers only) and replay.mp4 (never part of the verdict).
"""

import argparse, json, os, subprocess, sys, traceback
import numpy as np

LOG_DIR = os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier")
TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rcb_molmospaces.py")


def write(ok: bool, out: dict) -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    open(os.path.join(LOG_DIR, "reward.txt"), "w").write("1\n" if ok else "0\n")
    json.dump(out, open(os.path.join(LOG_DIR, "reward.json"), "w"))
    print(json.dumps(out), flush=True)


def agent_cost(path: str = "/app/output/rcb_session_log.jsonl") -> dict:
    """Self-reported cost from the tooling's log in the agent's container (accounting, not evidence)."""
    cost = {
        "agent_sessions": 0,
        "agent_resets": 0,
        "agent_sim_steps": 0,
        "agent_replays": 0,
        "agent_cost_self_reported": 1,
    }
    try:
        with open(path) as f:
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
                    elif ev == "replay":
                        cost["agent_replays"] += 1
                    elif ev == "session_end":
                        cost["agent_sim_steps"] += min(int(float(e.get("sim_steps", 0) or 0)), 10**9)
                except Exception:  # noqa: BLE001 -- one bad line must not sink the verdict
                    continue
    except OSError:
        pass
    return cost


def replay(instance: str, traj: str, video: str | None) -> dict:
    cmd = [sys.executable, TOOL, "replay", "--instance", instance, "--traj", traj] + (
        ["--video", video] if video else []
    )
    p = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
        text=True,
        timeout=1500,
        env={**os.environ, "RCB_SESSION_LOG": ""},
    )
    lines = [ln for ln in p.stdout.splitlines() if ln.startswith("{")]
    return json.loads(lines[-1]) if lines else {"error": f"replay process rc={p.returncode}"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", required=True)
    ap.add_argument("--traj", default="/app/output/trajectory.npz")
    a = ap.parse_args()
    cost = agent_cost()
    if not os.path.isfile(a.traj):
        write(False, {"success": 0, "missing_trajectory": 1, "grader_error": 0, **cost})
        return 0
    try:
        inst = json.load(open(a.instance))
        d = np.load(a.traj, allow_pickle=False)
        acts = np.asarray(d["actions"], dtype=np.float64) if "actions" in d.files else np.zeros((0, 0))
        dim = int(inst["t0"]["action_dim"])
        if "family" in d.files and str(d["family"]) != inst["family"]:
            write(False, {"success": 0, "wrong_family": 1, "grader_error": 0, **cost})
            return 0
        if acts.ndim != 2 or acts.shape[1] != dim or not np.all(np.isfinite(acts)):
            write(
                False,
                {
                    "success": 0,
                    "bad_trajectory": 1,
                    "n_actions": int(acts.shape[0]) if acts.ndim == 2 else 0,
                    "grader_error": 0,
                    **cost,
                },
            )
            return 0
        runs = [replay(a.instance, a.traj, None), replay(a.instance, a.traj, os.path.join(LOG_DIR, "replay.mp4"))]
        if any("error" in r for r in runs):
            write(False, {"success": 0, "grader_error": 1, **cost})
            return 0
        all_success = all(r["success"] for r in runs)
        deterministic = runs[0]["state_sha"] == runs[1]["state_sha"]
        ok = all_success and deterministic
        write(
            ok,
            {
                "success": int(ok),
                "replay_success": int(all_success),
                "deterministic": int(deterministic),
                "n_actions": int(len(acts)),
                "sim_steps": int(runs[0]["executed_rows"]),
                "horizon": int(runs[0]["horizon"]),
                "reached_horizon": int(bool(runs[0]["reached_horizon"])),
                "replay_s": float(runs[0]["replay_s"]),
                "grader_error": 0,
                "video_rendered": int(os.path.isfile(os.path.join(LOG_DIR, "replay.mp4"))),
                **cost,
            },
        )
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        write(False, {"success": 0, "grader_error": 1, **cost})
    return 0


if __name__ == "__main__":
    sys.exit(main())
