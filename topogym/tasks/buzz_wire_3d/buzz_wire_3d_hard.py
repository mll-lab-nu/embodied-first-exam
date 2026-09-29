"""buzz_wire_3d: F3. Difficulty is a design target, not a qualification."""

from .common import BuzzWireTask
from topogym.tasks.base import merge_parameters


class BuzzWire3DHardTask(BuzzWireTask):
    variant_parameters = {'linear_scale': 1.0, 'geometry': {}, 'base_elevation_m': 0.125}
    defaults = merge_parameters(BuzzWireTask.defaults, variant_parameters)
    variation_id = 'buzz_wire_3d_hard'
    family_id = 'F3'
    model_revision = 'F3_thin_connectors_deck_rest_v1'
    difficulty = 'hard'
    fixed_parameters = ('linear_scale', 'geometry', 'base_elevation_m')

    layout_resource = 'variations/buzz_wire_3d/F3_compact_toy_s70_home_lab_v4/layout.json'
