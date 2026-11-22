"""Projections of a verdict (eo-verdict/1). The verdict is the authority; reward.json, the leaderboard rows and the
legacy verdict shape are computed from it and nothing else (plus, for reward.json, a few fields of the world report
that the legacy reward always carried: seed, video, play and action layer).

  reward(verdict, world, success_line)   reward.json: numbers only, the keys of the core 0.3.0 verifier
  leaderboard_rows(verdict)               one row per entrant side, what a Competition aggregates
  legacy_verdict(verdict)                 the core 0.3.0 verdict.json shape (status, failure, sides) for the tools
                                          that still read it (tools/olympiad/matchrun.py, run_round.py); written
                                          as verdict_v0.json

Legacy failure classes: platform, plugin and undetermined -> infrastructure; external -> external_provider; agent ->
agent; a valid match with no deciding agent fault -> none.
"""
from __future__ import annotations

LEGACY_CLASS = {"platform": "infrastructure", "plugin": "infrastructure", "undetermined": "infrastructure",
                "external": "external_provider", "agent": "agent"}
DECIDING = ("no_show", "resigned", "clock", "nocode_violation")


def _seats(verdict: dict) -> dict:
    """seat -> side, from the sides' entries or the faults (legacy verdicts name seats in faults)."""
    out = {}
    for side, x in verdict["sides"].items():
        for seat in (x.get("entries") or {}):
            out[seat] = side
    return out


def _void_faults(verdict: dict) -> list:
    return [f for f in verdict["faults"] if f["effect"] in ("void_match", "void_side")]


def legacy_class(verdict: dict) -> tuple[str, str | None, list]:
    """(class, reason, evidence) in the core 0.3.0 vocabulary."""
    voids = _void_faults(verdict)
    if not verdict["valid"] and voids:
        f = voids[0]
        return LEGACY_CLASS[f["class"]], f["code"], [f"{x['class']}/{x['code']}: {x['note']}"[:200] for x in voids]
    deciding = [f for f in verdict["faults"] if f["class"] == "agent" and f["code"] in DECIDING]
    if verdict["valid"] and deciding:
        f = deciding[0]
        return "agent", f["code"], [f"seat {x.get('seat')}" if x.get("seat") else x["note"] for x in deciding]
    return "none", None, []


def legacy_verdict(verdict: dict, taskspec_sha256: str | None = None, overrides: dict | None = None) -> dict:
    cls, reason, evidence = legacy_class(verdict)
    out = {"status": "decided" if verdict["valid"] else "void", "valid_trial": bool(verdict["valid"]),
           "failure": {"class": cls, "reason": reason, "evidence": evidence[:20]},
           "taskspec_sha256": taskspec_sha256, "overrides": overrides or {},
           "eo_verdict": {"run_id": verdict["run_id"], "termination": verdict["termination"],
                          "faults": [f"{f['class']}/{f['code']}/{f['effect']}" for f in verdict["faults"]]}}
    entrants = [s for s, x in verdict["sides"].items() if x["kind"] == "entrant"]
    if len(verdict["sides"]) > 2:
        sides = {}
        for s in entrants:
            x = verdict["sides"][s]
            mine = [f for f in verdict["faults"] if f.get("side") == s]
            if not x["valid"]:
                f = next((g for g in _void_faults(verdict) if g.get("side") in (s, None)), None)
                st, fc = "void", {"class": LEGACY_CLASS[f["class"]] if f else "infrastructure",
                                  "reason": f["code"] if f else None}
                res = "void"
            else:
                ag = next((g for g in mine if g["class"] == "agent"), None)
                st, fc = "decided", ({"class": "agent", "reason": ag["code"]} if ag else {"class": "none",
                                                                                           "reason": None})
                res = {"retired": "forfeit", "dnf": "dnf", "disqualified": "forfeit"}.get(x["status"], "ranked")
            sides[s] = {"result": res, "place": x["rank"], "status": st, "failure": fc}
        out["sides"] = sides
    return out


def reward(verdict: dict, world: dict | None = None, success_line: dict | None = None,
           seat_side: dict | None = None) -> dict:
    """reward.json (numbers only) as a projection of the verdict. `world`: the legacy final.json (seed, video, play,
    action layer); `success_line`: the solo format's line ({"score_at_least": n} or {"score_at_most": n});
    `seat_side`: seat -> side (the world report's)."""
    d = world or {}
    diag = verdict.get("diagnostics") or {}
    seat_side = seat_side or (d.get("sides") or {}) or _seats(verdict)
    seats = list(seat_side)
    valid = bool(verdict["valid"])
    sides = verdict["sides"]
    entrants = [s for s, x in sides.items() if x["kind"] == "entrant"]
    solo = len(sides) == 1
    single = len(entrants) == 1
    end = (diag.get("world_end") or {}).get("reason")
    out = {"success": 0, "valid_trial": int(valid), "technical_failure": int(not valid), "grader_error": 0,
           "missing_log": int(world is None), "deterministic": int(verdict["checks"]["replay"] == "pass"),
           "match_over": int(end == "match_over"), "seed": int(d.get("seed") or 0),
           "official_config": int(((diag.get("legacy") or {}).get("official_config")) or 0),
           "video_rendered": int(bool(d.get("video"))), "direct_play": int(d.get("play") == "direct"),
           "lowlevel_actions": int(d.get("action_level") in ("low", "joint")), "solo": int(solo),
           "no_show": int(verdict["termination"] == "no_show"), "abandoned": int(end == "abandoned")}
    hidx = (diag.get("legacy") or {}).get("hidden_seed_index")
    out.update(hidden_seed=int(hidx is not None), hidden_seed_index=hidx if hidx is not None else -1)
    if solo:
        x = sides[entrants[0]] if entrants else {}
        score = x.get("score")
        out["success"] = int(valid and verdict["termination"] == "completed" and x.get("status") == "finished"
                             and score is not None and _line_ok(score, success_line or {}))
    elif single:
        out["success"] = int(valid and verdict["winner"] == entrants[0])
    else:                                  # a valid match was played: some entrant side finished it
        out["success"] = int(valid and any(sides[x]["status"] == "finished" for x in entrants))
    ranks = [x.get("rank") for x in sides.values() if x.get("valid")]
    out["draw"] = int(valid and not solo and verdict["winner"] is None and len(ranks) == 2
                      and ranks == [1, 1])   # core 0.5.2: a draw the fixture allows (both sides first)
    cname = (diag.get("scoring") or {}).get("continuous")
    cont = {s: x["metrics"][cname] for s, x in sides.items() if cname and isinstance((x.get("metrics") or {}).get(
        cname), (int, float))}
    api = diag.get("model_api") or {}
    for seat in seats:
        side = seat_side.get(seat, seat)
        x = sides.get(side) or {}
        out[seat + "_won"] = int(valid and x.get("valid", False) and verdict["winner"] == side)
        out[seat + "_no_show"] = int(x.get("exit") == "no_show" and any(
            f.get("seat") == seat and f["code"] == "no_show" for f in verdict["faults"]))
        if len(sides) > 2:
            out[seat + "_place"] = int(x.get("rank") or 0) if x.get("valid") else 0
        if side in cont:
            out[seat + "_continuous_score"] = float(cont[side])
        u = (api.get(seat) or {}).get("errors") or {}         # counts only (the model access rule: time lost)
        out[seat + "_transient_api_errors"] = int(u.get("transient") or 0)
        out[seat + "_unrecovered_api_errors"] = int(u.get("unrecovered") or 0)
        out[seat + "_api_retries"] = int(((api.get(seat) or {}).get("errors_by_cause") or {}).get(
            "platform/account_rate_limit_retry", 0))
        out[seat + "_api_wait_s"] = float(((diag.get("model_access") or {}).get(seat) or {}).get("lost_s") or 0.0)
    if single and seats and (seats[0] + "_continuous_score") in out:
        out["continuous_score"] = out[seats[0] + "_continuous_score"]
    for k, v in (diag.get("sport_fields") or {}).items():
        if isinstance(v, (int, float)) and not isinstance(v, bool) and k not in out:
            out[k] = v
        elif isinstance(v, bool) and k not in out:
            out[k] = int(v)
    # validity numbers a sport hook copies from the world report are the judge's to give (the world's are snapshots)
    unions = [((api.get(s) or {}).get("errors") or {}) for s in seats]
    rules = diag.get("fault_rules") or []
    out.update(proxy_error=int(any(r == "R-API-OUTAGE" and f["effect"] != "recorded"
                                   for f, r in zip(verdict["faults"], rules))),
               meter_error=int(any(f["code"] == "metering" for f in verdict["faults"])),
               transient_api_errors=sum(int(u.get("transient") or 0) for u in unions),
               unrecovered_api_errors=sum(int(u.get("unrecovered") or 0) for u in unions))
    voids = _void_faults(verdict)
    classes = {f["class"] for f in voids}
    cls, _reason, _ev = legacy_class(verdict)
    out.update(failure_agent=int(cls == "agent"), failure_infrastructure=int(cls == "infrastructure"),
               failure_external=int(cls == "external_provider"), void=int(not valid),
               failure_platform=int("platform" in classes), failure_plugin=int("plugin" in classes),
               failure_undetermined=int("undetermined" in classes),
               t0_barrier=int((d.get("t0") or {}).get("source") == "barrier"),
               official_eligible=int(bool(verdict["official"]["eligible"])))
    if len(sides) > 2:
        for seat in seats:
            side = seat_side.get(seat, seat)
            mine = [f for f in verdict["faults"] if f.get("side") == side]
            out[seat + "_failure_agent"] = int(any(f["class"] == "agent" for f in mine))
            out[seat + "_failure_infrastructure"] = int(any(f["class"] in ("platform", "plugin", "undetermined")
                                                            for f in mine))
            out[seat + "_side_void"] = int(not (sides.get(side) or {}).get("valid", False))
    assert all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in out.values()), \
        [k for k, v in out.items() if not isinstance(v, (int, float)) or isinstance(v, bool)]
    return out


def _line_ok(score, line: dict) -> bool:
    if "score_at_least" in line:
        return score >= line["score_at_least"]
    if "score_at_most" in line:
        return score <= line["score_at_most"]
    return False


def leaderboard_rows(verdict: dict) -> list:
    """One row per entrant side: what a Competition aggregates (only valid sides count)."""
    rows = []
    for side, x in sorted(verdict["sides"].items()):
        if x["kind"] != "entrant":
            continue
        rows.append({"fixture_id": verdict["fixture_id"], "run_id": verdict["run_id"],
                     "task_release": verdict["task_release"], "side": side, "entries": x.get("entries") or {},
                     "counts": bool(x["valid"]), "official": bool(verdict["official"]["eligible"] and x["valid"]),
                     "status": x["status"], "exit": x["exit"], "rank": x["rank"], "score": x["score"],
                     "won": bool(x["valid"] and verdict["winner"] == side), "termination": verdict["termination"],
                     "faults": sorted({f"{f['class']}/{f['code']}" for f in verdict["faults"]
                                       if f.get("side") in (side, None)})})
    return rows
