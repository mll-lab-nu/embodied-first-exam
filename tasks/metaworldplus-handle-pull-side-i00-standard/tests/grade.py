"""MetaWorld+ standard-mode verifier (separate sandbox, no network): grades what the sim service wrote.

The agent never touched the service. /data/final.json holds the service's verdict on a fresh replay of the recorded
episode: deterministic = the replay ends in the live episode's final state; success = deterministic and Meta-World's
success check holds on that state, both live and in the replay.

/logs/verifier/reward.txt: 1 or 0. /logs/verifier/reward.json: numeric fields only.
"""

import json
import os
import shutil

LOG = "/logs/verifier"
FINAL = "/data/final.json"


def write(out: dict) -> None:
    open(f"{LOG}/reward.txt", "w").write(f"{out['success']}\n")
    json.dump(out, open(f"{LOG}/reward.json", "w"), indent=1)
    print(json.dumps(out))


def main() -> None:
    os.makedirs(LOG, exist_ok=True)
    if not os.path.exists(FINAL):
        write({"success": 0, "deterministic": 0, "missing_log": 1, "infra_error": 1, "grader_error": 0})
        return
    d = json.load(open(FINAL))
    for f in ("replay.mp4", "replay.last.png", "trajectory.npz", "episode.jsonl"):
        if os.path.exists(f"/data/{f}"):
            shutil.copy(f"/data/{f}", f"{LOG}/{f}")
    det = bool(d.get("deterministic"))
    live = bool(d.get("live_success"))
    rep = bool(d.get("replay_success"))
    ok = bool(d.get("success")) and det and rep and live
    out = {
        "success": int(ok),
        "deterministic": int(det),
        "replay_success": int(rep),
        "live_success": int(live),
        "finalized": int(bool(d.get("finalized"))),
        "control_steps": int(d.get("control_steps") or 0),
        "sim_steps": int(d.get("control_steps") or 0),
        "calls": int(d.get("calls") or 0),
        "elapsed_s": float(d.get("elapsed_s") or 0),
        "final_reward": float(d.get("final_reward") or 0),
        "video_rendered": int(bool(d.get("video"))),
        "sim_error": int(d.get("reason") == "error"),
        "infra_error": 0,
        "grader_error": 0,
    }
    # no verdict on the agent: the service crashed (restart refused) or its verification replay failed
    if d.get("infra_error") or d.get("finalize_error"):
        out.update(infra_error=1, grader_error=int(bool(d.get("finalize_error"))))
    write(out)


if __name__ == "__main__":
    main()
