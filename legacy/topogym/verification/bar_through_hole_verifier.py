"""Did the shaft end up threaded through the bulkhead aperture?

The C2 (`routing`) invariant contract in
`docs/develop/framework/task_taxonomy_zh.md` Section 4.2 requires an integer
reading, an explicitly declared reference surface and gateway, and a physical
recheck kept separate from the geometric one. All four are in `to_info()`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from topogym.tasks_legacy.routing.bar_through_hole import BarThroughHoleScene

INVARIANT_NAME = "threading_count"

# Below this |axis . normal| the shaft is nearly parallel to the panel and the
# plane crossing is numerically meaningless, so the reading is 0 by definition
# rather than a division by something close to zero.
_MIN_AXIS_ALIGNMENT = float(np.cos(np.deg2rad(80.0)))


def _entity_pos(entity) -> np.ndarray:
    value = entity.get_pos()
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value).reshape(-1, 3)[0]


def _entity_quat(entity) -> np.ndarray:
    value = entity.get_quat()
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value).reshape(-1, 4)[0]


def prism_axis(quat) -> np.ndarray:
    """World direction of the shaft's local +x axis.

    `prism_mesh` extrudes along local x, so this is the shaft's own
    direction. Worth stating because the convention is not uniform: a
    `gs.morphs.Cylinder` is built about local *z* (stacked_plate turns one onto
    world y with `euler=(90,0,0)`), and reading the wrong column here yields a
    plausible-looking unit vector that is silently 90 degrees off.
    """

    w, x, y, z = (float(v) for v in np.asarray(quat, dtype=float).reshape(4))
    axis = np.array(
        [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y + w * z), 2.0 * (x * z - w * y)],
        dtype=float,
    )
    norm = float(np.linalg.norm(axis))
    return axis / norm if norm > 1e-12 else np.array([1.0, 0.0, 0.0], dtype=float)


def polygon_contains(point_yz, center_yz, across_flats: float, sides: int) -> bool:
    """Is a (y, z) point inside a regular flat-side-down polygon?

    A regular polygon with an even number of sides is the intersection of
    ``sides / 2`` slabs, one per pair of opposite edges, each of half-width equal
    to the inradius. Flat-side-down puts one edge normal straight down, so the
    normals sit at 90 degrees plus multiples of ``360 / sides``.

    2026-09-08: generalised from a hexagon-only version, so the same test serves
    the 16-sided bore the task now uses by default and the 6-sided variant.
    An odd side count would need all ``sides`` half-planes rather than half that
    many, which no configuration asks for -- it is refused rather than silently
    tested as if it were even.
    """

    sides = int(sides)
    if sides < 4 or sides % 2:
        raise ValueError(
            f"aperture.sides must be an even number of at least 4, got {sides}."
        )
    offset = np.asarray(point_yz, dtype=float) - np.asarray(center_yz, dtype=float)
    inradius = 0.5 * float(across_flats)
    for index in range(sides // 2):
        angle = np.deg2rad(90.0 + index * 360.0 / sides)
        if abs(float(offset[0] * np.cos(angle) + offset[1] * np.sin(angle))) > inradius:
            return False
    return True


@dataclass(frozen=True)
class BarThroughHolePuzzleState:
    """One reading of where the shaft sits relative to the panel."""

    ends: tuple[tuple[float, float, float], tuple[float, float, float]]
    center: tuple[float, float, float]
    end_offsets: tuple[float, float]  # signed distance of each end from the panel plane
    plane_point_x: float  # world x of the panel mid-plane (the reference surface)
    axis_alignment: float  # |axis . plane normal|
    crossing_yz: tuple[float, float] | None  # where the shaft axis pierces the plane
    aperture_center_yz: tuple[float, float]
    aperture_across_flats: float
    aperture_sides: int
    tilt_rad: float
    tilt_tolerance: float
    seated_z: float
    seated_z_tolerance: float
    min_end_z: float
    min_end_z_threshold: float  # absolute world z both ends must clear
    release_stable: bool

    @property
    def straddles(self) -> bool:
        low, high = self.end_offsets
        return (low < 0.0) != (high < 0.0)

    @property
    def crossing_inside_aperture(self) -> bool:
        """Load-bearing, not a refinement.

        A shaft laid across the top edge of the panel also puts its two ends on
        opposite sides of the plane. Only this test rejects it.

        Only the shaft's *axis* crossing is tested, not its whole cross-section.
        Collision already keeps the section inside the bore, and the exact
        section test would be the bore hexagon eroded by the shaft hexagon --
        which for the correctly seated pose (shaft face resting on the bore's
        lower face) evaluates exactly on the boundary, so it would turn genuine
        successes into float-precision coin flips.
        """

        if self.crossing_yz is None:
            return False
        return polygon_contains(
            self.crossing_yz,
            self.aperture_center_yz,
            self.aperture_across_flats,
            self.aperture_sides,
        )

    @property
    def threading_count(self) -> int:
        if self.axis_alignment < _MIN_AXIS_ALIGNMENT:
            return 0
        return 1 if (self.straddles and self.crossing_inside_aperture) else 0

    @property
    def invariant_value(self) -> int:
        return self.threading_count

    @property
    def tilt_ok(self) -> bool:
        return bool(self.tilt_rad <= self.tilt_tolerance)

    @property
    def airborne(self) -> bool:
        """Both ends clear of the table -- rejects a shaft that merely fell in leaning."""

        return bool(self.min_end_z >= self.min_end_z_threshold)

    @property
    def seated(self) -> bool:
        center_z = float(self.center[2])
        return bool(abs(center_z - self.seated_z) <= self.seated_z_tolerance)

    @property
    def geometry_ok(self) -> bool:
        return bool(self.threading_count == 1 and self.tilt_ok and self.airborne and self.seated)

    @property
    def is_terminal(self) -> bool:
        return bool(self.geometry_ok and self.release_stable)

    def to_info(self) -> dict[str, Any]:
        return {
            # --- the category invariant -------------------------------------
            "invariant": INVARIANT_NAME,
            "invariant_value": int(self.invariant_value),
            # The shaft is axially symmetric, so end-for-end reversal is the same
            # physical state and a state-based reading cannot carry a sign. The
            # direction sensitivity that Section 4.2 asks for is carried at the
            # task-pair level by docx 2.4/2.5 (wind vs unwind), not here.
            "invariant_signed": False,
            # --- declarations Section 4.2 requires --------------------------
            "reference_plane": {"point_x": float(self.plane_point_x), "normal": [1.0, 0.0, 0.0]},
            "gateway": "panel_aperture",
            "aperture": {
                "shape": "regular_hexagon",
                "orientation": "flat_side_down",
                "center_yz": [float(v) for v in self.aperture_center_yz],
                "across_flats": float(self.aperture_across_flats),
                "sides": int(self.aperture_sides),
            },
            # --- geometry readings ------------------------------------------
            "end_offsets": [float(v) for v in self.end_offsets],
            "straddles": bool(self.straddles),
            "crossing_yz": None if self.crossing_yz is None else [float(v) for v in self.crossing_yz],
            "crossing_inside_aperture": bool(self.crossing_inside_aperture),
            "axis_alignment": float(self.axis_alignment),
            # --- tightenings, listed apart from the invariant ---------------
            "tilt_rad": float(self.tilt_rad),
            "tilt_deg": float(np.rad2deg(self.tilt_rad)),
            "tilt_ok": bool(self.tilt_ok),
            "min_end_z": float(self.min_end_z),
            "airborne": bool(self.airborne),
            "center_z": float(self.center[2]),
            "seated": bool(self.seated),
            "geometry_ok": bool(self.geometry_ok),
            # --- physical recheck, reported separately ----------------------
            "release_stable": bool(self.release_stable),
            "terminal": bool(self.is_terminal),
        }


@dataclass(frozen=True)
class BarThroughHolePuzzleEvaluator:
    """Success = the shaft pierces the aperture and stays there after release."""

    tilt_tolerance: float = float(np.deg2rad(10.0))
    seated_z_tolerance: float = 0.015
    min_end_clearance: float = 0.030

    def classify(
        self, bar_scene: BarThroughHoleScene, *, release_stable: bool = True
    ) -> BarThroughHolePuzzleState:
        layout = bar_scene.layout
        entity = bar_scene.bar_entity()
        center = _entity_pos(entity)
        axis = prism_axis(_entity_quat(entity))
        half = 0.5 * layout.bar_length
        end_low = center - half * axis
        end_high = center + half * axis

        plane_point, normal = layout.panel_plane()
        offset_low = float(np.dot(end_low - plane_point, normal))
        offset_high = float(np.dot(end_high - plane_point, normal))
        alignment = abs(float(np.dot(axis, normal)))

        crossing = None
        if alignment >= _MIN_AXIS_ALIGNMENT and (offset_low < 0.0) != (offset_high < 0.0):
            # Parameterise the shaft from end_low to end_high and solve for the
            # point where it meets the plane.
            span = offset_high - offset_low
            t = -offset_low / span if abs(span) > 1e-12 else 0.5
            pierce = end_low + t * (end_high - end_low)
            crossing = (float(pierce[1]), float(pierce[2]))

        tilt = float(np.arccos(np.clip(alignment, -1.0, 1.0)))
        # The shaft seats on a flat face, so its axis sits one inradius (half the
        # across-flats size) above the aperture's lower edge.
        seated_z = layout.sill_top_z() + layout.bar_inradius
        aperture_center = layout.aperture_center()

        return BarThroughHolePuzzleState(
            ends=(tuple(float(v) for v in end_low), tuple(float(v) for v in end_high)),
            center=tuple(float(v) for v in center),
            end_offsets=(offset_low, offset_high),
            plane_point_x=float(plane_point[0]),
            axis_alignment=alignment,
            crossing_yz=crossing,
            aperture_center_yz=(float(aperture_center[1]), float(aperture_center[2])),
            aperture_across_flats=float(layout.aperture_across_flats),
            aperture_sides=int(layout.aperture_sides),
            tilt_rad=tilt,
            tilt_tolerance=float(self.tilt_tolerance),
            seated_z=float(seated_z),
            seated_z_tolerance=float(self.seated_z_tolerance),
            min_end_z=float(min(end_low[2], end_high[2])),
            min_end_z_threshold=float(layout.world_z(0.0) + self.min_end_clearance),
            release_stable=bool(release_stable),
        )

    def is_success(self, bar_scene: BarThroughHoleScene, *, release_stable: bool = True) -> bool:
        return self.classify(bar_scene, release_stable=release_stable).is_terminal
