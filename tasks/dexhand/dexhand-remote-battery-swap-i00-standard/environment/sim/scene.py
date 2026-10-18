"""T07 remote battery replacement: MJCF scene (approved presentation geometry) with the shared hand rig."""

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

# Remote geometry (remote body frame; x = long axis, the cover opens toward -x). The approved source shell is
# 160 x 64 x 30 mm with a 94 x 52 mm battery cavity, kept at source size (WIDTH_SCALE 1).
WIDTH_SCALE = 1.0
SHELL_HALF = (0.080, 0.032 * WIDTH_SCALE)
CAVITY_HALF_Y = 0.026 * WIDTH_SCALE
SHELL_TOP, SHELL_BOTTOM, CAVITY_FLOOR = 0.012, -0.018, -0.010
CAVITY_X = (-0.072, 0.022)
REAR_WALL_TOP = 0.002  # source end wall top between the ears
REAR_EAR_INNER_Y = 0.012  # source rear ears span |y| 0.012..0.026
LATCH_STOP_HALF, LATCH_STOP_POS = (0.002, 0.006, 0.0008), (-0.071, 0.0, 0.0085)  # source task_latch_stop
TAB_LOCAL_X = -0.035  # source cover_tab (thumb pad) position in the door frame
TAB_HALF, TAB_Z = (0.009, 0.009, 0.002), 0.003  # source task_cover_tab: 3 mm proud of the door plate
NEG_BLOCK_X0 = -0.0625  # rear end of the negative terminal block (clear of the hook's path)
HOOK_HALF, HOOK_POS = (0.002, 0.006, 0.002), (-0.007, 0.0, -0.0055)  # source task_cover_hook (tab frame)
FOOT_HALF_HEIGHT = 0.001
CELL_RADIUS, CELL_HALF_LENGTH = 0.007, 0.0245
DARK = (0.045, 0.055, 0.065, 1)
GOLD = (0.93, 0.71, 0.23, 1)
SILVER = (0.72, 0.74, 0.75, 1)
TRAY = (0.75, 0.82, 0.78, 1)


def node(parent, tag, **attributes):
    def value(x):
        return " ".join(f"{float(v):.10g}" for v in x) if isinstance(x, (tuple, list, np.ndarray)) else str(x)

    return ET.SubElement(parent, tag, {k: value(v) for k, v in attributes.items()})


def box(parent, name, half, pos, color=DARK, friction=(1.0, 0.005, 0.0001), **attributes):
    return node(parent, "geom", name=name, type="box", size=half, pos=pos, rgba=color, friction=friction,
                condim=4, solref=(0.005, 1), solimp=(0.95, 0.99, 0.0005), group=3 if "contype" not in attributes else 2,
                **attributes)


def visual(parent, name, kind, color, **attributes):
    return node(parent, "geom", name=name, type=kind, rgba=color, contype=0, conaffinity=0, mass=0, group=2,
                **attributes)


def slot_center(config):
    """Seated cell centre in the remote frame (x along the slot, z from the cradle contact)."""
    return np.asarray(config["slot_center_local"], dtype=float)


def add_cell(world, assets, name, pos, quat, texture):
    body = node(world, "body", name=name, pos=pos, quat=quat)
    node(body, "freejoint", name=name + "_free")
    node(body, "inertial", pos=(0, 0, 0), mass=0.023, diaginertia=(4.9e-6, 4.9e-6, 5.6e-7))
    node(body, "geom", name=name + "_collision", type="cylinder", size=(CELL_RADIUS, CELL_HALF_LENGTH),
         rgba=(0.5, 0.5, 0.5, 0), friction=(1.0, 0.01, 0.0002), condim=6, solref=(0.004, 1),
         solimp=(0.95, 0.99, 0.0005), group=3, mass=0)
    node(assets, "texture", name=name + "_wrap", type="2d", file=texture)
    node(assets, "material", name=name + "_wrap_material", texture=name + "_wrap", specular=0.3, shininess=0.4)
    visual(body, name + "_label", "mesh", (1, 1, 1, 1), mesh="aa_cell", material=name + "_wrap_material")
    visual(body, name + "_negative_cap", "cylinder", SILVER, size=(CELL_RADIUS * 0.97, 0.0004),
           pos=(0, 0, -CELL_HALF_LENGTH + 0.0004))
    visual(body, name + "_positive_shoulder", "cylinder", SILVER, size=(CELL_RADIUS * 0.97, 0.0004),
           pos=(0, 0, CELL_HALF_LENGTH - 0.0004))
    visual(body, name + "_positive", "cylinder", GOLD, size=(0.0028, 0.0009), pos=(0, 0, CELL_HALF_LENGTH + 0.0005))
    return body


def add_remote(world, assets, config):
    sy = WIDTH_SCALE
    for mesh in ("remote_shell", "battery_door", "thumb_pad", "open_arrow"):
        node(assets, "mesh", name=mesh, file=mesh + ".obj", scale=(1, sy, 1), inertia="shell")
    remote = node(world, "body", name="remote", pos=config["remote_pos"])
    node(remote, "freejoint", name="remote_free")
    # A weighted handset (0.35 kg incl. a steel ballast plate) on four rubber feet.
    node(remote, "inertial", pos=(0, 0, -0.008), mass=config["remote_mass"],
         diaginertia=(0.00025, 0.00085, 0.00105))
    plastic = dict(mass=0)
    hx, hy = SHELL_HALF
    cavity_y = CAVITY_HALF_Y
    wall = (hy - cavity_y) / 2
    box(remote, "remote_floor", (hx, hy, (CAVITY_FLOOR - SHELL_BOTTOM) / 2),
        (0, 0, (CAVITY_FLOOR + SHELL_BOTTOM) / 2), **plastic)
    height = (SHELL_TOP - CAVITY_FLOOR) / 2
    zc = (SHELL_TOP + CAVITY_FLOOR) / 2
    for sign in (-1, 1):
        box(remote, f"remote_side_{'neg' if sign < 0 else 'pos'}", (hx, wall, height), (0, sign * (cavity_y + wall), zc),
            **plastic)
    # Rear end wall as in the source: low (top at z = REAR_WALL_TOP) between two ears, so the door's latch hook can
    # pass over it while the tab is pressed; the ears rise to the shell top.
    rear_hx, rear_x = (CAVITY_X[0] + hx) / 2, (CAVITY_X[0] - hx) / 2
    box(remote, "remote_rear_wall", (rear_hx, cavity_y, (REAR_WALL_TOP - CAVITY_FLOOR) / 2),
        (rear_x, 0, (REAR_WALL_TOP + CAVITY_FLOOR) / 2), **plastic)
    ear_hy = (cavity_y - REAR_EAR_INNER_Y) / 2
    for sign in (-1, 1):
        box(remote, f"remote_rear_ear_{'neg' if sign < 0 else 'pos'}", (rear_hx, ear_hy, (SHELL_TOP - REAR_WALL_TOP) / 2),
            (rear_x, sign * (REAR_EAR_INNER_Y + ear_hy), (SHELL_TOP + REAR_WALL_TOP) / 2), **plastic)
    # Fixed latch stop (source task_latch_stop): the door's hook rests just in front of it when the door is shut.
    box(remote, "latch_stop", LATCH_STOP_HALF, LATCH_STOP_POS, color=(0.10, 0.11, 0.12, 1), **plastic)
    box(remote, "remote_front_block", ((hx - CAVITY_X[1]) / 2, cavity_y, height), ((hx + CAVITY_X[1]) / 2, 0, zc),
        **plastic)
    for i, (x, y) in enumerate(((-0.064, -0.028), (-0.064, 0.028), (0.064, -0.028), (0.064, 0.028))):
        box(remote, f"remote_foot_{i}", (0.009, 0.006, FOOT_HALF_HEIGHT), (x, y * sy, SHELL_BOTTOM - FOOT_HALF_HEIGHT),
            color=(0.02, 0.02, 0.02, 1), friction=(1.4, 0.01, 0.0002), **plastic)
    # Single-cell slot: two low cradle ribs along x, terminal blocks at both ends of the slot.
    slot = slot_center(config)
    rib_h = 0.00075
    for sign in (-1, 1):
        box(remote, f"cradle_rib_{'neg' if sign < 0 else 'pos'}", (0.021, 0.001, rib_h),
            (slot[0], sign * 0.0045, CAVITY_FLOOR + rib_h), color=(0.065, 0.075, 0.085, 1), **plastic)
    gap = config["terminal_clearance_m"]
    plus_face = slot[0] + CELL_HALF_LENGTH + 0.0014 + gap
    minus_face = slot[0] - CELL_HALF_LENGTH - gap
    axis_z = slot[2]
    box(remote, "positive_terminal_block", ((CAVITY_X[1] - plus_face - 0.001) / 2, 0.009, (axis_z - CAVITY_FLOOR) / 2 + 0.003),
        ((CAVITY_X[1] + plus_face + 0.001) / 2, 0, (axis_z + CAVITY_FLOOR) / 2 + 0.003), **plastic)
    # The negative terminal block stops short of the rear wall, leaving room for the latch hook (source: no block).
    box(remote, "negative_terminal_block", ((minus_face - 0.004 - NEG_BLOCK_X0) / 2, 0.009,
                                            (axis_z - CAVITY_FLOOR) / 2 + 0.003),
        ((minus_face - 0.004 + NEG_BLOCK_X0) / 2, 0, (axis_z + CAVITY_FLOOR) / 2 + 0.003), **plastic)
    node(remote, "geom", name="positive_contact", type="cylinder", size=(0.005, 0.0005),
         pos=(plus_face + 0.0005, 0, axis_z), euler=(0, np.pi / 2, 0), rgba=GOLD, friction=(0.6, 0.005, 0.0001),
         condim=4, solref=(0.005, 1), solimp=(0.95, 0.99, 0.0005), mass=0, group=2)
    for k in range(4):  # conical negative spring coil (visual), its tip is the contact plate below
        x = minus_face - 0.004 + 0.001 * k
        visual(remote, f"negative_spring_turn_{k}", "cylinder", SILVER, size=(0.0048 - 0.0006 * k, 0.00025),
               pos=(x, 0, axis_z), euler=(0, np.pi / 2, 0))
    node(remote, "geom", name="negative_contact", type="cylinder", size=(0.0035, 0.0005),
         pos=(minus_face - 0.0005, 0, axis_z), euler=(0, np.pi / 2, 0), rgba=SILVER, friction=(0.6, 0.005, 0.0001),
         condim=4, solref=(0.005, 1), solimp=(0.95, 0.99, 0.0005), mass=0, group=2)
    node(assets, "material", name="remote_plastic", rgba=DARK, specular=0.15, shininess=0.25)
    visual(remote, "remote_shell_visual", "mesh", DARK, mesh="remote_shell", material="remote_plastic")
    for i, (x, y) in enumerate(((-0.069, -0.029), (-0.069, 0.029), (0.07, -0.022), (0.07, 0.022))):
        visual(remote, f"fastener_{i}", "cylinder", (0.18, 0.2, 0.22, 1), size=(0.00115, 0.00015),
               pos=(x, y * sy, SHELL_TOP + 0.00005))
    for i, y in enumerate((-0.015, -0.005, 0.005, 0.015)):
        visual(remote, f"button_{i}", "cylinder", (0.7, 0.72, 0.7, 1), size=(0.004, 0.0008),
               pos=(0.052, y * sy, SHELL_TOP + 0.0008))
    for sign in (-1, 1):
        visual(remote, f"polarity_mark_{'neg' if sign < 0 else 'pos'}", "box", (0.67, 0.7, 0.7, 1),
               size=(0.0022, 0.0005 if sign < 0 else 0.0022, 0.0001) if sign > 0 else (0.0022, 0.0005, 0.0001),
               pos=(slot[0] + sign * 0.017, -0.017 * sy, CAVITY_FLOOR + 0.0001))
    visual(remote, "polarity_mark_pos_bar", "box", (0.67, 0.7, 0.7, 1), size=(0.0005, 0.0022, 0.0001),
           pos=(slot[0] + 0.017, -0.017 * sy, CAVITY_FLOOR + 0.0001))
    # Sliding battery door (source mechanism): passive slide joint with the source damping/friction and end stops,
    # plus the source latch: a spring-loaded thumb tab (slide joint along -z, 0..5 mm, 120 N/m) carrying a hook that
    # sits in front of the fixed latch stop when the door is shut. Opening (and closing) needs the tab pressed
    # 2.8..4.5 mm: the hook then passes under the stop and over the low rear wall.
    cover = node(remote, "body", name="cover", pos=(-0.025, 0, SHELL_TOP + 0.002))
    node(cover, "joint", name="cover_slide", type="slide", axis=(-1, 0, 0), range=(0, config["cover_travel_m"]),
         damping=config["cover_damping"], frictionloss=config["cover_frictionloss_n"], armature=0.002,
         limited="true")
    node(cover, "inertial", pos=(0, 0, 0), mass=0.012, diaginertia=(2.4e-6, 1.0e-5, 1.2e-5))
    box(cover, "cover_plate", (0.050, 0.027 * sy, 0.002), (-0.001, 0, 0), friction=(1.0, 0.005, 0.0001), mass=0)
    visual(cover, "cover_visual", "mesh", DARK, mesh="battery_door", material="remote_plastic")
    tab = node(cover, "body", name="cover_tab", pos=(TAB_LOCAL_X, 0, 0))
    node(tab, "joint", name="tab_depth", type="slide", axis=(0, 0, -1), range=(0, config["tab_travel_m"]),
         stiffness=config["tab_stiffness_n_m"], damping=0.1, armature=0.0005, limited="true")
    node(tab, "inertial", pos=(0, 0, 0.002), mass=0.003, diaginertia=(1.0e-7, 1.0e-7, 1.6e-7))
    box(tab, "cover_tab", TAB_HALF, (0, 0, TAB_Z), color=(0.14, 0.16, 0.18, 1), friction=(1.2, 0.005, 0.0001),
        mass=0)
    box(tab, "cover_hook", HOOK_HALF, HOOK_POS, color=(0.10, 0.11, 0.12, 1), mass=0)
    visual(tab, "cover_tab_visual", "box", DARK, size=TAB_HALF, pos=(0, 0, TAB_Z), material="remote_plastic")
    visual(tab, "thumb_pad_visual", "mesh", DARK, mesh="thumb_pad", pos=(0, 0, TAB_Z + TAB_HALF[2] - 0.0017 + 0.0001),
           material="remote_plastic")
    visual(tab, "open_arrow_visual", "mesh", (0.28, 0.32, 0.34, 1), mesh="open_arrow",
           pos=(0, 0, TAB_Z + TAB_HALF[2] - 0.0019 + 0.0002))
    for k, x in enumerate((-0.006, -0.0036, -0.0012, 0.0012, 0.0036, 0.006)):
        visual(tab, f"thumb_rib_{k}", "box", (0.14, 0.16, 0.18, 1), size=(0.00025, 0.003 * sy, 0.0001),
               pos=(x, 0.0, TAB_Z + TAB_HALF[2] + 0.0001))
    return remote


def add_tray(world, config):
    tray = node(world, "body", name="tray", pos=config["tray_pos"])
    node(tray, "freejoint", name="tray_free")
    node(tray, "inertial", pos=(0, 0, 0.001), mass=0.12, diaginertia=(6e-5, 7e-5, 1.2e-4))
    hx, hy = config["tray_inner_half"]
    t = 0.003
    box(tray, "tray_floor", (hx + 2 * t, hy + 2 * t, 0.003), (0, 0, 0), color=TRAY, friction=(1.1, 0.005, 0.0001),
        mass=0, contype=1)
    for sign in (-1, 1):
        box(tray, f"tray_wall_x_{'neg' if sign < 0 else 'pos'}", (t, hy + 2 * t, 0.009), (sign * (hx + t), 0, 0.006),
            color=TRAY, mass=0, contype=1)
        box(tray, f"tray_wall_y_{'neg' if sign < 0 else 'pos'}", (hx, t, 0.009), (0, sign * (hy + t), 0.006),
            color=TRAY, mass=0, contype=1)
    return tray


def arm_rig_id():
    return _arm_rig_module().ROBOT_ID


def add_marvin_rig(root, config, hand_id, folder):
    """The Tianji Marvin stand with both 7-DoF arms (shared arm_rig); the right arm/hand works, the left is parked."""
    arm_rig = _arm_rig_module()
    actuator, hand = root.find("actuator"), root.find("worldbody").find("body")
    for a in actuator:  # the family's Sharpa tweaks, before mounting (the mirrored left Wave inherits them)
        if a.tag == "general":
            bias = [float(v) for v in a.get("biasprm", "0 0 0").split()]
            bias[2] = -0.9
            a.set("biasprm", " ".join(map(str, bias)))
    for g in hand.iter("geom"):
        if "fingertip_collision" in g.get("name", ""):
            g.set("friction", "1.5 .005 .0001")
    sibling = folder.parent / "wuji_v2_2"
    marvin = config["marvin"]
    return arm_rig.mount_marvin(root, marvin["base_pos"], marvin["base_yaw"], hand=hand_id, active=("right",),
                                mount_names={"right": "wrist_stage"}, sharpa_folder=folder,
                                wuji_folder=sibling if (sibling / "mjcf/right.xml").is_file() else None)


def add_wrist_stage(root, hand, hand_id, folder):
    """Authoring/legacy rig: the hand on a floating six-axis wrist stage (assemble_hamburger joints and gains)."""
    world, actuator = root.find("worldbody"), root.find("actuator")
    world.remove(hand)
    wrist = node(world, "body", name="wrist_stage")
    node(wrist, "inertial", pos=(0, 0, 0), mass=0.01, diaginertia=(0.00001,) * 3)
    hand.set("quat", "0 0.7071067811865476 0 0.7071067811865476")
    wrist.append(hand)
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
    for g in hand.iter("geom"):
        if "fingertip_collision" in g.get("name", ""):
            g.set("friction", "1.5 .005 .0001")
    if hand_id != "sharpa":
        sibling = folder.parent / "wuji_v2_2"
        hands.replace_wave_hands(root, hand_id, folder=sibling if (sibling / "mjcf/right.xml").is_file() else None)


def build(config, asset_dir=None, hand="sharpa"):
    """Compose the frozen scene with the selected genuine hand on the Marvin arm rig (``config["rig"] == "marvin"``;
    the left arm is parked) or, for authoring only, on the legacy six-axis wrist stage."""
    hand_id = hands.canonical(hand)
    folder = Path(
        asset_dir
        or os.environ.get("DEXHAND_ASSET_DIR")
        or hands.sharpa_dir()  # DEXHAND_ASSET_DIR, else the image path /opt/dexhand/hand
    )
    root = ET.parse(folder / "right_hand.xml").getroot()
    root.set("model", hands.info(hand_id)["model"] + " remote battery swap")
    compiler = root.find("compiler")
    compiler.set("meshdir", str((folder / "assets/right").resolve()))
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
    hand = world.find("body")
    if config.get("rig", "floating") == "marvin":
        add_marvin_rig(root, config, hand_id, folder)
    else:
        add_wrist_stage(root, hand, hand_id, folder)
    # Family meshes/textures are referenced by absolute path so the hand's meshdir stays untouched.
    family_assets = HERE / "assets"
    node(assets, "texture", name="studio_sky", type="skybox", builtin="gradient", width=256, height=256,
         rgb1=(0.93, 0.88, 0.84), rgb2=(0.98, 0.95, 0.92))
    node(assets, "texture", name="table_grain", type="2d", builtin="gradient", width=256, height=256,
         rgb1=(0.90, 0.81, 0.73), rgb2=(0.84, 0.75, 0.67))
    node(assets, "material", name="table_material", texture="table_grain", texrepeat=(1, 1), reflectance=0.0,
         specular=0.05)
    node(assets, "mesh", name="aa_cell", file="aa_cell.obj", inertia="shell")
    world_geom = dict(condim=4, solref=(0.005, 1), solimp=(0.95, 0.99, 0.0005))
    floor_z = config.get("floor_z", 0.0)
    node(world, "geom", name="floor", type="plane", size=(3, 3, 0.1), pos=(0, 0, floor_z),
         rgba=(0.80, 0.76, 0.72, 1), **world_geom)
    tz = config["table_z"]
    th = config["table_half"]
    tc = config["table_center"]
    node(world, "geom", name="table", type="box", size=(th[0], th[1], 0.025), pos=(tc[0], tc[1], tz - 0.025),
         rgba=(0.87, 0.78, 0.70, 1), material="table_material", friction=(0.9, 0.005, 0.0001), **world_geom)
    leg_h = (tz - 0.05 - floor_z) / 2
    inset = config.get("table_leg_inset", [0.04, 0.04])  # (robot side, far side): the robot's stand feet sit under
    for i, (sx, sy) in enumerate(((-1, -1), (-1, 1), (1, -1), (1, 1))):  # the front edge, so its legs stand back
        visual(world, f"table_leg_{i}", "box", (0.30, 0.27, 0.24, 1), size=(0.02, 0.02, leg_h),
               pos=(tc[0] + sx * (th[0] - inset[0 if sx < 0 else 1]), tc[1] + sy * (th[1] - 0.04), floor_z + leg_h))
    add_remote(world, assets, config)
    add_tray(world, config)
    add_cell(world, assets, "old_cell", config["old_cell_pos"], config["old_cell_quat"], "old_aa_wrap.png")
    add_cell(world, assets, "new_cell", config["new_cell_pos"], config["new_cell_quat"], "new_aa_wrap.png")
    for item in assets:
        if item.tag in ("mesh", "texture") and item.get("file") and not item.get("file").startswith("/"):
            if item.get("name") in ("aa_cell", "remote_shell", "battery_door", "thumb_pad", "open_arrow") or \
                    item.get("file").endswith("_wrap.png"):
                item.set("file", str((family_assets / item.get("file")).resolve()))
    node(world, "light", name="key", pos=(-0.25, -0.35, 0.95), dir=(0.35, 0.45, -0.8), diffuse=(0.75, 0.71, 0.65),
         castshadow="true")
    node(world, "light", name="fill", pos=(0.4, 0.3, 0.9), dir=(-0.4, -0.3, -0.8), diffuse=(0.40, 0.43, 0.47),
         castshadow="false")
    cam = config["cameras"]
    for name, spec in cam.items():
        node(world, "camera", name=name, pos=spec["pos"], xyaxes=spec["xyaxes"], fovy=spec["fovy"])
    v = root.find("visual")
    if v is None:
        v = node(root, "visual")
    node(v, "global", offwidth=1280, offheight=720)
    node(v, "quality", shadowsize=4096, offsamples=4)
    node(v, "headlight", ambient=(0.36, 0.35, 0.34), diffuse=(0.42, 0.42, 0.42), specular=(0.08, 0.08, 0.08))
    xml = ET.tostring(root, encoding="unicode")
    return mujoco.MjModel.from_xml_string(xml), xml
