"""Endpoint oracle for Rope Winding: a helix around one post, then placement.

Unlike the cable_routing planner, waypoint positions here are ABSOLUTE world
targets for the plug (the demo passes them to the drag primitive unchanged).
Cable's route-point convention -- planar points at rope height, with the demo
adding a handle z-offset and a wrap lift -- cannot express a helix, whose whole
point is that z is a function of the winding angle.

`WindingSpec` and the post geometry live here rather than beside the criterion
because supervision already depends on planning (see
`supervision/cable_routing.py`), and the dependency has to run one way. The
verifier imports them, so the sign convention -- which way is a positive turn,
the whole basis of this task's contrast pair -- is stated once and measured
against itself.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .subgoal import PlannedSubgoal
from .waypoint import EpisodePlan, WaypointPlan, WaypointTarget

_DIRECTION_SIGNS = {"ccw": 1.0, "cw": -1.0}


@dataclass(frozen=True)
class WindingSpec:
    """The `task.winding` block, as planner and verifier both read it."""

    post: str
    turns: int
    direction: str
    wind_radius: float
    wind_z_start: float
    climb_per_turn: float
    arc_points_per_turn: int
    exit_extension: float
    wind_speed: float
    travel_speed: float
    min_segment_steps: int

    @classmethod
    def from_config(cls, task_cfg, *, direction: str | None = None) -> "WindingSpec":
        cfg = getattr(task_cfg, "winding", None)
        if cfg is None:
            raise ValueError("rope_winding task config requires a `winding` block.")
        chosen = str(direction if direction is not None else cfg.direction).lower()
        if chosen not in _DIRECTION_SIGNS:
            raise ValueError(
                f"winding.direction must be one of {sorted(_DIRECTION_SIGNS)}, "
                f"got {chosen!r}."
            )
        turns = int(cfg.turns)
        if turns < 1:
            raise ValueError(f"winding.turns must be >= 1, got {turns}.")
        return cls(
            post=str(cfg.post),
            turns=turns,
            direction=chosen,
            wind_radius=float(cfg.wind_radius),
            wind_z_start=float(cfg.wind_z_start),
            climb_per_turn=float(cfg.climb_per_turn),
            arc_points_per_turn=max(4, int(cfg.arc_points_per_turn)),
            exit_extension=float(cfg.exit_extension),
            wind_speed=float(cfg.wind_speed),
            travel_speed=float(cfg.travel_speed),
            min_segment_steps=int(cfg.min_segment_steps),
        )

    @property
    def sign(self) -> float:
        """+1 for counter-clockwise seen from +z, -1 for clockwise."""

        return _DIRECTION_SIGNS[self.direction]

    @property
    def target_winding(self) -> float:
        """Signed winding number a successful episode must reach."""

        return self.sign * float(self.turns)


def post_center(layout, spec: WindingSpec) -> np.ndarray:
    """World position of the winding post's axis, at the rope's spawn height."""

    return layout.fixture_pos(spec.post, z=float(layout.cfg.rope.z))


def post_top_z(layout, spec: WindingSpec) -> float:
    """World z of the post's top -- the only gateway that changes winding."""

    fixture = layout.cfg.fixtures[spec.post]
    return layout.world_z(float(fixture.pos[2]) + 0.5 * float(fixture.height))


def _orbit_point(center: np.ndarray, radius: float, angle: float, z: float) -> np.ndarray:
    return np.array(
        [
            float(center[0]) + radius * float(np.cos(angle)),
            float(center[1]) + radius * float(np.sin(angle)),
            float(z),
        ],
        dtype=float,
    )


@dataclass(frozen=True)
class RopeWindingRouteCommand:
    """One winding route: how many turns, which way, and where it ends."""

    waypoint_count: int
    turns: int
    direction: str
    target_winding: float
    final_route_point_xyz: tuple[float, float, float]


def plan_rope_winding_route(
    layout, *, direction: str | None = None
) -> tuple[RopeWindingRouteCommand, EpisodePlan]:
    """Wind the free end ``turns`` times around the post, then seat it in C.

    Phases: lift the plug off its spawn port -> pull radially in to the orbit
    entry (the rope comes to rest against the post here) -> ``turns`` full
    orbits, climbing ``climb_per_turn`` each, so a new turn lands beside the
    previous one rather than on top of it -> leave along the orbit tangent,
    which unloads the wrap before the pull toward C -> hover above the target
    port -> straight down into it.

    ``direction`` overrides the configured winding sense; the mirrored run is
    the task's contrast pair (same grasp, same placement, winding of the
    opposite sign).
    """

    spec = WindingSpec.from_config(layout.cfg, direction=direction)
    center = post_center(layout, spec)
    plug_spawn = np.asarray(layout.route_polyline("initial")[-1], dtype=float)

    seat = np.asarray(
        layout.route_point({"fixture": "C", "relation": "endpoint"}), dtype=float
    )
    # The plug's origin sits `physical_handle.z_offset` above the route height
    # when seated (flush-port rim + grasp-column half height).
    seat[2] += float(layout.cfg.physical_handle.z_offset)
    hover_z = float(seat[2]) + float(
        getattr(layout.cfg.physical_handle, "insert_hover_lift", 0.035)
    )

    wind_z = layout.world_z(spec.wind_z_start)
    entry_angle = float(
        np.arctan2(plug_spawn[1] - center[1], plug_spawn[0] - center[0])
    )

    # (label, point, on_the_post). Step counts come afterwards, from the
    # distance actually travelled -- see the loop below.
    #
    # Nothing here turns the plug. Carrying it around the post without turning
    # it does wind one turn of twist into the rope per orbit, but the cure is at
    # the rope's end, not the plug's: `rope.fem.follow_swivel` lets the end spin
    # inside the plug. Turning the plug instead was tried on 2026-08-12 and made
    # the rope tangle with the gripper worse -- the rope end is welded to the
    # plug, so turning the plug wrings the rope against stationary finger pads.
    targets: list[tuple[str, np.ndarray, bool]] = [
        # Straight up out of the spawn port, before any lateral pull.
        (
            "lift_from_port",
            np.array([plug_spawn[0], plug_spawn[1], wind_z], dtype=float),
            False,
        ),
        # Radially in at a constant bearing: the rope lays itself against the
        # post without yet changing winding.
        ("wind_entry", _orbit_point(center, spec.wind_radius, entry_angle, wind_z), False),
    ]

    per_turn = spec.arc_points_per_turn
    total_points = spec.turns * per_turn
    step_angle = 2.0 * np.pi / per_turn
    for index in range(1, total_points + 1):
        angle = entry_angle + spec.sign * step_angle * index
        z = layout.world_z(
            spec.wind_z_start + spec.climb_per_turn * (index / per_turn)
        )
        turn_index = (index - 1) // per_turn + 1
        point_index = (index - 1) % per_turn + 1
        targets.append(
            (
                f"wind_t{turn_index}_{point_index:02d}",
                _orbit_point(center, spec.wind_radius, angle, z),
                True,
            )
        )

    last_angle = entry_angle + spec.sign * step_angle * total_points
    last_point = targets[-1][1]
    # Tangent of the orbit at the final angle, in the travel direction.
    tangent = spec.sign * np.array(
        [-float(np.sin(last_angle)), float(np.cos(last_angle)), 0.0], dtype=float
    )
    targets.append(("wind_exit", last_point + spec.exit_extension * tangent, False))
    targets.append(
        ("to_C_hover", np.array([seat[0], seat[1], hover_z], dtype=float), False)
    )
    targets.append(("insert_at_C", seat.copy(), False))

    # Uniform commanded speed: steps = distance / speed. Two speeds, because the
    # two halves of the route are not equally delicate -- on the post the rope is
    # being dragged into new contact and has to keep up; off it the rope just
    # trails the plug. A single step count per waypoint cannot express this: the
    # segments here differ by 5x in length.
    waypoints = []
    previous = plug_spawn
    for label, point, on_post in targets:
        distance = float(np.linalg.norm(point - previous))
        speed = spec.wind_speed if on_post else spec.travel_speed
        steps = max(spec.min_segment_steps, int(round(distance / max(speed, 1e-9))))
        waypoints.append(
            WaypointTarget.from_sequence(
                label,
                point,
                steps=steps,
                metadata={
                    "entity": str(layout.cfg.rope.endpoint_handle.name),
                    "is_wind_target": bool(on_post),
                },
            )
        )
        previous = point
    waypoints = tuple(waypoints)
    command = RopeWindingRouteCommand(
        waypoint_count=len(waypoints),
        turns=spec.turns,
        direction=spec.direction,
        target_winding=spec.target_winding,
        final_route_point_xyz=waypoints[-1].position,
    )
    subgoal = PlannedSubgoal(
        subgoal_id="rope_wind_free_end_around_post",
        kind="wind_rope_endpoint",
        entity=str(layout.cfg.rope.endpoint_handle.name),
        target={
            "post": spec.post,
            "turns": spec.turns,
            "direction": spec.direction,
            "target_winding": spec.target_winding,
            "final_route_point_xyz": command.final_route_point_xyz,
        },
    )
    waypoint_plan = WaypointPlan(
        plan_id="rope_winding_endpoint_route",
        waypoints=waypoints,
        metadata={"planner": "rope_winding_endpoint_route", "direction": spec.direction},
    )
    episode_plan = EpisodePlan(
        task_id="rope_winding",
        subgoals=(subgoal,),
        waypoint_plan=waypoint_plan,
        plan_id="rope_winding_endpoint_route",
        metadata={
            "waypoint_count": command.waypoint_count,
            "turns": spec.turns,
            "direction": spec.direction,
        },
    )
    return command, episode_plan
