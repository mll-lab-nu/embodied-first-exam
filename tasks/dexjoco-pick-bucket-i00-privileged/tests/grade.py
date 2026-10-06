"""Verifier entry point for the privileged DexJoCo tasks: replay /app/output/trajectory.npz from the frozen instance and
write Harbor rewards.

    python /tests/grade.py --family water_plant --instance /tests/instance.npz --traj /app/output/trajectory.npz

Writes /logs/verifier/reward.txt (1/0), reward.json (numeric fields only; Harbor rejects strings), a replay video
/logs/verifier/replay.mp4 (front camera + wrist camera) and replay.last.png. Replays `--repeat` times in this fresh
process; success requires every replay to end its episode in success (DexJoCo's own rule: the episode ends at the first
success or task failure) AND all final-state hashes to agree (MuJoCo on the CPU is bit-deterministic), and the frozen
instance rebuilt here from tests/instance.npz must match its recorded hash.
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


def self_reported_cost() -> dict:
    # From the tooling's append-only log in the agent's container: SELF-REPORTED accounting, never evidence.
    cost = {"agent_sessions": 0, "agent_resets": 0, "agent_sim_steps": 0, "agent_records": 0, "agent_replays": 0,
            "agent_cost_self_reported": 1}
    try:
        with open("/app/output/rcb_session_log.jsonl") as f:
            for i, line in enumerate(f):
                if i > 200_000 or len(line) > 10_000:
                    break
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
    return cost


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", required=True); ap.add_argument("--instance", required=True)
    ap.add_argument("--traj", default="/app/output/trajectory.npz"); ap.add_argument("--repeat", type=int, default=2)
    ap.add_argument("--no-video", action="store_true")
    a = ap.parse_args()
    cost = self_reported_cost()
    os.environ["RCB_SESSION_LOG"] = ""  # the verifier's own sessions are not the agent's cost
    if not os.path.isfile(a.traj):
        write(False, {"success": 0, "missing_trajectory": 1, "grader_error": 0, **cost}); return 0
    s = None
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # the verifier's own copy of the tooling
        import rcb_dexjoco
        rcb_dexjoco.SESSION_LOG = ""
        from rcb_dexjoco import Session, MAX_STEPS
        d = np.load(a.traj, allow_pickle=False)
        if str(d["task"]) != a.family:
            write(False, {"success": 0, "wrong_family": 1, "grader_error": 0, **cost}); return 0
        acts = np.asarray(d["actions"], dtype=np.float64)
        s = Session(a.family, instance=a.instance)
        if (acts.ndim != 2 or acts.shape[1] != s.action_dim or acts.shape[0] > MAX_STEPS
                or not np.all(np.isfinite(acts))):
            write(False, {"success": 0, "bad_trajectory": 1, "grader_error": 0,
                          "n_actions": int(acts.shape[0]) if acts.ndim == 2 else 0, **cost}); return 0
        t0 = time.time()
        outs = []
        for _ in range(a.repeat):
            try:
                outs.append(s.replay(acts))
            except (ValueError, rcb_dexjoco.PrimitiveError):
                write(False, {"success": 0, "bad_trajectory": 1, "grader_error": 0, "n_actions": int(len(acts)), **cost}); return 0
        all_success = all(o["success"] for o in outs)
        deterministic = len({o["state_sha"] for o in outs}) == 1
        instance_ok = bool(s.instance_exact)
        ok = all_success and deterministic and instance_ok
        out = {"success": int(ok), "all_success": int(all_success), "deterministic": int(deterministic),
               "instance_ok": int(instance_ok), "n_actions": int(len(acts)), "sim_steps": int(outs[0]["steps"]),
               "task_failure": int(bool(outs[0]["reason"]) and not outs[0]["success"]),
               "replay_wall_s": round(time.time() - t0, 1), "grader_error": 0, "video_rendered": 0, **cost}
        if not a.no_video:  # human-viewable replay (never affects the verdict)
            try:
                n = int(outs[0]["replayed_rows"])
                s.render_video(acts[:n], os.path.join(LOG_DIR, "replay.mp4"), cameras=s.video_cameras(), every=max(2, -(-n // 1500)))
                import imageio.v2 as imageio
                imageio.imwrite(os.path.join(LOG_DIR, "replay.last.png"), s.render_frame(s.default_camera(), (480, 640)))
                out["video_rendered"] = int(os.path.isfile(os.path.join(LOG_DIR, "replay.mp4")))
            except Exception:  # noqa: BLE001
                traceback.print_exc(file=sys.stderr)
        write(ok, out)
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        write(False, {"success": 0, "grader_error": 1, **cost})
    finally:
        if s is not None:
            s.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
