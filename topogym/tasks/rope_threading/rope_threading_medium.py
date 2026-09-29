"""rope_threading: wang_reference_v1. Difficulty is a design target, not a qualification."""

from .common import RopeThreadingTask


class RopeThreadingMediumTask(RopeThreadingTask):
    variation_id = 'rope_threading_medium'
    family_id = 'wang_reference_v1'
    model_revision = 'simulator_v1_fem_soft50_fine_v1'
    difficulty = 'medium'
