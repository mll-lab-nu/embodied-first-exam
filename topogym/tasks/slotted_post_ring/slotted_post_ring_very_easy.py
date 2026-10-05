"""slotted_post_ring: below_easy, very_easy. The cord runs under the ring; the ring lifts straight off the post."""

from topogym.tasks.base import merge_parameters
from .below_easy import SlottedBelowEasyTask


class SlottedPostRingVeryEasyTask(SlottedBelowEasyTask):
    variant_parameters = {"cord_route": "under_ring"}
    defaults = merge_parameters(SlottedBelowEasyTask.defaults, variant_parameters)
    variation_id = 'slotted_post_ring_very_easy'
    difficulty = 'very_easy'
