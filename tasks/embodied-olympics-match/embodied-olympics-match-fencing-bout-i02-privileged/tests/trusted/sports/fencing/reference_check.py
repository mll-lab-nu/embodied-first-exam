"""The reference check of tools/check stage 5 (docs/screening/README.md "Reference check", sport.toml [reference]):
one bout of the reference (builtin_players.Reference) against the scripted fencer at a level, played as the step-4
screening on the sport plays it (docs/screening/fencing/phrase/game/step4_sport.py): the player answers every phrase
from `game spec` and its state, the phrase is fenced at once.

  perception    "truth" and "camera" are the same player on the same view: a seat's observation of a phrase is the
                referee's record of it (the intentions, the delays, the result: `state` phrases), and the reference
                reads nothing else; the images (a half-way and an end snapshot of the last phrase) carry no
                information the record does not, so none are drawn

Returns {"won", "scores": [ours, theirs], "perception", "report": {"touches": [ours, both], "phrases_won": [phrases
with our touch only, phrases]}}.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def reference_match(format: str = "bout", level: int | None = 1, seed: int = 1, perception: str = "truth") -> dict:
    if perception not in ("truth", "camera"):
        raise ValueError(f"perception must be truth or camera, not {perception!r}")
    if format != "bout":
        raise ValueError("the opponent calibration is for format bout (the scripted fencer)")
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import builtin_players as BP
    import plugin as PL
    from core.sport import MatchConfig

    cfg = MatchConfig(sport="fencing", format="bout", seats=("A",), seed=int(seed),
                      level=1 if level is None else int(level), action_level="low")
    m = PL.SPORT.build(cfg)
    ref = BP.Reference({"seat": "A", "action_level": "low", **PL.SPORT.spec(cfg, "A", m)}, "A", int(seed))
    while not m.bout.over:
        m.apply("A", ref.act({"state": {"seat": "A", **m.observe("A")}}))
    ours, theirs = m.bout.score["A"], m.bout.score[m.other("A")]
    won = sum(m._phrase_view(r, "A")["result"] == "you" for r in m.bout.log)
    return {"won": m.bout.winner == "A", "scores": [ours, theirs], "perception": perception,
            "report": {"touches": [ours, ours + theirs], "phrases_won": [won, len(m.bout.log)]}}
