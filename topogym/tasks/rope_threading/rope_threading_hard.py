"""rope_threading: three_tight_rings. Difficulty is a design target, not a qualification."""

from topogym.tasks.base import merge_parameters
from .common import RopeThreadingTask


class RopeThreadingHardTask(RopeThreadingTask):
    # Only aperture size changes: ring planes, tube diameter and rope stay fixed.
    # ThreadingLayout moves each stand/base to preserve its rim connection.
    variant_parameters = {'geometry': {'ring_ids': ['R1', 'R2', 'R3'], 'ring_inner_radius_m': .050}}
    defaults = merge_parameters(RopeThreadingTask.defaults, variant_parameters)
    fixed_parameters = ('geometry.ring_ids', 'geometry.ring_inner_radius_m')
    variation_id = 'rope_threading_hard'
    family_id = 'three_tight_rings'
    model_revision = 'three_rings_id100_v1_fem_soft50_fine_v1'
    difficulty = 'hard'
