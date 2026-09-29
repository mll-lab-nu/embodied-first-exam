"""Retained simulator_v1 five-fold setting and its historical evidence identity."""
from .common import BlanketFlattenTask


class BlanketFlattenSimpleFoldsTask(BlanketFlattenTask):
    variation_id = "blanket_flatten_simple_folds"
    family_id = "simple_folds"
    model_revision = "simulator_v1"
    fixed_parameters = ("fold_count",)
