"""T11 coffee cup, coffee surface and teaspoon on a stone worktop, with a genuine hand on the Tianji Marvin arm.

Geometry follows the approved T11 scene (source: scene_expansion/repairs/coffee_tripod, refined presentation
meshes in ``assets/``): cup 57 mm outer / 50 mm inner radius, 100 mm tall, 8 mm internal floor, rounded U handle
(300 g); stainless teaspoon with a 24 x 46 mm bowl and 181.7 mm axial reach (35 g); worktop top at z = 0.75 m.
The cup and spoon are free bodies; they move only through contact. Coffee is a visual surface only.
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

# Cup frame (body origin = centre of the cup base), metres.
CUP_OUTER_R = 0.057
CUP_INNER_R = 0.050
CUP_FLOOR_Z = 0.008
CUP_RIM_Z = 0.100
COFFEE_Z = 0.064  # coffee+milk surface above the cup base (world z = 0.814 with the cup on the worktop; T11 level after the 23.75 ml milk)
# Spoon frame (body origin = bowl centre; handle along +z): bowl spans z in [-0.023, 0.023].
BOWL_HALF_LENGTH = 0.023
SPOON_TOP_Z = 0.1817

MATTE = dict(friction=(0.6, 0.005, 0.0005), solref=(0.005, 1), solimp=(0.95, 0.99, 0.001))
STEEL = dict(friction=(1.0, 0.005, 0.0005), solref=(0.005, 1), solimp=(0.95, 0.99, 0.001))


def node(parent, tag, **attributes):
    def value(x):
        return " ".join(repr(float(v)) if isinstance(v, (float, np.floating)) else str(v) for v in x) if isinstance(
            x, (tuple, list, np.ndarray)
        ) else (repr(float(x)) if isinstance(x, (float, np.floating)) else str(x))

    return ET.SubElement(parent, tag, {k: value(v) for k, v in attributes.items()})


def verify_assets(folder=HERE / "assets"):
    """Check every offline asset against ``assets/manifest.json`` (sha256 + size)."""
    manifest = json.loads((folder / "manifest.json").read_text())
    for name, entry in manifest["files"].items():
        data = (folder / name).read_bytes()
        if len(data) != entry["bytes"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise RuntimeError(f"Asset {name} does not match assets/manifest.json")
    return manifest


def add_cup(world, assets, config):
    pos = config["cup_pos"]
    cup = node(world, "body", name="cup", pos=pos[:3], quat=pos[3:])
    node(cup, "freejoint", name="cup_free")
    node(cup, "inertial", pos=(0.012, 0, 0.046), mass=0.3, diaginertia=(0.00054, 0.00075, 0.00072))
    node(assets, "mesh", name="cup_mesh", file=str((HERE / "assets/cup.obj").resolve()))
    node(cup, "geom", name="cup_visual", type="mesh", mesh="cup_mesh", contype=0, conaffinity=0, group=2, mass=0,
         material="glaze")
    # Coffee: a visual surface at the fill height (not simulated). A dark disk just below hides the cavity.
    node(cup, "geom", name="coffee_surface", type="cylinder", size=(CUP_INNER_R - 0.0004, 0.0008),
         pos=(0, 0, COFFEE_Z - 0.0008), contype=0, conaffinity=0, group=2, mass=0, material="coffee")
    node(cup, "geom", name="coffee_body", type="cylinder", size=(CUP_INNER_R - 0.0006, (COFFEE_Z - CUP_FLOOR_Z) / 2 - 0.001),
         pos=(0, 0, (COFFEE_Z + CUP_FLOOR_Z) / 2 - 0.001), contype=0, conaffinity=0, group=2, mass=0,
         rgba=(0.16, 0.08, 0.035, 1))
    node(cup, "geom", name="cup_base", type="cylinder", size=(CUP_OUTER_R, CUP_FLOOR_Z / 2), pos=(0, 0, CUP_FLOOR_Z / 2),
         group=3, mass=0, rgba=(0.8, 0.8, 0.8, 0.3), **MATTE)
    n = 32
    half = (CUP_OUTER_R - CUP_INNER_R) / 2
    width = (CUP_OUTER_R * np.tan(np.pi / n)) + 0.0004
    for i in range(n):
        a = 2 * np.pi * i / n
        r = (CUP_OUTER_R + CUP_INNER_R) / 2
        node(cup, "geom", name=f"cup_wall_{i}", type="box", size=(half, width, (CUP_RIM_Z - CUP_FLOOR_Z) / 2),
             pos=(r * np.cos(a), r * np.sin(a), (CUP_RIM_Z + CUP_FLOOR_Z) / 2), euler=(0, 0, a), group=3, mass=0,
             rgba=(0.8, 0.8, 0.8, 0.3), **MATTE)
    for name, size, p in (
        ("cup_handle_top", (0.0445, 0.008, 0.006), (0.0865, 0, 0.086)),
        ("cup_handle_bottom", (0.0445, 0.008, 0.006), (0.0865, 0, 0.024)),
        ("cup_handle_side", (0.008, 0.008, 0.035), (0.117, 0, 0.055)),
    ):
        node(cup, "geom", name=name, type="box", size=size, pos=p, group=3, mass=0, rgba=(0.8, 0.8, 0.8, 0.3), **MATTE)
    return cup


def add_spoon(world, assets, config):
    pos = config["spoon_pos"]
    spoon = node(world, "body", name="spoon", pos=pos[:3], quat=pos[3:])
    node(spoon, "freejoint", name="spoon_free")
    node(spoon, "inertial", pos=(0, 0, 0.069), mass=0.035, diaginertia=(0.000125, 0.000125, 1.2e-6))
    node(assets, "mesh", name="spoon_mesh", file=str((HERE / "assets/spoon.obj").resolve()))
    node(spoon, "geom", name="spoon_visual", type="mesh", mesh="spoon_mesh", contype=0, conaffinity=0, group=2, mass=0,
         material="steel")
    node(spoon, "geom", name="spoon_shaft", type="capsule", fromto=(0, 0, 0.022, 0, 0, 0.179), size=(0.0027,), group=3,
         mass=0, rgba=(0.7, 0.7, 0.75, 0.3), **STEEL)
    # The pressed oval bowl (24 x 46 mm, 6.6 mm deep) as two crossed flat slabs: flat faces/edges rest stably
    # (a smooth ellipsoid proxy rocks about the spoon axis without damping).
    node(spoon, "geom", name="spoon_bowl", type="box", size=(0.0032, 0.0105, 0.0125), pos=(0.001, 0, 0),
         group=3, mass=0, rgba=(0.7, 0.7, 0.75, 0.3), **STEEL)
    node(spoon, "geom", name="spoon_bowl_long", type="box", size=(0.0032, 0.0062, 0.0215), pos=(0.001, 0, 0),
         group=3, mass=0, rgba=(0.7, 0.7, 0.75, 0.3), **STEEL)
    node(spoon, "site", name="bowl_center", pos=(0, 0, 0), size=(0.002,), group=5)
    node(spoon, "site", name="bowl_tip", pos=(0, 0, -BOWL_HALF_LENGTH), size=(0.002,), group=5)
    node(spoon, "site", name="bowl_neck", pos=(0, 0, BOWL_HALF_LENGTH), size=(0.002,), group=5)
    node(spoon, "site", name="spoon_top", pos=(0, 0, SPOON_TOP_Z), size=(0.002,), group=5)
    return spoon


def _arm_rig_module():
    """The shared Marvin arm rig (copied next to this file in generated task dirs)."""
    try:
        import arm_rig

        return arm_rig
    except ModuleNotFoundError:
        path = HERE.parent.parent / "shared/arm_rig.py"
        spec = importlib.util.spec_from_file_location("arm_rig", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules["arm_rig"] = module
        spec.loader.exec_module(module)
        return module


arm_rig = _arm_rig_module()


def add_rig(root, folder, hand_id, config):
    """The Tianji Marvin dual-arm stand (``arm_rig.mount_marvin``): the right arm and hand do the task, the left
    arm hangs parked beside the torso. The right hand's flange mount keeps the old name ``wrist_stage``."""
    option = root.find("option")
    option.set("timestep", str(config["physics_dt"]))
    option.set("gravity", "0 0 -9.81")
    option.set("iterations", "80")
    option.set("integrator", "implicitfast")
    option.set("cone", "elliptic")
    node(option, "flag", multiccd="enable")
    for key in root.findall("keyframe"):
        root.remove(key)
    actuator, world = root.find("actuator"), root.find("worldbody")
    # The wave-2 Sharpa tweaks, applied to the right Wave before mounting (the rig mirrors it for the left hand).
    for a in actuator:
        if a.tag == "general":
            bias = [float(v) for v in a.get("biasprm", "0 0 0").split()]
            bias[2] = -0.9
            a.set("biasprm", " ".join(map(str, bias)))
    for g in world.iter("geom"):
        if "fingertip_collision" in g.get("name", ""):
            g.set("friction", "1.5 .005 .0001")
    sibling = Path(os.environ.get("WUJI_ASSET_DIR") or folder.parent / "wuji_v2_2")
    marvin = config["marvin"]
    return arm_rig.mount_marvin(root, marvin["base_pos"], marvin["base_yaw"], hand=hand_id, active=("right",),
                                mount_names={"right": "wrist_stage"}, sharpa_folder=folder,
                                wuji_folder=sibling if (sibling / "mjcf/right.xml").is_file() else None)


def build(config, asset_dir=None, hand="sharpa"):
    """Compose the frozen scene with the selected genuine hands on the Marvin dual-arm stand (right arm active)."""
    hand_id = hands.canonical(hand)
    verify_assets()
    folder = asset_dir or os.environ.get("DEXHAND_ASSET_DIR")
    if not folder:
        # Repository checkout (scripts/dexhand/families/<family>/) or the image default.
        repo = HERE.parents[4] / "images/dexhand/assets/hand" if len(HERE.parents) > 4 else None
        folder = repo if repo is not None and (repo / "right_hand.xml").is_file() else "/opt/dexhand/hand"
    folder = Path(folder)
    root = ET.parse(folder / "right_hand.xml").getroot()
    root.set("model", hands.info(hand_id)["model"] + " coffee stirring")
    root.find("compiler").set("meshdir", str((folder / "assets/right").resolve()))
    add_rig(root, folder, hand_id, config)
    assets, world = root.find("asset"), root.find("worldbody")
    node(assets, "texture", name="stone", type="2d", builtin="flat", width=512, height=512, rgb1=(0.83, 0.81, 0.77),
         rgb2=(0.78, 0.76, 0.72), mark="random", random=0.08, markrgb=(0.74, 0.72, 0.68))
    node(assets, "material", name="stone_material", texture="stone", texrepeat=(6, 4), reflectance=0.04, specular=0.2)
    node(assets, "texture", name="studio_sky", type="skybox", builtin="gradient", width=256, height=256,
         rgb1=(0.90, 0.89, 0.86), rgb2=(0.97, 0.96, 0.93))
    node(assets, "material", name="glaze", rgba=(0.90, 0.87, 0.80, 1), specular=0.45, shininess=0.6, reflectance=0.03)
    node(assets, "material", name="steel", rgba=(0.78, 0.80, 0.83, 1), specular=0.9, shininess=0.9, reflectance=0.25)
    node(assets, "material", name="coffee", rgba=(0.24, 0.13, 0.06, 1), specular=0.6, shininess=0.8, reflectance=0.08)
    node(assets, "material", name="cabinet", rgba=(0.93, 0.92, 0.89, 1), specular=0.1)
    table_z = config["table_z"]
    floor_z = config["floor_z"]  # the Marvin stand's platform rests on the floor (ARM_RIG: base_z - 0.1)
    node(world, "geom", name="floor", type="plane", size=(3, 3, 0.1), pos=(0, 0, floor_z), rgba=(0.55, 0.52, 0.48, 1),
         **MATTE)
    wt = config["worktop"]
    node(world, "geom", name="worktop", type="box", size=(wt["half"][0], wt["half"][1], 0.018),
         pos=(wt["center"][0], wt["center"][1], table_z - 0.018), material="stone_material", **MATTE)
    for x in (wt["center"][0] - wt["half"][0] + 0.04, wt["center"][0] + wt["half"][0] - 0.04):
        for y in (-0.42, 0.42):
            node(world, "geom", name=f"table_leg_{x}_{y}", type="box", size=(0.02, 0.02, (table_z - 0.036 - floor_z) / 2),
                 pos=(x, y, (table_z - 0.036 + floor_z) / 2), rgba=(0.30, 0.27, 0.24, 1), contype=0, conaffinity=0,
                 group=1)
    # Backsplash / cabinet set dressing (visual only, far from the workspace).
    node(world, "geom", name="backsplash", type="box", size=(1.4, 0.01, 0.40), pos=(0.30, 0.47, table_z + 0.40),
         material="cabinet", contype=0, conaffinity=0, group=1)
    add_cup(world, assets, config)
    add_spoon(world, assets, config)
    node(world, "light", name="key", pos=(0.2, -0.6, 1.9), dir=(0.25, 0.5, -1), diffuse=(0.75, 0.73, 0.68),
         castshadow="true")
    node(world, "light", name="fill", pos=(1.0, 0.6, 1.6), dir=(-0.4, -0.4, -1), diffuse=(0.35, 0.36, 0.38),
         castshadow="false")
    # Camera placements follow the approved T11 film (wide and near views from the front-right of the cup).
    for name, pos, target, fovy in (
        ("overview", (0.98, -0.62, 1.24), (0.46, 0.0, 0.94), 40),
        ("closeup", (0.83, -0.48, 1.15), (0.49, 0.015, 0.86), 36),
        ("top", (0.48, 0.015, 1.45), None, 30),
    ):
        if target is None:
            xyaxes = (1, 0, 0, 0, 1, 0)
        else:
            f = np.subtract(target, pos) / np.linalg.norm(np.subtract(target, pos))
            x = np.cross(f, (0, 0, 1))
            x /= np.linalg.norm(x)
            xyaxes = (*np.round(x, 5), *np.round(np.cross(x, f), 5))
        node(world, "camera", name=name, pos=pos, xyaxes=xyaxes, fovy=fovy)
    v = node(root, "visual")
    node(v, "global", offwidth=1280, offheight=720)
    node(v, "quality", shadowsize=4096, offsamples=4)
    node(v, "headlight", ambient=(0.30, 0.30, 0.30), diffuse=(0.45, 0.45, 0.45), specular=(0.1, 0.1, 0.1))
    xml = ET.tostring(root, encoding="unicode")
    return mujoco.MjModel.from_xml_string(xml), xml
