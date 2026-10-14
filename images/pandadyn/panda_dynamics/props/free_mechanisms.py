"""Free-root mechanisms: wheels, carrier pendulum, and a contact-operated latch.

These are ordinary articulated payloads, never attached to either Panda.
"""

import numpy as np
import sapien
from .primitives import add_box, material, container_shapes
from .fixtures import DrivenFixture
from .mechanisms import quat_xyz


def scale_mass(link, mass):
    rb = link._objs[0]
    rb.inertia *= mass / rb.mass
    rb.mass = mass


def wheeled_cart(scene, name, origin):
    builder = scene.create_articulation_builder()
    root = builder.create_link_builder()
    root.set_name(name)
    container_shapes(root, (0.065, 0.055), 0.012)
    for i, (x, y) in enumerate(
        ((-0.05, -0.04), (-0.05, 0.04), (0.05, -0.04), (0.05, 0.04))
    ):
        wheel = builder.create_link_builder(root)
        wheel.set_name(f"{name}_wheel_{i}")
        wheel.set_joint_name(f"{name}_wheel_axle_{i}")
        wheel.set_joint_properties(
            "revolute",
            [[-1e5, 1e5]],
            sapien.Pose([x, y, -0.018]),
            sapien.Pose(),
            friction=0.00001,
            damping=0,
        )
        wheel.add_cylinder_collision(
            radius=0.018, half_length=0.006, material=material(0.65), density=400
        )
        wheel.add_cylinder_visual(
            radius=0.018, half_length=0.006, material=[0.14, 0.17, 0.18, 1]
        )
    builder.initial_pose = sapien.Pose(origin)
    art = builder.build(name=name + "_assembly", fix_root_link=False)
    scale_mass(art.links[0], 0.16)
    fixture = DrivenFixture(art, art.links[0], force=0, kp=0, kd=0)
    fixture.enabled = False
    return fixture


def hanging_carrier(scene, name, origin, length=0.16):
    builder = scene.create_articulation_builder()
    root = builder.create_link_builder()
    root.set_name(name)
    add_box(root, [0.06, 0.015, 0.009], density=700, color=[0.34, 0.43, 0.49, 1])
    rod = builder.create_link_builder(root)
    rod.set_name(name + "_load")
    rod.set_joint_name(name + "_passive_hinge")
    axis = quat_xyz([0, 0, np.pi / 2])
    rod.set_joint_properties(
        "revolute",
        [[-1.3, 1.3]],
        sapien.Pose([0, 0, -0.012], axis),
        sapien.Pose(q=axis),
        friction=0.00001,
        damping=0.00003,
    )
    add_box(
        rod,
        [0.006, 0.006, length / 2],
        [0, 0, -length / 2],
        density=200,
        color=[0.45, 0.47, 0.48, 1],
    )
    rod.add_sphere_collision(
        radius=0.022, pose=sapien.Pose([0, 0, -length]), material=material(0.4)
    )
    rod.add_sphere_visual(
        radius=0.022, pose=sapien.Pose([0, 0, -length]), material=[0.92, 0.38, 0.10, 1]
    )
    builder.initial_pose = sapien.Pose(origin)
    art = builder.build(name=name + "_assembly", fix_root_link=False)
    scale_mass(art.links[0], 0.055)
    scale_mass(art.links[1], 0.06)
    fixture = DrivenFixture(art, art.links[1], force=0, kp=0, kd=0)
    fixture.enabled = False
    fixture.length = length
    return fixture


def unlock_fixture(scene, name, origin):
    builder = scene.create_articulation_builder()
    root = builder.create_link_builder()
    root.set_name(name)
    # Channel with a real exit gap and separate handle for the left hand.
    add_box(root, [0.045, 0.028, 0.005], [-0.025, 0, -0.005], density=450)
    for y in (-0.034, 0.034):
        add_box(root, [0.068, 0.006, 0.025], [0, y, 0.02], density=450)
    add_box(root, [0.008, 0.017, 0.014], [-0.083, 0, 0.025], density=450)
    # Square socket: 28 mm empty opening, finite 7 mm walls.
    for x, y, hx, hy in (
        (-0.022, 0, 0.008, 0.03),
        (0.022, 0, 0.008, 0.03),
        (0, -0.022, 0.014, 0.008),
        (0, 0.022, 0.014, 0.008),
    ):
        add_box(root, [hx, hy, 0.015], [x + 0.02, y + 0.065, 0.075], density=450)
    latch = builder.create_link_builder(root)
    latch.set_name(name + "_latch")
    latch.set_joint_name(name + "_pin_driven_latch")
    axis = quat_xyz([0, -np.pi / 2, 0])
    latch.set_joint_properties(
        "prismatic",
        [[-0.026, 0]],
        sapien.Pose(q=axis),
        sapien.Pose(q=axis),
        friction=0.04,
        damping=0.08,
    )
    add_box(
        latch,
        [0.005, 0.03, 0.010],
        [0.025, 0, 0.010],
        density=500,
        color=[0.89, 0.58, 0.18, 1],
    )
    add_box(
        latch,
        [0.008, 0.035, 0.005],
        [0.025, 0.035, 0.026],
        density=500,
        color=[0.89, 0.58, 0.18, 1],
    )
    add_box(
        latch,
        [0.011, 0.011, 0.008],
        [0.020, 0.065, 0.049],
        density=500,
        color=[0.89, 0.58, 0.18, 1],
    )
    builder.initial_pose = sapien.Pose(origin)
    art = builder.build(name=name + "_assembly", fix_root_link=False)
    scale_mass(art.links[0], 0.14)
    scale_mass(art.links[1], 0.025)
    f = DrivenFixture(art, art.links[1], force=0, kp=0, kd=0)
    f.enabled = False
    f.joint.set_friction(0.04)
    return f
