"""T38 desk scene (DL wallet envelope + tri-folded A4 letter) with a dexterous hand on a six-axis wrist stage.

Geometry and layout follow the approved T38 scene (`envelope_meta_delivery`): writing desk top at z = 0.70 m, the
110 x 220 mm envelope centred at (0.48, 0.16) with its open mouth facing +X and the open flap lying on the desk, and
the 99 x 210 mm folded letter at (0.48, -0.14). Physics simplifications (documented in README.md):

* the envelope is one light free rigid pocket: back and front walls, permanent 3 mm side seams and a 4 mm bottom seam
  are solid walls, the front wall ends in a hinged mouth lip (closed at the start) and the open flap is a thin ramp on the desk;
* the folded letter is one light free rigid card (2 mm thick, the paper's bending is not simulated).

Nothing is attached to the hand; both objects move only through contact.
"""

from __future__ import annotations

import importlib.util
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

PAPER_FRICTION = (0.35, 0.005, 0.0001)
DESK_FRICTION = (0.5, 0.005, 0.0001)
OBJECT_SOLREF = (0.004, 1)
OBJECT_SOLIMP = (0.95, 0.99, 0.0005)
OBJECT_SOLMIX = 20


def node(parent, tag, **attributes):
    def value(x):
        return " ".join(f"{float(v):.10g}" if isinstance(v, float) else str(v) for v in x) if isinstance(
            x, (tuple, list, np.ndarray)) else (f"{x:.10g}" if isinstance(x, float) else str(x))

    return ET.SubElement(parent, tag, {k: value(v) for k, v in attributes.items()})


def solid(parent, name, kind, size, friction=PAPER_FRICTION, **attributes):
    if size is not None:
        attributes["size"] = size
    # solmix: the paper's stiff contact dominates the soft elastomer fingertip pads (otherwise a pad would sink
    # through the 2 mm letter onto the desk).
    return node(parent, "geom", name=name, type=kind, friction=friction, condim=4,
                solref=OBJECT_SOLREF, solimp=OBJECT_SOLIMP, solmix=OBJECT_SOLMIX, **attributes)


def visual(parent, name, kind, size=None, **attributes):
    if size is not None:
        attributes["size"] = size
    return node(parent, "geom", name=name, type=kind, contype=0, conaffinity=0, mass=0, group=2, **attributes)


def envelope_geometry(cfg):
    """Envelope dimensions in its own frame (origin: envelope centre on the desk surface, +X towards the mouth)."""
    e = cfg["envelope"]
    half_depth, half_width = e["depth_m"] / 2, e["width_m"] / 2
    wall, gap = e["wall_m"], e["gap_m"]
    return dict(
        half_depth=half_depth,
        half_width=half_width,
        wall=wall,
        gap=gap,
        floor=wall,  # top of the back wall = cavity floor
        ceiling=wall + gap,  # underside of the front wall = cavity ceiling
        side_seam=e["side_seam_m"],
        bottom_seam=e["bottom_seam_m"],
        lip=e["lip_m"],
        lip_angle=e["lip_angle_rad"],
        flap_depth=e["flap_depth_m"],
        flap_tip_half_width=e["flap_tip_half_width_m"],
    )


def add_envelope(world, assets, cfg):
    g = envelope_geometry(cfg)
    e = cfg["envelope"]
    body = node(world, "body", name="envelope", pos=(*e["pos"], cfg["desk_top_z"]), euler=(0, 0, e["yaw"]))
    node(body, "freejoint", name="envelope_free")
    hd, hw, t, gap = g["half_depth"], g["half_width"], g["wall"], g["gap"]
    mass = e["mass_kg"]
    paper = dict(material="envelope_paper")
    # Back wall (lies on the desk) and front wall; the last `lip` metres of the front wall form the hinged mouth lip.
    solid(body, "envelope_back", "box", (hd, hw, t / 2), pos=(0, 0, t / 2), mass=0.42 * mass, **paper)
    main_half = (2 * hd - g["lip"]) / 2
    solid(body, "envelope_front", "box", (main_half, hw, t / 2), pos=(-hd + main_half, 0, g["ceiling"] + t / 2),
          mass=0.36 * mass, **paper)
    # The mouth lip: the last `lip` metres of the front wall bend about the fold line as a passive elastic hinge
    # (paper stiffness), resting at task.json lip_angle_rad (0 = closed); a fingertip or the letter can lift it.
    a = g["lip_angle"]
    hinge_x = hd - g["lip"]
    lip = node(body, "body", name="envelope_lip", pos=(hinge_x, 0, g["ceiling"] + t / 2), euler=(0, -a, 0))
    node(lip, "joint", name="envelope_lip_fold", type="hinge", axis=(0, -1, 0), ref=a,
         springref=e.get("lip_springref_rad", a),
         range=(0.0, e["lip_max_angle_rad"]), stiffness=e["lip_stiffness_nm_rad"], damping=e["lip_damping"],
         armature=1e-5)
    solid(lip, "envelope_mouth_lip", "box", (g["lip"] / 2, hw, t / 2), pos=(g["lip"] / 2, 0, 0),
          mass=0.09 * mass, **paper)
    # Permanent glued side and bottom seams close the cavity (solid walls between the two envelope walls).
    s, b = g["side_seam"], g["bottom_seam"]
    taper = e["seam_taper_m"]
    for sign, label in ((1, "left"), (-1, "right")):
        # Wallet-envelope side flaps narrow towards the mouth: the glued band is full width up to `taper` metres
        # before the mouth line and then tapers to nothing at the mouth (a small entry funnel).
        length = 2 * hd - taper
        solid(body, f"envelope_side_seam_{label}", "box", (length / 2, s / 2, gap / 2),
              pos=(-hd + length / 2, sign * (hw - s / 2), t + gap / 2), mass=0.03 * mass, **paper)
        y_out, y_in, x0, z0, z1 = sign * hw, sign * (hw - s), hd - taper, t, t + gap
        vertices = [(x0, y_out, z0), (x0, y_in, z0), (hd, y_out, z0), (x0, y_out, z1), (x0, y_in, z1), (hd, y_out, z1)]
        node(assets, "mesh", name=f"envelope_seam_taper_{label}_mesh", vertex=np.asarray(vertices, dtype=float).ravel())
        solid(body, f"envelope_seam_taper_{label}", "mesh", None, mesh=f"envelope_seam_taper_{label}_mesh",
              mass=0.005 * mass, **paper)
    solid(body, "envelope_bottom_seam", "box", (b / 2, hw - s, gap / 2), pos=(-hd + b / 2, 0, t + gap / 2),
          mass=0.03 * mass, **paper)
    # The open flap lies flat on the desk outside the mouth, as a thin ramp from the back wall down to the desk.
    fd, tip = g["flap_depth"], g["flap_tip_half_width"]
    vertices = [  # a wedge: full wall thickness at the mouth fold, zero at the flap's free edge
        (hd, -hw, 0), (hd, hw, 0), (hd + fd, tip, 0), (hd + fd, -tip, 0), (hd, -hw, t), (hd, hw, t),
    ]
    node(assets, "mesh", name="envelope_flap_mesh", vertex=np.asarray(vertices, dtype=float).ravel())
    solid(body, "envelope_open_flap", "mesh", None, mesh="envelope_flap_mesh", mass=0.12 * mass,
          material="flap_paper")
    # Visual detail only: faint glue-band and fold lines on the front wall.
    z = g["ceiling"] + t + 0.00002
    for sign in (1, -1):
        visual(body, f"envelope_side_band_{sign}", "box", (hd - g["lip"] / 2, s / 2, 0.00001),
               pos=(-g["lip"] / 2, sign * (hw - s / 2), z), rgba=(0.90, 0.90, 0.87, 1))
    visual(body, "envelope_bottom_band", "box", (b / 2, hw - s, 0.00001), pos=(-hd + b / 2, 0, z),
           rgba=(0.90, 0.90, 0.87, 1))
    visual(body, "envelope_flap_fold", "box", (0.0004, hw, 0.00001), pos=(hd, 0, t + 0.00002),
           rgba=(0.70, 0.76, 0.77, 1))
    return body


def add_letter(world, assets, cfg):
    l = cfg["letter"]
    half_depth, half_width, half_t = l["depth_m"] / 2, l["width_m"] / 2, l["thickness_m"] / 2
    body = node(world, "body", name="letter", pos=(*l["pos"], cfg["desk_top_z"] + half_t), euler=(0, 0, l["yaw"]))
    node(body, "freejoint", name="letter_free")
    # Contact shape: a flat card whose two long edges are the rounded folds of the tri-fold (capsules), so the
    # letter can ride over the open flap's edge instead of catching on it.
    r = half_t
    solid(body, "letter_card", "box", (half_depth - r, half_width, half_t), mass=0.8 * l["mass_kg"],
          material="letter_paper")
    for sign, label in ((1, "trailing"), (-1, "leading")):
        solid(body, f"letter_fold_{label}", "capsule", (r, half_width - r), pos=(sign * (half_depth - r), 0, 0),
              euler=(np.pi / 2, 0, 0), mass=0.1 * l["mass_kg"], material="letter_paper")
    # Printed top face (project-original letterhead texture, visual only): u along the 210 mm width.
    z = half_t + 0.00002
    vertex = [(-half_depth, -half_width, z), (half_depth, -half_width, z), (half_depth, half_width, z),
              (-half_depth, half_width, z)]
    texcoord = [(0, 0), (0, 1), (1, 1), (1, 0)]
    node(assets, "mesh", name="letter_print_mesh", vertex=np.asarray(vertex, dtype=float).ravel(),
         texcoord=np.asarray(texcoord, dtype=float).ravel(), face=(0, 1, 2, 0, 2, 3), inertia="shell")
    visual(body, "letter_print", "mesh", mesh="letter_print_mesh", material="letter_print")
    # Tri-fold crease lines on the long edges (visual only).
    for sign in (1, -1):
        visual(body, f"letter_crease_{sign}", "box", (0.0003, half_width, half_t * 0.98),
               pos=(sign * (half_depth - 0.0003), 0, 0), rgba=(0.90, 0.88, 0.82, 1))
    return body


def add_desk(world, assets, cfg):
    d = cfg["desk"]
    node(assets, "texture", name="desk_grain", type="2d", builtin="checker", width=512, height=512,
         rgb1=(0.55, 0.40, 0.27), rgb2=(0.555, 0.405, 0.275))
    node(assets, "material", name="desk_wood", texture="desk_grain", texrepeat=(10, 10), specular=0.1,
         reflectance=0.02)
    node(world, "geom", name="floor", type="plane", size=(2, 2, 0.02), rgba=(0.67, 0.69, 0.66, 1),
         friction=DESK_FRICTION)
    half_t = d["thickness_m"] / 2
    node(world, "geom", name="desk", type="box", size=(d["half_x"], d["half_y"], half_t),
         pos=(d["center"][0], d["center"][1], cfg["desk_top_z"] - half_t), material="desk_wood",
         friction=DESK_FRICTION, condim=4, solref=OBJECT_SOLREF, solimp=OBJECT_SOLIMP)
    leg = (cfg["desk_top_z"] - d["thickness_m"]) / 2
    for i, x in enumerate((d["center"][0] - d["half_x"] + 0.05, d["center"][0] + d["half_x"] - 0.05)):
        for j, y in enumerate((d["center"][1] - d["half_y"] + 0.06, d["center"][1] + d["half_y"] - 0.06)):
            node(world, "geom", name=f"desk_leg_{i}{j}", type="box", size=(0.022, 0.022, leg), pos=(x, y, leg),
                 rgba=(0.22, 0.23, 0.21, 1), contype=0, conaffinity=0)


def look_at(position, target):
    position, target = np.asarray(position, float), np.asarray(target, float)
    forward = target - position
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, (0, 0, 1))
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    return np.r_[right, up]


def _default_hand_dir():
    """Repository checkout (scripts/dexhand/families/<family>/ -> images/dexhand/assets/hand), else the image path."""
    parents = Path(__file__).resolve().parents
    if len(parents) > 4 and (parents[4] / "images/dexhand/assets/hand/right_hand.xml").is_file():
        return parents[4] / "images/dexhand/assets/hand"
    return Path("/opt/dexhand/hand")


def _wrist_stage(root, config, hand_id, folder):
    """The wave-2 floating six-axis wrist stage (authoring reference rig; the task uses the Marvin arm)."""
    world, actuator = root.find("worldbody"), root.find("actuator")
    hand_body = world.find("body")
    world.remove(hand_body)
    stage = config["wrist_stage"]
    wrist = node(world, "body", name="wrist_stage", pos=stage["origin"])
    node(wrist, "inertial", pos=(0, 0, 0), mass=0.01, diaginertia=(0.00001,) * 3)
    # Mount: at zero wrist rotation the fingers point down (-Z), the palm faces -X (towards the envelope mouth) and
    # the thumb side is +Y, so the task's working orientations stay far from the +-pi wrist limits.
    hand_body.set("quat", "0 0 1 0")
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


def build(config, asset_dir=None, hand="sharpa"):
    """Compose the frozen scene with the selected genuine hand on the same six-axis wrist stage."""
    hand_id = hands.canonical(hand)
    folder = Path(asset_dir or os.environ.get("DEXHAND_ASSET_DIR") or _default_hand_dir())
    root = ET.parse(folder / "right_hand.xml").getroot()
    root.set("model", hands.info(hand_id)["model"] + " envelope letter insertion")
    root.find("compiler").set("meshdir", str((folder / "assets/right").resolve()))
    option = root.find("option")
    option.set("timestep", str(config["physics_dt"]))
    option.set("gravity", "0 0 -9.81")
    option.set("iterations", "80")
    option.set("integrator", "implicitfast")
    option.set("cone", "elliptic")
    node(option, "flag", multiccd="enable")
    for key in root.findall("keyframe"):
        root.remove(key)
    assets, world, actuator = root.find("asset"), root.find("worldbody"), root.find("actuator")
    if config.get("rig", "floating") == "marvin":
        # Marvin arm rig (wave 3): the Sharpa tweaks first (they reach the mirrored left Wave too), then the stand and
        # both 7-DoF arms; the right hand hangs from the right flange under the mount body "wrist_stage".
        for a in actuator:
            if a.tag == "general":
                bias = [float(v) for v in a.get("biasprm", "0 0 0").split()]
                bias[2] = -0.9
                a.set("biasprm", " ".join(map(str, bias)))
        for g in world.iter("geom"):
            if "fingertip_collision" in g.get("name", ""):
                g.set("friction", "1.5 .005 .0001")
        sibling = folder.parent / "wuji_v2_2"
        marvin = config["marvin"]
        _arm_rig_module().mount_marvin(root, marvin["base_pos"], marvin["base_yaw"], hand=hand_id, active=("right",),
                                       mount_names={"right": "wrist_stage"}, sharpa_folder=folder,
                                       wuji_folder=sibling if (sibling / "mjcf/right.xml").is_file() else None)
    else:
        _wrist_stage(root, config, hand_id, folder)
    texture_dir = HERE / "assets"
    node(assets, "texture", name="letter_print_tex", type="2d", file=str((texture_dir / "letter.png").resolve()))
    node(assets, "material", name="letter_print", texture="letter_print_tex", specular=0.05, rgba=(1, 1, 1, 1))
    node(assets, "material", name="letter_paper", rgba=(0.99, 0.98, 0.94, 1), specular=0.05)
    node(assets, "material", name="envelope_paper", rgba=(0.965, 0.967, 0.947, 1), specular=0.05)
    node(assets, "material", name="flap_paper", rgba=(0.79, 0.85, 0.86, 1), specular=0.05)
    node(assets, "texture", name="studio_sky", type="skybox", builtin="gradient", width=256, height=256,
         rgb1=(0.84, 0.85, 0.81), rgb2=(0.94, 0.92, 0.87))
    add_desk(world, assets, config)
    add_envelope(world, assets, config)
    add_letter(world, assets, config)
    node(world, "light", pos=(0.22, -0.28, 1.45), dir=(0.3, 0.2, -1), diffuse=(0.8, 0.77, 0.7))
    node(world, "light", pos=(0.78, 0.46, 1.35), dir=(-0.3, -0.3, -1), diffuse=(0.4, 0.43, 0.46))
    for name, cam in config["cameras"].items():
        node(world, "camera", name=name, pos=cam["pos"], xyaxes=look_at(cam["pos"], cam["target"]),
             fovy=cam["fovy"])
    v = node(root, "visual")
    node(v, "global", offwidth=1280, offheight=720)
    node(v, "quality", shadowsize=4096, offsamples=4)
    node(v, "headlight", ambient=(0.32, 0.32, 0.32), diffuse=(0.5, 0.5, 0.5), specular=(0.12, 0.12, 0.12))
    xml = ET.tostring(root, encoding="unicode")
    return mujoco.MjModel.from_xml_string(xml), xml
