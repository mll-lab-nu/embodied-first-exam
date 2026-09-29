"""interlocked_claws: claw_weave. Difficulty is a design target, not a qualification."""

from .common import InterlockedClawsTask


class InterlockedClawsHardTask(InterlockedClawsTask):
    variation_id = 'interlocked_claws_hard'
    family_id = 'claw_weave'
    model_revision = 'pregrasp_scaled_weld_v3'
    difficulty = 'hard'
    pregrasp_weld = True
    # Volume matched to easy (0.85 -> 0.26 L per piece); grip blocks keep finger size.
    claw_scale = .68
