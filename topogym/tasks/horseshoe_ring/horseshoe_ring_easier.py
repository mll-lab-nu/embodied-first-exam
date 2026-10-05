"""horseshoe_ring: below_easy, easier. A 146 x 120 mm bore passes over a shoe only once turned."""

from topogym.tasks.base import merge_parameters
from .below_easy import HorseshoeBelowEasyTask, ring


class HorseshoeRingEasierTask(HorseshoeBelowEasyTask):
    variant_parameters = {"ring": ring(146., 120.)}
    defaults = merge_parameters(HorseshoeBelowEasyTask.defaults, variant_parameters)
    variation_id = 'horseshoe_ring_easier'
    difficulty = 'easier'
    layout_resource = 'variations/horseshoe_ring/below_easy_easier_settled_poses.json'
