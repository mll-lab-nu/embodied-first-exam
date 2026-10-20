"""Overhead cameras of the wheeled 5 v 5 soccer (RoboCup SSL division B), C line of the SSL build
(interfaces: the Embodied Olympics screening notes §5, outside the repository).

Real setup: the SSL shared vision looks at the field from a camera bar 4 m above the playing surface, four cameras
for the 9 x 6 m field (RoboCup 2022 SSL page: "four cameras that are attached to a camera bar located 4 m above the
playing surface"; SSL-Vision's pattern-fitting parameters are tuned for about 4 m, robocup-small list 2013). The rule
book does not fix the number, height or frame rate of the cameras (SSL rules 2026-09-19 §2.3.1). The robots' tops
carry the standard vision pattern (rules §3.2.5, `PATTERN` below): a 50 mm blue or yellow centre dot (team) and four
40 mm pink / green dots (id 0..15) on a black or dark grey matte top.

Layouts (all cameras look straight down; image right = world +x, image up = world +y, so every tile is a plain map
of its part of the field; both teams get the same images, as with the shared SSL vision):
    ssl4    four cameras over the four quadrants, 4.0 m up (the real division B bar)        default
    ssl2    two cameras over the two halves, 4.0 m up (SSL-Vision 2009 style, wider lenses)
    single  one camera over the whole field, 4.0 m up (a very wide lens; the cheapest picture)
Each camera covers its part of the walled area (|x| <= 4.8, |y| <= 3.3 m: the 9 x 6 m playing area plus the 0.3 m
division B margin) at robot-top height 0.15 m, plus OVERLAP beyond the centre lines, so a robot on a seam is whole in
at least one tile.

API (interfaces §5):
    add_cameras(spec, field_handles=None, layout="ssl4", size=None, lights=True) -> [camera names]
    render(model, data, names, size=None) -> [H x W x 3 uint8]       (MuJoCo off-screen: OSMesa in the sim image)
    camera_defs(layout="ssl4", size=None, field_handles=None) -> [CameraDef dicts]  (for Match.cameras(seat): the
        core's renderer (renderers/mujoco) draws exactly the same pictures from these)
    project(cam, point) / ground_point(cam, u, v, z): the pinhole model of renderers/base.CameraDef (pixel (u, v)
        from the top-left corner, u right, v down), to put the calibration into /spec.
Rendering never changes physics: render() only reads data (MuJoCo's visual pass)."""
from __future__ import annotations

import math

import numpy as np

CAMERA_HEIGHT = 4.0          # m above the carpet (RoboCup 2022 SSL page; SSL-Vision tuned for ~4 m)
ROBOT_TOP = 0.15             # m: the robots' tops (rules §3.2.2: at most 0.15 m high); coverage is checked at this height
OVERLAP = 0.10               # m: each camera sees this far past the centre line(s) at robot-top height (estimate)
WALL_HALF = (4.8, 3.3)       # m: half extents of the walled area, division B (9 x 6 m + 0.3 m margin, rules §2.1.2)
DEFAULT_LAYOUT = "ssl4"
DEFAULT_SIZE = {"ssl4": (800, 600), "ssl2": (600, 800), "single": (1200, 840)}   # (width, height) per tile
NAME = "ssl_cam"

# Standard vision pattern (SSL rules §3.2.5, figures standard_pattern2010.png / standard_colors2010.svg of the
# rules repository): robot frame x forward, y left, metres. Front dots at (0.035, +-0.054772), back dots at
# (-0.054772, +-0.035); centre dot radius 0.025, the others 0.020. Colours read off standard_colors2010.svg
# (front-left, front-right, back-left, back-right); P = pink (#ff00ff), G = green (#00ff00).
PATTERN = {
    "center_radius": 0.025, "dot_radius": 0.020,
    "dots": {"FL": (0.035, 0.054772), "FR": (0.035, -0.054772), "BL": (-0.054772, 0.035), "BR": (-0.054772, -0.035)},
    "ids": ["PPGP", "GPGP", "GGGP", "PGGP", "PPPG", "GPPG", "GGPG", "PGPG",
            "GGGG", "PPPP", "PPGG", "GGPP", "GPGG", "GPPP", "PGGG", "PGPP"],
    "rgb": {"blue": (0.0, 0.0, 1.0), "yellow": (1.0, 1.0, 0.0), "P": (1.0, 0.0, 1.0), "G": (0.0, 1.0, 0.0)},
}


# ------------------------------------------------------------------------------------------------- layouts
def _wall_half(field_handles):
    """(wall_x, wall_y) from the field handles (B's field.build_scene: handles["field"]["wall_x" / "wall_y"], or the
    field dict itself, or {"wall_half": (x, y)}); the division B default otherwise."""
    fh = field_handles or {}
    if isinstance(fh, dict) and isinstance(fh.get("field"), dict):
        fh = fh["field"]
    if isinstance(fh, dict):
        if "wall_half" in fh:
            return tuple(float(v) for v in fh["wall_half"])
        if "wall_x" in fh and "wall_y" in fh:
            return float(fh["wall_x"]), float(fh["wall_y"])
    return WALL_HALF


def _fovy_for(half_x, half_y, w, h, depth):
    """The vertical field of view (deg) whose picture of w x h px covers +-half_x by +-half_y at `depth`."""
    t = max(half_y / depth, half_x / depth * h / w)
    return math.degrees(2 * math.atan(t))


def camera_defs(layout: str = DEFAULT_LAYOUT, size=None, field_handles=None) -> list[dict]:
    """The cameras of a layout in renderers/base.CameraDef dict form (name, pos, lookat, up, fovy_deg, width, height)."""
    if layout not in DEFAULT_SIZE:
        raise ValueError(f"unknown camera layout {layout!r}; one of {sorted(DEFAULT_SIZE)}")
    w, h = (int(v) for v in (size or DEFAULT_SIZE[layout]))
    X, Y = _wall_half(field_handles)
    depth = CAMERA_HEIGHT - ROBOT_TOP
    if layout == "ssl4":
        cx, cy = X / 2, Y / 2
        hx, hy = X / 2 + OVERLAP, Y / 2 + OVERLAP          # half spans around each quadrant centre (centred cams)
        centres = [(-cx, cy), (cx, cy), (-cx, -cy), (cx, -cy)]   # tiles in reading order: top-left first
    elif layout == "ssl2":
        cx = X / 2
        hx, hy = X / 2 + OVERLAP, Y
        centres = [(-cx, 0.0), (cx, 0.0)]
    else:
        hx, hy = X, Y
        centres = [(0.0, 0.0)]
    fovy = _fovy_for(hx, hy, w, h, depth)
    return [{"name": f"{NAME}{i}", "pos": [x, y, CAMERA_HEIGHT], "lookat": [x, y, 0.0], "up": [0.0, 1.0, 0.0],
             "fovy_deg": round(fovy, 4), "width": w, "height": h} for i, (x, y) in enumerate(centres)]


# ------------------------------------------------------------------------------------------------- scene
def add_cameras(spec, field_handles=None, layout: str = DEFAULT_LAYOUT, size=None, lights: bool = True,
                msaa: bool = False, venue_lighting: bool = True) -> list[str]:
    """Add the layout's fixed overhead cameras to a mujoco.MjSpec (world body) and make the off-screen buffer big
    enough for them. lights=True: when the scene has no light yet, one shadowless overhead light (a lit hall; shadows
    off: the venue lights are many and diffuse, and a shadow pass costs about 3 x the render time). msaa=False turns
    MuJoCo's 4 x multisampling of the off-screen buffer off (visual.quality.offsamples = 0): about 3 x faster on
    OSMesa, and the robots' ids, positions and headings are read as well without it
    (docs/screening/soccer_ssl/render/README.md). venue_lighting=True makes the scene's own lights directional and
    shadowless and the carpet matte (specular 0; field_handles["field"]["carpet"], default geom "carpet"): an SSL hall
    is lit evenly, and a spot light's falloff and the carpet's highlights darken the id dots in the corners (the
    detector of docs/.../detect.py then reads 56 % of the ids instead of 100 %) and blow the PNG up from 30 to 512 KB.
    It also draws every plane as one cell (size[2], MuJoCo's render-only grid spacing of a plane): the grid only
    serves spot-light shading and costs about 12 ms per 4-camera observation on B's field. Visual only: no contact
    or physics parameter changes. Returns the camera names."""
    defs = camera_defs(layout, size, field_handles)
    spec.visual.quality.offsamples = 4 if msaa else 0
    g = spec.visual.global_
    g.offwidth = max(int(g.offwidth), max(d["width"] for d in defs))
    g.offheight = max(int(g.offheight), max(d["height"] for d in defs))
    for d in defs:
        # straight down with image right = +x and image up = +y: the MuJoCo camera frame (x right, y up, looking
        # along -z) is the world frame itself -> identity orientation
        # resolution: the tile size travels with the model (render() reads cam_resolution when size is None)
        spec.worldbody.add_camera(name=d["name"], pos=d["pos"], quat=[1.0, 0.0, 0.0, 0.0], fovy=d["fovy_deg"],
                                  resolution=[d["width"], d["height"]])
    if venue_lighting:
        import mujoco as mj
        for lt in spec.lights:
            lt.type = mj.mjtLightType.mjLIGHT_DIRECTIONAL
            lt.castshadow = False
        for geom in spec.geoms:
            if geom.type == mj.mjtGeom.mjGEOM_PLANE and geom.size[0] > 0 and geom.size[1] > 0:
                geom.size = [geom.size[0], geom.size[1], 2.0 * max(geom.size[0], geom.size[1])]
        fh = field_handles.get("field", field_handles) if isinstance(field_handles, dict) else {}
        carpet = fh.get("carpet", "carpet") if isinstance(fh, dict) else "carpet"
        try:
            cg = spec.geom(carpet)
        except (KeyError, ValueError):
            cg = None
        if cg is not None and not cg.material:
            spec.add_material(name="ssl_cam_matte_carpet", rgba=list(cg.rgba), specular=0.0, shininess=0.0)
            cg.material = "ssl_cam_matte_carpet"
    if lights and not list(spec.lights):               # the field's own lights win
        spec.visual.headlight.ambient = [0.35, 0.35, 0.35]
        spec.visual.headlight.diffuse = [0.35, 0.35, 0.35]
        spec.visual.headlight.specular = [0.0, 0.0, 0.0]
        import mujoco as mj
        spec.worldbody.add_light(name="ssl_overhead", pos=[0.0, 0.0, CAMERA_HEIGHT + 1.0], dir=[0.0, 0.0, -1.0],
                                 type=mj.mjtLightType.mjLIGHT_DIRECTIONAL, castshadow=False,
                                 diffuse=[0.45, 0.45, 0.45], specular=[0.05, 0.05, 0.05])
    return [d["name"] for d in defs]


# ------------------------------------------------------------------------------------------------- drawing
_RENDERERS: dict = {}
_OPTION = None
HIDDEN_GROUPS = (3, 4, 5)    # never in the players' images: A's robot-robot hulls (<name>_hull_outer, geom group 3),
                             # sensor sites (group 4); MuJoCo's default option hides them too, this makes it explicit


def _option():
    global _OPTION
    if _OPTION is None:
        import mujoco as mj
        _OPTION = mj.MjvOption()
        for g in HIDDEN_GROUPS:
            _OPTION.geomgroup[g] = 0
            _OPTION.sitegroup[g] = 0
    return _OPTION


def render(model, data, names, size=None) -> list[np.ndarray]:
    """One H x W x 3 uint8 picture per named camera of the current state in `data` (read only). size = (w, h) of every
    tile, or None for the size add_cameras gave the cameras (the model's cam_resolution)."""
    import mujoco as mj
    if size is None:
        sizes = {tuple(int(v) for v in model.cam_resolution[model.camera(n).id]) for n in names}
        if len(sizes) != 1:
            raise ValueError(f"cameras {names} have different sizes {sorted(sizes)}: pass size")
        size = sizes.pop()
    w, h = int(size[0]), int(size[1])
    if w > model.vis.global_.offwidth or h > model.vis.global_.offheight:
        raise ValueError(f"tile {w} x {h} exceeds the off-screen buffer {model.vis.global_.offwidth} x "
                         f"{model.vis.global_.offheight} (pass size to add_cameras)")
    key = (id(model), w, h)
    r = _RENDERERS.get(key)
    if r is None:
        r = _RENDERERS[key] = mj.Renderer(model, height=h, width=w)
    out = []
    for n in names:
        r.update_scene(data, camera=n, scene_option=_option())
        out.append(np.array(r.render(), dtype=np.uint8, copy=True))
    return out


def close():
    """Free the off-screen contexts render() made."""
    for r in _RENDERERS.values():
        r.close()
    _RENDERERS.clear()


# ------------------------------------------------------------------------------------------------- calibration
def _basis(cam):
    fwd = np.subtract(cam["lookat"], cam["pos"]).astype(float)
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, cam["up"])
    right /= np.linalg.norm(right)
    return right, np.cross(right, fwd), fwd


def focal_px(cam) -> float:
    return (cam["height"] / 2) / math.tan(math.radians(cam["fovy_deg"]) / 2)


def project(cam, point):
    """Pixel (u, v) of a world point (renderers/base.CameraDef.project), None behind the camera."""
    right, up, fwd = _basis(cam)
    d = np.subtract(point, cam["pos"])
    depth = float(d @ fwd)
    if depth <= 1e-9:
        return None
    f = focal_px(cam)
    return (cam["width"] / 2 + f * float(d @ right) / depth, cam["height"] / 2 - f * float(d @ up) / depth)


def ground_point(cam, u, v, z=0.0):
    """The world point at height z seen at pixel (u, v) (the inverse of project on the plane z)."""
    right, up, fwd = _basis(cam)
    f = focal_px(cam)
    ray = fwd + right * (u - cam["width"] / 2) / f - up * (v - cam["height"] / 2) / f
    t = (z - cam["pos"][2]) / ray[2]
    return np.asarray(cam["pos"], float) + t * ray


def metres_per_pixel(cam, z=0.0) -> float:
    """Ground sampling distance at height z for a straight-down camera."""
    return (cam["pos"][2] - z) / focal_px(cam)
