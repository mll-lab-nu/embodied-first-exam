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

The cord is the team's rigid link chain (2026-10-07; topogym/assets/geometry/slotted_post_chain.py): 16.5 mm capsule
links on ball joints along the same authored route, the discs on ball joints at their eyes, the beads sliding on it. The
FEM+IPC cord of the original tiers is replaced in these two settings only; the geometry, the route and the goal stay.
"""
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import trimesh

from topogym.assets.geometry.slotted_post_chain import (
    DISC_EYE_M, chain_roots, disc_mesh, write_cord_assembly, write_ring)
from topogym.assets.geometry.slotted_post_ring import SlottedPostLayout, generate_assets, make_meshes
from topogym.assets.scene_visuals import visual_collision_urdf
from topogym.evaluation.task_metrics import body_points, quiet_body, rigid_asset_vertices
from topogym.tasks.base import merge_parameters, EntitySpec, TaskSpec
from topogym.tasks.scene_presets import record_preset
from topogym.utils.geometry.regions import placement_measurements
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

    model_revision = "below_easy_chain_v1"
    physics_model = "rigid_articulated"
    placement_attachment_names = ()
    family_id = "below_easy_cord_route"
    defaults = merge_parameters(SlottedPostRingEasyTask.defaults, {"cord_route": "under_ring"})
    fixed_parameters = (*SlottedPostRingEasyTask.fixed_parameters, "cord_route")

    def make_layout(self):
        return ROUTES[self.config["cord_route"]](**self.config["geometry"])

    def chain_parts(self):
        """The authored layout, meshes and cord, the link joints, the disc centres and the beads, without writing assets."""
        layout = self.make_layout().validate()
        parts, cord = make_meshes(layout)
        discs = [np.r_[parts[f"disc_{side}"].bounds.mean(axis=0)[:2], layout.floor_clearance_m] for side in ("left", "right")]
        beads = []
        for name, index in zip(("bead_left", "bead_right"), layout.bead_controls()):
            k = int(np.argmin(np.linalg.norm(cord-layout.cord_controls()[index], axis=1)))
            beads.append((name, cord[k], cord[k+1]-cord[k-1]))
        return layout, parts, cord, chain_roots(layout, cord, discs), discs, beads

    def declare(self, asset_dir, table_height_m):
        self.table_height_m = float(table_height_m)
        preset = record_preset(self, asset_dir)
        xy = np.asarray(self.config["center_xy_m"], dtype=float)
        if xy.shape != (2,) or not np.isfinite(xy).all():
            raise ValueError("Invalid Slotted Post Ring center_xy_m")
        origin = tuple(np.r_[xy, table_height_m])
        self.layout, report = generate_assets(asset_dir, self.make_layout())
        layout, parts, cord, roots, discs, beads = self.chain_parts()
        folder = Path(asset_dir)
        xml, self.link_names, self.link_lengths, self.link_reversed = write_cord_assembly(folder, layout, roots, discs, beads)
        ring_xml, ring_mass = write_ring(folder, layout, layout.ring_z)
        entities = [EntitySpec(name, "urdf", visual_collision_urdf(folder, name), origin, fixed=True,
                               morph_options={"convexify": False, "decimate": False, "file_meshes_are_zup": True,
                                              "align": False, "merge_fixed_links": False})
                    for name in ("base", "post")]
        entities += [EntitySpec("target_ring", "mjcf", ring_xml, origin), EntitySpec("cord", "mjcf", xml, origin)]
        # Authored geometry in each entity's frame (the goal region's separator) and in each body's frame (evaluation).
        self.placement_vertices = {e.name: rigid_asset_vertices(e) for e in entities[:2]}
        self.placement_vertices["target_ring"] = np.asarray(parts["target_ring"].vertices)
        self.placement_vertices["cord"] = np.vstack([cord, *(parts[n].vertices for n in (
            "disc_left", "disc_right", "bead_left", "bead_right"))])
        disc = np.asarray(disc_mesh(layout).vertices)+[0., -DISC_EYE_M, -layout.disc_thickness_m]
        bead = np.asarray(trimesh.creation.icosphere(subdivisions=2, radius=layout.bead_radius_m).vertices)
        self.body_vertices = dict(target_ring=self.placement_vertices["target_ring"]-[0., 0., layout.ring_z],
                                  disc_left=disc, disc_right=disc, bead_left=bead, bead_right=bead)
        self.placement_targets = ("target_ring",)
        self.placement_remainder = ("base", "post", "cord")
        return TaskSpec(
            tuple(entities),
            {"rigid": {"enable_self_collision": True, "constraint_solver": "CG"}},
            dict(
                **preset,
                assembly_origin_m=list(origin),
                task_id=self.task_id,
                cord_chain=dict(links=len(self.link_names), radius_m=layout.rope_radius_m,
                                link_lengths_m=[float(v) for v in self.link_lengths],
                                length_m=float(self.link_lengths.sum()), ring_mass_kg=float(ring_mass)),
                geometry_report=report,
                permanent_connections=["cord ends to the disc eyes (ball joints)", "links (ball joints)"],
                goal_evaluation_complete=bool(self.goal_complete),
            ),
        )

    def link_cover(self, length):
        """Capsule axis ends and their radial extremes, in the link frame."""
        r = self.layout.rope_radius_m
        return np.array([[x, *offset] for x in (0., length) for offset in
                         ((0., 0.), (r, 0.), (-r, 0.), (0., r), (0., -r))])

    def evaluate_goal_region(self, state, region):
        """The whole ring inside the goal and still; the fixture, chain, discs and beads on the system side."""
        links = state["articulations"]["cord"]["links"]
        ring = state["bodies"]["target_ring"]
        cord = [body_points(links[name], self.link_cover(length))
                for name, length in zip(self.link_names, self.link_lengths)]
        cord += [body_points(links[name], self.body_vertices[name])
                 for name in ("disc_left", "disc_right", "bead_left", "bead_right")]
        remainder = {name: body_points(state["bodies"][name], self.placement_vertices[name]) for name in ("base", "post")}
        remainder["cord"] = np.vstack(cord)
        metrics = placement_measurements(region, {"target_ring": body_points(ring, self.body_vertices["target_ring"])},
                                         remainder)
        quiet = quiet_body(ring)
        metrics.update(quiet=bool(quiet), connections_intact=True, evaluation_status="available", holding_allowed=True)
        reached = metrics["all_target_inside"] and metrics["remainder_on_system_side"] and quiet
        return bool(reached), None, metrics
