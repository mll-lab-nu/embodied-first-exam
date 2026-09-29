"""figure_eight; difficulty is an authored target, not runtime qualification."""
from .common import KnotUntyingTask
from topogym.tasks.base import merge_parameters


class KnotUntyingHardTask(KnotUntyingTask):
    variation_id = 'knot_untying_hard'
    family_id = 'figure_eight'
    model_revision = 'local_curve_v2_fem_soft50_fine_v1'
    difficulty = 'hard'
    variant_parameters = {'geometry': {'family': 'figure_eight', 'planar_scale_m': 0.0325, 'crossing_height_m': 0.01}}
    defaults = merge_parameters(KnotUntyingTask.defaults, variant_parameters)
    fixed_parameters = ('geometry.family', 'geometry.planar_scale_m', 'geometry.crossing_height_m')
