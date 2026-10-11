"""Standard-realtime verifier (eai-standard/2.3) for RoboOlympics: grades what the sim service -- which the agent could
not touch -- wrote.

/data/final.json holds the live match's outcome and the verdict of a fresh-process replay of its record:
success = live_success (the match finished and the agent won it) AND replay_success (the replay's match too) AND
deterministic (the replay ends in the live run's state). /data/match.json (the replay's summary: the score, the breaks,
the commands) only adds information to reward.json; it never decides the verdict.
Writes /logs/verifier/reward.txt (1/0) and a numeric-only reward.json, and copies the evidence (replay video, last
frame, the replay's summary, event log) next to them for humans.
infra_error = 1: no verdict on the agent (the service crashed past its restarts, failed to resume, ended on a simulator
error, never finished, or failed to finalize; PROTOCOL §4b).
reward.json says realtime = 1 (every RoboOlympics task is standard-realtime; the other realtime graders write the same
key) and repeats how well the service kept its clock (PROTOCOL §4b; none of it decides the verdict): slowdown S;
clock_s, the wall seconds the clock ran; max_lag_s, the furthest a control step ran behind its time; stalls, the times
the service dropped more than 0.5 s of debt instead of fast-forwarding the match; stalled_s, the wall time dropped that
way (the match stood still while its clock should have run); stalled_share = stalled_s / clock_s; held_steps and
late_steps; requests_refused (answered 4xx) and request_busy_s (simulator-thread time spent on requests). A field
final.json does not have is 0.
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


def num(x, default=0.0) -> float:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return default
    return x if math.isfinite(x) else default


def match_fields() -> dict:
    """Information from the replay's summary (numbers only); {} if there is none."""
    try:
        with open(os.path.join(DATA, "match.json")) as f:
            m = json.load(f)
    except (OSError, ValueError):
        return {}
    return {"match_finished": int(bool(m.get("finished"))), "match_won": int(bool(m.get("won"))),
            "points_for": num(m.get("points_for")), "points_against": num(m.get("points_against")),
            "match_steps": int(num(m.get("match_steps"))), "breaks": len(m.get("breaks") or []),
            "breaks_ended_by_ready": sum(1 for b in m.get("breaks") or [] if b.get("by") == "ready"),
            "commands_applied": int(num(m.get("commands_applied"))),
            "commands_refused": int(num(m.get("commands_refused")))}


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
        sim_error = d.get("reason") == "error"
        infra = bool(d.get("infra_error")) or failed_finalize or unfinished or sim_error
        ok = live and replay and det and not infra
        out = {"success": int(ok), "live_success": int(live), "replay_success": int(replay), "deterministic": int(det),
               "finalized": int(not unfinished), "missing_log": 0, "infra_error": int(infra),
               "sim_error": int(sim_error), "grader_error": int(failed_finalize),
               "timeout": int(d.get("reason") == "timeout"),
               "n_actions": int(num(d.get("n_actions"))), "control_steps": int(num(d.get("control_steps_total"))),
               "calls": int(num(d.get("calls"))), "rows": int(num(d.get("rows"))),
               "reset_budget": int(num(d.get("reset_budget"))), "realtime": 1, "slowdown": num(d.get("slowdown")),
               "clock_s": num(d.get("clock_s")), "max_lag_s": num(d.get("max_lag_s")),
               "stalls": int(num(d.get("stalls"))), "stalled_s": num(d.get("stalled_s")),
               "stalled_share": num(d.get("stalled_share")), "held_steps": int(num(d.get("held_steps"))),
               "late_steps": int(num(d.get("late_steps"))), "requests_refused": int(num(d.get("requests_refused"))),
               "request_busy_s": num(d.get("request_busy_s")), "sim_startups": int(num(d.get("sim_startups"))),
               "elapsed_s": num(d.get("elapsed_s")), "video_rendered": int(bool(d.get("video"))), **match_fields()}
    except Exception:  # noqa: BLE001 -- an unreadable final.json is the grader's failure, not the agent's
        traceback.print_exc()
        write(False, {"success": 0, "deterministic": 0, "missing_log": 0, "infra_error": 1, "sim_error": 0,
                      "grader_error": 1})
        return
    for name in ("replay.mp4", "replay.last.png", "match.json", "episode.jsonl"):
        try:
            if os.path.exists(os.path.join(DATA, name)):
                shutil.copy(os.path.join(DATA, name), os.path.join(LOG, name))
        except OSError:
            traceback.print_exc()
    write(ok, out)


if __name__ == "__main__":
    main()
