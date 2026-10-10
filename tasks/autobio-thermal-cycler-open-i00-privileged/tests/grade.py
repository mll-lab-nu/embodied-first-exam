"""Verifier (privileged AutoBio tasks): replay /app/output/trajectory.npz from the frozen instance and write Harbor's rewards.

    python /tests/grade.py --instance /tests/instance.json --traj /app/output/trajectory.npz

Two replays, each in its own fresh process (`rcb_autobio.py replay`: AutoBio's reset with the instance's seed, one
2 ms control step per row; rule `first`: the episode ends at the first step at which AutoBio's check holds; rule
`final`: it is judged where the rows end). success = both replays succeed, end in the same state, and start from the
instance's recorded model and initial-state hashes. Writes /logs/verifier/reward.txt (1/0) and reward.json (numbers
only); then a third replay renders replay.mp4, after the verdict is on disk (it never changes it).
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import traceback

import numpy as np

LOG_DIR = os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier")
TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rcb_autobio.py")
MAX_ROWS = 600_000  # rcb_autobio.MAX_STEPS: 1200 s of simulated time; a replay runs 600 to 20000 control steps/s
# Time. VERIFIER_TIMEOUT_S is the [verifier] timeout_sec of task.toml (scripts/autobio/generate.py checks they agree).
# The longest trajectory the grader accepts (MAX_ROWS) replays in 1000 s in the slowest family (insert_centrifuge_5430,
# 600 control steps/s), so each verdict replay may take VERDICT_TIMEOUT_S, 2.4 times that; the video replay gets what
# is left of the verifier's time (at most VIDEO_TIMEOUT_S), MARGIN_S kept back: 2 x 2400 + video + 300 <= 5400. A
# replay that passes its limit is a replay without a result (grader_error, infra_error), a reward is written, and
# Harbor's own timeout is never reached.
VERIFIER_TIMEOUT_S = 5400
VERDICT_TIMEOUT_S = 2400
VIDEO_TIMEOUT_S = 1800
MARGIN_S = 300
T0 = time.monotonic()


WROTE = False  # a verdict is on disk


def write(ok: bool, out: dict) -> None:
    global WROTE
    os.makedirs(LOG_DIR, exist_ok=True)
    open(os.path.join(LOG_DIR, "reward.txt"), "w").write("1\n" if ok else "0\n")
    json.dump(out, open(os.path.join(LOG_DIR, "reward.json"), "w"))
    print(json.dumps(out), flush=True)
    WROTE = True


def agent_cost() -> dict:
    """Self-reported cost from the tooling's log in the agent's container (accounting, never evidence)."""
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
                except Exception:  # noqa: BLE001 -- one bad line must not sink the verdict
                    continue
    except OSError:
        pass
    return cost


def replay(a, traj: str, out: str, video: str | None = None, timeout: float = VERDICT_TIMEOUT_S) -> dict:
    """One replay in a fresh process: its result ({} when the process gave none), `timed_out` set when it ran into its
    limit. A result on disk counts whatever the exit status (it is written before the simulator shuts down)."""
    cmd = [sys.executable, TOOL, "replay", "--family", a.family, "--instance", a.instance, "--traj", traj, "--out", out]
    if video:
        cmd += ["--video", video]
    env = {**os.environ, "RCB_SESSION_LOG": ""}  # the verifier's sessions are not the agent's
    timed_out = False
    try:
        rc = subprocess.run(
            cmd, env=env, cwd="/tmp", stdout=subprocess.DEVNULL, stderr=sys.stderr, timeout=timeout, check=False
        ).returncode
        print(f"replay process exit {rc}" + (" (video)" if video else ""), file=sys.stderr, flush=True)
    except subprocess.TimeoutExpired:
        timed_out = True
        print(f"replay process killed at its {timeout:.0f} s limit" + (" (video)" if video else ""), file=sys.stderr, flush=True)
    except OSError:
        traceback.print_exc(file=sys.stderr)
    try:
        r = json.load(open(out))
        r = r if isinstance(r, dict) else {}
    except (OSError, ValueError):
        r = {}
    if timed_out and not r.get("state_sha"):
        r["timed_out"] = True
    return r


def main() -> int:
    try:
        return grade()
    except Exception:  # noqa: BLE001 -- the grader's own failure: a reward is still written, flagged
        traceback.print_exc(file=sys.stderr)
        if not WROTE:
            write(False, {"success": 0, "deterministic": 0, "progress": 0.0, "grader_error": 1, "infra_error": 1})
        return 0


def grade() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", required=True)
    ap.add_argument("--traj", default="/app/output/trajectory.npz")
    ap.add_argument("--no-video", action="store_true")
    a = ap.parse_args()
    inst = json.load(open(a.instance))
    a.family, n_act = inst["family"], int(inst["n_action"])
    cost = agent_cost()
    zero = {"success": 0, "deterministic": 0, "progress": 0.0, "grader_error": 0, "infra_error": 0, **cost}
    if not os.path.isfile(a.traj):
        write(False, {**zero, "missing_trajectory": 1})
        return 0
    try:
        d = np.load(a.traj, allow_pickle=False)
        task = str(d["task"]) if "task" in d.files else a.family
        acts = np.asarray(d["actions"], dtype=np.float64)
    except Exception:  # noqa: BLE001 -- not a readable trajectory: the agent's 0
        traceback.print_exc(file=sys.stderr)
        write(False, {**zero, "bad_trajectory": 1})
        return 0
    if task != a.family:
        write(False, {**zero, "wrong_family": 1})
        return 0
    if acts.ndim != 2 or acts.shape[1] != n_act or not 0 < acts.shape[0] <= MAX_ROWS or not np.all(np.isfinite(acts)):
        long = acts.ndim == 2 and acts.shape[0] > MAX_ROWS
        write(False, {**zero, "bad_trajectory": 1, "too_long": int(long), "n_actions": int(acts.shape[0]) if acts.ndim == 2 else 0})
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        clean = os.path.join(tmp, "trajectory.npz")  # only the rows cross into the replay processes
        np.savez(clean, actions=acts, task=a.family)
        r1 = replay(a, clean, os.path.join(tmp, "r1.json"))
        r2 = replay(a, clean, os.path.join(tmp, "r2.json"))
        if not (r1.get("state_sha") and r2.get("state_sha")):  # a replay process died or timed out: not the agent's 0
            timed_out = bool(r1.get("timed_out") or r2.get("timed_out"))
            write(False, {**zero, "grader_error": 1, "infra_error": 1, "replay_failed": 1, "replay_timed_out": int(timed_out),
                          "n_actions": int(len(acts))})
            return 0
        for i, r in ((1, r1), (2, r2)):  # the record (grade.log): each fresh process's verdict and final-state hash
            print(
                f"replay {i}: success={r.get('success')} score={r.get('score')} steps={r.get('steps')} "
                f"reason={r.get('reason')} state_sha={r.get('state_sha')} instance_ok={r.get('instance_ok')}",
                file=sys.stderr,
                flush=True,
            )
        both = bool(r1.get("success")) and bool(r2.get("success"))
        deterministic = r1["state_sha"] == r2["state_sha"]
        instance_ok = bool(r1.get("instance_ok")) and bool(r2.get("instance_ok"))
        ok = both and deterministic and instance_ok
        out = {
            "success": int(ok),
            "replay_success": int(both),
            "deterministic": int(deterministic),
            "instance_ok": int(instance_ok),
            "progress": float(min(r1.get("score") or 0.0, r2.get("score") or 0.0)),
            "n_actions": int(len(acts)),
            "sim_steps": int(r1.get("steps") or 0),
            "task_failure": int(str(r1.get("reason") or "").startswith("failure")),
            "grader_error": int(not instance_ok),
            "infra_error": int(not instance_ok),  # the image no longer builds the frozen start: not the agent's 0
            "video_rendered": 0,
            **cost,
        }
        write(ok, out)
        left = min(VIDEO_TIMEOUT_S, VERIFIER_TIMEOUT_S - MARGIN_S - (time.monotonic() - T0))
        if not a.no_video and left >= 120:  # a human-viewable replay (never affects the verdict), in the time left
            try:
                r3 = replay(a, clean, os.path.join(tmp, "r3.json"), video=os.path.join(LOG_DIR, "replay.mp4"), timeout=left)
                out["video_rendered"] = int(bool(r3.get("video")))
                write(ok, out)
            except Exception:  # noqa: BLE001 -- the verdict is on disk and stays
                traceback.print_exc(file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
