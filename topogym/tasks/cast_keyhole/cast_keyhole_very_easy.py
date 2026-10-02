"""Straight extraction channel with short blind cross branches."""
from .common import CastKeyholeTask


class CastKeyholeVeryEasyTask(CastKeyholeTask):
    variation_id = "cast_keyhole_very_easy"
    family_id = "simplified_very_easy"
    model_revision = "simplified_original_layout_v4"
    difficulty = None  # Explicit experimental entry; the three-tier seeded pool is unchanged.
    fixed_parameters = ("scale",)
    geometry_resource = "variations/cast_keyhole/very_easy/geometry.json"
