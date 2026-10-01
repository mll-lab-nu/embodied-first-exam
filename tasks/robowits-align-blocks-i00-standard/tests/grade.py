"""Standard-mode verifier (eai-standard/2.2): reads what the sim service (which the agent could not touch) wrote:
/data/final.json (live success, the in-process replay of the recorded trajectory, determinism, crash recovery),
/data/trajectory.npz, /data/replay.mp4. success = live success AND replay success AND deterministic, and no
infrastructure failure. Numeric-only reward.json. Source: scripts/robowits/shared/grade_standard.py.
With RCB_ROBOWITS_BACKEND=gpu (the particle-heavy tasks, user 2026-09-26) the physics is not bit-exact: live and
replay must both succeed, their states need not agree."""
import json, os, shutil
LOG = "/logs/verifier"; os.makedirs(LOG, exist_ok=True)
def write(ok, out):
    open(f"{LOG}/reward.txt", "w").write("1\n" if ok else "0\n"); json.dump(out, open(f"{LOG}/reward.json", "w")); print(out)
p = "/data/final.json"
if not os.path.exists(p):
    write(False, {"success": 0, "missing_log": 1, "infra_error": 1, "grader_error": 0}); raise SystemExit   # the service never started
try:
    d = json.load(open(p))
except ValueError:
    write(False, {"success": 0, "missing_log": 1, "infra_error": 1, "grader_error": 1}); raise SystemExit
for f in ("replay.mp4", "replay.last.png", "trajectory.npz", "episode.jsonl", "startups.jsonl", "server.log"):
    if os.path.exists(f"/data/{f}"): shutil.copy(f"/data/{f}", f"{LOG}/{f}")
gpu = os.environ.get("RCB_ROBOWITS_BACKEND", "cpu") == "gpu"  # not bit-exact: determinism reported, not required
# infrastructure: the service gave up after crashes it caused (sim_crashed, resume_failed), or never finished grading
infra = bool(d.get("infra_error")) or not (d.get("finalized") or d.get("gave_up"))
ok = bool(d.get("success")) and bool(d.get("replay_success")) and (bool(d.get("deterministic")) or gpu) and not infra
num = lambda k, cast=int: cast(d.get(k) or 0)  # noqa: E731
write(ok, {"success": int(ok), "live_success": int(bool(d.get("success"))), "replay_success": int(bool(d.get("replay_success"))),
           "deterministic": int(bool(d.get("deterministic"))), "gpu_backend": int(gpu), "finalized": int(bool(d.get("finalized"))),
           "n_actions": num("n_actions"), "sim_steps": num("control_steps"), "physics_steps": num("physics_steps"), "steps": num("steps"),
           "elapsed_s": num("elapsed_s", float), "video_rendered": int(bool(d.get("video"))), "infra_error": int(infra),
           "gave_up": int(bool(d.get("gave_up"))), "sim_startups": num("sim_startups"), "resumes": num("resumes"),
           "resume_state_mismatch": num("resume_state_mismatch"), "resume_max_tcp_dev_m": num("resume_max_tcp_dev_m", float),
           "resume_max_joint_dev": num("resume_max_joint_dev", float), "grader_error": 0})
