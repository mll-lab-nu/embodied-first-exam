"""Blender (4.5.3) studio render of exported native coffee_stir poses in the approved T11 kitchen look.

Materials, set dressing, lights and camera lens follow the approved T11 film renderer
(scene_expansion/repairs/coffee_tripod/meta_delivery_polish_r1_gravity_trajectory_r1/render.py); hand meshes and
materials follow families/assemble_hamburger/studio_renderer.py. Every mug, spoon and hand pose is a recorded native
MuJoCo pose (tools/presentation.py export); nothing is interpolated or synthesized. The coffee is a static visual
volume inside the mug (not simulated).
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


def read_obj(path):
    vertices, faces = [], []
    for line in Path(path).read_text().splitlines():
        if line.startswith("v "):
            vertices.append(tuple(float(x) for x in line.split()[1:4]))
        elif line.startswith("f "):
            faces.append(tuple(int(x.split("/")[0]) - 1 for x in line.split()[1:]))
    return vertices, faces


def smooth(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def main():
    import bmesh
    import bpy
    import numpy as np
    from mathutils import Matrix, Vector

    parser = argparse.ArgumentParser()
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=24)
    parser.add_argument("--frame-step", type=int, default=1)
    parser.add_argument("--still", type=int, nargs="*")
    parser.add_argument("--device", choices=["GPU", "CPU"], default="GPU")
    parser.add_argument("--percent", type=int, default=100)
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
    s = bpy.context.scene
    s.render.engine = "CYCLES"
    s.render.use_persistent_data = True
    s.cycles.samples = args.samples
    s.cycles.use_denoising = True
    s.cycles.denoiser = "OPENIMAGEDENOISE"
    s.cycles.denoising_use_gpu = True
    s.cycles.use_adaptive_sampling = True
    s.cycles.adaptive_threshold = 0.025
    s.cycles.max_bounces = 8
    s.cycles.device = args.device
    if args.device == "GPU":
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "OPTIX"
        prefs.get_devices()
        for device in prefs.devices:
            device.use = device.type == "OPTIX"
        if not any(d.use for d in prefs.devices):
            raise RuntimeError("OptiX device unavailable")
    else:
        s.cycles.denoising_use_gpu = False
    s.render.resolution_x, s.render.resolution_y = 1280, 720
    s.render.resolution_percentage = args.percent
    s.render.image_settings.file_format = "PNG"
    s.view_settings.view_transform = "AgX"
    s.view_settings.look = "AgX - Medium High Contrast"
    s.view_settings.exposure = -1.0
    s.world.use_nodes = True
    s.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.70, 0.75, 0.80, 1)
    s.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.12

    def linear(c):
        return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c)

    def material(name, color, roughness=0.4, metal=0, coat=0):
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        bs = m.node_tree.nodes["Principled BSDF"]
        bs.inputs["Base Color"].default_value = (*linear(color), 1)
        bs.inputs["Roughness"].default_value = roughness
        bs.inputs["Metallic"].default_value = metal
        bs.inputs["Coat Weight"].default_value = coat
        return m

    def texture(m, scale, amount, distance, colors=None):
        n, l = m.node_tree.nodes, m.node_tree.links
        coord = n.new("ShaderNodeTexCoord")
        noise = n.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = scale
        noise.inputs["Detail"].default_value = 3
        l.new(coord.outputs["Object"], noise.inputs["Vector"])
        bump = n.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = amount
        bump.inputs["Distance"].default_value = distance
        l.new(noise.outputs["Fac"], bump.inputs["Height"])
        l.new(bump.outputs["Normal"], n["Principled BSDF"].inputs["Normal"])
        if colors:
            ramp = n.new("ShaderNodeValToRGB")
            for stop, col in zip(ramp.color_ramp.elements, colors):
                stop.color = (*linear(col), 1)
            l.new(noise.outputs["Fac"], ramp.inputs[0])
            l.new(ramp.outputs["Color"], n["Principled BSDF"].inputs["Base Color"])

    # T11 film materials.
    ceramic = material("Warm ivory glazed ceramic", (0.76, 0.72, 0.63), 0.22, coat=0.30)
    texture(ceramic, 1600, 0.09, 0.000012)
    steel = material("Brushed stainless steel", (0.65, 0.68, 0.70), 0.24, metal=1)
    if "Anisotropic" in steel.node_tree.nodes["Principled BSDF"].inputs:
        steel.node_tree.nodes["Principled BSDF"].inputs["Anisotropic"].default_value = 0.30
    stone = material("Warm limestone countertop", (0.73, 0.70, 0.65), 0.62)
    texture(stone, 28, 0.22, 0.00008, ((0.66, 0.64, 0.60), (0.80, 0.78, 0.73)))
    sage = material("Muted green kitchen cabinetry", (0.25, 0.34, 0.29), 0.46)
    tile = material("Warm white backsplash", (0.81, 0.80, 0.75), 0.28, coat=0.12)
    grout = material("Fine pale grout", (0.59, 0.59, 0.55), 0.8)
    oak = material("Oak shelf", (0.53, 0.39, 0.25), 0.53)
    texture(oak, 45, 0.12, 0.00008)
    coffee = material("Coffee with milk (visual only)", (0.36, 0.20, 0.09), 0.19, coat=0.08)
    bs = coffee.node_tree.nodes["Principled BSDF"]
    bs.inputs["IOR"].default_value = 1.333
    bs.inputs["Specular IOR Level"].default_value = 0.5
    texture(coffee, 280, 0.035, 0.000009)
    # Hand materials (hamburger studio renderer).
    shell = material("Pearl white polymer housing", (0.89, 0.91, 0.89), 0.27, 0.10)
    rubber = material("Forest silicone fingertips", (0.10, 0.24, 0.18), 0.68)

    def mesh_object(name, vertices, faces, mat):
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(list(vertices), [], list(faces))
        mesh.update()
        for face in mesh.polygons:
            face.use_smooth = True
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.collection.objects.link(obj)
        obj.data.materials.append(mat)
        return obj

    cup = mesh_object("Mug (approved T11 refined mesh)", *read_obj(args.export / "cup.obj"), ceramic)
    spoon = mesh_object("Teaspoon (approved T11 refined mesh)", *read_obj(args.export / "spoon.obj"), steel)
    # Coffee: a static visual volume in the mug frame (cavity radius 50 mm, floor at 8 mm, surface at 64 mm).
    bpy.ops.mesh.primitive_cylinder_add(vertices=192, radius=0.0497, depth=0.064 - 0.009, location=(0, 0, 0))
    liquid = bpy.context.object
    liquid.name = "Coffee with milk, visual only (not simulated)"
    liquid.data.transform(Matrix.Translation((0, 0, (0.064 + 0.009) / 2)))
    liquid.data.materials.append(coffee)
    bm = bmesh.new()
    bm.from_mesh(liquid.data)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.normal.z < -0.5], context="FACES")
    bm.to_mesh(liquid.data)
    bm.free()
    liquid.parent = cup

    def box(name, pos, size, mat, bevel=0):
        bpy.ops.mesh.primitive_cube_add(size=1, location=pos)
        o = bpy.context.object
        o.name = name
        o.dimensions = size
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        o.data.materials.append(mat)
        if bevel:
            b = o.modifiers.new("Soft edge", "BEVEL")
            b.width = bevel
            b.segments = 3
            o.modifiers.new("Weighted normals", "WEIGHTED_NORMAL")
        return o

    # T11 set dressing; the task worktop top stays at z = 0.750 m.
    # One continuous stone counter (top at the task worktop height); a single slab avoids coplanar seams.
    box("Worktop and kitchen counter, stone finish", (1.075, 0.1525, 0.732), (1.65, 1.415, 0.036), stone, 0.002)
    box("Kitchen cabinetry background", (0.85, 0.64, 0.36), (1.7, 0.43, 0.71), sage, 0.003)
    box("Backsplash wall", (0.75, 0.87, 1.0), (4, 0.018, 2), grout)
    for iz in range(4):
        for ix in range(-4, 11):
            box("Backsplash tile", (-0.35 + ix * 0.235 + (iz % 2) * 0.117, 0.854, 0.83 + iz * 0.11),
                (0.232, 0.012, 0.107), tile, 0.001)
    box("Oak shelf in background", (0.81, 0.76, 1.20), (1.50, 0.20, 0.028), oak, 0.002)

    cache, hand_objects, arm_materials = {}, [], {}
    for record in payload["hand_geoms"]:
        mid = str(record["mesh"])
        if mid not in cache:
            source = payload["meshes"][mid]
            prefix = source["prefix"]
            mesh = bpy.data.meshes.new(source["name"])
            mesh.from_pydata(geometry[prefix + "vertices"].tolist(), [], geometry[prefix + "faces"].tolist())
            mesh.update()
            for polygon in mesh.polygons:
                polygon.use_smooth = True
            cache[mid] = mesh
        obj = bpy.data.objects.new(record["name"], cache[mid])
        bpy.context.collection.objects.link(obj)
        obj.data.materials.clear()
        if record.get("robot_link"):
            # Marvin arm/stand meshes: the factory rgba with the accepted arm-film finish (ARM_RIG.md section 9).
            key = tuple(record["rgba"][:3])
            if key not in arm_materials:
                arm_materials[key] = material("Marvin %.2f %.2f %.2f" % key, key, 0.29, 0.15)
            obj.data.materials.append(arm_materials[key])
        else:
            obj.data.materials.append(rubber if record["material"] == "green" else shell)
        hand_objects.append(obj)

    def light(name, pos, target, energy, size, color, shape="DISK", size_y=None):
        dat = bpy.data.lights.new(name, "AREA")
        dat.energy, dat.shape, dat.size, dat.color = energy, shape, size, color
        if size_y is not None:
            dat.size_y = size_y
        o = bpy.data.objects.new(name, dat)
        bpy.context.collection.objects.link(o)
        o.location = pos
        o.rotation_euler = (Vector(target) - o.location).to_track_quat("-Z", "Y").to_euler()

    light("Large warm window key", (0.08, -0.45, 1.55), (0.48, 0.015, 0.84), 32, 0.85, (1, 0.91, 0.80))
    light("Cool soft fill", (0.97, -0.22, 1.14), (0.48, 0.015, 0.84), 8, 0.48, (0.85, 0.92, 1))
    light("Long window reflection", (0.43, 0.40, 1.35), (0.48, 0.015, 0.83), 18, 0.55, (1, 0.96, 0.88), "RECTANGLE",
          0.14)
    light("Soft top fill for the hand", (0.30, -0.20, 1.75), (0.45, 0.0, 1.0), 10, 0.8, (1, 0.97, 0.93))
    cam_data = bpy.data.cameras.new("T11 camera")
    cam = bpy.data.objects.new("T11 camera", cam_data)
    bpy.context.collection.objects.link(cam)
    s.camera = cam
    cam_data.clip_start, cam_data.clip_end = 0.01, 20
    cam_data.dof.use_dof = True
    cam_data.dof.aperture_fstop = 9

    frames = payload["frames"]
    n = len(frames)
    hand_pos, hand_rot = poses["hand_positions"], poses["hand_rotations"]
    body_pos, body_rot = poses["body_positions"], poses["body_rotations"]
    # Camera: the T11 film's wide and near views (wide while reaching and releasing, near while stirring).
    wide_pos, wide_target, wide_lens = Vector((1.03, -0.68, 1.30)), Vector((0.47, 0.0, 0.95)), 36
    near_pos, near_target, near_lens = Vector((0.86, -0.50, 1.18)), Vector((0.48, 0.01, 0.90)), 44
    end_pos, end_target, end_lens = Vector((1.18, -0.30, 1.10)), Vector((0.54, -0.16, 0.80)), 34
    steps = [f["step"] for f in frames]
    total = max(steps[-1], 1)

    def camera_at(step):
        t = step / total
        # Near view while the bowl is in the coffee (stirring), wide view for the start, the carry and the laying down.
        w = smooth((t - 0.12) / 0.08) * (1 - smooth((t - 0.55) / 0.08))
        pos = wide_pos.lerp(near_pos, w)
        target = wide_target.lerp(near_target, w)
        lens = wide_lens + (near_lens - wide_lens) * w
        # End: a view along the worktop from the +x side that shows the spoon laid down beside the mug.
        e = smooth((t - 0.62) / 0.10)
        pos, target = pos.lerp(end_pos, e), target.lerp(end_target, e)
        lens = lens + (end_lens - lens) * e
        cam.location = pos
        cam.rotation_euler = (target - pos).to_track_quat("-Z", "Y").to_euler()
        cam_data.lens = lens
        cam_data.dof.focus_distance = (pos - target).length

    if args.still:
        indices = [i if i >= 0 else n + i for i in args.still]
    else:
        indices = list(range(0, n, args.frame_step))
        if indices[-1] != n - 1:
            indices.append(n - 1)
    settings = {
        "renderer_source_sha256": sha(__file__),
        "export_sha256": sha(args.export / "scene.json"),
        "samples": args.samples,
        "width": 1280 * args.percent // 100,
        "height": 720 * args.percent // 100,
        "engine": "Cycles OptiX" if args.device == "GPU" else "Cycles CPU",
        "appearance_only": True,
        "native_pose_interpolation": False,
        "video_fps": 25,
        "frame_step": args.frame_step,
        "native_controls_per_rendered_frame": payload["stride"] * args.frame_step,
        "coffee": "static visual volume at the T11 milk-added level (not simulated)",
    }
    measurements = []
    for index in indices:
        for k, obj in enumerate(hand_objects):
            matrix = Matrix(hand_rot[index, k].tolist()).to_4x4()
            matrix.translation = Vector(hand_pos[index, k].tolist())
            obj.matrix_world = matrix
        for obj, j in ((cup, 0), (spoon, 1)):
            matrix = Matrix(body_rot[index, j].tolist()).to_4x4()
            matrix.translation = Vector(body_pos[index, j].tolist())
            obj.matrix_world = matrix
        camera_at(frames[index]["step"])
        started = time.monotonic()
        s.render.filepath = str(frame_dir / f"{index:06d}.png")
        bpy.ops.render.render(write_still=True)
        measurements.append({"frame": index, "native_step": frames[index]["step"],
                             "seconds": round(time.monotonic() - started, 3)})
        print("FRAME " + json.dumps(measurements[-1]), flush=True)
    settings.update(indices=indices, measurements=measurements, blender_version=bpy.app.version_string)
    if not args.still:
        (frame_dir / "render.json").write_text(json.dumps(settings, indent=2) + "\n")


if __name__ == "__main__":
    main()
