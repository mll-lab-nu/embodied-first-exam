"""T28 desktop RAM installation scene rebuilt for physics with a dexterous hand on a six-axis wrist stage.

The motherboard, service tray, workbench, four DDR4 sockets and the Kingston DIMM are taken from the accepted T28
source scene (``assets/t28_scene.xml``, copied verbatim; see ``assets/manifest.json``). The hand rig is the shared
Sharpa Wave / Wuji Hand 2.2 composition (``hands.py``). Physics changes are listed in ``MODELLING_NOTES`` and in the
family README; they keep the scene's objects, look and goal.
"""

from __future__ import annotations

import copy
import importlib.util
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

MODELLING_NOTES = [
    "Geometry, materials, label texture, module dimensions/mass/inertia, key position and latch joint law come from "
    "the accepted T28 source scene (assets/t28_scene.xml).",
    "The 30 copper contact sliders (0.25 g, 900 N/m) are static visuals: they are numerically unstable at a 2 ms "
    "step and carry no task meaning (no electrical model).",
    "The fixed-end retainer post is rigid (its flexure is not needed for a straight insertion) and both side catches "
    "are visual only, so the module is inserted straight down instead of fixed-end-first with a lean.",
    "Socket 3 keeps the source throat (1.66 mm for the 1.27 mm module) and end-fork gap, with lead-in chamfers on the "
    "guide tops; the floor is raised by 1 mm so the module rests at the source's 2 mm seating datum.",
    "The DIMM starts upright in a slotted anti-static foam holder on the bench (key towards +x) instead of lying flat: "
    "picking a 1.27 mm flat PCB off a table is outside a position-controlled hand's reach in this task.",
    "The moving latch keeps the source joint law (hinge 0..0.6 rad, spring 0.012 N m/rad towards closed, damping "
    "0.001, frictionloss 0.008 N m, starts open at 0.55 rad); only the module's lower edge pressing its foot closes it.",
]


def verify_assets():
    """Check the copied source files against ``assets/manifest.json`` (sha256 + size)."""
    import hashlib
    import json

    manifest = json.loads((ASSETS / "manifest.json").read_text())
    for name, entry in manifest["files"].items():
        data = (ASSETS / name).read_bytes()
        if len(data) != entry["bytes"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise RuntimeError(f"Asset {name} does not match assets/manifest.json")


def node(parent, tag, **attributes):
    def value(x):
        return " ".join(str(v) for v in x) if isinstance(x, (tuple, list, np.ndarray)) else str(x)

    return ET.SubElement(parent, tag, {k: value(v) for k, v in attributes.items()})


def look_at(position, target, up=(0, 0, 1)):
    position, target = np.asarray(position, float), np.asarray(target, float)
    forward = target - position
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, up)
    right /= np.linalg.norm(right)
    true_up = np.cross(right, forward)
    return np.r_[right, true_up].round(5)


def _float_list(text):
    return [float(v) for v in text.split()]


def _set_visual_only(geom):
    geom.set("contype", "0")
    geom.set("conaffinity", "0")
    geom.set("group", "2")
    geom.set("density", "0")


def _socket3(body, config):
    """Make the selected socket physical: static copper visuals, rigid fixed post, visual catches, wider throat."""
    half_gap = config["socket_half_gap_m"]
    for child in list(body):
        name = child.get("name", "")
        if child.tag == "body" and name.startswith("contact_"):
            # Copper sliders -> static visual capsules at their rest position (no joint, no mass).
            pos = np.asarray(_float_list(child.get("pos")))
            for g in child.findall("geom"):
                visual = copy.deepcopy(g)
                if visual.get("fromto"):
                    ends = np.asarray(_float_list(visual.get("fromto"))) + np.r_[pos, pos]
                    visual.set("fromto", " ".join(map(str, ends.round(7))))
                else:
                    visual.set("pos", " ".join(map(str, pos)))
                _set_visual_only(visual)
                body.append(visual)
            body.remove(child)
        elif child.tag == "body" and name == "fixed_retainer":
            for j in child.findall("joint"):
                child.remove(j)
            # Rigid end stop: moved 1 mm inward so it locates the module along the slot (0.3 mm play), with a
            # chamfered top inner edge that steers the module's fixed end in.
            pos = _float_list(child.get("pos"))
            pos[0] = -(0.066675 + config["fixed_stop_play_m"] + 0.001)
            child.set("pos", " ".join(f"{v:.6f}" for v in pos))
            for g in child.findall("geom"):
                if g.get("name") == "fixed_catch":
                    _set_visual_only(g)
                if g.get("name") == "fixed_post":
                    size = _float_list(g.get("size"))
                    gpos = _float_list(g.get("pos"))
                    top = gpos[2] + size[2]
                    h, ang, thick = config["lead_in_height_m"], config["lead_in_angle_rad"], 0.0004
                    length = h / np.cos(ang)
                    # inner face is at local x = +size[0]; slope outward (towards -x) going up
                    mid_x = size[0] - 0.5 * h * np.tan(ang)
                    mid_z = top - 0.5 * h
                    cx, cz = mid_x - thick * np.cos(ang), mid_z - thick * np.sin(ang)
                    lead = copy.deepcopy(g)
                    lead.set("name", "fixed_post_lead_in")
                    lead.set("size", f"{thick} {size[1]} {length / 2}")
                    lead.set("pos", f"{cx:.6f} {gpos[1]} {cz:.6f}")
                    lead.set("euler", f"0 {-ang:.6f} 0")
                    child.append(lead)
                    look = copy.deepcopy(g)
                    look.set("name", "fixed_post_visual")
                    _set_visual_only(look)
                    child.append(look)
                    bottom = gpos[2] - size[2]
                    size[2] = (top - h - bottom) / 2
                    gpos[2] = bottom + size[2]
                    g.set("size", " ".join(f"{v:.6f}" for v in size))
                    g.set("pos", " ".join(f"{v:.6f}" for v in gpos))
                    g.set("group", "3")
        elif child.tag == "body" and name == "moving_latch":
            for g in child.findall("geom"):
                if g.get("name") == "latch_catch":
                    _set_visual_only(g)
                if g.get("name") == "latch_foot":
                    g.set("friction", "0.1 0.0002 0.00001")  # smooth plastic foot: does not drag the module
            # The source hinge spring pulled the latch closed and relied on frictionloss to keep it open, which
            # creeps shut in a soft-constraint solver. Replace it by an over-centre (toggle) spring: a passive
            # spatial tendon from the latch spine to an anchor below the pivot. The latch rests open against its
            # 0.55 rad stop, and once the module's lower edge pushes the foot past the centre it snaps closed.
            for j in child.findall("joint"):
                j.set("stiffness", "0")
                j.set("frictionloss", "0")
                j.set("range", "0 " + str(config["latch_initial_rad"]))
            node(child, "site", name="latch_spring_site", pos=(0, 0, 0.006), size=(0.0003,), rgba=(0, 0, 0, 0))
            pivot = np.asarray(_float_list(child.get("pos")))
            centre = config["latch_toggle_rad"]
            anchor = pivot - 0.004 * np.array([np.sin(centre), 0.0, np.cos(centre)])
            node(body, "site", name="latch_anchor_site", pos=anchor.round(6), size=(0.0003,), rgba=(0, 0, 0, 0))
        elif child.tag == "geom" and name.startswith("socket_3_wall_"):
            side = 1.0 if "_1_" in name and "_-1_" not in name else -1.0
            size = _float_list(child.get("size"))
            pos = _float_list(child.get("pos"))
            pos[1] = side * (half_gap + size[1])
            child.set("pos", " ".join(map(str, pos)))
            if name.endswith("_upper"):
                _lead_in(body, child, pos[2] + size[2], config["lead_in_height_m"], size[0], pos[0], side, half_gap,
                         config["lead_in_angle_rad"])
        elif child.tag == "geom" and name.startswith("socket_3_fork_"):
            side = 1.0 if name.endswith("_1") and not name.endswith("_-1") else -1.0
            size = _float_list(child.get("size"))
            pos = _float_list(child.get("pos"))
            pos[1] = side * (half_gap + size[1])
            child.set("pos", " ".join(map(str, pos)))
            _lead_in(body, child, pos[2] + size[2], config["lead_in_height_m"], size[0], pos[0], side, half_gap,
                     config["lead_in_angle_rad"])
        elif child.tag == "geom" and name == "socket_3_key":
            # Same off-centre position and height; 0.70 mm wide instead of 1.18 mm (module notch 1.50 mm) with a
            # rounded top that guides the notch onto it, so a correctly keyed module clears it with 0.4 mm per side
            # while a reversed module (notch 11 mm away) still lands on it.
            size = _float_list(child.get("size"))
            pos = _float_list(child.get("pos"))
            half = config["socket_key_half_m"]
            top = pos[2] + size[2]
            size[0] = half
            size[2] = (top - half) / 2
            pos[2] = size[2]
            child.set("size", " ".join(map(str, size)))
            child.set("pos", " ".join(map(str, pos)))
            cap = copy.deepcopy(child)
            cap.set("name", "socket_3_key_top")
            cap.set("type", "cylinder")
            cap.set("size", f"{half} {size[1]}")
            cap.set("pos", f"{pos[0]} 0 {top - half}")
            cap.set("euler", f"{np.pi / 2} 0 0")
            body.append(cap)
        elif child.tag == "geom" and name == "socket_3_floor":
            child.set("size", "0.0678 0.0027 0.001")
            child.set("pos", "0 0 0.001")


def _lead_in(body, base, top_z, height, half_len, x, side, half_gap, angle):
    """A chamfer at the top inner edge of a socket guide: a thin box whose inner face slopes outward by ``angle``
    from (y = half_gap, z = top_z - height) to the guide top, so a slightly misaligned module edge is steered in."""
    thick = 0.0004
    length = height / np.cos(angle)
    # inner face centre line: from (half_gap, top_z - height) to (half_gap + height*tan, top_z)
    mid_y = half_gap + 0.5 * height * np.tan(angle)
    mid_z = top_z - 0.5 * height
    # move the box centre outward by its half thickness along the face normal
    normal = np.array([np.cos(angle), -np.sin(angle)])  # (y, z) pointing away from the slot centre, side=+1
    cy, cz = mid_y + thick * normal[0], mid_z + thick * normal[1]
    lead = copy.deepcopy(base)
    lead.set("name", base.get("name") + "_lead_in")
    lead.set("size", f"{half_len} {thick} {length / 2}")
    lead.set("pos", f"{x} {side * cy:.6f} {cz:.6f}")
    lead.set("euler", f"{-side * angle:.6f} 0 0")
    body.append(lead)
    # The guide's collision box stops below the chamfer; an exact visual copy keeps the source look.
    look = copy.deepcopy(base)
    look.set("name", base.get("name") + "_visual")
    _set_visual_only(look)
    body.append(look)
    size = _float_list(base.get("size"))
    pos = _float_list(base.get("pos"))
    bottom = pos[2] - size[2]
    new_top = top_z - height
    size[2] = (new_top - bottom) / 2
    pos[2] = bottom + size[2]
    base.set("size", " ".join(f"{v:.6f}" for v in size))
    base.set("pos", " ".join(f"{v:.6f}" for v in pos))
    base.set("group", "3")


def _holder(world, config):
    """Slotted anti-static foam holder; the module stands in its slit (slit along the module length)."""
    x, y = config["holder_xy"]
    yaw = config["holder_yaw_rad"]
    along, across = np.array([np.cos(yaw), np.sin(yaw), 0]), np.array([-np.sin(yaw), np.cos(yaw), 0])
    z0 = config["bench_top_z"]
    base_h, jaw_h, length, width = 0.010, 0.006, 0.078, 0.016
    slit = config["holder_slit_half_m"]
    common = dict(material="foam", friction=(0.8, 0.005, 0.0001), condim=3, solref=(0.004, 1),
                  solimp=(0.95, 0.99, 0.0005), euler=(0, 0, yaw))
    node(world, "geom", name="holder_base", type="box", size=(length, width, base_h / 2),
         pos=(x, y, z0 + base_h / 2), **common)
    jaw = (width - slit) / 2
    for sign in (-1, 1):
        centre = np.array([x, y, z0 + base_h + jaw_h / 2]) + across * sign * (slit + jaw)
        node(world, "geom", name=f"holder_jaw_{'n' if sign < 0 else 'p'}", type="box", size=(length, jaw, jaw_h / 2),
             pos=centre.round(6), **common)


def build(config, asset_dir=None, hand="sharpa"):
    """Compose the frozen RAM scene with the selected genuine hand on the six-axis wrist stage."""
    hand_id = hands.canonical(hand)
    folder = Path(
        asset_dir
        or os.environ.get("DEXHAND_ASSET_DIR")
        or Path(__file__).resolve().parents[4] / "images/dexhand/assets/hand"
    )
    root = ET.parse(folder / "right_hand.xml").getroot()
    root.set("model", hands.info(hand_id)["model"] + " DDR4 module installation")
    root.find("compiler").set("meshdir", str((folder / "assets/right").resolve()))
    option = root.find("option")
    if option is None:
        option = node(root, "option")
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
    wrist = node(world, "body", name="wrist_stage", pos=config["wrist_base"])
    node(wrist, "inertial", pos=(0, 0, 0), mass=0.01, diaginertia=(0.00001,) * 3)
    hand_body.set("quat", " ".join(map(str, config["hand_mount_quat"])))
    wrist.append(hand_body)
    ranges = config["wrist_ranges"]
    for i, name in enumerate(("x", "y", "z", "rx", "ry", "rz")):
        axis = [int(i % 3 == j) for j in range(3)]
        wrist.insert(
            i,
            ET.Element(
                "joint",
                name="wrist_" + name,
                type="slide" if i < 3 else "hinge",
                axis=" ".join(map(str, axis)),
                range=" ".join(map(str, ranges[i])),
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

    # ---------------------------------------------------------------- source scene (accepted T28 geometry)
    verify_assets()
    source = ET.parse(ASSETS / "t28_scene.xml").getroot()
    existing = {(c.tag, c.get("name")) for c in assets}
    for item in source.find("asset"):
        if item.get("name", "").startswith(("l_hand_", "r_hand_")) or (item.tag, item.get("name")) in existing:
            continue
        item = copy.deepcopy(item)
        if item.tag == "texture" and item.get("file"):
            item.set("file", str((ASSETS / Path(item.get("file")).name).resolve()))
        assets.append(item)
    node(assets, "material", name="foam", rgba=(0.78, 0.42, 0.50, 1), specular=0.05, shininess=0.1)
    src_world = source.find("worldbody")
    for item in src_world:
        item = copy.deepcopy(item)
        name = item.get("name", "")
        if item.tag == "body" and name == "socket_3":
            _socket3(item, config)
        elif item.tag == "body" and name == "dimm":
            item.set("pos", " ".join(map(str, config["dimm_initial_pos"])))
            item.set("quat", " ".join(map(str, config["dimm_initial_quat"])))
            for g in item.iter("geom"):
                if g.get("contype") != "0":
                    g.set("condim", "4")
                    g.set("friction", "0.8 0.005 0.0001")
        elif item.tag == "light":
            continue
        world.append(item)
    _holder(world, config)
    tendon = root.find("tendon")
    if tendon is None:
        tendon = node(root, "tendon")
    spring = node(tendon, "spatial", name="latch_toggle_spring", stiffness=config["latch_toggle_stiffness"],
                  springlength=0, damping=0.0, width=0.0002, rgba=(0, 0, 0, 0))
    node(spring, "site", site="latch_spring_site")
    node(spring, "site", site="latch_anchor_site")
    contact = root.find("contact")
    if contact is None:
        contact = node(root, "contact")
    for exclude in source.find("contact"):
        contact.append(copy.deepcopy(exclude))

    # ---------------------------------------------------------------- lights, cameras, rendering
    node(world, "light", pos=(0.3, -0.8, 2.1), dir=(0.1, 0.4, -1), diffuse=(0.75, 0.74, 0.70), castshadow="true")
    node(world, "light", pos=(1.2, 0.8, 1.8), dir=(-0.4, -0.2, -1), diffuse=(0.45, 0.47, 0.50), castshadow="false")
    node(world, "light", pos=(0.58, 0.0, 1.35), dir=(0, 0, -1), diffuse=(0.35, 0.35, 0.35), castshadow="false")
    for name, (pos, target, fovy) in config["cameras"].items():
        node(world, "camera", name=name, pos=pos, xyaxes=look_at(pos, target), fovy=fovy)
    v = root.find("visual")
    if v is None:
        v = node(root, "visual")
    for child in list(v):
        v.remove(child)
    node(v, "global", offwidth=1280, offheight=720)
    node(v, "quality", shadowsize=4096, offsamples=4)
    node(v, "headlight", ambient=(0.30, 0.30, 0.30), diffuse=(0.45, 0.45, 0.45), specular=(0.10, 0.10, 0.10))
    node(v, "map", znear=0.002)
    xml = ET.tostring(root, encoding="unicode")
    return mujoco.MjModel.from_xml_string(xml), xml
