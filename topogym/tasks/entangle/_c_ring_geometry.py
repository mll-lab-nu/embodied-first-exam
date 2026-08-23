"""Ring geometry for docx 3.4: a closed ring and a C-shaped open ring, as convex parts.

Both rings are non-convex, and the repo's standing answer to a non-convex body is a
union of convex primitives rather than a concave mesh -- `gs.morphs.Mesh(convexify=True)`
fills a hole in (`tasks/routing/bar_through_hole.py:14`). So a ring here is a chain of
short cylinders laid along the chords of its circle, and the C is the same chain with a
few links left out.

**Chords, not tangents.** Each cylinder's axis is the chord between two points that sit
exactly on the true circle, so the approximation only ever moves material *inward*: at a
segment's midpoint the tube centre is at `R*cos(seg/2)` instead of `R`. That makes the
hole marginally tighter and the outside marginally smaller, and it never widens the C's
opening -- which is the one dimension the task's anti-shortcut rests on
(`docs/develop/tasks/rigid_first_track_zh.md` section 4.5).

**Segments are configured by arc angle, not by count.** Held at a fixed count, the chord
error `R*(1 - cos(seg/2))` would grow with the ring; held at a fixed arc angle it is
proportional to `R` and the two rings stay comparably faithful.

Pure numpy: no Genesis, no `HingeShape`. The task module turns `SegmentSpec` into
`HingeShape`; `tests/check_c_ring_clearance.py` loads this file by path so the offline
gate runs on a checkout with no solver installed.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class RingSpec:
    """A ring's own dimensions, independent of where it sits.

    ``gap_deg = 0`` is a closed ring. ``gap_azimuth_deg`` is the centre of the
    opening, measured from the frame's ``ref`` direction toward ``normal x ref``.
    """

    major_radius: float
    tube_radius: float
    gap_deg: float = 0.0
    gap_azimuth_deg: float = 0.0
    segment_deg: float = 10.0
    joint_overlap: float = 0.0

    def __post_init__(self) -> None:
        if self.major_radius <= self.tube_radius:
            raise ValueError(
                f"major_radius {self.major_radius} must exceed tube_radius {self.tube_radius}."
            )
        if not 0.0 <= self.gap_deg < 360.0:
            raise ValueError(f"gap_deg must be in [0, 360), got {self.gap_deg}.")
        if not 0.0 < self.segment_deg <= 45.0:
            raise ValueError(f"segment_deg must be in (0, 45], got {self.segment_deg}.")
        if self.joint_overlap < 0.0:
            raise ValueError(f"joint_overlap must not be negative, got {self.joint_overlap}.")

    @property
    def body_deg(self) -> float:
        return 360.0 - self.gap_deg

    @property
    def inner_radius(self) -> float:
        """Radius of the hole, before the chord approximation tightens it."""

        return self.major_radius - self.tube_radius

    @property
    def outer_radius(self) -> float:
        return self.major_radius + self.tube_radius

    @property
    def sagitta(self) -> float:
        """How far a chord's midpoint falls inside the true circle."""

        return self.major_radius * (1.0 - np.cos(0.5 * np.deg2rad(self.segment_deg)))

    @property
    def gap_clear_width(self) -> float:
        """Free width between the two end caps of the C, across the opening.

        The end faces sit on the circle at the opening's two boundary azimuths, so
        the free span is that chord less one tube diameter. This is what has to
        clear the other ring's body for the opening to be a gateway at all.
        """

        if self.gap_deg <= 0.0:
            return 0.0
        chord = 2.0 * self.major_radius * np.sin(0.5 * np.deg2rad(self.gap_deg))
        return float(chord - 2.0 * self.tube_radius)


@dataclass(frozen=True)
class RingFrame:
    """Where a ring sits: its centre, its plane, and which way azimuth 0 points."""

    center: np.ndarray
    normal: np.ndarray
    ref: np.ndarray

    @staticmethod
    def create(center, normal, ref) -> "RingFrame":
        center = np.asarray(center, dtype=float).reshape(3)
        normal = _unit(np.asarray(normal, dtype=float).reshape(3))
        ref = np.asarray(ref, dtype=float).reshape(3)
        ref = _unit(ref - np.dot(ref, normal) * normal)
        return RingFrame(center=center, normal=normal, ref=ref)

    @property
    def binormal(self) -> np.ndarray:
        return np.cross(self.normal, self.ref)

    def point(self, azimuth_rad, radius: float) -> np.ndarray:
        """Points at ``radius`` from the centre, at the given azimuths."""

        angle = np.atleast_1d(np.asarray(azimuth_rad, dtype=float))
        offset = (
            np.cos(angle)[:, None] * self.ref[None, :]
            + np.sin(angle)[:, None] * self.binormal[None, :]
        )
        return self.center[None, :] + float(radius) * offset

    def transformed(self, *, translation=(0.0, 0.0, 0.0), rotation=None) -> "RingFrame":
        """Rigid-body move of the whole ring, rotating about its own centre."""

        shift = np.asarray(translation, dtype=float).reshape(3)
        if rotation is None:
            return RingFrame(center=self.center + shift, normal=self.normal, ref=self.ref)
        rot = np.asarray(rotation, dtype=float).reshape(3, 3)
        return RingFrame(
            center=self.center + shift, normal=rot @ self.normal, ref=rot @ self.ref
        )


@dataclass(frozen=True)
class TabSpec:
    """A radial stub on the C, sticking out from the ring's outer surface.

    `tasks/_fixtures.py` `_link_xml` places a body's centre of mass at the bounding
    box of its colliding shapes. For a bare C that box is essentially centred on the
    ring -- the opening pulls it 1.62 mm sideways and nothing at all downward -- and
    the bar the C hangs from is directly above the ring's centre. So the orientation
    the C would settle into is the one that puts those 1.62 mm straight down, which
    is the opening turned onto the bar, 90 degrees from where it spawns. The stub
    drops the box 8.3 mm below the ring, which moves that resting orientation to 11
    degrees from the spawn azimuth instead of 90.

    Measured 2026-08-22: neither resting orientation is reached, because Coulomb
    friction at the hanging contact holds the C wherever it starts. At the default
    contact friction of 1.0 that is mu*W*r = 12.3 mNm against a gravity torque of
    0.79 mNm, a factor of 15, and 600 steps of hold move the opening by 0.6 degrees.
    So the stub is NOT what keeps this scene linked. What it is: the grasp feature
    (hence its own radius), and the margin if the contact ever gets slippery -- a
    friction sweep, a different material, or a randomised layout that lightens the
    C. Shortening it is a live option; see `docs/develop/tasks/unlink_c_ring_zh.md`.
    """

    azimuth_deg: float
    length: float
    radius: float

    def __post_init__(self) -> None:
        if self.length <= 0.0 or self.radius <= 0.0:
            raise ValueError("Tab length and radius must be positive.")


@dataclass(frozen=True)
class SegmentSpec:
    """One cylinder of the chain, in the same frame the ring's centre was given in."""

    origin: tuple[float, float, float]
    rpy: tuple[float, float, float]
    radius: float
    length: float


def _unit(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if norm < 1e-12:
        raise ValueError("Cannot normalise a zero-length vector.")
    return vector / norm


def body_azimuths(spec: RingSpec) -> np.ndarray:
    """Segment boundaries along the ring body, in radians.

    The body runs from one edge of the opening to the other the long way round, and
    is cut into equal pieces no coarser than ``segment_deg``. A closed ring wraps, so
    its last boundary is its first and is dropped.
    """

    count = int(np.ceil(spec.body_deg / spec.segment_deg))
    start = np.deg2rad(spec.gap_azimuth_deg + 0.5 * spec.gap_deg)
    end = np.deg2rad(spec.gap_azimuth_deg + 360.0 - 0.5 * spec.gap_deg)
    boundaries = np.linspace(start, end, count + 1)
    return boundaries[:-1] if spec.gap_deg <= 0.0 else boundaries


def centerline(spec: RingSpec, frame: RingFrame, *, closure_samples: int = 6) -> np.ndarray:
    """The ring's centreline as a CLOSED polyline, ready for the crossing readers.

    A closed ring is its own loop. The C is an open arc, and a linking number is only
    defined once it is closed -- so its opening is bridged by a straight chord. That
    chord IS the task's declared canonical closure: it is the segment the other ring's
    body has to cross to change the reading, which is the same thing as passing
    through the opening.
    """

    arc = frame.point(body_azimuths(spec), spec.major_radius)
    if spec.gap_deg <= 0.0:
        return arc
    chord = np.linspace(arc[-1], arc[0], closure_samples + 2)[1:-1]
    return np.vstack([arc, chord])


def ring_tangent(frame: RingFrame, azimuth_deg: float) -> np.ndarray:
    """Unit direction the tube runs at one azimuth: the circle's tangent there.

    What a gripper has to close ACROSS. Closing along it instead pushes the ring
    away instead of pinching it, which is not something the pose alone reveals --
    the hand looks correctly placed either way.
    """

    angle = np.deg2rad(float(azimuth_deg))
    return _unit(-np.sin(angle) * frame.ref + np.cos(angle) * frame.binormal)


def direction_to_rpy(direction: np.ndarray) -> tuple[float, float, float]:
    """URDF ``rpy`` that points a cylinder's local +Z along ``direction``.

    URDF composes fixed-axis roll-pitch-yaw as ``Rz(yaw) @ Ry(pitch) @ Rx(roll)``, so
    with roll left at zero the local +Z lands on
    ``(cos(yaw) sin(pitch), sin(yaw) sin(pitch), cos(pitch))``. Yaw is undefined when
    the direction is vertical; zero is as good as any value there.
    """

    unit = _unit(np.asarray(direction, dtype=float).reshape(3))
    pitch = float(np.arccos(np.clip(unit[2], -1.0, 1.0)))
    yaw = 0.0 if abs(unit[2]) > 1.0 - 1e-9 else float(np.arctan2(unit[1], unit[0]))
    return (0.0, pitch, yaw)


def tab_axis(spec: RingSpec, frame: RingFrame, tab: TabSpec) -> tuple[np.ndarray, np.ndarray]:
    """Where the stub's axis starts and ends, in the frame's own coordinates.

    It starts on the ring's centreline circle rather than on its outer surface, so
    the stub and the ring interpenetrate over one tube radius and the joint reads as
    one part.
    """

    azimuth = np.deg2rad(tab.azimuth_deg)
    start = frame.point(azimuth, spec.major_radius)[0]
    end = frame.point(azimuth, spec.major_radius + tab.length)[0]
    return start, end


def segment_specs(spec: RingSpec, frame: RingFrame, tab: TabSpec | None = None) -> list[SegmentSpec]:
    """The chain of cylinders, positioned relative to ``frame.center``.

    Internal joints are lengthened by ``joint_overlap`` at both ends so neighbours
    interpenetrate and the chain reads as one continuous ring; volumetric overlap is
    harmless, only coplanar faces z-fight (`tasks/_fixtures.py` `add_v_block`). The
    two free ends of a C are NOT lengthened -- that would eat into the opening, which
    is the dimension the task is judged on.
    """

    points = frame.point(body_azimuths(spec), spec.major_radius)
    closed = spec.gap_deg <= 0.0
    count = len(points) if closed else len(points) - 1

    segments: list[SegmentSpec] = []
    for index in range(count):
        start = points[index]
        end = points[(index + 1) % len(points)]
        chord = end - start
        chord_length = float(np.linalg.norm(chord))
        head_free = not closed and index == 0
        tail_free = not closed and index == count - 1
        grow = spec.joint_overlap * ((0.0 if head_free else 1.0) + (0.0 if tail_free else 1.0))
        # Growing only at the joined end also shifts the cylinder's centre toward it.
        shift = 0.5 * spec.joint_overlap * (
            (0.0 if tail_free else 1.0) - (0.0 if head_free else 1.0)
        )
        direction = chord / chord_length
        midpoint = 0.5 * (start + end) + shift * direction - frame.center
        segments.append(
            SegmentSpec(
                origin=tuple(float(v) for v in midpoint),
                rpy=direction_to_rpy(direction),
                radius=float(spec.tube_radius),
                length=chord_length + grow,
            )
        )
    if tab is not None:
        start, end = tab_axis(spec, frame, tab)
        segments.append(
            SegmentSpec(
                origin=tuple(float(v) for v in 0.5 * (start + end) - frame.center),
                rpy=direction_to_rpy(end - start),
                radius=float(tab.radius),
                length=float(np.linalg.norm(end - start)),
            )
        )
    return segments


def body_axes(
    spec: RingSpec, frame: RingFrame, tab: TabSpec | None = None
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Axis start points, end points, and radii of every collision cylinder.

    This is the exact axis set the collision bodies are built from, so distances
    measured against it are distances against what the solver will actually see --
    not against the ideal torus.
    """

    points = frame.point(body_azimuths(spec), spec.major_radius)
    if spec.gap_deg <= 0.0:
        starts, ends = points, np.roll(points, -1, axis=0)
    else:
        starts, ends = points[:-1], points[1:]
    radii = np.full(len(starts), spec.tube_radius, dtype=float)
    if tab is not None:
        start, end = tab_axis(spec, frame, tab)
        starts = np.vstack([starts, start])
        ends = np.vstack([ends, end])
        radii = np.append(radii, tab.radius)
    return starts, ends, radii


def segment_distance(a0: np.ndarray, a1: np.ndarray, b0: np.ndarray, b1: np.ndarray) -> np.ndarray:
    """Shortest distance between every pair of segments, as an (len(a), len(b)) grid.

    Closest-point-between-two-segments, clamped to both parameter ranges. Vectorised
    over the full pair grid because a trajectory probe evaluates it a few hundred
    times and the two chains are a few dozen segments each.
    """

    d1 = (a1 - a0)[:, None, :]
    d2 = (b1 - b0)[None, :, :]
    r = a0[:, None, :] - b0[None, :, :]
    a = np.einsum("ijk,ijk->ij", d1, d1)
    e = np.einsum("ijk,ijk->ij", d2, d2)
    f = np.einsum("ijk,ijk->ij", d2, r)
    c = np.einsum("ijk,ijk->ij", d1, r)
    b = np.einsum("ijk,ijk->ij", d1, d2)

    denom = np.maximum(a * e - b * b, 1e-24)
    s = np.clip((b * f - c * e) / denom, 0.0, 1.0)
    t = np.clip((b * s + f) / np.maximum(e, 1e-24), 0.0, 1.0)
    s = np.clip((b * t - c) / np.maximum(a, 1e-24), 0.0, 1.0)

    closest = d1 * s[:, :, None] - d2 * t[:, :, None] + r
    return np.linalg.norm(closest, axis=2)


def surface_gap(axes_a, axes_b) -> float:
    """Clearance between two chains' surfaces: negative means they interpenetrate.

    Each argument is a ``body_axes`` triple. Radii are per segment, so a stub of a
    different thickness than the ring it grows from is handled without a special case.
    """

    a0, a1, ra = axes_a
    b0, b1, rb = axes_b
    axis_distance = segment_distance(a0, a1, b0, b1)
    return float((axis_distance - ra[:, None] - rb[None, :]).min())


def bisector_projection(normal_a, normal_b) -> np.ndarray:
    """A projection basis that views both ring planes obliquely.

    Rows are ``(u, v, w)`` in `world/closed_band.py`'s convention: ``u, v`` span the
    picture plane and ``w`` points at the viewer, so "over" means a larger ``w``.

    The two ring normals are perpendicular to each other by construction -- the C
    hangs on a stretch of bar that is tangent to the closed ring -- so looking along
    their bisector puts both rings at 45 degrees and neither is seen edge-on. That is
    the condition a crossing count needs to be defined at all.

    Derived rather than written into config because the whole scene turns with
    ``stand.hang_yaw_deg``: a matrix that was correct at one hang bearing read
    ``Lk = -2`` at another, where it happened to look straight down the C's own plane.
    """

    normal_a = _unit(np.asarray(normal_a, dtype=float).reshape(3))
    normal_b = _unit(np.asarray(normal_b, dtype=float).reshape(3))
    viewer = _unit(normal_a + normal_b)
    across = _unit(normal_a - normal_b)
    return np.vstack([across, np.cross(viewer, across), viewer])


def rotation_about(axis, angle_rad: float) -> np.ndarray:
    """Rodrigues rotation matrix."""

    unit = _unit(np.asarray(axis, dtype=float).reshape(3))
    cross = np.array(
        [
            [0.0, -unit[2], unit[1]],
            [unit[2], 0.0, -unit[0]],
            [-unit[1], unit[0], 0.0],
        ]
    )
    return (
        np.eye(3)
        + np.sin(angle_rad) * cross
        + (1.0 - np.cos(angle_rad)) * (cross @ cross)
    )


# ---------------------------------------------------------------------------
# The scene's geometry, derived once from config so nothing is stated twice.
# ---------------------------------------------------------------------------

# Where the default home pose puts the fingertip pads, in the task frame. Anything
# taller than this is inside the arm at reset: `reset_home` teleports the joints with
# `set_dofs_position`, so an overlap is not pushed apart, it is spawned. Same number
# and same reasoning as `tasks/routing/bar_through_hole.py`'s panel height ceiling.
HOME_FINGERTIP_Z = 0.1608

# Kept off the table by this much at rest and at the end of the extraction.
TABLE_CLEARANCE = 0.004


@dataclass(frozen=True)
class SceneGeometry:
    """Every derived length the scene, the verifier, and the offline gate all need.

    Deriving it here rather than in the task module keeps the offline gate free of
    Genesis, and keeps the gate measuring the same scene the builder builds.
    """

    fixed: RingSpec
    fixed_frame: RingFrame
    c_ring: RingSpec
    tab: TabSpec | None
    c_rest_frame: RingFrame
    c_spawn_frame: RingFrame
    stand_axes: tuple[np.ndarray, np.ndarray, np.ndarray]
    tube_point: np.ndarray
    tube_direction: np.ndarray
    hang_direction: np.ndarray
    projection: np.ndarray
    closure_samples: int
    jam_depth: float
    stand_clearance: float

    @property
    def hang_offset(self) -> float:
        """How far the C's centre sits below the bar when it hangs on it."""

        return self.c_ring.inner_radius - self.fixed.tube_radius

    @property
    def extract_travel(self) -> float:
        """Descent that carries the bar from the hole's rim clear of the C's outside.

        From touching the inside to clear of the outside is one hole diameter less
        one outside diameter, which reduces to twice the two tube radii.
        """

        return 2.0 * (self.c_ring.tube_radius + self.fixed.tube_radius)

    @property
    def top_z(self) -> float:
        """Highest point of anything fixed in the scene.

        The closed ring lies flat, so it only reaches its own tube radius above its
        plane -- unlike a ring stood on edge, which would add a whole major radius.
        That is most of why this layout leaves the arm's home pose so much room.
        """

        starts, ends, radii = self.stand_axes
        axis = ends - starts
        # A cylinder's cap is flat: the radius only lifts the silhouette by how much
        # the axis leans off vertical. Adding the full radius would read the upright
        # post as taller than it is.
        lean = np.sqrt(np.clip(1.0 - (axis[:, 2] / np.linalg.norm(axis, axis=1)) ** 2, 0.0, 1.0))
        stand_top = float(np.max(np.maximum(starts[:, 2], ends[:, 2]) + radii * lean))
        ring_top = float(self.fixed_frame.center[2] + self.fixed.tube_radius)
        return max(stand_top, ring_top)

    @property
    def post_center(self) -> np.ndarray:
        """Where the post stands: on the rim, diametrically opposite the C."""

        return self.stand_axes[0][0]

    @property
    def post_to_c_ring(self) -> float:
        """Clearance between the post's surface and the C ring's outermost point."""

        gap = float(np.linalg.norm(self.post_center[:2] - self.c_rest_frame.center[:2]))
        return gap - self.c_ring.outer_radius - float(self.stand_axes[2][0])

    def fixed_axes(self):
        return body_axes(self.fixed, self.fixed_frame)

    def c_axes(self, frame: RingFrame):
        return body_axes(self.c_ring, frame, self.tab)

    def align_rotation(self) -> tuple[np.ndarray, float]:
        """Axis and angle in degrees that bring the opening onto the bar.

        The same rotation `gateway_phases`' first phase applies, but expressed the
        way a quaternion builder wants it: ``quat_about_axis(axis, radians(angle))``.

        The angle is wrapped to (-180, 180]. As a rotation matrix -270 and +90 are
        the same thing, so `apply_phases` never cared; a WRIST does, and asking it
        for 270 degrees when 90 would do is how a reachable motion turns into an
        unreachable one.
        """

        turn = -float(self.c_ring.gap_azimuth_deg)
        turn = (turn + 180.0) % 360.0 - 180.0
        return np.asarray(self.c_rest_frame.normal, dtype=float), turn

    def gateway_phases(self, *, carry: float = 0.090):
        """The one trajectory that unlinks: align the opening, drop out, carry away.

        Phase 1 turns the C about the bar until its opening points at the bar --
        which is what "keeping the opening aligned with the ring body" means once the
        C hangs from that body. Phase 2 is the only direction the bar can leave
        through. Phase 3 carries it out RADIALLY, away from the closed ring's centre:
        every other direction runs back under the ring, whose far rim curves down
        over the path.
        """

        axis, turn = self.align_rotation()
        return (
            ("rotate", (-turn, tuple(axis))),
            ("translate", (0.0, 0.0, -self.extract_travel)),
            ("translate", tuple(float(carry) * self.hang_direction)),
        )

    def checks(self) -> list[tuple[str, float, float, bool]]:
        """(name, measured, lower limit, ok) for every inequality the scene rests on."""

        rest_z = float(self.c_rest_frame.center[2])
        rows = [
            (
                "opening clears the bar",
                self.c_ring.gap_clear_width,
                2.0 * self.fixed.tube_radius,
            ),
            ("C fits over the bar", self.hang_offset, 0.0),
            (
                "ring clears the table after extraction",
                rest_z - self.extract_travel - self.c_ring.outer_radius,
                TABLE_CLEARANCE,
            ),
            ("post clears the C ring", self.post_to_c_ring, self.stand_clearance),
            ("stand clears the home pose", HOME_FINGERTIP_Z - self.top_z, 0.0),
        ]
        if self.tab is not None:
            rows.insert(
                3,
                (
                    "tab clears the table at rest",
                    rest_z - self.c_ring.major_radius - self.tab.length,
                    TABLE_CLEARANCE,
                ),
            )
        return [(name, value, limit, value > limit) for name, value, limit in rows]


def scene_geometry(cfg: dict) -> SceneGeometry:
    """Build the derived geometry from a plain dict of the task config.

    The layout: a post stands on the table and carries a closed ring lying FLAT at
    its top, attached at the rim right above the post. The C hangs on the opposite
    rim, one ring diameter away, so nothing the arm has to reach is under anything.

    An earlier version stood the closed ring on edge at the end of a horizontal
    cantilever. It failed for a reason the clearance gate could not see: the gate
    measured the C ring's envelope against the arm, and the thing that collided was
    the HAND, descending onto a grasp point directly beneath the cantilever.
    A flat ring removes the overhead structure entirely -- and, as a bonus, puts the
    extraction's rotation axis horizontal, pointing at the robot, so a gripper that
    approaches the C face-on rolls it about its own tool axis.
    """

    stand, fixed_cfg, c_cfg = cfg["stand"], cfg["fixed_ring"], cfg["c_ring"]
    topology, tab_cfg = cfg["topology"], cfg["c_ring"]["tab"]

    fixed = RingSpec(
        major_radius=float(fixed_cfg["major_radius"]),
        tube_radius=float(fixed_cfg["tube_radius"]),
        segment_deg=float(fixed_cfg["segment_deg"]),
        joint_overlap=float(fixed_cfg["joint_overlap"]),
    )
    # The closed ring lies flat: normal up, azimuth 0 pointing at the hang point so
    # every other bearing in this function is measured from the same place.
    hang_yaw = np.deg2rad(float(stand["hang_yaw_deg"]))
    hang_direction = np.array([np.cos(hang_yaw), np.sin(hang_yaw), 0.0])
    fixed_frame = RingFrame.create(
        [float(v) for v in fixed_cfg["center"]], [0.0, 0.0, 1.0], hang_direction
    )
    tube_point = fixed_frame.point(0.0, fixed.major_radius)[0]
    # Tangent to the flat ring at the hang point: horizontal, across the radius.
    tube_direction = fixed_frame.binormal

    c_ring = RingSpec(
        major_radius=float(c_cfg["major_radius"]),
        tube_radius=float(c_cfg["tube_radius"]),
        gap_deg=float(c_cfg["gap_deg"]),
        gap_azimuth_deg=float(c_cfg["gap_azimuth_deg"]),
        segment_deg=float(c_cfg["segment_deg"]),
        joint_overlap=float(c_cfg["joint_overlap"]),
    )
    tab = None
    if bool(tab_cfg.get("enabled", False)):
        tab = TabSpec(
            azimuth_deg=float(tab_cfg["azimuth_deg"]),
            length=float(tab_cfg["length"]),
            radius=float(tab_cfg["radius"]),
        )
    # Azimuth 0 points straight up, at the bar the C hangs from, so the opening's
    # azimuth reads directly as how far it is from falling off.
    hang = c_ring.inner_radius - fixed.tube_radius
    c_rest_frame = RingFrame.create(
        tube_point - np.array([0.0, 0.0, hang]), tube_direction, [0.0, 0.0, 1.0]
    )
    c_spawn_frame = c_rest_frame.transformed(
        translation=(0.0, 0.0, float(c_cfg["spawn_drop"]))
    )

    # The post stands under the rim opposite the hang point and rises to the ring's
    # own plane -- the ring is bolted to its top, so there is no arm at all.
    ring_z = float(fixed_frame.center[2])
    post_xy = fixed_frame.point(np.pi, fixed.major_radius)[0]
    stand_axes = (
        np.vstack([[post_xy[0], post_xy[1], 0.0]]),
        np.vstack([[post_xy[0], post_xy[1], ring_z]]),
        np.array([float(stand["post_radius"])]),
    )

    return SceneGeometry(
        fixed=fixed,
        fixed_frame=fixed_frame,
        c_ring=c_ring,
        tab=tab,
        c_rest_frame=c_rest_frame,
        c_spawn_frame=c_spawn_frame,
        stand_axes=stand_axes,
        tube_point=tube_point,
        tube_direction=tube_direction,
        hang_direction=hang_direction,
        projection=bisector_projection(fixed_frame.normal, tube_direction),
        closure_samples=int(topology["closure_samples"]),
        jam_depth=float(topology["jam_depth"]),
        stand_clearance=float(stand["clearance"]),
    )


def apply_phases(frame: RingFrame, phases, progress: float) -> RingFrame:
    """Where the C is at ``progress`` in [0, 1] through an equal-time phase list.

    A phase is ``("rotate", (degrees, axis))`` or ``("translate", (dx, dy, dz))``.
    Rotation is about the ring's own centre, so a phase list reads as the wrist's
    programme rather than as a world-frame path. Positive degrees move a body-fixed
    azimuth toward zero, matching how the opening's azimuth is quoted.
    """

    phases = list(phases)
    span = 1.0 / len(phases)
    for index, (kind, value) in enumerate(phases):
        fraction = float(np.clip((progress - index * span) / span, 0.0, 1.0))
        if kind == "rotate":
            degrees, axis = value
            frame = frame.transformed(
                rotation=rotation_about(axis, -np.deg2rad(float(degrees)) * fraction)
            )
        elif kind == "translate":
            frame = frame.transformed(translation=np.asarray(value, dtype=float) * fraction)
        else:
            raise ValueError(f"Unknown phase kind {kind!r}; use 'rotate' or 'translate'.")
    return frame
