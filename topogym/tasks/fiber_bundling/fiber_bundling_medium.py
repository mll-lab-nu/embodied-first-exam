"""fiber_bundling: 8_strands. Difficulty is a design target, not a qualification."""

from .common import FiberBundlingTask
from topogym.tasks.base import merge_parameters


class FiberBundlingMediumTask(FiberBundlingTask):
    variant_parameters = {'geometry': {'fiber_count': 8, 'ring_inner_radius_m': 0.0135}}
    defaults = merge_parameters(FiberBundlingTask.defaults, variant_parameters)
    variation_id = 'fiber_bundling_medium'
    family_id = '8_strands'
    model_revision = 'simulator_v1'
    difficulty = 'medium'
    fixed_parameters = ('geometry.fiber_count', 'geometry.ring_inner_radius_m')
