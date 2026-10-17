"""Standard-mode verifier (separate sandbox, no network): reads what the sim service, which the agent could not touch, wrote --
/out/final.json (the live episode's result and the crash-recovery record) and the evidence next to it. success = the live
episode's success: upstream's geometric success under settle-eval, judged by the service at every control step the
episode ran; nothing replays it (owner 2026-10-17, board 0150/0151). Numeric-only reward.json (docs/PROTOCOL.md
Appendix H.1, H.4; docs/STANDARD_MODE.md).

infra_error = 1 means no verdict on the agent: final.json is missing, unreadable or not finalized, the service never
ended the episode, it gave up after crashes that were not all inside the agent's calls (sim_crashed, resume_failed), or
the frozen start did not rebuild (instance_mismatch, found before the agent was served). A crash inside the agent's
calls (sim_crashed_on_call) and a simulator error raised by its actions (reason "error") are the agent's: 0, not infra.
The video never decides anything. A reward is written in every case."""
import json, os, shutil, traceback
LOG = "/logs/verifier"


def write(ok, out):
    open(f"{LOG}/reward.txt", "w").write("1\n" if ok else "0\n"); json.dump(out, open(f"{LOG}/reward.json", "w")); print(out)


def grade(d: dict) -> tuple[bool, dict]:
    """(success, reward.json) of a final.json."""
    if not isinstance(d, dict): raise ValueError(f"final.json is not an object: {type(d).__name__}")
    num = lambda k: float(d.get(k) or 0.0)  # noqa: E731
    finalized = bool(d.get("finalized"))
    reason = str(d.get("reason") or "")
    infra = bool(d.get("infra_error")) or not finalized
    live = bool(d.get("live_success", d.get("success")))
    ok = live and bool(d.get("success")) and not d.get("gave_up") and not infra
    return ok, {
        "success": int(ok), "live_success": int(live), "graded_by_live": 1, "replays": 0,
        "finalized": int(finalized), "missing_log": 0, "n_actions": int(d.get("n_actions") or 0), "sim_steps": int(d.get("control_steps") or 0),
        "max_steps": int(d.get("max_steps") or 0), "steps": int(d.get("steps") or 0), "elapsed_s": num("elapsed_s"),
        # upstream's own diagnostics of the live episode: the BDDL goal alone, and the step at which the goal held
        "symbolic_success": int(bool(d.get("symbolic_success"))), "success_step": int(d.get("success_step") or 0),
        "video_rendered": int(bool(d.get("video"))), "video_live": int(d.get("video_source") == "live" and bool(d.get("video"))),
        "trajectory": int(bool(d.get("trajectory", True))),
        "instance_ok": int(not reason.startswith("instance_mismatch") and d.get("instance_ok", 1) not in (0, False)),
        "sim_error": int(reason == "error"), "sim_crashed_on_call": int(reason == "sim_crashed_on_call"),
        "sim_startups": int(d.get("sim_startups") or 0), "resumes": int(d.get("resumes") or 0),
        "resume_state_mismatch": int(bool(d.get("resume_state_mismatch"))), "resume_max_tcp_dev_m": num("resume_max_tcp_dev_m"),
        "resume_max_joint_dev": num("resume_max_joint_dev"), "gave_up": int(bool(d.get("gave_up"))),
        "infra_error": int(infra), "grader_error": 0}


def main() -> None:
    os.makedirs(LOG, exist_ok=True)
    data = os.environ.get("RCB_DATA") or \
        next((d for d in ("/out", "/data") if os.path.exists(f"{d}/final.json")), "/out")   # where the artifacts were uploaded
    p = f"{data}/final.json"
    if not os.path.exists(p):
        write(False, {"success": 0, "live_success": 0, "graded_by_live": 1, "replays": 0, "finalized": 0, "missing_log": 1,
                      "infra_error": 1, "grader_error": 0}); return
    try:
        ok, out = grade(json.load(open(p)))
    except Exception:  # noqa: BLE001 -- an unreadable final.json is not the agent's failure
        traceback.print_exc()
        write(False, {"success": 0, "live_success": 0, "graded_by_live": 1, "replays": 0, "finalized": 0, "missing_log": 0,
                      "infra_error": 1, "grader_error": 1}); return
    for f in ("live.mp4", "replay.mp4", "trajectory.npz", "episode.jsonl"):
        try:
            if os.path.exists(f"{data}/{f}"): shutil.copy(f"{data}/{f}", f"{LOG}/{f}")
        except OSError:    # the evidence never decides the verdict
            traceback.print_exc()
    write(ok, out)


if __name__ == "__main__":
    LOG = os.environ.get("RCB_VERIFIER_LOG_DIR") or LOG
    main()
