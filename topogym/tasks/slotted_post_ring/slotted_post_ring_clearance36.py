"""slotted_post_ring: clearance36. Difficulty is a design target, not a qualification."""

from .common import SlottedPostRingTask
from topogym.tasks.base import merge_parameters


class SlottedPostRingClearance36Task(SlottedPostRingTask):
    variant_parameters = {'geometry': {'slot_width_m': 0.036}}
    defaults = merge_parameters(SlottedPostRingTask.defaults, variant_parameters)
    variation_id = 'slotted_post_ring_clearance36'
    family_id = 'clearance36'
    model_revision = 'simulator_v1_fem_soft50_fine_v1'
    difficulty = None
