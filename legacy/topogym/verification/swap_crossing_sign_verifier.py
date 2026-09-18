"""Terminal judgement for `swap_crossing_sign` (docx 3.2).

Scene: 2 or 3 ropes from a power strip cross each other once or twice. The
episode succeeds when, in the END state (ropes released and settled), every pair
of ropes that crossed at spawn still crosses the same number of times, with the
other rope on top. Extra or missing crossings fail. Neither where the ropes end
up nor the order of a pair's crossings along them is graded (decision
2026-09-12): what the task asks for is that where A lay over B, B now lies over
A. Nothing about the path is graded either (decision 2026-09-10; the old
`separated_seen` path condition is gone).

The crossings are read the way `untangle_continuous_verifier.count_crossings`
reads them (top-down projection of the 80-bin centerlines, higher z on top, hits
of one pair within the merge radius merged), by `planning/rope_crossings.py`,
which also keeps where each crossing sits along both ropes. Those ranks are what
`relation_flipped` falls back on when a pair crosses TWICE: "A over then B over"
and its flip are the same pair of tops, so only the ranked form tells them apart.

Per `docs/develop/framework/task_taxonomy_zh.md` §4.3 (category C3), `to_info()`
states the invariant, the projection and the boundary conditions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from topogym.planning.rope_crossings import (
    CrossingCode,
    RopeCrossing,
    code_text,
    crossing_code,
    failure_label,
    find_crossings,
    flip_code,
    relation_flipped,
)
from topogym.tasks_legacy.entangle._swap_crossing_sign_scene import expected_code
from topogym.tasks_legacy.entangle.untangle_continuous import UntangleContinuousScene

from .untangle_continuous_verifier import min_inter_strand_distance, strand_polylines

# Sign convention, matching `generation/braid.py`'s sigma letters: positive means
# the lower-numbered strand is the one on top.
SignedCrossing = tuple[int, int, int]


def signed_crossings(crossings) -> tuple[SignedCrossing, ...]:
    """`(lo_strand, hi_strand, +1 if lo is on top else -1)`, sorted.

    Kept for the log and for callers outside this task; the predicate below uses
    the crossing code instead, because this sorted form cannot tell two ropes
    crossing twice apart from the same two ropes with both crossings flipped.
    """

    out = []
    for crossing in crossings:
        over = int(crossing.over_strand)
        under = int(crossing.under_strand)
        lo, hi = (over, under) if over < under else (under, over)
        out.append((lo, hi, 1 if over == lo else -1))
    return tuple(sorted(out))


@dataclass(frozen=True)
class SwapCrossingSignPuzzleState:
    crossings: tuple[RopeCrossing, ...]
    min_separation: float  # closest approach between any two strands, meters
    # The code of the freshly settled spawn: what every crossing has to flip away
    # from. Empty means it was never captured -- `is_terminal` refuses then.
    spawn_code: CrossingCode = ()

    @property
    def crossing_count(self) -> int:
        return len(self.crossings)

    @property
    def code(self) -> CrossingCode:
        return crossing_code(self.crossings)

    @property
    def invariant_value(self) -> CrossingCode:
        return self.code

    @property
    def target_code(self) -> CrossingCode:
        return flip_code(self.spawn_code)

    @property
    def is_terminal(self) -> bool:
        """Every pair of ropes that crossed at spawn now crosses with the other one on top.

        Where the ropes ended up, and in what order a pair's crossings sit along
        them, are not graded (decision 2026-09-12) -- `target_code` below is one
        end state that satisfies this, not the only one.
        """

        return bool(self.spawn_code) and relation_flipped(self.code, self.spawn_code)

    @property
    def failure_label(self) -> str | None:
        """None on success; else unchanged / partial_flip / extra_crossing / missing_crossing / reordered."""

        if not self.spawn_code:
            return "no_spawn_code"
        return failure_label(self.code, self.spawn_code)

    def to_info(self) -> dict[str, Any]:
        return {
            # C3 contract: the invariant, and what makes it well defined.
            "invariant": "crossing_code",
            "invariant_value": [list(entry) for entry in self.code],
            "projection": "top_down_xy",
            "boundary_condition": "each strand anchored at its power-strip end; free ends unconstrained",
            "spawn_code": [list(entry) for entry in self.spawn_code],
            "target_code": [list(entry) for entry in self.target_code],
            "crossings": [
                {
                    "over": int(c.over_strand),
                    "under": int(c.under_strand),
                    "position": [float(c.position[0]), float(c.position[1])],
                    "z_gap": float(c.z_gap),
                    "s": {int(c.a): float(c.s_a), int(c.b): float(c.s_b)},
                }
                for c in self.crossings
            ],
            "crossing_count": int(self.crossing_count),
            "min_separation": float(self.min_separation),
            "failure_label": self.failure_label,
            "terminal": bool(self.is_terminal),
        }


@dataclass(frozen=True)
class SwapCrossingSignPuzzleEvaluator:
    """Read the crossing code and compare it with the spawn's."""

    merge_radius: float
    samples: int = 80

    @classmethod
    def from_config(cls, task_cfg) -> SwapCrossingSignPuzzleEvaluator:
        success = task_cfg.success
        return cls(
            merge_radius=float(success.crossing_merge_radius),
            samples=int(success.centerline_samples),
        )

    def classify(
        self,
        rope_scene: UntangleContinuousScene,
        *,
        spawn_code: CrossingCode = (),
    ) -> SwapCrossingSignPuzzleState:
        polylines = strand_polylines(rope_scene, samples=self.samples)
        return SwapCrossingSignPuzzleState(
            crossings=find_crossings(polylines, merge_radius=self.merge_radius),
            min_separation=min_inter_strand_distance(polylines),
            spawn_code=tuple(spawn_code),
        )

    def capture_spawn_code(self, rope_scene: UntangleContinuousScene) -> CrossingCode:
        """The code to flip away from, read off the settled spawn state."""

        return self.classify(rope_scene).code

    def matches_braid_ground_truth(self, rope_scene: UntangleContinuousScene) -> tuple[bool, str]:
        """Does the detector's reading of the settled spawn equal what the generator built?

        The generator knows which rope it put on top at each crossing and in what
        order; if the detector disagrees on the spawn, the grade at the end would
        be read off tubes that do not show what they were built to show.
        """

        detected = self.classify(rope_scene).code
        expected = expected_code(rope_scene.braid.crossings)
        if detected != expected:
            return False, f"code detected=[{code_text(detected)}] != gt=[{code_text(expected)}]"
        return True, f"code=[{code_text(detected)}]"


__all__ = [
    "SignedCrossing",
    "SwapCrossingSignPuzzleEvaluator",
    "SwapCrossingSignPuzzleState",
    "signed_crossings",
]
