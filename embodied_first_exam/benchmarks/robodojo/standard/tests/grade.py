"""Standard-mode verifier: reads what the sim service (which the agent could not touch) wrote: /data/final.json (the
LIVE episode's result and the crash-recovery fields), /data/trajectory.npz, /data/live.mp4. The trial is graded by its
live episode (owner 2026-10-17, board 0150/0151; no grading replay): success = the live episode's success (RoboDojo's
check passed at an action of the episode the agent ran) and no infrastructure failure. The same rule for every task; a
task whose physics does not replay bit for bit (instance.json "determinism": "verdict", `determinism_verdict_mode`) was
graded so before, with a replay recorded that no longer runs. Until 2026-10-17 the other tasks were graded by
`live_success` and the success of one fresh-process replay. Numeric-only reward.json; a reward is written whatever final.json holds.

infra_error = 1 (no verdict on the agent, PROTOCOL §2.6): final.json is missing (the service never came up, or its
container was gone when the collect hook ran), unreadable, or not finalized (the collect hook did not finish); or the
service or the hook reported one: a give-up after crashes between calls (`sim_crashed`), a failed resume, the frozen
instance not rebuilt at the episode's start (`instance_mismatch`, before the agent was served), the episode never ended
for the hook, no record of the live episode (episode.json). A give-up after crashes inside the agent's calls
(`sim_crashed_on_call`) and a simulator error raised during the agent's calls (reason "error", `sim_error`) stay the
agent's 0. The video never decides anything (`video_rendered`)."""
import json, os, shutil, traceback
LOG = os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier"); DATA = os.environ.get("RCB_DATA", "/data")
os.makedirs(LOG, exist_ok=True)
def write(ok, out):
    open(f"{LOG}/reward.txt", "w").write("1\n" if ok else "0\n"); json.dump(out, open(f"{LOG}/reward.json", "w")); print(out)
NONE = {"success": 0, "live_success": 0, "graded_by_live": 1, "replays": 0, "finalized": 0, "sim_error": 0}   # no verdict could be read
p = f"{DATA}/final.json"
if not os.path.exists(p):
    write(False, {**NONE, "missing_log": 1, "grader_error": 0, "infra_error": 1}); raise SystemExit
try:
    d = json.load(open(p))
    if not isinstance(d, dict): raise ValueError(f"final.json holds a {type(d).__name__}, not an object")
except Exception:  # noqa: BLE001 -- a truncated or corrupt final.json is the infrastructure's failure, not the agent's
    traceback.print_exc()
    write(False, {**NONE, "missing_log": 0, "grader_error": 1, "infra_error": 1}); raise SystemExit
for f in ("live.mp4", "live.last.png", "trajectory.npz", "episode.jsonl"):
    try:
        if os.path.exists(f"{DATA}/{f}"): shutil.copy(f"{DATA}/{f}", f"{LOG}/{f}")
    except OSError:
        traceback.print_exc()                              # the evidence never decides the verdict
def num(k):
    try: return float(d.get(k) or 0)
    except (TypeError, ValueError): return 0.0
unfinished = not d.get("finalized")                        # the collect hook never completed final.json
infra = bool(d.get("infra_error")) or unfinished
ok = bool(d.get("success")) and not infra
write(ok, {"success": int(ok), "live_success": int(bool(d.get("success"))), "graded_by_live": 1, "replays": 0,
           "finalized": int(not unfinished), "missing_log": 0, "n_actions": int(num("n_actions")), "sim_steps": int(num("control_steps")),
           "physics_steps": int(num("physics_steps")), "steps": int(num("steps")), "elapsed_s": num("elapsed_s"),
           "ended_failed_check": int(d.get("reason") == "failed_check"), "ended_step_guard": int(d.get("reason") == "step_guard"),
           "determinism_verdict_mode": int(bool(d.get("determinism_verdict_mode"))), "video_rendered": int(bool(d.get("video"))), "video_frames": int(num("video_frames")),
           "sim_error": int(d.get("reason") == "error"),   # a simulator error during the agent's calls: the agent's 0
           "instance_mismatch": int(bool(d.get("instance_mismatch"))), "instance_exact": int(bool(d.get("instance_exact"))),
           "grader_error": 0,
           # an infrastructure failure, not the agent's (PROTOCOL §2.6): see the module docstring
           "infra_error": int(infra), "gave_up": int(bool(d.get("gave_up"))),
           "sim_crashed_on_call": int(d.get("reason") == "sim_crashed_on_call"),
           "sim_startups": int(num("sim_startups")), "resumes": int(num("resumes")),
           "resume_state_mismatch": int(num("resume_state_mismatch")), "resume_max_tcp_dev_m": num("resume_max_tcp_dev_m"),
           "resume_max_joint_dev": num("resume_max_joint_dev")})
