"""One overlap at the mouth of an open rope loop; difficulty is an authored target."""
from .common import KnotUntyingTask
from topogym.tasks.base import merge_parameters


class KnotUntyingVeryEasyTask(KnotUntyingTask):
    variation_id = 'knot_untying_very_easy'
    family_id = 'single_overlap_loop'
    model_revision = 'single_overlap_v1_fem_soft50_fine_v1'
    difficulty = 'very_easy'
    variant_parameters = {'geometry': {'family': 'single_overlap_loop'}}
    defaults = merge_parameters(KnotUntyingTask.defaults, variant_parameters)
    fixed_parameters = ('geometry.family',)
