"""Which strand to pull next, read from the current rope centre line.

Node deletion after HULK (Grannen et al., CoRL 2020, arXiv 2011.04999): from a
free end, the first crossing where that strand passes UNDER is removed by
pulling the strand just past it while another grasp pins the rope. Unlike
HULK's pin on the over strand next to the crossing, the pin here holds the
other end (the v9 demo's remote anchor): a pin next to the crossing leaves only
~0.3 m of rope between the hands and stretches it instead of drawing the tail.
When only local curls remain (R-I loops), the Reidemeister move of HULK and
SGTM 2.0 (arXiv 2207.07813) pulls both ends apart instead.
"""
import numpy as np


def passes(crossings, stations):
    """[(s, under, s_other)] for both strands of every crossing, sorted by s."""
    out = []
    for h in crossings:
        (i, j), (a, b) = h["segments"], h["parameters"]
        si = float(stations[i]+a*(stations[i+1]-stations[i]))
        sj = float(stations[j]+b*(stations[j+1]-stations[j]))
        out += [(si, not h["first_over"], sj), (sj, bool(h["first_over"]), si)]
    return sorted(out)


def only_local_loops(crossings, stations):
    """True when no crossing has another crossing's pass between its own two passes (R-I curls only)."""
    spans = []
    for h in crossings:
        (i, j), (a, b) = h["segments"], h["parameters"]
        spans.append(sorted((stations[i]+a*(stations[i+1]-stations[i]), stations[j]+b*(stations[j+1]-stations[j]))))
    return all(not any(lo < x < hi for m, other in enumerate(spans) if m != k for x in other)
               for k, (lo, hi) in enumerate(spans))


def choose(line, stations, crossings, length, hold="far", pull_direction="tangent"):
    """Pick the end with the shorter tail to its first under-crossing.

    Returns dict(end, s_under, s_pull, s_anchor, direction) with the pull band
    35 mm past the under-crossing toward the body, the anchor 15 mm from the other
    end (hold="far") or on the over strand 20 mm from the crossing (hold="over"),
    and the horizontal pull direction along the rope away from the crossing
    ("tangent") or pull point minus anchor ("away", HULK's p_pull - p_pin).
    """
    best = None
    ps = passes(crossings, stations)
    for end in ("A", "B"):
        walk = ps if end == "A" else ps[::-1]
        first, over = next(((s, o) for s, under, o in walk if under), (None, None))
        if first is None:
            continue
        tail = first if end == "A" else length-first
        if best is None or tail < best[0]:
            pull = first+.035 if end == "A" else first-.035
            anchor = length-.015 if end == "A" else .015
            best = (tail, end, first, pull, anchor, over)
    if best is None:
        return None
    _, end, under, pull, anchor, over = best
    at = lambda s: np.array([np.interp(s, stations, line[:, k]) for k in range(2)])
    if hold == "over":
        anchor = max((over-.02, over+.02), key=lambda s: np.linalg.norm(at(s)-at(pull)))
    direction = at(pull)-at(under) if pull_direction == "tangent" else at(pull)-at(anchor)
    return dict(end=end, s_under=under, s_pull=pull, s_anchor=float(anchor),
                direction=(direction/np.linalg.norm(direction)).tolist())
