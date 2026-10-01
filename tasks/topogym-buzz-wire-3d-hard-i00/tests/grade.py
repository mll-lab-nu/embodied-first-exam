"""Verifier entry point: replay /app/output/trajectory.npz from the frozen instance and write Harbor rewards.
Adapted from robot_coding_bench's RoboWits grader (fa59c1a6: tasks/robowits-stack-cubes-i00/tests/grade.py).

    python /tests/grade.py --family cube_pick_place --instance /tests/instance.json --traj /app/output/trajectory.npz

Writes /logs/verifier/reward.txt (1/0), reward.json (numeric fields only — Harbor rejects strings), and a
human-viewable replay video /logs/verifier/replay.mp4 (all cameras tiled) plus replay.last.png.
Replays `--repeat` times in this fresh process. TopoGym's physics runs on the GPU, whose contact solver is not
bit-exact (the rule of robot_coding_bench's GPU backend): every replay must complete the task; the final-state hashes
(`deterministic`) and the rebuilt frozen scene (`instance_ok`: exact state hash, or every object / joint pose within
tolerance) are reported and not required.
"""
from __future__ import annotations
import argparse, json, os, sys, time, traceback
import numpy as np

LOG_DIR = os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier")


def write(ok: bool, out: dict) -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    open(os.path.join(LOG_DIR, "reward.txt"), "w").write("1\n" if ok else "0\n")
    json.dump(out, open(os.path.join(LOG_DIR, "reward.json"), "w"))
    print(json.dumps(out), flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", required=True); ap.add_argument("--instance", required=True)
    ap.add_argument("--traj", default="/app/output/trajectory.npz"); ap.add_argument("--repeat", type=int, default=2)
    ap.add_argument("--no-video", action="store_true"); ap.add_argument("--video-fps", type=int, default=15)
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
    s = None
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # the verifier's own copy of the tooling
        from rcb_topogym import Session, MAX_STEPS
        inst = json.load(open(a.instance))
        d = np.load(a.traj, allow_pickle=False)
        if str(d["task"]) != a.family:
            write(False, {"success": 0, "wrong_family": 1, "grader_error": 0, **cost}); return 0
        acts = np.asarray(d["actions"], dtype=np.float32)
        dim = int(inst["action_dim"])
        if acts.ndim != 2 or acts.shape[1] != dim or acts.shape[0] > MAX_STEPS or not np.all(np.isfinite(acts)):
            write(False, {"success": 0, "bad_trajectory": 1, "n_actions": int(acts.shape[0]) if acts.ndim == 2 else 0, "grader_error": 0, **cost}); return 0
        s = Session(a.family, instance=a.instance)
        t0 = time.time()
        outs = [s.replay(acts) for _ in range(a.repeat)]
        all_success = all(o["success"] for o in outs)
        deterministic = len({o["state_sha"] for o in outs}) == 1
        instance_ok = bool(s.instance_matches)
        gpu = True     # TopoGym's physics always runs on CUDA: neither the hash agreement nor the frozen-state check is required
        ok = all_success and (gpu or (deterministic and instance_ok))
        out = {"success": int(ok), "all_success": int(all_success), "deterministic": int(deterministic), "gpu_backend": int(gpu),
               "instance_ok": int(instance_ok), "instance_exact": int(bool(s.instance_exact)), "n_actions": int(len(acts)),
               "sim_steps": int(outs[0]["sim_steps"]), "final_reward": float(outs[-1].get("progress") or 0.0),
               "replay_wall_s": round(time.time() - t0, 1), "grader_error": 0, "video_rendered": 0, **cost}
        # Human-viewable replay video (never affects the verdict): /logs/verifier/replay.mp4 + replay.last.png
        if not a.no_video:
            try:
                s.start_video(os.path.join(LOG_DIR, "replay.mp4"), fps=a.video_fps); s.replay(acts); s.stop_video()
                out["video_rendered"] = int(os.path.isfile(os.path.join(LOG_DIR, "replay.mp4")))
            except Exception:  # noqa: BLE001
                traceback.print_exc(file=sys.stderr)
        write(ok, out)
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        write(False, {"success": 0, "grader_error": 1, **cost})
    finally:
        if s is not None:
            s.close()  # reward files are already written
    return 0


if __name__ == "__main__":
    sys.exit(main())
