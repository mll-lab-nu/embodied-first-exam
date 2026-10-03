"""Below-easy Slotted Post: the easy tier's parts, the ring around the post, the cord re-routed.

What traps the ring is any stretch of cord that passes over it between the slot and an end disc:
the discs (110 mm) cannot pass through the ring (108 mm). ``cord_route`` sets the difficulty:

  under_ring      very_easy. As in easy the cord passes the slot once and returns round the right
                  rail, but on both sides it runs from the slot down inside the ring and out under
                  it. The ring lifts straight off over the post top.
  loop_over_ring  easier. The cord passes the slot twice (as after the first move of the standard
                  solution): both end discs lie on the near side with the cord under the ring, and
                  the far-side loop carrying bead 2 lies over the ring. Pass that loop with its bead
                  down through the gap between ring and post, then lift.

In both the ring rests on the cord at its foot. See
topogym/planning/slotted_post_ring/below_easy_witness.py. Design targets, not robot qualifications.
"""
from dataclasses import dataclass

import numpy as np

from topogym.assets.geometry.slotted_post_ring import SlottedPostLayout
from topogym.tasks.base import merge_parameters
from .slotted_post_ring_easy import SlottedPostRingEasyTask


def ring_band_runs(layout, cord):
    """Each stretch of cord within the ring's radial band: (side, 'under' | 'over' | 'through').

    side is the sign of y (-1 near, +1 far). 'under' and 'over' clear the ring's tube by a cord
    radius; 'through' would meet the ring. The ring is the layout's, around the post at ring_z.
    """
    r = np.hypot(cord[:, 0], cord[:, 1])
    band = (r > layout.ring_inner_radius - layout.rope_radius_m) & (
        r < layout.ring_major_radius_m + layout.ring_tube_radius_m + layout.rope_radius_m)
    clear = layout.ring_tube_radius_m + layout.rope_radius_m
    runs, start = [], None
    for i, inside in enumerate(np.r_[band, False]):
        if inside and start is None:
            start = i
        elif not inside and start is not None:
            z = cord[start:i, 2] - layout.ring_z
            kind = "under" if z.max() < -clear else "over" if z.min() > clear else "through"
            runs.append((int(np.sign(cord[start:i, 1].mean())), kind))
            start = None
    return runs


@dataclass(frozen=True)
class RingOnCordLayout(SlottedPostLayout):
    """The ring lies on the cord at the post's foot instead of on the base."""

    @property
    def ring_z(self):
        return self._heights()["base"] + self.rope_radius_m + self.floor_clearance_m + self.ring_tube_radius_m

    def _heights(self):
        # Cord on the base 2.5 mm higher than contact: the spline dips where the cord drops from the slot.
        c = self.floor_clearance_m
        return dict(base=self.base_height_m + self.rope_radius_m + c + .0025, bead=self.bead_radius_m + c,
                    end=self.disc_thickness_m + c + self.rope_radius_m + .002)


@dataclass(frozen=True)
class UnderRingLayout(RingOnCordLayout):
    def cord_controls(self):
        h, slot_z = self._heights(), self.slot_bottom_m + self.slot_width_m * .8
        zb, bz, end = h["base"], h["bead"], h["end"]
        return np.array([
            [-.092, -.281, end], [-.082, -.261, bz], [-.070, -.237, bz], [-.058, -.213, bz],
            [-.050, -.150, .034], [-.038, -.098, .030],
            [-.024, -.062, zb], [-.012, -.040, zb], [-.004, -.028, .060],     # under, then inside the ring
            [0, -.025, slot_z], [0, .025, slot_z],
            [.004, .028, .060], [.012, .040, zb], [.030, .066, zb],           # inside, then under the ring
            [.062, .078, zb], [.098, .040, zb], [.106, -.010, zb], [.108, -.070, zb],  # round the right rail
            [.108, -.125, .034],
            [.066, -.199, bz], [.078, -.223, bz], [.090, -.247, bz], [.104, -.277, end],
        ])

    def route_checks(self, slot_crossings, exterior_crossings, cord):
        runs = ring_band_runs(self, cord)
        return dict(super().route_checks(slot_crossings, exterior_crossings, cord),
                    cord_under_ring=len(runs) == 2 and all(kind == "under" for _, kind in runs))


@dataclass(frozen=True)
class LoopOverRingLayout(RingOnCordLayout):
    def cord_controls(self):
        h = self._heights()
        zb, bz, end = h["base"], h["bead"], h["end"]
        lane_a, lane_b = self.slot_bottom_m + .008, self.slot_bottom_m + .032
        return np.array([
            [-.092, -.281, end], [-.082, -.261, bz], [-.070, -.237, bz], [-.058, -.213, bz],
            [-.050, -.150, .034], [-.038, -.098, .030],
            [-.024, -.062, zb], [-.012, -.040, zb], [-.008, -.030, .055],     # near side: under the ring
            [-.004, -.025, lane_a], [-.004, .025, lane_a],
            [-.010, .034, .085], [-.025, .064, .064], [-.032, .095, .040],    # far side: over the ring
            [-.034, .125, bz], [-.034, .150, bz], [-.034, .175, bz],          # bead 2 at the loop's end
            [-.022, .205, .008], [.010, .212, .006], [.032, .185, .006], [.034, .140, .010],
            [.032, .100, .035], [.025, .064, .064], [.010, .034, .095],       # back over the ring
            [.004, .025, lane_b], [.004, -.025, lane_b],
            [.012, -.032, .090], [.016, -.040, .055], [.018, -.046, zb], [.026, -.062, zb],  # near side: under the ring
            [.040, -.098, .030], [.055, -.150, .030],
            [.066, -.199, bz], [.078, -.223, bz], [.090, -.247, bz], [.104, -.277, end],
        ])

    def bead_controls(self):
        return 2, 15

    def route_checks(self, slot_crossings, exterior_crossings, cord):
        runs = ring_band_runs(self, cord)
        near, far = [k for s, k in runs if s < 0], [k for s, k in runs if s > 0]
        return dict(cord_passes_slot_twice=len(slot_crossings) == 2, no_exterior_crossing=not exterior_crossings,
                    near_side_under_ring=near == ["under", "under"], far_loop_over_ring=far == ["over", "over"])


ROUTES = {"under_ring": UnderRingLayout, "loop_over_ring": LoopOverRingLayout}


class SlottedBelowEasyTask(SlottedPostRingEasyTask):
    """Shared construction; very_easy / easier set only the cord route."""

    model_revision = "below_easy_v1"
    family_id = "below_easy_cord_route"
    defaults = merge_parameters(SlottedPostRingEasyTask.defaults, {"cord_route": "under_ring"})
    fixed_parameters = (*SlottedPostRingEasyTask.fixed_parameters, "cord_route")

    def make_layout(self):
        return ROUTES[self.config["cord_route"]](**self.config["geometry"])
