"""Single upward-open cradle, keeping the source R1 lower semicircle."""
from topogym.tasks.base import merge_parameters
from .simplified import RopeThreadingDrapeTask


class RopeThreadingVeryEasyTask(RopeThreadingDrapeTask):
    variant_parameters = {"geometry": {"ring_ids": ["R1"], "ring_inner_radius_m": None,
                                       "ring_shape": "lower_semicircle"},
                          "terminal": {"support_gap_m": .001, "support_penetration_m": .0005,
                                       "drape_span_m": .02, "minimum_drape_length_m": .05}}
    defaults = merge_parameters(RopeThreadingDrapeTask.defaults, variant_parameters)
    fixed_parameters = ("geometry.ring_ids", "geometry.ring_inner_radius_m", "geometry.ring_shape")
    variation_id = "rope_threading_very_easy"
    family_id = "single_lower_semicircle"
    model_revision = "single_lower_semicircle_yaw0_v1_fem_soft50_fine_v1"
    difficulty = "very_easy"
    instruction = "Lift the rope from the table and drape it onto the cyan lower semicircle from its open top."
