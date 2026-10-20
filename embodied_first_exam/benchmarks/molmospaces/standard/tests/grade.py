"""Standard-mode verifier (MolmoSpaces): reads what the sim service (which the agent could not touch) wrote:
/data/final.json (the live episode's result and the crash-recovery fields), /data/trajectory.npz, /data/replay.mp4.
success = the live episode's success: upstream judge_success() on the state at the episode's end, judged by the service;
nothing replays it (owner 2026-10-17). The video is rendered after the verdict and never decides it.
Numeric-only reward.json; a reward is always written.

infra_error = 1 means no verdict on the agent (success is 0, the trial is not the agent's failure). The agent can reach
none of these: final.json is missing (the service never came up or its record was not collected: missing_log) or
unreadable (also grader_error); the collect hook did not finish (`finalized` false: only the service's own running copy
is there); a give-up after crashes between calls or a failed resume (docs/protocol/standard_mode.md §13); the service not
ending its episode for the collect hook; a frozen start that did not rebuild (instance_mismatch: checked by the service
when it builds the scene, before the agent is served). A give-up after crashes during a call is finalized by the
service and stays the agent's failure, and so is a simulator error raised by the agent's actions (reason "error")."""

import json, os, shutil, traceback

LOG = "/logs/verifier"
DATA = "/data"
LOG = os.environ.get("RCB_VERIFIER_LOG_DIR") or LOG  # a check's synthetic records (ci_checks/check-live-verdict.py)
DATA = os.environ.get("RCB_DATA") or DATA
os.makedirs(LOG, exist_ok=True)


def write(ok, out):
    open(f"{LOG}/reward.txt", "w").write("1\n" if ok else "0\n")
    json.dump(out, open(f"{LOG}/reward.json", "w"))
    print(out)


def grade(d: dict):
    finalized = bool(d.get("finalized"))
    # the collect hook writes `finalized` with its verdict (and the service with a give-up): without it the file is the
    # service's own running copy, before the collect hook ended the episode
    infra = bool(d.get("infra_error")) or not finalized
    reason = str(d.get("reason") or "")
    mismatch = bool(d.get("instance_mismatch")) or reason.startswith("instance_mismatch")
    live = bool(d.get("live_success", d.get("success")))
    # reason "error": a simulator error the agent's actions raised; the state after it is never judged (the agent's 0)
    ok = live and bool(d.get("success")) and reason != "error" and not mismatch and not d.get("gave_up") and not infra
    num = lambda k: float(d.get(k) or 0)  # noqa: E731
    return ok, {
        "success": int(ok),
        "live_success": int(live),
        "graded_by_live": 1,
        "replays": 0,
        "finalized": int(finalized),
        "missing_log": 0,
        "n_actions": int(d.get("n_actions") or 0),
        "sim_steps": int(d.get("control_steps") or 0),
        "physics_steps": int(d.get("physics_steps") or 0),
        "steps": int(d.get("steps") or 0),
        "elapsed_s": float(d.get("elapsed_s") or 0),
        "video_rendered": int(bool(d.get("video"))),
        "video_pending": int(bool(d.get("video_pending"))),
        "grader_error": 0,
        "instance_mismatch": int(mismatch),
        # an infrastructure failure, not the agent's (PROTOCOL §2.6): the module docstring lists the cases
        "infra_error": int(infra),
        "gave_up": int(bool(d.get("gave_up"))),
        "sim_crashed_on_call": int(d.get("reason") == "sim_crashed_on_call"),
        "sim_error": int(d.get("reason") == "error"),
        "sim_startups": int(d.get("sim_startups") or 0),
        "resumes": int(d.get("resumes") or 0),
        "resume_state_mismatch": int(d.get("resume_state_mismatch") or 0),
        "resume_max_tcp_dev_m": num("resume_max_tcp_dev_m"),
        "resume_max_joint_dev": num("resume_max_joint_dev"),
    }


def main():
    p = f"{DATA}/final.json"
    none = {"success": 0, "live_success": 0, "graded_by_live": 1, "replays": 0, "finalized": 0, "infra_error": 1}
    if not os.path.exists(p):  # written only by the trusted sidecar: its absence is never the agent's doing
        write(False, {**none, "missing_log": 1, "grader_error": 0})
        return
    try:
        d = json.load(open(p))
        if not isinstance(d, dict):
            raise ValueError("final.json is not an object")
        ok, out = grade(d)
    except Exception:  # noqa: BLE001 -- an unreadable final.json is the infrastructure's failure, not the agent's
        traceback.print_exc()
        write(False, {**none, "missing_log": 0, "grader_error": 1})
        return
    for f in ("replay.mp4", "trajectory.npz", "episode.jsonl"):
        try:
            if os.path.exists(f"{DATA}/{f}"):
                shutil.copy(f"{DATA}/{f}", f"{LOG}/{f}")
        except OSError:
            traceback.print_exc()  # evidence for humans: it never decides the verdict
    write(ok, out)


if __name__ == "__main__":
    main()
