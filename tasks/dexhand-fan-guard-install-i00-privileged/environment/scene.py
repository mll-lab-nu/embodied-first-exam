"""Fan-guard installation scene: worktop, desk fan with rear cage and four clips, free front guard, and one genuine
dexterous hand (Sharpa Wave or Wuji Hand 2.2) on a six-axis wrist stage."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

from geometry import TABLE, make_fan, node


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
HERE = Path(__file__).resolve().parent


def _sharpa_folder(asset_dir=None):
    """The Sharpa Wave asset folder: argument, DEXHAND_ASSET_DIR, the image path, else a repository checkout."""
    candidates = [asset_dir, os.environ.get("DEXHAND_ASSET_DIR"), "/opt/dexhand/hand"]
    if len(HERE.parents) > 4:  # repository layout scripts/dexhand/families/<family>/ (task copies are shallower)
        candidates.append(HERE.parents[4] / "images/dexhand/assets/hand")
    for candidate in candidates:
        if candidate and (Path(candidate) / "right_hand.xml").is_file():
            return Path(candidate)
    raise RuntimeError("Sharpa Wave assets not found (set DEXHAND_ASSET_DIR)")


def build(config, asset_dir=None, hand="sharpa"):
    """Compose the frozen scene with the selected genuine hand on the same six-axis wrist stage."""
    hand_id = hands.canonical(hand)
    folder = _sharpa_folder(asset_dir)
    root = ET.parse(folder / "right_hand.xml").getroot()
    root.set("model", hands.info(hand_id)["model"] + " desk-fan front guard installation")
    root.find("compiler").set("meshdir", str((folder / "assets/right").resolve()))
    root.find("compiler").set("autolimits", "true")
    option = root.find("option")
    option.set("timestep", str(config["physics_dt"]))
    option.set("gravity", "0 0 -9.81")
    option.set("iterations", "60")
    option.set("ls_iterations", "20")
    option.set("integrator", "implicitfast")
    option.set("cone", "elliptic")
    node(root, "size", memory="256M")
    for key in root.findall("keyframe"):
        root.remove(key)
    assets, world, actuator = root.find("asset"), root.find("worldbody"), root.find("actuator")
    hand_body = world.find("body")
    world.remove(hand_body)
    stage = config["wrist_stage"]
    wrist = node(world, "body", name="wrist_stage", pos=stage["origin"])
    node(wrist, "inertial", pos=(0, 0, 0), mass=0.01, diaginertia=(0.00001,) * 3)
    hand_body.set("quat", "0 0.7071067811865476 0 0.7071067811865476")
    wrist.append(hand_body)
    for i, name in enumerate(("x", "y", "z", "rx", "ry", "rz")):
        axis = [int(i % 3 == j) for j in range(3)]
        lo, hi = stage["range"][i]
        wrist.insert(
            i,
            ET.Element(
                "joint",
                name="wrist_" + name,
                type="slide" if i < 3 else "hinge",
                axis=" ".join(map(str, axis)),
                range=f"{lo} {hi}",
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
    for g in hand_body.iter("geom"):
        if "fingertip_collision" in g.get("name", ""):
            g.set("friction", "1.5 .005 .0001")
    if hand_id != "sharpa":
        # Swap the Wave body under the unchanged wrist stage for the genuine Wuji Hand 2.2 model; the vendor's
        # joints, actuators, gains and contact geometry are kept as published. Wrist actuators stay first.
        sibling = folder.parent / "wuji_v2_2"
        hands.replace_wave_hands(root, hand_id, folder=sibling if (sibling / "mjcf/right.xml").is_file() else None)
    tendon = root.find("tendon")
    if tendon is None:
        tendon = node(root, "tendon")
    fan_asset_dir = HERE / "assets"
    make_fan(root, tendon, fan_asset_dir, None)
    node(assets, "texture", name="oak_grain", type="2d", builtin="gradient", width=256, height=256,
         rgb1=(0.56, 0.42, 0.29), rgb2=(0.47, 0.35, 0.24))
    node(assets, "material", name="oak", texture="oak_grain", texrepeat=(3, 3), reflectance=0.04, rgba=(1, 1, 1, 1))
    node(assets, "texture", name="studio_sky", type="skybox", builtin="gradient", width=256, height=256,
         rgb1=(0.62, 0.68, 0.66), rgb2=(0.84, 0.85, 0.80))
    node(world, "geom", name="floor", type="plane", pos=(0, 0, -0.1), size=(3, 3, 0.05), rgba=(0.65, 0.68, 0.66, 1))
    node(world, "geom", name="table_top", type="box", pos=(0.68, 0, TABLE - 0.022), size=(0.40, 0.50, 0.022),
         material="oak", friction=(0.60, 0.003, 0.0001), solref=(0.004, 1))
    for x in (0.32, 1.04):
        for y in (-0.44, 0.44):
            node(world, "geom", name=f"table_leg_{x}_{y}", type="box", pos=(x, y, 0.27), size=(0.022, 0.022, 0.358),
                 rgba=(0.27, 0.29, 0.27, 1))
    node(world, "light", name="key", pos=(-0.6, -1.1, 2.4), dir=(0.6, 0.6, -1), diffuse=(0.9, 0.87, 0.80),
         castshadow="true")
    node(world, "light", name="fill", pos=(1.4, 0.8, 2.1), dir=(-0.5, -0.3, -1), diffuse=(0.55, 0.58, 0.60),
         castshadow="false")
    for cam in config["cameras"]:
        node(world, "camera", name=cam["name"], pos=cam["pos"], xyaxes=cam["xyaxes"], fovy=cam["fovy"])
    v = node(root, "visual")
    node(v, "global", offwidth=1280, offheight=720)
    # Render-only tessellation: ~1,700 thin wire capsules dominate software rendering (no effect on physics).
    node(v, "quality", shadowsize=4096, offsamples=4, numslices=16, numstacks=8)
    node(v, "headlight", ambient=(0.35, 0.35, 0.35), diffuse=(0.5, 0.5, 0.5), specular=(0.1, 0.1, 0.1))
    node(v, "map", znear=0.005)
    xml = ET.tostring(root, encoding="unicode")
    model = mujoco.MjModel.from_xml_string(xml)
    return model, xml
