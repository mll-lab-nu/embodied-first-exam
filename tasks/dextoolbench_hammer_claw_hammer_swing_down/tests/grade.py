"""DexToolBench verifier (separate sandbox): replay /app/output/trajectory.npz twice from the frozen start state and
score the benchmark's task progress (goals reached / goals, 1.5 cm keypoint tolerance, 10 s per goal).
reward.txt = progress when both replays agree bit-exactly (else 0); success = every goal reached.
Also renders /logs/verifier/replay.mp4 (front / side / top / oblique) and, after the verdict, videos of the agent's own
rollouts from its self-reported traces (agent_sessions/)."""
import glob, json, os, sys, traceback
import numpy as np
os.environ["RCB_SESSION_LOG"] = ""; os.environ["RCB_AGENT_TRACE_DIR"] = ""
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
LOG = "/logs/verifier"; os.makedirs(LOG, exist_ok=True)


def write(reward: float, out: dict) -> None:
    open(f"{LOG}/reward.txt", "w").write(f"{reward:.4f}\n"); json.dump(out, open(f"{LOG}/reward.json", "w")); print(json.dumps(out))


def cost() -> dict:
    c = {"agent_sessions": 0, "agent_resets": 0, "agent_control_steps": 0, "agent_cost_self_reported": 1}
    try:
        for i, line in enumerate(open("/app/output/rcb_session_log.jsonl")):
            if i > 200_000 or len(line) > 10_000: break
            try:
                e = json.loads(line); ev = e.get("ev")
                if ev == "session_start": c["agent_sessions"] += 1
                elif ev == "reset": c["agent_resets"] += 1
                elif ev == "session_end": c["agent_control_steps"] += min(int(float(e.get("sim_steps", 0) or 0)) // 10, 10**9)
            except Exception: continue
    except Exception: pass
    return c


def main() -> int:
    c = cost(); traj = "/app/output/trajectory.npz"
    if not os.path.isfile(traj):
        write(0.0, {"success": 0, "progress": 0.0, "missing_trajectory": 1, "grader_error": 0, **c}); return 0
    try:
        import rcb_dtb
        d = np.load(traj, allow_pickle=False); A = np.asarray(d["actions"], dtype=np.float64)
        if A.ndim != 2 or A.shape[1] != rcb_dtb.N or A.shape[0] > 100_000 or not np.all(np.isfinite(A)):
            write(0.0, {"success": 0, "progress": 0.0, "bad_trajectory": 1, "grader_error": 0, **c}); return 0
        s = rcb_dtb.Session("/tests/instance.json", enable_render=True)
        r1 = s.replay(A); r2 = s.replay(A); det = r1["state_sha"] == r2["state_sha"] and r1["reached"] == r2["reached"]
        prog = float(r1["progress"]) if det else 0.0
        out = {"success": int(det and r1["done"]), "progress": round(prog, 4), "goals_reached": int(r1["reached"]), "n_goals": int(r1["n_goals"]),
               "failed_on_timeout": int(bool(r1["failed"])), "deterministic": int(det), "n_actions": int(len(A)), "control_steps_used": int(r1["steps"]),
               "video_rendered": 0, "grader_error": 0, **c}
        write(prog, out)
        try:
            s.render_video(A, f"{LOG}/replay.mp4", every=2, fps=30); out["video_rendered"] = 1
        except Exception: traceback.print_exc(file=sys.stderr)
        try:  # agent rollouts (self-reported traces): last 6 with >= 30 control steps
            files = sorted(glob.glob("/app/output/rcb_trace/*.npz"), key=os.path.getmtime)[:2000]; od = f"{LOG}/agent_sessions"; idx = []
            for f in files:
                try:
                    t = np.load(f, allow_pickle=False)["actions"]
                    if t.ndim == 2 and t.shape[1] == rcb_dtb.N and len(t) <= 100_000 and np.all(np.isfinite(t)): idx.append((f, len(t)))
                except Exception: continue
            out["agent_traces"] = len(idx); out["agent_trace_videos"] = 0
            if idx:
                os.makedirs(od, exist_ok=True); meta = []
                for k, (f, n) in enumerate([x for x in idx if x[1] >= 30][-6:]):
                    r = s.render_video(np.load(f)["actions"], f"{od}/{k:02d}_{os.path.basename(f)[:-4]}.mp4", every=4, fps=15)
                    meta.append({"trace": os.path.basename(f), "steps": n, "reached": r["reached"]}); out["agent_trace_videos"] += 1
                json.dump({"self_reported": True, "traces": [os.path.basename(f) for f, _ in idx], "videos": meta}, open(f"{od}/index.json", "w"), indent=1)
        except Exception: traceback.print_exc(file=sys.stderr)
        write(prog, out)
    except Exception:
        traceback.print_exc(file=sys.stderr); write(0.0, {"success": 0, "progress": 0.0, "grader_error": 1, **c})
    return 0


if __name__ == "__main__":
    sys.exit(main())
