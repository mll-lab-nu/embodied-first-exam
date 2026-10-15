"""T50 portable bicycle pump scene: a free Mini Morph pump with a passive piston, a connected wheel and one hand.

Static props (bench, wheel, Schrader valve, locked pump head and hose) are frozen at the approved T50 film pose
(``assets/t50_scene.json``, copied from the scene-v4 export with sha256 manifest). The pump itself is a free rigid
body standing on its foot; its piston rod and T handle slide on a passive joint (200 mm travel) whose stiffness,
damping and seal friction model the compressed-air spring of the chamber. The hand (Sharpa Wave by default, or the
genuine Wuji Hand 2.2) hangs from the same six-axis wrist stage for both hands.
"""

from __future__ import annotations

import importlib.util
import json
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
ASSETS = Path(__file__).resolve().with_name("assets")
# Source masses (scene_expansion bicycle_pump/mechanism.py): barrel 65 g, bottom housing 17 g, upper cap 5 g,
# folding foot 10 g, piston rod 10 g, T handle 18 g.
PUMP_MASS = {"barrel": 0.065, "bottom_housing": 0.017, "upper_cap": 0.005, "foot_pad": 0.010}
PISTON_MASS = {"piston_rod": 0.010, "t_handle": 0.018}


def node(parent, tag, **attributes):
    def value(x):
        return " ".join(f"{float(v):.12g}" for v in x) if isinstance(x, (tuple, list, np.ndarray)) else str(x)

    return ET.SubElement(parent, tag, {k: value(v) for k, v in attributes.items()})


def material(assets, name, item):
    metallic, roughness = float(item.get("metallic", 0)), float(item.get("roughness", 0.5))
    node(
        assets,
        "material",
        name=name,
        rgba=item["rgba"],
        specular=round(0.15 + 0.55 * metallic, 4),
        shininess=round(max(0.05, 1 - roughness), 4),
        reflectance=round(0.08 * metallic, 4),
    )
    return name


def contact_geom(parent, name, kind, size, **attributes):
    return node(
        parent,
        "geom",
        name=name,
        type=kind,
        size=size,
        friction=attributes.pop("friction", (1.0, 0.005, 0.0001)),
        condim=attributes.pop("condim", 4),
        solref=attributes.pop("solref", (0.005, 1)),
        solimp=attributes.pop("solimp", (0.95, 0.99, 0.0005)),
        **attributes,
    )


def add_hand_rig(root, config, hand_id, folder):
    """The six-axis wrist stage (same joints, ranges and gains for both hands) with the Sharpa Wave mounted."""
    world, actuator = root.find("worldbody"), root.find("actuator")
    hand = world.find("body")
    world.remove(hand)
    wrist = node(world, "body", name="wrist_stage", pos=config["stage_origin"])
    node(wrist, "inertial", pos=(0, 0, 0), mass=0.01, diaginertia=(0.00001,) * 3)
    # Zero wrist rotation = palm facing down (-z), fingers pointing +y, thumb toward -x.
    hand.set("quat", "0.5 -0.5 0.5 0.5")
    wrist.append(hand)
    ranges = config["wrist_range"]
    for i, name in enumerate(("x", "y", "z", "rx", "ry", "rz")):
        axis = [int(i % 3 == j) for j in range(3)]
        wrist.insert(
            i,
            ET.Element(
                "joint",
                name="wrist_" + name,
                type="slide" if i < 3 else "hinge",
                axis=" ".join(map(str, axis)),
                range=" ".join(str(v) for v in ranges[i]),
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


def add_static_props(root, assets, source):
    """Bench and the connected wheel/valve/head/hose at the approved film pose (static world geometry)."""
    world = root.find("worldbody")
    center = np.asarray(source["wheel_center_world"])
    rotation = np.asarray(source["wheel_rotation_world"])
    meshes = set()

    def solid(name):
        if name.startswith("hose_geom_"):
            return int(name.rsplit("_", 1)[1]) >= 2
        return name.startswith("spoke_") or name in (
            "hub", "axle", "valve_stem", "core_tip", "continuous_hollow_head", "continuous_collar", "hose_neck",
            "lock_lever", "lock_eccentric")

    for item in source["geoms"]:
        body = item["body"]
        if body in ("pump_barrel", "piston"):
            continue
        name = item["name"]
        mat = material(assets, "mat_" + name, item)
        attributes = dict(pos=item["pos"], quat=item["quat"], material=mat)
        if item["type"] == "mesh":
            mesh = Path(item["mesh"]).stem
            if mesh not in meshes:
                node(assets, "mesh", name=mesh, file=str((ASSETS / item["mesh"]).resolve()), inertia="shell")
                meshes.add(mesh)
            attributes["mesh"] = mesh
        else:
            attributes["size"] = item["size"]
        if body == "world" and name != "floor":
            # Bench top and legs: support geometry.
            contact_geom(world, name, item["type"], attributes.pop("size"), friction=(0.8, 0.005, 0.0001), **attributes)
        elif name == "floor":
            contact_geom(world, name, "plane", (3, 3, 0.05), pos=item["pos"], material=mat)
        elif solid(name):
            # Static solid props the hand can touch: hub, axle, spokes, valve, locked head and hose (static: the
            # head is locked on the valve; the hose segments next to the pump outlet are visual only so the free
            # pump never leans on a static hose).
            if "size" in attributes:
                contact_geom(world, name, item["type"], attributes.pop("size"), **attributes)
            else:
                contact_geom(world, name, item["type"], None, **attributes).attrib.pop("size")
        else:
            node(world, "geom", name=name, type=item["type"], contype=0, conaffinity=0, group=2, **attributes)
    # The rim's contact surface: 60 hidden capsules on the 202 mm mid-rim circle (the merged visual rim mesh is not
    # convex, so it never collides itself).
    for i in range(60):
        t0, t1 = 2 * np.pi * i / 60, 2 * np.pi * (i + 1) / 60
        a = center + rotation @ np.array([0.202 * np.cos(t0), 0.202 * np.sin(t0), 0])
        b = center + rotation @ np.array([0.202 * np.cos(t1), 0.202 * np.sin(t1), 0])
        contact_geom(world, f"rim_contact_{i}", "capsule", (0.009,), fromto=np.r_[a, b], group=3,
                     rgba=(0.4, 0.4, 0.4, 0), friction=(0.6, 0.005, 0.0001))
    # The tire's contact surface: the source model's 48 capsules on the 228.5 mm centre circle (hidden; the
    # smooth tire shell above is its visual).
    for i in range(48):
        t0, t1 = 2 * np.pi * i / 48, 2 * np.pi * (i + 1) / 48
        a = center + rotation @ np.array([0.2285 * np.cos(t0), 0.2285 * np.sin(t0), 0])
        b = center + rotation @ np.array([0.2285 * np.cos(t1), 0.2285 * np.sin(t1), 0])
        contact_geom(world, f"tire_contact_{i}", "capsule", (0.0285,), fromto=np.r_[a, b], group=3,
                     rgba=(0.1, 0.1, 0.1, 0), friction=(0.9, 0.005, 0.0001))


def add_pump(root, assets, source, config):
    """Free Mini Morph pump on its foot; piston + T handle on a passive slide (the chamber's air spring)."""
    world = root.find("worldbody")
    pump_cfg = config["pump"]
    origin = np.asarray(source["pump_origin_world"]) + np.array([0, 0, pump_cfg["base_lift_m"]])
    pump = node(world, "body", name="pump", pos=origin)
    node(pump, "freejoint", name="pump_free")
    items = {g["name"]: g for g in source["geoms"] if g["body"] in ("pump_barrel", "piston")}
    for name, mass in PUMP_MASS.items():
        item = items[name]
        # Hard plastic foot/housing on the wooden bench: an inelastic (over-damped) contact, so a rocked pump
        # settles within a few rocks instead of ringing on the soft-contact springs.
        contact_geom(pump, name, item["type"], item["size"], pos=item["pos"], quat=item["quat"], mass=mass,
                     material=material(assets, "mat_" + name, item), friction=(0.8, 0.005, 0.0001),
                     solref=pump_cfg["base_solref"])
    node(pump, "site", name="pump_top", pos=(0, 0, 0.249), size=(0.002,), group=5)
    travel = pump_cfg["travel_m"]
    piston = node(pump, "body", name="piston", pos=(0, 0, 0.25 + travel))
    node(
        piston,
        "joint",
        name="piston_extension",
        type="slide",
        axis=(0, 0, 1),
        range=(0, travel),
        ref=travel,
        limited="true",
        stiffness=pump_cfg["air_spring_n_m"],
        springref=pump_cfg["air_spring_ref_m"],
        damping=pump_cfg["damping_n_s_m"],
        frictionloss=pump_cfg["seal_friction_n"],
        armature=0.001,
        solreflimit=pump_cfg["limit_solref"],
    )
    rod = items["piston_rod"]
    # The exposed rod is solid for the hand (parent/child filtering keeps it from colliding with its own barrel).
    contact_geom(piston, "piston_rod", "cylinder", rod["size"], pos=(0, 0, -0.105), mass=PISTON_MASS["piston_rod"],
                 material=material(assets, "mat_piston_rod", rod))
    handle = items["t_handle"]
    contact_geom(piston, "t_handle", "capsule", handle["size"], pos=(0, 0, 0), quat=handle["quat"],
                 mass=PISTON_MASS["t_handle"], material=material(assets, "mat_t_handle", handle),
                 friction=(1.2, 0.005, 0.0001))
    node(piston, "site", name="t_handle_top", pos=(0, 0, handle["size"][0]), size=(0.002,), group=5)
    return pump


def build(config, asset_dir=None, hand="sharpa"):
    """Compose the frozen scene with the selected genuine hand on the same six-axis wrist stage."""
    hand_id = hands.canonical(hand)
    folder = Path(
        asset_dir
        or os.environ.get("DEXHAND_ASSET_DIR")
        or Path(__file__).resolve().parents[4] / "images/dexhand/assets/hand"
    )
    source = json.loads((ASSETS / "t50_scene.json").read_text())
    root = ET.parse(folder / "right_hand.xml").getroot()
    root.set("model", hands.info(hand_id)["model"] + " bicycle pump strokes")
    root.find("compiler").set("meshdir", str((folder / "assets/right").resolve()))
    option = root.find("option")
    option.set("timestep", str(config["physics_dt"]))
    option.set("gravity", "0 0 -9.81")
    option.set("iterations", "80")
    option.set("integrator", "implicitfast")
    option.set("cone", "elliptic")
    for key in root.findall("keyframe"):
        root.remove(key)
    assets = root.find("asset")
    add_hand_rig(root, config, hand_id, folder)
    node(assets, "texture", name="studio_sky", type="skybox", builtin="gradient", width=256, height=256,
         rgb1=(0.66, 0.69, 0.68), rgb2=(0.80, 0.80, 0.77))
    add_static_props(root, assets, source)
    add_pump(root, assets, source, config)
    world = root.find("worldbody")
    target = np.asarray(source["camera"]["target"])
    for light in source["lights"]:
        pos = target + np.asarray(light["offset"]) * 1.6
        direction = target - pos
        node(world, "light", name="light_" + light["name"].lower(), pos=pos, dir=direction / np.linalg.norm(direction),
             diffuse=np.asarray(light["color"]) * min(0.75, light["energy"] / 28), specular=(0.15, 0.15, 0.15),
             castshadow="true" if light["name"] == "Key" else "false")
    for name, camera in config["cameras"].items():
        pos, look = np.asarray(camera["pos"], float), np.asarray(camera["target"], float)
        forward = (look - pos) / np.linalg.norm(look - pos)
        right = np.cross(forward, [0, 0, 1])
        right /= np.linalg.norm(right)
        up = np.cross(right, forward)
        node(world, "camera", name=name, pos=pos, xyaxes=np.r_[right, up], fovy=camera["fovy"])
    v = root.find("visual")
    if v is None:
        v = node(root, "visual")
    node(v, "global", offwidth=1280, offheight=720)
    node(v, "quality", shadowsize=4096, offsamples=4)
    node(v, "headlight", ambient=(0.30, 0.30, 0.30), diffuse=(0.35, 0.35, 0.35), specular=(0.05, 0.05, 0.05))
    xml = ET.tostring(root, encoding="unicode")
    return mujoco.MjModel.from_xml_string(xml), xml
