"""Standard-mode verifier: reads what the sim service (which the agent could not touch) wrote:
/data/final.json (live success, two fresh-process replays of the recorded trajectory, determinism, crash-recovery
fields), /data/trajectory.npz, /data/replay.mp4. success = live success AND replay success AND deterministic, and no
infrastructure failure. Numeric-only reward.json; a reward is written whatever final.json holds.

infra_error = 1 (no verdict on the agent, PROTOCOL §2.6): final.json is missing (the service never came up, or its
container was gone when the collect hook ran), unreadable, or not finalized (the collect hook did not finish: killed at
its time limit, or the sidecar died during the replays); the hook could not replay the episode (the GPU lost, a replay
process that died or ran out of time without a result: `replay_error`); or the service itself reported one (a give-up
after crashes between calls, a failed resume, the episode never ended for the hook). A give-up after crashes inside the
agent's calls (`sim_crashed_on_call`) stays the agent's 0."""
import json, os, shutil, traceback
LOG = os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier"); DATA = os.environ.get("RCB_DATA", "/data")
os.makedirs(LOG, exist_ok=True)
def write(ok, out):
    open(f"{LOG}/reward.txt", "w").write("1\n" if ok else "0\n"); json.dump(out, open(f"{LOG}/reward.json", "w")); print(out)
NONE = {"success": 0, "live_success": 0, "replay_success": 0, "deterministic": 0, "finalized": 0}   # no verdict could be read
p = f"{DATA}/final.json"
if not os.path.exists(p):
    write(False, {**NONE, "missing_log": 1, "grader_error": 0, "infra_error": 1}); raise SystemExit
try:
    d = json.load(open(p))
    if not isinstance(d, dict): raise ValueError(f"final.json holds a {type(d).__name__}, not an object")
except Exception:  # noqa: BLE001 -- a truncated or corrupt final.json is the infrastructure's failure, not the agent's
    traceback.print_exc()
    write(False, {**NONE, "missing_log": 0, "grader_error": 1, "infra_error": 1}); raise SystemExit
for f in ("replay.mp4", "replay.last.png", "trajectory.npz", "episode.jsonl"):
    try:
        if os.path.exists(f"{DATA}/{f}"): shutil.copy(f"{DATA}/{f}", f"{LOG}/{f}")
    except OSError:
        traceback.print_exc()                              # the evidence never decides the verdict
def num(k):
    try: return float(d.get(k) or 0)
    except (TypeError, ValueError): return 0.0
unfinished = not d.get("finalized")                        # the collect hook never completed final.json
replay_error = bool(d.get("replay_error"))                 # a replay process died or timed out without a result
gpu_lost = bool(d.get("gpu_lost"))
infra = bool(d.get("infra_error")) or gpu_lost or unfinished or replay_error
ok = bool(d.get("success")) and bool(d.get("replay_success")) and bool(d.get("deterministic")) and not infra
write(ok, {"success": int(ok), "live_success": int(bool(d.get("success"))), "replay_success": int(bool(d.get("replay_success"))),
           "deterministic": int(bool(d.get("deterministic"))), "live_matches_replay": int(bool(d.get("live_matches_replay"))),
           "object_fell": int(d.get("reason") == "object_fell"),
           "finalized": int(not unfinished), "missing_log": 0, "n_actions": int(num("n_actions")), "sim_steps": int(num("control_steps")),
           "physics_steps": int(num("physics_steps")), "steps": int(num("steps")), "elapsed_s": num("elapsed_s"),
           "video_rendered": int(bool(d.get("video"))), "gpu_lost": int(gpu_lost), "replay_error": int(replay_error),
           "replay_timed_out": int(bool(d.get("replay_timed_out"))),
           "grader_error": int(gpu_lost or replay_error),   # the replays could not run: an infrastructure failure, not the agent's 0
           # an infrastructure failure, not the agent's (PROTOCOL §2.6): see the module docstring
           "infra_error": int(infra), "gave_up": int(bool(d.get("gave_up"))),
           "sim_crashed_on_call": int(d.get("reason") == "sim_crashed_on_call"),
           "sim_startups": int(num("sim_startups")), "resumes": int(num("resumes")),
           "resume_state_mismatch": int(num("resume_state_mismatch")), "resume_max_tcp_dev_m": num("resume_max_tcp_dev_m"),
           "resume_max_joint_dev": num("resume_max_joint_dev")})
