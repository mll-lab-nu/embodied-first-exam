"""Onboard front cameras of the wheeled 5 v 5 soccer (RoboCup SSL division B): the second perception mode, in which
every robot sees only through its own forward-looking camera (no overhead vision, no absolute pose). Line "onboard"
of the SSL build; the overhead mode is sim/camera.py (line C) and stays the main mode.

What a robot carries in this mode (report: the Embodied Olympics screening notes):
  - one front camera (this module: mount, pose on the chassis, field of view, resolution);
  - wheel odometry and a yaw gyro with realistic drift (prototype: docs/screening/soccer_ssl/onboard/sensors.py);
  - the break beam across the dribbler opening (line A's rig.state()["ball_in_beam"]).

The camera (sources: report section 1.2; ESTIMATE where no published robot gives the number):
  - CAM_FORWARD = 0.072 m ahead of the robot's centre (just ahead of the flat front chord at 0.0715 m,
    bodies/ssl_robot/body.toml [geometry] front), CAM_HEIGHT = 0.13 m above the carpet: inside the 0.15 m height
    cap (SSL rules §3.2.2) under the 0.148 m cover, so a camera never looks over another robot's top. Published SSL
    onboard cameras: KIKS 0.085 m (2022 ETDP §3.2), RobôCIn 0.171 m (allowed above the cap in the Vision Blackout
    challenge; arXiv 2207.09851);
  - pitched down by PITCH_DEG = 15 deg (between KIKS 12.5 deg and RobôCIn about 17 deg): the horizon sits in the
    upper third and the ball is visible from about 0.1 m ahead of the lens; the last centimetres in front of the
    dribbler are hidden by the robot's own front, which is what the break beam is for;
  - a pinhole with HFOV_DEG = 90 deg (4:3: 73.7 deg vertical): between the 53-56 deg of the Raspberry Pi v1 / NAO v6
    / RobôCIn cameras and TIGERs' 140 deg diagonal lens (2020 ETDP §3); MuJoCo renders pinholes only (no fisheye);
  - DEFAULT_SIZE = 640 x 480 px at DEFAULT_FPS = 30 Hz of game time (RobôCIn's C922 and NAO v6 run 640 x 480 at
    30 fps; the Pi camera v1 does 640 x 480 up to 90 fps).
The robots of both teams carry one camera each, named f"{robot}_onboard" (e.g. "blue0_onboard"). Image right =
the robot's right, image up = up.

Team colour on the sides (team_band=True, default): visual-only panels in the team colour around the back and sides
of the hull (not in front of the lens), 0.085-0.125 m high over 300 deg: about 22 % of the side area. The SSL rules
require exactly this (§3.2.3: a distinctive colour on at least 20 % of the side area, "partially visible from all
sides"); line A's robot has only the top pattern, which a camera at 0.13 m can never see on a 0.148 m robot. The
band belongs in bodies/ssl_robot (report, decision); it is added here so the onboard mode can be tried now.

API:
    add_onboard_cameras(spec, robots=None, size=None, hfov_deg=HFOV_DEG, pitch_deg=PITCH_DEG,
                        height=CAM_HEIGHT, forward=CAM_FORWARD, team_band=True) -> {robot name: camera name}
        robots: {(team, number): line A Handles or a dict with "body"} (sports/soccer_ssl/sim/field.build_scene's
        handles["robots"]); None: every body named "<team><number>_robot" in the spec. Also lowers the near clip
        plane (MuJoCo's default 0.01 x extent clips the ball in front of the lens) and grows the off-screen buffer.
    render(model, data, cams, size=None) -> [H x W x 3 uint8]    (OSMesa in the sim image; read only)
    intrinsics(size=None, hfov_deg=HFOV_DEG) -> dict(f, cx, cy, w, h)      (pinhole, square pixels)
    camera_defs(...)                                            (the static part for /spec: mount and intrinsics)
    pixel_to_robot(u, v, z, ...) / robot_to_pixel(x, y, z, ...) (robot frame <-> pixel at a known height z)
    world_builder(...)                                          (a field.build_scene wrapper for World, see below)
Rendering never changes physics."""
from __future__ import annotations

import math
from contextlib import contextmanager

import numpy as np

CAM_HEIGHT = 0.13       # m above the carpet (ESTIMATE: under the 0.148 m cover; rules §3.2.2 max 0.15 m)
CAM_FORWARD = 0.072     # m ahead of the robot's centre (just ahead of the front chord at 0.0715 m)
PITCH_DEG = 15.0        # deg down (ESTIMATE)
HFOV_DEG = 90.0         # deg horizontal (ESTIMATE, a wide small-board lens; report §1.2)
DEFAULT_SIZE = (640, 480)
DEFAULT_FPS = 30.0      # Hz of game time
SUFFIX = "_onboard"
BAND = dict(z0=0.085, z1=0.125, r=0.0905, front_gap_deg=30.0, panels=14)   # team_band (visual only)
TEAM_RGBA = {"blue": (0.0, 0.25, 1.0, 1.0), "yellow": (1.0, 0.9, 0.0, 1.0)}   # = bodies/ssl_robot TEAM_RGBA


# ------------------------------------------------------------------------------------------------- geometry
def intrinsics(size=None, hfov_deg: float = HFOV_DEG) -> dict:
    w, h = (int(v) for v in (size or DEFAULT_SIZE))
    f = (w / 2) / math.tan(math.radians(hfov_deg) / 2)
    return dict(f=f, cx=w / 2, cy=h / 2, w=w, h=h, fovy_deg=math.degrees(2 * math.atan((h / 2) / f)))


def _cam_rot(pitch_deg: float) -> np.ndarray:
    """camera axes (columns x right, y up, z backwards: MuJoCo's camera frame) in the robot frame (x fwd, y left)."""
    p = math.radians(pitch_deg)
    cx = np.array([0.0, -1.0, 0.0])
    cy = np.array([math.sin(p), 0.0, math.cos(p)])
    cz = np.array([-math.cos(p), 0.0, math.sin(p)])
    return np.stack([cx, cy, cz], axis=1)


def camera_defs(size=None, hfov_deg=HFOV_DEG, pitch_deg=PITCH_DEG, height=CAM_HEIGHT, forward=CAM_FORWARD) -> dict:
    """The camera's static description for /spec (robot frame: x forward, y left, z up from the carpet)."""
    K = intrinsics(size, hfov_deg)
    return dict(mount=dict(x=forward, y=0.0, z=height, pitch_down_deg=pitch_deg), hfov_deg=hfov_deg,
                vfov_deg=round(K["fovy_deg"], 4), width=K["w"], height=K["h"], f_px=round(K["f"], 4),
                principal_point=[K["cx"], K["cy"]], model="pinhole, no distortion",
                image_axes="u right (robot's right), v down")


def robot_to_pixel(x, y, z, size=None, hfov_deg=HFOV_DEG, pitch_deg=PITCH_DEG, height=CAM_HEIGHT,
                   forward=CAM_FORWARD):
    """pixel (u, v) of robot-frame point(s) (x fwd, y left, z up); NaN behind the camera. Arrays broadcast."""
    K = intrinsics(size, hfov_deg)
    p = math.radians(pitch_deg)
    dx, dy, dz = np.asarray(x, float) - forward, np.asarray(y, float), np.asarray(z, float) - height
    depth = dx * math.cos(p) - dz * math.sin(p)          # along the optical axis
    up = dx * math.sin(p) + dz * math.cos(p)
    with np.errstate(divide="ignore", invalid="ignore"):
        u = K["cx"] + K["f"] * (-dy) / depth
        v = K["cy"] - K["f"] * up / depth
    bad = depth <= 1e-6
    return np.where(bad, np.nan, u), np.where(bad, np.nan, v)


def pixel_to_robot(u, v, z=0.0, size=None, hfov_deg=HFOV_DEG, pitch_deg=PITCH_DEG, height=CAM_HEIGHT,
                   forward=CAM_FORWARD):
    """robot-frame (x, y) of the point at height z seen at pixel (u, v); NaN at or above the horizon of z."""
    K = intrinsics(size, hfov_deg)
    p = math.radians(pitch_deg)
    a = (np.asarray(u, float) - K["cx"]) / K["f"]          # right
    b = -(np.asarray(v, float) - K["cy"]) / K["f"]         # up
    # ray in the robot frame: fwd*1 + right*a + up*b (camera frame), rotated by the pitch
    rx = math.cos(p) + b * math.sin(p)
    rz = -math.sin(p) + b * math.cos(p)
    ry = -a
    with np.errstate(divide="ignore", invalid="ignore"):
        t = (z - height) / rz
    ok = t > 0
    return np.where(ok, forward + t * rx, np.nan), np.where(ok, t * ry, np.nan)


def horizon_row(size=None, hfov_deg=HFOV_DEG, pitch_deg=PITCH_DEG) -> float:
    """image row of the camera's own height plane far away (objects taller than the lens reach above it)."""
    K = intrinsics(size, hfov_deg)
    return K["cy"] - K["f"] * math.tan(math.radians(pitch_deg))


# ------------------------------------------------------------------------------------------------- scene
def _robot_bodies(spec, robots):
    if robots:
        out = {}
        for (team, num), h in robots.items():
            body = h.get("body") if isinstance(h, dict) else getattr(h, "body", None)
            out[(team, int(num))] = body or f"{team}{num}_robot"
        return out
    out = {}
    for b in spec.bodies:
        n = b.name or ""
        for team in ("blue", "yellow"):
            if n.startswith(team) and n.endswith("_robot") and n[len(team):-len("_robot")].isdigit():
                out[(team, int(n[len(team):-len("_robot")]))] = n
    return out


def add_onboard_cameras(spec, robots=None, size=None, hfov_deg: float = HFOV_DEG, pitch_deg: float = PITCH_DEG,
                        height: float = CAM_HEIGHT, forward: float = CAM_FORWARD, team_band: bool = True,
                        venue_lighting: bool = True, msaa: bool = False, backdrop: bool = True) -> dict:
    """One front camera on every robot body of `spec` (see the module docstring). Returns {robot body: camera}.
    venue_lighting: the even hall lighting that line E put into field.py (one shadowless directional light, a matte
    carpet, planes drawn as one cell; visual only), applied here too for a field built without it (idempotent).
    msaa=False: no multisampling of the off-screen buffer (as line C: about 3 x cheaper on OSMesa).
    backdrop=True: a plain grey hall around the field (a skybox gradient; MuJoCo's default background is black, the
    colour of the robots' covers and the walls). A simplification: a real hall has spectators and clutter."""
    import mujoco as mj
    K = intrinsics(size, hfov_deg)
    quat = np.zeros(4)
    mj.mju_mat2Quat(quat, _cam_rot(pitch_deg).flatten())
    spec.visual.quality.offsamples = 4 if msaa else 0
    g = spec.visual.global_
    g.offwidth = max(int(g.offwidth), K["w"])
    g.offheight = max(int(g.offheight), K["h"])
    # near clip: MuJoCo's znear is relative to the model extent (about 6-7 m here): 0.01 x 6.5 = 6.5 cm would cut the
    # ball off in front of the lens. 0.0006 x extent (16 m with the venue floor) ~ 1 cm; the 24-bit depth buffer still separates 1 mm at 10 m.
    spec.visual.map.znear = min(float(spec.visual.map.znear), 0.0006)
    if venue_lighting:
        _venue_lighting(spec)
    if backdrop and not any(t.type == mj.mjtTexture.mjTEXTURE_SKYBOX for t in spec.textures):
        spec.add_texture(name="onboard_hall", type=mj.mjtTexture.mjTEXTURE_SKYBOX,
                         builtin=mj.mjtBuiltin.mjBUILTIN_GRADIENT, rgb1=[0.62, 0.62, 0.64], rgb2=[0.42, 0.42, 0.45],
                         width=64, height=64)
    out = {}
    for (team, num), bname in sorted(_robot_bodies(spec, robots).items()):
        body = spec.body(bname)
        name = bname[: -len("_robot")] + SUFFIX if bname.endswith("_robot") else bname + SUFFIX
        body.add_camera(name=name, pos=[forward, 0.0, height], quat=list(quat), fovy=K["fovy_deg"],
                        resolution=[K["w"], K["h"]])
        out[bname] = name
        if team_band:
            _add_band(spec, body, bname, team)
    return out


def _venue_lighting(spec):
    import mujoco as mj
    for lt in spec.lights:
        lt.type = mj.mjtLightType.mjLIGHT_DIRECTIONAL
        lt.castshadow = False
    for geom in spec.geoms:
        if geom.type == mj.mjtGeom.mjGEOM_PLANE and geom.size[0] > 0 and geom.size[1] > 0:
            geom.size = [geom.size[0], geom.size[1], 2.0 * max(geom.size[0], geom.size[1])]
    try:
        cg = spec.geom("carpet")
    except (KeyError, ValueError):
        cg = None
    if cg is not None and not cg.material:
        spec.add_material(name="onboard_matte_carpet", rgba=list(cg.rgba), specular=0.0, shininess=0.0)
        cg.material = "onboard_matte_carpet"


def _add_band(spec, body, bname, team):
    """visual-only panels in the team colour around the back and sides of the hull (not in front of the lens)."""
    import mujoco as mj
    B = BAND
    mat = f"{bname}_band_mat"
    spec.add_material(name=mat, rgba=list(TEAM_RGBA[team]), specular=0.0, shininess=0.0)
    gap = math.radians(B["front_gap_deg"])
    n = B["panels"]
    span = 2 * math.pi - 2 * gap
    half_w = B["r"] * math.tan(span / n / 2) * 1.02
    for k in range(n):
        a = gap + span * (k + 0.5) / n
        body.add_geom(name=f"{bname}_band{k}", type=mj.mjtGeom.mjGEOM_BOX,
                      size=[0.0015, half_w, (B["z1"] - B["z0"]) / 2],
                      pos=[B["r"] * math.cos(a), B["r"] * math.sin(a), (B["z0"] + B["z1"]) / 2],
                      quat=[math.cos(a / 2), 0.0, 0.0, math.sin(a / 2)], material=mat, contype=0, conaffinity=0,
                      mass=0.0, density=0.0, group=1)


@contextmanager
def world_builder(**kw):
    """Make sim.world.World build its scene with onboard cameras, without touching world.py:

        with onboard.world_builder(size=(640, 480)) as cams:
            w = World(seed=1)
        # cams: {robot body: camera name}
    It wraps sim.field.build_scene for the duration of the block (the plugin would call add_onboard_cameras itself
    in World's constructor)."""
    from . import field as F
    from . import world as W
    orig = F.build_scene
    cams: dict = {}

    def build(*a, **k):
        spec, handles = orig(*a, **k)
        cams.update(add_onboard_cameras(spec, handles["robots"], **kw))
        return spec, handles

    F.build_scene = build
    W.F.build_scene = build
    try:
        yield cams
    finally:
        F.build_scene = orig
        W.F.build_scene = orig


# ------------------------------------------------------------------------------------------------- drawing
_RENDERERS: dict = {}
_OPTION = None


def _option():
    global _OPTION
    if _OPTION is None:
        import mujoco as mj
        _OPTION = mj.MjvOption()
        for g in (3, 4, 5):          # A's robot-robot hulls (group 3), sensor sites (group 4): never in a picture
            _OPTION.geomgroup[g] = 0
            _OPTION.sitegroup[g] = 0
    return _OPTION


def render(model, data, cams, size=None) -> list[np.ndarray]:
    """One H x W x 3 uint8 picture per named onboard camera (read only; MuJoCo's off-screen renderer)."""
    import mujoco as mj
    if size is None:
        size = tuple(int(v) for v in model.cam_resolution[model.camera(cams[0]).id])
    w, h = int(size[0]), int(size[1])
    key = (id(model), w, h)
    r = _RENDERERS.get(key)
    if r is None:
        r = _RENDERERS[key] = mj.Renderer(model, height=h, width=w)
    out = []
    for n in cams:
        r.update_scene(data, camera=n, scene_option=_option())
        out.append(np.array(r.render(), dtype=np.uint8, copy=True))
    return out


def close():
    for r in _RENDERERS.values():
        r.close()
    _RENDERERS.clear()
