"""T27 ODDVAR stool dry frame with real dowel bores, composed with a dexterous hand on a six-axis wrist stage.

Geometry follows the T27 scene source (two pine side frames with hollow blind bores, four 0.26 m rails with 8 mm
dowels exposed 15 mm, an ordinary grey table, an uninstalled seat and eight screws). Every task part is a free rigid
body; bores are hollow convex contact sectors (no welds, no equality constraints, no object actuators).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation

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

PINE = (0.83, 0.72, 0.54, 1)
FRAMES = ("lower_frame", "upper_frame")
RAILS = ("brace", "rail_1", "rail_2", "rail_3")  # "brace" is the loose target rail of the source scene
WOOD_CONTACT = dict(friction=(0.45, 0.003, 0.0001), condim=4, solref=(0.01, 1), solimp=(0.9, 0.95, 0.001))
# Collision bits: 1 hand (vendor default), 2 bore walls <-> dowels, 4 table/floor <-> rails, 8 wood <-> wood,
# 16 table/floor <-> frame skids.
# Frame members collide with the hand and other wood; frames touch the table only through thin skids under each leg
# face (fewer redundant box/box contacts); rails and dowels collide with everything they can physically reach.
BITS = {
    "frame": dict(contype=8, conaffinity=9),
    "skid": dict(contype=16, conaffinity=16),
    "bore": dict(contype=2, conaffinity=2),
    "rail": dict(contype=12, conaffinity=13),
    "dowel": dict(contype=14, conaffinity=15),
    "support": dict(contype=20, conaffinity=21),
}


def verify_assets():
    """Check the copied runtime assets against assets/manifest.json (sha256 + size)."""
    manifest = json.loads((ASSETS / "manifest.json").read_text())
    for name, expected in manifest["files"].items():
        raw = (ASSETS / name).read_bytes()
        if len(raw) != expected["bytes"] or hashlib.sha256(raw).hexdigest() != expected["sha256"]:
            raise RuntimeError(f"stool asset integrity failure: {name}")
    return manifest


def text(values):
    return " ".join(f"{float(x):.17g}" for x in values)


def node(parent, tag, **attributes):
    return ET.SubElement(
        parent,
        tag,
        {k: text(v) if isinstance(v, (tuple, list, np.ndarray)) else str(v) for k, v in attributes.items()},
    )


def quat(matrix):
    return Rotation.from_matrix(matrix).as_quat()[[3, 0, 1, 2]]


def wood(parent, name, size, pos, bits="frame", **attributes):
    return node(parent, "geom", name=name, type="box", size=size, pos=pos, density=0, material="pine",
                **BITS[bits], **WOOD_CONTACT, **attributes)


def sector_vertices(r_in_low, r_in_high, r_out, a, b, z_low, z_high):
    vertices = []
    for z, r_in in ((z_low, r_in_low), (z_high, r_in_high)):
        for radius, angle in ((r_in, a), (r_out, a), (r_out, b), (r_in, b)):
            vertices.extend([radius * np.cos(angle), radius * np.sin(angle), z])
    return vertices


def hollow_leg(parent, assets, config, y, prefix):
    """A leg split around its two blind bores: solid blocks, shoulders, a blind bottom and convex wall sectors.

    Each bore is a straight section of the source radius (4.1 mm for the 4.0 mm dowel: 0.1 mm radial clearance, 24
    sectors, no entry chamfer, as in the T27 source); no convex geometry fills it.
    """
    length, width = config["leg_length"], config["leg_width"]
    half = width / 2
    cut = 0.009
    depth = config["bore_depth"]
    edges = [-length / 2]
    for x in config["rail_stations"]:
        edges += [x - cut, x + cut]
    edges += [length / 2]
    for i in range(0, len(edges) - 1, 2):
        a, b = edges[i : i + 2]
        wood(parent, f"{prefix}_solid_{i}", ((b - a) / 2, half, half), ((a + b) / 2, y, 0))
    n = int(config["bore_sectors"])
    # Circumscribed polygons keep at least the nominal radial clearance everywhere.
    r_bore = config["bore_radius"] / np.cos(np.pi / n)
    z_bottom, z_top = half - depth, half
    pieces = [(r_bore, r_bore, z_bottom, z_top)]  # one straight section from the blind bottom to the entry
    if config.get("chamfer_depth", 0.0) > 0:  # optional entry chamfer (not used: the source bores have none)
        z_chamfer = half - config["chamfer_depth"]
        r_chamfer = config["chamfer_radius"] / np.cos(np.pi / n)
        pieces = [(r_bore, r_bore, z_bottom, z_chamfer), (r_bore, r_chamfer, z_chamfer, z_top)]
    for k, x in enumerate(config["rail_stations"]):
        wood(parent, f"{prefix}_b{k}_left", (cut, (half - cut) / 2, half), (x, y - (half + cut) / 2, 0))
        wood(parent, f"{prefix}_b{k}_right", (cut, (half - cut) / 2, half), (x, y + (half + cut) / 2, 0))
        wood(parent, f"{prefix}_b{k}_bottom", (cut, cut, (width - depth) / 2), (x, y, -half + (width - depth) / 2))
        for j in range(n):
            a, b = 2 * np.pi * np.array([j, j + 1]) / n
            for part, (r0, r1, z0, z1) in enumerate(pieces):
                mesh = f"{prefix}_b{k}_s{j}_{part}"
                node(assets, "mesh", name=mesh, vertex=sector_vertices(r0, r1, 0.013, a, b, z0, z1))
                # Bore walls collide with dowels only (collision bit 2): nothing else can reach inside a bore.
                node(parent, "geom", name=mesh, type="mesh", mesh=mesh, pos=(x, y, 0), density=0, material="pine",
                     **BITS["bore"], **WOOD_CONTACT)
        # Bore entry and axis (pointing into the leg) for the checker.
        node(parent, "site", name=f"{prefix}_b{k}_entry", pos=(x, y, half), size=(0.001,), rgba=(0, 0, 0, 0))


def side_frame(world, assets, config, name, pos, rotation):
    body = node(world, "body", name=name, pos=pos, quat=quat(rotation))
    node(body, "freejoint", name=name + "_free")
    node(body, "inertial", pos=(0, 0, 0), mass=config["frame_mass"], diaginertia=(0.009, 0.012, 0.020))
    for sign in (-1, 1):
        hollow_leg(body, assets, config, sign * config["half_spacing"], f"{name}_leg_{'m' if sign < 0 else 'p'}")
    for k, x in enumerate(config["rail_stations"]):
        wood(body, f"{name}_factory_crossrail_{k}", (0.015, config["half_spacing"] - 0.015, 0.015), (x, 0, 0))
    half = config["leg_width"] / 2
    for sign in (-1, 1):
        for face in (-1, 1):
            # Invisible 1 mm skid on each leg face: the only frame geometry that touches the table.
            node(body, "geom", name=f"{name}_skid_{'m' if sign < 0 else 'p'}_{'b' if face < 0 else 't'}", type="box",
                 size=(config["leg_length"] / 2, half, 0.0005), pos=(0, sign * config["half_spacing"], face * (half - 0.0005)),
                 density=0, rgba=(0, 0, 0, 0), group=3, **BITS["skid"], **WOOD_CONTACT)
    return body


def rail(world, config, name, pos, rotation):
    body = node(world, "body", name=name, pos=pos, quat=quat(rotation))
    node(body, "freejoint", name=name + "_free")
    node(body, "inertial", pos=(0, 0, 0), mass=config["rail_mass"], diaginertia=(0.00073, 0.00073, 0.0000195))
    half_length = config["rail_length"] / 2
    wood(body, name + "_pine", (0.015, 0.015, half_length), (0, 0, 0), bits="rail")
    r, exposed = config["dowel_radius"], config["dowel_exposed"]
    for sign in (-1, 1):
        # A dowel pin with rounded (chamfered) ends: 15 mm exposed beyond the rail shoulder.
        inner, tip = sign * (half_length - exposed + r), sign * (half_length + exposed - r)
        node(body, "geom", name=f"{name}_dowel_{'m' if sign < 0 else 'p'}", type="capsule", size=(r,),
             fromto=(0, 0, inner, 0, 0, tip), density=0, rgba=(0.70, 0.52, 0.31, 1), **BITS["dowel"],
             **WOOD_CONTACT)
        node(body, "site", name=f"{name}_tip_{'m' if sign < 0 else 'p'}", pos=(0, 0, sign * (half_length + exposed)),
             size=(0.001,), rgba=(0, 0, 0, 0))
        node(body, "site", name=f"{name}_shoulder_{'m' if sign < 0 else 'p'}", pos=(0, 0, sign * half_length),
             size=(0.001,), rgba=(0, 0, 0, 0))
    return body


def rail_poses(config):
    """Initial rail poses: the brace lies on the table, three rails stand seated in the lower frame."""
    lower = np.asarray(config["lower_frame_pos"], dtype=float)
    poses = {"brace": (np.asarray(config["brace_pos"], dtype=float), Rotation.from_euler("y", np.pi / 2).as_matrix())}
    stations = [(x, y) for x in config["rail_stations"] for y in (-config["half_spacing"], config["half_spacing"])]
    for i, (x, y) in enumerate(stations[1:], 1):
        poses[f"rail_{i}"] = (lower + [x, y, config["leg_width"] / 2 + config["rail_length"] / 2], np.eye(3))
    return poses


def add_stool(root, config):
    assets, world = root.find("asset"), root.find("worldbody")
    node(assets, "texture", name="pine_grain", type="2d", file=str((ASSETS / "pine-grain.png").resolve()))
    # The pine-grain texture already carries the pale pine colour of the source film (mean ~0.88/0.74/0.52).
    node(assets, "material", name="pine", texture="pine_grain", texrepeat=(1, 1), rgba=(1, 1, 1, 1), specular=0.12,
         shininess=0.15)
    node(assets, "texture", name="studio_sky", type="skybox", builtin="gradient", width=256, height=256,
         rgb1=(0.80, 0.82, 0.83), rgb2=(0.93, 0.93, 0.92))
    table_z = config["table_z"]
    node(world, "geom", name="floor", type="plane", size=(3, 3, 0.05), pos=(0, 0, -0.1), rgba=(0.53, 0.56, 0.54, 1),
         **BITS["support"])
    node(world, "geom", name="table", type="box", size=(0.50, 0.88, 0.025), pos=(0.73, 0.15, table_z - 0.025),
         rgba=(0.42, 0.44, 0.45, 1), friction=(0.45, 0.003, 0.0001), solref=(0.01, 1), **BITS["support"])
    for x in (0.28, 1.18):
        for y in (-0.68, 0.98):
            node(world, "geom", name=f"table_leg_{x}_{y}", type="box", size=(0.025, 0.025, 0.395),
                 pos=(x, y, 0.295), rgba=(0.18, 0.20, 0.21, 1), contype=0, conaffinity=0)
    side_frame(world, assets, config, "lower_frame", config["lower_frame_pos"], np.eye(3))
    side_frame(world, assets, config, "upper_frame", config["upper_frame_pos"],
               Rotation.from_euler("x", np.pi).as_matrix())
    for name, (pos, rotation) in rail_poses(config).items():
        rail(world, config, name, pos, rotation)
    # Uninstalled seat and eight screws: static decor from the source scene (not part of the task).
    target_r = Rotation.from_euler("y", np.pi / 2).as_matrix()
    node(world, "geom", name="uninstalled_seat", type="box", size=(0.16, 0.16, 0.01), pos=(0.98, -0.37, table_z + 0.01),
         material="pine", contype=0, conaffinity=0)
    for i in range(8):
        base = np.array([0.99 + (i % 4) * 0.033, 0.14 + (i // 4) * 0.055, table_z + 0.005])
        node(world, "geom", name=f"screw_{i}_shaft", type="cylinder", size=(0.002, 0.018), pos=base, quat=quat(target_r),
             rgba=(0.58, 0.59, 0.61, 1), contype=0, conaffinity=0)
        node(world, "geom", name=f"screw_{i}_head", type="cylinder", size=(0.005, 0.002), pos=base + [0.018, 0, 0],
             quat=quat(target_r), rgba=(0.67, 0.68, 0.70, 1), contype=0, conaffinity=0)
    node(world, "light", pos=(0.6, -1.0, 2.6), dir=(0, 0, -1), diffuse=(0.7, 0.7, 0.7))
    node(world, "light", pos=(0.5, 1.6, 2.3), dir=(0, 0, -1), diffuse=(0.55, 0.55, 0.55))
    node(world, "camera", name="overview", pos=(1.50, -0.95, 1.50),
         xyaxes=(0.7809, 0.6247, 0, -0.2474, 0.3093, 0.9182), fovy=42)
    node(world, "camera", name="closeup", pos=(1.02, -0.62, 1.12),
         xyaxes=(0.7926, 0.6097, 0, -0.1696, 0.2205, 0.9605), fovy=45)
    node(world, "camera", name="side", pos=(0.62, -1.30, 1.10), xyaxes=(1, 0, 0, 0, 0.1275, 0.9918), fovy=40)


def build(config, asset_dir=None, hand="sharpa"):
    """Compose the frozen scene with the selected genuine hand on the six-axis wrist stage."""
    hand_id = hands.canonical(hand)
    verify_assets()
    folder = Path(asset_dir) if asset_dir else hands.sharpa_dir()  # DEXHAND_ASSET_DIR or the image path
    root = ET.parse(folder / "right_hand.xml").getroot()
    root.set("model", hands.info(hand_id)["model"] + " stool brace insertion")
    root.find("compiler").set("meshdir", str((folder / "assets/right").resolve()))
    option = root.find("option")
    option.set("timestep", str(config["physics_dt"]))
    option.set("gravity", "0 0 -9.81")
    option.set("iterations", "60")
    option.set("integrator", "implicitfast")
    option.set("cone", "elliptic")
    option.set("impratio", "10")
    if config.get("noslip_iterations"):
        option.set("noslip_iterations", str(config["noslip_iterations"]))
    for key in root.findall("keyframe"):
        root.remove(key)
    world, actuator = root.find("worldbody"), root.find("actuator")
    hand_body = world.find("body")
    world.remove(hand_body)
    wrist = node(world, "body", name="wrist_stage", pos=config["stage_origin"])
    node(wrist, "inertial", pos=(0, 0, 0), mass=0.01, diaginertia=(0.00001,) * 3)
    # Zero wrist angles: palm down (-z), fingers +x, thumb +y.
    hand_body.set("quat", "0.7071067811865476 0 0.7071067811865476 0")
    wrist.append(hand_body)
    for i, name in enumerate(("x", "y", "z", "rx", "ry", "rz")):
        axis = [int(i % 3 == j) for j in range(3)]
        wrist.insert(
            i,
            ET.Element(
                "joint",
                name="wrist_" + name,
                type="slide" if i < 3 else "hinge",
                axis=" ".join(map(str, axis)),
                range="-0.8 0.8" if i < 3 else "-3.14 3.14",
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
    add_stool(root, config)
    visual = node(root, "visual")
    node(visual, "global", offwidth=1280, offheight=720)
    node(visual, "quality", shadowsize=4096, offsamples=4)
    node(visual, "headlight", ambient=(0.38, 0.38, 0.38), diffuse=(0.45, 0.45, 0.45), specular=(0.1, 0.1, 0.1))
    xml = ET.tostring(root, encoding="unicode")
    return mujoco.MjModel.from_xml_string(xml), xml
