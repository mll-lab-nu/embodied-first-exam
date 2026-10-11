"""RoboCasa-series standard-mode verifier (separate sandbox, no network): grades what the sim service wrote.

The agent never touched the service. /data/final.json holds the service's verdict on a fresh replay of the recorded
episode: deterministic = the replay ends in the live episode's final state; success = deterministic, and the
environment's success check holds on that state both live and in the replay (and not already at the start).

/logs/verifier/reward.txt: 1 or 0. /logs/verifier/reward.json: numeric fields only. infra_error = 1: no verdict on the
agent (the service crashed past its restarts, never finished, or failed to finalize; a final.json that is missing, or
that cannot be read as a JSON object: then grader_error = 1 too).
"""

import json
import os
import shutil

LOG = "/logs/verifier"
DATA = "/data"


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
        write({"success": 0, "deterministic": 0, "missing_log": 1, "infra_error": 1, "grader_error": 0})
        return
    try:
        d = json.load(open(path))
        if not isinstance(d, dict):
            raise ValueError(f"final.json is not a JSON object: {type(d).__name__}")
    except (OSError, ValueError) as exc:  # truncated, not JSON, not an object: the service's record is broken, no verdict
        print(f"unreadable final.json: {exc!r}"[:300])
        write({"success": 0, "deterministic": 0, "missing_log": 0, "infra_error": 1, "grader_error": 1})
        return
    for f in ("replay.mp4", "replay.last.png", "trajectory.npz", "episode.jsonl"):
        if os.path.exists(f"{DATA}/{f}"):
            shutil.copy(f"{DATA}/{f}", f"{LOG}/{f}")
    det, live, rep = (bool(d.get(k)) for k in ("deterministic", "live_success", "replay_success"))
    finalize_error = bool(d.get("finalize_error"))
    infra = bool(d.get("infra_error")) or finalize_error or not d.get("finalized")
    ok = bool(d.get("success")) and det and live and rep and not infra
    write(
        {
            "success": int(ok),
            "deterministic": int(det),
            "replay_success": int(rep),
            "live_success": int(live),
            "finalized": int(bool(d.get("finalized"))),
            "control_steps": num(d.get("control_steps"), int),
            "sim_steps": num(d.get("control_steps"), int),
            "calls": num(d.get("calls"), int),
            "elapsed_s": num(d.get("elapsed_s")),
            "final_reward": num(d.get("final_reward")),
            "video_rendered": int(bool(d.get("video"))),
            "sim_error": int(d.get("reason") == "error"),
            "missing_log": 0,
            "infra_error": int(infra),
            "grader_error": int(finalize_error),
        }
    )


if __name__ == "__main__":
    main()
