"""Original hamburger geometry with free ingredients and passive thin layers."""

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
        path = Path(__file__).resolve().parents[2] / "shared/hands.py"
        spec = importlib.util.spec_from_file_location("hands", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules["hands"] = module
        spec.loader.exec_module(module)
        return module


hands = _hands_module()

LAYER_HALF_HEIGHT = {
    "bottom_bun": 0.013,
    "patty": 0.010,
    "cheese": 0.002,
    "tomato": 0.004,
    "lettuce": 0.0025,
    "top_bun": 0.017,
}


def node(parent, tag, **attributes):
    def value(x):
        return " ".join(str(v) for v in x) if isinstance(x, (tuple, list, np.ndarray)) else str(x)

    return ET.SubElement(parent, tag, {k: value(v) for k, v in attributes.items()})


def geom(parent, name, kind, size=None, color=(1, 1, 1, 1), **attributes):
    if size is not None:
        attributes["size"] = size
    return node(
        parent,
        "geom",
        name=name,
        type=kind,
        rgba=color,
        friction=(1.2, 0.005, 0.0001),
        condim=4,
        solref=(0.006, 1),
        solimp=(0.95, 0.99, 0.0005),
        **attributes,
    )


def visual(parent, name, kind, size=None, color=(1, 1, 1, 1), **attributes):
    return geom(parent, name, kind, size, color, contype=0, conaffinity=0, mass=0, group=2, **attributes)


def dome_mesh(assets, name, radius, height, seed=0):
    """Create an original closed, softly irregular bun dome."""
    rng = np.random.default_rng(seed)
    n, rings = 48, 10
    vertices = [[0, 0, height]]
    for j in range(1, rings + 1):
        angle = np.pi / 2 * j / rings
        for i in range(n):
            a = 2 * np.pi * i / n
            r = radius * np.sin(angle) * (1 + 0.012 * np.sin(7 * a))
            z = height * np.cos(angle) + rng.uniform(-0.0002, 0.0002)
            vertices.append([r * np.cos(a), r * np.sin(a), max(z, 0)])
    vertices.append([0, 0, 0])
    faces = [[0, 1 + i, 1 + (i + 1) % n] for i in range(n)]
    for j in range(rings - 1):
        for i in range(n):
            a, b = 1 + j * n + i, 1 + j * n + (i + 1) % n
            c, d = a + n, b + n
            faces.extend([[a, c, b], [b, c, d]])
    last, center = 1 + (rings - 1) * n, len(vertices) - 1
    faces.extend([[center, last + (i + 1) % n, last + i] for i in range(n)])
    node(
        assets,
        "mesh",
        name=name,
        vertex=np.asarray(vertices).ravel(),
        face=np.asarray(faces).ravel(),
        smoothnormal="true",
    )


def leaf_mesh(assets, name, half_x, half_y, offset=0.0):
    """A rippled visual sheet; contact uses the declared strip approximation."""
    nx, ny = 20, 12
    vertices, faces = [], []
    for j in range(ny):
        v = -1 + 2 * j / (ny - 1)
        for i in range(nx):
            u = -1 + 2 * i / (nx - 1)
            edge = 1 + 0.07 * np.cos(8 * u + 2 * v)
            z = 0.0014 * np.sin(10 * u + offset) * np.cos(8 * v) + 0.0011 * abs(v) * np.sin(19 * u)
            vertices.append([half_x * u * edge, half_y * v, z])
    for j in range(ny - 1):
        for i in range(nx - 1):
            a = j * nx + i
            faces.extend([[a, a + 1, a + nx], [a + 1, a + nx + 1, a + nx]])
    node(
        assets,
        "mesh",
        name=name,
        vertex=np.asarray(vertices).ravel(),
        face=np.asarray(faces).ravel(),
        smoothnormal="true",
    )


def add_layer(world, assets, name, position):
    b = node(world, "body", name=name, pos=position)
    node(b, "freejoint", name=name + "_free")
    h = LAYER_HALF_HEIGHT[name]
    if "bun" in name:
        top = name == "top_bun"
        geom(b, name + "_collision", "cylinder", (0.051, h), mass=0.045, color=(0.93, 0.65, 0.31, 0 if top else 1))
        if top:
            dome_mesh(assets, "bun_dome", 0.052, 0.030, seed=19)
            visual(b, "bun_crust", "mesh", mesh="bun_dome", pos=(0, 0, -h + 0.004), color=(0.78, 0.39, 0.12, 1))
            visual(b, "top_bun_crumb", "cylinder", (0.051, 0.002), pos=(0, 0, -h + 0.002), color=(0.98, 0.80, 0.47, 1))
            rng = np.random.default_rng(42)
            for i in range(42):
                x, y = rng.uniform(-0.042, 0.042, 2)
                if np.hypot(x, y) > 0.045:
                    continue
                z = -h + 0.004 + 0.030 * np.sqrt(max(0, 1 - (x * x + y * y) / 0.052**2))
                visual(
                    b,
                    f"sesame_{i}",
                    "ellipsoid",
                    (0.0021, 0.00075, 0.0005),
                    pos=(x, y, z + 0.0006),
                    euler=(0, 0, float(rng.uniform(0, np.pi))),
                    color=(0.98, 0.88, 0.61, 1),
                )
        else:
            visual(
                b, "bottom_bun_crumb", "cylinder", (0.049, 0.0004), pos=(0, 0, h + 0.0002), color=(0.99, 0.81, 0.48, 1)
            )
    elif name == "patty":
        geom(b, "patty_collision", "cylinder", (0.048, h), mass=0.055, color=(0.27, 0.12, 0.055, 1))
        rng = np.random.default_rng(33)
        for i in range(50):
            x, y = rng.uniform(-0.045, 0.045, 2)
            if np.hypot(x, y) < 0.043:
                visual(
                    b,
                    f"patty_texture_{i}",
                    "ellipsoid",
                    (0.003, 0.002, 0.0008),
                    pos=(x, y, h),
                    color=(0.16 + float(rng.uniform(0, 0.09)), 0.075, 0.028, 1),
                )
        for i in range(5):
            visual(
                b,
                f"grill_mark_{i}",
                "box",
                (0.032, 0.0012, 0.00025),
                pos=(0, (i - 2) * 0.012, h + 0.0002),
                color=(0.10, 0.055, 0.03, 1),
            )
    elif name == "tomato":
        geom(b, "tomato_collision", "cylinder", (0.046, h), mass=0.030, color=(0.79, 0.085, 0.035, 1))
        visual(b, "tomato_flesh", "cylinder", (0.043, 0.0003), pos=(0, 0, h + 0.0002), color=(0.96, 0.23, 0.12, 1))
        for i in range(5):
            a = 2 * np.pi * i / 5
            pos = (0.027 * np.cos(a), 0.027 * np.sin(a), h + 0.0006)
            visual(
                b,
                f"tomato_chamber_{i}",
                "ellipsoid",
                (0.014, 0.008, 0.0003),
                pos=pos,
                euler=(0, 0, a),
                color=(0.69, 0.095, 0.025, 1),
            )
            for k in range(3):
                visual(
                    b,
                    f"tomato_seed_{i}_{k}",
                    "ellipsoid",
                    (0.0018, 0.0009, 0.00035),
                    pos=(pos[0] + 0.005 * np.cos(a + k), pos[1] + 0.005 * np.sin(a + k), h + 0.001),
                    color=(0.98, 0.77, 0.29, 1),
                )
    else:
        lettuce = name == "lettuce"
        color = (0.24, 0.64, 0.065, 1) if lettuce else (0.98, 0.68, 0.07, 1)
        hx = 0.052 if lettuce else 0.049
        center_y = 0.018
        geom(b, name + "_center_collision", "box", (hx, center_y, h), mass=0.009 if lettuce else 0.018, color=color)
        if lettuce:
            leaf_mesh(assets, "lettuce_center_mesh", hx, center_y)
            visual(b, "lettuce_center_visual", "mesh", mesh="lettuce_center_mesh", pos=(0, 0, h), color=color)
            visual(
                b,
                "lettuce_vein",
                "capsule",
                (0.0007,),
                fromto=(-0.047, 0, h + 0.001, 0.047, 0, h + 0.001),
                color=(0.57, 0.79, 0.23, 1),
            )
        for sign in (-1, 1):
            wing = node(b, "body", name=f"{name}_wing_{sign}", pos=(0, sign * center_y, 0))
            node(
                wing,
                "joint",
                name=f"{name}_bend_{sign}",
                type="hinge",
                axis=(1, 0, 0),
                range=(-0.7, 0.7),
                stiffness=0.025 if lettuce else 0.06,
                damping=0.002,
                armature=0.000002,
            )
            geom(
                wing,
                f"{name}_wing_collision_{sign}",
                "box",
                (hx, 0.015, h),
                pos=(0, sign * 0.015, 0),
                mass=0.004 if lettuce else 0.006,
                color=color,
            )
            if lettuce:
                mesh = f"lettuce_wing_mesh_{sign}"
                leaf_mesh(assets, mesh, hx, 0.015, offset=sign)
                visual(
                    wing,
                    f"lettuce_wing_visual_{sign}",
                    "mesh",
                    mesh=mesh,
                    pos=(0, sign * 0.015, h),
                    color=(0.31, 0.72, 0.08, 1),
                )
    return b


def build(config, asset_dir=None, hand="sharpa"):
    """Compose the frozen scene with the selected genuine hand on the same six-axis wrist stage."""
    hand_id = hands.canonical(hand)
    folder = Path(
        asset_dir
        or os.environ.get("DEXHAND_ASSET_DIR")
        or Path(__file__).resolve().parents[4] / "images/dexhand/assets/hand"
    )
    root = ET.parse(folder / "right_hand.xml").getroot()
    root.set("model", hands.info(hand_id)["model"] + " hamburger assembly")
    root.find("compiler").set("meshdir", str((folder / "assets/right").resolve()))
    option = root.find("option")
    option.set("timestep", str(config["physics_dt"]))
    option.set("gravity", "0 0 -9.81")
    option.set("iterations", "80")
    option.set("integrator", "implicitfast")
    option.set("cone", "elliptic")
    node(option, "flag", multiccd="enable")
    for key in root.findall("keyframe"):
        root.remove(key)
    assets, world, actuator = root.find("asset"), root.find("worldbody"), root.find("actuator")
    hand = world.find("body")
    world.remove(hand)
    wrist = node(world, "body", name="wrist_stage")
    node(wrist, "inertial", pos=(0, 0, 0), mass=0.01, diaginertia=(0.00001,) * 3)
    hand.set("quat", "0 0.7071067811865476 0 0.7071067811865476")
    wrist.append(hand)
    for i, name in enumerate(("x", "y", "z", "rx", "ry", "rz")):
        axis = [int(i % 3 == j) for j in range(3)]
        wrist.insert(
            i,
            ET.Element(
                "joint",
                name="wrist_" + name,
                type="slide" if i < 3 else "hinge",
                axis=" ".join(map(str, axis)),
                range="-0.8 0.8" if i < 3 else "-3.14 3.14",
                damping="15" if i < 3 else "1",
                armature=".02",
            ),
        )
        actuator.insert(
            i,
            ET.Element(
                "position",
                name="wrist_" + name + "_act",
                joint="wrist_" + name,
                kp="2500" if i < 3 else "120",
                kv="80" if i < 3 else "8",
                inheritrange="1",
                forcerange="-80 80" if i < 3 else "-10 10",
            ),
        )
    for a in actuator:
        if a.tag == "general":
            bias = [float(v) for v in a.get("biasprm", "0 0 0").split()]
            bias[2] = -0.9
            a.set("biasprm", " ".join(map(str, bias)))
    for g in hand.iter("geom"):
        if "fingertip_collision" in g.get("name", ""):
            g.set("friction", "1.5 .005 .0001")
    if hand_id != "sharpa":
        # Swap the Wave body under the unchanged wrist stage for the genuine Wuji Hand 2.2 model; the vendor's
        # joints, actuators, gains and contact geometry are kept as published. Wrist actuators stay first.
        sibling = folder.parent / "wuji_v2_2"
        hands.replace_wave_hands(root, hand_id, folder=sibling if (sibling / "mjcf/right.xml").is_file() else None)
    node(
        assets,
        "texture",
        name="wood",
        type="2d",
        builtin="checker",
        width=512,
        height=512,
        rgb1=(0.62, 0.45, 0.29),
        rgb2=(0.65, 0.49, 0.33),
    )
    node(assets, "material", name="wood_material", texture="wood", texrepeat=(6, 1), reflectance=0.01)
    node(
        assets,
        "texture",
        name="studio_sky",
        type="skybox",
        builtin="gradient",
        width=256,
        height=256,
        rgb1=(0.84, 0.85, 0.81),
        rgb2=(0.94, 0.92, 0.87),
    )
    geom(world, "floor", "plane", (2, 2, 0.1), color=(0.84, 0.83, 0.79, 1))
    geom(
        world,
        "table",
        "box",
        (0.64, 0.52, 0.025),
        pos=(0, 0, config["table_z"] - 0.025),
        color=(0.69, 0.50, 0.31, 1),
        material="wood_material",
    )
    xy = config["target_xy"]
    geom(
        world,
        "serving_plate",
        "cylinder",
        (0.098, 0.006),
        pos=(*xy, config["plate_z"] - 0.006),
        color=(0.95, 0.96, 0.95, 1),
    )
    for i in range(40):
        a = 2 * np.pi * i / 40
        visual(
            world,
            f"plate_rim_{i}",
            "ellipsoid",
            (0.008, 0.003, 0.003),
            pos=(xy[0] + 0.092 * np.cos(a), xy[1] + 0.092 * np.sin(a), config["plate_z"]),
            euler=(0, 0, a + np.pi / 2),
            color=(0.85, 0.88, 0.85, 1),
        )
    add_layer(world, assets, "bottom_bun", (*xy, config["plate_z"] + LAYER_HALF_HEIGHT["bottom_bun"]))
    for i, name in enumerate(config["recipe"][1:]):
        x, y = config["source_x"], config["source_y"][i]
        geom(
            world,
            name + "_prep_support",
            "cylinder",
            (0.026, 0.0175),
            pos=(x, y, config["source_support_z"] - 0.0175),
            color=(0.80, 0.83, 0.78, 1),
        )
        add_layer(world, assets, name, (x, y, config["source_support_z"] + LAYER_HALF_HEIGHT[name]))
    node(world, "light", pos=(0.2, -0.4, 1.5), dir=(0, 0, -1), diffuse=(0.85, 0.82, 0.75))
    node(world, "light", pos=(-0.6, 0.4, 1.0), dir=(1, -1, -1), diffuse=(0.55, 0.58, 0.62))
    node(world, "camera", name="overview", pos=(0.70, -0.93, 1.03), xyaxes=(0.81, 0.59, 0, -0.30, 0.42, 0.86), fovy=39)
    node(
        world, "camera", name="closeup", pos=(0.025, -0.245, 0.535), xyaxes=(0.81, 0.59, 0, -0.26, 0.36, 0.895), fovy=35
    )
    v = node(root, "visual")
    node(v, "global", offwidth=1280, offheight=720)
    node(v, "quality", shadowsize=4096, offsamples=4)
    node(v, "headlight", ambient=(0.32, 0.32, 0.32), diffuse=(0.5, 0.5, 0.5), specular=(0.12, 0.12, 0.12))
    xml = ET.tostring(root, encoding="unicode")
    return mujoco.MjModel.from_xml_string(xml), xml
