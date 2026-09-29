"""buzz_wire_3d: F1. Difficulty is a design target, not a qualification."""

from topogym.tasks.buzz_wire_3d.common import BuzzWireTask
from topogym.tasks.base import merge_parameters


class BuzzWire3DDoubleArchTask(BuzzWireTask):
    variant_parameters = {'linear_scale': 1.0, 'geometry': {}, 'base_elevation_m': 0.025}
    defaults = merge_parameters(BuzzWireTask.defaults, variant_parameters)
    variation_id = 'buzz_wire_3d_double_arch'
    family_id = 'F1'
    model_revision = 'F1_compact_toy_s70_home_lab_v4'
    difficulty = None
    fixed_parameters = ('linear_scale', 'geometry', 'base_elevation_m')

    layout_resource = 'variations/buzz_wire_3d/F1_compact_toy_s70_home_lab_v4/layout.json'
