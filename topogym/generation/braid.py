"""Braid-word parameterization of the continuous Untangle initial state.

The continuous Untangle variant does NOT scatter ropes randomly and settle. It
samples a word in the braid group, turns that word into analytic control points
(one polyline per strand), and keeps the word as ground truth. Two things fall
out of that for free, which random scattering cannot give:

- **The crossing ground truth.** ``BraidSpec.crossings`` says exactly which strand
  is over which, and where along the main axis. The geometric detector
  (``topogym.supervision.rope_topology``) is validated against it.
- **The optimal solution.** Undoing the word letter by letter, back to front,
  untangles the braid; ``BraidSpec.optimal_sequence`` is that move list, so the
  benchmark can report "actual moves / optimal moves".

Conventions (fixed here, relied on by the scene builder and the planner):

- A word letter is a signed 1-based generator, matching the usual sigma notation:
  ``+1`` is sigma_1, ``-2`` is sigma_2 inverse. ``|letter|`` is in ``1..n-1``.
- sigma_i swaps the two strands currently occupying **channels** ``i-1`` and ``i``
  (0-based). Channels are fixed y lanes; strands move between them.
- A **positive** letter means the strand arriving from the LOWER channel index
  passes OVER the other one. A negative letter means it passes under.
- Channel 0 is the -y lane; the anchored (power-strip) end is at ``x_start``.

This module is pure Python + NumPy on purpose: no Genesis, no OmegaConf. It sits
in ``generation`` because it is the seed-to-geometry boundary, the same role
``layout_randomization`` plays for the deterministic tasks.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from topogym.generation.variant_rng import VariantRng

# A lane swap must run at least this much x per unit of y it travels, i.e. the
# swap stays flatter than ~59 degrees in the top-down view. Steeper than that and
# the swept tube starts to pinch on its own inside radius.
_MIN_WINDOW_PER_LANE = 0.6


@dataclass(frozen=True)
class BraidLayout:
    """Where the braid lives in the task frame (all lengths in meters).

    The task config owns these numbers; the scene builder converts its ``braid:``
    block into this dataclass so the generator stays free of OmegaConf.
    """

    x_start: float  # anchored end (power strip), task frame
    x_end: float  # free end
    center_y: float
    channel_spacing: float  # lane pitch; must clear 2x rope diameter
    base_z: float  # rope centerline height when lying on the table
    over_lift: float  # extra z for the over-strand at a crossing
    braid_span: tuple[float, float] = (0.25, 0.75)  # crossings occupy this fraction of x
    # Fraction of one crossing's x slot used by the lane-swap window. Derived
    # rather than configured as an absolute width on purpose: an absolute width
    # silently overlaps neighbouring crossings once `length` grows (a 5-crossing
    # braid packs its windows ~2.5x tighter than a 2-crossing one).
    crossing_fill: float = 0.8
    # Where the single crossing of a length-1 word sits along the main axis, as
    # a fraction of x_start..x_end, or None for the evenly spaced default. Set by
    # ``swap_crossing_sign``'s layout axis; the swap window is clipped so it stays
    # inside ``braid_span`` (see ``crossing_window_at``). Only defined for one
    # crossing: with more, the slots are equal by construction.
    crossing_frac: float | None = None


@dataclass(frozen=True)
class BraidCrossing:
    """One crossing of the braid, in ground-truth (not measured) form."""

    index: int  # position in the word, 0-based
    over_strand: int
    under_strand: int
    position_frac: float  # along the main axis, 0 at x_start .. 1 at x_end
    sign: int  # +1 / -1


@dataclass(frozen=True)
class BraidSpec:
    """A generated braid: geometry to build, plus the ground truth it encodes."""

    n_strands: int
    word: tuple[int, ...]  # freely reduced; one letter per crossing
    layout: BraidLayout
    control_points: dict[int, np.ndarray]  # strand_idx -> (K, 3) task-frame points
    crossings: tuple[BraidCrossing, ...]  # top-down ground truth, in x order

    @property
    def inverse_word(self) -> tuple[int, ...]:
        """The word that cancels this one (reverse order, flipped signs)."""

        return tuple(-letter for letter in reversed(self.word))

    @property
    def optimal_sequence(self) -> tuple[BraidCrossing, ...]:
        """Crossings in the order the oracle should undo them (last one first).

        NOTE on "optimal": this is an *achievable* move count -- undoing the
        freely reduced word always works, in ``len(word)`` moves. It equals the
        true minimum whenever the reduced word is geodesic in the braid group,
        which free reduction alone does not prove. For the frozen MVP band
        (n_strands=3, length<=5) treat it as the reference cost, and revisit if
        the efficiency metric ever reports a ratio below 1.0.
        """

        return tuple(reversed(self.crossings))


@dataclass(frozen=True)
class BraidVerification:
    """Result of the self-check that stands in for a unit test in this repo."""

    ok: bool
    failures: tuple[str, ...]
    crossing_count: int

    def __str__(self) -> str:
        status = "ok" if self.ok else "FAILED"
        detail = "" if self.ok else " " + "; ".join(self.failures)
        return f"braid_verify={status} crossings={self.crossing_count}{detail}"


def reduce_braid_word(word) -> tuple[int, ...]:
    """Free reduction: repeatedly cancel adjacent ``sigma_i sigma_i^-1`` pairs.

    This is deliberately only *free* reduction, not full braid-group
    normalization (which would need Dehornoy handle reduction). It is what makes
    the crossing count honest: a cancelling pair is not a crossing you can see.
    """

    stack: list[int] = []
    for letter in word:
        value = int(letter)
        if value == 0:
            raise ValueError("Braid word letters are signed 1-based generators; 0 is invalid.")
        if stack and stack[-1] == -value:
            stack.pop()
        else:
            stack.append(value)
    return tuple(stack)


def sample_braid_word(
    *,
    n_strands: int,
    length: int,
    seed: int | None = None,
    rng: np.random.Generator | None = None,
) -> tuple[int, ...]:
    """Sample a freely reduced word of exactly ``length`` letters.

    Letters are rejected as they are drawn rather than reduced afterwards, so the
    requested difficulty always equals the resulting crossing count (a
    reduce-after-sampling scheme would silently hand back shorter braids).

    Randomness comes from ``rng`` when given; otherwise from the episode seed's
    ``"braid/word"`` stream (``VariantRng``), so the word depends only on the seed
    and not on whatever else was drawn before it.
    """

    if int(n_strands) < 2:
        raise ValueError(f"A braid needs >= 2 strands, got {n_strands}.")
    if int(length) < 0:
        raise ValueError(f"Braid length must be >= 0, got {length}.")

    if rng is None:
        if seed is None:
            raise ValueError("sample_braid_word needs either rng or seed.")
        rng = VariantRng(seed).stream("braid/word")
    word: list[int] = []
    while len(word) < int(length):
        letter = int(rng.integers(1, int(n_strands)))  # generator 1..n-1
        if rng.random() < 0.5:
            letter = -letter
        if word and letter == -word[-1]:
            continue
        word.append(letter)
    return tuple(word)


def crossing_window(n_crossings: int, layout: BraidLayout) -> float:
    """x length of one lane-swap window, scaled so windows never collide.

    The braid region is split into ``n_crossings`` equal slots; the swap consumes
    ``crossing_fill`` of its slot and runs straight through the rest.
    """

    span = (float(layout.braid_span[1]) - float(layout.braid_span[0])) * (
        float(layout.x_end) - float(layout.x_start)
    )
    pitch = span / max(1, int(n_crossings))
    return float(layout.crossing_fill) * pitch


def crossing_position_frac(index: int, n_crossings: int, layout: BraidLayout) -> float:
    """Main-axis fraction of crossing ``index``: evenly spaced slots, or the
    layout's ``crossing_frac`` for a one-crossing braid."""

    span_lo, span_hi = (float(layout.braid_span[0]), float(layout.braid_span[1]))
    if layout.crossing_frac is not None:
        if int(n_crossings) != 1:
            raise ValueError(
                f"BraidLayout.crossing_frac is only defined for one crossing, "
                f"got {n_crossings}."
            )
        frac = float(layout.crossing_frac)
        if not span_lo < frac < span_hi:
            raise ValueError(
                f"crossing_frac {frac:.3f} must lie strictly inside braid_span "
                f"[{span_lo:.2f}, {span_hi:.2f}]."
            )
        return frac
    return span_lo + (span_hi - span_lo) * ((int(index) + 0.5) / int(n_crossings))


def crossing_window_at(frac: float, n_crossings: int, layout: BraidLayout) -> float:
    """x length of the lane-swap window centred at ``frac``.

    The evenly spaced default (``crossing_window``) already fits its slot. A
    crossing moved off centre by ``crossing_frac`` keeps the same width where it
    fits and is clipped where it would run past either end of ``braid_span`` --
    the anchored lead-in and the straight free tail (where the plug sits) must
    survive. Clipping narrows the window, so ``verify_braid_spec``'s steepness
    rule is what bounds how far the crossing may be pushed.
    """

    total_x = float(layout.x_end) - float(layout.x_start)
    span_lo, span_hi = (float(layout.braid_span[0]), float(layout.braid_span[1]))
    full = crossing_window(n_crossings, layout)
    return float(
        min(
            full,
            2.0 * (float(frac) - span_lo) * total_x,
            2.0 * (span_hi - float(frac)) * total_x,
        )
    )


def channel_y_positions(n_strands: int, layout: BraidLayout) -> list[float]:
    """Lane centers, channel 0 at -y, centered on ``layout.center_y``."""

    offset = 0.5 * (int(n_strands) - 1)
    return [
        float(layout.center_y + (channel - offset) * layout.channel_spacing)
        for channel in range(int(n_strands))
    ]


def braid_to_control_points(
    word,
    *,
    n_strands: int,
    layout: BraidLayout,
) -> tuple[dict[int, np.ndarray], tuple[BraidCrossing, ...]]:
    """Turn a braid word into one control polyline per strand, plus the crossings.

    Each strand runs straight down its lane until a crossing involves it, then
    swaps lanes over a window of ``layout.crossing_width``. The over-strand gets a
    z bump of ``layout.over_lift`` at the midpoint; the under-strand stays on the
    table. Feeding these points through ``catmull_rom_centerline`` rounds the lane
    swap into a smooth S, so no extra smoothing logic is needed here.
    """

    word = tuple(int(letter) for letter in word)
    channel_y = channel_y_positions(n_strands, layout)
    total_x = float(layout.x_end) - float(layout.x_start)

    # perm[channel] = which strand currently occupies that lane.
    perm = list(range(int(n_strands)))
    points: dict[int, list[np.ndarray]] = {
        strand: [np.array([layout.x_start, channel_y[strand], layout.base_z], dtype=float)]
        for strand in range(int(n_strands))
    }
    crossings: list[BraidCrossing] = []

    for index, letter in enumerate(word):
        generator = abs(letter)
        if not 1 <= generator <= int(n_strands) - 1:
            raise ValueError(
                f"Braid letter {letter} is out of range for n_strands={n_strands}."
            )
        low = generator - 1  # channels low and low+1 swap
        frac = crossing_position_frac(index, len(word), layout)
        half_window = 0.5 * crossing_window_at(frac, len(word), layout)
        x_center = float(layout.x_start) + frac * total_x

        low_strand = perm[low]
        high_strand = perm[low + 1]
        over, under = (
            (low_strand, high_strand) if letter > 0 else (high_strand, low_strand)
        )
        y_low, y_high = channel_y[low], channel_y[low + 1]
        y_mid = 0.5 * (y_low + y_high)

        for strand, y_from, y_to in (
            (low_strand, y_low, y_high),
            (high_strand, y_high, y_low),
        ):
            z_mid = float(layout.base_z) + (
                float(layout.over_lift) if strand == over else 0.0
            )
            points[strand].append(
                np.array([x_center - half_window, y_from, layout.base_z], dtype=float)
            )
            points[strand].append(np.array([x_center, y_mid, z_mid], dtype=float))
            points[strand].append(
                np.array([x_center + half_window, y_to, layout.base_z], dtype=float)
            )

        perm[low], perm[low + 1] = perm[low + 1], perm[low]
        crossings.append(
            BraidCrossing(
                index=index,
                over_strand=int(over),
                under_strand=int(under),
                position_frac=float(frac),
                sign=1 if letter > 0 else -1,
            )
        )

    for channel, strand in enumerate(perm):
        points[strand].append(
            np.array([layout.x_end, channel_y[channel], layout.base_z], dtype=float)
        )

    control_points = {
        strand: np.stack(values, axis=0) for strand, values in points.items()
    }
    return control_points, tuple(crossings)


def build_braid_spec(
    *,
    n_strands: int,
    length: int,
    seed: int | None = None,
    layout: BraidLayout,
    rng: np.random.Generator | None = None,
    word=None,
) -> BraidSpec:
    """Sample a braid and lay it out. Deterministic in ``seed`` (or ``rng``).

    ``word`` skips the sampling: the caller already holds the letters (a task
    whose crossing sign is a declared variation axis rather than a seed draw).
    It must be freely reduced and ``length`` letters long.
    """

    if word is None:
        word = sample_braid_word(n_strands=n_strands, length=length, seed=seed, rng=rng)
    else:
        word = tuple(int(letter) for letter in word)
        if len(word) != int(length) or reduce_braid_word(word) != word:
            raise ValueError(
                f"build_braid_spec: word {word} is not a freely reduced word of "
                f"length {length}."
            )
    control_points, crossings = braid_to_control_points(
        word,
        n_strands=n_strands,
        layout=layout,
    )
    return BraidSpec(
        n_strands=int(n_strands),
        word=word,
        layout=layout,
        control_points=control_points,
        crossings=crossings,
    )


def verify_braid_spec(
    spec: BraidSpec,
    *,
    rope_radius: float,
    particle_size: float,
    x_bounds: tuple[float, float],
    y_bounds: tuple[float, float],
) -> BraidVerification:
    """Self-check a generated braid before it is ever handed to the simulator.

    This repo has no pytest suite; verification is "run it and look". So the
    invariants that a unit test would assert live here instead, and the inspect
    demo prints the result for every seed it builds. Checks:

    1. the word is freely reduced (crossing count is honest);
    2. one crossing per letter, and each crossing's over/under are distinct;
    3. word followed by its inverse cancels completely (the oracle really solves);
    4. crossing windows do not overlap in x, and are not so narrow that the lane
       swap becomes a near-vertical y jump (a corner that steep makes the swept
       tube self-intersect, which is exactly what PBD blows up on);
    5. ``over_lift >= 2 * rope_radius + particle_size`` -- the exact condition for
       the two ropes not to interact at spawn. Surface particles sit one radius
       out from each centreline, and PBD collision only engages below
       ``particle_size`` between particle centres, so that sum is the threshold,
       not an approximation of one. It is also, not coincidentally, the separation
       collision settles them to, which makes it the value that spawns the ropes
       already at rest. Raising it further only adds visible daylight between the
       ropes for no physical benefit -- an earlier ``2 * particle_size`` version of
       this rule forced 8 mm of air between two 8 mm ropes;
    6. every control point stays inside the declared workspace box.

    NOTE: this only sees control points. The *splined* centerline can undershoot
    below them, which is checked where the spline exists --
    ``UntangleContinuousLayout.rope_mesh`` asserts tabletop clearance.
    """

    failures: list[str] = []

    if reduce_braid_word(spec.word) != spec.word:
        failures.append(f"word_not_reduced:{spec.word}")

    if len(spec.crossings) != len(spec.word):
        failures.append(
            f"crossing_count_mismatch:{len(spec.crossings)}!={len(spec.word)}"
        )
    for crossing in spec.crossings:
        if crossing.over_strand == crossing.under_strand:
            failures.append(f"self_crossing_at:{crossing.index}")

    if reduce_braid_word(spec.word + spec.inverse_word):
        failures.append("inverse_does_not_cancel")

    if not 0.0 < float(spec.layout.crossing_fill) <= 1.0:
        failures.append(f"crossing_fill_out_of_range:{float(spec.layout.crossing_fill)}")
    for crossing in spec.crossings:
        # Per crossing: an off-centre crossing (``crossing_frac``) has its window
        # clipped to ``braid_span``, so it is the clipped width that must stay flat.
        window = crossing_window_at(crossing.position_frac, len(spec.crossings), spec.layout)
        if window < _MIN_WINDOW_PER_LANE * float(spec.layout.channel_spacing):
            failures.append(
                f"crossing_window_too_steep:crossing={crossing.index}:window={window:.4f}"
                f"<{_MIN_WINDOW_PER_LANE:.2f}*spacing={float(spec.layout.channel_spacing):.4f}"
            )

    min_lift = 2.0 * float(rope_radius) + float(particle_size)
    if float(spec.layout.over_lift) < min_lift:
        failures.append(
            f"over_lift_too_small:{float(spec.layout.over_lift):.4f}<{min_lift:.4f}"
        )

    for strand, points in spec.control_points.items():
        if not (x_bounds[0] <= points[:, 0].min() and points[:, 0].max() <= x_bounds[1]):
            failures.append(f"strand_{strand}_x_out_of_bounds")
        if not (y_bounds[0] <= points[:, 1].min() and points[:, 1].max() <= y_bounds[1]):
            failures.append(f"strand_{strand}_y_out_of_bounds")

    return BraidVerification(
        ok=not failures,
        failures=tuple(failures),
        crossing_count=len(spec.crossings),
    )
