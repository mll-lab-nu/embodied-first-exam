"""MuJoCo scene for paper_staple: the T36 desk, NOVUS B2 envelope stapler, three A5 sheets and a hand on a wrist stage.

Geometry provenance: scene-expansion T36 (``stapler_meta_delivery_polish_r1_trajectory_r1``): desk, stapler base/handle
shells, anvil, magazine, driver blade and A5 sheets keep the source dimensions; the blue shells and anvil walls are
loaded from ``assets/*.obj`` (sha256 in ``assets/manifest.json``). Physics simplifications (declared in the README):
sheets are 0.5 mm rigid plates; the magazine is rigid with the base; the handle and driver blade turn on one passive
spring-returned hinge whose bottom stop puts the blade on a 3-sheet stack lying on the anvil.
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

# Stapler part frame (source legacy_geometry.py): base origin BASE, handle pivot PIVOT relative to BASE.
PIVOT = np.array([-0.052, 0.0, 0.020])
MAGAZINE = np.array([-0.052, 0.0, 0.009])
BLADE_LOCAL = np.array([0.115, 0.0, 0.0195])  # driver blade centre in the handle frame
BLADE_HALF = np.array([0.00028, 0.0065, 0.0065])
STAPLE_LOCAL = np.array([0.063, 0.0, 0.012])  # staple position on the anvil top (base frame)
ANVIL_TOP = 0.012  # anvil support height above the base origin
STOP_X = 0.052  # paper stop plate centre (base frame); its front face is the stack corner's seat


def node(parent, tag, **attributes):
    def value(x):
        if isinstance(x, (tuple, list, np.ndarray)):
            return " ".join(f"{float(v):.12g}" for v in x)
        return str(x)

    return ET.SubElement(parent, tag, {k: value(v) for k, v in attributes.items()})


def look_at(pos, target):
    """Camera x and y axes (MuJoCo ``xyaxes``) looking from ``pos`` at ``target`` with world z up."""
    f = np.asarray(target, float) - np.asarray(pos, float)
    f /= np.linalg.norm(f)
    x = np.cross(f, [0.0, 0.0, 1.0])
    x /= np.linalg.norm(x)
    y = np.cross(x, f)
    return np.r_[x, y]


def verify_assets():
    manifest = json.loads((ASSETS / "manifest.json").read_text())
    for name, expected in manifest["files"].items():
        raw = (ASSETS / name).read_bytes()
        if len(raw) != expected["bytes"] or hashlib.sha256(raw).hexdigest() != expected["sha256"]:
            raise RuntimeError(f"paper_staple asset integrity failure: {name}")
    return manifest


def blade_bottom(theta, config):
    """World z of the lowest driver-blade point at head angle ``theta`` (positive closes the head)."""
    lows = []
    for sx in (-1, 1):
        x = BLADE_LOCAL[0] + sx * BLADE_HALF[0]
        z = BLADE_LOCAL[2] - BLADE_HALF[2]
        lows.append(-x * np.sin(theta) + z * np.cos(theta))
    return config["stapler"]["pos"][2] + PIVOT[2] + min(lows)


def head_stop(config):
    """Bottom-stop angle: the blade bottom sits ``stop_margin_m`` inside the top of a 3-sheet stack on the anvil."""
    target = (config["stapler"]["pos"][2] + ANVIL_TOP + len(config["sheets"]) * config["sheet"]["thickness"]
              - config["head"]["stop_margin_m"])
    lo, hi = 0.0, 0.5
    for _ in range(80):
        mid = (lo + hi) / 2
        if blade_bottom(mid, config) > target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _materials(assets):
    node(assets, "texture", name="studio_sky", type="skybox", builtin="gradient", width=256, height=256,
         rgb1=(0.80, 0.82, 0.82), rgb2=(0.93, 0.92, 0.88))
    node(assets, "texture", name="desk_wood", type="2d", builtin="flat", width=512, height=512,
         rgb1=(0.46, 0.35, 0.26), rgb2=(0.43, 0.32, 0.24), mark="random", random=0.08, markrgb=(0.40, 0.30, 0.22))
    node(assets, "material", name="desk", texture="desk_wood", texrepeat=(3, 3), rgba=(1, 1, 1, 1), specular=0.15,
         shininess=0.2, reflectance=0.02)
    node(assets, "material", name="blue", rgba=(0.06, 0.18, 0.42, 1), specular=0.7, shininess=0.8, reflectance=0.06)
    node(assets, "material", name="steel", rgba=(0.72, 0.76, 0.80, 1), specular=0.9, shininess=0.9, reflectance=0.2)
    node(assets, "material", name="rubber", rgba=(0.035, 0.036, 0.037, 1), specular=0.1, shininess=0.1)
    node(assets, "material", name="paper", rgba=(0.965, 0.955, 0.915, 1), specular=0.05, shininess=0.05)
    node(assets, "material", name="ink", rgba=(0.16, 0.18, 0.16, 1), specular=0.0)
    node(assets, "material", name="floor", rgba=(0.62, 0.63, 0.60, 1), specular=0.05)
    for name in ("stapler_base_shell", "stapler_handle_shell", "anvil_wall_right", "anvil_wall_left"):
        node(assets, "mesh", name=name, file=str((ASSETS / f"{name}.obj").resolve()))


def _part(parent, name, kind, size, pos, material, friction=(0.6, 0.005, 0.0001), **kw):
    return node(parent, "geom", name=name, type=kind, size=size, pos=pos, material=material, friction=friction,
                solref=(0.004, 1), solimp=(0.95, 0.99, 0.0005), **kw)


def _visual(parent, name, kind, size, pos, material, **kw):
    return node(parent, "geom", name=name, type=kind, size=size, pos=pos, material=material, contype=0,
                conaffinity=0, density=0, group=2, **kw)


def add_stapler(world, config):
    stop = head_stop(config)
    cfg = config["stapler"]
    base = node(world, "body", name="stapler_base", pos=cfg["pos"], euler=(0, 0, cfg["yaw"]))
    node(base, "freejoint", name="stapler_free")
    # base + rigid magazine: 0.075 kg + 0.045 kg (source component masses)
    node(base, "inertial", pos=(0.0, 0, 0.008), mass=0.120, diaginertia=(1.6e-5, 1.9e-4, 2.0e-4))
    node(base, "geom", name="stapler_base_shell", type="mesh", mesh="stapler_base_shell", material="blue",
         density=0, friction=(0.6, 0.005, 0.0001), solref=(0.004, 1), solimp=(0.95, 0.99, 0.0005))
    _part(base, "rubber_sole", "box", (0.057, 0.012, 0.0015), (0, 0, -0.0015), "rubber", friction=(1.0, 0.005, 0.0001),
          density=0)
    af = (config.get("anvil_friction", 0.5), 0.005, 0.0001)
    _part(base, "anvil_lower_plate", "box", (0.011, 0.013, 0.001), (0.060, 0, 0.009), "steel", density=0, friction=af)
    for sign, label in ((-1, "right"), (1, "left")):
        node(base, "geom", name=f"anvil_wall_{label}", type="mesh", mesh=f"anvil_wall_{label}", material="steel",
             density=0, friction=af, solref=(0.004, 1), solimp=(0.95, 0.99, 0.0005))
        _part(base, f"anvil_clinch_ramp_{label}", "box", (0.010, 0.0020, 0.00035), (0.060, sign * 0.0053, 0.0103),
              "steel", density=0, quat=(0.9238795, sign * 0.3826834, 0, 0), friction=af)
    # Paper insertion stop (depth guide) behind the anvil: the stack corner is fed against it, which also squares
    # the sheets' leading edges; it sets the staple 10.5 mm from the edges.
    _part(base, "paper_stop", "box", (0.0005, 0.012, 0.005), (STOP_X, 0, 0.012), "steel", density=0, friction=af)
    _part(base, "rear_pivot_bracket", "box", (0.009, 0.013, 0.010), (-0.052, 0, 0.013), "steel", density=0)
    m = MAGAZINE
    for sign, label in ((-1, "right"), (1, "left")):
        _part(base, f"magazine_side_{label}", "box", (0.054, 0.0005, 0.004), m + (0.054, sign * 0.008, 0.013),
              "steel", density=0)
    _part(base, "magazine_floor", "box", (0.049, 0.0075, 0.0005), m + (0.049, 0, 0.009), "steel", density=0)
    _part(base, "front_driver_guide", "box", (0.00035, 0.0085, 0.004), m + (0.1158, 0, 0.014), "steel", density=0)
    _visual(base, "feed_tab", "box", (0.0058, 0.0055, 0.001), m + (0.102 + 0.014, 0, 0.018), "steel")
    _visual(base, "staple_strip", "box", (0.030, 0.0064, 0.0009), m + (0.082, 0, 0.0105), "steel")
    for i in range(18):
        a = i * 2 * np.pi / 6
        z = 0.013 + i * 0.00070
        node(base, "geom", name=f"return_coil_{i}", type="capsule",
             fromto=(-0.025 + 0.004 * np.cos(a), 0.004 * np.sin(a), z, -0.025 + 0.004 * np.cos(a + 0.8),
                     0.004 * np.sin(a + 0.8), z + 0.00045),
             size=(0.00035,), material="steel", density=0, contype=0, conaffinity=0, group=2)
    head = node(base, "body", name="stapler_head", pos=PIVOT)
    h = config["head"]
    node(head, "joint", name="head_hinge", type="hinge", axis=(0, 1, 0), range=(0.0, stop), limited="true",
         stiffness=h["stiffness"], springref=-h["preload_rad"], damping=h["damping"], frictionloss=h["frictionloss"],
         armature=1e-5, solreflimit=(0.004, 1))
    node(head, "inertial", pos=(0.054, 0, 0.027), mass=0.053, diaginertia=(9e-6, 5e-5, 5.9e-5))
    node(head, "geom", name="stapler_handle_shell", type="mesh", mesh="stapler_handle_shell", material="blue",
         density=0, friction=(0.8, 0.005, 0.0001), solref=(0.004, 1), solimp=(0.95, 0.99, 0.0005))
    _part(head, "driver_blade", "box", BLADE_HALF, BLADE_LOCAL, "steel", density=0)
    return stop


def add_sheets(world, config):
    s = config["sheet"]
    hx, hy = s["half"]
    t = s["thickness"]
    z0 = config["table_z"] + t / 2
    for i, sheet in enumerate(config["sheets"]):
        if "pose" in sheet:  # settled rest pose (tools/settle_sheets.py)
            b = node(world, "body", name=f"sheet_{i}", pos=sheet["pose"][:3], quat=sheet["pose"][3:])
        else:
            b = node(world, "body", name=f"sheet_{i}", pos=(*sheet["center"], z0 + i * t * 1.0004),
                     euler=(0, 0, sheet["yaw"]))
        node(b, "freejoint", name=f"sheet_{i}_free")
        mass = s["mass"]
        node(b, "inertial", pos=(0, 0, 0), mass=mass,
             diaginertia=(mass * (2 * hy) ** 2 / 12, mass * (2 * hx) ** 2 / 12, mass * ((2 * hx) ** 2 + (2 * hy) ** 2) / 12))
        node(b, "geom", name=f"sheet_{i}_plate", type="box", size=(hx, hy, t / 2), material="paper", density=0,
             friction=(s["friction"], 0.002, 0.0001), condim=4, solref=(0.004, 1), solimp=(0.95, 0.99, 0.0003))
        # printed text lines (visual only), as in the source sheets
        for j in range(9):
            _visual(b, f"sheet_{i}_print_{j}", "box", (0.025, 0.00020, 0.000003),
                    (0.025, 0.045 - j * 0.008, t / 2 + 0.000004), "ink")


def add_desk(world, config):
    cx, cy = config["desk"]["center"]
    hx, hy = config["desk"]["half"]
    th = config["desk"]["thickness"]
    top = config["table_z"]
    node(world, "geom", name="floor", type="plane", size=(3, 3, 0.05), material="floor")
    node(world, "geom", name="desk_top", type="box", size=(hx, hy, th / 2), pos=(cx, cy, top - th / 2),
         material="desk", friction=(config.get("desk_friction", 0.5), 0.005, 0.0001), solref=(0.004, 1),
         solimp=(0.95, 0.99, 0.0005))
    leg_h = (top - th) / 2
    for i, x in enumerate((cx - hx + 0.05, cx + hx - 0.05)):
        for j, y in enumerate((cy - hy + 0.05, cy + hy - 0.05)):
            node(world, "geom", name=f"desk_leg_{i}{j}", type="box", size=(0.023, 0.023, leg_h),
                 pos=(x, y, leg_h), material="desk", group=1)


def build(config, asset_dir=None, hand="sharpa"):
    """Compose the frozen scene with the Marvin arm rig carrying the selected genuine hand (right arm active)."""
    hand_id = hands.canonical(hand)
    verify_assets()
    folder = Path(
        asset_dir
        or os.environ.get("DEXHAND_ASSET_DIR")
        or Path(__file__).resolve().parents[4] / "images/dexhand/assets/hand"
    )
    root = ET.parse(folder / "right_hand.xml").getroot()
    root.set("model", hands.info(hand_id)["model"] + " paper stapling")
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
    hand_body = world.find("body")
    # the family's Sharpa tweaks on the right Wave, before mounting (the rig mirrors them onto the parked left Wave)
    for a in actuator:
        if a.tag == "general":
            bias = [float(v) for v in a.get("biasprm", "0 0 0").split()]
            bias[2] = -0.9
            a.set("biasprm", " ".join(map(str, bias)))
    for g in hand_body.iter("geom"):
        if "fingertip_collision" in g.get("name", ""):
            g.set("friction", "1.5 .005 .0001")
    arm_rig = _arm_rig_module()
    sibling = folder.parent / "wuji_v2_2"
    marvin = config["marvin"]
    arm_rig.mount_marvin(root, marvin["base_pos"], marvin["base_yaw"], hand=hand_id, active=("right",),
                         mount_names={"right": "wrist_stage"}, sharpa_folder=folder,
                         wuji_folder=sibling if (sibling / "mjcf/right.xml").is_file() else None)
    assets, world, actuator = root.find("asset"), root.find("worldbody"), root.find("actuator")
    _materials(assets)
    add_desk(world, config)
    stop = add_stapler(world, config)
    add_sheets(world, config)
    contact = root.find("contact")
    if contact is None:
        contact = node(root, "contact")
    # The handle wraps the rigid magazine/base around the shared pivot (as in the source scene).
    node(contact, "exclude", body1="stapler_base", body2="stapler_head")
    # Paper on varnished wood / chrome steel slides more easily than paper on paper (explicit pair friction).
    for i in range(len(config["sheets"])):
        for other, mu in [("desk_top", config.get("desk_friction", 0.25))] + [
                (g, config.get("anvil_friction", 0.2)) for g in ("anvil_lower_plate", "anvil_wall_right",
                                                                 "anvil_wall_left", "anvil_clinch_ramp_right",
                                                                 "anvil_clinch_ramp_left", "paper_stop")]:
            node(contact, "pair", geom1=f"sheet_{i}_plate", geom2=other, condim=4, friction=(mu, mu, 0.002, 0.0001, 0.0001),
                 solref=(0.004, 1), solimp=(0.95, 0.99, 0.0003))
    node(world, "light", name="key", pos=(1.2, -0.7, 2.0), dir=(-0.35, 0.45, -1), diffuse=(0.80, 0.77, 0.70),
         castshadow="true")
    node(world, "light", name="fill", pos=(0.2, 0.6, 1.8), dir=(0.3, -0.4, -1), diffuse=(0.40, 0.42, 0.46),
         castshadow="false")
    for name, pos, target, fovy in (("overview", (1.42, 0.62, 1.38), (0.66, -0.12, 0.84), 50),
                                    ("closeup", (1.02, 0.30, 1.02), (0.68, -0.06, 0.79), 42),
                                    ("throat", (0.80, 0.12, 0.89), (0.625, -0.095, 0.80), 40)):
        node(world, "camera", name=name, pos=pos, xyaxes=look_at(pos, target), fovy=fovy)
    v = root.find("visual")
    if v is None:
        v = node(root, "visual")
    node(v, "global", offwidth=1280, offheight=720)
    node(v, "quality", shadowsize=4096, offsamples=4)
    node(v, "headlight", ambient=(0.30, 0.30, 0.30), diffuse=(0.45, 0.45, 0.45), specular=(0.10, 0.10, 0.10))
    node(v, "map", znear=0.005)
    xml = ET.tostring(root, encoding="unicode")
    model = mujoco.MjModel.from_xml_string(xml)
    return model, xml, stop
