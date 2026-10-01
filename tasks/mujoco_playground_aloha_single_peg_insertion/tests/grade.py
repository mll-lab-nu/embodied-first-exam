"""MuJoCo Playground ALOHA verifier (separate sandbox): replay /app/output/trajectory.npz twice from the frozen
instance; success = the environment's success check (rcb_aloha.Session.check) at the end of the trajectory, in both
replays with bit-identical final states. Renders /logs/verifier/replay.mp4 and the agent's own rollouts
(self-reported traces, agent_sessions/)."""
import glob, json, math, os, sys, time, traceback
import numpy as np
os.environ["RCB_SESSION_LOG"] = ""; os.environ["RCB_AGENT_TRACE_DIR"] = ""
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
LOG = "/logs/verifier"; os.makedirs(LOG, exist_ok=True)
# Videos come after the verdict and must end well inside the verifier timeout, even on software rendering (~1.3 s a
# frame): the replay video has at most MAX_FRAMES frames, agent-rollout videos start only while under the budget.
T0 = time.time(); RENDER_BUDGET_S = float(os.environ.get("RCB_RENDER_BUDGET_S", "600")); MAX_FRAMES = 400


def write(ok: bool, out: dict) -> None:
    open(f"{LOG}/reward.txt", "w").write("1\n" if ok else "0\n"); json.dump(out, open(f"{LOG}/reward.json", "w")); print(json.dumps(out))


def cost() -> dict:
    c = {"agent_sessions": 0, "agent_resets": 0, "agent_cost_self_reported": 1}
    try:
        for i, line in enumerate(open(next((f for f in ("/logs/agent/rcb/rcb_session_log.jsonl", "/app/output/rcb_session_log.jsonl") if os.path.exists(f)), "/app/output/rcb_session_log.jsonl"))):
            if i > 200_000 or len(line) > 10_000: break
            try:
                ev = json.loads(line).get("ev"); c["agent_sessions"] += ev == "session_start"; c["agent_resets"] += ev == "reset"
            except Exception: continue
    except Exception: pass
    return c


def main() -> int:
    c = cost(); traj = "/app/output/trajectory.npz"
    if not os.path.isfile(traj):
        write(False, {"success": 0, "missing_trajectory": 1, "grader_error": 0, **c}); return 0
    try:
        import rcb_aloha as ra
        A = np.asarray(np.load(traj, allow_pickle=False)["actions"], dtype=np.float64)
        if A.ndim != 2 or A.shape[1] != ra.N or len(A) > ra.MAX_STEPS or not np.all(np.isfinite(A)):
            write(False, {"success": 0, "bad_trajectory": 1, "n_actions": int(A.shape[0]) if A.ndim == 2 else 0, "grader_error": 0, **c}); return 0
        s = ra.Session("/tests/instance.json", enable_render=True)
        r1 = s.replay(A); r2 = s.replay(A); det = r1["state_sha"] == r2["state_sha"]; ok = bool(det and r1["success"])
        fields = {k: (int(v) if isinstance(v, bool) else v) for k, v in r1.items() if k not in ("success", "state_sha", "steps") and isinstance(v, (bool, int, float))}
        out = {"success": int(ok), "live_check_success": int(bool(r1["success"])), "deterministic": int(det), **fields,
               "n_actions": int(len(A)), "video_rendered": 0, "grader_error": 0, **c}
        write(ok, out)
        try: s.render_video(A, f"{LOG}/replay.mp4", every=max(2, math.ceil(len(A) / MAX_FRAMES)), fps=25); out["video_rendered"] = 1
        except Exception: traceback.print_exc(file=sys.stderr)
        try:
            files = sorted((glob.glob("/logs/agent/rcb/rcb_trace/*.npz") + glob.glob("/app/output/rcb_trace/*.npz")), key=os.path.getmtime)[:2000]; idx = []
            for f in files:
                try:
                    t = np.load(f, allow_pickle=False)["actions"]
                    if t.ndim == 2 and t.shape[1] == ra.N and len(t) <= ra.MAX_STEPS and np.all(np.isfinite(t)): idx.append((f, len(t)))
                except Exception: continue
            out["agent_traces"] = len(idx); out["agent_trace_videos"] = 0
            if idx:
                od = f"{LOG}/agent_sessions"; os.makedirs(od, exist_ok=True); meta = []
                for k, (f, n) in enumerate([x for x in idx if x[1] >= 25][-6:]):
                    if time.time() - T0 > RENDER_BUDGET_S: out["agent_trace_videos_skipped_budget"] = 1; break
                    r = s.render_video(np.load(f)["actions"], f"{od}/{k:02d}_{os.path.basename(f)[:-4]}.mp4", every=max(4, math.ceil(n / MAX_FRAMES)), fps=12)
                    meta.append({"trace": os.path.basename(f), "steps": n, "success": r["success"]}); out["agent_trace_videos"] += 1
                json.dump({"self_reported": True, "traces": [os.path.basename(f) for f, _ in idx], "videos": meta}, open(f"{od}/index.json", "w"), indent=1)
        except Exception: traceback.print_exc(file=sys.stderr)
        write(ok, out)
    except Exception:
        traceback.print_exc(file=sys.stderr); write(False, {"success": 0, "grader_error": 1, **c})
    return 0


if __name__ == "__main__":
    sys.exit(main())
