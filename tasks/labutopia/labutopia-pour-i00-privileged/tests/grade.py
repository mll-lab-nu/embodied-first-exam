"""Verifier (privileged LabUtopia tasks): replay /app/output/trajectory.npz from the frozen instance and write Harbor's rewards.

    python /tests/grade.py --instance /tests/instance.json --traj /app/output/trajectory.npz

ONE replay, in its own fresh process (`rcb_labutopia.py replay`: LabUtopia's scene and reset with the instance's seed,
one 1/60 s control step per row; the episode ends at the first step at which the family's rule is met; on Isaac Sim only
a fresh process repeats an episode bit for bit), decides: success = the replay succeeds and rebuilds the instance's
recorded placements. With one replay there is no second end state to compare: `deterministic` is written as 1 (nothing
disagreed) with `determinism_checked` = 0 and `replays` = 1, which say that nothing was compared. Writes
/logs/verifier/reward.txt (1/0) and reward.json (numbers only); then a second replay renders replay.mp4, after the
verdict is on disk (it never changes it).
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
TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rcb_labutopia.py")
MAX_ROWS = 36_000  # rcb_labutopia.MAX_STEPS: 600 s of simulated time; a replay runs about 200 control steps/s
# Time. VERIFIER_TIMEOUT_S is the [verifier] timeout_sec of task.toml (keep the two equal).
# A verdict replay only simulates (no renderer): under a minute to start, then the rows, at most MAX_ROWS at about 200
# control steps/s = 180 s; each may take VERDICT_TIMEOUT_S, ten times that (the limit it always had). The video replay starts the renderer, which
# prepares the stage the first time in a container (minutes: tasks/labutopia/README.md): it gets what is left of the
# verifier's time (at most VIDEO_TIMEOUT_S), MARGIN_S kept back: 2400 + video + 300 <= 5400. A replay that passes
# its limit is a replay without a result (grader_error, infra_error), a reward is written, and Harbor's own timeout is
# never reached.
VERIFIER_TIMEOUT_S = 5400
VERDICT_TIMEOUT_S = 2400
VIDEO_TIMEOUT_S = 2400
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
        with open("/app/output/rcb_session_log.jsonl", errors="replace") as f:
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
    except Exception:  # noqa: BLE001 -- the agent's file, any bytes: the cost stays self-reported, the verdict is never lost
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
        r = replay(a, clean, os.path.join(tmp, "r1.json"))
        if not r.get("state_sha"):  # the replay process died or timed out: not the agent's 0
            write(False, {**zero, "grader_error": 1, "infra_error": 1, "replay_failed": 1,
                          "replay_timed_out": int(bool(r.get("timed_out"))), "n_actions": int(len(acts))})
            return 0
        print(  # the record (grade.log): the fresh process's verdict and final-state hash
            f"replay: success={r.get('success')} steps={r.get('steps')} reason={r.get('reason')} "
            f"state_sha={r.get('state_sha')} instance_ok={r.get('instance_ok')} start_exact={r.get('start_exact')} "
            f"rule={r.get('rule_state')}",
            file=sys.stderr,
            flush=True,
        )
        replay_success = bool(r.get("success"))
        instance_ok = bool(r.get("instance_ok"))
        ok = replay_success and instance_ok
        out = {
            "success": int(ok),
            "replay_success": int(replay_success),
            "deterministic": 1,  # one replay: nothing disagreed; determinism_checked = 0 says nothing was compared
            "determinism_checked": 0,
            "replays": 1,
            "instance_ok": int(instance_ok),
            "progress": float(r.get("score") or 0.0),
            "n_actions": int(len(acts)),
            "sim_steps": int(r.get("steps") or 0),
            "start_state_exact": int(bool(r.get("start_exact"))),
            "grader_error": int(not instance_ok),
            "infra_error": int(not instance_ok),  # the image no longer builds the frozen start: not the agent's 0
            "video_rendered": 0,
            **cost,
        }
        write(ok, out)
        left = min(VIDEO_TIMEOUT_S, VERIFIER_TIMEOUT_S - MARGIN_S - (time.monotonic() - T0))
        if not a.no_video and left >= 120:  # a human-viewable replay (never affects the verdict), in the time left
            try:
                rv = replay(a, clean, os.path.join(tmp, "video.json"), video=os.path.join(LOG_DIR, "replay.mp4"), timeout=left)
                out["video_rendered"] = int(bool(rv.get("video")))
                write(ok, out)
            except Exception:  # noqa: BLE001 -- the verdict is on disk and stays
                traceback.print_exc(file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
