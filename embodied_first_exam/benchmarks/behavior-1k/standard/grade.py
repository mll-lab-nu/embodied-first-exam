"""Standard-mode verifier: reads what the sim service (which the agent could not touch) wrote: /out/final.json (the live
episode's result and the crash-recovery record), /out/trajectory.npz, the video (/out/live.mp4, recorded during the
episode, or /out/replay.mp4 from the video-only render). success = the live episode's success: the tooling's success
rule (the BDDL goal held 1 s, released and at rest), judged by the service on the live simulator, including the settle
window it runs after the agent's phase when the agent's episode was still running (`settled_success`). Nothing replays
the episode (owner 2026-10-17). Numeric-only reward.json (docs/protocol/README.md Appendix H).

infra_error = 1 means no verdict on the agent: final.json is the trusted sidecar's own file, so when it is missing (the
service never came up, or its container was gone), unreadable, or not finalized (the collect hook did not finish), the 0
is an infrastructure failure, not the agent's; so are a give-up after crashes not all inside the agent's calls
(sim_crashed, resume_failed) and a frozen start that did not rebuild (instance_mismatch, found before the agent was
served). A crash inside the agent's calls (sim_crashed_on_call), a simulator error raised by its actions (reason
"error"), a fall and a simulator breakdown (`sim_breakdown`: infrastructure or the agent's 0 is the owner's decision,
2026-10-16; until then the agent's 0) are the agent's. The video never decides anything. A reward is written in every
case."""
import json, os, shutil, traceback
LOG = os.environ.get("RCB_VERIFIER_LOG_DIR") or "/logs/verifier"; os.makedirs(LOG, exist_ok=True)
def write(ok, out):
    open(f"{LOG}/reward.txt", "w").write("1\n" if ok else "0\n"); json.dump(out, open(f"{LOG}/reward.json", "w")); print(out)
DATA = os.environ.get("RCB_DATA") or next((d for d in ("/out", "/data") if os.path.exists(f"{d}/final.json")), "/out")   # the service wrote to /out: /data is the dataset
p = f"{DATA}/final.json"
NONE = {"success": 0, "live_success": 0, "graded_by_live": 1, "replays": 0, "finalized": 0}
if not os.path.exists(p):
    write(False, {**NONE, "missing_log": 1, "infra_error": 1, "grader_error": 0}); raise SystemExit
try:
    d = json.load(open(p))
    if not isinstance(d, dict): raise ValueError(f"final.json is not an object: {type(d).__name__}")
    num = lambda k: float(d.get(k) or 0.0)  # noqa: E731
    finalized = bool(d.get("finalized"))
    reason = str(d.get("reason") or "")
    breakdown = bool(d.get("sim_breakdown")) or reason.startswith("failure: simulator breakdown")
    infra = bool(d.get("infra_error")) or not finalized
    live = bool(d.get("live_success", d.get("success")))
    # reason "error": a simulator error the agent's actions raised; the state after it is never judged a success
    ok = live and bool(d.get("success")) and reason != "error" and not d.get("gave_up") and not infra
    out = {"success": int(ok), "live_success": int(live), "graded_by_live": 1, "replays": 0,
           "finalized": int(finalized), "missing_log": 0, "n_actions": int(d.get("n_actions") or 0), "sim_steps": int(d.get("control_steps") or 0),
           "physics_steps": int(d.get("physics_steps") or 0), "steps": int(d.get("steps") or 0), "elapsed_s": num("elapsed_s"),
           "video_rendered": int(bool(d.get("video"))), "video_live": int(bool(d.get("video")) and d.get("video_source") == "live"),
           "video_pending": int(bool(d.get("video_pending"))),
           # the agent's episode was still running at its end: the success came in the settle window the service ran on
           # the live simulator after the agent's phase (server.py end_live), and how long that window ran
           "settled_success": int(bool(d.get("settled_success"))), "settle_steps": int(d.get("settle_steps") or 0),
           "sim_breakdown": int(breakdown),                      # a simulator breakdown ended the episode
           "instance_ok": int(not reason.startswith("instance_mismatch")),   # 0: the frozen start did not rebuild (infra_error)
           # the episode ended by a failure rule: the robot fell over ("failure: the robot fell over") or the simulator
           # broke down ("failure: simulator breakdown", sim_breakdown)
           "task_failure": int(reason.startswith("failure")),
           "sim_error": int(reason == "error"), "sim_crashed_on_call": int(reason == "sim_crashed_on_call"),
           "q_score": num("q_score"),   # progress (the challenge's q_score of the live episode's end state), 2026-09-27
           "goal_first_step": int(d.get("goal_first_step") or 0),   # the first step the bare BDDL goal held (re-grades)
           # crash recovery (eai-standard/2.2): service starts, resumes, whether a resumed state differed and by how much,
           # and a give-up after too many crashes
           "sim_startups": int(d.get("sim_startups") or 0), "resumes": int(d.get("resumes") or 0),
           "resume_state_mismatch": int(bool(d.get("resume_state_mismatch"))), "resume_max_tcp_dev_m": num("resume_max_tcp_dev_m"),
           "resume_max_joint_dev": num("resume_max_joint_dev"), "gave_up": int(bool(d.get("gave_up"))),
           # an infrastructure failure, not the agent's 0 (the module docstring lists the cases)
           "infra_error": int(infra), "grader_error": 0}
except Exception:  # noqa: BLE001 -- an unreadable final.json is not the agent's failure
    traceback.print_exc()
    write(False, {**NONE, "missing_log": 0, "infra_error": 1, "grader_error": 1}); raise SystemExit
for f in ("live.mp4", "replay.mp4", "replay.last.png", "trajectory.npz", "episode.jsonl"):
    try:
        if os.path.exists(f"{DATA}/{f}"): shutil.copy(f"{DATA}/{f}", f"{LOG}/{f}")
    except OSError:    # the evidence never decides the verdict
        traceback.print_exc()
write(ok, out)
