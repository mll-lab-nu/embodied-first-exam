"""Shared surface palette for TopoGym scenes (module A).

One place owns the semantic material roles so every task builds surfaces the
same way, instead of scattering inline ``gs.surfaces.Plastic(...)`` calls with
ad-hoc roughness values (the pre-unification code had 12 distinct values
between 0.5 and 0.95 across 35 call sites).

Colors stay caller/config-driven — this module only owns the per-role finish.

Rasterizer note (see docs/develop/visual/photorealism_workstream_zh.md): Genesis'
rasterizer honors only a surface's diffuse color/texture and opacity;
``roughness`` is raytracer-only and currently has no visual effect. The
per-role values are kept anyway so a future renderer upgrade inherits a
consistent finish for free.
"""

from __future__ import annotations

import genesis as gs
import numpy as np

# Per-role finish. Values consolidate the sensible majority of the previous
# inline constants (matte boards/markers, slightly glossier rigid objects).
_ROLE_ROUGHNESS = {
    "table": 0.90,       # shared table top
    "stage": 0.95,       # optional staging pad
    "frame": 0.70,       # decorative table frame / apron
    "board": 0.90,       # task boards, workspaces, discard zones, substrates
    "marker": 0.95,      # flat visual indicators: holes, slots, cells, path dots
    "fixture": 0.80,     # static rigid posts, pegs, supports, axes
    "connector": 0.85,   # graspable endpoint handles / plugs
    "object": 0.80,      # manipulable rigid bodies: blocks, walls, plates, tabs
    "deformable": 0.75,  # PBD visual skins: ropes, cables, film
}


def plastic(
    role: str, color, *, vis_mode: str | None = None, texture=None
) -> gs.surfaces.Plastic:
    """Return the standard Plastic surface for a semantic ``role``.

    ``color`` is required (RGB tuple/list, usually straight from config).
    ``vis_mode`` is passed through for deformable visual skins.

    ``texture`` is an ``(H, W, 3)`` uint8 array to use as the DIFFUSE image --
    the only texture slot the rasterizer honours. `Plastic` also accepts
    `normal_texture`, `roughness_texture` and the rest, and they are silently
    dropped: `surface_uvs_to_trimesh_visual` builds the visual from
    `surface.get_rgba()` alone. Passing one costs nothing and does nothing, which
    is the worst kind of failure, so this entry point exposes only the slot that
    works.

    Two consequences of that same function, both worth knowing before using this:
    the mesh must carry UVs (without them the texture collapses to its mean
    colour), and the image is applied against a white diffuse, so the texture's
    own colours are final and ``color`` stops having any effect.
    """

    if role not in _ROLE_ROUGHNESS:
        raise ValueError(
            f"Unknown material role {role!r}; expected one of {sorted(_ROLE_ROUGHNESS)}."
        )
    kwargs = {
        "color": tuple(float(channel) for channel in color),
        "roughness": _ROLE_ROUGHNESS[role],
    }
    if vis_mode is not None:
        kwargs["vis_mode"] = str(vis_mode)
    if texture is not None:
        image = np.ascontiguousarray(texture)
        if image.dtype != np.uint8:
            # The renderer asserts this; failing here says which texture is wrong.
            raise ValueError(
                f"texture must be uint8, got {image.dtype} -- the rasterizer "
                f"asserts uint8 (genesis/utils/mesh.py)."
            )
        kwargs["diffuse_texture"] = gs.textures.ImageTexture(image_array=image)
    return gs.surfaces.Plastic(**kwargs)


def texture_reaches_renderer(surface) -> str:
    """Report whether the renderer will actually see ``surface``'s image texture.

    The visual is built from ``surface.get_rgba()``, not from the
    ``diffuse_texture`` field directly, so a texture set in the wrong place is
    accepted, raises nothing, and renders as flat colour. This turns that silent
    case into a line in the build log.
    """

    try:
        resolved = surface.get_rgba()
    except Exception as exc:  # pragma: no cover - depends on Genesis internals
        return f"unverified({type(exc).__name__})"
    if isinstance(resolved, gs.textures.ImageTexture):
        shape = getattr(getattr(resolved, "image_array", None), "shape", "?")
        return f"ok{shape}"
    return f"FLAT({type(resolved).__name__})"
