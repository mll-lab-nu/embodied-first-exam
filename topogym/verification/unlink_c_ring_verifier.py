"""Did the C ring come off the closed ring, and can it now leave freely?

The C3 (`entangle`) contract in `docs/develop/framework/task_taxonomy_zh.md`
Section 4.3 asks for four things, and all four are in `to_info()`: a signed crossing
sequence as the invariant, an explicitly declared projection, an explicitly declared
boundary condition, and a physical recheck kept apart from the geometric reading.

Two of those need a word here.

**The C ring is an open curve**, so a linking number is undefined until the opening
is bridged. The declared closure is a straight chord across the opening
(`_c_ring_geometry.centerline`), and it is not an arbitrary choice: that chord is the
very segment the closed ring's body has to cross, so "the reading changed" and "the
body went through the opening" are the same event.

**The projection is derived from the layout, not configured.** Both rings turn with
`stand.hang_yaw_deg`, and a matrix that was right at one bearing looked straight down
the C's own plane at another and read `Lk = -2`. `_c_ring_geometry.bisector_projection` takes
the bisector of the two ring normals, which puts both rings at 45 degrees. The judge
therefore reads `|Lk|`, not `Lk`: the sign follows the handedness of that basis and
flipped from -1 to +1 when the stand was turned, with no change to the interlock.

**The end state alone cannot judge this task.** The C ring carried on an assisted
attachment has its pose written every step, so a trajectory that should have jammed
tunnels through the closed ring instead -- and once it is 90 mm away it reads
unlinked, because it *is* unlinked. Both the correct extraction and the shortcut end
in the same state. So the reading needs path evidence: `min_gap_seen`, the smallest
surface clearance the two chains ever had, fed in by a caller that samples it while
the episode runs. `swap_crossing_sign`'s `separated_seen` is the same shape of
argument.

The physical recheck lives in `topogym/tasks/entangle/_c_ring_travel_probe.py`,
because it has to step physics and this package stays free of side effects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from topogym.tasks.entangle import _c_ring_geometry as ring_geometry
from topogym.tasks.entangle._c_ring_geometry import opening_to_bar_deg
from topogym.tasks.entangle.unlink_c_ring import UnlinkCRingScene
from topogym.world.closed_band import crossings_between, linking_number

INVARIANT_NAME = "signed_crossing_sequence"

# Curve numbering for the crossing sequence. Fixed by the order the centerlines are
# handed to `crossings_between`, and written down because the sequence is meaningless
# without it.
FIXED_RING = 0
C_RING = 1

# Below this the reading is treated as unlinked. The linking number of two closed
# curves is an integer, so anything near zero is zero; the tolerance only absorbs the
# chord approximation, which moves nothing by half a crossing.
_UNLINKED_TOLERANCE = 0.5


def _entity_pos(entity) -> np.ndarray:
    value = entity.get_pos()
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value).reshape(-1, 3)[0].astype(float)


def _entity_quat(entity) -> np.ndarray:
    value = entity.get_quat()
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value).reshape(-1, 4)[0].astype(float)


def _quat_to_matrix(quat) -> np.ndarray:
    w, x, y, z = (float(v) for v in np.asarray(quat, dtype=float).reshape(4))
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
            [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
            [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
        ],
        dtype=float,
    )


def c_ring_frame(ring_scene: UnlinkCRingScene) -> ring_geometry.RingFrame:
    """The C's current ring frame, read back from the solver.

    The body was written with its URDF origin at the ring's centre and spawned
    unrotated, so the entity's pose IS the frame's rigid transform -- no offset to
    unwind, which is why `add_rigid_assembly` was given centre-relative shapes.
    """

    entity = ring_scene.c_ring_entity()
    rotation = _quat_to_matrix(_entity_quat(entity))
    center = _entity_pos(entity) - np.asarray(ring_scene.layout.task_origin, dtype=float)
    spawn = ring_scene.geometry.c_spawn_frame
    return ring_geometry.RingFrame(
        center=center, normal=rotation @ spawn.normal, ref=rotation @ spawn.ref
    )


def signed_crossing_sequence(crossings) -> tuple[tuple[int, int, int], ...]:
    """`(over curve, under curve, sign)` per crossing, sorted.

    Section 4.3's literal form. Note this is NOT
    `swap_crossing_sign_verifier.signed_crossings`, which orders the pair by strand
    index and spends the third slot on which strand is on top. That works there
    because the geometric sign of its single crossing never changes; here the two
    crossings of a link share one geometric sign and differ in which ring is over, so
    both facts have to be carried separately.
    """

    out = []
    for crossing in crossings:
        over = int(crossing.over_curve)
        out.append((over, FIXED_RING if over == C_RING else C_RING, int(crossing.sign)))
    return tuple(sorted(out))


@dataclass(frozen=True)
class UnlinkCRingPuzzleState:
    """One reading of the two rings, with the thresholds it was judged against."""

    crossings: tuple[tuple[int, int, int], ...]
    linking: float
    surface_gap: float
    min_surface_gap: float
    opening_to_bar_deg: float
    center_drift: float
    tilt_deg: float
    projection_viewer: tuple[float, float, float]
    gap_deg: float
    min_gap_seen: float | None = None
    jam_depth: float = 0.001
    travel_tested: bool = False
    travel_free: bool = False
    travel_info: dict[str, Any] = field(default_factory=dict)
    release_stable: bool = True

    @property
    def invariant_value(self) -> tuple[tuple[int, int, int], ...]:
        return self.crossings

    @property
    def crossing_count(self) -> int:
        return len(self.crossings)

    @property
    def unlinked(self) -> bool:
        return bool(abs(self.linking) < _UNLINKED_TOLERANCE)

    @property
    def separated(self) -> bool:
        """Clear of the other ring by a real margin, not merely not overlapping.

        A pose that reads unlinked while the two surfaces are still touching is a
        reading taken mid-extraction, not a finished one.
        """

        return bool(self.surface_gap >= self.min_surface_gap)

    @property
    def path_watched(self) -> bool:
        return self.min_gap_seen is not None

    @property
    def passed_through(self) -> bool:
        """Did the two bodies ever interpenetrate on the way here?

        The one reading that separates the gateway from the shortcut, because their
        end states are identical. Unwatched paths report False rather than None so
        the predicate stays a boolean; `path_watched` says whether it means anything.
        """

        return bool(
            self.min_gap_seen is not None and self.min_gap_seen < -abs(self.jam_depth)
        )

    @property
    def geometry_ok(self) -> bool:
        return bool(self.unlinked and self.separated and not self.passed_through)

    @property
    def judge_disagrees(self) -> bool:
        """Geometry says unlinked, yet the ring cannot be pushed anywhere.

        The judge is wrong, not the run. Worth surfacing rather than failing on:
        it means the closure or the projection is misreading the scene.
        """

        return bool(self.unlinked and self.travel_tested and not self.travel_free)

    @property
    def probe_uninformative(self) -> bool:
        """The ring moved freely while still linked -- the push overpowered the interlock."""

        return bool(self.travel_tested and self.travel_free and not self.unlinked)

    @property
    def is_terminal(self) -> bool:
        return bool(
            self.geometry_ok
            and self.path_watched
            and self.travel_free
            and self.release_stable
        )

    def to_info(self) -> dict[str, Any]:
        return {
            # --- the category invariant -------------------------------------
            "invariant": INVARIANT_NAME,
            "invariant_value": [list(item) for item in self.invariant_value],
            "crossing_count": self.crossing_count,
            # Derived from the same crossings; the judge reads its magnitude, since
            # the sign follows the handedness of the projection basis.
            "linking_number": float(self.linking),
            "linking_number_abs": float(abs(self.linking)),
            # --- declarations Section 4.3 requires --------------------------
            "projection": {
                "viewer": [float(v) for v in self.projection_viewer],
                "rule": "bisector of the two ring normals, derived from the layout",
            },
            "canonical_closure": (
                "the C ring's opening is bridged by a straight chord; that chord is "
                "the segment the closed ring's body crosses"
            ),
            "boundary_condition": "the closed ring is fixed to the stand and never moves",
            "gateway": "c_ring_opening",
            "gap_deg": float(self.gap_deg),
            # --- geometry readings ------------------------------------------
            "surface_gap": float(self.surface_gap),
            "min_surface_gap": float(self.min_surface_gap),
            "separated": bool(self.separated),
            "opening_to_bar_deg": float(self.opening_to_bar_deg),
            "center_drift": float(self.center_drift),
            "tilt_deg": float(self.tilt_deg),
            "unlinked": bool(self.unlinked),
            # --- path evidence, not an endpoint predicate --------------------
            "path_watched": bool(self.path_watched),
            "min_gap_seen": None if self.min_gap_seen is None else float(self.min_gap_seen),
            "jam_depth": float(self.jam_depth),
            "passed_through": bool(self.passed_through),
            "geometry_ok": bool(self.geometry_ok),
            # --- physical recheck, reported separately ----------------------
            "travel_tested": bool(self.travel_tested),
            "travel_free": bool(self.travel_free),
            "free_translation": dict(self.travel_info),
            "release_stable": bool(self.release_stable),
            "judge_disagrees": bool(self.judge_disagrees),
            "probe_uninformative": bool(self.probe_uninformative),
            "terminal": bool(self.is_terminal),
        }


@dataclass(frozen=True)
class UnlinkCRingPuzzleEvaluator:
    """Success = unlinked, clear of the ring, free to translate, and stays put."""

    min_surface_gap: float = 0.002
    jam_depth: float = 0.001

    @classmethod
    def from_config(cls, task_cfg) -> "UnlinkCRingPuzzleEvaluator":
        success = getattr(task_cfg, "success", None)
        topology = getattr(task_cfg, "topology", None)
        return cls(
            min_surface_gap=0.002 if success is None else float(success.min_surface_gap),
            jam_depth=0.001 if topology is None else float(topology.jam_depth),
        )

    def classify(
        self,
        ring_scene: UnlinkCRingScene,
        *,
        frame: ring_geometry.RingFrame | None = None,
        min_gap_seen: float | None = None,
        travel=None,
        release_stable: bool = True,
    ) -> UnlinkCRingPuzzleState:
        """Read the scene, or a hypothetical pose of the C ring.

        ``frame`` exists so a caller can ask what a pose WOULD read -- the spawn pose
        before anything has stepped, or a waypoint along a planned trajectory --
        without moving the body to find out. Left out, it reads the solver.
        """

        geometry = ring_scene.geometry
        frame = c_ring_frame(ring_scene) if frame is None else frame
        fixed_line = ring_geometry.centerline(geometry.fixed, geometry.fixed_frame)
        c_line = ring_geometry.centerline(
            geometry.c_ring, frame, closure_samples=geometry.closure_samples
        )
        crossings = crossings_between(fixed_line, c_line, projection=geometry.projection)

        return UnlinkCRingPuzzleState(
            crossings=signed_crossing_sequence(crossings),
            linking=float(linking_number(fixed_line, c_line, projection=geometry.projection)),
            surface_gap=float(
                ring_geometry.surface_gap(geometry.fixed_axes(), geometry.c_axes(frame))
            ),
            min_surface_gap=float(self.min_surface_gap),
            opening_to_bar_deg=opening_to_bar_deg(geometry, frame),
            center_drift=float(np.linalg.norm(frame.center - geometry.c_rest_frame.center)),
            # How far the ring's plane has cocked off the bar's axis. Zero all
            # through a roll about that axis, so it reads only genuine wobble.
            tilt_deg=float(
                np.rad2deg(
                    np.arccos(
                        np.clip(abs(float(np.dot(frame.normal, geometry.tube_direction))), -1.0, 1.0)
                    )
                )
            ),
            projection_viewer=tuple(float(v) for v in geometry.projection[2]),
            gap_deg=float(geometry.c_ring.gap_deg),
            min_gap_seen=None if min_gap_seen is None else float(min_gap_seen),
            jam_depth=float(self.jam_depth),
            travel_tested=travel is not None,
            travel_free=bool(travel.all_free) if travel is not None else False,
            travel_info=travel.to_info() if travel is not None else {},
            release_stable=bool(release_stable),
        )

    def is_success(self, ring_scene: UnlinkCRingScene, **kwargs) -> bool:
        return self.classify(ring_scene, **kwargs).is_terminal
