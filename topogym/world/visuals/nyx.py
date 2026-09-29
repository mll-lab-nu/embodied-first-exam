"""Nyx camera and pre-build surface overrides, tested with gs121/plugin 0.1.4.

Loaded by the shared presentation path only when Nyx is selected.
No rigid material, collision mesh, pose, mass, or controller is modified here.
"""

from fnmatch import fnmatchcase
import os
from pathlib import Path

import genesis as gs
from genesis.utils.geom import pos_lookat_up_to_T
import numpy as np
from omegaconf import OmegaConf
from PIL import Image
from trimesh.visual.material import PBRMaterial
from trimesh.visual.texture import TextureVisuals




def apply_finishes(manifest, rules) -> dict:
    """Apply explicit PBR finishes before build, to both entity and visual meshes.

    Nyx 0.1.4's geometry exporter drops roughness and metalness for ColorVisuals.
    Use texture visuals on explicitly styled meshes so its surface export path
    carries the full finish. Geometry, UV-independent color and physics stay intact.
    URDFs take a separate nested-scene path: child visuals may keep their source
    material despite the parent override. Those assets must embed their PBR
    finish at generation time (as the staged-lock key does).
    """
    applied = {}
    for name, entity in manifest.entities.items():
        finish = None
        for rule in rules:
            if fnmatchcase(name, str(rule.pattern)):
                finish = rule
        if finish is None:
            continue
        color = tuple(float(v) for v in finish.color)
        maps = {key: asset_path(finish[key]) for key in ("diffuse_map", "normal_map") if key in finish}
        for path in maps.values():
            if not path.is_file():
                raise FileNotFoundError(
                    f"Missing material: {path}; run scripts/prepare_nyx_studio.py or set "
                    "TOPOGYM_VISUAL_ASSET_ROOT to the prepared visual asset directory"
                )
        surfaces = [entity.surface]
        for geom in entity.vgeoms:
            geom.vmesh.set_color(color)
            surfaces.append(geom.vmesh.surface)
        for surface in surfaces:
            surface.color = np.asarray(color)
            surface.diffuse_texture = gs.textures.ColorTexture(color=color)
            surface.metallic = float(finish.metallic)
            surface.roughness = float(finish.roughness)
            surface.roughness_texture = gs.textures.ColorTexture(color=(surface.roughness,))
            for key, slot in (("diffuse_map", "diffuse_texture"), ("normal_map", "normal_texture")):
                if key in maps:
                    setattr(surface, slot, gs.textures.ImageTexture(image_path=str(maps[key])))
        for geom in entity.vgeoms:
            # Preserve the primitive's UVs for image maps. Nyx's native boxes use
            # their built-in face UVs; the rasterizer reads these mesh UVs.
            uv = geom.vmesh.uvs
            if uv is None:
                uv = np.zeros((len(geom.vmesh.verts), 2))
            images = {}
            for key, slot in (("diffuse_map", "baseColorTexture"), ("normal_map", "normalTexture")):
                if key in maps:
                    with Image.open(maps[key]) as source:
                        images[slot] = source.convert("RGB")
            geom.vmesh.trimesh.visual = TextureVisuals(
                uv=uv,
                material=PBRMaterial(
                    baseColorFactor=(np.asarray((*color[:3], 1.0)) * 255).astype(np.uint8),
                    metallicFactor=float(finish.metallic),
                    roughnessFactor=float(finish.roughness),
                    **images,
                ),
            )
        applied[name] = {"color": color, "metallic": float(finish.metallic),
                         "roughness": float(finish.roughness), **{k: str(v) for k, v in maps.items()}}
    return applied









from topogym.assets.library import visual_asset_path as asset_path
