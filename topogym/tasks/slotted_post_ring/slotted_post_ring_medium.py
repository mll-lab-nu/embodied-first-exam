"""slotted_post_ring: middle_ring. Difficulty is a design target, not a qualification."""

from topogym.tasks.base import merge_parameters
from .common import SlottedPostRingTask


class SlottedPostRingMediumTask(SlottedPostRingTask):
    variant_parameters = {'geometry': {'ring_major_radius_m': .0625,
        'ring_tube_radius_m': .010, 'slot_width_m': .028, 'disc_radius_m': .055}}
    defaults = merge_parameters(SlottedPostRingTask.defaults, variant_parameters)
    fixed_parameters = tuple('geometry.' + key for key in variant_parameters['geometry'])
    variation_id = 'slotted_post_ring_medium'
    family_id = 'middle_ring'
    model_revision = 'ring105_v1_fem_soft50_fine_v1'
    difficulty = 'medium'
