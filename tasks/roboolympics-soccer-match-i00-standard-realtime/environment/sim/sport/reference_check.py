"""The reference check of tools/check stage 5 (docs/screening/README.md "Reference check", sport.toml [reference]):
one match of the reference against the scripted team at a level.

  perception "truth"   the reference's decisions with the true state: the scripted coach at the "reference" level
                       (soccer.Coach("reference"), soccer-2v2-9: both robots go for the ball at the reference's speed
                       and kick with the in-walk kick, the strongest play found in the screening) plays team A inside
                       the world against level `level`
  perception "camera"  the sport's [players] reference (builtin_players.Reference) unchanged, through core.local.play:
                       it sees only the head-camera images, its own state and the referee

Returns {"won", "scores": [ours, theirs] (regulation goals, the shoot-out not counted), "report": {name: [count, of]}}
with the playability counters of team A: swing / push kicks that were not called off, kicks that ended without a fall.
"""
from __future__ import annotations

import os

HERE = os.path.dirname(os.path.abspath(__file__))


def _report(stats: dict, team: str = "A") -> dict:
    rs = [v for k, v in stats.items() if k.startswith(team)]
    kicks = sum(int(s.get("kicks", 0)) for s in rs)
    cancelled = sum(int(s.get("kicks_cancelled", 0)) for s in rs)
    falls = sum(int(s.get("kick_falls", 0)) for s in rs)
    return {"kicks not called off": [kicks - cancelled, kicks], "kicks without a fall": [kicks - falls, kicks]}


def _truth(level: int, seed: int) -> dict:
    import soccer as S
    w = S.World(seed=int(seed), first_kickoff="A", scripted={"A": "reference", "B": int(level)})
    while not w.done:
        if w.stopped:
            w.resume()
            continue
        w.advance()
    return {"won": w.winner == "A", "scores": [w.score["A"], w.score["B"]], "report": _report(w.stats)}


def _camera(fmt: str, level: int, seed: int) -> dict:
    from core import local
    from core import spec as spec_mod
    from core.episode import load_plugin
    from core.sport import MatchConfig
    plugin = os.path.join(HERE, "plugin.py")
    sport = load_plugin(plugin)
    f = spec_mod.load(plugin)["formats"][fmt]
    cfg = MatchConfig(sport=sport.name, format=fmt, seats=tuple(f["seats"]), seed=int(seed), first="A",
                      level=int(level), action_level="low", sides=f.get("sides"))
    players = local.make_players(sport, cfg, {s: "reference" for s in cfg.seats}, plugin=plugin)
    r = local.play(sport, cfg, players, plugin=plugin)
    sc = r["scores"]
    ours = sc.get("A", 0)
    theirs = max([v for k, v in sc.items() if k != "A"] or [0])
    stats = (r.get("final_fields") or {}).get("summary", {}).get("stats", {})
    return {"won": r["winner"] == "A", "scores": [ours, theirs], "report": _report(stats)}


def reference_match(format: str = "match", level: int | None = 2, seed: int = 1, perception: str = "truth") -> dict:
    level = 2 if level is None else int(level)
    if perception == "truth":
        return _truth(level, seed)
    if perception == "camera":
        return _camera(format, level, seed)
    raise ValueError(f"perception must be truth or camera, not {perception!r}")
