"""airhockey's part of reward.json (the common part is core/grading.py, which runs first; these keys are added after
it): numbers only, from final.json and, for the legacy metering keys, the sim's artifacts think_usage_<seat>.json in
RCB_DATA. The keys are the legacy tasks' (scripts/olympiad/airhockey/{match,duel}/tests/grade.py) wherever final.json
still has the value; README lists what changed and why. official_config replaces the core's value: the legacy rule is
per format (match: the level's own seeds and the slowdowns 1-20; duel: seeds 1-3 at x10 or x20), which [official]
cannot express."""
import json
import os
from pathlib import Path

DATA = Path(os.environ.get("RCB_DATA", "/data"))
OFFICIAL_SEEDS = {1: [101, 111, 121], 2: [202, 212, 222], 3: [303, 313, 323], 4: [404, 414, 424]}
OFFICIAL_SLOWDOWNS = [1, 2, 5, 10, 20]
DUEL_SEEDS = [1, 2, 3]
DUEL_SLOWDOWNS = [10, 20]
REVISION = 4                                      # hockey.REVISION airhockey-program-v4 (the simulator and referee)
METERED = ("requests", "input_tokens", "output_tokens", "rate_limit_retries")


def _usage(seat):
    try:
        return json.loads((DATA / f"think_usage_{seat}.json").read_text())
    except (OSError, ValueError):
        return {}


def evaluate(d):
    f, seats = d.get("sport_fields") or {}, d["cfg"]["seats"]
    duel = len(seats) == 2
    reason, errors = d.get("reason"), d.get("errors") or []
    results = f.get("results") or []
    table = f.get("scores") or {}
    normal = reason == "match_over" and bool(f.get("done"))
    decided = (f.get("decided_by") or "") if normal else ""
    lag = d.get("sim_lag") or {}
    run_sim = float(lag.get("run_sim_s") or 0.0)
    level, seed, slow = int(f.get("level") or 1), int(d.get("seed") or 0), float(d.get("slowdown") or 0.0)
    official = (seed in DUEL_SEEDS and slow in DUEL_SLOWDOWNS) if duel else \
        (seed in OFFICIAL_SEEDS.get(level, []) and slow in OFFICIAL_SLOWDOWNS)
    stats = d.get("seats") or {}
    out = dict(
        replay_error=int(not d.get("deterministic") or any(e.get("where") == "replay" for e in errors)),
        sim_error=int(reason == "technical_error" or any(e.get("where") == "world" for e in errors)),
        meter_error=int(any((d.get("meter_error") or {}).get(s) for s in seats)),
        proxy_error=int(any((d.get("proxy_error") or {}).get(s) for s in seats)), timing_invalid=0,
        official_config=int(official), revision=REVISION, slowdown=slow,
        first_player_A=int((f.get("first_player") or d.get("first")) == "A"),
        match_limit=int(normal and decided.startswith("cap")), decided_by_score=int(decided == "score"),
        decided_by_last_goal=int(decided == "cap_last_goal"), decided_by_territory=int(decided == "cap_territory"),
        decided_by_first_possession=int(decided == "cap_first_possession"),
        rallies=len(results), goals=sum(r.get("how") == "goal" for r in results),
        own_goals=sum(bool(r.get("own_goal")) for r in results),
        seven_second_fouls=sum(r.get("how") == "seven_second_foul" for r in results),
        dead_pucks=sum(r.get("how") == "dead_puck" for r in results),
        n_actions=sum(int((stats.get(s) or {}).get("applied", 0)) for s in seats),
        n_reviews=len(d.get("reviews") or []), steps=int(d.get("steps") or 0),
        mallet_contact_steps=int(f.get("mallet_contact_steps", 0)), rail_contact_steps=int(f.get("rail_contact_steps", 0)),
        late_over_100ms=int(float(lag.get("late_max_s") or 0.0) > 0.1),
        sim_lag_late_max_s=float(lag.get("late_max_s") or 0.0), sim_lag_late_p99_s=float(lag.get("late_p99_s") or 0.0),
        sim_effective_slowdown=float(lag.get("run_wall_s") or 0.0) / run_sim if run_sim > 0 else 0.0,
        sim_run_wall_s=float(lag.get("run_wall_s") or 0.0))
    if duel:
        complete = d.get("match_winner") is not None
        out.update(ready_forfeit=int(reason == "ready_timeout" and complete),
                   start_forfeit=int(reason == "no_show" and complete))
        for s in seats:
            row, u = table.get(s) or {}, _usage(s)
            out[s + "_points"] = int(row.get("points", 0))
            out[s + "_fouls"] = int(row.get("fouls", 0))
            for k in METERED:
                out[f"{s}_metered_{k}"] = int(u.get(k, 0))
        return out
    a, b, u = table.get("A") or {}, table.get("B") or {}, _usage("A")
    out.update(level=level, won=int(bool(d.get("valid_trial")) and d.get("match_winner") == "A"),
               points_for=int(a.get("points", 0)), points_against=int(b.get("points", 0)), fouls=int(a.get("fouls", 0)),
               opponent_fouls=int(b.get("fouls", 0)),
               session_ended=int(reason in ("no_show", "collected", "incomplete", "abandoned") and not f.get("done")),
               transient_api_errors=int((d.get("transient_api_errors") or {}).get("A", 0)),
               unrecovered_api_errors=int((d.get("unrecovered_api_errors") or {}).get("A", 0)),
               metered_requests=int(u.get("requests", 0)), metered_input_tokens=int(u.get("input_tokens", 0)),
               metered_output_tokens=int(u.get("output_tokens", 0)), rate_limit_retries=int(u.get("rate_limit_retries", 0)))
    return out
