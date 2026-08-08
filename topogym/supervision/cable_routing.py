from __future__ import annotations

import numpy as np

from topogym.planning.cable_routing_planner import _relation_axis, _route_radius


def tensor_to_numpy(value) -> np.ndarray:
    """Convert Genesis/Torch-like tensor values to a NumPy array."""

    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        return np.asarray(value.numpy())
    return np.asarray(value)


def signature_text(cable_scene) -> str:
    """Return a compact text form of the target routing signature."""

    return " -> ".join(
        f"{item['fixture']}:{item['relation']}"
        for item in cable_scene.layout.target_signature().to_info()
    )


def polyline_length(polyline: np.ndarray) -> float:
    """Return the total length of a route polyline."""

    polyline = np.asarray(polyline, dtype=float)
    if len(polyline) < 2:
        return 0.0
    return float(np.sum(np.linalg.norm(polyline[1:] - polyline[:-1], axis=1)))


def peg_signature_items(layout) -> list[dict[str, str]]:
    """Return target-signature items that describe wrapping around pegs."""

    return [
        item
        for item in layout.target_signature().to_info()
        if layout.fixture_type(str(item["fixture"])) == "peg"
        and str(item["relation"]) in {"left", "right", "above", "below"}
    ]


def rope_particles(cable_scene) -> np.ndarray:
    """Return rope node positions as an ``(N, 3)`` NumPy array.

    Goes through the scene's rope backend when present (rope_backends
    protocol); the direct PBD read is the fallback for unmigrated scenes.
    """

    backend = getattr(cable_scene, "rope_backend", None)
    if backend is not None:
        return np.asarray(backend.nodes(cable_scene.rope_handle.entity), dtype=float)
    particles = tensor_to_numpy(cable_scene.rope_handle.entity.get_particles_pos())
    if particles.ndim == 3:
        particles = particles[0]
    return np.asarray(particles, dtype=float)


def circular_span(angles: np.ndarray) -> float:
    """Smallest circular arc span that covers the given angles."""

    angles = np.asarray(angles, dtype=float)
    if angles.size <= 1:
        return 0.0
    wrapped = np.sort((angles + 2.0 * np.pi) % (2.0 * np.pi))
    gaps = np.diff(np.concatenate([wrapped, wrapped[:1] + 2.0 * np.pi]))
    return float(2.0 * np.pi - np.max(gaps))


def endpoint_route_ok(
    endpoint_trace: list[np.ndarray],
    layout,
    fixture_name: str,
    relation: str,
) -> tuple[bool, float, float]:
    """Check whether the driven endpoint visited the intended side of a peg."""

    if not endpoint_trace:
        return False, 0.0, float("inf")
    trace = np.asarray(endpoint_trace, dtype=float)
    center = layout.fixture_pos(fixture_name, z=float(layout.cfg.rope.z))
    vectors = trace[:, :2] - center[None, :2]
    distances = np.linalg.norm(vectors, axis=1)
    angles = np.unwrap(np.arctan2(vectors[:, 1], vectors[:, 0]))
    angle_span = float(np.max(angles) - np.min(angles)) if angles.size else 0.0
    axis = _relation_axis(relation)
    side_projection = vectors @ axis
    radius = _route_radius(layout, fixture_name, endpoint_path=True)
    visited_target_side = bool(np.any(side_projection >= 0.75 * radius))
    nearest = float(np.min(distances)) if distances.size else float("inf")
    close_enough = nearest <= radius + float(
        getattr(layout.cfg.routing, "wrap_near_tolerance", 0.036)
    )
    return (
        bool(
            visited_target_side
            and close_enough
            and angle_span >= np.deg2rad(75.0)
        ),
        angle_span,
        nearest,
    )


def rope_wrap_metrics(
    cable_scene,
    fixture_name: str,
    relation: str,
) -> dict[str, float | int | bool]:
    """Measure PBD rope contact/wrap state around one routing peg."""

    layout = cable_scene.layout
    fixture = layout.cfg.fixtures[str(fixture_name)]
    fixture_center = layout.fixture_pos(fixture_name)
    center = layout.fixture_pos(fixture_name, z=float(layout.cfg.rope.z))
    particles = rope_particles(cable_scene)
    vectors = particles[:, :2] - center[None, :2]
    distances = np.linalg.norm(vectors, axis=1)
    fixture_radius = float(getattr(fixture, "radius", 0.0))
    fixture_height = float(getattr(fixture, "height", 0.0))
    z_min = float(fixture_center[2] - 0.5 * fixture_height)
    z_max = float(fixture_center[2] + 0.5 * fixture_height)
    rope_radius = float(layout.cfg.rope.radius)
    contact_tol = float(getattr(layout.cfg.routing, "wrap_contact_tolerance", 0.010))
    near_tol = float(getattr(layout.cfg.routing, "wrap_near_tolerance", 0.036))
    z_tol = float(
        getattr(layout.cfg.routing, "wrap_height_tolerance", rope_radius + 0.004)
    )
    contact_limit = fixture_radius + rope_radius + contact_tol
    near_limit = fixture_radius + rope_radius + near_tol
    z_mask = (particles[:, 2] >= z_min - z_tol) & (
        particles[:, 2] <= z_max + z_tol
    )
    contact_mask = (distances <= contact_limit) & z_mask
    near_mask = (distances <= near_limit) & z_mask
    axis = _relation_axis(relation)
    side_projection = vectors @ axis
    side_mask = near_mask & (side_projection >= fixture_radius)
    near_angles = np.arctan2(vectors[near_mask, 1], vectors[near_mask, 0])
    angle_span = circular_span(near_angles)
    contact_count = int(np.sum(contact_mask))
    near_count = int(np.sum(near_mask))
    side_count = int(np.sum(side_mask))
    height_count = int(np.sum(z_mask))
    rope_contact = contact_count > 0
    rope_side_ok = side_count > 0
    rope_wrap_ok = bool(rope_contact and rope_side_ok and angle_span >= np.deg2rad(35.0))
    z_gap = np.maximum(z_min - particles[:, 2], particles[:, 2] - z_max)
    z_gap = np.maximum(z_gap, 0.0)
    particle_surface_gap = (
        float(np.min(distances) - fixture_radius)
        if distances.size
        else float("inf")
    )
    centerline_gap_approx = (
        float(np.min(distances) - fixture_radius - rope_radius)
        if distances.size
        else float("inf")
    )
    return {
        "rope_contact": rope_contact,
        "rope_side_ok": rope_side_ok,
        "rope_wrap_ok": rope_wrap_ok,
        "contact_particles": contact_count,
        "near_particles": near_count,
        "side_particles": side_count,
        "height_particles": height_count,
        "angle_span_rad": angle_span,
        # PBD particles are tube mesh/volume material points, not an abstract
        # centerline. This is the safer penetration signal for peg contact.
        "particle_surface_gap": particle_surface_gap,
        "centerline_gap_approx": centerline_gap_approx,
        "min_gap": centerline_gap_approx,
        "min_z_gap": float(np.min(z_gap)) if z_gap.size else float("inf"),
        "z_min": z_min,
        "z_max": z_max,
    }


def print_routing_verification(
    cable_scene,
    endpoint_trace: list[np.ndarray],
) -> bool:
    """Print and return final route verification for all target peg relations."""

    routing_ok = True
    for item in peg_signature_items(cable_scene.layout):
        fixture = str(item["fixture"])
        relation = str(item["relation"])
        endpoint_ok, endpoint_span, endpoint_nearest = endpoint_route_ok(
            endpoint_trace,
            cable_scene.layout,
            fixture,
            relation,
        )
        metrics = rope_wrap_metrics(cable_scene, fixture, relation)
        item_ok = bool(endpoint_ok and metrics["rope_wrap_ok"])
        routing_ok = routing_ok and item_ok
        print(
            "cable_routing_verify "
            f"{fixture}:{relation} "
            f"success={item_ok} "
            f"endpoint_route_ok={endpoint_ok} "
            f"endpoint_angle_span_deg={np.rad2deg(endpoint_span):.1f} "
            f"endpoint_nearest={endpoint_nearest:.4f} "
            f"rope_contact={metrics['rope_contact']} "
            f"rope_wrap_ok={metrics['rope_wrap_ok']} "
            f"contact_particles={metrics['contact_particles']} "
            f"near_particles={metrics['near_particles']} "
            f"side_particles={metrics['side_particles']} "
            f"height_particles={metrics['height_particles']} "
            f"rope_angle_span_deg={np.rad2deg(float(metrics['angle_span_rad'])):.1f} "
            f"particle_surface_gap={float(metrics['particle_surface_gap']):.4f} "
            f"centerline_gap_approx={float(metrics['centerline_gap_approx']):.4f} "
            f"min_z_gap={float(metrics['min_z_gap']):.4f}",
            flush=True,
        )
    return routing_ok


def print_phase_routing_metrics(
    cable_scene,
    endpoint_trace: list[np.ndarray],
    *,
    phase: str,
) -> None:
    """Print route metrics at an intermediate waypoint phase."""

    for item in peg_signature_items(cable_scene.layout):
        fixture = str(item["fixture"])
        relation = str(item["relation"])
        endpoint_ok, endpoint_span, endpoint_nearest = endpoint_route_ok(
            endpoint_trace,
            cable_scene.layout,
            fixture,
            relation,
        )
        metrics = rope_wrap_metrics(cable_scene, fixture, relation)
        print(
            "cable_routing_phase_verify "
            f"phase={phase} "
            f"{fixture}:{relation} "
            f"endpoint_route_ok={endpoint_ok} "
            f"endpoint_angle_span_deg={np.rad2deg(endpoint_span):.1f} "
            f"endpoint_nearest={endpoint_nearest:.4f} "
            f"rope_contact={metrics['rope_contact']} "
            f"rope_wrap_ok={metrics['rope_wrap_ok']} "
            f"contact_particles={metrics['contact_particles']} "
            f"near_particles={metrics['near_particles']} "
            f"height_particles={metrics['height_particles']} "
            f"particle_surface_gap={float(metrics['particle_surface_gap']):.4f} "
            f"centerline_gap_approx={float(metrics['centerline_gap_approx']):.4f} "
            f"min_z_gap={float(metrics['min_z_gap']):.4f}",
            flush=True,
        )
