"""Standard-mode verifier (eai-standard/2.1): grades what the sim service -- which the agent could not touch -- wrote.

/data/final.json holds the verdict of the live episode (docs/PROTOCOL.md H.4; owner, 2026-10-17, board 0151): the sim
service judged the episode it ran by the task's rule, after the agent's container was stopped; nothing is replayed.
success = final.json's success (the live episode's, "graded_by": "live"; a benchmark's live_rule, such as a settle
window on the live simulator, can only take it away) AND not infra.
Writes /logs/verifier/reward.txt (1/0) and a numeric-only reward.json, and copies the evidence (the episode's video,
rendered from the trajectory after the verdict, its last frame, the trajectory, the event log) next to them for humans;
the evidence never decides the verdict.
infra_error = 1: no verdict on the agent (no or an unreadable final.json, the service never finished or failed to
finalize, it gave up after crashes not all inside the agent's calls, or the scene did not start at the frozen instance:
instance_mismatch). Every branch writes success, live_success, graded_by_live = 1, replays = 0, infra_error and
grader_error (PROTOCOL §2.6); sim_error = 1 when the graded episode ended on a simulator error (reason "error").
A standard-realtime service's final.json (eai-standard/2.3) also says how well its clock was kept; reward.json repeats
it (REALTIME below; PROTOCOL §4b), and none of it decides the verdict.
"""
import json
import math
import os
import shutil
import traceback

DATA = os.environ.get("RCB_DATA", "/data")
LOG = os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier")
os.makedirs(LOG, exist_ok=True)


def write(ok: bool, out: dict) -> None:
    with open(os.path.join(LOG, "reward.txt"), "w") as f:
        f.write("1\n" if ok else "0\n")
    with open(os.path.join(LOG, "reward.json"), "w") as f:
        json.dump(out, f)
    print(json.dumps(out))


def num(x, default: float = 0.0) -> float:
    """A finite number, or the default (reward.json takes numbers only)."""
    try:
        x = float(x)
    except (TypeError, ValueError):
        return default
    return x if math.isfinite(x) else default


# Standard-realtime only: slowdown S; clock_s, the wall seconds the clock ran; max_lag_s, the furthest a control step ran
# behind its time; stalls, the times the service dropped more than 0.5 s of debt instead of fast-forwarding the robot;
# stalled_s, the wall time dropped that way (the robot stood still while its clock should have run); stalled_share =
# stalled_s / clock_s; held_steps and late_steps; requests_refused (answered 4xx) and request_busy_s (simulator-thread
# time spent on requests). A field final.json does not have is 0.
REALTIME = {"slowdown": float, "clock_s": float, "max_lag_s": float, "stalls": int, "stalled_s": float,
            "stalled_share": float, "held_steps": int, "late_steps": int, "requests_refused": int,
            "request_busy_s": float}


def realtime_fields(d: dict) -> dict:
    if not (d.get("realtime") or str(d.get("protocol")) == "eai-standard/2.3"):
        return {}
    return {"realtime": 1, **{k: kind(num(d.get(k))) for k, kind in REALTIME.items()}}


# Every branch writes these keys (PROTOCOL §2.6): a missing or unreadable final.json as well as a graded one.
BASE = {"success": 0, "live_success": 0, "graded_by_live": 1, "replays": 0, "live_rule": 0, "live_verdict_error": 0,
        "finalized": 0, "missing_log": 0, "infra_error": 0, "grader_error": 0, "sim_error": 0, "sim_crashed_on_call": 0,
        "instance_mismatch": 0, "n_actions": 0, "sim_steps": 0, "calls": 0, "rows": 0, "resets": 0, "reset_budget": 0,
        "sim_startups": 0, "elapsed_s": 0.0, "video_rendered": 0}


def main() -> None:
    path = os.path.join(DATA, "final.json")
    if not os.path.exists(path):
        write(False, {**BASE, "missing_log": 1, "infra_error": 1})
        return
    try:
        with open(path) as f:
            d = json.load(f)
        if not isinstance(d, dict):
            raise ValueError("final.json is not a JSON object")
        live = bool(d.get("live_success"))
        graded = d.get("graded_by") == "live"         # the service's verdict on the live episode is in
        failed_finalize = bool(d.get("finalize_error"))
        unfinished = not d.get("finalized")
        mismatch = bool(d.get("instance_mismatch")) or str(d.get("reason") or "").startswith("instance_mismatch")
        infra = bool(d.get("infra_error")) or failed_finalize or unfinished or mismatch
        ok = bool(d.get("success")) and live and graded and not infra
        out = {**BASE, "success": int(ok), "live_success": int(live), "graded_by_live": 1, "replays": 0,
               "live_rule": int(bool(d.get("live_rule", True))),
               "live_verdict_error": int(bool(d.get("live_verdict_error"))),
               "finalized": int(not unfinished), "missing_log": 0, "infra_error": int(infra),
               "grader_error": int(failed_finalize), "sim_error": int(d.get("reason") == "error"),
               "sim_crashed_on_call": int(d.get("reason") == "sim_crashed_on_call"), "instance_mismatch": int(mismatch),
               "n_actions": int(d.get("n_actions") or 0), "sim_steps": int(d.get("control_steps_total") or 0),
               "calls": int(d.get("calls") or 0), "rows": int(d.get("rows") or 0), "resets": int(d.get("resets") or 0),
               "reset_budget": int(d.get("reset_budget") or 0),
               "sim_startups": int(d.get("sim_startups") or 0), "elapsed_s": float(d.get("elapsed_s") or 0.0),
               "video_rendered": int(bool(d.get("video"))), **realtime_fields(d)}
    except Exception:  # noqa: BLE001 -- an unreadable final.json is the grader's failure, not the agent's
        traceback.print_exc()
        write(False, {**BASE, "infra_error": 1, "grader_error": 1})
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
