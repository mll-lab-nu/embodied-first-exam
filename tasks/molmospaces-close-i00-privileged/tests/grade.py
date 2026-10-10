"""Verifier: replay /app/output/trajectory.npz from the frozen instance and write Harbor's rewards.

    python /tests/grade.py --instance /tests/instance.json --traj /app/output/trajectory.npz

Two replays, each in its own fresh process (`rcb_molmospaces.py replay`: upstream's episode, one Task.step per row until
upstream ends the episode, upstream's judge_success on the final state). success = both replays succeed and end in the
same state. Writes /logs/verifier/reward.txt (1/0) and reward.json (numbers only); then a third replay renders
replay.mp4, after the verdict is on disk (it never changes it).

What is whose failure (success is 0 in every case): the agent's is a missing file (missing_trajectory), a file that is not
a trajectory of this task (bad_trajectory: not an npz, no `actions`, a pickled or non-numeric array, a wrong shape,
NaN/inf; wrong_family) and a trajectory upstream judges a failure; the grader's (grader_error = 1 and infra_error = 1,
no verdict on the agent) is a replay process that died or ran out of time, a frozen start the image no longer builds (instance_mismatch),
any other exception here.
"""

import argparse, json, os, subprocess, sys, tempfile, traceback
import numpy as np

LOG_DIR = os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier")
TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rcb_molmospaces.py")
REPLAY_TIMEOUT_S = 500  # three replays fit the verifier's 1800 s (a replay takes 20-120 s)


def write(ok: bool, out: dict) -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    out.setdefault("infra_error", int(bool(out.get("grader_error"))))   # every grader_error here is the host's, never the agent's (PROTOCOL §2.6)
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
    """One replay in a fresh process; its result (`--out`), or {"error": ...}."""
    with tempfile.NamedTemporaryFile(suffix=".json") as out:
        cmd = [sys.executable, TOOL, "replay", "--instance", instance, "--traj", traj, "--out", out.name]
        try:
            p = subprocess.run(
                cmd + (["--video", video] if video else []),
                stdout=subprocess.DEVNULL,
                stderr=sys.stderr,
                timeout=REPLAY_TIMEOUT_S,
                env={**os.environ, "RCB_SESSION_LOG": ""},
            )
        except subprocess.TimeoutExpired:
            return {"error": f"replay took over {REPLAY_TIMEOUT_S} s"}
        try:
            return json.load(open(out.name))
        except ValueError:
            return {"error": f"replay process rc={p.returncode}"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", required=True)
    ap.add_argument("--traj", default="/app/output/trajectory.npz")
    a = ap.parse_args()
    cost = agent_cost()
    if not os.path.isfile(a.traj):
        write(False, {"success": 0, "missing_trajectory": 1, "deterministic": 0, "grader_error": 0, **cost})
        return 0
    try:
        inst = json.load(open(a.instance))
        dim = int(inst["t0"]["action_dim"])
        try:  # the agent's file: whatever is wrong with it is its failure, not the grader's (nothing is unpickled)
            d = np.load(a.traj, allow_pickle=False)
            acts = np.asarray(d["actions"], dtype=np.float64) if "actions" in d.files else np.zeros((0, 0))
            family = str(d["family"]) if "family" in d.files else None
        except Exception:  # noqa: BLE001 -- not an npz, a truncated one, a pickled / object / non-numeric array
            traceback.print_exc(file=sys.stderr)
            write(False, {"success": 0, "bad_trajectory": 1, "deterministic": 0, "grader_error": 0, **cost})
            return 0
        if family is not None and family != inst["family"]:
            write(False, {"success": 0, "wrong_family": 1, "deterministic": 0, "grader_error": 0, **cost})
            return 0
        if acts.ndim != 2 or acts.shape[1] != dim or not np.all(np.isfinite(acts)):
            write(
                False,
                {
                    "success": 0,
                    "bad_trajectory": 1,
                    "n_actions": int(acts.shape[0]) if acts.ndim == 2 else 0,
                    "deterministic": 0,
                    "grader_error": 0,
                    **cost,
                },
            )
            return 0
        runs = [replay(a.instance, a.traj, None), replay(a.instance, a.traj, None)]
        if any("error" in r for r in runs):
            timed_out = int(any("took over" in str(r.get("error")) for r in runs))
            write(False, {"success": 0, "deterministic": 0, "grader_error": 1, "replay_timed_out": timed_out, **cost})
            return 0
        if not all(r["instance_ok"] for r in runs):  # the image no longer builds the frozen start: not the agent's 0
            write(False, {"success": 0, "deterministic": 0, "grader_error": 1, "instance_mismatch": 1, **cost})
            return 0
        all_success = all(r["success"] for r in runs)
        deterministic = runs[0]["state_sha"] == runs[1]["state_sha"]
        ok = all_success and deterministic
        out = {
            "success": int(ok),
            "replay_success": int(all_success),
            "deterministic": int(deterministic),
            "n_actions": int(len(acts)),
            "sim_steps": int(runs[0]["executed_rows"]),
            "horizon": int(runs[0]["horizon"]),
            "reached_horizon": int(bool(runs[0]["reached_horizon"])),
            "replay_s": float(runs[0]["replay_s"]),
            "grader_error": 0,
            "video_rendered": 0,
            **cost,
        }
        write(ok, out)  # the verdict, before any video
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        write(False, {"success": 0, "deterministic": 0, "grader_error": 1, **cost})
        return 0
    try:  # the video, for humans: it never changes the verdict
        if replay(a.instance, a.traj, os.path.join(LOG_DIR, "replay.mp4")).get("video"):
            write(ok, {**out, "video_rendered": 1})
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
