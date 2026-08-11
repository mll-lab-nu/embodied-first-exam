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


def winding_number(centerline: np.ndarray, post_xy) -> float:
    """Signed turns of the rope around the post axis, with canonical closure.

    The rope is an open curve, so its unwrapped azimuth alone is not an integer.
    Closing it the short way -- from the free end straight back to the anchor's
    bearing -- is the canonical closure for this layout: both ends stay far from
    the post and below its top, so no closure path can cross the post and change
    the count. The sum is an integer up to discretization.
    """

    centerline = np.asarray(centerline, dtype=float)
    post_xy = np.asarray(post_xy, dtype=float)[:2]
    angles = np.unwrap(
        np.arctan2(
            centerline[:, 1] - post_xy[1],
            centerline[:, 0] - post_xy[0],
        )
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


def winding_metrics(scene, spec: WindingSpec, groups: list[np.ndarray]) -> dict:
    """Winding number, the gateway (post-top) check, and post contact."""

    layout = scene.layout
    center = post_center(layout, spec)
    centerline = winding_centerline(scene, groups)
    turns = winding_number(centerline, center)

    radial = np.linalg.norm(centerline[:, :2] - center[None, :2], axis=1)
    # "On the post" = within a wrap radius plus a rope diameter of the axis.
    wrap_band = float(layout.cfg.fixtures[spec.post].radius) + 3.0 * float(
        layout.cfg.rope.radius
    )
    wound = centerline[radial <= wrap_band]
    wound_max_z = float(wound[:, 2].max()) if len(wound) else float("nan")
    contact = post_contact(scene, spec)
    return {
        "winding_number": float(turns),
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
    turns = metrics["winding_number"]
    target = metrics["target_winding"]
    winding_ok = abs(turns - target) <= tolerance
    # Gateway semantics: winding may only change over the post's top, so a run
    # that lifted the rope above it did not wind, it hopped.
    below_top = not (metrics["wound_points"] and metrics["wound_max_z"] > metrics["post_top_z"])
    print(
        f"rope_winding_verify post={spec.post} success={winding_ok and below_top} "
        f"winding_number={turns:+.3f} target={target:+.1f} tolerance={tolerance:.2f} "
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
