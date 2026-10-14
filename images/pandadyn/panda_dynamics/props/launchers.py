"""Reused audited finite-mass launcher geometry, with task-declared passive return."""

import numpy as np
import sapien
from .primitives import add_box, container_shapes
from .fixtures import DrivenFixture


def build_launcher(scene, origin=(0.12, 0, 0.13), pad_offset=0.075, lever_mass=0.07):
    """Offset strike pad keeps the robot out of the projectile flight plane."""
    builder = scene.create_articulation_builder()
    root = builder.create_link_builder()
    root.set_name("lever_base")
    add_box(root, [0.02, 0.02, 0.015], [0, 0, -0.035])
    lever = builder.create_link_builder(root)
    lever.set_name("lever")
    lever.set_joint_name("lever_hinge")
    axis = [np.sqrt(0.5), 0, 0, np.sqrt(0.5)]
    lever.set_joint_properties(
        "revolute",
        [[0, 1.2]],
        sapien.Pose(q=axis),
        sapien.Pose(q=axis),
        friction=0,
        damping=0,
    )
    add_box(lever, [0.09, 0.025, 0.008], [-0.03, 0, 0])
    offset = pad_offset
    add_box(lever, [0.018, abs(offset) / 2, 0.008], [0.04, offset / 2, 0])
    nc, nv = len(lever.collision_records), len(lever.visual_records)
    container_shapes(lever, (0.027, 0.027), 0.012)
    for record in lever.collision_records[nc:] + lever.visual_records[nv:]:
        record.pose = sapien.Pose([-0.12, 0, 0.012]) * record.pose
    pad = builder.create_link_builder(lever)
    pad.set_name("lever_pad")
    pad.set_joint_name("lever_passive_pad_spring")
    zaxis = [np.sqrt(0.5), 0, -np.sqrt(0.5), 0]
    pad.set_joint_properties(
        "prismatic",
        [[-0.030, 0.002]],
        sapien.Pose([0.04, offset, 0.045], zaxis),
        sapien.Pose(q=zaxis),
        friction=0,
        damping=0,
    )
    add_box(pad, [0.018, 0.025, 0.006])
    builder.initial_pose = sapien.Pose(origin)
    articulation = builder.build(name="lever_fixture", fix_root_link=True)
    for link, mass in [
        (articulation.links[1], lever_mass),
        (articulation.links[2], 0.008),
    ]:
        rb = link._objs[0]
        rb.inertia *= mass / rb.mass
        rb.mass = mass
    spring = articulation._objs[0].active_joints[1]
    spring.set_drive_properties(80.0, 0.2, 3.0, mode="force")
    spring.set_drive_target(0.0)
    spring.set_drive_velocity_target(0.0)
    fixture = DrivenFixture(
        articulation, articulation.links[1], speed=0.0, force=0.0, kp=0.0, kd=0.0
    )
    fixture.enabled = False
    return fixture
