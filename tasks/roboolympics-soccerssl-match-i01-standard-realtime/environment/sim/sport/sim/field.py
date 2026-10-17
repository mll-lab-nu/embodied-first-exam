"""The Division B field of the SSL rulebook (RoboCup SSL rules, 2026-09-19, ssl-rules commit 2ff4be0c), its geometry
helpers for the referee, and `build_scene()` that puts the field, the ball and the robots into a mujoco.MjSpec.

Dimensions (rulebook §2.1, figures 2 and 4; line-centre distances, lines 0.01 m wide, a line belongs to the areas it
bounds, §2.1.3):
- field of play 9 x 6 m (§2.1.1, Division B), the halfway line x = 0, the goal-to-goal line y = 0;
- field margin 0.3 m on all sides from the field lines to the surrounding walls (§2.1.2, Division B); the carpet
  continues at least 0.7 m beyond the field lines (10.4 x 7.4 m, §2.1.1-2.1.2);
- walls 0.1 m high: the rulebook before 2026-02-25 (ssl-rules commit db471f1^, §2.1.2: "a 0.1 meters tall black wall");
  the current text keeps the walls and no longer gives the height. Thickness 0.05 m: ESTIMATE (outside the margin, it
  touches nothing in play);
- centre circle diameter 1 m (§2.1.3.4); defense areas 2 m (along the goal line) x 1 m (deep) (§2.1.3.5);
  penalty marks 6 m from the opponent goal centre, on the goal-to-goal line (§2.1.3.6), i.e. x = -+1.5;
- goals (§2.1.4, figure 4): inner width 1 m, inner depth 0.18 m, walls 0.16 m high and 0.02 m thick, touching the goal
  line from outside (from x = 4.505); the side walls extend to the outside wall; inner faces white and covered with an
  energy absorbing material (here an over-damped contact, solref (-5000, -300): a 3 m/s ball rebounds at about 5 %, a 6.5 m/s ball at about 14 % and sinks 1.4 cm into the 2 cm wall; ESTIMATE, no published value), outer faces black;
- carpet: green felt (§2.1.2); its contact with the ball is the ball's (ball.py).

Coordinates: world frame of frames.py (origin at the centre, x along the length).
"""

from __future__ import annotations

import math
import os
import sys

from . import ball as B

# ------------------------------------------------------------------------------------------------- dimensions
FIELD_LENGTH, FIELD_WIDTH = 9.0, 6.0
HALF_L, HALF_W = FIELD_LENGTH / 2, FIELD_WIDTH / 2
LINE_W = 0.01
MARGIN = 0.3  # field line -> wall (inner face), Division B
WALL_X, WALL_Y = HALF_L + MARGIN, HALF_W + MARGIN  # 4.8, 3.3
WALL_H, WALL_T = 0.10, 0.05
CARPET_X, CARPET_Y = HALF_L + 0.7, HALF_W + 0.7  # 5.2, 3.7 (10.4 x 7.4)
CENTER_R = 0.5
DA_DEPTH, DA_WIDTH = 1.0, 2.0
PENALTY_DIST = 6.0
GOAL_W, GOAL_D, GOAL_H, GOAL_T = 1.0, 0.18, 0.16, 0.02
GOAL_X0 = HALF_L + LINE_W / 2  # 4.505: the goal walls touch the line from outside
FOAM_T = 0.005  # the inner foam layer (inside the 0.02 m walls)
ROBOT_R = 0.09  # §2.1.3: distances from a robot use an assumed radius of 0.09 m
BALL_R = B.RADIUS

# The ball has fully crossed a field line when its centre is beyond the line's outer edge by a radius (§6, "fully
# crossing the field line"; lines belong to the field, §2.1.3).
OUT_X = HALF_L + LINE_W / 2 + BALL_R  # 4.5265
OUT_Y = HALF_W + LINE_W / 2 + BALL_R  # 3.0265


def defense_area(side: int):
    """the defense area at the goal x = side * 4.5 as (xmin, xmax, ymin, ymax), its lines included (§2.1.3)."""
    a, b = side * (HALF_L - DA_DEPTH), side * HALF_L
    h = LINE_W / 2
    return (min(a, b) - h, max(a, b) + h, -DA_WIDTH / 2 - h, DA_WIDTH / 2 + h)


def dist_to_rect(x: float, y: float, r) -> float:
    """distance from a point to a rectangle (0 inside)."""
    dx = max(r[0] - x, 0.0, x - r[1])
    dy = max(r[2] - y, 0.0, y - r[3])
    return math.hypot(dx, dy)


def point_in_rect(x: float, y: float, r) -> bool:
    return r[0] <= x <= r[1] and r[2] <= y <= r[3]


def robot_fully_inside(x: float, y: float, r, radius: float = ROBOT_R) -> bool:
    return r[0] + radius <= x <= r[1] - radius and r[2] + radius <= y <= r[3] - radius


def robot_touches_rect(x: float, y: float, r, radius: float = ROBOT_R) -> bool:
    """partially or fully inside (§8.4.2.1)."""
    return dist_to_rect(x, y, r) <= radius


def penalty_mark(attack: int):
    """the penalty mark from which a team attacking `attack` (+1 / -1) shoots: 6 m from the goal it attacks."""
    return (attack * (HALF_L - PENALTY_DIST), 0.0)


def in_goal(x: float, y: float, z: float):
    """+1 / -1 if the ball has fully entered the goal at x = +-4.5 between the posts (§7), else 0."""
    if abs(x) > OUT_X and abs(y) < GOAL_W / 2 and z < GOAL_H and abs(x) < GOAL_X0 + GOAL_D:
        return 1 if x > 0 else -1
    return 0


def outside_field(x: float, y: float) -> bool:
    return abs(x) > OUT_X or abs(y) > OUT_Y


def beyond_boundary(x: float, y: float) -> bool:
    """the ball has left the field boundary (past the walls' inner faces: §8.4.1.6 boundary crossing)."""
    return abs(x) > WALL_X + BALL_R or abs(y) > WALL_Y + BALL_R


# --------------------------------------------------------------------------------- free-kick placement positions
# Ported from the ssl-game-controller (internal/app/statemachine/placementPos.go, commit 45e4b3d, 2026-10-05) with its
# Division B geometry (internal/app/config/config.go): placement offsets 0.2 m from the touch and goal lines, 1.0 m from
# the goal line for a goal kick, 1.0 m from the defense area (rulebook §5.3.3: a free-kick position is valid with
# >= 0.2 m to all field lines and >= 1 m to either defense area; §6.1.1, §6.2.1-6.2.2).
PLACE_OFF_LINE, PLACE_OFF_GOALKICK, PLACE_OFF_DA = 0.2, 1.0, 1.0


def valid_free_kick_pos(x: float, y: float):
    """move a position into the field, out of the defense areas, and into the field again (placementPos.go
    validateLocation)."""

    def inside(x, y):
        mx, my = HALF_L - PLACE_OFF_LINE, HALF_W - PLACE_OFF_LINE
        return (math.copysign(min(abs(x), mx), x), math.copysign(min(abs(y), my), y))

    x, y = inside(x, y)
    max_x = HALF_L - DA_DEPTH - PLACE_OFF_DA
    min_y = DA_WIDTH / 2 + PLACE_OFF_DA
    if abs(x) > max_x and abs(y) < min_y:
        if abs(max_x - abs(x)) < abs(min_y - abs(y)):
            x = math.copysign(max_x, x)
        else:
            y = math.copysign(min_y, y if y != 0 else 1.0)
    return inside(x, y)


def throw_in_pos(x_cross: float, y_cross: float):
    """§6.1.1: 0.2 m inside the touch line where the ball crossed it, >= 0.2 m from the goal lines."""
    mx = HALF_L - PLACE_OFF_LINE
    x = math.copysign(min(abs(x_cross), mx), x_cross)
    return valid_free_kick_pos(x, math.copysign(HALF_W - PLACE_OFF_LINE, y_cross))


def goal_kick_pos(x_cross: float, y_cross: float):
    """§6.2.1: 0.2 m from the closest touch line and 1 m from the goal line."""
    return valid_free_kick_pos(
        math.copysign(HALF_L - PLACE_OFF_GOALKICK, x_cross),
        math.copysign(HALF_W - PLACE_OFF_LINE, y_cross if y_cross != 0 else 1.0),
    )


def corner_kick_pos(x_cross: float, y_cross: float):
    """§6.2.2: 0.2 m from the closest touch line and 0.2 m from the goal line."""
    return valid_free_kick_pos(
        math.copysign(HALF_L - PLACE_OFF_LINE, x_cross),
        math.copysign(HALF_W - PLACE_OFF_LINE, y_cross if y_cross != 0 else 1.0),
    )


# ------------------------------------------------------------------------------------------------ the MjSpec
GREEN = (0.13, 0.42, 0.18, 1.0)
WHITE = (0.95, 0.95, 0.95, 1.0)
BLACK = (0.05, 0.05, 0.05, 1.0)
VENUE = (0.35, 0.35, 0.37, 1.0)


def _repo_root():
    here = os.path.dirname(os.path.abspath(__file__))
    d = here
    for _ in range(5):
        d = os.path.dirname(d)
        if os.path.isdir(os.path.join(d, "bodies")):
            return d
    return None


def default_body():
    """the robot module: the library robot bodies/ssl_robot (line A; loaded through the library's registry,
    bodies.load_body, then its module for the batched fast path Group) when it is in the checkout or the task's
    simulator directory (sport.toml [body]), else the stand-in sim/stub_robot.py. RCB_SSL_BODY=stub forces the
    stand-in; RCB_SSL_BODY=library makes a missing library robot an error (the plugin sets it: a match never runs on
    the stand-in silently)."""
    want = os.environ.get("RCB_SSL_BODY", "")
    if want != "stub":
        root = _repo_root()
        if root and os.path.isfile(os.path.join(root, "bodies", "ssl_robot", "body.py")):
            if root not in sys.path:
                sys.path.insert(0, root)
            from bodies import load_body  # noqa: PLC0415

            return sys.modules[type(load_body("ssl_robot")).__module__]
        if want == "library":
            raise ImportError("bodies/ssl_robot is not in this checkout (sport.toml [body] copies it into a task)")
    from . import stub_robot

    return stub_robot


def _box(parent, name, center, half, rgba, collide=True, priority=0, solref=None, friction=None, group=0):
    import mujoco

    kw = dict(
        name=name, type=mujoco.mjtGeom.mjGEOM_BOX, pos=list(center), size=list(half), rgba=list(rgba), group=group
    )
    if not collide:
        kw.update(contype=0, conaffinity=0)
    if priority:
        kw["priority"] = priority
    if solref is not None:
        kw["solref"] = list(solref)
    if friction is not None:
        kw["friction"] = list(friction)
    return parent.add_geom(**kw)


def _lines(wb):
    """the white field markings (visual only: they do not touch anything)."""
    z, hz, h = 0.0006, 0.0005, LINE_W / 2
    names = []

    def seg(name, x0, y0, x1, y1):
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        length = math.hypot(x1 - x0, y1 - y0)
        import mujoco

        g = wb.add_geom(
            name=name,
            type=mujoco.mjtGeom.mjGEOM_BOX,
            pos=[cx, cy, z],
            size=[length / 2 + h, h, hz],
            rgba=list(WHITE),
            contype=0,
            conaffinity=0,
            group=1,
        )
        g.quat = [math.cos(math.atan2(y1 - y0, x1 - x0) / 2), 0, 0, math.sin(math.atan2(y1 - y0, x1 - x0) / 2)]
        names.append(name)

    seg("line_touch_pos", -HALF_L, HALF_W, HALF_L, HALF_W)
    seg("line_touch_neg", -HALF_L, -HALF_W, HALF_L, -HALF_W)
    seg("line_goal_pos", HALF_L, -HALF_W, HALF_L, HALF_W)
    seg("line_goal_neg", -HALF_L, -HALF_W, -HALF_L, HALF_W)
    seg("line_halfway", 0, -HALF_W, 0, HALF_W)
    seg("line_goal_to_goal", -HALF_L, 0, HALF_L, 0)
    n = 48
    for i in range(n):
        a0, a1 = 2 * math.pi * i / n, 2 * math.pi * (i + 1) / n
        seg(
            f"line_circle_{i}",
            CENTER_R * math.cos(a0),
            CENTER_R * math.sin(a0),
            CENTER_R * math.cos(a1),
            CENTER_R * math.sin(a1),
        )
    for s, tag in ((1, "pos"), (-1, "neg")):
        xf = s * (HALF_L - DA_DEPTH)
        seg(f"line_da_front_{tag}", xf, -DA_WIDTH / 2, xf, DA_WIDTH / 2)
        seg(f"line_da_left_{tag}", xf, DA_WIDTH / 2, s * HALF_L, DA_WIDTH / 2)
        seg(f"line_da_right_{tag}", xf, -DA_WIDTH / 2, s * HALF_L, -DA_WIDTH / 2)
        px, _ = penalty_mark(-s)  # the mark from which the goal at s * 4.5 is attacked
        seg(f"line_penalty_mark_{tag}", px - 0.01, 0, px + 0.01, 0)
    return names


def _walls_and_goals(wb):
    walls, goals, foam = [], [], []
    t, hh = WALL_T / 2, WALL_H / 2
    lx, ly = WALL_X + WALL_T, WALL_Y + WALL_T
    for name, c, hs in (
        ("wall_pos_x", (WALL_X + t, 0, hh), (t, ly, hh)),
        ("wall_neg_x", (-WALL_X - t, 0, hh), (t, ly, hh)),
        ("wall_pos_y", (0, WALL_Y + t, hh), (lx, t, hh)),
        ("wall_neg_y", (0, -WALL_Y - t, hh), (lx, t, hh)),
    ):
        _box(wb, name, c, hs, BLACK)
        walls.append(name)
    gh = GOAL_H / 2
    side_len = WALL_X - GOAL_X0  # the side walls run from the goal line to the outside wall
    for s, tag in ((1, "pos"), (-1, "neg")):
        for ys, ytag in ((1, "l"), (-1, "r")):
            # structural black wall behind a white foam layer facing the goal mouth
            yb = ys * (GOAL_W / 2 + FOAM_T + (GOAL_T - FOAM_T) / 2)
            _box(
                wb,
                f"goal_{tag}_side_{ytag}",
                (s * (GOAL_X0 + side_len / 2), yb, gh),
                (side_len / 2, (GOAL_T - FOAM_T) / 2, gh),
                BLACK,
            )
            goals.append(f"goal_{tag}_side_{ytag}")
            _box(
                wb,
                f"goal_{tag}_foam_side_{ytag}",
                (s * (GOAL_X0 + GOAL_D / 2), ys * (GOAL_W / 2 + FOAM_T / 2), gh),
                (GOAL_D / 2, FOAM_T / 2, gh),
                WHITE,
                priority=2,
                solref=(-5000.0, -300.0),
                friction=(B.MU_SLIDE, 0.005, 0.0001),
            )
            foam.append(f"goal_{tag}_foam_side_{ytag}")
        _box(
            wb,
            f"goal_{tag}_back",
            (s * (GOAL_X0 + GOAL_D + FOAM_T + (GOAL_T - FOAM_T) / 2), 0, gh),
            ((GOAL_T - FOAM_T) / 2, GOAL_W / 2 + GOAL_T, gh),
            BLACK,
        )
        goals.append(f"goal_{tag}_back")
        _box(
            wb,
            f"goal_{tag}_foam_back",
            (s * (GOAL_X0 + GOAL_D + FOAM_T / 2), 0, gh),
            (FOAM_T / 2, GOAL_W / 2, gh),
            WHITE,
            priority=2,
            solref=(-5000.0, -300.0),
            friction=(B.MU_SLIDE, 0.005, 0.0001),
        )
        foam.append(f"goal_{tag}_foam_back")
    return walls, goals, foam


def build_scene(n_per_team: int = 5, seed: int = 0, body=None, poses=None, lod: str = "sim"):
    """The field (carpet, lines, walls, goals), the ball and n_per_team robots per team into a new mujoco.MjSpec.

    poses: {(team, number): (x, y, yaw)} in the world frame (default: world.kickoff_formation for half 1, blue kicks
    off, seeded jitter). body: the robot module with mount(spec, name, team, number, pose, lod) (default_body()).
    Returns (spec, handles): handles = {"field": {...}, "ball": {...}, "robots": {(team, number): mount handles},
    "body": the robot module}."""
    import mujoco

    body = body or default_body()
    spec = mujoco.MjSpec()
    spec.modelname = "soccer_ssl"
    o = spec.option
    o.timestep = 0.001  # interfaces v1 §2: 1 ms physics steps
    o.integrator = mujoco.mjtIntegrator.mjINT_IMPLICITFAST
    o.cone = mujoco.mjtCone.mjCONE_ELLIPTIC  # ball.py: rolling without residual slip
    o.impratio = 10
    spec.visual.global_.offwidth, spec.visual.global_.offheight = 1920, 1080
    wb = spec.worldbody
    wb.add_geom(
        name="venue_floor",
        type=mujoco.mjtGeom.mjGEOM_PLANE,
        pos=[0, 0, -0.002],
        size=[12, 9, 0.1],
        rgba=list(VENUE),
        contype=0,
        conaffinity=0,
        group=1,
    )
    wb.add_geom(
        name="carpet",
        type=mujoco.mjtGeom.mjGEOM_PLANE,
        size=[CARPET_X, CARPET_Y, 0.1],
        rgba=list(GREEN),
        condim=3,
        friction=[1.0, 0.005, 0.0001],
    )
    # even venue lighting (line C, docs/screening/soccer_ssl/render/README.md: a spot light's falloff and the carpet's
    # highlight darken the id dots in the corners: 56 % of the ids read instead of 100 %): one shadowless directional
    # light, a matte carpet, planes drawn as one grid cell (render only). Visual only: no contact or physics changes.
    wb.add_light(
        name="light_main",
        pos=[0, 0, 6],
        dir=[0, 0, -1],
        diffuse=[0.8, 0.8, 0.8],
        castshadow=False,
        type=mujoco.mjtLightType.mjLIGHT_DIRECTIONAL,
    )
    spec.add_material(name="carpet_matte", rgba=list(GREEN), specular=0.0, shininess=0.0)
    spec.geom("carpet").material = "carpet_matte"
    for name in ("venue_floor", "carpet"):
        g = spec.geom(name)
        g.size = [g.size[0], g.size[1], 2.0 * max(g.size[0], g.size[1])]
    lines = _lines(wb)
    walls, goals, foam = _walls_and_goals(wb)
    ball_h = B.add_ball(spec)
    if poses is None:
        from .world import kickoff_formation

        poses = kickoff_formation(n_per_team, seed, half=1, kicking="blue")
    robots = {}
    for (team, number), pose in sorted(poses.items()):
        robots[(team, number)] = body.mount(spec, f"{team}{number}", team, number, tuple(pose), lod=lod)
    field = dict(
        carpet="carpet",
        lines=lines,
        walls=walls,
        goals=goals,
        goal_foam=foam,
        half_length=HALF_L,
        half_width=HALF_W,
        wall_x=WALL_X,
        wall_y=WALL_Y,
        goal_width=GOAL_W,
        goal_depth=GOAL_D,
        goal_height=GOAL_H,
        defense_area=(DA_DEPTH, DA_WIDTH),
        center_radius=CENTER_R,
    )
    return spec, dict(field=field, ball=ball_h, robots=robots, body=body)
