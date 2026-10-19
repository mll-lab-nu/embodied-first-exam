"""Desk fan (HTF1220-style estimate) with open wire cages, a free front guard and four passive perimeter clips.

Adapted from the T26 scene-expansion source (``scene_expansion/repairs/fan_guard_meta_delivery_polish_r1_capture_
trajectory_r1/geometry.py``): same cage radius, wire layout, blade meshes, fan body, masses and clip U-channel
geometry. Physical changes for a 2 ms hand simulation (all disclosed in README.md):

* the 45 mg articulated snap leaf and its bracket are kept as visual-only shapes; the clip detent is the source's
  over-centre elastic tendon (stiffer, so a closed clip stays closed under the guard's weight);
* the centre badge is a 22 mm tall raised hub cap (source 6 mm) so a hand can grip its edge in front of the spokes;
* dish spokes and inner hoops collide with the hand, the table and the rims, but not with the other cage's spokes;
* the disconnected plug and cord are static decoration.
"""

from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from scipy.spatial.transform import Rotation

TABLE = 0.650
FAN_POSITION = np.array([0.73, 0.18, TABLE + 0.302])
RADIUS = 0.1845
RIM_WIRE = 0.0018
AXIAL = np.array([-1.0, 0.0, 0.0])  # cage axis, pointing from the fan toward the operator (world -x)
ANGLES = np.deg2rad([45, 135, 225, 315])
UPPER = (0, 1)  # upper clips: must lock after the guard is seated
LOWER = (2, 3)  # lower clips (all four clips start open)
# Hook-lip centre along the clip axis: the lower hanger clips have a 1.3 mm deeper lip (0.65 mm axial play on the
# seated rim) so the hung guard cannot tip forward; the upper clips keep the source lip (1.95 mm play) and clear the
# seated rim while they swing closed.
HOOK_X = {0: 0.0122, 1: 0.0122, 2: 0.0109, 3: 0.0109}
OPEN = 1.40
GUARD_SEAT = 0.00365  # seated front-rim plane, in front of the rear-rim plane along AXIAL
TOTAL_MASS = 2.35868
GUARD_MASS = 0.185
CLIP_MASS = 0.004
CAP_RADIUS = 0.043
CAP_HALF = 0.011
CAP_AXIAL = 0.046
CLIP_SPRING_STIFFNESS = 2500.0
CLIP_SPRING_LENGTH = 0.011
GUARD_REST = np.array([0.48, -0.275, TABLE + RIM_WIRE])
GUARD_REST_ROTATION = np.array([[0, 0, -1], [0, 1, 0], [1, 0, 0]], float)  # dome up, flat on the worktop


def vec(a):
    return " ".join(f"{float(x):.17g}" for x in a)


def node(p, tag, **kwargs):
    return ET.SubElement(
        p, tag, {k: vec(v) if isinstance(v, (list, tuple, np.ndarray)) else str(v) for k, v in kwargs.items()}
    )


def quat(r):
    return np.roll(Rotation.from_matrix(r).as_quat(), 1)


def frame(angle):
    radial = np.array([0.0, np.cos(angle), np.sin(angle)])
    return np.column_stack([AXIAL, radial, np.cross(AXIAL, radial)])


def contact(**kw):
    base = dict(group=2, mass=0, friction=(0.5, 0.001, 0.00005), solref=(0.004, 1), solimp=(0.95, 0.99, 0.0003))
    base.update(kw)
    return base


def visual(**kw):
    return dict(group=2, mass=0, contype=0, conaffinity=0, **kw)


def wire(body, name, p, q, radius=0.00065, material="fan_wire", **kw):
    node(body, "geom", name=name, type="capsule", fromto=(*p, *q), size=(radius,), material=material, **contact(**kw))


# Dish wires collide with hands, table, rims and fan body, never with the other cage's dish wires.
DISH = dict(contype=0, conaffinity=1)


def hoop(body, name, radius, axial=0.0, thickness=0.00065, n=96, **kw):
    for j in range(n):
        a, b = 2 * np.pi * j / n, 2 * np.pi * (j + 1) / n
        wire(
            body,
            f"{name}_{j}",
            (axial, radius * np.cos(a), radius * np.sin(a)),
            (axial, radius * np.cos(b), radius * np.sin(b)),
            thickness,
            **kw,
        )


def dish(radius, sign):
    return sign * 0.047 * (1 - radius / RADIUS) ** 0.70


def grille(body, name, front=True):
    """Dished open wire cage: load-bearing rim, three hoops, 96 radial spokes and the centre badge/cap."""
    sign = 1 if front else -1
    hoop(body, name + "_rim", RADIUS, thickness=RIM_WIRE)
    for radius in [0.065, 0.130, 0.173]:
        hoop(body, name + "_hoop_" + str(radius), radius, dish(radius, sign), **DISH)
    for j in range(96):
        a = 2 * np.pi * j / 96
        for k, (r0, r1) in enumerate(zip([0.043, 0.065, 0.130, 0.173], [0.065, 0.130, 0.173, RADIUS])):
            wire(
                body,
                f"{name}_spoke_{j}_{k}",
                (dish(r0, sign), r0 * np.cos(a), r0 * np.sin(a)),
                (dish(r1, sign), r1 * np.cos(a), r1 * np.sin(a)),
                0.00050,
                **DISH,
            )
    axial, half = (CAP_AXIAL, CAP_HALF) if front else (0.038, 0.003)
    node(
        body,
        "geom",
        name=name + "_badge",
        type="cylinder",
        pos=(sign * axial, 0, 0),
        quat=quat(Rotation.from_euler("y", np.pi / 2).as_matrix()),
        size=(CAP_RADIUS, half),
        material="fan_black",
        **contact(friction=(0.9, 0.003, 0.0001)),
    )
    if front:
        node(
            body,
            "geom",
            name=name + "_badge_ring",
            type="cylinder",
            pos=(sign * (axial + half + 0.0002), 0, 0),
            quat=quat(Rotation.from_euler("y", np.pi / 2).as_matrix()),
            size=(CAP_RADIUS * 0.72, 0.0003),
            material="fan_badge",
            **visual(),
        )


def assets(root, asset_dir):
    a = root.find("asset")
    for name, rgba, spec in [
        ("fan_black", (0.026, 0.029, 0.032, 1), 0.65),
        ("fan_badge", (0.10, 0.105, 0.11, 1), 0.85),
        ("fan_wire", (0.045, 0.048, 0.050, 1), 0.70),
        ("fan_clip", (0.07, 0.075, 0.08, 1), 0.40),
        ("fan_rubber", (0.085, 0.087, 0.09, 1), 0.05),
        ("plug_metal", (0.56, 0.58, 0.60, 1), 0.80),
    ]:
        node(a, "material", name=name, rgba=rgba, specular=spec, shininess=0.5)
    for i in range(3):
        node(a, "mesh", name=f"blade_mesh_{i}", file=str(Path(asset_dir) / f"blade-{i}.stl"))


def make_fan(root, tendon, asset_dir, clip_initial):
    """Add the fan (free body on its feet), the static plug and the free front guard; return (fan, guard)."""
    assets(root, asset_dir)
    world = root.find("worldbody")
    fan = node(world, "body", name="fan", pos=FAN_POSITION)
    node(fan, "freejoint", name="fan_free")
    node(
        fan,
        "inertial",
        pos=(0.042, 0, -0.105),
        mass=TOTAL_MASS - GUARD_MASS - 4 * CLIP_MASS - 0.020,
        diaginertia=(0.032, 0.035, 0.019),
    )
    node(fan, "geom", name="fan_base", type="ellipsoid", pos=(0.045, 0, -0.277), size=(0.140, 0.120, 0.022),
         material="fan_black", **contact())
    for x, y in [(-0.050, -0.085), (-0.050, 0.085), (0.135, -0.070), (0.135, 0.070)]:
        node(fan, "geom", name=f"foot_{x}_{y}", type="cylinder", pos=(x, y, -0.299), size=(0.010, 0.003),
             material="fan_rubber", **contact(friction=(0.9, 0.003, 0.0001)))
    node(fan, "geom", name="fan_stem", type="capsule", fromto=(0.060, 0, -0.257, 0.059, 0, -0.055), size=(0.022,),
         material="fan_black", **contact())
    node(fan, "geom", name="fan_neck", type="ellipsoid", pos=(0.05, 0, -0.055), size=(0.05, 0.029, 0.041),
         material="fan_black", **contact())
    node(fan, "geom", name="motor_housing", type="ellipsoid", pos=(0.063, 0, 0), size=(0.075, 0.055, 0.055),
         material="fan_black", **contact())
    node(fan, "geom", name="oscillation_knob", type="cylinder", pos=(0.098, 0, 0.061), size=(0.006, 0.008),
         material="fan_black", **contact())
    for i in range(4):
        node(fan, "geom", name=f"speed_button_{i}", type="cylinder", pos=(-0.036, (i - 1.5) * 0.013, -0.249),
             size=(0.005, 0.006 if i else 0.004), material="fan_black", **contact())
    rear = node(fan, "body", name="rear_grille", quat=(0, 0, 0, 1))
    grille(rear, "rear", False)
    for i in range(3):
        node(rear, "geom", name=f"stationary_blade_{i}", type="mesh", mesh=f"blade_mesh_{i}", material="fan_black",
             **contact())
    node(rear, "geom", name="blade_nut", type="cylinder", pos=(0.018, 0, 0), size=(0.014, 0.009),
         quat=quat(Rotation.from_euler("y", np.pi / 2).as_matrix()), material="fan_black", **contact())
    # Slack cord and disconnected plug: static decoration lying on the worktop.
    points = [(0.13, 0, -0.25), (0.15, -0.035, -0.28), (0.18, -0.07, -0.295), (0.20, -0.13, -0.295),
              (0.19, -0.20, -0.295)]
    origin = FAN_POSITION
    for i, (p, q) in enumerate(zip(points, points[1:])):
        node(world, "geom", name=f"power_cord_{i}", type="capsule", fromto=(*(origin + p), *(origin + q)),
             size=(0.002,), material="fan_black", **visual())
    node(world, "geom", name="disconnected_plug", type="box", pos=origin + (0.19, -0.218, -0.297),
         size=(0.009, 0.016, 0.005), material="fan_black", **visual())
    for x in [0.187, 0.193]:
        node(world, "geom", name=f"plug_prong_{x}", type="box", pos=origin + (x, -0.241, -0.297),
             size=(0.0008, 0.009, 0.0025), material="plug_metal", **visual())
    for i, angle in enumerate(ANGLES):
        B = frame(angle)
        localpos = AXIAL * (-0.004) + B[:, 1] * (RADIUS + 0.0033)
        clip = node(fan, "body", name=f"clip_{i}", pos=localpos, quat=quat(B))
        node(clip, "inertial", pos=(0.006, 0, 0), mass=CLIP_MASS, diaginertia=(0.00000015, 0.00000015, 0.00000006))
        node(clip, "joint", name=f"clip_hinge_{i}", axis=(0, 0, 1), range=(0, OPEN), damping=0.0003,
             frictionloss=0.00015, armature=2e-6, solreflimit=(0.004, 1), ref=0)
        # U channel folding over both rims: solid bridge and lip (hook). Contact geometry, no lock or equality.
        node(clip, "geom", name=f"clip_{i}_bridge", type="box", pos=(0.0065, 0, 0), size=(0.0065, 0.0008, 0.006),
             material="fan_clip", **contact(friction=(0.8, 0.002, 0.0001)))
        node(clip, "geom", name=f"clip_{i}_hook", type="box", pos=(HOOK_X[i], -0.002, 0), size=(0.0008, 0.0028, 0.006),
             material="fan_clip", **contact(friction=(0.8, 0.002, 0.0001)))
        # Thumb tab on the bridge's outer face (operated by a fingertip).
        node(clip, "geom", name=f"clip_{i}_tab", type="box", pos=(0.0105, 0.0022, 0), size=(0.0025, 0.0014, 0.0055),
             material="fan_clip", **contact(friction=(0.9, 0.003, 0.0001)))
        # Source snap leaf/lug and bracket: visual only here (the detent is the elastic tendon below).
        node(clip, "geom", name=f"clip_{i}_snap_leaf", type="box", pos=(0.004, 0.00045, 0.0065),
             size=(0.006, 0.001, 0.0003), material="fan_clip", **visual())
        node(clip, "geom", name=f"clip_{i}_snap_lug", type="box", pos=(0.010, 0.00065, 0.0065),
             size=(0.0018, 0.001, 0.0004), material="fan_clip", **visual())
        bracket = node(fan, "body", name=f"clip_{i}_snap_bracket", pos=localpos, quat=quat(B))
        for gname, pos, size in [
            ("shelf", (0.010, 0.00265, 0.0065), (0.0018, 0.001, 0.0004)),
            ("mount", (0.0045, 0.00365, 0.012), (0.0113, 0.001, 0.0004)),
            ("return", (0.015, 0.00365, 0.00925), (0.0008, 0.001, 0.00315)),
            ("shelf_link", (0.01265, 0.00365, 0.0065), (0.00165, 0.001, 0.0004)),
        ]:
            node(bracket, "geom", name=f"clip_{i}_snap_{gname}", type="box", pos=pos, size=size, material="fan_clip",
                 **visual())
        # Over-centre elastic detent (two stable end stops); constant parameters, no task-state input.
        anchor = B @ np.array([-0.008 * np.cos(OPEN / 2), -0.008 * np.sin(OPEN / 2), 0]) + localpos
        node(fan, "site", name=f"clip_anchor_{i}", pos=anchor, size=0.0002, group=5)
        node(clip, "site", name=f"clip_spring_{i}", pos=(0.009, 0, 0), size=0.0002, group=5)
        spring = node(tendon, "spatial", name=f"clip_elastic_{i}", stiffness=CLIP_SPRING_STIFFNESS,
                      springlength=CLIP_SPRING_LENGTH, damping=0.02, width=0.0002, rgba=(0, 0, 0, 0))
        node(spring, "site", site=f"clip_anchor_{i}")
        node(spring, "site", site=f"clip_spring_{i}")
    guard = node(world, "body", name="front_guard", pos=GUARD_REST, quat=quat(GUARD_REST_ROTATION))
    node(guard, "freejoint", name="guard_free")
    node(guard, "inertial", pos=(0.018, 0, 0), mass=GUARD_MASS, diaginertia=(0.0033, 0.0017, 0.0017))
    grille(guard, "front", True)
    return fan, guard
