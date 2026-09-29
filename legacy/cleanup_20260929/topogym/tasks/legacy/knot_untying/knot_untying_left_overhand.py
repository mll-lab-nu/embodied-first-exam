"""knot_untying: overhand_trefoil_left. Difficulty is a design target, not a qualification."""

from topogym.tasks.knot_untying.common import KnotUntyingTask
from topogym.tasks.base import merge_parameters


class KnotUntyingLeftOverhandTask(KnotUntyingTask):
    variant_parameters = {'geometry': {'family': 'overhand_trefoil', 'handedness': 'left'}}
    defaults = merge_parameters(KnotUntyingTask.defaults, variant_parameters)
    variation_id = 'knot_untying_left_overhand'
    family_id = 'overhand_trefoil_left'
    model_revision = 'simulator_v1'
    difficulty = None
