"""MetaWorld+ standard-mode verifier (separate sandbox, no network): grades what the sim service wrote.

The agent never touched the service. /data/final.json holds the service's verdict on a fresh replay of the recorded
episode: deterministic = the replay ends in the live episode's final state; success = deterministic and Meta-World's
success check holds on that state, both live and in the replay.

infra_error = 1: there is no verdict on the agent, so the trial is not the agent's 0: final.json is missing or
unreadable, the service gave up after crashes or its verification replay failed, or it never got as far as a verdict
(not finalized: the collect hook gave up waiting, or never ran). A verdict that is on disk is graded whether or not
the replay video was rendered after it; the video never decides anything.

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
    return {"success": 0, "deterministic": 0, "missing_log": 0, "sim_error": 0, "infra_error": 1, "grader_error": 0, **flags}


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
    det = bool(d.get("deterministic"))
    live = bool(d.get("live_success"))
    rep = bool(d.get("replay_success"))
    unfinished = not d.get("finalized") and "deterministic" not in d  # the service never reached a verdict
    failed_finalize = bool(d.get("finalize_error"))
    infra = bool(d.get("infra_error")) or failed_finalize or unfinished
    ok = bool(d.get("success")) and det and rep and live and not infra
    out = {
        "success": int(ok),
        "deterministic": int(det),
        "replay_success": int(rep),
        "live_success": int(live),
        "finalized": int(bool(d.get("finalized"))),
        "no_verdict": int(unfinished),
        "missing_log": 0,
        "control_steps": int(d.get("control_steps") or 0),
        "sim_steps": int(d.get("control_steps") or 0),
        "calls": int(d.get("calls") or 0),
        "elapsed_s": float(d.get("elapsed_s") or 0),
        "final_reward": float(d.get("final_reward") or 0),
        "video_rendered": int(bool(d.get("video"))),
        "sim_error": int(d.get("reason") == "error"),
        "sim_crashed_on_call": int(d.get("reason") == "sim_crashed_on_call"),
        # no verdict on the agent: the service crashed (restart refused), its verification replay failed, or it never
        # finished
        "infra_error": int(infra),
        "grader_error": int(failed_finalize),
    }
    write(out)


if __name__ == "__main__":
    main()
