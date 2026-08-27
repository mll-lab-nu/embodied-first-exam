"""Terminal judgement for `band_untwist` (docx 3.3): one rope, its own crossings.

The other entangle verifiers count crossings *between* strands
(`untangle_continuous_verifier.count_crossings` iterates distinct strand pairs and
never compares a polyline with itself). This task has one rope whose only
crossing is with itself, so it needs the single-curve count. `world/closed_band.py`
has one, but for a CLOSED curve: it wraps segment ``N-1`` back to ``0``, and on an
open rope whose two ends lie side by side that phantom closing segment sits right
where the real geometry is and corrupts the count. Hence the open-polyline kernel
below, written here rather than imported from either place (same rule as the
module-boundaries doc: no private symbols across modules).

Per `docs/develop/framework/task_taxonomy_zh.md` §4.3 (category C3) the
invariant is `self_crossing_number`, and `to_info()` states the projection and
the fixed boundary conditions alongside it. It is a projected count, which is
what makes the docx's anti-shortcut hold: pressing the 8 flat or hiding the
crossing behind the other strand changes the depth gap, not the count.

The docx's physical layer ("pull the band's lower edge down and check the
perimeter opens into one loop") is deferred, exactly as `untangle_continuous`
defers its lift-test: it needs the arm, and the geometric reading is what drives
the oracle and grades the episode today.

No Genesis import at module level, so `tests/check_band_untwist_geometry.py` can
load this file by path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:  # pragma: no cover
    from topogym.tasks.entangle.band_untwist import BandUntwistScene


@dataclass(frozen=True)
class SelfCrossing:
    """One measured top-down crossing of the rope with itself."""

    position: tuple[float, float]  # world xy of the crossing
    z_gap: float  # over centerline z minus under centerline z
    over_at: float  # normalized arc length (0..1) of the strand on top
    under_at: float  # normalized arc length of the strand underneath
    sign: int  # +1 / -1, the signed-crossing convention below

    @property
    def over_end(self) -> int:
        """Which rope end (0 or 1) the over strand is nearer to, by arc length."""

        return 0 if self.over_at < 0.5 else 1


def _segment_hit(p0, p1, q0, q1):
    """Return (t, u) where 2D segments p and q properly cross, else None."""

    r = p1[:2] - p0[:2]
    s = q1[:2] - q0[:2]
    denom = float(r[0] * s[1] - r[1] * s[0])
    if abs(denom) < 1e-12:
        return None
    diff = q0[:2] - p0[:2]
    t = float(diff[0] * s[1] - diff[1] * s[0]) / denom
    u = float(diff[0] * r[1] - diff[1] * r[0]) / denom
    if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
        return t, u
    return None


def open_self_crossings(
    polyline: np.ndarray,
    *,
    merge_radius: float,
    skip_adjacent: int = 2,
) -> tuple[SelfCrossing, ...]:
    """Signed top-down self-crossings of one OPEN polyline.

    Segment ``i`` runs from sample ``i`` to ``i+1`` for ``i < N-1``; there is no
    segment from the last sample back to the first. Pairs closer than
    ``skip_adjacent`` along the curve are skipped -- they share a vertex or nearly
    do, so their "crossing" is the curve touching itself. Adjacency is linear:
    the first and last segments are *not* neighbours.

    Over/under comes from the z of each strand at the hit, so it is a
    measurement. Hits within ``merge_radius`` of each other collapse into one,
    keeping the largest depth gap: one physical crossing spans several centerline
    segments. Sign is ``over x under`` in the xy plane (+1 when the under strand
    runs to the left of the over strand's direction).
    """

    points = np.asarray(polyline, dtype=float)
    count = len(points)
    if count < 2:
        return ()
    segments = count - 1
    raw: list[SelfCrossing] = []
    for i in range(segments):
        a0, a1 = points[i], points[i + 1]
        for j in range(i + int(skip_adjacent) + 1, segments):
            b0, b1 = points[j], points[j + 1]
            hit = _segment_hit(a0, a1, b0, b1)
            if hit is None:
                continue
            t, u = hit
            point = a0[:2] + t * (a1[:2] - a0[:2])
            za = a0[2] + t * (a1[2] - a0[2])
            zb = b0[2] + u * (b1[2] - b0[2])
            at_a = (i + t) / segments
            at_b = (j + u) / segments
            if za >= zb:
                over, under = a1 - a0, b1 - b0
                over_at, under_at = at_a, at_b
            else:
                over, under = b1 - b0, a1 - a0
                over_at, under_at = at_b, at_a
            twist = float(over[0] * under[1] - over[1] * under[0])
            raw.append(
                SelfCrossing(
                    position=(float(point[0]), float(point[1])),
                    z_gap=abs(float(za - zb)),
                    over_at=float(over_at),
                    under_at=float(under_at),
                    sign=1 if twist > 0.0 else -1,
                )
            )
    return _merge_nearby(raw, merge_radius=float(merge_radius))


def _merge_nearby(hits: list[SelfCrossing], *, merge_radius: float) -> tuple[SelfCrossing, ...]:
    """Collapse hits within ``merge_radius`` into one, keeping the largest z gap."""

    merged: list[SelfCrossing] = []
    for hit in hits:
        for index, kept in enumerate(merged):
            distance = float(
                np.hypot(hit.position[0] - kept.position[0], hit.position[1] - kept.position[1])
            )
            if distance <= merge_radius:
                if hit.z_gap > kept.z_gap:
                    merged[index] = hit
                break
        else:
            merged.append(hit)
    return tuple(merged)


def _entity_xyz(entity) -> np.ndarray:
    raw = entity.get_pos()
    if hasattr(raw, "detach"):
        raw = raw.detach().cpu().numpy()
    return np.asarray(raw, dtype=float).reshape(-1)[:3]


@dataclass(frozen=True)
class BandUntwistPuzzleState:
    crossings: tuple[SelfCrossing, ...]
    # z of each free-end plug above the table, in end order (0, 1).
    end_heights: tuple[float, float]
    end_height_tolerance: float

    @property
    def crossing_count(self) -> int:
        return len(self.crossings)

    @property
    def invariant_value(self) -> int:
        return self.crossing_count

    @property
    def ends_on_table(self) -> bool:
        """Both plugs resting on the table.

        Zero crossings while a plug is still in the air is not a solved 8 --
        it is a rope being held up. The reading has to be taken with the rope
        released.
        """

        return all(height <= self.end_height_tolerance for height in self.end_heights)

    @property
    def is_terminal(self) -> bool:
        return self.crossing_count == 0 and self.ends_on_table

    @property
    def failure_label(self) -> str | None:
        """The docx's contrast: flipping from the wrong side makes 2, not 0."""

        if self.crossing_count >= 2:
            return "wrong_end"
        return None

    def to_info(self) -> dict[str, Any]:
        return {
            # C3 contract: the invariant, and what makes it well defined.
            "invariant": "self_crossing_number",
            "invariant_value": int(self.invariant_value),
            "projection": "top_down_xy",
            "boundary_condition": "open rope on the tabletop, both ends free; held by friction only",
            "crossings": [
                {
                    "position": [float(c.position[0]), float(c.position[1])],
                    "z_gap": float(c.z_gap),
                    "over_at": float(c.over_at),
                    "under_at": float(c.under_at),
                    "over_end": int(c.over_end),
                    "sign": int(c.sign),
                }
                for c in self.crossings
            ],
            "crossing_count": int(self.crossing_count),
            # Task-level tightening, listed apart from the invariant per §4.3.
            "end_heights": [float(h) for h in self.end_heights],
            "end_height_tolerance": float(self.end_height_tolerance),
            "ends_on_table": bool(self.ends_on_table),
            "failure_label": self.failure_label,
            "terminal": bool(self.is_terminal),
        }


@dataclass(frozen=True)
class BandUntwistPuzzleEvaluator:
    """Count the rope's top-down self-crossings on a settled scene."""

    merge_radius: float
    end_height_tolerance: float
    samples: int = 80

    @classmethod
    def from_config(cls, task_cfg) -> BandUntwistPuzzleEvaluator:
        success = task_cfg.success
        return cls(
            merge_radius=float(success.crossing_merge_radius),
            end_height_tolerance=float(success.end_height_tolerance),
            samples=int(success.centerline_samples),
        )

    def polyline(self, rope_scene: BandUntwistScene) -> np.ndarray:
        return rope_scene.strand_centerline(0, samples=self.samples)

    def classify(self, rope_scene: BandUntwistScene) -> BandUntwistPuzzleState:
        polyline = self.polyline(rope_scene)
        table_z = float(rope_scene.layout.world_z(0.0))
        # Plug axis height above the table when it lies on its flange, so a
        # resting plug reads ~0 rather than one flange radius.
        rest = float(rope_scene.connector_rest_height)
        heights = tuple(
            float(_entity_xyz(rope_scene.free_end_connectors[end])[2] - table_z - rest)
            for end in (0, 1)
        )
        return BandUntwistPuzzleState(
            crossings=open_self_crossings(polyline, merge_radius=self.merge_radius),
            end_heights=heights,
            end_height_tolerance=self.end_height_tolerance,
        )

    def is_success(self, rope_scene: BandUntwistScene) -> bool:
        return self.classify(rope_scene).is_terminal

    def matches_spawn_ground_truth(self, rope_scene: BandUntwistScene) -> tuple[bool, str]:
        """Self-check on the settled spawn: exactly one crossing, and the strand
        the generator raised is the one measured on top.

        Only meaningful before the rope is moved; afterwards the spawn is history.
        """

        state = self.classify(rope_scene)
        expected_end = int(rope_scene.layout.over_end)
        if state.crossing_count != 1:
            return False, f"crossing_count detected={state.crossing_count} != gt=1"
        measured_end = state.crossings[0].over_end
        if measured_end != expected_end:
            return False, (
                f"over_end detected={measured_end} != gt={expected_end} "
                f"(over_at={state.crossings[0].over_at:.2f})"
            )
        return True, (
            f"crossings=1 over_end={measured_end} z_gap={state.crossings[0].z_gap * 1000:.1f}mm"
        )
