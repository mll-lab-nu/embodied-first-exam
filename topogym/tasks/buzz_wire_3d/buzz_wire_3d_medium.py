"""buzz_wire_3d: F2. Difficulty is a design target, not a qualification."""

from .common import BuzzWireTask
from topogym.tasks.base import merge_parameters


class BuzzWire3DMediumTask(BuzzWireTask):
    variant_parameters = {'linear_scale': 1.0, 'geometry': {}, 'base_elevation_m': 0.125}
    defaults = merge_parameters(BuzzWireTask.defaults, variant_parameters)
    variation_id = 'buzz_wire_3d_medium'
    family_id = 'F2'
    model_revision = 'F2_thin_connectors_deck_rest_v1'
    difficulty = 'medium'
    fixed_parameters = ('linear_scale', 'geometry', 'base_elevation_m')

    layout_resource = 'variations/buzz_wire_3d/F2_compact_toy_s70_home_lab_v4/layout.json'
