"""A half-folded blanket with the free corner of its upper layer turned inward."""
from .corner_folds import CornerFoldBlanketTask, tier_defaults


class BlanketFlattenEasierTask(CornerFoldBlanketTask):
    variation_id = "blanket_flatten_easier"
    difficulty = "easier"
    defaults = tier_defaults(difficulty)
