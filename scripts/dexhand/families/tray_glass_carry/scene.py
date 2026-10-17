"""T48 'carry a tray with two filled glasses' as a physical MuJoCo scene with two hands on two wrist stages.

Objects come from the accepted scene-expansion scene T48 (frozen in ``assets/``): the original perforated oval
serving tray (0.39 x 0.52 m, 1.0 kg, open handle slots at both ends of the long axis) and two 150 mL glasses
(0.275 kg each incl. water) on the source counter; two 0.40 x 0.80 m stone counters with a 30 mm gap and a fixed
stainless bottle obstacle rebuilt from the scene's builder (``trajectory_r1/build.py``). Liquid is not simulated.

Rig: the left and right Sharpa Wave hands of the accepted ``sweep_dustpan`` rig (left = mirrored Wave), each on its
own six-axis wrist stage (slides x/y/z in metres, then hinges rx/ry/rz in radians). Wuji Hand 2.2 is swapped in with
``hands.replace_wave_hands`` under the unchanged stages. Actuator order: left stage (6), right stage (6), left hand,
right hand.
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

STAGE_AXES = ("x", "y", "z", "rx", "ry", "rz")
SIDES = ("l", "r")
# Hand frame (Wave): fingers +Z, palm normal +X. Mount: fingers point down (-Z world); the palm faces the tray centre
# (left hand at the +y end faces -y, right hand at the -y end faces +y). Columns = world images of hand X, Y, Z.
MOUNT = {
    "l": np.array([[0.0, -1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, -1.0]]),
    "r": np.array([[0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, -1.0]]),
}


def _fmt(values) -> str:
    if isinstance(values, (list, tuple, np.ndarray)):
        return " ".join(f"{float(v):.10g}" for v in np.ravel(values))
    return str(values)


def node(parent, tag, **attributes):
    return ET.SubElement(parent, tag, {k: _fmt(v) for k, v in attributes.items()})


def mat_quat(matrix) -> np.ndarray:
    q = np.zeros(4)
    mujoco.mju_mat2Quat(q, np.asarray(matrix, dtype=float).ravel())
    return q


def lathe(profile, n=96, flutes=False):
    """Surface of revolution (same construction as the T48 scene builder); returns (vertices, faces)."""
    vertices, faces = [], []
    for k, (r, z) in enumerate(profile):
        for j in range(n):
            a = 2 * np.pi * j / n
            rr = r + (0.00016 * np.cos(48 * a) if flutes and k in (1, 2, 3) else 0.0)
            vertices.append([rr * np.cos(a), rr * np.sin(a), z])
    for k in range(len(profile) - 1):
        for j in range(n):
            a, b = k * n + j, k * n + (j + 1) % n
            faces.extend([[a, b, b + n], [a, b + n, a + n]])
    return np.asarray(vertices), np.asarray(faces)


def _mesh(assets, name, vertices, faces):
    node(assets, "mesh", name=name, vertex=np.round(vertices, 7), face=faces)


def _verify_assets() -> dict:
    manifest = json.loads((HERE / "assets/manifest.json").read_text())
    for name, digest in manifest["files"].items():
        if hashlib.sha256((HERE / "assets" / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"frozen task asset changed: assets/{name}")
    return manifest


def water_top(volume=0.00015):
    """Height of a 150 mL water column in the glass (tapered profile of the T48 builder)."""
    slope = (0.034 - 0.027) / 0.092
    z = np.linspace(0, 0.092, 10000)
    vol = np.pi * (0.027**2 * z + 0.027 * slope * z**2 + slope**2 * z**3 / 3)
    h = float(np.interp(volume, vol, z))
    return 0.008 + h, 0.027 + slope * h


def build(config, hand="sharpa"):
    """Return ``(MjModel, xml)`` of the frozen scene with the selected genuine hands."""
    hand_id = hands.canonical(hand)
    _verify_assets()
    sharpa = hands.sharpa_dir()
    hand_xml = (HERE / "assets/sharpa_bimanual_hands.xml").read_text().replace("${DEXHAND_ASSET_DIR}", str(sharpa))
    hand_root = ET.fromstring(hand_xml)
    src = ET.parse(HERE / "assets/t48_tray_glasses.xml").getroot()

    root = ET.Element("mujoco", model=f"tray_glass_carry ({hands.info(hand_id)['model']})")
    node(root, "compiler", angle="radian", autolimits="true")
    option = node(
        root,
        "option",
        timestep=config["physics_dt"],
        gravity="0 0 -9.81",
        integrator="implicitfast",
        cone="elliptic",
        impratio=config.get("impratio", 1),
        iterations=100,
        ls_iterations=50,
    )
    node(option, "flag", multiccd="enable")
    node(root, "size", memory="400M")
    visual = node(root, "visual")
    node(visual, "global", offwidth=1280, offheight=720)
    node(visual, "quality", shadowsize=4096, offsamples=4)
    node(visual, "headlight", ambient=(0.30, 0.30, 0.30), diffuse=(0.45, 0.45, 0.45), specular=(0.1, 0.1, 0.1))
    node(visual, "map", znear=0.01)
    default = node(root, "default")
    default.extend(list(hand_root.find("default")))
    assets = node(root, "asset")
    assets.extend(list(hand_root.find("asset")))
    assets.extend(list(src.find("asset")))
    node(assets, "texture", name="sky", type="skybox", builtin="gradient", width=256, height=256,
         rgb1=(0.80, 0.82, 0.82), rgb2=(0.30, 0.33, 0.35))
    node(assets, "texture", name="stone_tex", type="2d", builtin="flat", width=256, height=256,
         rgb1=(0.57, 0.52, 0.43), rgb2=(0.53, 0.48, 0.40), mark="random", random=0.04, markrgb=(0.62, 0.57, 0.48))
    node(assets, "material", name="stone", texture="stone_tex", texrepeat=(3, 3), specular=0.25, shininess=0.25)
    node(assets, "texture", name="floor_tex", type="2d", builtin="checker", width=512, height=512,
         rgb1=(0.43, 0.47, 0.46), rgb2=(0.41, 0.45, 0.44))
    node(assets, "material", name="floor", texture="floor_tex", texrepeat=(10, 10), reflectance=0.03)
    node(assets, "material", name="cabinet", rgba=(0.11, 0.16, 0.15, 1), specular=0.3)
    node(assets, "material", name="steel", rgba=(0.62, 0.67, 0.69, 1), specular=0.9, shininess=0.8, reflectance=0.25)
    node(assets, "material", name="tray_paint", rgba=(0.86, 0.89, 0.86, 1), specular=0.45, shininess=0.6)
    node(assets, "material", name="glass", rgba=(0.88, 0.95, 0.97, 0.32), specular=0.9, shininess=0.95)
    node(assets, "material", name="water", rgba=(0.38, 0.70, 0.82, 0.78), specular=0.6, shininess=0.8)
    bv, bf = lathe([(0, 0), (0.028, 0), (0.028, 0.23), (0.018, 0.25), (0.018, 0.28), (0, 0.28)], 64)
    _mesh(assets, "bottle_shell", bv, bf)
    gv, gf = lathe([(0, 0), (0.029, 0), (0.030, 0.008), (0.037, 0.100), (0.034, 0.100), (0.027, 0.008), (0, 0.008)],
                   96, flutes=True)
    _mesh(assets, "glass_shell", gv, gf)
    top, radius = water_top()
    wv, wf = lathe([(0, 0.008), (0.0268, 0.008), (radius - 0.0002, top), (0, top)], 96)
    _mesh(assets, "water_volume", wv, wf)

    world = node(root, "worldbody")
    node(world, "light", name="key", pos=(-0.2, -0.9, 2.3), dir=(0.3, 0.5, -1), diffuse=(0.75, 0.70, 0.64),
         castshadow="true")
    node(world, "light", name="fill", pos=(1.3, 0.8, 2.4), dir=(-0.3, -0.3, -1), diffuse=(0.45, 0.50, 0.56),
         castshadow="false")
    node(world, "geom", name="floor", type="plane", size=(3, 3, 0.1), material="floor")
    friction = config["counter_friction"]
    top_z = config["table_top_z"]
    for i, cx in enumerate(config["counter_x"]):
        node(world, "geom", name=f"counter_{i}", type="box", size=(0.2, 0.4, 0.025), pos=(cx, 0, top_z - 0.025),
             material="stone", friction=(friction, 0.005, 0.0001), solref=(0.004, 1), condim=4)
        for j, (dx, dy) in enumerate(((-0.17, -0.37), (-0.17, 0.37), (0.17, -0.37), (0.17, 0.37))):
            node(world, "geom", name=f"counter_{i}_leg_{j}", type="box", size=(0.0175, 0.0175, (top_z - 0.05) / 2),
                 pos=(cx + dx, dy, (top_z - 0.05) / 2), material="cabinet")
    bx, by = config["bottle_xy"]
    bottle = node(world, "body", name="bottle", pos=(bx, by, top_z))
    node(bottle, "geom", name="bottle_visual", type="mesh", mesh="bottle_shell", material="steel", contype=0,
         conaffinity=0, group=1)
    node(bottle, "geom", name="bottle_body", type="cylinder", size=(0.028, 0.115), pos=(0, 0, 0.115), rgba=(0, 0, 0, 0),
         group=3)
    node(bottle, "geom", name="bottle_neck", type="cylinder", size=(0.018, 0.025), pos=(0, 0, 0.255), rgba=(0, 0, 0, 0),
         group=3)

    # Tray and glasses: the frozen T48 bodies (meshes, masses, inertias, frictions) unchanged; only looks are added.
    for body in src.find("worldbody").findall("body"):
        name = body.get("name")
        if name == "tray":
            for g in body.findall("geom"):
                g.attrib.pop("rgba", None)
                g.set("material", "tray_paint")
                g.set("condim", "4")
        else:
            for g in body.findall("geom"):
                g.set("rgba", "0.7 0.85 0.9 0")
                g.set("group", "3")
                g.set("condim", "4")
            node(body, "geom", name=name + "_glass_visual", type="mesh", mesh="glass_shell", material="glass",
                 contype=0, conaffinity=0, group=1, mass=0)
            node(body, "geom", name=name + "_water_visual", type="mesh", mesh="water_volume", material="water",
                 contype=0, conaffinity=0, group=1, mass=0)
        world.append(body)

    # Two six-axis wrist stages, each carrying one hand (fingers down, palm toward the tray centre).
    actuator = node(root, "actuator")
    stage_gain = config["stage_gains"]
    palms = {b.get("name")[0]: b for b in hand_root.find("worldbody").findall("body")}
    for side in SIDES:
        base = config["stage_base"][side]
        stage = node(world, "body", name=f"{side}_wrist_stage", pos=base)
        node(stage, "inertial", pos=(0, 0, 0), mass=0.05, diaginertia=(1e-4, 1e-4, 1e-4))
        lo, hi = config["stage_range"]["lo"], config["stage_range"]["hi"]
        for i, axis_name in enumerate(STAGE_AXES):
            joint = f"{side}_wrist_{axis_name}"
            node(stage, "joint", name=joint, type="slide" if i < 3 else "hinge", axis=np.eye(3)[i % 3],
                 range=(lo[i], hi[i]), damping=stage_gain["damping"][i // 3], armature=stage_gain["armature"][i // 3])
            node(actuator, "position", name=f"{joint}_act", joint=joint, kp=stage_gain["kp"][i // 3],
                 kv=stage_gain["kv"][i // 3], inheritrange=1, forcerange=(-stage_gain["force"][i // 3],
                                                                         stage_gain["force"][i // 3]))
        palm = palms[side]
        palm.set("quat", _fmt(mat_quat(MOUNT[side])))
        stage.append(palm)
    for item in hand_root.find("actuator"):
        actuator.append(item)
    contact = node(root, "contact")
    contact.extend(list(hand_root.find("contact")))
    for g in root.iter("geom"):
        if "fingertip_collision" in (g.get("name") or ""):
            g.set("friction", _fmt(config["fingertip_friction"]))
    if hand_id != "sharpa":
        sibling = sharpa.parent / "wuji_v2_2"
        hands.replace_wave_hands(root, hand_id, folder=sibling if (sibling / "mjcf/right.xml").is_file() else None)

    cams = config["cameras"]
    for name, cam in cams.items():
        node(world, "camera", name=name, pos=cam["pos"], xyaxes=cam["xyaxes"], fovy=cam["fovy"])
    xml = ET.tostring(root, encoding="unicode")
    return mujoco.MjModel.from_xml_string(xml), xml


def look_at(position, target, up=(0, 0, 1)):
    """xyaxes for a camera at ``position`` looking at ``target``."""
    position, target = np.asarray(position, float), np.asarray(target, float)
    forward = target - position
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, up)
    right /= np.linalg.norm(right)
    upv = np.cross(right, forward)
    return [*np.round(right, 5), *np.round(upv, 5)]
