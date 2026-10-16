"""darts' part of reward.json (the common part is core/grading.py): numbers only, from final.json (and, for the
legacy metering fields of format 501, the seat's think_usage_A.json artifact). The keys are the legacy tasks' keys,
plus the sport's continuous score (darts-7): the average points per dart (`points_per_dart`, a bust visit scores 0)."""
import json
import os
from pathlib import Path

COUNTS = ("n_act", "n_observe", "n_reviews", "refused_busy", "refused_turn", "refused_not_model")


def usage(seat):
    try:
        return json.loads((Path(os.environ.get("RCB_DATA", "/data")) / f"think_usage_{seat}.json").read_text())
    except (OSError, ValueError):
        return {}


def evaluate(d):
    f, seats = d.get("sport_fields") or {}, d["cfg"]["seats"]
    if len(seats) == 1:
        return single(d, f, seats[0])
    fo = f.get("forfeit") or {}
    out = dict(clock_forfeit=int(fo.get("why") == "clock"), abandoned=int(fo.get("why") == "abandoned"),
               first_player_A=int(d.get("first") == "A"), darts=len(f.get("log") or []),
               elapsed_s=float(d.get("elapsed_s") or 0.0))
    for s in seats:
        st = d["seats"].get(s, {})
        out[s + "_legs"] = int((f.get("legs") or {}).get(s, 0))
        out[s + "_remaining"] = int((f.get("remaining") or {}).get(s, 0))
        out[s + "_clock_used_s"] = float((d.get("clock_used_s") or {}).get(s, 0.0))
        out[s + "_clock_forfeit"] = int(fo.get("seat") == s and fo.get("why") == "clock")
        for k in ("darts", "busts", "trebles", "checkouts") + COUNTS:
            out[s + "_" + k] = int(st.get(k, 0))
        out[s + "_three_dart_avg"] = float(st.get("three_dart_avg", 0.0))
        out[s + "_points_per_dart"] = float((f.get("points_per_dart") or {}).get(s, 0.0))
    return out


def single(d, f, a):
    st, sy, so = d["seats"].get(a, {}), f.get("stats_you") or {}, f.get("stats_opponent") or {}
    legs, u = f.get("legs") or [0, 0], usage(a)
    errs = d.get("errors") or []
    replay_error = int(not d.get("deterministic") or any(e.get("where") == "replay" for e in errs))
    return dict(
        won=int(bool(f.get("won"))), sim_error=int(d.get("reason") == "technical_error" or any(
            e.get("where") != "replay" for e in errs)), replay_error=replay_error,
        meter_error=int(bool((d.get("meter_error") or {}).get(a))), proxy_error=int(bool((d.get("proxy_error") or {})
                                                                                         .get(a))),
        finalized=int(bool(d.get("finalized"))), level=int(f.get("level") or 0),
        clock_forfeit=int(bool(f.get("clock_forfeit"))), started=int(bool((d.get("joined") or {}).get(a))),
        you_legs=int(legs[0]), opponent_legs=int(legs[1]), you_remaining=int(f.get("you_remaining") or 0),
        opponent_remaining=int(f.get("opponent_remaining") or 0), darts=int(sy.get("darts", 0)),
        visits=int(sy.get("visits", 0)), three_dart_avg=float(sy.get("three_dart_avg", 0.0)),
        points_per_dart=float(sy.get("points_per_dart", 0.0)),
        opponent_points_per_dart=float(so.get("points_per_dart", 0.0)),
        busts=int(sy.get("busts", 0)), trebles=int(sy.get("trebles", 0)), opponent_visits=int(so.get("visits", 0)),
        opponent_three_dart_avg=float(so.get("three_dart_avg", 0.0)),
        clock_used_s=float((d.get("clock_used_s") or {}).get(a, 0.0)), n_reviews=int(st.get("n_reviews", 0)),
        n_act=int(st.get("n_act", 0)), n_observe=int(st.get("n_observe", 0)),
        refused_busy=int(st.get("refused_busy", 0)), refused_not_model=int(st.get("refused_not_model", 0)),
        elapsed_s=float(d.get("elapsed_s") or 0.0), metered_requests=int(u.get("requests", 0)),
        metered_output_tokens=int(u.get("output_tokens", 0)), metered_input_tokens=int(u.get("input_tokens", 0)),
        rate_limit_retries=int(u.get("rate_limit_retries", 0)),
        transient_api_errors=int((d.get("transient_api_errors") or {}).get(a, 0)),
        unrecovered_api_errors=int((d.get("unrecovered_api_errors") or {}).get(a, 0)))
