"""Blender studio look (after the approved T37 film) on exact native poses; appearance only, no synthesized motion.

    blender -b -P studio_renderer.py -- --export <dir> --output <film.mp4> [--engine eevee] [--frame-step 1]
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

    parser = argparse.ArgumentParser()
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=16)
    parser.add_argument("--frame-step", type=int, default=1)
    parser.add_argument("--engine", choices=["cycles", "eevee"], default="eevee")
    parser.add_argument("--only", default="", help="comma-separated frame indices (preview)")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    payload = json.loads((args.export / "scene.json").read_text())
    geometry = np.load(args.export / "geometry.npz", allow_pickle=False)
    poses = np.load(args.export / "poses.npz", allow_pickle=False)
    pos_all, rot_all = poses["positions"], poses["rotations"]
    frame_dir = args.output.with_suffix("").with_name(args.output.stem + "-frames")
    frame_dir.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene
    if args.engine == "cycles":
        scene.render.engine = "CYCLES"
        scene.cycles.samples = args.samples
        scene.cycles.use_denoising = True
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "OPTIX"
        prefs.get_devices()
        for device in prefs.devices:
            device.use = device.type == "OPTIX"
        scene.cycles.device = "GPU"
    else:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
        scene.eevee.taa_render_samples = 24
        scene.eevee.use_shadows = True
    scene.render.resolution_x, scene.render.resolution_y = 1280, 720
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -1.0
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.72, 0.75, 0.77, 1)
    bg.inputs["Strength"].default_value = 0.45

    def linear(c):
        return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)

    cache = {}

    def material(name, color, roughness=0.4, metallic=0.0, coat=0.0, noise_scale=0, noise_mix=None):
        if name in cache:
            return cache[name]
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        bsdf = nodes["Principled BSDF"]
        bsdf.inputs["Base Color"].default_value = (*linear(color), 1)
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
        bsdf.inputs["Coat Weight"].default_value = coat
        if noise_scale:
            tex = nodes.new("ShaderNodeTexNoise")
            tex.inputs["Scale"].default_value = noise_scale
            tex.inputs["Detail"].default_value = 6
            coords = nodes.new("ShaderNodeTexCoord")
            links.new(coords.outputs["Object"], tex.inputs["Vector"])
            ramp = nodes.new("ShaderNodeValToRGB")
            ramp.color_ramp.elements[0].color = (*linear(noise_mix[0]), 1)
            ramp.color_ramp.elements[1].color = (*linear(noise_mix[1]), 1)
            links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
            links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        cache[name] = mat
        return mat

    shell = material("Studio ceramic white shell", (0.9, 0.92, 0.92), 0.24)
    rubber = material("Studio forest elastomer", (0.22, 0.29, 0.25), 0.65)
    desk = material("Warm oak desk", (0.66, 0.52, 0.41), 0.5, noise_scale=7,
                    noise_mix=((0.55, 0.41, 0.31), (0.72, 0.58, 0.46)))
    floor = material("Studio warm gray floor", (0.62, 0.64, 0.63), 0.8)
    board = material("Binder polypropylene board", (0.93, 0.93, 0.90), 0.45, coat=0.2)
    film = material("Binder clear view film", (0.97, 0.97, 0.95), 0.12, coat=0.6)
    pocket = material("Binder inner pocket", (0.86, 0.90, 0.91), 0.2)
    steel = material("Nickel plated ring steel", (0.80, 0.81, 0.82), 0.22, metallic=1.0)
    paper = material("Punched paper stock", (0.97, 0.96, 0.93), 0.75)
    ink = material("Printed ink", (0.32, 0.34, 0.36), 0.6)
    wood = material("Page stand wood", (0.66, 0.50, 0.34), 0.5, noise_scale=12,
                    noise_mix=((0.55, 0.40, 0.26), (0.72, 0.56, 0.40)))
    objects = []
    for record in payload["geoms"]:
        name, kind, size = record["name"], record["kind"], record["size"]
        if record["owner"] == "hand" and "_wuji_" in name and "collision" in name:
            continue
        if kind == 7:
            src = payload["meshes"][str(record["mesh"])]
            mesh = bpy.data.meshes.new(src["name"])
            mesh.from_pydata(geometry[src["prefix"] + "vertices"].tolist(), [],
                             geometry[src["prefix"] + "faces"].tolist())
            mesh.update()
            smooth = record["owner"] == "hand"
            for poly in mesh.polygons:
                poly.use_smooth = smooth
            obj = bpy.data.objects.new(name, mesh)
            scene.collection.objects.link(obj)
        elif kind == 6:
            bpy.ops.mesh.primitive_cube_add(size=2)
            obj = bpy.context.object
            obj.data.transform(Matrix.Diagonal((*size, 1)))
        elif kind == 5:
            bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=size[0], depth=2 * size[1])
            obj = bpy.context.object
        elif kind in (2, 4):
            bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=1)
            obj = bpy.context.object
            obj.data.transform(Matrix.Diagonal((*(size if kind == 4 else [size[0]] * 3), 1)))
            for poly in obj.data.polygons:
                poly.use_smooth = True
        elif kind == 3:
            bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=size[0], depth=2 * size[1])
            obj = bpy.context.object
            for poly in obj.data.polygons:
                poly.use_smooth = True
            for end in (-1, 1):
                bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, radius=size[0],
                                                     location=(0, 0, end * size[1]))
                cap = bpy.context.object
                for poly in cap.data.polygons:
                    poly.use_smooth = True
                cap.select_set(True)
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.join()
        else:
            raise ValueError(f"Unsupported geometry kind {kind}: {name}")
        obj.name = name
        bevel = 0.0
        if record["owner"] == "hand":
            chosen = rubber if record["material"] == "green" else shell
        elif name == "floor":
            chosen = floor
        elif name == "desk":
            chosen, bevel = desk, 0.004
        elif name.startswith("desk_leg"):
            chosen = material("Dark desk legs", (0.24, 0.23, 0.21), 0.5)
        elif name.startswith("page_stand"):
            chosen, bevel = wood, 0.0015
        elif "_heading" in name or "_line_" in name:
            chosen = ink
        elif name.startswith("page_"):
            chosen = paper
        elif name.startswith("ring_") or "toggle" in name or "booster" in name or "rivet" in name or "backplate" in name:
            chosen = steel
        elif "film" in name:
            chosen = film
        elif "pocket" in name:
            chosen = pocket
        else:
            chosen, bevel = board, 0.0012
        obj.data.materials.clear()
        obj.data.materials.append(chosen)
        if bevel and kind == 6:
            mod = obj.modifiers.new("Edge rounding", "BEVEL")
            mod.width, mod.segments = bevel, 3
        if name == "desk":
            # studio extension of the desk top only in the visible range; native size kept (no scaling of objects)
            pass
        objects.append((obj, record["id"]))

    def area(name, position, target, energy, size, color):
        data = bpy.data.lights.new(name, "AREA")
        data.energy, data.shape, data.size, data.color = energy, "DISK", size, color
        light = bpy.data.objects.new(name, data)
        scene.collection.objects.link(light)
        light.location = position
        light.rotation_euler = (Vector(target) - light.location).to_track_quat("-Z", "Y").to_euler()

    centre = Vector((0.60, 0.0, 0.72))
    area("Key softbox", centre + Vector((-0.55, -0.35, 0.85)), centre, 120, 0.9, (1, 0.92, 0.82))
    area("Cool fill", centre + Vector((0.45, 0.55, 0.55)), centre, 45, 0.8, (0.8, 0.9, 1))
    area("Top edge light", centre + Vector((-0.10, 0.10, 0.95)), centre, 60, 0.6, (1, 1, 1))
    cam_data = bpy.data.cameras.new("Presentation camera")
    camera = bpy.data.objects.new("Presentation camera", cam_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    cam_data.lens = 34
    cam_data.clip_start, cam_data.clip_end = 0.01, 20
    camera.location = Vector((1.30, -0.70, 1.24))  # wave 3: also frames the desk's +x edge where pages are picked up
    target = Vector((0.73, 0.04, 0.74))
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    n = len(payload["frames"])
    if args.only:
        indices = [int(i) for i in args.only.split(",")]
    else:
        indices = list(range(0, n, args.frame_step))
        if indices[-1] != n - 1:
            indices.append(n - 1)
    id_index = {g["id"]: i for i, g in enumerate(payload["geoms"])}
    timings = []
    for index in indices:
        for obj, gid in objects:
            j = id_index[gid]
            matrix = Matrix(rot_all[index, j].tolist()).to_4x4()
            matrix.translation = Vector(pos_all[index, j].tolist())
            obj.matrix_world = matrix
        started = time.monotonic()
        scene.render.filepath = str(frame_dir / f"{index:06d}.png")
        bpy.ops.render.render(write_still=True)
        timings.append(round(time.monotonic() - started, 2))
        print("FRAME", index, timings[-1], flush=True)
    manifest = {"engine": "Eevee Next" if args.engine == "eevee" else f"Cycles OptiX {args.samples} spp",
                "indices": indices, "frame_step": args.frame_step, "video_fps": payload["fps"] / args.frame_step,
                "appearance_only": True, "native_pose_interpolation": False, "seconds_per_frame": timings,
                "blender_version": bpy.app.version_string}
    if not args.only:
        (frame_dir / "render.json").write_text(json.dumps(manifest, indent=1) + "\n")


if __name__ == "__main__":
    main()
