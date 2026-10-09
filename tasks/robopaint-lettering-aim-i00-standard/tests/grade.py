"""Standard-mode verifier (RoboPaint brush tasks): reads what the sim service (which the agent could not touch) wrote:
/data/final.json (the recorded episode replayed twice in fresh processes by the collect hook, the replayed main sheet scored against
the exemplar, determinism), plus the replay video and sheet pictures. success = both replays meet the task's rule AND they agree
exactly. Numeric-only reward.json; every metric of the replayed sheet is reported (final_reward = the replay's final_reward), with
the crash-recovery evidence (sim_startups, resumes, resume_state_mismatch, ...; docs/STANDARD_MODE_2_2.md §13.2) and infra_error
(the service gave up after crashes that were not the agent's, or never dumped its episode)."""
import json, os, shutil
LOG = "/logs/verifier"; os.makedirs(LOG, exist_ok=True)
RECOVERY = ("sim_startups", "resumes", "resume_state_mismatch", "resume_max_tcp_dev_m", "resume_max_joint_dev")


def write(ok, out):
    open(f"{LOG}/reward.txt", "w").write("1\n" if ok else "0\n"); json.dump(out, open(f"{LOG}/reward.json", "w")); print(out)


p = "/data/final.json"
if not os.path.exists(p):
    write(False, {"success": 0, "final_reward": 0.0, "missing_log": 1, "grader_error": 0, "infra_error": 0}); raise SystemExit
d = json.load(open(p))
for f in ("replay.mp4", "replay.last.png", "canvas.png", "canvas_practice.png", "canvas_live.png", "canvas_live_practice.png", "trajectory.npz", "episode.jsonl"):
    if os.path.exists(f"/data/{f}"): shutil.copy(f"/data/{f}", f"{LOG}/{f}")
m = d.get("metrics") or {}
ok = bool(d.get("replay_success")) and bool(d.get("deterministic"))
write(ok, {**{k: float(v) for k, v in m.items() if isinstance(v, (int, float)) and not isinstance(v, bool)},
           "success": int(ok), "replay_success": int(bool(d.get("replay_success"))), "deterministic": int(bool(d.get("deterministic"))),
           "live_matches_replay": int(bool(d.get("live_matches_replay"))), "instance_exact": int(bool(d.get("instance_exact"))),
           "finalized": int(bool(d.get("finalized"))), "final_reward": float(m.get("final_reward") or 0.0),
           "n_actions": int(d.get("n_actions") or 0), "sim_steps": int(d.get("control_steps") or 0), "physics_steps": int(d.get("physics_steps") or 0),
           "steps": int(d.get("steps") or 0), "calls": int(d.get("calls") or 0), "elapsed_s": float(d.get("elapsed_s") or 0),
           "video_rendered": int(bool(d.get("video"))), "gpu_lost": int(bool(d.get("gpu_lost"))),
           **{k: float(d.get(k) or 0) for k in RECOVERY}, "gave_up": int(bool(d.get("gave_up"))),
           "infra_error": int(bool(d.get("infra_error"))),
           "grader_error": int(bool(d.get("gpu_lost")) or (bool(d.get("replay_error")) and int(d.get("n_actions") or 0) > 0))})
