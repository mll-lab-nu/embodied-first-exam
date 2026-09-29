"""fiber_bundling: 4_strands. Difficulty is a design target, not a qualification."""

from .common import FiberBundlingTask
from topogym.tasks.base import merge_parameters


class FiberBundlingEasyTask(FiberBundlingTask):
    variant_parameters = {'geometry': {'fiber_count': 4, 'ring_inner_radius_m': 0.0135}}
    defaults = merge_parameters(FiberBundlingTask.defaults, variant_parameters)
    variation_id = 'fiber_bundling_easy'
    family_id = '4_strands'
    model_revision = 'simulator_v1'
    difficulty = 'easy'
    fixed_parameters = ('geometry.fiber_count', 'geometry.ring_inner_radius_m')
