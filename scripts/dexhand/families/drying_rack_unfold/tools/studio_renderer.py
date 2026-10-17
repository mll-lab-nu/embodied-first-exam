"""Blender studio render of exact native drying-rack poses (presentation only; no motion is synthesized).

blender -b -P tools/studio_renderer.py -- --export <dir> --output <film.mp4> [--samples 16] [--frame-step 1] [--cpu]
Writes <film>-frames/NNNNNN.png and render.json; tools/presentation.py encode builds the mp4.
Lighting, exposure and the rack/counter palette follow the approved T20 scene film (warm window, soft fill, rim
softbox, AgX medium-high contrast); hand materials follow the assemble_hamburger film.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
import time


def main():
    import bpy
    import numpy as np
    from mathutils import Matrix, Vector

    p = argparse.ArgumentParser()
    p.add_argument("--export", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--samples", type=int, default=16)
    p.add_argument("--frame-step", type=int, default=1)
    p.add_argument("--cpu", action="store_true")
    p.add_argument("--only", default="", help="comma separated frame indices (test stills)")
    a = p.parse_args(sys.argv[sys.argv.index("--") + 1:])
    payload = json.loads((a.export / "scene.json").read_text())
    geometry = np.load(a.export / "geometry.npz", allow_pickle=False)
    poses = np.load(a.export / "poses.npz", allow_pickle=False)
    P, Rm = poses["positions"], poses["rotations"]
    frame_dir = a.output.with_suffix("").with_name(a.output.stem + "-frames")
    frame_dir.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = a.samples
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = "OPENIMAGEDENOISE"
    scene.cycles.max_bounces = 6
    if not a.cpu:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "OPTIX"
        prefs.get_devices()
        for device in prefs.devices:
            device.use = device.type == "OPTIX"
        if not any(d.use for d in prefs.devices):
            raise RuntimeError("no OptiX device; use --cpu")
        scene.cycles.device = "GPU"
        scene.cycles.denoising_use_gpu = True
    scene.render.threads_mode = "FIXED"
    scene.render.threads = 8
    scene.render.resolution_x, scene.render.resolution_y = 1280, 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.75
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.72, 0.75, 0.77, 1)
    bg.inputs["Strength"].default_value = 0.45

    def linear(rgb):
        return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb)

    def material(name, color, roughness=0.4, metallic=0.0, coat=0.0):
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        b = m.node_tree.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (*linear(color), 1)
        b.inputs["Roughness"].default_value = roughness
        b.inputs["Metallic"].default_value = metallic
        b.inputs["Coat Weight"].default_value = coat
        return m

    def wood(m, scale):
        nodes, links = m.node_tree.nodes, m.node_tree.links
        coord = nodes.new("ShaderNodeTexCoord")
        mapping = nodes.new("ShaderNodeMapping")
        mapping.inputs["Scale"].default_value = (1.0, 14.0, 1.0)
        wave = nodes.new("ShaderNodeTexNoise")
        wave.inputs["Scale"].default_value = scale
        wave.inputs["Detail"].default_value = 6
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = (*linear((0.36, 0.24, 0.14)), 1)
        ramp.color_ramp.elements[1].color = (*linear((0.55, 0.40, 0.25)), 1)
        links.new(coord.outputs["Object"], mapping.inputs["Vector"])
        links.new(mapping.outputs["Vector"], wave.inputs["Vector"])
        links.new(wave.outputs["Fac"], ramp.inputs[0])
        links.new(ramp.outputs["Color"], m.node_tree.nodes["Principled BSDF"].inputs["Base Color"])

    tube = material("Brushed aluminium rack tube", (0.74, 0.77, 0.78), 0.28, 0.75)
    polymer = material("Ivory polymer housing", (0.90, 0.90, 0.85), 0.35, coat=0.1)
    net = material("Woven drying net", (0.78, 0.80, 0.74), 0.65)
    foot = material("Dark rubber foot", (0.30, 0.32, 0.29), 0.7)
    oak = material("Oiled oak counter", (0.47, 0.33, 0.21), 0.42, coat=0.15)
    wood(oak, 3.0)
    cabinet = material("Sage painted cabinet", (0.32, 0.39, 0.35), 0.6)
    floor = material("Warm grey floor", (0.62, 0.62, 0.58), 0.8)
    shell = material("Pearl white polymer housing", (0.89, 0.91, 0.89), 0.27, 0.10)
    rubber = material("Forest silicone fingertips", (0.10, 0.24, 0.18), 0.68)
    steel = material("Brushed stainless mechanics", (0.35, 0.39, 0.40), 0.30, 0.8)
    by_material = {"rack_tube": tube, "rack_polymer": polymer, "rack_mesh": net, "rack_foot": foot,
                   "counter_oak": oak, "counter_base": cabinet}
    cache, objects = {}, []

    def capsule_mesh(name, r, half, seg=16, rings=6):
        verts, faces = [], []
        prof = [(math.pi / 2 * j / rings, half) for j in range(rings + 1)]
        prof += [(math.pi / 2 + math.pi / 2 * j / rings, -half) for j in range(rings + 1)]
        for ang, off in prof:
            for k in range(seg):
                t = 2 * math.pi * k / seg
                verts.append((r * math.sin(ang) * math.cos(t), r * math.sin(ang) * math.sin(t), r * math.cos(ang) + off))
        for j in range(len(prof) - 1):
            for k in range(seg):
                i0, i1 = j * seg + k, j * seg + (k + 1) % seg
                faces.append((i0, i1, i1 + seg, i0 + seg))
        me = bpy.data.meshes.new(name)
        me.from_pydata(verts, [], faces)
        for poly in me.polygons:
            poly.use_smooth = True
        return me

    for gi, rec in enumerate(payload["geoms"]):
        kind, size, name = rec["kind"], rec["size"], rec["name"]
        if kind == 7:
            key = str(rec["mesh"])
            if key not in cache:
                src = payload["meshes"][key]
                me = bpy.data.meshes.new(src["name"])
                me.from_pydata(geometry[src["prefix"] + "vertices"].tolist(), [], geometry[src["prefix"] + "faces"].tolist())
                me.update()
                for poly in me.polygons:
                    poly.use_smooth = True
                cache[key] = me
            obj = bpy.data.objects.new(name, cache[key])
        elif kind == 3:
            key = f"cap_{size[0]:.5f}_{size[1]:.5f}"
            if key not in cache:
                thin = size[0] < 0.001
                cache[key] = capsule_mesh(key, size[0], size[1], 6 if thin else 20, 1 if thin else 6)
            obj = bpy.data.objects.new(name, cache[key])
        elif kind == 6:
            me = bpy.data.meshes.new(name)
            bm_verts = [(sx * size[0], sy * size[1], sz * size[2]) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
            me.from_pydata(bm_verts, [], [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)])
            obj = bpy.data.objects.new(name, me)
            if name.startswith(("fixed_corner", "moving_corner", "fixed_leg", "moving_leg")) or name.startswith("counter"):
                mod = obj.modifiers.new("bevel", "BEVEL")
                mod.width, mod.segments = (0.004 if "counter" in name else 0.002), 3
        elif kind == 2:
            key = f"sph_{size[0]:.5f}"
            if key not in cache:
                bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=size[0])
                tmp = bpy.context.object
                cache[key] = tmp.data
                for poly in tmp.data.polygons:
                    poly.use_smooth = True
                bpy.data.objects.remove(tmp)
            obj = bpy.data.objects.new(name, cache[key])
        elif kind == 0:
            me = bpy.data.meshes.new(name)
            s = 6.0
            me.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
            obj = bpy.data.objects.new(name, me)
        else:
            continue
        scene.collection.objects.link(obj)
        if rec["owner"] == "hand":
            mat = rubber if rec["material"] == "green" else steel if "_VL" in name else shell
        elif name == "floor":
            mat = floor
        else:
            mat = by_material.get(rec["material"], polymer)
        if len(obj.data.materials) == 0:
            obj.data.materials.append(mat)
        obj.material_slots[0].link = "OBJECT"
        obj.material_slots[0].material = mat
        objects.append((obj, gi))

    def area(name, offset, energy, size, color):
        target = Vector((0.62, 0.0, 0.95))
        data = bpy.data.lights.new(name, "AREA")
        data.energy, data.shape, data.size, data.color = energy, "DISK", size, color
        obj = bpy.data.objects.new(name, data)
        scene.collection.objects.link(obj)
        obj.location = target + Vector(offset)
        obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()

    area("Warm window", (-0.3, -0.8, 1.8), 208, 1.8, (1, 0.94, 0.86))
    area("Soft fill", (1.3, 0.3, 1.1), 102.4, 1.4, (0.86, 0.93, 1))
    area("Rim softbox", (-0.7, 1.1, 1.5), 160, 1.6, (1, 1, 1))
    cam_data = bpy.data.cameras.new("Studio camera")
    cam = bpy.data.objects.new("Studio camera", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam_data.lens, cam_data.clip_start, cam_data.clip_end = 31, 0.01, 30
    cam.location = (-0.78, -1.62, 1.92)
    cam.rotation_euler = (Vector((0.62, 0.0, 0.93)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    n = len(payload["frames"])
    indices = [int(x) for x in a.only.split(",") if x] or list(range(0, n, a.frame_step))
    if not a.only and indices[-1] != n - 1:
        indices.append(n - 1)
    meas = []
    for index in indices:
        for obj, j in objects:
            mtx = Matrix(Rm[index, j].tolist()).to_4x4()
            mtx.translation = Vector(P[index, j].tolist())
            obj.matrix_world = mtx
        t0 = time.monotonic()
        scene.render.filepath = str(frame_dir / f"{index:06d}.png")
        bpy.ops.render.render(write_still=True)
        meas.append(round(time.monotonic() - t0, 2))
        print(f"FRAME {index} {meas[-1]}", flush=True)
    (frame_dir / "render.json").write_text(json.dumps({
        "engine": f"Blender {bpy.app.version_string} Cycles {'CPU' if a.cpu else 'OptiX'}", "samples": a.samples,
        "frame_step": a.frame_step, "width": 1280, "height": 720, "indices": indices, "seconds": meas,
        "appearance_only": True, "native_pose_interpolation": False}, indent=1) + "\n")


if __name__ == "__main__":
    main()
