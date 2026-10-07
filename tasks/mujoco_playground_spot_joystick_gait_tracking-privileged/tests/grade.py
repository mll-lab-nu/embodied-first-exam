"""Verifier (privileged): replay /app/output/trajectory.npz from the frozen instance and write Harbor's rewards.

    python /tests/grade.py --instance /tests/instance.json --traj /app/output/trajectory.npz

Two replays, each in its own fresh process (`rcb_quadruped.py replay`: the frozen start, one control step per row, the
task's success check on the whole trajectory). success = both replays succeed and end in the same state. Writes
/logs/verifier/reward.txt (1/0) and reward.json (numbers only); then a third replay renders replay.mp4, after the
verdict is on disk (it never changes it).
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import traceback

import numpy as np

LOG_DIR = os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier")
TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rcb_quadruped.py")
REPLAY_TIMEOUT_S = 300  # a 1000-step replay takes a few seconds; the video replay renders 4 views every 2nd step


def write(ok: bool, out: dict) -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    open(os.path.join(LOG_DIR, "reward.txt"), "w").write("1\n" if ok else "0\n")
    json.dump(out, open(os.path.join(LOG_DIR, "reward.json"), "w"))
    print(json.dumps(out), flush=True)


def agent_cost() -> dict:
    """Self-reported cost from the tooling's log in the agent's container (accounting, not evidence)."""
    cost = {"agent_sessions": 0, "agent_resets": 0, "agent_sim_steps": 0, "agent_replays": 0, "agent_cost_self_reported": 1}
    for path in ("/logs/agent/rcb/rcb_session_log.jsonl", "/app/output/rcb_session_log.jsonl"):
        if not os.path.exists(path):
            continue
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
        break
    return cost


def replay(instance: str, traj: str, video: str | None) -> dict:
    """One replay in a fresh process; its result (`--out`), or {"error": ...}."""
    with tempfile.NamedTemporaryFile(suffix=".json") as out:
        cmd = [sys.executable, TOOL, "replay", "--instance", instance, "--traj", traj, "--out", out.name]
        try:
            p = subprocess.run(cmd + (["--video", video] if video else []), stdout=subprocess.DEVNULL, stderr=sys.stderr,
                               timeout=REPLAY_TIMEOUT_S, env={**os.environ, "RCB_SESSION_LOG": "", "RCB_AGENT_TRACE_DIR": ""})
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
        write(False, {"success": 0, "missing_trajectory": 1, "grader_error": 0, **cost})
        return 0
    try:
        horizon = int(json.load(open(a.instance))["horizon"])
        d = np.load(a.traj, allow_pickle=False)
        acts = np.asarray(d["actions"], dtype=np.float64) if "actions" in d.files else np.zeros((0, 0))
        if acts.ndim != 2 or acts.shape[1] != 12 or len(acts) > horizon or not np.all(np.isfinite(acts)):
            write(False, {"success": 0, "bad_trajectory": 1, "n_actions": int(acts.shape[0]) if acts.ndim == 2 else 0,
                          "grader_error": 0, **cost})
            return 0
        runs = [replay(a.instance, a.traj, None), replay(a.instance, a.traj, None)]
        if any("error" in r and not r.get("bad_trajectory") for r in runs):
            write(False, {"success": 0, "grader_error": 1, **cost})
            return 0
        if not all(r.get("instance_ok") for r in runs):  # the image no longer builds the frozen start: not the agent's 0
            write(False, {"success": 0, "grader_error": 1, "instance_mismatch": 1, **cost})
            return 0
        all_success = all(bool(r.get("success")) for r in runs)
        deterministic = runs[0].get("state_sha") == runs[1].get("state_sha")
        ok = all_success and deterministic
        r = runs[0]
        num = lambda k: float(r.get(k) if r.get(k) is not None else -1)  # noqa: E731
        out = {"success": int(ok), "replay_success": int(all_success), "deterministic": int(deterministic),
               "n_actions": int(len(acts)), "horizon": horizon, "fell": int(r.get("fell_at") is not None),
               "fell_at_step": num("fell_at"), "worst_lin_err": num("worst_lin_err"), "worst_yaw_err": num("worst_yaw_err"),
               "end_tilt_deg": num("tilt_deg"), "end_imu_height": num("imu_height"), "end_pose_angle_deg": num("pose_angle_deg"),
               "grader_error": 0,
               "video_rendered": 0, **cost}
        write(ok, out)  # the verdict, before any video
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        write(False, {"success": 0, "grader_error": 1, **cost})
        return 0
    try:  # the video, for humans: it never changes the verdict
        if replay(a.instance, a.traj, os.path.join(LOG_DIR, "replay.mp4")).get("video"):
            write(ok, {**out, "video_rendered": 1})
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
