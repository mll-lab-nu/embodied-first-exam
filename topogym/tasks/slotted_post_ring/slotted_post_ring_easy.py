"""slotted_post_ring: large_ring. Difficulty is a design target, not a qualification."""

from topogym.tasks.base import merge_parameters
from .common import SlottedPostRingTask


class SlottedPostRingEasyTask(SlottedPostRingTask):
    variant_parameters = {'geometry': {'ring_major_radius_m': .064,
        'ring_tube_radius_m': .010, 'slot_width_m': .028, 'disc_radius_m': .055}}
    defaults = merge_parameters(SlottedPostRingTask.defaults, variant_parameters)
    fixed_parameters = tuple('geometry.' + key for key in variant_parameters['geometry'])
    variation_id = 'slotted_post_ring_easy'
    family_id = 'large_ring'
    model_revision = 'ring108_v1_fem_soft50_fine_v1'
    difficulty = 'easy'
