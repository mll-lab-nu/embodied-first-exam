"""A synthetic turn-protocol game with images for the core's reply-image tests (core 0.2.8): two sides move in turn,
each move v in [0, 1] adds v to the mover's score and puts the mover's block at x = v (TURNS moves each). The scene
is a floor and two mocap blocks; cameras() serves the top view to the seat on turn only, and not while another seat's
review is due (Match.awaiting_review); reply_views() shows the move's result: two frames (the block before and after
the move), camera order."""
import os

from core.sport import FINISHED, PLAYING, LowLayer, MatchBase, Phase, Refused, sha_json

TURNS = 2
XML = ('<mujoco><visual><headlight ambient=".5 .5 .5"/></visual><worldbody><geom type="plane" size="5 5 .1" '
       'rgba=".3 .5 .3 1"/><body mocap="true" pos="0 0 .1"><geom type="box" size=".1 .1 .1" rgba="1 0 0 1"/></body>'
       '<body mocap="true" pos="0 1 .1"><geom type="box" size=".1 .1 .1" rgba="0 0 1 1"/></body></worldbody></mujoco>')
TOP = {"name": "top", "pos": [0.5, 0.5, 4], "lookat": [0.5, 0.5, 0], "up": [1, 0, 0], "fovy_deg": 50, "width": 80,
       "height": 60}


class Game(MatchBase):
    def __init__(self, cfg):
        self.cfg, self.k = cfg, 0
        self.order = list(cfg.seats) if cfg.first in (None, cfg.seats[0]) else list(cfg.seats)[::-1]
        self.score = dict.fromkeys(cfg.seats, 0.0)
        self.x = dict.fromkeys(cfg.seats, 0.0)
        self.moves = dict.fromkeys(cfg.seats, 0)
        self.before = None                                   # the mover's block before its last move

    def schema(self, seat):
        return {"add": {"v": {"type": "number", "min": 0, "max": 1}}}

    def apply(self, seat, cmd):
        self.before = dict(self.x)
        self.score[seat] = round(self.score[seat] + cmd["v"], 6)
        self.x[seat] = cmd["v"]
        self.moves[seat] += 1
        self.k += 1
        return {"moved": seat}

    def to_move(self):
        if self.phase().state == FINISHED:
            return None
        return min(self.order, key=lambda s: (self.moves[s], self.order.index(s)))

    def phase(self):
        return Phase(FINISHED, reason="match_over") if all(n >= TURNS for n in self.moves.values()) else Phase(PLAYING)

    def scores(self):
        return dict(self.score)

    def tiebreaks(self):
        a, b = self.order[:2]
        return [("score", lambda m: None if m.score[a] == m.score[b] else (a if m.score[a] > m.score[b] else b)),
                ("first", lambda m: a)]

    def state_digest(self):
        return sha_json({"k": self.k, "score": self.score, "x": self.x})

    def observe(self, seat, query=None):
        return {"unit": self.k, "pos": self.x[seat]}

    def cameras(self, seat, query=None):
        if seat != self.to_move() or self.awaiting_review not in (None, seat):
            return []
        return [TOP]

    def state_of(self, x):
        s = list(self.cfg.seats)
        return {"qpos": [], "mocap_pos": [[x[s[0]], 0.0, 0.1], [x[s[1]], 1.0, 0.1]],
                "mocap_quat": [[1, 0, 0, 0], [1, 0, 0, 0]]}

    def render_state(self):
        return self.state_of(self.x)

    def reply_views(self, seat, cmd, info):
        return {"frames": [{"cameras": [TOP], "state": self.state_of(self.before), "label": "before"},
                           {"cameras": [TOP], "label": "after"}], "note": "your block before and after the move"}


def validate(seat, body, match, ctx):
    try:
        v = float(body.get("v"))
    except (TypeError, ValueError):
        raise Refused("v must be a number") from None
    if not 0 <= v <= 1:
        raise Refused("v must be in [0, 1]")
    return {"type": "add", "v": v}


class Fixture:
    name, protocol, revision, workers = "fixture_images", "turn", "fixture-images-1", ()
    source_dirs = [os.path.dirname(os.path.abspath(__file__))]

    def build(self, cfg):
        return Game(cfg)

    def action_layer(self, level):
        return LowLayer(validate)

    def scene(self, cfg):
        from renderers.base import Scene
        return Scene(xml=XML)


SPORT = Fixture()
