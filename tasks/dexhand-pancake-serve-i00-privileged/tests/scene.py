"""T16 pancake serving scene: real-product pan, flexible turner, ceramic plate and a coherent pancake.

Geometry, masses and passive turner strips follow the T16 scene source
(``scene_expansion/repairs/pan_sharpa/geometry.py``); its exported meshes and the browning texture are copied
verbatim into ``assets/`` (sha256 in ``assets/manifest.json``). One genuine hand (Sharpa Wave by default, or
Wuji Hand 2.2) hangs from a six-axis wrist stage. Every object is a free body moved only by contact.
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

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"


def _hands_module():
    """The shared DexHand hand-selection module (copied next to this file in generated task dirs)."""
    try:
        import hands

        return hands
    except ModuleNotFoundError:
        path = HERE.parents[1] / "shared/hands.py"  # repository layout only (task dirs ship hands.py)
        spec = importlib.util.spec_from_file_location("hands", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules["hands"] = module
        spec.loader.exec_module(module)
        return module


hands = _hands_module()

# Source scene constants (T16 geometry.py), metres / kilograms.
COUNTER_Z = 0.850
PAN_START = (0.50, 0.10, COUNTER_Z + 0.0003)
PLATE_START = (0.76, 0.18, COUNTER_Z + 0.0003)
PAN_PROFILE = [(0.0001, 0), (0.096, 0), (0.111, 0.025), (0.108, 0.026), (0.093, 0.006), (0.0001, 0.006)]
PLATE_PROFILE = [(0.0001, 0), (0.085, 0), (0.104, 0.004), (0.128, 0.019), (0.126, 0.023), (0.100, 0.008),
                 (0.0001, 0.006)]
PLATE_RADIUS = 0.128
PANCAKE_RADIUS = 0.070
PANCAKE_THICKNESS = 0.0095
TURNER_BANDS = np.linspace(0.140, 0.2575, 4)
TURNER_WIDTHS = [0.037, 0.049, 0.0508, 0.046]
STEEL_E = 190e9
STEEL_CORE_THICKNESS = 0.00025

# Contact materials (declared estimates, see README). MuJoCo takes a pair's friction from the geom with the higher
# ``priority`` (the larger coefficient when priorities tie), so each food pairing is set explicitly:
# pancake-pan 0.45 (pancake, priority 1), pancake-turner blade 0.20 and blade-pan 0.20 (blade, priority 2),
# pancake-plate 0.60 (plate, priority 2); everything else uses the larger coefficient.
FRICTION = {
    "pancake": (0.45, 1),  # cooked batter on a lightly oiled pan
    "pan": (0.25, 0),      # non-stick coating (pancake pairs use the pancake's value)
    "blade": (0.20, 2),    # thin greased silicone/steel turner edge
    "plate": (0.60, 2),    # glazed ceramic against a cooked pancake
    "handle": (1.20, 0),   # soft non-slip turner grip
    "counter": (0.70, 0),  # oak counter
}


def node(parent, tag, **attributes):
    def value(x):
        if isinstance(x, (tuple, list, np.ndarray)):
            return " ".join(f"{float(v):.17g}" for v in x)
        return str(x)

    return ET.SubElement(parent, tag, {k: value(v) for k, v in attributes.items()})


def contact(body, name, material, **attributes):
    mu, priority = FRICTION[material]
    return node(body, "geom", name=name, group=3, rgba=(0, 0, 0, 0), mass=0, friction=(mu, 0.002, 0.0001),
                priority=priority, solref=(0.004, 1), solimp=(0.95, 0.99, 0.0003), condim=4, **attributes)


def visual(body, name, material, mesh=None):
    node(body, "geom", name=name + "_visual", type="mesh", mesh=mesh or name, material=material, group=2,
         contype=0, conaffinity=0, mass=0)


def mesh(assets, name, suffix=".stl"):
    node(assets, "mesh", name=name, file=str((ASSETS / (name + suffix)).resolve()))


def verify_assets():
    """Check every copied source file against assets/manifest.json (sha256 + size)."""
    manifest = json.loads((ASSETS / "manifest.json").read_text())
    for name, expected in manifest["files"].items():
        raw = (ASSETS / name).read_bytes()
        if len(raw) != expected["bytes"] or hashlib.sha256(raw).hexdigest() != expected["sha256"]:
            raise RuntimeError(f"pancake_serve asset integrity failure: {name}")
    return manifest


def add_materials(assets):
    node(assets, "texture", name="pancake_browning", type="2d", file=str((ASSETS / "pancake-browning.png").resolve()))
    node(assets, "texture", name="oak_grain", type="2d", builtin="flat", width=512, height=512,
         rgb1=(0.80, 0.66, 0.52), rgb2=(0.76, 0.62, 0.48), mark="random", random=0.04, markrgb=(0.70, 0.56, 0.42))
    node(assets, "texture", name="studio_sky", type="skybox", builtin="gradient", width=256, height=256,
         rgb1=(0.80, 0.81, 0.80), rgb2=(0.55, 0.56, 0.57))
    for name, rgba, specular in [
        ("pan_coating", (0.07, 0.075, 0.08, 1), 0.18), ("tool_grip", (0.055, 0.055, 0.052, 1), 0.12),
        ("silicone_blade", (0.09, 0.095, 0.085, 1), 0.12), ("steel", (0.72, 0.75, 0.77, 1), 0.75),
        ("ceramic", (0.93, 0.92, 0.88, 1), 0.45), ("cabinet", (0.36, 0.37, 0.38, 1), 0.1),
    ]:
        node(assets, "material", name=name, rgba=rgba, specular=specular, shininess=0.35)
    node(assets, "material", name="pancake_skin", texture="pancake_browning", rgba=(1, 1, 1, 1), specular=0.08,
         shininess=0.35)
    node(assets, "material", name="oak", texture="oak_grain", texrepeat=(4, 4), rgba=(1, 1, 1, 1), specular=0.1,
         shininess=0.2)


def make_pan(assets, world):
    body = node(world, "body", name="pan", pos=PAN_START, quat=(2 ** -0.5, 0, 0, 2 ** -0.5))
    node(body, "freejoint", name="pan_free")
    node(body, "inertial", mass=0.90, pos=(0, 0.025, 0.014), diaginertia=(0.008, 0.0035, 0.011))
    mesh(assets, "pan_shell")
    mesh(assets, "pan_handle")
    visual(body, "pan_shell", "pan_coating")
    visual(body, "pan_handle", "tool_grip")
    contact(body, "pan_floor", "pan", type="cylinder", size=(0.096, 0.003), pos=(0, 0, 0.003))
    for i in range(64):
        mesh(assets, f"pan_wall_{i}")
        contact(body, f"pan_wall_{i}", "pan", type="mesh", mesh=f"pan_wall_{i}")
    for i in range(5):
        mesh(assets, f"pan_handle_{i}")
        contact(body, f"pan_handle_{i}", "counter", type="mesh", mesh=f"pan_handle_{i}")


def make_turner(assets, world, pos=(0.43, -0.30, COUNTER_Z + 0.096), quat=(2 ** -0.5, 0, 0, -(2 ** -0.5))):
    """OXO SKU1071534 flexible turner: rigid handle/neck root plus three passive steel-core bending strips."""
    body = node(world, "body", name="turner", pos=pos, quat=quat)
    node(body, "freejoint", name="turner_free")
    node(body, "inertial", mass=0.110, pos=(0, 0.029, -0.0121), diaginertia=(0.00037, 0.000055, 0.00036))
    mesh(assets, "turner_handle")
    mesh(assets, "turner_neck")
    visual(body, "turner_handle", "tool_grip")
    visual(body, "turner_neck", "steel")
    for i in range(3):
        mesh(assets, f"turner_handle_{i}")
        contact(body, f"turner_handle_{i}", "handle", type="mesh", mesh=f"turner_handle_{i}")
    for i in range(2):
        mesh(assets, f"turner_neck_{i}")
        contact(body, f"turner_neck_{i}", "blade", type="mesh", mesh=f"turner_neck_{i}")
    parent = body
    bands, widths = TURNER_BANDS, TURNER_WIDTHS
    for i, (a, b) in enumerate(zip(bands[:-1], bands[1:])):
        strip = node(parent, "body", name=f"turner_blade_{i}",
                     pos=(0, a if i == 0 else a - bands[i - 1], -0.07055 if i == 0 else 0))
        length = b - a
        w = widths[i:i + 2]
        mass = 0.040 * length / (bands[-1] - bands[0])
        inertia = (mass * (length ** 2 + 0.0015 ** 2) / 12, mass * ((2 * max(w)) ** 2 + 0.0015 ** 2) / 12,
                   mass * (length ** 2 + (2 * max(w)) ** 2) / 12)
        node(strip, "inertial", mass=mass, pos=(0, length / 2, 0.00075), diaginertia=inertia)
        ei = STEEL_E * (2 * np.mean(w)) * STEEL_CORE_THICKNESS ** 3 / 12
        node(strip, "joint", name=f"turner_bend_{i}", type="hinge", axis=(1, 0, 0), stiffness=ei / length,
             damping=0.002, range=(-0.35, 0.35), springref=0, solreflimit=(0.003, 1))
        mesh(assets, f"turner_blade_{i}")
        visual(strip, f"turner_blade_{i}", "silicone_blade")
        contact(strip, f"turner_blade_{i}", "blade", type="mesh", mesh=f"turner_blade_{i}")
        parent = strip


def make_plate(assets, world):
    body = node(world, "body", name="plate", pos=PLATE_START)
    node(body, "freejoint", name="plate_free")
    node(body, "inertial", mass=0.48, pos=(0, 0, 0.005), diaginertia=(0.0019, 0.0019, 0.0038))
    mesh(assets, "plate_shell")
    visual(body, "plate_shell", "ceramic")
    contact(body, "plate_floor", "plate", type="cylinder", size=(0.1, 0.003), pos=(0, 0, 0.003))
    for i in range(48):
        mesh(assets, f"plate_rim_{i}")
        contact(body, f"plate_rim_{i}", "plate", type="mesh", mesh=f"plate_rim_{i}")


def make_pancake(assets, world):
    body = node(world, "body", name="pancake", pos=(PAN_START[0], PAN_START[1], PAN_START[2] + 0.0062))
    node(body, "freejoint", name="pancake_free")
    node(body, "inertial", mass=0.06, pos=(0, 0, 0.0045), diaginertia=(0.000075, 0.000075, 0.00015))
    mesh(assets, "pancake", ".obj")
    visual(body, "pancake", "pancake_skin")
    for i in range(48):
        mesh(assets, f"pancake_sector_{i}")
        contact(body, f"pancake_sector_{i}", "pancake", type="mesh", mesh=f"pancake_sector_{i}")


def add_wrist_stage(world, actuator, hand_body, ranges):
    """Six-axis wrist stage (world-frame slides, then serial X/Y/Z hinges) carrying the hand."""
    wrist = node(world, "body", name="wrist_stage")
    node(wrist, "inertial", pos=(0, 0, 0), mass=0.01, diaginertia=(0.00001,) * 3)
    hand_body.set("quat", "0 0.7071067811865476 0 0.7071067811865476")
    wrist.append(hand_body)
    for i, name in enumerate(("x", "y", "z", "rx", "ry", "rz")):
        axis = [int(i % 3 == j) for j in range(3)]
        lo, hi = ranges[name]
        wrist.insert(i, ET.Element("joint", name="wrist_" + name, type="slide" if i < 3 else "hinge",
                                   axis=" ".join(map(str, axis)), range=f"{lo:.17g} {hi:.17g}",
                                   damping="15" if i < 3 else "1", armature=".02"))
        actuator.insert(i, ET.Element("position", name="wrist_" + name + "_act", joint="wrist_" + name,
                                      kp="2500" if i < 3 else "120", kv="80" if i < 3 else "8", inheritrange="1",
                                      forcerange="-80 80" if i < 3 else "-10 10"))


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


def _repo_hand_dir():
    """The repository's prepared Sharpa assets when this file sits in the repository layout; None in a task dir."""
    parents = HERE.parents
    candidate = parents[4] / "images/dexhand/assets/hand" if len(parents) > 4 else None
    return candidate if candidate is not None and (candidate / "right_hand.xml").is_file() else None


def build(config, asset_dir=None, hand="sharpa"):
    """Compose the frozen scene with the selected genuine hand on the six-axis wrist stage."""
    hand_id = hands.canonical(hand)
    verify_assets()
    folder = Path(asset_dir or os.environ.get("DEXHAND_ASSET_DIR") or _repo_hand_dir() or hands.sharpa_dir())
    root = ET.parse(folder / "right_hand.xml").getroot()
    root.set("model", hands.info(hand_id)["model"] + " pancake serving")
    compiler = root.find("compiler")
    compiler.set("meshdir", str((folder / "assets/right").resolve()))
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
    marvin = config.get("rig") == "marvin"
    if not marvin:
        world.remove(hand_body)
        add_wrist_stage(world, actuator, hand_body, config["wrist_ranges"])
    for a in actuator:
        if a.tag == "general":
            # The vendor's velocity bias term is +0.9 (energy injecting); make it dissipative as in the
            # accepted DexHand families.
            bias = [float(v) for v in a.get("biasprm", "0 0 0").split()]
            bias[2] = -0.9
            a.set("biasprm", " ".join(map(str, bias)))
    sibling = folder.parent / "wuji_v2_2"
    wuji_folder = sibling if (sibling / "mjcf/right.xml").is_file() else None
    if marvin:
        # Tianji Marvin stand at the origin facing +x; the right arm serves, the left arm stays parked. The mount
        # body on the right flange keeps the name "wrist_stage" (the checker's hand-root lookup).
        rig = config["marvin"]
        _arm_rig_module().mount_marvin(root, rig["base_pos"], rig["base_yaw"], hand=hand_id, active=("right",),
                                       mount_names={"right": "wrist_stage"}, sharpa_folder=folder,
                                       wuji_folder=wuji_folder)
    elif hand_id != "sharpa":
        hands.replace_wave_hands(root, hand_id, folder=wuji_folder)
    add_materials(assets)
    node(world, "geom", name="floor", type="plane", pos=(0, 0, -0.1), size=(3, 3, 0.05), rgba=(0.55, 0.56, 0.55, 1),
         friction=(1, 0.005, 0.0001))
    node(world, "geom", name="counter_top", type="box", pos=(0.68, -0.10, COUNTER_Z - 0.025),
         size=(0.45, 0.55, 0.025), material="oak", friction=(FRICTION["counter"][0], 0.002, 0.0001))
    height = (COUNTER_Z - 0.025 + 0.1) / 2
    x0, x1 = 0.28, 1.12
    if marvin:
        # The stand's base plate reaches 0.75 m in front of the base: the cabinet starts behind it (the near part of
        # the counter top is cantilevered), so no robot geom overlaps furniture.
        x0 = max(x0, float(config["marvin"]["base_pos"][0]) + 0.77)
    node(world, "geom", name="counter_cabinet", type="box", pos=((x0 + x1) / 2, -0.10, height - 0.1),
         size=((x1 - x0) / 2, 0.52, height), material="cabinet", contype=0, conaffinity=0, group=2)
    make_pan(assets, world)
    make_turner(assets, world)
    make_plate(assets, world)
    make_pancake(assets, world)
    node(world, "light", name="key", pos=(0.2, -0.9, 2.4), dir=(0.25, 0.4, -1), diffuse=(0.78, 0.76, 0.72),
         castshadow="true")
    node(world, "light", name="fill", pos=(1.6, 0.9, 2.0), dir=(-0.5, -0.4, -1), diffuse=(0.40, 0.42, 0.45),
         castshadow="false")
    for camera in config["cameras"]:
        node(world, "camera", name=camera["name"], pos=camera["pos"],
             xyaxes=camera["xyaxes"], fovy=camera["fovy"])
    vis = node(root, "visual")
    node(vis, "global", offwidth=1280, offheight=720)
    node(vis, "quality", shadowsize=4096, offsamples=4)
    node(vis, "headlight", ambient=(0.30, 0.30, 0.30), diffuse=(0.45, 0.45, 0.45), specular=(0.08, 0.08, 0.08))
    xml = ET.tostring(root, encoding="unicode")
    return mujoco.MjModel.from_xml_string(xml), xml


def look_at(position, target, up=(0, 0, 1)):
    """Camera ``xyaxes`` that looks from ``position`` at ``target``."""
    forward = np.asarray(target, float) - np.asarray(position, float)
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, up)
    right /= np.linalg.norm(right)
    upv = np.cross(right, forward)
    return [*right.tolist(), *upv.tolist()]
