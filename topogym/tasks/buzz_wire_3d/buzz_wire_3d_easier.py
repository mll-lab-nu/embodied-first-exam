"""Approved sideways-then-downward layout; qualification recorded separately."""

from .simplified import BuzzWireSimplifiedTask


class BuzzWire3DEasierTask(BuzzWireSimplifiedTask):
    variation_id = "buzz_wire_3d_easier"
    family_id = "sideways_then_down"
    model_revision = "sideways_then_down_deck_rest_v2"
    difficulty = "easier"
    layout_resource = "variations/buzz_wire_3d/sideways_then_down_deck_rest_v2/layout.json"
