"""cast_coil: corner_cut. Difficulty is a design target, not a qualification."""

from topogym.tasks.cast_coil.common import CastCoilTask


class CastCoilCornerCutTask(CastCoilTask):
    variation_id = 'cast_coil_corner_cut'
    family_id = 'corner_cut'
    model_revision = 'simulator_v1'
    difficulty = None

    template_resource = 'variations/cast_coil/corner_cut.json'
