"""interlocked_claws: claw_weave. Difficulty is a design target, not a qualification."""

from .common import InterlockedClawsTask


class InterlockedClawsHardTask(InterlockedClawsTask):
    variation_id = 'interlocked_claws_hard'
    family_id = 'claw_weave'
    model_revision = 'pregrasp_scaled_inset3mm_weld_v4'
    difficulty = 'hard'
    pregrasp_weld = True
    # Volume matched to easy (0.85 -> 0.26 L per piece); grip blocks keep finger size.
    claw_scale = .68
    # Owner-authorized clearance candidate: thin both puzzle pieces while
    # retaining the original-size pads and the two independent rigid bodies.
    claw_surface_inset_m = .003
