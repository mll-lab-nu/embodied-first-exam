"""Two-player 8-ball (program play duel): one rack of the single-player game's rules (eightball.py) with two agents.
Seat A is player 0, seat B player 1; FIRST_PLAYER breaks. The game is a pure function of DUEL_SEED (the rack and the
execution scatter), the breaker and the sequence of shots (deterministic replay)."""
from __future__ import annotations

import eightball as E8

SIDES = ("A", "B")
OTHER = {"A": "B", "B": "A"}
REVISION = "eightball-duel-turn-2"


class Duel:
    def __init__(self, seed: int, first: str, keep_systems: bool = False):
        assert first in SIDES
        self.seed, self.first = int(seed), first
        self.g = E8.Game(self.seed, SIDES.index(first), keep_systems=keep_systems)
        self.decisions: list[dict] = []

    @property
    def turn(self) -> str:
        return SIDES[self.g.turn]

    @property
    def done(self) -> bool:
        return self.g.done

    @property
    def winner(self):
        return None if self.g.winner is None else SIDES[self.g.winner]

    @property
    def shots(self) -> list:
        return [dict(s, player=SIDES[s["player"]]) for s in self.g.shots]

    def check(self, seat: str, dec: dict):
        return self.g.check(SIDES.index(seat), dec)

    def play(self, seat: str, dec: dict) -> dict:
        self.decisions.append(dict(dec, seat=seat))
        return self.g.shoot(SIDES.index(seat), dec)

    def replay(self, decisions: list[dict]) -> None:
        for d in decisions:
            if self.done:
                break
            self.play(d["seat"], {k: v for k, v in d.items() if k != "seat"})

    def resolve_tie(self, seat: str, clock_left_s: dict) -> None:
        """The chess clocks decide a tie at the shot limit (server_duel.py)."""
        self.g.resolve_tiebreak(SIDES.index(seat), [clock_left_s["A"], clock_left_s["B"]])

    def balls_left(self, seat: str) -> int:
        p = SIDES.index(seat)
        return len(self.g.left_in_group(p)) if self.g.group[p] else 7

    def state_sha(self) -> str:
        return self.g.state_sha()


def render_video(seed: int, first: str, decisions: list[dict], path: str) -> None:
    """Top-view video of a recorded duel (from a fresh replay)."""
    import render
    m = Duel(seed, first, keep_systems=True)
    m.replay(decisions)
    g = m.g
    by_k = {s["k"]: s for s in g.shots}
    clips = []
    for k, p, pos0, s in g.systems:
        rec = by_k[k]
        what = ("BREAK " if rec["break"] else "") + ("FOUL: " + rec["foul"] if rec["foul"] else
                                                     "potted " + (",".join(rec["potted"]) or "nothing"))
        clips.append((f"shot {k + 1}: player {SIDES[p]} | {what}", pos0, s))
    res = (f"player {m.winner} wins" if m.winner else "draw") if m.done else "not finished"
    render.render_video(clips, dict(g.pos), f"final: {res} ({g.result or ''})", path)
