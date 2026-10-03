"""Basketball shootout, two players (seats A and B): each on its own identical court (bball.Game with the same seed: the
same five spots and headings, the same release scatter for the n-th shot of either player).

Format: five rounds, one per spot (spot 1 .. spot 5); in each round one player takes its 2 shots from the spot, then
the other; FIRST shoots first in rounds 1, 3 and 5, the other player in rounds 2 and 4. Most makes wins. A tie goes to
extra shots: pairs of one shot each from spot 1, 2, ... 5, 1, ... (FIRST first), continuing until one pair differs,
which decides. After EXTRA_PAIRS tied pairs (a safety cap) the player with more chess-clock time left wins (the
last-resort rule; both clocks are recorded with every shot and replayed exactly); never a draw.
"""
from __future__ import annotations

import hashlib
import json
import sys

import bball

SEATS = ("A", "B")
OTHER = {"A": "B", "B": "A"}
N_SPOTS = len(bball.SPOT_NOMINAL)
EXTRA_PAIRS = 30                     # safety cap on tied extra pairs; then the chess clocks decide


class Duel:
    def __init__(self, seed: int, first: str):
        assert first in SEATS
        self.seed, self.first = int(seed), first
        self.games = {s: bball.Game(self.seed) for s in SEATS}
        self.order = []                            # whose shot, in order (regulation), then the extra pairs
        for r in range(N_SPOTS):
            a = first if r % 2 == 0 else OTHER[first]
            self.order += [a, a, OTHER[a], OTHER[a]]
        self.n = 0                                 # shots taken in all
        self.extra = 0                             # extra pairs started
        self.decisions = []
        self.done = False
        self.winner = None
        self.reason = None
        self.forfeit = None
        self.tiebreak = None                       # the last-resort rule's record, if it decided the match

    @property
    def turn(self):
        return None if self.done else self.order[self.n]

    def made(self):
        return {s: self.games[s].made for s in SEATS}

    def stage(self):
        return "regulation" if self.n < 4 * N_SPOTS else "extra shots"

    def shoot(self, seat: str, dec: dict, clock_left: dict | None = None) -> dict:
        """clock_left: both players' chess-clock time left (s) when the shot is taken, recorded with it; it decides a
        match still level after the last extra pair (the last-resort rule)."""
        assert not self.done and seat == self.turn, (seat, self.turn)
        d = dict(dec, seat=seat)
        if clock_left is not None:
            d["clock_left_s"] = {k: round(float(v), 3) for k, v in clock_left.items()}
        self.decisions.append(d)
        res = self.games[seat].shoot(dec)
        self.n += 1
        if self.n == 4 * N_SPOTS or (self.n > 4 * N_SPOTS and (self.n - 4 * N_SPOTS) % 2 == 0):
            m = self.made()
            if m["A"] != m["B"]:
                self.done, self.winner, self.reason = True, ("A" if m["A"] > m["B"] else "B"), "match_over"
            elif self.extra >= EXTRA_PAIRS:                       # level at the cap: more clock time left wins
                c = d.get("clock_left_s") or {}
                ca, cb = c.get("A", 0.0), c.get("B", 0.0)
                self.done, self.reason = True, "match_over"
                self.winner = "A" if ca > cb else "B" if cb > ca else OTHER[self.first]
                self.tiebreak = {"clock_left_s": c, "winner": self.winner}
            else:
                spot = self.extra % N_SPOTS
                self.extra += 1
                for s in SEATS:
                    self.games[s].extend(spot)
                self.order += [self.first, OTHER[self.first]]
        return res

    def lose(self, seat: str, why: str):
        if not self.done:
            self.forfeit = {"seat": seat, "why": why}
            self.decisions.append({"seat": seat, "forfeit": why})
            self.done, self.winner, self.reason = True, OTHER[seat], why

    def replay(self, decisions):
        for d in decisions:
            if "forfeit" in d:
                self.lose(d["seat"], d["forfeit"])
            else:
                self.shoot(d["seat"], {k: d[k] for k in ("angle_deg", "speed", "spin_hz", "yaw_deg")}, d.get("clock_left_s"))

    def state_sha(self):
        h = hashlib.sha256()
        for s in SEATS:
            h.update(self.games[s].state_sha().encode())
        h.update(json.dumps([self.winner, self.reason, self.forfeit, self.n]).encode())
        return h.hexdigest()


if __name__ == "__main__":
    if sys.argv[1] == "replay":
        tr = json.load(open(sys.argv[2]))
        m = Duel(tr["seed"], tr["first_player"])
        for g in m.games.values():
            g.record_snaps = False
        m.replay(tr["decisions"])
        print(json.dumps({"sha": m.state_sha(), "made": m.made(), "winner": m.winner, "reason": m.reason,
                          "done": m.done}))
