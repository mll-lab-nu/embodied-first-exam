"""slotted_post_ring: below_easy, easier. A cord loop with bead 2 lies over the ring; pass it through, then lift."""

from topogym.tasks.base import merge_parameters
from .below_easy import SlottedBelowEasyTask


class SlottedPostRingEasierTask(SlottedBelowEasyTask):
    variant_parameters = {"cord_route": "loop_over_ring"}
    defaults = merge_parameters(SlottedBelowEasyTask.defaults, variant_parameters)
    variation_id = 'slotted_post_ring_easier'
    difficulty = 'easier'
