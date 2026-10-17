"""Photo-dimensioned legacy OXO sweater dryer: passive rim hinge and offset legs.

Only the published overall footprint/height are product dimensions. Component
sections, stop angles, mass and contact properties are explicit model estimates.
There is no deployment latch: the assembly buttons join the removable end poles.
"""

import xml.etree.ElementTree as ET
import numpy as np
from scipy.spatial.transform import Rotation

DT = 0.002
WIDTH = 26 * 0.0254
HEIGHT = 4.5 * 0.0254
RADIUS = 0.0045
HALF = WIDTH / 2 - RADIUS
HINGE_OFFSET = 0.012
COUNTER_Z = 0.75
CENTRE = np.array([0.47, 0.0, COUNTER_Z + HEIGHT - 0.016])
LEG_LENGTH = HEIGHT - 0.016
LEG_X = 0.257
LEG_Y = 0.255
LEG_STOP = np.deg2rad(100)
WORLD_R = Rotation.from_euler("z", -np.pi / 2).as_matrix()


def vec(v):
    return " ".join(f"{float(x):.17g}" for x in v)


def node(parent, tag, **values):
    return ET.SubElement(
        parent, tag, {k: vec(v) if isinstance(v, (list, tuple, np.ndarray)) else str(v) for k, v in values.items()}
    )


def materials(asset):
    node(asset, "material", name="rack_polymer", rgba=(0.88, 0.88, 0.83, 1), specular=0.22, shininess=0.25)
    node(asset, "material", name="rack_tube", rgba=(0.72, 0.76, 0.77, 1), specular=0.7, shininess=0.65)
    node(asset, "material", name="rack_mesh", rgba=(0.74, 0.76, 0.70, 1), specular=0.05)
    node(asset, "material", name="rack_foot", rgba=(0.36, 0.38, 0.34, 1), specular=0.08)


def geom(parent, name, **kw):
    return node(
        parent,
        "geom",
        name=name,
        mass=0,
        friction=(0.65, 0.002, 0.0001),
        solref=(0.006, 1),
        solimp=(0.95, 0.99, 0.0005),
        condim=4,
        **kw,
    )


def panel(body, side):
    sign = -1 if side == "fixed" else 1
    z = 0 if side == "fixed" else HINGE_OFFSET
    node(body, "inertial", pos=(sign * HALF / 2, 0, z), mass=0.205, diaginertia=(0.0074, 0.0019, 0.0093))
    for y, label in [(HALF, "l"), (-HALF, "r")]:
        geom(
            body,
            f"{side}_rim_{label}",
            type="capsule",
            size=(RADIUS,),
            fromto=(sign * 0.017, y, z, sign * HALF, y, z),
            material="rack_tube",
        )
        # Real side-pole joint collar, with the pivot axis shared by both poles.
        geom(
            body,
            f"{side}_hinge_{label}",
            type="capsule",
            size=(0.010,),
            fromto=(0, y - 0.012, z, 0, y + 0.012, z),
            material="rack_polymer",
        )
    geom(
        body,
        f"{side}_end_pole",
        type="capsule",
        size=(RADIUS,),
        fromto=(sign * HALF, -HALF, z, sign * HALF, HALF, z),
        material="rack_tube",
    )
    for y, label in [(HALF, "l"), (-HALF, "r")]:
        geom(
            body,
            f"{side}_corner_{label}",
            type="box",
            size=(0.013, 0.017, 0.012),
            pos=(sign * (HALF - 0.004), y - np.sign(y) * 0.007, z),
            material="rack_polymer",
        )
        # Fixed corner push button is an assembly fixing, never an unfolding lock.
        node(
            body,
            "geom",
            name=f"{side}_assembly_button_{label}",
            type="sphere",
            size=".0025",
            pos=(sign * (HALF - 0.004), y - np.sign(y) * 0.007, z + 0.013),
            material="rack_foot",
            mass=0,
            contype=0,
            conaffinity=0,
        )
    # Coarse woven net appearance is a declared reduced cloth treatment. It is
    # not a rigid sheet supporting the hands or feet. No laundry is simulated.
    for i, y in enumerate(np.linspace(-HALF + 0.016, HALF - 0.016, 35)):
        node(
            body,
            "geom",
            name=f"{side}_net_x_{i}",
            type="capsule",
            size=".00045",
            fromto=(sign * 0.008, y, z - 0.002, sign * (HALF - 0.008), y, z - 0.002),
            material="rack_mesh",
            mass=0,
            contype=0,
            conaffinity=0,
        )
    for i, x in enumerate(sign * np.linspace(0.008, HALF - 0.008, 18)):
        node(
            body,
            "geom",
            name=f"{side}_net_y_{i}",
            type="capsule",
            size=".00045",
            fromto=(x, -HALF + 0.008, z - 0.002, x, HALF - 0.008, z - 0.002),
            material="rack_mesh",
            mass=0,
            contype=0,
            conaffinity=0,
        )
    for y, label in [(LEG_Y, "l"), (-LEG_Y, "r")]:
        # All leg mounts are inset, preserving the maker's offset-leg footprint.
        leg = node(body, "body", name=f"{side}_leg_{label}", pos=(sign * LEG_X, y, z))
        inward = -sign
        node(
            leg,
            "joint",
            name=f"{side}_leg_{label}_hinge",
            type="hinge",
            axis=(0, inward, 0),
            limited="true",
            range=(0, LEG_STOP),
            damping=0.003,
            frictionloss=0.003,
            solreflimit=(0.004, 1),
            solimplimit=(0.99, 0.999, 0.0001),
        )
        node(
            leg, "inertial", pos=(inward * LEG_LENGTH / 2, 0, 0), mass=0.025, diaginertia=(0.000003, 0.000021, 0.000021)
        )
        geom(
            leg,
            f"{side}_leg_{label}_tube",
            type="capsule",
            size=(0.004,),
            fromto=(0, 0, 0, inward * (LEG_LENGTH - 0.010), 0, 0),
            material="rack_tube",
        )
        geom(
            leg,
            f"{side}_leg_{label}_foot",
            type="sphere",
            size=(0.006,),
            pos=(inward * (LEG_LENGTH - 0.004), 0, 0),
            material="rack_foot",
        )
        # Small visible stop cheek: rotational stop behavior is represented by
        # the permanently enabled passive joint range, not by a mutable latch.
        geom(
            body,
            f"{side}_leg_{label}_mount",
            type="box",
            size=(0.011, 0.008, 0.009),
            pos=(sign * LEG_X, y, z),
            material="rack_polymer",
        )


def make_rack(world, centre=CENTRE):
    root = node(world, "body", name="rack", pos=centre, quat=np.roll(Rotation.from_matrix(WORLD_R).as_quat(), 1))
    node(root, "freejoint", name="rack_free")
    panel(root, "fixed")
    child = node(root, "body", name="moving_panel", pos=(0, 0, -HINGE_OFFSET))
    node(
        child,
        "joint",
        name="fold_hinge",
        type="hinge",
        axis=(0, 1, 0),
        limited="true",
        range=(0, np.pi),
        damping=0.001,
        frictionloss=0.0005,
        solreflimit=(0.004, 1),
        solimplimit=(0.99, 0.999, 0.0001),
    )
    panel(child, "moving")
    return root


def initial_rack(model, data, angle=1.0, legs=(LEG_STOP, LEG_STOP, 0, 0)):
    """Frozen authoring initialization only; never called during execution."""
    data.qpos[model.joint("fold_hinge").qposadr[0]] = angle
    for name, value in zip([f"{p}_leg_{s}_hinge" for p in ["fixed", "moving"] for s in ["l", "r"]], legs):
        data.qpos[model.joint(name).qposadr[0]] = value
