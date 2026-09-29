"""blanket_flatten: corner_cross_twist. Difficulty is a design target, not a qualification."""

from topogym.tasks.base import UnavailableTaskDefinition


class BlanketFlattenCornerCrossTwistTask(UnavailableTaskDefinition):
    task_id = 'blanket_flatten'
    unavailable_reason = 'The traced crossing/twist preparation has no stable simulator initial-state adapter.'
    variation_id = 'blanket_flatten_corner_cross_twist'
    family_id = 'corner_cross_twist'
    model_revision = 'simulator_v1'
    difficulty = None
