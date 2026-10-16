"""billiards' part of reward.json (the common part is core/grading.py: success, valid_trial, <seat>_won, ...): numbers
only, from final.json (and the seats' metering summaries, think_usage_<seat>.json, both declared artifacts of the
sim). The keys keep the legacy reward names of both tasks (scripts/olympiad/billiards/{eightball,duel}/tests/
grade.py), official_config with the per-format official configurations; new: breaker (duel: the seat that broke,
0 = A, 1 = B; since billiards-2 the seed's coin toss, so it may differ from first_player; eightball since billiards-3:
1 if the player broke, 0 if the scripted opponent did), physics_retries, ball_share (billiards-3: the continuous score,
the player's share of the rack's progress, see plugin.BilliardsMatch.ball_share; duel: <seat>_ball_share).
A hidden official seed (core 0.2.14, frozen sport) is recorded as seed = -1: the legacy public-seed rule lets it
through and core/grading.py makes official_config 1 only for a seed registered in the match's cell (core 0.2.19)."""
import json
import os
from pathlib import Path

DATA = Path(os.environ.get("RCB_DATA", "/data"))
OFFICIAL = {"eightball": {lv: [1, 2, 3, 4, 5, 6, 7, 8] for lv in (1, 2, 3)}, "duel": [1, 3, 4]}   # sport.toml [official]


def _usage(seat):
    try:
        return json.loads((DATA / f"think_usage_{seat}.json").read_text())
    except (OSError, ValueError):
        return {}


def evaluate(d):
    f = d.get("sport_fields") or {}
    seats = d["cfg"]["seats"]
    reason, forfeiting = d.get("reason"), d.get("forfeiting")
    stats = d.get("seats") or {}
    clock_s = float(d.get("clock_s") or 0.0)
    used = d.get("clock_used_s") or {}
    started = d.get("started") or {}
    seed = int(d.get("seed") or 0)
    out = {"clock_forfeit": int(reason == "clock"), "clock_tiebreak": int(bool(f.get("tiebreak"))),
           "elapsed_s": float(d.get("elapsed_s") or 0.0), "physics_retries": int(f.get("physics_retries", 0)),
           "physics_voids": int(f.get("physics_voids", 0))}
    if len(seats) == 1:                                  # the rack against the scripted opponent
        s = seats[0]
        st, u = stats.get(s, {}), _usage(s)
        level = int(f.get("level") or 0)
        out.update(
            won=int(d.get("match_winner") == s and reason == "match_over"), lost=int(d.get("match_winner") == "opponent"),
            level=level, official_config=int(seed == -1 or seed in OFFICIAL["eightball"].get(level, [])),
            game_over=int(bool(f.get("game_over"))), your_balls_left=int(f.get("your_balls_left", 7)),
            opponent_balls_left=int(f.get("opponent_balls_left", 7)), finalized=int(bool(d.get("finalized"))),
            ball_share=float(f.get("ball_share", 0.5)), breaker=int(f.get("breaker") == s),
            clock_left_s=round(clock_s - float(used.get(s, 0.0)), 1), our_shots=int(f.get("our_shots", 0)),
            opponent_shots=int(f.get("opponent_shots", 0)), our_pots=int(f.get("our_pots", 0)),
            our_fouls=int(f.get("our_fouls", 0)), n_decisions=int(st.get("n_act", 0)),
            n_reviews=int(st.get("n_reviews", 0)), refused_busy=int(st.get("refused_busy", 0)),
            refused_not_model=int(st.get("refused_not_model", 0)), sim_error=int(bool(d.get("errors"))),
            replay_error=int(not d.get("deterministic")), meter_error=int(bool((d.get("meter_error") or {}).get(s))),
            proxy_error=int(bool((d.get("proxy_error") or {}).get(s))),
            transient_api_errors=int((d.get("transient_api_errors") or {}).get(s, 0)),
            unrecovered_api_errors=int((d.get("unrecovered_api_errors") or {}).get(s, 0)),
            metered_requests=int(u.get("requests", 0)), metered_output_tokens=int(u.get("output_tokens", 0)),
            metered_input_tokens=int(u.get("input_tokens", 0)), rate_limit_retries=int(u.get("rate_limit_retries", 0)))
        return out
    balls = f.get("balls_left") or {}
    out.update(start_forfeit=int(reason == "no_show" or (reason == "incomplete" and any(started.values())
                                                                and not all(started.values()))),
               first_player=0 if d.get("first") == "A" else 1, breaker=0 if f.get("breaker") == "A" else 1,
               n_shots=int(f.get("n_shots", 0)),
               official_config=int((seed == -1 or seed in OFFICIAL["duel"]) and d.get("first") in ("A", "B")))
    for s in seats:
        st = stats.get(s, {})
        out[s + "_balls_left"] = int(balls.get(s, (d.get("scores") or {}).get(s, 7)))
        out[s + "_ball_share"] = float((f.get("ball_share") or {}).get(s, 0.5))
        out[s + "_clock_forfeit"] = int(reason == "clock" and forfeiting == s)
        out[s + "_n_decisions"] = int(st.get("n_act", 0))
        out[s + "_n_reviews"] = int(st.get("n_reviews", 0))
        out[s + "_refused_busy"] = int(st.get("refused_busy", 0))
        out[s + "_refused_not_model"] = int(st.get("refused_not_model", 0))
        out[s + "_refused_out_of_turn"] = int(st.get("refused_turn", 0))
        out[s + "_clock_left_s"] = round(clock_s - float(used.get(s, 0.0)), 1)
    return out
