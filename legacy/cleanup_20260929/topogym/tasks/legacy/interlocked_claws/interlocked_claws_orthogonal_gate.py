"""interlocked_claws: orthogonal_gate. Difficulty is a design target, not a qualification."""

from topogym.tasks.interlocked_claws.common import InterlockedClawsTask


class InterlockedClawsOrthogonalGateTask(InterlockedClawsTask):
    variation_id = 'interlocked_claws_orthogonal_gate'
    family_id = 'orthogonal_gate'
    model_revision = 'simulator_v1'
    difficulty = None

    geometry_family = 'orthogonal_gate'
