"""Two lateral offsets before withdrawal through the open gold fork."""
from .common import CastKeyholeTask


class CastKeyholeEasierTask(CastKeyholeTask):
    variation_id = "cast_keyhole_easier"
    family_id = "simplified_easier"
    model_revision = "simplified_original_layout_v4"
    difficulty = None
    fixed_parameters = ("scale",)
    geometry_resource = "variations/cast_keyhole/easier/geometry.json"
