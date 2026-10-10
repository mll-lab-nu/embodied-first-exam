"""Standard-mode verifier: reads what the sim service (which the agent could not touch) wrote:
/data/final.json (live success, two fresh-process replays of the recorded trajectory, determinism, crash-recovery
fields), /data/trajectory.npz, /data/replay.mp4. success = live success AND replay success AND deterministic.
Numeric-only reward.json."""
import json, os, shutil
LOG = "/logs/verifier"; os.makedirs(LOG, exist_ok=True)
def write(ok, out):
    open(f"{LOG}/reward.txt", "w").write("1\n" if ok else "0\n"); json.dump(out, open(f"{LOG}/reward.json", "w")); print(out)
p = "/data/final.json"
if not os.path.exists(p):
    write(False, {"success": 0, "missing_log": 1, "grader_error": 0, "infra_error": 0}); raise SystemExit
d = json.load(open(p))
for f in ("replay.mp4", "replay.last.png", "trajectory.npz", "episode.jsonl"):
    if os.path.exists(f"/data/{f}"): shutil.copy(f"/data/{f}", f"{LOG}/{f}")
ok = bool(d.get("success")) and bool(d.get("replay_success")) and bool(d.get("deterministic"))
num = lambda k: float(d.get(k) or 0)  # noqa: E731
write(ok, {"success": int(ok), "live_success": int(bool(d.get("success"))), "replay_success": int(bool(d.get("replay_success"))),
           "deterministic": int(bool(d.get("deterministic"))), "live_matches_replay": int(bool(d.get("live_matches_replay"))),
           "object_fell": int(d.get("reason") == "object_fell"),
           "finalized": int(bool(d.get("finalized"))), "n_actions": int(d.get("n_actions") or 0), "sim_steps": int(d.get("control_steps") or 0),
           "physics_steps": int(d.get("physics_steps") or 0), "steps": int(d.get("steps") or 0), "elapsed_s": float(d.get("elapsed_s") or 0),
           "video_rendered": int(bool(d.get("video"))), "gpu_lost": int(bool(d.get("gpu_lost"))),
           "grader_error": int(bool(d.get("gpu_lost"))),   # the replays could not run: an infrastructure failure, not the agent's 0
           # an infrastructure failure, not the agent's (PROTOCOL §2.6): the GPU lost, a give-up after crashes between calls or
           # a failed resume (docs/STANDARD_MODE_2_2.md §13), the service not ending its episode for the collect hook
           "infra_error": int(bool(d.get("infra_error")) or bool(d.get("gpu_lost"))), "gave_up": int(bool(d.get("gave_up"))),
           "sim_startups": int(d.get("sim_startups") or 0), "resumes": int(d.get("resumes") or 0),
           "resume_state_mismatch": int(d.get("resume_state_mismatch") or 0), "resume_max_tcp_dev_m": num("resume_max_tcp_dev_m"),
           "resume_max_joint_dev": num("resume_max_joint_dev")})
