"""Blender Cycles studio renderer for exported native grinder poses (authoring film only, not shipped).

    blender -b -P studio_renderer.py -- --export OUT --output film.mp4 [--samples 48] [--frame-step 1] [--still N]

Materials, lighting and camera follow the approved T15 scene film (studio_render.py of the scene source): clear
receptacle, black polymer hopper, brushed steel crank, warm grey counter, AgX view. The hand shells and fingertip
pads follow the assemble_hamburger studio renderer. Poses are the exported MuJoCo geom frames, never interpolated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import time


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def linear(rgb):
    return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb[:3])


def main():
    import bpy
    import numpy as np
    from mathutils import Matrix, Vector

    parser = argparse.ArgumentParser()
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=48)
    parser.add_argument("--frame-step", type=int, default=1)
    parser.add_argument("--still", type=int, nargs="*")
    parser.add_argument("--camera", type=float, nargs=3, default=(0.96, -0.66, 1.25))
    parser.add_argument("--target", type=float, nargs=3, default=(0.45, 0.0, 0.88))
    parser.add_argument("--lens", type=float, default=40)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    payload = json.loads((args.export / "scene.json").read_text())
    for name, expected in payload["files"].items():
        if sha(args.export / name) != expected:
            raise ValueError("Export integrity mismatch: " + name)
    geometry = np.load(args.export / "geometry.npz", allow_pickle=False)
    poses = np.load(args.export / "poses.npz", allow_pickle=False)
    frame_dir = args.output.with_suffix("").with_name(args.output.stem + "-frames")
    frame_dir.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = args.samples
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.02
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = "OPENIMAGEDENOISE"
    scene.cycles.denoising_use_gpu = True
    scene.cycles.use_persistent_data = True
    scene.cycles.max_bounces = 8
    scene.cycles.transmission_bounces = 6
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.get_devices()
    for device in prefs.devices:
        device.use = device.type == "OPTIX"
    if not any(device.use for device in prefs.devices):
        raise RuntimeError("This authoring renderer requires an OptiX device")
    scene.cycles.device = "GPU"
    scene.render.resolution_x, scene.render.resolution_y = args.width, args.height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = 0.1  # T15 approved film
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes["Background"]
    background.inputs["Color"].default_value = (0.72, 0.75, 0.77, 1)
    background.inputs["Strength"].default_value = 0.45

    def material(name, rgba, metallic=0.0, roughness=0.38, transmission=0.0, ior=1.45, coat=0.0, bump=None):
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        bsdf = nodes["Principled BSDF"]
        bsdf.inputs["Base Color"].default_value = (*linear(rgba), 1)
        bsdf.inputs["Metallic"].default_value = metallic
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Transmission Weight"].default_value = transmission
        bsdf.inputs["IOR"].default_value = ior
        bsdf.inputs["Coat Weight"].default_value = coat
        if bump:
            coordinates = nodes.new("ShaderNodeTexCoord")
            noise = nodes.new("ShaderNodeTexNoise")
            noise.inputs["Scale"].default_value = bump["scale"]
            noise.inputs["Detail"].default_value = 2
            links.new(coordinates.outputs["Object"], noise.inputs["Vector"])
            node = nodes.new("ShaderNodeBump")
            node.inputs["Strength"].default_value = bump["strength"]
            node.inputs["Distance"].default_value = bump["distance"]
            links.new(noise.outputs["Fac"], node.inputs["Height"])
            links.new(node.outputs["Normal"], bsdf.inputs["Normal"])
        return mat

    # Grinder finishes of the approved T15 film (scene-v2 visual_material overrides).
    clear = material("Clear receptacle", (0.55, 0.59, 0.60), 0, 0.13, transmission=0.65, ior=1.49, coat=0.15)
    hopper = material("Black polymer hopper", (0.095, 0.10, 0.11), 0, 0.30, coat=0.12,
                      bump={"scale": 1800, "strength": 0.04, "distance": 1.5e-05})
    resin = material("Black resin", (0.09, 0.105, 0.11), 0, 0.38)
    steel = material("Brushed steel", (0.68, 0.70, 0.71), 0.92, 0.22)
    lid = material("Clear lid", (0.35, 0.38, 0.39), 0, 0.2, transmission=0.5, ior=1.49, coat=0.1)
    ceramic = material("Ceramic burr", (0.86, 0.84, 0.77), 0, 0.8)
    counter = material("Counter top", (0.77, 0.75, 0.70), 0, 0.38)
    surface = material("Studio warm gray surface", (0.72, 0.73, 0.71), 0, 0.75)
    legs = material("Dark counter legs", (0.28, 0.26, 0.22), 0, 0.38)
    # Hand finishes of the assemble_hamburger film.
    shell = material("Pearl white polymer housing", (0.89, 0.91, 0.89), 0.1, 0.27, coat=0.1)
    rubber = material("Forest silicone fingertips", (0.10, 0.24, 0.18), 0, 0.68)
    joint_steel = material("Brushed stainless mechanics", (0.35, 0.39, 0.40), 0.8, 0.30)
    dark = material("Dark anodised hand parts", (0.06, 0.065, 0.07), 0.3, 0.35)
    by_name = {"mill_cup_visual": clear, "mill_hopper_visual": hopper, "mill_base": resin, "mill_lid": lid,
               "crank_shaft": steel, "crank_center_cap": resin, "crank_bent_root": steel, "crank_handle": steel,
               "inner_burr": ceramic, "knob_resin_neck": resin, "knob_resin_bulb": resin, "mill_steel_band": steel,
               "mill_lid_ring": steel, "counter": counter, "floor": surface}
    objects, audit, cache = [], [], {}
    for record in payload["geoms"]:
        name, kind, size = record["name"], record["kind"], record["size"]
        if kind == 7:
            mid = str(record["mesh"])
            if mid not in cache:
                source = payload["meshes"][mid]
                mesh = bpy.data.meshes.new(source["name"])
                mesh.from_pydata(geometry[source["prefix"] + "vertices"].tolist(), [],
                                 geometry[source["prefix"] + "faces"].tolist())
                mesh.update()
                for polygon in mesh.polygons:
                    polygon.use_smooth = True
                cache[mid] = mesh
            obj = bpy.data.objects.new(name, cache[mid].copy())
            scene.collection.objects.link(obj)
        elif kind in (0, 6):
            bpy.ops.mesh.primitive_cube_add(size=2)
            obj = bpy.context.object
            obj.data.transform(Matrix.Diagonal((*(size if kind == 6 else [3, 3, 0.001]), 1)))
            if kind == 6 and name == "counter":
                mod = obj.modifiers.new("Edge finish", "BEVEL")
                mod.width, mod.segments = 0.003, 3
        elif kind == 5:
            bpy.ops.mesh.primitive_cylinder_add(vertices=96, radius=size[0], depth=2 * size[1])
            obj = bpy.context.object
            for polygon in obj.data.polygons:
                polygon.use_smooth = len(polygon.vertices) == 4
        elif kind in (2, 4):
            bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=1)
            obj = bpy.context.object
            obj.data.transform(Matrix.Diagonal((*(size if kind == 4 else [size[0]] * 3), 1)))
            for polygon in obj.data.polygons:
                polygon.use_smooth = True
        elif kind == 3:
            r, half = size[:2]
            vertices, faces = [], []
            rings = [(math.pi * j / 24, half) for j in range(13)] + [(math.pi * j / 24, -half) for j in range(12, 25)]
            for angle, offset in rings:
                for k in range(32):
                    a = 2 * math.pi * k / 32
                    vertices.append((r * math.sin(angle) * math.cos(a), r * math.sin(angle) * math.sin(a),
                                     r * math.cos(angle) + offset))
            for j in range(len(rings) - 1):
                for k in range(32):
                    a, b = j * 32 + k, j * 32 + (k + 1) % 32
                    faces.append((a, b, b + 32, a + 32))
            mesh = bpy.data.meshes.new(name)
            mesh.from_pydata(vertices, [], faces)
            obj = bpy.data.objects.new(name, mesh)
            scene.collection.objects.link(obj)
            for polygon in mesh.polygons:
                polygon.use_smooth = True
        else:
            raise ValueError(f"Unsupported geometry {kind}")
        obj.name = name
        if record["owner"] in ("right", "left"):
            mat_name = record["material"]
            if mat_name == "green" or "elastomer" in name or "fingertip" in name:
                chosen = rubber
            elif "_VL" in name:
                chosen = joint_steel
            elif "_wuji_" in name and max(record["rgba"][:3]) < 0.3:
                chosen = dark
            else:
                chosen = shell
        elif name in by_name:
            chosen = by_name[name]
        elif name.startswith("leg_"):
            chosen = legs
        else:
            chosen = material("Primitive " + name, record["rgba"])
        obj.data.materials.clear()
        obj.data.materials.append(chosen)
        objects.append(obj)
        audit.append({"geom": name, "material": chosen.name})
    target = Vector(args.target)
    for name, offset, energy, size, color in [
        ("Key softbox", (-0.45, -0.30, 0.62), 30, 0.6, (1, 0.92, 0.82)),
        ("Cool fill", (0.20, 0.42, 0.36), 14, 0.5, (0.8, 0.9, 1)),
        ("Top edge light", (-0.18, 0.12, 0.62), 16, 0.35, (1, 1, 1)),
        ("Front soft fill", (0.55, -0.55, 0.30), 10, 0.6, (1, 0.97, 0.93)),
    ]:
        data = bpy.data.lights.new(name, "AREA")
        data.energy, data.shape, data.size, data.color = energy, "DISK", size, color
        light = bpy.data.objects.new(name, data)
        scene.collection.objects.link(light)
        light.location = target + Vector(offset)
        light.rotation_euler = (target - light.location).to_track_quat("-Z", "Y").to_euler()
    data = bpy.data.cameras.new("Presentation camera")
    camera = bpy.data.objects.new("Presentation camera", data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera.location = Vector(args.camera)
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    data.lens, data.clip_start, data.clip_end = args.lens, 0.001, 20
    n = len(payload["frames"])
    if args.still is not None:
        indices = [i if i >= 0 else n + i for i in args.still]
    else:
        indices = list(range(0, n, args.frame_step))
        if indices[-1] != n - 1:
            indices.append(n - 1)
    measurements = []
    for index in indices:
        for obj, position, rotation in zip(objects, poses["positions"][index], poses["rotations"][index]):
            matrix = Matrix(rotation.tolist()).to_4x4()
            matrix.translation = Vector(position.tolist())
            obj.matrix_world = matrix
        started = time.monotonic()
        scene.render.filepath = str(frame_dir / f"{index:06d}.png")
        bpy.ops.render.render(write_still=True)
        measurements.append({"frame": index, "native_step": payload["frames"][index]["step"],
                             "seconds": round(time.monotonic() - started, 2)})
        print("FRAME " + json.dumps(measurements[-1]), flush=True)
    settings = {
        "renderer_source_sha256": sha(__file__),
        "export_sha256": sha(args.export / "scene.json"),
        "engine": "Blender Cycles OptiX",
        "blender_version": bpy.app.version_string,
        "samples": args.samples,
        "width": args.width,
        "height": args.height,
        "camera": list(args.camera),
        "target": list(args.target),
        "lens": args.lens,
        "video_fps": payload["fps"] / args.frame_step,
        "native_controls_per_rendered_frame": payload["stride"] * args.frame_step,
        "appearance_only": True,
        "native_pose_interpolation": False,
        "indices": indices,
        "materials": audit,
        "measurements": measurements,
    }
    if args.still is None:
        (frame_dir / "render.json").write_text(json.dumps(settings, indent=2) + "\n")


if __name__ == "__main__":
    main()
