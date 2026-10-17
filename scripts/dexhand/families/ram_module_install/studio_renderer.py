"""Blender 4.5.3 studio renderer for exact native poses of the physical RAM-installation replay (authoring only).

Adapted from the accepted T28 scene renderer (scene_expansion repairs/ram_install_meta_delivery_trajectory_r1/
studio_render.py, with its lighting r3 values): same native materials and textures, dark-polymer socket finish, warm
studio key/fill/edge lights, AgX view transform and zooming socket camera. The hand uses the DexHand film materials
(pearl shell, forest silicone fingertips). Only appearance differs from the MuJoCo state; no pose is interpolated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import time

ROLE_NAMES = {"1": "base_color", "2": "occlusion", "3": "roughness", "4": "metallic", "5": "normal", "6": "opacity",
              "7": "emissive", "8": "base_color", "9": "orm"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def linear_rgb(color):
    return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in color[:3])


def main():
    import bpy
    import numpy as np
    from mathutils import Matrix, Vector

    parser = argparse.ArgumentParser()
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=24)
    parser.add_argument("--engine", choices=["cycles", "eevee"], default="eevee")
    parser.add_argument("--frame-step", type=int, default=1)
    parser.add_argument("--still", choices=["initial", "middle", "final"])
    parser.add_argument("--cpu", action="store_true", help="Cycles on the CPU (no GPU lane available)")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    directory, output = args.export.resolve(), args.output.resolve()
    payload = json.loads((directory / "scene.json").read_text())
    if payload["scripted_object_motion"] or payload["evidence_type"] != "physical_actuator_replay":
        raise ValueError("Only physical actuator-replay exports are rendered here")
    for name, expected in payload["files"].items():
        if sha(directory / name) != expected:
            raise ValueError("Export integrity mismatch: " + name)
    geometry = np.load(directory / "geometry.npz", allow_pickle=False)
    poses = np.load(directory / "poses.npz", allow_pickle=False)
    positions, rotations = poses["positions"], poses["rotations"]
    config = payload["config"]
    frames_dir = output.with_suffix("").with_name(output.stem + "-frames")
    frames_dir.mkdir(parents=True, exist_ok=True)
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
            device.use = device.type == "OPTIX" and not args.cpu
        scene.cycles.device = "GPU" if any(d.use for d in prefs.devices) else "CPU"
        scene.cycles.use_persistent_data = True
    else:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
        scene.eevee.taa_render_samples = args.samples
    scene.render.resolution_x, scene.render.resolution_y = 1280, 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = config.get("exposure", -0.25)
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes["Background"]
    background.inputs["Color"].default_value = (0.72, 0.75, 0.77, 1)
    background.inputs["Strength"].default_value = 0.45
    cache = {}

    def material(name, rgba, metallic=0.0, roughness=0.3, textures=None, coat=0.0):
        if name in cache:
            return cache[name]
        result = bpy.data.materials.new(name)
        result.use_nodes = True
        nodes, links = result.node_tree.nodes, result.node_tree.links
        bsdf = nodes.get("Principled BSDF")
        bsdf.inputs["Base Color"].default_value = (*linear_rgb(rgba), rgba[3])
        bsdf.inputs["Metallic"].default_value = metallic
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Coat Weight"].default_value = coat
        for role, filename in (textures or {}).items():
            role = ROLE_NAMES.get(role, role)
            texture = nodes.new("ShaderNodeTexImage")
            texture.image = bpy.data.images.load(str(directory / filename), check_existing=True)
            if role == "base_color":
                links.new(texture.outputs["Color"], bsdf.inputs["Base Color"])
        cache[name] = result
        return result

    shell = material("Pearl white polymer housing", (0.89, 0.91, 0.89, 1), 0.10, 0.27)
    rubber = material("Forest silicone fingertips", (0.10, 0.24, 0.18, 1), 0.0, 0.68)
    surface = material("Studio warm gray surface", (0.72, 0.73, 0.71, 1), 0.0, 0.75)
    natives = [material(f"Native {i}: {m['name']}", m["rgba"], max(0, m.get("metallic", 0)),
                        m["roughness"] if m.get("roughness", -1) >= 0 else 0.35, m.get("textures"))
               for i, m in enumerate(payload["materials"])]
    objects, audit, mesh_cache = [], [], {}
    for geom in payload["geoms"]:
        kind, size, name = geom["kind"], geom["size"], geom["name"]
        if kind == 7:
            key = str(geom["mesh"])
            if key not in mesh_cache:
                record = payload["meshes"][key]
                prefix = record["prefix"]
                mesh = bpy.data.meshes.new(record["name"] or key)
                mesh.from_pydata(geometry[prefix + "vertices"].tolist(), [], geometry[prefix + "faces"].tolist())
                mesh.update()
                for polygon in mesh.polygons:
                    polygon.use_smooth = not geom.get("authored_cad", False)
                normals, face_normals = geometry[prefix + "normals"], geometry[prefix + "face_normals"]
                if len(normals) and face_normals.min() >= 0 and not geom["is_hand"]:
                    mesh.normals_split_custom_set(normals[face_normals.reshape(-1)].tolist())
                mesh_cache[key] = mesh
            obj = bpy.data.objects.new(name, mesh_cache[key].copy())
            scene.collection.objects.link(obj)
        elif kind in (0, 6):
            bpy.ops.mesh.primitive_cube_add(size=2)
            obj = bpy.context.object
            obj.scale = size if kind == 6 else [3, 3, 0.001]
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
            bevel = config.get("visual_bevel_m", 0.00005)
            if kind == 6 and bevel and not geom["is_hand"]:
                modifier = obj.modifiers.new("Visual edge finish", "BEVEL")
                modifier.width, modifier.segments = min(bevel, min(size) * 0.3), 2
        elif kind == 3:
            r, half = size[:2]
            vertices, faces = [], []
            rings = [(math.pi * j / 8, half) for j in range(5)] + [(math.pi * j / 8, -half) for j in range(4, 9)]
            for angle, offset in rings:
                for k in range(16):
                    a = 2 * math.pi * k / 16
                    vertices.append((r * math.sin(angle) * math.cos(a), r * math.sin(angle) * math.sin(a),
                                     r * math.cos(angle) + offset))
            for j in range(len(rings) - 1):
                for k in range(16):
                    a, b = j * 16 + k, j * 16 + (k + 1) % 16
                    faces.append((a, b, b + 16, a + 16))
            mesh = bpy.data.meshes.new(name)
            mesh.from_pydata(vertices, [], faces)
            obj = bpy.data.objects.new(name, mesh)
            scene.collection.objects.link(obj)
            for polygon in mesh.polygons:
                polygon.use_smooth = True
        elif kind in (2, 4):
            bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=1)
            obj = bpy.context.object
            obj.scale = [size[0]] * 3 if kind == 2 else size
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
            for polygon in obj.data.polygons:
                polygon.use_smooth = True
        elif kind == 5:
            bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=size[0], depth=2 * size[1])
            obj = bpy.context.object
            for polygon in obj.data.polygons:
                polygon.use_smooth = len(polygon.vertices) == 4
        else:
            raise ValueError(f"Unsupported visible geometry {kind}: {name}")
        obj.name = name
        mid = geom["material"]
        if "visual_material" in geom:
            v = geom["visual_material"]
            chosen = material(f"Presentation {name}", v.get("rgba", geom["rgba"]), v.get("metallic", 0),
                              v.get("roughness", 0.3))
        elif geom["is_hand"]:
            native = payload["materials"][mid]["name"] if mid >= 0 else ""
            chosen = rubber if native == "green" else shell
        elif kind == 0:
            chosen = surface
        elif mid >= 0:
            chosen = natives[mid]
        else:
            chosen = material(f"Primitive {geom['rgba']}", geom["rgba"], 0, 0.38)
        obj.data.materials.clear()
        obj.data.materials.append(chosen)
        objects.append(obj)
        audit.append(dict(geom=name, material=chosen.name))

    camera_data = bpy.data.cameras.new("Socket camera")
    camera = bpy.data.objects.new("Socket camera", camera_data)
    scene.collection.objects.link(camera)
    camera_data.clip_start, camera_data.clip_end = 0.001, 20
    scene.camera = camera
    light_target = Vector(config["light_target"])
    for lamp in config["lights"]:
        data = bpy.data.lights.new(lamp["name"], "AREA")
        data.energy, data.shape, data.size, data.color = lamp["energy"], "DISK", lamp["size"], lamp["color"]
        light = bpy.data.objects.new(lamp["name"], data)
        scene.collection.objects.link(light)
        light.location = light_target + Vector(lamp["offset"])
        light.rotation_euler = (light_target - light.location).to_track_quat("-Z", "Y").to_euler()
    count = len(payload["frames"])
    if args.still:
        indices = [{"initial": 0, "middle": count // 2, "final": count - 1}[args.still]]
    else:
        indices = list(range(0, count, args.frame_step))
        if indices[-1] != count - 1:
            indices.append(count - 1)
    moving = [i for i, g in enumerate(payload["geoms"]) if g["is_hand"] or g["body"] in ("dimm", "moving_latch")]
    measurements = []
    for n, index in enumerate(indices):
        update = range(len(objects)) if n == 0 else moving
        for j in update:
            matrix = Matrix(rotations[index, j]).to_4x4()
            matrix.translation = Vector(positions[index, j])
            objects[j].matrix_world = matrix
        shot = payload["frames"][index]["camera"]
        camera.location = Vector(shot["position"])
        camera.rotation_euler = (Vector(shot["target"]) - camera.location).to_track_quat("-Z", "Y").to_euler()
        camera_data.lens = shot["lens"]
        started = time.monotonic()
        scene.render.filepath = str(frames_dir / f"{index:06d}.png")
        bpy.ops.render.render(write_still=True)
        measurements.append(dict(frame=index, step=payload["frames"][index]["step"],
                                 seconds=round(time.monotonic() - started, 3)))
        print("FRAME " + json.dumps(measurements[-1]), flush=True)
    settings = dict(renderer_source_sha256=sha(__file__), export_sha256=sha(directory / "scene.json"),
                    engine=("Cycles " if args.engine == "cycles" else "EEVEE Next ") + bpy.app.version_string,
                    samples=args.samples, width=1280, height=720, appearance_only=True,
                    native_pose_interpolation=False, indices=indices, measurements=measurements, materials=audit)
    if not args.still:
        (frames_dir / "render.json").write_text(json.dumps(settings, indent=2) + "\n")


if __name__ == "__main__":
    main()
