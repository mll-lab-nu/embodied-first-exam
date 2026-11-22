"""Bosch-style handheld vacuum (T19 UniversalVac18 geometry) with a free dust bin and one dexterous hand.

The vacuum housing, filter, lower seat, spring release button (passive slide with the native spring) and the
transparent dust bin are the authored T19 scene geometry, copied verbatim into ``assets/vacuum_scene.xml``
(sha256 in ``assets/manifest.json``). This module composes that scene with the selected genuine hand on a
six-axis wrist stage. Only the hand's finger actuators and the wrist-stage actuators exist; every task object
moves through contact and passive joint dynamics.
"""

from __future__ import annotations

import copy
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


def arm_rig_id():
    return _arm_rig_module().ROBOT_ID


def add_marvin_rig(root, config, hand_id, folder):
    """The Tianji Marvin stand with both 7-DoF arms (shared arm_rig): the left hand holds the vacuum body, the right
    hand presses the release button and handles the bin."""
    arm_rig = _arm_rig_module()
    actuator, hand = root.find("actuator"), root.find("worldbody").find("body")
    for a in actuator:  # the family's Sharpa tweaks, before mounting (the mirrored left Wave inherits them)
        if a.tag == "general":
            bias = [float(v) for v in a.get("biasprm", "0 0 0").split()]
            bias[2] = -0.9
            a.set("biasprm", " ".join(map(str, bias)))
    for g in hand.iter("geom"):
        if "fingertip_collision" in g.get("name", ""):
            g.set("friction", "1.5 .005 .0001")
    sibling = folder.parent / "wuji_v2_2"
    marvin = config["marvin"]
    return arm_rig.mount_marvin(root, marvin["base_pos"], marvin["base_yaw"], hand=hand_id, active=("left", "right"),
                                mount_names={"right": "wrist_stage", "left": "left_wrist_stage"},
                                sharpa_folder=folder,
                                wuji_folder=sibling if (sibling / "mjcf/right.xml").is_file() else None)

# Native scene items that are copied; the native file also carries unused Sharpa default classes and materials.
SCENE_MATERIALS = ("vac_green", "vac_black", "vac_red", "vac_smoke", "vac_filter")


def verify_assets():
    """Check the copied scene files against assets/manifest.json (sha256 + size)."""
    manifest = json.loads((ASSETS / "manifest.json").read_text())
    for name, entry in manifest["files"].items():
        data = (ASSETS / name).read_bytes()
        if len(data) != entry["bytes"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise RuntimeError(f"Scene asset {name} differs from assets/manifest.json")
    return manifest


def node(parent, tag, **attributes):
    def value(x):
        return " ".join(repr(float(v)) if isinstance(v, float) else str(v) for v in x) if isinstance(
            x, (tuple, list, np.ndarray)) else str(x)

    return ET.SubElement(parent, tag, {k: value(v) for k, v in attributes.items()})


def look_at(position, target, up=(0, 0, 1)):
    """xyaxes of a camera at ``position`` looking at ``target``."""
    position, target = np.asarray(position, float), np.asarray(target, float)
    forward = target - position
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, up)
    right /= np.linalg.norm(right)
    upward = np.cross(right, forward)
    return np.round(np.concatenate([right, upward]), 6)


def _sharpa_folder(asset_dir=None):
    candidates = [asset_dir, os.environ.get("DEXHAND_ASSET_DIR"), "/opt/dexhand/hand"]
    candidates += [parent / "images/dexhand/assets/hand" for parent in HERE.parents]
    for candidate in candidates:
        if candidate and (Path(candidate) / "right_hand.xml").is_file():
            return Path(candidate)
    raise FileNotFoundError("Sharpa Wave assets not found (set DEXHAND_ASSET_DIR)")


def add_left_stage(root, config, folder):
    """The second hand: the right Wave mirrored in y (shared ``arm_rig.mirrored_left_wave``, same tweaks) on its own
    six-axis wrist stage (``task.json`` ``left_wrist_stage``); its 6 stage + 22 finger actuators follow the right
    hand's 28."""
    arm_rig = _arm_rig_module()
    world, actuator, asset = root.find("worldbody"), root.find("actuator"), root.find("asset")
    contact = root.find("contact")
    if contact is None:
        contact = node(root, "contact")
    body, meshes, excludes, fingers = arm_rig.mirrored_left_wave(root, folder)
    asset.extend(meshes)
    contact.extend(excludes)
    stage = config["left_wrist_stage"]
    wrist = node(world, "body", name="left_wrist_stage", pos=stage["origin"])
    node(wrist, "inertial", pos=(0, 0, 0), mass=0.01, diaginertia=(0.00001,) * 3)
    for i, name in enumerate(("x", "y", "z", "rx", "ry", "rz")):
        axis = [int(i % 3 == j) for j in range(3)]
        low, high = stage["range"][i]
        node(wrist, "joint", name="left_wrist_" + name, type="slide" if i < 3 else "hinge", axis=" ".join(map(str, axis)),
             range=f"{low} {high}", damping="15" if i < 3 else "1", armature=".02")
        node(actuator, "position", name="left_wrist_" + name + "_act", joint="left_wrist_" + name,
             kp="2500" if i < 3 else "120", kv="80" if i < 3 else "8", inheritrange="1",
             forcerange="-80 80" if i < 3 else "-10 10")
    body.set("pos", "0 0 0")
    body.set("quat", stage["hand_quat"])
    wrist.append(body)
    actuator.extend(fingers)


def add_wrist_stage(root, config, hand_body, hand_id, folder):
    """Authoring/legacy rig: the hand on a floating six-axis wrist stage."""
    world, actuator = root.find("worldbody"), root.find("actuator")
    world.remove(hand_body)
    stage = config["wrist_stage"]
    wrist = node(world, "body", name="wrist_stage", pos=stage["origin"])
    node(wrist, "inertial", pos=(0, 0, 0), mass=0.01, diaginertia=(0.00001,) * 3)
    hand_body.set("quat", config["wrist_stage"]["hand_quat"])
    wrist.append(hand_body)
    for i, name in enumerate(("x", "y", "z", "rx", "ry", "rz")):
        axis = [int(i % 3 == j) for j in range(3)]
        low, high = stage["range"][i]
        wrist.insert(i, ET.Element(
            "joint", name="wrist_" + name, type="slide" if i < 3 else "hinge", axis=" ".join(map(str, axis)),
            range=f"{low} {high}", damping="15" if i < 3 else "1", armature=".02"))
        actuator.insert(i, ET.Element(
            "position", name="wrist_" + name + "_act", joint="wrist_" + name,
            kp="2500" if i < 3 else "120", kv="80" if i < 3 else "8", inheritrange="1",
            forcerange="-80 80" if i < 3 else "-10 10"))
    for a in actuator:
        if a.tag == "general":
            bias = [float(v) for v in a.get("biasprm", "0 0 0").split()]
            bias[2] = -0.9
            a.set("biasprm", " ".join(map(str, bias)))
    for g in hand_body.iter("geom"):
        if "fingertip_collision" in g.get("name", ""):
            g.set("friction", "1.5 .005 .0001")
    if hand_id != "sharpa":
        sibling = folder.parent / "wuji_v2_2"
        hands.replace_wave_hands(root, hand_id, folder=sibling if (sibling / "mjcf/right.xml").is_file() else None)



def build(config, asset_dir=None, hand="sharpa"):
    """Compose the frozen vacuum scene with the selected genuine hand on the six-axis wrist stage."""
    verify_assets()
    hand_id = hands.canonical(hand)
    folder = _sharpa_folder(asset_dir)
    root = ET.parse(folder / "right_hand.xml").getroot()
    root.set("model", hands.info(hand_id)["model"] + " vacuum dust bin reseat")
    root.find("compiler").set("meshdir", str((folder / "assets/right").resolve()))
    option = root.find("option")
    option.set("timestep", str(config["physics_dt"]))
    option.set("gravity", "0 0 -9.81")
    option.set("iterations", "60")
    option.set("ls_iterations", "20")
    option.set("integrator", "implicitfast")
    option.set("cone", "elliptic")
    option.set("impratio", "10")
    for key in root.findall("keyframe"):
        root.remove(key)
    assets, world, actuator = root.find("asset"), root.find("worldbody"), root.find("actuator")
    hand_body = world.find("body")

    if config.get("rig", "floating") == "marvin":
        add_marvin_rig(root, config, hand_id, folder)
    else:
        add_wrist_stage(root, config, hand_body, "sharpa", folder)
        if "left_wrist_stage" in config:
            add_left_stage(root, config, folder)
        if hand_id != "sharpa":
            sibling = folder.parent / "wuji_v2_2"
            hands.replace_wave_hands(root, hand_id, folder=sibling if (sibling / "mjcf/right.xml").is_file() else None)

    # ------------------------------------------------------------------ native T19 scene (verbatim geometry)
    native = ET.parse(ASSETS / "vacuum_scene.xml").getroot()
    for item in native.find("asset"):
        if item.tag == "mesh" or (item.tag == "material" and item.get("name") in SCENE_MATERIALS):
            assets.append(copy.deepcopy(item))
    node(assets, "texture", name="studio_sky", type="skybox", builtin="gradient", width=256, height=256,
         rgb1=(0.65, 0.69, 0.68), rgb2=(0.79, 0.79, 0.75))
    node(assets, "texture", name="counter_grain", type="2d", builtin="flat", width=64, height=64,
         rgb1=(0.75, 0.73, 0.68), rgb2=(0.75, 0.73, 0.68))
    for item in native.find("worldbody"):
        world.append(copy.deepcopy(item))
    body = next(b for b in world.iter("body") if b.get("name") == "vacuum_body")
    for lip in config.get("latch_lips", []):
        # A fixed lip over the bin's latch bridge: with the tooth up the bin can neither tilt out (tooth) nor lift
        # straight out (lip); tilting the top out after pressing the button slides the bridge out from under it.
        node(body, "geom", name=lip["name"], type="box", pos=lip["pos"], size=lip["size"], mass=0,
             material="vac_black", friction=lip.get("friction", (0.15, 0.005, 0.0001)), condim=3,
             solref="0.004 1", solimp="0.95 0.99 0.001")
    for skid in config.get("base_skids", []):
        # A flat rubber skid under the housing (the native rounded housing hull rocks and creeps on the counter).
        node(body, "geom", name=skid["name"], type="box", pos=skid["pos"], size=skid["size"], mass=0,
             material="vac_black", friction=skid.get("friction", (0.9, 0.005, 0.0001)), condim=4, solref="0.004 1",
             solimp="0.95 0.99 0.001")
    contact = root.find("contact")
    if contact is None:
        contact = node(root, "contact")
    for pair in native.find("contact"):
        pair = copy.deepcopy(pair)
        contact.append(pair)

    # Physics adaptations (documented in README): mm-scale contact margins for the thin bin shell and latch,
    # and a reset that starts from the settled assembled state (task.json initial_qpos).
    for g in world.iter("geom"):
        name = g.get("name", "")
        if name.startswith(("container_", "spring_latch", "release_button", "lower_seat", "filter_", "button_guide",
                            "vac_", "handle_", "battery_", "on_off")):
            for key, value in config.get("object_contact", {}).items():
                g.set(key, value)
    for j in world.iter("joint"):
        if j.get("name") == "button_depression" and "button_range" in config:
            # Release-button travel (native 6 mm): the settled bin sits ~1 mm lower than the authored pose, so the
            # tooth needs ~6.2 mm to pass under the catch; the travel is extended to 7.5 mm.
            j.set("range", " ".join(str(v) for v in config["button_range"]))
    for g in world.iter("geom"):
        if g.get("name", "").startswith("button_guide_lower") and "button_range" in config:
            # The lower guide is the travel stop of the button's guide tabs: move it down with the longer travel.
            x, y, z = (float(v) for v in g.get("pos").split())
            g.set("pos", f"{x} {y} {z - (config['button_range'][1] - 0.006)}")
    for g in world.iter("geom"):
        shift = config.get("geom_shift", {}).get(g.get("name", ""))
        if shift:
            # Documented geometry fix: the native lower filter rim protrudes into the bin mouth and, with the
            # lower lip, leaves no collision-free removal path (the source notes 3.66 mm buried interference).
            x, y, z = (float(v) for v in g.get("pos").split())
            g.set("pos", f"{x + shift[0]} {y + shift[1]} {z + shift[2]}")
    for g in world.iter("geom"):
        if any(g.get("name", "").startswith(prefix) for prefix in config.get("visual_only_prefixes", [])):
            # Documented: the stationary filter frame/pleats stay visible but do not collide. In the native geometry
            # the frame protrudes into the bin mouth and, with the lower lip, leaves no collision-free removal path
            # (the source notes 3.66 mm buried interference along its prescribed path).
            g.set("contype", "0")
            g.set("conaffinity", "0")
    for g in world.iter("geom"):
        friction = config.get("geom_friction", {}).get(g.get("name", ""))
        if friction:
            # Documented: smooth plastic latch ramp (low friction) and rubber base skid.
            g.set("friction", " ".join(str(v) for v in friction))
    for g in world.iter("geom"):
        resize = config.get("geom_resize", {}).get(g.get("name", ""))
        if resize:
            # Documented: taller lower-seat lips so the released bin stays hooked while it tips.
            g.set("pos", " ".join(str(v) for v in resize["pos"]))
            g.set("size", " ".join(str(v) for v in resize["size"]))
    for g in world.iter("geom"):
        for prefix, bits in config.get("collision_bits", {}).items():
            if g.get("name", "").startswith(prefix):
                # Documented: the lower seat ledges sit in the bin's tab slots; the reduced bin shell has no slot
                # cut-outs, so the ledges collide only with the lower tabs (bit 2), never with the shell.
                g.set("contype", str(bits[0]))
                g.set("conaffinity", str(bits[1]))
    for pair in contact.findall("pair"):
        for key, value in config.get("guide_pair", {}).items():
            pair.set(key, value)

    node(world, "camera", name="overview", pos=config["cameras"]["overview"]["pos"],
         xyaxes=look_at(config["cameras"]["overview"]["pos"], config["cameras"]["overview"]["target"]),
         fovy=config["cameras"]["overview"]["fovy"])
    node(world, "camera", name="closeup", pos=config["cameras"]["closeup"]["pos"],
         xyaxes=look_at(config["cameras"]["closeup"]["pos"], config["cameras"]["closeup"]["target"]),
         fovy=config["cameras"]["closeup"]["fovy"])
    v = root.find("visual")
    if v is None:
        v = node(root, "visual")
    node(v, "global", offwidth=1280, offheight=720)
    node(v, "quality", shadowsize=4096, offsamples=4)
    node(v, "headlight", ambient=(0.30, 0.30, 0.30), diffuse=(0.45, 0.45, 0.45), specular=(0.1, 0.1, 0.1))
    xml = ET.tostring(root, encoding="unicode")
    return mujoco.MjModel.from_xml_string(xml), xml
