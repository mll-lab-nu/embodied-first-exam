"""soccer's part of reward.json (the common part is core/grading.py): numbers only, from final.json and the declared
artifacts episode.jsonl (team messages) and think_usage_<seat>.json (metering). The keys are the legacy tasks' keys
(scripts/olympiad/soccer/*/tests/grade.py) where the v0.2 record holds the value; README "Reward keys" lists the
differences. official_config replaces the core's value with the legacy per-format rule (match: the level's own seeds and
the slowdowns; duel / team: seeds 1-3 at x10); with a hidden official seed (core 0.2.14, the sport's registered set) the
core's value stands and only the slowdown rule can lower it (hidden_rule)."""
import json
import os
from pathlib import Path

ROBOTS = ("A1", "A2", "B1", "B2")
OFFICIAL_SEEDS = {2: [202, 212, 222], 3: [303, 313, 323]}     # match: per opponent level (level 1: a warm-up, soccer-2v2-6)
OFFICIAL_SLOWDOWNS = [1, 2, 5, 10]                            # match
DUEL_SLOWDOWNS = [10]                                         # duel and team
SEAT_KEYS = ("attempts", "applied", "refused", "refused_robot", "dropped", "observations")
ROBOT_KEYS = ("goals", "own_goals", "shootout_goals", "touches", "passes_completed", "kicks", "kick_falls",
              "kicks_cancelled", "falls", "pushed_over", "penalties")


def data_dir():
    return Path(os.environ.get("RCB_DATA", "/data"))


def usage(seat):
    try:
        return json.loads((data_dir() / f"think_usage_{seat}.json").read_text())
    except (OSError, ValueError):
        return {}


def messages():
    """seat -> team messages sent (the episode's `team` rows)."""
    out = {}
    try:
        for line in (data_dir() / "episode.jsonl").read_text().splitlines():
            if '"team"' in line:
                r = json.loads(line)
                if r.get("ev") == "team":
                    out[r["seat"]] = out.get(r["seat"], 0) + 1
    except (OSError, ValueError):
        pass
    return out


def official_config(d, f):
    try:
        s = float(d.get("slowdown") or 0)
        if len(d["cfg"]["seats"]) == 1:
            return int(int(d.get("seed") or 0) in OFFICIAL_SEEDS.get(int(f.get("level") or 0), []) and
                       s in OFFICIAL_SLOWDOWNS)
        return int(int(d.get("seed") or 0) in (1, 2, 3) and s in DUEL_SLOWDOWNS)
    except (KeyError, TypeError, ValueError):
        return 0


def hidden_rule(d, out):
    """A hidden official seed (core 0.2.14: final.json seed_proof; the seed itself is never written): the core's rule
    decides (the seed must be in the format x level cell of the registered set, tests/grade.py hidden_index), so its
    official_config stands; this sport only adds its per-format slowdown rule, which can only lower it."""
    if not d.get("seed_proof"):
        return out
    try:
        single = len(d["cfg"]["seats"]) == 1
        ok = float(d.get("slowdown") or 0) in (OFFICIAL_SLOWDOWNS if single else DUEL_SLOWDOWNS)
    except (KeyError, TypeError, ValueError):
        ok = False
    if ok:
        out.pop("official_config", None)
    else:
        out["official_config"] = 0
    return out


def evaluate(d):
    f = d.get("sport_fields") or {}
    seats = d["cfg"]["seats"]
    single = len(seats) == 1
    summ = f.get("summary") or {}
    score = f.get("score") or {"A": 0, "B": 0}
    pso = summ.get("pso") or {}
    lag = d.get("sim_lag") or {}
    sim_s = float(lag.get("run_sim_s") or 0.0)
    valid = bool(d.get("valid_trial"))
    win = d.get("match_winner") if valid else None
    team_win = {"A": win == (d.get("sides") or {}).get(seats[0], seats[0]) if single else None}
    msgs = messages()
    out = dict(
        official_config=official_config(d, f), ready_forfeit=int(d.get("reason") == "ready_timeout" and
                                                                  d.get("match_winner") is not None),
        unfinished=int(d.get("reason") == "collected" and d.get("phase") == "over" and not summ.get("winner")),
        slowdown=float(d.get("slowdown") or 0.0), steps=int(d.get("steps") or 0),
        A_goals=int(score.get("A", 0)), B_goals=int(score.get("B", 0)), shootout=int(bool(pso)),
        A_shootout_goals=int((pso.get("score") or {}).get("A", 0)), B_shootout_goals=int((pso.get("score") or {}).get("B", 0)),
        end_mercy=int(f.get("end_reason") == "mercy"), end_coin_toss=int(f.get("end_reason") == "pso_coin_toss"),
        n_messages=int(d.get("team_messages") or 0), team_channel_on=int(d.get("format") == "team"),
        n_reviews=len(d.get("reviews") or []), sim_lag_late_max_s=float(lag.get("late_max_s") or 0.0),
        sim_lag_late_p99_s=float(lag.get("late_p99_s") or 0.0),
        sim_effective_slowdown=float(lag.get("run_wall_s") or 0.0) / sim_s if sim_s else 0.0)
    if single:
        won = int(valid and team_win["A"])
        out.update(won=won, level=int(f.get("level") or 0), goals_for=out["A_goals"], goals_against=out["B_goals"])
    else:
        side = d.get("sides") or {s: s for s in seats}
        for t in ("A", "B"):                                  # the team's result (duel: = the seat's <seat>_won)
            out[f"{t}_won"] = int(valid and win is not None and any(side[s] == win for s in seats if s[0] == t))
    for s in seats:
        st = d["seats"].get(s, {})
        p = "" if single else s + "_"
        for k in SEAT_KEYS:
            out[p + k] = int(st.get(k, 0))
        out[p + "act_s_max"] = float(max(st.get("act_s") or [0.0]))
        out[p + "messages"] = int(msgs.get(s, 0))
        u = usage(s)
        out[p + "metered_requests"] = int(u.get("requests", 0))
        out[p + "metered_output_tokens"] = int(u.get("output_tokens", 0))
        if single:
            out["transient_api_errors"] = int((d.get("transient_api_errors") or {}).get(s, 0))
            out["unrecovered_api_errors"] = int((d.get("unrecovered_api_errors") or {}).get(s, 0))
    stats = summ.get("stats") or {}
    for rb in ROBOTS:
        st = stats.get(rb) or {}
        for k in ROBOT_KEYS:
            out[f"{rb}_{k}"] = int(st.get(k, 0))
        out[f"{rb}_distance_m"] = round(float(st.get("distance_m", 0.0)), 2)
        out[f"{rb}_messages"] = int(msgs.get(rb, 0)) if d.get("format") == "team" else 0
    return hidden_rule(d, out)
