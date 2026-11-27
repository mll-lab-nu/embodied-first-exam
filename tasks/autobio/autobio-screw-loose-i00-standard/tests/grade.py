"""Standard-mode verifier (AutoBio): reads what the sim service (which the agent could not touch) wrote: /data/final.json
(the LIVE episode's result and the crash-recovery fields), /data/trajectory.npz, /data/replay.mp4. The trial is graded by
its live episode (docs/protocol/invariants.md H.4; no grading replay): success = the live episode's success, no
infrastructure failure and no simulator error. Numeric-only reward.json; a reward is always written.

infra_error = 1 (no verdict on the agent, docs/protocol/tasks.md#grading) when final.json is missing (the service writes it as soon as
its scene is up, so the agent cannot make it disappear), unreadable, or not finalized (the collect hook did not
finish); or the service or the hook reported one: a give-up after crashes between calls, a failed resume, the live
episode not started in the instance's recorded state (`instance_mismatch`), the episode never ended for the hook, no
record of the live episode (episode.json). A give-up after crashes inside the agent's calls (`sim_crashed_on_call`)
and a simulator error during the agent's calls (reason "error", `sim_error`) stay the agent's 0. The video never
decides anything (`video_rendered`)."""

import json, os, shutil, traceback

def agent_end_fields(d):
    """An agent-ended episode's record (docs/protocol/tasks.md#modes: final.json success_signal / ended_by, step_limit / steps_used):
    evidence only, never the verdict (numbers only: a bad value is 0); the runner reads ended_session_end."""
    if not isinstance(d, dict) or d.get("success_signal") != "hidden":
        return {}
    by = d.get("ended_by")
    out = {"ended_finish": int(by == "finish"), "ended_step_limit": int(by == "step_limit"),
           "ended_session_end": int(by == "session_end"), "hidden_success_seen": int(bool(d.get("hidden_success_seen")))}
    if d.get("step_limit"):
        def n(k):
            try:
                v = float(d.get(k) or 0)
            except (TypeError, ValueError):
                return 0
            return int(v) if abs(v) < 1e18 else 0      # NaN and inf too
        out.update(step_limit=n("step_limit"), steps_used=n("steps_used"))
    return out


DATA = os.environ.get("RCB_DATA", "/data")
LOG = os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier")
os.makedirs(LOG, exist_ok=True)
ZERO = {"success": 0, "live_success": 0, "graded_by_live": 1, "replays": 0, "finalized": 0}


def write(ok, out):
    open(f"{LOG}/reward.txt", "w").write("1\n" if ok else "0\n")
    json.dump(out, open(f"{LOG}/reward.json", "w"))
    print(out)


def grade(d: dict) -> tuple[bool, dict]:
    def num(k):
        try:
            return float(d.get(k) or 0)
        except (TypeError, ValueError):
            return 0.0
    reason = str(d.get("reason") or "")
    unfinished = not d.get("finalized")  # the collect hook never completed final.json
    infra = bool(d.get("infra_error")) or bool(d.get("instance_mismatch")) or unfinished
    ok = bool(d.get("success")) and not infra and reason != "error"   # docs/protocol/tasks.md#grading: a simulator error is the agent's 0
    return ok, {
        "success": int(ok),
        "live_success": int(bool(d.get("success"))),
        "graded_by_live": 1,
        "replays": 0,
        "progress": num("score"),
        "finalized": int(not unfinished),
        "missing_log": 0,
        "n_actions": int(num("n_actions")),
        "sim_steps": int(num("control_steps")),
        "physics_steps": int(num("physics_steps")),
        "steps": int(num("steps")),
        "calls": int(num("calls")),
        "elapsed_s": num("elapsed_s"),
        "video_rendered": int(bool(d.get("video"))),
        "timeout": int(reason == "timeout"),
        "instance_mismatch": int(bool(d.get("instance_mismatch"))),
        "grader_error": 0,
        # an infrastructure failure, not the agent's (docs/protocol/tasks.md#grading): see the module docstring
        "infra_error": int(infra),
        "gave_up": int(bool(d.get("gave_up"))),
        "sim_crashed_on_call": int(reason == "sim_crashed_on_call"),
        "sim_error": int(reason == "error"),
        "sim_startups": int(num("sim_startups")),
        "resumes": int(num("resumes")),
        "resume_state_mismatch": int(num("resume_state_mismatch")),
        "resume_max_joint_dev": num("resume_max_joint_dev"),
    }


def main() -> None:
    p = f"{DATA}/final.json"
    if not os.path.exists(p):
        write(False, {**ZERO, "missing_log": 1, "grader_error": 0, "infra_error": 1})
        return
    try:
        d = json.load(open(p))
        if not isinstance(d, dict):
            raise ValueError("final.json is not an object")
        ok, out = grade(d)
    except Exception:  # noqa: BLE001 -- an unreadable final.json is not the agent's failure
        traceback.print_exc()
        write(False, {**ZERO, "missing_log": 0, "grader_error": 1, "infra_error": 1})
        return
    for f in ("replay.mp4", "trajectory.npz", "episode.jsonl"):  # evidence for people; it never decides the verdict
        try:
            if os.path.exists(f"{DATA}/{f}"):
                shutil.copy(f"{DATA}/{f}", f"{LOG}/{f}")
        except OSError:
            traceback.print_exc()
    write(ok, {**out, **agent_end_fields(d)})


if __name__ == "__main__":
    main()
