"""Table tennis' part of reward.json (the common part is core/grading.py, which runs first; these keys are added after
it): numbers only, from final.json (and for the legacy metering and no-code fields of the match tasks the sim's
artifacts think_usage_A.json, think_calls_A.jsonl, direct_gate[_<seat>].jsonl in RCB_DATA). The keys are the legacy
tasks' keys (scripts/olympiad/tabletennis/{match,duel}/tests/grade.py); README lists what changed and why.
official_config replaces the core's value: the legacy rule is per format (match: the level's own seeds and the
program / direct slowdowns; duel: the slowdown only), which [official] cannot express. With a hidden official seed
(core 0.2.14, the sport's registered set) the core's value stands and only the slowdown rule can lower it."""
import importlib.util
import json
import os
from pathlib import Path

DATA = Path(os.environ.get("RCB_DATA", "/data"))
OFFICIAL_SEEDS = {1: [101, 111, 121], 2: [202, 212, 222], 3: [303, 313, 323], 4: [404, 414, 424]}
OFFICIAL_SLOWDOWNS = {"match": {"program": [1, 2, 5, 10, 20], "direct": [20, 50, 100]},
                      "duel": {"program": [10, 20], "direct": [20, 50, 100]}}
LADDER_KEYS = ("points", "balls", "points_touched", "points_active", "points_over_net", "points_landed_in",
               "points_returned", "points_won", "points_won_expedite", "points_won_rally", "balls_touched",
               "balls_active", "balls_over_net", "balls_landed_in", "balls_returned")
EXPEDITE = "(expedite rule)"


def _json(name):
    try:
        return json.loads((DATA / name).read_text())
    except (OSError, ValueError):
        return {}


def _gate_blocks(name):
    p = DATA / name
    return sum('"ev": "blocked"' in ln for ln in p.read_text().splitlines()) if p.exists() else 0


def _audit(seat):
    """(tool calls, violations) of the players' no-code audit (tests/nocode_audit.py, the same one the core runs)."""
    p = Path(__file__).resolve().parent / "nocode_audit.py"
    if not p.exists():
        return 0, []
    spec = importlib.util.spec_from_file_location("tt_nocode_audit", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.nocode_audit(DATA / f"think_calls_{seat}.jsonl")


def hidden_rule(d, fmt, out):
    """A hidden official seed (core 0.2.14: final.json seed_proof; the seed itself is never written): the core's rule
    decides (the seed must be in the format x level cell of the registered set, tests/grade.py hidden_index), so its
    official_config stands; this sport only adds its per-format slowdown rule, which can only lower it."""
    if not d.get("seed_proof"):
        return out
    try:
        ok = float(d.get("slowdown")) in OFFICIAL_SLOWDOWNS[fmt].get(d.get("play", "program"), [])
    except (TypeError, ValueError):
        ok = False
    if ok:
        out.pop("official_config", None)
    else:
        out["official_config"] = 0
    return out


def official(d, fmt):
    try:
        seed, slow = int(d.get("seed")), float(d.get("slowdown"))
    except (TypeError, ValueError):
        return 0
    ok = slow in OFFICIAL_SLOWDOWNS[fmt].get(d.get("play", "program"), [])
    if fmt == "match":
        ok &= seed in OFFICIAL_SEEDS.get(int((d.get("sport_fields") or {}).get("level") or 0), [])
    return int(ok)


def lag(d):
    s = d.get("sim_lag") or {}
    run_sim = float(s.get("run_sim_s") or 0.0)
    return s, (float(s.get("run_wall_s") or 0.0) / run_sim if run_sim > 0 else 0.0)


def evaluate(d):
    f, seats = d.get("sport_fields") or {}, d["cfg"]["seats"]
    if len(seats) == 1:
        return hidden_rule(d, "match", match(d, f, seats[0]))
    return hidden_rule(d, "duel", duel(d, f, seats))


def duel(d, f, seats):
    s_lag, _ = lag(d)
    out = dict(ready_forfeit=int(d.get("reason") == "ready_timeout" and d.get("match_winner") is not None),
               timing_invalid=0, steps=int(d["steps"]), hits=int(f.get("hits", 0)), slowdown=float(d["slowdown"]),
               official_config=official(d, "duel"), sim_lag_max_s=float(s_lag.get("late_max_s") or 0.0),
               net_touches=sum(p.get("net_touches", 0) for p in f.get("points", [])),
               lets=sum(bool(p.get("let")) for p in f.get("points", [])))
    serves = [x for x in (f.get("serves") or []) if isinstance(x, dict)]
    for s in seats:
        st = d["seats"].get(s, {})
        out[s + "_points"] = int((f.get("score") or {}).get(s, 0))
        mine = [x for x in serves if x.get("server") == s and x.get("why") != "undue delay"]   # tossed services
        out[s + "_serves"] = len(mine)
        out[s + "_serves_good"] = sum(x.get("verdict") == "good" for x in mine)
        out[s + "_serve_faults"] = sum(x.get("verdict") in ("fault", "obstruction") for x in mine)
        out[s + "_serve_points_won"] = sum(p.get("server") == s and p.get("winner") == s for p in f.get("points", []))
        out[s + "_delay_faults"] = int((f.get("delay_faults") or {}).get(s, 0))
        out[s + "_disqualified"] = int(f.get("disqualified") == s)
        out[s + "_points_expedite"] = sum(p.get("winner") == s and EXPEDITE in str(p.get("how", ""))
                                          for p in f.get("points", []))
        out[s + "_rejected_acts"] = int((f.get("rejected_acts") or {}).get(s, 0))
        if d.get("play") == "direct":
            out[s + "_gate_blocks"] = _gate_blocks(f"direct_gate_{s}.jsonl")
        for k in ("attempts", "applied", "refused", "dropped", "observations"):
            out[s + "_" + k] = int(st.get(k, 0))
        for k in ("plan_s", "act_s", "obs_age_s"):
            out[s + "_" + k + "_max"] = float(max(st.get(k) or [], default=0))
    return out


def match(d, f, a):
    st, u = d["seats"].get(a, {}), _json(f"think_usage_{a}.json")
    errs = d.get("errors") or []
    direct = d.get("play") == "direct"
    model = (d.get("player_modes") or {}).get(a) == "model"
    n_tools, bad = _audit(a) if direct else (0, [])
    forfeit = direct and model and bool(bad)
    s_lag, eff = lag(d)
    rep = d.get("replay_scores") or {}
    lad = f.get("ladder") if isinstance(f.get("ladder"), dict) else {}
    out = dict(
        won=int(d.get("match_winner") == a and not forfeit),
        sim_error=int(d.get("reason") == "technical_error" or any(e.get("where") != "replay" for e in errs)),
        replay_error=int(not d.get("deterministic") or any(e.get("where") == "replay" for e in errs)),
        meter_error=int(bool((d.get("meter_error") or {}).get(a))),
        proxy_error=int(bool((d.get("proxy_error") or {}).get(a))), timing_invalid=0,
        points_for=int(f.get("points_for", 0)), points_against=int(f.get("points_against", 0)),
        replay_points_for=int(rep.get(a, -1)), replay_points_against=int(rep.get("opponent", -1)),
        replay_joint_targets_equal=int(bool(d.get("deterministic"))), finalized=int(bool(d.get("finalized"))),
        revision=8, timing_lag_enforced=0, rejected_acts=int(f.get("rejected_acts", 0)),
        nocode_tool_calls=int(n_tools), nocode_violations=len(bad), nocode_forfeit=int(forfeit),
        gate_blocks=_gate_blocks("direct_gate.jsonl") + _gate_blocks(f"direct_gate_{a}.jsonl"),
        metered_requests=int(u.get("requests", 0)), metered_output_tokens=int(u.get("output_tokens", 0)),
        metered_input_tokens=int(u.get("input_tokens", 0)), rate_limit_retries=int(u.get("rate_limit_retries", 0)),
        transient_api_errors=int((d.get("transient_api_errors") or {}).get(a, 0)),
        unrecovered_api_errors=int((d.get("unrecovered_api_errors") or {}).get(a, 0)),
        level=float(f.get("level") or 0), slowdown=float(d.get("slowdown") or 0),
        our_shots=float(f.get("our_shots", 0)), balls_to_you=float(f.get("our_legs", 0)),
        good_shots=float(f.get("returns", 0)), n_decisions=float(st.get("applied", 0)),
        refused_not_model=float(st.get("refused", 0)), dropped_acts=float(st.get("dropped", 0)),
        n_actions=float(d.get("steps") or 0), sim_steps=float(f.get("physics_steps", 0)),
        steps=float(d.get("steps") or 0), n_reviews=float(len(d.get("reviews") or [])),
        n_calls=float(st.get("attempts", 0) + st.get("observations", 0)), n_observe=float(st.get("observations", 0)),
        n_act=float(st.get("attempts", 0)), elapsed_s=float(d.get("elapsed_s") or 0), max_lag_s=0.0,
        official_config=official(d, "match"), sim_lag_late_max_s=float(s_lag.get("late_max_s") or 0),
        sim_lag_late_p99_s=float(s_lag.get("late_p99_s") or 0), sim_effective_slowdown=float(eff),
        sim_run_wall_s=float(s_lag.get("run_wall_s") or 0))
    for k in LADDER_KEYS:
        v = lad.get(k)
        out["ladder_" + k] = int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else -1
    ours = [x for x in (f.get("our_serves") or []) if isinstance(x, dict)]
    out.update(serves=len(ours), serves_good=sum(x.get("verdict") == "good" for x in ours),
               serve_faults=sum(x.get("verdict") == "fault" for x in ours),
               serve_points_won=sum(p.get("server") == "you" and p.get("winner") == "you" for p in f.get("points", [])),
               delay_faults=int(f.get("delay_faults") or 0), disqualified=int(bool(f.get("disqualified"))))
    return out
