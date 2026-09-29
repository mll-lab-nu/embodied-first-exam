"""Shared gathered Blanket, medium design tier; scene-layout acceptance only."""
from .gathered import GatheredBlanketTask, tier_defaults


class BlanketFlattenMediumTask(GatheredBlanketTask):
    variation_id = "blanket_flatten_medium"
    family_id = "gathered_twist"
    difficulty = "medium"
    defaults = tier_defaults(difficulty)
