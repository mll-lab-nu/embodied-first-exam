"""Authoring only (Blender 4.5): studio render of exported native poses with the T16 scene film's look.

Materials, lights, exposure and camera follow the approved T16 kinematic film (warm oak counter, dark coated pan,
glazed plate, browned pancake texture, three area lights). Geometry poses are the exported MuJoCo geom poses; nothing
is interpolated or moved by Blender.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys


def main():
    import bpy
    import numpy as np
    from mathutils import Matrix, Vector

    parser = argparse.ArgumentParser()
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=16)
    parser.add_argument("--frame-step", type=int, default=1)
    parser.add_argument("--only", type=str, default="")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    payload = json.loads((args.export / "scene.json").read_text())
    geometry = np.load(args.export / "geometry.npz", allow_pickle=False)
    poses = np.load(args.export / "poses.npz", allow_pickle=False)
    positions, rotations = poses["positions"], poses["rotations"]
    args.output.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = args.samples
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = "OPENIMAGEDENOISE"
    scene.cycles.use_persistent_data = True
    scene.cycles.max_bounces = 6
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.get_devices()
    for device in prefs.devices:
        device.use = device.type == "OPTIX"
    scene.cycles.device = "GPU" if any(d.use for d in prefs.devices) else "CPU"
    scene.render.resolution_x, scene.render.resolution_y = 1280, 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.2
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes["Background"]
    background.inputs["Color"].default_value = (0.72, 0.75, 0.77, 1)
    background.inputs["Strength"].default_value = 0.45

    def linear(rgb):
        return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb)

    def material(name, rgb, metallic=0.0, roughness=0.3, coat=0.0, bump=None, image=None):
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        bsdf = nodes["Principled BSDF"]
        bsdf.inputs["Base Color"].default_value = (*linear(rgb), 1)
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
        if image:
            tex = nodes.new("ShaderNodeTexImage")
            tex.image = bpy.data.images.load(image, check_existing=True)
            links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
            bsdf.inputs["Subsurface Weight"].default_value = 0.08
            bsdf.inputs["Subsurface Scale"].default_value = 0.002
        return mat

    # T16 scene film presentation materials (scene_expansion pan_sharpa studio export, visual overrides).
    oak = material("Warm oak counter", (0.56, 0.43, 0.28), roughness=0.67, bump=(250, 0.15, 5e-05))
    cabinet = material("Kitchen cabinet", (0.24, 0.32, 0.27), roughness=0.6)
    floor = material("Studio floor", (0.65, 0.67, 0.63), roughness=0.8)
    pan = material("Hard-anodised pan coating", (0.09, 0.095, 0.1), 0.65, 0.34, bump=(1900, 0.1, 1.2e-05))
    grip = material("Soft-touch black grip", (0.06, 0.065, 0.055), 0.0, 0.53, bump=(1200, 0.1, 1e-05))
    steel = material("Brushed stainless neck", (0.76, 0.79, 0.81), 0.9, 0.22)
    ceramic = material("Glazed ceramic plate", (0.91, 0.90, 0.84), 0.0, 0.23, coat=0.4)
    pancake = material("Browned pancake", (1, 1, 1), 0.0, 0.62, image=payload["texture"])
    shell = material("Studio ceramic white shell", (0.90, 0.92, 0.92), 0.0, 0.24)
    rubber = material("Studio forest elastomer", (0.22, 0.29, 0.25), 0.0, 0.65)
    joints = material("Satin joint housings", (0.55, 0.58, 0.60), 0.6, 0.35)

    robot_materials = {}

    def pick(record):
        name = record["name"]
        if record["owner"] == "robot":
            key = tuple(round(c, 3) for c in record["rgba"][:3])
            if key not in robot_materials:
                robot_materials[key] = material("Marvin " + str(key), key, 0.15, 0.35)
            return robot_materials[key]
        if record["owner"] == "hand":
            if record["material"] == "green" or "elastomer" in name:
                return rubber
            return joints if "_VL" in name else shell
        if name == "floor":
            return floor
        if name == "counter_top":
            return oak
        if name == "counter_cabinet":
            return cabinet
        if name.startswith("pan_shell"):
            return pan
        if name.startswith(("pan_handle", "turner_handle", "turner_blade")):
            return grip
        if name.startswith("turner_neck"):
            return steel
        if name.startswith("plate"):
            return ceramic
        if name.startswith("pancake"):
            return pancake
        return shell

    objects = []
    for j, record in enumerate(payload["geoms"]):
        kind, size, name = record["kind"], record["size"], record["name"]
        if kind == 7:
            source = payload["meshes"][str(record["mesh"])]
            prefix = source["prefix"]
            mesh = bpy.data.meshes.new(source["name"])
            faces = geometry[prefix + "faces"].tolist()
            mesh.from_pydata(geometry[prefix + "vertices"].tolist(), [], faces)
            mesh.update()
            if source.get("uv"):
                uv = geometry[prefix + "uv"]
                faceuv = geometry[prefix + "faceuv"]
                layer = mesh.uv_layers.new(name="UVMap")
                for poly in mesh.polygons:
                    for k, loop in enumerate(poly.loop_indices):
                        layer.data[loop].uv = uv[faceuv[poly.index][k]].tolist()
            for poly in mesh.polygons:
                poly.use_smooth = True
            obj = bpy.data.objects.new(name, mesh)
            scene.collection.objects.link(obj)
            if not name.startswith("pancake"):
                mod = obj.modifiers.new("Weighted normals", "WEIGHTED_NORMAL")
                mod.keep_sharp = True
        elif kind == 0:  # plane
            bpy.ops.mesh.primitive_plane_add(size=2)
            obj = bpy.context.object
            obj.data.transform(Matrix.Diagonal((6, 6, 1, 1)))
        elif kind == 6:  # box
            bpy.ops.mesh.primitive_cube_add(size=2)
            obj = bpy.context.object
            obj.data.transform(Matrix.Diagonal((*size, 1)))
            mod = obj.modifiers.new("Edge rounding", "BEVEL")
            mod.width, mod.segments = 0.003, 3
        elif kind == 5:
            bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=size[0], depth=2 * size[1])
            obj = bpy.context.object
        elif kind in (2, 4):
            bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=1)
            obj = bpy.context.object
            obj.data.transform(Matrix.Diagonal((*(size if kind == 4 else [size[0]] * 3), 1)))
        elif kind == 3:
            bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=size[0], depth=2 * size[1])
            obj = bpy.context.object
        else:
            continue
        obj.name = name
        obj.data.materials.clear()
        obj.data.materials.append(pick(record))
        objects.append((obj, j))

    target = Vector((0.57, -0.065, 0.925))
    for name, offset, energy, size, color in (
        ("Large warm kitchen key", (-0.25, -0.22, 0.62), 32, 0.55, (1, 0.92, 0.81)),
        ("Cool soft fill", (0.2, 0.3, 0.5), 20, 0.45, (0.85, 0.91, 1)),
        ("Metal rim", (0.35, 0.04, 0.7), 28, 0.4, (1, 1, 1)),
    ):
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
    camera.location = (1.16, -1.10, 1.66)  # T16 film camera; slightly wider to include the Marvin arm
    look = Vector((0.52, -0.08, 0.98))
    camera.rotation_euler = (look - camera.location).to_track_quat("-Z", "Y").to_euler()
    data.lens, data.clip_start, data.clip_end = 36, 0.01, 30
    indices = list(range(0, len(payload["frames"]), args.frame_step))
    if indices[-1] != len(payload["frames"]) - 1:
        indices.append(len(payload["frames"]) - 1)
    if args.only:
        indices = [int(v) for v in args.only.split(",")]
    for index in indices:
        for obj, j in objects:
            matrix = Matrix(rotations[index, j].tolist()).to_4x4()
            matrix.translation = Vector(positions[index, j].tolist())
            obj.matrix_world = matrix
        scene.render.filepath = str(args.output / f"{index:06d}.png")
        bpy.ops.render.render(write_still=True)
        print(f"FRAME {index}", flush=True)


if __name__ == "__main__":
    main()
