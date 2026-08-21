"""Terminal judgement for `swap_crossing_sign` (docx 3.2).

The crossing geometry is measured exactly as in the continuous-untangle variant
-- same top-down projection, same centerline sampling, same merge radius -- so
all of that is imported rather than restated. What is task-specific is the
predicate on top of it.

`untangle_continuous` asks "are they apart"; this task asks "did who-is-on-top
change, with everything else still a single crossing". That is a comparison
against the state the episode *started* in, which is why this evaluator is not
stateless the way the untangle one is: `classify` takes the signature captured
after the spawn settle, plus whether the episode has been observed in a fully
separated state.

Per `docs/develop/framework/task_taxonomy_zh.md` §4.3 (category C3), the
invariant is the *signed* crossing sequence, and `to_info()` has to state the
projection direction and the fixed boundary conditions alongside it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from topogym.tasks.entangle.untangle_continuous import UntangleContinuousScene

from .untangle_continuous_verifier import (
    GeoCrossing,
    count_crossings,
    min_inter_strand_distance,
    strand_polylines,
)

# Sign convention, matching `generation/braid.py`'s sigma letters: positive means
# the lower-numbered strand is the one on top.
SignedCrossing = tuple[int, int, int]


def signed_crossings(crossings) -> tuple[SignedCrossing, ...]:
    """`(lo_strand, hi_strand, +1 if lo is on top else -1)`, sorted.

    Ordering the pair by strand index rather than by over/under is what makes two
    signatures comparable: the *pair* stays put while the sign is the thing under
    test, so `(0, 1, +1)` and `(0, 1, -1)` differ in exactly one number.
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
    crossings: tuple[GeoCrossing, ...]
    min_separation: float  # closest approach between any two strands, meters
    separation_threshold: float
    # Signed signature of the freshly settled scene: what the sign has to flip
    # away from. Empty means it was never captured, which is a programming error
    # rather than a state -- `is_terminal` refuses in that case.
    initial_signature: tuple[SignedCrossing, ...] = ()
    # Has the episode been seen with the ropes fully apart? This is the path
    # component of the predicate; see `is_terminal`.
    separated_seen: bool = False

    @property
    def crossing_count(self) -> int:
        return len(self.crossings)

    @property
    def is_separated(self) -> bool:
        return self.min_separation >= self.separation_threshold

    @property
    def invariant_value(self) -> tuple[SignedCrossing, ...]:
        return signed_crossings(self.crossings)

    @property
    def sign_flipped(self) -> bool:
        """Same single crossing, same two strands, opposite sign."""

        current = self.invariant_value
        if len(current) != 1 or len(self.initial_signature) != 1:
            return False
        lo, hi, sign = current[0]
        lo0, hi0, sign0 = self.initial_signature[0]
        return (lo, hi) == (lo0, hi0) and sign == -sign0

    @property
    def is_terminal(self) -> bool:
        """One crossing, same pair, opposite sign, and it went through zero.

        The first three conditions are the docx's state change. The fourth is
        what keeps this from being a pure endpoint predicate: the two cables have
        to have been measured fully apart at some point in the episode. Without
        it, a policy that never separated them -- that merely nudged the contact
        until the z measurement changed sign -- would read as success, and so
        would one that dragged the lower cable out from under the upper one, a
        motion this task deliberately does not use (see the task module's
        docstring for why).
        """

        return self.crossing_count == 1 and self.sign_flipped and self.separated_seen

    def to_info(self) -> dict[str, Any]:
        return {
            # C3 contract: the invariant, and what makes it well defined.
            "invariant": "signed_crossing_sequence",
            "invariant_value": [list(entry) for entry in self.invariant_value],
            "projection": "top_down_xy",
            "boundary_condition": "each strand anchored at its power-strip end; free ends unconstrained",
            "initial_signature": [list(entry) for entry in self.initial_signature],
            "sign_flipped": bool(self.sign_flipped),
            "separated_seen": bool(self.separated_seen),
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
            # Task-level tightening, listed apart from the invariant per §4.3.
            "min_separation": float(self.min_separation),
            "separation_threshold": float(self.separation_threshold),
            "is_separated": bool(self.is_separated),
            "terminal": bool(self.is_terminal),
        }


@dataclass(frozen=True)
class SwapCrossingSignPuzzleEvaluator:
    """Measure the signed top-down crossing and compare it against the spawn."""

    separation_threshold: float
    merge_radius: float
    samples: int = 80

    @classmethod
    def from_config(cls, task_cfg) -> SwapCrossingSignPuzzleEvaluator:
        success = task_cfg.success
        return cls(
            separation_threshold=float(success.separation_threshold),
            merge_radius=float(success.crossing_merge_radius),
            samples=int(success.centerline_samples),
        )

    def classify(
        self,
        rope_scene: UntangleContinuousScene,
        *,
        initial_signature: tuple[SignedCrossing, ...] = (),
        separated_seen: bool = False,
    ) -> SwapCrossingSignPuzzleState:
        polylines = strand_polylines(rope_scene, samples=self.samples)
        return SwapCrossingSignPuzzleState(
            crossings=count_crossings(polylines, merge_radius=self.merge_radius),
            min_separation=min_inter_strand_distance(polylines),
            separation_threshold=self.separation_threshold,
            initial_signature=tuple(initial_signature),
            separated_seen=bool(separated_seen),
        )

    def capture_initial_signature(
        self,
        rope_scene: UntangleContinuousScene,
    ) -> tuple[SignedCrossing, ...]:
        """The signature to flip away from, read off the settled spawn state."""

        return self.classify(rope_scene).invariant_value

    def matches_braid_ground_truth(
        self,
        rope_scene: UntangleContinuousScene,
    ) -> tuple[bool, str]:
        """Does the detector's signed reading agree with the braid word?

        The braid generator already knows which strand it put on top, so this is
        free evidence that the sign this task grades is measured correctly at all
        -- and unlike the untangle variant's version, it compares the *sign*,
        which is the quantity under test here. Only meaningful on the freshly
        settled scene; once a rope is moved the braid word is history.
        """

        detected = self.classify(rope_scene).invariant_value
        expected = signed_crossings(rope_scene.braid.crossings)
        if detected != expected:
            return False, f"signed_crossings detected={detected} != gt={expected}"
        return True, f"signed_crossings={detected}"
