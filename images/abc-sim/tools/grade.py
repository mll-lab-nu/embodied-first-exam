"""Verifier (privileged ABC Sim tasks): replay /app/output/trajectory.npz from the frozen instance and write Harbor's rewards.

    python /opt/abc-tools/grade.py --instance /tests/instance.npz --traj /app/output/trajectory.npz

Two replays, each in its own fresh process, run side by side (`rcb_abc.py replay`: the frozen start, one control step
per row, the episode ends at the task's success -- the evaluator's success held for 1.02 s; ball tray: the countdown
completed with the ball on the tray and both handles held -- or at its failure). success = both replays succeed, end in
the same state, and start from the instance's recorded state hash. Writes /logs/verifier/reward.txt (1/0) and
reward.json (numbers only); then a third replay renders replay.mp4, after the verdict is on disk (it never changes it).

Whose failure a 0 is (PROTOCOL §4, H.5): a file that is no trajectory for this instance -- unreadable, not (T, 14),
empty or longer than MAX_ROWS, NaN/inf -- is the agent's (`bad_trajectory`), checked here before any replay. After that
check a replay process that gives no result (out of time, killed, not started, a failing tool) is the grader's
(`replay_failed`, `grader_error` and `infra_error` = 1), as is an instance the verifier's host does not rebuild:
every `grader_error` = 1 has `infra_error` = 1 next to it, and every reward.json carries `infra_error`.
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
TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rcb_abc.py")
MAX_ROWS = 20_000        # 680 s of simulated time, 7x the longest reference; the instruction states it
REPLAY_TIMEOUT_S = 2400  # the slowest scene (chess) replays ~14 control steps/s: MAX_ROWS in ~24 min
NU = 14


def write(ok: bool, out: dict) -> None:
    out = {**out, "infra_error": int(bool(out.get("grader_error")))}  # no grader error here is the agent's doing
    os.makedirs(LOG_DIR, exist_ok=True)
    open(os.path.join(LOG_DIR, "reward.txt"), "w").write("1\n" if ok else "0\n")
    json.dump(out, open(os.path.join(LOG_DIR, "reward.json"), "w"))
    print(json.dumps(out), flush=True)


def agent_cost() -> dict:
    """Self-reported cost from the tooling's log in the agent's container (accounting, never evidence)."""
    cost = {"agent_sessions": 0, "agent_resets": 0, "agent_sim_steps": 0, "agent_records": 0, "agent_replays": 0,
            "agent_cost_self_reported": 1}
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
    except Exception:  # noqa: BLE001 -- the agent's file, any bytes: the cost stays self-reported
        pass
    return cost


def start_replay(a, traj: str, out: str, video: str | None = None) -> subprocess.Popen:
    cmd = [sys.executable, TOOL, "replay", "--instance", a.instance, "--traj", traj, "--out", out]
    if video:
        cmd += ["--video", video]
    env = {**os.environ, "RCB_SESSION_LOG": "", "RCB_SESSION_LOG_KEEP": ""}  # the verifier's sessions are not the agent's
    return subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=sys.stderr)


def result(p: subprocess.Popen, out: str, timeout: float) -> dict:
    try:
        p.wait(timeout=timeout)
        with open(out) as f:
            r = json.load(f)
        return r if isinstance(r, dict) else {}
    except subprocess.TimeoutExpired:
        p.kill()
        p.wait()
        print(f"replay ran out of time ({timeout:.0f} s)", file=sys.stderr, flush=True)
        return {}
    except (OSError, ValueError):
        traceback.print_exc(file=sys.stderr)
        return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", required=True)
    ap.add_argument("--traj", default="/app/output/trajectory.npz")
    ap.add_argument("--no-video", action="store_true")
    a = ap.parse_args()
    family = str(np.load(a.instance, allow_pickle=False)["family"])
    cost = agent_cost()
    if not os.path.isfile(a.traj):
        write(False, {"success": 0, "deterministic": 0, "missing_trajectory": 1, "grader_error": 0, **cost})
        return 0
    try:
        d = np.load(a.traj, allow_pickle=False)
        fam = str(d["family"]) if "family" in d.files else family
        acts = np.asarray(d["actions"], dtype=np.float64)
    except Exception:  # noqa: BLE001 -- not a readable trajectory: the agent's 0
        traceback.print_exc(file=sys.stderr)
        write(False, {"success": 0, "deterministic": 0, "bad_trajectory": 1, "grader_error": 0, **cost})
        return 0
    if fam != family:
        write(False, {"success": 0, "deterministic": 0, "wrong_family": 1, "grader_error": 0, **cost})
        return 0
    if acts.ndim != 2 or not 0 < acts.shape[0] <= MAX_ROWS or acts.shape[1] != NU or not np.all(np.isfinite(acts)):
        write(False, {"success": 0, "deterministic": 0, "bad_trajectory": 1, "grader_error": 0,
                      "n_actions": int(acts.shape[0]) if acts.ndim == 2 else 0, **cost})
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        clean = os.path.join(tmp, "trajectory.npz")  # only the rows cross into the replay processes
        np.savez(clean, actions=acts, family=family)
        o1, o2 = os.path.join(tmp, "r1.json"), os.path.join(tmp, "r2.json")
        p1, p2 = start_replay(a, clean, o1), start_replay(a, clean, o2)   # two fresh processes, side by side
        r1, r2 = result(p1, o1, REPLAY_TIMEOUT_S), result(p2, o2, REPLAY_TIMEOUT_S)
        if not (r1.get("state_sha") and r2.get("state_sha")):
            # The rows were checked above, so a replay without a result did not run to a verdict (out of time, killed,
            # not started, the tool failed): no verdict on the agent.
            write(False, {"success": 0, "deterministic": 0, "replay_failed": 1, "grader_error": 1,
                          "n_actions": int(len(acts)), **cost})
            return 0
        for i, r in ((1, r1), (2, r2)):  # the record (grade.log): each fresh process's verdict and final-state hash
            print(f"replay {i}: success={r.get('success')} steps={r.get('steps')} reason={r.get('reason')} "
                  f"state_sha={r.get('state_sha')} instance_ok={r.get('instance_ok')}", file=sys.stderr, flush=True)
        both = bool(r1.get("success")) and bool(r2.get("success"))
        deterministic = r1["state_sha"] == r2["state_sha"]
        instance_ok = bool(r1.get("instance_ok")) and bool(r2.get("instance_ok"))
        ok = both and deterministic and instance_ok
        out = {
            "success": int(ok),
            "replay_success": int(both),
            "deterministic": int(deterministic),
            "instance_ok": int(instance_ok),
            "n_actions": int(len(acts)),
            "sim_steps": int(r1.get("steps") or 0),
            "task_failure": int(bool(r1.get("reason")) and not r1.get("success")),
            "grader_error": int(not instance_ok),
            "video_rendered": 0,
            **cost,
        }
        write(ok, out)
        if not a.no_video:  # a human-viewable replay (never affects the verdict)
            o3 = os.path.join(tmp, "r3.json")
            r3 = result(start_replay(a, clean, o3, video=os.path.join(LOG_DIR, "replay.mp4")), o3, REPLAY_TIMEOUT_S)
            out["video_rendered"] = int(bool(r3.get("video")))
            write(ok, out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
