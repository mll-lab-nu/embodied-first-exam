"""Blender (Cycles) studio look for the exact native poses of the batter-whisk episode.

Materials, lights and the camera language follow the approved T49 scene film (scene_expansion/tasks/batter_mix/
trajectory_r1: brushed stainless bowl and whisk, warm stone counter, warm window + cool edge softbox + steel
reflection strip, AgX, close stirring view then a wide set-down view). Only appearance and the camera differ from the
native MuJoCo state; no object or hand motion is synthesized or interpolated.
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


def smooth(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * x * (10 + x * (-15 + 6 * x))


def main():
    import bpy
    import numpy as np
    from mathutils import Matrix, Vector

    parser = argparse.ArgumentParser()
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=32)
    parser.add_argument("--frames", default="")
    parser.add_argument("--device", choices=["optix", "cpu"], default="optix")
    parser.add_argument("--percent", type=int, default=100, help="resolution percentage (previews)")
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
    scene.cycles.glossy_bounces = 5
    if args.device == "optix":
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "OPTIX"
        prefs.get_devices()
        for device in prefs.devices:
            device.use = device.type == "OPTIX"
        if not any(device.use for device in prefs.devices):
            raise RuntimeError("--device optix requires an OptiX device")
        scene.cycles.device = "GPU"
    else:
        scene.cycles.device = "CPU"
        scene.cycles.denoising_use_gpu = False
    scene.render.resolution_x, scene.render.resolution_y = 1280, 720
    scene.render.resolution_percentage = args.percent
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.35
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.72, 0.75, 0.77, 1)
    bg.inputs["Strength"].default_value = 0.45

    def linear(rgb):
        return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb)

    def material(name, color, roughness=0.4, metallic=0.0, coat=0.0, sss=0.0):
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes["Principled BSDF"]
        bsdf.inputs["Base Color"].default_value = (*linear(color), 1)
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
        bsdf.inputs["Coat Weight"].default_value = coat
        bsdf.inputs["Subsurface Weight"].default_value = sss
        bsdf.inputs["Subsurface Scale"].default_value = 0.002
        return mat

    def noise(mat, scale, detail=3):
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        coord = nodes.new("ShaderNodeTexCoord")
        tex = nodes.new("ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = scale
        tex.inputs["Detail"].default_value = detail
        tex.inputs["Roughness"].default_value = 0.65
        links.new(coord.outputs["Object"], tex.inputs["Vector"])
        return tex

    def palette(mat, tex, colors):
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements.remove(ramp.color_ramp.elements[1])
        for i, (position, color) in enumerate(colors):
            element = ramp.color_ramp.elements[0] if i == 0 else ramp.color_ramp.elements.new(position)
            element.position = position
            element.color = (*linear(color), 1)
        links.new(tex.outputs["Fac"], ramp.inputs[0])
        links.new(ramp.outputs["Color"], nodes["Principled BSDF"].inputs["Base Color"])

    def bump(mat, tex, distance, strength):
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        node = nodes.new("ShaderNodeBump")
        node.inputs["Distance"].default_value = distance
        node.inputs["Strength"].default_value = strength
        links.new(tex.outputs["Fac"], node.inputs["Height"])
        links.new(node.outputs["Normal"], nodes["Principled BSDF"].inputs["Normal"])

    # T49 film materials: brushed stainless (rgba .66 .68 .70, metallic .96, roughness .22, fine bump).
    steel = material("Brushed stainless bowl and whisk", (0.66, 0.68, 0.70), 0.22, 0.96)
    bump(steel, noise(steel, 2400, 2), 0.000008, 0.035)
    wire = material("Polished stainless whisk wire", (0.74, 0.76, 0.78), 0.16, 1.0)
    batter = material("Smooth pancake batter", (0.86, 0.68, 0.42), 0.29, coat=0.12, sss=0.15)
    palette(batter, noise(batter, 60, 3), [(0.25, (0.80, 0.60, 0.34)), (0.6, (0.86, 0.68, 0.42)),
                                           (0.9, (0.90, 0.75, 0.50))])
    bump(batter, noise(batter, 140, 2), 0.0004, 0.12)
    stone = material("Warm stone kitchen counter", (0.80, 0.78, 0.72), 0.6)
    palette(stone, noise(stone, 6, 5), [(0.05, (0.70, 0.68, 0.62)), (0.5, (0.81, 0.79, 0.73)),
                                        (0.9, (0.88, 0.86, 0.80))])
    bump(stone, noise(stone, 250, 2), 0.00007, 0.11)
    cabinet = material("Dark cabinet base", (0.14, 0.21, 0.18), 0.5)
    wall = material("Muted studio wall", (0.62, 0.63, 0.60), 0.85)
    floor = material("Studio floor", (0.43, 0.46, 0.44), 0.8)
    shell = material("Pearl white polymer housing", (0.89, 0.91, 0.89), 0.27, 0.10)
    rubber = material("Forest silicone fingertips", (0.10, 0.24, 0.18), 0.68)

    cache, objects, robot_materials = {}, [], {}
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
            half = size if kind == 6 else [size[0], size[1], 0.001]
            obj.data.transform(Matrix.Diagonal((*half, 1)))
        elif kind == 5:
            bpy.ops.mesh.primitive_cylinder_add(vertices=96, radius=size[0], depth=2 * size[1])
            obj = bpy.context.object
            for p in obj.data.polygons:
                p.use_smooth = len(p.vertices) == 4
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
            for p in mesh.polygons:
                p.use_smooth = True
        else:
            raise ValueError(f"Unsupported geometry {kind}")
        obj.name = name
        if record["owner"] == "hand":
            chosen = rubber if record["material"] == "green" else shell
        elif record["owner"] == "robot":  # Marvin stand and arm links: their own MuJoCo colours
            key = tuple(round(c, 3) for c in record["rgba"][:3])
            if key not in robot_materials:
                robot_materials[key] = material("Marvin " + str(key), key, 0.35, 0.15)
            chosen = robot_materials[key]
        elif name == "floor":
            chosen = floor
        elif name == "counter_top":
            chosen = stone
            mod = obj.modifiers.new("Counter edge rounding", "BEVEL")
            mod.width, mod.segments = 0.004, 4
        elif name == "cabinet":
            chosen = cabinet
        elif name == "backsplash":
            chosen = wall
        elif name == "batter_surface":
            chosen = batter
        elif name == "whisk_wires_visible":
            chosen = wire
        else:
            chosen = steel
        obj.data.materials.clear()
        obj.data.materials.append(chosen)
        objects.append(obj)

    def area(name, offset, energy, size, color, target):
        data = bpy.data.lights.new(name, "AREA")
        data.energy, data.shape, data.size, data.color = energy, "DISK", size, color
        obj = bpy.data.objects.new(name, data)
        scene.collection.objects.link(obj)
        obj.location = Vector(target) + Vector(offset)
        obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()

    # T49 lights (offsets from the light target, film frame shifted to this scene: bowl at (0.58, 0, 0.68)).
    light_target = (0.66, 0.06, 0.80)
    area("Large warm window", (-0.45, -0.4, 0.8), 60, 0.8, (1, 0.92, 0.8), light_target)
    area("Cool edge softbox", (0.45, 0.45, 0.65), 48, 0.65, (0.86, 0.93, 1), light_target)
    area("Steel reflection strip", (-0.3, 0.3, 0.6), 30, 0.35, (1, 1, 1), light_target)
    data = bpy.data.cameras.new("Studio camera")
    camera = bpy.data.objects.new("Studio camera", data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    data.clip_start, data.clip_end = 0.01, 30

    frames = payload["frames"]
    final_com = Vector(frames[-1]["whisk_com"])
    success_step = payload["success_step"]
    # Camera language of the T49 film: wide on the two-arm robot, closer for the pickup off the rim, close on the bowl
    # while whisking, wide for the drain and set-down, then a slow push-in on the resting whisk (final state held).
    views = [  # (native step, target, offset from target, lens mm); Marvin stand at the origin facing +x, cameras
        # in front of the robot on its right (x < the backsplash at 1.01 m)
        (0, Vector((0.42, -0.05, 0.88)), Vector((0.55, -0.95, 0.40)), 28),
        (230, Vector((0.50, -0.12, 0.76)), Vector((0.42, -0.62, 0.30)), 32),
        (560, Vector((0.50, -0.12, 0.76)), Vector((0.42, -0.62, 0.30)), 32),
        (860, Vector((0.58, 0.00, 0.82)), Vector((0.32, -0.60, 0.26)), 34),
        (1360, Vector((0.58, 0.00, 0.82)), Vector((0.32, -0.60, 0.26)), 34),
        (1480, Vector((0.52, -0.15, 0.78)), Vector((0.40, -0.70, 0.32)), 31),
    ]
    tail_view = (final_com + Vector((0.0, 0.04, 0.03)), Vector((0.35, -0.55, 0.26)), 36)
    n_tail = sum(1 for f in frames if f["tail"])

    def blend(a, b, u):
        return a[0].lerp(b[0], u), a[1].lerp(b[1], u), a[2] + (b[2] - a[2]) * u

    def view(index):
        record = frames[index]
        step = record["step"]
        current = views[0][1:]
        for (s0, *v0), (s1, *v1) in zip(views, views[1:]):
            if step >= s1:
                current = tuple(v1)
            elif step > s0:
                current = blend(tuple(v0), tuple(v1), smooth((step - s0) / (s1 - s0)))
                break
        if record["tail"]:
            k = index - (len(frames) - n_tail)
            current = blend(current, tail_view, smooth(k / max(1, n_tail - 1) * 1.15))
        target, offset, lens = current
        return target, target + offset, lens

    indices = [int(v) for v in args.frames.split(",")] if args.frames else list(range(len(frames)))
    measurements = []
    for index in indices:
        target, position, lens = view(index)
        camera.location = position
        camera.rotation_euler = (target - position).to_track_quat("-Z", "Y").to_euler()
        data.lens = lens
        for j, obj in enumerate(objects):
            matrix = Matrix(poses["rotations"][index, j]).to_4x4()
            matrix.translation = Vector(poses["positions"][index, j])
            obj.matrix_world = matrix
        started = time.monotonic()
        scene.render.filepath = str(frame_dir / f"{index:06d}.png")
        bpy.ops.render.render(write_still=True)
        measurements.append({"frame": index, "native_step": frames[index]["step"],
                             "seconds": round(time.monotonic() - started, 2)})
        print("FRAME " + json.dumps(measurements[-1]), flush=True)
    settings = {
        "renderer_source_sha256": sha(__file__),
        "export_sha256": sha(args.export / "scene.json"),
        "samples": args.samples,
        "width": 1280,
        "height": 720,
        "engine": "Cycles " + ("OptiX" if args.device == "optix" else "CPU"),
        "appearance_only": True,
        "native_pose_interpolation": False,
        "video_fps": payload["fps"],
        "native_controls_per_rendered_frame": payload["stride"],
        "success_step": success_step,
        "tail_frames_hold_final_native_state": n_tail,
        "indices": indices,
        "measurements": measurements,
        "blender_version": bpy.app.version_string,
    }
    if not args.frames:
        (frame_dir / "render.json").write_text(json.dumps(settings, indent=2) + "\n")


if __name__ == "__main__":
    main()
