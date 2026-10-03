"""XYZ cross head and a square frame with a lateral handle extension."""
from .simplified import SimplifiedClawsTask


class InterlockedClawsEasierTask(SimplifiedClawsTask):
    variation_id = "interlocked_claws_easier"
    family_id = "cross_square_offset"
    model_revision = "xyz_cross_offset_frame_candidate_v1"
    difficulty = "easier"
