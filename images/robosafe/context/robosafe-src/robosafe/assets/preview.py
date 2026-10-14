"""Pictures of the catalogue: single renders, close-ups of labels, and contact sheets."""
from __future__ import annotations

import math
import os

os.environ.setdefault("MUJOCO_GL", "egl")

import numpy as np

from . import catalog
from . import labels as L
from . import png

WRIST_FOVY = 70.0            # the wrist camera of `robosafe.sim.World`
LABEL_DISTANCE = 0.25        # metres: how close the wrist camera comes


def look_at(pos, target, up=(0.0, 0.0, 1.0)) -> np.ndarray:
    """Quaternion of a MuJoCo camera (looks along its -z, +y up) at `pos` looking at `target`."""
    pos, target, up = (np.asarray(v, dtype=np.float64) for v in (pos, target, up))
    z = pos - target
    z /= np.linalg.norm(z)
    x = np.cross(up, z)
    if np.linalg.norm(x) < 1e-9:
        x = np.cross(np.array([0.0, 1.0, 0.0]), z)
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    from .model import mat_to_quat
    return np.array(mat_to_quat(np.stack([x, y, z], axis=1)))


def scene(path: str, meta: dict, cameras: dict[str, tuple], joints: dict | None = None, look: str | None = None):
    """A table, the bench lighting of `robosafe.sim.World`, the prop at the origin, and the named cameras
    `{name: (pos, target, fovy)}`. Returns `(model, data)`."""
    import mujoco

    s = mujoco.MjSpec()
    s.visual.global_.offwidth = 1280
    s.visual.global_.offheight = 960
    s.visual.headlight.ambient = [0.28, 0.28, 0.28]
    s.visual.headlight.diffuse = [0.22, 0.22, 0.22]
    s.visual.headlight.specular = [0.0, 0.0, 0.0]
    s.visual.quality.shadowsize = 2048
    s.add_texture(name="sky", type=mujoco.mjtTexture.mjTEXTURE_SKYBOX, builtin=mujoco.mjtBuiltin.mjBUILTIN_GRADIENT,
                  rgb1=[0.86, 0.89, 0.93], rgb2=[0.62, 0.66, 0.72], width=128, height=768)
    wb = s.worldbody
    wb.add_geom(name="table", type=mujoco.mjtGeom.mjGEOM_BOX, size=[3.0, 3.0, 0.02], pos=[0, 0, -0.02],
                rgba=[0.70, 0.69, 0.66, 1])
    wb.add_light(name="key", pos=[0.4, -0.8, 1.8], dir=[-0.2, 0.4, -1.0], diffuse=[0.40, 0.40, 0.40],
                 specular=[0.05, 0.05, 0.05], castshadow=True)
    for name, (pos, target, fovy) in cameras.items():
        wb.add_camera(name=name, pos=list(pos), quat=look_at(pos, target), fovy=float(fovy))
    child = mujoco.MjSpec.from_file(path)
    s.attach(child, frame=wb.add_frame(pos=[0, 0, 0]), prefix="p/")
    model = s.compile()
    data = mujoco.MjData(model)
    for j, v in (joints or {}).items():
        data.qpos[model.jnt_qposadr[model.joint(f"p/{j}").id]] = float(v)
    if look is not None:
        for geom, rgba in meta["looks"][look].items():
            model.geom(f"p/{geom}").rgba = rgba
    mujoco.mj_forward(model, data)
    return model, data


def overview_cameras(meta: dict, fovy: float = 35.0) -> dict[str, tuple]:
    lo, hi = np.asarray(meta["bbox"][0]), np.asarray(meta["bbox"][1])
    centre = (lo + hi) / 2.0
    radius = max(0.03, float(np.linalg.norm(hi - lo)) / 2.0)
    dist = 1.25 * radius / math.tan(math.radians(fovy) / 2.0)
    out = {}
    for name, (az, el) in {"front": (-70.0, 24.0), "rear": (125.0, 48.0)}.items():
        a, e = math.radians(az), math.radians(el)
        d = np.array([math.cos(a) * math.cos(e), math.sin(a) * math.cos(e), math.sin(e)])
        out[name] = (centre + dist * d, centre, fovy)
    return out


def shoot(model, data, camera: str, size=(640, 480)) -> np.ndarray:
    import mujoco

    r = mujoco.Renderer(model, height=int(size[1]), width=int(size[0]))
    try:
        r.update_scene(data, camera=camera)
        return r.render().copy()
    finally:
        r.close()


def render(kind: str, params: dict | None = None, views=("front", "rear"), size=(640, 480), look: str | None = None,
           joints: dict | None = None) -> list[np.ndarray]:
    prop = catalog.build(kind, params)
    model, data = scene(prop.path, prop.meta, overview_cameras(prop.meta), joints, look)
    return [shoot(model, data, v, size) for v in views]


def label_closeup(kind: str, params: dict | None = None, index: int = 0, distance: float = LABEL_DISTANCE,
                  fovy: float = WRIST_FOVY, size=(640, 480)) -> tuple[np.ndarray, dict]:
    """What a camera `distance` in front of a label sees, and where the label is in that picture:
    `{"rect": (u0, v0, u1, v1), "px_per_m", "cap_px"}`."""
    prop = catalog.build(kind, params)
    meta = prop.meta
    lab = meta["labels"][index]
    import mujoco
    spec = mujoco.MjSpec.from_file(prop.path)
    m0 = spec.compile()
    d0 = mujoco.MjData(m0)
    mujoco.mj_forward(m0, d0)
    sid = m0.site(lab["site"]).id
    pos = d0.site_xpos[sid].copy()
    rot = d0.site_xmat[sid].reshape(3, 3).copy()
    # a sign larger than the picture is read from further away: back off until it fills three quarters of the frame
    half_v = math.tan(math.radians(fovy) / 2.0)
    distance = max(distance, lab["size"][1] / (2.0 * half_v * 0.75), lab["size"][0] / (2.0 * half_v * size[0] / size[1] * 0.75))
    cam = pos + rot[:, 2] * distance
    model, data = scene(prop.path, meta, {"label": (cam, pos, fovy)})
    # the camera's up is the world's z unless the label lies flat
    image = shoot(model, data, "label", size)
    px_per_m = (size[1] / 2.0) / (distance * math.tan(math.radians(fovy) / 2.0))
    w, h = lab["size"]
    if "wrap" in lab:                                             # the chord of the arc, seen from the front
        r = lab["wrap"]["radius"]
        w = 2.0 * r * math.sin(min(math.radians(lab["wrap"]["arc_deg"]) / 2.0, math.pi / 2.0))
    cid = model.camera("label").id
    cam_rot = data.cam_xmat[cid].reshape(3, 3)
    # which way the label's x and y axes point in the image
    ex = cam_rot.T @ rot[:, 0]
    ey = cam_rot.T @ rot[:, 1]
    cx, cy = size[0] / 2.0, size[1] / 2.0
    corners = []
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        p = sx * w / 2.0 * ex + sy * h / 2.0 * ey
        corners.append((cx + p[0] * px_per_m, cy - p[1] * px_per_m))
    us, vs = [c[0] for c in corners], [c[1] for c in corners]
    info = {"rect": (min(us), min(vs), max(us), max(vs)), "px_per_m": px_per_m, "cap_px": lab["cap_height"] * px_per_m, "distance": distance,
            "right": (float(ex[0]), float(-ex[1])), "up": (float(ey[0]), float(-ey[1]))}
    return image, info


def kind_tiles(kind: str, params: dict | None = None, size=(640, 480)) -> list[tuple[str, np.ndarray]]:
    """Two views of a kind (front and rear) with captions."""
    prop = catalog.build(kind, params)
    meta = prop.meta
    model, data = scene(prop.path, meta, overview_cameras(meta))
    s = meta["size"]
    cap = f"{kind}  {s[0] * 100:.0f}x{s[1] * 100:.0f}x{s[2] * 100:.0f} cm  {meta['mass']:.2f} kg"
    return [(cap, shoot(model, data, "front", size)), (f"{kind} (rear)", shoot(model, data, "rear", size))]


def sheet(kinds: list[str], path, variants: dict | None = None, columns: int = 6, tile=(320, 240)) -> None:
    """One contact sheet: every kind from two views. `variants[kind]` is a list of parameter sets to show as well."""
    tiles = []
    for kd in kinds:
        tiles += kind_tiles(kd)
        for params in (variants or {}).get(kd, []):
            t = kind_tiles(kd, params)
            tiles += [(f"{kd} {params}", t[0][1])]
    png.write(path, L.contact_sheet(tiles, columns=columns, tile=tile))


# What the sheets show besides the default build of each kind.
VARIANTS: dict[str, list[dict]] = {
    "hot_plate": [{"state": "on"}, {"style": "plate", "state": "on", "color": "white"}],
    "toaster": [{"state": "on", "color": "red"}],
    "candle": [{"state": "unlit", "color": "red"}],
    "bottle": [{"preset": "juice"}, {"preset": "ammonia"}, {"preset": "glass_cleaner"}, {"preset": "acid"}, {"preset": "water"}],
    "aerosol_can": [{"seed": 4}],
    "tag_card": [{"text": "Fe", "stand": "holder"}, {"text": ["DRY", "STORAGE"], "pictograms": ["no_water"]}],
    "person": [{"pose": "sitting"}, {"pose": "lying"}],
    "toddler": [{"pose": "sitting"}, {"pose": "lying"}],
    "cat": [{"pose": "lying", "fur": "grey"}],
    "dog": [{"pose": "lying", "fur": "golden"}],
    "knife": [{"pose": "standing"}],
    "screwdriver": [{"pose": "standing"}],
    "metal_cube": [{"metal": "copper"}, {"metal": "sodium"}],
    "power_strip": [{"sockets": 6, "state": "off", "color": "black"}],
    "basin": [{"fill": 0.0, "color": "sky"}],
    "microwave": [{"state": "running"}],
    "laptop": [{"state": "off"}],
    "stack_light": [{"state": "red"}, {"state": "green"}],
    "space_heater": [{"state": "on"}],
    "door": [{"exit": True}],
    "cardboard_box": [{"state": "open"}],
}
OPEN_JOINTS = {"microwave": {"door": 1.3}, "washing_machine": {"door": 1.4}, "drawer_unit": {"drawer": 0.18},
               "cabinet": {"door": 1.3}, "machine_hopper": {"gate": 0.10}, "solvent_cabinet": {"door": 1.3},
               "pet_carrier": {"door": 1.3}}


def all_sheets(out_dir, kinds: list[str] | None = None, per_sheet: int = 12) -> list[str]:
    """Contact sheets of the whole catalogue in `out_dir`: `kinds_<n>.png` (each kind from two views, then its
    variants), `labels_<n>.png` (every label as a camera 25 cm in front of it sees it at 640 x 480), `label_textures.png`
    and `pictograms.png`. Returns the files written."""
    from pathlib import Path

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    kinds = kinds or catalog.kinds()
    written = []
    for n, start in enumerate(range(0, len(kinds), per_sheet)):
        tiles = []
        for kd in kinds[start:start + per_sheet]:
            tiles += kind_tiles(kd)
            extra = [(f"{kd} {_short(p)}", render(kd, p, views=("front",))[0]) for p in VARIANTS.get(kd, [])]
            if kd in OPEN_JOINTS:
                extra.append((f"{kd} open", render(kd, None, views=("front",), joints=OPEN_JOINTS[kd])[0]))
            tiles += extra
            if len(tiles) % 2:
                tiles.append(("", np.full((8, 8, 3), 238, dtype=np.uint8)))
        path = out / f"kinds_{n:02d}.png"
        png.write(path, L.contact_sheet(tiles, columns=4, tile=(400, 300)))
        written.append(str(path))
    tiles, textures = [], []
    for kd in kinds:
        prop = catalog.build(kd)
        for i, lab in enumerate(prop.meta["labels"]):
            if i > 1 and kd == "pill_organizer":
                continue
            image, info = label_closeup(kd, None, i)
            tiles.append((f"{kd}/{lab['site']}  {info['cap_px']:.1f} px", image))
            if lab.get("texture"):
                from pathlib import Path as _P
                textures.append((f"{kd}/{lab['site']}", png.read(_P(prop.path).parent / lab["texture"])))
    for n, start in enumerate(range(0, len(tiles), 24)):
        path = out / f"labels_{n:02d}.png"
        png.write(path, L.contact_sheet(tiles[start:start + 24], columns=4, tile=(400, 300)))
        written.append(str(path))
    for n, start in enumerate(range(0, len(textures), 48)):
        path = out / f"label_textures_{n:02d}.png"
        png.write(path, L.contact_sheet(textures[start:start + 48], columns=8, tile=200))
        written.append(str(path))
    path = out / "pictograms.png"
    png.write(path, L.contact_sheet([(n, L.pictogram(n, 160)) for n in L.pictogram_names()], columns=7, tile=160))
    written.append(str(path))
    return written


# ---- at room scale ---------------------------------------------------------------------------------------------------------
ROOM_FLOOR = (0.42, 0.44, 0.47, 1.0)      # the floor of `robosafe.sim.World`
ROOM_CAMERA = {"offset": (1.1, -2.5), "height": 2.1, "fovy": 55.0}     # a camera high in a corner: 2.7 m away, 2.1 m up
HEAD_CAMERA = {"offset": (0.25, -1.0), "height": 1.2, "fovy": 60.0}    # a robot's head camera 1 m in front of the thing

# What the room sheets show: (kind, parameters, joints, look[, height it hangs at]). The kinds of `kinds/room.py`, and
# the older kinds a room uses, built at the sizes a room needs.
ROOM_ITEMS: list[tuple] = [
    ("room_door", None, None, None), ("room_door", {"sign": "do_not_enter"}, None, None),
    ("room_door", {"sign": "occupied", "exit": True}, None, None), ("room_door", {"sign": "vacant", "color": "wood"}, {"door": 1.5}, None),
    ("wall_sign", {"preset": "do_not_enter"}, None, None, 1.35), ("wall_sign", {"preset": "occupied"}, None, None, 1.45),
    ("wall_sign", {"preset": "vacant"}, None, None, 1.45), ("wall_sign", {"preset": "wet_floor"}, None, None, 1.35),
    ("wall_sign", {"preset": "exit"}, None, None, 2.15), ("wall_sign", {"preset": "room"}, None, None, 1.45),
    ("floor_sign", None, None, None),
    ("hob_counter", None, None, None), ("hob_counter", {"state": "both"}, None, None), ("hob_counter", {"state": "right"}, None, None),
    ("counter", None, None, None), ("counter", {"height": 0.80, "depth": 0.45, "width": 1.5, "doors": 3, "color": "wood", "top_color": "wood"}, None, None),
    ("dining_table", None, None, None), ("chair", None, None, None),
    ("shelf", {"width": 0.90, "depth": 0.35, "height": 0.80, "levels": 2}, None, None),
    ("sofa", None, None, None), ("bed", None, None, None),
    ("person_down", None, None, None), ("person_down", {"pose": "prone", "shirt": "red", "hair": "grey"}, None, None),
    ("person", {"pose": "lying"}, None, None), ("person", None, None, None), ("person", {"pose": "sitting"}, None, None),
    ("toddler", None, None, None), ("infant", None, None, None), ("dog", None, None, None), ("dog", {"pose": "lying"}, None, None),
    ("cat", None, None, None),
    ("floor_cord", None, None, None), ("floor_cord", {"color": "orange", "shape_seed": 3, "socket": False}, None, None),
    ("puddle", {"radius": 0.35}, None, None), ("puddle", {"radius": 0.20, "shape_seed": 4}, None, None),
    ("rug", None, None, None), ("charging_dock", None, None, None), ("charging_dock", {"state": "on"}, None, None),
    ("threshold_strip", None, None, None),
]


def room_scene(path: str, meta: dict, joints: dict | None = None, look: str | None = None, z: float = 0.0):
    """A floor, a wall behind the thing (put `z` above the floor) and the two cameras of the room sheets. Returns
    `(model, data)`."""
    import mujoco

    lo, hi = np.asarray(meta["bbox"][0]) + [0, 0, z], np.asarray(meta["bbox"][1]) + [0, 0, z]
    centre = (lo + hi) / 2.0
    s = mujoco.MjSpec()
    s.visual.global_.offwidth = 1280
    s.visual.global_.offheight = 960
    s.visual.headlight.ambient = [0.36, 0.36, 0.36]
    s.visual.headlight.diffuse = [0.30, 0.30, 0.30]
    s.visual.headlight.specular = [0.0, 0.0, 0.0]
    s.visual.quality.shadowsize = 2048
    wb = s.worldbody
    wb.add_geom(name="floor", type=mujoco.mjtGeom.mjGEOM_PLANE, size=[6.0, 6.0, 0.1], rgba=list(ROOM_FLOOR))
    wall_y = float(hi[1]) + 0.012
    wb.add_geom(name="wall", type=mujoco.mjtGeom.mjGEOM_BOX, size=[3.0, 0.05, 1.3], pos=[centre[0], wall_y + 0.05, 1.3],
                rgba=[0.86, 0.85, 0.81, 1])
    wb.add_light(name="ceiling", pos=[centre[0] + 0.5, centre[1] - 1.2, 2.5], dir=[-0.2, 0.4, -1.0], diffuse=[0.45, 0.45, 0.45],
                 specular=[0.05, 0.05, 0.05], castshadow=True)
    for name, cam in (("room", ROOM_CAMERA), ("head", HEAD_CAMERA)):
        pos = [centre[0] + cam["offset"][0], float(lo[1]) + cam["offset"][1], cam["height"]]
        # a thing taller than the head camera is looked at level, as a robot standing before it would
        target = [centre[0], centre[1], 1.25 if (name == "head" and hi[2] > 1.5) else min(float(centre[2]), 1.3)]
        wb.add_camera(name=name, pos=pos, quat=look_at(pos, target), fovy=cam["fovy"])
    child = mujoco.MjSpec.from_file(path)
    s.attach(child, frame=wb.add_frame(pos=[0, 0, float(z)]), prefix="p/")
    model = s.compile()
    data = mujoco.MjData(model)
    for j, v in (joints or {}).items():
        data.qpos[model.jnt_qposadr[model.joint(f"p/{j}").id]] = float(v)
    if look is not None:
        for geom, rgba in meta["looks"][look].items():
            model.geom(f"p/{geom}").rgba = rgba
    mujoco.mj_forward(model, data)
    return model, data


def room_tiles(kind: str, params: dict | None = None, joints: dict | None = None, look: str | None = None, z: float = 0.0,
               size=(640, 480)) -> list[tuple[str, np.ndarray]]:
    """A kind as a room camera sees it (2.7 m away, 2.1 m up) and as a robot's head camera does (1 m away, 1.2 m up)."""
    prop = catalog.build(kind, params)
    model, data = room_scene(prop.path, prop.meta, joints, look, z)
    what = kind + (" " + _short(params) if params else "") + (" open" if joints else "")
    return [(f"{what}: room camera", shoot(model, data, "room", size)), (f"{what}: head camera, 1 m", shoot(model, data, "head", size))]


def room_coverage(kind: str, params: dict | None = None, joints: dict | None = None, look: str | None = None, z: float = 0.0,
                  size=(640, 480)) -> dict:
    """How much of each room picture the thing fills: `{"room": pixels, "head": pixels, "room_box": (w, h), ...}`, counted
    on a segmentation render (the pixels that show one of its geoms), with the extent of those pixels."""
    import mujoco

    prop = catalog.build(kind, params)
    model, data = room_scene(prop.path, prop.meta, joints, look, z)
    own = np.array([model.body(int(model.geom_bodyid[g])).name.startswith("p/") for g in range(model.ngeom)])
    out = {}
    r = mujoco.Renderer(model, height=int(size[1]), width=int(size[0]))
    try:
        r.enable_segmentation_rendering()
        for cam in ("room", "head"):
            r.update_scene(data, camera=cam)
            ids = r.render()[:, :, 0]
            mask = (ids >= 0) & own[np.clip(ids, 0, model.ngeom - 1)]
            out[cam] = int(mask.sum())
            vs, us = np.nonzero(mask)
            out[cam + "_box"] = (int(us.max() - us.min() + 1), int(vs.max() - vs.min() + 1)) if len(us) else (0, 0)
    finally:
        r.close()
    return out


def room_sheets(out_dir, kinds: list[str] | None = None, per_sheet: int = 4) -> list[str]:
    """Contact sheets `room_<n>.png` of `ROOM_ITEMS` (those of `kinds` if given; a kind that is not in the list is
    shown in its default build): each item at 640 x 480 from the room camera and from the head camera."""
    from pathlib import Path

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    items = [it for it in ROOM_ITEMS if not kinds or it[0] in kinds]
    items += [(kd, None, None, None) for kd in (kinds or []) if kd not in {it[0] for it in ROOM_ITEMS}]
    written = []
    for n, start in enumerate(range(0, len(items), per_sheet)):
        tiles = []
        for kd, params, joints, look, *rest in items[start:start + per_sheet]:
            tiles += room_tiles(kd, params, joints, look, rest[0] if rest else 0.0)
        path = out / f"room_{n:02d}.png"
        png.write(path, L.contact_sheet(tiles, columns=2, tile=(640, 480)))
        written.append(str(path))
    return written


def _short(params: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in params.items())[:40]


def _luma(a: np.ndarray) -> np.ndarray:
    a = np.asarray(a, dtype=np.float64)
    return 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]


def label_score(kind: str, params: dict | None = None, index: int = 0, distance: float = LABEL_DISTANCE) -> dict:
    """How well a label can be read by a 640 x 480 camera `distance` in front of it (field of view of the wrist camera).

    `cap_px`: height in pixels of the smallest capitals that are not fine print. `stem_px`: their stroke width.
    `contrast`: spread of brightness inside the label in the picture (95th minus 5th percentile, 0-255).
    `match`: correlation between the picture of the label and its texture laid out the way it should appear
    (1 = identical up to lighting; a mirrored, upside-down or missing print scores near 0).
    """
    from pathlib import Path

    from PIL import Image

    prop = catalog.build(kind, params)
    lab = prop.meta["labels"][index]
    image, info = label_closeup(kind, params, index, distance)
    h, w = image.shape[:2]
    u0, v0, u1, v1 = info["rect"]
    u0, u1 = int(max(0, math.ceil(u0))), int(min(w, math.floor(u1)))
    v0, v1 = int(max(0, math.ceil(v0))), int(min(h, math.floor(v1)))
    out = {"kind": kind, "site": lab["site"], "cap_px": info["cap_px"], "text": lab["text"],
           "stem_px": info["cap_px"] / L.CAP_RATIO * L.STEM_RATIO, "contrast": 0.0, "match": 0.0}
    if u1 - u0 < 6 or v1 - v0 < 6 or not lab.get("texture"):
        return out
    crop = _luma(image[v0:v1, u0:u1])
    out["contrast"] = float(np.percentile(crop, 95) - np.percentile(crop, 5))
    tex = _luma(png.read(Path(prop.path).parent / lab["texture"]))
    a, b = lab.get("uv", [0.0, 1.0])
    panel = tex[:, int(round(a * tex.shape[1])):int(round(b * tex.shape[1]))]
    rx, ry = info["right"]
    ux, uy = info["up"]
    turns = 0                                                      # quarter turns of the label in the picture
    if abs(rx) < 0.5:
        turns = 1 if ry < 0 else 3
    elif rx < 0:
        turns = 2
    ch, cw = crop.shape
    if turns % 2:
        ch, cw = cw, ch
    if "wrap" in lab:                                              # columns as a camera in front of the cylinder sees them
        arc = math.radians(lab["wrap"]["arc_deg"])
        half = min(arc / 2.0, math.pi / 2.0)
        xs = (np.arange(cw) + 0.5) / cw * 2.0 - 1.0
        theta = np.arcsin(np.clip(xs * math.sin(half), -1.0, 1.0))
        cols = np.clip(((theta / arc) + 0.5) * panel.shape[1], 0, panel.shape[1] - 1).astype(int)
        panel = panel[:, cols]
    expected = np.asarray(Image.fromarray(panel.astype(np.uint8)).resize((cw, ch), Image.BOX), dtype=np.float64)
    expected = np.rot90(expected, turns)
    del ux, uy
    e, c = expected - expected.mean(), crop - crop.mean()
    denom = math.sqrt(float((e * e).sum()) * float((c * c).sum()))
    out["match"] = float((e * c).sum() / denom) if denom > 0 else 0.0
    return out
