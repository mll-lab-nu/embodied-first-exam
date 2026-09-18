"""Layout budget for `ring_transfer` (docx 2.6): posts, the closed loop, and what
the one-gripper oracle needs from them.

Pure numpy on top of `topogym.world.closed_band`. Nothing here touches a solver;
`tests/check_ring_transfer_geometry.py` runs every inequality below without a
GPU, and `RingTransferLayout` calls the same functions so the scene and the gate
cannot disagree.

Frame: task coordinates (origin at the table centre, z=0 on the tabletop). The
loop lies flat; it spawns one tube radius plus `contact_d_hat` + 1 mm above the
table (outside the barrier) and settles onto it -- derived, never configured.

The numbers that decide whether the task can be done with ONE gripper come from
the stretch phase, and they are worth stating once because they are not obvious.

A loop pulled from a single pinched point is a doubled strand: under tension it
collapses to the anchor post's wrap width, 2 (r_post + r_tube) = 28 mm here, and
a closed curve made of two coincident strands winds around nothing but the
anchor. Pinching the far cap therefore cannot get post B inside the loop --
measured by this module's first version, the strands passed B 12.5 mm from its
axis against the 14 mm of shaft plus tube. What does work, and is how a person
does it, is to HOOK the loop over both open fingers: the fingers go inside the
cap, the gripper opens to `grasp.spread`, and the cap is carried held open that
wide. The loop then forms a trapezoid from the anchor wrap (28 mm) to the held
piece (`spread`), and B enters where the strands are further apart than B's
diameter plus two tubes plus the barrier. `strand_separation_at` evaluates that
line where it passes B; `min_strand_separation` is what it has to clear. Two
follow bands, one per finger, model the hook.

Why the posts have collision HEADS: the stretch pulls the anchor wrap upward at
about 40 degrees (the held cap must clear B's head from 0.176 m away), and a
wrap held only by friction slides up the shaft once tan(angle) exceeds mu
(0.3, i.e. 17 degrees). Measured 2026-08-24 on a headless post: the loop left
A's top at carry step ~60 and never enclosed anything. A head wider than the
tube retains the wrap, as a real peg's head does, and the gateway becomes the
head's top instead of the shaft's.

The carry over B happens at a height where each strand -- a straight line from
the anchor's tangent point on the table up to its held end -- clears B's top
where it crosses B. The strands are only straight while the loop is taut, so the
gate also checks the loop is stretched (ratio >= 1) throughout the carry;
`carry_height_floor` gives the height for a landing point and the oracle's
`carry_z` must be at or above it.
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


# ---- variation: the Layout rules that replace hand-written leaves ------------
# Each constant restores the 2026-08-25/26 baseline exactly (see the task yaml's
# `carry` comments for the measurements behind the original numbers).
#
# lift_low_z = anchor head top + this: the fingertips pass over the head with the
# loop's bottom still on the table (baseline 0.108 + 0.012 = 0.120).
LIFT_LOW_ABOVE_HEAD = 0.012
# hang_bottom_z = post base height + this: the hanging U meets the shaft between
# the base cone and the head underside (baseline 0.016 + 0.024 = 0.040).
HANG_BOTTOM_ABOVE_BASE = 0.024
# drop_z = max(hang_bottom_z, target head top + this - palm_bottom_above_tip): the
# palm box, which covers the target at the drop, stays above its head
# (baseline max(0.040, 0.108 + 0.009 - 0.077) = 0.040).
DROP_PALM_MARGIN = 0.009
# pinch_along = anchor head radius + hand_half_thickness + this, capped at the
# straight's length: the palm box beside the anchor clears its head
# (baseline 0.026 + 0.030 + 0.014 = 0.070).
PINCH_HEAD_GAP = 0.014
# Layout rows: the spawn loop keeps this off the target's head; the hanging U
# sits at least this far from the base cone and the head underside; every hand
# position and the spawn loop keep this inside `workspace`.
TARGET_SPAWN_CLEARANCE = 0.020
SHAFT_MARGIN = 0.015
WORKSPACE_MARGIN = 0.020


@dataclass(frozen=True)
class PostSpec:
    name: str
    center: np.ndarray  # task-frame xy
    radius: float  # shaft: the wrap radius
    height: float  # shaft height
    head_radius: float  # retaining head on top, a collision body
    head_height: float

    @property
    def top_z(self) -> float:
        """Top of the head: what the loop has to clear to leave or land."""

        return float(self.height) + float(self.head_height)


@dataclass(frozen=True)
class RingSpec:
    perimeter: float
    loop_radius: float
    tube_radius: float
    long_axis: np.ndarray  # unit xy direction the loop extends in from its post
    enclosure: tuple[str, ...]  # posts the loop is spawned around
    segment_length: float
    radial_segments: int
    spawn_clearance: float  # skin-to-table gap at spawn: contact_d_hat + margin


def posts_from_config(posts_cfg, shape_cfg, *, centers: dict | None = None) -> dict[str, PostSpec]:
    """`task.posts` maps name -> {x, y, colours}; `task.post_shape` is the one
    shaft / head geometry both posts share (the loop's rest length around two
    posts assumes equal radii, and the variation axes move both together).
    `centers` overrides the yaml positions (name -> xy)."""

    posts: dict[str, PostSpec] = {}
    radius = float(shape_cfg.radius)
    head_radius = radius + float(shape_cfg.head_overhang)
    if float(shape_cfg.head_overhang) < 0.0:
        raise ValueError("post_shape.head_overhang must not be negative: the head retains the loop.")
    for name, item in posts_cfg.items():
        name = str(name)
        center = centers[name] if centers is not None else (float(item.x), float(item.y))
        posts[name] = PostSpec(
            name=name,
            center=np.array([float(center[0]), float(center[1])], dtype=float),
            radius=radius,
            height=float(shape_cfg.height),
            head_radius=head_radius,
            head_height=float(shape_cfg.head_height),
        )
    if len(posts) != 2:
        raise ValueError("ring_transfer needs exactly two posts (A and B).")
    return posts


def ring_from_config(ring_cfg, rope_cfg, *, long_axis, on_post: str) -> RingSpec:
    """`long_axis` and `on_post` come from the Layout (derived from the post pair),
    not from the yaml."""

    axis = np.asarray(long_axis, dtype=float)[:2]
    norm = float(np.linalg.norm(axis))
    if norm <= 1e-9:
        raise ValueError("ring long_axis must be a non-zero xy direction.")
    return RingSpec(
        perimeter=float(ring_cfg.perimeter),
        loop_radius=float(ring_cfg.loop_radius),
        tube_radius=float(rope_cfg.radius),
        long_axis=axis / norm,
        enclosure=(str(on_post),),
        segment_length=float(rope_cfg.mesh.segment_length),
        radial_segments=int(rope_cfg.mesh.radial_segments),
        spawn_clearance=float(rope_cfg.fem.contact_d_hat) + 0.001,
    )


# ---- the post pair and what the Layout derives from it ------------------------


def pair_heading(pair_cfg) -> np.ndarray:
    """Unit xy direction from post A to post B: `pair.heading_deg` from +x."""

    theta = np.radians(float(pair_cfg.heading_deg))
    return np.array([np.cos(theta), np.sin(theta)], dtype=float)


def pair_centers(pair_cfg, mid_xy=None) -> dict[str, np.ndarray]:
    """A and B from the pair's midpoint, spacing and heading. `mid_xy` overrides
    `pair.mid_x / mid_y` (the derivation evaluates the pair at the origin first)."""

    heading = pair_heading(pair_cfg)
    if mid_xy is None:
        mid_xy = (float(pair_cfg.mid_x), float(pair_cfg.mid_y))
    mid = np.asarray(mid_xy, dtype=float)[:2]
    half = 0.5 * float(pair_cfg.spacing)
    if half <= 0.0:
        raise ValueError("pair.spacing must be positive.")
    return {"A": mid - half * heading, "B": mid + half * heading}


def long_axis_from_heading(pair_cfg) -> np.ndarray:
    """The loop extends from its post perpendicular to the pair, on the pair's
    -y side when the heading is 0 (the 2026-08-25 layout: `[0, -1]`). Rotates
    with the pair, so the whole scene turns together."""

    heading = pair_heading(pair_cfg)
    return np.array([heading[1], -heading[0]], dtype=float)


def other_post(name: str) -> str:
    if name not in ("A", "B"):
        raise ValueError(f"ring_transfer posts are A and B, got {name!r}.")
    return "B" if name == "A" else "A"


def pinch_side_for(ring: RingSpec, anchor: PostSpec, target: PostSpec) -> float:
    """Which straight the carry pinches: the one AWAY from the target, so the hand
    is never between the posts (baseline -1 for A->B along +x)."""

    across = np.array([-ring.long_axis[1], ring.long_axis[0]])
    return -float(np.sign(np.dot(across, target.center - anchor.center)))


def straight_length(ring: RingSpec) -> float:
    """Length of each straight of the flat stadium: (perimeter - 2 pi loop_radius) / 2."""

    return 0.5 * (ring.perimeter - 2.0 * np.pi * ring.loop_radius)


def pinch_along_for(ring: RingSpec, anchor: PostSpec, physical_cfg) -> float:
    """How far down the straight the carry pinches: far enough that the palm box
    (half thickness along the straight) clears the anchor's head by
    `PINCH_HEAD_GAP`, but not past the straight onto the far cap."""

    want = anchor.head_radius + float(physical_cfg.hand_half_thickness) + PINCH_HEAD_GAP
    return float(min(straight_length(ring), want))


def carry_heights(*, anchor: PostSpec, target: PostSpec, base_height: float, physical_cfg) -> dict[str, float]:
    """The three fingertip heights of the carry that follow the posts (module constants)."""

    hang_bottom_z = float(base_height) + HANG_BOTTOM_ABOVE_BASE
    return {
        "lift_low_z": anchor.top_z + LIFT_LOW_ABOVE_HEAD,
        "hang_bottom_z": hang_bottom_z,
        "drop_z": max(hang_bottom_z, target.top_z + DROP_PALM_MARGIN - float(physical_cfg.palm_bottom_above_tip)),
    }


def mid_y_window(points_xy: np.ndarray, *, workspace_y, y_range) -> tuple[float, float]:
    """Interval of pair midpoints (y) that keeps every point of the mid = 0 layout
    inside the workspace by `WORKSPACE_MARGIN`, intersected with `y_range`."""

    pts = np.asarray(points_xy, dtype=float)[:, :2]
    lo = max(float(workspace_y[0]) + WORKSPACE_MARGIN - float(pts[:, 1].min()), float(y_range[0]))
    hi = min(float(workspace_y[1]) - WORKSPACE_MARGIN - float(pts[:, 1].max()), float(y_range[1]))
    return lo, hi


def mid_x_window(
    points_xy: np.ndarray, hands_xy: np.ndarray, *, mid_y: float, workspace_x, x_range, base_xy, max_hand_dist
) -> tuple[float, float]:
    """Interval of pair midpoints (x) for the mid = (0, mid_y) layout: the
    workspace bound on every point, and the reach disc on every hand position
    (`|hand - base| <= max_hand_dist`, solved for x at the hand's own y)."""

    pts = np.asarray(points_xy, dtype=float)[:, :2]
    lo = max(float(workspace_x[0]) + WORKSPACE_MARGIN - float(pts[:, 0].min()), float(x_range[0]))
    hi = min(float(workspace_x[1]) - WORKSPACE_MARGIN - float(pts[:, 0].max()), float(x_range[1]))
    base = np.asarray(base_xy, dtype=float)[:2]
    reach = float(max_hand_dist)
    for hand in np.asarray(hands_xy, dtype=float)[:, :2]:
        dy = hand[1] + float(mid_y) - base[1]
        if abs(dy) >= reach:
            return lo, lo - 1.0
        hi = min(hi, base[0] - hand[0] + float(np.sqrt(reach * reach - dy * dy)))
    return lo, hi


def value_from_frac(window: tuple[float, float], frac: float, *, what: str) -> float:
    lo, hi = window
    if hi < lo:
        raise ValueError(f"ring_transfer: {what} has no feasible value (window [{lo:+.4f}, {hi:+.4f}] is empty).")
    return float(lo + float(frac) * (hi - lo))


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
    # Spawn just OUTSIDE the contact barrier, not resting on the table: a tube
    # whose skin starts within `contact_d_hat` of the table is inside the barrier
    # at step 0 and gets shoved upward on the first solve (read as a visible hop;
    # settle logs showed the centerline rising from 4.0 to 6.4 mm). From here it
    # drops the last millimetres under gravity instead.
    peg = np.array([post.center[0], post.center[1], ring.tube_radius + ring.spawn_clearance], dtype=float)
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


def pinch_point(centerline: np.ndarray, ring: RingSpec, post: PostSpec, *, along: float, side: float) -> np.ndarray:
    """Where the carry oracle pinches: on one of the loop's STRAIGHTS, `along` metres
    from the spawn post down the long axis, on the `side` (+1/-1 across) straight.

    Not the cap apex: pinching a cap means closing the fingers along the radial
    direction, and the Franka hand -- ~200 mm long along its closing axis, palm
    bottom 77 mm above the fingertips, i.e. below a 93 mm head -- then sits on
    top of the post (measured 2026-08-25). On a straight the closing axis is
    across the loop's long axis and the hand lies alongside the post, offset by
    `along`; `hand_clearance` checks the palm box against every head.
    """

    long = np.array([ring.long_axis[0], ring.long_axis[1], 0.0])
    across = np.array([-ring.long_axis[1], ring.long_axis[0], 0.0])
    peg = np.array([post.center[0], post.center[1], 0.0])
    target = peg + float(along) * long + float(side) * ring.loop_radius * across
    return np.asarray(centerline[int(np.argmin(np.linalg.norm(centerline - target[None, :], axis=1)))], dtype=float)


def hand_clearance(*, fingertip_xy, close_axis, fingertip_z: float, posts, physical_cfg) -> dict[str, float]:
    """Smallest gap between the hand's palm box and each post's head, metres
    (negative = overlap). The box is `hand_half_length` along the closing axis,
    `hand_half_thickness` across it, and its bottom is `palm_bottom_above_tip`
    above the fingertips; a head only matters where the box bottom is below its
    top."""

    tip = np.asarray(fingertip_xy, dtype=float)[:2]
    axis = np.asarray(close_axis, dtype=float)[:2]
    axis = axis / float(np.linalg.norm(axis))
    normal = np.array([-axis[1], axis[0]])
    half_len = float(physical_cfg.hand_half_length)
    half_thick = float(physical_cfg.hand_half_thickness)
    bottom = float(fingertip_z) + float(physical_cfg.palm_bottom_above_tip)
    out = {}
    for name, post in posts.items():
        if bottom >= post.top_z:
            out[name] = float("inf")
            continue
        rel = post.center - tip
        # Distance from the head disc to the box in the box's own frame.
        du = max(abs(float(np.dot(rel, axis))) - half_len, 0.0)
        dv = max(abs(float(np.dot(rel, normal))) - half_thick, 0.0)
        out[name] = float(np.hypot(du, dv)) - post.head_radius
    return out


def strand_tangent(centerline: np.ndarray, point) -> np.ndarray:
    """Unit xy tangent of the loop at the sample nearest `point` (central difference)."""

    pts = np.asarray(centerline, dtype=float)
    index = int(np.argmin(np.linalg.norm(pts[:, :2] - np.asarray(point, dtype=float)[None, :2], axis=1)))
    tangent = pts[(index + 1) % len(pts), :2] - pts[index - 1, :2]
    return tangent / float(np.linalg.norm(tangent))


def hang_depth(ring: RingSpec, carry_cfg) -> float:
    """How far below the fingertips a PINCHED loop hangs.

    `carry.hang_depth` when the spike has measured it; otherwise the pessimistic
    estimate: half the material outside the clamped segment, i.e. the two
    strands hanging straight down side by side. The real loop hangs shorter --
    the clamp holds a `clamp_width` piece straight and the rope leaves it
    horizontally before bending down over a length (EI/w)^(1/3) ~ 40 mm, which
    is also what keeps the hanging loop open (`u_width` in the spike).
    """

    measured = getattr(carry_cfg, "hang_depth", None)
    if measured is not None:
        return float(measured)
    return 0.5 * (ring.perimeter - 2.0 * float(carry_cfg.clamp_width))


def carry_path(
    *,
    ring: RingSpec,
    anchor: PostSpec,
    target: PostSpec,
    start_xy,
    carry_cfg,
    lift_low_z: float,
    hang_bottom_z: float,
    drop_z: float,
) -> list[tuple[str, np.ndarray]]:
    """Held-point waypoints (task frame) for the carry oracle: PINCH the loop on a
    straight, take it off the anchor from directly above, carry it hanging, lasso
    the target from the side, put it down.

    Heights are FINGERTIP heights; the loop's bottom U hangs `hang_depth` below.
    `lift_low_z`, `hang_bottom_z`, `drop_z` come from `carry_heights` (they
    follow the posts); `clear` is derived here from the anchor's head.
      lift_low    -- a few cm straight up; the rest of the loop stays on the
                     table, so nothing is under tension.
      over_anchor -- horizontally to above the anchor's axis, and `unhook_past`
                     beyond it on the side away from the pinch. The loop slides
                     loosely on the table around the shaft.
      clear       -- straight up until the bottom U is `clear_margin` above the
                     anchor's head. Pulled from above, the strands pass over the
                     head's rim and the U (106-130 mm wide, measured) clears the
                     52 mm head. Pulling from the SIDE instead wraps the loop
                     round the shaft and jams it under the head lip: measured
                     2026-08-25 (inspect_lift), the far strand climbed to 106 mm
                     (lip 100-108) and stayed, the loop stretched 56 % and the
                     arm was dragged 142 mm off its command.
      travel      -- at that height to above the approach point.
      approach    -- down until the bottom U is `hang_bottom_z` above the table
                     (below the target's head, above its base cone).
      push        -- past the target by `push_past`: the bottom U meets the shaft,
                     the two strands part around it, the hand ends on the far side.
      lower       -- down to `drop_z`, still on the far side; the loop lands around
                     the target.
    """

    start = np.asarray(start_xy, dtype=float)[:2]
    depth = hang_depth(ring, carry_cfg)
    finger_z = float(hang_bottom_z) + depth
    clear_z = anchor.top_z + ring.tube_radius + float(carry_cfg.clear_margin) + depth
    low_z = float(lift_low_z)
    direction = target.center - anchor.center
    direction = direction / float(np.linalg.norm(direction))
    toward_anchor = anchor.center - start
    toward_anchor = toward_anchor / float(np.linalg.norm(toward_anchor))
    over = anchor.center + float(carry_cfg.unhook_past) * toward_anchor
    approach = target.center - (target.radius + ring.tube_radius + float(carry_cfg.approach_before)) * direction
    landing = target.center + float(carry_cfg.push_past) * direction
    return [
        ("start", np.array([start[0], start[1], ring.tube_radius])),
        ("lift_low", np.array([start[0], start[1], low_z])),
        ("over_anchor", np.array([over[0], over[1], low_z])),
        ("clear", np.array([over[0], over[1], clear_z])),
        ("travel", np.array([approach[0], approach[1], clear_z])),
        ("approach", np.array([approach[0], approach[1], finger_z])),
        ("push", np.array([landing[0], landing[1], finger_z])),
        ("lower", np.array([landing[0], landing[1], float(drop_z)])),
    ]


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
    2 (r_post + r_tube), the wrap the loop collapses to under tension) to the
    held piece (separation 2*held_half_width). Under tension they are straight,
    so the separation is linear in the distance along the pull direction. Points
    behind the anchor or beyond the landing read as the end values.
    """

    direction = np.asarray(landing_xy, dtype=float) - anchor.center
    length = float(np.linalg.norm(direction))
    if length <= 1e-9:
        raise ValueError("landing point coincides with the anchor post.")
    direction /= length
    fraction = float(np.clip(np.dot(np.asarray(query_xy, dtype=float) - anchor.center, direction) / length, 0.0, 1.0))
    wrap_half = anchor.radius + ring.tube_radius
    return 2.0 * (wrap_half + (held_half_width - wrap_half) * fraction)


def hook_points(centerline: np.ndarray, ring: RingSpec, post: PostSpec, spread: float) -> tuple[np.ndarray, np.ndarray]:
    """Where the two fingers hook the far cap: the cap's samples nearest to the
    apex offset by +-spread/2 across the long axis. One follow band each."""

    along = np.array([ring.long_axis[0], ring.long_axis[1], 0.0])
    across = np.array([-ring.long_axis[1], ring.long_axis[0], 0.0])
    peg = np.array([post.center[0], post.center[1], 0.0])
    reach = float(np.max((centerline - peg[None, :]) @ along))
    cap_centre = peg + (reach - ring.loop_radius) * along
    half = 0.5 * float(spread)
    if half >= ring.loop_radius:
        raise ValueError(
            f"grasp.spread/2 = {half:.4f} m must be less than loop_radius {ring.loop_radius:.4f} m: "
            "the fingers hook the cap, they cannot be wider than it."
        )
    forward = float(np.sqrt(ring.loop_radius**2 - half**2))
    points = []
    for side in (1.0, -1.0):
        target = cap_centre + forward * along + side * half * across
        points.append(np.asarray(centerline[int(np.argmin(np.linalg.norm(centerline - target[None, :], axis=1)))], dtype=float))
    return points[0], points[1]


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


# ---- the carry oracle's feasibility rows ---------------------------------------


def carry_hand_positions(path, hand_above: float) -> np.ndarray:
    """Hand (wrist) positions for the carry waypoints after `start`: fingertip + `hand_above` in z."""

    return np.array([[p[0], p[1], p[2] + float(hand_above)] for _, p in path[1:]], dtype=float)


def ring_transfer_checks(layout) -> list[tuple[str, float, float, bool]]:
    """``[(name, measured, limit, ok)]``: what a spawnable, carry-solvable layout needs.

    One list for the randomizer's reject step, the offline gate, the corner
    harness and the demo's start-up print. Takes a `RingTransferLayout` (or the
    gate's stand-in): `ring`, `posts`, `anchor`, `target`, `spawn`,
    `pinch_point()`, `carry_path()`, `hang_bottom_z`, `task_cfg`. Metres.

    The transfer route's rows (stretch trapezoid, far-cap path) are NOT here:
    that route is unavailable at the baseline spacing and the offline gate only
    reports it.
    """

    cfg = layout.task_cfg
    ring, anchor, target, spawn = layout.ring, layout.anchor, layout.target, layout.spawn
    physical, carry_cfg = cfg.physical, cfg.carry
    d_hat = float(cfg.rope.fem.contact_d_hat)
    base_height = float(cfg.post_shape.base_height)
    depth = hang_depth(ring, carry_cfg)
    pinch = layout.pinch_point()
    path = layout.carry_path(start_xy=pinch[:2])
    by_label = dict(path)
    tangent = strand_tangent(spawn, pinch)
    close_axis = np.array([-tangent[1], tangent[0]])
    workspace = cfg.workspace
    ws_x = [float(v) for v in workspace.x]
    ws_y = [float(v) for v in workspace.y]
    ws_z_max = float(workspace.z[1])

    def palm_gap(label_xy, fingertip_z):
        gaps = hand_clearance(
            fingertip_xy=label_xy, close_axis=close_axis, fingertip_z=fingertip_z, posts=layout.posts, physical_cfg=physical
        )
        return float(min(gaps.values()))

    # Hanging strands (hand +- hang_half_width across the heading) vs the anchor's
    # head, on the legs where the loop is below the head top and away from it.
    heading = target.center - anchor.center
    heading = heading / float(np.linalg.norm(heading))
    across = np.array([-heading[1], heading[0]])
    strands_clear = float("inf")
    for label, point in path:
        if label in ("start", "lift_low", "over_anchor", "clear") or point[2] - depth >= anchor.top_z:
            continue
        for side in (-1.0, 1.0):
            offset = point[:2] + side * float(carry_cfg.hang_half_width) * across
            strands_clear = min(
                strands_clear, float(np.linalg.norm(offset - anchor.center)) - anchor.head_radius - ring.tube_radius
            )
    hands = carry_hand_positions(path, float(physical.hand_above))
    in_workspace = min(
        float(np.min(hands[:, 0] - ws_x[0])),
        float(np.min(ws_x[1] - hands[:, 0])),
        float(np.min(hands[:, 1] - ws_y[0])),
        float(np.min(ws_y[1] - hands[:, 1])),
        float(np.min(ws_z_max - hands[:, 2])),
    )
    spawn_in_workspace = min(
        float(np.min(spawn[:, 0] - ws_x[0])),
        float(np.min(ws_x[1] - spawn[:, 0])),
        float(np.min(spawn[:, 1] - ws_y[0])),
        float(np.min(ws_y[1] - spawn[:, 1])),
    )
    hang_bottom_z = float(layout.hang_bottom_z)
    ge = [
        ("loop_clears_post", ring.loop_radius - (anchor.radius + ring.tube_radius + d_hat), 0.0),
        (
            "spawn_clears_target",
            float(np.min(xy_distance_to_post(spawn, target))) - target.head_radius - ring.tube_radius,
            TARGET_SPAWN_CLEARANCE,
        ),
        ("head_overhang", anchor.head_radius - anchor.radius, 2.0 * ring.tube_radius),
        ("pinch_on_straight", straight_length(ring) - float(layout.pinch_along), 0.0),
        ("palm_clears_heads_at_grasp", palm_gap(pinch[:2], ring.tube_radius + float(cfg.grasp.pinch_lift)), 0.0),
        ("palm_clears_heads_over_anchor", palm_gap(by_label["over_anchor"][:2], by_label["over_anchor"][2]), 0.0),
        ("palm_clears_heads_at_drop", palm_gap(by_label["lower"][:2], by_label["lower"][2]), 0.0),
        ("fingertips_over_anchor_head", by_label["over_anchor"][2] - anchor.top_z, 0.0),
        ("lift_low_below_hang", depth - by_label["lift_low"][2], 0.0),
        ("hang_bottom_on_shaft", min(hang_bottom_z - base_height, target.height - hang_bottom_z), SHAFT_MARGIN),
        ("u_width_fits_target", 2.0 * float(carry_cfg.hang_half_width) - min_strand_separation(target, ring, d_hat), 0.0),
        ("hanging_strands_clear_anchor_head", strands_clear, 0.0),
        ("carry_in_workspace", in_workspace, WORKSPACE_MARGIN),
        ("spawn_in_workspace", spawn_in_workspace, WORKSPACE_MARGIN),
    ]
    rows = [(name, float(value), float(limit), bool(value >= limit - 1e-9)) for name, value, limit in ge]
    base_xy = np.asarray([float(v) for v in cfg.reach.base_xy], dtype=float)
    reach = float(np.max(np.linalg.norm(hands[:, :2] - base_xy[None, :], axis=1)))
    max_reach = float(cfg.reach.max_hand_dist)
    rows.append(("hand_reach", reach, max_reach, bool(reach <= max_reach + 1e-9)))
    return rows


__all__ = [
    "DROP_PALM_MARGIN",
    "HANG_BOTTOM_ABOVE_BASE",
    "LIFT_LOW_ABOVE_HEAD",
    "PINCH_HEAD_GAP",
    "PostSpec",
    "RingSpec",
    "carry_hand_positions",
    "carry_heights",
    "carry_height_floor",
    "carry_path",
    "hang_depth",
    "strand_tangent",
    "far_cap_path",
    "far_cap_point",
    "hook_points",
    "landing_point",
    "long_axis_from_heading",
    "loop_perimeter",
    "loop_reach",
    "mid_x_window",
    "mid_y_window",
    "min_strand_separation",
    "near_cap_point",
    "other_post",
    "hand_clearance",
    "pair_centers",
    "pair_heading",
    "pinch_along_for",
    "pinch_point",
    "pinch_side_for",
    "post_axis_segment",
    "posts_from_config",
    "rest_length_around",
    "ring_from_config",
    "ring_transfer_checks",
    "segment_distance",
    "spawn_centerline",
    "spawn_mesh",
    "straight_length",
    "strand_segments",
    "strand_separation_at",
    "stretched_length",
    "value_from_frac",
    "xy_distance_to_post",
]
