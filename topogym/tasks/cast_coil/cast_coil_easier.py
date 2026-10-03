"""Offset insertion followed by sliding the front bar into the root pocket."""
from .simplified import SimplifiedCoilTask


class CastCoilEasierTask(SimplifiedCoilTask):
    variation_id = "cast_coil_easier"
    family_id = "offset_baffle"
    model_revision = "cubic_baffle_v2_aloha_v1"
    difficulty = None
    geometry_resource = "variations/cast_coil/easier/geometry.json"
