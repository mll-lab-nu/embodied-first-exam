"""Two alternating overlaps in an open rope loop; difficulty is an authored target."""
from .common import KnotUntyingTask
from topogym.tasks.base import merge_parameters


class KnotUntyingEasierTask(KnotUntyingTask):
    variation_id = 'knot_untying_easier'
    family_id = 'alternating_overlap_loop'
    model_revision = 'alternating_overlap_v1_fem_soft50_fine_v1'
    difficulty = 'easier'
    variant_parameters = {'geometry': {'family': 'alternating_overlap_loop'}}
    defaults = merge_parameters(KnotUntyingTask.defaults, variant_parameters)
    fixed_parameters = ('geometry.family',)
