"""A half-folded blanket with one corner of the two-layer packet turned inward."""
from .corner_folds import CornerFoldBlanketTask, tier_defaults


class BlanketFlattenEasierTask(CornerFoldBlanketTask):
    variation_id = "blanket_flatten_easier"
    difficulty = "easier"
    defaults = tier_defaults(difficulty)
