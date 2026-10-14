"""Finite geometry and finite-energy mechanisms reused across the V4 tasks."""

import numpy as np
import sapien
from scipy.spatial.transform import Rotation
from .primitives import add_box, finish, material, container_shapes, box
from .fixtures import DrivenFixture
from .supports import pedestal


def quat_xyz(angles):
    q = Rotation.from_euler("xyz", angles).as_quat()
    return np.r_[q[3], q[:3]]


def gravity_channel(scene, name, start, end, width=0.045, wall=0.022, mu=0.12):
    start, end = np.asarray(start), np.asarray(end)
    direction = end - start
    length = np.linalg.norm(direction)
    yaw = np.arctan2(direction[1], direction[0])
    pitch = -np.arctan2(direction[2], np.linalg.norm(direction[:2]))
    q = quat_xyz([0, pitch, yaw])
    builder = scene.create_actor_builder()
    add_box(
        builder,
        [length / 2, width, 0.005],
        [0, 0, -0.005],
        mat=material(mu),
        color=[0.48, 0.53, 0.55, 1],
    )
    for sign in (-1, 1):
        add_box(
            builder,
            [length / 2, 0.004, wall / 2],
            [0, sign * (width + 0.004), wall / 2],
            mat=material(mu),
            color=[0.28, 0.34, 0.36, 1],
        )
    return finish(builder, name, (start + end) / 2, q, static=True)


def passive_gate(
    scene,
    name,
    pivot,
    length=0.12,
    height=0.055,
    friction=0.003,
    spring=0.0,
    initial=0.0,
):
    builder = scene.create_articulation_builder()
    root = builder.create_link_builder()
    root.set_name(name + "_base")
    add_box(root, [0.013, 0.013, 0.012], [0, 0, -0.035], color=[0.28, 0.31, 0.34, 1])
    pedestal(root, pivot, top_local=-0.047)
    moving = builder.create_link_builder(root)
    moving.set_name(name)
    axis = quat_xyz([0, -np.pi / 2, 0])
    moving.set_joint_name(name + "_joint")
    moving.set_joint_properties(
        "revolute",
        [[-1.5, 1.5]],
        sapien.Pose(q=axis),
        sapien.Pose(q=axis),
        friction=friction,
        damping=0.001,
    )
    add_box(
        moving,
        [0.006, length / 2, height / 2],
        [0, -length / 2, height / 2],
        mat=material(0.2, 0.35),
        color=[0.84, 0.57, 0.19, 1],
        density=220,
    )
    add_box(
        moving,
        [0.016, 0.012, 0.012],
        [0, -length, 0.07],
        color=[0.8, 0.35, 0.17, 1],
        density=220,
    )
    builder.initial_pose = sapien.Pose(pivot)
    art = builder.build(name=name + "_fixture", fix_root_link=True)
    fixture = DrivenFixture(
        art,
        art.links[1],
        force=0.25 if spring else 0,
        kp=spring,
        kd=0.005,
        speed=0,
        phase=initial,
    )
    fixture.motion = "spring" if spring else "passive"
    fixture.enabled = False
    fixture.joint.set_friction(friction)
    fixture.reset(initial, 0)
    return fixture


def coasting_carriage(scene, name, origin, half=(0.085, 0.055), mass=0.18):
    """Passive linear carriage; no motor force after its declared initial velocity."""
    b = scene.create_articulation_builder()
    root = b.create_link_builder()
    root.set_name(name + "_base")
    add_box(root, [0.018, 0.24, 0.012], [0, 0, -0.05], color=[0.25, 0.29, 0.31, 1])
    pedestal(root, origin, top_local=-0.062)
    moving = b.create_link_builder(root)
    moving.set_name(name)
    axis = quat_xyz([0, 0, np.pi / 2])
    moving.set_joint_properties(
        "prismatic",
        [[-0.42, 0.42]],
        sapien.Pose(q=axis),
        sapien.Pose(q=axis),
        friction=0,
        damping=0,
    )
    moving.set_joint_name(name + "_free_rail")
    container_shapes(moving, half, 0.009, mat=material(0.4))
    # Thin accessible vertical handle, connected to the actual carriage chassis.
    add_box(moving, [0.014, 0.018, 0.038], [half[0] + 0.025, 0, 0.035], density=500)
    b.initial_pose = sapien.Pose(origin)
    art = b.build(name=name + "_fixture", fix_root_link=True)
    rb = art.links[1]._objs[0]
    factor = mass / rb.mass
    rb.inertia *= factor
    rb.mass = mass
    result = DrivenFixture(art, art.links[1], speed=0, force=0, kp=0, kd=0)
    result.enabled = False
    return result


class RollerConveyor(DrivenFixture):
    """Twenty actual spinning rollers, each with a bounded velocity motor."""

    def reset(self, q=0, v=0):
        self.raw.set_qpos(np.zeros(self.raw.dof, dtype=np.float32))
        self.raw.set_qvel(np.full(self.raw.dof, self.speed, dtype=np.float32))
        self.phase = q
        self.target = q
        self.work = 0.0
        for joint in self.raw.active_joints:
            joint.set_drive_properties(0, 0.012, 0.008, mode="force")
            joint.set_drive_velocity_target(self.speed)

    def step(self, time, dt):
        for joint, v in zip(self.raw.active_joints, self.raw.qvel):
            joint.set_drive_velocity_target(self.speed)
            self.work += float(
                np.clip(0.012 * (self.speed - v), -0.008, 0.008) * v * dt
            )


def roller_conveyor(scene, name, center, speed=0.09):
    b = scene.create_articulation_builder()
    root = b.create_link_builder()
    root.set_name(name + "_base")
    add_box(root, [0.08, 0.14, 0.012], [0, 0, -0.035], color=[0.26, 0.29, 0.32, 1])
    pedestal(root, center, top_local=-0.047)
    for i in range(20):
        link = b.create_link_builder(root)
        link.set_name(f"{name}_roller_{i}")
        link.set_joint_name(f"{name}_motor_{i}")
        link.set_joint_properties(
            "revolute",
            [[-1e5, 1e5]],
            sapien.Pose([0, (i - 9.5) * 0.0125, 0.008]),
            sapien.Pose(),
            friction=0,
            damping=0,
        )
        link.add_cylinder_collision(
            radius=0.006, half_length=0.068, material=material(0.9), density=350
        )
        link.add_cylinder_visual(
            radius=0.006, half_length=0.068, material=[0.38, 0.42, 0.43, 1]
        )
    b.initial_pose = sapien.Pose(center)
    art = b.build(name=name + "_fixture", fix_root_link=True)
    f = RollerConveyor(
        art, art.links[1], speed=-speed / 0.006, force=0.008, kp=0, kd=0.012
    )
    f.reset()
    return f


def cylinder(scene, name, radius=0.019, half_length=0.038, mass=0.055):
    b = scene.create_actor_builder()
    b.add_cylinder_collision(
        radius=radius, half_length=half_length, material=material(0.35, 0.05)
    )
    b.add_cylinder_visual(
        radius=radius, half_length=half_length, material=[0.94, 0.39, 0.10, 1]
    )
    return finish(b, name, [0, 0, 0.2], mass=mass)
