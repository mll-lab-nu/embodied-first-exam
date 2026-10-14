"""One-axis physical articulations. Only finite motor targets change after reset."""

from __future__ import annotations
import numpy as np
import sapien
from .primitives import add_box, container_shapes, material
from .supports import pedestal, hanging_stand


class DrivenFixture:
    def __init__(
        self,
        articulation,
        link,
        speed=0.0,
        force=10.0,
        kp=50.0,
        kd=5.0,
        motion="linear",
        phase=0.0,
    ):
        self.articulation = articulation
        self.raw = articulation._objs[0]
        self.link = link
        self.joint = self.raw.active_joints[0]
        self.speed, self.force, self.kp, self.kd = speed, force, kp, kd
        self.motion, self.phase = motion, phase
        self.target = phase
        self.enabled = True
        self.joint.set_drive_properties(kp, kd, force, mode="force")
        self.joint.set_friction(0.0)
        self.work = 0.0
        # PhysX reports a revolute position wrapped into one branch, while a
        # constant-speed target keeps growing; only joints whose limits allow
        # more than one turn need the target moved onto the measured branch.
        low, high = self.joint.get_limits()[0]
        self.continuous = self.joint.type == "revolute" and high - low > 2 * np.pi

    def drive_target(self):
        if not self.continuous:
            return self.target
        return self.q + (self.target - self.q + np.pi) % (2 * np.pi) - np.pi

    def reset(self, q=0.0, v=0.0):
        qpos = np.zeros(self.raw.dof, dtype=np.float32)
        qpos[0] = q
        qvel = np.zeros(self.raw.dof, dtype=np.float32)
        qvel[0] = v
        self.raw.set_qpos(qpos)
        self.raw.set_qvel(qvel)
        self.target = self.phase = q
        self.work = 0.0
        self.joint.set_drive_target(q)
        self.joint.set_drive_velocity_target(v)
        if self.motion == "spring":
            self.target = 0.0
            self.joint.set_drive_target(0.0)
            self.joint.set_drive_velocity_target(0.0)

    def step(self, time, dt):
        if not self.enabled:
            return
        velocity_target = self.speed
        if self.motion == "oscillate":
            amplitude = 0.20
            frequency = self.speed / amplitude
            self.target = self.phase + amplitude * np.sin(frequency * time)
            velocity_target = self.speed * np.cos(frequency * time)
        else:
            self.target = self.phase + self.speed * time
        target = self.drive_target()
        self.joint.set_drive_target(target)
        self.joint.set_drive_velocity_target(velocity_target)
        effort = np.clip(
            self.kp * (target - self.q) + self.kd * (velocity_target - self.v),
            -self.force,
            self.force,
        )
        self.work += float(effort * self.v * dt)

    @property
    def q(self):
        return float(self.raw.qpos[0])

    @property
    def v(self):
        return float(self.raw.qvel[0])

    def state(self):
        return dict(
            target=self.target,
            phase=self.phase,
            work=self.work,
            enabled=self.enabled,
            speed=self.speed,
        )

    def restore(self, state):
        for k, v in state.items():
            setattr(self, k, v)
        self.joint.set_drive_target(self.drive_target())
        self.joint.set_drive_velocity_target(self.speed if self.enabled else 0.0)


def single_axis(
    scene,
    name,
    origin,
    kind="slider",
    shape="cup",
    radius=0.1,
    force=12.0,
    speed=0.1,
    mass=0.3,
    platform_half=(0.14, 0.09),
    cup_half=(0.075, 0.075),
    slider_axis="y",
):
    builder = scene.create_articulation_builder()
    root = builder.create_link_builder()
    root.set_name(name + "_base")
    # Base geometry below the moving link, no overlap.
    add_box(root, [0.025, 0.025, 0.02], [0, 0, -0.07], color=[0.22, 0.25, 0.29, 1])
    pedestal(root, origin, top_local=-0.09)
    moving = builder.create_link_builder(root)
    moving.set_name(name)
    if kind == "slider":
        axis = (
            [np.sqrt(0.5), 0, 0, np.sqrt(0.5)] if slider_axis == "y" else [1, 0, 0, 0]
        )
        limits = [[-0.5, 0.5]]
        jtype = "prismatic"
        rail_half = [0.025, 0.25, 0.007] if slider_axis == "y" else [0.25, 0.025, 0.007]
        add_box(root, rail_half, [0, 0, -0.045], color=[0.42, 0.45, 0.47, 1])
        # The explicit prismatic joint represents the bearing; these collidable
        # meshes make its rail and sled visible without welding any payload.
        add_box(moving, [0.018, 0.018, 0.012], [0, 0, -0.025], color=[0.28, 0.31, 0.33, 1])
        add_box(moving, [0.012, 0.012, 0.006], [0, 0, -0.010], color=[0.28, 0.31, 0.33, 1])
    else:
        axis = [np.sqrt(0.5), 0, -np.sqrt(0.5), 0]
        limits = [[-100, 100]]
        jtype = "revolute"
    moving.set_joint_name(name + "_joint")
    moving.set_joint_properties(
        jtype,
        limits,
        sapien.Pose(q=axis),
        sapien.Pose(q=axis),
        friction=0.0,
        damping=0.0,
    )
    if shape == "cup":
        container_shapes(moving, cup_half, 0.06)
    elif shape == "platform":
        add_box(moving, [*platform_half, 0.01], [0, 0, -0.01])
    elif shape == "carousel":
        add_box(moving, [radius + 0.10, 0.035, 0.008], [radius / 2, 0, -0.02])
        # Shift the cup off-axis: its aperture follows an orbit.
        temp_count = len(moving.collision_records)
        container_shapes(moving, (0.07, 0.07), 0.06)
        for r in moving.collision_records[temp_count:]:
            r.pose = sapien.Pose([radius, 0, 0]) * r.pose
        for r in moving.visual_records[-5:]:
            r.pose = sapien.Pose([radius, 0, 0]) * r.pose
    elif shape == "socket":
        # Square 26 mm opening for a 16 mm peg, open through its bottom.
        for dx, dy, hx, hy in [
            (radius - 0.022, 0, 0.008, 0.03),
            (radius + 0.022, 0, 0.008, 0.03),
            (radius, -0.022, 0.014, 0.008),
            (radius, 0.022, 0.014, 0.008),
        ]:
            add_box(moving, [hx, hy, 0.018], [dx, dy, 0])
    builder.initial_pose = sapien.Pose(origin)
    art = builder.build(name=name + "_fixture", fix_root_link=True)
    rb = art.links[1]._objs[0]
    rb.inertia *= mass / rb.mass
    rb.mass = mass
    fixture = DrivenFixture(
        art, art.links[1], speed=speed, force=force, kp=80.0, kd=8.0
    )
    if kind == "slider":
        fixture.motion = "oscillate"
    fixture.origin = np.array(origin)
    fixture.radius = radius
    return fixture


def hinged_prop(scene, name, pivot, length=0.25, mass=0.12, upright=False, lever=False):
    builder = scene.create_articulation_builder()
    root = builder.create_link_builder()
    root.set_name(name + "_base")
    add_box(root, [0.02, 0.02, 0.015], [0, 0, -0.035], color=[0.2, 0.2, 0.25, 1])
    if not lever and not upright:
        hanging_stand(root, pivot)
    else:
        pedestal(root, pivot, top_local=-0.05)
    moving = builder.create_link_builder(root)
    moving.set_name(name)
    axis = [np.sqrt(0.5), 0, 0, np.sqrt(0.5)]  # x hinge axis rotated onto world y
    moving.set_joint_properties(
        "revolute",
        [[0, 1.2]] if lever else [[-1.45, 1.45]],
        sapien.Pose(q=axis),
        sapien.Pose(q=axis),
        friction=0.0,
        damping=0.0,
    )
    moving.set_joint_name(name + "_hinge")
    if lever:
        # 120 mm launch arm and 60 mm strike arm; the pad is 40 mm off-axis.
        # Do not extend an unused arm into the basket's incoming path.
        add_box(moving, [length * 0.375, 0.025, 0.008], [-length * 0.125, 0, 0])
        start = len(moving.collision_records)
        vstart = len(moving.visual_records)
        container_shapes(moving, (0.027, 0.027), 0.012)
        for r in moving.collision_records[start:]:
            r.pose = sapien.Pose([-length / 2, 0, 0.012]) * r.pose
        for r in moving.visual_records[vstart:]:
            r.pose = sapien.Pose([-length / 2, 0, 0.012]) * r.pose
        pad = builder.create_link_builder(moving)
        pad.set_name(name + "_pad")
        pad.set_joint_name(name + "_passive_pad_spring")
        zaxis = [np.sqrt(0.5), 0, -np.sqrt(0.5), 0]
        pad.set_joint_properties(
            "prismatic",
            [[-0.030, 0.002]],
            sapien.Pose([0.04, 0, 0.045], zaxis),
            sapien.Pose(q=zaxis),
            friction=0.0,
            damping=0.0,
        )
        add_box(pad, [0.018, 0.035, 0.006])
        pad.set_mass_and_inertia(0.008, sapien.Pose(), [5e-6] * 3)
    else:
        direction = 1 if upright else -1
        add_box(moving, [0.009, 0.009, length / 2], [0, 0, direction * length / 2])
        moving.add_sphere_collision(
            radius=0.026,
            pose=sapien.Pose([0, 0, direction * length]),
            material=material(0.5, 0.05),
        )
        moving.add_sphere_visual(
            radius=0.026,
            pose=sapien.Pose([0, 0, direction * length]),
            material=[0.9, 0.45, 0.1, 1],
        )
    # Density-derived COM and inertia are scaled together, keeping geometry intact.
    builder.initial_pose = sapien.Pose(pivot)
    art = builder.build(name=name + "_fixture", fix_root_link=True)
    if lever:
        # Unloaded at reset. A finite, passive pad spring spreads the impact;
        # no motor kick and no initial stored launch energy are supplied.
        spring = art._objs[0].active_joints[1]
        spring.set_drive_properties(80.0, 0.2, 3.0, mode="force")
        spring.set_drive_target(0.0)
        spring.set_drive_velocity_target(0.0)
    link = art.links[1]
    rb = link._objs[0]
    ratio = mass / rb.mass
    rb.inertia *= ratio
    rb.mass = mass
    f = DrivenFixture(art, link, speed=0.0, force=0.0, kp=0.0, kd=0.0)
    f.enabled = False
    f.origin = np.array(pivot)
    f.length = length
    return f
