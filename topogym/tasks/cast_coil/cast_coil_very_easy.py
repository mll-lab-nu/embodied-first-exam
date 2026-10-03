"""One alignment followed by straight insertion of complementary large teeth."""
from .simplified import SimplifiedCoilTask


class CastCoilVeryEasyTask(SimplifiedCoilTask):
    variation_id = "cast_coil_very_easy"
    family_id = "straight_comb"
    model_revision = "cubic_comb_v2_aloha_v1"
    difficulty = None  # Explicit entry; preserve the original three-tier seed pool.
    geometry_resource = "variations/cast_coil/very_easy/geometry.json"
