"""Shared load-bearing fixtures -- the collision counterpart to `_visuals.py`.

`_visuals` builds dressing, and everything it adds is `collision=False`. This
module builds parts a payload actually rests on, so everything here DOES
collide and switching a piece off changes the physics. Keeping the two apart is
the point: `_visuals` can be disabled wholesale to check that decoration is not
load-bearing, and that check is only meaningful if the load-bearing shapes live
somewhere else.

Same "standard asset = a builder function" convention as `_visuals`: the repo
checks in no meshes, so a reusable fixture is code.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import genesis as gs
import numpy as np
from omegaconf import OmegaConf

from topogym.world import materials


def _to_container(value):
    if OmegaConf.is_config(value):
        return OmegaConf.to_container(value, resolve=True)
    return value


def v_block_seat_drop(profile, half_angle_rad: float) -> float:
    """How far a part's axis sits above the V's apex when it settles in.

    ``profile`` is the part's cross-section as (N, 2) ``(y, z)`` corners about
    its own axis -- the same convention `_visuals.add_aperture_ring` takes, so a
    hex shaft passes `bar_through_hole.hexagon_vertices(...)` to both. Taking the
    profile rather than a radius is what makes one V-block serve round, hex and
    square stock: the seat is derived from whichever corner touches first, so a
    hex resting on two of its corners and a cylinder resting on two lines both
    come out right.

    ``half_angle_rad`` is measured from VERTICAL, so 45 degrees is the machinist
    standard 90-degree included V.

    Method: each V face is a plane through the apex. The perpendicular distance
    from the part's axis to that plane, when the part is touching, is the
    profile's support distance in the face's inward normal. A point on the axis
    at height ``h`` above the apex stands ``h * sin(half_angle)`` off the face,
    so ``h = support / sin(half_angle)``.
    """

    profile = np.asarray(_to_container(profile), dtype=float).reshape(-1, 2)
    half_angle = float(half_angle_rad)
    # Inward normal of the +y face (pointing back toward the groove).
    normal = np.array([-np.cos(half_angle), np.sin(half_angle)], dtype=float)
    support = float(np.max(-(profile @ normal)))
    return support / float(np.sin(half_angle))


def add_v_block(
    scene,
    manifest,
    *,
    prefix: str,
    center_x: float,
    center_y: float,
    apex_z: float,
    length_x: float,
    half_angle_rad: float,
    jaw_width: float,
    jaw_thickness: float,
    post_width: float,
    base_z: float,
    color,
    to_world,
) -> None:
    """A V-block: two angled jaws forming a groove, on a post down to the table.

    Three convex boxes, because that is what the payload has to touch and a
    non-convex mesh would be filled in by `convexify` (the same reason
    `bar_through_hole` builds its bored panel out of boxes).

    Why a groove instead of a flat pad: a flat top locates a part vertically and
    nothing else. Measured on `bar_through_hole`, a shaft set down on flat pads
    crept 5.2 mm sideways just settling under gravity, and the closing pads then
    turned it a further 3.3 degrees -- against a bore with 7 mm of clearance. The
    groove takes both away, because the part cannot move sideways without
    climbing.

    ``apex_z`` is the groove's bottom line; `v_block_seat_drop` converts between
    it and the height the part's axis ends up at. The two jaws are built from
    their own signed geometry rather than by mirroring one, so nothing depends on
    a sign convention holding across a copy. They overlap below the apex, which
    is fine -- volumetric overlap is invisible, only coplanar faces z-fight.

    The post is skipped when the apex is already at ``base_z``: a groove sitting
    directly on the table needs no column, and a zero-height box is not a thing
    Genesis should be asked to build.
    """

    half_angle = float(half_angle_rad)
    jaw_width = float(jaw_width)
    jaw_thickness = float(jaw_thickness)
    apex_z = float(apex_z)
    surface = materials.plastic("fixture", _to_container(color))

    for sign, tag in ((1.0, "l"), (-1.0, "r")):
        # Up-and-out along this face, and the face's inward normal.
        along = np.array([sign * np.sin(half_angle), np.cos(half_angle)], dtype=float)
        normal = np.array([-sign * np.cos(half_angle), np.sin(half_angle)], dtype=float)
        seat = (
            np.array([center_y, apex_z], dtype=float)
            + along * (0.5 * jaw_width)
            - normal * (0.5 * jaw_thickness)
        )
        name = f"{prefix}_jaw_{tag}"
        manifest.add(
            name,
            scene.add_entity(
                gs.morphs.Box(
                    pos=tuple(to_world((center_x, float(seat[0]), float(seat[1])))),
                    size=(float(length_x), jaw_width, jaw_thickness),
                    # A rotation about x turns the box within the YZ plane, and the
                    # box's `jaw_width` axis is its local y, so this lays that axis
                    # along the face.
                    euler=(float(np.degrees(0.5 * np.pi - sign * half_angle)), 0.0, 0.0),
                    fixed=True,
                ),
                surface=surface,
                name=name,
            ),
        )

    post_height = apex_z - float(base_z)
    if post_height <= 0.0:
        return
    manifest.add(
        f"{prefix}_post",
        scene.add_entity(
            gs.morphs.Box(
                pos=tuple(to_world((center_x, center_y, float(base_z) + 0.5 * post_height))),
                size=(float(length_x), float(post_width), post_height),
                fixed=True,
            ),
            surface=surface,
            name=f"{prefix}_post",
        ),
    )


# ---------------------------------------------------------------------------
# Single-DOF hinge mechanism (procedural URDF)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HingeShape:
    """One rigid part of a hinge's rotating link, in the link's local frame.

    The link's origin sits on the joint axis, so a part's ``origin`` is also its
    offset from the pivot -- which is what a lever arm is described by anyway.
    """

    kind: str  # "box" -> size (x, y, z); "cylinder" -> size (radius, length)
    size: Sequence[float]
    origin: Sequence[float] = (0.0, 0.0, 0.0)
    rpy: Sequence[float] = (0.0, 0.0, 0.0)
    color: Sequence[float] | None = None
    # Visual-only parts get no <collision>, so shaping a part for readability
    # cannot quietly change what the payload collides with -- and the judge's
    # model of the part stays the one thing that touches the ball.
    collide: bool = True

    def half_extent(self) -> np.ndarray:
        """Axis-aligned half size, used only to size the link's inertia box.

        A rotated or cylindrical part is approximated by its own bounding box.
        The inertia of a driven mechanism running against a joint limit does not
        turn on this being exact, and an exact composite tensor would be a
        machinery bill nothing here is asking for.
        """

        if self.kind == "box":
            return 0.5 * np.asarray(_to_container(self.size), dtype=float).reshape(3)
        if self.kind == "cylinder":
            radius, length = (float(v) for v in _to_container(self.size))
            return np.array([radius, radius, 0.5 * length], dtype=float)
        raise ValueError(f"Unsupported HingeShape.kind={self.kind!r}; use 'box' or 'cylinder'.")

    def geometry_xml(self) -> str:
        if self.kind == "box":
            x, y, z = (float(v) for v in _to_container(self.size))
            return f'<box size="{x:.9f} {y:.9f} {z:.9f}"/>'
        radius, length = (float(v) for v in _to_container(self.size))
        return f'<cylinder radius="{radius:.9f}" length="{length:.9f}"/>'


def _origin_xml(origin, rpy) -> str:
    ox, oy, oz = (float(v) for v in _to_container(origin))
    rr, rp, ry = (float(v) for v in _to_container(rpy))
    return f'<origin xyz="{ox:.9f} {oy:.9f} {oz:.9f}" rpy="{rr:.9f} {rp:.9f} {ry:.9f}"/>'


def _link_xml(link_name: str, *, robot_name: str, shapes: Sequence[HingeShape],
              mass: float, color) -> str:
    """One `<link>` carrying every shape in ``shapes``.

    Shared by the hinge writer and the rigid-assembly writer: several primitives
    in one link is how this repo builds a non-convex part, so a swinging lever and
    a bolted-together frame differ only in whether a joint follows.

    ``mass`` is distributed over the bounding box of the COLLIDING shapes: the
    inertial origin is that box's centre and the tensor is a solid cuboid of the
    same extent. Visual-only parts are excluded so that dressing a part cannot
    move its centre of mass. See `HingeShape.half_extent`.
    """

    shapes = list(shapes)
    if not shapes:
        raise ValueError(f"Link {link_name!r} needs at least one shape.")
    mass = float(mass)
    if mass <= 0.0:
        raise ValueError(f"Link {link_name!r} mass must be positive, got {mass}.")
    if not any(shape.collide for shape in shapes):
        raise ValueError(f"Link {link_name!r} has no colliding shape to size its inertia on.")

    lower = np.full(3, np.inf)
    upper = np.full(3, -np.inf)
    for shape in shapes:
        if not shape.collide:
            continue
        origin = np.asarray(_to_container(shape.origin), dtype=float).reshape(3)
        half = shape.half_extent()
        lower = np.minimum(lower, origin - half)
        upper = np.maximum(upper, origin + half)
    center = 0.5 * (lower + upper)
    extent = np.maximum(upper - lower, 1e-4)
    ixx = mass * (extent[1] ** 2 + extent[2] ** 2) / 12.0
    iyy = mass * (extent[0] ** 2 + extent[2] ** 2) / 12.0
    izz = mass * (extent[0] ** 2 + extent[1] ** 2) / 12.0

    default_rgba = _to_container(color)
    parts: list[str] = []
    for index, shape in enumerate(shapes):
        rgba = _to_container(shape.color) if shape.color is not None else default_rgba
        rgba_text = " ".join(f"{float(v):.6f}" for v in list(rgba)[:3]) + " 1"
        geometry = shape.geometry_xml()
        origin = _origin_xml(shape.origin, shape.rpy)
        collision = (
            f"""    <collision>
      {origin}
      <geometry>{geometry}</geometry>
    </collision>
"""
            if shape.collide
            else ""
        )
        parts.append(
            collision
            + f"""    <visual>
      {origin}
      <geometry>{geometry}</geometry>
      <material name="{robot_name}_mat_{index}">
        <color rgba="{rgba_text}"/>
      </material>
    </visual>"""
        )

    return f"""  <link name="{link_name}">
    <inertial>
      <origin xyz="{center[0]:.9f} {center[1]:.9f} {center[2]:.9f}" rpy="0 0 0"/>
      <mass value="{mass:.9f}"/>
      <inertia ixx="{ixx:.9f}" ixy="0" ixz="0" iyy="{iyy:.9f}" iyz="0" izz="{izz:.9f}"/>
    </inertial>
{chr(10).join(parts)}
  </link>"""


def write_hinge_urdf(
    path,
    *,
    robot_name: str,
    joint_name: str,
    axis,
    shapes: Sequence[HingeShape],
    mass: float,
    color,
    sliding: bool = False,
    joint_limit: tuple[float, float] | None = None,
    damping: float = 0.0,
    friction: float = 0.0,
    effort: float = 50.0,
    max_velocity: float = 5.0,
) -> Path:
    """Write a two-link URDF: a fixed base and one link on a single joint.

    Generalized from `tasks/connectivity/stacked_plate.py`'s `_write_disk_urdf`,
    which is hard-wired to one cylinder collider, the Y axis and a continuous
    joint. Three of those are wrong for a diverter flap, which needs a box
    collider, the Z axis, a joint that STOPS at each seated position, and several
    parts on the same rotating link (the flap inside the channel plus the lever
    the gripper turns it by, above the walls).

    ``sliding`` and ``joint_limit`` pick the joint type:

    ===========  =================  ==================================
    ``sliding``  ``joint_limit``    joint
    ===========  =================  ==================================
    False        ``None``           ``continuous``
    False        ``(lo, hi)`` rad   ``revolute``
    True         ``(lo, hi)`` m     ``prismatic`` (URDF requires limits)
    ===========  =================  ==================================

    The limit is load-bearing rather than a safety rail. On a hinge, a
    contact-driven sweep that overshoots is stopped by it, so the seated pose is
    set by the joint rather than by how accurately the arm tracked the arc; on a
    slide, it is the carriage's travel.

    The name says "hinge" because a hinge is all it wrote until
    `linkbar_merge_components` needed a carriage on a rail. Renaming it (and
    `HingeShape`, which `add_rigid_assembly` already uses for parts with no joint
    at all) is worth doing the next time all three call sites are open anyway.

    ``mass`` is distributed over the bounding box of ``shapes``: the inertial
    origin is that box's centre and the tensor is a solid cuboid of the same
    extent. See `HingeShape.half_extent`.

    Note for the `stacked_plate` migration (`rigid_first_track_zh.md` §7.6): its
    disk carries a *mesh* visual over a cylinder collider, and no shape kind here
    writes a `<mesh>` element yet. Adding one is a few lines, and is left until
    that task is actually migrated rather than written blind now.
    """

    path = Path(path)
    link_xml = _link_xml(
        "hinge_arm", robot_name=robot_name, shapes=shapes, mass=mass, color=color
    )

    ax, ay, az = (float(v) for v in _to_container(axis))
    if sliding and joint_limit is None:
        raise ValueError(
            "A prismatic joint needs a travel limit: URDF has no unbounded slide, "
            "and a carriage that can run off its rail is not a rail."
        )
    if joint_limit is None:
        joint_type = "continuous"
        limit_xml = ""
    else:
        joint_type = "prismatic" if sliding else "revolute"
        low, high = (float(v) for v in joint_limit)
        limit_xml = (
            f'\n    <limit lower="{low:.9f}" upper="{high:.9f}" '
            f'effort="{float(effort):.6f}" velocity="{float(max_velocity):.6f}"/>'
        )

    xml = f"""<?xml version="1.0"?>
<robot name="{robot_name}">
  <link name="hinge_base"/>
{link_xml}
  <joint name="{joint_name}" type="{joint_type}">
    <parent link="hinge_base"/>
    <child link="hinge_arm"/>
    <origin xyz="0 0 0" rpy="0 0 0"/>
    <axis xyz="{ax:.9f} {ay:.9f} {az:.9f}"/>{limit_xml}
    <dynamics damping="{float(damping):.9f}" friction="{float(friction):.9f}"/>
  </joint>
</robot>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(xml, encoding="utf-8")
    return path


def add_hinge_mechanism(
    scene,
    manifest,
    *,
    name: str,
    urdf_path,
    world_pos,
    axis,
    shapes: Sequence[HingeShape],
    mass: float,
    color,
    joint_name: str = "hinge_joint",
    yaw_deg: float = 0.0,
    sliding: bool = False,
    joint_limit: tuple[float, float] | None = None,
    damping: float = 0.0,
    friction: float = 0.0,
    armature: float = 0.01,
    contact_friction: float = 1.0,
) -> tuple[Any, str]:
    """Write the URDF and add it to the scene; returns ``(entity, joint_name)``.

    ``fixed=True`` pins the BASE link to the world, which is what a pivot bolted
    to a frame is; the joint still moves. ``convexify=False`` keeps the parts as
    the primitives they were written as, and ``recompute_inertia=False`` keeps
    the tensor `write_hinge_urdf` computed -- both matching `stacked_plate`.

    ``yaw_deg`` turns the whole mechanism, base and axis together, which is how a
    rail laid along some direction in the scene gets its shapes written in its own
    frame instead of in world coordinates.
    """

    written = write_hinge_urdf(
        urdf_path,
        robot_name=name,
        joint_name=joint_name,
        axis=axis,
        shapes=shapes,
        mass=mass,
        color=color,
        sliding=sliding,
        joint_limit=joint_limit,
        damping=damping,
        friction=friction,
    )
    entity = scene.add_entity(
        gs.morphs.URDF(
            file=str(written),
            pos=tuple(float(v) for v in _to_container(world_pos)),
            euler=(0.0, 0.0, float(yaw_deg)),
            fixed=True,
            convexify=False,
            recompute_inertia=False,
            prioritize_urdf_material=True,
            default_armature=float(armature),
        ),
        material=gs.materials.Rigid(friction=float(contact_friction)),
        name=name,
    )
    manifest.add(name, entity)
    return entity, joint_name


def hinge_joint_dof(entity, joint_name: str) -> int:
    """Local DOF index of a hinge's single joint."""

    joint = entity.get_joint(name=str(joint_name))
    return int(np.asarray(joint.dofs_idx_local).reshape(-1)[0])


# ---------------------------------------------------------------------------


def write_body_urdf(path, *, robot_name: str, shapes: Sequence[HingeShape],
                    mass: float, color) -> Path:
    """Write a one-link URDF: several primitives welded into a single rigid body.

    The case this exists for is a part that has to LOOK like an assembly and
    BEHAVE like one object. `linkbar_merge_components`' component B is a section
    of machine frame -- rails, uprights, feet -- and the lift test that judges the
    task asks whether B as a whole is held down, so B has to be one body with one
    pose, not a pile of separate entities that would drift apart.

    A single link with several `<collision>` elements is how URDF says that, and
    it is the same construction `write_hinge_urdf` already puts on its rotating
    link; the two share `_link_xml`. It is also the repo's standing answer to
    non-convex geometry -- a union of convex primitives rather than a concave
    mesh (`routing/bar_through_hole.py` bores its panel out of 8 boxes).

    No joint is written, so the body is free or pinned purely by the morph's
    ``fixed`` flag. Like `write_hinge_urdf`, no `<mesh>` shape kind exists yet.
    """

    path = Path(path)
    xml = f"""<?xml version="1.0"?>
<robot name="{robot_name}">
{_link_xml("body", robot_name=robot_name, shapes=shapes, mass=mass, color=color)}
</robot>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(xml, encoding="utf-8")
    return path


def add_rigid_assembly(
    scene,
    manifest,
    *,
    name: str,
    urdf_path,
    world_pos,
    shapes: Sequence[HingeShape],
    mass: float,
    color,
    fixed: bool = False,
    contact_friction: float = 1.0,
    yaw_deg: float = 0.0,
) -> Any:
    """Write the URDF and add it to the scene; returns the entity.

    ``convexify=False`` keeps the parts as the primitives they were written as,
    and ``recompute_inertia=False`` keeps the tensor `write_body_urdf` computed --
    both matching `add_hinge_mechanism`. Recomputing would fold the visual-only
    parts back into the mass properties, which is exactly what `_link_xml`
    excludes them from.
    """

    written = write_body_urdf(
        urdf_path, robot_name=name, shapes=shapes, mass=mass, color=color
    )
    entity = scene.add_entity(
        gs.morphs.URDF(
            file=str(written),
            pos=tuple(float(v) for v in _to_container(world_pos)),
            euler=(0.0, 0.0, float(yaw_deg)),
            fixed=bool(fixed),
            convexify=False,
            recompute_inertia=False,
            prioritize_urdf_material=True,
        ),
        material=gs.materials.Rigid(friction=float(contact_friction)),
        name=name,
    )
    manifest.add(name, entity)
    return entity
