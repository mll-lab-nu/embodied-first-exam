"""The fixture's sport: a seat commands two robots; the high level's act `swing` is the skill (evaluator.SWING's request
fields) plus the core's `entity`, which names the robot (core/sport.py check_command, Match.entities)."""

from core.sport import MatchBase
from evaluator import SWING

ROBOTS = ("1", "2")


class Match(MatchBase):
    def __init__(self, cfg):
        self.cfg = cfg

    def entities(self, seat):
        return ROBOTS


class HighLayer:
    level = "high"

    def schema(self, match, seat):
        ents = list(match.entities(seat))
        entity = {"type": "enum", "values": ents, "default": ents[0], "doc": "which of your robots"}
        return {"swing": {"entity": entity, **SWING.request_schema()["swing"]}}


class Fixture:
    name = "fixture"

    def build(self, cfg):
        return Match(cfg)

    def action_layer(self, level):
        return HighLayer()


SPORT = Fixture()
