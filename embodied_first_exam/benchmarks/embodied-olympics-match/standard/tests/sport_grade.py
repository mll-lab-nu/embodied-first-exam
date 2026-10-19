"""fencing's part of reward.json (the common part is core/grading.py: success, valid_trial, technical_failure,
deterministic, seed, official_config, video_rendered, <seat>_won, <seat>_transient/unrecovered_api_errors, ...):
numbers only, from final.json (and the seat's metering summary think_usage_<seat>.json, a declared artifact of the
sim). fencing-7 (the phrase-level sport): the bout's phrases instead of fencing-6's halts; the legacy reward names
of both tasks are kept where they still mean something (README.md)."""
import json
import os
from collections import Counter
from pathlib import Path

DATA = Path(os.environ.get("RCB_DATA", "/data"))
COUNTS = ("n_act", "n_observe", "n_reviews", "refused_busy", "refused_turn", "refused_not_model")


def _usage(seat):
    try:
        return json.loads((DATA / f"think_usage_{seat}.json").read_text())
    except (OSError, ValueError):
        return {}


def _bout(f):
    ph = f.get("phrases") or []
    return {"bout_over": int(f.get("how") in ("touches", "passivity", "time", "deciding_touch", "priority")),
            "extra_minute": int(bool(f.get("extra_minute"))), "phrases": len(ph),
            "doubles": sum(1 for r in ph if r.get("res") == "double"),
            "doubles_not_counted": sum(1 for r in ph if r.get("annulled")),
            "no_touch_phrases": sum(1 for r in ph if r.get("res") == "none"),
            "p_cards": int(f.get("p_cards") or 0), "fencing_time_s": float(f.get("fencing_time_s") or 0.0)}


def _intentions(f, side, prefix):
    c = Counter((r.get("intentions") or {}).get(side) for r in f.get("phrases") or [])
    names = ("lunge", "low", "line", "rline", "stop", "counter", "delay", "retreat", "draw")
    return {f"{prefix}intention_{n}": int(c.get(n, 0)) for n in names}


def evaluate(d):
    f = d.get("sport_fields") or {}
    seats = d["cfg"]["seats"]
    scores = d.get("scores") or {}
    stats = d.get("seats") or {}
    out = _bout(f)
    if len(seats) == 1:                                  # the bout against the scripted fencer (side B)
        s = seats[0]
        st, u = stats.get(s, {}), _usage(s)
        errs = d.get("errors") or []
        won = d.get("match_winner") == s and out["bout_over"] == 1
        rp = d.get("replay_scores") or {}
        pf, pa = int(scores.get(s, 0)), int(scores.get("B", 0))
        out.update(
            won=int(won), level=int(f.get("level") or 0), won_on_priority=int(won and f.get("how") == "priority"),
            sim_error=int(d.get("reason") == "technical_error" or any(e.get("where") != "replay" for e in errs)),
            replay_error=int(not d.get("deterministic") or any(e.get("where") == "replay" for e in errs)),
            meter_error=int(bool((d.get("meter_error") or {}).get(s))),
            proxy_error=int(bool((d.get("proxy_error") or {}).get(s))), finalized=int(bool(d.get("finalized"))),
            touches_for=pf, touches_against=pa, points_for=pf, points_against=pa,
            replay_touches_for=int(rp.get(s, -1)), replay_touches_against=int(rp.get("B", -1)),
            clock_forfeit=int(f.get("how") == "clock"), clock_used_s=float((d.get("clock_used_s") or {}).get(s, 0.0)),
            elapsed_s=float(d.get("elapsed_s") or 0.0), metered_requests=int(u.get("requests", 0)),
            metered_output_tokens=int(u.get("output_tokens", 0)), metered_input_tokens=int(u.get("input_tokens", 0)),
            rate_limit_retries=int(u.get("rate_limit_retries", 0)),
            transient_api_errors=int((d.get("transient_api_errors") or {}).get(s, 0)),
            unrecovered_api_errors=int((d.get("unrecovered_api_errors") or {}).get(s, 0)),
            **{k: int(st.get(k, 0)) for k in COUNTS}, **_intentions(f, s, ""), **_intentions(f, "B", "opponent_"))
        return out
    out.update(won_on_priority=int(bool(d.get("valid_trial")) and f.get("how") == "priority"),
               clock_forfeit=int(f.get("how") == "clock"), abandoned=int(f.get("how") == "abandoned"),
               first_player_A=int(f.get("first_player") == "A"), elapsed_s=float(d.get("elapsed_s") or 0.0))
    for s in seats:
        st = stats.get(s, {})
        out[s + "_points"] = int(scores.get(s, 0))
        out[s + "_clock_used_s"] = float((d.get("clock_used_s") or {}).get(s, 0.0))
        for k in COUNTS:
            out[s + "_" + k] = int(st.get(k, 0))
        out.update(_intentions(f, s, s + "_"))
    return out
