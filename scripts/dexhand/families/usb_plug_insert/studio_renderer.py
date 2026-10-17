"""Blender studio presentation of exact native poses (authoring only; run by presentation.py render).

Materials, lighting and exposure follow the approved T24 scene film (`studio_renderer_r1.py` of the scene-expansion
source: warm wood counter with micro bump, satin black hub/cable PBR, metal shell, AgX, three soft area lights); hand
surfaces follow `assemble_hamburger/studio_renderer.py`. Only appearance, bevels and cameras differ from the native
model. No hand, plug, cable or hub motion is synthesized or interpolated: every frame is one exported native sample.
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


# Arm films: a wide shot from the robot's left-front quarter (robot, desk, hub and plug), then the port close-up.
WIDE = {"position": (0.05, -1.05, 1.45), "target": (0.72, -0.22, 0.85), "lens": 30}
CLOSE = {"position": (0.20, -0.75, 0.95), "target": (0.66, -0.15, 0.72), "lens": 40}


def main():
    import bpy
    import numpy as np
    from mathutils import Matrix, Vector

    parser = argparse.ArgumentParser()
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=32)
    parser.add_argument("--frame-step", type=int, default=1)
    parser.add_argument("--engine", choices=["cycles", "eevee"], default="eevee")
    parser.add_argument("--only")
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
        scene.cycles.device = "GPU" if any(d.use for d in prefs.devices) else "CPU"  # CPU: preview stills only
        scene.cycles.use_persistent_data = True
    else:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
        scene.eevee.taa_render_samples = args.samples
        scene.eevee.use_raytracing = True
        scene.eevee.ray_tracing_options.resolution_scale = "2"
        scene.eevee.use_shadows = True
    scene.render.resolution_x, scene.render.resolution_y = 1280, 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.25
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes["Background"]
    background.inputs["Color"].default_value = (0.72, 0.75, 0.77, 1)
    background.inputs["Strength"].default_value = 0.45

    def linear(rgb):
        return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb[:3])

    cache = {}

    def material(name, rgba, metallic=0.0, roughness=0.4, bump=None, coat=0.0):
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
        cache[name] = mat
        return mat

    # Approved T24 film surfaces (export config of the scene-expansion film) and hamburger hand surfaces.
    counter = material("Warm wood counter", (0.63, 0.55, 0.43), 0, 0.65,
                       {"scale": 1000, "strength": 0.08, "distance": 2.5e-05})
    legs = material("Dark counter legs", (0.25, 0.23, 0.21), 0, 0.6)
    floor = material("Studio floor", (0.69, 0.70, 0.68), 0, 0.82)
    shell = material("Studio ceramic white shell", (0.9, 0.92, 0.92), 0, 0.24)
    rubber = material("Studio forest elastomer", (0.22, 0.29, 0.25), 0, 0.65)
    satin = {"scale": 3200, "strength": 0.08, "distance": 1.2e-05}
    objects, audit = [], []
    arm_materials = {}
    for record in payload["geoms"]:
        name, kind, size = record["name"], record["kind"], record["size"]
        if kind == 7:
            source = payload["meshes"][str(record["mesh"])]
            mesh = bpy.data.meshes.new(source["name"])
            mesh.from_pydata(geometry[source["prefix"] + "vertices"].tolist(), [],
                             geometry[source["prefix"] + "faces"].tolist())
            mesh.update()
            for polygon in mesh.polygons:
                polygon.use_smooth = True
            obj = bpy.data.objects.new(name, mesh)
            scene.collection.objects.link(obj)
        elif kind in (0, 6):
            bpy.ops.mesh.primitive_cube_add(size=2)
            obj = bpy.context.object
            obj.data.transform(Matrix.Diagonal((*(size if kind == 6 else [6, 6, 0.001]), 1)))
        elif kind == 5:
            bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=size[0], depth=2 * size[1])
            obj = bpy.context.object
        elif kind in (2, 4):
            bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=1)
            obj = bpy.context.object
            obj.data.transform(Matrix.Diagonal((*(size if kind == 4 else [size[0]] * 3), 1)))
            for p in obj.data.polygons:
                p.use_smooth = True
        elif kind == 3:
            r, half = size[:2]
            vertices, faces = [], []
            rings = [(math.pi * j / 16, half) for j in range(9)] + [(math.pi * j / 16, -half) for j in range(8, 17)]
            for angle, offset in rings:
                for k in range(24):
                    a = 2 * math.pi * k / 24
                    vertices.append((r * math.sin(angle) * math.cos(a), r * math.sin(angle) * math.sin(a),
                                     r * math.cos(angle) + offset))
            for j in range(len(rings) - 1):
                for k in range(24):
                    a, b = j * 24 + k, j * 24 + (k + 1) % 24
                    faces.append((a, b, b + 24, a + 24))
            mesh = bpy.data.meshes.new(name)
            mesh.from_pydata(vertices, [], faces)
            obj = bpy.data.objects.new(name, mesh)
            scene.collection.objects.link(obj)
            for p in mesh.polygons:
                p.use_smooth = True
        else:
            raise ValueError(f"Unsupported geometry {kind}")
        obj.name = name
        bevel = 0.0
        if record["owner"] == "hand" or (record["owner"] == "robot" and name.startswith("left_")):
            chosen = rubber if record["material"] == "green" else shell
        elif record["owner"] == "robot":
            # Tianji Marvin stand/arms: the native factory rgba per sub-mesh (accepted arm films: roughness 0.29,
            # metallic 0.15).
            key = tuple(round(float(v), 3) for v in record["rgba"][:3])
            if key not in arm_materials:
                arm_materials[key] = material("Marvin " + "/".join(map(str, key)), record["rgba"], 0.15, 0.29)
            chosen = arm_materials[key]
        elif name == "counter":
            chosen, bevel = counter, 0.002
        elif name.startswith("leg_"):
            chosen = legs
        elif name == "floor":
            chosen = floor
        elif record["pbr"]:
            pbr = record["pbr"]
            dark = record["material"] in ("usb_black", "usb_pvc")
            chosen = material("USB " + record["material"], pbr["rgba"], max(0.0, pbr["metallic"]),
                              0.48 if dark else pbr["roughness"], satin if dark else None)
            if kind == 6 and min(size) > 0.0012:
                bevel = 0.0004
        else:
            chosen = material("Primitive " + name, record["rgba"], 0, 0.4)
        obj.data.materials.clear()
        obj.data.materials.append(chosen)
        if bevel > 0:
            mod = obj.modifiers.new("Presentation edge rounding", "BEVEL")
            mod.width, mod.segments = bevel, 3
            obj.modifiers.new("Weighted surface normals", "WEIGHTED_NORMAL")
        objects.append((obj, record["id"]))
        audit.append({"geom": name, "native_geom_id": record["id"], "bevel_m": bevel, "material": chosen.name})

    light_target = Vector((0.70, -0.06, 0.72))

    def area(name, offset, energy, size, color):
        data = bpy.data.lights.new(name, "AREA")
        data.energy, data.shape, data.size, data.color = energy, "DISK", size, color
        obj = bpy.data.objects.new(name, data)
        scene.collection.objects.link(obj)
        obj.location = light_target + Vector(offset)
        obj.rotation_euler = (light_target - obj.location).to_track_quat("-Z", "Y").to_euler()

    # The approved film's softbox layout (offsets from the target), scaled to this wider set.
    area("Key softbox", (-0.45, -0.30, 0.70), 40, 0.7, (1, 0.92, 0.82))
    area("Cool fill", (0.20, 0.45, 0.42), 18, 0.55, (0.8, 0.9, 1))
    area("Top edge light", (-0.20, 0.12, 0.70), 22, 0.4, (1, 1, 1))
    area("Front fill", (0.15, -0.70, 0.35), 10, 0.6, (1, 0.97, 0.92))
    data = bpy.data.cameras.new("Presentation camera")
    camera = bpy.data.objects.new("Presentation camera", data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    data.clip_start, data.clip_end = 0.002, 20
    frames = payload["frames"]
    if args.only:
        indices = [int(v) for v in args.only.split(",")]
    else:
        indices = list(range(0, len(frames), args.frame_step))
        if indices[-1] != len(frames) - 1:
            indices.append(len(frames) - 1)
    id_index = {g["id"]: i for i, g in enumerate(payload["geoms"])}
    # Cut to the port close-up once the plug is carried in front of the desk edge (purposeful cut, no motion edit).
    cut = next((i for i, f in enumerate(frames) if f["plug_pos"][1] < -0.14 and f["plug_pos"][2] < 0.73), len(frames))
    measurements = []
    for index in indices:
        shot = CLOSE if index >= cut else WIDE
        camera.location = Vector(shot["position"])
        camera.rotation_euler = (Vector(shot["target"]) - camera.location).to_track_quat("-Z", "Y").to_euler()
        data.lens = shot["lens"]
        for obj, gid in objects:
            j = id_index[gid]
            matrix = Matrix(pose_rotations[index, j].tolist()).to_4x4()
            matrix.translation = Vector(pose_positions[index, j].tolist())
            obj.matrix_world = matrix
        started = time.monotonic()
        scene.render.filepath = str(frame_dir / f"{index:06d}.png")
        bpy.ops.render.render(write_still=True)
        measurements.append({"frame": index, "native_step": frames[index]["step"],
                             "seconds": round(time.monotonic() - started, 3)})
        print("FRAME " + json.dumps(measurements[-1]), flush=True)
    settings = {
        "renderer_source_sha256": sha(__file__),
        "export_sha256": sha(args.export / "scene.json"),
        "engine": "Cycles OptiX" if args.engine == "cycles" else "Eevee Next / ray tracing",
        "samples": args.samples,
        "width": 1280,
        "height": 720,
        "appearance_only": True,
        "native_pose_interpolation": False,
        "video_fps": payload["fps"] / args.frame_step,
        "playback_speed": payload["playback_speed"] * args.frame_step,
        "native_controls_per_rendered_frame": payload["stride"] * args.frame_step,
        "camera_cut_frame": cut,
        "cameras": {"wide": WIDE, "close": CLOSE},
        "materials_and_bevels": audit,
        "indices": indices,
        "measurements": measurements,
        "blender_version": bpy.app.version_string,
    }
    (frame_dir / "render.json").write_text(json.dumps(settings, indent=1) + "\n")


if __name__ == "__main__":
    main()
