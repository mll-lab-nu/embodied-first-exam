"""T37 ring binder (Avery 05806 reconstruction) with two rigid punched pages and one dexterous hand.

The binder hardware follows the accepted T37 scene (`scene_expansion/tasks/binder_pages/scene.py`, copied with its
sha256 into `assets/source/`): a free binder with passive spine/cover hinges, two toggle ring plates carrying three
split rings (1 in round rings, 1.3 mm wire), an over-centre spatial-tendon spring per plate (two stable stops: closed
0 rad, open 0.6 rad) and two booster paddles linked to the plates. Pages are rigid punched cardstock plates whose
collision geometry leaves three see-through holes (octagonal openings, 6.35 mm across flats), so a ring can only enter
a page through its hole. A single Sharpa Wave (or Wuji Hand 2.2) hangs from the six-axis wrist stage.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import mujoco
import numpy as np


def _hands_module():
    """The shared DexHand hand-selection module (copied next to this file in generated task dirs)."""
    try:
        import hands

        return hands
    except ModuleNotFoundError:
        # Repository layout only (generated task dirs ship hands.py next to this file).
        path = Path(__file__).resolve().parent.parent.parent / "shared/hands.py"
        spec = importlib.util.spec_from_file_location("hands", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules["hands"] = module
        spec.loader.exec_module(module)
        return module


hands = _hands_module()

# --- Binder hardware (values of the accepted T37 source scene) ---------------------------------------------------
BINDER_POS = np.array([0.48, 0.0, 0.705])
RING_RADIUS = 0.0140
WIRE_RADIUS = 0.0013
STATIONS = np.array([-0.06985, 0.0, 0.06985])
OPEN_ANGLE = 0.60
PLATE_Z = 0.006
RING_SEGMENTS = 24
DESK_TOP = 0.700
# --- Pages ------------------------------------------------------------------------------------------------------------
PAGE_W, PAGE_H = 0.1397, 0.2159  # 5.5 x 8.5 in
HOLE_RADIUS, HOLE_MARGIN = 0.003175, 0.009525  # 1/4 in punched holes, 3/8 in from the binding edge
PAGE_HALF_T = 0.0004  # stiff cardstock contact plate (visual sheet is thinner)
PAGE_MASS = 0.006


def node(parent, tag, **attributes):
    def value(x):
        return " ".join(repr(float(v)) if isinstance(v, (float, np.floating)) else str(v) for v in x) if isinstance(
            x, (tuple, list, np.ndarray)
        ) else (repr(float(x)) if isinstance(x, (float, np.floating)) else str(x))

    return ET.SubElement(parent, tag, {k: value(v) for k, v in attributes.items()})


def hard_geom(parent, name, kind, size, pos=(0, 0, 0), mass=0.0, color=(0.75, 0.77, 0.78, 1), **kw):
    """Binder hardware contact law of the source scene (steel/board, low friction)."""
    attrs = dict(name=name, type=kind, size=size, pos=pos, mass=mass, rgba=color, friction=(0.45, 0.005, 0.0001))
    attrs.update(solref=(0.004, 1), solimp=(0.95, 0.99, 0.0005))
    attrs.update(kw)
    return node(parent, "geom", **attrs)


def vis(parent, name, kind, size, pos=(0, 0, 0), color=(1, 1, 1, 1), **kw):
    if size is not None:
        kw["size"] = size
    return node(parent, "geom", name=name, type=kind, pos=pos, rgba=color, contype=0, conaffinity=0,
                mass=0, group=1, **kw)


def ring_curve(sign, n=RING_SEGMENTS):
    """Closed-ring half in its plate frame (plate hinge at the origin), as in the source scene."""
    angles = np.linspace(0, np.pi, n + 1)
    curve = np.c_[sign * (WIRE_RADIUS + RING_RADIUS * np.sin(angles)), np.zeros(len(angles)),
                  RING_RADIUS * (1 - np.cos(angles))]
    curve[:, 0] -= sign * 0.008
    return curve


def add_binder(world, tendon, equality):
    binder = node(world, "body", name="binder", pos=BINDER_POS)
    node(binder, "freejoint", name="binder_free")
    board = (0.87, 0.86, 0.82, 1)
    hard_geom(binder, "back_cover", "box", (0.0889, 0.1143, 0.0018), pos=(0.070, 0, -0.0032), mass=0.095, color=board)
    vis(binder, "back_view_film", "box", (0.087, 0.112, 0.0001), pos=(0.070, 0, -0.0051), color=(0.96, 0.96, 0.93, 1))
    hard_geom(binder, "back_pocket", "box", (0.070, 0.030, 0.0001), pos=(0.070, 0.082, -0.0013),
              color=(0.80, 0.86, 0.87, 0.25), contype=0, conaffinity=0)
    spine = node(binder, "body", name="spine", pos=(-0.0189, 0, -0.0032))
    node(spine, "joint", name="spine_fold", type="hinge", axis=(0, 1, 0), range=(-2.8, 2.8), damping=0.02,
         stiffness=0.001, armature=0.0005)
    hard_geom(spine, "spine_board", "box", (0.01778, 0.1143, 0.0018), pos=(-0.01778, 0, 0), mass=0.03,
              color=(0.92, 0.91, 0.88, 1))
    cover = node(spine, "body", name="front_cover", pos=(-0.03556, 0, 0))
    node(cover, "joint", name="cover_fold", type="hinge", axis=(0, 1, 0), range=(-3.1, 3.1), damping=0.02,
         stiffness=0.001, armature=0.0005)
    hard_geom(cover, "front_board", "box", (0.0889, 0.1143, 0.0018), pos=(-0.0889, 0, 0), mass=0.095,
              color=(0.91, 0.91, 0.87, 1))
    vis(cover, "front_view_film", "box", (0.087, 0.112, 0.0001), pos=(-0.0889, 0, -0.0019), color=(0.96, 0.96, 0.93, 1))
    vis(cover, "front_pocket", "box", (0.07, 0.03, 0.0001), pos=(-0.089, 0.082, 0.0019), color=(0.80, 0.86, 0.87, 0.35))
    steel = (0.70, 0.72, 0.74, 1)
    hard_geom(binder, "steel_backplate", "box", (0.012, 0.090, 0.0007), pos=(0, 0, 0.002), mass=0.014, color=steel)
    for k, y in enumerate((-0.083, 0.083)):
        hard_geom(binder, f"rivet_{k}", "cylinder", (0.0025, 0.001), pos=(0, y, 0.003), mass=0.001, color=steel)
    for side, sign in (("left", -1), ("right", 1)):
        plate = node(binder, "body", name=side + "_ring_plate", pos=(sign * 0.008, 0, PLATE_Z))
        node(plate, "joint", name=side + "_toggle", type="hinge", axis=(0, sign, 0), range=(0, OPEN_ANGLE),
             damping=0.01, armature=0.00002, solreflimit=(0.004, 1))
        hard_geom(plate, side + "_toggle_plate", "box", (0.0038, 0.083, 0.0005), pos=(-sign * 0.0038, 0, -0.0008),
                  mass=0.005, color=steel)
        curve = ring_curve(sign)
        for i, y in enumerate(STATIONS):
            pts = curve + np.array([0, y, 0])
            for j, (a, b) in enumerate(zip(pts[:-1], pts[1:])):
                node(plate, "geom", name=f"ring_{side}_{i}_{j}", type="capsule", fromto=np.r_[a, b],
                     size=(WIRE_RADIUS,), mass=0.004 / RING_SEGMENTS, rgba=(0.68, 0.71, 0.73, 1),
                     friction=(0.30, 0.005, 0.0001), solref=(0.004, 1), solimp=(0.95, 0.99, 0.0005))
            node(plate, "site", name=f"tip_{side}_{i}", pos=pts[-1], size=(0.0005,), group=5)
        # Over-centre housing spring (source): maximum extension at 0.30 rad, stable stops at 0 and 0.6 rad.
        qc, rad, anchor = 0.30, 0.006, 0.006
        node(plate, "site", name=side + "_spring_moving", pos=(-sign * rad, 0, 0), size=(0.0005,), group=5)
        fixed = (sign * 0.008 + sign * anchor * np.cos(qc), 0, PLATE_Z - anchor * np.sin(qc))
        node(binder, "site", name=side + "_spring_fixed", pos=fixed, size=(0.0005,), group=5)
        spring = node(tendon, "spatial", name=side + "_housing_spring", stiffness=30000, damping=0.01,
                      springlength=0.0095, width=0.0002, rgba=(0.55, 0.55, 0.55, 0.0))
        node(spring, "site", site=side + "_spring_fixed")
        node(spring, "site", site=side + "_spring_moving")
    # Internal linkage of the mechanism (both plates and both boosters move together), as in the source.
    node(equality, "joint", name="paired_toggle_plates", joint1="left_toggle", joint2="right_toggle",
         polycoef=(0, 1, 0, 0, 0), solref=(0.004, 1), solimp=(0.95, 0.99, 0.0005))
    for end in (-1, 1):
        lever = node(binder, "body", name=f"booster_{end}", pos=(0, end * 0.091, 0.0035))
        node(lever, "joint", name=f"booster_hinge_{end}", type="hinge", axis=(-end, 0, 0), range=(0, 0.90),
             damping=0.001, armature=0.00002)
        hard_geom(lever, f"booster_paddle_{end}", "box", (0.008, 0.010, 0.00065),
                  pos=(0, end * 0.010 * np.cos(0.55), 0.010 * np.sin(0.55)), mass=0.004, euler=(end * 0.55, 0, 0),
                  color=steel)
        node(lever, "site", name=f"booster_tip_{end}", pos=(0, end * 0.020 * np.cos(0.55), 0.020 * np.sin(0.55)),
             size=(0.0005,), group=5)
        node(equality, "joint", name=f"booster_link_{end}", joint1=f"booster_hinge_{end}", joint2="left_toggle",
             polycoef=(0, 1.5, 0, 0, 0), solref=(0.004, 1), solimp=(0.95, 0.99, 0.0005))
    return binder


def look_at(pos, target):
    """MuJoCo camera xyaxes for a camera at ``pos`` looking at ``target`` (world z up)."""
    f = np.asarray(target, float) - np.asarray(pos, float)
    f /= np.linalg.norm(f)
    right = np.cross(f, [0, 0, 1.0])
    right /= np.linalg.norm(right)
    up = np.cross(right, f)
    return tuple(np.round(np.r_[right, up], 5))


def octagon_hole_points(radius, n=8):
    """Vertices of a regular octagonal opening whose inscribed circle is ``radius``."""
    r = radius / np.cos(np.pi / n)
    return np.array([[r * np.cos(np.pi / n * (2 * k + 1)), r * np.sin(np.pi / n * (2 * k + 1))] for k in range(n)])


def prism_mesh(assets, name, xy, half_t):
    xy = np.asarray(xy, dtype=float)
    vertices = np.r_[np.c_[xy, np.full(len(xy), -half_t)], np.c_[xy, np.full(len(xy), half_t)]]
    node(assets, "mesh", name=name, vertex=vertices.ravel())


def sheet_visual_mesh(assets, name, half_t):
    """Closed thin sheet with three round holes (visual only): triangulated top/bottom and walls."""
    from scipy.spatial import Delaunay

    x0, x1 = -HOLE_MARGIN, PAGE_W - HOLE_MARGIN
    y0, y1 = -PAGE_H / 2, PAGE_H / 2
    outer = []
    for x in np.linspace(x0, x1, 12):
        outer.append((x, y0))
    for y in np.linspace(y0, y1, 18)[1:]:
        outer.append((x1, y))
    for x in np.linspace(x1, x0, 12)[1:]:
        outer.append((x, y1))
    for y in np.linspace(y1, y0, 18)[1:-1]:
        outer.append((x0, y))
    loops = []
    pts = list(outer)
    n_hole = 20
    for y in STATIONS:
        loop = []
        for k in range(n_hole):
            a = 2 * np.pi * k / n_hole
            loop.append(len(pts))
            pts.append((HOLE_RADIUS * np.cos(a), y + HOLE_RADIUS * np.sin(a)))
        for k in range(n_hole):
            a = 2 * np.pi * (k + 0.5) / n_hole
            pts.append((2.1 * HOLE_RADIUS * np.cos(a), y + 2.1 * HOLE_RADIUS * np.sin(a)))
        loops.append(loop)
    for x in np.linspace(x0 + 0.012, x1 - 0.01, 8):
        for y in np.linspace(y0 + 0.012, y1 - 0.012, 10):
            if min(np.hypot(x, y - s) for s in STATIONS) > 2.6 * HOLE_RADIUS:
                pts.append((x, y))
    pts = np.asarray(pts)
    tri = Delaunay(pts).simplices
    keep = []
    for f in tri:
        c = pts[f].mean(axis=0)
        if min(np.hypot(c[0], c[1] - s) for s in STATIONS) < HOLE_RADIUS * 0.999:
            continue
        v = pts[f]
        a, b = v[1] - v[0], v[2] - v[0]
        if a[0] * b[1] - a[1] * b[0] < 0:
            f = f[[0, 2, 1]]
        keep.append(f)
    keep = np.asarray(keep)
    n = len(pts)
    vertices = np.r_[np.c_[pts, np.full(n, half_t)], np.c_[pts, np.full(n, -half_t)]]
    faces = [list(f) for f in keep] + [[f[0] + n, f[2] + n, f[1] + n] for f in keep]
    boundary = list(range(len(outer)))
    for a, b in zip(boundary, boundary[1:] + boundary[:1]):
        faces += [[a, a + n, b], [b, a + n, b + n]]
    for loop in loops:
        for a, b in zip(loop, loop[1:] + loop[:1]):
            faces += [[b, a + n, a], [b + n, a + n, b]]
    node(assets, "mesh", name=name, vertex=vertices.ravel(), face=np.asarray(faces).ravel())


def add_page(world, assets, index, pos, yaw, quat=None):
    """A rigid punched page; body origin = centre of the middle hole, +x = across the sheet away from the holes."""
    if quat is None:
        body = node(world, "body", name=f"page_{index}", pos=pos, euler=(0, 0, yaw))
    else:
        body = node(world, "body", name=f"page_{index}", pos=pos, quat=quat)
    node(body, "freejoint", name=f"page_{index}_free")
    x0, x1 = -HOLE_MARGIN, PAGE_W - HOLE_MARGIN
    area = PAGE_W * PAGE_H
    cx = (x0 + x1) / 2
    node(body, "inertial", pos=(cx, 0, 0), mass=PAGE_MASS,
         diaginertia=(PAGE_MASS * PAGE_H**2 / 12, PAGE_MASS * PAGE_W**2 / 12, PAGE_MASS * (PAGE_W**2 + PAGE_H**2) / 12))
    # solmix: the stiff cardstock contact law dominates the soft fingertip elastomer (no tunnelling through the sheet).
    contact = dict(friction=(0.7, 0.005, 0.0001), condim=4, solref=(0.004, 1), solimp=(0.95, 0.99, 0.0005), solmix=1000,
                   rgba=(0.95, 0.93, 0.86, 0.0), group=3, mass=0)
    s = HOLE_RADIUS
    t = PAGE_HALF_T

    def box(name, xa, xb, ya, yb):
        node(body, "geom", name=name, type="box", size=((xb - xa) / 2, (yb - ya) / 2, t),
             pos=((xa + xb) / 2, (ya + yb) / 2, 0), **contact)

    box(f"page_{index}_left_margin", x0, -s, -PAGE_H / 2, PAGE_H / 2)
    box(f"page_{index}_sheet", s, x1, -PAGE_H / 2, PAGE_H / 2)
    edges = [-PAGE_H / 2] + [v for y in STATIONS for v in (y - s, y + s)] + [PAGE_H / 2]
    for k in range(4):
        box(f"page_{index}_bridge_{k}", -s, s, edges[2 * k], edges[2 * k + 1])
    octagon = octagon_hole_points(s)
    for i, y in enumerate(STATIONS):
        for c, (sx, sy) in enumerate(((1, 1), (-1, 1), (-1, -1), (1, -1))):
            corner = np.array([sx * s, sy * s])
            # The two octagon vertices adjacent to this square corner.
            near = sorted(octagon, key=lambda p: np.hypot(*(p - corner)))[:2]
            mesh = f"page_{index}_hole_{i}_corner_{c}"
            prism_mesh(assets, mesh, [corner, near[0], near[1]], t)
            node(body, "geom", name=mesh, type="mesh", mesh=mesh, pos=(0, y, 0), **contact)
        node(body, "site", name=f"page_{index}_hole_{i}", pos=(0, y, 0), size=(0.0008,), group=5)
    # Visual sheet with round holes, a printed heading and body lines (cosmetic only).
    vis(body, f"page_{index}_paper", "mesh", None, mesh="page_sheet_mesh", material="paper_stock")
    ink = (0.36, 0.38, 0.40, 1)
    top = t + 0.00002
    vis(body, f"page_{index}_heading", "box", (0.0011, 0.016, 0.00001), pos=(0.106, 0.035, top), color=ink)
    for k in range(13):
        length = 0.072 if k % 4 != 3 else 0.040
        vis(body, f"page_{index}_line_{k}", "box", (0.0005, length / 2, 0.00001),
            pos=(0.096 - 0.0062 * k, 0.065 - length / 2 - 0.012, top), color=(0.58, 0.60, 0.62, 1))
    return body


def build(config, asset_dir=None, hand="sharpa"):
    """Compose the frozen scene with the selected genuine hand on the six-axis wrist stage."""
    hand_id = hands.canonical(hand)
    folder = Path(asset_dir or os.environ.get("DEXHAND_ASSET_DIR") or "/opt/dexhand/hand")
    root = ET.parse(folder / "right_hand.xml").getroot()
    root.set("model", hands.info(hand_id)["model"] + " ring binder page loading")
    root.find("compiler").set("meshdir", str((folder / "assets/right").resolve()))
    option = root.find("option")
    option.set("timestep", str(config["physics_dt"]))
    option.set("gravity", "0 0 -9.81")
    option.set("iterations", "80")
    option.set("integrator", "implicitfast")
    option.set("cone", "elliptic")
    option.set("impratio", "10")
    for key in root.findall("keyframe"):
        root.remove(key)
    assets, world, actuator = root.find("asset"), root.find("worldbody"), root.find("actuator")
    hand_body = world.find("body")
    world.remove(hand_body)
    wrist = node(world, "body", name="wrist_stage", pos=config["wrist_base"])
    node(wrist, "inertial", pos=(0, 0, 0), mass=0.01, diaginertia=(0.00001,) * 3)
    # Mount: at zero wrist rotation the fingers point down (-z), the palm faces +x and the thumb is on the -y side.
    hand_body.set("quat", "0 1 0 0")
    wrist.append(hand_body)
    ranges = config["wrist_ranges"]
    for i, name in enumerate(("x", "y", "z", "rx", "ry", "rz")):
        axis = [int(i % 3 == j) for j in range(3)]
        wrist.insert(i, ET.Element("joint", name="wrist_" + name, type="slide" if i < 3 else "hinge",
                                   axis=" ".join(map(str, axis)), range=" ".join(map(str, ranges[i])),
                                   damping="15" if i < 3 else "1", armature=".02"))
        actuator.insert(i, ET.Element("position", name="wrist_" + name + "_act", joint="wrist_" + name,
                                      kp="2500" if i < 3 else "120", kv="80" if i < 3 else "8", inheritrange="1",
                                      forcerange="-80 80" if i < 3 else "-10 10"))
    for a in actuator:
        if a.tag == "general":
            bias = [float(v) for v in a.get("biasprm", "0 0 0").split()]
            bias[2] = -0.9
            a.set("biasprm", " ".join(map(str, bias)))
    for g in hand_body.iter("geom"):
        if "fingertip_collision" in g.get("name", ""):
            # Soft finger pads: sliding, torsional and rolling resistance of a ~1 cm contact patch.
            g.set("friction", "1.5 0.01 0.004")
            g.set("condim", "6")
    if hand_id != "sharpa":
        sibling = folder.parent / "wuji_v2_2"
        hands.replace_wave_hands(root, hand_id, folder=sibling if (sibling / "mjcf/right.xml").is_file() else None)
        for g in root.iter("geom"):
            if "tip_sensor_frame_collision" in g.get("name", ""):
                # Same soft-pad contact law as the Sharpa fingertips.
                g.set("friction", "1.5 0.01 0.004")
                g.set("condim", "6")
    tendon = root.find("tendon")
    if tendon is None:
        tendon = node(root, "tendon")
    equality = root.find("equality")
    if equality is None:
        equality = node(root, "equality")
    node(assets, "texture", name="desk_wood", type="2d", builtin="checker", width=512, height=512,
         rgb1=(0.54, 0.40, 0.27), rgb2=(0.56, 0.42, 0.29))
    node(assets, "material", name="desk_material", texture="desk_wood", texrepeat=(8, 2), reflectance=0.02)
    node(assets, "material", name="paper_stock", rgba=(0.97, 0.96, 0.92, 1), specular=0.05)
    node(assets, "texture", name="studio_sky", type="skybox", builtin="gradient", width=256, height=256,
         rgb1=(0.62, 0.66, 0.66), rgb2=(0.86, 0.86, 0.84))
    sheet_visual_mesh(assets, "page_sheet_mesh", 0.00015)
    ground = dict(friction=(0.6, 0.005, 0.0001), solref=(0.004, 1), solimp=(0.95, 0.99, 0.0005))
    node(world, "geom", name="floor", type="plane", size=(3, 3, 0.05), pos=(0, 0, 0), rgba=(0.65, 0.68, 0.67, 1),
         **ground)
    node(world, "geom", name="desk", type="box", size=(0.39, 0.43, 0.022), pos=(0.59, 0.05, DESK_TOP - 0.022),
         rgba=(0.54, 0.40, 0.27, 1), material="desk_material", **ground)
    for x in (0.25, 0.93):
        for y in (-0.31, 0.41):
            node(world, "geom", name=f"desk_leg_{x}_{y}", type="box", size=(0.022, 0.022, 0.339),
                 pos=(x, y, 0.339), rgba=(0.25, 0.24, 0.21, 1), contype=0, conaffinity=0, group=1)
    add_binder(world, tendon, equality)
    for i, (px, py) in enumerate(config["page_xy"]):
        # loose sheets lying flat on the desk as in the source (T37 scene.py: page origin = middle hole centre)
        add_page(world, assets, i, (px, py, DESK_TOP + PAGE_HALF_T), 0.0)
    node(world, "light", pos=(0.5, -1.0, 2.3), dir=(0, 0.3, -1), diffuse=(0.7, 0.7, 0.68), castshadow="true")
    node(world, "light", pos=(0.1, 1.2, 2.0), dir=(0.3, -0.3, -1), diffuse=(0.4, 0.4, 0.42), castshadow="false")
    cams = {
        "overview": ((1.08, -0.62, 1.28), (0.62, 0.0, 0.72), 42),
        "closeup": ((0.74, -0.34, 0.98), (0.51, 0.0, 0.72), 45),
        "rings": ((0.64, -0.21, 0.86), (0.49, 0.0, 0.725), 45),
        "pages": ((0.62, -0.45, 1.00), (0.82, 0.10, 0.70), 50),
    }
    for name, (cpos, target, fovy) in cams.items():
        node(world, "camera", name=name, pos=cpos, xyaxes=look_at(cpos, target), fovy=fovy)
    v = root.find("visual")
    if v is None:
        v = node(root, "visual")
    node(v, "global", offwidth=1280, offheight=720)
    node(v, "quality", shadowsize=4096, offsamples=4)
    node(v, "headlight", ambient=(0.30, 0.30, 0.30), diffuse=(0.45, 0.45, 0.45), specular=(0.1, 0.1, 0.1))
    xml = ET.tostring(root, encoding="unicode")
    return mujoco.MjModel.from_xml_string(xml), xml
