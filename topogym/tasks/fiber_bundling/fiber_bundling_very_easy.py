"""Two opposed passive strands on the original anchored Fiber scene."""
from topogym.assets.geometry.fiber_bundling_simplified import SymmetricFiberLayout
from topogym.tasks.base import merge_parameters

from .common import FiberBundlingTask


class FiberBundlingVeryEasyTask(FiberBundlingTask):
    layout_class = SymmetricFiberLayout
    variant_parameters = {"geometry": {"fiber_count": 2, "ring_inner_radius_m": 0.0135}}
    defaults = merge_parameters(FiberBundlingTask.defaults, variant_parameters)
    variation_id = "fiber_bundling_very_easy"
    family_id = "2_opposed_strands"
    model_revision = "symmetric_branches_v1"
    difficulty = "very_easy"
    fixed_parameters = ("geometry.fiber_count", "geometry.ring_inner_radius_m")
