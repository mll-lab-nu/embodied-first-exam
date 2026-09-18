"""Geometric topology judgement for the continuous Untangle variant.

The discrete variant decides crossings combinatorially, on grid hole indices
(the removed `untangle` task's MDP shell). That was unusable here: the continuous variant
has no holes, and the ropes are wherever physics put them. So crossings are
measured on the actual PBD particles, projected top-down.

Two layers, per the design doc:

- **geometric proxy** (`crossing_count == 0` plus a separation margin) — cheap,
  computed every step, drives the oracle and any reward shaping;
- **physical lift-test** — the episode-end gold standard. Deferred to P4: it
  needs the robot to actually grasp and lift a free end, which does not exist
  until the pinch primitive lands.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from topogym.tasks_legacy.entangle.untangle_continuous import UntangleContinuousScene


@dataclass(frozen=True)
class GeoCrossing:
    """One measured top-down crossing between two strands."""

    over_strand: int
    under_strand: int
    position: tuple[float, float]  # world xy of the crossing
    z_gap: float  # over centerline z minus under centerline z


@dataclass(frozen=True)
class UntangleContinuousPuzzleState:
    crossings: tuple[GeoCrossing, ...]
    min_separation: float  # closest approach between any two strands, meters
    separation_threshold: float

    @property
    def crossing_count(self) -> int:
        return len(self.crossings)

    @property
    def is_separated(self) -> bool:
        return self.min_separation >= self.separation_threshold

    @property
    def is_terminal(self) -> bool:
        """Geometric proxy for "untangled and moved aside".

        Zero crossings alone is not enough: two ropes can lie side by side,
        touching, with no top-down crossing. The separation margin is what makes
        the state read as deliberately sorted rather than accidentally uncrossed.
        """

        return self.crossing_count == 0 and self.is_separated

    def to_info(self) -> dict[str, Any]:
        return {
            "crossings": [
                {
                    "over": int(c.over_strand),
                    "under": int(c.under_strand),
                    "position": [float(c.position[0]), float(c.position[1])],
                    "z_gap": float(c.z_gap),
                }
                for c in self.crossings
            ],
            "crossing_count": int(self.crossing_count),
            "min_separation": float(self.min_separation),
            "separation_threshold": float(self.separation_threshold),
            "is_separated": bool(self.is_separated),
            "terminal": bool(self.is_terminal),
        }


def strand_polylines(rope_scene: UntangleContinuousScene, *, samples: int = 80) -> dict[int, np.ndarray]:
    """Ordered centerline polyline per strand. See `scene.strand_centerline`.

    The binning lives on the scene so settling and crossing detection measure the
    same curve -- if they diverged, "the rope stopped moving" and "the ropes
    cross here" would be statements about two different geometries.
    """

    return {
        strand_index: rope_scene.strand_centerline(strand_index, samples=samples)
        for strand_index in sorted(rope_scene.strand_entities)
    }


def _segment_crossing(p0, p1, q0, q1):
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


def count_crossings(
    polylines: dict[int, np.ndarray],
    *,
    merge_radius: float,
) -> tuple[GeoCrossing, ...]:
    """Count top-down crossings between distinct strands.

    Over/under comes from the centerline z at the crossing point, so it is a
    measurement rather than an assumption. Hits closer together than
    ``merge_radius`` are merged: one physical crossing spans several centerline
    segments, and would otherwise be counted once per intersecting segment pair.
    """

    hits: list[GeoCrossing] = []
    strands = sorted(polylines)
    for a_pos in range(len(strands)):
        for b_pos in range(a_pos + 1, len(strands)):
            a, b = strands[a_pos], strands[b_pos]
            pa, pb = polylines[a], polylines[b]
            raw: list[GeoCrossing] = []
            for i in range(len(pa) - 1):
                for j in range(len(pb) - 1):
                    hit = _segment_crossing(pa[i], pa[i + 1], pb[j], pb[j + 1])
                    if hit is None:
                        continue
                    t, u = hit
                    point = pa[i, :2] + t * (pa[i + 1, :2] - pa[i, :2])
                    za = pa[i, 2] + t * (pa[i + 1, 2] - pa[i, 2])
                    zb = pb[j, 2] + u * (pb[j + 1, 2] - pb[j, 2])
                    over, under = (a, b) if za > zb else (b, a)
                    raw.append(
                        GeoCrossing(
                            over_strand=int(over),
                            under_strand=int(under),
                            position=(float(point[0]), float(point[1])),
                            z_gap=abs(float(za - zb)),
                        )
                    )
            hits.extend(_merge_nearby(raw, merge_radius=merge_radius))
    return tuple(hits)


def _merge_nearby(crossings: list[GeoCrossing], *, merge_radius: float) -> list[GeoCrossing]:
    """Collapse hits within ``merge_radius`` into one, keeping the largest z gap."""

    merged: list[GeoCrossing] = []
    for crossing in crossings:
        for index, kept in enumerate(merged):
            distance = float(
                np.hypot(
                    crossing.position[0] - kept.position[0],
                    crossing.position[1] - kept.position[1],
                )
            )
            if distance <= merge_radius:
                if crossing.z_gap > kept.z_gap:
                    merged[index] = crossing
                break
        else:
            merged.append(crossing)
    return merged


def min_inter_strand_distance(polylines: dict[int, np.ndarray]) -> float:
    """Closest 3D approach between any two distinct strands."""

    strands = sorted(polylines)
    best = float("inf")
    for a_pos in range(len(strands)):
        for b_pos in range(a_pos + 1, len(strands)):
            pa = polylines[strands[a_pos]]
            pb = polylines[strands[b_pos]]
            distance = np.linalg.norm(pa[:, None, :] - pb[None, :, :], axis=2)
            best = min(best, float(distance.min()))
    return best


@dataclass(frozen=True)
class UntangleContinuousPuzzleEvaluator:
    """Measure the top-down rope topology of a settled continuous-untangle scene."""

    separation_threshold: float
    merge_radius: float
    samples: int = 80

    @classmethod
    def from_config(cls, task_cfg) -> UntangleContinuousPuzzleEvaluator:
        success = task_cfg.success
        return cls(
            separation_threshold=float(success.separation_threshold),
            merge_radius=float(success.crossing_merge_radius),
            samples=int(success.centerline_samples),
        )

    def classify(self, rope_scene: UntangleContinuousScene) -> UntangleContinuousPuzzleState:
        polylines = strand_polylines(rope_scene, samples=self.samples)
        return UntangleContinuousPuzzleState(
            crossings=count_crossings(polylines, merge_radius=self.merge_radius),
            min_separation=min_inter_strand_distance(polylines),
            separation_threshold=self.separation_threshold,
        )

    def is_success(self, rope_scene: UntangleContinuousScene) -> bool:
        return self.classify(rope_scene).is_terminal

    def matches_braid_ground_truth(
        self,
        rope_scene: UntangleContinuousScene,
    ) -> tuple[bool, str]:
        """Self-check: does the detector see exactly the braid word's crossings?

        This is the evidence that the geometric detector is trustworthy at all
        (design doc §3.3). It only holds on the freshly settled initial state --
        once the robot starts moving ropes, the braid word is history.
        """

        state = self.classify(rope_scene)
        expected = rope_scene.braid.crossings
        if len(state.crossings) != len(expected):
            return False, (
                f"crossing_count detected={len(state.crossings)} != gt={len(expected)}"
            )
        detected_pairs = sorted((c.over_strand, c.under_strand) for c in state.crossings)
        expected_pairs = sorted((c.over_strand, c.under_strand) for c in expected)
        if detected_pairs != expected_pairs:
            return False, f"over/under detected={detected_pairs} != gt={expected_pairs}"
        return True, f"crossings={len(expected)} over_under={expected_pairs}"
