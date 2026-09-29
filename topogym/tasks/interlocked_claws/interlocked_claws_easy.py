"""interlocked_claws: helical_claws_balanced_v2. Difficulty is a design target, not a qualification."""

from .common import InterlockedClawsTask


class InterlockedClawsEasyTask(InterlockedClawsTask):
    variation_id = 'interlocked_claws_easy'
    family_id = 'helical_claws_balanced_v2'
    model_revision = 'pregrasp_weld_v2'
    difficulty = 'easy'
    pregrasp_weld = True

    geometry_family = 'helical_claws_balanced_v2'
