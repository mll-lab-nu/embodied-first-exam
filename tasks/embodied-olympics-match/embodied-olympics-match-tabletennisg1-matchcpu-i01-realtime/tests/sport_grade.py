"""tabletennis_g1's part of reward.json (the common part is core/grading.py): numbers only, from final.json alone
(the verifier has no simulator)."""


def evaluate(d):
    f = d.get("sport_fields") or {}
    points = f.get("points") or []
    score = f.get("score") or {}
    robots = f.get("robots") or {}
    out = {"points_played": sum(not p.get("let") for p in points), "lets": sum(bool(p.get("let")) for p in points),
           "hits": int(f.get("hits") or 0),
           "service_faults": sum(str(s.get("verdict")) == "fault" for s in f.get("serves") or []),
           "short_services": sum(str(s.get("code")) == "short" for s in f.get("serves") or []),
           "wide_services": sum(str(s.get("code")) == "wide" for s in f.get("serves") or [])}
    for side, n in score.items():
        out[f"{side}_points"] = int(n)
    for side, r in robots.items():
        out[f"{side}_falls"] = int(r.get("falls") or 0)
        out[f"{side}_reflexes"] = int(r.get("reflexes") or 0)
        out[f"{side}_selfcol_events"] = int(r.get("selfcol_events") or 0)
    if "level" in f:
        out["opponent_level"] = int(f["level"])
    return out
