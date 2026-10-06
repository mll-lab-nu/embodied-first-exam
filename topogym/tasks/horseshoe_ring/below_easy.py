"""Below-easy Horseshoe: the easy tier's shoes and chains with a larger ring, still around both chains.

With one shoe held up, the chains hang along one axis. Seen along that axis a shoe is a bar of
about 138 x 25 mm, and the ring comes off by sliding along the chains over the lower shoe once
its bore holds that bar. The bore sets the difficulty: a round 144 mm bore (very_easy) holds the
bar at every phase about the chain axis; a 146 x 136 mm ellipse (easier) at 61 of the 90 phases
(2 deg apart) with up to 4.0 mm to spare, so the ring passes at most phases and needs a turn at
the others. The current easy tier's enlarged ring (142.6 x 135.9 mm) passes at 53 phases with up
to 2.3 mm, the original easy ring (135 x 128 mm) at none: very_easy < easier < easy. (The first
easier draft, 146 x 120 mm, passed at only 27 phases: harder than the enlarged easy ring.)
Knob: ``ring``. Each setting starts from its own
gravity-settled layout. See topogym/planning/horseshoe_ring/below_easy_witness.py. These are
design targets, not robot qualifications.
"""
from copy import deepcopy

from topogym.tasks.base import merge_parameters
from .horseshoe_ring_easy import HorseshoeRingEasyTask


def ring(long_mm, short_mm):
    """Ring bore (inner long and short axes, mm); the wire stays the easy ring's."""
    return {"bore_mm": [float(long_mm), float(short_mm)]}


class HorseshoeBelowEasyTask(HorseshoeRingEasyTask):
    """Shared construction; very_easy / easier set the ring bore and their settled layout."""

    model_revision = "below_easy_v1"
    family_id = "below_easy_ring_bore"
    defaults = merge_parameters(HorseshoeRingEasyTask.defaults, {"ring": ring(144., 144.)})
    fixed_parameters = ("scale", "ring")
    layout_resource = None

    def template(self):
        template = deepcopy(super().template())
        wire, scale = template["target_ring"]["wire_radius"], float(self.config["scale"])
        template["template_id"] += "+below_easy"
        template["target_ring"]["centerline_radii"] = [b / (2 * scale) + wire for b in self.config["ring"]["bore_mm"]]
        return template
