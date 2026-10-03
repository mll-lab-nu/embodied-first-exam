"""horseshoe_ring: below_easy, very_easy. A round 144 mm bore passes over a shoe at every phase."""

from topogym.tasks.base import merge_parameters
from .below_easy import HorseshoeBelowEasyTask, ring


class HorseshoeRingVeryEasyTask(HorseshoeBelowEasyTask):
    variant_parameters = {"ring": ring(144., 144.)}
    defaults = merge_parameters(HorseshoeBelowEasyTask.defaults, variant_parameters)
    variation_id = 'horseshoe_ring_very_easy'
    difficulty = 'very_easy'
    layout_resource = 'variations/horseshoe_ring/below_easy_very_easy_settled_poses.json'
