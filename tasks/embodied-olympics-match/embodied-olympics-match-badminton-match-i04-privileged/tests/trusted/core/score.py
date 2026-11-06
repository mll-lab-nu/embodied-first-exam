"""The continuous score (core 0.2.14, docs/framework_zh.md §4.3): one number per side, LARGER IS BETTER, that the
leaderboards and statistics read next to the win (final.json `continuous`, reward.json `<seat>_continuous_score` and,
for a single-side format, `continuous_score`). The sport defines it in sport.toml [score]:

  name     an id ([a-z][a-z0-9_]*), e.g. point_share, mean_per_throw, goal_difference
  text     the definition in one sentence (README, site)
  from     share   own score / the sum of every side's score in Match.scores() (0.5 when nothing was scored)
           margin  own score - the best other score in Match.scores()
           own     own score (a single format scored against a line)
           hook    Match.continuous_score() -> {side: number} (anything else, e.g. a mean per throw)
  forfeit  the value of a side that forfeited (no_show, abandoned, clock, review time) or retired: a side cannot
           keep a good number by walking away; it should be the worst value the definition allows
  range    optional [lo, hi]: the values the definition can take (core.testkit checks them)

A sport without [score] has no continuous score (the fields are absent); tools/check warns, and fails once the sport
has registered hidden official seeds (it is frozen for a season)."""
from __future__ import annotations

import math
import re

KINDS = ("share", "margin", "own", "hook")
NAME = re.compile(r"^[a-z][a-z0-9_]*$")


def declaration(decl: dict) -> dict | None:
    return decl.get("score") or None


def problems(decl: dict, has_hook: bool) -> list[str]:
    """What is wrong with sport.toml [score] (empty: fine, or not declared)."""
    d = declaration(decl)
    if d is None:
        return []
    out = []
    if not NAME.match(str(d.get("name", ""))):
        out.append("name: an id [a-z][a-z0-9_]*")
    if not str(d.get("text", "")).strip():
        out.append("text: the definition in one sentence")
    if d.get("from") not in KINDS:
        out.append(f"from: one of {', '.join(KINDS)}")
    if (d.get("from") == "hook") != has_hook:
        out.append("from = \"hook\" iff the plugin defines continuous_score()")
    if not isinstance(d.get("forfeit"), (int, float)) or isinstance(d.get("forfeit"), bool):
        out.append("forfeit: a number (the value of a side that forfeits)")
    r = d.get("range")
    if r is not None and not (isinstance(r, list) and len(r) == 2 and all(isinstance(x, (int, float)) for x in r)
                              and r[0] < r[1]):
        out.append("range: [lo, hi] with lo < hi")
    if d.get("from") in ("share", "margin") and not any(
            len(set((f.get("sides") or {s: s for s in f.get("seats", [])}).values())) > 1 or f.get("opponent")
            for f in (decl.get("formats") or {}).values()):
        out.append(f"from = \"{d.get('from')}\" needs a format with an opponent")
    return out


def compute(match, decl: dict, sides, forfeited=()) -> dict | None:
    """{"name", "from", "higher_is_better": True, "by_side": {side: float}, "forfeited": [sides]} for the player
    sides at the end of a match, None without a declaration. Raises on a non-finite value (a sport bug)."""
    d = declaration(decl)
    if d is None:
        return None
    kind = d["from"]
    if kind == "hook":
        raw = match.continuous_score()
        if raw is None:
            raise RuntimeError("[score] from = \"hook\" but Match.continuous_score() returned None")
        vals = {s: raw.get(s) for s in sides}
    else:
        sc = {str(k): float(v) for k, v in (match.scores() or {}).items()}
        vals = {}
        for s in sides:
            own = sc.get(s, 0.0)
            others = [v for k, v in sc.items() if k != s]
            if kind == "share":
                tot = own + sum(others)
                vals[s] = own / tot if tot > 0 else 0.5
            elif kind == "margin":
                vals[s] = own - max(others) if others else own
            else:
                vals[s] = own
    by = {}
    for s in sides:
        v = float(d["forfeit"]) if s in forfeited else vals.get(s)
        if v is None or isinstance(v, bool) or not math.isfinite(float(v)):
            raise RuntimeError(f"continuous score of side {s}: {v!r} is not a finite number")
        by[s] = round(float(v), 6)
    return {"name": d["name"], "from": kind, "higher_is_better": True, "by_side": by,
            "forfeited": [s for s in sides if s in forfeited]}
