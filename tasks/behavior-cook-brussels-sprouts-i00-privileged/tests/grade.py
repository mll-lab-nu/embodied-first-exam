"""Verifier entry point: replay /app/output/trajectory.npz from the frozen instance and write Harbor rewards.

    python /tests/grade.py --family picking_up_trash --instance /tests/instance.json --traj /app/output/trajectory.npz

Writes /logs/verifier/reward.txt (1/0), reward.json (numeric fields only — Harbor rejects strings), and a
human-viewable replay video /logs/verifier/replay.mp4 (the challenge cameras).
Replays `--repeat` times, each in its own FRESH process (`rcb_behavior.py replay`): on Isaac, only the first replay in a
process is bit-exact (an in-process reset leaves PhysX solver / contact state behind), so fresh process == fresh process is the
determinism check. Success requires every replay to complete the task AND all final-state hashes to agree, so a lucky
non-deterministic run cannot pass. The frozen scene rebuilt here from tests/instance.json must also match
the recorded one (`instance_ok`: exact state hash, or every object / joint pose within tolerance on another host).
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys, time, traceback
import numpy as np

LOG_DIR = os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier")
# Wall-clock limit of ONE replay process, scaled with the trajectory (2026-10-08; time limit only, the verdict rules are
# unchanged). Measured on an idle 8-vCPU L40S host (job #3137): Isaac start + scene load 626 s, and a 10,475-step replay
# had not finished when the old flat 3600 s ran out (< 3.5 control steps/s). Allowance: REPLAY_STARTUP_S for the start plus
# a worst case of REPLAY_MIN_RATE control steps/s, never below the old 3600 s, at most REPLAY_CAP_S (4 h);
# task.toml's [verifier] timeout_sec fits two capped replays plus overhead.
REPLAY_FLOOR_S, REPLAY_STARTUP_S, REPLAY_MIN_RATE, REPLAY_CAP_S = 3600.0, 1200.0, 2.0, 14400.0


def replay_timeout(n_steps: int) -> float:
    return min(REPLAY_CAP_S, max(REPLAY_FLOOR_S, REPLAY_STARTUP_S + n_steps / REPLAY_MIN_RATE))


def write(ok: bool, out: dict) -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    open(os.path.join(LOG_DIR, "reward.txt"), "w").write("1\n" if ok else "0\n")
    json.dump(out, open(os.path.join(LOG_DIR, "reward.json"), "w"))
    print(json.dumps(out), flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", required=True); ap.add_argument("--instance", required=True)
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
    if not os.path.isfile(a.traj):
        write(False, {"success": 0, "missing_trajectory": 1, "grader_error": 0, **cost}); return 0
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # the verifier's own copy of the tooling
        from rcb_behavior import MAX_STEPS
        ACTION_DIM = int(json.load(open(a.instance)).get("action_dim", 25))   # the R1Pro's with the task's robot config
        d = np.load(a.traj, allow_pickle=False)
        if str(d["task"]) != a.family:
            write(False, {"success": 0, "wrong_family": 1, "grader_error": 0, **cost}); return 0
        acts = np.asarray(d["actions"], dtype=np.float32)
        if acts.ndim != 2 or acts.shape[1] != ACTION_DIM or acts.shape[0] > MAX_STEPS or not np.all(np.isfinite(acts)):
            write(False, {"success": 0, "bad_trajectory": 1, "n_actions": int(acts.shape[0]) if acts.ndim == 2 else 0, "grader_error": 0, **cost}); return 0
        tool = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rcb_behavior.py")
        t0 = time.time(); runs = []; limit = replay_timeout(int(acts.shape[0]))
        for i in range(a.repeat):
            video = os.path.join(LOG_DIR, "replay.mp4") if (i == a.repeat - 1 and not a.no_video) else None   # never affects the verdict
            cmd = [sys.executable, tool, "replay", "--task", a.family, "--instance", a.instance, "--traj", a.traj] + (["--video", video, "--fps", str(a.video_fps)] if video else [])
            try:
                p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=sys.stderr, text=True, timeout=limit, env={**os.environ, "RCB_SESSION_LOG": ""})
            except subprocess.TimeoutExpired:
                print(f"[grade] replay {i + 1} exceeded its {limit:.0f} s limit ({len(acts)} steps)", file=sys.stderr, flush=True)
                write(False, {"success": 0, "grader_error": 1, "replay_timed_out": 1, "replay_timeout_s": round(limit, 1),
                              "n_actions": int(len(acts)), "replay_wall_s": round(time.time() - t0, 1), **cost}); return 0
            lines = [l for l in p.stdout.splitlines() if l.startswith("{")]
            runs.append(json.loads(lines[-1]) if lines else {"error": f"replay process rc={p.returncode}"})
        outs = [(r.get("replays") or [{}])[0] for r in runs]
        if any("error" in r or not o for r, o in zip(runs, outs)):
            write(False, {"success": 0, "grader_error": 1, **cost}); return 0
        all_success = all(o.get("success") for o in outs)
        deterministic = len({o.get("state_sha") for o in outs}) == 1
        instance_ok = all(bool(r.get("instance_matches")) for r in runs)
        ok = all_success and deterministic and instance_ok
        out = {"success": int(ok), "all_success": int(all_success), "deterministic": int(deterministic),
               "instance_ok": int(instance_ok), "instance_exact": int(all(bool(r.get("instance_exact")) for r in runs)), "n_actions": int(len(acts)),
               "sim_steps": int(outs[0].get("sim_steps") or 0),
               # the robot fell over in a replay (the tooling's fall rule ended it there; the goal did not hold)
               "fallen": int(any(bool(o.get("fallen")) for o in outs)),
               # progress: the 2026 challenge's q_score of the last replay (before 2026-09-27 this read a key "progress"
               # that the replay does not report, so final_reward was always 0)
               "final_reward": float(outs[-1].get("q_score") or 0.0), "q_score": float(outs[-1].get("q_score") or 0.0),
               "replay_wall_s": round(time.time() - t0, 1), "replay_timeout_s": round(limit, 1), "grader_error": 0,
               "video_rendered": int(os.path.isfile(os.path.join(LOG_DIR, "replay.mp4"))), **cost}
        write(ok, out)
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        write(False, {"success": 0, "grader_error": 1, **cost})
    return 0


if __name__ == "__main__":
    sys.exit(main())
