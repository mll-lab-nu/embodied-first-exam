"""T21 picture-hanging scene: a free 52 x 52 x 6 cm framed print with two passive hinged D-rings, two installed
brass wall hooks, a console and a Tianji Marvin dual-arm robot with a dexterous hand on each arm.

Scene geometry, masses and materials follow the accepted T21 source scene
(``scripts/scene_expansion/repairs/picture_sharpa/meta_delivery_trajectory_r1/hardware.py`` and ``scene.py``).
The only physical object that moves is the frame (with its two D-rings on passive hinges); hooks, wall and
console are static. Nothing is attached to a hand.

Robot (wave 3): the shared ``arm_rig.mount_marvin`` stand with two 7-DoF Marvin arms (position servos) stands in
front of the console, facing the wall; the genuine Sharpa Wave right hand is on the right flange and its declared
y-mirror on the left flange (``hand="wuji"``: the genuine right/left Wuji Hand 2.2). The flange mount bodies keep
the old stage names ``l_wrist_stage`` / ``r_wrist_stage`` so that every hand geometry lies below them.
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

# ------------------------------------------------------------------------------------------------ source geometry
WIDTH, HEIGHT, DEPTH = 0.52, 0.52, 0.060
RAIL = 0.010
RING_Y = (WIDTH - RAIL) / 2
RING_PIVOT_Z = 0.478
RING_BACK = DEPTH / 2 + 0.003
WALL_X = 0.74
HOOK_Z = 1.38
START = np.array([0.50, 0.0, 0.72])
FRAME_MASS = 2.0
SIDES = ("l", "r")
SIDE_SIGN = {"l": 1.0, "r": -1.0}  # +y is the viewer's left when facing the wall (+x)

def vec(value):
    return " ".join(f"{float(v):.17g}" for v in np.ravel(value))


def node(parent, tag, **attributes):
    return ET.SubElement(
        parent,
        tag,
        {k: vec(v) if isinstance(v, (list, tuple, np.ndarray)) else str(v) for k, v in attributes.items()},
    )


def mat2quat(matrix):
    quat = np.empty(4)
    mujoco.mju_mat2Quat(quat, np.asarray(matrix, dtype=float).ravel())
    return quat


# ------------------------------------------------------------------------------------------------ assets
class AssetError(RuntimeError):
    """A bundled asset is missing or differs from assets/manifest.json."""


def asset_path(name: str) -> Path:
    manifest = json.loads((HERE / "assets/manifest.json").read_text())
    record = manifest["files"][name]
    path = HERE / "assets" / name
    raw = path.read_bytes()
    if len(raw) != record["bytes"] or hashlib.sha256(raw).hexdigest() != record["sha256"]:
        raise AssetError(f"asset integrity failure: {name}")
    return path


def sharpa_folder(asset_dir=None) -> Path:
    candidates = [asset_dir, os.environ.get("DEXHAND_ASSET_DIR"), "/opt/dexhand/hand"]
    if len(HERE.parents) > 3:  # repository checkout: scripts/dexhand/families/<family>/
        candidates += [HERE.parents[3] / "images/dexhand/assets/hand"]
    for candidate in candidates:
        if candidate and (Path(candidate) / "right_hand.xml").is_file():
            return Path(candidate)
    raise AssetError("Sharpa Wave assets not found (set DEXHAND_ASSET_DIR or use the eai-dexhand image)")


# ------------------------------------------------------------------------------------------------ objects
def materials(asset):
    node(asset, "material", name="frame_white", rgba=(0.91, 0.89, 0.84, 1), specular=0.2, shininess=0.15)
    node(asset, "material", name="brass", rgba=(0.71, 0.51, 0.19, 1), specular=0.8, shininess=0.7)
    node(asset, "material", name="backboard", rgba=(0.32, 0.25, 0.19, 1))
    node(asset, "material", name="glass", rgba=(0.77, 0.85, 0.86, 0.12), specular=0.8, shininess=0.8)
    node(asset, "texture", name="print_texture", type="2d", file=str(asset_path("water-lilies.png")))
    node(asset, "material", name="print", texture="print_texture", texuniform="false", texrepeat=(1, 1))
    node(asset, "material", name="wall_paint", rgba=(0.73, 0.77, 0.72, 1))
    node(asset, "material", name="console_oak", rgba=(0.42, 0.29, 0.19, 1))
    node(asset, "texture", name="sky", type="skybox", builtin="gradient", width=256, height=256,
         rgb1=(0.84, 0.85, 0.81), rgb2=(0.94, 0.92, 0.87))
    w, h = (WIDTH - 2 * RAIL) / 2, (HEIGHT - 2 * RAIL) / 2
    # A thin textured plane (no collision) with explicit UVs carries the print.
    node(asset, "mesh", name="print_plane",
         vertex=(0, -w, -h, 0, w, -h, 0, w, h, 0, -w, h, 0.00001, -w, -h),
         face=(0, 2, 1, 0, 3, 2, 0, 1, 4), texcoord=(0, 0, 1, 0, 1, 1, 0, 1, 0, 0))


FRAME_CONTACT = dict(friction=(1, 0.005, 0.0001), solref=(0.006, 1), solimp=(0.95, 0.99, 0.0005), condim=4)


def make_picture(world, pos=START):
    """The free framed print (source hardware.make_picture): four rails, backboard, glazing, print, clips, D-rings."""
    body = node(world, "body", name="picture", pos=pos)
    node(body, "freejoint", name="picture_free")
    node(body, "inertial", mass=FRAME_MASS, pos=(0, 0, HEIGHT / 2), diaginertia=(0.092, 0.047, 0.047))
    common = dict(FRAME_CONTACT, mass=0)
    for side in SIDES:
        y = SIDE_SIGN[side] * RING_Y
        node(body, "geom", name=f"frame_{side}_rail", type="box", pos=(0, y, HEIGHT / 2),
             size=(DEPTH / 2, RAIL / 2, HEIGHT / 2), material="frame_white", **common)
    for name, z in (("bottom", RAIL / 2), ("top", HEIGHT - RAIL / 2)):
        node(body, "geom", name=f"frame_{name}_rail", type="box", pos=(0, 0, z),
             size=(DEPTH / 2, (WIDTH - 2 * RAIL) / 2, RAIL / 2), material="frame_white", **common)
    node(body, "geom", name="picture_backboard", type="box", pos=(0.028, 0, HEIGHT / 2),
         size=(0.002, (WIDTH - 2 * RAIL) / 2, (HEIGHT - 2 * RAIL) / 2), material="backboard", **common)
    node(body, "geom", name="picture_print", type="mesh", mesh="print_plane", material="print",
         pos=(0.0258, 0, HEIGHT / 2), contype=0, conaffinity=0, mass=0, group=2)
    node(body, "geom", name="picture_glazing", type="box", pos=(0.024, 0, HEIGHT / 2),
         size=(0.001, (WIDTH - 2 * RAIL) / 2, (HEIGHT - 2 * RAIL) / 2), material="glass", **common)
    for side in SIDES:
        y = SIDE_SIGN[side] * RING_Y
        node(body, "geom", name=f"{side}_ring_clip", type="box", pos=(DEPTH / 2 + 0.0005, y, RING_PIVOT_Z - 0.007),
             size=(0.0005, 0.010, 0.0075), material="brass", **common)
        for k, yy in enumerate((-0.003, 0.003)):
            node(body, "geom", name=f"{side}_ring_screw_{k}", type="cylinder",
                 pos=(DEPTH / 2 + 0.0015, y + yy, RING_PIVOT_Z - 0.008), size=(0.0025, 0.001),
                 euler=(0, np.pi / 2, 0), rgba=(0.16, 0.17, 0.17, 1), **common)
        ring = node(body, "body", name=f"{side}_d_ring", pos=(RING_BACK, y, RING_PIVOT_Z))
        # Passive hinge (source: damping 0.0004 N m s/rad, friction 0.0015 N m, +-1 rad). The ring is a child of the
        # frame body, so MuJoCo filters ring-frame contacts; the lower stop at 0 stands in for the frame back that a
        # real D-ring cannot swing through, and a weak return spring keeps an unloaded ring upright.
        node(ring, "joint", name=f"{side}_ring_pivot", type="hinge", axis=(0, 1, 0), range=(0.0, 1.0),
             limited="true", damping=0.0004, frictionloss=0.0015, solreflimit=(0.004, 1), stiffness=0.005,
             springref=0.0)
        node(ring, "inertial", pos=(0, 0, 0.008), mass=0.006, diaginertia=(5e-7, 4e-7, 2e-7))
        # D outline: straight pivot bar, two short sides and an upper semicircle (2 mm brass wire).
        vertices = [(0, -0.009, 0), (0, 0.009, 0), (0, 0.009, 0.011)]
        vertices += [(0, 0.009 * np.cos(a), 0.011 + 0.009 * np.sin(a)) for a in np.linspace(0, np.pi, 17)[1:]]
        vertices += [(0, -0.009, 0)]
        for i, (a, b) in enumerate(zip(vertices, vertices[1:])):
            node(ring, "geom", name=f"{side}_ring_wire_{i}", type="capsule", fromto=(*a, *b), size=(0.001,),
                 material="brass", **common)
    for side in SIDES:
        y = SIDE_SIGN[side] * RING_Y
        node(body, "geom", name=f"{side}_felt_bumper", type="cylinder", pos=(DEPTH / 2 + 0.0015, y, 0.032),
             size=(0.006, 0.0015), euler=(0, np.pi / 2, 0), rgba=(0.17, 0.16, 0.15, 1), **common)
    return body


def make_hooks(world):
    """Two permanently installed bent-sheet brass hooks (source hardware.make_hooks): back strap, load saddle,
    upturned lip and nail."""
    for side in SIDES:
        y = SIDE_SIGN[side] * RING_Y
        hook = node(world, "body", name=f"{side}_wall_hook", pos=(WALL_X, y, HOOK_Z))
        common = dict(material="brass", friction=(0.35, 0.005, 0.0001), solref=(0.004, 1),
                      solimp=(0.95, 0.99, 0.0005))
        node(hook, "geom", name=f"{side}_hook_back", type="box", pos=(-0.0005, 0, 0.012),
             size=(0.0005, 0.006, 0.012), **common)
        node(hook, "geom", name=f"{side}_hook_saddle", type="box", pos=(-0.006, 0, 0),
             size=(0.006, 0.003, 0.0005), **common)
        node(hook, "geom", name=f"{side}_hook_lip", type="capsule", fromto=(-0.012, 0, 0.001, -0.012, 0, 0.011),
             size=(0.001,), **common)
        node(hook, "geom", name=f"{side}_hook_nail", type="capsule", fromto=(-0.002, 0, 0.023, 0.008, 0, 0.017),
             size=(0.0011,), rgba=(0.15, 0.18, 0.21, 1), friction=(0.35, 0.005, 0.0001))


# ------------------------------------------------------------------------------------------------ build
HAND_MOUNTS = {"left": "l_wrist_stage", "right": "r_wrist_stage"}


def _hand_tweaks(root, hand_id):
    """The wave-2 Sharpa tweaks of this family: fingertip friction 1.5 and dissipative finger velocity feedback."""
    if hand_id != "sharpa":
        return
    for item in root.iter("geom"):
        if "fingertip_collision" in item.get("name", ""):
            item.set("friction", "1.5 0.005 0.0001")
    for item in root.iter("general"):
        if "biasprm" in item.attrib:
            values = _numbers(item.attrib["biasprm"])
            if len(values) >= 3:
                values[2] = -abs(values[2])
                item.set("biasprm", vec(values))


def _numbers(text):
    return np.array([float(x) for x in text.split()])


def build(config, hand="sharpa", asset_dir=None):
    """Compose the frozen scene with the Marvin robot and the selected genuine hands; returns (model, xml)."""
    hand_id = hands.canonical(hand)
    folder = sharpa_folder(asset_dir)
    root = arm_rig.sharpa_root(folder)
    root.set("model", f"T21 picture hanging / Marvin + {hands.info(hand_id)['model']}")
    root.find("compiler").set("autolimits", "true")
    option = root.find("option")
    for key, value in (("timestep", config["physics_dt"]), ("integrator", "implicitfast"), ("cone", "elliptic"),
                       ("impratio", 10), ("iterations", 60), ("gravity", "0 0 -9.81")):
        option.set(key, str(value))
    visual = node(root, "visual")
    node(visual, "global", offwidth=1280, offheight=720)
    node(visual, "quality", shadowsize=4096, offsamples=4)
    node(visual, "headlight", ambient=(0.3, 0.3, 0.3), diffuse=(0.55, 0.55, 0.55), specular=(0.1, 0.1, 0.1))
    asset = root.find("asset")
    world = root.find("worldbody")
    materials(asset)
    node(world, "geom", name="floor", type="plane", size=(4, 4, 0.05), pos=(0, 0, 0), rgba=(0.47, 0.45, 0.41, 1))
    node(world, "geom", name="wall", type="box", size=(0.025, 2.5, 1.25), pos=(WALL_X + 0.025, 0, 1.25),
         material="wall_paint")
    node(world, "geom", name="console_top", type="box", size=(0.15, 0.19, 0.015), pos=(0.50, 0, START[2] - 0.015),
         material="console_oak", friction=(0.8, 0.005, 0.0001))
    # Wave 3: the console stands on its two rear legs only (a wall-side console), moved 15 mm back (x = 0.615 m) for
    # clearance. The dual-arm stand's 0.79 m base
    # plate occupies the floor under the console's front half; the source's front legs (x = 0.40 m) would pass
    # through it. Top, height and the frame's start are unchanged; the legs are decor (never touched).
    for j, y in enumerate((-0.15, 0.15)):
        node(world, "geom", name=f"console_leg_1{j}", type="box", size=(0.025, 0.025, 0.345), pos=(0.615, y, 0.345),
             material="console_oak")
    make_picture(world)
    make_hooks(world)
    node(world, "light", pos=(0.2, -0.6, 2.0), dir=(0, 0.3, -1), diffuse=(0.8, 0.8, 0.8), castshadow="true")
    node(world, "light", pos=(-0.2, 0.7, 1.6), dir=(1, -0.3, -0.4), diffuse=(0.5, 0.5, 0.5), castshadow="false")
    for name, cam in config["cameras"].items():
        node(world, "camera", name=name, pos=cam["pos"], xyaxes=cam["xyaxes"], fovy=cam["fovy"])
    robot = config["robot_base"]
    # The stand is raised on a plinth exactly under its base plate (|x|, |y| <= 0.393 m about the base origin): the
    # plinth top is the stand's floor, base_z - 0.1 (arm_rig convention; the feet reach 0.099 m below the origin).
    # Visual only: the static stand never collides with static geometry.
    plinth = robot["pos"][2] - 0.1
    if plinth > 0:
        node(world, "geom", name="robot_plinth", type="box", size=(0.393, 0.393, plinth / 2),
             pos=(robot["pos"][0], robot["pos"][1], plinth / 2), rgba=(0.30, 0.31, 0.32, 1), contype=0, conaffinity=0)
    arm_rig.mount_marvin(root, base_pos=robot["pos"], base_yaw=robot["yaw"], hand=hand_id, active=("left", "right"),
                         sharpa_folder=folder, mount_names=HAND_MOUNTS)
    _hand_tweaks(root, hand_id)
    xml = ET.tostring(root, encoding="unicode")
    return mujoco.MjModel.from_xml_string(xml), xml
