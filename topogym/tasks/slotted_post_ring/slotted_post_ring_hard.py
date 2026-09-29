"""slotted_post_ring: original_scale. Difficulty is a design target, not a qualification."""

from .common import SlottedPostRingTask
from topogym.tasks.base import merge_parameters


class SlottedPostRingHardTask(SlottedPostRingTask):
    variant_parameters = {'geometry': {'ring_major_radius_m': .061,
        'ring_tube_radius_m': .010, 'slot_width_m': .028, 'disc_radius_m': .055}}
    defaults = merge_parameters(SlottedPostRingTask.defaults, variant_parameters)
    fixed_parameters = tuple('geometry.' + key for key in variant_parameters['geometry'])
    variation_id = 'slotted_post_ring_hard'
    family_id = 'original_scale'
    model_revision = 'simulator_v1_fem_soft50_fine_v1'
    difficulty = 'hard'
