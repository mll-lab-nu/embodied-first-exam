"""Limited-mode verifier for the MuJoCo tasks: reads what the sim service (which the agent could not touch) wrote.
/data/final.json holds a fresh replay's verdict of the recorded episode (deterministic = the replay ends in the live
episode's final state). DexToolBench: reward = task progress (goals reached / goals); Playground: reward = success."""
import json, os, shutil
LOG = "/logs/verifier"; os.makedirs(LOG, exist_ok=True)
def write(reward, out):
    open(f"{LOG}/reward.txt", "w").write(f"{reward:.4f}\n"); json.dump(out, open(f"{LOG}/reward.json", "w")); print(out)
p = "/data/final.json"
if not os.path.exists(p):
    write(0.0, {"success": 0, "missing_log": 1, "infra_error": 1, "grader_error": 0}); raise SystemExit
d = json.load(open(p))
for f in ("replay.mp4", "replay.last.png", "trajectory.npz", "episode.jsonl"):
    if os.path.exists(f"/data/{f}"): shutil.copy(f"/data/{f}", f"{LOG}/{f}")
det = bool(d.get("deterministic")); ok = bool(d.get("success")) and det
out = {"success": int(ok), "deterministic": int(det), "finalized": int(bool(d.get("finalized"))), "control_steps": int(d.get("control_steps") or 0),
       "calls": int(d.get("calls") or 0), "elapsed_s": float(d.get("elapsed_s") or 0), "video_rendered": int(bool(d.get("video"))), "grader_error": 0}
# no verdict on the agent: the service crashed (restart refused) or its verification replay failed
if d.get("infra_error") or d.get("finalize_error"):
    out.update(infra_error=1, grader_error=int(bool(d.get("finalize_error"))), reason=str(d.get("reason") or ""), finalize_error=str(d.get("finalize_error") or "")[:300])
if "progress" in d:
    out.update(progress=float(d.get("progress") or 0.0) if det else 0.0, goals_reached=int(d.get("goals_reached") or 0), n_goals=int(d.get("n_goals") or 0),
               failed_on_timeout=int(bool(d.get("failed_on_timeout"))))
    reward = out["progress"]
else:
    out.update({k: (int(v) if isinstance(v, bool) else v) for k, v in d.items() if isinstance(v, (int, float, bool)) and k not in out and k not in ("success",)})
    reward = 1.0 if ok else 0.0
write(reward, out)
