"""soccer_ssl's part of reward.json (the common part is core/grading.py): numbers only, from final.json alone (the
verifier has no simulator). Per seat: its team's goals for and against (regular time), the goal margin, fouls and
cards; per match: the shoot-out goals and how it ended."""

TEAM_OF = {"A": "blue", "B": "yellow"}
HOW = {"REGULAR_TIME": 0, "EARLY_TERMINATION": 1, "SHOOTOUT": 2}


def evaluate(d):
    f = d.get("sport_fields") or {}
    score = f.get("score") or {"blue": 0, "yellow": 0}
    fouls = f.get("fouls") or {}
    cards = f.get("cards") or {}
    so = f.get("shootout") or {}
    out = {
        "goals_blue": int(score.get("blue", 0)),
        "goals_yellow": int(score.get("yellow", 0)),
        "end_how": HOW.get(f.get("end_how"), -1),
        "shootout": int(bool(so)),
        "stoppages": int(f.get("stops") or 0),
    }
    for seat in (d.get("cfg") or {}).get("seats", []):
        team = TEAM_OF.get(seat[:1])
        if team is None:
            continue
        opp = "yellow" if team == "blue" else "blue"
        out[f"{seat}_goals_for"] = int(score.get(team, 0))
        out[f"{seat}_goals_against"] = int(score.get(opp, 0))
        out[f"{seat}_goal_margin"] = int(score.get(team, 0)) - int(score.get(opp, 0))
        out[f"{seat}_fouls"] = int(fouls.get(team, 0))
        out[f"{seat}_yellow_cards"] = int((cards.get(team) or {}).get("yellow", 0))
        out[f"{seat}_red_cards"] = int((cards.get(team) or {}).get("red", 0))
        if so:
            out[f"{seat}_shootout_goals"] = int(so.get(team, 0))
    opp = f.get("opponent") or {}
    if opp:
        out["opponent_refused"] = int(opp.get("refused", 0))
        out["level"] = int(f.get("level") or 0)
    return out
