"""Verifier entry point: replay /app/output/trajectory.npz from the frozen instance and write Harbor rewards.

    python /tests/grade.py --family picking_up_trash --instance /tests/instance.json --traj /app/output/trajectory.npz

Writes /logs/verifier/reward.txt (1/0), reward.json (numeric fields only — Harbor rejects strings), and a
human-viewable replay video /logs/verifier/replay.mp4 (the challenge cameras) from a THIRD fresh-process replay.
Replays `--repeat` times, each in its own FRESH process (`rcb_behavior.py replay`): on Isaac, only the first replay in a
process is bit-exact (an in-process reset leaves PhysX solver / contact state behind), so fresh process == fresh process is the
determinism check. Success requires every replay to complete the task AND all final-state hashes to agree, so a lucky
non-deterministic run cannot pass. The frozen scene rebuilt here from tests/instance.json must also match
the recorded one (`instance_ok`: exact state hash, or every object / joint pose within tolerance on another host).
The graded replays run exactly alike (2026-10-14, failure analysis item 16; the last one used to record the video, with
other cameras; the replays' disagreements that voided 15 completed tasks came from OmniGibson's set order, which the
tooling now fixes, rcb_behavior._stable_hashes); the video is a third replay, capped at VIDEO_CAP_S, whose result never decides anything (`video_replay_matches`
reports whether it ended on the same state). "Success" is the tooling's rule (REST_* in rcb_behavior.py: the BDDL goal
held for 1 s with no goal object in a gripper and every goal object at rest, after the trajectory plus a settle window of
up to 5 s); a replay that ends on a simulator breakdown (the tooling's BREAKDOWN_* check: non-finite or runaway state) is
`sim_breakdown` + `infra_error`, no verdict on the agent.

Whose failure a 0 is (2026-10-10): a file the agent wrote that cannot be graded (not an npz, pickled / object arrays, no
`task` or `actions` entry, wrong shape, non-finite, more than MAX_ROWS rows) is `bad_trajectory` (the agent's 0,
grader_error 0); a replay process that dies, prints no result (`replay_failed`) or runs out of time
(`replay_timed_out`), a frozen scene that does not rebuild to the recorded one here (`instance_ok` 0: dataset /
simulator / hardware drift, decided before the first action) and any other error in this script are `grader_error` +
`infra_error`: no verdict on the agent. Every reward.json carries `deterministic`, `grader_error` and `infra_error`.
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys, time, traceback
import numpy as np

LOG_DIR = os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier")
# Wall-clock limit of ONE replay process, scaled with the trajectory (2026-10-08; time limit only, the verdict rules are
# unchanged). Measured on an idle 8-vCPU L40S host (job #3137): Isaac start + scene load 626 s, and a 10,475-step replay
# had not finished when the old flat 3600 s ran out (< 3.5 control steps/s). Allowance: REPLAY_STARTUP_S for the start plus
# a worst case of REPLAY_MIN_RATE control steps/s, never below the old 3600 s, at most REPLAY_CAP_S;
# task.toml's [verifier] timeout_sec fits two capped replays plus overhead.
# 2026-10-14 (board 0121; owner: a trajectory the grader accepts always gets a verdict): the grader accepts at most
# MAX_ROWS rows (was the tooling's runaway guard, 200,000, which no replay limit covered), and REPLAY_CAP_S is the time of
# MAX_ROWS rows at the worst rate. The basis, from the pool's privileged trials (2026-10-09..14, 484 graded): the longest
# successful trajectory had 25,404 rows (median of 113 successes 4,675), the frozen instances' challenge timeouts reach
# 39,090 steps; the slowest replay measured was the filmed one of a 7,747-row trajectory, 4,851 s with a 725 s start
# (1.88 control steps/s; the start took up to 1,115 s). MAX_ROWS 40,000 is above every challenge timeout and 1.6 times the
# longest success; REPLAY_MIN_RATE 1.5 is 20 % under the slowest measured rate.
MAX_ROWS = 40_000
REPLAY_FLOOR_S, REPLAY_STARTUP_S, REPLAY_MIN_RATE = 3600.0, 1200.0, 1.5
REPLAY_CAP_S = 28000.0                               # >= REPLAY_STARTUP_S + MAX_ROWS / REPLAY_MIN_RATE = 27,867 s
VIDEO_CAP_S = 3600.0                                 # the video replay's own limit (evidence only; a cut video still plays)


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
        write(False, {"success": 0, "deterministic": 0, "missing_trajectory": 1, "grader_error": 0, "infra_error": 0, **cost}); return 0
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # the verifier's own copy of the tooling
        from rcb_behavior import MAX_STEPS
        ACTION_DIM = int(json.load(open(a.instance)).get("action_dim", 25))   # the R1Pro's with the task's robot config
        try:      # the agent's file: whatever is wrong with it is the agent's 0 (bad_trajectory), not a grader error
            with np.load(a.traj, allow_pickle=False) as d:
                task = d["task"]; task = str(task.item() if getattr(task, "shape", None) == () else task)
                acts = np.asarray(d["actions"], dtype=np.float32)
        except Exception as exc:  # noqa: BLE001 -- not an npz, pickled / object arrays, a missing entry, not numbers
            print(f"[grade] unreadable trajectory: {exc!r}", file=sys.stderr, flush=True)
            write(False, {"success": 0, "deterministic": 0, "bad_trajectory": 1, "n_actions": 0, "grader_error": 0, "infra_error": 0, **cost}); return 0
        if task != a.family:
            write(False, {"success": 0, "deterministic": 0, "wrong_family": 1, "grader_error": 0, "infra_error": 0, **cost}); return 0
        if acts.ndim != 2 or acts.shape[1] != ACTION_DIM or acts.shape[0] > min(MAX_ROWS, MAX_STEPS) or not np.all(np.isfinite(acts)):
            write(False, {"success": 0, "deterministic": 0, "bad_trajectory": 1, "n_actions": int(acts.shape[0]) if acts.ndim == 2 else 0, "grader_error": 0, "infra_error": 0, **cost}); return 0
        tool = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rcb_behavior.py")
        t0 = time.time(); runs = []; limit = replay_timeout(int(acts.shape[0]))
        for i in range(a.repeat):     # the graded replays: all alike (tiny cameras, no video)
            cmd = [sys.executable, tool, "replay", "--task", a.family, "--instance", a.instance, "--traj", a.traj]
            try:
                p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=sys.stderr, text=True, timeout=limit, env={**os.environ, "RCB_SESSION_LOG": ""})
            except subprocess.TimeoutExpired:
                print(f"[grade] replay {i + 1} exceeded its {limit:.0f} s limit ({len(acts)} steps)", file=sys.stderr, flush=True)
                write(False, {"success": 0, "deterministic": 0, "grader_error": 1, "infra_error": 1, "replay_timed_out": 1, "replay_timeout_s": round(limit, 1),
                              "n_actions": int(len(acts)), "replay_wall_s": round(time.time() - t0, 1), **cost}); return 0
            lines = [l for l in p.stdout.splitlines() if l.startswith("{")]
            runs.append(json.loads(lines[-1]) if lines else {"error": f"replay process rc={p.returncode}"})
        outs = [(r.get("replays") or [{}])[0] for r in runs]
        if any("error" in r or not o for r, o in zip(runs, outs)):
            print(f"[grade] a replay did not run to its result: {[r.get('error') for r in runs]}", file=sys.stderr, flush=True)
            write(False, {"success": 0, "deterministic": 0, "grader_error": 1, "infra_error": 1, "replay_failed": 1, "n_actions": int(len(acts)), **cost}); return 0
        all_success = all(o.get("success") for o in outs)
        deterministic = len({o.get("state_sha") for o in outs}) == 1
        instance_ok = all(bool(r.get("instance_matches")) for r in runs)
        breakdown = any(bool(o.get("breakdown")) for o in outs)   # a simulator breakdown: infrastructure, no verdict
        if breakdown:
            print(f"[grade] simulator breakdown in a replay: {[o.get('end_reason') for o in outs]}", file=sys.stderr, flush=True)
        ok = all_success and deterministic and instance_ok and not breakdown
        video = {"video_rendered": 0, "video_replay_matches": 0}
        if not a.no_video:            # the video: a third replay with the challenge cameras, evidence only
            vpath = os.path.join(LOG_DIR, "replay.mp4")
            vcmd = [sys.executable, tool, "replay", "--task", a.family, "--instance", a.instance, "--traj", a.traj,
                    "--video", vpath, "--fps", str(a.video_fps)]
            try:
                vp = subprocess.run(vcmd, stdout=subprocess.PIPE, stderr=sys.stderr, text=True, timeout=min(limit, VIDEO_CAP_S),
                                    env={**os.environ, "RCB_SESSION_LOG": ""})
                vl = [l for l in vp.stdout.splitlines() if l.startswith("{")]
                vo = ((json.loads(vl[-1]).get("replays") or [{}])[0]) if vl else {}
                video["video_replay_matches"] = int(bool(vo.get("state_sha")) and vo.get("state_sha") == outs[0].get("state_sha"))
            except Exception as exc:  # noqa: BLE001 -- the video never decides the verdict (a timeout keeps a playable cut)
                print(f"[grade] video replay: {exc!r}"[:300], file=sys.stderr, flush=True)
            video["video_rendered"] = int(os.path.isfile(vpath))
        out = {"success": int(ok), "all_success": int(all_success), "deterministic": int(deterministic),
               # instance_ok 0: the frozen scene did not rebuild to the recorded one in the verifier (dataset / simulator /
               # hardware drift, decided before the first action): an infrastructure failure, not the agent's 0
               "instance_ok": int(instance_ok), "infra_error": int(not instance_ok or breakdown), "instance_exact": int(all(bool(r.get("instance_exact")) for r in runs)), "n_actions": int(len(acts)),
               "sim_breakdown": int(breakdown),
               # the BDDL goal at the end of the last replay, and the settle window it ran (the success rule, REST_*)
               "goal": int(bool(outs[-1].get("goal"))), "settle_steps": int(outs[-1].get("settle_steps") or 0),
               "sim_steps": int(outs[0].get("sim_steps") or 0),
               # the robot fell over in a replay (the tooling's fall rule ended it there; the goal did not hold)
               "fallen": int(any(bool(o.get("fallen")) for o in outs)),
               # progress: the 2026 challenge's q_score of the last replay (before 2026-09-27 this read a key "progress"
               # that the replay does not report, so final_reward was always 0)
               "final_reward": float(outs[-1].get("q_score") or 0.0), "q_score": float(outs[-1].get("q_score") or 0.0),
               "replay_wall_s": round(time.time() - t0, 1), "replay_timeout_s": round(limit, 1), "grader_error": int(not instance_ok),
               **video, **cost}
        write(ok, out)
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        write(False, {"success": 0, "deterministic": 0, "grader_error": 1, "infra_error": 1, **cost})
    return 0


if __name__ == "__main__":
    sys.exit(main())
