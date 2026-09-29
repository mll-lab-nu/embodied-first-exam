"""knot_untying: double_overhand. Difficulty is a design target, not a qualification."""

from .common import KnotUntyingTask
from topogym.tasks.base import merge_parameters


class KnotUntyingDoubleOverhandTask(KnotUntyingTask):
    variant_parameters = {'geometry': {'family': 'double_overhand'}}
    defaults = merge_parameters(KnotUntyingTask.defaults, variant_parameters)
    variation_id = 'knot_untying_double_overhand'
    family_id = 'double_overhand'
    model_revision = 'simulator_v1_fem_soft50_fine_v1'
    difficulty = None
    fixed_parameters = ('geometry.family',)
