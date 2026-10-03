"""Three triangular passive strands on the original anchored Fiber scene."""
from topogym.assets.geometry.fiber_bundling_simplified import SymmetricFiberLayout
from topogym.tasks.base import merge_parameters

from .common import FiberBundlingTask


class FiberBundlingEasierTask(FiberBundlingTask):
    layout_class = SymmetricFiberLayout
    variant_parameters = {"geometry": {"fiber_count": 3, "ring_inner_radius_m": 0.0135}}
    defaults = merge_parameters(FiberBundlingTask.defaults, variant_parameters)
    variation_id = "fiber_bundling_easier"
    family_id = "3_triangular_strands"
    model_revision = "symmetric_branches_v1"
    difficulty = "easier"
    fixed_parameters = ("geometry.fiber_count", "geometry.ring_inner_radius_m")
