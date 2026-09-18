"""Bar Through Hole (docx 2.3): push a rigid shaft through a bulkhead aperture.

Scene: a vertical bulkhead panel standing on the table with a **hexagonal**
aperture, a hex shaft resting on two open cradles, and a far cradle whose top is
level with the aperture sill so the threaded shaft lands on two supports.

Both the shaft and the bore are regular hexagonal prisms, sized by their
across-flats dimension -- the way hex stock and hex broaches are actually
specified. The profile is oriented flat-side-down, which is why the cradles are
plain open blocks: a hex bar rests on a face and cannot roll, so the anti-roll
chocks an earlier round shaft needed are gone.

The panel's aperture is a compound of convex boxes rather than a mesh with a
hole: `gs.morphs.Mesh(convexify=True)` fills holes in, so the repo's standing
answer for a non-convex fixture is a compound of convex parts -- see
`_add_routing_post` in `./cable_routing.py`. Four boxes give a rectangular
opening at the hexagon's bounding box, and four more, each rotated onto one
slanted hex edge, cut the remaining corner triangles away.

The shaft itself IS convex, so it is a generated mesh loaded with
`convexify=True`: the convex hull of a hex prism is the prism, i.e. collision is
exact rather than approximated.

The panel is deliberately short (top 0.150) so two things hold at once: the
default home pose's fingertips (task z 0.1608) clear it without a task-local
robot config, and lifting the shaft *over* the top stays physically available --
that bypass is the task's anti-shortcut, and it must remain reachable to be
judged a failure.

STAGING (intentional, not an oversight): this is stage 1 -- scene, verifier,
primitive, demo. There is no `generation/bar_through_hole_generator.py` and no
rollout contrast pair yet, so per `docs/develop/framework/task_taxonomy_zh.md`
Section 4.0 this task does NOT yet qualify for benchmark artifacts. Stage 2 adds
the generator and the over-the-top contrast episode.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import genesis as gs
import numpy as np
from omegaconf import OmegaConf

from topogym.core import EntityManifest
from topogym.primitives.pick_place import HAND_TO_PAD_Z
from topogym.tasks_legacy._fixtures import add_v_block, v_block_seat_drop
from topogym.tasks_legacy.entangle._c_ring_geometry import HOME_FINGERTIP_Z
from topogym.tasks_legacy._visuals import (
    add_aperture_ring,
    add_industrial_pedestal,
    add_panel_bolts,
    box_entity_enabled,
)
from topogym.world import StandardTabletopSceneBuilder, TabletopBaseScene, materials
from topogym.world.rope import resolve_mesh_dir, write_obj


def _list(value):
    if OmegaConf.is_config(value):
        value = OmegaConf.to_container(value, resolve=True)
    return value


# Where the cradles sit relative to what they serve, in metres along x. The two
# near blocks bracket the shaft's rest centre; `near_b` and `far` are placed from
# the shaft's END so a short shaft still spans them. On the baseline config these
# reproduce the hand-placed values -0.070 / 0.020 / 0.200 exactly.
NEAR_A_BEHIND_CENTRE = 0.020
END_SETBACK = 0.030
# How far the shaft's rest end, the nearer cradle, and the hand at seat must all
# stop short of the panel's near face; and how much shaft must remain beyond the
# grasp point / past a cradle's jaw so the fingers close on bare stock.
PANEL_MARGIN = 0.010
#: Thinnest run of solid panel the bores may leave -- between the outermost bore
#: and the panel's edge, or between two neighbours. Two mullions at 42 mm is the
#: tightest the pitch envelope produces; 20 mm leaves the frame something to be.
PANEL_STRIP_MIN = 0.020
FINGER_MARGIN = 0.015


def regular_polygon_vertices(sides: int, across_flats: float) -> np.ndarray:
    """The corners of a regular polygon in the (y, z) plane, flat side down.

    Flat-side-down is the orientation that lets the shaft rest without rolling
    and lets it seat on the aperture's lower edge, so the vertex angles are
    offset by half a step from the bottom: the two corners either side of
    straight down sit symmetrically about it, leaving a horizontal edge there
    (and, for an even number of sides, another at the top).

    ``across_flats`` is the inscribed diameter (2 * inradius) -- the dimension
    hex stock is sold by, kept for round stock too so one number sizes both.
    The circumradius is ``inradius / cos(pi / sides)``.

    2026-09-08: generalised from a hexagon-only version. The shaft and the bore
    are 16-sided by default, which reads as round at the scene's camera distance
    while keeping three things a cylinder would cost: the mesh is generated
    axis-along-X so the entity needs no spawn rotation, ``convexify=True`` is
    exact on a prism rather than an approximation, and the verifier can go on
    reading the shaft direction as ``R @ (1, 0, 0)``. Six is still available as
    a variant (`bar.sides` / `aperture.sides`).
    """

    sides = int(sides)
    if sides < 3:
        raise ValueError(f"a polygon needs at least 3 sides, got {sides}.")
    inradius = 0.5 * float(across_flats)
    circumradius = inradius / float(np.cos(np.pi / sides))
    step = 360.0 / sides
    angles = np.deg2rad(270.0 + 0.5 * step + np.arange(sides) * step)
    return np.stack([circumradius * np.cos(angles), circumradius * np.sin(angles)], axis=1)


def polygon_extents(corners) -> tuple[float, float]:
    """``(half width in y, half height in z)`` of a profile's bounding box.

    The frame around an aperture is built on the bore's bounding rectangle, and
    where that rectangle sits depends on the number of sides: a hexagon's widest
    points are corners (circumradius), a 16-gon's are the middles of its flat
    sides (inradius). Reading it off the corners is what keeps the frame right
    for both instead of only for the one it was written against.
    """

    corners = np.asarray(corners, dtype=float).reshape(-1, 2)
    return float(np.abs(corners[:, 0]).max()), float(np.abs(corners[:, 1]).max())


def prism_mesh(sides: int, across_flats: float, length: float) -> tuple[np.ndarray, np.ndarray]:
    """A regular prism with its axis along local +X.

    Local frame: cross-section in the YZ plane (flat side down, see
    `regular_polygon_vertices`), extruded along X and centred on the origin.
    Axis-along-X is chosen so the entity needs no spawn rotation and the verifier
    can read the shaft direction as ``R @ (1, 0, 0)``.

    Faces are 0-indexed triangles for `topogym.world.rope.write_obj`.
    """

    sides = int(sides)
    half = 0.5 * float(length)
    corners = regular_polygon_vertices(sides, across_flats)
    verts = [[-half, y, z] for y, z in corners] + [[half, y, z] for y, z in corners]
    faces: list[list[int]] = []
    for i in range(sides):
        j = (i + 1) % sides
        # side quad, split into two triangles, wound outward
        faces.append([i, j, j + sides])
        faces.append([i, j + sides, i + sides])
    for k in range(1, sides - 1):  # fan each cap from its first corner
        faces.append([0, k + 1, k])
        faces.append([sides, sides + k, sides + k + 1])
    return np.asarray(verts, dtype=float), np.asarray(faces, dtype=int)


@dataclass(frozen=True)
class BarThroughHoleLayout:
    """Panel, aperture, shaft, and cradle geometry for Bar Through Hole."""

    cfg: Any
    task_origin: tuple[float, float, float] = (0.0, 0.0, 0.0)

    @property
    def coordinate_frame(self) -> str:
        return str(getattr(self.cfg, "coordinate_frame", "world"))

    def position_to_world(self, position) -> np.ndarray:
        pos = np.asarray(_list(position), dtype=float)
        if pos.shape != (3,):
            raise ValueError(f"Position must have shape (3,), got {pos}.")
        if self.coordinate_frame == "world":
            return pos
        if self.coordinate_frame == "task":
            return pos + np.asarray(self.task_origin, dtype=float)
        raise ValueError(
            f"Unsupported BarThroughHole coordinate_frame={self.coordinate_frame!r}; "
            "expected 'world' or 'task'."
        )

    def world_z(self, z: float) -> float:
        if self.coordinate_frame == "world":
            return float(z)
        if self.coordinate_frame == "task":
            return float(self.task_origin[2]) + float(z)
        raise ValueError(
            f"Unsupported BarThroughHole coordinate_frame={self.coordinate_frame!r}; "
            "expected 'world' or 'task'."
        )

    # ----- panel / aperture -------------------------------------------------

    @property
    def panel_x(self) -> float:
        return float(self.cfg.panel.x)

    @property
    def panel_thickness(self) -> float:
        return float(self.cfg.panel.thickness)

    def panel_plane(self) -> tuple[np.ndarray, np.ndarray]:
        """The panel's mid-plane as (point, unit normal) in world coordinates.

        The verifier's threading count is defined against this plane, so it is
        published here rather than recomputed there -- the reference surface and
        the collision geometry must not be able to drift apart.
        """

        point = self.position_to_world((self.panel_x, 0.0, 0.0))
        return point, np.array([1.0, 0.0, 0.0], dtype=float)

    def aperture_center(self) -> np.ndarray:
        """World centre of the bore the shaft has to go through.

        **The one place the task asks where the hole is.** The oracle's insertion
        target and the verifier's threading test both read it (the demo's
        `insert_part_xy`, the evaluator's `aperture_center_yz`), so a hole that
        moves is followed by both without either of them knowing it moved.

        `center_y` was a hard-coded 0.0 until 2026-09-08, when the panel grew two
        more holes and only one of them stayed on the centreline.

        The y is COMPUTED from `open_index` and `pitch` rather than read back from
        the derived `aperture.center_y` leaf. Both exist: the leaf is what gets
        recorded into the episode's variant, the computation is what the task
        acts on, and `checks()` proves they agree. Reading the leaf here would
        mean a path that skips derivation (any fixed-layout run -- every demo
        invocation that is not randomised) silently aims at the middle bore
        whatever `open_index` says. That is exactly what happened on the first
        try: the shaft was driven at a blind bore and the judge, reading the same
        stale leaf, called it a success.
        """

        return self.position_to_world(self.aperture_center_task())

    def aperture_center_task(self) -> np.ndarray:
        """The same point in the task frame, for the feasibility rows.

        `checks()` is task-frame arithmetic throughout, so it reads this rather
        than undoing `position_to_world` -- two readers of one fact instead of
        two ways of computing it.
        """

        return np.array(
            [
                self.panel_x,
                self.aperture_center_y(int(self.cfg.aperture.open_index)),
                float(self.cfg.aperture.center_z),
            ],
            dtype=float,
        )

    def aperture_center_y(self, index: int) -> float:
        """Task-frame y of hole ``index``, counting from the -y side.

        The holes are evenly spaced about the panel's centreline, so hole 1 of 3
        sits on it and the outer two are one `pitch` either side. Which one is
        open is `aperture.open_index`; the other two are blind (`_add_panel`).
        """

        count = int(self.cfg.aperture.count)
        return (float(index) - 0.5 * (count - 1)) * float(self.cfg.aperture.pitch)

    def aperture_centers_y(self) -> list[float]:
        """Task-frame y of every hole, open and blind alike, in index order."""

        return [self.aperture_center_y(i) for i in range(int(self.cfg.aperture.count))]

    @property
    def aperture_across_flats(self) -> float:
        return float(self.cfg.aperture.across_flats)

    @property
    def aperture_inradius(self) -> float:
        return 0.5 * self.aperture_across_flats

    @property
    def aperture_sides(self) -> int:
        return int(self.cfg.aperture.sides)

    @property
    def aperture_circumradius(self) -> float:
        return self.aperture_inradius / float(np.cos(np.pi / self.aperture_sides))

    def aperture_profile(self) -> np.ndarray:
        """The bore's corners about its own centre, (N, 2) as (y, z)."""

        return regular_polygon_vertices(self.aperture_sides, self.aperture_across_flats)

    def aperture_bbox(self) -> tuple[tuple[float, float], tuple[float, float]]:
        """The bore's bounding box as ((y_min, y_max), (z_min, z_max)), world.

        This is the rectangular opening the frame boxes leave; the corner boxes
        then trim it down to the polygon itself. Read off the corners rather than
        assumed: a hexagon's widest points are corners (circumradius) while a
        16-gon's are the middles of its flat sides (inradius), so hard-coding
        either one gets the frame wrong for the other.
        """

        center = self.aperture_center()
        half_y, half_z = polygon_extents(self.aperture_profile())
        return (
            (float(center[1] - half_y), float(center[1] + half_y)),
            (float(center[2] - half_z), float(center[2] + half_z)),
        )

    def sill_top_z(self) -> float:
        """World z of the aperture's flat lower edge -- what a threaded shaft rests on."""

        return float(self.aperture_center()[2] - self.aperture_inradius)

    # ----- shaft ------------------------------------------------------------

    @property
    def bar_length(self) -> float:
        return float(self.cfg.bar.length)

    @property
    def bar_across_flats(self) -> float:
        return float(self.cfg.bar.across_flats)

    @property
    def bar_inradius(self) -> float:
        """Half the across-flats size: how far the flat bottom sits below the axis."""

        return 0.5 * self.bar_across_flats

    @property
    def bar_sides(self) -> int:
        return int(self.cfg.bar.sides)

    @property
    def bar_circumradius(self) -> float:
        return self.bar_inradius / float(np.cos(np.pi / self.bar_sides))

    def bar_rest_center(self) -> np.ndarray:
        bar = self.cfg.bar
        return self.position_to_world((float(bar.rest_x), float(bar.rest_y), float(bar.rest_z)))

    def grasp_offset(self) -> float:
        """Signed x distance from the grasp point to the shaft centre.

        Positive: the hand grips *behind* the centre, so the hand can stop short
        of the panel while the shaft's leading half is already through. Sized in
        the config from the hand's own half-depth plus the panel half-thickness.
        """

        return float(self.cfg.bar.grasp_offset)

    def grasp_xy(self) -> np.ndarray:
        """World xy the gripper descends on to pick the shaft up."""

        center = self.bar_rest_center()
        return np.array([center[0] - self.grasp_offset(), center[1]], dtype=float)

    # Where the hand goes is not published here: it is the shaft's target minus the
    # offset the pair actually ends up with, which only the primitive can measure
    # after the lift. A precomputed hand xy assumes the shaft is exactly on its
    # nominal spot, and every millimetre it is not comes straight out of the bore's
    # clearance.

    # The anti-shortcut rollout aims at the same aperture centre and differs only
    # in carry height: identical start and end xy, different trajectory homotopy.
    # That is what docx asks a contrast pair to be, and it keeps the hand behind
    # the panel plane -- carrying the shaft to the far side would drag the forearm
    # across the panel, which is the failure cable_routing documented.

    # ----- cradles ----------------------------------------------------------

    def cradle_specs(self) -> tuple[tuple[str, Any], ...]:
        cradles = getattr(self.cfg, "cradles", None)
        if cradles is None:
            return ()
        return tuple((str(name), spec) for name, spec in cradles.items())

    def bar_profile(self) -> np.ndarray:
        """The shaft's cross-section, as the V-blocks and the bore both read it."""

        return regular_polygon_vertices(self.bar_sides, self.bar_across_flats)

    def cradle_apex_z(self, spec) -> float:
        """Groove bottom for a cradle, from the axis height its config asks for.

        Config states `seat_axis_z` -- where the shaft's AXIS ends up -- because
        that is the number the rest of the task is written against: the rest pose,
        the grasp height, and the far cradle's agreement with the aperture sill.
        The apex is derived from it and the shaft's profile, so changing the
        shaft's size moves the grooves instead of silently changing where it sits.
        """

        half_angle = np.deg2rad(float(getattr(spec, "half_angle_deg", 45.0)))
        return float(spec.seat_axis_z) - v_block_seat_drop(self.bar_profile(), half_angle)

    def cradle_jaw_top_z(self, spec) -> float:
        """Task-frame z of the top of a cradle's slanted jaws -- what a passing shaft must clear."""

        half_angle = np.deg2rad(float(getattr(spec, "half_angle_deg", 45.0)))
        return self.cradle_apex_z(spec) + float(spec.jaw_width) * float(np.cos(half_angle))

    # ----- derived layout (variation) ----------------------------------------
    #
    # Task-frame numbers throughout. These are the formulas the yaml's
    # ``variation:`` block names through `derive_task_cfg`; the fixed-layout path
    # never calls them, so the hand-written baseline values stay authoritative
    # there and `tests/check_bar_through_hole_geometry.py` pins the two to agree.

    def panel_near_face_x(self) -> float:
        return self.panel_x - 0.5 * self.panel_thickness

    def sill_task_z(self) -> float:
        """Task-frame z of the aperture's flat lower edge (see `sill_top_z` for world)."""

        return float(self.cfg.aperture.center_z) - self.aperture_inradius

    def length_bounds(self) -> tuple[float, float]:
        """Where the shaft length may fall: the config's range, capped so the
        shaft's rest end stops `PANEL_MARGIN` short of the panel's near face."""

        lo, hi = (float(v) for v in _list(self.cfg.bar.length_range))
        cap = 2.0 * (self.panel_near_face_x() - PANEL_MARGIN - float(self.cfg.bar.rest_x))
        hi = min(hi, cap)
        if hi < lo:
            raise ValueError(
                f"No shaft length fits: range [{lo:.3f}, {hi:.3f}] is empty with the shaft "
                f"at x={float(self.cfg.bar.rest_x):+.3f} and the panel at x={self.panel_x:.3f}."
            )
        return lo, hi

    def length_from_frac(self, frac: float) -> float:
        lo, hi = self.length_bounds()
        return lo + (hi - lo) * float(np.clip(frac, 0.0, 1.0))

    def grasp_offset_bounds(self) -> tuple[float, float]:
        """Where the grasp offset may fall: the config's range, capped so the pads
        still close on shaft (`FINGER_MARGIN` of stock beyond the grasp point)."""

        lo, hi = (float(v) for v in _list(self.cfg.bar.grasp_offset_range))
        hi = min(hi, 0.5 * self.bar_length - FINGER_MARGIN)
        if hi < lo:
            raise ValueError(
                f"No grasp offset fits: range [{lo:.3f}, {hi:.3f}] is empty for a "
                f"{self.bar_length:.3f} m shaft."
            )
        return lo, hi

    def grasp_offset_from_frac(self, frac: float) -> float:
        lo, hi = self.grasp_offset_bounds()
        return lo + (hi - lo) * float(np.clip(frac, 0.0, 1.0))

    def cradle_x(self, name: str) -> float:
        """Where a cradle belongs given the shaft, the panel, and the shaft length."""

        half = 0.5 * self.bar_length
        rest_x = float(self.cfg.bar.rest_x)
        if name == "near_a":
            return rest_x - NEAR_A_BEHIND_CENTRE
        if name == "near_b":
            return rest_x + half - END_SETBACK
        if name == "far":
            return self.panel_x + half - END_SETBACK
        raise KeyError(name)

    def seated_axis_z(self) -> float:
        """Axis height of a shaft resting in the bore, flat-side-down on the sill.

        Named for the bore rather than for the cradle that used to share it: the
        far cradle was retired 2026-09-08 and the shaft is now held by the bore
        alone. The verifier reads the same quantity (`seated_z`).
        """

        return self.sill_task_z() + self.bar_inradius

    def cradle_y(self, name: str) -> float:
        """Task-frame y of a cradle's groove.

        The near blocks sit under the resting shaft, so they follow `bar.rest_y`;
        the far block catches the shaft where the bore puts it, on the panel's
        centreline. Was a hard-coded 0.0 for all three until 2026-09-04: the
        first variation corner with `rest_y` != 0 spawned the shaft beside its
        grooves, it fell to the table, and the pads closed on air above it.
        """

        if name in ("near_a", "near_b"):
            return float(self.cfg.bar.rest_y)
        if name == "far":
            return 0.0
        raise KeyError(name)

    # ----- derived heights (task frame, hand-link z) --------------------------

    def grasp_hand_z(self) -> float:
        """Pads centred on the resting shaft's axis."""

        return float(self.cfg.bar.rest_z) + HAND_TO_PAD_Z

    def lift_hand_z(self) -> float:
        return self.grasp_hand_z() + float(self.cfg.primitive.lift_height)

    def push_window(self) -> tuple[float, float]:
        """Task-frame z range the shaft's AXIS may occupy during the horizontal push.

        Lower bound: the shaft's flat bottom clears every cradle's jaw tops (the
        far cradle's dominate, since its seat follows the sill). Upper bound: the
        shaft's flat top stays under the aperture's upper edge. Both are
        one-inradius offsets from the axis because the shaft lies flat-side-down.
        """

        clearance = self.aperture_inradius - self.bar_inradius
        center_z = float(self.cfg.aperture.center_z)
        jaw_tops = [
            self.cradle_jaw_top_z(spec)
            for _, spec in self.cradle_specs()
            if bool(getattr(spec, "enabled", True))
        ]
        lo = max([center_z - clearance] + [top + self.bar_inradius for top in jaw_tops])
        hi = center_z + clearance
        return lo, hi

    def push_center_z(self) -> float:
        lo, hi = self.push_window()
        return 0.5 * (lo + hi)

    def insert_hand_z(self) -> float:
        return self.push_center_z() + HAND_TO_PAD_Z

    def seat_hand_z(self) -> float:
        """Shaft bottom `seat_drop` above the sill when the pads open."""

        return self.sill_task_z() + float(self.cfg.primitive.seat_drop) + self.bar_inradius + HAND_TO_PAD_Z

    # ----- solvability -------------------------------------------------------

    def checks(self) -> list[tuple[str, float, float, bool]]:
        """``[(name, measured, limit, ok)]``: what a solvable, buildable layout needs.

        One list for the randomizer's reject step, the offline gate, the corner
        harness and the demo's start-up print. Metres throughout.
        """

        bar = self.cfg.bar
        primitive = self.cfg.primitive
        cradles = self.cfg.cradles
        half = 0.5 * self.bar_length
        rest_x = float(bar.rest_x)
        near_face = self.panel_near_face_x()
        grasp_x = rest_x - self.grasp_offset()
        lo, hi = self.push_window()
        seat_hand_x = self.panel_x - self.grasp_offset()
        base_x, base_y = (float(v) for v in _list(self.cfg.reach.base_xy))
        # The hand ends up at the HOLE's y, not at the y the shaft started on.
        # Those were within 0.7 mm of each other while every hole sat on the
        # panel's centreline, so reading `bar.rest_y` here never showed; with the
        # holes a `pitch` apart it would under-report the reach by 8 mm.
        seat_hand_y = float(self.aperture_center_task()[1])
        reach = float(np.hypot(seat_hand_x - base_x, seat_hand_y - base_y))
        ge = [
            ("push_window", hi - lo, 2.0 * float(primitive.push_clearance_min)),
            ("bar_end_clears_panel", near_face - (rest_x + half), PANEL_MARGIN),
            (
                "near_cradle_clears_panel",
                near_face - (float(cradles.near_b.x) + 0.5 * float(cradles.near_b.length_x)),
                PANEL_MARGIN,
            ),
            ("grasp_on_shaft", half - self.grasp_offset(), FINGER_MARGIN),
            (
                "grasp_clears_near_a",
                abs(grasp_x - float(cradles.near_a.x)) - 0.5 * float(cradles.near_a.length_x),
                FINGER_MARGIN,
            ),
            (
                "hand_short_of_panel",
                near_face - (seat_hand_x + float(primitive.hand_half_depth)),
                PANEL_MARGIN,
            ),
            # Guards edits rather than draws: no axis moves the panel's top.
            ("panel_clears_home", HOME_FINGERTIP_Z - float(self.cfg.panel.top_z), 0.0),
        ]
        rows = [(name, value, limit, value >= limit - 1e-9) for name, value, limit in ge]
        rows.append(("hand_reach", reach, float(self.cfg.reach.max_hand_dist), reach <= float(self.cfg.reach.max_hand_dist) + 1e-9))
        # The shaft and the bore are the same kind of cross-section, or "how much
        # wider the hole is than the shaft" -- the quantity the difficulty axis is
        # written in -- has no meaning. Read as a difference so the row prints
        # which two numbers disagree.
        rows.append(
            ("profiles_match", float(self.aperture_sides - self.bar_sides), 0.0,
             self.aperture_sides == self.bar_sides)
        )
        # The outermost bore has to leave a post between it and the panel's edge,
        # and neighbouring bores a mullion between them. Both are the same
        # measurement -- the narrowest strip of solid panel the frame is left
        # with -- so the row reads that rather than the two separately.
        rows.append(
            ("panel_strip", self.narrowest_panel_strip(), PANEL_STRIP_MIN,
             self.narrowest_panel_strip() >= PANEL_STRIP_MIN - 1e-9)
        )
        # The recorded `aperture.center_y` has to be the bore the task is aiming
        # at. It is derived, so on a randomised run it always is; this catches a
        # hand-written layout, or a derivation that stopped being run.
        center_y_gap = abs(
            float(self.cfg.aperture.center_y) - float(self.aperture_center_task()[1])
        )
        rows.append(
            ("center_y_recorded", center_y_gap, 1e-9, center_y_gap <= 1e-9)
        )
        return rows

    def max_shaft_center_x(self, shaft_y: float) -> float:
        """Furthest the shaft's centre may travel before it meets solid panel.

        Task frame. ``inf`` when the shaft is lined up with the open bore and
        goes straight through.

        The carry is assisted -- `AttachmentManager` writes the shaft's pose every
        step rather than pushing it -- so nothing in the solver stops a shaft
        driven at a blind bore or at the wall between two of them. That would
        leave the picture and the physics disagreeing: a sealed hole that the
        shaft passes through anyway, which is the one thing a policy trained from
        these pictures must never see. So the limit is stated here and the
        attachment clamps to it.

        Three cases, decided by how much of the shaft's own cross-section fits:
        lined up with the open bore, it is unlimited; lined up with a blind one,
        the shaft's leading end stops at that bore's plug; anywhere else it stops
        at the panel's near face.
        """

        clearance = self.aperture_inradius - self.bar_inradius
        half = 0.5 * self.bar_length
        near_face = self.panel_near_face_x()
        recess = float(self.cfg.aperture.blind_recess)
        open_index = int(self.cfg.aperture.open_index)
        for index, centre in enumerate(self.aperture_centers_y()):
            if abs(float(shaft_y) - centre) > clearance:
                continue
            if index == open_index:
                return float("inf")
            # The plug fills the bore from the far face inward, so its near face
            # is one recess in from the panel's.
            return near_face + recess - half
        return near_face - half

    def narrowest_panel_strip(self) -> float:
        """The thinnest run of solid panel the bores leave, in metres.

        Between the outermost bore and the panel's edge, and between each pair of
        neighbours. `_add_panel` builds exactly these strips, so a layout that
        fails here is one the builder would have to raise on.
        """

        half_y, _ = polygon_extents(self.aperture_profile())
        edges = [-0.5 * float(self.cfg.panel.width)]
        for centre in self.aperture_centers_y():
            edges.extend((centre - half_y, centre + half_y))
        edges.append(0.5 * float(self.cfg.panel.width))
        return float(min(edges[k + 1] - edges[k] for k in range(0, len(edges) - 1, 2)))

    def validate(self) -> None:
        """Refuse a layout that fails any check, instead of building it anyway."""

        for name, measured, limit, ok in self.checks():
            if not ok:
                raise ValueError(
                    f"bar_through_hole layout check {name} failed: "
                    f"measured {measured:+.4f} against {limit:+.4f}."
                )


def derive_task_cfg(task_cfg) -> None:
    """Derivation hook named by the task yaml's ``variation:`` block.

    Runs after the axes are drawn and before ``validate_task_cfg``. Order
    matters: the length (needs the panel and the rest x), then the grasp offset
    (needs the length), then the two near cradles (need the length).
    A ``ValueError`` (empty range) rejects the draw.

    The far cradle's x and seat height were derived here too until 2026-09-08,
    when the cradle itself was retired: the shaft is held by the bore alone.
    """

    layout = BarThroughHoleLayout(task_cfg)
    task_cfg.bar.length = layout.length_from_frac(float(task_cfg.bar.length_frac))
    task_cfg.bar.grasp_offset = layout.grasp_offset_from_frac(float(task_cfg.bar.grasp_frac))
    for name in ("near_a", "near_b"):
        task_cfg.cradles[name].x = layout.cradle_x(name)
    # Which bore is open decides where the shaft has to go, and that is the one
    # place the rest of the task asks (`aperture_center`).
    task_cfg.aperture.center_y = layout.aperture_center_y(int(task_cfg.aperture.open_index))


def validate_task_cfg(task_cfg) -> None:
    """Validation hook named by the task yaml's ``variation:`` block.

    `layout_randomization.randomize_task_cfg` calls it after each draw; a
    ``ValueError`` rejects the draw and the whole set of axes is resampled.
    """

    BarThroughHoleLayout(task_cfg).validate()


@dataclass
class BarThroughHoleScene:
    scene: Any
    manifest: EntityManifest
    layout: BarThroughHoleLayout
    cameras: dict = field(default_factory=dict)
    tabletop: TabletopBaseScene | None = None

    def bar_entity(self):
        return self.manifest.get("bar")


class BarThroughHoleSceneBuilder:
    """Build the common table plus the bulkhead panel, shaft, and cradles."""

    def __init__(self, env_cfg, task_cfg, robot_cfg, *, rigid_options=None) -> None:
        self.env_cfg = env_cfg
        self.task_cfg = task_cfg
        self.robot_cfg = robot_cfg
        self.rigid_options = rigid_options

    def build(self, *, show_viewer: bool = False, before_finalize=None) -> BarThroughHoleScene:
        tabletop_builder = StandardTabletopSceneBuilder(
            self.env_cfg,
            self.robot_cfg,
            rigid_options=self.rigid_options,
        )
        tabletop = tabletop_builder.create(show_viewer=show_viewer)
        scene = tabletop.scene
        manifest = tabletop.manifest

        layout = BarThroughHoleLayout(self.task_cfg, task_origin=tabletop.frames.task_origin)
        layout.validate()
        self._add_panel(scene, manifest, layout)
        self._add_cradles(scene, manifest, layout)
        self._add_bar(scene, manifest, layout)
        self._add_visual_details(scene, manifest, layout)

        # Rendering sensors and visual finishes must be added before scene.build().
        if before_finalize is not None:
            before_finalize(tabletop)
        tabletop_builder.finalize(tabletop)
        return BarThroughHoleScene(
            scene=scene,
            manifest=manifest,
            layout=layout,
            cameras=tabletop.cameras,
            tabletop=tabletop,
        )

    # ------------------------------------------------------------------ panel

    def _add_panel(self, scene, manifest: EntityManifest, layout: BarThroughHoleLayout) -> None:
        """Convex boxes whose union is a wall with `aperture.count` bores in a row.

        Three groups. The frame -- two end posts, a mullion between each pair of
        neighbouring bores, and a sill and lintel spanning the whole width --
        leaves one rectangular opening per bore at that bore's bounding box; its
        faces are tiled edge-to-edge, never overlapped, because coincident faces
        z-fight in the rasterizer. The corner pieces then lie along the slanted
        edges of each bore and cut its rectangle down to the polygon; those DO
        overlap the frame, which is fine -- only coplanar faces z-fight.

        The third group is the caps: every bore except `aperture.open_index` is
        blind, filled from the far face and left as a recess `aperture.blind_recess`
        deep on the robot's side. That is the whole point of having three of them
        -- which one goes through can only be read off the picture, and the shaft
        stops against a cap if the policy picks wrong.
        """

        panel = self.task_cfg.panel
        if not box_entity_enabled(panel):
            return

        aperture = self.task_cfg.aperture
        color = _list(panel.color)
        thickness = float(panel.thickness)
        width = float(panel.width)
        top = float(panel.top_z)
        # Lay the parts out in task-frame numbers straight from the config and
        # convert only the finished centres.
        across_flats = float(aperture.across_flats)
        sides = int(aperture.sides)
        center_z = float(aperture.center_z)
        # Bounding box read off the corners, not assumed: a hexagon's widest
        # points are corners while a 16-gon's are the middles of its flat sides.
        half_y, half_z = polygon_extents(regular_polygon_vertices(sides, across_flats))
        ap_z_min, ap_z_max = center_z - half_z, center_z + half_z
        if ap_z_max >= top:
            raise ValueError(f"Aperture top {ap_z_max} must sit below the panel top {top}.")

        centres = layout.aperture_centers_y()
        # The vertical strips of solid panel between the bores, plus the two ends.
        # Edges are y of the bore openings; a strip runs from one bore's outer
        # edge to the next one's, and the two end strips reach the panel's edge.
        edges = [-0.5 * width] + [c + sign * half_y for c in centres for sign in (-1.0, 1.0)]
        edges.append(0.5 * width)
        strips = [(edges[k], edges[k + 1]) for k in range(0, len(edges) - 1, 2)]
        for index, (lo, hi) in enumerate(strips):
            strip_width = hi - lo
            if strip_width <= 0.0:
                raise ValueError(
                    f"Panel width {width} and pitch {float(aperture.pitch)} leave no "
                    f"material between bores {index - 1} and {index} (strip {strip_width:+.4f} m)."
                )
            manifest.add(
                f"panel_post_{index}",
                scene.add_entity(
                    gs.morphs.Box(
                        pos=tuple(
                            layout.position_to_world(
                                (layout.panel_x, 0.5 * (lo + hi), 0.5 * ap_z_max)
                            )
                        ),
                        size=(thickness, strip_width, ap_z_max),
                        fixed=True,
                    ),
                    surface=materials.plastic("board", color),
                    name=f"panel_post_{index}",
                ),
            )

        # Sill and lintel span the whole panel: below and above every bore there
        # is solid material all the way across.
        for name, centre_z_, height in (
            ("panel_sill", 0.5 * ap_z_min, ap_z_min),
            ("panel_lintel", 0.5 * (ap_z_max + top), top - ap_z_max),
        ):
            manifest.add(
                name,
                scene.add_entity(
                    gs.morphs.Box(
                        pos=tuple(layout.position_to_world((layout.panel_x, 0.0, centre_z_))),
                        size=(thickness, width, height),
                        fixed=True,
                    ),
                    surface=materials.plastic("board", color),
                    name=name,
                ),
            )

        open_index = int(aperture.open_index)
        recess = float(aperture.blind_recess)
        for index, centre_y in enumerate(centres):
            self._add_aperture_corners(
                scene, manifest, layout, thickness, color, index=index, center_y=centre_y
            )
            if index == open_index:
                continue
            # Blind bore: a plug filling the opening from the far face, leaving a
            # recess on the near side. Filling the bounding rectangle rather than
            # the polygon is fine -- the excess is buried in the frame.
            depth = thickness - recess
            if depth <= 0.0:
                raise ValueError(
                    f"aperture.blind_recess {recess} is not shallower than the panel "
                    f"({thickness} m); a blind bore would poke out of the far face."
                )
            manifest.add(
                f"panel_plug_{index}",
                scene.add_entity(
                    gs.morphs.Box(
                        pos=tuple(
                            layout.position_to_world(
                                (
                                    layout.panel_x + 0.5 * recess,
                                    centre_y,
                                    center_z,
                                )
                            )
                        ),
                        size=(depth, 2.0 * half_y, 2.0 * half_z),
                        fixed=True,
                    ),
                    surface=materials.plastic("board", _list(aperture.blind_color)),
                    name=f"panel_plug_{index}",
                ),
            )

    def _add_aperture_corners(
        self, scene, manifest, layout, thickness, color, *, index: int = 0, center_y: float = 0.0
    ) -> None:
        """One box per slanted bore edge, trimming the rectangle down to the polygon.

        The horizontal top and bottom edges are the lintel and the sill, so they
        are skipped; every other edge gets a box seated just outside it. A hexagon
        leaves 4 such edges, a 16-gon 14 -- the count follows from the profile
        rather than being written down.
        """

        across_flats = float(self.task_cfg.aperture.across_flats)
        inradius = 0.5 * across_flats
        center_z = float(self.task_cfg.aperture.center_z)
        sides = int(self.task_cfg.aperture.sides)
        corners = regular_polygon_vertices(sides, across_flats)
        # Depth measured perpendicular to the edge. The deepest cut any edge has
        # to make is from the bounding rectangle's corner to the polygon, which is
        # `circumradius * (sqrt(2) - 1)` at worst on a many-sided bore and
        # `inradius / 2` on a hexagon; taking the larger of the two covers both,
        # and overlapping past it only buries the piece in the frame.
        half_y, half_z = polygon_extents(corners)
        deepest = float(np.hypot(half_y, half_z)) - float(
            np.min(np.linalg.norm(corners, axis=1))
        )
        overlap = float(getattr(self.task_cfg.aperture, "corner_overlap", 0.004))
        depth = max(0.5 * inradius, deepest) + overlap
        edge_len = float(np.linalg.norm(corners[1] - corners[0]))
        length = edge_len + 2.0 * overlap

        piece = 0
        for k in range(sides):
            p, q = corners[k], corners[(k + 1) % sides]
            delta = q - p
            if abs(delta[1]) < 1e-12:
                continue  # the horizontal top/bottom edges are the lintel and sill
            mid = 0.5 * (p + q)
            outward = np.array([delta[1], -delta[0]], dtype=float)
            outward /= np.linalg.norm(outward)
            if float(np.dot(outward, mid)) < 0.0:
                outward = -outward
            seat = mid + outward * (0.5 * depth)
            name = f"panel_chamfer_{index}_{piece}"
            piece += 1
            manifest.add(
                name,
                scene.add_entity(
                    gs.morphs.Box(
                        pos=tuple(
                            layout.position_to_world(
                                (
                                    layout.panel_x,
                                    float(center_y) + float(seat[0]),
                                    center_z + float(seat[1]),
                                )
                            )
                        ),
                        size=(thickness, length, depth),
                        # A rotation about x turns the box within the YZ plane; the
                        # box's length axis is y, so this lays it along the edge.
                        euler=(float(np.degrees(np.arctan2(delta[1], delta[0]))), 0.0, 0.0),
                        fixed=True,
                    ),
                    surface=materials.plastic("board", color),
                    name=name,
                ),
            )

    # ---------------------------------------------------------------- cradles

    def _add_cradles(self, scene, manifest: EntityManifest, layout: BarThroughHoleLayout) -> None:
        """V-blocks the shaft rests in, from the shared `_fixtures` builder.

        These were flat-top pads until 2026-08-16. A pad locates the shaft
        vertically and in nothing else, so it crept 5.2 mm sideways just settling
        under gravity and the closing pads turned it a further 3.3 degrees --
        both spent out of the bore's 7 mm of clearance before the arm had done
        anything. A groove takes the sideways freedom away, which is the whole
        reason the oracle's own alignment correction can stay small.

        Grooves sit away from the grasp x, same as the pads did, so the fingers
        still close on bare shaft.
        """

        for name, spec in layout.cradle_specs():
            if not bool(getattr(spec, "enabled", True)):
                continue
            add_v_block(
                scene,
                manifest,
                prefix=name,
                center_x=float(spec.x),
                center_y=layout.cradle_y(name),
                apex_z=layout.cradle_apex_z(spec),
                length_x=float(spec.length_x),
                half_angle_rad=float(np.deg2rad(float(spec.half_angle_deg))),
                jaw_width=float(spec.jaw_width),
                jaw_thickness=float(spec.jaw_thickness),
                post_width=float(spec.post_width),
                base_z=0.0,
                color=_list(getattr(spec, "color", self.task_cfg.panel.color)),
                to_world=layout.position_to_world,
            )

    # -------------------------------------------------------------------- bar

    def _add_bar(self, scene, manifest: EntityManifest, layout: BarThroughHoleLayout) -> None:
        """The shaft: a free rigid regular prism with its axis along +x.

        Genesis has no prism primitive, so it is generated and loaded as a
        mesh. `convexify=True` is exact here rather than an approximation: a
        prism is convex, so its convex hull is itself. `prism_mesh` already
        builds it axis-along-X, so no spawn rotation is needed and the verifier
        reads the shaft direction as ``R @ (1, 0, 0)``.
        """

        bar = self.task_cfg.bar
        sides = int(bar.sides)
        verts, faces = prism_mesh(sides, float(bar.across_flats), float(bar.length))
        mesh_dir = resolve_mesh_dir(
            getattr(bar, "mesh_output_dir", "runs/generated_meshes/bar_through_hole")
        )
        mesh_path = mesh_dir / f"bar_prism_{sides}.obj"
        write_obj(mesh_path, verts, faces)
        manifest.add(
            "bar",
            scene.add_entity(
                gs.morphs.Mesh(
                    file=str(mesh_path.resolve()).replace("\\", "/"),
                    pos=tuple(layout.bar_rest_center()),
                    scale=1.0,
                    decimate=False,
                    convexify=True,
                    fixed=False,
                    file_meshes_are_zup=False,
                ),
                material=gs.materials.Rigid(rho=float(getattr(bar, "rho", 2700.0))),
                surface=materials.plastic("object", _list(bar.color)),
                name="bar",
            ),
        )

    # -------------------------------------------------------- visual dressing

    def _add_visual_details(
        self, scene, manifest: EntityManifest, layout: BarThroughHoleLayout
    ) -> None:
        """Collision-free industrial dressing, each item independently switchable.

        Same recipe as stacked_plate's visual upgrade: decoration never touches
        the collision geometry, so turning any of it off cannot change physics.
        Only static parts are dressed -- a decorative collar on the moving shaft
        would need per-step syncing, which is not worth a cosmetic gain.
        """

        details = getattr(self.task_cfg, "visual_details", None)
        if details is None:
            return

        flange = getattr(details, "flange", None)
        if flange is not None and bool(getattr(flange, "enabled", True)):
            self._add_flange(scene, manifest, layout, flange)

        bolts = getattr(details, "bolts", None)
        if bolts is not None and bool(getattr(bolts, "enabled", True)):
            self._add_bolts(scene, manifest, layout, bolts)

        pedestal = getattr(details, "pedestal", None)
        if pedestal is not None and bool(getattr(pedestal, "enabled", True)):
            self._add_cradle_pedestals(scene, manifest, layout, pedestal)

    def _add_cradle_pedestals(self, scene, manifest, layout, pedestal) -> None:
        """Dress each V-block's post as a bolted pedestal.

        The post and the jaws are untouched -- same groove, same footprint, so
        the shaft rests where it did. `add_industrial_pedestal` gives the tall
        far post a foot plate, anchor bolts, knee braces and a cap collar, and
        the two short near posts just the plate and bolts, since a brace does not
        read at that height. The collar is what visually joins post to jaws.
        """

        for name, spec in layout.cradle_specs():
            if not bool(getattr(spec, "enabled", True)):
                continue
            apex_z = layout.cradle_apex_z(spec)
            add_industrial_pedestal(
                scene,
                manifest,
                prefix=name,
                spec=pedestal,
                center_x=float(spec.x),
                center_y=layout.cradle_y(name),
                top_z=apex_z,
                block_size=(float(spec.length_x), float(spec.post_width), apex_z),
                to_world=layout.position_to_world,
            )

    def _add_flange(self, scene, manifest, layout, flange) -> None:
        """A bolted collar around EVERY bore, on both panel faces.

        Both faces are dressed identically: the panel is a bulkhead, and a bore
        collar that exists only on the robot's side gives the far half of the
        insertion -- the half the shaft is actually in when it seats -- a
        visibly different wall to sit in. `faces` in config can drop back to one
        side if a camera only ever sees one.

        All three bores get the same bright collar (2026-09-08), open and blind
        alike. Colouring only the open one would put the answer in the paint
        rather than in the geometry, which is the shortcut the three bores exist
        to remove -- what separates them has to stay "you can see through this
        one", read off the recess and the background.
        """

        corners = regular_polygon_vertices(
            int(self.task_cfg.aperture.sides), float(self.task_cfg.aperture.across_flats)
        )
        for index, centre_y in enumerate(layout.aperture_centers_y()):
            add_aperture_ring(
                scene,
                manifest,
                prefix=f"flange_{index}",
                corners=corners,
                panel_x=layout.panel_x,
                panel_thickness=layout.panel_thickness,
                center_y=centre_y,
                center_z=float(self.task_cfg.aperture.center_z),
                band=float(flange.band),
                depth=float(flange.depth),
                color=_list(flange.color),
                to_world=layout.position_to_world,
                faces=tuple(_list(getattr(flange, "faces", ("near", "far")))),
            )

    def _add_bolts(self, scene, manifest, layout, bolts) -> None:
        """Bolt heads at the panel's four corners, on both faces."""

        inset = float(bolts.inset)
        half_width = 0.5 * float(self.task_cfg.panel.width)
        top = float(self.task_cfg.panel.top_z)
        stations = [
            (f"{y_tag}{z_tag}", (y_sign * (half_width - inset), z_value))
            for y_sign, y_tag in ((1.0, "l"), (-1.0, "r"))
            for z_value, z_tag in ((top - inset, "t"), (inset, "b"))
        ]
        add_panel_bolts(
            scene,
            manifest,
            prefix="panel_bolt",
            stations=stations,
            panel_x=layout.panel_x,
            panel_thickness=layout.panel_thickness,
            radius=float(bolts.radius),
            height=float(bolts.height),
            color=_list(bolts.color),
            to_world=layout.position_to_world,
            faces=tuple(_list(getattr(bolts, "faces", ("near", "far")))),
        )
