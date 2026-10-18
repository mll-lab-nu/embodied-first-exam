"""badminton's part of reward.json (the common part is core/grading.py): numbers only, from final.json (and, for the
metering fields of format match-wallclock, the seat's think_usage_A.json artifact). The keys are the legacy tasks'
keys where the v0.2 core records the quantity (sports/badminton/README.md lists the differences)."""
import json
import os
from pathlib import Path


def usage(seat):
    try:
        return json.loads((Path(os.environ.get("RCB_DATA", "/data")) / f"think_usage_{seat}.json").read_text())
    except (OSError, ValueError):
        return {}


def _lag(d):
    lag = d.get("sim_lag") or {}
    sim_s, wall_s = float(lag.get("run_sim_s") or 0.0), float(lag.get("run_wall_s") or 0.0)
    return lag, sim_s, wall_s


def _max(v, scale=1.0):
    return scale * max([float(x) for x in v or []], default=0.0)


def evaluate(d):
    f, seats = d.get("sport_fields") or {}, d["cfg"]["seats"]
    if len(seats) == 1:
        return single(d, f, seats[0])
    lag, _, _ = _lag(d)
    out = dict(ready_forfeit=int(d.get("reason") == "ready_timeout" and d.get("match_winner") is not None),
               timing_invalid=0, steps=int(d.get("steps") or 0), hits=int(f.get("hits") or 0),
               slowdown=float(d.get("slowdown") or 0.0), first_server_A=int(f.get("first_server") == "A"),
               lead_steps=int(f.get("lead_steps") or 0), match_limit=int(bool(f.get("match_limit"))),
               plan_mismatch=int(sum((f.get("plan_mismatch") or {}).values())),
               sim_lag_max_s=float(lag.get("late_max_s") or 0.0))
    pts = f.get("points") or []
    for s in seats:
        st = d["seats"].get(s, {})
        out[s + "_points"] = int((f.get("score") or {}).get(s, 0))
        out[s + "_serves"] = sum(1 for p in pts if p.get("server") == s)
        out[s + "_service_faults"] = sum(1 for p in pts if p.get("server") == s and p.get("loser") == s
                                         and str(p.get("how", "")).startswith("serve_fault:"))
        for k in ("attempts", "applied", "refused", "dropped", "observations", "rejected_acts"):
            out[s + "_" + k] = int(st.get(k, 0))
        for k in ("plan_s", "act_s", "obs_age_s"):
            out[s + "_" + k + "_max"] = _max(st.get(k))
    return out


def single(d, f, a):
    st, u = d["seats"].get(a, {}), usage(a)
    lag, sim_s, wall_s = _lag(d)
    errs = d.get("errors") or []
    replay = d.get("replay_scores") or {}
    det = bool(d.get("deterministic"))
    return dict(
        won=int(bool(f.get("won"))),
        sim_error=int(d.get("reason") == "technical_error" or any(e.get("where") != "replay" for e in errs)),
        replay_error=int(not det or any(e.get("where") == "replay" for e in errs)),
        meter_error=int(bool((d.get("meter_error") or {}).get(a))),
        proxy_error=int(bool((d.get("proxy_error") or {}).get(a))), timing_invalid=0,
        points_for=int(f.get("points_for") or 0), points_against=int(f.get("points_against") or 0),
        replay_points_for=int(replay.get(a, -1)), replay_points_against=int(replay.get("opponent", -1)),
        replay_joint_targets_equal=int(det), finalized=int(bool(d.get("finalized"))), revision=12,
        our_serves=float(sum(1 for x in f.get("serves") or [] if x.get("server") == "you")),
        our_service_faults=float(sum(1 for p in f.get("points") or [] if p.get("server") == 0
                                     and p.get("winner") == "opponent"
                                     and str(p.get("how", "")).startswith("serve_fault:"))),
        timing_lag_enforced=0, match_limit=int(bool(f.get("match_limit"))),
        metered_requests=int(u.get("requests", 0)), metered_output_tokens=int(u.get("output_tokens", 0)),
        metered_input_tokens=int(u.get("input_tokens", 0)), rate_limit_retries=int(u.get("rate_limit_retries", 0)),
        transient_api_errors=int((d.get("transient_api_errors") or {}).get(a, 0)),
        unrecovered_api_errors=int((d.get("unrecovered_api_errors") or {}).get(a, 0)),
        level=float(f.get("level") or 0), slowdown=float(d.get("slowdown") or 0.0),
        our_shots=float(f.get("our_legs") or 0), good_shots=float(f.get("returns") or 0),
        n_decisions=float(st.get("applied", 0)), refused_not_model=float(st.get("refused", 0)),
        dropped_acts=float(st.get("dropped", 0)), rejected_acts=float(st.get("rejected_acts", 0)),
        n_actions=float(d.get("steps") or 0), sim_steps=float(f.get("physics_steps") or 0),
        steps=float(d.get("steps") or 0), n_reviews=float(len(d.get("reviews") or [])),
        n_observe=float(st.get("observations", 0)), n_act=float(st.get("applied", 0)),
        elapsed_s=float(d.get("elapsed_s") or 0.0), max_lag_s=0.0,
        sim_lag_late_max_s=float(lag.get("late_max_s") or 0.0), sim_lag_late_p99_s=float(lag.get("late_p99_s") or 0.0),
        sim_effective_slowdown=round(wall_s / sim_s, 4) if sim_s > 0 else 0.0, sim_run_wall_s=wall_s,
        plan_ms_max=_max(st.get("plan_s"), 1000.0), plan_lead_steps=float(f.get("plan_lead_steps") or 0),
        plan_mismatch=float(sum((f.get("plan_mismatch") or {}).values())))
