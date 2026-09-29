"""interlocked_claws: helical_crown. Difficulty is a design target, not a qualification."""

from topogym.tasks.interlocked_claws.common import InterlockedClawsTask


class InterlockedClawsHelicalCrownTask(InterlockedClawsTask):
    variation_id = 'interlocked_claws_helical_crown'
    family_id = 'helical_crown'
    model_revision = 'simulator_v1'
    difficulty = None

    geometry_family = 'helical_crown'
