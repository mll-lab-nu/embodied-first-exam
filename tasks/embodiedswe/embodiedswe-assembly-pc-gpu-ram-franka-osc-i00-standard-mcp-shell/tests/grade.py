"""Standard-mode verifier (EmbodiedSWE): reads what the sim service (which the agent could not touch) wrote:
/data/final.json (the LIVE episode's verdict and the crash-recovery record), /data/trajectory.npz, /data/live.mp4.
Graded by the live episode, no grading replay: success = EmbodiedSWE's verdict on the live state at the episode's end
(the grader's success predicate; a broken tool-only rule disqualifies), and no infrastructure failure; progress = the
grader's rubric score. Numeric-only reward.json (tasks/embodiedswe/README.md "Standard mode").

infra_error = 1 (no verdict on the agent): final.json missing, unreadable or not finalized; the service gave up after
crashes outside a call, never ended the episode, or found the scene was not the frozen instance (`instance_mismatch`).
A give-up after crashes during a call (`sim_crashed_on_call`) and a simulator error raised by the agent's actions
(reason "error") stay the agent's 0."""
import json, os, shutil, traceback
LOG = os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier"); DATA = os.environ.get("RCB_DATA", "/data")
os.makedirs(LOG, exist_ok=True)


def write(ok, out):
    open(f"{LOG}/reward.txt", "w").write("1\n" if ok else "0\n"); json.dump(out, open(f"{LOG}/reward.json", "w")); print(out)


NONE = {"success": 0, "progress": 0.0, "live_success": 0, "graded_by_live": 1, "replays": 0, "finalized": 0, "sim_error": 0}
p = f"{DATA}/final.json"
if not os.path.exists(p):
    write(False, {**NONE, "missing_log": 1, "grader_error": 0, "infra_error": 1}); raise SystemExit
try:
    d = json.load(open(p))
    if not isinstance(d, dict):
        raise ValueError(f"final.json holds a {type(d).__name__}, not an object")
except Exception:  # noqa: BLE001 -- a truncated or corrupt final.json is the infrastructure's failure, not the agent's
    traceback.print_exc()
    write(False, {**NONE, "missing_log": 0, "grader_error": 1, "infra_error": 1}); raise SystemExit
for f in ("live.mp4", "live.last.png", "trajectory.npz", "episode.jsonl"):
    try:
        if os.path.exists(f"{DATA}/{f}"):
            shutil.copy(f"{DATA}/{f}", f"{LOG}/{f}")
    except OSError:
        traceback.print_exc()                              # the evidence never decides the verdict


def num(k):
    try:
        return float(d.get(k) or 0)
    except (TypeError, ValueError):
        return 0.0


unfinished = not d.get("finalized")
infra = bool(d.get("infra_error")) or unfinished
sim_error = d.get("reason") == "error"
ok = bool(d.get("success")) and not infra and not sim_error
write(ok, {"success": int(ok), "progress": 0.0 if infra else num("progress"), "live_success": int(bool(d.get("success"))),
           "graded_by_live": 1, "replays": 0, "finalized": int(not unfinished), "missing_log": 0,
           "n_actions": int(num("n_actions")), "sim_steps": int(num("control_steps")), "physics_steps": int(num("physics_steps")),
           "steps": int(num("steps")), "calls": int(num("calls")), "elapsed_s": num("elapsed_s"),
           "success_ended_episode": int(d.get("reason") == "success"), "step_cap_reached": int(d.get("reason") == "step_guard"),
           "tool_only": int(num("tool_only")), "tool_contact": int(num("tool_contact")), "disqualified": int(num("disqualified")),
           "video_rendered": int(bool(d.get("video"))), "video_frames": int(num("video_frames")), "sim_error": int(sim_error),
           "instance_mismatch": int(bool(d.get("instance_mismatch"))), "instance_exact": int(bool(d.get("instance_exact"))),
           "grader_error": 0, "infra_error": int(infra), "gave_up": int(bool(d.get("gave_up"))),
           "sim_crashed_on_call": int(d.get("reason") == "sim_crashed_on_call"),
           "sim_startups": int(num("sim_startups")), "resumes": int(num("resumes")),
           "resume_state_mismatch": int(num("resume_state_mismatch")), "resume_max_tcp_dev_m": num("resume_max_tcp_dev_m"),
           "resume_max_joint_dev": num("resume_max_joint_dev")})
