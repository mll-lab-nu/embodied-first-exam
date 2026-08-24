"""Layout budget for `ring_transfer` (docx 2.6): posts, the closed loop, and what
the one-gripper oracle needs from them.

Pure numpy on top of `topogym.world.closed_band`. Nothing here touches a solver;
`tests/check_ring_transfer_geometry.py` runs every inequality below without a
GPU, and `RingTransferLayout` calls the same functions so the scene and the gate
cannot disagree.

Frame: task coordinates (origin at the table centre, z=0 on the tabletop). The
loop lies flat, so its centerline plane is one tube radius above the table --
derived, never configured.

The numbers that decide whether the task can be done with ONE gripper come from
the stretch phase, and they are worth stating once because they are not obvious:

The loop starts hooked on post A and pointing away from post B. The only way a
single grasp can get post B *inside* the loop is to pull the far cap past B at
table height, so that B enters the triangle formed by A's two tangent points and
the held cap. The two strands straighten under tension, so their separation
narrows linearly from the loop's full width at A to the held piece's width at
the cap. `strand_separation_at` evaluates that line where it passes B, and
`min_strand_separation` is what it has to clear: B's diameter plus two tube
diameters plus the barrier. This is the inequality that sizes `loop_radius`
against `posts[*].radius` and the post spacing; at 20 mm posts and a 60 mm loop
it cannot be met at any stretch below ~50 %, which is why the posts are 10 mm.

The carry over B happens at a height where the strand -- a straight line from
A's tangent point on the table up to the held cap -- clears B's top where it
crosses B's x. `carry_height_floor` gives that height for a landing point; the
oracle's `carry_z` must be at or above it, and the offline gate checks it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from topogym.world.closed_band import (
    TOPDOWN_PROJECTION,
    band_reach,
    closed_arc_length,
    closed_transport_frames,
    closed_tube_mesh,
    pegged_band_centerline,
)


@dataclass(frozen=True)
class PostSpec:
    name: str
    center: np.ndarray  # task-frame xy
    radius: float
    height: float

    @property
    def top_z(self) -> float:
        return float(self.height)


@dataclass(frozen=True)
class RingSpec:
    perimeter: float
    loop_radius: float
    tube_radius: float
    long_axis: np.ndarray  # unit xy direction the loop extends in from its post
    enclosure: tuple[str, ...]  # posts the loop is spawned around
    segment_length: float
    radial_segments: int


def posts_from_config(posts_cfg) -> dict[str, PostSpec]:
    """`task.posts` is a LIST so the variant axis (more posts) is a config edit."""

    posts: dict[str, PostSpec] = {}
    for item in posts_cfg:
        name = str(item.name)
        if name in posts:
            raise ValueError(f"ring_transfer: post name {name!r} appears twice in task.posts.")
        posts[name] = PostSpec(
            name=name,
            center=np.array([float(item.pos[0]), float(item.pos[1])], dtype=float),
            radius=float(item.radius),
            height=float(item.height),
        )
    if len(posts) < 2:
        raise ValueError("ring_transfer needs at least two posts.")
    return posts


def ring_from_config(ring_cfg, rope_cfg) -> RingSpec:
    axis = np.array([float(ring_cfg.long_axis[0]), float(ring_cfg.long_axis[1])], dtype=float)
    norm = float(np.linalg.norm(axis))
    if norm <= 1e-9:
        raise ValueError("ring.long_axis must be a non-zero xy direction.")
    return RingSpec(
        perimeter=float(ring_cfg.perimeter),
        loop_radius=float(ring_cfg.loop_radius),
        tube_radius=float(rope_cfg.radius),
        long_axis=axis / norm,
        enclosure=tuple(str(name) for name in ring_cfg.enclosure),
        segment_length=float(rope_cfg.mesh.segment_length),
        radial_segments=int(rope_cfg.mesh.radial_segments),
    )


def spawn_centerline(ring: RingSpec, posts: dict[str, PostSpec]) -> np.ndarray:
    """Flat stadium hooked on the one post in `ring.enclosure`, task frame.

    Subsets of two or more posts are the variant axis (docx 2.7's "enclose a
    given subset" family) and are not generated yet: a loop around two posts is
    a different curve (two half-caps and two straights between them), and the
    spawn must not intersect either post.
    """

    if len(ring.enclosure) != 1:
        raise NotImplementedError(
            f"ring.enclosure={list(ring.enclosure)}: only a loop around ONE post is "
            "generated so far; multi-post spawns are the reserved variant axis."
        )
    post = posts[ring.enclosure[0]]
    peg = np.array([post.center[0], post.center[1], ring.tube_radius], dtype=float)
    along = np.array([ring.long_axis[0], ring.long_axis[1], 0.0], dtype=float)
    across = np.array([-ring.long_axis[1], ring.long_axis[0], 0.0], dtype=float)
    return pegged_band_centerline(
        perimeter=ring.perimeter,
        loop_radius=ring.loop_radius,
        peg_center=peg,
        long_axis=along,
        width_axis=across,
        half_turns=0.0,
        segment_length=ring.segment_length,
    )


def spawn_mesh(ring: RingSpec, centerline: np.ndarray):
    """Periodic tube on the spawn centerline at self-linking 0. Returns (frames, V, F)."""

    frames = closed_transport_frames(
        centerline,
        tube_radius=ring.tube_radius,
        self_linking_target=0,
        projection=TOPDOWN_PROJECTION,
    )
    vertices, faces = closed_tube_mesh(
        centerline, frames, radius=ring.tube_radius, radial_segments=ring.radial_segments
    )
    return frames, vertices, faces


def far_cap_point(centerline: np.ndarray, ring: RingSpec, post: PostSpec) -> np.ndarray:
    """The loop's far cap apex: the material the stretch phase grasps."""

    along = np.array([ring.long_axis[0], ring.long_axis[1], 0.0])
    peg = np.array([post.center[0], post.center[1], 0.0])
    return np.asarray(centerline[int(np.argmax((centerline - peg[None, :]) @ along))], dtype=float)


def near_cap_point(centerline: np.ndarray, ring: RingSpec, post: PostSpec) -> np.ndarray:
    """The cap apex around the spawn post: the material the lift-off phase grasps.

    During the swing the loop turns about the post and this cap stays around it;
    during the stretch it wraps the post's far side. So after the stretch this
    material sits at the post's outer surface, which is where the lift has to
    take hold to carry the loop over the top. The spike reads back where it
    actually ended up (`near_band_drift`) rather than assuming this.
    """

    along = np.array([ring.long_axis[0], ring.long_axis[1], 0.0])
    peg = np.array([post.center[0], post.center[1], 0.0])
    return np.asarray(centerline[int(np.argmin((centerline - peg[None, :]) @ along))], dtype=float)


def xy_distance_to_post(points: np.ndarray, post: PostSpec) -> np.ndarray:
    pts = np.atleast_2d(np.asarray(points, dtype=float))[:, :2]
    return np.linalg.norm(pts - post.center[None, :], axis=1)


def min_strand_separation(post: PostSpec, ring: RingSpec, contact_d_hat: float) -> float:
    """Room the two strands need so a post passes between them: 2 (r_post + 2 r_tube + d_hat)."""

    return 2.0 * (post.radius + 2.0 * ring.tube_radius + float(contact_d_hat))


def strand_separation_at(
    *,
    ring: RingSpec,
    anchor: PostSpec,
    landing_xy: np.ndarray,
    held_half_width: float,
    query_xy: np.ndarray,
) -> float:
    """Separation of the two taut strands where they pass `query_xy`.

    The strands run from the anchor post's tangent points (separation
    2*loop_radius) to the held cap (separation 2*held_half_width). Under tension
    they are straight, so the separation is linear in the distance along the
    pull direction. Points behind the anchor or beyond the landing read as the
    end values.
    """

    direction = np.asarray(landing_xy, dtype=float) - anchor.center
    length = float(np.linalg.norm(direction))
    if length <= 1e-9:
        raise ValueError("landing point coincides with the anchor post.")
    direction /= length
    fraction = float(np.clip(np.dot(np.asarray(query_xy, dtype=float) - anchor.center, direction) / length, 0.0, 1.0))
    return 2.0 * (ring.loop_radius + (held_half_width - ring.loop_radius) * fraction)


def held_half_width(ring: RingSpec, band_radius: float) -> float:
    """Half-width of the piece of cap the grasp band holds rigid.

    The band captures every vertex within `band_radius` of the cap apex. On a cap
    of radius `loop_radius` that is an arc whose chord half-width is exactly
    `band_radius` (the chord of a circle at distance r from a point on it), capped
    at the loop radius. Everything outside it straightens under tension.
    """

    return min(float(band_radius), ring.loop_radius)


def carry_height_floor(
    *,
    anchor: PostSpec,
    crossed: PostSpec,
    landing_xy: np.ndarray,
    tube_radius: float,
    margin: float,
) -> float:
    """Lowest held-cap height at which a taut strand clears `crossed`'s top.

    The strand is a straight line from the anchor's tangent point (on the table,
    z = tube radius) to the held cap. Where it crosses the other post's x it is at
    a fraction of the cap's height; that fraction is the post's distance along the
    pull direction over the landing distance. The cap must be high enough that
    the strand's underside is `margin` above the post top there.
    """

    direction = np.asarray(landing_xy, dtype=float) - anchor.center
    length = float(np.linalg.norm(direction))
    direction /= length
    fraction = float(np.dot(crossed.center - anchor.center, direction) / length)
    if fraction <= 0.0 or fraction >= 1.0:
        return 0.0
    needed_at_post = crossed.top_z + float(tube_radius) + float(margin)
    return float(tube_radius) + (needed_at_post - float(tube_radius)) / fraction


def stretched_length(
    *,
    ring: RingSpec,
    anchor: PostSpec,
    held_xyz: np.ndarray,
    held_half_width: float,
) -> float:
    """Perimeter the loop needs with its far cap held at `held_xyz` (task frame).

    Anchor half-cap + two straight strands + the held piece's chord. The strands
    run from the anchor's tangent points (table height) to the held piece's ends.
    """

    held = np.asarray(held_xyz, dtype=float)
    direction = held[:2] - anchor.center
    length = float(np.linalg.norm(direction))
    direction /= length
    across = np.array([-direction[1], direction[0]])
    wrap_radius = anchor.radius + ring.tube_radius
    strands = 0.0
    for side in (-1.0, 1.0):
        start = np.array(
            [*(anchor.center + side * wrap_radius * across), ring.tube_radius], dtype=float
        )
        end = np.array([*(held[:2] + side * held_half_width * across), held[2]], dtype=float)
        strands += float(np.linalg.norm(end - start))
    return float(np.pi * wrap_radius + strands + 2.0 * held_half_width)


def rest_length_around(posts: list[PostSpec], ring: RingSpec) -> float:
    """Perimeter of a loop lying taut around these posts (convex hull of the wrap circles).

    Two posts: two straights of the centre distance plus one full wrap circumference
    at r_post + r_tube (the two half-caps). Only the two-post case is needed now.
    """

    if len(posts) != 2:
        raise NotImplementedError("rest_length_around handles exactly two posts.")
    a, b = posts
    if abs(a.radius - b.radius) > 1e-9:
        raise NotImplementedError("rest_length_around assumes equal post radii.")
    wrap_radius = a.radius + ring.tube_radius
    return float(2.0 * np.linalg.norm(a.center - b.center) + 2.0 * np.pi * wrap_radius)


def far_cap_path(
    *,
    ring: RingSpec,
    anchor: PostSpec,
    target: PostSpec,
    spawn_line: np.ndarray,
    transfer_cfg,
) -> list[tuple[str, np.ndarray]]:
    """Held-cap waypoints for the stretch phase, task frame: (label, xyz) pairs.

    Four legs, all driven at the far cap and all read from `task.transfer`:
      swing   -- turn the loop about the anchor post at `swing_z`, keeping the
                 spawn reach, from the long axis through +y to `swing_end_deg`
                 measured from the anchor->target direction. The loop rotates on
                 the table; nothing stretches.
      rise    -- straight up to `carry_z` at the same xy.
      carry   -- straight to above the landing point (target's far side).
      descend -- straight down to table height at the landing point; the strands
                 come down on either side of the target.
    The planner emits exactly this list; the offline gate samples it and checks
    every leg's strands against the target post.
    """

    reach = loop_reach(spawn_line, ring, anchor)
    to_target = target.center - anchor.center
    heading = float(np.arctan2(to_target[1], to_target[0]))
    start = float(np.arctan2(ring.long_axis[1], ring.long_axis[0]))
    end = heading + np.radians(float(transfer_cfg.swing_end_deg))
    # Go the way that passes through +y (the side the long axis is not on).
    while end <= start:
        end += 2.0 * np.pi
    if end - start > np.pi:
        end -= 2.0 * np.pi
    swing_z = float(transfer_cfg.swing_z)
    count = int(transfer_cfg.swing_waypoints)
    path: list[tuple[str, np.ndarray]] = []
    for index in range(count + 1):
        angle = start + (end - start) * index / count
        xy = anchor.center + reach * np.array([np.cos(angle), np.sin(angle)])
        path.append((f"swing{index}", np.array([xy[0], xy[1], swing_z])))
    carry_z = float(transfer_cfg.carry_z)
    last_xy = path[-1][1][:2]
    path.append(("rise", np.array([last_xy[0], last_xy[1], carry_z])))
    landing = landing_point(ring=ring, anchor=anchor, target=target, transfer_cfg=transfer_cfg)
    path.append(("carry", np.array([landing[0], landing[1], carry_z])))
    path.append(("descend", np.array([landing[0], landing[1], ring.tube_radius])))
    return path


def landing_point(*, ring: RingSpec, anchor: PostSpec, target: PostSpec, transfer_cfg) -> np.ndarray:
    """Where the far cap is put down: on the target's far side, along anchor->target."""

    direction = target.center - anchor.center
    direction = direction / float(np.linalg.norm(direction))
    offset = target.radius + ring.tube_radius + float(transfer_cfg.landing_clearance)
    return target.center + offset * direction


def strand_segments(
    *,
    ring: RingSpec,
    anchor: PostSpec,
    held_xyz: np.ndarray,
    held_half_width: float,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """The two taut strands as 3D segments: anchor tangent point -> held piece end."""

    held = np.asarray(held_xyz, dtype=float)
    direction = held[:2] - anchor.center
    direction = direction / float(np.linalg.norm(direction))
    across = np.array([-direction[1], direction[0]])
    wrap_radius = anchor.radius + ring.tube_radius
    segments = []
    for side in (-1.0, 1.0):
        start = np.array([*(anchor.center + side * wrap_radius * across), ring.tube_radius])
        end = np.array([*(held[:2] + side * held_half_width * across), held[2]])
        segments.append((start, end))
    return segments


def segment_distance(p0: np.ndarray, p1: np.ndarray, q0: np.ndarray, q1: np.ndarray) -> float:
    """Closest approach of two 3D segments (sampled; 1 mm resolution is plenty here)."""

    p0, p1, q0, q1 = (np.asarray(v, dtype=float) for v in (p0, p1, q0, q1))
    steps_p = max(2, int(np.ceil(np.linalg.norm(p1 - p0) / 0.001)) + 1)
    steps_q = max(2, int(np.ceil(np.linalg.norm(q1 - q0) / 0.001)) + 1)
    ps = p0[None, :] + np.linspace(0.0, 1.0, steps_p)[:, None] * (p1 - p0)[None, :]
    qs = q0[None, :] + np.linspace(0.0, 1.0, steps_q)[:, None] * (q1 - q0)[None, :]
    return float(np.min(np.linalg.norm(ps[:, None, :] - qs[None, :, :], axis=2)))


def post_axis_segment(post: PostSpec) -> tuple[np.ndarray, np.ndarray]:
    return (
        np.array([post.center[0], post.center[1], 0.0]),
        np.array([post.center[0], post.center[1], post.top_z]),
    )


def loop_reach(centerline: np.ndarray, ring: RingSpec, post: PostSpec) -> float:
    along = np.array([ring.long_axis[0], ring.long_axis[1], 0.0])
    return band_reach(centerline, np.array([post.center[0], post.center[1], 0.0]), along)


def loop_perimeter(centerline: np.ndarray) -> float:
    return closed_arc_length(centerline)[1]


__all__ = [
    "PostSpec",
    "RingSpec",
    "carry_height_floor",
    "far_cap_path",
    "far_cap_point",
    "held_half_width",
    "landing_point",
    "loop_perimeter",
    "loop_reach",
    "min_strand_separation",
    "near_cap_point",
    "post_axis_segment",
    "posts_from_config",
    "rest_length_around",
    "ring_from_config",
    "segment_distance",
    "spawn_centerline",
    "spawn_mesh",
    "strand_segments",
    "strand_separation_at",
    "stretched_length",
    "xy_distance_to_post",
]
