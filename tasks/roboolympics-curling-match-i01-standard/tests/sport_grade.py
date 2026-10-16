"""curling's part of reward.json (the common part is core/grading.py: success, valid_trial, <seat>_won, ...): numbers
only, from final.json (and the seats' metering summaries, think_usage_<seat>.json, both declared artifacts of the
sim). The keys keep the legacy reward names of both tasks (scripts/olympiad/curling/{match,duel}/tests/grade.py)."""
import json
import os
from pathlib import Path

DATA = Path(os.environ.get("RCB_DATA", "/data"))


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
    out = {"clock_forfeit": int(reason == "clock"), "clock_tiebreak": int(bool(f.get("tiebreak"))),
           "elapsed_s": float(d.get("elapsed_s") or 0.0)}
    if len(seats) == 1:                                  # the match against the scripted team
        s = seats[0]
        st, u = stats.get(s, {}), _usage(s)
        pf, pa = int(f.get("points_for", 0)), int(f.get("points_against", 0))
        rp = d.get("replay_scores") or {}
        out.update(
            won=int(d.get("match_winner") == s and reason == "match_over"), level=int(f.get("level") or 0),
            points_for=pf, points_against=pa, margin=pf - pa,
            stone_share=0.5 if pf + pa == 0 else round(pf / (pf + pa), 6),    # the continuous score (curling-3)
            replay_points_for=int(rp.get(s, -1)), replay_points_against=int(rp.get("opponent", -1)),
            finalized=int(bool(d.get("finalized"))), n_ends_played=int(f.get("n_ends_played", 0)),
            throws=int(f.get("throws", 0)), clock_left_s=round(clock_s - float(used.get(s, 0.0)), 1),
            n_decisions=int(st.get("n_act", 0)), n_reviews=int(st.get("n_reviews", 0)),
            refused_busy=int(st.get("refused_busy", 0)), refused_not_model=int(st.get("refused_not_model", 0)),
            sim_error=int(bool(d.get("errors"))), replay_error=int(not d.get("deterministic")),
            meter_error=int(bool((d.get("meter_error") or {}).get(s))),
            proxy_error=int(bool((d.get("proxy_error") or {}).get(s))),
            transient_api_errors=int((d.get("transient_api_errors") or {}).get(s, 0)),
            unrecovered_api_errors=int((d.get("unrecovered_api_errors") or {}).get(s, 0)),
            metered_requests=int(u.get("requests", 0)), metered_output_tokens=int(u.get("output_tokens", 0)),
            metered_input_tokens=int(u.get("input_tokens", 0)), rate_limit_retries=int(u.get("rate_limit_retries", 0)))
        return out
    out.update(start_forfeit=int(reason == "no_show" or (reason == "incomplete" and any(started.values())
                                                                and not all(started.values()))),
               first_player=0 if d.get("first") == "A" else 1, n_shots=int(f.get("n_shots", 0)))
    sc = d.get("scores") or {}
    tot = sum(int(sc.get(s, 0)) for s in seats)
    for s in seats:
        st = stats.get(s, {})
        out[s + "_points"] = int(sc.get(s, 0))
        out[s + "_stone_share"] = 0.5 if tot == 0 else round(int(sc.get(s, 0)) / tot, 6)
        out[s + "_clock_forfeit"] = int(reason == "clock" and forfeiting == s)
        out[s + "_n_decisions"] = int(st.get("n_act", 0))
        out[s + "_n_reviews"] = int(st.get("n_reviews", 0))
        out[s + "_refused_busy"] = int(st.get("refused_busy", 0))
        out[s + "_refused_not_model"] = int(st.get("refused_not_model", 0))
        out[s + "_refused_out_of_turn"] = int(st.get("refused_turn", 0))
        out[s + "_clock_left_s"] = round(clock_s - float(used.get(s, 0.0)), 1)
    return out
