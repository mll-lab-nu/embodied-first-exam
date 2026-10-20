"""RoboCasa-series standard-mode verifier (separate sandbox, no network): grades what the sim service wrote.

The agent never touched the service. /data/final.json holds the service's verdict on the live episode (graded_by
"live"; docs/protocol/README.md H.4; owner, 2026-10-17): success = the environment's success check holds on the
state after the last executed control step (live_success), the scene was not solved at the start, and the episode did
not end on a simulator error. Nothing is replayed (replays = 0).

/logs/verifier/reward.txt: 1 or 0. /logs/verifier/reward.json: numeric fields only. infra_error = 1: no verdict on the
agent from the live episode: final.json missing (missing_log), unreadable (grader_error too) or not finalized (the
collect hook ran out of time, the service never started); the service gave up after crashes that were not all inside
the agent's calls (sim_crashed, resume_failed) or on a scene that did not start at the frozen instance
(instance_mismatch); or it failed to write its verdict (finalize_error; grader_error too). A crash inside the agent's
calls (sim_crashed_on_call) or a simulator error raised by its actions (sim_error) is the agent's: 0, not infra. The
video decides nothing.
"""

import json
import os
import shutil

LOG = os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier")
DATA = os.environ.get("RCB_DATA", "/data")


def write(out: dict) -> None:
    open(f"{LOG}/reward.txt", "w").write(f"{out['success']}\n")
    json.dump(out, open(f"{LOG}/reward.json", "w"), indent=1)
    print(json.dumps(out))


def num(v, kind=float):
    """A number from the service's record for the reward's evidence fields; anything else (a string, a list) is 0: these
    fields decide nothing, and a value of the wrong type must not cost the verdict."""
    try:
        return kind(v or 0)
    except (TypeError, ValueError, OverflowError):
        return kind(0)


def main() -> None:
    os.makedirs(LOG, exist_ok=True)
    path = f"{DATA}/final.json"
    if not os.path.exists(path):
        write({"success": 0, "live_success": 0, "graded_by_live": 1, "replays": 0, "missing_log": 1, "infra_error": 1,
               "grader_error": 0, "sim_error": 0, "finalized": 0})
        return
    try:
        d = json.load(open(path))
        if not isinstance(d, dict):
            raise ValueError(f"final.json is not a JSON object: {type(d).__name__}")
    except (OSError, ValueError) as exc:  # truncated, not JSON, not an object: the service's record is broken, no verdict
        print(f"unreadable final.json: {exc!r}"[:300])
        write({"success": 0, "live_success": 0, "graded_by_live": 1, "replays": 0, "missing_log": 0, "infra_error": 1,
               "grader_error": 1, "sim_error": 0, "finalized": 0})
        return
    for f in ("replay.mp4", "replay.last.png", "trajectory.npz", "episode.jsonl"):
        if os.path.exists(f"{DATA}/{f}"):
            shutil.copy(f"{DATA}/{f}", f"{LOG}/{f}")
    live = bool(d.get("live_success"))
    finalize_error = bool(d.get("finalize_error"))
    infra = bool(d.get("infra_error")) or finalize_error or not d.get("finalized")
    # the service's verdict (live success, not solved at the start, no simulator error), and the live check itself
    ok = d.get("graded_by") == "live" and d.get("success") is True and live and not infra
    write(
        {
            "success": int(ok),
            "live_success": int(live),
            "graded_by_live": 1,
            "replays": 0,
            "initial_success": int(bool(d.get("initial_success"))),
            "finalized": int(bool(d.get("finalized"))),
            "control_steps": num(d.get("control_steps"), int),
            "n_actions": num(d.get("n_actions"), int),
            "sim_steps": num(d.get("control_steps"), int),
            "calls": num(d.get("calls"), int),
            "elapsed_s": num(d.get("elapsed_s")),
            "final_reward": num(d.get("final_reward")),
            "video_rendered": int(bool(d.get("video"))),
            "sim_error": int(d.get("reason") == "error"),
            "sim_crashed_on_call": int(d.get("reason") == "sim_crashed_on_call"),
            "missing_log": 0,
            "infra_error": int(infra),
            "grader_error": int(finalize_error),
        }
    )


if __name__ == "__main__":
    main()
