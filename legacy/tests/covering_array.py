"""Covering arrays: a physics-sized substitute for a full-factorial corner sweep.

A task's `variation:` block defines a box, and the corner harness's cells are its
VERTICES -- every continuous axis at both ends, every discrete axis at every
value, full Cartesian product. That is the right set to check ANALYTICALLY: the
feasibility rows are closed-form arithmetic and a hundred thousand of them run in
under a minute. It stopped being the right set to run PHYSICS on the moment the
axis count grew: cloth_unpleat's sixteen axes make 98,304 vertices, and at a
minute a cell that is two months of GPU.

A ``t``-way covering array is the standard answer. It is a small set of rows such
that **for any ``t`` axes, every combination of their values appears in at least
one row**. The claim it buys is stronger than a hand-picked subset's -- "every
four-way combination of axis values has been run" rather than "we chose these
sixty" -- and it does not grow with the axis count the way the product does. For
cloth_unpleat's axes, measured with the greedy construction below:

===========  =====
strength     rows
===========  =====
2-way          12
3-way          31
4-way          79
===========  =====

Why ``t`` can be small: this repo's own record. Every problem the corner sweeps
have caught was triggered by one to three axes interacting -- cloth_unpleat's
world-anchored occupancy grid (one axis), cloth_fold's control-mesh diagonal
(one), bar_through_hole's hard-coded cradle y (one), rope_winding's c1052 (two),
cloth_unpleat's flat-pleat residual (three: pull_scale x crest x width). None was
four-way or higher, and the 98,225 vertices a 4-way array leaves out differ from
it only in five-way-and-higher interactions.

**Determinism is part of the contract.** The construction is randomised, so the
seed is fixed and the chosen rows are written next to the run they justify; a
sweep that picked a different set each time would not be evidence of anything.
"""

from __future__ import annotations

import itertools
import random

#: Fixed so the same axes give the same rows on every run. Changing it changes
#: which cells the physics evidence covers, so it is a decision, not a knob.
SEED = 0

#: Candidate rows drawn per greedy pick. More candidates means a slightly
#: smaller array for proportionally more time; 200 puts a 16-axis 4-way array at
#: 79 rows in about a minute.
CANDIDATES = 200


def _targets(levels: list[int], strength: int) -> set:
    out = set()
    for columns in itertools.combinations(range(len(levels)), strength):
        for values in itertools.product(*(range(levels[c]) for c in columns)):
            out.add((columns, values))
    return out


def build(levels, strength: int = 4, *, seed: int = SEED, candidates: int = CANDIDATES):
    """Rows covering every ``strength``-way combination of the given axis levels.

    ``levels`` is one entry per axis: how many values that axis takes (2 for a
    continuous axis read at its two ends). Returns a list of rows, each a tuple
    of value INDICES in the same order.

    Greedy by density: draw ``candidates`` random rows, keep whichever covers the
    most still-uncovered combinations, repeat until none are left. It does not
    give the smallest possible array -- that is a hard combinatorial problem --
    but it terminates, it is short enough to read, and being a few rows above
    optimal costs a few GPU minutes rather than correctness.
    """

    levels = [int(v) for v in levels]
    strength = int(strength)
    if strength < 1 or strength > len(levels):
        raise ValueError(f"strength must be between 1 and {len(levels)}, got {strength}.")
    if any(v < 1 for v in levels):
        raise ValueError(f"every axis needs at least one value, got {levels}.")

    rng = random.Random(int(seed))
    remaining = _targets(levels, strength)
    rows: list[tuple[int, ...]] = []
    while remaining:
        best, best_cover = None, -1
        for _ in range(int(candidates)):
            row = tuple(rng.randrange(v) for v in levels)
            cover = sum(
                1
                for columns, values in remaining
                if all(row[c] == v for c, v in zip(columns, values))
            )
            if cover > best_cover:
                best, best_cover = row, cover
        if best_cover <= 0:
            # Cannot happen with random rows over a non-empty target set, but a
            # silent infinite loop is the one failure mode worth ruling out.
            raise RuntimeError(
                f"no candidate covered any of the {len(remaining)} remaining combinations."
            )
        rows.append(best)
        remaining = {
            (columns, values)
            for columns, values in remaining
            if not all(best[c] == v for c, v in zip(columns, values))
        }
    return rows


def verify(rows, levels, strength: int) -> bool:
    """Every ``strength``-way combination really does appear in ``rows``."""

    remaining = _targets([int(v) for v in levels], int(strength))
    for row in rows:
        remaining = {
            (columns, values)
            for columns, values in remaining
            if not all(row[c] == v for c, v in zip(columns, values))
        }
        if not remaining:
            return True
    return not remaining


if __name__ == "__main__":  # a size table for whoever is budgeting GPU time
    import sys

    levels = [int(v) for v in sys.argv[1:]] or [2, 2, 3, 2] + [2] * 12
    print(f"axes {levels} -> full factorial {eval('*'.join(map(str, levels)))}")
    for strength in (2, 3, 4):
        rows = build(levels, strength)
        print(
            f"  {strength}-way: {len(rows):3d} rows"
            f"  (covers every combination: {verify(rows, levels, strength)})"
        )
