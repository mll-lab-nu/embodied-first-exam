"""A synthetic turn-protocol game for the core's tests: the sides move in turn (the first side first), each move adds
v in [0, 1] to the mover's side score; the match ends when every side still in has made TURNS moves. Two sides are
decided by score, then the first side; more sides are ranked by score (retired sides last). The built-in player adds
0.5 on every turn (the fairness check, core/testkit.py). No physics, no images."""
import os

from core.sport import FINISHED, PLAYING, LowLayer, MatchBase, Phase, Refused, sha_json

TURNS = 2


class Game(MatchBase):
    def __init__(self, cfg):
        self.cfg, self.k = cfg, 0
        sides = cfg.side_list()
        first = cfg.side_of(cfg.first) if cfg.first in cfg.seats else (cfg.first or sides[0])
        i = sides.index(first) if first in sides else 0
        self.order = sides[i:] + sides[:i]
        self.score = dict.fromkeys(sides, 0.0)
        self.moves = dict.fromkeys(sides, 0)
        self.out: list[str] = []

    def schema(self, seat):
        return {"add": {"v": {"type": "number", "min": 0, "max": 1}}}

    def apply(self, seat, cmd):
        side = self.cfg.side_of(seat)
        self.score[side] = round(self.score[side] + cmd["v"], 6)
        self.moves[side] += 1
        self.k += 1
        return {}

    def live(self):
        return [s for s in self.order if s not in self.out]

    def to_move(self):
        if self.phase().state == FINISHED:
            return None
        side = min(self.live(), key=lambda s: (self.moves[s], self.order.index(s)))
        return self.cfg.seats_of(side)[0]

    def phase(self):
        if all(self.moves[s] >= TURNS for s in self.live()):
            return Phase(FINISHED, reason="match_over")
        return Phase(PLAYING)

    def retire(self, side, why):
        self.out.append(side)
        return True

    def scores(self):
        return dict(self.score)

    def ranking(self):
        return sorted(self.score, key=lambda s: (s in self.out, -self.score[s], self.order.index(s)))

    def tiebreaks(self):
        if len(self.order) < 2:
            return []                                     # one side: solo
        a, b = self.order[:2]
        return [("score", lambda m: None if m.score[a] == m.score[b] else (a if m.score[a] > m.score[b] else b)),
                ("first_side", lambda m: a)]

    def state_digest(self):
        return sha_json({"k": self.k, "score": self.score, "moves": self.moves, "out": self.out})

    def final_fields(self):                               # a sport that records its seed (core/seeds.py scrub test)
        return {"seed": self.cfg.seed, "draws": [self.cfg.seed, 1]}

    def observe(self, seat, query=None):
        return {"unit": self.k, "pos": self.score[self.cfg.side_of(seat)]}


def validate(seat, body, match, ctx):
    try:
        v = float(body.get("v"))
    except (TypeError, ValueError):
        raise Refused("v must be a number") from None
    if not 0 <= v <= 1:
        raise Refused("v must be in [0, 1]")
    return {"type": "add", "v": v}


class Steady:
    def __init__(self, spec, seat, seed):
        pass

    def act(self, view):
        return {"type": "add", "v": 0.5}


class Fixture:
    name, protocol, revision, workers = "fixture_turn", "turn", "fixture-turn-1", ()
    source_dirs = [os.path.dirname(os.path.abspath(__file__))]

    def build(self, cfg):
        return Game(cfg)

    def action_layer(self, level):
        return LowLayer(validate)

    def players(self):
        return {"reference": Steady}


SPORT = Fixture()
