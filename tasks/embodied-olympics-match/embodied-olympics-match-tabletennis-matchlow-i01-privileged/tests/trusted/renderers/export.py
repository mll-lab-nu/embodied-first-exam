"""Scene export for the path-traced renderers (cycles, isaac): the format of scripts/olympiad/showcase/blender/
export_scene.py (scene.json, meshes.npz, poses.npz), written from a renderer's own MuJoCo model, a list of world
states and one camera per state. Geometry = the model's own meshes and tessellated primitives; materials and lights
= the showcase model's; the camera of each frame = its CameraDef (as lookat / distance / azimuth / elevation; the
path tracers keep the world z axis up, so a camera's `up` must be +z)."""
from __future__ import annotations

import json
import os
import sys

import numpy as np

from .base import CameraDef
from .scene_check import DEFAULT_RGBA, effective_rgba

SHOWCASE_TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "olympiad",
                              "showcase")


def _geom_mesh():
    sys.path[:0] = [p for p in (SHOWCASE_TOOLS, os.path.join(SHOWCASE_TOOLS, "blender")) if p not in sys.path]
    from export_scene import geom_mesh
    return geom_mesh


def export(m, frames: list, outdir: str, title: str = "renderer") -> dict:
    """frames = [(state, CameraDef)], all cameras with the same size and field of view. Returns the scene summary."""
    import mujoco as mj
    from .mujoco import MujocoRenderer  # noqa: F401  (same state handling)
    cams = [c for _, c in frames]
    if len({(c.width, c.height, c.fovy_deg) for c in cams}) != 1:
        raise ValueError("one export holds cameras of one size and field of view")
    for c in cams:
        if abs(abs(float(np.dot(c.up, (0, 0, 1)))) - float(np.linalg.norm(c.up))) > 1e-9 or c.up[2] <= 0:
            raise ValueError(f"camera {c.name}: the path tracers support up = +z only")
    geom_mesh = _geom_mesh()
    os.makedirs(outdir, exist_ok=True)
    d = mj.MjData(m)
    geoms, meshes = [], {}
    for g in range(m.ngeom):
        if m.geom_group[g] not in (0, 1, 2):
            continue
        rgba = np.asarray(effective_rgba(m, g), float)
        if rgba[3] <= 0.01:
            continue
        gm = geom_mesh(m, g)
        if gm is None:
            continue
        v, f, shade = gm
        meshes[f"v{g}"], meshes[f"f{g}"] = v.astype(np.float32), f.astype(np.int32)
        mid = int(m.geom_matid[g])
        mat = dict(specular=0.5, shininess=0.5, reflectance=0.0, emission=0.0, tex=None, texrepeat=[1, 1])
        if mid >= 0:
            mat.update(specular=float(m.mat_specular[mid]), shininess=float(m.mat_shininess[mid]),
                       emission=float(m.mat_emission[mid]), reflectance=float(m.mat_reflectance[mid]),
                       texrepeat=[float(x) for x in m.mat_texrepeat[mid]])
            tid = int(m.mat_texid[mid, mj.mjtTextureRole.mjTEXROLE_RGB])
            if tid >= 0 and m.tex_type[tid] == mj.mjtTexture.mjTEXTURE_2D:
                from PIL import Image
                h, w, c = m.tex_height[tid], m.tex_width[tid], m.tex_nchannel[tid]
                px = m.tex_data[m.tex_adr[tid]:m.tex_adr[tid] + h * w * c].reshape(h, w, c)[..., :3]
                name = f"tex{tid}.png"
                if not os.path.exists(os.path.join(outdir, name)):
                    Image.fromarray(px).save(os.path.join(outdir, name))
                mat["tex"] = name
                rgba = m.mat_rgba[mid].astype(float) if np.allclose(m.geom_rgba[g], DEFAULT_RGBA) else rgba
        geoms.append(dict(id=g, name=m.geom(g).name or f"geom{g}", type=int(m.geom_type[g]),
                          size=[float(x) for x in m.geom_size[g]], rgba=[float(x) for x in rgba], shade=shade,
                          static=bool(m.body_weldid[m.geom_bodyid[g]] == 0), mat=mat))
    np.savez_compressed(os.path.join(outdir, "meshes.npz"), **meshes)
    ids = [gg["id"] for gg in geoms]
    pos = np.zeros((len(frames), len(ids), 3), np.float32)
    rot = np.zeros((len(frames), len(ids), 9), np.float32)
    for j, (state, _) in enumerate(frames):
        d.qpos[:] = np.asarray(state["qpos"], float)
        if m.nmocap and "mocap_pos" in state:
            d.mocap_pos[:] = np.asarray(state["mocap_pos"], float).reshape(-1, 3)
        if m.nmocap and "mocap_quat" in state:
            d.mocap_quat[:] = np.asarray(state["mocap_quat"], float).reshape(-1, 4)
        mj.mj_kinematics(m, d)
        mj.mj_comPos(m, d)
        mj.mj_camlight(m, d)
        pos[j], rot[j] = d.geom_xpos[ids], d.geom_xmat[ids]
    np.savez_compressed(os.path.join(outdir, "poses.npz"), pos=pos, rot=rot, step=np.arange(len(frames)))
    lights = [dict(name=m.light(i).name or f"light{i}", type=int(m.light_type[i]) if hasattr(m, "light_type") else 0,
                   pos=[float(x) for x in d.light_xpos[i]], dir=[float(x) for x in d.light_xdir[i]],
                   diffuse=[float(x) for x in m.light_diffuse[i]], cutoff=float(m.light_cutoff[i]),
                   exponent=float(m.light_exponent[i]), castshadow=bool(m.light_castshadow[i]),
                   bulbradius=float(m.light_bulbradius[i])) for i in range(m.nlight)]
    sky = None
    for t in range(m.ntex):
        if m.tex_type[t] == mj.mjtTexture.mjTEXTURE_SKYBOX:
            h, w, c = m.tex_height[t], m.tex_width[t], m.tex_nchannel[t]
            px = m.tex_data[m.tex_adr[t]:m.tex_adr[t] + h * w * c].reshape(-1, w, c)
            sky = dict(top=(px[:h // 6].reshape(-1, c)[:, :3].mean(0) / 255).tolist(),
                       horizon=(px[h * 5 // 6 - h // 12: h * 5 // 6].reshape(-1, c)[:, :3].mean(0) / 255).tolist())
    scene = dict(sport=title, decor=None, fps=1.0, fovy=float(cams[0].fovy_deg), geoms=geoms, lights=lights,
                 headlight=dict(ambient=[float(x) for x in m.vis.headlight.ambient],
                                diffuse=[float(x) for x in m.vis.headlight.diffuse]),
                 sky=sky, cameras=[CameraDef.spherical(c) for c in cams], steps=list(range(len(frames))))
    with open(os.path.join(outdir, "scene.json"), "w") as f:
        json.dump(scene, f)
    return dict(geoms=len(geoms), frames=len(frames), lights=len(lights))
