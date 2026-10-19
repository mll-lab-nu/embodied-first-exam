"""Jam jar with a contact-only twist-off (lug) lid and one dexterous hand on a six-axis wrist stage.

Scene: the T14 "Open a jam jar" objects (real-size 297 ml jam jar, 67 mm body, 110 mm tall, 550 g filled; red
steel 64.8 mm twist-off lid, 32 g) on a plain worktop. Both objects are free bodies. The thread is contact geometry
only: four inclined glass ramps on the jar neck and four inward steel lugs on the lid skirt. With the lid seated,
each lug sits under a ramp, so the lid cannot be lifted; turning the lid counter-clockwise (seen from above) slides
the lugs along the rising ramps until they pass the ramp ends (about 1.05 rad) into the gaps, where the lid lifts
off freely. Turning clockwise jams the lugs against the descending ramps (tightening). Turning past the gap runs the
lugs into the next ramp's lead end (a stop at about 1.32 rad) unless the lid is lifted. No joint, weld, actuator or
scripted change acts on the jar or the lid.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
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


def _arm_module():
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


arm_rig = _arm_module()
ASSETS = Path(__file__).resolve().with_name("assets")

# ---------------------------------------------------------------------------------------------- jar geometry
JAR_HEIGHT = 0.110          # glass height, base to rim (m)
BODY_RADIUS = 0.0335        # 67 mm body
NECK_RADIUS = 0.0283        # finish (neck) contact radius: 0.8 mm radial play to the lugs, so a tilted lid cannot bind
THREAD_INNER, THREAD_OUTER = 0.0283, 0.0316   # radial extent of the glass thread ramps
RIM_Z = 0.110               # rim top, jar frame
LID_RADIUS = 0.0324         # 64.8 mm lid
LID_SEAT_Z = 0.1009         # lid body origin above the jar origin when seated (liner resting on the rim)
LUG_RADIUS = 0.0304
LUG_HALF = (0.0013, 0.0015, 0.0008)   # radial, tangential, vertical half sizes of a lid lug
LUG_TOP = -0.0001           # lug top in the lid frame
THREAD_CLEARANCE = 0.0003   # seated lug top to ramp underside (m)
THREAD_RUN = 1.00           # rising run counter-clockwise of the seated lug (rad)
THREAD_RISE = 0.003         # rise of the run (m)
LEAD_START = 0.06           # the lead (tightening) part starts this far clockwise of the seated lug (rad)
LEAD_SPAN = 0.20            # lead length (rad); it drops LEAD_DROP below the clearance line (clockwise turns jam)
LEAD_DROP = 0.0015
THREAD_THICKNESS = 0.0020
LEAD_SEGMENTS, RUN_SEGMENTS = 2, 6
LUG_ANGLE0 = 0.25           # seated lug angle (rad) in the jar frame, plus k * pi / 2
LUG_HALF_ANGLE = LUG_HALF[1] / LUG_RADIUS
RELEASE_ANGLE = THREAD_RUN + LUG_HALF_ANGLE                              # lugs clear the ramp ends
STOP_ANGLE = math.pi / 2 - (LEAD_START + LEAD_SPAN) - LUG_HALF_ANGLE      # next ramp's lead end (when not lifted)

STEEL_FRICTION = (0.25, 0.00002, 0.000005)
THREAD_SOLREF = (0.004, 1)
THREAD_SOLIMP = (0.98, 0.999, 0.0001)


def vec(value):
    return " ".join(f"{float(x):.17g}" for x in value)


def node(parent, tag, **attrs):
    return ET.SubElement(
        parent, tag, {k: vec(v) if isinstance(v, (tuple, list, np.ndarray)) else str(v) for k, v in attrs.items()}
    )


def contact_geom(parent, **attrs):
    values = dict(friction=STEEL_FRICTION, condim=3, solref=THREAD_SOLREF, solimp=THREAD_SOLIMP)
    values.update(attrs)
    return node(parent, "geom", **values)


def ring(parent, prefix, radius, halfheight, z, width, segments=48, collision=True, **attrs):
    """A closed ring of box segments (collision rings are the contact surfaces of rims and skirts)."""
    for i in range(segments):
        angle = 2 * math.pi * (i + 0.5) / segments
        values = dict(
            name=f"{prefix}_{i}",
            type="box",
            size=(width / 2, radius * math.tan(math.pi / segments) + 0.000015, halfheight),
            pos=(radius * math.cos(angle), radius * math.sin(angle), z),
            quat=(math.cos(angle / 2), 0, 0, math.sin(angle / 2)),
            mass=0,
            contype=int(collision),
            conaffinity=int(collision),
            friction=(0.3, 0.00002, 0.000005),
            condim=3,
            solref=THREAD_SOLREF,
            solimp=THREAD_SOLIMP,
        )
        values.update(attrs)
        node(parent, "geom", **values)


def ramp_underside(u):
    """Underside height (jar frame) of a ramp at ``u`` rad counter-clockwise of its seated lug."""
    base = LID_SEAT_Z + LUG_TOP + THREAD_CLEARANCE
    if u >= -LEAD_START:
        return base + THREAD_RISE * max(u, 0.0) / THREAD_RUN
    return base - LEAD_DROP * (-LEAD_START - u) / LEAD_SPAN


def ramp_breaks():
    lead = np.linspace(-LEAD_START - LEAD_SPAN, -LEAD_START, LEAD_SEGMENTS + 1)
    run = np.linspace(0.0, THREAD_RUN, RUN_SEGMENTS + 1)
    return np.r_[lead, run]


def verify_assets(names=("continuous-glass.obj", "label.obj", "label.png")):
    """Check the copied visual assets against ``assets/manifest.json`` (sha256 + size) before use."""
    manifest = json.loads((ASSETS / "manifest.json").read_text())
    for name in names:
        raw = (ASSETS / name).read_bytes()
        expected = manifest["files"][name]
        if len(raw) != expected["bytes"] or hashlib.sha256(raw).hexdigest() != expected["sha256"]:
            raise RuntimeError(f"jar_lid_open asset integrity failure: {name}")


def add_jar(root, position):
    verify_assets()
    world, asset = root.find("worldbody"), root.find("asset")
    node(asset, "material", name="jar_glass", rgba=(0.80, 0.90, 0.88, 0.28), specular=0.9, shininess=0.9,
         reflectance=0.08)
    node(asset, "material", name="jar_glass_thread", rgba=(0.80, 0.90, 0.88, 0.45), specular=0.9, shininess=0.9)
    node(asset, "material", name="lid_metal", rgba=(0.74, 0.10, 0.06, 1), specular=0.7, shininess=0.75,
         reflectance=0.12)
    node(asset, "material", name="lid_inner", rgba=(0.62, 0.62, 0.60, 1), specular=0.4, shininess=0.4)
    node(asset, "material", name="jam", rgba=(0.40, 0.02, 0.04, 1), specular=0.35, shininess=0.5)
    node(asset, "material", name="liner", rgba=(0.95, 0.90, 0.77, 1), specular=0.1)
    node(asset, "mesh", name="continuous_glass", file=str((ASSETS / "continuous-glass.obj").resolve()))
    node(asset, "mesh", name="printed_label_mesh", file=str((ASSETS / "label.obj").resolve()))
    node(asset, "texture", name="jam_label", type="2d", file=str((ASSETS / "label.png").resolve()))
    node(asset, "material", name="printed_jam_label", texture="jam_label", rgba=(1, 1, 1, 1), specular=0.15)

    jar = node(world, "body", name="jar", pos=position)
    node(jar, "freejoint", name="jar_free")
    # Filled 297 ml jar: glass plus jam as one rigid body (the jam is not simulated as a fluid).
    node(jar, "inertial", pos=(0, 0, 0.051), mass=0.55, diaginertia=(0.00065, 0.00065, 0.00031))
    contact_geom(jar, name="jar_body_collision", type="cylinder", size=(BODY_RADIUS, 0.044), pos=(0, 0, 0.049),
                 rgba=(0, 0, 0, 0), group=3, mass=0, friction=(0.7, 0.0001, 0.00001))
    # Twelve contact pads on the base ring (glass on the worktop); the visible base is display only.
    for i in range(12):
        a = 2 * math.pi * i / 12
        node(jar, "geom", name=f"jar_foot_{i}", type="sphere", size=(0.0015,),
             pos=(0.0295 * math.cos(a), 0.0295 * math.sin(a), 0.0015), rgba=(0, 0, 0, 0), group=3, mass=0,
             friction=(0.8, 0.002, 0.0001), condim=3, solref=(0.004, 1), solimp=(0.95, 0.99, 0.0005))
    node(jar, "geom", name="jar_base_visual", type="cylinder", size=(0.031, 0.0025), pos=(0, 0, 0.0028),
         material="jar_glass", contype=0, conaffinity=0, mass=0, group=2)
    node(jar, "geom", name="continuous_glass_visual", type="mesh", mesh="continuous_glass", material="jar_glass",
         contype=0, conaffinity=0, mass=0, group=2)
    node(jar, "geom", name="printed_label_visual", type="mesh", mesh="printed_label_mesh",
         material="printed_jam_label", contype=0, conaffinity=0, mass=0, group=2)
    node(jar, "geom", name="jam_fill", type="cylinder", size=(0.0305, 0.040), pos=(0, 0, 0.046), material="jam",
         contype=0, conaffinity=0, mass=0, group=2)
    node(jar, "geom", name="jam_top", type="cylinder", size=(0.0285, 0.004), pos=(0, 0, 0.088), material="jam",
         contype=0, conaffinity=0, mass=0, group=2)
    # Shoulder and finish (neck) contact solids; the hollow glass is shown by the continuous visual mesh.
    contact_geom(jar, name="jar_shoulder", type="cylinder", size=(0.0319, 0.0045), pos=(0, 0, 0.094),
                 rgba=(0, 0, 0, 0), group=3, mass=0, friction=(0.3, 0.00002, 0.000005))
    contact_geom(jar, name="jar_neck", type="cylinder", size=(NECK_RADIUS, 0.006), pos=(0, 0, RIM_Z - 0.006),
                 rgba=(0, 0, 0, 0), group=3, mass=0, friction=(0.3, 0.00002, 0.000005))
    for k in range(4):
        phase = LUG_ANGLE0 + k * math.pi / 2
        breaks = ramp_breaks()
        for i, (u0, u1) in enumerate(zip(breaks[:-1], breaks[1:])):
            z0, z1 = ramp_underside(u0), ramp_underside(u1)
            # One inclined glass box per segment (box-box contacts give robust face normals for thin lugs).
            # The thread sits inside the steel skirt: it collides with the lid lugs only (collision bit 2), so a
            # compliant fingertip pad pressed into the thin skirt cannot reach it.
            centre, half_arc = phase + (u0 + u1) / 2, (u1 - u0) / 2
            rc = (THREAD_INNER + THREAD_OUTER) / 2
            slope = math.atan2(z1 - z0, rc * (u1 - u0))
            qz = np.array([math.cos(centre / 2), 0, 0, math.sin(centre / 2)])
            qx = np.array([math.cos(slope / 2), math.sin(slope / 2), 0, 0])
            quat = np.empty(4)
            mujoco.mju_mulQuat(quat, qz, qx)
            contact_geom(jar, name=f"glass_thread_{k}_{i}", type="box",
                         size=((THREAD_OUTER - THREAD_INNER) / 2, rc * math.sin(half_arc) + 0.0002,
                               THREAD_THICKNESS / 2),
                         pos=(rc * math.cos(centre), rc * math.sin(centre), (z0 + z1) / 2 + THREAD_THICKNESS / 2),
                         quat=quat, material="jar_glass_thread", mass=0, contype=2, conaffinity=2)

    lid = node(world, "body", name="lid", pos=np.asarray(position) + (0, 0, LID_SEAT_Z))
    node(lid, "freejoint", name="lid_free")
    node(lid, "inertial", pos=(0, 0, 0.007), mass=0.032, diaginertia=(0.000009, 0.000009, 0.000016))
    contact_geom(lid, name="lid_top", type="cylinder", size=(LID_RADIUS, 0.0004), pos=(0, 0, 0.0106),
                 material="lid_metal", mass=0)
    ring(lid, "lid_skirt", LID_RADIUS - 0.00025, 0.006, 0.0042, 0.0005, segments=24, rgba=(0, 0, 0, 0), group=3)
    node(lid, "geom", name="lid_skirt_visual", type="cylinder", size=(LID_RADIUS, 0.006), pos=(0, 0, 0.0042),
         material="lid_metal", contype=0, conaffinity=0, mass=0, group=2)
    # Visual rolled edge and an orientation stripe that makes the rotation visible.
    node(lid, "geom", name="lid_rolled_edge", type="cylinder", size=(LID_RADIUS + 0.0003, 0.0009),
         pos=(0, 0, -0.0012), material="lid_metal", contype=0, conaffinity=0, mass=0, group=2)
    node(lid, "geom", name="lid_panel", type="cylinder", size=(LID_RADIUS - 0.004, 0.00025), pos=(0, 0, 0.01115),
         material="lid_metal", contype=0, conaffinity=0, mass=0, group=2)
    node(lid, "geom", name="cap_orientation_print", type="box", size=(0.0014, 0.014, 0.00004),
         pos=(0.009, 0, 0.01145), rgba=(0.96, 0.92, 0.84, 1), contype=0, conaffinity=0, mass=0, group=2)
    for i in range(4):
        angle = LUG_ANGLE0 + i * math.pi / 2
        contact_geom(lid, name=f"lid_lug_{i}", type="box", size=LUG_HALF,
                     pos=(LUG_RADIUS * math.cos(angle), LUG_RADIUS * math.sin(angle), LUG_TOP - LUG_HALF[2]),
                     quat=(math.cos(angle / 2), 0, 0, math.sin(angle / 2)), material="lid_inner", mass=0,
                     contype=3, conaffinity=3)
    # Sealing liner under the lid panel: rests on the rim when the lid is seated.
    contact_geom(lid, name="lid_liner", type="cylinder", size=(0.0295, 0.0004), pos=(0, 0, 0.0095),
                 material="liner", mass=0, friction=(0.3, 0.00002, 0.000005))
    return jar, lid


# ---------------------------------------------------------------------------------------------- robot
def robot_bodies(model):
    """(hand body ids, arm + stand body ids) of the Marvin rig in a compiled model (both hands count as hands)."""
    hand = set(arm_rig.hand_body_ids(model, "left")) | set(arm_rig.hand_body_ids(model, "right"))
    return hand, set(arm_rig.robot_body_ids(model))


def look_at(pos, target):
    pos, target = np.asarray(pos, float), np.asarray(target, float)
    forward = target - pos
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, (0, 0, 1))
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    return np.r_[right, up]


def build(config, asset_dir=None, hand="sharpa"):
    """Compose the frozen scene with the selected genuine hand on the six-axis wrist stage."""
    hand_id = hands.canonical(hand)
    folder = Path(
        asset_dir
        or os.environ.get("DEXHAND_ASSET_DIR")
        or Path(__file__).resolve().parents[4] / "images/dexhand/assets/hand"
    )
    root = ET.parse(folder / "right_hand.xml").getroot()
    root.set("model", hands.info(hand_id)["model"] + " jam jar lid opening")
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
    world, actuator = root.find("worldbody"), root.find("actuator")
    hand_body = world.find("body")
    # The family's Sharpa tweaks (as on the old wrist stage), applied before mounting so the mirrored left Wave gets
    # them too: dissipative finger velocity feedback and grippy fingertip pads.
    for a in actuator:
        if a.tag == "general":
            bias = [float(v) for v in a.get("biasprm", "0 0 0").split()]
            bias[2] = -0.9
            a.set("biasprm", " ".join(map(str, bias)))
    for g in hand_body.iter("geom"):
        if "fingertip_collision" in g.get("name", ""):
            g.set("friction", "1.5 .005 .0001")
    sibling = folder.parent / "wuji_v2_2"
    marvin = config["marvin"]
    # Tianji Marvin stand + both 7-DoF arms; the right arm carries the working hand under the fixed body
    # "wrist_stage" (the checker's hand root), the left arm is parked (arm_rig.PARK) with its hand.
    arm_rig.mount_marvin(root, marvin["base_pos"], marvin["base_yaw"], hand=hand_id, active=("right",),
                         mount_names={"right": "wrist_stage"}, sharpa_folder=folder,
                         wuji_folder=sibling if (sibling / "mjcf/right.xml").is_file() else None)
    assets = root.find("asset")

    node(assets, "texture", name="worktop_tex", type="2d", builtin="flat", width=512, height=512,
         rgb1=(0.90, 0.89, 0.86), rgb2=(0.86, 0.85, 0.82), mark="random", random=0.02, markrgb=(0.80, 0.79, 0.76))
    node(assets, "material", name="worktop_material", texture="worktop_tex", texrepeat=(4, 4), reflectance=0.03,
         specular=0.2)
    node(assets, "texture", name="studio_sky", type="skybox", builtin="gradient", width=256, height=256,
         rgb1=(0.62, 0.64, 0.64), rgb2=(0.86, 0.86, 0.84))
    tz = config["table_z"]
    half = config["table_half"]
    # Floor 0.1 m below the robot stand's origin: the stand's platform (z -0.099..0.104 in its frame) rests on it.
    floor_z = config["marvin"]["base_pos"][2] - 0.1
    node(world, "geom", name="floor", type="plane", size=(3, 3, 0.1), pos=(0, 0, floor_z), rgba=(0.40, 0.42, 0.41, 1))
    node(world, "geom", name="worktop", type="box", size=(half[0], half[1], 0.02), pos=(0, 0, tz - 0.02),
         material="worktop_material", friction=(0.6, 0.002, 0.0001), condim=3)
    for sx in (-1, 1):
        for sy in (-1, 1):
            node(world, "geom", name=f"table_leg_{sx}_{sy}", type="box", size=(0.02, 0.02, (tz - 0.04 - floor_z) / 2),
                 pos=(sx * (half[0] - 0.05), sy * (half[1] - 0.05), (tz - 0.04 + floor_z) / 2),
                 rgba=(0.32, 0.28, 0.22, 1), contype=0, conaffinity=0)
    add_jar(root, (*config["jar_xy"], tz))
    jar = np.array([*config["jar_xy"], tz])
    node(world, "light", name="key", pos=jar + (0.5, -0.6, 1.1), dir=(-0.4, 0.5, -1), diffuse=(0.75, 0.72, 0.66),
         castshadow="true")
    node(world, "light", name="fill", pos=jar + (-0.5, 0.5, 0.9), dir=(0.5, -0.4, -1), diffuse=(0.40, 0.44, 0.48),
         castshadow="false")
    for name, offset, target, fovy in (
        ("overview", (0.40, -0.52, 0.32), (0.04, -0.05, 0.09), 40),
        ("closeup", (0.20, -0.26, 0.17), (0.0, 0.0, 0.09), 38),
        ("side", (0.0, -0.55, 0.12), (0.0, -0.06, 0.08), 45),
        ("wide", (1.05, -0.85, 0.75), (-0.25, 0.05, 0.12), 45),
    ):
        node(world, "camera", name=name, pos=jar + offset, xyaxes=look_at(jar + offset, jar + target), fovy=fovy)
    v = node(root, "visual")
    node(v, "global", offwidth=1280, offheight=720)
    node(v, "quality", shadowsize=4096, offsamples=4)
    node(v, "headlight", ambient=(0.32, 0.32, 0.32), diffuse=(0.45, 0.45, 0.45), specular=(0.1, 0.1, 0.1))
    xml = ET.tostring(root, encoding="unicode")
    return mujoco.MjModel.from_xml_string(xml), xml
