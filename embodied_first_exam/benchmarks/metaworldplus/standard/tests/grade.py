"""MetaWorld+ standard-mode verifier (separate sandbox, no network): grades what the sim service wrote.

The agent never touched the service. /data/final.json holds the service's verdict on the live episode (owner
2026-10-17, board 0150/0151; graded_by "live", nothing replayed): success = Meta-World's success check on the live
simulator's state after the last executed control step (live_success). The check is a predicate on that one state
(no hold or settle window), the same rule the privileged verifier applies to its replay.

infra_error = 1: there is no verdict on the agent, so the trial is not the agent's 0: final.json is missing or
unreadable, the service gave up after crashes that were not all inside the agent's calls (sim_crashed, resume_failed),
the scene did not start at the frozen instance (instance_mismatch), the service failed to record the verdict
(finalize_error), or it never got as far as a verdict (not finalized: the collect hook gave up waiting, or never ran).
A crash inside the agent's calls (sim_crashed_on_call) or a simulator error raised by its actions (reason "error") is
the agent's 0. A verdict that is on disk is graded whether or not the video was rendered after it; the video never
decides anything.

/logs/verifier/reward.txt: 1 or 0. /logs/verifier/reward.json: numeric fields only.
"""

import json
import os
import shutil
import traceback

LOG = os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier")
DATA = os.environ.get("RCB_DATA", "/data")


def write(out: dict) -> None:
    open(f"{LOG}/reward.txt", "w").write(f"{out['success']}\n")
    json.dump(out, open(f"{LOG}/reward.json", "w"), indent=1)
    print(json.dumps(out))


def no_verdict(**flags: int) -> dict:
    return {"success": 0, "live_success": 0, "graded_by_live": 1, "replays": 0, "finalized": 0, "missing_log": 0,
            "sim_error": 0, "infra_error": 1, "grader_error": 0, **flags}


def num(v, kind=float):
    """A number for the reward's evidence fields; anything else is 0 (these fields decide nothing)."""
    try:
        return kind(v or 0)
    except (TypeError, ValueError, OverflowError):
        return kind(0)


def main() -> None:
    os.makedirs(LOG, exist_ok=True)
    final = f"{DATA}/final.json"
    if not os.path.exists(final):
        write(no_verdict(missing_log=1))
        return
    try:
        d = json.load(open(final))
        if not isinstance(d, dict):
            raise ValueError("final.json is not a JSON object")
    except Exception:  # noqa: BLE001 -- cut short or garbled: not the agent's 0
        traceback.print_exc()
        write(no_verdict(bad_log=1, grader_error=1))
        return
    for f in ("replay.mp4", "replay.last.png", "trajectory.npz", "episode.jsonl"):
        try:
            if os.path.exists(f"{DATA}/{f}"):
                shutil.copy(f"{DATA}/{f}", f"{LOG}/{f}")
        except OSError:
            traceback.print_exc()
    live = bool(d.get("live_success"))
    unfinished = not d.get("finalized")  # the service never reached a verdict
    failed_finalize = bool(d.get("finalize_error"))
    infra = bool(d.get("infra_error")) or failed_finalize or unfinished
    ok = bool(d.get("success")) and live and not infra
    reason = str(d.get("reason") or "")
    out = {
        "success": int(ok),
        "live_success": int(live),
        "graded_by_live": 1,
        "replays": 0,
        "finalized": int(bool(d.get("finalized"))),
        "no_verdict": int(unfinished),
        "missing_log": 0,
        "control_steps": num(d.get("control_steps"), int),
        "sim_steps": num(d.get("control_steps"), int),
        "calls": num(d.get("calls"), int),
        "elapsed_s": num(d.get("elapsed_s")),
        "final_reward": num(d.get("final_reward")),
        "video_rendered": int(bool(d.get("video"))),
        "sim_error": int(reason == "error"),
        "sim_crashed_on_call": int(reason == "sim_crashed_on_call"),
        "instance_mismatch": int(reason.startswith("instance_mismatch")),
        "infra_error": int(infra),
        "grader_error": int(failed_finalize),
    }
    write(out)


if __name__ == "__main__":
    main()
