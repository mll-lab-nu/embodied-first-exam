"""The no-draw decision chain (docs/framework_zh.md §5): a forfeit (a core decision: review or clock time, abandonment,
or a side that never started, "no_show"; sides that retired before it rank last, the last to retire first), then the
sport's tiebreaks in order (rulebook result -> rulebook tiebreak -> capped extra play -> last resort; the last one must
decide). A match with more than two sides is decided by the sport's classification (Match.ranking, best first). A solo
match (single format without an opponent: tiebreaks() == []) has no winner; its result is the score against the
success line. A match that did not finish has no winner."""
from __future__ import annotations

from dataclasses import dataclass, field

from .sport import FINISHED


@dataclass
class Outcome:
    winner: str | None
    decided_by: str
    scores: dict
    ranking: list = field(default_factory=list)
    solo: bool = False


def decide(match, forfeit_seat: str | None = None, why: str | None = None, sides=("A", "B"),
           side_of=lambda s: s, retired=()) -> Outcome:
    scores = match.scores()
    sides = list(sides)
    rules = match.tiebreaks()
    solo = len(sides) == 1 and not rules
    if forfeit_seat is not None:
        lost = side_of(forfeit_seat)
        others = [s for s in sides if s != lost and s not in retired]
        if len(others) == 1:
            return Outcome(others[0], f"forfeit:{why}", scores, others + [lost] + list(reversed(retired)))
        if not others and len(sides) == 1:       # a single player who forfeits loses (to the line or the opponent)
            return Outcome(None, f"forfeit:{why}", scores, [], solo)
    if match.phase().state != FINISHED:
        return Outcome(None, "unfinished", scores, [], solo)
    if solo:
        return Outcome(None, "score", scores, list(sides), True)
    if len(sides) > 2:
        ranking = list(match.ranking() or [])
        if sorted(ranking) != sorted(sides):
            raise RuntimeError("a match of more than two sides must rank every side (Match.ranking)")
        return Outcome(ranking[0], "ranking", scores, ranking)
    for name, rule in rules:
        w = rule(match)
        if w is not None:
            rest = [s for s in sides if s != w]
            return Outcome(w, name, scores, [w] + rest)
    raise RuntimeError("a finished match must be decided by its last tiebreak (no draws)")
