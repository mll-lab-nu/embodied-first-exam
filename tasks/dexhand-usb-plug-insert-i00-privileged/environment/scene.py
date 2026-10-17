"""T24 USB connection scene: the original four-port hub and USB-A cable, composed with a dexterous hand.

Geometry follows the accepted scene-expansion source (`usb_cable_meta_delivery_trajectory_r1/mechanism.py`, copied
dimensions and materials in ``assets/usb_scene.json``). Physical modelling changes for a 2 ms dexterous-hand task are
documented in README.md: each port is an open rectangular cavity with generous clearance (0.5 mm per side across,
0.55 mm per side in height, against 0.1 mm in the real connector); the plug shell collides as one solid box, while the
receptacle tongue, the plug's polarized insert and all gold contacts are visual only (polarity is part of the success
predicate instead); retention leaf springs are omitted; the hub's own upstream cable is a visual, rigidly attached
to the hub and lying on the counter; the plug's 0.5 m cable is a passive 20-link ball-joint rod. The hand is carried by
the right arm of the Tianji Marvin robot (``arm_rig``; left arm parked) standing on the floor in front of the desk;
the floor sits 0.10 m lower than in the source (desk top unchanged) and the desk's two visual front legs stand back
under the top (``counter_legs_xy``) so that no robot geom overlaps them.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation


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
ASSETS = Path(__file__).with_name("assets")


def _load_assets():
    """The source-derived USB geometry/material table, checked against the sha256 manifest."""
    manifest = json.loads((ASSETS / "manifest.json").read_text())
    for name, entry in manifest["files"].items():
        raw = (ASSETS / name).read_bytes()
        if len(raw) != entry["bytes"] or hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            raise RuntimeError(f"USB scene asset integrity failure: {name}")
    return json.loads((ASSETS / "usb_scene.json").read_text())


USB = _load_assets()


def vec(v):
    return " ".join(f"{float(x):.17g}" for x in v)


def node(parent, tag, **attributes):
    return ET.SubElement(
        parent, tag, {k: vec(v) if isinstance(v, (list, tuple, np.ndarray)) else str(v) for k, v in attributes.items()}
    )


def quat_wxyz(rotation):
    return Rotation.from_matrix(rotation).as_quat()[[3, 0, 1, 2]]


def part(parent, name, kind, material, *, collide=True, friction=(0.5, 0.005, 0.0001), solref=(0.004, 1),
         solimp=(0.95, 0.99, 0.0002), **attrs):
    """A task geom: collidable (group 0) with the task's contact law, or visual only (group 2)."""
    if collide:
        attrs.update(friction=friction, condim=4, solref=solref, solimp=solimp, contype=1, conaffinity=1)
    else:
        attrs.update(contype=0, conaffinity=0, group=2)
    attrs.setdefault("mass", 0)
    return node(parent, "geom", name=name, type=kind, material=material, **attrs)


def box(parent, name, pos, size, material, **attrs):
    return part(parent, name, "box", material, pos=pos, size=size, **attrs)


FIT = {"solimp": tuple(USB["fit_solimp"])}  # connector fit surfaces: stiffer impedance, small penetration


def thin_shell(parent, prefix, front_y, length, width, height, material, wall=0.0003):
    """Visual open metal shell (four walls), as in the source scene."""
    cy = front_y + length / 2
    for sign in (-1, 1):
        box(parent, f"{prefix}_side_{sign}", (sign * (width / 2 - wall / 2), cy, 0), (wall / 2, length / 2, height / 2),
            material, collide=False)
        box(parent, f"{prefix}_plate_{sign}", (0, cy, sign * (height / 2 - wall / 2)),
            (width / 2 - wall, length / 2, wall / 2), material, collide=False)


def add_hub(world, cfg):
    h = USB["hub"]
    hub = node(world, "body", name="hub", pos=cfg["hub_pos"], quat=quat_wxyz(Rotation.from_euler("z", cfg["hub_yaw"]).as_matrix()))
    node(hub, "freejoint", name="hub_free")
    node(hub, "inertial", pos=(0, 0.002, 0), mass=h["mass"], diaginertia=h["diaginertia"])
    hx, hz = h["half_width"], h["half_height"]
    box(hub, "hub_rear_case", (0, 0.007, 0), (hx, 0.008, hz), "usb_black")
    for sign in (-1, 1):
        box(hub, f"hub_face_rail_{sign}", (0, -0.008, sign * (hz - h["rail_half"])), (hx, 0.007, h["rail_half"]),
            "usb_black", **FIT)
    ports = h["ports_x"]
    half = h["aperture_half_width"]
    edges = [-hx] + [v for x in ports for v in (x - half, x + half)] + [hx]
    for i in range(0, len(edges), 2):
        lo, hi = edges[i: i + 2]
        box(hub, f"hub_front_partition_{i}", ((lo + hi) / 2, -0.008, 0), ((hi - lo) / 2, 0.007, hz), "usb_black",
            **FIT)
    mouth = h["mouth_y"]
    depth = USB["port_depth"]
    for index, x in enumerate(ports):
        port = node(hub, "body", name=f"socket_{index}", pos=(x, mouth, 0))
        # Collision back stop of the cavity (12 mm deep, the plug shell length) up to the rear case.
        box(port, f"socket{index}_back", (0, depth + 0.001, 0), (half, 0.001, hz - 2 * h["rail_half"]), "usb_black",
            **FIT)
        # Visual receptacle details (source dimensions).
        thin_shell(port, f"socket{index}", 0, 0.012, 0.0128, 0.0053, "usb_metal")
        box(port, f"socket{index}_polarized_tongue", (0, 0.0071, 0.00080), (0.0053, 0.0049, 0.00065), "usb_blue",
            collide=False)
        for k, px in enumerate((-0.0035, -0.001, 0.001, 0.0035)):
            box(port, f"socket{index}_contact_{k}", (px, 0.0072, 0.00010), (0.0004, 0.0037, 0.00005), "usb_gold",
                collide=False)
        node(port, "site", name=f"port{index}_mouth", pos=(0, 0, 0), size=(0.0005,), rgba=(1, 0, 0, 0), group=5)
    box(hub, "hub_led", (-0.043, -0.0151, 0), (0.0006, 0.0001, 0.0011), "usb_blue", collide=False)
    # Rubber pads under the case (the hub rests on them).
    pad = h["pad_half_height"]
    for sx in (-1, 1):
        for sy in (-1, 1):
            box(hub, f"hub_pad_{sx}_{sy}", (sx * 0.040, sy * 0.009, -hz - pad), (0.006, 0.004, pad), "usb_pvc",
                friction=(h["pad_friction"], 0.005, 0.0001))
    # The hub's own upstream cable: visual only, rigid with the case, lying on the counter (README: scope).
    cable_z = -hz - 2 * pad + USB["cable_diameter"] / 2
    points = np.asarray(USB["upstream_centerline_xy"], dtype=float)
    pts = np.column_stack([points, np.full(len(points), cable_z)])
    pts[0, 2] = 0.0
    pts[1, 2] = cable_z * 0.6
    for i in range(len(pts) - 1):
        part(hub, f"upstream_jacket_{i}", "capsule", "usb_pvc", collide=False, size=(USB["cable_diameter"] / 2,),
             fromto=np.r_[pts[i], pts[i + 1]])
    end, prev = pts[-1], pts[-2]
    direction = (end - prev) / np.linalg.norm(end - prev)
    yaw = np.arctan2(direction[1], direction[0])
    rot = Rotation.from_euler("z", yaw).as_matrix() @ Rotation.from_euler("y", np.pi / 2).as_matrix()
    far = node(hub, "body", name="upstream_far_end", pos=end + direction * 0.0, quat=quat_wxyz(rot))
    part(far, "upstream_far_housing", "box", "usb_black", collide=False, pos=(0, 0, 0.009), size=(0.007, 0.0045, 0.009))
    part(far, "upstream_far_metal", "box", "usb_metal", collide=False, pos=(0, 0, 0.023), size=(0.0058, 0.00225, 0.005))
    return hub


def add_plug(world, cfg):
    p = USB["plug"]
    roll = Rotation.from_euler("y", cfg["plug_roll"]).as_matrix()
    rot = Rotation.from_euler("z", cfg["plug_yaw"]).as_matrix() @ roll
    plug = node(world, "body", name="plug", pos=cfg["plug_pos"], quat=quat_wxyz(rot))
    node(plug, "freejoint", name="plug_free")
    node(plug, "inertial", pos=(0, -0.019, 0), mass=p["mass"], diaginertia=p["diaginertia"])
    sw, sh, sl = p["shell_width"], p["shell_height"], p["shell_length"]
    # Collision: the shell as one solid box; visual: the source's open shell, insert and contacts.
    box(plug, "plug_shell_collision", (0, -sl / 2, 0), (sw / 2, sl / 2, sh / 2), "usb_metal",
        friction=(0.3, 0.003, 0.0001), rgba=(0.65, 0.68, 0.71, 0), group=3, **FIT)
    thin_shell(plug, "plug", -sl, sl, sw, sh, "usb_metal")
    box(plug, "plug_polarized_insert", (0, -0.006, -0.00125), (0.0054, 0.006, 0.00070), "usb_white", collide=False)
    for k, x in enumerate((-0.0035, -0.001, 0.001, 0.0035)):
        box(plug, f"plug_contact_{k}", (x, -0.0048, -0.0005), (0.0004, 0.0046, 0.00005), "usb_gold", collide=False)
    # Moulded housing and strain relief: the grip surfaces (torsional coefficient of a ~1 cm soft pad patch).
    box(plug, "plug_housing", (0, -0.022, 0), (0.0075, 0.010, p["housing_half_height"]), "usb_black",
        friction=p["grip_friction"])
    part(plug, "plug_strain_relief", "capsule", "usb_pvc", fromto=(0, -0.032, 0, 0, -0.041, 0), size=(0.0028,),
         friction=p["grip_friction"])
    node(plug, "site", name="plug_tip", pos=(0, 0, 0), size=(0.0005,), rgba=(0, 1, 0, 0), group=5)
    add_cable(plug, roll)
    return plug


def add_cable(plug, roll):
    """Passive inextensible rod: ball joints with bending stiffness EI / segment length (EI = 2e-5 N m^2).

    The centreline is authored in the plug's yaw frame on the counter (the plug lies on its side, rotated by ``roll``
    about its axis) and expressed in the plug frame.
    """
    c = USB["cable"]
    support = abs(roll[2] @ np.array([USB["plug"]["shell_width"] / 2 + 0.0015, 0, USB["plug"]["housing_half_height"]]))
    rest_z = -support + USB["cable_diameter"] / 2
    xy = np.asarray(c["centerline_xy"], dtype=float)
    total = c["length"]
    seg = c["segments"]
    arclen = np.r_[0, np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))]
    u = np.linspace(0, total, seg + 1)
    pts = np.column_stack([np.interp(u, arclen, xy[:, 0]), np.interp(u, arclen, xy[:, 1]), np.full(seg + 1, rest_z)])
    pts[0, 2] = 0.0
    # Re-normalise each link to the exact segment length (the first link descends to the counter).
    length = total / seg
    far_half = (0.007, 0.0055)  # USB-B housing half width (horizontal) and half height (vertical)
    pts[-1, 2] = rest_z + far_half[1] - USB["cable_diameter"] / 2  # the rod enters the far housing at its centre
    for i in range(1, seg + 1):
        d = pts[i] - pts[i - 1]
        pts[i] = pts[i - 1] + d / np.linalg.norm(d) * length
    pts = pts @ roll  # yaw-frame points -> plug frame (row vectors: roll.T @ p)
    up = roll.T @ np.array([0.0, 0.0, 1.0])  # world vertical in the plug frame
    parent, previous = plug, np.eye(3)
    segmass = c["mass"] / seg
    radius = USB["cable_diameter"] / 2
    for i in range(seg):
        delta = pts[i + 1] - pts[i]
        rot, _ = Rotation.align_vectors([delta / np.linalg.norm(delta)], [[0, 0, 1]])
        rot = rot.as_matrix()
        offset = pts[0] if i == 0 else (0, 0, length)
        b = node(parent, "body", name=f"cable_{i}", pos=offset, quat=quat_wxyz(previous.T @ rot))
        node(b, "joint", name=f"cable_bend_{i}", type="ball", stiffness=c["EI"] / length, damping=c["damping"],
             armature=c["armature"])
        node(b, "inertial", pos=(0, 0, length / 2), mass=segmass,
             diaginertia=(segmass * length**2 / 12, segmass * length**2 / 12, segmass * radius**2 / 2))
        part(b, f"cable_jacket_{i}", "capsule", "usb_pvc", fromto=(0, 0, 0, 0, 0, length), size=(radius,),
             friction=(0.5, 0.005, 0.0001), solref=(0.006, 1))
        parent, previous = b, rot
    # USB-B far plug lying flat on the counter: local z continues the rod, local y is vertical.
    axis = previous[:, 2]
    side = np.cross(up, axis)
    side /= np.linalg.norm(side)
    frame = np.column_stack([side, np.cross(axis, side), axis])
    end = node(parent, "body", name="cable_far_end", pos=(0, 0, length), quat=quat_wxyz(previous.T @ frame))
    node(end, "inertial", pos=(0, 0, 0.011), mass=0.008, diaginertia=(4e-7, 4e-7, 2e-7))
    part(end, "cable_far_housing", "box", "usb_black", pos=(0, 0, 0.009), size=(far_half[0], far_half[1], 0.009),
         friction=(0.8, 0.005, 0.0001))
    part(end, "cable_far_metal", "box", "usb_metal", pos=(0, 0, 0.023), size=(0.0058, 0.005, 0.005),
         friction=(0.4, 0.005, 0.0001))


def add_room(root, world, assets, cfg):
    for name, color, metallic, roughness in USB["materials"]:
        node(assets, "material", name=name, rgba=color, metallic=metallic, roughness=roughness)
    node(assets, "texture", name="studio_sky", type="skybox", builtin="gradient", width=512, height=512,
         rgb1=(0.62, 0.67, 0.68), rgb2=(0.80, 0.79, 0.75))
    node(assets, "texture", name="counter_grain", type="2d", builtin="flat", width=64, height=64,
         rgb1=(0.77, 0.75, 0.70), rgb2=(0.74, 0.72, 0.67), mark="random", random=0.05, markrgb=(0.72, 0.70, 0.65))
    node(assets, "material", name="counter_top", texture="counter_grain", texrepeat=(8, 8), reflectance=0.02,
         rgba=(1, 1, 1, 1))
    node(assets, "material", name="leg_material", rgba=(0.25, 0.23, 0.21, 1), roughness=0.6)
    node(assets, "material", name="floor_material", rgba=(0.69, 0.70, 0.68, 1), roughness=0.8)
    top = cfg["counter_top_z"]
    cx, cy = cfg["counter_center_xy"]
    hx, hy = cfg["counter_half_xy"]
    part(world, "floor", "plane", "floor_material", size=(3, 3, 0.05), pos=(0, 0, cfg["floor_z"]),
         friction=(0.8, 0.005, 0.0001))
    part(world, "counter", "box", "counter_top", size=(hx, hy, 0.025), pos=(cx, cy, top - 0.025),
         friction=(0.4, 0.005, 0.0001))
    # Legs (visual only): the source corners, or ``counter_legs_xy`` when the robot's stand plate needs the room.
    legs = cfg.get("counter_legs_xy") or [(x, y) for x in (cx - hx + 0.04, cx + hx - 0.04)
                                          for y in (cy - hy + 0.06, cy + hy - 0.06)]
    for x, y in legs:
        leg_half = (top - 0.05 - cfg["floor_z"]) / 2
        part(world, f"leg_{x:.2f}_{y:.2f}", "box", "leg_material", collide=False, size=(0.022, 0.022, leg_half),
             pos=(x, y, cfg["floor_z"] + leg_half))
    node(world, "light", name="key", pos=(0.7, -0.7, 1.9), dir=(0, 0.35, -1), diffuse=(0.8, 0.8, 0.8), castshadow="true")
    node(world, "light", name="fill", pos=(0.2, 0.9, 1.7), dir=(0.2, -0.3, -1), diffuse=(0.5, 0.5, 0.5),
         castshadow="false")
    for camera in cfg["cameras"]:
        node(world, "camera", name=camera["name"], pos=camera["pos"], xyaxes=camera["xyaxes"], fovy=camera["fovy"])


def robot_parts(model):
    """(hand bodies of the working right hand, every other robot body: stand, torso, both arms, parked left hand)."""
    right = set(arm_rig.hand_body_ids(model, "right"))
    other = set(arm_rig.robot_body_ids(model)) | set(arm_rig.hand_body_ids(model, "left"))
    return right, other


def build(config, asset_dir=None, hand="sharpa"):
    """Compose the frozen scene with the selected genuine hand on the Marvin right arm (left arm parked)."""
    hand_id = hands.canonical(hand)
    folder = Path(
        asset_dir
        or os.environ.get("DEXHAND_ASSET_DIR")
        or Path(__file__).resolve().parents[4] / "images/dexhand/assets/hand"
    )
    root = ET.parse(folder / "right_hand.xml").getroot()
    root.set("model", hands.info(hand_id)["model"] + " USB plug insertion")
    root.find("compiler").set("meshdir", str((folder / "assets/right").resolve()))
    option = root.find("option")
    option.set("timestep", str(config["physics_dt"]))
    option.set("gravity", "0 0 -9.81")
    option.set("iterations", "80")
    option.set("integrator", "implicitfast")
    option.set("cone", "elliptic")
    option.set("impratio", "10")
    node(option, "flag", multiccd="enable")
    for key in root.findall("keyframe"):
        root.remove(key)
    assets, world, actuator = root.find("asset"), root.find("worldbody"), root.find("actuator")
    hand_body = world.find("body")
    # The family's Sharpa tweaks, applied before mounting so the mirrored (parked) left Wave gets them too.
    for a in actuator:
        if a.tag == "general":
            bias = [float(v) for v in a.get("biasprm", "0 0 0").split()]
            bias[2] = -0.9
            a.set("biasprm", " ".join(map(str, bias)))
    for g in hand_body.iter("geom"):
        if "fingertip_collision" in g.get("name", ""):
            g.set("friction", "1.5 .005 .0001")
    # Tianji Marvin stand with two 7-DoF arms: the right arm carries the working hand under the fixed body
    # ``wrist_stage`` (the checker's hand root), the left arm is parked with its hand (arm_rig.PARK). With
    # hand="wuji" both Waves are swapped for the genuine Wuji Hand 2.2 (vendor joints, gains and contacts).
    sibling = folder.parent / "wuji_v2_2"
    marvin = config["marvin"]
    arm_rig.mount_marvin(root, marvin["base_pos"], marvin["base_yaw"], hand=hand_id, active=("right",),
                         mount_names={"right": "wrist_stage"}, sharpa_folder=folder,
                         wuji_folder=sibling if (sibling / "mjcf/right.xml").is_file() else None)
    add_room(root, world, assets, config)
    add_hub(world, config)
    add_plug(world, config)
    v = node(root, "visual")
    node(v, "global", offwidth=1280, offheight=720)
    node(v, "quality", shadowsize=4096, offsamples=4)
    node(v, "headlight", ambient=(0.3, 0.3, 0.3), diffuse=(0.45, 0.45, 0.45), specular=(0.1, 0.1, 0.1))
    node(v, "map", znear=0.005)
    xml = ET.tostring(root, encoding="unicode")
    return mujoco.MjModel.from_xml_string(xml), xml
