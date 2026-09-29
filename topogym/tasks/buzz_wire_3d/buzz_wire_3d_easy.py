"""buzz_wire_3d: F1_triple. Difficulty is a design target, not a qualification."""

from .common import BuzzWireTask
from topogym.tasks.base import merge_parameters


class BuzzWire3DEasyTask(BuzzWireTask):
    variant_parameters = {'linear_scale': 1.0, 'geometry': {}, 'base_elevation_m': 0.125}
    defaults = merge_parameters(BuzzWireTask.defaults, variant_parameters)
    variation_id = 'buzz_wire_3d_easy'
    family_id = 'F1_triple'
    model_revision = 'F1_triple_thin_connectors_deck_rest_v1'
    difficulty = 'easy'
    fixed_parameters = ('linear_scale', 'geometry', 'base_elevation_m')

    layout_resource = 'variations/buzz_wire_3d/F1_triple_compact_toy_s70_home_lab_v1/layout.json'
