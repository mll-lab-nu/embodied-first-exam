"""MJCF builder for the boot-sole brushing scene (scene T29 objects) with the selected genuine hand.

Objects (all passive, contact and gravity only):
- ``boot``: the Poly Haven "Rubber Boots" left boot (CC0), free 650 g rigid body slipped sole-up onto a fixed boot-rack
  peg that stands in the collection tray. Visual = the source mesh + diffuse texture; contact with hand/brush/debris =
  the source scene's 292 convex hulls of source triangle patches; contact with the peg = an invisible interior proxy
  (footbed pad + shaft sleeve), because the visual mesh has no modelled interior lining.
- ``clod_0..5``: six free 1 g irregular dry-soil clods resting in the tread of the upward sole (friction only; no
  cohesion force, no weld).
- ``brush``: free 84 g shoe brush (beech back, 32 tufts). The bristle field touches the world through one compliant
  bristle pad (box); the 32 tufts are drawn with their fine fibres but individual fibre bending is not simulated.
- ``tray`` (floor + four walls) on the counter, the fixed ``rack`` (base + peg) inside the tray.
The hand is mounted on the right arm of the Tianji Marvin bimanual robot (``arm_rig.py``: stand, torso, two 7-DoF arms,
both hands; the left arm stays parked); the stand stands on the floor in front of the counter's -y side.
"""

from __future__ import annotations

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


def _fmt(x):
    if isinstance(x, (tuple, list, np.ndarray)):
        return " ".join(f"{float(v):.10g}" if not isinstance(v, str) else v for v in np.asarray(x).ravel().tolist())
    if isinstance(x, float):
        return f"{x:.10g}"
    return str(x)


def node(parent, tag, **attributes):
    return ET.SubElement(parent, tag, {k: _fmt(v) for k, v in attributes.items()})


def quat_of(matrix):
    """wxyz quaternion of a rotation matrix (no SciPy dependency in the runtime)."""
    q = np.empty(4)
    mujoco.mju_mat2Quat(q, np.asarray(matrix, dtype=float).ravel())
    return q


# Boot frame: source local z is the shaft axis (sole at z=0), local y runs toe (-) to heel (+). Mounted sole-up with
# the foot along world x: local (x, y, z) -> world (y, x, -z).
BOOT_ROTATION = np.array([[0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, -1.0]])


def look_at(pos, target):
    """Camera ``xyaxes`` looking from ``pos`` at ``target`` with world +z up."""
    forward = np.asarray(target, float) - np.asarray(pos, float)
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, [0.0, 0.0, 1.0])
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    return np.round(np.r_[right, up], 6)


def verify_assets(folder: Path) -> None:
    manifest = json.loads((folder / "manifest.json").read_text())
    import hashlib

    for name, digest in manifest["files"].items():
        data = (folder / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError(f"frozen task asset changed: assets/{name}")


def clod_vertices(i):
    """The source scene's irregular clod aggregate (two 7-point rings, seeded per clod), in the clod frame."""
    rng = np.random.default_rng(290 + i)
    mesh = np.array(
        [
            [np.cos(t) * r, np.sin(t) * r, z]
            for z, r in [(-0.003, 0.005), (0.003, 0.006)]
            for t in np.linspace(0, 2 * np.pi, 7, endpoint=False)
        ]
    )
    return mesh * rng.uniform(0.83, 1.13, mesh.shape)


def add_marvin_rig(root, config, hand_id, folder):
    """The Tianji Marvin stand with two 7-DoF arms (``arm_rig``): the right arm carries the working hand under the
    fixed mount body ``wrist_stage`` (the checker's hand root), the left arm hangs parked with its hand
    (``arm_rig.PARK``). The stand stands on the floor (``base_z = floor + 0.1``) beside the counter."""
    world, actuator = root.find("worldbody"), root.find("actuator")
    hand_body = world.find("body")
    # The family's Sharpa tweaks, applied before mounting so the mirrored (parked) left Wave gets them too.
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
    return arm_rig.mount_marvin(root, marvin["base_pos"], marvin["base_yaw"], hand=hand_id, active=("right",),
                                mount_names={"right": "wrist_stage"}, sharpa_folder=folder,
                                wuji_folder=sibling if (sibling / "mjcf/right.xml").is_file() else None)


def robot_parts(model):
    """(right hand bodies, other robot bodies): the working hand is the ``wrist_stage`` mount subtree; the stand,
    torso, both arms (links + flanges) and the parked left hand are the rest of the robot."""
    right = set(arm_rig.hand_body_ids(model, "right"))
    rest = set(arm_rig.robot_body_ids(model)) | set(arm_rig.hand_body_ids(model, "left"))
    return right, rest - right


def build(config, hand="sharpa", asset_dir=None):
    """Return ``(model, xml)`` for the frozen scene with the selected hand on the Marvin arm rig."""
    hand_id = hands.canonical(hand)
    folder = Path(asset_dir or hands.sharpa_dir())
    if not (folder / "right_hand.xml").is_file():
        raise FileNotFoundError(f"Sharpa Wave assets not found in {folder} (set DEXHAND_ASSET_DIR)")
    assets_dir = HERE / "assets"
    verify_assets(assets_dir)
    root = ET.parse(folder / "right_hand.xml").getroot()
    root.set("model", hands.info(hand_id)["model"] + " boot sole brushing")
    root.find("compiler").set("meshdir", str((folder / "assets/right").resolve()))
    option = root.find("option")
    option.set("timestep", _fmt(config["physics_dt"]))
    option.set("gravity", "0 0 -9.81")
    option.set("iterations", "60")
    option.set("integrator", "implicitfast")
    option.set("cone", "elliptic")
    option.set("impratio", "10")
    node(option, "flag", multiccd="enable")
    for key in root.findall("keyframe"):
        root.remove(key)
    asset, world = root.find("asset"), root.find("worldbody")

    # ------------------------------------------------------------------ hand on the Marvin arm rig
    add_marvin_rig(root, config, hand_id, folder)

    # ------------------------------------------------------------------ room, counter, tray, rack
    table_z = config["table_z"]
    node(asset, "texture", name="sky", type="skybox", builtin="gradient", rgb1=(0.66, 0.70, 0.68),
         rgb2=(0.84, 0.83, 0.77), width=256, height=256)
    node(asset, "texture", name="counter_tex", type="2d", builtin="flat", rgb1=(0.79, 0.77, 0.71), width=64,
         height=64, mark="random", random=0.04, markrgb=(0.72, 0.70, 0.64))
    node(asset, "material", name="counter_mat", texture="counter_tex", texrepeat=(8, 8), roughness=0.65)
    node(asset, "material", name="tray_mat", rgba=(0.28, 0.37, 0.33, 1), roughness=0.52)
    node(asset, "material", name="steel_mat", rgba=(0.62, 0.64, 0.66, 1), specular=0.6, shininess=0.6)
    node(asset, "material", name="beech_mat", rgba=(0.72, 0.52, 0.29, 1), specular=0.2, shininess=0.25)
    hard = dict(solref=(0.004, 1), solimp=(0.95, 0.99, 0.0005))
    node(world, "geom", name="floor", type="plane", size=(3, 3, 0.02), pos=(0, 0, 0), rgba=(0.55, 0.58, 0.56, 1),
         friction=(0.8, 0.005, 0.0001), **hard)
    c = config["counter"]
    node(world, "geom", name="counter", type="box", size=c["half"], pos=(c["center"][0], c["center"][1],
         table_z - c["half"][2]), material="counter_mat", friction=(0.7, 0.005, 0.0001), **hard)
    t = config["tray"]
    tx, ty = t["center"]
    hx, hy = t["half"]
    wall_h, wall_t, floor_t = t["wall_height"], t["wall_thickness"], t["floor_thickness"]
    # The tray is a rubber-lined basin: soft, well-damped floor contact so a falling clod does not bounce out.
    tray_kw = dict(material="tray_mat", friction=(1.0, 0.01, 0.002), condim=6, solref=(0.006, 1.2),
                   solimp=(0.9, 0.95, 0.002))
    node(world, "geom", name="tray_floor", type="box", size=(hx, hy, floor_t / 2), pos=(tx, ty, table_z + floor_t / 2),
         **tray_kw)
    for sign in (-1, 1):
        node(world, "geom", name=f"tray_side_{'n' if sign < 0 else 'p'}", type="box",
             size=(hx, wall_t / 2, wall_h / 2), pos=(tx, ty + sign * (hy - wall_t / 2), table_z + wall_h / 2), **tray_kw)
        node(world, "geom", name=f"tray_end_{'n' if sign < 0 else 'p'}", type="box",
             size=(wall_t / 2, hy - wall_t, wall_h / 2), pos=(tx + sign * (hx - wall_t / 2), ty, table_z + wall_h / 2),
             **tray_kw)
    r = config["rack"]
    floor_top = table_z + floor_t
    node(world, "geom", name="rack_base", type="cylinder", size=(r["base_radius"], r["base_half_height"]),
         pos=(r["peg_xy"][0], r["peg_xy"][1], floor_top + r["base_half_height"]), material="steel_mat",
         friction=(0.7, 0.005, 0.0001), **hard)
    peg_bottom = floor_top + 2 * r["base_half_height"]
    peg_half = (r["peg_top_z"] - peg_bottom) / 2
    # The peg touches only the boot's interior proxy (contype/conaffinity bit 2): it stands inside the shaft.
    node(world, "geom", name="rack_peg", type="box", size=(r["peg_radius"], r["peg_radius"], peg_half),
         pos=(r["peg_xy"][0], r["peg_xy"][1], peg_bottom + peg_half), material="steel_mat", contype=2,
         conaffinity=2, condim=4, friction=(0.8, 0.02, 0.0001), **hard)

    # ------------------------------------------------------------------ boot
    b = config["boot"]
    boot_assets = assets_dir / "boot"
    inspection = json.loads((boot_assets / "inspection.json").read_text())
    node(asset, "mesh", name="boot_visual_mesh", file=str((boot_assets / "left-clean.obj").resolve()))
    node(asset, "texture", name="boot_diffuse", type="2d",
         file=str((boot_assets / "textures/rubber_boots_diff_2k.png").resolve()))
    node(asset, "material", name="boot_rubber", texture="boot_diffuse", specular=0.12, shininess=0.10)
    boot = node(world, "body", name="boot", pos=b["pos"], quat=quat_of(BOOT_ROTATION))
    node(boot, "freejoint", name="boot_free")
    node(boot, "inertial", pos=(-0.002, 0.040, 0.155), mass=0.65, diaginertia=(0.0080, 0.0085, 0.0030))
    node(boot, "geom", name="boot_visual", type="mesh", mesh="boot_visual_mesh", material="boot_rubber", contype=0,
         conaffinity=0, group=2, mass=0)
    sole_kw = dict(friction=(b["friction"], 0.005, 0.0001), solref=(0.004, 1), solimp=(0.95, 0.99, 0.0005), mass=0)
    for i, filename in enumerate(inspection["collision_files"]):
        name = f"boot_patch_{i}"
        node(asset, "mesh", name=name, file=str((boot_assets / "collision" / filename).resolve()))
        node(boot, "geom", name=name, type="mesh", mesh=name, rgba=(0, 0, 0, 0), group=3, **sole_kw)
    proxy = dict(contype=2, conaffinity=2, rgba=(0, 0, 0, 0), group=4, mass=0, condim=4, friction=(0.8, 0.02, 0.0001),
                 solref=(0.004, 1), solimp=(0.95, 0.99, 0.0005))
    axis = np.asarray(b["shaft_axis_local"], dtype=float)  # (x, y) of the shaft axis in the boot frame
    node(boot, "geom", name="boot_footbed_proxy", type="box", size=(0.022, 0.022, 0.004),
         pos=(axis[0], axis[1], b["footbed_local_z"] + 0.004), **proxy)
    gap = r["peg_radius"] + b["sleeve_clearance"]
    z0, z1 = b["sleeve_local_z"]
    zc, zh = (z0 + z1) / 2, (z1 - z0) / 2
    for k, (dx, dy, sx, sy) in enumerate(((gap + 0.003, 0, 0.003, gap + 0.006), (-gap - 0.003, 0, 0.003, gap + 0.006),
                                          (0, gap + 0.003, gap + 0.006, 0.003), (0, -gap - 0.003, gap + 0.006, 0.003))):
        node(boot, "geom", name=f"boot_sleeve_proxy_{k}", type="box", size=(sx, sy, zh),
             pos=(axis[0] + dx, axis[1] + dy, zc), **proxy)

    # ------------------------------------------------------------------ clods
    clod_kw = dict(friction=(config["clod_friction"], 0.01, 0.002), condim=6, solref=(0.004, 1),
                   solimp=(0.95, 0.99, 0.0005))
    for i, pose in enumerate(config["clods"]):
        node(asset, "mesh", name=f"clod_mesh_{i}", vertex=clod_vertices(i).ravel())
        body = node(world, "body", name=f"clod_{i}", pos=pose["pos"], quat=pose["quat"])
        node(body, "freejoint", name=f"clod_{i}_free")
        node(body, "geom", name=f"clod_{i}", type="mesh", mesh=f"clod_mesh_{i}", mass=config["clod_mass"],
             rgba=(0.30 + 0.025 * i, 0.20 + 0.01 * i, 0.10, 1), **clod_kw)

    # ------------------------------------------------------------------ brush
    br = config["brush"]
    outline = np.array([[-0.070, 0], [-0.052, -0.018], [0.055, -0.018], [0.070, -0.012], [0.070, 0.012],
                        [0.055, 0.018], [-0.052, 0.018]])
    vertices = np.vstack([np.c_[outline, np.full(len(outline), z)] for z in (-0.0065, 0.0065)])
    node(asset, "mesh", name="brush_beech_mesh", vertex=vertices.ravel())
    brush = node(world, "body", name="brush", pos=br["pos"], quat=br["quat"])
    node(brush, "freejoint", name="brush_free")
    node(brush, "inertial", pos=(0, 0, -0.003), mass=0.084, diaginertia=(1.6e-5, 1.45e-4, 1.5e-4))
    node(brush, "geom", name="brush_back", type="mesh", mesh="brush_beech_mesh", material="beech_mat", mass=0,
         friction=(0.8, 0.005, 0.0001), solref=(0.004, 1), solimp=(0.95, 0.99, 0.0005))
    pad = br["pad"]
    node(brush, "geom", name="brush_bristle_pad", type="box", size=pad["half"], pos=pad["pos"], mass=0,
         rgba=(0.11, 0.10, 0.06, 0), group=3, friction=(br["bristle_friction"], 0.005, 0.0001),
         solref=pad["solref"], solimp=(0.9, 0.97, 0.002))
    for i, (x, y) in enumerate((x, y) for x in np.linspace(-0.050, 0.050, 8) for y in np.linspace(-0.012, 0.012, 4)):
        tuft = node(brush, "body", name=f"tuft_{i}", pos=(x, y, -0.0065), euler=(0.18 * 0.25, 0.12 * 0.25, 0))
        node(tuft, "geom", name=f"tuft_core_{i}", type="capsule", fromto=(0, 0, -0.001, 0, 0, -0.024),
             size=(0.0012,), rgba=(0.11, 0.10, 0.06, 1), contype=0, conaffinity=0, group=2, mass=0)
        for k in range(5):
            angle = k * 2 * np.pi / 5
            dx, dy = 0.0017 * np.cos(angle), 0.0017 * np.sin(angle)
            node(tuft, "geom", name=f"fibre_visual_{i}_{k}", type="capsule", fromto=(dx, dy, 0, dx * 1.4, dy * 1.4,
                 -0.0245), size=(0.00035,), rgba=(0.17 + 0.04 * (k % 2), 0.14, 0.07, 1), contype=0, conaffinity=0,
                 group=2, mass=0)

    # ------------------------------------------------------------------ lights, cameras, visual
    node(world, "light", pos=(0.4, -0.8, 2.4), dir=(0, 0.5, -1), diffuse=(0.75, 0.75, 0.72), castshadow="true")
    node(world, "light", pos=(0.1, 0.8, 2.2), dir=(0.2, -0.3, -1), diffuse=(0.45, 0.45, 0.47), castshadow="false")
    for cam in config["cameras"]:
        node(world, "camera", name=cam["name"], pos=cam["pos"], xyaxes=look_at(cam["pos"], cam["target"]),
             fovy=cam["fovy"])
    v = root.find("visual")
    if v is None:
        v = node(root, "visual")
    node(v, "global", offwidth=1280, offheight=720)
    node(v, "quality", shadowsize=4096, offsamples=4)
    node(v, "headlight", ambient=(0.32, 0.32, 0.32), diffuse=(0.45, 0.45, 0.45), specular=(0.1, 0.1, 0.1))
    xml = ET.tostring(root, encoding="unicode")
    return mujoco.MjModel.from_xml_string(xml), xml
