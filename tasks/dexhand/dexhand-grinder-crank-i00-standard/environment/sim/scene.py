"""HARIO-style manual coffee grinder on a counter, composed with a Tianji Marvin dual-arm robot and two dexterous hands.

The grinder geometry, materials, masses and passive crank/knob joints come from the unchanged scene source
``assets/source/hario_mechanism.py`` (sha256 in ``assets/manifest.json``). Task-level overrides (grinding load,
contact parameters) are applied to the generated MJCF elements and listed in ``MECHANISM_OVERRIDES``.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
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
        path = HERE.parents[1] / "shared/arm_rig.py"
        spec = importlib.util.spec_from_file_location("arm_rig", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules["arm_rig"] = module
        spec.loader.exec_module(module)
        return module


arm_rig = _arm_rig_module()
HAND_MOUNTS = {"right": "right_wrist_stage", "left": "left_wrist_stage"}  # flange mount bodies (hand roots)


def _mechanism_module():
    path = ASSETS / "source/hario_mechanism.py"
    manifest = json.loads((ASSETS / "manifest.json").read_text())
    expected = manifest["files"]["source/hario_mechanism.py"]["sha256"]
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise RuntimeError("assets/source/hario_mechanism.py differs from its manifest hash")
    spec = importlib.util.spec_from_file_location("grinder_hario_mechanism", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mechanism = _mechanism_module()



def node(parent, tag, **attributes):
    def value(x):
        return " ".join(f"{float(v):.17g}" for v in x) if isinstance(x, (tuple, list, np.ndarray)) else str(x)

    return ET.SubElement(parent, tag, {k: value(v) for k, v in attributes.items()})


def sharpa_folder(asset_dir=None) -> Path:
    if asset_dir:
        return Path(asset_dir)
    if os.environ.get("DEXHAND_ASSET_DIR"):
        return Path(os.environ["DEXHAND_ASSET_DIR"])
    candidates = [Path("/opt/dexhand/hand")]
    if len(HERE.parents) > 4:  # repository checkout: images/dexhand/assets/hand
        candidates.append(HERE.parents[4] / "images/dexhand/assets/hand")
    for candidate in candidates:
        if (candidate / "right_hand.xml").is_file():
            return candidate
    raise FileNotFoundError("Sharpa Wave assets not found (set DEXHAND_ASSET_DIR)")


def add_grinder(root, config):
    """Add the unchanged source grinder, then apply the declared task overrides."""
    g = config["grinder"]
    mill = mechanism.add_grinder(root, g["base_position"])
    world = root.find("worldbody")
    crank_joint = mill.find(".//joint[@name='crank_rotation']")
    crank_joint.set("frictionloss", repr(float(g["crank_frictionloss_nm"])))
    crank_joint.set("damping", repr(float(g["crank_damping_nms"])))
    crank_joint.set("armature", repr(float(g["crank_armature"])))
    knob_joint = mill.find(".//joint[@name='knob_spin']")
    knob_joint.set("armature", repr(float(g["knob_armature"])))
    base = mill.find("geom[@name='mill_base']")
    base.set("friction", " ".join(repr(float(v)) for v in g["base_friction"]))
    base.set("condim", str(g["base_condim"]))
    # The knob and crank handle are what the fingers grip: rubber-like resin friction on the knob.
    for name in ("knob_resin_bulb", "knob_resin_neck"):
        geom = mill.find(f".//geom[@name='{name}']")
        geom.set("friction", " ".join(repr(float(v)) for v in g["knob_friction"]))
        geom.set("condim", "4")
    # The steel shaft and the inner burr sit inside the closed grinder body: they never take part in contacts.
    for name in ("crank_shaft", "inner_burr"):
        geom = mill.find(f".//geom[@name='{name}']")
        geom.set("contype", "0")
        geom.set("conaffinity", "0")
    # Decorative visual-only details seen in the approved film (steel band, lid ring); no mass, no contact.
    visual = dict(contype=0, conaffinity=0, group=2, mass=0)
    node(mill, "geom", name="mill_steel_band", type="cylinder", size=(0.0262, 0.0035), pos=(0, 0, 0.0835),
         material="mill_steel", **visual)
    node(mill, "geom", name="mill_lid_ring", type="cylinder", size=(0.0362, 0.0012), pos=(0, 0, 0.1745),
         material="mill_steel", **visual)
    return mill, world


def build(config, asset_dir=None, hand="sharpa"):
    """Compose the frozen grinder scene with the Marvin robot and two hands of the selected model.

    Actuator order: left arm (7), right arm (7), left-hand fingers, right-hand fingers (``arm_rig`` layout)."""
    hand_id = hands.canonical(hand)
    folder = sharpa_folder(asset_dir)
    root = arm_rig.sharpa_root(folder)
    root.set("model", "Marvin + " + hands.info(hand_id)["model"] + " manual coffee grinder")
    root.find("compiler").set("inertiafromgeom", "auto")
    option = root.find("option")
    option.set("timestep", repr(float(config["physics_dt"])))
    option.set("gravity", "0 0 -9.81")
    option.set("iterations", "80")
    option.set("integrator", "implicitfast")
    option.set("cone", "elliptic")
    option.set("impratio", "10")
    # Several contact points for convex-convex pairs (the grinder's base disk resting on the counter box).
    node(option, "flag", multiccd="enable")
    assets, world, actuator = root.find("asset"), root.find("worldbody"), root.find("actuator")
    # The family's Sharpa tweaks on the right Wave before mounting (arm_rig mirrors it for the left flange):
    # dissipative finger velocity feedback and fingertip friction 1.5.
    for a in actuator:
        if a.tag == "general":
            bias = [float(v) for v in a.get("biasprm", "0 0 0").split()]
            while len(bias) < 3:
                bias.append(0.0)
            bias[2] = -0.9
            a.set("biasprm", " ".join(map(str, bias)))
    for g in world.iter("geom"):
        if "fingertip_collision" in g.get("name", ""):
            g.set("friction", "1.5 .005 .0001")
    robot = config["robot_base"]
    sibling = folder.parent / "wuji_v2_2"
    arm_rig.mount_marvin(root, base_pos=robot["pos"], base_yaw=robot["yaw"], hand=hand_id, active=("left", "right"),
                         sharpa_folder=folder, mount_names=HAND_MOUNTS,
                         wuji_folder=sibling if (sibling / "mjcf/right.xml").is_file() else None)
    # ---- room, counter and lights (source scene layout: counter top z = 0.70 m, grinder at x = 0.45 m)
    node(assets, "texture", name="sky", type="skybox", builtin="gradient", rgb1=(0.63, 0.68, 0.67),
         rgb2=(0.85, 0.84, 0.79), width=512, height=512)
    node(assets, "texture", name="counter_tex", type="2d", builtin="flat", width=256, height=256,
         rgb1=(0.77, 0.75, 0.70), rgb2=(0.77, 0.75, 0.70), mark="random", random=0.04, markrgb=(0.80, 0.78, 0.73))
    node(assets, "material", name="counter_material", texture="counter_tex", texrepeat=(4, 4), reflectance=0.03)
    c = config["counter"]
    node(world, "geom", name="floor", type="plane", size=(2, 2, 0.05), pos=(0, 0, c["floor_z"]),
         rgba=(0.63, 0.65, 0.61, 1))
    node(world, "geom", name="counter", type="box", size=c["half_size"], pos=c["center"],
         material="counter_material", friction=c["friction"], condim=3)
    cx, cy, cz = c["center"]
    hx, hy, hz = c["half_size"]
    leg_h = (cz - hz - c["floor_z"]) / 2
    for x in (cx - hx + 0.02, cx + hx - 0.02):
        for y in (cy - hy + 0.06, cy + hy - 0.06):
            node(world, "geom", name=f"leg_{x:.2f}_{y:.2f}", type="box", size=(0.022, 0.022, leg_h),
                 pos=(x, y, c["floor_z"] + leg_h), rgba=(0.28, 0.26, 0.22, 1))
    node(world, "light", pos=(0.4, -0.8, 1.8), dir=(0, 0.3, -1), diffuse=(0.8, 0.8, 0.8))
    node(world, "light", pos=(0.4, 0.8, 1.6), dir=(0, -0.3, -1), diffuse=(0.55, 0.55, 0.55))
    add_grinder(root, config)
    for name, cam in config["cameras"].items():
        node(world, "camera", name=name, pos=cam["pos"], mode="targetbody" if False else "fixed",
             xyaxes=look_at(cam["pos"], cam["target"]), fovy=cam["fovy"])
    v = root.find("visual")
    if v is None:
        v = node(root, "visual")
    node(v, "global", offwidth=1280, offheight=720)
    node(v, "quality", shadowsize=4096, offsamples=4)
    node(v, "headlight", ambient=(0.32, 0.32, 0.32), diffuse=(0.5, 0.5, 0.5), specular=(0.12, 0.12, 0.12))
    xml = ET.tostring(root, encoding="unicode")
    return mujoco.MjModel.from_xml_string(xml), xml


def look_at(position, target, up=(0, 0, 1)):
    position, target, up = (np.asarray(v, dtype=float) for v in (position, target, up))
    forward = target - position
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, up)
    right /= np.linalg.norm(right)
    true_up = np.cross(right, forward)
    return [round(float(v), 6) for v in (*right, *true_up)]
