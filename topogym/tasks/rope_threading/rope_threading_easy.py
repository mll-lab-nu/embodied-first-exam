"""rope_threading: two_rings. Difficulty is a design target, not a qualification."""

from topogym.tasks.base import merge_parameters
from .common import RopeThreadingTask


class RopeThreadingEasyTask(RopeThreadingTask):
    # Keep source dimensions and the complete initial rope; remove R3 and its mount.
    variant_parameters = {'geometry': {'ring_ids': ['R1', 'R2'], 'ring_inner_radius_m': None}}
    defaults = merge_parameters(RopeThreadingTask.defaults, variant_parameters)
    fixed_parameters = ('geometry.ring_ids', 'geometry.ring_inner_radius_m')
    variation_id = 'rope_threading_easy'
    family_id = 'two_rings'
    model_revision = 'two_rings_v1_fem_soft50_fine_v1'
    difficulty = 'easy'
