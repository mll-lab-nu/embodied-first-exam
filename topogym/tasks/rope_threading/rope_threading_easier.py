"""Single full-size source R1 for a two-hand threading scene."""
from topogym.tasks.base import merge_parameters
from .simplified import RopeThreadingBimanualTask


class RopeThreadingEasierTask(RopeThreadingBimanualTask):
    variant_parameters = {"geometry": {"ring_ids": ["R1"], "ring_inner_radius_m": None,
                                       "ring_shape": "closed"},
                          "terminal": {"handoff_band_m": .12, "handoff_contact_gap_m": .0003,
                                       "handoff_side_clearance_m": .012, "handoff_grip_duration_s": .02}}
    defaults = merge_parameters(RopeThreadingBimanualTask.defaults, variant_parameters)
    fixed_parameters = ("geometry.ring_ids", "geometry.ring_inner_radius_m", "geometry.ring_shape")
    variation_id = "rope_threading_easier"
    family_id = "single_ring_bimanual"
    model_revision = "single_ring_bimanual_yaw0_v1_fem_soft50_fine_v1"
    difficulty = "easier"
    instruction = "Use both hands to feed and receive a rope end through the single cyan ring."
