"""Ground truth for Rope Winding: the signed winding number around the post.

The sign convention and the post geometry come from the planner
(`planning/rope_winding_planner.py`) rather than being restated here, so the
oracle and the criterion cannot disagree about which way a positive turn goes --
the task's contrast pair is exactly +turns vs -turns for the mirrored
trajectory. Supervision already depends on planning (see `cable_routing.py`),
so this is the direction the dependency has to run.

Recovering the winding number needs an ORDERED centerline, and a FEM rope is an
unordered tet mesh (tetgen adds interior points and does not preserve the tube's
vertex order). `material_bins` solves that once per scene by projecting the
SPAWN node positions onto the spawn centerline -- each node gets the arc length
it sits at along the rope -- and grouping nodes into bins of equal arc length.
Those groups are material, so averaging each group's CURRENT positions gives an
ordered centerline no matter how the rope has moved.
"""

from __future__ import annotations

import numpy as np

from topogym.planning.rope_winding_planner import WindingSpec, post_center, post_top_z
from topogym.primitives.pick_place import HAND_TO_PAD_Z
from .cable_routing import rope_particles, tensor_to_numpy


_MATERIAL_COORDS: dict[str, np.ndarray] = {}


def material_coords(scene) -> np.ndarray:
    """Per-node spawn material coordinates: ``(arc_length, n_offset, b_offset)``.

    Cached per entity because the projection runs every node against every
    centerline segment, and both consumers here need it -- the arc length for
    binning, the cross-section offsets for the twist measure.
    """

    from topogym.world.rope import tube_material_coords

    entity = scene.rope_handle.entity
    key = str(entity.uid)
    cached = _MATERIAL_COORDS.get(key)
    if cached is not None:
        return cached
    spawn = getattr(entity, "init_positions", None)
    if spawn is None:
        raise RuntimeError(
            "winding supervision needs the rope's spawn node positions "
            "(entity.init_positions); the FEM backend provides them."
        )
    spawn = tensor_to_numpy(spawn)
    if spawn.ndim == 3:
        spawn = spawn[0]
    centerline = scene.layout.rope_mesh(scene.route_mode).centerline
    coords = tube_material_coords(np.asarray(spawn, dtype=float), centerline)
    _MATERIAL_COORDS[key] = coords
    return coords


def material_bins(scene, *, bins: int) -> list[np.ndarray]:
    """Group rope nodes into ``bins`` groups of equal spawn arc length.

    Call once per scene: the projection is over every node against every
    centerline segment. The result is valid for the whole episode because the
    grouping is material, not positional.
    """

    arc = material_coords(scene)[:, 0]
    edges = np.linspace(0.0, float(arc.max()), int(bins) + 1)
    # `digitize` puts the far endpoint in an extra bin; fold it back.
    index = np.clip(np.digitize(arc, edges[1:-1]), 0, int(bins) - 1)
    groups = [np.flatnonzero(index == i) for i in range(int(bins))]
    return [group for group in groups if len(group)]


def winding_centerline(scene, groups: list[np.ndarray]) -> np.ndarray:
    """Ordered centerline: each material group's current mean position."""

    nodes = rope_particles(scene)
    return np.stack([nodes[group].mean(axis=0) for group in groups], axis=0)


def wrapped_span(centerline: np.ndarray, post_xy, wrap_band: float) -> np.ndarray:
    """The stretch of rope that is on the post: first contact to last.

    Everything outside it is a free tail -- the run-in from the anchor and the
    run-out to the target zone -- and a tail's azimuth is not winding. Returned
    as a contiguous span rather than a mask because the rope may leave the band
    briefly mid-wrap, and that excursion is still part of the wrap.
    """

    centerline = np.asarray(centerline, dtype=float)
    post_xy = np.asarray(post_xy, dtype=float)[:2]
    radial = np.linalg.norm(centerline[:, :2] - post_xy[None, :], axis=1)
    on_post = np.flatnonzero(radial <= float(wrap_band))
    if on_post.size < 2:
        return centerline[:0]
    return centerline[on_post[0] : on_post[-1] + 1]


def winding_sweep(centerline: np.ndarray, post_xy, wrap_band: float) -> float:
    """Unwrapped azimuth swept by the rope ON THE POST, in turns.

    The continuous quantity `winding_number` rounds. Worth reporting on its own
    because the rounding boundary is where the criterion breaks. Measured over
    the whole rope -- as this did until 2026-08-13 -- the route's sweep is the
    wrap count PLUS whatever the run-in and run-out contribute, and that overhead
    was 0.674 turn: past 2.5, so a two-turn wrap read as three. Restricted to the
    wrapped span the overhead is only the entry-to-exit bearing difference, which
    is bounded by half a turn by construction, so the rounding cannot tip.
    """

    span = wrapped_span(centerline, post_xy, wrap_band)
    if len(span) < 2:
        return 0.0
    post_xy = np.asarray(post_xy, dtype=float)[:2]
    angles = np.unwrap(
        np.arctan2(span[:, 1] - post_xy[1], span[:, 0] - post_xy[0])
    )
    return float(angles[-1] - angles[0]) / (2.0 * np.pi)


def winding_number(centerline: np.ndarray, post_xy, wrap_band: float) -> float:
    """Signed turns of the rope around the post axis, with canonical closure.

    The wrapped span is an open curve, so its unwrapped azimuth alone is not an
    integer. Closing it the short way -- from where the rope leaves the post
    straight back to where it arrived -- is the canonical closure: both ends of
    the span are on the post's surface and below its top, so no closure path can
    cross the post and change the count.

    Note what that closure does arithmetically: it is exactly `round(sweep)`.
    That makes the reading robust to discretization and useless as a warning, so
    read `winding_sweep` whenever this one surprises you.
    """

    swept = 2.0 * np.pi * winding_sweep(centerline, post_xy, wrap_band)
    closure = float(np.arctan2(np.sin(-swept), np.cos(-swept)))
    return (swept + closure) / (2.0 * np.pi)


def winding_topological(centerline: np.ndarray, post_xy) -> float:
    """Signed turns of the WHOLE rope around the post axis, anchor to free end.

    The homotopy invariant itself: with both ends held and the post fixed, the
    rope's unwrapped azimuth from end to end, closed the short way from the free
    end's bearing back to the anchor's, is an integer that only a crossing of the
    post can change. It does not care where the rope IS -- on the post, on the
    board, in a loose coil -- only how many times it goes round.

    `winding_number` above reads only the rope resting on the post, which is the
    right thing to look at while a wrap is being laid or peeled, but it is not
    invariant: rope_unwinding at two wraps (2026-08-27) read +1 at the end with
    every orbit done, because the slack that came off the post was dragged back
    against it three quarters of the way round -- 0.73 of sweep, rounded up. The
    verdict is on this quantity; the on-post reading is a diagnostic.
    """

    centerline = np.asarray(centerline, dtype=float)
    post_xy = np.asarray(post_xy, dtype=float)[:2]
    angles = np.unwrap(
        np.arctan2(centerline[:, 1] - post_xy[1], centerline[:, 0] - post_xy[0])
    )
    swept = float(angles[-1] - angles[0])
    closure = float(np.arctan2(np.sin(-swept), np.cos(-swept)))
    return (swept + closure) / (2.0 * np.pi)


def rope_twist_turns(scene, groups: list[np.ndarray]) -> float:
    """Total twist stored in the rope, in turns. NaN if it cannot be measured.

    Carrying the plug around the post without turning it winds one full turn of
    twist into the rope per orbit: the rope's tangent at the plug rotates with
    the orbit while the material frame welded to the plug does not, and the
    anchored far end leaves the difference nowhere to go. That is invisible in a
    video until the rope is finally laid down looking wrung out, so it is
    measured here instead of judged by eye.

    Method: parallel-transport a reference frame along the CURRENT centerline,
    and at each material bin compare where the nodes actually sit around the
    cross section against where they sat at spawn. The difference, unwrapped
    along the rope, is the accumulated twist. The transported frame's arbitrary
    starting phase cancels because only the end-to-end difference is used.
    """

    from topogym.world.rope import parallel_transport_frames

    coords = material_coords(scene)
    nodes = rope_particles(scene)
    centerline = winding_centerline(scene, groups)
    if len(centerline) < 3:
        return float("nan")

    # Parallel transport needs non-degenerate segments; drop bins whose centers
    # coincide with the previous kept one (compression can collapse a pair).
    kept = [0]
    for index in range(1, len(centerline)):
        if float(np.linalg.norm(centerline[index] - centerline[kept[-1]])) > 1e-6:
            kept.append(index)
    if len(kept) < 3:
        return float("nan")
    kept = np.asarray(kept, dtype=int)
    _tangents, normals, binormals = parallel_transport_frames(centerline[kept])

    # Nodes near the axis have a meaningless azimuth; keep the outer shell.
    min_radius = 0.5 * float(scene.layout.cfg.rope.radius)
    measured: list[float] = []
    for frame_index, bin_index in enumerate(kept):
        group = groups[bin_index]
        n_off = coords[group, 1]
        b_off = coords[group, 2]
        outer = np.hypot(n_off, b_off) > min_radius
        if not np.any(outer):
            continue
        rel = nodes[group][outer] - centerline[bin_index]
        current = np.arctan2(rel @ binormals[frame_index], rel @ normals[frame_index])
        spawned = np.arctan2(b_off[outer], n_off[outer])
        # Circular mean of the per-node offset: the bin's twist angle.
        measured.append(float(np.angle(np.mean(np.exp(1j * (current - spawned))))))
    if len(measured) < 3:
        return float("nan")
    unwrapped = np.unwrap(np.asarray(measured, dtype=float))
    return float((unwrapped[-1] - unwrapped[0]) / (2.0 * np.pi))


def wrap_band_radius(layout, spec: WindingSpec) -> float:
    """"Near the post" for the gateway check: a wrap radius plus a rope diameter.

    Deliberately generous -- the question it serves is "did any rope that ended
    up near the post get above its top", and a near miss is worth catching.
    """

    return float(layout.cfg.fixtures[spec.post].radius) + 3.0 * float(layout.cfg.rope.radius)


def settled_band_radius(layout, spec: WindingSpec) -> float:
    """"On the post" for the winding count: only rope actually resting on it.

    Tighter than `wrap_band_radius` on purpose. The rope settles at
    `post_radius + rope_radius`; one further rope radius admits that and little
    else. Loosen it and the run-in from the anchor and the run-out to the target
    zone leak in, and a tail's azimuth is not winding. Measured against the
    oracle route on 2026-08-13, the wrapped sweep by band:

        post_r + 1.0*rope_r -> 2.420    (the wrap itself)
        post_r + 2.0*rope_r -> 2.469
        post_r + 3.0*rope_r -> 2.492
        post_r + 4.0*rope_r -> 2.508    -> rounds to +3, i.e. wrong

    The wrapped span alone can never tip the rounding: its sweep is
    `turns + (entry-to-exit bearing difference)`, and that difference is under
    half a turn by construction. Only leaked tail can push it over.
    """

    return float(layout.cfg.fixtures[spec.post].radius) + 2.0 * float(layout.cfg.rope.radius)


def post_contact(scene, spec: WindingSpec) -> dict:
    """How deep into the post the rope is, and how much of it is touching.

    `rope_wrap_metrics` is the cable_routing equivalent, but it is built around
    "which side of the peg is the rope on", which a wound post has no answer to
    -- the rope is on every side. Only the two relation-free numbers carry over:
    the worst surface gap (negative = interpenetration, the divergence signal)
    and how many nodes are in contact.
    """

    layout = scene.layout
    center = post_center(layout, spec)
    fixture = layout.cfg.fixtures[spec.post]
    post_radius = float(fixture.radius)
    rope_radius = float(layout.cfg.rope.radius)
    contact_tol = float(getattr(layout.cfg.routing, "wrap_contact_tolerance", 0.010))

    nodes = rope_particles(scene)
    fixture_center = layout.fixture_pos(spec.post)
    half_height = 0.5 * float(fixture.height)
    z_tol = float(getattr(layout.cfg.routing, "wrap_height_tolerance", rope_radius + 0.004))
    in_band = (nodes[:, 2] >= fixture_center[2] - half_height - z_tol) & (
        nodes[:, 2] <= fixture_center[2] + half_height + z_tol
    )
    radial = np.linalg.norm(nodes[:, :2] - center[None, :2], axis=1)
    banded = radial[in_band]
    return {
        "surface_gap": float(banded.min() - post_radius) if banded.size else float("inf"),
        "contact_nodes": int(
            np.count_nonzero(banded <= post_radius + rope_radius + contact_tol)
        ),
    }


# Franka fingertip pad, from the MJCF (`fingertip_pad_collision_1`,
# assets/xml/franka_emika_panda/panda.xml): half sizes in the finger's own frame,
# where local +z runs along the approach direction, plus the pad's offset from
# the finger origin.
_PAD_HALF = np.array([0.0085, 0.004, 0.0085], dtype=float)
_PAD_OFFSET = np.array([0.0, 0.0055, 0.0445], dtype=float)


def pad_gap(scene, robot, finger_links) -> float:
    """Smallest distance from any rope node to either fingertip pad, in metres.

    Negative means the rope is inside a pad. The task is meant to be rope
    against post; the gripper is a carrying tool, and anything it touches it can
    drag. Reasoning about this from geometry alone has already been wrong once
    -- a pad reaches 8.5 mm along the plug's axis, which is exactly where the
    rope leaves it -- so it is measured.
    """

    nodes = rope_particles(scene)
    best = float("inf")
    robotiq=getattr(robot,'_topogym_tool_model','panda')=='robotiq_2f85'
    pad_offset=np.array([0,-.0026,.01875]) if robotiq else _PAD_OFFSET
    pad_half=np.array([.011,.004,.01875]) if robotiq else _PAD_HALF
    for name in finger_links:
        link = robot.get_link(str(name))
        origin = np.asarray(tensor_to_numpy(link.get_pos()), dtype=float).reshape(3)
        rotation = _quat_to_matrix(tensor_to_numpy(link.get_quat()))
        # Node positions in the pad's own frame, then the box distance.
        local = (nodes - origin[None, :]) @ rotation - pad_offset[None, :]
        outside = np.maximum(np.abs(local) - pad_half[None, :], 0.0)
        distance = np.linalg.norm(outside, axis=1)
        inside = np.max(np.abs(local) - pad_half[None, :], axis=1)
        # Outside the box the norm of the overshoot is exact; inside it is zero,
        # so fall back to the (negative) largest per-axis penetration.
        signed = np.where(distance > 0.0, distance, inside)
        best = min(best, float(signed.min()))
    return best


def _quat_to_matrix(quat) -> np.ndarray:
    w, x, y, z = (float(v) for v in np.asarray(quat, dtype=float).reshape(4))
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
            [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
            [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
        ],
        dtype=float,
    )


# The gripper's own envelope about the tool axis: the fingers and their shafts
# travel within 45 mm of the hand axis, and the geometry runs from the hand
# origin down to the bottom of the fingertip pads. Rope inside that cylinder is
# among the gripper; rope below the fingertips is hanging clear of it.
#
# `intrusion` is PROXIMITY, not contact -- a 45 mm cylinder is far wider than the
# fingers themselves. `pad_gap` is the contact measure. The pair is what
# separates "the rope is geometrically wrapped around the gripper" from "the rope
# is touching it", and on the 2026-08-13 run those two answered differently:
# wrap reached +2.04 turns while `pad_gap` never dropped below 1.6 mm.
_GRIPPER_RADIUS = 0.045
# A rope point on the tool axis has no meaningful bearing, the same reason
# `rope_twist_turns` keeps only the outer shell of each cross section.
_STRAND_MIN_RADIUS = 0.020


def rope_free_end_first(scene, groups: list[np.ndarray], plug_pos) -> bool:
    """Whether the ordered centerline starts at the free (plug) end.

    `material_bins` orders by spawn arc length, and which end of the rope arc
    length zero sits at is a property of the spawn centerline, not something
    worth restating here. Ask the geometry once instead: the free end is the one
    the plug is at.
    """

    centerline = winding_centerline(scene, groups)
    plug_pos = np.asarray(plug_pos, dtype=float).reshape(3)
    head = float(np.linalg.norm(centerline[0] - plug_pos))
    tail = float(np.linalg.norm(centerline[-1] - plug_pos))
    return bool(head <= tail)


def gripper_frame_metrics(
    nodes,
    arc_fractions,
    centerline,
    hand_pos,
    hand_rot,
    *,
    free_end_first: bool,
) -> dict:
    """Where the rope sits relative to the gripper, and which way it leaves it.

    Arrays in, numbers out -- no scene, no solver -- so the geometry can be
    checked against a synthesised orbit (`tests/check_rope_winding_geometry.py`)
    before any of it is trusted on a GPU run.

    `strand_bearing` and `hand_yaw` are both WORLD angles about the vertical.
    Their difference is the quantity this task has never measured: how far the
    rope has swept around the gripper since the grasp. Carrying the plug around
    the post with a fixed wrist sweeps it one full turn per orbit, and that sweep
    is what drags the rope across the fingers. Taking both angles in the same
    frame and subtracting keeps the sign clear of the hand frame's fingers-down
    flip. This route carries the hand fingers-down throughout, so its tool axis
    is vertical and a bearing about the vertical IS the tool roll; a hand tilted
    far off vertical would make `hand_yaw` a poor stand-in for its own roll.

    Returned keys:

    - ``strand_bearing`` -- world bearing of the rope leaving the hand, radians.
      Unwrapped over a run, this IS the yaw profile the wrist would have to
      follow to hold the rope still relative to the gripper.
    - ``hand_yaw`` -- world yaw of the hand, radians.
    - ``near_r`` / ``near_depth`` / ``near_s`` -- the rope node closest to the
      tool axis (excluding the held stretch): its radial distance, its depth
      relative to the fingertip pads (positive = hanging below them, clear), and
      its material arc fraction (which part of the rope it is).
    - ``intrusion`` -- how many nodes are inside the gripper envelope AND above
      the pads. Zero is the goal; anything else is rope up among the fingers.
    """

    nodes = np.asarray(nodes, dtype=float)
    arc_fractions = np.asarray(arc_fractions, dtype=float)
    centerline = np.asarray(centerline, dtype=float)
    hand_pos = np.asarray(hand_pos, dtype=float).reshape(3)
    hand_rot = np.asarray(hand_rot, dtype=float).reshape(3, 3)

    hand_yaw = float(np.arctan2(hand_rot[1, 0], hand_rot[0, 0]))
    empty = {
        "strand_bearing": float("nan"),
        "hand_yaw": hand_yaw,
        "near_r": float("inf"),
        "near_depth": float("nan"),
        "near_s": float("nan"),
        "intrusion": 0,
    }

    # Walk back from the free end to the first centerline point far enough off
    # the tool axis for its bearing to mean anything. Everything nearer than that
    # is the stretch the gripper is holding.
    order = centerline if free_end_first else centerline[::-1]
    planar = np.linalg.norm(order[:, :2] - hand_pos[None, :2], axis=1)
    far = np.flatnonzero(planar > _STRAND_MIN_RADIUS)
    if not far.size:
        return empty
    sample = order[far[0]]
    strand_bearing = float(
        np.arctan2(sample[1] - hand_pos[1], sample[0] - hand_pos[0])
    )

    # `material_bins` bins by equal spawn arc length, so a bin's index is its
    # arc fraction. Use the strand sample's bin as the cut: beyond it is free
    # rope, before it is the held stretch, which would otherwise win every
    # closest-node query by sitting between the pads.
    bin_count = len(centerline)
    bin_index = far[0] if free_end_first else bin_count - 1 - far[0]
    gate = (bin_index + 0.5) / bin_count
    free = arc_fractions >= gate if free_end_first else arc_fractions <= gate
    if not np.any(free):
        return {**empty, "strand_bearing": strand_bearing}

    axis = hand_rot[:, 2]
    delta = nodes[free] - hand_pos[None, :]
    depth = delta @ axis
    radial = np.linalg.norm(delta - depth[:, None] * axis[None, :], axis=1)

    nearest = int(np.argmin(radial))
    # Inside the envelope and no deeper than the fingertips reach. The band runs
    # to the BOTTOM of the pads, not to their centre: the pads are 8.5 mm half
    # height, and the 2026-08-13 run put the nearest rope node 4.5 mm below their
    # centre for most of the second turn -- inside the fingers, and invisible to
    # a band that stopped at the centre. Rope nearer the plug than the strand
    # sample is already excluded by the arc gate above, so nothing here needs a
    # second margin to keep the held stretch out.
    inside = (
        (radial < _GRIPPER_RADIUS)
        & (depth >= 0.0)
        & (depth <= HAND_TO_PAD_Z + _PAD_HALF[2])
    )
    return {
        "strand_bearing": strand_bearing,
        "hand_yaw": hand_yaw,
        "near_r": float(radial[nearest]),
        "near_depth": float(depth[nearest] - HAND_TO_PAD_Z),
        "near_s": float(arc_fractions[free][nearest]),
        "intrusion": int(np.count_nonzero(inside)),
    }


#: Fraction of the rope, measured from the free end, treated as "in hand" rather
#: than as something already laid down. The span from the plug to where the rope
#: meets the post is one orbit radius plus a little -- about 140 mm of a 708 mm
#: rope, so 20%. A quarter gives that some room.
CARRIED_FRACTION = 0.25


def blocking_gap(scene, arc_fractions, outlet_z: float, *, free_end_first: bool) -> dict:
    """How much height the plug's cable outlet has over the rope already laid.

    The winding is meant to be a rising spiral: every turn passes OVER whatever
    is already on the post or on the board, so nothing can be in the way. Stated
    as a number, that is the outlet's height minus the top of every rope node
    that is not the span currently in hand. Positive means the invariant holds.

    It does not hold by default. `climb_per_turn` shipped at exactly one rope
    diameter, which puts turn two's outlet touching turn one's top -- zero gap,
    and the second turn grazed the first at one azimuth every lap. That was
    visible in the viewer long before it was measurable, because nothing was
    measuring it.

    The carried span is excluded by material coordinate rather than by distance:
    it is the rope's own last stretch that is legitimately up at the outlet's
    height, and including it would make the gap read zero for a trivial reason.
    """

    nodes = rope_particles(scene)
    fraction = np.asarray(arc_fractions, dtype=float)
    if not free_end_first:
        fraction = 1.0 - fraction
    laid = nodes[fraction > CARRIED_FRACTION]
    if not len(laid):
        return {"blocking_gap": float("nan"), "blocking_top": float("nan")}
    top = float(laid[:, 2].max())
    return {"blocking_gap": float(outlet_z) - top, "blocking_top": top}


def gripper_wrap(
    scene,
    controller,
    groups: list[np.ndarray],
    *,
    free_end_first: bool,
    outlet_z: float | None = None,
) -> dict:
    """`gripper_frame_metrics` for a live scene and controller."""

    arc = material_coords(scene)[:, 0]
    fractions = arc / max(float(arc.max()), 1e-9)
    metrics = gripper_frame_metrics(
        rope_particles(scene),
        fractions,
        winding_centerline(scene, groups),
        controller.hand_pos(),
        _quat_to_matrix(tensor_to_numpy(controller.hand_quat())),
        free_end_first=free_end_first,
    )
    if outlet_z is not None:
        metrics.update(
            blocking_gap(scene, fractions, outlet_z, free_end_first=free_end_first)
        )
    return metrics


def winding_metrics(scene, spec: WindingSpec, groups: list[np.ndarray]) -> dict:
    """Winding number, the gateway (post-top) check, and post contact."""

    layout = scene.layout
    center = post_center(layout, spec)
    centerline = winding_centerline(scene, groups)
    settled_band = settled_band_radius(layout, spec)
    turns = winding_number(centerline, center, settled_band)

    radial = np.linalg.norm(centerline[:, :2] - center[None, :2], axis=1)
    wound = centerline[radial <= wrap_band_radius(layout, spec)]
    wound_max_z = float(wound[:, 2].max()) if len(wound) else float("nan")
    contact = post_contact(scene, spec)
    return {
        "winding_number": float(turns),
        "winding_topological": float(winding_topological(centerline, center)),
        "swept_turns": winding_sweep(centerline, center, settled_band),
        "target_winding": float(spec.target_winding),
        "wound_points": int(len(wound)),
        "wound_max_z": wound_max_z,
        "post_top_z": float(post_top_z(layout, spec)),
        "contact_nodes": contact["contact_nodes"],
        "surface_gap": contact["surface_gap"],
        "rope_min_z": float(rope_particles(scene)[:, 2].min()),
        "twist_turns": rope_twist_turns(scene, groups),
    }


def print_winding_verification(scene, spec: WindingSpec, groups: list[np.ndarray]) -> bool:
    """Print the winding verdict; return whether the winding criterion passed."""

    success_cfg = getattr(scene.layout.cfg, "success", None)
    tolerance = float(getattr(success_cfg, "winding_tolerance", 0.25))
    metrics = winding_metrics(scene, spec, groups)
    # Which count is the verdict is the task's call (`success.winding_metric`):
    # "on_post" is the task book's wraps-on-the-post reading (rope_winding,
    # 0 -> 2); "closure" is the whole-rope count closed to the anchor, which
    # slack cannot fool (rope_unwinding). They differ by the tails: with C
    # where both layouts put it, a straight run to C adds one to the closure
    # count, which is why rope_unwinding's oracle routes to C the other way.
    metric = str(getattr(success_cfg, "winding_metric", "on_post"))
    if metric not in ("on_post", "closure"):
        raise ValueError(f"success.winding_metric must be 'on_post' or 'closure', got {metric!r}.")
    turns = metrics["winding_number" if metric == "on_post" else "winding_topological"]
    other = metrics["winding_topological" if metric == "on_post" else "winding_number"]
    target = metrics["target_winding"]
    winding_ok = abs(turns - target) <= tolerance
    # Gateway semantics: winding may only change over the post's top, so a run
    # that lifted the rope above it did not wind, it hopped.
    below_top = not (metrics["wound_points"] and metrics["wound_max_z"] > metrics["post_top_z"])
    print(
        f"rope_winding_verify post={spec.post} success={winding_ok and below_top} "
        f"winding_number={turns:+.3f} target={target:+.1f} tolerance={tolerance:.2f} "
        f"metric={metric} "
        # The other count, for comparison.
        f"{'closure' if metric == 'on_post' else 'on_post'}_winding={other:+.3f} "
        # The unrounded sweep `winding_number` came from. Distance from the
        # nearest half-integer is the margin the reading has left.
        f"swept_turns={metrics['swept_turns']:+.3f} "
        f"winding_ok={winding_ok} below_post_top={below_top} "
        f"wound_points={metrics['wound_points']} "
        f"wound_max_z={metrics['wound_max_z']:.4f} "
        f"post_top_z={metrics['post_top_z']:.4f} "
        f"contact_nodes={metrics['contact_nodes']} "
        f"surface_gap={metrics['surface_gap']:+.4f} "
        f"rope_min_z={metrics['rope_min_z']:.4f} "
        # Reported, not gated: a wrung-out rope is a quality problem, not a
        # topology one -- the winding number is what the task is defined on.
        f"twist_turns={metrics['twist_turns']:+.2f}",
        flush=True,
    )
    return bool(winding_ok and below_top)
