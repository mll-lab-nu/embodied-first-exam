"""Recognizable HARIO MSS-1DTB-style hand mill with passive shaft/knob joints.

Public product data constrain the envelope; local part dimensions are declared
authoring estimates. Native hinge friction approximates grinding load. There are
no object actuators, applied object forces, bean fracture or generated grounds.
"""

import math
import xml.etree.ElementTree as ET

import numpy as np
from scipy.spatial.transform import Rotation

BODY_HEIGHT = 0.174
CRANK_RADIUS = 0.080
CRANK_Z = 0.175
KNOB_CENTER_Z = 0.204
INITIAL_PHASE = -math.pi / 2
DRY_LOAD_NM = 0.080
VISCOUS_LOAD_NMS = 0.012


def vec(values):
    return " ".join(f"{float(x):.17g}" for x in values)


def node(parent, tag, **attrs):
    return ET.SubElement(parent, tag, {k: vec(v) if isinstance(v, (tuple, list, np.ndarray)) else str(v)
                                      for k, v in attrs.items()})


def contact(parent, **attrs):
    values = dict(friction=(0.55, 0.0001, 0.00001), condim=3,
                  solref=(0.004, 1), solimp=(0.95, 0.99, 0.001), mass=0)
    values.update(attrs)
    return node(parent, "geom", **values)


def lathe_mesh(asset, name, profile, segments=128):
    vertices, faces = [], []
    for radius, z in profile:
        for j in range(segments):
            a = 2 * math.pi * j / segments
            vertices.append((max(radius, 1e-6) * math.cos(a), max(radius, 1e-6) * math.sin(a), z))
    for i in range(len(profile)):
        for j in range(segments):
            a, b = i * segments + j, i * segments + (j + 1) % segments
            c, d = ((i + 1) % len(profile)) * segments + (j + 1) % segments, ((i + 1) % len(profile)) * segments + j
            faces.extend(((a, b, c), (a, c, d)))
    node(asset, "mesh", name=name, vertex=np.array(vertices).ravel(), face=np.array(faces).ravel())


def metal_link(parent, name, start, end, width=0.010, thickness=0.002):
    start, end = np.asarray(start), np.asarray(end)
    direction = end - start
    rotation, _ = Rotation.align_vectors([direction / np.linalg.norm(direction)], [[1, 0, 0]])
    xyzw = rotation.as_quat()
    contact(parent, name=name, type="box", size=(np.linalg.norm(direction) / 2, width / 2, thickness / 2),
            pos=(start + end) / 2, quat=xyzw[[3, 0, 1, 2]], material="mill_steel")


def add_grinder(root, position):
    asset, world = root.find("asset"), root.find("worldbody")
    if asset is None:
        asset = node(root, "asset")
    node(asset, "material", name="mill_black_resin", rgba=(0.09, 0.105, 0.11, 1), roughness=0.42)
    node(asset, "material", name="mill_clear_resin", rgba=(0.35, 0.38, 0.39, 0.35), specular=0.6, shininess=0.7)
    node(asset, "material", name="mill_steel", rgba=(0.68, 0.70, 0.71, 1), metallic=0.9, roughness=0.25)
    node(asset, "material", name="mill_ceramic", rgba=(0.86, 0.84, 0.77, 1), roughness=0.8)
    cup_profile = [(0, 0), (0.023, 0), (0.026, 0.003), (0.026, 0.008), (0.025, 0.078),
                   (0.0255, 0.086), (0.0235, 0.086), (0.023, 0.008), (0.022, 0.004), (0, 0.004)]
    hopper_profile = [(0, 0.080), (0.026, 0.080), (0.026, 0.101), (0.027, 0.115),
                      (0.030, 0.130), (0.034, 0.153), (0.036, 0.169), (0.036, 0.174),
                      (0.033, 0.174), (0.033, 0.166), (0.031, 0.153), (0.027, 0.128), (0.023, 0.111), (0, 0.105)]
    lathe_mesh(asset, "mill_cup_mesh", cup_profile)
    lathe_mesh(asset, "mill_hopper_mesh", hopper_profile)
    mill = node(world, "body", name="grinder", pos=position)
    node(mill, "freejoint", name="grinder_free")
    node(mill, "inertial", pos=(0, 0, 0.106), mass=0.325, diaginertia=(0.00092, 0.00092, 0.00018))
    node(mill, "geom", name="mill_cup_visual", type="mesh", mesh="mill_cup_mesh", material="mill_clear_resin",
         contype=0, conaffinity=0, group=2, mass=0)
    node(mill, "geom", name="mill_hopper_visual", type="mesh", mesh="mill_hopper_mesh", material="mill_black_resin",
         contype=0, conaffinity=0, group=2, mass=0)
    for name, radius, half, z in [("cup", 0.025, 0.038, 0.042), ("waist", 0.026, 0.023, 0.102),
                                  ("lower_hopper", 0.030, 0.016, 0.138), ("upper_hopper", 0.035, 0.016, 0.158)]:
        contact(mill, name="mill_" + name + "_collision", type="cylinder", size=(radius, half), pos=(0, 0, z),
                rgba=(0, 0, 0, 0), group=3)
    contact(mill, name="mill_base", type="cylinder", size=(0.026, 0.002), pos=(0, 0, 0.002), material="mill_black_resin")
    contact(mill, name="mill_lid", type="cylinder", size=(0.036, 0.002), pos=(0, 0, 0.172), material="mill_clear_resin")
    node(mill, "site", name="body_grip", pos=(0, 0, 0.105), size=0.003, group=5)
    # An unpowered bearing supports the steel shaft relative to the free body.
    rotor = node(mill, "body", name="crank", pos=(0, 0, CRANK_Z),
                 quat=(math.cos(INITIAL_PHASE / 2), 0, 0, math.sin(INITIAL_PHASE / 2)))
    node(rotor, "joint", name="crank_rotation", type="hinge", axis=(0, 0, 1), limited="false",
         frictionloss=DRY_LOAD_NM, damping=VISCOUS_LOAD_NMS, armature=0.00002)
    node(rotor, "inertial", pos=(0.025, 0, -0.03), mass=0.050,
         diaginertia=(0.000020, 0.000090, 0.000080))
    contact(rotor, name="crank_shaft", type="cylinder", size=(0.003, 0.042), pos=(0, 0, -0.025), material="mill_steel")
    contact(rotor, name="crank_center_cap", type="cylinder", size=(0.010, 0.006), pos=(0, 0, 0.003), material="mill_black_resin")
    metal_link(rotor, "crank_bent_root", (0, 0, 0.003), (0.016, 0, 0.015))
    metal_link(rotor, "crank_handle", (0.016, 0, 0.015), (CRANK_RADIUS, 0, 0.015))
    contact(rotor, name="inner_burr", type="cylinder", size=(0.012, 0.011), pos=(0, 0, -0.060), material="mill_ceramic")
    knob = node(rotor, "body", name="knob", pos=(CRANK_RADIUS, 0, 0.015))
    node(knob, "joint", name="knob_spin", type="hinge", axis=(0, 0, 1), limited="false",
         frictionloss=0.00005, damping=0.00002)
    node(knob, "inertial", pos=(0, 0, 0.014), mass=0.025,
         diaginertia=(0.000002, 0.000002, 0.0000018))
    contact(knob, name="knob_resin_neck", type="cylinder", size=(0.006, 0.005), pos=(0, 0, 0.005), material="mill_black_resin")
    contact(knob, name="knob_resin_bulb", type="ellipsoid", size=(0.014, 0.014, 0.016), pos=(0, 0, 0.014),
            material="mill_black_resin")
    node(knob, "site", name="knob_grip", pos=(0, 0, 0.014), size=0.003, group=5)
    return mill
