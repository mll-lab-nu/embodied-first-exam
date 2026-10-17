"""Board-book page-turn scene: a free 6x6 in board book on a desk and the Tianji Marvin arm robot with dexterous hands.

The book reuses the T39 scene's board-book design (eight rigid 1.2 mm laminated leaves with sixteen fixed printed
pages, two covers, a teal flexible spine wrap). Every leaf is a passive hinge (with friction and damping) plus a small
vertical binding compliance under one free spine body; nothing in the book is actuated.
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

# Board-book geometry (T39 source: common 6 x 6 in trim, two 350 gsm sheets laminated per leaf).
WIDTH = HEIGHT = 0.1524
THICKNESS = 0.0012
AREAL_MASS = 0.700  # kg / m^2
CORNER = 0.005
LEAVES = 8
# Hinge-root heights above the spine origin (T39 source): leaves 0-1 lie on the left, 2-7 on the right.
PAGE_ROOT_Z = [0.0014, 0.0028, 0.0084, 0.0070, 0.0056, 0.0042, 0.0028, 0.0014]
LEFT_LEAVES = (0, 1)
TARGET_LEAF = 2
GUTTER_GAP = 0.004  # collision boxes start 4 mm from the hinge line


def node(parent, tag, **attributes):
    def value(x):
        if isinstance(x, (tuple, list, np.ndarray)):
            return " ".join(repr(float(v)) if isinstance(v, (float, np.floating)) else str(v) for v in np.ravel(x))
        return repr(float(x)) if isinstance(x, (float, np.floating)) else str(x)

    return ET.SubElement(parent, tag, {k: value(v) for k, v in attributes.items()})


def outline():
    """Rounded 6 x 6 in board outline in the leaf frame (x from the hinge to the fore-edge, y along the spine)."""
    points = []
    for cx, cy, start in [
        (WIDTH - CORNER, -HEIGHT / 2 + CORNER, -np.pi / 2),
        (WIDTH - CORNER, HEIGHT / 2 - CORNER, 0),
        (CORNER, HEIGHT / 2 - CORNER, np.pi / 2),
        (CORNER, -HEIGHT / 2 + CORNER, np.pi),
    ]:
        for angle in np.linspace(start, start + np.pi / 2, 7):
            points.append([cx + CORNER * np.cos(angle), cy + CORNER * np.sin(angle)])
    return np.round(np.array(points), 9)


def add_book_assets(asset):
    p = outline()
    n = len(p)
    vertices = np.vstack([np.c_[p, np.full(n, -THICKNESS / 2)], np.c_[p, np.full(n, THICKNESS / 2)]])
    faces = []
    for i in range(1, n - 1):
        faces.extend([(0, i + 1, i), (n, n + i, n + i + 1)])
    for i in range(n):
        j = (i + 1) % n
        faces.extend([(i, j, n + j), (i, n + j, n + i)])
    node(asset, "mesh", name="rounded_board_solid", vertex=vertices, face=np.asarray(faces))
    for page in range(1, 17):
        node(asset, "texture", name=f"page_tex_{page}", type="2d", file=str(ASSETS / f"page-{page:02d}.png"))
        node(
            asset,
            "material",
            name=f"print_{page}",
            texture=f"page_tex_{page}",
            texuniform="false",
            rgba=(1, 1, 1, 1),
            specular=0.08,
            shininess=0.15,
        )
    node(asset, "texture", name="cover_tex", type="2d", file=str(ASSETS / "cover.png"))
    node(asset, "material", name="cover_print", texture="cover_tex", texuniform="false", rgba=(1, 1, 1, 1), specular=0.08)
    for top in (True, False):
        # Recto (top) faces map u from the hinge to the fore-edge; verso (bottom) faces reverse u so a turned leaf
        # reads normally from above (the T39 export applies the same reversal).
        z = (1 if top else -1) * (THICKNESS / 2 + 0.000003)
        vertices = np.c_[p, np.full(n, z)]
        u = p[:, 0] / WIDTH if top else 1 - p[:, 0] / WIDTH
        uv = np.c_[u, 1 - (p[:, 1] + HEIGHT / 2) / HEIGHT]  # MuJoCo samples PNG rows top-down
        face = [(0, i, i + 1) if top else (0, i + 1, i) for i in range(1, n - 1)]
        node(
            asset,
            "mesh",
            name="print_face_" + ("a" if top else "b"),
            vertex=vertices,
            face=np.asarray(face),
            texcoord=uv,
            inertia="shell",
        )


def add_board(parent, name, z, side, config, page=None):
    """One rigid laminated board: passive binding hinge + small vertical binding compliance."""
    book = config["book"]
    # Every board starts flat on its stack (as in the T39 source); qpos measures the opening angle from the flat
    # authored side.
    rest = 0.0
    angle = np.pi if side == "left" else rest
    body = node(parent, "body", name=name, pos=(0, 0, z), quat=(np.cos(angle / 2), 0, -np.sin(angle / 2), 0))
    node(
        body,
        "joint",
        name=name + "_binding_compliance",
        type="slide",
        axis=(0, 0, 1),
        range=(-book["compliance_range_m"], book["compliance_range_m"]),
        stiffness=book["compliance_stiffness_N_m"],
        damping=book["compliance_damping_Ns_m"],
        frictionloss=0.002,
    )
    # Hinge angle 0 is the board's authored side; right-hand boards open with positive angles, left-hand boards
    # (authored flipped) with negative angles, so every board can be turned over the spine in either direction.
    lower, upper = (-np.pi - 0.25, 0.25) if side == "left" else (-0.25, np.pi + 0.25)
    stiffness, damping = 0.00002, book["hinge_damping_Nms"]
    if name.endswith("_cover"):
        # Covers are glued to the spine wrap: a stiff binding spring keeps the spine level with the covers.
        stiffness, damping = book["cover_hinge_stiffness_Nm_rad"], 0.02
    node(
        body,
        "joint",
        name=name + "_binding",
        type="hinge",
        axis=(0, -1, 0),
        range=(lower, upper),
        stiffness=stiffness,
        damping=damping,
        frictionloss=book["hinge_frictionloss_Nm"],
        armature=0.00001,
        ref=rest,
        solreflimit=(0.01, 1),
    )
    area = WIDTH * HEIGHT - (4 - np.pi) * CORNER**2
    mass = area * AREAL_MASS
    node(
        body,
        "inertial",
        mass=mass,
        pos=(WIDTH / 2, 0, 0),
        diaginertia=(
            mass * (HEIGHT**2 + THICKNESS**2) / 12,
            mass * (WIDTH**2 + THICKNESS**2) / 12,
            mass * (WIDTH**2 + HEIGHT**2) / 12,
        ),
    )
    # Contact: a thin box with the board's footprint (the 5 mm corner rounding is visual only). It starts
    # GUTTER_GAP from the hinge line: boards of opposite stacks meet at the flexible binding, not board-to-board.
    node(
        body,
        "geom",
        name=name + "_board",
        type="box",
        size=((WIDTH - GUTTER_GAP) / 2, HEIGHT / 2, THICKNESS / 2),
        pos=((WIDTH + GUTTER_GAP) / 2, 0, 0),
        mass=0,
        rgba=(0.88, 0.86, 0.80, 0),
        friction=(book["board_friction"], 0.001, 0.0001),
        solref=(0.004, 1),
        solimp=(0.95, 0.99, 0.001),
        condim=3,
        group=3,
    )
    node(
        body,
        "geom",
        name=name + "_board_visual",
        type="mesh",
        mesh="rounded_board_solid",
        mass=0,
        contype=0,
        conaffinity=0,
        group=2,
        rgba=(0.88, 0.86, 0.80, 1),
    )
    if page is not None:
        for face, number in (("a", page), ("b", page + 1)):
            node(
                body,
                "geom",
                name=f"{name}_print_{face}",
                type="mesh",
                mesh="print_face_" + face,
                material=f"print_{number}",
                mass=0,
                contype=0,
                conaffinity=0,
                group=2,
            )
    else:
        node(
            body,
            "geom",
            name=name + "_outer_cover",
            type="mesh",
            mesh="print_face_a" if side == "left" else "print_face_b",
            material="cover_print",
            mass=0,
            contype=0,
            conaffinity=0,
            group=2,
        )
    node(body, "site", name=name + "_edge", pos=(WIDTH, 0, 0), size=(0.001,), group=5)
    return mass


def add_book(world, asset, config):
    add_book_assets(asset)
    xy = config["book_xy"]
    book_cfg = config["book"]
    yaw = np.radians(config.get("book_yaw_deg", 0.0))
    book = node(world, "body", name="book_spine", pos=(xy[0], xy[1], config["table_z"] + config["book"]["spine_origin_height_m"]),
                quat=(np.cos(yaw / 2), 0, 0, np.sin(yaw / 2)))
    node(book, "freejoint", name="book_free")
    # The teal cloth spine wrap seen in the gutter (visual) and the glued binding base it covers, which rests
    # flat on the desk under the gutter (contact; keeps the free spine level).
    node(
        book,
        "geom",
        name="flexible_spine_wrap",
        type="box",
        pos=(0, 0, 0.0049),
        size=(0.0012, HEIGHT / 2, 0.0055),
        mass=0,
        rgba=(0.16, 0.38, 0.42, 1),
        contype=0,
        conaffinity=0,
        group=2,
    )
    node(
        book,
        "geom",
        name="binding_base",
        type="box",
        pos=(0, 0, 0),
        size=(0.008, HEIGHT / 2, 0.0006),
        mass=book_cfg["binding_mass_kg"],
        rgba=(0.16, 0.38, 0.42, 1),
        friction=(0.5, 0.002, 0.0001),
        solref=(0.004, 1),
        group=3,
    )
    for i in range(LEAVES):
        add_board(book, f"leaf_{i}", PAGE_ROOT_Z[i], "left" if i in LEFT_LEAVES else "right", config, 2 * i + 1)
    add_board(book, "left_cover", 0.0, "left", config)
    add_board(book, "right_cover", 0.0, "right", config)
    return book


def asset_manifest():
    return json.loads((ASSETS / "manifest.json").read_text())


def verify_assets():
    """Check every bundled texture/license against the sha256 manifest."""
    manifest = asset_manifest()
    for name, expected in manifest["files"].items():
        raw = (ASSETS / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected["sha256"] or len(raw) != expected["bytes"]:
            raise RuntimeError(f"Asset integrity failure: {name}")
    return manifest


def build(config, asset_dir=None, hand="sharpa"):
    """Compose the frozen book scene with the Marvin robot carrying the selected genuine hands."""
    verify_assets()
    hand_id = hands.canonical(hand)
    folder = Path(
        asset_dir
        or os.environ.get("DEXHAND_ASSET_DIR")
        or Path(__file__).resolve().parents[4] / "images/dexhand/assets/hand"
    )
    root = ET.parse(folder / "right_hand.xml").getroot()
    root.set("model", hands.info(hand_id)["model"] + " board-book page turn")
    root.find("compiler").set("meshdir", str((folder / "assets/right").resolve()))
    option = root.find("option")
    option.set("timestep", str(config["physics_dt"]))
    option.set("gravity", "0 0 -9.81")
    option.set("iterations", "80")
    option.set("integrator", "implicitfast")
    option.set("cone", "elliptic")
    for key in root.findall("keyframe"):
        root.remove(key)
    assets, world, actuator = root.find("asset"), root.find("worldbody"), root.find("actuator")
    hand_body = world.find("body")
    # The family's Sharpa tweaks (finger bias, fingertip friction), applied before mounting so both Waves share them.
    for a in actuator:
        if a.tag == "general":
            bias = [float(v) for v in a.get("biasprm", "0 0 0").split()]
            bias[2] = -0.9
            a.set("biasprm", " ".join(map(str, bias)))
    for g in hand_body.iter("geom"):
        if "fingertip_collision" in g.get("name", ""):
            g.set("friction", "1.2 .005 .0001")
    # Tianji Marvin robot standing at the desk (both 7-DoF arms; the right arm turns the page, the left arm is parked).
    # Wuji: the genuine Wuji Hand 2.2 replaces both Waves inside mount_marvin.
    marvin = config["marvin"]
    sibling = folder.parent / "wuji_v2_2"
    arm_rig.mount_marvin(root, marvin["base_pos"], marvin["base_yaw"], hand=hand_id, active=("right",),
                         mount_names={"right": "wrist_stage"}, sharpa_folder=folder,
                         wuji_folder=sibling if (sibling / "mjcf/right.xml").is_file() else None)
    table = config["table"]
    node(assets, "texture", name="desk_grain", type="2d", builtin="flat", width=512, height=512,
         rgb1=(0.74, 0.48, 0.30), rgb2=(0.66, 0.42, 0.26), mark="random", random=0.04, markrgb=(0.62, 0.40, 0.25))
    node(assets, "material", name="desk_material", texture="desk_grain", texrepeat=(3, 3), reflectance=0.0,
         specular=0.25, shininess=0.3)
    node(assets, "texture", name="studio_sky", type="skybox", builtin="gradient", width=256, height=256,
         rgb1=(0.42, 0.45, 0.45), rgb2=(0.20, 0.23, 0.24))
    floor_z = config.get("floor_z", 0.0)
    node(world, "geom", name="floor", type="plane", pos=(0, 0, floor_z), size=(3, 3, 0.1), rgba=(0.30, 0.33, 0.34, 1),
         friction=(0.65, 0.002, 0.0001))
    top = config["table_z"] - 0.05
    # Desk legs: the T39 desk's front legs (0.07 m from the front edge) would stand inside the Marvin stand's base
    # plate (+-0.393 m around the stand origin); they are set back to desk_legs_x so that no robot geom (convex hull,
    # collision or visual) overlaps any furniture geom. The desk top keeps the source pose and size.
    legs_x = config.get("desk_legs_x", [table["center_x"] - table["half_x"] + 0.07, table["center_x"] + table["half_x"] - 0.07])
    for lx in legs_x:
        for ly in (table["center_y"] - table["half_y"] + 0.05, table["center_y"] + table["half_y"] - 0.05):
            node(world, "geom", name=f"desk_leg_{lx:.2f}_{ly:.2f}", type="box", pos=(lx, ly, (top + floor_z) / 2),
                 size=(0.02, 0.02, (top - floor_z) / 2), rgba=(0.25, 0.26, 0.27, 1))
    node(
        world,
        "geom",
        name="table",
        type="box",
        size=(table["half_x"], table["half_y"], 0.025),
        pos=(table["center_x"], table["center_y"], config["table_z"] - 0.025),
        material="desk_material",
        rgba=(1, 1, 1, 1),
        friction=(0.65, 0.002, 0.0001),
        solref=(0.004, 1),
    )
    add_book(world, assets, config)
    node(world, "light", name="key", pos=(0.85, -0.95, 2.1), dir=(-0.25, 0.65, -1), diffuse=(0.62, 0.60, 0.57),
         specular=(0.15, 0.15, 0.15), castshadow="true")
    node(world, "light", name="fill", pos=(0.1, 0.7, 1.8), dir=(0.4, -0.5, -1), diffuse=(0.30, 0.32, 0.35),
         specular=(0, 0, 0), castshadow="false")
    for camera in config["cameras"]:
        node(world, "camera", name=camera["name"], pos=camera["pos"], xyaxes=camera["xyaxes"], fovy=camera["fovy"])
    v = node(root, "visual")
    node(v, "global", offwidth=1280, offheight=720)
    node(v, "quality", shadowsize=4096, offsamples=4)
    node(v, "headlight", ambient=(0.30, 0.30, 0.30), diffuse=(0.30, 0.30, 0.30), specular=(0.05, 0.05, 0.05))
    xml = ET.tostring(root, encoding="unicode")
    return mujoco.MjModel.from_xml_string(xml), xml
