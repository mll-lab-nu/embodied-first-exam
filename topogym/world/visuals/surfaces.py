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

from pathlib import Path

import genesis as gs
import numpy as np

# Per-role finish. Values consolidate the sensible majority of the previous
# inline constants (matte boards/markers, slightly glossier rigid objects).
from topogym.assets.surfaces import ROLE_ROUGHNESS


def from_spec(parameters):
    """Build a surface from Task data, resolving an optional diffuse image path.

    Tasks declare paths, not Genesis objects. A procedural image already owns
    its colour; simultaneous colour/texture declarations are rejected.
    """
    options = dict(parameters)
    image_path = options.pop("diffuse_texture_path", None)
    if image_path is not None:
        if options.get("color") is not None or options.get("diffuse_texture") is not None:
            raise ValueError("diffuse_texture_path cannot be combined with color or diffuse_texture")
        image_path = Path(image_path).expanduser().resolve()
        if not image_path.is_file():
            raise FileNotFoundError(f"Missing declared diffuse texture: {image_path}")
        options["diffuse_texture"] = gs.textures.ImageTexture(image_path=str(image_path))
    return gs.surfaces.Default(**options)


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
    own colours are final.

    Which is why ``color`` is NOT forwarded when a texture is given. Genesis
    treats ``color`` as a shorthand for ``diffuse_texture`` and rejects both at
    once ("'color' and 'diffuse_texture' cannot both be set"), so the caller's
    colour has to be baked into the image by its producer. ``color`` stays
    a required argument here so a role's palette still comes from config in one
    place, and so switching the texture off returns the same flat colour as before.
    """

    if role not in ROLE_ROUGHNESS:
        raise ValueError(
            f"Unknown material role {role!r}; expected one of {sorted(ROLE_ROUGHNESS)}."
        )
    kwargs = {"roughness": ROLE_ROUGHNESS[role]}
    if vis_mode is not None:
        kwargs["vis_mode"] = str(vis_mode)
    if texture is None:
        kwargs["color"] = tuple(float(channel) for channel in color)
    else:
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


def restore_renderer_materials(entity):
    """Keep GLB PBR finishes through Genesis' diffuse-only mesh conversion.

    Restore only the visual material before rasterizer construction. The loaded
    vertices, collision meshes and dynamics are untouched.
    """
    from pathlib import Path
    import trimesh
    from trimesh.visual.texture import TextureVisuals
    for geom in entity.vgeoms:
        mesh = geom.vmesh
        path = mesh.metadata.get("mesh_path")
        if not path or Path(path).suffix != ".glb":
            continue
        original = trimesh.load(path, force="mesh", process=False)
        if not isinstance(original.visual, TextureVisuals):
            continue
        # Keep Genesis' UVs: its loader flips them twice before rasterization.
        uv = getattr(mesh.trimesh.visual, "uv", None)
        if uv is None:
            uv = np.zeros((len(mesh.trimesh.vertices), 2))
        mesh.trimesh.visual = TextureVisuals(
            uv=uv, material=original.visual.material.copy()
        )
