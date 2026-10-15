"""Standard-mode verifier (eai-standard/2.1): grades what the sim service -- which the agent could not touch -- wrote.

/data/final.json holds the live run's outcome and the verdict of a fresh replay of the graded episode:
success = live_success AND replay_success AND deterministic (the replay ends in the live run's final state).
Writes /logs/verifier/reward.txt (1/0) and a numeric-only reward.json, and copies the evidence (replay video, last
frame, trajectory, event log) next to them for humans; the evidence never decides the verdict.

The verdict is in once the episode ended (`done`) and, for a live success, once the replay's verdict is on disk
(`deterministic` present: rcb_service writes it before the video is finished). `finalized` only says the video is done
too: a video still unfinished when the collect hook stops waiting costs the video, never the verdict (PROTOCOL §2.6).
An episode that ended without a live success (time up, the step cap, a simulator error) is a failure whatever its
replay says, so it needs no replay.
infra_error = 1: no verdict on the agent -- the service crashed past its restarts (its own infra_error), the episode
never ended, or a live success has no replay verdict (the replay did not finish in time or failed).
reward.json has the same fields on every path, also when final.json is missing or unreadable (all 0 but the error flags;
`deterministic` is a MUST for trajectory tasks, PROTOCOL §2.6).
"""
import json
import os
import shutil
import traceback

DATA = os.environ.get("RCB_DATA", "/data")
LOG = os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier")
os.makedirs(LOG, exist_ok=True)
# Every reward.json field, at the value it has when there is no verdict to read.
BLANK = {"success": 0, "live_success": 0, "replay_success": 0, "deterministic": 0, "replayed": 0, "finalized": 0,
         "missing_log": 0, "infra_error": 0, "grader_error": 0, "timeout": 0, "sim_error": 0, "sim_crashed_on_call": 0,
         "n_actions": 0, "sim_steps": 0, "calls": 0, "rows": 0, "resets": 0, "reset_budget": 0, "sim_startups": 0,
         "elapsed_s": 0.0, "video_rendered": 0}


def write(ok: bool, out: dict) -> None:
    with open(os.path.join(LOG, "reward.txt"), "w") as f:
        f.write("1\n" if ok else "0\n")
    with open(os.path.join(LOG, "reward.json"), "w") as f:
        json.dump(out, f)
    print(json.dumps(out))


def main() -> None:
    path = os.path.join(DATA, "final.json")
    if not os.path.exists(path):
        write(False, {**BLANK, "missing_log": 1, "infra_error": 1})
        return
    try:
        with open(path) as f:
            d = json.load(f)
        live, replay, det = (bool(d.get(k)) for k in ("live_success", "replay_success", "deterministic"))
        ended = bool(d.get("done"))
        replayed = "deterministic" in d                  # the fresh replay's verdict is on disk
        failed_finalize = bool(d.get("finalize_error"))
        infra = bool(d.get("infra_error")) or not ended or (live and not replayed)
        ok = live and replay and det and not infra
        out = {"success": int(ok), "live_success": int(live), "replay_success": int(replay), "deterministic": int(det),
               "replayed": int(replayed), "finalized": int(bool(d.get("finalized"))), "missing_log": 0,
               "infra_error": int(infra), "grader_error": int(failed_finalize),
               "timeout": int(d.get("reason") == "timeout"), "sim_error": int(d.get("reason") == "error"),
               "sim_crashed_on_call": int(d.get("reason") == "sim_crashed_on_call"),
               "n_actions": int(d.get("n_actions") or 0), "sim_steps": int(d.get("control_steps_total") or 0),
               "calls": int(d.get("calls") or 0), "rows": int(d.get("rows") or 0), "resets": int(d.get("resets") or 0),
               "reset_budget": int(d.get("reset_budget") or 0),
               "sim_startups": int(d.get("sim_startups") or 0), "elapsed_s": float(d.get("elapsed_s") or 0.0),
               "video_rendered": int(bool(d.get("video")))}
    except Exception:  # noqa: BLE001 -- an unreadable final.json is the grader's failure, not the agent's
        traceback.print_exc()
        write(False, {**BLANK, "infra_error": 1, "grader_error": 1})
        return
    for name in ("replay.mp4", "replay.last.png", "trajectory.npz", "episode.jsonl"):
        try:
            if os.path.exists(os.path.join(DATA, name)):
                shutil.copy(os.path.join(DATA, name), os.path.join(LOG, name))
        except OSError:
            traceback.print_exc()
    write(ok, out)


if __name__ == "__main__":
    main()
