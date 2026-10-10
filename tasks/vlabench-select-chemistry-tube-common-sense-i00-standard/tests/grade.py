"""Standard-mode verifier (eai-standard/2.1): grades what the sim service -- which the agent could not touch -- wrote.

/data/final.json holds the live run's outcome and the verdict of a fresh replay of the graded episode:
success = live_success AND replay_success AND deterministic (the replay ends in the live run's final state).
Writes /logs/verifier/reward.txt (1/0) and a numeric-only reward.json, and copies the evidence (replay video, last
frame, trajectory, event log) next to them for humans; the evidence never decides the verdict.
infra_error = 1: no verdict on the agent (the service crashed past its restarts, never finished, or failed to finalize).
Every branch writes success, deterministic, infra_error and grader_error (PROTOCOL §2.6); sim_error = 1 when the graded
episode ended on a simulator error (reason "error").
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


def main() -> None:
    path = os.path.join(DATA, "final.json")
    if not os.path.exists(path):
        write(False, {"success": 0, "deterministic": 0, "missing_log": 1, "infra_error": 1, "sim_error": 0,
                      "grader_error": 0})
        return
    try:
        with open(path) as f:
            d = json.load(f)
        if not isinstance(d, dict):
            raise ValueError("final.json is not a JSON object")
        live, replay, det = (bool(d.get(k)) for k in ("live_success", "replay_success", "deterministic"))
        failed_finalize = bool(d.get("finalize_error"))
        unfinished = not d.get("finalized")
        infra = bool(d.get("infra_error")) or failed_finalize or unfinished
        ok = live and replay and det and not infra
        out = {"success": int(ok), "live_success": int(live), "replay_success": int(replay), "deterministic": int(det),
               "finalized": int(not unfinished), "missing_log": 0, "infra_error": int(infra),
               "grader_error": int(failed_finalize), "sim_error": int(d.get("reason") == "error"),
               "sim_crashed_on_call": int(d.get("reason") == "sim_crashed_on_call"),
               "n_actions": int(d.get("n_actions") or 0), "sim_steps": int(d.get("control_steps_total") or 0),
               "calls": int(d.get("calls") or 0), "rows": int(d.get("rows") or 0), "resets": int(d.get("resets") or 0),
               "reset_budget": int(d.get("reset_budget") or 0),
               "sim_startups": int(d.get("sim_startups") or 0), "elapsed_s": float(d.get("elapsed_s") or 0.0),
               "video_rendered": int(bool(d.get("video"))), **realtime_fields(d)}
    except Exception:  # noqa: BLE001 -- an unreadable final.json is the grader's failure, not the agent's
        traceback.print_exc()
        write(False, {"success": 0, "deterministic": 0, "missing_log": 0, "infra_error": 1, "sim_error": 0,
                      "grader_error": 1})
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
