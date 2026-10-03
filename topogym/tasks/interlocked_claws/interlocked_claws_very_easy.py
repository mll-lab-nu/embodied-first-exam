"""Two staggered L hooks engaging through perpendicular short legs."""
from .simplified import SimplifiedClawsTask


class InterlockedClawsVeryEasyTask(SimplifiedClawsTask):
    variation_id = "interlocked_claws_very_easy"
    family_id = "shallow_l_hooks"
    model_revision = "perpendicular_short_legs_pregrasp_candidate_v2"
    difficulty = "very_easy"
