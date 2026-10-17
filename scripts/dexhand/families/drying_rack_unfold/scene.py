"""T20 folding sweater dryer (legacy OXO construction) on a kitchen counter with one dexterous hand.

The rack geometry, materials, masses, inertias, hinge ranges, damping, friction losses and contact parameters are
ported unchanged from the approved T20 source (``assets/source/rack.py``): two 0.33 x 0.65 m frame halves joined by
one passive pole hinge (range [0, pi], folded at pi) and four passive offset legs (range [0, 100 deg]). The rack is a
free body; it starts in the source storage pose (fully folded, legs folded, underside up, lower corner housings on
the counter). Only the hand and its six-axis wrist stage are actuated.
"""

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

# ---- source rack constants (assets/source/rack.py, unchanged) ----
WIDTH = 26 * 0.0254
HEIGHT = 4.5 * 0.0254
RADIUS = 0.0045
HALF = WIDTH / 2 - RADIUS
HINGE_OFFSET = 0.012
LEG_LENGTH = HEIGHT - 0.016
LEG_X = 0.257
LEG_Y = 0.255
LEG_STOP = float(np.deg2rad(100))
# Leg pivot: source dry friction 0.003 N m kept; viscous damping raised from the source's 0.003 to 0.03 N m s/rad (a
# plastic pivot that does not flutter when the frame is jolted). Documented modelling choice.
LEG_FRICTIONLOSS = 0.003
LEG_DAMPING = 0.03
# Pole joint (fold hinge): source damping 0.001 N m s/rad and dry friction 0.0005 N m, unchanged.
FOLD_FRICTIONLOSS = 0.0005
PANELS = ("fixed", "moving")
SIDES = ("l", "r")
LEG_JOINTS = tuple(f"{p}_leg_{s}_hinge" for p in PANELS for s in SIDES)
FOOT_GEOMS = tuple(f"{p}_leg_{s}_foot" for p in PANELS for s in SIDES)


def fmt(v):
    if isinstance(v, (list, tuple, np.ndarray)):
        return " ".join(f"{float(x):.17g}" for x in v)
    return str(v)


def node(parent, tag, **values):
    return ET.SubElement(parent, tag, {k: fmt(v) for k, v in values.items()})


def quat_wxyz(matrix):
    q = np.empty(4)
    mujoco.mju_mat2Quat(q, np.asarray(matrix, dtype=float).ravel())
    return q


def rot_z(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def rot_y(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def rack_materials(asset):
    node(asset, "material", name="rack_polymer", rgba=(0.88, 0.88, 0.83, 1), specular=0.22, shininess=0.25)
    node(asset, "material", name="rack_tube", rgba=(0.72, 0.76, 0.77, 1), specular=0.7, shininess=0.65)
    node(asset, "material", name="rack_mesh", rgba=(0.74, 0.76, 0.70, 1), specular=0.05)
    node(asset, "material", name="rack_foot", rgba=(0.36, 0.38, 0.34, 1), specular=0.08)


def rgeom(parent, name, **kw):
    """Collision geometry with the source contact law (mass lives in explicit inertials)."""
    return node(
        parent,
        "geom",
        name=name,
        mass=0,
        friction=(0.65, 0.002, 0.0001),
        solref=(0.006, 1),
        solimp=(0.95, 0.99, 0.0005),
        condim=4,
        **kw,
    )


def panel(body, side):
    sign = -1 if side == "fixed" else 1
    z = 0 if side == "fixed" else HINGE_OFFSET
    node(body, "inertial", pos=(sign * HALF / 2, 0, z), mass=0.205, diaginertia=(0.0074, 0.0019, 0.0093))
    for y, label in [(HALF, "l"), (-HALF, "r")]:
        rgeom(body, f"{side}_rim_{label}", type="capsule", size=(RADIUS,),
              fromto=(sign * 0.017, y, z, sign * HALF, y, z), material="rack_tube")
        rgeom(body, f"{side}_hinge_{label}", type="capsule", size=(0.010,),
              fromto=(0, y - 0.012, z, 0, y + 0.012, z), material="rack_polymer")
    rgeom(body, f"{side}_end_pole", type="capsule", size=(RADIUS,),
          fromto=(sign * HALF, -HALF, z, sign * HALF, HALF, z), material="rack_tube")
    for y, label in [(HALF, "l"), (-HALF, "r")]:
        rgeom(body, f"{side}_corner_{label}", type="box", size=(0.013, 0.017, 0.012),
              pos=(sign * (HALF - 0.004), y - np.sign(y) * 0.007, z), material="rack_polymer")
        node(body, "geom", name=f"{side}_assembly_button_{label}", type="sphere", size=".0025",
             pos=(sign * (HALF - 0.004), y - np.sign(y) * 0.007, z + 0.013), material="rack_foot",
             mass=0, contype=0, conaffinity=0, group=1)
    # Woven net: visual only (declared reduced cloth treatment; no laundry is simulated).
    for i, y in enumerate(np.linspace(-HALF + 0.016, HALF - 0.016, 35)):
        node(body, "geom", name=f"{side}_net_x_{i}", type="capsule", size=".00045",
             fromto=(sign * 0.008, y, z - 0.002, sign * (HALF - 0.008), y, z - 0.002),
             material="rack_mesh", mass=0, contype=0, conaffinity=0, group=1)
    for i, x in enumerate(sign * np.linspace(0.008, HALF - 0.008, 18)):
        node(body, "geom", name=f"{side}_net_y_{i}", type="capsule", size=".00045",
             fromto=(x, -HALF + 0.008, z - 0.002, x, HALF - 0.008, z - 0.002),
             material="rack_mesh", mass=0, contype=0, conaffinity=0, group=1)
    for y, label in [(LEG_Y, "l"), (-LEG_Y, "r")]:
        leg = node(body, "body", name=f"{side}_leg_{label}", pos=(sign * LEG_X, y, z))
        inward = -sign
        node(leg, "joint", name=f"{side}_leg_{label}_hinge", type="hinge", axis=(0, inward, 0), limited="true",
             range=(0, LEG_STOP), damping=LEG_DAMPING, frictionloss=LEG_FRICTIONLOSS, solreflimit=(0.004, 1),
             solimplimit=(0.99, 0.999, 0.0001))
        node(leg, "inertial", pos=(inward * LEG_LENGTH / 2, 0, 0), mass=0.025,
             diaginertia=(0.000003, 0.000021, 0.000021))
        rgeom(leg, f"{side}_leg_{label}_tube", type="capsule", size=(0.004,),
              fromto=(0, 0, 0, inward * (LEG_LENGTH - 0.010), 0, 0), material="rack_tube")
        rgeom(leg, f"{side}_leg_{label}_foot", type="sphere", size=(0.006,),
              pos=(inward * (LEG_LENGTH - 0.004), 0, 0), material="rack_foot")
        rgeom(body, f"{side}_leg_{label}_mount", type="box", size=(0.011, 0.008, 0.009),
              pos=(sign * LEG_X, y, z), material="rack_polymer")


def make_rack(world, centre, rotation):
    """Source ``make_rack`` + the source storage initialisation (moving half Ry(pi), fold ref pi => q0 = pi)."""
    root = node(world, "body", name="rack", pos=centre, quat=quat_wxyz(rotation))
    node(root, "freejoint", name="rack_free")
    panel(root, "fixed")
    child = node(root, "body", name="moving_panel", pos=(0, 0, -HINGE_OFFSET), quat=(0, 0, 1, 0))
    node(child, "joint", name="fold_hinge", type="hinge", axis=(0, 1, 0), limited="true", range=(0, np.pi),
         ref=np.pi, damping=0.001, frictionloss=FOLD_FRICTIONLOSS, solreflimit=(0.004, 1),
         solimplimit=(0.99, 0.999, 0.0001))
    panel(child, "moving")
    return root


def build(config, asset_dir=None, hand="sharpa"):
    """Compose the frozen scene with the selected genuine hand on the six-axis wrist stage."""
    hand_id = hands.canonical(hand)
    folder = Path(
        asset_dir
        or os.environ.get("DEXHAND_ASSET_DIR")
        or Path(__file__).resolve().parents[4] / "images/dexhand/assets/hand"
    )
    root = ET.parse(folder / "right_hand.xml").getroot()
    root.set("model", hands.info(hand_id)["model"] + " drying rack unfold")
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
    world.remove(hand_body)
    stage = config["wrist_stage"]
    wrist = node(world, "body", name="wrist_stage", pos=stage["origin"])
    node(wrist, "inertial", pos=(0, 0, 0), mass=0.01, diaginertia=(0.00001,) * 3)
    # Palm down at zero wrist angles: fingers +x, palm normal -z, thumb +y (the hamburger mount turned by Rx(pi)).
    base = np.empty(9)
    mujoco.mju_quat2Mat(base, np.array([0, 0.7071067811865476, 0, 0.7071067811865476]))
    hand_body.set("quat", fmt(quat_wxyz(np.diag([1.0, -1.0, -1.0]) @ base.reshape(3, 3))))
    wrist.append(hand_body)
    ranges = stage["ranges"]
    for i, name in enumerate(("x", "y", "z", "rx", "ry", "rz")):
        axis = [int(i % 3 == j) for j in range(3)]
        wrist.insert(
            i,
            ET.Element(
                "joint",
                name="wrist_" + name,
                type="slide" if i < 3 else "hinge",
                axis=" ".join(map(str, axis)),
                range=fmt(ranges[name]),
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
        sibling = folder.parent / "wuji_v2_2"
        hands.replace_wave_hands(root, hand_id, folder=sibling if (sibling / "mjcf/right.xml").is_file() else None)

    rack_materials(assets)
    node(assets, "texture", name="counter_grain", type="2d", builtin="flat", width=64, height=64,
         rgb1=(0.47, 0.33, 0.21), rgb2=(0.44, 0.31, 0.20), mark="random", random=0.08, markrgb=(0.40, 0.28, 0.18))
    node(assets, "material", name="counter_oak", texture="counter_grain", texrepeat=(4, 4), rgba=(1, 1, 1, 1),
         specular=0.1)
    node(assets, "material", name="counter_base", rgba=(0.32, 0.39, 0.35, 1), specular=0.1)
    node(assets, "texture", name="studio_sky", type="skybox", builtin="gradient", width=256, height=256,
         rgb1=(0.80, 0.81, 0.79), rgb2=(0.93, 0.92, 0.89))
    tz = config["table_z"]
    c = config["counter"]
    node(world, "geom", name="floor", type="plane", pos=(0, 0, 0), size=(3, 3, 0.05), rgba=(0.67, 0.68, 0.64, 1))
    node(world, "geom", name="counter_top", type="box", pos=(c["center"][0], c["center"][1], tz - 0.025),
         size=(c["half"][0], c["half"][1], 0.025), material="counter_oak", friction=(0.7, 0.002, 0.0001),
         solref=(0.006, 1), condim=4)
    node(world, "geom", name="counter_cabinet", type="box", pos=(c["center"][0], c["center"][1], (tz - 0.05) / 2),
         size=(c["half"][0] - 0.04, c["half"][1] - 0.04, (tz - 0.05) / 2), material="counter_base")
    rotation = rot_z(-np.pi / 2) @ rot_y(np.pi)  # source storage pose: underside up
    make_rack(world, config["rack_pos"], rotation)
    node(world, "light", pos=(0.2, -0.7, 2.2), dir=(0.3, 0.4, -1), diffuse=(0.8, 0.8, 0.77))
    node(world, "light", pos=(1.2, 0.7, 1.8), dir=(-0.3, -0.4, -1), diffuse=(0.45, 0.45, 0.45), castshadow="false")
    for cam in config["cameras"]:
        pos, target = np.asarray(cam["pos"], float), np.asarray(cam["target"], float)
        forward = (target - pos) / np.linalg.norm(target - pos)
        right = np.cross(forward, (0, 0, 1))
        right /= np.linalg.norm(right)
        up = np.cross(right, forward)
        node(world, "camera", name=cam["name"], pos=pos, xyaxes=np.round(np.r_[right, up], 6), fovy=cam["fovy"])
    v = node(root, "visual")
    node(v, "global", offwidth=1280, offheight=720)
    node(v, "quality", shadowsize=4096, offsamples=4)
    node(v, "headlight", ambient=(0.32, 0.32, 0.32), diffuse=(0.5, 0.5, 0.5), specular=(0.12, 0.12, 0.12))
    xml = ET.tostring(root, encoding="unicode")
    return mujoco.MjModel.from_xml_string(xml), xml
