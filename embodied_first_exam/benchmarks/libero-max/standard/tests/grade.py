"""Standard-mode verifier (eai-standard/2.1): grades what the sim service -- which the agent could not touch -- wrote.

The verdict is the live episode's (docs/protocol/README.md H.4; owner, 2026-10-17): /data/final.json holds the
episode the service ran and its verdict, nothing is replayed. success = the live episode ended in LIBERO's success
(`live_success`; the service ends the episode the moment the success check holds) and the service graded it live
(`graded_by = "live"`, its `success`). Writes /logs/verifier/reward.txt (1/0) and a numeric-only reward.json, and copies
the evidence (the video, its last frame and record, the trajectory, the event log) next to them for humans; the
evidence never decides the verdict.

The verdict is in once final.json is `finalized` (the service writes it within seconds of the collect hook's signal,
before the video is rendered: a video still unfinished when the hook stops waiting costs the video, never the verdict).
infra_error = 1: no verdict on the agent -- final.json missing, unreadable or never finalized (the service never came
back), the service's own infra_error (crashes not all inside the agent's calls, a failed resume, the scene not
starting at the frozen instance's state: instance_mismatch), or a finalize that failed on the service's side.
A crash inside the agent's calls (sim_crashed_on_call), a simulator error the agent's actions raised (sim_error), the
time running out and the step cap are the agent's: 0, never infra.
reward.json has the same fields on every path, also when final.json is missing or unreadable.
"""
import json
import os
import shutil
import traceback

DATA = os.environ.get("RCB_DATA", "/data")
LOG = os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier")
os.makedirs(LOG, exist_ok=True)
# Every reward.json field, at the value it has when there is no verdict to read.
BLANK = {"success": 0, "live_success": 0, "graded_by_live": 0, "replays": 0, "finalized": 0, "missing_log": 0,
         "infra_error": 0, "grader_error": 0, "instance_mismatch": 0, "timeout": 0, "sim_error": 0,
         "sim_crashed_on_call": 0, "event_fired": 0, "event_step": 0, "n_actions": 0, "sim_steps": 0, "calls": 0,
         "rows": 0, "resets": 0, "reset_budget": 0, "sim_startups": 0, "elapsed_s": 0.0, "video_rendered": 0}


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
        if not isinstance(d, dict):
            raise ValueError("final.json is not a JSON object")
        live = bool(d.get("live_success"))
        by_live = d.get("graded_by") == "live"
        finalized = bool(d.get("finalized"))
        failed_finalize = bool(d.get("finalize_error"))
        reason = str(d.get("reason") or "")
        infra = bool(d.get("infra_error")) or not finalized or failed_finalize
        ok = bool(d.get("success")) and live and by_live and not infra
        out = {"success": int(ok), "live_success": int(live), "graded_by_live": int(by_live),
               "replays": int(d.get("replays") or 0), "finalized": int(finalized), "missing_log": 0,
               "infra_error": int(infra), "grader_error": int(failed_finalize),
               "instance_mismatch": int(reason.startswith("instance_mismatch")),
               "timeout": int(reason == "timeout"), "sim_error": int(reason == "error"),
               "sim_crashed_on_call": int(reason == "sim_crashed_on_call"),
               "event_fired": int(bool(d.get("event_fired"))), "event_step": int(d.get("event_step") or 0),
               "n_actions": int(d.get("n_actions") or 0), "sim_steps": int(d.get("control_steps_total") or 0),
               "calls": int(d.get("calls") or 0), "rows": int(d.get("rows") or 0), "resets": int(d.get("resets") or 0),
               "reset_budget": int(d.get("reset_budget") or 0),
               "sim_startups": int(d.get("sim_startups") or 0), "elapsed_s": float(d.get("elapsed_s") or 0.0),
               "video_rendered": int(bool(d.get("video")))}
    except Exception:  # noqa: BLE001 -- an unreadable final.json is the grader's failure, not the agent's
        traceback.print_exc()
        write(False, {**BLANK, "infra_error": 1, "grader_error": 1})
        return
    for name in ("replay.mp4", "replay.last.png", "replay.video.json", "trajectory.npz", "episode.jsonl"):
        try:
            if os.path.exists(os.path.join(DATA, name)):
                shutil.copy(os.path.join(DATA, name), os.path.join(LOG, name))
        except OSError:
            traceback.print_exc()
    write(ok, out)


if __name__ == "__main__":
    main()
