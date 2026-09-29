"""Shared gathered Blanket, hard design tier; scene-layout acceptance only."""
from .gathered import GatheredBlanketTask, tier_defaults


class BlanketFlattenHardTask(GatheredBlanketTask):
    variation_id = "blanket_flatten_hard"
    family_id = "gathered_twist"
    difficulty = "hard"
    defaults = tier_defaults(difficulty)
