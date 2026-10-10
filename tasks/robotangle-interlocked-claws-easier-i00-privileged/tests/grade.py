"""Verifier entry point: replay /app/output/trajectory.npz from the frozen instance and write Harbor rewards.
Adapted from robot_coding_bench's RoboWits grader (fa59c1a6: tasks/robowits-stack-cubes-i00/tests/grade.py).

    python /tests/grade.py --family cube_pick_place --instance /tests/instance.json --traj /app/output/trajectory.npz

Writes /logs/verifier/reward.txt (1/0), reward.json (numeric fields only — Harbor rejects strings), and a
human-viewable replay video /logs/verifier/replay.mp4 (all cameras tiled) plus replay.last.png, rendered during the last of
the `--repeat` (2) replays in this fresh process: two passes in all, no separate video replay. TopoGym's physics runs on
the GPU, whose contact solver is not bit-exact (the rule of robot_coding_bench's GPU backend): every replay must complete
the task. Initial state and runtime binding must match exactly; final-state determinism is reported separately.
The replays are grading replays (rcb_topogym.Session.replay(grading=True), tooling v16): for the GPU families the rows run
with the instance's own thresholds and, if the episode has not ended after the last row, the final targets are held for up
to 2 s with the replay tolerances (rcb_topogym.REPLAY_TOLERANCES). R-hold (the user's decision, 2026-10-05): every replay
may confirm within that hold, exactly as in standard mode, and no replay has to meet the strict goal within the rows any
more (the recording ends on the live success tick, so that replay had zero margin); the live run stays strict. The strict
goal is still reported (`strict_goal_reached`, `strict_goal_row`; verdict.json `evidence.strict_goal`), and
`strict_replay_required` 0 marks the rule. Each replay's "grading" record is in verdict.json; `replay_hold_steps` /
`replay_tolerance_needed` summarize them.
Task-contact penetration is evidence, not a verdict (tooling v16): a success during whose replays a task contact went deep
(rcb_topogym.CONTACT_RULE, each replay's status "review") is not credited automatically: success 0 with
`success_pending_review` 1, the events in verdict.json `evidence.review` and frames around them in review_frames/ (one more
replay, after the verdict and the video); a clean success is credited. Forcing (rcb_topogym.FORCING, each replay's status
"forcing") is evidence only: verdict.json `evidence.forcing`, `forcing_events`, and frames around it when a success is held.
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
    from rcb_topogym import Session, InvalidTrajectory, InstanceMismatch, load_trajectory, atomic_json, strict_goal
    try:
        inst = json.load(open(a.instance))  # trusted input failure remains infrastructure failure
        if type(inst.get("action_dim")) is not int or not 0 < inst["action_dim"] <= 1024:
            raise ValueError("invalid action dimension in trusted instance")
        try:
            acts, _ = load_trajectory(a.traj, a.family, int(inst["action_dim"]), layout=inst["action_layout"])
        except InvalidTrajectory as exc:
            atomic_json(os.path.join(LOG_DIR, "submission_error.json"), {"error": str(exc)})
            write(False, {"success": 0, "bad_trajectory": 1, "grader_error": 0, **cost})
            return 0
        if a.repeat < 2:
            raise ValueError("grading requires at least two replays")
        s = Session(a.family, instance=a.instance, strict=True)
        # A frozen PBD state prepared on another GPU is generated from the instance's recipe on this one (instance_generated)
        generated = bool(getattr(s, "instance_generated", False))
        # A CPU of another instruction-set class realizes the frozen recipe's assets with other bytes (instance_realized)
        realized = bool(getattr(s, "instance_realized", False))
        if not s.instance_matches or not (s.instance_exact or generated or realized) or not s.runtime_binding:
            raise InstanceMismatch("verifier requires the frozen instance (exact, or its recipe realized on this GPU or CPU) and a runtime binding")
        t0 = time.time()
        outs, video_error = [], None
        while len(outs) < a.repeat:
            if len(outs) == a.repeat - 1 and not a.no_video:
                try:
                    s.start_video(os.path.join(LOG_DIR, "replay.mp4"), fps=a.video_fps)
                except Exception as exc:
                    video_error = repr(exc)[:200]
            # Physics errors must not be reclassified as video errors or retried away.
            outs.append(s.replay(acts, grading=True))
        all_success = all(o["success"] for o in outs)
        deterministic = len({o["state_sha"] for o in outs}) == 1
        # A replay that ended in a numerically unstable simulation (rcb_topogym.SIMULATOR_INSTABILITY) is an infrastructure
        # failure: never success, never the task's failure (the evidence is in verdict.json's replays[].instability).
        unstable = any(o.get("episode_end") == "simulator_instability" for o in outs)
        # R-hold (2026-10-05): each replay may confirm within the tolerant hold (as in standard); the strict goal is reported only
        goal = strict_goal(outs)
        ok = all_success and bool(s.instance_matches) and not unstable
        # a success with a deep task contact in either replay is held for review, not credited automatically
        reviews = [o.get("review") for o in outs]
        pending = ok and any(reviews)
        credited = ok and not pending
        forcing = [o.get("forcing") for o in outs]          # evidence only: never a verdict
        grading = [o.get("grading") or {} for o in outs]
        out = {"success": int(credited), "success_pending_review": int(pending),
               "review_events": max(int((r or {}).get("count", 0)) for r in reviews),
               "review_max_depth_mm": max(float((r or {}).get("max_depth_mm", 0.)) for r in reviews),
               "forcing_events": max(int((f or {}).get("count", 0)) for f in forcing),
               "all_success": int(all_success), "deterministic": int(deterministic), "gpu_backend": 1,
               "infra_error": int(unstable), "simulator_instability": int(unstable),
               "instance_ok": int(bool(s.instance_matches)), "instance_exact": int(bool(s.instance_exact)),
               "initial_state_generated": int(generated), "instance_realized": int(realized),
               "assets_exact": int(bool(getattr(s, "assets_exact", True))),
               "runtime_binding_ok": 1,
               "n_actions": int(grading[-1].get("rows", outs[-1]["sim_steps"])), "submitted_actions": int(len(acts)),
               "sim_steps": int(outs[-1]["sim_steps"]), "physics_steps": int(outs[-1].get("physics_steps", 0)),
               "sim_time_s": float(outs[-1].get("sim_time_s", 0)), "final_reward": float(outs[-1].get("progress") or 0.0),
               "replay_wall_s": round(time.time() - t0, 1), "replays": len(outs), "grader_error": 0, "video_rendered": 0,
               "replay_hold_steps": max(int(g.get("hold_steps", 0)) for g in grading),
               "replay_tolerance_needed": int(any(g.get("tolerance_needed") for g in grading)),
               "strict_goal_reached": int(goal is not None), "strict_goal_row": goal[1] if goal else 0,
               "strict_replay_required": 0, **cost}
        import hashlib, uuid
        from pathlib import Path
        evidence = dict(commit_id=uuid.uuid4().hex, replays=outs,
                        runtime_binding=s.runtime_binding, initial_state=getattr(s, "initial_state", None),
                        strict_goal=dict(replay=goal[0], row=goal[1]) if goal else None,
                        review=dict(pending=pending, replays=reviews) if any(reviews) else None,
                        forcing=forcing if any(forcing) else None,
                        trajectory_sha256=hashlib.sha256(Path(a.traj).read_bytes()).hexdigest(),
                        instance_sha256=hashlib.sha256(Path(a.instance).read_bytes()).hexdigest())
        write(credited, out, evidence=evidence)
        atomic_json(os.path.join(LOG_DIR, "media.json"), {"status": "pending" if not a.no_video else "disabled"})
        if not a.no_video:
            try:
                s.stop_video()
                out["video_rendered"] = int(os.path.isfile(os.path.join(LOG_DIR, "replay.mp4")))
            except Exception as exc:
                traceback.print_exc(file=sys.stderr); video_error = repr(exc)[:200]
            atomic_json(os.path.join(LOG_DIR, "media.json"), {"status": "error" if video_error else "complete", "error": video_error})
            write(credited, out, evidence=evidence)
        if pending:      # frames around the review and forcing events, for the reviewer (one more replay; the verdict is committed)
            try:
                k = next(i for i, r in enumerate(reviews) if r)
                events = reviews[k]["events"] + ((forcing[k] or {}).get("events") or [])
                files = s.render_review_frames(acts, events, os.path.join(LOG_DIR, "review_frames"))
                evidence["review"]["frames"] = [os.path.relpath(f, LOG_DIR) for f in files]
            except Exception as exc:
                traceback.print_exc(file=sys.stderr); evidence["review"]["frames_error"] = repr(exc)[:200]
            write(credited, out, evidence=evidence)
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
