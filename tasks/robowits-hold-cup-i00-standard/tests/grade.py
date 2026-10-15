"""Standard-mode verifier (eai-standard/2.2): reads what the sim service (which the agent could not touch) wrote:
/data/final.json (live success, the in-process replay of the recorded trajectory, determinism, crash recovery),
/data/trajectory.npz, /data/replay.mp4. success = live success AND replay success AND deterministic, and no
infrastructure failure (infra_error = 1: no record, a give-up the service caused, a frozen instance the host could not
rebuild, a grading replay that failed after an episode that ended normally). Numeric-only reward.json. Source:
scripts/robowits/shared/grade_standard.py.
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
    if not isinstance(d, dict): raise ValueError("final.json is not an object")
except (OSError, ValueError):
    write(False, {"success": 0, "missing_log": 1, "infra_error": 1, "grader_error": 1}); raise SystemExit
for f in ("replay.mp4", "replay.last.png", "trajectory.npz", "episode.jsonl", "startups.jsonl", "server.log"):
    if os.path.exists(f"/data/{f}"): shutil.copy(f"/data/{f}", f"{LOG}/{f}")
gpu = os.environ.get("RCB_ROBOWITS_BACKEND", "cpu") == "gpu"  # not bit-exact: determinism reported, not required
reason = str(d.get("reason") or "")
sim_error = reason == "error"                          # the live episode ended with a simulator error (PROTOCOL §4.6): the agent's 0
instance_mismatch = reason.startswith("instance_mismatch")   # the host could not rebuild the frozen instance (server.py)
# The service's grading replay raised (final.json grade_error). After an episode that ended normally the episode was never
# graded: a grader fault and not the agent's failure. After a simulator error the replay fails as the live episode did:
# that stays the agent's 0 (sim_error), so an agent cannot void a failed episode by breaking the simulator.
grade_error = bool(d.get("grade_error")) and not sim_error
# infrastructure: the service gave up after crashes it caused (sim_crashed, resume_failed) or because it could not rebuild
# the frozen instance (instance_mismatch), never finished grading, or its grading replay failed
infra = bool(d.get("infra_error")) or not (d.get("finalized") or d.get("gave_up")) or grade_error
ok = bool(d.get("success")) and bool(d.get("replay_success")) and (bool(d.get("deterministic")) or gpu) and not infra
num = lambda k, cast=int: cast(d.get(k) or 0)  # noqa: E731
write(ok, {"success": int(ok), "live_success": int(bool(d.get("success"))), "replay_success": int(bool(d.get("replay_success"))),
           "deterministic": int(bool(d.get("deterministic"))), "gpu_backend": int(gpu), "finalized": int(bool(d.get("finalized"))),
           "n_actions": num("n_actions"), "sim_steps": num("control_steps"), "physics_steps": num("physics_steps"), "steps": num("steps"),
           "elapsed_s": num("elapsed_s", float), "video_rendered": int(bool(d.get("video"))), "infra_error": int(infra),
           "sim_error": int(sim_error), "instance_mismatch": int(instance_mismatch), "instance_exact": int(bool(d.get("instance_exact"))),
           "gave_up": int(bool(d.get("gave_up"))), "sim_startups": num("sim_startups"), "resumes": num("resumes"),
           "resume_state_mismatch": num("resume_state_mismatch"), "resume_max_tcp_dev_m": num("resume_max_tcp_dev_m", float),
           "resume_max_joint_dev": num("resume_max_joint_dev", float), "grader_error": int(grade_error)})
