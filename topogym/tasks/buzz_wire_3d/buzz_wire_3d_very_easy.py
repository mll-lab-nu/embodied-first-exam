"""Approved straight-span layout; physical qualification is recorded separately."""

from .simplified import BuzzWireSimplifiedTask


class BuzzWire3DVeryEasyTask(BuzzWireSimplifiedTask):
    variation_id = "buzz_wire_3d_very_easy"
    family_id = "straight_span"
    model_revision = "straight_span_deck_rest_v1"
    difficulty = "very_easy"
    layout_resource = "variations/buzz_wire_3d/straight_span_deck_rest_v1/layout.json"
