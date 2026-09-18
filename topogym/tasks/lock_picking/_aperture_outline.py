"""Paint aperture contours into the rotor's visual texture, on both faces.

The silhouette uses the same 720 radial samples as disc_assets(). Only the
solid side of the opening receives paint. No geometry or dynamics is changed.
"""
from copy import deepcopy
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import distance_transform_edt
import trimesh
from trimesh.visual.material import PBRMaterial
from trimesh.visual.texture import TextureVisuals


def paint_aperture_outline(urdf_path, g, slots, disc_color, cfg):
    urdf_path = Path(urdf_path)
    if cfg is None or not bool(cfg.get('enabled', False)):
        (urdf_path.parent/'aperture_outline.json').unlink(missing_ok=True)
        return
    width = float(cfg.get('width_m', .0015))
    color = np.asarray(cfg.get('color_rgb', [1., .95, 0.]), dtype=float)
    if not np.isfinite(width) or not 0 < width < g.disc_radius-g.slot_radius:
        raise ValueError('Aperture paint width must fit on the solid rotor face')
    if color.shape != (3,) or not np.all(np.isfinite(color)) or np.any((color<0)|(color>1)):
        raise ValueError('Outline color must be finite RGB in [0,1]')
    tree = ET.parse(urdf_path)
    visuals = tree.findall('.//visual/geometry/mesh')
    if len(visuals) != 1:
        raise ValueError('Rotor outline expects the single combined visual mesh')
    source = Path(visuals[0].get('filename'))
    mesh = trimesh.load(source, force='mesh', process=False)

    size, strip_height = 2048, 32
    extent = g.disc_radius * 1.02
    angles = np.arange(720) * 2*np.pi/720
    degrees = np.degrees(angles)
    error = np.minimum.reduce([np.abs((degrees-s+180)%360-180) for s in slots])
    radii = np.where(error <= g.slot_half_deg, g.slot_radius, g.bore_radius)
    # Texture rows run downwards; +z runs upwards on the physical rotor.
    pixel = np.c_[(radii*np.sin(angles)/extent+1)*(size-1)/2,
                  (1-radii*np.cos(angles)/extent)*(size-1)/2]
    opening = Image.new('L', (size, size))
    ImageDraw.Draw(opening).polygon([tuple(p) for p in pixel], fill=255)
    solid = np.asarray(opening) == 0
    distance_m = distance_transform_edt(solid) * (2*extent/(size-1))
    paint = solid & (distance_m <= width)
    face = np.empty((size, size, 3), dtype=np.uint8)
    face[:] = (np.asarray(disc_color)*255).astype(np.uint8)
    face[paint] = np.rint(color*255).astype(np.uint8)

    if mesh.visual.kind == 'texture':
        material = deepcopy(mesh.visual.material)
        original = material.baseColorTexture.convert('RGB')
        uv = np.asarray(mesh.visual.uv).copy()
    else:
        material = PBRMaterial(metallicFactor=.35, roughnessFactor=.45)
        original = Image.new('RGB', (1, 1), tuple((np.asarray(disc_color)*255).astype(int)))
        uv = np.full((len(mesh.vertices), 2), .5)
    height = size + strip_height
    atlas = Image.new('RGB', (size, height))
    atlas.paste(original.resize((size, strip_height), Image.Resampling.NEAREST), (0, 0))
    atlas.paste(Image.fromarray(face), (0, strip_height))
    # Preserve existing ear/pin colours in a separate strip of the same atlas.
    uv[:, 1] = 1-(1-uv[:, 1])*strip_height/height
    v = mesh.vertices
    rotor_faces = np.isclose(np.abs(v[:, 0]), g.disc_thickness/2, atol=2e-7, rtol=0)
    rotor_faces &= np.linalg.norm(v[:, 1:3], axis=1) <= g.disc_radius+1e-7
    if not np.any(rotor_faces):
        raise ValueError('No rotor face vertices found for aperture paint')
    uv[rotor_faces, 0] = (v[rotor_faces, 1]/extent+1)/2
    uv[rotor_faces, 1] = 1-(strip_height+(1-v[rotor_faces, 2]/extent)*size/2)/height
    material.baseColorTexture = atlas
    mesh.visual = TextureVisuals(uv=uv, material=material)
    target = urdf_path.parent/'outlined_visual.glb'
    mesh.export(target, include_normals=True)
    visuals[0].set('filename', str(target.resolve()))
    tree.write(urdf_path, encoding='unicode')
    (urdf_path.parent/'aperture_outline.json').write_text(json.dumps(dict(
        enabled=True, width_m=width, color_rgb=color.tolist(), both_faces=True,
        paint_side='solid side of the aperture silhouette', boundary_samples=720,
        geometry_changed=False, collision_changed=False,
        source_visual=str(source), outlined_visual=str(target.resolve()),
    ), indent=2)+'\n')
