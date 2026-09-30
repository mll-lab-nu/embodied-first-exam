"""Limited-mode verifier: reads what the sim service (which the agent could not touch) wrote:
/data/final.json (live success, fresh replay of the recorded trajectory, determinism), /data/trajectory.npz,
/data/replay.mp4. Adapted from robot_coding_bench's RoboWits limited grader (fa59c1a6). success = live success AND
replay success; TopoGym's physics runs on the GPU (the RoboWits GPU-backend rule): the live and replayed states need
not agree bit for bit, so `deterministic` is reported, not required. Numeric-only reward.json."""
import json, os, shutil
LOG = "/logs/verifier"; os.makedirs(LOG, exist_ok=True)
def write(ok, out):
    open(f"{LOG}/reward.txt", "w").write("1\n" if ok else "0\n"); json.dump(out, open(f"{LOG}/reward.json", "w")); print(out)
p = "/data/final.json"
if not os.path.exists(p):
    write(False, {"success": 0, "missing_log": 1, "grader_error": 0}); raise SystemExit
d = json.load(open(p))
for f in ("replay.mp4", "replay.last.png", "trajectory.npz", "episode.jsonl"):
    if os.path.exists(f"/data/{f}"): shutil.copy(f"/data/{f}", f"{LOG}/{f}")
gpu = True  # CUDA physics: determinism reported, not required
valid = bool(d.get("finalized")) and d.get("replay_success") is not None and os.path.isfile("/data/trajectory.npz")
ok = valid and bool(d.get("success")) and bool(d.get("replay_success")) and (bool(d.get("deterministic")) or gpu)
write(ok, {"success": int(ok), "live_success": int(bool(d.get("success"))), "replay_success": int(bool(d.get("replay_success"))),
           "deterministic": int(bool(d.get("deterministic"))), "gpu_backend": int(gpu), "finalized": int(bool(d.get("finalized"))),
           "n_actions": int(d.get("n_actions") or 0), "sim_steps": int(d.get("control_steps") or 0), "physics_steps": int(d.get("physics_steps") or 0),
           "steps": int(d.get("steps") or 0), "elapsed_s": float(d.get("elapsed_s") or 0), "video_rendered": int(bool(d.get("video"))), "grader_error": int(not valid)})
