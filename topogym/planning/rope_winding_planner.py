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
    yaw_track: bool
    yaw_forward_points: int

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
        points_per_turn = max(4, int(cfg.arc_points_per_turn))
        forward = int(getattr(cfg, "yaw_forward_points", points_per_turn - 2))
        if not 1 <= forward < points_per_turn:
            raise ValueError(
                "winding.yaw_forward_points is how many of a turn's orbit points "
                f"the wrist tracks before it starts giving the travel back; it "
                f"must be in 1..{points_per_turn - 1}, got {forward}."
            )
        # The return has to fit in one waypoint's worth of wrist each step. Half a
        # turn is where the command breaks -- it is a quaternion and the
        # interpolation takes the short arc, so a bigger ask is executed as its
        # complement, in the wrong direction. That is not theory: on 2026-08-15 a
        # 270 degree throw ran as +96 and drove joint7 onto its stop for the rest
        # of the route. Fail here, at plan time, rather than ten minutes into a
        # GPU run.
        step_angle = 2.0 * np.pi / points_per_turn
        back = step_angle * forward / (points_per_turn - forward)
        if bool(getattr(cfg, "yaw_track", False)) and back >= MAX_WRIST_STEP:
            raise ValueError(
                f"winding.yaw_forward_points={forward} of {points_per_turn} asks "
                f"the wrist for {np.degrees(back):.0f} degrees in one waypoint "
                f"(limit {np.degrees(MAX_WRIST_STEP):.0f}). Lower it: the return "
                f"is spread over the remaining {points_per_turn - forward} points, "
                "so fewer forward points means a gentler return."
            )
        return cls(
            post=str(cfg.post),
            turns=turns,
            direction=chosen,
            wind_radius=float(cfg.wind_radius),
            wind_z_start=float(cfg.wind_z_start),
            climb_per_turn=float(cfg.climb_per_turn),
            arc_points_per_turn=points_per_turn,
            exit_extension=float(cfg.exit_extension),
            wind_speed=float(cfg.wind_speed),
            travel_speed=float(cfg.travel_speed),
            min_segment_steps=int(cfg.min_segment_steps),
            yaw_track=bool(getattr(cfg, "yaw_track", False)),
            yaw_forward_points=forward,
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


def settle_radius(layout, spec: WindingSpec) -> float:
    """Radius the rope's centreline settles at once it is wrapped on the post."""

    return float(layout.cfg.fixtures[spec.post].radius) + float(layout.cfg.rope.radius)


def taut_demand(layout, spec: WindingSpec, waypoints) -> tuple[float, str]:
    """Longest taut path the route ever asks the rope for, and the waypoint of it.

    Anchor to the post, plus whatever is already wrapped, plus post to wherever
    the plug is. One turn on the post eats ``2 pi * settle_radius`` -- 151 mm at
    this layout -- which is why the turn count and the rope's length are not
    independent, and why this lives beside the planner instead of being written
    out twice. `tests/check_rope_winding_geometry.py` turns it into the slack
    gate; the demo refuses to start a run outside that band.
    """

    center = post_center(layout, spec)
    anchor = np.asarray(
        layout.route_point({"fixture": "S", "relation": "center"}), dtype=float
    )
    per_turn = 2.0 * np.pi * settle_radius(layout, spec)
    labels = [str(waypoint.label) for waypoint in waypoints]
    orbit = [index for index, label in enumerate(labels) if label.startswith("wind_t")]
    worst, worst_label = 0.0, ""
    for index, label in enumerate(labels):
        if index in orbit:
            wound = (orbit.index(index) + 1) / spec.arc_points_per_turn
        elif orbit and index > orbit[-1]:
            wound = float(spec.turns)
        else:
            wound = 0.0
        point = np.asarray(waypoints[index].position, dtype=float)
        need = (
            float(np.linalg.norm(anchor[:2] - center[:2]))
            + wound * per_turn
            + float(np.linalg.norm(point[:2] - center[:2]))
        )
        if need > worst:
            worst, worst_label = need, label
    return worst, worst_label


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


#: Slack band the rope's spawn length has to land in: (length - taut demand) /
#: taut demand. Too much and the free span coils -- cable_routing's helix blew up
#: at 19% -- too little and the rope fights its anchor instead of laying onto the
#: post. The demand moves with `winding.turns`, so `rope.spawn_arc.sweep_deg` has
#: to move with it too; this is the pair both the offline gate and the demo check.
SLACK_BAND = (0.05, 0.15)

#: Largest wrist turn one waypoint may ask for, in radians -- a hard bound, not
#: a hint. The command is a quaternion and the interpolation takes the short arc
#: (`primitives/attachment.py` `slerp`), so anything at or past pi is executed as
#: its complement, in the wrong direction. 150 degrees leaves 30 of margin below
#: that. `WindingSpec.from_config` refuses a schedule that exceeds it.
MAX_WRIST_STEP = np.radians(150.0)

#: How far the wrist may roll either side of the pose it grasped in, in radians.
#: Franka joint7 travels +-2.8973 rad (166 deg) and the grasp does not land it
#: centred -- measured 2026-08-15, it started a run at -0.4296 rad, 25 degrees
#: off. What is left is the budget the whole schedule, phase included, has to fit
#: inside.
WRIST_BUDGET = np.radians(166.0 - 25.0)

#: Of that budget, how much is held back from the alignment phase as margin.
PHASE_MARGIN = np.radians(10.0)


def _wrap_to_pi(angle: float) -> float:
    return float(np.arctan2(np.sin(angle), np.cos(angle)))


def plan_rope_winding_route(
    layout, *, direction: str | None = None, plug_heading: float = 0.0
) -> tuple[RopeWindingRouteCommand, EpisodePlan]:
    """Wind the free end ``turns`` times around the post, then seat it in C.

    Phases: lift the plug off its spawn port -> pull radially in to the orbit
    entry (the rope comes to rest against the post here) -> ``turns`` full
    orbits, climbing ``climb_per_turn`` each, so a new turn lands beside the
    previous one rather than on top of it -> leave along the orbit tangent,
    which unloads the wrap before the pull toward C -> hover above the target
    zone -> straight down to set the plug on it.

    ``direction`` overrides the configured winding sense; the mirrored run is
    the task's contrast pair (same grasp, same placement, winding of the
    opposite sign).

    ``plug_heading`` is the compass angle the plug's axis points at the moment it
    is grasped, which is what the emitted ``yaw`` is an offset FROM. It is only
    knowable once the rope mesh exists, so it defaults to zero for callers that
    have no scene -- `tests/check_rope_winding_geometry.py` builds a config-only
    stand-in layout. Everything that default changes is the absolute phase; the
    shape of the wrist schedule, which is what the offline gate checks, does not
    move.
    """

    spec = WindingSpec.from_config(layout.cfg, direction=direction)
    center = post_center(layout, spec)
    plug_spawn = np.asarray(layout.route_polyline("initial")[-1], dtype=float)

    seat = np.asarray(
        layout.route_point({"fixture": "C", "relation": "endpoint"}), dtype=float
    )
    # Where the plug's origin ends up once it is set down. `z_offset` carries
    # the difference between the rope's route height and the plug's axis height
    # for whichever pose this task uses.
    seat[2] += float(layout.cfg.physical_handle.z_offset)
    hover_z = float(seat[2]) + float(
        getattr(layout.cfg.physical_handle, "insert_hover_lift", 0.035)
    )

    wind_z = layout.world_z(spec.wind_z_start)
    entry_angle = float(
        np.arctan2(plug_spawn[1] - center[1], plug_spawn[0] - center[0])
    )

    # (label, point, on_the_post, tool_roll, steps_override). Step counts
    # otherwise come from the distance actually travelled -- see the loop below.
    #
    # `tool_roll` is an offset from the grasp yaw, about the vertical, and the
    # WHOLE GRIPPER turns by it -- hand, plug and rope end together, so nothing
    # slides on the finger pads. That is the distinction from the 2026-08-12
    # attempt, which turned the plug alone inside stationary pads and wrung the
    # rope against them.
    #
    # Why turn at all: carried with a fixed wrist, the rope's bearing out of the
    # hand sweeps one full turn per orbit, and that sweep is what drags it across
    # the fingers (measured 2026-08-13: +2.04 turns over two orbits). Tracking
    # the orbit 1:1 holds the bearing still.
    #
    # Why it cannot just keep tracking: two turns ask for 720 degrees and joint7
    # has 332 (and the grasp starts it ~25 off centre). The sweep cannot be
    # removed -- only MOVED. The wrist tracks 1:1 for `yaw_forward_points` of each
    # turn, then hands all of it back over the remaining points.
    #
    # The handing back happens WHILE THE HAND IS ORBITING, not at a standstill,
    # and that is the whole point of the 2026-08-15 rework. Turning in place made
    # the plug's tip trace a closed circle 40 mm across (the plug is 39 mm long)
    # in the plane the rope lies in -- and the plug is `collision: false`, a
    # visual mesh that cannot push the rope aside. A closed sweep through a rope
    # threads it: `docs/debug/preview.png` is the resulting inner loop, and the
    # same throw wrung 0.6 turns into the rope between the plug's weld and the
    # finger pads it was pressed against (`runs/short_rope_1turn.log`,
    # `onset_phase=wind_t1_06_flick3`).
    #
    # Spread over a moving segment the hand travels 110 mm per orbit point while
    # the plug turns, so the tip traces an open trochoid rather than a closed
    # circle -- 110 mm against a 40 mm circle, a factor of 2.75 -- and the rope is
    # pushed along instead of threaded. The rate drops with it, 4.5 deg/step to
    # 1.1.
    targets: list[tuple[str, np.ndarray, bool, float, int | None]] = []

    per_turn = spec.arc_points_per_turn
    total_points = spec.turns * per_turn
    step_angle = 2.0 * np.pi / per_turn

    # Roll at each orbit point. Forward at 1:1, then back at whatever rate clears
    # the accumulated travel over the points that are left, so each turn ends the
    # wrist where it began. Built from a zero base, then centred so the wrist
    # works both sides of the pose it grasped in rather than running off one end.
    forward = spec.yaw_forward_points
    back = -spec.sign * step_angle * forward / (per_turn - forward)
    rolls: list[float] = []
    roll = 0.0
    for index in range(1, total_points + 1):
        point_index = (index - 1) % per_turn + 1
        # The return's only payoff is the tracking that FOLLOWS it, so the last
        # turn does not get one -- it holds instead. On a one-turn run those two
        # points were pure cost: `winding` already reads +1.000 when they start,
        # and giving the travel back swept the plug's alignment through a whole
        # turn, past fully-backwards, which is what dragged the rope up into the
        # jaw (`runs/rolling_return_1turn.log`, `intrusion` 51 -> 190 -> 47).
        # Holding drifts the alignment to 90 degrees instead of sweeping 360.
        #
        # The old flick schedule made the same call for the same reason and this
        # was lost when the flicks were replaced; hence the check in tests/.
        last_turn = (index - 1) // per_turn == spec.turns - 1
        if not spec.yaw_track:
            roll = 0.0
        elif point_index <= forward:
            roll += spec.sign * step_angle
        elif not last_turn:
            roll += back
        rolls.append(roll)
    centre = 0.5 * (max(rolls + [0.0]) + min(rolls + [0.0]))
    rolls = [value - centre for value in rolls]
    base_roll = -centre

    # Where the plug SHOULD point, and how far off the schedule above leaves it.
    #
    # The rope leaves the settled wrap tangentially and then runs straight to the
    # plug, so it arrives `lead` ahead of the outward radius -- NOT along the
    # tangent. With the orbit at 3.1x the settled radius that is only 18.7
    # degrees off pointing straight at the post. The plug's cap has to face back
    # down that span; `connector_mesh` is a solid body of revolution with no
    # cable hole, so the rope enters through the plug's SIDE for every degree of
    # misalignment, which is what the interpenetration looks like on screen.
    settle_radius = float(layout.cfg.fixtures[spec.post].radius) + float(
        layout.cfg.rope.radius
    )
    lead = spec.sign * float(np.arcsin(min(1.0, settle_radius / spec.wind_radius)))

    # The error is constant through the forward stretch and sweeps a whole turn
    # during the return, so there is nothing to centre: put the forward stretch
    # -- most of the orbit, and the part that lays rope onto the post -- exactly
    # on zero, and let the return pass through wherever it must. (Centring the
    # min and max, which is what this did while the schedule was made of discrete
    # flick levels, would push the forward stretch 90 degrees off.)
    # `plug_heading` is the compass angle the rope ARRIVES on, and the plug's bore
    # is antiparallel to it (the cap swallows the cable, the pin sticks out the
    # far side -- `grasp_geometry` reads `axis_vs_rope_deg=180`). Both sides of
    # the difference below carry that pi, so neither needs it written down: the
    # target direction for the bore is `azimuth + pi + lead`, and the bore itself
    # is `plug_heading + pi + roll`.
    errors = [
        plug_heading
        + rolls[index]
        - (entry_angle + spec.sign * step_angle * (index + 1))
        - lead
        for index in range(total_points)
    ]
    #
    # The phase is a free additive constant on every roll, so it slides the whole
    # band -- and the band is already nearly as wide as the wrist has room for.
    # Aim as far toward alignment as the budget allows and no further: with
    # `yaw_forward_points=6` the band is +-135 of a +-141 budget, so only 6
    # degrees of the phase survive, and the forward stretch settles wherever that
    # leaves it. It stays acute, which is what governs whether the rope enters
    # the plug's cap or its side; exact alignment is a luxury the joint cannot
    # afford at this f. Fewer forward points buy it back (f=5 leaves 28 degrees).
    #
    # Without the clamp this read +227 degrees of roll on a one-turn plan -- the
    # arm would have hit the stop, which is the failure this whole schedule
    # exists to avoid.
    # Keep a margin rather than spending the budget down to the last degree:
    # aiming the plug is a nicety, hitting joint7's stop is a dead run (it
    # happened on 2026-08-15 and cost the last six waypoints of the route).
    # `base_roll` is the low end of the band -- it is what `wind_entry` pre-rolls
    # to -- so the room has to be measured over it as well. Measuring `rolls`
    # alone read the band as 112 degrees wide on a one-turn plan (where the last
    # turn holds and so never reaches the low end) and let the phase push the
    # schedule to 154 of a 141 budget.
    band = max(abs(value) for value in rolls + [base_roll])
    room = max(0.0, float(WRIST_BUDGET - band) - PHASE_MARGIN)
    phase = float(np.clip(-_wrap_to_pi(errors[0]), -room, room))
    rolls = [value + phase for value in rolls]
    base_roll += phase

    targets.append(
        # Straight up out of the spawn port, before any lateral pull.
        #
        # Roll 0: the wrist holds the pose it grasped in. It used to take
        # `base_roll` here, which asked for the whole pre-roll during a 35 mm
        # vertical move -- 40 steps, the segment floor. At the [4, 8] schedule's
        # -90 degrees that survived; at [6, 8]'s -132 it did not, and the run of
        # 2026-08-15 ended on waypoint 1 with the plug dragged 10 mm THROUGH the
        # board (`handle_z_above` +0.031 -> -0.010, follow_error 0.0454 over a
        # 0.0450 limit). The pre-roll belongs on the long travel below, which is
        # what the comment there always claimed.
        (
            "lift_from_port",
            np.array([plug_spawn[0], plug_spawn[1], wind_z], dtype=float),
            False,
            0.0,
            None,
        )
    )
    targets.append(
        # Radially in at a constant bearing: the rope lays itself against the
        # post without yet changing winding. The wrist pre-rolls to the start of
        # its band here, on a long travel segment, well before the first orbit.
        (
            "wind_entry",
            _orbit_point(center, spec.wind_radius, entry_angle, wind_z),
            False,
            base_roll,
            None,
        )
    )

    for index in range(1, total_points + 1):
        angle = entry_angle + spec.sign * step_angle * index
        z = layout.world_z(
            spec.wind_z_start + spec.climb_per_turn * (index / per_turn)
        )
        turn_index = (index - 1) // per_turn + 1
        point_index = (index - 1) % per_turn + 1
        point = _orbit_point(center, spec.wind_radius, angle, z)
        label = f"wind_t{turn_index}_{point_index:02d}"
        targets.append((label, point, True, rolls[index - 1], None))

    last_angle = entry_angle + spec.sign * step_angle * total_points
    last_point = targets[-1][1]
    # Tangent of the orbit at the final angle, in the travel direction.
    tangent = spec.sign * np.array(
        [-float(np.sin(last_angle)), float(np.cos(last_angle)), 0.0], dtype=float
    )
    # The wrist locks once the orbit is over. Everything after this point --
    # tangent exit, travel, setting down -- holds the last roll. Turning it back
    # to the grasp pose would look tidier and would wring another quarter turn
    # into a rope that is already wound and can no longer pay it out anywhere.
    hold_roll = targets[-1][3]
    targets.append(
        ("wind_exit", last_point + spec.exit_extension * tangent, False, hold_roll, None)
    )
    targets.append(
        ("to_C_hover", np.array([seat[0], seat[1], hover_z], dtype=float), False, hold_roll, None)
    )
    targets.append(("place_at_C", seat.copy(), False, hold_roll, None))

    # Uniform commanded speed: steps = distance / speed. Two speeds, because the
    # two halves of the route are not equally delicate -- on the post the rope is
    # being dragged into new contact and has to keep up; off it the rope just
    # trails the plug. A single step count per waypoint cannot express this: the
    # segments here differ by 5x in length.
    waypoints = []
    previous = plug_spawn
    for label, point, on_post, tool_roll, steps_override in targets:
        distance = float(np.linalg.norm(point - previous))
        speed = spec.wind_speed if on_post else spec.travel_speed
        steps = (
            int(steps_override)
            if steps_override is not None
            else max(spec.min_segment_steps, int(round(distance / max(speed, 1e-9))))
        )
        waypoints.append(
            WaypointTarget.from_sequence(
                label,
                point,
                steps=steps,
                # Tool roll relative to the grasp yaw, not an absolute heading:
                # the grasp yaw is the plug's, and the scene decides it at spawn.
                yaw=tool_roll if spec.yaw_track else None,
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
