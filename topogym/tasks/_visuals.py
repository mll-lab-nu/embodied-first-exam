"""Shared scene dressing (module B to `topogym/world/materials.py`'s module A).

`materials` owns the finish; this module owns the *shapes* that recur across
tasks. Everything built here is `collision=False`, which is the standing rule
for decoration in this repo (see
`docs/develop/visual/stacked_plate_visual_upgrade_zh.md`): switching any of it
off must not move a single contact.

The repo has no asset directory and no checked-in meshes -- every piece of
geometry is generated in code, and the `.obj` files under `.cache/topogym/` and
`runs/generated_meshes/` are build products, both gitignored. So a "standard
asset" here is a builder function, not a file.
"""

from __future__ import annotations

import genesis as gs
import numpy as np
from omegaconf import OmegaConf

from topogym.world import materials

# A support block shorter than this has no room to show a brace or a cap collar
# -- a 6 mm knee brace on a 12 mm pad is noise, not detail. Below the threshold
# `add_industrial_pedestal` draws the foot plate and anchor bolts only. This is
# a "does this shape read at all" cutoff, not a design dial, so it stays here
# rather than in config.
_PEDESTAL_TALL_M = 0.030


def _to_container(value):
    if OmegaConf.is_config(value):
        return OmegaConf.to_container(value, resolve=True)
    return value


def _cfg_get(cfg, name: str, default=None):
    if OmegaConf.is_config(cfg):
        return OmegaConf.select(cfg, name, default=default)
    return getattr(cfg, name, default)


def box_entity_enabled(cfg, *, default: bool = True) -> bool:
    """Return whether a configured box should be materialized in Genesis."""

    if cfg is None or not bool(_cfg_get(cfg, "enabled", default)):
        return False

    size = _cfg_get(cfg, "size", None)
    if size is None:
        return True
    values = np.asarray(_to_container(size), dtype=float)
    if values.size == 0:
        return False
    return bool(np.all(values > 0.0))


# --------------------------------------------------------------- panel faces

def panel_face_x(panel_x: float, panel_thickness: float, face: str, depth: float) -> float:
    """Centre x for a dressing piece of thickness ``depth`` on a panel face.

    ``face`` is ``"near"`` (the -x side, where the robot works) or ``"far"``.
    The piece is seated fully outside the panel skin rather than flush with it:
    coincident faces z-fight in the rasterizer, which is the same reason
    `bar_through_hole._add_panel` tiles its frame boxes edge-to-edge.
    """

    if face == "near":
        return float(panel_x) - 0.5 * float(panel_thickness) - 0.5 * float(depth)
    if face == "far":
        return float(panel_x) + 0.5 * float(panel_thickness) + 0.5 * float(depth)
    raise ValueError(f"Unknown panel face {face!r}; expected 'near' or 'far'.")


def add_aperture_ring(
    scene,
    manifest,
    *,
    prefix: str,
    corners,
    panel_x: float,
    panel_thickness: float,
    center_z: float,
    band: float,
    depth: float,
    color,
    to_world,
    faces=("near", "far"),
) -> None:
    """A light border tracing an aperture outline, one box per edge, per face.

    ``corners`` is the outline as (N, 2) ``(y, z)`` offsets from the bore centre
    -- pass `bar_through_hole.hexagon_vertices(...)` for a hex bore, four
    corners for a rectangular one. Each segment is seated ``band / 2`` *outside*
    its edge, so the border frames the opening instead of narrowing it, and is
    over-long by ``band`` so consecutive segments meet at the corners. The
    overlap there is cosmetic: these are collision-free.
    """

    corners = np.asarray(_to_container(corners), dtype=float)
    band = float(band)
    depth = float(depth)
    for face in faces:
        face_x = panel_face_x(panel_x, panel_thickness, face, depth)
        for k in range(len(corners)):
            start, end = corners[k], corners[(k + 1) % len(corners)]
            delta = end - start
            edge_len = float(np.linalg.norm(delta))
            mid = 0.5 * (start + end)
            outward = np.array([delta[1], -delta[0]], dtype=float)
            outward /= np.linalg.norm(outward)
            if float(np.dot(outward, mid)) < 0.0:
                outward = -outward
            seat = mid + outward * (0.5 * band)
            name = f"{prefix}_{face}_{k}"
            manifest.add(
                name,
                scene.add_entity(
                    gs.morphs.Box(
                        pos=tuple(
                            to_world(
                                (face_x, float(seat[0]), float(center_z) + float(seat[1]))
                            )
                        ),
                        size=(depth, edge_len + band, band),
                        # A rotation about x turns the box within the YZ plane;
                        # the box's length axis is y, so this lays it along the
                        # edge.
                        euler=(float(np.degrees(np.arctan2(delta[1], delta[0]))), 0.0, 0.0),
                        fixed=True,
                        collision=False,
                    ),
                    surface=materials.plastic("frame", color),
                    name=name,
                ),
            )


def add_panel_bolts(
    scene,
    manifest,
    *,
    prefix: str,
    stations,
    panel_x: float,
    panel_thickness: float,
    radius: float,
    height: float,
    color,
    to_world,
    faces=("near", "far"),
) -> None:
    """Bolt heads at named ``(tag, (y, z))`` stations on one or both panel faces.

    The heads lie along x, so they read as bolts driven through the panel; on
    both faces they read as a bolt and its nut.
    """

    height = float(height)
    for face in faces:
        face_x = panel_face_x(panel_x, panel_thickness, face, height)
        for tag, (y, z) in stations:
            name = f"{prefix}_{face}_{tag}"
            manifest.add(
                name,
                scene.add_entity(
                    gs.morphs.Cylinder(
                        pos=tuple(to_world((face_x, float(y), float(z)))),
                        radius=float(radius),
                        height=height,
                        euler=(0.0, 90.0, 0.0),
                        fixed=True,
                        collision=False,
                    ),
                    surface=materials.plastic("frame", color),
                    name=name,
                ),
            )


# ------------------------------------------------------------------ pedestal

def add_industrial_pedestal(
    scene,
    manifest,
    *,
    prefix: str,
    spec,
    center_x: float,
    center_y: float,
    top_z: float,
    block_size,
    to_world,
) -> None:
    """Dress a plain support block as a bolted industrial pedestal.

    The load-bearing block itself is left exactly as the physics needs it --
    same top face, same footprint. Everything added here is `collision=False`,
    so turning the group off cannot change a contact.

    ``block_size`` is the block's full (x, y, z) and ``top_z`` its top face, both
    in the caller's frame; ``to_world`` converts a finished centre. Four pieces:

    - **foot plate** -- a wider, thinner plate at the block's base, so the block
      reads as bolted down rather than set loose on the table;
    - **anchor bolts** -- four heads centred on the lip the foot plate leaves,
      which is why the lip width sets their position instead of a config inset;
    - **knee braces** -- two struts angling from the foot plate's outer edge up
      to the block's upper flank, the piece that most says "support stand";
    - **cap collar** -- a machined lip below the top face. It stops short of the
      face by ``collar_gap``: sharing that plane would z-fight, and the real top
      face is what the payload lands on.

    Blocks shorter than `_PEDESTAL_TALL_M` get the plate and bolts only.
    """

    block = np.asarray(_to_container(block_size), dtype=float)
    half_block = 0.5 * block
    foot_scale = float(_cfg_get(spec, "foot_scale", 1.5))
    foot_thickness = float(_cfg_get(spec, "foot_thickness", 0.006))
    color = _to_container(_cfg_get(spec, "color", [0.30, 0.32, 0.35]))
    bolt_color = _to_container(_cfg_get(spec, "bolt_color", color))

    half_foot = half_block[:2] * foot_scale
    base_z = top_z - block[2]

    manifest.add(
        f"{prefix}_footplate",
        scene.add_entity(
            gs.morphs.Box(
                pos=tuple(to_world((center_x, center_y, base_z + 0.5 * foot_thickness))),
                size=(2.0 * half_foot[0], 2.0 * half_foot[1], foot_thickness),
                fixed=True,
                collision=False,
            ),
            surface=materials.plastic("fixture", color),
            name=f"{prefix}_footplate",
        ),
    )

    # Centre each bolt on the lip -- midway between the block edge and the plate
    # edge -- so it always lands on visible plate, whatever the block's aspect.
    bolt_radius = float(_cfg_get(spec, "bolt_radius", 0.0035))
    bolt_height = float(_cfg_get(spec, "bolt_height", 0.004))
    bolt_x = 0.5 * (half_block[0] + half_foot[0])
    bolt_y = 0.5 * (half_block[1] + half_foot[1])
    # Sink the head 1 mm so its underside is not coplanar with the plate's face.
    bolt_z = base_z + foot_thickness + 0.5 * bolt_height - 0.001
    for x_sign, x_tag in ((-1.0, "n"), (1.0, "f")):
        for y_sign, y_tag in ((1.0, "l"), (-1.0, "r")):
            name = f"{prefix}_anchor_{x_tag}{y_tag}"
            manifest.add(
                name,
                scene.add_entity(
                    gs.morphs.Cylinder(
                        pos=tuple(
                            to_world(
                                (
                                    center_x + x_sign * bolt_x,
                                    center_y + y_sign * bolt_y,
                                    bolt_z,
                                )
                            )
                        ),
                        radius=bolt_radius,
                        height=bolt_height,
                        fixed=True,
                        collision=False,
                    ),
                    surface=materials.plastic("fixture", bolt_color),
                    name=name,
                ),
            )

    if block[2] < _PEDESTAL_TALL_M:
        return

    collar = float(_cfg_get(spec, "collar", 0.005))
    collar_thickness = float(_cfg_get(spec, "collar_thickness", 0.008))
    collar_gap = float(_cfg_get(spec, "collar_gap", 0.001))
    collar_top = top_z - collar_gap

    # Braces run in the YZ plane, from the foot plate's outer edge up to the
    # block's flank just under the collar. Each side is built from its own
    # signed endpoints, so the two lean opposite ways without a mirroring trick.
    brace_thickness = float(_cfg_get(spec, "brace_thickness", 0.005))
    foot_z = base_z + foot_thickness
    head_z = collar_top - collar_thickness
    for y_sign, y_tag in ((1.0, "l"), (-1.0, "r")):
        start = np.array([y_sign * half_foot[1], foot_z], dtype=float)
        end = np.array([y_sign * half_block[1], head_z], dtype=float)
        delta = end - start
        span = float(np.linalg.norm(delta))
        mid = 0.5 * (start + end)
        name = f"{prefix}_brace_{y_tag}"
        manifest.add(
            name,
            scene.add_entity(
                gs.morphs.Box(
                    pos=tuple(
                        to_world(
                            (center_x, center_y + float(mid[0]), float(mid[1]))
                        )
                    ),
                    size=(0.6 * block[0], span, brace_thickness),
                    euler=(float(np.degrees(np.arctan2(delta[1], delta[0]))), 0.0, 0.0),
                    fixed=True,
                    collision=False,
                ),
                surface=materials.plastic("fixture", color),
                name=name,
            ),
        )

    manifest.add(
        f"{prefix}_collar",
        scene.add_entity(
            gs.morphs.Box(
                pos=tuple(
                    to_world((center_x, center_y, collar_top - 0.5 * collar_thickness))
                ),
                size=(
                    block[0] + 2.0 * collar,
                    block[1] + 2.0 * collar,
                    collar_thickness,
                ),
                fixed=True,
                collision=False,
            ),
            surface=materials.plastic("fixture", color),
            name=f"{prefix}_collar",
        ),
    )
