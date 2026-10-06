"""One inward corner fold on the standard full-size blanket."""
from .corner_folds import CornerFoldBlanketTask, tier_defaults


class BlanketFlattenVeryEasyTask(CornerFoldBlanketTask):
    variation_id = "blanket_flatten_very_easy"
    difficulty = "very_easy"
    defaults = tier_defaults(difficulty)
