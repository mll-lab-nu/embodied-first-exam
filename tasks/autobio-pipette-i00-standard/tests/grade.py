"""Standard-mode verifier (AutoBio): reads what the sim service (which the agent could not touch) wrote: /data/final.json
(live success, two fresh-process replays of the recorded trajectory, determinism, crash-recovery fields),
/data/trajectory.npz, /data/replay.mp4. success = live success AND replay success AND deterministic, the replays having
started in the instance's recorded state. Numeric-only reward.json; a reward is always written.

infra_error = 1 (no verdict on the agent, PROTOCOL §2.6) when final.json is missing (the service writes it as soon as
its scene is up, so the agent cannot make it disappear), unreadable, or holds no verdict: neither the collect hook's
(`finalized` with `deterministic`) nor the service's give-up after crashes (`finalized` with `gave_up`; a crash inside
a call, `sim_crashed_on_call`, stays the agent's failure)."""

import json, os, shutil, traceback

DATA = os.environ.get("RCB_DATA", "/data")
LOG = os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier")
os.makedirs(LOG, exist_ok=True)
ZERO = {"success": 0, "live_success": 0, "replay_success": 0, "deterministic": 0, "finalized": 0}


def write(ok, out):
    open(f"{LOG}/reward.txt", "w").write("1\n" if ok else "0\n")
    json.dump(out, open(f"{LOG}/reward.json", "w"))
    print(out)


def grade(d: dict) -> tuple[bool, dict]:
    num = lambda k: float(d.get(k) or 0)  # noqa: E731
    reason = str(d.get("reason") or "")
    # a verdict: the collect hook's (two replays compared) or the service's give-up; anything else is an episode the
    # hook never finished grading (it was killed, or the service's own unfinalized copy is all there is)
    no_verdict = not d.get("finalized") or (not d.get("gave_up") and d.get("deterministic") is None)
    infra = bool(d.get("infra_error")) or no_verdict
    ok = bool(d.get("success")) and bool(d.get("replay_success")) and bool(d.get("deterministic"))
    ok = ok and not d.get("instance_mismatch") and not infra
    return ok, {
        "success": int(ok),
        "live_success": int(bool(d.get("success"))),
        "replay_success": int(bool(d.get("replay_success"))),
        "deterministic": int(bool(d.get("deterministic"))),
        "live_matches_replay": int(bool(d.get("live_matches_replay"))),
        "progress": min(num("score"), num("replay_score")),
        "finalized": int(bool(d.get("finalized"))),
        "missing_log": 0,
        "n_actions": int(d.get("n_actions") or 0),
        "sim_steps": int(d.get("control_steps") or 0),
        "physics_steps": int(d.get("physics_steps") or 0),
        "steps": int(d.get("steps") or 0),
        "calls": int(d.get("calls") or 0),
        "elapsed_s": float(d.get("elapsed_s") or 0),
        "video_rendered": int(bool(d.get("video"))),
        "task_failure": int(reason.startswith("failure")),
        "timeout": int(reason == "timeout"),
        "agent_done": int(reason == "done"),
        # a replay process gave no result, or the image no longer builds the frozen start: not the agent's 0
        "grader_error": int(bool(d.get("replay_failed") or d.get("instance_mismatch"))),
        "replay_failed": int(bool(d.get("replay_failed"))),
        "replay_timed_out": int(bool(d.get("replay_timed_out"))),
        "instance_mismatch": int(bool(d.get("instance_mismatch"))),
        # an infrastructure failure, not the agent's (PROTOCOL §2.6): a give-up after crashes between calls or a failed
        # resume (docs/STANDARD_MODE.md §13), the service not ending its episode for the collect hook, a replay
        # process that gave no result, replays that did not start in the instance's recorded state, a collect hook
        # that never wrote its verdict
        "infra_error": int(infra),
        "no_verdict": int(no_verdict),
        "gave_up": int(bool(d.get("gave_up"))),
        "sim_crashed_on_call": int(reason == "sim_crashed_on_call"),
        "sim_error": int(reason == "error"),
        "sim_startups": int(d.get("sim_startups") or 0),
        "resumes": int(d.get("resumes") or 0),
        "resume_state_mismatch": int(d.get("resume_state_mismatch") or 0),
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
    write(ok, out)


if __name__ == "__main__":
    main()
