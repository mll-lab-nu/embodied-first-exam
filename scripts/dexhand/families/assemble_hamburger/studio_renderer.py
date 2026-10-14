"""Food photography materials and Cycles lighting on exact native poses.

Only presentation surfaces, bevels, cameras and lighting differ from the native
preview. No ingredient or hand motion is synthesized or interpolated.
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


def main():
    import bpy
    import numpy as np
    from mathutils import Matrix, Vector

    parser = argparse.ArgumentParser()
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=48)
    parser.add_argument("--frame-step", type=int, default=2)
    parser.add_argument("--engine", choices=["cycles", "eevee"], default="cycles")
    parser.add_argument("--still", choices=["initial", "final"])
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    if args.frame_step < 1 or args.samples < 1:
        parser.error("Frame step and sample count must be positive")
    payload = json.loads((args.export / "scene.json").read_text())
    for name, expected in payload["files"].items():
        if sha(args.export / name) != expected:
            raise ValueError("Export integrity mismatch: " + name)
    geometry = np.load(args.export / "geometry.npz", allow_pickle=False)
    poses = np.load(args.export / "poses.npz", allow_pickle=False)
    pose_positions = poses["positions"]
    pose_rotations = poses["rotations"]
    frame_dir = args.output.with_suffix("").with_name(args.output.stem + "-frames")
    frame_dir.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = args.samples
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.025
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = "OPENIMAGEDENOISE"
    scene.cycles.denoising_use_gpu = True
    scene.cycles.use_persistent_data = True
    scene.cycles.max_bounces = 7
    scene.cycles.diffuse_bounces = 3
    scene.cycles.glossy_bounces = 4
    scene.cycles.transmission_bounces = 4
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.get_devices()
    for device in prefs.devices:
        device.use = device.type == "OPTIX"
    if not any(device.use for device in prefs.devices):
        raise RuntimeError("This authoring renderer requires an OptiX device")
    scene.cycles.device = "GPU"
    if args.engine == "eevee":
        scene.render.engine = "BLENDER_EEVEE_NEXT"
        scene.eevee.taa_render_samples = 32
        scene.eevee.use_raytracing = True
        scene.eevee.ray_tracing_options.resolution_scale = "2"
    scene.render.resolution_x, scene.render.resolution_y = 1280, 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.55
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.76, 0.78, 0.73, 1)
    bg.inputs["Strength"].default_value = 0.32

    def linear(rgb):
        return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb)

    def material(name, color, roughness=0.4, metallic=0, sss=0, coat=0):
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes["Principled BSDF"]
        bsdf.inputs["Base Color"].default_value = (*linear(color), 1)
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
        bsdf.inputs["Subsurface Weight"].default_value = sss
        bsdf.inputs["Subsurface Scale"].default_value = 0.0015
        bsdf.inputs["Coat Weight"].default_value = coat
        bsdf.inputs["Coat Roughness"].default_value = 0.23
        return mat

    def noise(mat, scale, detail=3):
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        coord = nodes.new("ShaderNodeTexCoord")
        tex = nodes.new("ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = scale * 10
        tex.inputs["Detail"].default_value = detail
        tex.inputs["Roughness"].default_value = 0.68
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

    def bump(mat, tex, distance, strength=0.4):
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        node = nodes.new("ShaderNodeBump")
        node.inputs["Distance"].default_value = distance
        node.inputs["Strength"].default_value = strength
        links.new(tex.outputs["Fac"], node.inputs["Height"])
        links.new(node.outputs["Normal"], nodes["Principled BSDF"].inputs["Normal"])

    shell = material("Pearl white polymer housing", (0.89, 0.91, 0.89), 0.27, 0.10)
    rubber = material("Forest silicone fingertips", (0.10, 0.24, 0.18), 0.68)
    steel = material("Brushed stainless mechanics", (0.35, 0.39, 0.40), 0.30, 0.8)
    crust = material("Golden toasted bread crust", (0.82, 0.44, 0.12), 0.45, sss=0.06, coat=0.12)
    palette(
        crust, noise(crust, 6, 4), [(0.15, (0.32, 0.095, 0.02)), (0.48, (0.65, 0.24, 0.04)), (0.8, (0.84, 0.50, 0.14))]
    )
    bump(crust, noise(crust, 95, 3), 0.00055, 0.45)
    crumb = material("Soft bread crumb", (0.93, 0.76, 0.45), 0.73, sss=0.19)
    palette(crumb, noise(crumb, 28), [(0.2, (0.69, 0.47, 0.22)), (0.55, (0.91, 0.77, 0.49)), (0.8, (0.99, 0.9, 0.66))])
    bump(crumb, noise(crumb, 100), 0.00075, 0.65)
    seed = material("Sesame seed ivory", (0.91, 0.82, 0.61), 0.65, sss=0.09)
    meat = material("Seared beef patty", (0.27, 0.12, 0.052), 0.52, sss=0.055, coat=0.1)
    palette(
        meat,
        noise(meat, 18, 5),
        [
            (0.17, (0.055, 0.022, 0.01)),
            (0.42, (0.22, 0.082, 0.027)),
            (0.65, (0.38, 0.19, 0.074)),
            (0.88, (0.55, 0.35, 0.18)),
        ],
    )
    bump(meat, noise(meat, 95, 4), 0.001, 0.7)
    char = material("Grilled caramelized crust", (0.09, 0.042, 0.02), 0.78)
    bump(char, noise(char, 32), 0.0005, 0.5)
    cheese = material("Waxy cheddar slice", (0.98, 0.65, 0.09), 0.32, sss=0.22, coat=0.12)
    palette(cheese, noise(cheese, 5), [(0.1, (0.83, 0.47, 0.025)), (0.55, (0.97, 0.67, 0.11)), (0.9, (1, 0.79, 0.23))])
    bump(cheese, noise(cheese, 140, 2), 0.000025, 0.23)
    skin = material("Tomato skin", (0.72, 0.07, 0.025), 0.23, sss=0.16, coat=0.4)
    flesh = material("Moist tomato flesh", (0.91, 0.15, 0.055), 0.24, sss=0.29, coat=0.30)
    palette(
        flesh, noise(flesh, 10), [(0.1, (0.65, 0.04, 0.015)), (0.6, (0.91, 0.19, 0.065)), (0.92, (0.96, 0.36, 0.13))]
    )
    bump(flesh, noise(flesh, 55), 0.00016, 0.35)
    gel = material("Tomato seed gel", (0.71, 0.20, 0.045), 0.12, sss=0.10, coat=0.45)
    gel.node_tree.nodes["Principled BSDF"].inputs["Transmission Weight"].default_value = 0.24
    gel.node_tree.nodes["Principled BSDF"].inputs["IOR"].default_value = 1.34
    tomato_seed = material("Tomato seeds", (0.94, 0.75, 0.31), 0.36, sss=0.15)
    leaf = material("Fresh green lettuce leaf", (0.24, 0.48, 0.06), 0.36, sss=0.24, coat=0.22)
    leaf.node_tree.nodes["Principled BSDF"].inputs["Subsurface Scale"].default_value = 0.0005
    palette(
        leaf, noise(leaf, 6, 5), [(0.05, (0.065, 0.24, 0.018)), (0.45, (0.21, 0.43, 0.035)), (0.85, (0.48, 0.64, 0.15))]
    )
    bump(leaf, noise(leaf, 55, 3), 0.00014, 0.35)
    vein = material("Lettuce pale veins", (0.47, 0.63, 0.17), 0.43, sss=0.25)
    porcelain = material("Glazed warm white porcelain", (0.91, 0.91, 0.84), 0.20, coat=0.4)
    ceramic = material("Matte ivory preparation ceramics", (0.80, 0.81, 0.73), 0.41)
    stone = material("Warm limestone counter", (0.69, 0.66, 0.59), 0.71)
    palette(
        stone, noise(stone, 4, 5), [(0.05, (0.49, 0.47, 0.41)), (0.45, (0.70, 0.67, 0.60)), (0.90, (0.82, 0.79, 0.71))]
    )
    bump(stone, noise(stone, 220, 2), 0.00004, 0.2)
    floor = material("Warm neutral studio", (0.73, 0.72, 0.66), 0.82)
    cache, objects = {}, []
    audit = []
    hidden = []
    for record in payload["geoms"]:
        name, kind, size = record["name"], record["kind"], record["size"]
        if record["owner"] == "lettuce" and "collision" in name:
            hidden.append(name)
            continue
        if kind == 7:
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
            obj = bpy.data.objects.new(name, cache[mid].copy())
            scene.collection.objects.link(obj)
        elif kind in (0, 6):
            bpy.ops.mesh.primitive_cube_add(size=2)
            obj = bpy.context.object
            obj.data.transform(Matrix.Diagonal((*(size if kind == 6 else [2, 2, 0.001]), 1)))
        elif kind == 5:
            bpy.ops.mesh.primitive_cylinder_add(vertices=96, radius=size[0], depth=2 * size[1])
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
            r, half = size[:2]
            vertices, faces = [], []
            rings = [(math.pi * j / 24, half) for j in range(13)] + [(math.pi * j / 24, -half) for j in range(12, 25)]
            for angle, offset in rings:
                for k in range(32):
                    a = 2 * math.pi * k / 32
                    vertices.append(
                        (
                            r * math.sin(angle) * math.cos(a),
                            r * math.sin(angle) * math.sin(a),
                            r * math.cos(angle) + offset,
                        )
                    )
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
        chosen = ceramic
        bevel = 0.0
        if record["owner"] == "hand":
            chosen = rubber if record["material"] == "green" else steel if "_VL" in name else shell
        elif name == "floor":
            chosen = floor
        elif name == "table":
            chosen, bevel = stone, 0.002
        elif name == "serving_plate" or name.startswith("plate_rim_"):
            chosen, bevel = porcelain, 0.003 if kind == 5 else 0
        elif name == "bun_crust":
            chosen = crust
        elif name.startswith("sesame_"):
            chosen = seed
        elif "bun" in name:
            chosen = crust if name == "bottom_bun_collision" else crumb
            bevel = 0.0035 if kind == 5 and "collision" in name else 0.0002
        elif name.startswith("patty_texture") or name.startswith("grill_mark"):
            chosen = char
        elif name == "patty_collision":
            chosen, bevel = meat, 0.0015
        elif record["owner"] == "cheese":
            chosen, bevel = cheese, 0.00035
        elif name == "tomato_collision":
            chosen, bevel = skin, 0.0006
        elif name == "tomato_flesh":
            chosen = flesh
        elif name.startswith("tomato_chamber"):
            chosen = gel
        elif name.startswith("tomato_seed"):
            chosen = tomato_seed
        elif record["owner"] == "lettuce":
            chosen = vein if "vein" in name else leaf
        elif "prep_support" in name:
            chosen, bevel = ceramic, 0.001
        obj.data.materials.clear()
        obj.data.materials.append(chosen)
        if bevel > 0 and kind in (5, 6):
            mod = obj.modifiers.new("Presentation edge rounding", "BEVEL")
            mod.width, mod.segments = bevel, 4
            obj.modifiers.new("Weighted surface normals", "WEIGHTED_NORMAL")
        if record["owner"] == "lettuce" and kind == 7:
            mod = obj.modifiers.new("Leaf visual epidermis", "SOLIDIFY")
            mod.thickness = 0.00015
            mod.offset = 0
        if name == "patty_collision":
            mod = obj.modifiers.new("Meat surface tessellation", "SUBSURF")
            mod.subdivision_type = "SIMPLE"
            mod.levels, mod.render_levels = 2, 2
            texture = bpy.data.textures.new("Static seared meat surface", type="CLOUDS")
            texture.noise_scale = 0.0035
            texture.noise_depth = 2
            mod = obj.modifiers.new("Presentation meat micro surface", "DISPLACE")
            mod.texture, mod.texture_coords = texture, "LOCAL"
            mod.strength, mod.mid_level = 0.0012, 0.5
        objects.append((obj, record["id"]))
        audit.append({"geom": name, "native_geom_id": record["id"], "bevel_m": bevel, "material": chosen.name})

    def area(name, position, target, energy, size, color):
        data = bpy.data.lights.new(name, "AREA")
        data.energy, data.shape, data.size, data.color = energy, "DISK", size, color
        obj = bpy.data.objects.new(name, data)
        scene.collection.objects.link(obj)
        obj.location = position
        obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()

    area("Large warm window", (0.2, -0.5, 1.4), (-0.02, 0, 0.35), 40, 0.65, (1, 0.91, 0.78))
    area("Soft daylight fill", (-0.55, 0.25, 1.0), (-0.02, 0, 0.35), 20, 0.5, (0.83, 0.91, 1))
    area("Warm rim light", (0.35, 0.45, 1.1), (-0.02, 0, 0.35), 16, 0.45, (1, 0.95, 0.86))
    data = bpy.data.cameras.new("Food photography camera")
    camera = bpy.data.objects.new("Food photography camera", data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    data.clip_start, data.clip_end = 0.001, 20
    data.dof.use_dof = True
    focus = bpy.data.objects.new("Optical focus", None)
    scene.collection.objects.link(focus)
    data.dof.focus_object = focus
    indices = (
        [0 if args.still == "initial" else len(payload["frames"]) - 1]
        if args.still
        else list(range(0, len(payload["frames"]), args.frame_step))
    )
    if not args.still and indices[-1] != len(payload["frames"]) - 1:
        indices.append(len(payload["frames"]) - 1)
    id_index = {g["id"]: i for i, g in enumerate(payload["geoms"])}
    settings = {
        "renderer_source_sha256": sha(__file__),
        "export_sha256": sha(args.export / "scene.json"),
        "samples": args.samples,
        "width": 1280,
        "height": 720,
        "engine": "Cycles OptiX" if args.engine == "cycles" else "Eevee Next / ray tracing",
        "appearance_only": True,
        "native_pose_interpolation": False,
        "video_fps": payload["fps"] / args.frame_step,
        "native_controls_per_rendered_frame": payload["stride"] * args.frame_step,
        "meat_visual_displacement_m": 0.0012,
        "hidden_visual_proxies": hidden,
        "materials_and_bevels": audit,
    }
    measurements = []
    active = "patty"
    for index in indices:
        record = payload["frames"][index]
        complete = record["features"]["success"]
        target = Vector((-0.16, 0, 0.375) if complete else (0.065, -0.035, 0.37))
        camera.location = (0.075, -0.275, 0.54) if complete else (0.55, -0.71, 0.96)
        for ingredient in ("patty", "cheese", "tomato", "lettuce", "top_bun"):
            if ingredient in record["phase"]:
                active = ingredient
        if not complete and record["phase"].startswith(
            ("pinch", "stabilize grasp", "lift", "center", "lower", "stabilize above", "open side", "wait for free")
        ):
            position = Vector(record["features"]["positions"][active])
            target = position + Vector((0, 0, 0.045))
            camera.location = target + Vector((0.30, -0.40, 0.34))
        camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
        data.lens = 46 if complete else 38
        data.dof.aperture_fstop = 8 if complete else 6.3
        focus.location = target
        for obj, gid in objects:
            j = id_index[gid]
            matrix = Matrix(pose_rotations[index, j]).to_4x4()
            matrix.translation = Vector(pose_positions[index, j])
            obj.matrix_world = matrix
        started = time.monotonic()
        scene.render.filepath = str(frame_dir / f"{index:06d}.png")
        bpy.ops.render.render(write_still=True)
        measurements.append({"frame": index, "native_step": record["step"], "seconds": time.monotonic() - started})
        print("FRAME " + json.dumps(measurements[-1]), flush=True)
    settings.update(indices=indices, measurements=measurements, blender_version=bpy.app.version_string)
    (frame_dir / "render.json").write_text(json.dumps(settings, indent=2) + "\n")


if __name__ == "__main__":
    main()
