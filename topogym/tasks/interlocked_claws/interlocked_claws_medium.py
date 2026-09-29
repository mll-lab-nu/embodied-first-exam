"""interlocked_claws: orthogonal_gate_balanced_v2. Difficulty is a design target, not a qualification."""

from .common import InterlockedClawsTask


class InterlockedClawsMediumTask(InterlockedClawsTask):
    variation_id = 'interlocked_claws_medium'
    family_id = 'acute_windows_opposed'
    model_revision = 'opposed_pregrasp_wide2_v1'
    difficulty = 'medium'

    geometry_family = 'acute_windows_opposed'
    # Both gates +2 mm per side: the unwidened and gate-A-only versions had no
    # separation route; single-orientation pulls stay blocked.
    gate_extra_m = (.002, .002)
