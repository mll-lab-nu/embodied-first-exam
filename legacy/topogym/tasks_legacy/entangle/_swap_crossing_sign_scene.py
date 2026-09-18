"""swap_crossing_sign spawn geometry from scalar leaves (Genesis-free).

Scene: 2 or 3 ropes leave a power strip at x_start in parallel lanes (lane 0 at
-y), each first runs an S-shaped bend (the lead-in), then swaps lanes with its
neighbour 1 or 2 times at chosen positions, then a straight tail carries it to
its plug at x_end. Everything here is a pure function of numbers, so the
variation hooks, the offline gates and the offline sequence planner all build
the same ropes the scene builder will.

The lane swaps are `generation/braid.py`'s `braid_to_control_points` itself
(lane swap = three control points per involved rope, the over rope lifted by
``over_lift`` at the middle one), with two additions:

- crossing positions and window widths are given per crossing
  (``BraidLayout.crossing_fracs`` / ``crossing_windows``) instead of the even
  slots (one crossing: ``BraidLayout.crossing_frac``);
- the lead-in carries a lateral S bend. It is the only place extra rope length
  can go without lengthening any crossing-to-plug arc -- and that arc is what sets
  every lift (hand height = arc hanging below the hand + clearance), while the
  total length is what sets reach. So the bend buys reach at zero lift cost.
"""

from __future__ import annotations

import math

import numpy as np

from topogym.generation.braid import BraidLayout, BraidSpec, braid_to_control_points

#: Smallest swap window as a fraction of the lane pitch (braid.py's
#: `_MIN_WINDOW_PER_LANE`: a steeper lane change reads as a kink, ~59 degrees).
MIN_WINDOW_PER_LANE = 0.6
#: Fraction of the gap between two crossing centres a window may use.
WINDOW_FILL = 0.95
#: Straight run kept at the anchored end (inside the strip outlet) before the bend.
ANCHOR_RUN = 0.03
#: Straight run kept between the bend and the first swap window.
BEND_MARGIN = 0.01
#: Control-point pitch along the bend, so the spline follows it.
BEND_STEP = 0.01
#: Peak of 2 sin^2(pi u) cos(pi u) on [0, 1]; divides it out so ``bow`` is the peak offset.
_S_PEAK = 2.0 * (2.0 / 3.0) / math.sqrt(3.0)


#: Every braid word the task spawns, per (ropes, crossings). Letter k: which
#: adjacent lanes swap (1 = lanes 0-1, 2 = lanes 1-2), sign = whether the rope
#: coming from the lower lane goes over. Two ropes crossing twice can only be
#: (s, s) (a freely reduced word repeats its sign). Three ropes crossing twice use
#: two different pairs (decision 2026-09-10: all three take part); the two words
#: whose shared rope is under at the strip-side crossing and over at the
#: plug-side one, (+2, -1) and (-1, +2), are left out -- the offline study found
#: 1/72 of their layouts flippable (decision gate A, 2026-09-11).
WORDS: dict[tuple[int, int], tuple[tuple[int, ...], ...]] = {
    (2, 1): ((1,), (-1,)),
    (2, 2): ((1, 1), (-1, -1)),
    (3, 1): ((1,), (-1,), (2,), (-2,)),
    (3, 2): ((1, 2), (-2, -1), (2, 1), (-1, -2), (1, -2), (-2, 1)),
}
#: ``braid.word_index`` takes 0..11: 12 is a multiple of every cell's word count,
#: so each word of a cell is equally likely and a corner sweep over the choice
#: visits them all.
WORD_INDEX_COUNT = 12


def braid_word(n_strands: int, length: int, word_index: int) -> tuple[int, ...]:
    words = WORDS[(int(n_strands), int(length))]
    return words[int(word_index) % len(words)]


def lane_y(n_strands: int, center_y: float, spacing: float) -> list[float]:
    offset = 0.5 * (int(n_strands) - 1)
    return [float(center_y) + (lane - offset) * float(spacing) for lane in range(int(n_strands))]


def swap_windows(fracs, *, x_start: float, x_end: float, span: tuple[float, float]) -> list[float]:
    """Window width per crossing: as wide as the neighbours and the span allow."""

    total = float(x_end) - float(x_start)
    centres = [float(x_start) + float(f) * total for f in fracs]
    lo, hi = float(x_start) + span[0] * total, float(x_start) + span[1] * total
    windows = []
    for k, x in enumerate(centres):
        room_left = 2.0 * (x - lo) if k == 0 else WINDOW_FILL * (x - centres[k - 1])
        room_right = 2.0 * (hi - x) if k == len(centres) - 1 else WINDOW_FILL * (centres[k + 1] - x)
        cap = WINDOW_FILL * span_width(span, total) if len(centres) == 1 else float("inf")
        windows.append(float(min(room_left, room_right, cap)))
    return windows


def span_width(span, total: float) -> float:
    return (float(span[1]) - float(span[0])) * float(total)


def s_bend(u: np.ndarray) -> np.ndarray:
    """Lateral S bend on u in [0, 1]: zero value and zero slope at both ends, peak 1."""

    return 2.0 * np.sin(np.pi * u) ** 2 * np.cos(np.pi * u) / _S_PEAK


def braid_layout(*, n_strands: int, x_start: float, x_end: float, center_y: float, spacing: float,
                 fracs, windows, base_z: float, over_lift: float, span=(0.10, 0.85), fill: float = WINDOW_FILL) -> BraidLayout:
    """The generator's layout with every crossing's position and window given."""

    return BraidLayout(
        x_start=float(x_start), x_end=float(x_end), center_y=float(center_y), channel_spacing=float(spacing),
        base_z=float(base_z), over_lift=float(over_lift), braid_span=(float(span[0]), float(span[1])),
        crossing_fill=float(fill),
        crossing_fracs=tuple(float(f) for f in fracs), crossing_windows=tuple(float(w) for w in windows),
    )


def add_lead_in_bends(points: dict[int, np.ndarray], crossings, layout: BraidLayout, bows) -> dict[int, np.ndarray]:
    """Insert each rope's S bend between its anchored run and its first swap window.

    ``crossings`` are the generator's (word order = x order). A rope that takes
    part in no crossing bends over its whole run short of the straight tail.
    """

    total = float(layout.x_end) - float(layout.x_start)
    out = {}
    for strand, poly in points.items():
        bow = 0.0 if bows is None else float(bows[strand])
        edges = [
            float(layout.x_start) + c.position_frac * total - 0.5 * float(layout.crossing_windows[c.index])
            for c in crossings
            if strand in (c.over_strand, c.under_strand)
        ]
        bend_start = float(layout.x_start) + ANCHOR_RUN
        bend_end = (min(edges) if edges else float(layout.x_end) - 0.08) - BEND_MARGIN
        if bow == 0.0 or bend_end - bend_start <= 4 * BEND_STEP:
            out[strand] = poly
            continue
        n = max(4, int(math.ceil((bend_end - bend_start) / BEND_STEP)))
        u = np.linspace(0.0, 1.0, n + 1)
        y0, z0 = float(poly[0, 1]), float(poly[0, 2])
        bend = np.column_stack([bend_start + u * (bend_end - bend_start), y0 + bow * s_bend(u), np.full(len(u), z0)])
        out[strand] = np.vstack([poly[:1], bend, poly[1:]])
    return out


def control_points(
    word,
    *,
    n_strands: int,
    x_start: float,
    x_end: float,
    center_y: float,
    spacing: float,
    fracs,
    windows,
    base_z: float,
    over_lift: float,
    bows=None,
) -> tuple[dict[int, np.ndarray], list[tuple[int, int, int, float]]]:
    """Control polyline per rope, plus (index, over, under, frac) per crossing.

    The lane swaps are `braid_to_control_points` itself (one source for that
    geometry); only the lead-in bend is added here.
    """

    word = tuple(int(letter) for letter in word)
    if len(fracs) != len(word) or len(windows) != len(word):
        raise ValueError("one position and one window per letter")
    layout = braid_layout(n_strands=n_strands, x_start=x_start, x_end=x_end, center_y=center_y, spacing=spacing,
                          fracs=fracs, windows=windows, base_z=base_z, over_lift=over_lift)
    points, crossings = braid_to_control_points(word, n_strands=int(n_strands), layout=layout)
    points = add_lead_in_bends(points, crossings, layout, bows)
    return points, [(c.index, c.over_strand, c.under_strand, c.position_frac) for c in crossings]


# ----------------------------------------------------------------- envelope
# Numbers below come from the offline feasibility study (plan stage A,
# `tests/study_swap_crossing_sign_feasibility.py`, runs/swap_crossing_sign_probe/).

#: One crossing: where along x_start..x_end it may sit (today's envelope).
ONE_CROSSING_FRACS = (0.30, 0.75)
#: Two crossings: the strip-side one no nearer the strip than this (the lift to
#: undo it is the arc from it to the plug, and the ceiling is 40 cm).
TWO_CROSSING_LO = 0.45
#: Narrowest sampled swap window, as a multiple of the lane pitch (braid.py's
#: hard floor is 0.6, ~59 degrees; sampling stops short of it).
WINDOW_MIN_PER_LANE = 0.75
#: Lane-to-lane clearance the lead-in bends keep: two rope diameters plus the
#: 1.6 cm separation threshold.
BOW_CLEARANCE = 0.032
#: Largest shift of the whole set of ropes off the table centre line.
CENTER_MAX = 0.03
#: Two crossings at least this far apart in x (the ``crossing_gap`` row asks 5 cm).
CROSSING_GAP_MIN = 0.055


def two_crossing_bounds(spacing: float, total: float, span=(0.10, 0.85)) -> tuple[float, float, float]:
    """(lo, hi, min_gap) of the two crossing fractions for this lane pitch."""

    min_window = MIN_WINDOW_PER_LANE * float(spacing)
    # Far enough apart that the windows between them stay flat enough, and that
    # two ropes crossing twice (both crossings on the same centre line) put them
    # past the crossing_gap row's 5 cm.
    gap = max(min_window / WINDOW_FILL, CROSSING_GAP_MIN) / float(total)
    hi = float(span[1]) - 0.5 * min_window / float(total)  # the plug-side window fits inside the span
    return TWO_CROSSING_LO, hi, gap


def crossing_fracs(length: int, u: float, gap_u: float, *, spacing: float, total: float) -> tuple[float, ...]:
    """Crossing positions from the two unit leaves (the variation hook's derivation)."""

    if int(length) == 1:
        lo, hi = ONE_CROSSING_FRACS
        return (lo + float(u) * (hi - lo),)
    lo, hi, gap = two_crossing_bounds(spacing, total)
    f1 = lo + float(u) * max(hi - gap - lo, 0.0)
    f2 = f1 + gap + float(gap_u) * max(hi - f1 - gap, 0.0)
    return (f1, f2)


def sampled_windows(fracs, window_u: float, *, spacing: float, x_start: float, x_end: float) -> list[float]:
    """Each window between the narrowest sampled one and the widest that fits; window_u = 1 is today's."""

    widest = swap_windows(fracs, x_start=x_start, x_end=x_end, span=(0.10, 0.85))
    narrow = WINDOW_MIN_PER_LANE * float(spacing)
    return [w if w <= narrow else narrow + float(window_u) * (w - narrow) for w in widest]


def bow_amplitudes(bow_u, *, spacing: float) -> list[float]:
    cap = max(0.5 * (float(spacing) - BOW_CLEARANCE), 0.0)
    return [float(u) * cap for u in bow_u]


def center_limit(n_strands: int, spacing: float, *, strip_half_length: float, tube_radius: float) -> float:
    """Largest |center_y| that keeps every outlet on the power strip (and within CENTER_MAX)."""

    outermost = 0.5 * (int(n_strands) - 1) * float(spacing)
    return max(min(CENTER_MAX, float(strip_half_length) - float(tube_radius) - outermost), 0.0)


def spec_from_leaves(braid) -> BraidSpec:
    """The task yaml's ``braid:`` leaves -> the ropes the builder will make.

    ``braid`` is the config node (OmegaConf) or a plain dict of the same leaves;
    the layout, the variation hooks and the offline gate all come through here.
    """

    n = int(braid["n_strands"])
    length = int(braid["length"])
    spacing = float(braid["channel_spacing"])
    word = braid_word(n, length, int(braid.get("word_index", 0)))
    fracs = (float(braid["crossing_frac"]),) if length == 1 else (float(braid["crossing_frac"]), float(braid["crossing_frac_2"]))
    windows = sampled_windows(fracs, float(braid.get("window_u", 1.0)), spacing=spacing,
                              x_start=float(braid["x_start"]), x_end=float(braid["x_end"]))
    span = braid["braid_span"]
    layout = braid_layout(
        n_strands=n, x_start=float(braid["x_start"]), x_end=float(braid["x_end"]), center_y=float(braid["center_y"]),
        spacing=spacing, fracs=fracs, windows=windows, base_z=float(braid["base_z"]), over_lift=float(braid["over_lift"]),
        span=(float(span[0]), float(span[1])), fill=float(braid["crossing_fill"]),
    )
    points, crossings = braid_to_control_points(word, n_strands=n, layout=layout)
    bows = bow_amplitudes([float(braid.get(f"bow_u_{k}", 0.0)) for k in range(n)], spacing=spacing)
    points = add_lead_in_bends(points, crossings, layout, bows)
    return BraidSpec(n_strands=n, word=word, layout=layout, control_points=points, crossings=tuple(crossings))


def derive_leaves(braid, *, strip_half_length: float) -> None:
    """The variation block's derivation: unit leaves -> crossing positions and left-right shift.

    Writes ``crossing_frac``, ``crossing_frac_2`` (kept as is for one crossing)
    and ``center_y``. Pure: draws nothing.

    It also settles one coupling between the two axes: **two crossings need three
    ropes** (decision 2026-09-12). Two ropes crossing twice put both crossings on
    the same pair, and that cell's oracle failed on GPU with no route left --
    flipping the inner crossing means lifting a tail past the outer one, which
    destroys it, so the only routes strip the table bare and rebuild two crossings
    from landings the laid-rope error takes away (offline: forbidding the bare
    state leaves 0/28 plans for two ropes). A draw of ``length`` 2 with
    ``n_strands`` 2 is therefore rewritten to one crossing rather than rejected,
    which keeps the rope-count axis uniform instead of biasing it.
    """

    if int(braid["n_strands"]) < 3:
        braid["length"] = 1
    total = float(braid["x_end"]) - float(braid["x_start"])
    fracs = crossing_fracs(int(braid["length"]), float(braid["crossing_u"]), float(braid["crossing_gap_u"]),
                           spacing=float(braid["channel_spacing"]), total=total)
    braid["crossing_frac"] = float(fracs[0])
    if len(fracs) > 1:
        braid["crossing_frac_2"] = float(fracs[1])
    limit = center_limit(int(braid["n_strands"]), float(braid["channel_spacing"]),
                         strip_half_length=strip_half_length, tube_radius=float(braid["tube_radius"]))
    braid["center_y"] = float((2.0 * float(braid["center_y_u"]) - 1.0) * limit)


def expected_code(crossings):
    """The crossing code the generator promises (word order = x order along every rope)."""

    along: dict[int, int] = {}
    entries = []
    for c in sorted(crossings, key=lambda c: c.index):
        a, b = sorted((int(c.over_strand), int(c.under_strand)))
        ra, rb = along.get(a, 0), along.get(b, 0)
        along[a], along[b] = ra + 1, rb + 1
        entries.append((a, ra, b, rb, int(c.over_strand)))
    return tuple(sorted(entries))


def scene_checks(
    points: dict[int, np.ndarray],
    crossings,
    layout: BraidLayout,
    *,
    tube_radius: float,
    min_plug_gap: float,
    plug_ahead: float,
    flange_radius: float,
    strip_half_length: float,
    workspace_x: tuple[float, float],
    workspace_y: tuple[float, float],
    workspace_margin: float,
    spawn_clearance: float = 0.030,
    crossing_gap: float = 0.05,
    merge_radius: float = 0.012,
) -> list[tuple[str, float, float, bool]]:
    """``[(name, measured, limit, ok)]`` for a swap layout, before anything is built.

    - ``spawn_code``       crossings read off the control polylines (the same
                           reader the verifier uses) differ from the generator's
                           promise in this many entries -- a bend that lets two
                           ropes touch where they should not shows up here.
    - ``spawn_clearance``  closest approach of two ropes, leaving out the swap
                           windows in which that pair crosses.
    - ``crossing_gap``     distance between the two crossing points: they must
                           not coincide (decision 3), and the judge merges hits of
                           one rope pair within 1.2 cm into one.
    - ``crossing_window``  narrowest swap window, braid.py's steepness rule.
    - ``window_overlap``   room between consecutive windows.
    - ``free_tail``        straight run from the last window to the plug, per rope.
    - ``plug_gap``         closest pair of plugs (gripper span rule).
    - ``footprint_x`` / ``footprint_y`` / ``strip_cover``  as in the frozen rows.
    """

    from topogym.planning.rope_crossings import crossing_code, find_crossings

    total = float(layout.x_end) - float(layout.x_start)
    dense = {k: densify(v, 0.005) for k, v in points.items()}
    found = find_crossings(dense, merge_radius=merge_radius)
    got, want = crossing_code(found), expected_code(crossings)
    code_miss = float(len(set(got) ^ set(want)))

    # Two ropes that cross converge across their whole swap window by design
    # (over 30 cm for today's single crossing), so for that pair the window's x
    # range is left out; everywhere else they must keep their distance.
    ropes = sorted(dense)
    clearance = float("inf")
    for i, a in enumerate(ropes):
        for b in ropes[i + 1:]:
            spans = [
                (float(layout.x_start) + c.position_frac * total - 0.5 * float(layout.crossing_windows[c.index]),
                 float(layout.x_start) + c.position_frac * total + 0.5 * float(layout.crossing_windows[c.index]))
                for c in crossings
                if {int(c.over_strand), int(c.under_strand)} == {a, b}
            ]

            def outside(poly):
                x = poly[:, 0]
                mask = np.ones(len(poly), dtype=bool)
                for lo, hi in spans:
                    mask &= (x < lo) | (x > hi)
                return poly[mask, :2]

            pa, pb = outside(dense[a]), outside(dense[b])
            if len(pa) and len(pb):
                clearance = min(clearance, float(np.linalg.norm(pa[:, None] - pb[None], axis=2).min()))

    positions = [c.position for c in found]
    gap = min((float(np.hypot(p[0] - q[0], p[1] - q[1])) for i, p in enumerate(positions) for q in positions[i + 1:]), default=float("inf"))

    windows = [float(layout.crossing_windows[c.index]) for c in crossings]
    window = min(windows, default=float("inf"))
    centres = [float(layout.x_start) + c.position_frac * total for c in crossings]
    order = sorted(range(len(centres)), key=lambda k: centres[k])
    overlap = min(
        (centres[order[k + 1]] - 0.5 * windows[order[k + 1]] - (centres[order[k]] + 0.5 * windows[order[k]]) for k in range(len(order) - 1)),
        default=float("inf"),
    )
    tail = float("inf")
    for strand in points:
        edges = [centres[k] + 0.5 * windows[k] for k, c in enumerate(crossings) if strand in (c.over_strand, c.under_strand)]
        if edges:
            tail = min(tail, float(layout.x_end) - max(edges))

    plugs = np.array([points[k][-1, :2] for k in ropes])
    plug_gap = min((float(np.linalg.norm(plugs[i] - plugs[j])) for i in range(len(plugs)) for j in range(i + 1, len(plugs))), default=float("inf"))
    footprint_x = min(float(workspace_x[1]) - (float(plugs[:, 0].max()) + float(plug_ahead)), float(layout.x_start) - float(workspace_x[0]))
    all_y = np.concatenate([p[:, 1] for p in points.values()])
    footprint_y = min(float(workspace_y[1]) - (float(all_y.max()) + float(flange_radius)), (float(all_y.min()) - float(flange_radius)) - float(workspace_y[0]))
    outlets = np.array([p[0, 1] for p in points.values()])
    strip_cover = float(strip_half_length) - float(np.abs(outlets).max())

    return [
        ("spawn_code", code_miss, 0.0, code_miss <= 0.0),
        ("spawn_clearance", clearance, float(spawn_clearance), clearance >= spawn_clearance - 1e-9),
        ("crossing_gap", gap, float(crossing_gap), gap >= crossing_gap - 1e-9),
        ("crossing_window", window, MIN_WINDOW_PER_LANE * float(layout.channel_spacing), window >= MIN_WINDOW_PER_LANE * float(layout.channel_spacing) - 1e-9),
        ("window_overlap", overlap, 0.0, overlap >= -1e-9),
        ("free_tail", tail, 0.050, tail >= 0.050 - 1e-9),
        ("plug_gap", plug_gap, float(min_plug_gap), plug_gap >= min_plug_gap - 1e-9),
        ("footprint_x", footprint_x, 0.0, footprint_x >= -1e-9),
        ("footprint_y", footprint_y, float(workspace_margin), footprint_y >= workspace_margin - 1e-9),
        ("strip_cover", strip_cover, float(tube_radius), strip_cover >= tube_radius - 1e-9),
    ]


def densify(points: np.ndarray, step: float = 0.005) -> np.ndarray:
    """Linear resampling at ~``step`` (keeps every control point)."""

    out = [np.asarray(points[0], dtype=float)]
    for a, b in zip(points[:-1], points[1:]):
        n = max(1, int(math.ceil(float(np.linalg.norm(b[:2] - a[:2])) / step)))
        for t in np.linspace(0.0, 1.0, n + 1)[1:]:
            out.append(a + (b - a) * t)
    return np.stack(out, axis=0)


__all__ = [
    "MIN_WINDOW_PER_LANE",
    "WORDS",
    "WORD_INDEX_COUNT",
    "add_lead_in_bends",
    "bow_amplitudes",
    "braid_layout",
    "braid_word",
    "center_limit",
    "control_points",
    "crossing_fracs",
    "densify",
    "derive_leaves",
    "expected_code",
    "lane_y",
    "s_bend",
    "sampled_windows",
    "scene_checks",
    "spec_from_leaves",
    "swap_windows",
    "two_crossing_bounds",
]
