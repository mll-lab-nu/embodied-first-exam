"""Closed elastic band: a periodic tube, and the topology readings it needs.

`world/rope.py` sweeps an OPEN tube: its side quads only connect ring `i` to
ring `i+1` (`rope.py:344`), it caps both ends unconditionally (`rope.py:352`),
and `parallel_transport_frames` (`rope.py:181`) takes one-sided differences at
the ends with no seam closure. A band has no ends, so this module supplies the
periodic versions. Everything else in the rope pipeline is reused unchanged --
`tube_morph`'s `force_retet=True` tetrahedralizes any watertight closed mesh, so
a torus loads as `FEM.Elastic` the same way an open tube does.

**The seam choice is the band's stored twist, and it decides whether the task is
solvable.** Bishop transport around a closed curve does not come home: the
normal returns rotated by a holonomy angle H. Closing the frame means rotating
it by `-H + 2*pi*k` over the loop, and that `k` is not cosmetic. The framed band
has an integer self-linking number `Lk = Tw + Wr`, which no motion can change
while the band does not pass through itself, and every unit of `k` moves `Lk` by
one. A flat O has `Lk = 0`. So a band spawned with `Lk = +-1` can never be
flipped flat -- the task would be physically unsolvable with a scene that looks
correct. `closed_transport_frames` therefore does not pick `k` to make the
built-in twist small; it picks the `k` that lands `Lk` on the requested target,
and reports what that cost in twist.

That cost is the physics the task runs on. A figure-8 spawned at `Lk = 0` carries
about one turn of material twist against a writhe of about minus one turn; the
flat O is the lower-energy state, and what holds the 8 up is the self-contact at
its crossing. `docs/develop/tasks/task_environment_buildout_zh.md` section 3
lists this as the closed-ring capability that blocks docx 2.6, 2.7 and 3.3.

Pure numpy: no Genesis, no solver. Importing it does pull `topogym.world`'s
package init, which imports Genesis.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Rows are the projection basis: (u, v) span the picture plane, w points at the
# viewer. `WALL_PROJECTION` looks along -x at a band hanging in front of a panel
# whose normal is +x, so the picture is (y, z) and "over" means larger x.
WALL_PROJECTION = np.array(
    [[0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [1.0, 0.0, 0.0]], dtype=float
)
TOPDOWN_PROJECTION = np.eye(3, dtype=float)


@dataclass(frozen=True)
class Crossing:
    """One crossing in a projection, signed and depth-resolved."""

    position: tuple[float, float]  # in the projection's (u, v) picture plane
    sign: int  # +1 when (over tangent, under tangent) is a right-handed 2D pair
    gap: float  # over minus under along the viewing axis, meters
    over_at: float  # normalized position along the over curve, [0, 1)
    under_at: float  # normalized position along the under curve, [0, 1)


@dataclass(frozen=True)
class BandFrames:
    """A closed centerline's material frames, plus what closing them cost."""

    tangents: np.ndarray  # (N, 3)
    normals: np.ndarray  # (N, 3), the material frame -- Bishop plus the closure
    binormals: np.ndarray  # (N, 3)
    holonomy_turns: float  # Bishop's failure to come home, in turns
    closure_turns: int  # the k that was chosen
    twist_turns: float  # material twist relative to Bishop, in turns
    self_linking: int  # Lk of the resulting ribbon
    perimeter: float  # closed arc length, meters


def _unit(vectors: np.ndarray) -> np.ndarray:
    vectors = np.asarray(vectors, dtype=float)
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    if np.any(norms <= 1e-12):
        raise ValueError("Degenerate segment in a closed band centerline.")
    return vectors / norms


def _rotate_about(vectors: np.ndarray, axes: np.ndarray, angles: np.ndarray) -> np.ndarray:
    """Rodrigues rotation of each row of ``vectors`` about the matching axis."""

    angles = np.asarray(angles, dtype=float)[:, None]
    cos, sin = np.cos(angles), np.sin(angles)
    dot = np.sum(vectors * axes, axis=1)[:, None]
    return vectors * cos + np.cross(axes, vectors) * sin + axes * dot * (1.0 - cos)


def closed_arc_length(centerline: np.ndarray) -> tuple[np.ndarray, float]:
    """Arc length at each sample and the closed perimeter (the wrap included)."""

    pts = np.asarray(centerline, dtype=float)
    steps = np.linalg.norm(np.roll(pts, -1, axis=0) - pts, axis=1)
    return np.concatenate([[0.0], np.cumsum(steps[:-1])]), float(steps.sum())


def closed_transport_frames(
    centerline: np.ndarray,
    *,
    tube_radius: float,
    self_linking_target: int = 0,
    projection: np.ndarray = WALL_PROJECTION,
) -> BandFrames:
    """Periodic material frames for a closed centerline, at a chosen self-linking.

    Tangents are wrap-around central differences. The normal is Bishop-transported
    right around the loop, including the closing segment, and the residual angle
    is the holonomy. The closure ``-H + 2*pi*k`` is then spread evenly along arc
    length -- even is the torsional-energy minimum for a uniform rod -- and ``k``
    is solved for, not guessed: each unit of ``k`` shifts the ribbon's self-linking
    by exactly one, so one trial framing measures the offset and the second lands
    on ``self_linking_target``.

    Self-linking is read as signed crossings between the centerline and its push-off
    along the material normal, halved. That is an integer by construction and needs
    no near-singular quadrature, unlike the Gauss integral for two curves this
    close together.
    """

    pts = np.asarray(centerline, dtype=float)
    count = len(pts)
    if count < 8:
        raise ValueError("A closed band centerline needs at least 8 samples.")

    tangents = _unit(np.roll(pts, -1, axis=0) - np.roll(pts, 1, axis=0))

    seed = np.cross(np.array([0.0, 0.0, 1.0]), tangents[0])
    if float(np.linalg.norm(seed)) <= 1e-8:
        seed = np.cross(np.array([1.0, 0.0, 0.0]), tangents[0])
    seed = _unit(seed[None, :])[0]

    def _transport(normal: np.ndarray, before: np.ndarray, after: np.ndarray) -> np.ndarray:
        axis = np.cross(before, after)
        sin_angle = float(np.linalg.norm(axis))
        if sin_angle > 1e-12:
            angle = float(np.arctan2(sin_angle, float(np.clip(np.dot(before, after), -1.0, 1.0))))
            normal = _rotate_about(normal[None, :], (axis / sin_angle)[None, :], [angle])[0]
        normal = normal - float(np.dot(normal, after)) * after
        return _unit(normal[None, :])[0]

    bishop = [seed]
    for index in range(1, count):
        bishop.append(_transport(bishop[-1], tangents[index - 1], tangents[index]))
    returned = _transport(bishop[-1], tangents[-1], tangents[0])
    bishop_array = np.asarray(bishop, dtype=float)

    # Signed angle from the seed to what came back, about the shared tangent.
    reference = np.cross(tangents[0], bishop_array[0])
    holonomy = float(
        np.arctan2(float(np.dot(returned, reference)), float(np.dot(returned, bishop_array[0])))
    )

    arc, perimeter = closed_arc_length(pts)

    def _framing(turns: int) -> tuple[np.ndarray, float]:
        total = -holonomy + 2.0 * np.pi * turns
        normals = _rotate_about(bishop_array, tangents, total * arc / perimeter)
        push_off = pts + tube_radius * normals
        linking = linking_number(pts, push_off, projection=projection)
        return normals, linking

    nearest = int(np.rint(holonomy / (2.0 * np.pi)))
    _, trial_linking = _framing(nearest)
    chosen = nearest + int(self_linking_target - round(trial_linking))
    normals, linking = _framing(chosen)
    if round(linking) != self_linking_target:
        raise ValueError(
            f"closed_transport_frames could not reach self_linking={self_linking_target}: "
            f"k={chosen} gives Lk={linking:.3f}. The centerline probably crosses itself "
            "in the projection at a grazing angle; re-sample it or change the projection."
        )

    return BandFrames(
        tangents=tangents,
        normals=normals,
        binormals=np.cross(tangents, normals),
        holonomy_turns=holonomy / (2.0 * np.pi),
        closure_turns=chosen,
        twist_turns=(-holonomy + 2.0 * np.pi * chosen) / (2.0 * np.pi),
        self_linking=int(round(linking)),
        perimeter=perimeter,
    )


def closed_tube_mesh(
    centerline: np.ndarray,
    frames: BandFrames,
    *,
    radius: float,
    radial_segments: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Sweep a periodic tube. Same rings as ``make_elastic_tube_mesh``, no caps.

    Ring ``N-1`` joins ring ``0`` directly with no index shift, because the frames
    handed in are already periodic -- that is what ``closed_transport_frames`` buys.
    The result is a torus: watertight, genus one, every edge in exactly two faces.
    """

    if radius <= 0.0:
        raise ValueError("closed_tube_mesh radius must be positive.")
    if radial_segments < 4:
        raise ValueError("closed_tube_mesh radial_segments must be at least 4.")

    pts = np.asarray(centerline, dtype=float)
    count = len(pts)
    theta = 2.0 * np.pi * np.arange(radial_segments) / radial_segments
    offsets = radius * (
        np.cos(theta)[None, :, None] * frames.normals[:, None, :]
        + np.sin(theta)[None, :, None] * frames.binormals[:, None, :]
    )
    vertices = (pts[:, None, :] + offsets).reshape(-1, 3)

    faces = []
    for index in range(count):
        ring_0 = index * radial_segments
        ring_1 = ((index + 1) % count) * radial_segments
        for spoke in range(radial_segments):
            spoke_1 = (spoke + 1) % radial_segments
            faces.append([ring_0 + spoke, ring_0 + spoke_1, ring_1 + spoke])
            faces.append([ring_0 + spoke_1, ring_1 + spoke_1, ring_1 + spoke])
    return vertices, np.asarray(faces, dtype=int)


def hanging_band_centerline(
    *,
    perimeter: float,
    loop_radius: float,
    peg_center,
    half_turns: float = 0.0,
    segment_length: float,
) -> np.ndarray:
    """A closed band hung on a horizontal peg, twisted by ``half_turns``.

    The flat shape is a stadium in the vertical plane: a top semicircle of
    ``loop_radius`` wrapped over ``peg_center``, two straights down, and a bottom
    semicircle. ``half_turns=0`` leaves it an O; ``+-1`` gives the figure-8 of docx
    3.3, ``+-2`` the two-crossing state a flip in the wrong direction reaches.

    The twist is a rotation about the vertical axis through the peg, ramped with a
    smoothstep in height between the two cap centers and held constant on the caps
    themselves. So the top cap stays put on the peg, the bottom cap turns as one
    piece and stays in the wall plane, and the crossing appears halfway down where
    the two strands have swapped sides -- the two of them sitting one full
    ``2 * loop_radius`` apart along the panel normal, which is why nothing
    interpenetrates at spawn. This is the same motion the robot has to undo, so
    the spawn generator and the oracle's target are one routine.

    The ramp is a smoothstep rather than linear because a linear one meets the caps
    with a step in twist rate, and that corner is a curvature spike: measured on a
    360 mm band over a 22 mm loop, the tightest bend was 8.2 mm (2.05 tube radii,
    where the skin starts folding into itself) against the 21.1 mm a smoothstep
    gives. Twist rate is then not uniform along the band, which costs nothing here
    -- with a straight rest shape the spawn distribution is an initial condition
    the solver relaxes, not stored shape.

    Height is solved for, not set, so that the O and the figure-8 are the SAME
    band: twisting turns the straights into helices and pulls the caps together,
    and the relation is not closed-form once the ramp is a smoothstep. The curve is
    then resampled at uniform arc length, because sampling before the twist and
    stretching afterwards leaves the ring pitch uneven where the twist is fastest.
    """

    top = np.asarray(peg_center, dtype=float)
    across = np.array([0.0, 1.0, 0.0])
    up = np.array([0.0, 0.0, 1.0])
    step = float(segment_length) / 5.0

    def _shape(straight: float) -> np.ndarray:
        bottom = top - np.array([0.0, 0.0, straight])

        def _line(start, end):
            steps = max(2, int(np.ceil(float(np.linalg.norm(end - start)) / step)))
            alpha = np.linspace(0.0, 1.0, steps, endpoint=False)[:, None]
            return start[None, :] * (1.0 - alpha) + end[None, :] * alpha

        def _cap(center, first, second):
            steps = max(3, int(np.ceil(np.pi * loop_radius / step)))
            angle = np.linspace(0.0, np.pi, steps, endpoint=False)[:, None]
            return (
                center[None, :]
                + loop_radius * np.cos(angle) * first[None, :]
                + loop_radius * np.sin(angle) * second[None, :]
            )

        pts = np.concatenate(
            [
                _line(top + loop_radius * across, bottom + loop_radius * across),
                _cap(bottom, across, -up),
                _line(bottom - loop_radius * across, top - loop_radius * across),
                _cap(top, -across, up),
            ]
        )
        ramp = np.clip((top[2] - pts[:, 2]) / straight, 0.0, 1.0)
        angle = float(half_turns) * np.pi * ramp * ramp * (3.0 - 2.0 * ramp)
        cos, sin = np.cos(angle), np.sin(angle)
        local = pts[:, :2] - top[None, :2]
        return np.column_stack(
            [
                top[0] + local[:, 0] * cos - local[:, 1] * sin,
                top[1] + local[:, 0] * sin + local[:, 1] * cos,
                pts[:, 2],
            ]
        )

    # Arc length grows monotonically with height, so bisect. At zero height the
    # band is two caps plus the strands winding on the spot, which is the shortest
    # a band with this much twist can be.
    floor = 2.0 * np.pi * loop_radius + 2.0 * loop_radius * abs(float(half_turns)) * np.pi
    if float(perimeter) <= floor:
        raise ValueError(
            f"perimeter {perimeter:.4f} m cannot take {half_turns:+.1f} half turns at "
            f"loop_radius {loop_radius:.4f} m: the caps and the winding alone are "
            f"{floor:.4f} m, leaving no height. Lengthen the band or narrow the loop."
        )
    low, high = 1e-4, 0.5 * float(perimeter)
    for _ in range(60):
        middle = 0.5 * (low + high)
        if closed_arc_length(_shape(middle))[1] < float(perimeter):
            low = middle
        else:
            high = middle

    dense = _shape(0.5 * (low + high))
    steps = np.linalg.norm(np.roll(dense, -1, axis=0) - dense, axis=1)
    arc = np.concatenate([[0.0], np.cumsum(steps)])
    count = max(8, int(round(arc[-1] / float(segment_length))))
    wanted = np.linspace(0.0, arc[-1], count, endpoint=False)
    closed = np.vstack([dense, dense[0]])
    return np.column_stack([np.interp(wanted, arc, closed[:, axis]) for axis in range(3)])


def _segment_hit(p0, p1, q0, q1):
    """(t, u) where the 2D segments properly cross, else None."""

    r = p1 - p0
    s = q1 - q0
    denom = float(r[0] * s[1] - r[1] * s[0])
    if abs(denom) < 1e-12:
        return None
    diff = q0 - p0
    t = float(diff[0] * s[1] - diff[1] * s[0]) / denom
    u = float(diff[0] * r[1] - diff[1] * r[0]) / denom
    if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
        return t, u
    return None


def _project(polyline: np.ndarray, projection: np.ndarray) -> np.ndarray:
    return np.asarray(polyline, dtype=float) @ np.asarray(projection, dtype=float).T


def _crossings(
    a: np.ndarray,
    b: np.ndarray,
    *,
    projection: np.ndarray,
    same_curve: bool,
    skip_adjacent: int,
) -> list[Crossing]:
    """Signed crossings between two closed projected polylines.

    Both are treated as closed: segment ``i`` runs from sample ``i`` to sample
    ``i+1 mod N``. When ``same_curve`` is set the pair loop is upper-triangular and
    segments within ``skip_adjacent`` of each other cyclically are skipped -- they
    share a vertex or nearly do, so their "crossing" is the curve touching itself.
    """

    pa, pb = _project(a, projection), _project(b, projection)
    count_a, count_b = len(pa), len(pb)
    hits: list[Crossing] = []
    for i in range(count_a):
        a0, a1 = pa[i], pa[(i + 1) % count_a]
        others = range(i + 1, count_a) if same_curve else range(count_b)
        for j in others:
            if same_curve and min(j - i, count_a - (j - i)) <= skip_adjacent:
                continue
            b0, b1 = pb[j], pb[(j + 1) % count_b]
            hit = _segment_hit(a0[:2], a1[:2], b0[:2], b1[:2])
            if hit is None:
                continue
            t, u = hit
            point = a0[:2] + t * (a1[:2] - a0[:2])
            depth_a = a0[2] + t * (a1[2] - a0[2])
            depth_b = b0[2] + u * (b1[2] - b0[2])
            if depth_a >= depth_b:
                over, under = a1 - a0, b1 - b0
                over_at, under_at = (i + t) / count_a, (j + u) / count_b
            else:
                over, under = b1 - b0, a1 - a0
                over_at, under_at = (j + u) / count_b, (i + t) / count_a
            twist = float(over[0] * under[1] - over[1] * under[0])
            hits.append(
                Crossing(
                    position=(float(point[0]), float(point[1])),
                    sign=1 if twist > 0.0 else -1,
                    gap=float(abs(depth_a - depth_b)),
                    over_at=float(over_at),
                    under_at=float(under_at),
                )
            )
    return hits


def _merge_nearby(hits: list[Crossing], *, merge_radius: float) -> tuple[Crossing, ...]:
    """Collapse hits within ``merge_radius``, keeping the largest depth gap.

    One physical crossing spans several segment pairs; without this it is counted
    once per intersecting pair. Same rule as ``untangle_continuous_verifier``.
    """

    merged: list[Crossing] = []
    for hit in hits:
        for index, kept in enumerate(merged):
            near = float(
                np.hypot(hit.position[0] - kept.position[0], hit.position[1] - kept.position[1])
            )
            if near <= merge_radius:
                if hit.gap > kept.gap:
                    merged[index] = hit
                break
        else:
            merged.append(hit)
    return tuple(merged)


def band_self_crossings(
    polyline: np.ndarray,
    *,
    projection: np.ndarray = WALL_PROJECTION,
    merge_radius: float,
    skip_adjacent: int = 2,
) -> tuple[Crossing, ...]:
    """Signed self-crossings of one closed curve in a projection.

    The reading docx 3.3 judges on: a flat O gives 0, a figure-8 gives 1, a flip
    in the wrong direction gives 2. It is a projected count, so squashing the 8
    flat or hiding the crossing behind the other strand does not change it.
    """

    hits = _crossings(
        polyline,
        polyline,
        projection=projection,
        same_curve=True,
        skip_adjacent=skip_adjacent,
    )
    return _merge_nearby(hits, merge_radius=merge_radius)


def linking_number(
    curve_a: np.ndarray,
    curve_b: np.ndarray,
    *,
    projection: np.ndarray = WALL_PROJECTION,
) -> float:
    """Gauss linking number of two closed curves, as half the signed crossings.

    Returns a float so a caller can see how far off an integer it landed; a value
    that is not nearly integral means the projection is degenerate for these
    curves (a crossing seen edge-on), not that the topology is fractional.
    """

    hits = _crossings(
        curve_a, curve_b, projection=projection, same_curve=False, skip_adjacent=0
    )
    return 0.5 * float(sum(hit.sign for hit in hits))


__all__ = [
    "BandFrames",
    "Crossing",
    "TOPDOWN_PROJECTION",
    "WALL_PROJECTION",
    "band_self_crossings",
    "closed_arc_length",
    "closed_transport_frames",
    "closed_tube_mesh",
    "hanging_band_centerline",
    "linking_number",
]
