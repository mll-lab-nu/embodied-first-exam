"""Verifier entry point: replay /app/output/trajectory.npz from the frozen instance and write Harbor rewards.
Adapted from robot_coding_bench's RoboWits grader (fa59c1a6: tasks/robowits-stack-cubes-i00/tests/grade.py).

    python /tests/grade.py --family cube_pick_place --instance /tests/instance.json --traj /app/output/trajectory.npz

Writes /logs/verifier/reward.txt (1/0), reward.json (numeric fields only — Harbor rejects strings), and a
human-viewable replay video /logs/verifier/replay.mp4 (all cameras tiled) plus replay.last.png, rendered during the last of
the `--repeat` (2) replays in this fresh process: two passes in all, no separate video replay. TopoGym's physics runs on
the GPU, whose contact solver is not bit-exact (the rule of robot_coding_bench's GPU backend): every replay must complete
the task; the final-state hashes (`deterministic`) and the rebuilt frozen scene (`instance_ok`: exact state hash, or
every object / joint pose within tolerance). Instance compatibility is required; exact GPU hashes are diagnostic.
"""
from __future__ import annotations
import argparse, json, os, sys, time, traceback
import numpy as np

LOG_DIR = os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier")


def write(ok: bool, out: dict, *, evidence=None) -> None:
    from rcb_topogym import atomic_json
    # This record commits before media close and is the authority for recovery.
    atomic_json(os.path.join(LOG_DIR, "verdict.json"), {"schema_version": 2, "reward": out, "success": bool(ok), "evidence": evidence or {}})
    atomic_json(os.path.join(LOG_DIR, "reward.json"), out)
    atomic_json(os.path.join(LOG_DIR, "reward.txt"), int(ok))
    print(json.dumps(out), flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", required=True); ap.add_argument("--instance", required=True)
    ap.add_argument("--traj", default="/app/output/trajectory.npz"); ap.add_argument("--repeat", type=int, default=2)
    ap.add_argument("--no-video", action="store_true"); ap.add_argument("--video-fps", type=int, default=15)
    a = ap.parse_args()
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
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
    from rcb_topogym import Session, InvalidTrajectory, InstanceMismatch, load_trajectory, atomic_json
    try:
        inst = json.load(open(a.instance))  # trusted input failure remains infrastructure failure
        if type(inst.get("action_dim")) is not int or not 0 < inst["action_dim"] <= 1024:
            raise ValueError("invalid action dimension in trusted instance")
        try:
            acts, _ = load_trajectory(a.traj, a.family, int(inst["action_dim"]))
        except InvalidTrajectory as exc:
            atomic_json(os.path.join(LOG_DIR, "submission_error.json"), {"error": str(exc)})
            write(False, {"success": 0, "bad_trajectory": 1, "grader_error": 0, **cost})
            return 0
        if a.repeat < 2:
            raise ValueError("grading requires at least two replays")
        s = Session(a.family, instance=a.instance, strict=True)
        if not s.instance_matches:
            raise InstanceMismatch("rebuilt instance differs from the frozen instance")
        t0 = time.time()
        outs, video_error = [], None
        while len(outs) < a.repeat:
            if len(outs) == a.repeat - 1 and not a.no_video:
                try:
                    s.start_video(os.path.join(LOG_DIR, "replay.mp4"), fps=a.video_fps)
                except Exception as exc:
                    video_error = repr(exc)[:200]
            # Physics errors must not be reclassified as video errors or retried away.
            outs.append(s.replay(acts))
        all_success = all(o["success"] for o in outs)
        deterministic = len({o["state_sha"] for o in outs}) == 1
        ok = all_success and bool(s.instance_matches)
        out = {"success": int(ok), "all_success": int(all_success), "deterministic": int(deterministic), "gpu_backend": 1,
               "instance_ok": int(bool(s.instance_matches)), "instance_exact": int(bool(s.instance_exact)),
               "n_actions": int(outs[-1]["sim_steps"]), "submitted_actions": int(len(acts)),
               "sim_steps": int(outs[-1]["sim_steps"]), "physics_steps": int(outs[-1].get("physics_steps", 0)),
               "sim_time_s": float(outs[-1].get("sim_time_s", 0)), "final_reward": float(outs[-1].get("progress") or 0.0),
               "replay_wall_s": round(time.time() - t0, 1), "replays": len(outs), "grader_error": 0, "video_rendered": 0, **cost}
        import hashlib, uuid
        from pathlib import Path
        evidence = dict(commit_id=uuid.uuid4().hex, replays=outs,
                        trajectory_sha256=hashlib.sha256(Path(a.traj).read_bytes()).hexdigest(),
                        instance_sha256=hashlib.sha256(Path(a.instance).read_bytes()).hexdigest())
        write(ok, out, evidence=evidence)
        atomic_json(os.path.join(LOG_DIR, "media.json"), {"status": "pending" if not a.no_video else "disabled"})
        if not a.no_video:
            try:
                s.stop_video()
                out["video_rendered"] = int(os.path.isfile(os.path.join(LOG_DIR, "replay.mp4")))
            except Exception as exc:
                traceback.print_exc(file=sys.stderr); video_error = repr(exc)[:200]
            atomic_json(os.path.join(LOG_DIR, "media.json"), {"status": "error" if video_error else "complete", "error": video_error})
            write(ok, out, evidence=evidence)
    except InstanceMismatch as exc:
        atomic_json(os.path.join(LOG_DIR, "instance_error.json"), {"error": str(exc)})
        write(False, {"success": 0, "instance_mismatch": 1, "grader_error": 0, **cost})
    except Exception:
        traceback.print_exc(file=sys.stderr)
        # Never overwrite a committed verdict because compatibility/media publication failed.
        if not os.path.isfile(os.path.join(LOG_DIR, "verdict.json")):
            write(False, {"success": 0, "grader_error": 1, **cost})
    finally:
        if s is not None:
            s.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
