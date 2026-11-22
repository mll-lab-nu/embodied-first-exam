"""T49 batter-whisk scene: Roesle bowl with (non-simulated) batter, free balloon whisk, one dexterous hand.

Geometry follows the accepted T49 source (scene_expansion/tasks/batter_mix): counter top at z = 0.68 m, the
Roesle 150672 deep bowl (12 cm, 233 g) and the Roesle 950633 balloon whisk (345 mm, 220 g, 25 mm handle).
The original authored bowl and wire meshes are used for the look; contact uses convex proxies of the same
profile (thin meridional wall strips, floor disc, rolled rim; handle cylinder and wire-loop capsules).
Robot (``config["rig"] == "marvin"``): the Tianji Marvin stand at the world origin facing +x with both 7-DoF arms and a
dexterous hand on each flange (``arm_rig.mount_marvin``); the right hand whisks, the left hand holds the bowl.
Legacy rig (no ``rig`` key): one hand on a six-axis wrist stage at the world origin (wrist_x/y/z = world position of the
grip point, wrist_rx/ry/rz serial XYZ rotations about it).
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

HERE = Path(__file__).resolve().parent


def _hands_module():
    """The shared DexHand hand-selection module (copied next to this file in generated task dirs)."""
    try:
        import hands

        return hands
    except ModuleNotFoundError:
        path = HERE.parents[1] / "shared/hands.py"
        spec = importlib.util.spec_from_file_location("hands", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules["hands"] = module
        spec.loader.exec_module(module)
        return module


hands = _hands_module()


def _arm_rig_module():
    """The shared Marvin arm rig (copied next to this file in generated task dirs)."""
    try:
        import arm_rig

        return arm_rig
    except ModuleNotFoundError:
        for parent in HERE.parents:
            path = parent / "shared/arm_rig.py"
            if path.is_file():
                spec = importlib.util.spec_from_file_location("arm_rig", path)
                module = importlib.util.module_from_spec(spec)
                sys.modules["arm_rig"] = module
                spec.loader.exec_module(module)
                return module
        raise

# Bowl inner profile (radius, height) in the bowl frame, from the T49 source geometry.
PROFILE = np.array(
    [
        [0.029, 0.000],
        [0.030, 0.003],
        [0.039, 0.008],
        [0.049, 0.018],
        [0.056, 0.031],
        [0.059, 0.047],
        [0.060, 0.072],
        [0.060, 0.076],
    ]
)
BOWL_HEIGHT = 0.078
BOWL_MASS = 0.233
BATTER_MASS = 0.2521344  # the T49 charge (469 parcels), lumped rigidly into the bowl (not simulated)
BATTER_DENSITY = 1050.0
FLOOR_TOP = 0.003
HANDLE_BOTTOM, HANDLE_TOP, HANDLE_RADIUS = 0.230, 0.345, 0.0125
WIRE_LENGTH, WIRE_HALF_WIDTH, LOOPS = 0.230, 0.035, 8
WHISK_MASS = 0.220


def inner_radius(z):
    return np.interp(z, PROFILE[:, 1], PROFILE[:, 0])


def batter_height():
    """Height of the 240 ml batter surface above the bowl origin (same integration as the T49 source)."""
    volume = BATTER_MASS / BATTER_DENSITY
    zz = np.linspace(FLOOR_TOP, 0.076, 6000)
    cum = np.cumsum(np.pi * inner_radius(zz) ** 2) * (zz[1] - zz[0])
    return float(np.interp(volume, cum, zz))


def wire_centerlines(points_per_strand=9):
    """Closed balloon loops (pairs of strands) on the T49 radius law: 8 loops, 23 cm long, 7 cm wide."""
    t = np.linspace(0, 1, 2 * (points_per_strand - 1) + 1)
    z = WIRE_LENGTH * t
    radius = np.sin(np.pi * t) ** 1.7 * np.exp(-1.45 * np.maximum(t - 0.33, 0))
    radius *= WIRE_HALF_WIDTH / radius.max()
    loops = []
    for loop in range(LOOPS):
        a = loop * np.pi / LOOPS
        direction = np.array([np.cos(a), np.sin(a), 0.0])
        plus = radius[:, None] * direction + np.c_[0 * t, 0 * t, z]
        minus = -radius[:, None] * direction + np.c_[0 * t, 0 * t, z]
        loops.append(np.vstack([plus, minus[-2::-1]]))
    return loops


def head_radius(z):
    """Balloon radius of the whisk head at height z (whisk frame)."""
    t = np.clip(np.asarray(z) / WIRE_LENGTH, 0, 1)
    tt = np.linspace(0, 1, 2001)
    r = np.sin(np.pi * tt) ** 1.7 * np.exp(-1.45 * np.maximum(tt - 0.33, 0))
    return np.interp(t, tt, r * WIRE_HALF_WIDTH / r.max())


def node(parent, tag, **attributes):
    def value(x):
        if isinstance(x, np.ndarray) and x.dtype.kind in "iu":
            return " ".join(str(int(v)) for v in x.ravel())
        if isinstance(x, (tuple, list, np.ndarray)):
            return " ".join(repr(float(v)) if not isinstance(v, str) else v for v in np.ravel(x))
        return str(x)

    return ET.SubElement(parent, tag, {k: value(v) for k, v in attributes.items()})


def quat_from_matrix(R):
    q = np.empty(4)
    mujoco.mju_mat2Quat(q, np.asarray(R, dtype=float).ravel())
    return q


def _batter_inertia():
    """Mass, COM height and diagonal inertia (about the COM) of the batter charge as a solid of revolution."""
    h = batter_height()
    zz = np.linspace(FLOOR_TOP, h, 400)
    dz = zz[1] - zz[0]
    r = inner_radius(zz)
    dm = BATTER_DENSITY * np.pi * r**2 * dz
    dm *= BATTER_MASS / dm.sum()
    zc = float((dm * zz).sum() / dm.sum())
    izz = float((0.5 * dm * r**2).sum())
    ixx = float((dm * (r**2 / 4 + (zz - zc) ** 2)).sum())
    return zc, ixx, izz


def bowl_inertial():
    """Bowl shell (source values) + rigid batter charge combined about their joint COM."""
    zb, ib = 0.036, np.array([0.00043, 0.00043, 0.00067])
    zc, ixx, izz = _batter_inertia()
    m = BOWL_MASS + BATTER_MASS
    z = (BOWL_MASS * zb + BATTER_MASS * zc) / m
    i_x = ib[0] + BOWL_MASS * (zb - z) ** 2 + ixx + BATTER_MASS * (zc - z) ** 2
    return m, z, (i_x, i_x, ib[2] + izz)


def add_bowl(world, assets, config):
    b = node(world, "body", name="bowl", pos=config["bowl_pos"])
    node(b, "freejoint", name="bowl_free")
    mass, zc, inertia = bowl_inertial()
    node(b, "inertial", pos=(0, 0, zc), mass=mass, diaginertia=inertia)
    node(b, "geom", name="bowl_visible", type="mesh", mesh="bowl_visible", material="steel", contype=0,
         conaffinity=0, group=2, mass=0)
    common = dict(material="steel_proxy", group=3, mass=0, friction=(0.2, 0.002, 0.0001), condim=3,
                  solref=(0.004, 1), solimp=(0.95, 0.99, 0.0005))
    sectors, wall = config["bowl_sectors"], config["bowl_wall_proxy_m"]
    da = 2 * np.pi / sectors
    for i in range(sectors):
        a = i * da
        for j in range(len(PROFILE) - 1):
            (r0, z0), (r1, z1) = PROFILE[j], PROFILE[j + 1]
            v = []
            for theta in (a - 0.02 * da, a + 1.02 * da):
                for r, z in ((r0, z0), (r1, z1), (r1 + wall, z1), (r0 + wall, z0)):
                    v.append((r * np.cos(theta), r * np.sin(theta), z))
            name = f"bowl_wall_{i}_{j}"
            node(assets, "mesh", name=name, vertex=np.asarray(v))
            node(b, "geom", name=name, type="mesh", mesh=name, **common)
    node(b, "geom", name="bowl_floor", type="cylinder", size=(0.0305, FLOOR_TOP / 2), pos=(0, 0, FLOOR_TOP / 2),
         **{**common, "friction": (0.4, 0.002, 0.0001)})
    for i in range(sectors):
        a0, a1 = i * da, (i + 1) * da
        node(b, "geom", name=f"bowl_rim_{i}", type="capsule", size=(0.0018,),
             fromto=(0.0618 * np.cos(a0), 0.0618 * np.sin(a0), 0.076, 0.0618 * np.cos(a1), 0.0618 * np.sin(a1), 0.076),
             **common)
    # Batter surface: visual only (the batter is not simulated; its mass is part of the bowl inertial).
    h = batter_height()
    radius = float(inner_radius(h) - 0.0004)
    rings, segments = 10, 64
    vertices, faces = [[0.0, 0.0, h]], []
    for k in range(1, rings + 1):
        rr = radius * k / rings
        for s in range(segments):
            a = 2 * np.pi * s / segments
            ripple = 0.0006 * np.sin(5 * a + 9 * rr / radius) * (k / rings) * (1 - k / rings)
            vertices.append([rr * np.cos(a), rr * np.sin(a), h + ripple])
    for s in range(segments):
        faces.append([0, 1 + s, 1 + (s + 1) % segments])
    for k in range(rings - 1):
        for s in range(segments):
            p, q = 1 + k * segments + s, 1 + k * segments + (s + 1) % segments
            faces.extend([[p, p + segments, q], [q, p + segments, q + segments]])
    node(assets, "mesh", name="batter_surface", vertex=np.asarray(vertices), face=np.asarray(faces, dtype=int).ravel(),
         smoothnormal="true")
    node(b, "geom", name="batter_surface", type="mesh", mesh="batter_surface", material="batter", contype=0,
         conaffinity=0, group=2, mass=0)
    return b


def add_whisk(world, config):
    w = node(world, "body", name="whisk", pos=config["whisk_pos"], quat=config.get("whisk_quat", (1, 0, 0, 0)))
    node(w, "freejoint", name="whisk_free")
    node(w, "inertial", pos=(0, 0, 0.245), mass=WHISK_MASS, diaginertia=(0.00135, 0.00135, 0.000017))
    node(w, "geom", name="whisk_wires_visible", type="mesh", mesh="whisk_wires_visible", material="wire_steel",
         contype=0, conaffinity=0, group=2, mass=0)
    # Contact: a capsule spanning the 115 mm handle (stable analytic capsule-box contact when it lies on the
    # counter); look: the 25 mm cylinder of the source.
    node(w, "geom", name="whisk_handle", type="capsule", size=(HANDLE_RADIUS,),
         fromto=(0, 0, HANDLE_BOTTOM + HANDLE_RADIUS, 0, 0, HANDLE_TOP - HANDLE_RADIUS), material="steel", mass=0,
         condim=6, group=3, friction=(0.8, 0.005, 0.001), solref=(0.004, 1), solimp=(0.95, 0.99, 0.0005))
    node(w, "geom", name="whisk_handle_visible", type="cylinder",
         size=(HANDLE_RADIUS, (HANDLE_TOP - HANDLE_BOTTOM) / 2), pos=(0, 0, (HANDLE_TOP + HANDLE_BOTTOM) / 2),
         material="steel", contype=0, conaffinity=0, group=2, mass=0)
    node(w, "geom", name="whisk_ferrule", type="capsule", size=(0.0065,), fromto=(0, 0, 0.205, 0, 0, 0.231),
         material="steel", mass=0, condim=3, friction=(0.5, 0.002, 0.0001), solref=(0.004, 1),
         solimp=(0.95, 0.99, 0.0005))
    radius = config["wire_proxy_radius_m"]
    for loop, points in enumerate(wire_centerlines(config["wire_points_per_strand"])):
        for i in range(len(points) - 1):
            node(w, "geom", name=f"whisk_wire_{loop}_{i}", type="capsule", size=(radius,),
                 fromto=np.r_[points[i], points[i + 1]], material="wire_proxy", group=3, mass=0, condim=6,
                 friction=(0.15, 0.002, 0.0005), solref=(0.004, 1), solimp=(0.95, 0.99, 0.0005))
    node(w, "site", name="whisk_head", pos=(0, 0, config["head_point_z"]), size=(0.003,), rgba=(1, 0, 0, 0),
         group=4)
    return w


def add_room(world, config):
    z = config["table_z"]
    floor_z = float(config.get("floor_z", 0.0))
    node(world, "geom", name="floor", type="plane", size=(3, 3, 0.05), pos=(0, 0, floor_z), material="floor")
    cx, cy, hx, hy = config["counter"]
    node(world, "geom", name="counter_top", type="box", pos=(cx, cy, z - 0.025), size=(hx, hy, 0.025),
         material="stone", friction=(0.4, 0.002, 0.0001), condim=3, solref=(0.004, 1),
         solimp=(0.95, 0.99, 0.0005))
    x0, x1 = cx - hx + 0.01, cx + hx - 0.01
    if config.get("rig") == "marvin":
        # The stand's base plate reaches 0.75 m in front of the base: the cabinet under the counter starts behind it
        # (the near part of the counter top is cantilevered), so no robot geom overlaps furniture.
        x0 = max(x0, float(config["marvin"]["base_pos"][0]) + 0.77)
    node(world, "geom", name="cabinet", type="box", pos=((x0 + x1) / 2, cy, (z - 0.05 + floor_z) / 2),
         size=((x1 - x0) / 2, hy - 0.02, (z - 0.05 - floor_z) / 2), material="cabinet", contype=0, conaffinity=0,
         group=2)
    if config.get("rig") == "marvin":
        # The robot stands at the origin facing +x: the wall is behind the counter (far side).
        node(world, "geom", name="backsplash", type="box", pos=(cx + hx + 0.02, cy, z + 0.35),
             size=(0.01, hy + 0.4, 0.35 + 0.025), material="wall", contype=0, conaffinity=0, group=2)
    else:
        node(world, "geom", name="backsplash", type="box", pos=(cx, cy + hy + 0.02, z + 0.35),
             size=(hx + 0.4, 0.01, 0.35 + 0.025), material="wall", contype=0, conaffinity=0, group=2)


def add_hand_stage(root, world, actuator, hand, config):
    """Six-axis wrist stage at the world origin carrying the Sharpa Wave root body (grip point on the joint axes)."""
    stage = config["stage"]
    wrist = node(world, "body", name="wrist_stage", pos=(0, 0, 0))
    node(wrist, "inertial", pos=(0, 0, 0), mass=0.01, diaginertia=(0.00001,) * 3)
    for i, name in enumerate(("x", "y", "z", "rx", "ry", "rz")):
        axis = [int(i % 3 == j) for j in range(3)]
        lo, hi = stage["range"][i]
        wrist.insert(i, ET.Element("joint", name="wrist_" + name, type="slide" if i < 3 else "hinge",
                                   axis=" ".join(map(str, axis)), range=f"{lo} {hi}",
                                   damping="15" if i < 3 else "1", armature=".02"))
        actuator.insert(i, ET.Element("position", name="wrist_" + name + "_act", joint="wrist_" + name,
                                      kp="2500" if i < 3 else "120", kv="80" if i < 3 else "8", inheritrange="1",
                                      forcerange="-80 80" if i < 3 else "-10 10"))
    R = np.asarray(stage["mount_matrix"], dtype=float)
    hand.set("quat", " ".join(repr(float(v)) for v in quat_from_matrix(R)))
    hand.set("pos", " ".join(repr(float(v)) for v in -R @ np.asarray(stage["grip_in_hand"], dtype=float)))
    wrist.append(hand)
    return wrist


def build(config, asset_dir=None, hand="sharpa"):
    """Compose the frozen scene with the selected genuine hand on the six-axis wrist stage."""
    hand_id = hands.canonical(hand)
    candidates = [Path(p) for p in (asset_dir, os.environ.get("DEXHAND_ASSET_DIR")) if p]
    candidates.append(Path("/opt/dexhand/hand"))
    # Repository checkouts (images/dexhand/assets/hand is prepared by images/dexhand/prepare_assets.py).
    candidates += [parent / "images/dexhand/assets/hand" for parent in HERE.parents]
    candidates += [parent / "robot_coding_bench/images/dexhand/assets/hand" for parent in HERE.parents]
    folder = next((c for c in candidates if (c / "right_hand.xml").is_file()), candidates[0])
    root = ET.parse(folder / "right_hand.xml").getroot()
    root.set("model", hands.info(hand_id)["model"] + " batter whisk")
    root.find("compiler").set("meshdir", str((folder / "assets/right").resolve()))
    option = root.find("option")
    option.set("timestep", str(config["physics_dt"]))
    option.set("gravity", "0 0 -9.81")
    option.set("iterations", "60")
    option.set("integrator", "implicitfast")
    option.set("cone", "elliptic")
    for key in root.findall("keyframe"):
        root.remove(key)
    assets, world, actuator = root.find("asset"), root.find("worldbody"), root.find("actuator")
    hand = world.find("body")
    for a in actuator:
        if a.tag == "general":
            bias = [float(v) for v in a.get("biasprm", "0 0 0").split()]
            bias[2] = -0.9
            a.set("biasprm", " ".join(map(str, bias)))
    for g in hand.iter("geom"):
        if "fingertip_collision" in g.get("name", ""):
            g.set("friction", "1.5 .005 .0001")
    sibling = folder.parent / "wuji_v2_2"
    wuji_folder = sibling if (sibling / "mjcf/right.xml").is_file() else None
    if config.get("rig") == "marvin":
        marvin = config["marvin"]
        _arm_rig_module().mount_marvin(root, marvin["base_pos"], marvin["base_yaw"], hand=hand_id,
                                       active=("left", "right"), sharpa_folder=folder, wuji_folder=wuji_folder)
    else:
        world.remove(hand)
        add_hand_stage(root, world, actuator, hand, config)
        if hand_id != "sharpa":
            hands.replace_wave_hands(root, hand_id, folder=wuji_folder)
    mesh_dir = HERE / "assets"
    node(assets, "mesh", name="bowl_visible", file=str((mesh_dir / "rosle-bowl-original.obj").resolve()))
    node(assets, "mesh", name="whisk_wires_visible", file=str((mesh_dir / "rosle-whisk-wires-original.obj").resolve()))
    node(assets, "texture", name="stone_tex", type="2d", builtin="flat", width=512, height=512,
         rgb1=(0.80, 0.78, 0.73), rgb2=(0.74, 0.72, 0.67), mark="random", markrgb=(0.70, 0.68, 0.63), random=0.08)
    node(assets, "material", name="stone", texture="stone_tex", texrepeat=(4, 4), specular=0.15, shininess=0.4,
         reflectance=0.02)
    node(assets, "texture", name="floor_tex", type="2d", builtin="checker", width=512, height=512,
         rgb1=(0.45, 0.47, 0.45), rgb2=(0.42, 0.44, 0.42))
    node(assets, "material", name="floor", texture="floor_tex", texrepeat=(8, 8), reflectance=0.0)
    node(assets, "material", name="cabinet", rgba=(0.16, 0.22, 0.19, 1), specular=0.2)
    node(assets, "material", name="wall", rgba=(0.86, 0.85, 0.81, 1), specular=0.05)
    node(assets, "material", name="steel", rgba=(0.70, 0.73, 0.75, 1), specular=0.8, shininess=0.85, reflectance=0.25)
    node(assets, "material", name="wire_steel", rgba=(0.80, 0.83, 0.85, 1), specular=0.9, shininess=0.9)
    node(assets, "material", name="steel_proxy", rgba=(0.6, 0.62, 0.66, 0.4))
    node(assets, "material", name="wire_proxy", rgba=(0.9, 0.3, 0.3, 0.5))
    node(assets, "material", name="batter", rgba=(0.93, 0.83, 0.62, 1), specular=0.25, shininess=0.5)
    node(assets, "texture", name="studio_sky", type="skybox", builtin="gradient", width=256, height=256,
         rgb1=(0.84, 0.85, 0.82), rgb2=(0.95, 0.94, 0.90))
    add_room(world, config)
    add_bowl(world, assets, config)
    add_whisk(world, config)
    node(world, "light", name="key", pos=(0.3, -0.6, 2.0), dir=(0.15, 0.3, -1), diffuse=(0.80, 0.78, 0.72),
         castshadow="true")
    node(world, "light", name="fill", pos=(1.4, 0.8, 1.8), dir=(-0.4, -0.3, -1), diffuse=(0.45, 0.48, 0.52),
         castshadow="false")
    for cam in config["cameras"]:
        node(world, "camera", name=cam["name"], pos=cam["pos"], xyaxes=cam["xyaxes"], fovy=cam["fovy"])
    v = node(root, "visual")
    node(v, "global", offwidth=1280, offheight=720)
    node(v, "quality", shadowsize=4096, offsamples=4)
    node(v, "headlight", ambient=(0.34, 0.34, 0.34), diffuse=(0.45, 0.45, 0.45), specular=(0.1, 0.1, 0.1))
    xml = ET.tostring(root, encoding="unicode")
    return mujoco.MjModel.from_xml_string(xml), xml


def look_at(pos, target, up=(0, 0, 1)):
    """xyaxes for a camera at ``pos`` looking at ``target``."""
    pos, target, up = (np.asarray(v, dtype=float) for v in (pos, target, up))
    forward = target - pos
    forward /= np.linalg.norm(forward)
    x = np.cross(forward, up)
    x /= np.linalg.norm(x)
    y = np.cross(x, forward)
    return np.r_[x, y].round(6).tolist()
