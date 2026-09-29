"""cast_coil: face_small. Difficulty is a design target, not a qualification."""

from topogym.tasks.cast_coil.common import CastCoilTask


class CastCoilFaceSmallTask(CastCoilTask):
    variation_id = 'cast_coil_face_small'
    family_id = 'face_small'
    model_revision = 'simulator_v1'
    difficulty = None

    template_resource = 'variations/cast_coil/face_small.json'
