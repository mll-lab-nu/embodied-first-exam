from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .subgoal import PlannedSubgoal
from .waypoint import EpisodePlan, WaypointPlan, WaypointTarget


def _relation_axis(relation: str) -> np.ndarray:
    axes = {
        "left": np.array([-1.0, 0.0], dtype=float),
        "right": np.array([1.0, 0.0], dtype=float),
        "above": np.array([0.0, 1.0], dtype=float),
        "below": np.array([0.0, -1.0], dtype=float),
    }
    if relation not in axes:
        raise ValueError(f"Unsupported wrap relation: {relation!r}.")
    return axes[relation].copy()


def _approach_axis_for_relation(relation: str) -> np.ndarray:
    axes = {
        "left": np.array([0.0, 1.0], dtype=float),
        "right": np.array([0.0, -1.0], dtype=float),
        "above": np.array([1.0, 0.0], dtype=float),
        "below": np.array([-1.0, 0.0], dtype=float),
    }
    if relation not in axes:
        raise ValueError(f"Unsupported approach relation: {relation!r}.")
    return axes[relation].copy()


def _angle_delta(start_angle: float, target_angle: float) -> float:
    return float((target_angle - start_angle + np.pi) % (2.0 * np.pi) - np.pi)


def _route_radius(layout, fixture_name: str, *, endpoint_path: bool = False) -> float:
    fixture = layout.cfg.fixtures[str(fixture_name)]
    fixture_radius = float(getattr(fixture, "radius", 0.0))
    rope_radius = float(layout.cfg.rope.radius)
    side_clearance = float(layout.cfg.routing.side_clearance)
    wrap_clearance = float(getattr(layout.cfg.routing, "wrap_clearance", 0.018))
    radius = max(side_clearance, fixture_radius + rope_radius + wrap_clearance)
    if endpoint_path:
        radius = max(radius, float(getattr(layout.cfg.routing, "endpoint_side_clearance", radius)))
    return radius


def _point_at_fixture_angle(layout, fixture_name: str, angle: float, radius: float) -> np.ndarray:
    center = layout.fixture_pos(fixture_name, z=float(layout.cfg.rope.z))
    point = center.copy()
    point[0] += float(radius) * float(np.cos(angle))
    point[1] += float(radius) * float(np.sin(angle))
    return point


def _wrap_waypoints(layout, fixture_name: str, relation: str, source_point: np.ndarray) -> list[np.ndarray]:
    center = layout.fixture_pos(fixture_name, z=float(layout.cfg.rope.z))
    axis = _relation_axis(relation)
    radius = _route_radius(layout, fixture_name, endpoint_path=True)
    source = np.asarray(source_point, dtype=float)
    source_vec = source[:2] - center[:2]
    if float(np.linalg.norm(source_vec)) <= 1e-8:
        source_vec = -axis

    start_angle = float(np.arctan2(source_vec[1], source_vec[0]))
    target_angle = float(np.arctan2(axis[1], axis[0]))
    delta = _angle_delta(start_angle, target_angle)
    direction = 1.0 if delta >= 0.0 else -1.0
    overshoot_degrees = float(getattr(layout.cfg.routing, "wrap_overshoot_degrees", 22.0))
    overshoot = np.deg2rad(overshoot_degrees) * direction
    arc_points = max(2, int(getattr(layout.cfg.routing, "wrap_arc_points", 5)))

    end_angle = start_angle + delta
    arc_end = end_angle + overshoot
    angles = np.linspace(start_angle, arc_end, arc_points + 1)[1:]
    return [_point_at_fixture_angle(layout, fixture_name, angle, radius) for angle in angles]


def _departure_waypoint(layout, source_point: np.ndarray, next_point: np.ndarray) -> np.ndarray:
    extension = float(getattr(layout.cfg.routing, "peg_departure_extension", 0.0))
    source = np.asarray(source_point, dtype=float)
    if extension <= 0.0:
        return source.copy()
    target = np.asarray(next_point, dtype=float)
    direction = target[:2] - source[:2]
    norm = float(np.linalg.norm(direction))
    if norm <= 1e-8:
        return source.copy()
    point = source.copy()
    point[:2] += extension * direction / norm
    return point


def _front_axis(layout) -> np.ndarray:
    axis = np.asarray(getattr(layout.cfg.routing, "front_axis", [0.0, -1.0]), dtype=float)
    if axis.shape != (2,):
        raise ValueError(f"routing.front_axis must have shape (2,), got {axis}.")
    norm = float(np.linalg.norm(axis))
    if norm <= 1e-8:
        return np.array([0.0, -1.0], dtype=float)
    return axis / norm


def _front_pull_enabled(layout, fixture_name: str) -> bool:
    fixtures = getattr(layout.cfg.routing, "peg_front_pull_fixtures", ["P1"])
    return str(fixture_name) in {str(name) for name in fixtures}


def _front_pull_waypoint(layout, fixture_name: str, source_point: np.ndarray) -> np.ndarray:
    targets = getattr(layout.cfg.routing, "peg_front_pull_targets", {})
    try:
        target_spec = targets[str(fixture_name)]
    except (KeyError, TypeError):
        target_spec = None
    if target_spec is not None:
        target = np.asarray(target_spec, dtype=float)
        if target.shape == (2,):
            target = np.array([target[0], target[1], float(layout.cfg.rope.z)], dtype=float)
        if target.shape != (3,):
            raise ValueError(f"front pull target for {fixture_name} must have shape (2,) or (3,), got {target}.")
        return layout.position_to_world(target)

    distance = float(getattr(layout.cfg.routing, "peg_front_pull_distance", 0.0))
    source = np.asarray(source_point, dtype=float).copy()
    if distance <= 0.0:
        return source
    source[:2] += _front_axis(layout) * distance
    return source


def _connector_approach_waypoint(layout, current_item: dict[str, str], connector_point: np.ndarray) -> np.ndarray:
    extension = float(getattr(layout.cfg.routing, "connector_approach_extension", 0.0))
    connector = np.asarray(connector_point, dtype=float).copy()
    if extension <= 0.0:
        return connector

    fixture = str(current_item["fixture"])
    center = layout.fixture_pos(fixture, z=float(layout.cfg.rope.z))
    direction = connector[:2] - center[:2]
    norm = float(np.linalg.norm(direction))
    if norm <= 1e-8:
        return connector

    point = connector.copy()
    point[:2] += extension * direction / norm
    return point


def _side_corridor_point(layout, source_point: np.ndarray, item: dict[str, str]) -> np.ndarray:
    fixture = str(item["fixture"])
    relation = str(item["relation"])
    source = np.asarray(source_point, dtype=float).copy()
    if layout.fixture_type(fixture) != "peg" or relation not in {"left", "right", "above", "below"}:
        return source

    center = layout.fixture_pos(fixture, z=float(layout.cfg.rope.z))
    radius = _route_radius(layout, fixture, endpoint_path=True)
    approach_scale = float(getattr(layout.cfg.routing, "peg_approach_scale", 1.15))
    axis = _relation_axis(relation)
    if abs(float(axis[0])) > abs(float(axis[1])):
        source[0] = center[0] + axis[0] * radius * approach_scale
    else:
        source[1] = center[1] + axis[1] * radius * approach_scale
    return source


def _transition_waypoints(
    layout,
    source_point: np.ndarray,
    current_item: dict[str, str],
    next_item: dict[str, str],
) -> list[np.ndarray]:
    next_fixture = str(next_item["fixture"])
    next_relation = str(next_item["relation"])
    source = np.asarray(source_point, dtype=float)
    # If this peg already inserted an explicit front-pull waypoint, that point
    # is the desired departure. Do not snap back to the peg side corridor, which
    # would undo the large forward sweep.
    if _front_pull_enabled(layout, str(current_item["fixture"])):
        side_exit = source.copy()
    else:
        side_exit = _side_corridor_point(layout, source, current_item)
    if layout.fixture_type(next_fixture) != "peg" or next_relation not in {"left", "right", "above", "below"}:
        route_point = layout.route_point(next_item)
        points = []
        if float(np.linalg.norm(side_exit[:2] - source[:2])) > 1e-6:
            points.append(side_exit)
        if layout.fixture_type(next_fixture) == "connector" and layout.fixture_type(str(current_item["fixture"])) == "peg":
            points.append(_connector_approach_waypoint(layout, current_item, route_point))
        else:
            points.append(_departure_waypoint(layout, side_exit, route_point))
        return points

    center = layout.fixture_pos(next_fixture, z=float(layout.cfg.rope.z))
    radius = _route_radius(layout, next_fixture, endpoint_path=True)
    approach_scale = float(getattr(layout.cfg.routing, "peg_approach_scale", 1.15))
    approach = center.copy()
    approach[:2] += _approach_axis_for_relation(next_relation) * radius * approach_scale

    corridor = side_exit.copy()
    corridor[:2] = np.array([side_exit[0], approach[1]], dtype=float)
    points = []
    if float(np.linalg.norm(side_exit[:2] - source[:2])) > 1e-6:
        points.append(side_exit)
    if float(np.linalg.norm(corridor[:2] - (points[-1] if points else source)[:2])) > 1e-6:
        points.append(corridor)
    points.append(approach)
    return points


def _manual_endpoint_oracle_targets(layout) -> list[tuple[str, np.ndarray, int | None, bool]] | None:
    waypoint_cfg = getattr(layout.cfg.routing, "endpoint_oracle_waypoints", None)
    if waypoint_cfg is None:
        return None

    targets: list[tuple[str, np.ndarray, int | None, bool]] = []
    wrap_steps = int(getattr(layout.cfg.routing, "wrap_steps_per_point", 24))
    for index, item in enumerate(waypoint_cfg, start=1):
        label = str(item.get("phase", f"redline_{index:02d}"))
        point = layout.route_point(item)
        steps_value = item.get("steps", wrap_steps)
        steps = None if steps_value is None else int(steps_value)
        lifted = bool(item.get("lifted", True))
        targets.append((label, point, steps, lifted))
    return targets


def _centripetal_catmull_rom(control, flags, per_seg: int) -> list[tuple[np.ndarray, bool]]:
    """Dense samples of a centripetal Catmull-Rom spline through ``control`` (xy) points.

    Centripetal (alpha=0.5) avoids the self-intersections/overshoot that uniform Catmull-Rom
    produces on unevenly spaced control points. Each output sample carries the ``flags`` value
    of the control point starting its segment (so lifted/lowered is preserved). The curve
    passes through every control point, so it keeps the (arm-safe, verified) manual shape while
    rounding the cusps out.
    """

    pts = [np.asarray(p, dtype=float)[:2] for p in control]
    if len(pts) < 3:
        return [(p, bool(f)) for p, f in zip(pts, flags)]
    padded = [pts[0] - (pts[1] - pts[0])] + pts + [pts[-1] + (pts[-1] - pts[-2])]
    alpha = 0.5
    out: list[tuple[np.ndarray, bool]] = []
    for i in range(1, len(padded) - 2):
        p0, p1, p2, p3 = padded[i - 1], padded[i], padded[i + 1], padded[i + 2]
        t0 = 0.0
        t1 = t0 + float(np.linalg.norm(p1 - p0)) ** alpha
        t2 = t1 + float(np.linalg.norm(p2 - p1)) ** alpha
        t3 = t2 + float(np.linalg.norm(p3 - p2)) ** alpha
        if t2 - t1 < 1e-9:
            continue
        seg_flag = bool(flags[i - 1])
        for s in range(per_seg):
            t = t1 + (t2 - t1) * (s / per_seg)
            a1 = ((t1 - t) * p0 + (t - t0) * p1) / (t1 - t0) if t1 - t0 > 1e-9 else p1
            a2 = ((t2 - t) * p1 + (t - t1) * p2) / (t2 - t1)
            a3 = ((t3 - t) * p2 + (t - t2) * p3) / (t3 - t2) if t3 - t2 > 1e-9 else p2
            b1 = ((t2 - t) * a1 + (t - t0) * a2) / (t2 - t0) if t2 - t0 > 1e-9 else a2
            b2 = ((t3 - t) * a2 + (t - t1) * a3) / (t3 - t1) if t3 - t1 > 1e-9 else a2
            out.append((((t2 - t) * b1 + (t - t1) * b2) / (t2 - t1), seg_flag))
    out.append((pts[-1], bool(flags[-1])))
    return out


def _smooth_route_targets(layout) -> list[tuple[str, np.ndarray, int | None, bool]]:
    """Smooth the proven manual ``endpoint_oracle_waypoints`` into a uniform-speed curve.

    A from-scratch circle around P2 cannot respect the robot arm's own volume (base is west,
    so wrapping P2's east sweeps the forearm over P2). The hand-authored waypoints already
    encode an arm-safe wrap (a big low loop that passes the forearm south of P2); this routes
    the free end through a centripetal Catmull-Rom fit of those points -> smooth (cusps rounded),
    uniform per-length steps (``smooth_speed``), same shape. ``smooth_arc_points`` = samples per
    manual segment.
    """

    routing = layout.cfg.routing
    z_world = float(layout.world_z(float(layout.cfg.rope.z)))
    speed = max(1e-5, float(getattr(routing, "smooth_speed", 0.0005)))
    per_seg = max(2, int(getattr(routing, "smooth_arc_points", 8)))

    waypoint_cfg = getattr(routing, "endpoint_oracle_waypoints", None)
    if waypoint_cfg is None:
        return []
    control = [np.asarray(layout.route_point(item), dtype=float)[:2] for item in waypoint_cfg]
    flags = [bool(item.get("lifted", True)) for item in waypoint_cfg]

    dense = _centripetal_catmull_rom(control, flags, per_seg)

    targets: list[tuple[str, np.ndarray, int | None, bool]] = []
    last_xy = control[0]
    total = len(dense)
    for index, (xy, lifted) in enumerate(dense):
        seg = float(np.linalg.norm(xy - last_xy))
        steps = max(8, int(round(seg / speed))) if seg > 1e-6 else 8
        label = "green_exit_to_C" if index == total - 1 else f"smooth_{index:03d}"
        targets.append((label, np.array([xy[0], xy[1], z_world], dtype=float), steps, bool(lifted)))
        last_xy = xy
    return targets


def _endpoint_oracle_targets(layout) -> list[tuple[str, np.ndarray, int | None, bool]]:
    """Resolve the target signature into an ordered free-end waypoint sequence.

    Each entry is ``(label, route_point, steps, is_wrap_target)``. ``route_point``
    is the raw task/world-space target (no endpoint-handle z-offset or execution
    lift applied yet); consumers add their own handle offset and wrap-lift the
    same way they already did before this function moved here.
    """

    if bool(getattr(layout.cfg.routing, "smooth_route", False)):
        return _smooth_route_targets(layout)

    manual_targets = _manual_endpoint_oracle_targets(layout)
    if manual_targets is not None:
        return manual_targets

    initial_polyline = layout.route_polyline("initial")
    current = np.asarray(initial_polyline[-1], dtype=float)
    targets: list[tuple[str, np.ndarray, int | None, bool]] = []
    wrap_steps = int(getattr(layout.cfg.routing, "wrap_steps_per_point", 24))
    signature = layout.target_signature().to_info()

    for item_index, item in enumerate(signature):
        fixture = str(item["fixture"])
        relation = str(item["relation"])
        route_point = layout.route_point(item)
        if layout.fixture_type(fixture) == "peg" and relation in {"left", "right", "above", "below"}:
            waypoints = _wrap_waypoints(layout, fixture, relation, current)
            for index, point in enumerate(waypoints, start=1):
                targets.append((f"wrap_{fixture}_{relation}_{index:02d}", point, wrap_steps, True))
            current = waypoints[-1]
            if _front_pull_enabled(layout, fixture):
                current = _front_pull_waypoint(layout, fixture, current)
                targets.append((f"front_pull_{fixture}_{relation}", current, wrap_steps, True))
            if item_index + 1 < len(signature):
                next_item = signature[item_index + 1]
                next_fixture = str(next_item["fixture"])
                for transition_index, transition in enumerate(
                    _transition_waypoints(layout, current, item, next_item),
                    start=1,
                ):
                    targets.append(
                        (
                            f"transition_{fixture}_to_{next_fixture}_{transition_index:02d}",
                            transition,
                            wrap_steps,
                            True,
                        )
                    )
                    current = transition
        else:
            label = "insert_at_C" if fixture == "C" else f"route_to_{fixture}_{relation}"
            targets.append((label, route_point, None, False))
            current = route_point
    return targets


@dataclass(frozen=True)
class CableRoutingRouteCommand:
    """One physically-grounded endpoint-drag route for the free cable end."""

    waypoint_count: int
    final_route_point_xyz: tuple[float, float, float]
    target_signature: tuple[tuple[str, str], ...]


def plan_cable_routing_endpoint_route(layout) -> tuple[CableRoutingRouteCommand, EpisodePlan]:
    """Resolve the configured target signature into an endpoint-drag waypoint plan.

    Waypoint positions are the raw route-point targets; the physical/oracle
    demos still add their own endpoint-handle z-offset and wrap-lift on top,
    exactly as before this logic moved out of the oracle demo file.
    """

    targets = _endpoint_oracle_targets(layout)
    waypoints = tuple(
        WaypointTarget.from_sequence(
            str(label),
            point,
            steps=None if steps is None else int(steps),
            lifted=bool(lifted),
            metadata={"entity": "cable_free_end_handle", "is_wrap_target": bool(lifted)},
        )
        for label, point, steps, lifted in targets
    )
    signature = tuple(
        (str(item["fixture"]), str(item["relation"]))
        for item in layout.target_signature().to_info()
    )
    command = CableRoutingRouteCommand(
        waypoint_count=len(waypoints),
        final_route_point_xyz=waypoints[-1].position if waypoints else (0.0, 0.0, 0.0),
        target_signature=signature,
    )
    subgoal = PlannedSubgoal(
        subgoal_id="cable_route_free_end_to_signature",
        kind="route_cable_endpoint",
        entity="cable_free_end_handle",
        target={
            "waypoint_count": command.waypoint_count,
            "final_route_point_xyz": command.final_route_point_xyz,
            "target_signature": command.target_signature,
        },
    )
    waypoint_plan = WaypointPlan(
        plan_id="cable_routing_endpoint_route",
        waypoints=waypoints,
        metadata={"planner": "cable_routing_endpoint_route"},
    )
    episode_plan = EpisodePlan(
        task_id="cable_routing",
        subgoals=(subgoal,),
        waypoint_plan=waypoint_plan,
        plan_id="cable_routing_endpoint_route",
        metadata={"waypoint_count": command.waypoint_count},
    )
    return command, episode_plan
