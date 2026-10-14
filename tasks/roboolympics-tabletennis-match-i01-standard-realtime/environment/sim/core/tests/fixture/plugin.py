"""A synthetic realtime world for the core's tests: every entity has a position on a line and a commanded velocity;
a unit ends every UNIT steps (all seats review), the match after UNITS units; a side's score is the sum of its
entities' positions; more than two sides are ranked by score (retired sides last). No physics, no images."""
import os

from core.sport import FINISHED, PLAYING, UNIT_OVER, MatchBase, Phase, Refused, SchemaLayer, sha_json

UNIT, UNITS, ENTITIES = 30, 3, ("e0", "e1")


class World(MatchBase):
    dt = 0.01

    def __init__(self, cfg):
        self.cfg, self.k, self.u, self.frozen = cfg, 0, 0, False
        self.pos = {f"{s}.{e}": 0.0 for s in cfg.seats for e in ENTITIES}
        self.vel = dict.fromkeys(self.pos, 0.0)
        self.out: list[str] = []

    def schema(self, seat):
        return {"move": {"v": {"type": "number", "min": -1, "max": 1}}}

    def entities(self, seat):
        return ENTITIES

    def apply(self, seat, cmd):
        self.vel[f"{seat}.{cmd['entity']}"] = cmd["v"]
        return {}

    def step(self):
        for key, v in self.vel.items():
            if key.split(".")[0] not in self.retired_seats():
                self.pos[key] = round(self.pos[key] + v, 6)
        self.k += 1
        if self.k % UNIT == 0:
            self.frozen = True
            return [{"kind": "unit_end", "unit": self.u}]     # an event (core 0.2.25 logs it as an `event` row)
        return []

    def retired_seats(self):
        return [s for s in self.cfg.seats if self.cfg.side_of(s) in self.out]

    def phase(self):
        if self.k >= UNIT * UNITS:
            return Phase(FINISHED, reason="match_over")
        if self.frozen:
            return Phase(UNIT_OVER, review=tuple(self.cfg.seats), reason="unit")
        return Phase(PLAYING)

    def resume(self):
        self.frozen, self.u = False, self.u + 1

    def unit(self):
        return self.u

    def retire(self, side, why):
        self.out.append(side)
        return True

    def scores(self):
        out = {}
        for s in self.cfg.seats:
            out[self.cfg.side_of(s)] = round(out.get(self.cfg.side_of(s), 0.0) + sum(
                self.pos[f"{s}.{e}"] for e in ENTITIES), 6)
        return out

    def ranking(self):
        sc = self.scores()
        return sorted(sc, key=lambda s: (s in self.out, -sc[s], s))

    def tiebreaks(self):
        if len(self.cfg.side_list()) < 2:
            return []                                     # one side: solo
        a, b = self.cfg.side_list()[:2]
        return [("score", lambda m: None if m.scores()[a] == m.scores()[b] else
                 (a if m.scores()[a] > m.scores()[b] else b)), ("first_side", lambda m: a)]

    def state_digest(self):
        return sha_json({"k": self.k, "pos": self.pos, "out": self.out})

    def observe(self, seat, query=None):
        if query is not None and query.get("view") not in ("near", "far"):
            raise Refused("query.view must be near or far")
        mine = {e: self.pos[f"{seat}.{e}"] for e in ENTITIES}
        extra = {"view": query["view"]} if query else {}
        if query and query["view"] == "far":
            extra["secret_state"] = self.pos           # not whitelisted: the core must drop it and record an error
        return {"unit": self.u, "pos": mine, **extra}


class Layer(SchemaLayer):
    def __init__(self, delay):
        super().__init__()
        self.delay_steps = delay


class Fixture:
    name, protocol, revision, workers = "fixture", "realtime", "fixture-1", ()
    source_dirs = [os.path.dirname(os.path.abspath(__file__))]

    def build(self, cfg):
        return World(cfg)

    def action_layer(self, level):
        return Layer(int(os.environ.get("FIXTURE_DELAY", "0")))


SPORT = Fixture()
