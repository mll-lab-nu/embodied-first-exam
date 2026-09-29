"""fiber_bundling: 16_strands. Difficulty is a design target, not a qualification."""

from .common import FiberBundlingTask
from topogym.tasks.base import merge_parameters


class FiberBundlingHardTask(FiberBundlingTask):
    variant_parameters = {'geometry': {'fiber_count': 16, 'ring_inner_radius_m': 0.0135}}
    defaults = merge_parameters(FiberBundlingTask.defaults, variant_parameters)
    variation_id = 'fiber_bundling_hard'
    family_id = '16_strands'
    model_revision = 'simulator_v1'
    difficulty = 'hard'
    fixed_parameters = ('geometry.fiber_count', 'geometry.ring_inner_radius_m')
