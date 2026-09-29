"""overhand_trefoil; difficulty is an authored target, not runtime qualification."""
from .common import KnotUntyingTask
from topogym.tasks.base import merge_parameters


class KnotUntyingMediumTask(KnotUntyingTask):
    variation_id = 'knot_untying_medium'
    family_id = 'overhand_trefoil'
    model_revision = 'simulator_v1_fem_soft50_fine_v1'
    difficulty = 'medium'
    variant_parameters = {'geometry': {'family': 'overhand_trefoil'}}
    defaults = merge_parameters(KnotUntyingTask.defaults, variant_parameters)
    fixed_parameters = ('geometry.family',)
