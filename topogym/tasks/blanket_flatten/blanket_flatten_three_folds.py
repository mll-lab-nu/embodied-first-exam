"""blanket_flatten: three_folds. Difficulty is a design target, not a qualification."""

from .common import BlanketFlattenTask
from topogym.tasks.base import merge_parameters


class BlanketFlattenThreeFoldsTask(BlanketFlattenTask):
    variant_parameters = {'fold_count': 3}
    defaults = merge_parameters(BlanketFlattenTask.defaults, variant_parameters)
    variation_id = 'blanket_flatten_three_folds'
    family_id = 'three_folds'
    model_revision = 'simulator_v1'
    difficulty = None
