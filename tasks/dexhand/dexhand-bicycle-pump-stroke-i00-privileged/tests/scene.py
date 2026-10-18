"""T50 portable bicycle pump scene: a free Mini Morph pump with a passive piston, a connected wheel and one hand.

Static props (bench, wheel, Schrader valve, locked pump head and hose) are frozen at the approved T50 film pose
(``assets/t50_scene.json``, copied from the scene-v4 export with sha256 manifest). The pump itself is a free rigid
body standing on its foot; its piston rod and T handle slide on a passive joint (200 mm travel) whose stiffness,
damping and seal friction model the compressed-air spring of the chamber. The hand (Sharpa Wave by default, or the
genuine Wuji Hand 2.2) is carried by the right arm of a Tianji Marvin robot standing at the bench (left arm parked).
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


def _arm_rig_module():
    """The shared Marvin arm rig (copied next to this file in generated task dirs)."""
    try:
        import arm_rig

        return arm_rig
    except ModuleNotFoundError:
        path = Path(__file__).resolve().parents[2] / "shared/arm_rig.py"
        spec = importlib.util.spec_from_file_location("arm_rig", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules["arm_rig"] = module
        spec.loader.exec_module(module)
        return module


arm_rig = _arm_rig_module()
ASSETS = Path(__file__).resolve().with_name("assets")
# Source masses (scene_expansion bicycle_pump/mechanism.py): barrel 65 g, bottom housing 17 g, upper cap 5 g,
# folding foot 10 g, piston rod 10 g, T handle 18 g.
PUMP_MASS = {"barrel": 0.065, "bottom_housing": 0.017, "upper_cap": 0.005, "foot_pad": 0.010}
PISTON_MASS = {"piston_rod": 0.010, "t_handle": 0.018}
# Pump head (TRK-RP04) and its thumb lock, from the T50 source model and trajectory: at the film's frame 50 the head
# is locked on the Schrader stem; disconnected (frame 0) it sits HEAD_TRAVEL further out along the stem axis (17.5 mm:
# 8 mm gap + 9.5 mm core engagement); the thumb lock turns LEVER_CLOSED rad about +y (world) from up (open, frame 0)
# to lying toward the hub (closed, frame 50).
STEM_AXIS = np.array([0.98055149865641, 0.0, 0.1962619639223775])   # Schrader stem axis (out of the rim, toward the hub)
HEAD_TRAVEL = 0.0175
LEVER_CLOSED = 1.65
LEVER_PIVOT_LOCKED = np.array([0.52940, -0.129, 0.74372])           # thumb-lock hinge at the film's locked pose
HEAD_GEOMS = ("continuous_hollow_head", "continuous_collar", "hose_neck", "core_pusher")
LEVER_GEOMS = ("lock_lever", "lock_eccentric")
HEAD_HOSE = ("hose_geom_8", "hose_geom_9", "hose_geom_10", "hose_geom_11")   # hose end that follows the head
HEAD_MASS, LEVER_MASS = 0.022, 0.003
BACK_LEGS, BACK_LEG_SHIFT = "bench_leg_0.37_", 0.08


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
    """The Tianji Marvin stand with two 7-DoF arms; the right arm carries the working hand under the fixed body
    ``wrist_stage`` (the checker's hand root), the left arm is parked with its hand (``arm_rig.PARK``)."""
    world, actuator = root.find("worldbody"), root.find("actuator")
    hand = world.find("body")
    # The family's Sharpa tweaks, applied before mounting so the mirrored left Wave gets them too.
    for a in actuator:
        if a.tag == "general":
            bias = [float(v) for v in a.get("biasprm", "0 0 0").split()]
            bias[2] = -0.9
            a.set("biasprm", " ".join(map(str, bias)))
    for g in hand.iter("geom"):
        if "fingertip_collision" in g.get("name", ""):
            g.set("friction", "1.5 .005 .0001")
    sibling = folder.parent / "wuji_v2_2"
    marvin = config["marvin"]
    return arm_rig.mount_marvin(root, marvin["base_pos"], marvin["base_yaw"], hand=hand_id, active=("right",),
                                mount_names={"right": "wrist_stage"}, sharpa_folder=folder,
                                wuji_folder=sibling if (sibling / "mjcf/right.xml").is_file() else None)


def robot_body_ids(model):
    """Every robot body (both hands, both arms, the stand): a contact of any of them with the pump is robot contact."""
    return (set(arm_rig.hand_body_ids(model, "left")) | set(arm_rig.hand_body_ids(model, "right"))
            | set(arm_rig.robot_body_ids(model)))


def add_static_props(root, assets, source):
    """Bench and the connected wheel/valve/head/hose at the approved film pose (static world geometry)."""
    world = root.find("worldbody")
    center = np.asarray(source["wheel_center_world"])
    rotation = np.asarray(source["wheel_rotation_world"])
    meshes = set()

    def solid(name):
        if name.startswith("hose_geom_"):
            return int(name.rsplit("_", 1)[1]) >= 2
        return name.startswith("spoke_") or name in ("hub", "axle", "valve_stem", "core_tip")

    head_items = []
    for item in source["geoms"]:
        body = item["body"]
        if body in ("pump_barrel", "piston"):
            continue
        name = item["name"]
        if name in HEAD_GEOMS + LEVER_GEOMS + HEAD_HOSE:
            head_items.append(item)
            continue
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
        if name.startswith(BACK_LEGS):
            # The two back bench legs stand 8 cm further under the bench top than in the source, clear of the robot
            # stand's floor platform (which reaches x = 0.393 m); the bench top itself is unchanged.
            attributes["pos"] = [item["pos"][0] + BACK_LEG_SHIFT, *item["pos"][1:]]
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
    return head_items


def _quat_mul(a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return np.array([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])


def add_head(root, assets, head_items):
    """The pump head on a passive slide along the Schrader stem axis (the hose guides it; no lateral play) with the
    thumb lock on a passive hinge. Reset = the source's disconnected state: head 17.5 mm out, lever up (open)."""
    world = root.find("worldbody")
    offset = STEM_AXIS * HEAD_TRAVEL
    head = node(world, "body", name="pump_head", pos=(0, 0, 0))
    node(head, "joint", name="head_slide", type="slide", axis=STEM_AXIS, pos=LEVER_PIVOT_LOCKED + offset,
         range=(-HEAD_TRAVEL, 0.0), limited="true", frictionloss=2.0, damping=5.0, armature=0.01,
         solreflimit=(0.004, 1), solreffriction=(0.004, 1), solimpfriction=(0.99, 0.999, 0.001))
    node(head, "inertial", pos=LEVER_PIVOT_LOCKED + offset - 0.008 * STEM_AXIS, mass=HEAD_MASS,
         diaginertia=(3e-6, 3e-6, 3e-6))
    pivot = LEVER_PIVOT_LOCKED + offset
    lever = node(head, "body", name="thumb_lock", pos=pivot)
    node(lever, "joint", name="lever_angle", type="hinge", axis=(0, 1, 0), pos=(0, 0, 0), range=(0.0, LEVER_CLOSED),
         limited="true", frictionloss=0.004, damping=0.002, armature=0.0001, solreflimit=(0.004, 1),
         solreffriction=(0.004, 1), solimpfriction=(0.99, 0.999, 0.001))
    node(lever, "inertial", pos=(0, 0, 0.008), mass=LEVER_MASS, diaginertia=(2e-7, 2e-7, 5e-8))
    c, s_ = np.cos(-LEVER_CLOSED / 2), np.sin(-LEVER_CLOSED / 2)
    q_open = np.array([c, 0.0, s_, 0.0])           # rotation by -LEVER_CLOSED about +y (closed -> open)
    rot_open = np.array([[np.cos(-LEVER_CLOSED), 0, np.sin(-LEVER_CLOSED)], [0, 1, 0],
                         [-np.sin(-LEVER_CLOSED), 0, np.cos(-LEVER_CLOSED)]])
    for item in head_items:
        name = item["name"]
        mat = material(assets, "mat_" + name, item)
        pos, quat = np.asarray(item["pos"], float), np.asarray(item["quat"], float)
        attributes = dict(material=mat)
        if item["type"] == "mesh":
            mesh = Path(item["mesh"]).stem
            node(assets, "mesh", name=mesh, file=str((ASSETS / item["mesh"]).resolve()), inertia="shell")
            attributes["mesh"] = mesh
        else:
            attributes["size"] = item["size"]
        if name in LEVER_GEOMS:
            parent = lever
            pos = rot_open @ (pos - LEVER_PIVOT_LOCKED)
            quat = _quat_mul(q_open, quat)
        else:
            parent = head
            pos = pos + offset
        if name in HEAD_HOSE or name == "core_pusher":
            node(parent, "geom", name=name, type=item["type"], pos=pos, quat=quat, contype=0, conaffinity=0, group=2,
                 mass=0, **attributes)
        elif "size" in attributes:
            contact_geom(parent, name, item["type"], attributes.pop("size"), pos=pos, quat=quat, mass=0,
                         friction=(1.0, 0.005, 0.0001), **attributes)
        else:
            contact_geom(parent, name, item["type"], None, pos=pos, quat=quat, mass=0, friction=(1.0, 0.005, 0.0001),
                         **attributes).attrib.pop("size")
    contact = root.find("contact")
    if contact is None:
        contact = ET.SubElement(root, "contact")
    # The head is guided along the stem axis by its slide; it never collides with the static wheel, valve or hose.
    for body in ("pump_head", "thumb_lock"):
        ET.SubElement(contact, "exclude", body1="world", body2=body)
    return head


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
    """Compose the frozen scene with the selected genuine hand on the Marvin right arm."""
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
    head_items = add_static_props(root, assets, source)
    add_head(root, assets, head_items)
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
