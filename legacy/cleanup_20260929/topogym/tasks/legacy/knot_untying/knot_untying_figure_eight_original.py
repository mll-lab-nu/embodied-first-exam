"""knot_untying: figure_eight. Difficulty is a design target, not a qualification."""

from topogym.tasks.knot_untying.common import KnotUntyingTask
from topogym.tasks.base import merge_parameters


class KnotUntyingFigureEightOriginalTask(KnotUntyingTask):
    variant_parameters = {'geometry': {'family': 'figure_eight'}}
    defaults = merge_parameters(KnotUntyingTask.defaults, variant_parameters)
    variation_id = 'knot_untying_figure_eight_original'
    family_id = 'figure_eight'
    model_revision = 'simulator_v1'
    difficulty = None
