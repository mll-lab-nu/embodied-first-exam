"""Shared gathered Blanket, easy design tier; scene-layout acceptance only."""
from .gathered import GatheredBlanketTask, tier_defaults


class BlanketFlattenEasyTask(GatheredBlanketTask):
    variation_id = "blanket_flatten_easy"
    family_id = "gathered_twist"
    difficulty = "easy"
    defaults = tier_defaults(difficulty)
