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
