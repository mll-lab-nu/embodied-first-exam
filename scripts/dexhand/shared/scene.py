"""Compose the Wave hand and thirty contact-driven rigid mechanism scenes.

All task joints are passive. The six wrist position actuators are generic
kinematic access, not task macros. Assets are installed in the simulator image.
"""

from __future__ import annotations

import math
import os
import xml.etree.ElementTree as ET
from pathlib import Path

import mujoco

import essential
import hands

PALM_BODY = "right_hand_C_MC"
WRIST_JOINTS = ["wrist_x", "wrist_y", "wrist_z", "wrist_rx", "wrist_ry", "wrist_rz"]
FREE_TASKS = {
    "cube_face_sequence",
    "pen_axial_shift",
    "coin_edge_roll",
    "two_ball_exchange",
    "sphere_palm_orbit",
} | essential.FREE_TASKS
BLUE = "0.12 0.52 0.83 1"
GOLD = "0.95 0.62 0.15 1"
GRAY = "0.28 0.32 0.37 1"


def _s(value):
    return " ".join(str(x) for x in value) if isinstance(value, (tuple, list)) else str(value)


def node(parent, tag, **attrs):
    return ET.SubElement(parent, tag, {k: _s(v) for k, v in attrs.items()})


def geom(parent, name, kind="box", size=(0.02, 0.02, 0.01), pos=(0, 0, 0), color=BLUE, **kw):
    return node(
        parent,
        "geom",
        name=name,
        type=kind,
        size=size,
        pos=pos,
        rgba=color,
        density=700,
        friction="0.9 0.01 0.001",
        **kw,
    )


class Mechanism:
    def __init__(self, world, spec):
        self.world, self.spec = world, spec
        self.initial = {}
        self.names = []
        self.origin = (0.13, 0, 0.165)
        geom(
            world,
            "fixture_base",
            size=(0.11, 0.10, 0.01),
            pos=(0.13, 0, 0.125),
            color=GRAY,
        )

    def body(self, name, pos=None, parent=None, **kw):
        return node(
            parent if parent is not None else self.world,
            "body",
            name="task_" + name,
            pos=pos or self.origin,
            **kw,
        )

    def joint(
        self,
        body,
        name,
        kind="hinge",
        axis=(0, 0, 1),
        limits=None,
        spring=False,
        initial=0,
    ):
        if limits is None:
            limits = self.spec.get("parameters", {}).get("joint_ranges", {}).get(name, [-0.12, 0.12])
        spring = spring or name in self.spec.get("parameters", {}).get("spring_joints", [])
        stiffness = (0.15 if kind == "hinge" else 80) if spring else 0
        if spring and name == "press":
            stiffness = {"spring_plunger": 400, "childproof_cap": 800}.get(self.spec["id"], stiffness)
        friction = 0.002 if kind == "hinge" else 0.04
        if self.spec["id"] == "keyed_peg" and name in {"x", "y"}:
            friction = 0.3
        if self.spec["id"] == "hook_ring" and name == "lift":
            friction = 0.25
        self.initial[name] = initial
        self.names.append(name)
        return node(
            body,
            "joint",
            name=name,
            type=kind,
            axis=axis,
            range=limits,
            damping=0.03 if kind == "hinge" else 0.8,
            armature=0.0001 if kind == "hinge" else 0.005,
            stiffness=stiffness,
            springref=0,
            frictionloss=friction,
            solreffriction=(0.004, 1),
            solimpfriction=(0.999, 0.999, 0.001, 0.5, 2),
        )

    def knob(self, body, name="knob", radius=0.031):
        geom(body, "task_" + name, "cylinder", (radius, 0.015))
        geom(
            body,
            "task_" + name + "_mark",
            size=(0.004, radius, 0.003),
            pos=(0, 0, 0.018),
            color=GOLD,
        )
        for i in range(4):
            a = i * math.pi / 2
            geom(
                body,
                f"task_{name}_lug_{i}",
                size=(0.007, 0.007, 0.019),
                pos=(radius * math.cos(a), radius * math.sin(a), 0),
                color=GOLD,
            )

    def slider(self, name, pos=None, axis=(1, 0, 0), spring=False, size=(0.025, 0.025, 0.012)):
        body = self.body(name, pos)
        self.joint(body, name, "slide", axis, spring=spring)
        geom(body, "task_" + name, size=size, color=GOLD)
        return body

    def button(self, name, pos, radius=0.009):
        body = self.body(name, pos)
        self.joint(body, name, "slide", (0, 0, -1), spring=True)
        geom(body, "task_" + name, "cylinder", (radius, 0.006), color=GOLD)
        # The guide is visual; the prismatic joint supplies the actual rail.
        geom(
            self.world,
            "guide_" + name,
            "cylinder",
            (radius + 0.002, 0.015),
            pos=(pos[0], pos[1], pos[2] - 0.022),
            color=GRAY,
            contype=0,
            conaffinity=0,
        )
        return body

    def lid(self, name="lid", parent=None, pos=None):
        body = self.body(name, pos or (0.075, 0, 0.21), parent)
        joint = self.joint(body, name, axis=(0, -1, 0))
        joint.set("frictionloss", "0.045")
        geom(body, "task_" + name, size=(0.05, 0.045, 0.005), pos=(0.05, 0, 0))
        geom(
            body,
            "task_" + name + "_handle",
            "capsule",
            (0.007, 0.025),
            pos=(0.085, 0, 0.013),
            quat=(0.707107, 0.707107, 0, 0),
            color=GOLD,
        )
        return body

    def free(self, name, pos, shape, size, color=BLUE, quat=(1, 0, 0, 0)):
        body = node(self.world, "body", name=name, pos=pos, quat=quat)
        node(body, "freejoint", name=name + "_free")
        geom(body, "task_" + name, shape, size, color=color)
        return body

    def build(self):
        task = self.spec["id"]
        if task in FREE_TASKS:
            # Remove the tabletop fixture beneath the hand for free manipulation.
            self.world.remove(self.world.find("geom[@name='fixture_base']"))
            center = (-0.024, 0, 0.328)
            if task == "cube_face_sequence":
                b = self.free("object", center, "box", (0.0225,) * 3)
                geom(
                    b,
                    "object_marker",
                    size=(0.012, 0.012, 0.001),
                    pos=(0, 0, 0.023),
                    color=GOLD,
                    contype=0,
                    conaffinity=0,
                )
            elif task == "pen_axial_shift":
                self.free(
                    "object",
                    center,
                    "capsule",
                    (0.007, 0.058),
                    quat=(0.707107, 0, 0.707107, 0),
                )
            elif task == "coin_edge_roll":
                self.free("object", center, "cylinder", (0.025, 0.0025), color=GOLD)
                geom(
                    self.world,
                    "coin_deposit",
                    size=(0.065, 0.055, 0.005),
                    pos=(0.09, 0, 0.23),
                    color=GRAY,
                )
            elif task == "two_ball_exchange":
                self.free("ball_a", (-0.025, -0.021, 0.327), "sphere", (0.018,), color=BLUE)
                self.free("ball_b", (-0.025, 0.021, 0.327), "sphere", (0.018,), color=GOLD)
            else:
                self.free("object", center, "sphere", (0.025,))
            return

        if task in {"button_chord", "key_sequence", "uneven_button_chord"}:
            names = list(self.spec["parameters"]["joint_ranges"])
            poses = [
                (0.12, -0.030, 0.20),
                (0.124, -0.009, 0.20),
                (0.117, 0.012, 0.20),
                (0.04, -0.052, 0.20),
            ]
            for name, pos in zip(names, poses):
                self.button(name, pos)
        elif task == "wrench_regrasp":
            b = self.body("wrench", (0.13, 0, 0.185))
            self.joint(b, "turn")
            geom(b, "task_wrench_head", "cylinder", (0.019, 0.011), color=GRAY)
            geom(
                b,
                "task_wrench_handle",
                size=(0.045, 0.010, 0.007),
                pos=(-0.045, 0, 0.012),
            )
            geom(
                b,
                "task_wrench_end",
                size=(0.011, 0.025, 0.008),
                pos=(-0.08, 0.014, 0.012),
                color=GOLD,
            )
        elif task in {"combination_dial", "valve_precision", "ratchet_index"}:
            b = self.body("dial", (0.13, 0, 0.18))
            self.joint(b, "turn")
            self.knob(b)
            if task == "ratchet_index":
                geom(
                    b,
                    "task_lever",
                    size=(0.042, 0.012, 0.006),
                    pos=(-0.04, 0, 0.022),
                    color=GOLD,
                )
            for i in range(12):
                a = i * math.pi / 6
                geom(
                    self.world,
                    f"dial_tick_{i}",
                    size=(0.002, 0.002, 0.001),
                    pos=(0.13 + 0.048 * math.cos(a), 0.048 * math.sin(a), 0.14),
                    color=GOLD,
                    contype=0,
                    conaffinity=0,
                )
        elif task == "coordinated_dials":
            for name, y in [("a", -0.035), ("b", 0.035)]:
                b = self.body(name, (0.13, y, 0.18))
                self.joint(b, name)
                self.knob(b, name, radius=0.021)
        elif task == "safety_slider_dial":
            self.slider(
                "slide",
                (0.096, -0.020, 0.18),
                axis=(0, -1, 0),
                spring=True,
                size=(0.003, 0.006, 0.016),
            )
            b = self.body("dial", (0.13, 0, 0.18))
            self.joint(b, "turn")
            self.knob(b)
        elif task in {"childproof_cap", "bayonet_lock", "lift_turn_latch"}:
            b = self.body("compound", (0.13, 0, 0.20))
            name = {
                "childproof_cap": "press",
                "bayonet_lock": "slide",
                "lift_turn_latch": "lift",
            }[task]
            axis = (0, 0, 1) if task == "lift_turn_latch" else (0, 0, -1)
            self.joint(b, name, "slide", axis)
            self.joint(b, "turn")
            self.knob(b, radius=0.032)
            geom(
                self.world,
                "compound_seat",
                "cylinder",
                (0.036, 0.012),
                pos=(0.13, 0, 0.119),
                color=GRAY,
            )
            # A lug encounters this stop while turning; axial release clears it.
            stop_z = 0.199 if task == "lift_turn_latch" else 0.216
            geom(
                self.world,
                "compound_stop",
                size=(0.002, 0.002, 0.004),
                pos=(0.1638, 0.0195, stop_z),
                color=GRAY,
            )
            if task == "lift_turn_latch":
                geom(
                    b,
                    "task_latch_lever",
                    size=(0.040, 0.010, 0.005),
                    pos=(0.04, 0, 0.02),
                    color=GOLD,
                )
        elif task == "latch_drawer":
            drawer = self.slider("slide", (0.10, 0, 0.16), axis=(-1, 0, 0), size=(0.045, 0.045, 0.015))
            b = self.body("latch", (0, 0, 0.035), drawer)
            self.joint(b, "turn", axis=(0, 0, -1))
            self.knob(b, radius=0.022)
            geom(
                b,
                "task_latch_tongue",
                size=(0.007, 0.025, 0.005),
                pos=(0, 0.035, 0.015),
                color=GOLD,
            )
            geom(
                self.world,
                "drawer_stop",
                size=(0.004, 0.010, 0.007),
                pos=(0.088, 0.051, 0.210),
                color=GRAY,
            )
            for y in (-0.052, 0.052):
                geom(
                    self.world,
                    "drawer_rail_" + str(y),
                    size=(0.08, 0.004, 0.012),
                    pos=(0.1, y, 0.16),
                    color=GRAY,
                )
        elif task == "spring_plunger":
            b = self.body("plunger", (0.13, 0, 0.21))
            self.joint(b, "press", "slide", (0, 0, -1))
            geom(b, "task_plunger_head", "cylinder", (0.032, 0.008), color=GOLD)
            geom(b, "task_plunger_shaft", "cylinder", (0.008, 0.025), pos=(0, 0, -0.025))
        elif task == "syringe_metering":
            self.slider("slide", (0.07, 0, 0.19), axis=(-1, 0, 0), size=(0.012, 0.029, 0.008))
            geom(
                self.world,
                "syringe_barrel",
                "cylinder",
                (0.017, 0.045),
                pos=(0.14, 0, 0.19),
                quat=(0.707107, 0, 0.707107, 0),
                color=GRAY,
            )
        elif task == "sliding_puzzle":
            self.slider("a", (0.105, -0.005, 0.17), axis=(-1, 0, 0), size=(0.020, 0.006, 0.018))
            self.slider("b", (0.138, 0.015, 0.17), axis=(0, -1, 0), size=(0.017, 0.005, 0.018))
            geom(
                self.world,
                "puzzle_border",
                size=(0.006, 0.06, 0.014),
                pos=(0.20, 0, 0.17),
                color=GRAY,
            )
        elif task == "rotary_gate_maze":
            b = self.body("gate", (0.090, 0.055, 0.193))
            self.joint(b, "turn", axis=(-1, 0, 0))
            geom(b, "task_gate", size=(0.004, 0.028, 0.015), pos=(0, -0.028, 0))
            self.slider("slide", (0.075, 0, 0.18), size=(0.004, 0.023, 0.014))
        elif task == "lid_contents":
            for name, pos, size in [
                ("floor", (0.13, 0, 0.16), (0.05, 0.045, 0.005)),
                ("front", (0.185, 0, 0.179), (0.005, 0.05, 0.024)),
                ("back", (0.075, 0, 0.179), (0.005, 0.05, 0.024)),
                ("left", (0.13, -0.05, 0.179), (0.05, 0.005, 0.024)),
                ("right", (0.13, 0.05, 0.179), (0.05, 0.005, 0.024)),
            ]:
                geom(self.world, "container_" + name, size=size, pos=pos, color=GRAY)
            self.free("contents", (0.13, 0, 0.178), "box", (0.01, 0.01, 0.012), color=GOLD)
            self.lid()
        elif task == "snap_clasp":
            self.lid()
            clasp = self.slider(
                "press",
                (0.174, -0.06, 0.222),
                axis=(0, -1, 0),
                spring=True,
                size=(0.018, 0.006, 0.009),
            )
            geom(
                clasp,
                "task_clasp_tongue",
                size=(0.010, 0.004, 0.003),
                pos=(0, 0.017, -0.002),
                color=GOLD,
            )
            geom(
                self.world,
                "clasp_base",
                size=(0.05, 0.04, 0.015),
                pos=(0.13, 0, 0.17),
                color=GRAY,
            )
        elif task == "keyed_peg":
            b = self.body("peg", (0.065, 0, 0.185))
            self.joint(b, "x", "slide", (0, 1, 0), [-0.015, 0.015])
            self.joint(b, "y", "slide", (0, 0, 1), [-0.015, 0.015])
            self.joint(b, "slide", "slide", (1, 0, 0))
            self.joint(b, "yaw", axis=(1, 0, 0))
            geom(b, "task_peg", size=(0.040, 0.012, 0.006), color=GOLD)
            # Socket walls form an actual narrow, keyed rectangular passage.
            for i, (pos, size) in enumerate(
                [
                    ((0.145, 0, 0.166), (0.025, 0.028, 0.005)),
                    ((0.145, 0, 0.204), (0.025, 0.028, 0.005)),
                    ((0.145, -0.015, 0.185), (0.025, 0.005, 0.014)),
                    ((0.145, 0.015, 0.185), (0.025, 0.005, 0.014)),
                ]
            ):
                geom(self.world, f"socket_{i}", size=size, pos=pos, color=GRAY)
        elif task == "connector_tab":
            plug = self.slider("slide", (0.07, 0, 0.18), size=(0.025, 0.026, 0.013))
            tab = self.body("tab", (0.018, 0, 0.025), plug)
            self.joint(tab, "press", "slide", (0, 0, -1))
            geom(tab, "task_tab", size=(0.010, 0.018, 0.005), color=BLUE)
            geom(
                self.world,
                "connector_roof",
                size=(0.0025, 0.040, 0.006),
                pos=(0.1075, 0, 0.204),
                color=GRAY,
            )
        elif task == "coin_slot_maze":
            b = self.body("coin", (0.065, -0.025, 0.165))
            self.joint(b, "x", "slide", (1, 0, 0), [-0.005, 0.065])
            self.joint(b, "y", "slide", (0, 1, 0), [-0.005, 0.04])
            self.joint(b, "yaw", limits=[-0.1, 1.8])
            geom(b, "task_coin", "cylinder", (0.008, 0.0025), color=GOLD)
            geom(
                b,
                "task_coin_tab",
                size=(0.004, 0.002, 0.002),
                pos=(0.007, 0, 0),
                color=BLUE,
            )
            for i, (x, y, sx, sy) in enumerate(
                [
                    (0.08, -0.060, 0.10, 0.005),
                    (0.08, 0.048, 0.10, 0.005),
                    (0.1025, -0.0125, 0.002, 0.003),
                ]
            ):
                geom(
                    self.world,
                    f"maze_wall_{i}",
                    size=(sx, sy, 0.012),
                    pos=(x, y, 0.165),
                    color=GRAY,
                )
        elif task == "card_feed":
            self.slider("slide", (0.06, 0, 0.18), size=(0.040, 0.026, 0.002))
            for i, z in enumerate((0.164, 0.191)):
                geom(
                    self.world,
                    f"card_guide_{i}",
                    size=(0.025, 0.04, 0.006),
                    pos=(0.155, 0, z),
                    color=GRAY,
                )
        elif task == "hook_ring":
            b = self.body("hook", (0.085, 0, 0.18))
            self.joint(b, "lift", "slide", (0, 0, 1))
            self.joint(b, "slide", "slide", (1, 0, 0))
            geom(b, "task_hook_handle", size=(0.020, 0.013, 0.008))
            geom(
                b,
                "task_hook_horizontal",
                "capsule",
                (0.004, 0.036),
                pos=(0.044, 0, 0),
                quat=(0.707107, 0, 0.707107, 0),
                color=GOLD,
            )
            geom(
                b,
                "task_hook_tip",
                "capsule",
                (0.004, 0.013),
                pos=(0.080, 0, 0.012),
                color=GOLD,
            )
            # Rails support the reset ring and leave the hook's path clear.
            for side in (-1, 1):
                geom(
                    self.world,
                    f"ring_support_{side}",
                    size=(0.08, 0.003, 0.008),
                    pos=(0.14, side * 0.023, 0.176),
                    color=GRAY,
                )
            ring = node(self.world, "body", name="ring", pos=(0.133, 0, 0.187))
            node(ring, "freejoint", name="ring_free")
            # Compound capsules produce a true open hole, unlike a convex mesh ring.
            for i in range(16):
                a, bangle = i * math.tau / 16, (i + 1) * math.tau / 16
                node(
                    ring,
                    "geom",
                    name=f"task_ring_{i}",
                    type="capsule",
                    size="0.003",
                    fromto=(
                        0.023 * math.cos(a),
                        0.023 * math.sin(a),
                        0,
                        0.023 * math.cos(bangle),
                        0.023 * math.sin(bangle),
                        0,
                    ),
                    rgba=BLUE,
                    density=700,
                )
        elif task == "elastic_clip":
            clip = self.slider("slide", (0.065, 0, 0.185), size=(0.027, 0.006, 0.006))
            jaw = self.body("jaw", (0, 0.012, 0), clip)
            self.joint(jaw, "press", axis=(0, 0, 1))
            geom(
                jaw,
                "task_clip_jaw",
                size=(0.030, 0.004, 0.007),
                pos=(0.016, 0.001, 0),
                color=BLUE,
            )
            geom(
                self.world,
                "clip_mount",
                size=(0.018, 0.001, 0.012),
                pos=(0.125, 0.0075, 0.185),
                color=GRAY,
            )
        else:
            raise ValueError(f"No scene builder for {task}")


def alias_wuji_geoms(source, record):
    """Give Wuji collision geoms the role names the essential predicates use for the Wave hand.

    Feature extraction identifies hand contacts by name: ``right_<finger>_...`` (finger links),
    ``right_<finger>_fingertip_collision`` (the fingertip pad) and ``palm...`` (palm links). The genuine Wuji meshes,
    joints, actuators and contact parameters are unchanged; only geom names (and the display group of collision
    meshes, which have no visual role) are set, so the same predicate code measures either hand.
    """
    prefix = record["prefix"]
    wrapper = next(body for body in source.iter("body") if body.get("name") == PALM_BODY)
    for link in wrapper.iter("body"):
        name = link.get("name") or ""
        if not name.startswith(prefix):
            continue
        vendor = name[len(prefix):]
        finger = hands.finger_of(vendor)
        for i, item in enumerate(link.findall("geom")):
            if item.get("contype") == "0":
                item.set("name", f"wuji_{vendor}_visual{i}")
                continue
            item.set("group", "3")
            if finger is None:
                item.set("name", f"palm_wuji_{vendor}_collision{i}")
            elif vendor.endswith("tip_sensor_frame"):
                item.set("name", f"right_{finger}_fingertip_collision" + (f"_{i}" if i > 1 else ""))
            else:
                item.set("name", f"right_{finger}_wuji_{vendor}_collision{i}")


def build(spec, asset_dir=None, hand="sharpa"):
    """Return (MjModel, task-joint initial positions, XML) without changing assets.

    ``hand="wuji"`` swaps the Sharpa Wave for the genuine Wuji Hand 2.2 in the same wrist-stage mount
    (HAND_INTERFACE.md); the Sharpa scene is built exactly as before.
    """
    hand_id = hands.canonical(hand)
    folder = Path(asset_dir or os.environ.get("DEXHAND_ASSET_DIR", "/opt/dexhand/hand"))
    source = ET.parse(folder / "right_hand.xml").getroot()
    source.find("compiler").set("meshdir", str((folder / "assets/right").resolve()))
    source.find("option").set("timestep", "0.002")
    source.find("option").set("gravity", "0 0 -9.81")
    source.find("option").set("iterations", "80")
    source.find("option").set("ls_iterations", "20")
    node(source.find("option"), "flag", multiccd="enable")
    node(source, "visual")
    node(source.find("visual"), "global", offwidth=1280, offheight=720)
    world = source.find("worldbody")
    hand = world.find("body")
    world.remove(hand)
    wrist = node(world, "body", name="wrist_stage")
    node(
        wrist,
        "inertial",
        pos="0 0 0",
        mass="0.01",
        diaginertia="0.00001 0.00001 0.00001",
    )
    wrist.append(hand)
    hand.set("pos", "0 0 0")
    hand.set("quat", "0 0.7071067811865476 0 0.7071067811865476")
    actuator = source.find("actuator")
    for i, name in enumerate(WRIST_JOINTS):
        axis = tuple(1 if j == i % 3 else 0 for j in range(3))
        joint = ET.Element(
            "joint",
            name=name,
            type="slide" if i < 3 else "hinge",
            axis=_s(axis),
            range="-0.5 0.7" if i < 2 else ("0.12 0.7" if i == 2 else "-3.14 3.14"),
            damping="15" if i < 3 else "1",
            armature="0.02",
        )
        wrist.insert(i, joint)
        actuator.insert(
            i,
            ET.Element(
                "position",
                name=name + "_act",
                joint=name,
                kp="1500" if i < 3 else "100",
                kv="60" if i < 3 else "6",
                inheritrange="1",
                forcerange="-80 80" if i < 3 else "-10 10",
            ),
        )
    geom(
        world,
        "table",
        size=(0.5, 0.4, 0.05),
        pos=(0.05, 0, 0.05),
        color="0.77 0.76 0.72 1",
    )
    node(world, "light", pos="0 0 1.2", dir="0 0 -1", diffuse="0.8 0.8 0.8")
    node(world, "light", pos="-0.5 -0.4 0.6", dir="1 1 -1", diffuse="0.45 0.45 0.45")
    node(
        world,
        "camera",
        name="overview",
        pos="0.6 -0.65 0.62",
        xyaxes="0.78 0.62 0 -0.27 0.34 0.90",
        fovy="42",
    )
    node(
        world,
        "camera",
        name="side",
        pos="0.03 -0.7 0.30",
        xyaxes="1 0 0 0 0.22 0.976",
        fovy="40",
    )
    node(
        hand,
        "camera",
        name="palm",
        pos="-0.23 0 0.10",
        xyaxes="0 -1 0 0 0 1",
        fovy="60",
    )
    if essential.is_essential(spec):
        # Close-up views of the held object (standard mode publishes no object state): both look at the grasp
        # region about 0.1 m along the fingers from the mount and 0.04 m above the palm, from about 0.2 m away;
        # `inhand_top` from above the palm, `inhand_side` from the thumb side. They are mounted on the hand body like
        # `palm` (frame: x along the palm normal, z along the fingers), which the essential families lock in place.
        node(hand, "camera", name="inhand_top", pos="0.21 0.09 0.04", xyaxes="0 0.6 0.8 0.507 -0.6895 0.5172",
             fovy="45")
        node(hand, "camera", name="inhand_side", pos="0.12 0.2 0.1", xyaxes="0 0 1 0.9216 -0.3881 0", fovy="45")
    if hand_id == "wuji":
        records = hands.replace_wave_hands(source, "wuji")
        if essential.is_essential(spec):
            alias_wuji_geoms(source, records[0])
    if essential.is_essential(spec):
        # Lock all six wrist coordinates with native constraints. The runtime
        # also rejects changes to these six targets, preventing actuator wiggle.
        equality = source.find("equality")
        if equality is None:
            equality = node(source, "equality")
        for name, value in zip(WRIST_JOINTS, essential.initial_wrist(spec)):
            node(
                equality, "joint", name="fixed_" + name, joint1=name,
                polycoef=(value, 0, 0, 0, 0), solref=(0.002, 1),
                solimp=(0.9999, 0.9999, 0.0001),
            )
        # The vendor's general actuators contain a positive velocity term.
        # These new scenes use explicit dissipative position servos; the
        # original thirty scenes and read-only vendor assets are unchanged.
        velocity_gain = spec.get("parameters", {}).get("finger_velocity_gain", -0.9)
        for act in actuator:
            if act.tag == "general":
                bias = [float(x) for x in act.get("biasprm", "0 0 0").split()]
                bias[2] = velocity_gain
                act.set("biasprm", _s(bias))
        helper = essential.module(spec)
        initial = helper.build(world, spec)
        if hasattr(helper, "configure"):
            helper.configure(source, spec)
        from essential_visual import configure as configure_presentation
        configure_presentation(source)
    else:
        mechanism = Mechanism(world, spec)
        mechanism.build()
        initial = mechanism.initial
    xml = ET.tostring(source, encoding="unicode")
    return mujoco.MjModel.from_xml_string(xml), initial, xml
