"""The robot soccer scene (MuJoCo 3.3.7): a pitch with two goals, a ball and 2 x N Booster T1 lower bodies.

No torch here: the render workers and the (external) broadcast renderer build the same model from this file alone.

Team size N (SOCCER_TEAM_SIZE, 2 or 5) picks the pitch (PITCHES):
  N = 2   the compact 10 x 7 m pitch with boards on the touchlines and goal lines (the earlier 2 v 2 tasks);
  N = 5   the RoboCup HSL 2026 M-Field (14 x 9 m, Large Division goals), no boards: a 1.5 m border strip (the
          "carpet") around the lines; the ball leaving the field is restarted by the referee (kick-in, goal kick,
          corner kick) and a robot leaving the carpet is penalized (soccer.py).

World frame (metres): x along the pitch, team A attacks +x (team B's goal at x = +HALF_L), team B attacks -x; y to
team A's left; z up. Each team's own frame is the world frame for A and the world turned 180 degrees about z for B, so
every team attacks +x in its own frame.

Robots: the Booster T1 lower body of sai-mujoco 0.1.30 (MIT, ArenaX Labs; copied into the image at $RCB_T1_ASSETS),
2 N copies with the prefixes A1: ... AN: B1: ... BN:. Their collision geometry (trunk box, leg cylinders, foot boxes)
collides with the other robots, the ball, the goals, the boards and the floor; contact friction and the floor's contact
model are the values of sai-mujoco's football scene after its reset with seed 0 (floor friction 0.4815, solimp
0 0.95 0.001 0.5 2), as in the earlier soccer tasks. Head camera: 0.10 m ahead of and 0.30 m above the trunk origin,
pitched 25 degrees down, 80 degree vertical field of view. Tactical cameras (one per team, the same view in each
team's frame): high above the middle of that team's touchline (its own right-hand side when attacking +x), looking at
the pitch: the whole field in one image.
"""
from __future__ import annotations

import os

import numpy as np

import mujoco

T1_ASSETS = os.environ.get("RCB_T1_ASSETS", "/opt/sai_t1")
TEAM_SIZE = int(os.environ.get("SOCCER_TEAM_SIZE", "2"))
# Pitches (lines are part of the area they bound), by team size.
#   2: between the HSL S-Field (9 x 6 m) and M-Field (14 x 9 m), sized for four slow walking robots; boards on the
#      touchlines and goal lines (the goal mouths are open).
#   5: the HSL 2026 M-Field (Law 1 table "Exemplary field dimensions": 14 x 9 m, goal area 1 x 4 m, penalty area
#      3 x 6 m, penalty mark 2.0 m, centre circle 3.0 m diameter, corner arcs 0.5 m, border strip >= 1 m) with the
#      Large Division's goal (2.6-3.1 x 1.8-2.0 m, 1.0-2.0 m deep: the smallest); the Large Division's Advanced
#      configuration (5 players per team, Law 3) may play on the M-Field.
PITCHES = {
    2: dict(half_l=5.0, half_w=3.5, goal=(2.6, 1.8, 0.6), center_r=1.0, pen_mark=1.5, pen_area=(2.0, 4.0),
            goal_area=(1.0, 3.0), boards=True, border=0.0, corner_arc=0.0),
    5: dict(half_l=7.0, half_w=4.5, goal=(2.6, 1.8, 1.0), center_r=1.5, pen_mark=2.0, pen_area=(3.0, 6.0),
            goal_area=(1.0, 4.0), boards=False, border=1.5, corner_arc=0.5),
}
if TEAM_SIZE not in PITCHES:
    raise ValueError(f"SOCCER_TEAM_SIZE must be one of {sorted(PITCHES)}")
PITCH = PITCHES[TEAM_SIZE]
ROBOTS = tuple(f"{t}{i}" for t in "AB" for i in range(1, TEAM_SIZE + 1))
TEAM_OF = {r: r[0] for r in ROBOTS}
HALF_L, HALF_W = PITCH["half_l"], PITCH["half_w"]
LINE_W = 0.05
GOAL_W, GOAL_H, GOAL_D = PITCH["goal"]          # inner width / height of the mouth, depth
POST_R = 0.05                                   # post radius (HSL: posts 7-12 cm wide)
CENTER_R = PITCH["center_r"]                    # centre circle radius (also the free kicks' avoidance radius)
PEN_MARK = PITCH["pen_mark"]                    # penalty mark distance from the goal line
PEN_AREA = PITCH["pen_area"]                    # penalty area length x width
GOAL_AREA = PITCH["goal_area"]                  # goal area length x width
BOARDS = PITCH["boards"]                        # boards on the lines (2 v 2) or an open field with a border strip
BORDER = PITCH["border"]                        # border strip ("carpet" beyond the lines; HSL: at least 1 m)
CORNER_ARC = PITCH["corner_arc"]
BOARD_T, BOARD_H = 0.05, 0.30       # board thickness and height (outside the lines)
# where a robot may stand: on the carpet (the boards' inside for 2 v 2)
PLAY_X, PLAY_Y = HALF_L + BORDER, HALF_W + BORDER
BALL_R, BALL_DENSITY = 0.11, 81.0   # FIFA size 5 (sai-mujoco's ball: 0.452 kg)
# The ball's contacts (soccer-2v2-8; before: MuJoCo's default critically damped contact, a 2 m drop rebounded 0.01 m):
# priority 1, so every contact of the ball (turf, robots, posts, boards) uses its solref; [0.01, 0.15] rebounds a 2 m
# drop on the turf 0.81 m (FIFA Quality Programme for Football Turf: 0.60-1.00 m) and comes off a post at 0.73 of its
# speed (a FIFA ball on a hard surface: about 0.82-0.88). A size 5 ball is a thin shell: moment of inertia 2/3 m R^2
# (a solid sphere's 2/5 before), so a ball struck at its centre keeps 3/5 of its speed once it rolls (5/7 before).
BALL_SOLREF = (0.01, 0.15)
BALL_SHELL = True
BALL_RGBA = (1.0, 0.45, 0.0, 1.0)   # an orange ball (easy to find in a camera image)
IDENTITY_VERSION = "team-colour-number/1"
TEAM_RGB = {"A": (40, 90, 245), "B": (230, 40, 40)}
ROBOT_NUMBERS = {r: int(r[1:]) for r in ROBOTS}
TEAM_RGBA = {r: tuple(v / 255 for v in TEAM_RGB[TEAM_OF[r]]) + (1.0,) for r in ROBOTS}
CAM_POS_TRUNK = (0.10, 0.0, 0.30)
CAM_PITCH_DEG = 25.0
CAM_FOVY_DEG = 80.0
TILE = (480, 360)                   # head-camera image size (width, height)
# The tactical camera (a coach's view of the whole pitch from high above its own touchline; one per team, the same
# view in each team's frame): position (team frame), the point it looks at, vertical field of view, image size.
TAC_TILE = (960, 600)
TAC_POS = (0.0, -(HALF_W + BORDER + 4.0), 1.5 * HALF_L)
TAC_LOOK = (0.0, -0.2 * HALF_W, 0.0)
TAC_FOVY_DEG = 45.0 if TEAM_SIZE == 5 else 46.0
FLOOR_FRICTION = (0.481519156, 0.00245215325, 0.0001)
FLOOR_SOLIMP = (0.0, 0.95, 0.001, 0.5, 2.0)


def cam_quat() -> np.ndarray:
    """The head camera's orientation in the trunk frame: looking along +x, pitched CAM_PITCH_DEG down."""
    p = np.deg2rad(CAM_PITCH_DEG)
    f = np.array([np.cos(p), 0.0, -np.sin(p)])
    up = np.array([np.sin(p), 0.0, np.cos(p)])
    z, y = -f, up
    x = np.cross(y, z)
    q = np.zeros(4)
    mujoco.mju_mat2Quat(q, np.stack([x, y, z], 1).reshape(-1))
    return q


def cam_to_trunk() -> list:
    """4x4 transform from the camera frame (x right, y down, z forward: OpenCV) to the trunk frame."""
    p = np.deg2rad(CAM_PITCH_DEG)
    fwd = np.array([np.cos(p), 0.0, -np.sin(p)])
    down = -np.array([np.sin(p), 0.0, np.cos(p)])
    right = np.cross(down, fwd)
    T = np.eye(4)
    T[:3, 0], T[:3, 1], T[:3, 2], T[:3, 3] = right, down, fwd, CAM_POS_TRUNK
    return T.round(6).tolist()


def intrinsics(w: int = TILE[0], h: int = TILE[1], fovy_deg: float = CAM_FOVY_DEG) -> list:
    fy = 0.5 * h / np.tan(np.deg2rad(fovy_deg) / 2)
    return [[round(fy, 4), 0.0, w / 2], [0.0, round(fy, 4), h / 2], [0.0, 0.0, 1.0]]


def _look_rot(pos, look):
    """Rotation matrix (columns: camera x right, y up, z backwards; MuJoCo's camera frame) of a camera at `pos`
    looking at `look` with world z up."""
    f = np.asarray(look, float) - np.asarray(pos, float)
    f /= np.linalg.norm(f)
    x = np.cross(f, [0.0, 0.0, 1.0]); x /= np.linalg.norm(x)
    y = np.cross(x, f)
    return np.stack([x, y, -f], 1)


def tac_pose(team: str):
    """World position and MuJoCo quaternion of a team's tactical camera (team B's: team A's turned 180 degrees)."""
    s = 1.0 if team == "A" else -1.0
    pos = np.array([s * TAC_POS[0], s * TAC_POS[1], TAC_POS[2]])
    look = np.array([s * TAC_LOOK[0], s * TAC_LOOK[1], TAC_LOOK[2]])
    q = np.zeros(4)
    mujoco.mju_mat2Quat(q, _look_rot(pos, look).reshape(-1))
    return pos, q


def tac_to_team() -> list:
    """4x4 transform from the tactical camera's frame (OpenCV: x right, y down, z forward) to the team frame; the same
    for both teams."""
    R = _look_rot(TAC_POS, TAC_LOOK)
    T = np.eye(4)
    T[:3, 0], T[:3, 1], T[:3, 2], T[:3, 3] = R[:, 0], -R[:, 1], -R[:, 2], TAC_POS
    return T.round(6).tolist()


def _box(body, name, pos, size, rgba, collide=True, **kw):
    g = body.add_geom(name=name, type=mujoco.mjtGeom.mjGEOM_BOX, pos=list(pos), size=list(size), rgba=list(rgba), **kw)
    if not collide:
        g.contype = 0; g.conaffinity = 0
    return g


def _lines(wb):
    """Field markings: thin boxes just above the floor, no collision."""
    w, z, hz = LINE_W / 2, 0.0006, 0.0005
    white = (0.95, 0.95, 0.95, 1)
    segs = []                                        # (x0, y0, x1, y1)
    L, W = HALF_L - w, HALF_W - w
    segs += [(-L, -W, L, -W), (-L, W, L, W), (-L, -W, -L, W), (L, -W, L, W), (0, -W, 0, W)]
    for s in (-1, 1):
        for (ln, wd) in (PEN_AREA, GOAL_AREA):
            x0, x1 = s * L, s * (HALF_L - ln + w)
            segs += [(x0, -wd / 2 + w, x1, -wd / 2 + w), (x0, wd / 2 - w, x1, wd / 2 - w), (x1, -wd / 2 + w, x1, wd / 2 - w)]
    for i, (x0, y0, x1, y1) in enumerate(segs):
        c = ((x0 + x1) / 2, (y0 + y1) / 2, z)
        size = (abs(x1 - x0) / 2 + w, abs(y1 - y0) / 2 + w, hz)
        _box(wb, f"line_{i}", c, size, white, collide=False)
    n = 48 if CENTER_R <= 1.0 else 72                # centre circle as short boxes
    for i in range(n):
        a = 2 * np.pi * (i + 0.5) / n
        r = CENTER_R - w
        g = wb.add_geom(name=f"circle_{i}", type=mujoco.mjtGeom.mjGEOM_BOX, pos=[r * np.cos(a), r * np.sin(a), z],
                        size=[w, np.pi * r / n + 0.004, hz], rgba=list(white))
        g.quat = [np.cos(a / 2), 0, 0, np.sin(a / 2)]
        g.contype = 0; g.conaffinity = 0
    for i, x in enumerate((0.0, -(HALF_L - PEN_MARK), HALF_L - PEN_MARK)):
        _box(wb, f"mark_{i}", (x, 0, z), (0.05, 0.05, hz), white, collide=False)
    if CORNER_ARC:                                   # quarter circles at the corners (HSL Law 1)
        j = 0
        for sx in (-1, 1):
            for sy in (-1, 1):
                for i in range(6):
                    a = (i + 0.5) / 6 * np.pi / 2
                    r = CORNER_ARC - w
                    px, py = sx * (HALF_L - r * np.cos(a)), sy * (HALF_W - r * np.sin(a))
                    g = wb.add_geom(name=f"arc_{j}", type=mujoco.mjtGeom.mjGEOM_BOX, pos=[px, py, z],
                                    size=[w, np.pi * r / 12 + 0.004, hz], rgba=list(white))
                    ang = np.arctan2(py - sy * HALF_W, px - sx * HALF_L)
                    g.quat = [np.cos(ang / 2), 0, 0, np.sin(ang / 2)]
                    g.contype = 0; g.conaffinity = 0
                    j += 1


def _goal(wb, s, rgba_post=(1, 1, 1, 1)):
    """Goal at x = s * HALF_L (posts on the goal line, the net behind)."""
    tag = "A" if s < 0 else "B"                     # the goal team A defends is at -x
    x = s * (HALF_L + POST_R)
    for side in (-1, 1):
        wb.add_geom(name=f"post_{tag}_{'L' if side * s > 0 else 'R'}", type=mujoco.mjtGeom.mjGEOM_CYLINDER,
                    pos=[x, side * (GOAL_W / 2 + POST_R), GOAL_H / 2], size=[POST_R, GOAL_H / 2, 0], rgba=list(rgba_post))
    g = wb.add_geom(name=f"bar_{tag}", type=mujoco.mjtGeom.mjGEOM_CYLINDER, pos=[x, 0, GOAL_H + POST_R],
                    size=[POST_R, GOAL_W / 2 + 2 * POST_R, 0], rgba=list(rgba_post))
    g.quat = [np.cos(np.pi / 4), np.sin(np.pi / 4), 0, 0]
    net = (0.85, 0.85, 0.85, 0.35)
    xb = s * (HALF_L + GOAL_D)
    _box(wb, f"net_back_{tag}", (xb + s * 0.01, 0, GOAL_H / 2), (0.01, GOAL_W / 2 + 2 * POST_R, GOAL_H / 2), net)
    for side in (-1, 1):
        _box(wb, f"net_side_{tag}_{side}", (s * (HALF_L + GOAL_D / 2 + POST_R), side * (GOAL_W / 2 + 2 * POST_R + 0.01),
                                            GOAL_H / 2), (GOAL_D / 2, 0.01, GOAL_H / 2), net)
    _box(wb, f"net_top_{tag}", (s * (HALF_L + GOAL_D / 2 + POST_R), 0, GOAL_H + 0.01),
         (GOAL_D / 2, GOAL_W / 2 + 2 * POST_R, 0.01), net)
    _box(wb, f"goal_floor_{tag}", (s * (HALF_L + GOAL_D / 2 + POST_R), 0, 0.0006),
         (GOAL_D / 2 + POST_R, GOAL_W / 2 + POST_R, 0.0005), (0.85, 0.85, 0.85, 1), collide=False)


def _boards(wb):
    dark = (0.18, 0.18, 0.2, 1)
    t, h = BOARD_T, BOARD_H
    _box(wb, "board_N", (0, HALF_W + t, h / 2), (HALF_L + 2 * t, t, h / 2), dark)
    _box(wb, "board_S", (0, -HALF_W - t, h / 2), (HALF_L + 2 * t, t, h / 2), dark)
    side = (HALF_W - GOAL_W / 2 - 2 * POST_R) / 2
    for s in (-1, 1):
        for sy in (-1, 1):
            _box(wb, f"board_end_{'W' if s < 0 else 'E'}_{'N' if sy > 0 else 'S'}",
                 (s * (HALF_L + t), sy * (HALF_W - side), h / 2), (t, side, h / 2), dark)


def identity_spec():
    """Public roster, never locations: team colour + unique number within a team."""
    return dict(version=IDENTITY_VERSION, team_colours={"A": "blue", "B": "red"},
                team_rgb=TEAM_RGB, number_colour="white", number_faces=["front", "back"] + (["top"] if TEAM_SIZE > 2 else []),
                roster={r: dict(team=TEAM_OF[r], number=ROBOT_NUMBERS[r]) for r in ROBOTS},
                recognition="Colour identifies team; read the jersey number or track the player to identify an individual. "
                            "Numbers may be occluded or too small to read; no hidden player detections are provided.")


def add_jersey_number(body, number, top=False):
    """Bold white 1..99 on the torso, with no contact or inertia contribution.

    Front and back; with `top` (5 v 5) also on the shoulders, readable from the tactical camera.
    """
    if not isinstance(number, int) or not 1 <= number <= 99:
        raise ValueError("jersey number must be an integer in 1..99")
    segments = {
        'a': ((-1, 1), (1, 1)), 'b': ((1, 1), (1, 0)), 'c': ((1, 0), (1, -1)),
        'd': ((-1, -1), (1, -1)), 'e': ((-1, 0), (-1, -1)),
        'f': ((-1, 1), (-1, 0)), 'g': ((-1, 0), (1, 0)),
    }
    digits = ('abcdef', 'bc', 'abged', 'abgcd', 'fgbc', 'afgcd', 'afgecd', 'abc', 'abcdefg', 'abfgcd')
    text = str(number)
    for i, digit in enumerate(text):
        strokes = [segments[s] for s in digits[int(digit)]]
        if digit == '1':
            strokes = [((0, 1), (0, -1)), ((-.55, .65), (0, 1)), ((-.55, -1), (.55, -1))]
        centre = (i - (len(text) - 1) / 2) * .077
        half_width = .032 if len(text) == 1 else .025
        for face, x, mirror in (("front", .155, 1), ("back", -.031, -1)):
            for j, ((y0, z0), (y1, z1)) in enumerate(strokes):
                points = [x, mirror * (centre + half_width * y0), .16 + .065 * z0,
                          x, mirror * (centre + half_width * y1), .16 + .065 * z1]
                body.add_geom(name=f"jersey_{face}_{i}_{j}", type=mujoco.mjtGeom.mjGEOM_CAPSULE,
                              fromto=points, size=[.01, 0, 0], rgba=[1, 1, 1, 1],
                              contype=0, conaffinity=0, mass=0, group=1)
        if top:                                      # on the shoulders, readable from above (the tactical camera)
            for j, ((y0, z0), (y1, z1)) in enumerate(strokes):
                # upright when seen from behind the robot: the digit's "up" is the robot's forward (+x)
                points = [.055 + .055 * z0, -(centre + half_width * 1.3 * y0), .305,
                          .055 + .055 * z1, -(centre + half_width * 1.3 * y1), .305]
                body.add_geom(name=f"jersey_top_{i}_{j}", type=mujoco.mjtGeom.mjGEOM_CAPSULE,
                              fromto=points, size=[.012, 0, 0], rgba=[1, 1, 1, 1],
                              contype=0, conaffinity=0, mass=0, group=1)


def build_spec():
    spec = mujoco.MjSpec()
    spec.option.timestep = 0.002
    spec.option.integrator = mujoco.mjtIntegrator.mjINT_IMPLICITFAST
    spec.visual.global_.offwidth = 1280
    spec.visual.global_.offheight = 960
    spec.visual.quality.shadowsize = 2048
    spec.visual.headlight.ambient = [0.35, 0.35, 0.35]
    spec.visual.headlight.diffuse = [0.45, 0.45, 0.45]
    spec.add_texture(name="sky", type=mujoco.mjtTexture.mjTEXTURE_SKYBOX, builtin=mujoco.mjtBuiltin.mjBUILTIN_GRADIENT,
                     rgb1=[0.55, 0.7, 0.9], rgb2=[0.2, 0.25, 0.3], width=256, height=256)
    spec.add_texture(name="grass", type=mujoco.mjtTexture.mjTEXTURE_2D, builtin=mujoco.mjtBuiltin.mjBUILTIN_CHECKER,
                     rgb1=[0.16, 0.52, 0.18], rgb2=[0.14, 0.47, 0.16], width=512, height=512)
    spec.add_material(name="grass", textures=["", "grass"], texrepeat=[10, 10])
    wb = spec.worldbody
    wb.add_light(name="sun", pos=[0, 0, 12], dir=[0.15, 0.1, -1], diffuse=[0.6, 0.6, 0.6], castshadow=False,
                 type=mujoco.mjtLightType.mjLIGHT_DIRECTIONAL)
    if BOARDS:
        floor = wb.add_geom(name="floor", type=mujoco.mjtGeom.mjGEOM_PLANE, size=[HALF_L + 3, HALF_W + 3, 0.05],
                            material="grass", friction=list(FLOOR_FRICTION), solimp=list(FLOOR_SOLIMP), solref=[0.02, 1])
    else:                                            # the carpet: the field and its border strip; grey floor beyond
        floor = wb.add_geom(name="floor", type=mujoco.mjtGeom.mjGEOM_PLANE, size=[PLAY_X, PLAY_Y, 0.05],
                            material="grass", friction=list(FLOOR_FRICTION), solimp=list(FLOOR_SOLIMP), solref=[0.02, 1])
        g = wb.add_geom(name="hall_floor", type=mujoco.mjtGeom.mjGEOM_PLANE, pos=[0, 0, -0.003],
                        size=[PLAY_X + 6, PLAY_Y + 6, 0.05], rgba=[0.45, 0.45, 0.47, 1])
        g.contype = 0; g.conaffinity = 0
    floor.contype = 1; floor.conaffinity = 2
    _lines(wb)
    _goal(wb, -1)
    _goal(wb, 1)
    if BOARDS:
        _boards(wb)
    for t in "AB":
        pos, q = tac_pose(t)
        wb.add_camera(name=f"tactical_{t}", pos=list(pos), quat=list(q), fovy=TAC_FOVY_DEG)
    ball = wb.add_body(name="ball", pos=[0, 0, BALL_R])
    ball.add_freejoint(name="ball")
    bg = ball.add_geom(name="ball", type=mujoco.mjtGeom.mjGEOM_SPHERE, size=[BALL_R, 0, 0], density=BALL_DENSITY,
                       rgba=list(BALL_RGBA), solimp=[0.9, 0.95, 0.001, 0.5, 2])
    if BALL_SOLREF is not None:
        bg.priority = 1
        bg.solref = list(BALL_SOLREF)
    if BALL_SHELL:
        mass = BALL_DENSITY * 4.0 / 3.0 * np.pi * BALL_R ** 3
        ball.explicitinertial = True
        ball.mass = mass
        ball.ipos = [0.0, 0.0, 0.0]
        ball.inertia = [2.0 / 3.0 * mass * BALL_R ** 2] * 3
    xml = os.path.join(T1_ASSETS, "v1", "robot_lower.xml")
    for r in ROBOTS:
        rs = mujoco.MjSpec.from_file(xml)
        rs.meshdir = os.path.join(T1_ASSETS, "meshes")
        add_jersey_number(rs.bodies[1], ROBOT_NUMBERS[r], top=TEAM_SIZE > 2)
        frame = wb.add_frame()
        frame.attach_body(rs.bodies[1], f"{r}:", "")
    return spec


def build_model() -> mujoco.MjModel:
    m = build_spec().compile()
    for r in ROBOTS:
        m.geom_rgba[m.geom(f"{r}:Trunk").id] = TEAM_RGBA[r]
        c = m.camera(f"{r}:egocentric").id
        m.cam_pos[c] = CAM_POS_TRUNK
        m.cam_quat[c] = cam_quat()
        m.cam_fovy[c] = CAM_FOVY_DEG
    return m
