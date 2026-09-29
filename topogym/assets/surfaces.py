"""Wood finishes for the existing meshes; collision geometry stays separate."""
from pathlib import Path

import numpy as np
from PIL import Image
import trimesh
from trimesh.visual.material import PBRMaterial
from trimesh.visual.texture import TextureVisuals


def wood_visual(mesh, texture_file, *, roughness, tile_size, grain_horizontal=False):
    """Box-project a real wood texture with per-corner UVs and smooth normals.

    Duplicating visual vertices at UV seams leaves every triangle in place.
    Texture coordinates are explicitly generated; zero UVs would look like a
    flat brown plastic surface.
    """
    vertices = mesh.vertices[mesh.faces].reshape(-1, 3)
    normals = mesh.vertex_normals[mesh.faces].reshape(-1, 3)
    dominant = np.repeat(np.argmax(np.abs(mesh.face_normals), axis=1), 3)
    u_axis = np.where(dominant == 0, 1, 0)
    v_axis = np.where(dominant == 2, 1, 2)
    rows = np.arange(len(vertices))
    uv = np.column_stack((vertices[rows, u_axis], vertices[rows, v_axis])) / tile_size + .5
    if grain_horizontal:
        uv = uv[:, ::-1]
    with Image.open(Path(texture_file)) as source:
        texture = source.convert("RGB")
    result = trimesh.Trimesh(vertices=vertices,
        faces=np.arange(len(vertices)).reshape(-1, 3),
        vertex_normals=normals, process=False)
    result.visual = TextureVisuals(uv=uv, material=PBRMaterial(
        name="light_wood" if grain_horizontal else "dark_wood",
        baseColorFactor=(1., 1., 1., 1.), baseColorTexture=texture,
        metallicFactor=0., roughnessFactor=roughness))
    return result


ROLE_ROUGHNESS = {
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
