"""two_overlap_loop; difficulty is an authored target, not runtime qualification."""
from .common import KnotUntyingTask
from topogym.tasks.base import merge_parameters


class KnotUntyingEasyTask(KnotUntyingTask):
    variation_id = 'knot_untying_easy'
    family_id = 'two_overlap_loop'
    model_revision = 'two_overlap_v1_fem_soft50_fine_v1'
    difficulty = 'easy'
    variant_parameters = {'geometry': {'family': 'two_overlap_loop'}}
    defaults = merge_parameters(KnotUntyingTask.defaults, variant_parameters)
    fixed_parameters = ('geometry.family',)
