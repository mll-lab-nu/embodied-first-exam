"""Blender 4.5 studio renderer for the remote battery swap: exact native geom poses, T07 studio look.

Materials, lighting and camera follow the approved T07 presentation (dark micro-textured molded plastic, gold and
nickel contacts, AA wrap textures, mint tray, warm studio tabletop, three soft area lights, AgX). Hand materials
follow the DexHand films (white polymer shell, forest elastomer fingertip pads). Only appearance differs from the
native MuJoCo preview: every pose comes from the exported physics replay.
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
    parser.add_argument("--engine", choices=["eevee", "cycles"], default="eevee")
    parser.add_argument("--samples", type=int, default=32)
    parser.add_argument("--frame-step", type=int, default=1)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    payload = json.loads((args.export / "scene.json").read_text())
    for name, expected in payload["files"].items():
        if sha(args.export / name) != expected:
            raise ValueError("Export integrity mismatch: " + name)
    geometry = np.load(args.export / "geometry.npz", allow_pickle=False)
    poses = np.load(args.export / "poses.npz", allow_pickle=False)
    pose_positions, pose_rotations = poses["positions"], poses["rotations"]
    frame_dir = args.output.with_suffix("").with_name(args.output.stem + "-frames")
    frame_dir.mkdir(parents=True, exist_ok=True)

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene
    if args.engine == "cycles":
        scene.render.engine = "CYCLES"
        scene.cycles.samples = args.samples
        scene.cycles.use_adaptive_sampling = True
        scene.cycles.use_denoising = True
        scene.cycles.denoiser = "OPENIMAGEDENOISE"
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "OPTIX"
        prefs.get_devices()
        for device in prefs.devices:
            device.use = device.type == "OPTIX"
        scene.cycles.device = "GPU"
        scene.cycles.use_persistent_data = True
    else:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
        scene.eevee.taa_render_samples = args.samples
        scene.eevee.use_shadows = True
        scene.eevee.use_raytracing = True
        scene.eevee.ray_tracing_options.resolution_scale = "2"
        scene.eevee.use_gtao = True
    scene.render.resolution_x, scene.render.resolution_y = 1280, 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.2
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (*linear((0.93, 0.86, 0.80)), 1)
    bg.inputs["Strength"].default_value = 0.45

    cache = {}

    def material(name, rgba, metallic=0.0, roughness=0.4, bump=None, coat=0.0, texture=None):
        if name in cache:
            return cache[name]
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        bsdf = nodes["Principled BSDF"]
        bsdf.inputs["Base Color"].default_value = (*linear(rgba), 1)
        bsdf.inputs["Metallic"].default_value = metallic
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Coat Weight"].default_value = coat
        if bump:
            coord = nodes.new("ShaderNodeTexCoord")
            noise = nodes.new("ShaderNodeTexNoise")
            noise.inputs["Scale"].default_value = bump[0]
            noise.inputs["Detail"].default_value = 2
            links.new(coord.outputs["Object"], noise.inputs["Vector"])
            node = nodes.new("ShaderNodeBump")
            node.inputs["Strength"].default_value = bump[1]
            node.inputs["Distance"].default_value = bump[2]
            links.new(noise.outputs["Fac"], node.inputs["Height"])
            links.new(node.outputs["Normal"], bsdf.inputs["Normal"])
        if texture:
            tex = nodes.new("ShaderNodeTexImage")
            tex.image = bpy.data.images.load(str(args.export / texture), check_existing=True)
            tex.interpolation = "Linear"
            links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        cache[name] = mat
        return mat

    plastic = material("Dark micro-textured molded plastic", (0.045, 0.055, 0.065), 0, 0.88, (4200, 0.23, 3.5e-5))
    rib = material("Molded rib plastic", (0.065, 0.075, 0.085), 0, 0.7)
    trim = material("Molded thumb ribs", (0.14, 0.16, 0.18), 0, 0.65)
    arrow = material("Molded OPEN arrow", (0.28, 0.32, 0.34), 0, 0.8)
    gold = material("Gold-plated contact", (0.93, 0.71, 0.23), 0.85, 0.28)
    nickel = material("Nickel spring contact", (0.72, 0.74, 0.75), 0.85, 0.28)
    endcap = material("AA exposed end metal", (0.65, 0.68, 0.68), 0.9, 0.28)
    buttons = material("Soft-touch keys", (0.62, 0.64, 0.62), 0, 0.55)
    fastener = material("Recessed fastener", (0.18, 0.2, 0.22), 0.7, 0.65)
    tray_mat = material("Mint molded tray", (0.75, 0.82, 0.78), 0, 0.65)
    table = material("Warm studio tabletop", (0.69, 0.56, 0.43), 0, 0.65, (650, 0.12, 5e-5))
    shell = material("White polymer hand shell", (0.9, 0.92, 0.92), 0, 0.24)
    rubber = material("Forest elastomer pads", (0.22, 0.29, 0.25), 0, 0.65)
    new_wrap = material("New AA wrap", (1, 1, 1), 0.15, 0.52, texture="new_aa_wrap.png")
    old_wrap = material("Old AA wrap", (1, 1, 1), 0.15, 0.52, texture="old_aa_wrap.png")

    table_legs = material("Dark steel table legs", (0.16, 0.16, 0.17), 0.6, 0.45)
    floor_mat = material("Studio floor", (0.80, 0.76, 0.71), 0, 0.8)

    def choose(record):
        name, owner = record["name"], record["owner"]
        if owner == "arm":  # Tianji Marvin factory colours (pot_shelf_transfer film look)
            rgba = record["rgba"][:3]
            return material("Marvin " + "_".join(f"{c:.3f}" for c in rgba), rgba, 0.15, 0.29)
        if name.startswith("table_leg"):
            return table_legs
        if owner == "hand":
            return rubber if record["material"] == "green" or "fingertip" in name else shell
        if name == "table":
            return table
        if owner == "tray":
            return tray_mat
        if owner in ("old_cell", "new_cell"):
            if name.endswith("_label"):
                return new_wrap if owner == "new_cell" else old_wrap
            if name.endswith("_positive"):
                return gold
            return endcap
        if name == "positive_contact":
            return gold
        if name.startswith("negative_"):
            return plastic if "block" in name else nickel
        if name.startswith("button_"):
            return buttons
        if name.startswith("fastener_"):
            return fastener
        if name.startswith("thumb_rib") or name.startswith("cover_ridge"):
            return trim
        if name.startswith("open_arrow"):
            return arrow
        if name.startswith("cradle_rib"):
            return rib
        if name.startswith("polarity_mark"):
            return material("Polarity print", (0.67, 0.7, 0.7), 0, 0.8)
        return plastic

    mesh_cache, objects = {}, []
    for record in payload["geoms"]:
        name, kind, size = record["name"], record["kind"], record["size"]
        if kind == 7:
            key = str(record["mesh"])
            if key not in mesh_cache:
                info = payload["meshes"][key]
                prefix = info["prefix"]
                mesh = bpy.data.meshes.new(info["name"])
                mesh.from_pydata(geometry[prefix + "vertices"].tolist(), [], geometry[prefix + "faces"].tolist())
                mesh.update()
                if info.get("has_uv"):
                    uv_layer = mesh.uv_layers.new(name="UVMap")
                    corner = geometry[prefix + "corner_uv"]
                    for poly in mesh.polygons:
                        for k, loop in enumerate(poly.loop_indices):
                            u, v = corner[poly.index, k]
                            uv_layer.data[loop].uv = (float(u), 1.0 - float(v))
                smooth = record["owner"] in ("hand", "old_cell", "new_cell")
                for poly in mesh.polygons:
                    poly.use_smooth = smooth
                if not smooth:
                    # flat planar faces, smooth rounded side strips (auto smooth by angle)
                    try:
                        mesh.shade_smooth_by_angle(angle=math.radians(35))
                    except AttributeError:
                        pass
                mesh_cache[key] = mesh
            obj = bpy.data.objects.new(name, mesh_cache[key].copy())  # own data: per-object material
            scene.collection.objects.link(obj)
        elif kind == 6:
            if False:
                pass
            else:
                bpy.ops.mesh.primitive_cube_add(size=2)
                obj = bpy.context.object
                obj.data.transform(Matrix.Diagonal((*size, 1)))
                if min(size) > 0.0008:
                    mod = obj.modifiers.new("edge rounding", "BEVEL")
                    mod.width, mod.segments = min(0.0008, min(size) * 0.4), 3
        elif kind == 5:
            bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=size[0], depth=2 * size[1])
            obj = bpy.context.object
            for p in obj.data.polygons:
                p.use_smooth = len(p.vertices) == 4
        elif kind in (2, 4):
            bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=1)
            obj = bpy.context.object
            obj.data.transform(Matrix.Diagonal((*(size if kind == 4 else [size[0]] * 3), 1)))
            for p in obj.data.polygons:
                p.use_smooth = True
        elif kind == 3:
            bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=size[0], depth=2 * size[1])
            obj = bpy.context.object
        else:
            continue
        obj.name = name
        obj.data.materials.clear()
        obj.data.materials.append(choose(record))
        objects.append((obj, record["id"]))

    def area(name, offset, energy, size, color, target):
        data = bpy.data.lights.new(name, "AREA")
        data.energy, data.shape, data.size, data.color = energy, "DISK", size, color
        obj = bpy.data.objects.new(name, data)
        scene.collection.objects.link(obj)
        obj.location = Vector(target) + Vector(offset)
        obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()

    # studio floor under the robot stand and the table
    bpy.ops.mesh.primitive_plane_add(size=12, location=(0, 0, payload.get("floor_z", 0.0)))
    floor = bpy.context.object
    floor.data.materials.append(floor_mat)
    # T07 presentation lights (offsets from the light target), scaled up for the arm framing
    light_target = (0.02, 0.0, 0.33)
    area("Large soft key", (-0.25, -0.45, 0.65), 45, 1.0, (1, 0.94, 0.85), light_target)
    area("Soft fill", (0.40, 0.25, 0.45), 22, 0.9, (0.86, 0.94, 1), light_target)
    area("Top sheen", (-0.1, 0.2, 0.6), 22, 0.7, (1, 1, 1), light_target)
    area("Robot rim", (-0.9, 0.5, 1.0), 60, 1.2, (1, 0.97, 0.93), light_target)
    cam_data = bpy.data.cameras.new("Studio camera")
    camera = bpy.data.objects.new("Studio camera", cam_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera.location = (0.50, -0.58, 0.88)
    target = Vector((-0.05, 0.0, 0.40))
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    cam_data.lens, cam_data.clip_start, cam_data.clip_end = 35, 0.005, 20
    cam_data.dof.use_dof = True
    cam_data.dof.aperture_fstop = 16
    cam_data.dof.focus_distance = (target - camera.location).length

    indices = list(range(0, len(payload["frames"]), args.frame_step))
    if indices[-1] != len(payload["frames"]) - 1:
        indices.append(len(payload["frames"]) - 1)
    if args.limit:
        picks = np.linspace(0, len(indices) - 1, args.limit).round().astype(int)
        indices = [indices[i] for i in sorted(set(picks.tolist()))]
    id_index = {g["id"]: i for i, g in enumerate(payload["geoms"])}
    measurements = []
    for index in indices:
        for obj, gid in objects:
            j = id_index[gid]
            matrix = Matrix(pose_rotations[index, j].tolist()).to_4x4()
            matrix.translation = Vector(pose_positions[index, j].tolist())
            obj.matrix_world = matrix
        started = time.monotonic()
        scene.render.filepath = str(frame_dir / f"{index:06d}.png")
        bpy.ops.render.render(write_still=True)
        measurements.append({"frame": index, "native_step": payload["frames"][index]["step"],
                             "seconds": round(time.monotonic() - started, 3)})
        print("FRAME " + json.dumps(measurements[-1]), flush=True)
    settings = {"renderer_source_sha256": sha(__file__), "export_sha256": sha(args.export / "scene.json"),
                "engine": args.engine, "samples": args.samples, "width": 1280, "height": 720,
                "frame_step": args.frame_step, "indices": indices, "measurements": measurements,
                "blender_version": bpy.app.version_string, "appearance_only": True,
                "native_pose_interpolation": False}
    (frame_dir / "render.json").write_text(json.dumps(settings, indent=1) + "\n")


if __name__ == "__main__":
    main()
