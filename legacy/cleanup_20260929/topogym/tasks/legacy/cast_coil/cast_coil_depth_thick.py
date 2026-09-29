"""cast_coil: depth_thick. Difficulty is a design target, not a qualification."""

from topogym.tasks.cast_coil.common import CastCoilTask


class CastCoilDepthThickTask(CastCoilTask):
    variation_id = 'cast_coil_depth_thick'
    family_id = 'depth_thick'
    model_revision = 'simulator_v1'
    difficulty = None

    template_resource = 'variations/cast_coil/depth_thick.json'
