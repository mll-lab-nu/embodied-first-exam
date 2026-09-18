"""Top-down crossings between ropes, numbered along each rope (swap_crossing_sign).

One reading serves the verifier and the offline sequence planner, so the
planner predicts exactly what the judge will read.

The measurement is the one `untangle_continuous_verifier.count_crossings` makes
-- every pair of centerline segments from two different ropes that cross in the
xy projection, the one with the larger z on top, hits of the same pair within
``merge_radius`` merged into one -- plus the two numbers that verifier throws
away: where along each rope the crossing sits.

Those two numbers are what the task needs. `swap_crossing_sign_verifier.
signed_crossings` sorts (lower rope, higher rope, sign) tuples, and for two ropes
that cross twice the only freely reduced words, (+1, +1) and (-1, -1), give the
same sorted tuple ((0, 1, -1), (0, 1, +1)): "both crossings flipped" and "nothing
flipped" read the same. The crossing code below keeps, for each crossing, its
rank along each of its two ropes counted from the power strip, so the two
crossings of one pair stay distinguishable and the whole diagram is compared,
not a multiset of signs.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

#: (lower rope, its rank, higher rope, its rank, rope on top), one per crossing,
#: sorted. Rank = 0-based position of the crossing among ALL crossings on that
#: rope, ordered by arclength from the anchored end.
CrossingCode = tuple[tuple[int, int, int, int, int], ...]


@dataclass(frozen=True)
class RopeCrossing:
    """One measured crossing, located along both ropes."""

    a: int  # lower rope id
    b: int  # higher rope id
    s_a: float  # arclength along rope a from its anchored end, meters
    s_b: float
    over: int  # rope id on top (a or b)
    position: tuple[float, float]  # xy of the crossing
    z_gap: float  # over centerline z minus under centerline z

    # The names `untangle_continuous_verifier.GeoCrossing` uses, so the shared
    # log printers (`supervision.untangle_continuous.crossing_lines`) read both.
    @property
    def over_strand(self) -> int:
        return self.over

    @property
    def under_strand(self) -> int:
        return self.b if self.over == self.a else self.a


def arclength(polyline: np.ndarray) -> np.ndarray:
    """Cumulative xy arclength of a polyline, 0 at its first vertex."""

    steps = np.linalg.norm(np.diff(np.asarray(polyline, dtype=float)[:, :2], axis=0), axis=1)
    return np.concatenate([[0.0], np.cumsum(steps)])


def segment_hits(p0: np.ndarray, p1: np.ndarray, q: np.ndarray):
    """Proper xy intersections of segments p0[k]->p1[k] with polyline q.

    Returns (k, j, t, u) arrays: candidate k meets q's segment j at parameter t
    along p and u along q. Vectorized over both, so the planner can test a fan of
    candidate tails against a rope in one call.
    """

    p0 = np.atleast_2d(np.asarray(p0, dtype=float))[:, None, :2]
    p1 = np.atleast_2d(np.asarray(p1, dtype=float))[:, None, :2]
    q0 = np.asarray(q, dtype=float)[None, :-1, :2]
    q1 = np.asarray(q, dtype=float)[None, 1:, :2]
    r = p1 - p0
    s = q1 - q0
    den = r[..., 0] * s[..., 1] - r[..., 1] * s[..., 0]
    d = q0 - p0
    with np.errstate(divide="ignore", invalid="ignore"):
        t = (d[..., 0] * s[..., 1] - d[..., 1] * s[..., 0]) / den
        u = (d[..., 0] * r[..., 1] - d[..., 1] * r[..., 0]) / den
    hit = (np.abs(den) > 1e-12) & (t >= 0.0) & (t <= 1.0) & (u >= 0.0) & (u <= 1.0)
    k, j = np.nonzero(hit)
    return k, j, t[k, j], u[k, j]


def _merge(hits: list[RopeCrossing], merge_radius: float) -> list[RopeCrossing]:
    """Same rule as `untangle_continuous_verifier._merge_nearby`, per rope pair."""

    kept: list[RopeCrossing] = []
    for hit in hits:
        for index, other in enumerate(kept):
            gap = float(np.hypot(hit.position[0] - other.position[0], hit.position[1] - other.position[1]))
            if gap <= merge_radius:
                if hit.z_gap > other.z_gap:
                    kept[index] = hit
                break
        else:
            kept.append(hit)
    return kept


def find_crossings(
    polylines: dict[int, np.ndarray],
    *,
    merge_radius: float,
    arcs: dict[int, np.ndarray] | None = None,
) -> tuple[RopeCrossing, ...]:
    """Every crossing between two different ropes, located along both.

    ``arcs`` gives each vertex's arclength coordinate when it is not the
    polyline's own xy length -- the offline planner lays a tail as a straight
    chord, and the rope along that chord is still its full length.
    """

    ropes = sorted(polylines)
    arcs = arcs or {}
    found: list[RopeCrossing] = []
    for i, a in enumerate(ropes):
        pa = np.asarray(polylines[a], dtype=float)
        sa_axis = np.asarray(arcs[a], dtype=float) if a in arcs else arclength(pa)
        for b in ropes[i + 1:]:
            pb = np.asarray(polylines[b], dtype=float)
            sb_axis = np.asarray(arcs[b], dtype=float) if b in arcs else arclength(pb)
            ks, js, ts, us = segment_hits(pa[:-1], pa[1:], pb)
            raw = []
            for k, j, t, u in zip(ks, js, ts, us):
                point = pa[k, :2] + t * (pa[k + 1, :2] - pa[k, :2])
                za = pa[k, 2] + t * (pa[k + 1, 2] - pa[k, 2])
                zb = pb[j, 2] + u * (pb[j + 1, 2] - pb[j, 2])
                raw.append(
                    RopeCrossing(
                        a=int(a),
                        b=int(b),
                        s_a=float(sa_axis[k] + t * (sa_axis[k + 1] - sa_axis[k])),
                        s_b=float(sb_axis[j] + u * (sb_axis[j + 1] - sb_axis[j])),
                        over=int(a) if za > zb else int(b),
                        position=(float(point[0]), float(point[1])),
                        z_gap=abs(float(za - zb)),
                    )
                )
            found.extend(_merge(raw, merge_radius))
    return tuple(found)


def crossing_code(crossings) -> CrossingCode:
    """The diagram as a sorted tuple of (a, rank_a, b, rank_b, over)."""

    along: dict[int, list[tuple[float, int]]] = {}
    for index, c in enumerate(crossings):
        along.setdefault(c.a, []).append((c.s_a, index))
        along.setdefault(c.b, []).append((c.s_b, index))
    rank: dict[tuple[int, int], int] = {}
    for rope, entries in along.items():
        for position, (_s, index) in enumerate(sorted(entries)):
            rank[(rope, index)] = position
    return tuple(
        sorted((c.a, rank[(c.a, i)], c.b, rank[(c.b, i)], c.over) for i, c in enumerate(crossings))
    )


def flip_code(code: CrossingCode) -> CrossingCode:
    """The same diagram with every crossing's top rope swapped."""

    return tuple(sorted((a, ra, b, rb, b if over == a else a) for a, ra, b, rb, over in code))


def pair_tops(code: CrossingCode) -> dict[tuple[int, int], tuple[int, ...]]:
    """Per rope pair, which rope is on top at each of their crossings, in order along the pair."""

    tops: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for a, ra, b, rb, over in code:
        tops.setdefault((a, b), []).append((ra + rb, over))
    return {pair: tuple(over for _rank, over in sorted(entries)) for pair, entries in tops.items()}


def relation_flipped(final: CrossingCode, spawn: CrossingCode) -> bool:
    """Does every pair of ropes that crossed at spawn now cross the same number of times,
    with the other rope on top?

    The order of the crossings along the ropes is NOT required to match (decision
    2026-09-12): what the task asks for is that where A lay over B, B now lies over
    A. Positions are free too -- the ropes need not return to where they started.

    A pair that crosses TWICE cannot be judged this way: "A over then B over" and its
    flip are the same multiset, so such a pair falls back to comparing the ranked
    code, the form that tells them apart.
    """

    got, want = pair_tops(final), pair_tops(spawn)
    if set(got) != set(want):
        return False
    if any(len(entries) > 1 for entries in want.values()):
        return final == flip_code(spawn)
    return all(
        len(got[pair]) == len(want[pair]) and all(g != w for g, w in zip(got[pair], want[pair]))
        for pair in want
    )


def failure_label(final: CrossingCode, spawn: CrossingCode) -> str | None:
    """None when every pair that crossed at spawn now crosses with the other rope on top."""

    if relation_flipped(final, spawn):
        return None
    if len(final) > len(spawn):
        return "extra_crossing"
    if len(final) < len(spawn):
        return "missing_crossing"
    got, want = pair_tops(final), pair_tops(spawn)
    if set(got) != set(want):
        return "reordered"  # crosses as often as it should, but not the same rope pairs
    flipped = sum(
        sum(g != w for g, w in zip(got[pair], want[pair]))
        for pair in want
        if len(got[pair]) == len(want[pair])
    )
    return "unchanged" if flipped == 0 else "partial_flip"


def code_text(code: CrossingCode) -> str:
    """`s0#1/s1#1 s0-over` style, compact enough for one log line."""

    if not code:
        return "none"
    return "; ".join(f"s{a}#{ra + 1}/s{b}#{rb + 1} s{over} over" for a, ra, b, rb, over in code)


__all__ = [
    "CrossingCode",
    "RopeCrossing",
    "arclength",
    "code_text",
    "crossing_code",
    "failure_label",
    "find_crossings",
    "flip_code",
    "pair_tops",
    "relation_flipped",
    "segment_hits",
]
