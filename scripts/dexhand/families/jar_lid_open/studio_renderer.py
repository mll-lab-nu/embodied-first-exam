"""Blender 4.5 studio render of exact native poses (authoring film only).

Materials, lighting and camera direction follow the approved T14 "Open a jam jar" scene film (transmissive glass,
printed label, red lacquered steel lid, glossy jam, warm-white worktop, warm key / cool fill / top rim area lights,
55 mm lens from the front right); hand materials follow the assemble_hamburger film. Only appearance differs from the
native model: no pose is synthesized or interpolated.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path
import sys
import time


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def linear(rgb):
    return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb)


def main():
    import bpy
    import numpy as np
    from mathutils import Matrix, Vector

    parser = argparse.ArgumentParser()
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=32)
    parser.add_argument("--frame-step", type=int, default=1)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    payload = json.loads((args.export / "scene.json").read_text())
    for name, expected in payload["files"].items():
        if sha(args.export / name) != expected:
            raise ValueError("Export integrity mismatch: " + name)
    geometry = np.load(args.export / "geometry.npz", allow_pickle=False)
    poses = np.load(args.export / "poses.npz", allow_pickle=False)
    positions, rotations = poses["positions"], poses["rotations"]
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
    scene.cycles.max_bounces = 10
    scene.cycles.transmission_bounces = 8
    scene.cycles.glossy_bounces = 4
    scene.cycles.diffuse_bounces = 3
    scene.render.use_persistent_data = True
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.get_devices()
    for device in prefs.devices:
        device.use = device.type == "OPTIX"
    if not any(device.use for device in prefs.devices):
        raise RuntimeError("This authoring renderer requires an OptiX device")
    scene.cycles.device = "GPU"
    scene.render.resolution_x, scene.render.resolution_y = 1280, 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.35
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes["Background"]
    background.inputs["Color"].default_value = (0.72, 0.75, 0.77, 1)
    background.inputs["Strength"].default_value = 0.45

    def material(name, color, roughness=0.4, metallic=0.0, transmission=0.0, ior=1.45, coat=0.0, texture=None,
                 bump=None, alpha=1.0):
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        bsdf = nodes["Principled BSDF"]
        bsdf.inputs["Base Color"].default_value = (*linear(color), 1)
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
        bsdf.inputs["Transmission Weight"].default_value = transmission
        bsdf.inputs["IOR"].default_value = ior
        bsdf.inputs["Coat Weight"].default_value = coat
        bsdf.inputs["Coat Roughness"].default_value = 0.15
        if texture:
            image = nodes.new("ShaderNodeTexImage")
            image.image = bpy.data.images.load(texture, check_existing=True)
            image.interpolation = "Linear"
            links.new(image.outputs["Color"], bsdf.inputs["Base Color"])
        if bump:
            coord = nodes.new("ShaderNodeTexCoord")
            noise = nodes.new("ShaderNodeTexNoise")
            noise.inputs["Scale"].default_value = bump[0]
            links.new(coord.outputs["Object"], noise.inputs["Vector"])
            node = nodes.new("ShaderNodeBump")
            node.inputs["Strength"].default_value = bump[1]
            node.inputs["Distance"].default_value = bump[2]
            links.new(noise.outputs["Fac"], node.inputs["Height"])
            links.new(node.outputs["Normal"], bsdf.inputs["Normal"])
        return mat

    # T14 film materials (scene-expansion trajectory_r1 build.py material overrides).
    glass = material("Clear soda-lime glass", (0.97, 0.99, 0.98), 0.065, transmission=1.0, ior=1.45)
    lid = material("Red lacquered steel lid", (0.58, 0.055, 0.034), 0.25, metallic=0.45, coat=0.4)
    lid_inside = material("Tinplate lid interior", (0.62, 0.62, 0.60), 0.3, metallic=0.8)
    jam = material("Strawberry jam", (0.34, 0.015, 0.026), 0.26, coat=0.3, bump=(700, 0.14, 0.00016))
    liner = material("Cream sealing liner", (0.95, 0.90, 0.77), 0.8)
    label = material("Printed jam label", (1, 1, 1), 0.73, texture=payload["label_texture"])
    printed = material("Ivory cap print", (0.96, 0.92, 0.84), 0.5)
    worktop = material("Warm white worktop", (0.76, 0.75, 0.69), 0.65, bump=(800, 0.07, 0.00002))
    floor = material("Studio floor", (0.40, 0.42, 0.41), 0.85)
    legs = material("Dark oak legs", (0.32, 0.28, 0.22), 0.6)
    shell = material("Studio ceramic white shell", (0.90, 0.92, 0.92), 0.24)
    rubber = material("Studio forest elastomer", (0.22, 0.29, 0.25), 0.65)
    dark = material("Graphite hand frame", (0.08, 0.08, 0.09), 0.45, metallic=0.3)
    steel = material("Brushed hand mechanics", (0.35, 0.39, 0.40), 0.30, metallic=0.8)
    by_material = {"jar_glass": glass, "jar_glass_thread": glass, "lid_metal": lid, "lid_inner": lid_inside,
                   "jam": jam, "liner": liner, "printed_jam_label": label, "worktop_material": worktop}

    objects, audit = [], []
    arm_materials = {}
    mesh_cache = {}
    for record in payload["geoms"]:
        name, kind, size = record["name"], record["kind"], record["size"]
        if kind == 7:
            key = str(record["mesh"])
            if key not in mesh_cache:
                source = payload["meshes"][key]
                prefix = source["prefix"]
                mesh = bpy.data.meshes.new(source["name"])
                mesh.from_pydata(geometry[prefix + "vertices"].tolist(), [], geometry[prefix + "faces"].tolist())
                mesh.update()
                for polygon in mesh.polygons:
                    polygon.use_smooth = True
                if source.get("has_uv"):
                    uv, face_uv = geometry[prefix + "uv"], geometry[prefix + "face_uv"]
                    layer = mesh.uv_layers.new(name="Native UV")
                    for loop, coordinates in zip(layer.data, uv[face_uv.reshape(-1)]):
                        loop.uv = (coordinates[0], 1 - coordinates[1])  # MuJoCo stores V as 1 - v
                mesh_cache[key] = mesh
            obj = bpy.data.objects.new(name, mesh_cache[key].copy())
            scene.collection.objects.link(obj)
        elif kind in (0, 6):
            bpy.ops.mesh.primitive_cube_add(size=2)
            obj = bpy.context.object
            obj.data.transform(Matrix.Diagonal((*(size if kind == 6 else [3, 3, 0.001]), 1)))
            if kind == 6 and min(size) > 0.002:
                mod = obj.modifiers.new("Edge finish", "BEVEL")
                mod.width, mod.segments = min(0.002, min(size) * 0.3), 3
        elif kind == 5:
            bpy.ops.mesh.primitive_cylinder_add(vertices=128, radius=size[0], depth=2 * size[1])
            obj = bpy.context.object
            for polygon in obj.data.polygons:
                polygon.use_smooth = len(polygon.vertices) == 4
            if size[1] > 0.0006:
                mod = obj.modifiers.new("Edge finish", "BEVEL")
                mod.width, mod.segments = min(0.0005, size[1] * 0.4), 3
                obj.modifiers.new("Weighted normals", "WEIGHTED_NORMAL")
        elif kind in (2, 4):
            bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=1)
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
        if record["owner"] == "hand":
            mat_name = record["material"]
            if mat_name == "green" or "fingertip" in name:
                chosen = rubber
            elif "_VL" in name:
                chosen = steel
            elif sum(record["rgba"][:3]) < 0.6:
                chosen = dark
            else:
                chosen = shell
        elif record["owner"] == "arm":
            # Tianji Marvin links (and the parked left hand): native rgba, the accepted arm films' finish.
            key = tuple(round(c, 3) for c in record["rgba"][:3])
            chosen = arm_materials.get(key)
            if chosen is None:
                chosen = arm_materials[key] = material(f"Marvin {len(arm_materials)}", record["rgba"][:3], 0.29, 0.15)
        elif name == "floor":
            chosen = floor
        elif name.startswith("table_leg"):
            chosen = legs
        elif name == "cap_orientation_print":
            chosen = printed
        else:
            chosen = by_material.get(record["material"])
            if chosen is None:
                chosen = material(f"Native {name}", record["rgba"][:3], 0.4)
        obj.data.materials.clear()
        obj.data.materials.append(chosen)
        objects.append(obj)
        audit.append({"geom": name, "material": chosen.name})

    # Cameras: the T14 film's viewing direction (front right, elevated) and its two-shot cut: a closer shot while the
    # hand grasps and unscrews the lid, then a wider one from the lift on (T14 camera revision 4 cut at the lift). Each
    # shot's target and distance are solved so the hand, jar and lid over all of its frames fit with margins.
    jar_origin = np.asarray(payload["frames"][0]["features"]["positions"]["jar"])
    normal = np.array([0.75, 0.2, 0.5])  # in front of the robot, slightly left: the right arm reaches in from behind the hand
    normal /= np.linalg.norm(normal)
    right = np.cross([0, 0, 1], normal)
    right /= np.linalg.norm(right)
    up = np.cross(normal, right)
    keep = [i for i, g in enumerate(payload["geoms"]) if g["owner"] in ("hand", "jar", "lid")]
    lens = 55.0
    tan_x = 0.018 / (lens / 1000)
    tan_y = tan_x / (1280 / 720)

    def solve(first, last, margin=0.85, pad=0.015):
        points = positions[first:last, keep].reshape(-1, 3)
        points = np.concatenate([points + np.array(c) for c in itertools.product((-pad, pad), repeat=3)])
        target = (points.min(axis=0) + points.max(axis=0)) / 2
        for _ in range(8):
            rel = points - target
            x, y, z = rel @ right, rel @ up, rel @ normal
            distance = max(np.max(z + np.abs(x) / (margin * tan_x)), np.max(z + np.abs(y) / (margin * tan_y)))
            px, py = x / ((distance - z) * tan_x), y / ((distance - z) * tan_y)
            target = target + right * (px.max() + px.min()) / 2 * distance * tan_x * 0.9 \
                + up * (py.max() + py.min()) / 2 * distance * tan_y * 0.9
        rel = points - target
        x, y, z = rel @ right, rel @ up, rel @ normal
        distance = max(np.max(z + np.abs(x) / (margin * tan_x)), np.max(z + np.abs(y) / (margin * tan_y)))
        return target, distance

    cut = next((i for i, f in enumerate(payload["frames"]) if f["phase"].startswith("lift")), None)
    if cut is None:  # rows without phase labels: cut a little after the lid is unscrewed (stage 1)
        first = next((i for i, f in enumerate(payload["frames"]) if f["features"]["stage"] >= 1), len(payload["frames"]))
        cut = min(first + 10, len(payload["frames"]))
    shots = []
    for first, last in ((0, cut), (cut, len(payload["frames"]))):
        if last > first:
            target, distance = solve(first, last)
            shots.append({"start_frame": first, "target": target.tolist(),
                          "position": (target + normal * distance).tolist(), "lens": lens})
    cam_data = bpy.data.cameras.new("Studio camera")
    camera = bpy.data.objects.new("Studio camera", cam_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    cam_data.lens, cam_data.clip_start, cam_data.clip_end = lens, 0.005, 20

    def aim(frame):
        shot = [s for s in shots if frame >= s["start_frame"]][-1]
        camera.location = Vector(shot["position"])
        camera.rotation_euler = (Vector(shot["target"]) - camera.location).to_track_quat("-Z", "Y").to_euler()

    target = np.asarray(shots[0]["target"])
    light_target = Vector((jar_origin + np.array([0.059, -0.025, 0.061])).tolist())
    for name, offset, energy, size, color in (
        ("Warm key", (-0.3, -0.2, 0.48), 18, 0.38, (1, 0.92, 0.80)),
        ("Cool fill", (0.18, 0.27, 0.36), 10, 0.32, (0.80, 0.9, 1)),
        ("Top rim", (0.12, 0.10, 0.55), 12, 0.30, (1, 1, 1)),
        ("Hand fill", (0.35, -0.45, 0.60), 14, 0.6, (1, 0.97, 0.92)),
    ):
        data = bpy.data.lights.new(name, "AREA")
        data.energy, data.shape, data.size, data.color = energy, "DISK", size, color
        light = bpy.data.objects.new(name, data)
        scene.collection.objects.link(light)
        light.location = light_target + Vector(offset)
        light.rotation_euler = (light_target - light.location).to_track_quat("-Z", "Y").to_euler()

    indices = list(range(0, len(payload["frames"]), args.frame_step))
    if indices[-1] != len(payload["frames"]) - 1:
        indices.append(len(payload["frames"]) - 1)
    if args.limit:
        indices = indices[:: max(1, len(indices) // args.limit)][: args.limit]
    measurements = []
    for index in indices:
        aim(index)
        for obj, j in zip(objects, range(len(objects))):
            matrix = Matrix(rotations[index, j].tolist()).to_4x4()
            matrix.translation = Vector(positions[index, j].tolist())
            obj.matrix_world = matrix
        started = time.monotonic()
        scene.render.filepath = str(frame_dir / f"{index:06d}.png")
        bpy.ops.render.render(write_still=True)
        measurements.append({"frame": index, "native_step": payload["frames"][index]["step"],
                             "seconds": round(time.monotonic() - started, 2)})
        print("FRAME " + json.dumps(measurements[-1]), flush=True)
    (frame_dir / "render.json").write_text(json.dumps({
        "renderer_source_sha256": sha(__file__), "export_sha256": sha(args.export / "scene.json"),
        "blender_version": "Blender " + bpy.app.version_string + " Cycles OptiX", "samples": args.samples,
        "width": 1280, "height": 720, "frame_step": args.frame_step, "indices": indices,
        "camera_schedule": shots,
        "native_pose_interpolation": False, "materials": audit, "measurements": measurements}, indent=1) + "\n")


if __name__ == "__main__":
    main()
