"""Spawn shapes for `band_untwist` beyond the figure-8: the "6", the twist and O|-|O.

Physical picture: one rope lies flat on the table with a plug on each end, and
crosses itself once or twice. The figure-8 stays in `_figure_eight_geometry.py`
(unchanged, so the default layout is reproduced bit for bit); this module adds
three more shapes built from the same part -- the teardrop: a circle plus the
two tangent lines from a crossing point to it. Every crossing therefore sits
where two straight segments meet, and the over strand's bump (``over_lift``
over a ``lift_ramp`` on either side) always lies on a straight run, never in a
bend.

Local frame: ``a`` along the shape's axis, ``b`` to its left. Rope order runs
from end 0 to end 1.

- ``six``: one teardrop hung on crossing X with its axis along +a; end 0's short
  tail and end 1's long stem continue the loop's two tangent lines through X
  to the -a side (end 0 on +b). One crossing.
- ``twist``: the 8 with one more closed lobe. Along +a: [open lobe carrying both
  ends] -X1- [middle lobe] -X2- [closed lobe]. The middle lobe is a circle with
  a pair of tangents to X1 and a pair to X2, so each strand changes side at X1
  and again at X2 (the band is twisted twice). Two crossings.
- ``curls`` (O|-|O): a straight middle rope from XA to XB along +a; at each end a
  teardrop loop hangs on the outer side of its crossing, and the end's short stub
  leaves the crossing at 2*phi from the middle rope, on the inner side. Stub side
  ``same``: both stubs on +b; ``opposite``: A's on +b, B's on -b. Two crossings.

Which strand is raised at each crossing is chosen per crossing
(`raise_crossings`). The flat path is the same either way, so the plugs sit in
the same place and only the crossings themselves show which strand is on top.

Pure numpy with no topogym imports, so the offline gate can load it by path.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

SHAPES = ("eight", "six", "twist", "curls")

#: Self-crossings each shape spawns with.
SHAPE_CROSSINGS = {"eight": 1, "six": 1, "twist": 2, "curls": 2}

STUB_SIDES = ("same", "opposite")


# --------------------------------------------------------------------- specs


@dataclass(frozen=True)
class SixSpec:
    """Metres and degrees. ``short_over=1``: the short tail's strand (end 0) is
    the one on top at the crossing; 0: the stem's (end 1)."""

    loop_radius: float
    half_angle_deg: float
    short_len: float
    stem_len: float
    short_over: int
    over_lift: float
    base_z: float
    lift_ramp: float = 0.030
    arc_points_per_quarter: int = 3
    center: tuple[float, float] = (0.0, 0.0)
    heading_deg: float = 0.0

    def __post_init__(self) -> None:
        _check_angle(self.half_angle_deg)
        _check_positive(loop_radius=self.loop_radius, short_len=self.short_len, stem_len=self.stem_len)
        _check_binary("short_over", self.short_over)


@dataclass(frozen=True)
class TwistSpec:
    """Metres and degrees. ``over_end_x1`` / ``over_end_x2``: which end's strand
    (0 or 1) is on top at X1 (next to the plugs) / X2 (next to the closed lobe).
    One half angle serves both crossings."""

    closed_lobe_radius: float
    middle_lobe_radius: float
    open_lobe_radius: float
    half_angle_deg: float
    end_gap: float
    over_end_x1: int
    over_end_x2: int
    over_lift: float
    base_z: float
    lift_ramp: float = 0.030
    arc_points_per_quarter: int = 3
    center: tuple[float, float] = (0.0, 0.0)
    heading_deg: float = 0.0

    def __post_init__(self) -> None:
        _check_angle(self.half_angle_deg)
        _check_positive(
            closed_lobe_radius=self.closed_lobe_radius,
            middle_lobe_radius=self.middle_lobe_radius,
            open_lobe_radius=self.open_lobe_radius,
        )
        if not 0.0 < self.end_gap < 2.0 * self.open_lobe_radius:
            raise ValueError(
                f"end_gap {self.end_gap} must be positive and below the open lobe's "
                f"diameter {2.0 * self.open_lobe_radius}."
            )
        _check_binary("over_end_x1", self.over_end_x1)
        _check_binary("over_end_x2", self.over_end_x2)


@dataclass(frozen=True)
class CurlsSpec:
    """Metres and degrees. ``stub_over_a`` / ``stub_over_b``: 1 when that end's
    stub is the strand on top at its own crossing, 0 when the middle rope is."""

    loop_radius: float
    half_angle_deg: float
    stub_len: float
    middle_len: float
    stub_side: str
    stub_over_a: int
    stub_over_b: int
    over_lift: float
    base_z: float
    lift_ramp: float = 0.030
    arc_points_per_quarter: int = 3
    center: tuple[float, float] = (0.0, 0.0)
    heading_deg: float = 0.0

    def __post_init__(self) -> None:
        _check_angle(self.half_angle_deg)
        if not self.half_angle_deg < 45.0:
            # The stub leaves at 2*phi from the middle rope; at 90 deg or more it
            # points back over its own loop.
            raise ValueError(f"curls need half_angle_deg < 45, got {self.half_angle_deg}.")
        _check_positive(loop_radius=self.loop_radius, stub_len=self.stub_len, middle_len=self.middle_len)
        if self.stub_side not in STUB_SIDES:
            raise ValueError(f"stub_side must be one of {STUB_SIDES}, got {self.stub_side!r}.")
        _check_binary("stub_over_a", self.stub_over_a)
        _check_binary("stub_over_b", self.stub_over_b)


def _check_angle(half_angle_deg: float) -> None:
    if not 0.0 < float(half_angle_deg) < 90.0:
        raise ValueError(f"half_angle_deg must be in (0, 90), got {half_angle_deg}.")


def _check_positive(**values: float) -> None:
    for name, value in values.items():
        if not float(value) > 0.0:
            raise ValueError(f"{name} must be positive, got {value}.")


def _check_binary(name: str, value: int) -> None:
    if int(value) not in (0, 1):
        raise ValueError(f"{name} must be 0 or 1, got {value}.")


# ------------------------------------------------------------------- pieces


def _dir(angle: float) -> np.ndarray:
    return np.array([math.cos(angle), math.sin(angle)])


def _arc(center, radius: float, start: float, end: float, points: int) -> np.ndarray:
    """``points`` samples on a circle from angle ``start`` to ``end`` inclusive."""

    angles = np.linspace(start, end, int(points))
    return np.column_stack([center[0] + radius * np.cos(angles), center[1] + radius * np.sin(angles)])


def _arc_count(sweep: float, per_quarter: int) -> int:
    return max(3, int(round(abs(sweep) / (0.5 * math.pi) * per_quarter)) + 1)


def teardrop(crossing, axis: float, radius: float, half_angle: float, enter: int, per_quarter: int) -> np.ndarray:
    """Arc of a teardrop loop hung on ``crossing`` (angles in radians).

    The loop's circle sits along ``axis`` from the crossing, at ``radius /
    sin(half_angle)``. The rope enters along the tangent ray at ``axis + enter *
    half_angle`` (``enter`` is +1 or -1), runs round the far side of the circle
    and comes back along the ray at ``axis - enter * half_angle``. Seen from the
    centre the tangent points sit at ``axis +- (pi/2 + half_angle)``, so the arc
    sweeps ``pi + 2 * half_angle``. Returns the arc from the entry tangent point
    to the exit tangent point, both included; the crossing itself is not.
    """

    crossing = np.asarray(crossing, dtype=float)
    centre = crossing + radius / math.sin(half_angle) * _dir(axis)
    start = axis + enter * (0.5 * math.pi + half_angle)
    end = axis - enter * (0.5 * math.pi + half_angle)
    arc = _arc(centre, radius, start, end, _arc_count(math.pi + 2.0 * half_angle, per_quarter))
    tangent = radius / math.tan(half_angle)
    assert np.allclose(arc[0], crossing + tangent * _dir(axis + enter * half_angle), atol=1e-9)
    assert np.allclose(arc[-1], crossing + tangent * _dir(axis - enter * half_angle), atol=1e-9)
    return arc


# ---------------------------------------------------------------- flat paths


def six_path(spec: SixSpec) -> np.ndarray:
    """Flat path (N, 2), end 0 to end 1: short tail -> X -> loop -> X -> stem."""

    phi = math.radians(spec.half_angle_deg)
    end0 = spec.short_len * _dir(math.pi - phi)
    loop = teardrop((0.0, 0.0), 0.0, spec.loop_radius, phi, -1, spec.arc_points_per_quarter)
    end1 = spec.stem_len * _dir(math.pi + phi)
    return np.vstack([end0, loop, end1])


def twist_path(spec: TwistSpec) -> np.ndarray:
    """Flat path (N, 2), end 0 to end 1, X1 at the origin:
    open lobe (+b half) -> X1 -> middle (-b) -> X2 -> closed lobe -> X2 ->
    middle (+b) -> X1 -> open lobe (-b half)."""

    phi = math.radians(spec.half_angle_deg)
    per = spec.arc_points_per_quarter
    r_o, r_m = spec.open_lobe_radius, spec.middle_lobe_radius
    c_open = np.array([-r_o / math.sin(phi), 0.0])
    c_mid = np.array([r_m / math.sin(phi), 0.0])
    x2 = 2.0 * c_mid
    cut = math.asin(spec.end_gap / (2.0 * r_o))
    tangent_angle = 0.5 * math.pi - phi  # open-lobe tangent points, seen from its centre
    open_sweep = math.pi - cut - tangent_angle
    open_plus = _arc(c_open, r_o, math.pi - cut, tangent_angle, _arc_count(open_sweep, per))
    mid_minus = _arc(c_mid, r_m, -(0.5 * math.pi + phi), -(0.5 * math.pi - phi), _arc_count(2.0 * phi, per))
    closed = teardrop(x2, 0.0, spec.closed_lobe_radius, phi, +1, per)
    mid_plus = _arc(c_mid, r_m, 0.5 * math.pi - phi, 0.5 * math.pi + phi, _arc_count(2.0 * phi, per))
    open_minus = _arc(c_open, r_o, -tangent_angle, -(math.pi - cut), _arc_count(open_sweep, per))
    return np.vstack([open_plus, mid_minus, closed, mid_plus, open_minus])


def curls_path(spec: CurlsSpec) -> np.ndarray:
    """Flat path (N, 2), end 0 to end 1, the middle rope's midpoint at the origin:
    stub A -> XA -> loop A -> XA -> middle -> XB -> loop B -> XB -> stub B."""

    phi = math.radians(spec.half_angle_deg)
    per = spec.arc_points_per_quarter
    side_a = 1
    side_b = 1 if spec.stub_side == "same" else -1
    xa = np.array([-0.5 * spec.middle_len, 0.0])
    xb = np.array([0.5 * spec.middle_len, 0.0])
    # Curl A: stub on the ray at side_a*2phi, loop between the rays at pi and
    # pi + side_a*2phi, entered along the stub line and left along the middle.
    end0 = xa + spec.stub_len * _dir(side_a * 2.0 * phi)
    loop_a = teardrop(xa, math.pi + side_a * phi, spec.loop_radius, phi, side_a, per)
    # Curl B: entered along the middle (ray 0), left along the ray at
    # -side_b*2phi; the stub continues that line to the inner side.
    loop_b = teardrop(xb, -side_b * phi, spec.loop_radius, phi, side_b, per)
    end1 = xb + spec.stub_len * _dir(math.pi - side_b * 2.0 * phi)
    return np.vstack([end0, loop_a, loop_b, end1])


def flat_path(spec) -> np.ndarray:
    if isinstance(spec, SixSpec):
        return six_path(spec)
    if isinstance(spec, TwistSpec):
        return twist_path(spec)
    if isinstance(spec, CurlsSpec):
        return curls_path(spec)
    raise TypeError(f"no flat path for {type(spec).__name__}")


def raised_passes(spec) -> tuple[str, ...]:
    """Per crossing, in rope order of its first pass: which pass is raised.

    ``"first"`` is the pass met first walking from end 0. The mapping from the
    yaml's per-shape leaves: six -- the short tail is the first pass; twist --
    end 0's strand is the first pass at both X1 and X2; curls -- at XA stub A is
    the first pass, at XB stub B is the second (the middle arrives first).
    """

    if isinstance(spec, SixSpec):
        return ("first" if int(spec.short_over) == 1 else "second",)
    if isinstance(spec, TwistSpec):
        return tuple("first" if int(end) == 0 else "second" for end in (spec.over_end_x1, spec.over_end_x2))
    if isinstance(spec, CurlsSpec):
        return (
            "first" if int(spec.stub_over_a) == 1 else "second",
            "second" if int(spec.stub_over_b) == 1 else "first",
        )
    raise TypeError(f"no raised passes for {type(spec).__name__}")


# ----------------------------------------------------------- crossings, bumps


def arclength(points: np.ndarray) -> np.ndarray:
    """Cumulative xy arclength, 0 at the first vertex."""

    steps = np.linalg.norm(np.diff(np.asarray(points, dtype=float)[:, :2], axis=0), axis=1)
    return np.concatenate([[0.0], np.cumsum(steps)])


def flat_crossings(path: np.ndarray) -> list[tuple[np.ndarray, float, float]]:
    """Proper xy self-crossings of an open polyline: ``(xy, s_first, s_second)``
    with arclengths ``s_first < s_second``, sorted by ``s_first``.

    Neighbouring segments are skipped (they share a vertex); the first and last
    segments are not neighbours.
    """

    p = np.asarray(path, dtype=float)[:, :2]
    s = arclength(p)
    a0, a1 = p[:-1], p[1:]
    r = a1 - a0
    out = []
    for i in range(len(r)):
        j = np.arange(i + 2, len(r))
        if not len(j):
            continue
        q0, sq = a0[j], r[j]
        denom = r[i, 0] * sq[:, 1] - r[i, 1] * sq[:, 0]
        ok = np.abs(denom) > 1e-14
        diff = q0 - a0[i]
        with np.errstate(divide="ignore", invalid="ignore"):
            t = (diff[:, 0] * sq[:, 1] - diff[:, 1] * sq[:, 0]) / denom
            u = (diff[:, 0] * r[i, 1] - diff[:, 1] * r[i, 0]) / denom
        hit = ok & (t > 1e-12) & (t < 1 - 1e-12) & (u > 1e-12) & (u < 1 - 1e-12)
        for k in np.nonzero(hit)[0]:
            jj = int(j[k])
            xy = a0[i] + t[k] * r[i]
            s1 = s[i] + t[k] * (s[i + 1] - s[i])
            s2 = s[jj] + u[k] * (s[jj + 1] - s[jj])
            out.append((xy, float(s1), float(s2)))
    out.sort(key=lambda item: item[1])
    return out


def _point_at(path: np.ndarray, s_path: np.ndarray, s: float) -> np.ndarray:
    return np.array([np.interp(s, s_path, path[:, 0]), np.interp(s, s_path, path[:, 1])])


def _straight_run(path: np.ndarray, s_path: np.ndarray, s: float, direction: int) -> float:
    """Arclength from ``s`` to the first vertex (walking ``direction``) where the
    polyline bends, or to the end of the rope."""

    heading = None
    if direction > 0:
        k = int(np.searchsorted(s_path, s, side="right"))
        indices = range(k, len(path))
        previous = s
    else:
        k = int(np.searchsorted(s_path, s, side="left")) - 1
        indices = range(k, -1, -1)
        previous = s
    start = _point_at(path, s_path, s)
    for index in indices:
        step = path[index] - start
        if np.linalg.norm(step) < 1e-12:
            continue
        unit = step / np.linalg.norm(step)
        if heading is None:
            heading = unit
        elif abs(heading[0] * unit[1] - heading[1] * unit[0]) > 1e-9 or float(heading @ unit) < 0.0:
            return float(abs(previous - s))
        previous = s_path[index]
    return float(abs(previous - s))


@dataclass(frozen=True)
class DeclaredCrossing:
    """One crossing as the generator built it (flat-path arclengths, metres)."""

    position: tuple[float, float]
    s_first: float
    s_second: float
    raised: str  # "first" or "second": which pass carries the bump

    @property
    def s_over(self) -> float:
        return self.s_first if self.raised == "first" else self.s_second

    @property
    def s_under(self) -> float:
        return self.s_second if self.raised == "first" else self.s_first


def raise_crossings(
    path: np.ndarray,
    raised: tuple[str, ...],
    *,
    over_lift: float,
    base_z: float,
    lift_ramp: float,
) -> tuple[np.ndarray, tuple[DeclaredCrossing, ...]]:
    """Lift one pass of every crossing of a flat path; ``(points (N, 3), declared)``.

    ``raised[k]`` is for the k-th crossing in rope order of its first pass. The
    raised pass gets three points -- ramp foot, apex ``over_lift`` above
    ``base_z`` at the crossing, ramp foot -- and the other pass one flat point
    at the crossing (the figure-8 does the same). The ramp is ``lift_ramp``,
    shortened to 0.8 of the straight run on either side (as the 8 clamps to
    ``0.8 * min(tangent lengths)``) and to 0.4 of the arclength to any other
    crossing pass, so no two bumps overlap. Control points inside a ramp lie
    on the straight run and are dropped.
    """

    path = np.asarray(path, dtype=float)[:, :2]
    s_path = arclength(path)
    hits = flat_crossings(path)
    if len(hits) != len(raised):
        raise ValueError(f"the flat path crosses itself {len(hits)} times, expected {len(raised)}.")
    passes = sorted([h[1] for h in hits] + [h[2] for h in hits])
    inserts: list[tuple[float, float]] = []  # (s, z)
    windows: list[tuple[float, float]] = []
    declared = []
    for (xy, s1, s2), which in zip(hits, raised):
        if which not in ("first", "second"):
            raise ValueError(f"raised must be 'first' or 'second', got {which!r}.")
        s_up, s_down = (s1, s2) if which == "first" else (s2, s1)
        others = [abs(p - s_up) for p in passes if abs(p - s_up) > 1e-12]
        ramp = min(
            float(lift_ramp),
            0.8 * _straight_run(path, s_path, s_up, -1),
            0.8 * _straight_run(path, s_path, s_up, +1),
            0.4 * min(others) if others else math.inf,
        )
        inserts += [(s_up - ramp, base_z), (s_up, base_z + over_lift), (s_up + ramp, base_z), (s_down, base_z)]
        windows.append((s_up - ramp, s_up + ramp))
        declared.append(DeclaredCrossing((float(xy[0]), float(xy[1])), float(s1), float(s2), which))

    keep = []
    for index, s in enumerate(s_path):
        inside = [lo < s < hi for lo, hi in windows]
        if any(inside):
            continue
        if any(abs(s - si) < 1e-12 for si, _z in inserts):
            continue
        keep.append((float(s), float(base_z)))
    rows = sorted(keep + inserts)
    s_new = np.array([s for s, _z in rows])
    xy_new = np.column_stack([np.interp(s_new, s_path, path[:, 0]), np.interp(s_new, s_path, path[:, 1])])
    points = np.column_stack([xy_new, [z for _s, z in rows]])
    return points, tuple(declared)


def to_task_frame(points: np.ndarray, center, heading_deg: float) -> np.ndarray:
    """Rotate local xy by ``heading_deg`` and add ``center``; z untouched."""

    points = np.asarray(points, dtype=float)
    theta = math.radians(float(heading_deg))
    rot = np.array([[math.cos(theta), -math.sin(theta)], [math.sin(theta), math.cos(theta)]])
    xy = points[:, :2] @ rot.T + np.asarray(center, dtype=float)[None, :]
    return np.column_stack([xy, points[:, 2]]) if points.shape[1] == 3 else xy


def shape_local_points(spec) -> tuple[np.ndarray, tuple[DeclaredCrossing, ...]]:
    """Control points (N, 3) in the local frame with the chosen passes raised."""

    return raise_crossings(
        flat_path(spec),
        raised_passes(spec),
        over_lift=float(spec.over_lift),
        base_z=float(spec.base_z),
        lift_ramp=float(spec.lift_ramp),
    )


def shape_control_points(spec) -> np.ndarray:
    """Control points (N, 3) in the task frame."""

    local, _declared = shape_local_points(spec)
    return to_task_frame(local, spec.center, spec.heading_deg)


# ------------------------------------------------------------ derived leaves


def curls_middle_bounds(
    stub_len: float, half_angle_deg: float, stub_side: str, *, min_plug_gap: float, min_middle: float, span: float
) -> tuple[float, float]:
    """Where the middle rope's length may sit for an O|-|O: ``(lo, lo + span)``.

    Both stubs lean in over the middle rope at 2*phi. With the stubs on the
    same side their tips are ``m - 2 l cos(2 phi)`` apart; with opposite sides
    the tips are also ``2 l sin(2 phi)`` apart across the rope. The lower bound
    keeps the two plugs ``min_plug_gap`` apart (the gripper span), which also
    keeps the stubs from crossing each other, and never goes below
    ``min_middle`` (opposite stubs alone would allow 2 cm, and the two loops
    then crowd each other).
    """

    two_phi = math.radians(2.0 * float(half_angle_deg))
    along = 2.0 * float(stub_len) * math.cos(two_phi)
    if stub_side == "same":
        lo = along + float(min_plug_gap)
    else:
        across = 2.0 * float(stub_len) * math.sin(two_phi)
        lo = along + math.sqrt(max(0.0, float(min_plug_gap) ** 2 - across**2))
    lo = max(lo, float(min_middle))
    return float(lo), float(lo + span)


# ------------------------------------------------------------- measurements


def teardrop_length(radius: float, half_angle_deg: float) -> float:
    """Rope in one teardrop loop, crossing to crossing: two tangents plus the
    far-side arc ``radius * (pi + 2 phi)``."""

    phi = math.radians(half_angle_deg)
    return float(2.0 * radius / math.tan(phi) + radius * (math.pi + 2.0 * phi))


def _resample(points: np.ndarray, step: float) -> tuple[np.ndarray, np.ndarray]:
    """xy samples every ``step`` of arclength (vertices kept), with their arclength."""

    xy = np.asarray(points, dtype=float)[:, :2]
    s = arclength(xy)
    fine = np.unique(np.concatenate([s, np.arange(0.0, s[-1], step)]))
    return np.column_stack([np.interp(fine, s, xy[:, 0]), np.interp(fine, s, xy[:, 1])]), fine


def strand_gap(points: np.ndarray, crossing_xy, *, min_arc: float, crossing_zone: float, step: float = 0.002) -> float:
    """Closest approach of two parts of the rope that are not neighbours and do
    not meet at a crossing (xy, metres).

    Pairs closer than ``min_arc`` along the rope are neighbours. Pairs that both
    lie within ``crossing_zone`` of one crossing are the crossing itself. What
    is left must keep clear: strands that spawn touching are pushed apart by the
    first settle and read differently; `_particle_arclength` would also give
    their FEM nodes to the wrong strand.
    """

    xy, s = _resample(points, step)
    diff = xy[:, None, :] - xy[None, :, :]
    dist = np.linalg.norm(diff, axis=2)
    mask = np.abs(s[:, None] - s[None, :]) > min_arc
    for c in crossing_xy:
        near = np.linalg.norm(xy - np.asarray(c, dtype=float)[None, :], axis=1) < crossing_zone
        mask &= ~(near[:, None] & near[None, :])
    return float(dist[mask].min()) if mask.any() else math.inf


def plug_clearance(points: np.ndarray, first_pass: float, last_pass: float, step: float = 0.002) -> float:
    """Smaller of the two plugs' distances to rope beyond their own tail (xy).

    End 0's own tail is the rope up to its first crossing pass; everything past
    it counts -- including the other strand through that crossing, which is
    what a short stub angled off a straight middle rope comes close to.
    """

    xy, s = _resample(points, step)
    d0 = np.linalg.norm(xy[s > first_pass] - xy[0][None, :], axis=1)
    d1 = np.linalg.norm(xy[s < last_pass] - xy[-1][None, :], axis=1)
    return float(min(d0.min() if len(d0) else math.inf, d1.min() if len(d1) else math.inf))


@dataclass(frozen=True)
class CentreWindow:
    """Where a shape's local origin may sit (task frame, metres): every spawn
    point and planned landing ``margin`` inside the workspace box, and every
    grasp and landing within ``max_hand_dist`` of the arm base.

    The set is a box cut by discs, so it is convex: the y range is an interval
    and so is the x range at any y inside it. The randomizer draws y from a
    unit fraction first and x second, the order ring_transfer uses for its
    reach disc.
    """

    y_range: tuple[float, float]
    x_box: tuple[float, float]
    reach_offsets: np.ndarray  # (K, 2) rotated local points that must stay in reach
    arm_base_xy: tuple[float, float]
    max_hand_dist: float

    def x_range(self, cy: float) -> tuple[float, float] | None:
        lo, hi = self.x_box
        bx, by = self.arm_base_xy
        for px, py in self.reach_offsets:
            dy = cy + py - by
            if abs(dy) > self.max_hand_dist:
                return None
            half = math.sqrt(self.max_hand_dist**2 - dy**2)
            lo, hi = max(lo, bx - px - half), min(hi, bx - px + half)
        return (float(lo), float(hi)) if hi >= lo else None

    def at(self, frac_x: float, frac_y: float) -> tuple[float, float]:
        """The centre for two unit fractions: y across the y range, then x
        across the x range at that y."""

        y_lo, y_hi = self.y_range
        cy = y_lo + min(max(float(frac_y), 0.0), 1.0) * (y_hi - y_lo)
        x_lo, x_hi = self.x_range(cy)
        return float(x_lo + min(max(float(frac_x), 0.0), 1.0) * (x_hi - x_lo)), float(cy)


def centre_window(
    local_points: np.ndarray,
    landing_points: np.ndarray,
    grasp_points: np.ndarray,
    *,
    heading_deg: float,
    workspace_x: tuple[float, float],
    workspace_y: tuple[float, float],
    margin: float,
    arm_base_xy: tuple[float, float],
    max_hand_dist: float,
) -> CentreWindow | None:
    """`CentreWindow` for points in the shape's local frame turned by
    ``heading_deg``; None if no centre fits."""

    theta = math.radians(float(heading_deg))
    rot = np.array([[math.cos(theta), -math.sin(theta)], [math.sin(theta), math.cos(theta)]])
    body = np.vstack([np.asarray(local_points)[:, :2], np.asarray(landing_points).reshape(-1, 2)]) @ rot.T
    reach = np.vstack([np.asarray(grasp_points).reshape(-1, 2), np.asarray(landing_points).reshape(-1, 2)]) @ rot.T
    x_lo, x_hi = workspace_x[0] + margin - body[:, 0].min(), workspace_x[1] - margin - body[:, 0].max()
    y_lo, y_hi = workspace_y[0] + margin - body[:, 1].min(), workspace_y[1] - margin - body[:, 1].max()
    if x_hi < x_lo or y_hi < y_lo:
        return None
    probe = CentreWindow((y_lo, y_hi), (x_lo, x_hi), reach, tuple(arm_base_xy), float(max_hand_dist))
    ok = [cy for cy in np.linspace(y_lo, y_hi, 401) if probe.x_range(float(cy)) is not None]
    if not ok:
        return None
    return CentreWindow((float(min(ok)), float(max(ok))), (x_lo, x_hi), reach, tuple(arm_base_xy), float(max_hand_dist))


def band_checks(
    points: np.ndarray,
    plan,
    *,
    expected_crossings: int,
    tube_radius: float,
    min_clearance: float,
    strand_gap_min: float,
    crossing_spacing_min: float,
    place_clearance: float,
    workspace_x: tuple[float, float],
    workspace_y: tuple[float, float],
    workspace_z_max: float,
    workspace_margin: float,
    arm_base_xy: tuple[float, float],
    max_hand_dist: float,
    merge_radius: float,
    lay_down_min: float,
    slack_range: tuple[float, float],
    rotation_min_deg: float,
) -> list[tuple[str, float, float, bool]]:
    """``[(name, measured, limit, ok)]`` for one spawn, task frame, metres.

    ``plan`` is the move model's plan on these same points
    (`topogym/planning/band_untwist_sequence.plan`), or None when it found none;
    the caller computes it so this module stays free of topogym imports. One
    list for the randomizer's reject step, the offline gates and the demo's
    start-up print. Rows that the planner already enforces (lay-down, slack,
    swing, hand height) are still listed: their margins pick the tightest cells
    for the physics sweep.
    """

    points = np.asarray(points, dtype=float)
    xy = points[:, :2]
    found = flat_crossings_measured(points, merge_radius)
    passes = sorted([p for c in found for p in (c[1], c[2])])
    radii = chord_turn_radii(points)
    corner = float(np.min(radii[np.isfinite(radii)]))
    gap = strand_gap(points, [c[0] for c in found], min_arc=0.05, crossing_zone=0.030)
    spacing = (
        min(float(np.linalg.norm(np.subtract(a[0], b[0]))) for i, a in enumerate(found) for b in found[i + 1 :])
        if len(found) > 1 else math.inf
    )
    plug = plug_clearance(points, passes[0], passes[-1]) if passes else math.inf
    separation = float(np.linalg.norm(xy[0] - xy[-1]))
    bottom = float(points[:, 2].min()) - float(tube_radius)

    rows = [
        ("crossing_count", float(len(found)), float(expected_crossings), len(found) == int(expected_crossings)),
        ("end_separation", separation, float(min_clearance), separation >= min_clearance - 1e-9),
        ("corner_radius", corner, 3.0 * float(tube_radius), corner >= 3.0 * float(tube_radius) - 1e-9),
        ("bottom_clearance", bottom, 0.0, bottom >= -1e-9),
        ("strand_gap", gap, float(strand_gap_min), gap >= strand_gap_min - 1e-9),
        ("crossing_spacing", spacing, float(crossing_spacing_min), spacing >= crossing_spacing_min - 1e-9),
        ("plug_clearance", plug, float(place_clearance), plug >= place_clearance - 1e-9),
    ]
    found_plan = plan is not None and len(plan.moves) > 0
    rows.append(("plan_found", 1.0 if found_plan else 0.0, 1.0, bool(found_plan)))
    landings = np.array([m.place_xy for m in plan.moves]) if found_plan else np.zeros((0, 2))
    grasps = np.array([m.grasp_xy for m in plan.moves]) if found_plan else np.zeros((0, 2))
    body = np.vstack([xy, landings])
    footprint = float(min(
        (body[:, 0] - workspace_x[0]).min(), (workspace_x[1] - body[:, 0]).min(),
        (body[:, 1] - workspace_y[0]).min(), (workspace_y[1] - body[:, 1]).min(),
    ))
    rows.append(("footprint", footprint, float(workspace_margin), footprint >= workspace_margin - 1e-9))
    base = np.asarray(arm_base_xy, dtype=float)
    reach_pts = np.vstack([grasps, landings]) if found_plan else xy[[0, -1]]
    reach = float(np.linalg.norm(reach_pts - base[None, :], axis=1).max())
    rows.append(("reach", reach, float(max_hand_dist), reach <= max_hand_dist + 1e-9))
    if found_plan:
        hand = plan.max_hand_height
        lay = plan.margin("lay_down_clearance")
        slack_lo, slack_hi = plan.margin("slack"), plan.margin("slack", max)
        swing = plan.margin("rotation_deg")
        place = plan.margin("place_clearance")
        if math.isnan(slack_lo):  # a plan of flips lays no chord: the slack rows do not apply
            slack_lo, slack_hi = slack_range
    else:
        hand, lay, slack_lo, slack_hi, swing, place = math.inf, 0.0, 0.0, math.inf, 0.0, 0.0
    rows += [
        ("hand_height", hand, float(workspace_z_max), hand <= workspace_z_max + 1e-9),
        ("lay_down_clearance", lay, float(lay_down_min), lay >= lay_down_min - 1e-9),
        ("slack_min", slack_lo, float(slack_range[0]), slack_lo >= slack_range[0] - 1e-9),
        ("slack_max", slack_hi, float(slack_range[1]), slack_hi <= slack_range[1] + 1e-9),
        ("swing", swing, float(rotation_min_deg), swing >= rotation_min_deg - 1e-9),
        ("place_clearance", place, float(place_clearance), place >= place_clearance - 1e-9),
    ]
    return rows


def flat_crossings_measured(points: np.ndarray, merge_radius: float) -> list[tuple[np.ndarray, float, float]]:
    """Self-crossings of a polyline whose crossings sit on vertices (a raised
    control polygon): segment hits counted inclusively and merged within
    ``merge_radius``. ``(xy, s_first, s_second)`` sorted by ``s_first``."""

    p = np.asarray(points, dtype=float)[:, :2]
    s = arclength(p)
    a0, a1 = p[:-1], p[1:]
    raw = []
    for i in range(len(a0)):
        for j in range(i + 2, len(a0)):
            r, q = a1[i] - a0[i], a1[j] - a0[j]
            denom = r[0] * q[1] - r[1] * q[0]
            if abs(denom) < 1e-14:
                continue
            d = a0[j] - a0[i]
            t = (d[0] * q[1] - d[1] * q[0]) / denom
            u = (d[0] * r[1] - d[1] * r[0]) / denom
            if -1e-9 <= t <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9:
                xy = a0[i] + t * r
                raw.append((xy, float(s[i] + t * (s[i + 1] - s[i])), float(s[j] + u * (s[j + 1] - s[j]))))
    merged: list = []
    for hit in raw:
        if not any(float(np.linalg.norm(hit[0] - kept[0])) <= merge_radius for kept in merged):
            merged.append(hit)
    merged.sort(key=lambda h: h[1])
    return merged


def chord_turn_radii(points: np.ndarray) -> np.ndarray:
    """Circumradius of each consecutive point triple, in 3D (collinear -> inf).

    In 3D rather than the xy plane so the crossing bump counts: its three
    points are collinear from above but form a corner in the vertical, and that
    corner tightens when the bump's ramp is clamped to a short straight run.
    """

    p = np.asarray(points, dtype=float)
    a, b, c = p[:-2], p[1:-1], p[2:]
    ab, bc, ca = np.linalg.norm(b - a, axis=1), np.linalg.norm(c - b, axis=1), np.linalg.norm(a - c, axis=1)
    cross = np.linalg.norm(np.cross(b - a, c - a), axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(cross < 1e-12, np.inf, ab * bc * ca / (2.0 * cross))
