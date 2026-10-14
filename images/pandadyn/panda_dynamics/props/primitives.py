"""Finite-thickness procedural props. Poses use SAPIEN wxyz quaternions."""

from __future__ import annotations
import numpy as np
import sapien

BLUE = [0.12, 0.38, 0.72, 1]
ORANGE = [0.95, 0.35, 0.08, 1]
GREEN = [0.12, 0.7, 0.4, 1]


def material(mu=0.3, restitution=0.05):
    return sapien.physx.PhysxMaterial(mu, mu * 0.85, restitution)


def add_box(
    builder, half, p=(0, 0, 0), q=(1, 0, 0, 0), color=BLUE, mat=None, density=1000.0
):
    pose = sapien.Pose(p, q)
    builder.add_box_collision(
        pose=pose, half_size=half, material=mat or material(), density=density
    )
    builder.add_box_visual(pose=pose, half_size=half, material=color)


def finish(builder, name, p=(0, 0, 0), q=(1, 0, 0, 0), mass=None, static=False):
    builder.initial_pose = sapien.Pose(p, q)
    if static and name not in ("table", "floor"):
        from .supports import support_static_builder
        support_static_builder(builder, builder.initial_pose)
    actor = builder.build_static(name) if static else builder.build(name)
    if mass is not None:
        body = actor._bodies[0]
        ratio = mass / body.mass
        body.inertia = body.inertia * ratio
        body.mass = mass
        body.linear_damping = 0.0
        body.angular_damping = 0.0
    return actor


def box(
    scene,
    name,
    half,
    p,
    mass=0.05,
    mu=0.3,
    restitution=0.05,
    color=ORANGE,
    static=False,
    q=(1, 0, 0, 0),
):
    b = scene.create_actor_builder()
    add_box(b, half, color=color, mat=material(mu, restitution))
    return finish(b, name, p, q, mass=None if static else mass, static=static)


def ball(scene, name, radius=0.018, mass=0.035, restitution=0.15, mu=0.2):
    b = scene.create_actor_builder()
    b.add_sphere_collision(
        radius=radius,
        material=material(mu, restitution),
        density=mass / (4 / 3 * np.pi * radius**3),
    )
    b.add_sphere_visual(radius=radius, material=ORANGE)
    return finish(b, name, p=[0, 0, 1.0], mass=mass)


def container_shapes(
    b,
    half=(0.065, 0.065),
    height=0.055,
    thickness=0.005,
    mat=None,
    color=BLUE,
    open_side=False,
    open_sign=-1,
):
    """Actual empty opening: bottom plus four independent box walls; -x can be open."""
    x, y = half
    add_box(
        b,
        [x + thickness, y + thickness, thickness / 2],
        [0, 0, -thickness / 2],
        mat=mat,
        color=color,
    )
    for sign in [-1, 1]:
        add_box(
            b,
            [x + thickness, thickness / 2, height / 2],
            [0, sign * (y + thickness / 2), height / 2],
            mat=mat,
            color=color,
        )
        if not (open_side and sign == open_sign):
            add_box(
                b,
                [thickness / 2, y, height / 2],
                [sign * (x + thickness / 2), 0, height / 2],
                mat=mat,
                color=color,
            )


def container(
    scene,
    name,
    p,
    half=(0.065, 0.065),
    height=0.055,
    mass=0.2,
    static=False,
    mu=0.4,
    restitution=0.03,
):
    b = scene.create_actor_builder()
    container_shapes(b, half, height, mat=material(mu, restitution))
    return finish(b, name, p, mass=None if static else mass, static=static)


def make_tool(
    scene, kind: str, half: float = 0.065, mass: float = 0.2, mu=0.4, restitution=0.05
):
    b = scene.create_actor_builder()
    tool_shapes(b, kind, half, mu, restitution)
    return finish(b, "tool", mass=mass)


def tool_shapes(
    b,
    kind,
    half,
    mu=0.4,
    restitution=0.05,
    side_mount=False,
    height=None,
    vertical_mount=0.0,
):
    mat = material(mu, restitution)
    if kind == "channel":
        add_box(b, [half, 0.036, 0.004], [0, 0, -0.004], mat=mat)
        for sign in (-1, 1):
            add_box(b, [half, 0.004, 0.02], [0, sign * 0.040, 0.02], mat=mat)
    elif kind == "support_fork":
        container_shapes(b, (half, half), 0.018, mat=mat, open_side=True, open_sign=1)
    elif kind == "toss_cup":
        container_shapes(
            b, (half, half), height or 0.028, mat=mat, open_side=True, open_sign=1
        )
        # Open pouring side is a declared geometry variant. Other walls and
        # bottom remain finite solids and are also used during recatching.
    elif kind in ("cup", "scoop", "tray", "receiver"):
        heights = dict(cup=0.055, scoop=0.025, tray=0.012, receiver=0.03)
        container_shapes(
            b,
            (half, half),
            height if height is not None else heights[kind],
            mat=mat,
            open_side=kind in ("scoop", "receiver"),
            open_sign=1 if kind == "scoop" else -1,
        )
    elif kind == "plate":
        add_box(b, [half, half, 0.004], [0, 0, -0.004], mat=mat)
    elif kind in ("paddle", "fork"):
        add_box(b, [0.006, half, 0.025], mat=mat)
    elif kind == "racket":
        add_box(b, [0.004, half, half], q=[np.cos(0.45), 0, -np.sin(0.45), 0], mat=mat)
    elif kind == "pusher":
        add_box(b, [0.004, 0.025, 0.006], mat=mat)
    elif kind == "peg":
        add_box(b, [0.008, 0.008, 0.035], [0, 0, -0.035], mat=mat)
    elif kind == "mallet":
        add_box(b, [0.025, 0.025, 0.015], mat=mat)
    else:
        raise ValueError(f"Unknown tool {kind}")
    # Physical lateral adapter connects the cup/paddle to the stock TCP.
    # Its mass and off-center inertia are included by density integration.
    if vertical_mount:
        add_box(
            b,
            [0.007, 0.007, vertical_mount / 2],
            [0, 0, vertical_mount / 2],
            mat=mat,
            color=[0.25, 0.27, 0.3, 1],
        )
    elif side_mount:
        side = 1 if side_mount > 0 else -1
        reach = abs(float(side_mount))
        # Route the bridge around the active contact face, not through it.
        edge = 0.02 if kind == "mallet" else 0.04 if kind == "channel" else half
        add_box(b, [0.06, 0.006, 0.006], [-0.06, side * reach, 0.035], mat=mat)
        add_box(
            b,
            [0.006, (reach - edge) / 2, 0.006],
            [0, side * (reach + edge) / 2, 0.035],
            mat=mat,
        )
        add_box(b, [0.006, 0.006, 0.018], [0, side * edge, 0.018], mat=mat)
    else:
        add_box(
            b,
            [0.047, 0.006, 0.006],
            [-half - 0.035, 0, 0.035],
            mat=mat,
            color=[0.25, 0.27, 0.3, 1],
        )
        add_box(
            b,
            [0.006, 0.006, 0.020],
            [-half, 0, 0.015],
            mat=mat,
            color=[0.25, 0.27, 0.3, 1],
        )


def body(actor):
    return actor._bodies[0] if hasattr(actor, "_bodies") else actor._objs[0]


def position(actor):
    return body(actor).entity_pose.p.copy()


def velocity(actor):
    return body(actor).linear_velocity.copy()


def set_initial(actor, p, velocity=(0, 0, 0), q=(1, 0, 0, 0), angular=(0, 0, 0)):
    """Reset-only utility. Never call this from task update or controller code."""
    rb = body(actor)
    rb.entity_pose = sapien.Pose(p, q)
    rb.linear_velocity = velocity
    rb.angular_velocity = angular
