#!/usr/bin/env python3
"""Authoring-only Blender studio renderer for the picture_hang PR film (never copied into a task).

Copied from the approved T21 scene film's renderer
(scripts/scene_expansion/repairs/picture_sharpa/meta_delivery_trajectory_r1/studio_renderer.py) so the materials,
lighting, colour management and cameras are the approved scene's. Changes: the caption names the hands and says
"physics replay, N x" with the native verdict (PASS / IN PROGRESS / FAIL), the footer names the checker stage, and the
final rendered state is held for ``--final-hold`` seconds. Every rendered pose is a saved MuJoCo state of the physical
actuator replay (tools/presentation.py export); no motion is interpolated and no dynamics is run here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
DEFAULT_BLENDER = "blender"  # Blender 4.5.3 LTS; set DEXHAND_BLENDER or --blender
ROLE_NAMES = {
    "1": "base_color",
    "2": "occlusion",
    "3": "roughness",
    "4": "metallic",
    "5": "normal",
    "6": "opacity",
    "7": "emissive",
    "8": "base_color",
    "9": "orm",
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_bundle(directory):
    directory = Path(directory).resolve()
    manifest = directory / "scene.json"
    scene = json.loads(manifest.read_text())
    mode = scene.get("evidence_type", scene.get("validation_mode"))
    if mode not in (
        "kinematic_demo",
        "physical_actuator_replay",
        "meta_actions",
        "robot_controls",
    ):
        raise ValueError("Declare kinematic_demo or a truthful native execution mode")
    if scene.get("scripted_object_motion", False) and mode != "kinematic_demo":
        raise ValueError("Prescribed object motion must be labelled kinematic_demo")
    if mode == "kinematic_demo" and not scene.get("prescribed_quantities"):
        raise ValueError("Describe the prescribed transforms/joints/deformations")
    if not scene.get("frames"):
        raise ValueError("At least one saved timestamped frame is required")
    for relative, expected in scene["files"].items():
        path = (directory / relative).resolve()
        if directory not in path.parents or sha(path) != expected:
            raise ValueError(f"Export file failed integrity check: {relative}")
    return scene


def linear_rgb(color):
    return tuple(
        v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in color[:3]
    )


def inside_blender(args):
    import bpy
    import numpy as np
    from mathutils import Matrix, Vector

    directory, output = args.export.resolve(), args.output.resolve()
    payload = load_bundle(directory)
    geometry = np.load(directory / "geometry.npz", allow_pickle=False)
    poses = np.load(directory / "poses.npz", allow_pickle=False)
    config = payload.get("config", {})
    deformation_file = directory / "deformations.npz"
    deformations = (
        np.load(deformation_file, allow_pickle=False)
        if deformation_file.exists()
        else None
    )
    if poses["positions"].shape != (len(payload["frames"]), len(payload["geoms"]), 3):
        raise ValueError("positions must have shape [saved frames, geoms,3]")
    if poses["rotations"].shape != (
        len(payload["frames"]),
        len(payload["geoms"]),
        3,
        3,
    ):
        raise ValueError("rotations must have shape [saved frames,geoms,3,3]")
    if not all(np.isfinite(poses[k]).all() for k in ("positions", "rotations")):
        raise ValueError("Saved transforms must be finite")
    frames_dir = output.with_suffix("").with_name(output.stem + "-frames")
    frames_dir.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene
    prefs = None
    scene.render.engine = "CYCLES" if args.engine == "cycles" else "BLENDER_EEVEE_NEXT"
    if args.engine == "cycles":
        scene.cycles.samples = args.samples
        scene.cycles.use_adaptive_sampling = True
        scene.cycles.use_denoising = True
        scene.cycles.denoiser = "OPENIMAGEDENOISE"
        scene.cycles.denoising_use_gpu = True
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "OPTIX"
        prefs.get_devices()
        for device in prefs.devices:
            device.use = device.type == "OPTIX"
        if not any(d.use for d in prefs.devices):
            raise RuntimeError("An OptiX GPU is required for this authoring render")
        scene.cycles.device = "GPU"
    elif hasattr(scene.eevee, "taa_render_samples"):
        scene.eevee.taa_render_samples = args.samples
    scene.render.resolution_x, scene.render.resolution_y = args.width, args.height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = config.get("exposure", -0.7)
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes["Background"]
    background.inputs["Color"].default_value = (0.72, 0.75, 0.77, 1)
    background.inputs["Strength"].default_value = 0.45
    material_cache, mesh_cache = {}, {}

    def material(
        name,
        rgba,
        metallic=0,
        roughness=0.3,
        textures=None,
        normal_strength=1,
        transmission=0,
        ior=1.45,
        coat=0,
        bump=None,
    ):
        if name in material_cache:
            return material_cache[name]
        result = bpy.data.materials.new(name)
        result.use_nodes = True
        nodes, links = result.node_tree.nodes, result.node_tree.links
        bsdf = nodes.get("Principled BSDF")
        bsdf.inputs["Base Color"].default_value = (*linear_rgb(rgba), rgba[3])
        bsdf.inputs["Alpha"].default_value = rgba[3]
        bsdf.inputs["Metallic"].default_value = metallic
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Transmission Weight"].default_value = transmission
        bsdf.inputs["IOR"].default_value = ior
        bsdf.inputs["Coat Weight"].default_value = coat
        if bump:
            coordinates = nodes.new("ShaderNodeTexCoord")
            noise = nodes.new("ShaderNodeTexNoise")
            noise.inputs["Scale"].default_value = bump.get("scale", 3000)
            noise.inputs["Detail"].default_value = 2
            links.new(coordinates.outputs["Object"], noise.inputs["Vector"])
            micro = nodes.new("ShaderNodeBump")
            micro.inputs["Strength"].default_value = bump.get("strength", 0.12)
            micro.inputs["Distance"].default_value = bump.get("distance", 0.000025)
            links.new(noise.outputs["Fac"], micro.inputs["Height"])
            links.new(micro.outputs["Normal"], bsdf.inputs["Normal"])
        for role, filename in (textures or {}).items():
            role = ROLE_NAMES.get(role, role)
            texture = nodes.new("ShaderNodeTexImage")
            texture.image = bpy.data.images.load(
                str(directory / filename), check_existing=True
            )
            texture.interpolation = "Linear"
            if role not in ("base_color", "emissive"):
                texture.image.colorspace_settings.name = "Non-Color"
            if role == "base_color":
                links.new(texture.outputs["Color"], bsdf.inputs["Base Color"])
            elif role in ("metallic", "roughness", "opacity"):
                links.new(
                    texture.outputs["Color"],
                    bsdf.inputs[
                        {
                            "metallic": "Metallic",
                            "roughness": "Roughness",
                            "opacity": "Alpha",
                        }[role]
                    ],
                )
            elif role == "normal":
                normal = nodes.new("ShaderNodeNormalMap")
                normal.inputs["Strength"].default_value = normal_strength
                links.new(texture.outputs["Color"], normal.inputs["Color"])
                links.new(normal.outputs["Normal"], bsdf.inputs["Normal"])
            elif role == "orm":
                separate = nodes.new("ShaderNodeSeparateColor")
                links.new(texture.outputs["Color"], separate.inputs["Color"])
                links.new(separate.outputs["Green"], bsdf.inputs["Roughness"])
                links.new(separate.outputs["Blue"], bsdf.inputs["Metallic"])
            elif role == "emissive":
                links.new(texture.outputs["Color"], bsdf.inputs["Emission Color"])
                bsdf.inputs["Emission Strength"].default_value = 1
        material_cache[name] = result
        return result

    shell = material("Studio ceramic white shell", (0.9, 0.92, 0.92, 1), 0, 0.24)
    rubber = material("Studio forest elastomer", (0.22, 0.29, 0.25, 1), 0, 0.65)
    surface = material("Studio warm gray surface", (0.72, 0.73, 0.71, 1), 0, 0.75)
    materials = [
        material(
            f"Native {mid}: {m['name']}",
            m["rgba"],
            max(0, m.get("metallic", 0)),
            m["roughness"] if m.get("roughness", -1) >= 0 else 0.35,
            m.get("textures"),
            m.get("normal_strength", 1),
        )
        for mid, m in enumerate(payload["materials"])
    ]
    objects, geometry_audit = [], []
    for geom in payload["geoms"]:
        kind, size = geom["kind"], geom["size"]
        if kind == 7:
            mesh_id = str(geom["mesh"])
            if mesh_id not in mesh_cache:
                record = payload["meshes"][mesh_id]
                prefix = record["prefix"]
                vertices, faces = (
                    geometry[prefix + "vertices"],
                    geometry[prefix + "faces"],
                )
                mesh = bpy.data.meshes.new(record["name"] or mesh_id)
                mesh.from_pydata(vertices.tolist(), [], faces.tolist())
                mesh.update()
                for polygon in mesh.polygons:
                    polygon.use_smooth = not geom.get("authored_cad", False)
                normals, face_normals = (
                    geometry[prefix + "normals"],
                    geometry[prefix + "face_normals"],
                )
                if (
                    len(normals)
                    and len(face_normals)
                    and face_normals.min() >= 0
                    and not geom["is_hand"]
                    and not geom.get("authored_cad", False)
                ):
                    mesh.normals_split_custom_set(
                        normals[face_normals.reshape(-1)].tolist()
                    )
                if record["has_uv"]:
                    uv, face_uv = geometry[prefix + "uv"], geometry[prefix + "face_uv"]
                    layer = mesh.uv_layers.new(name="Native UV")
                    if face_uv.min() < 0:
                        raise ValueError(
                            f"A textured visual mesh has missing UV corners: {record['name']}"
                        )
                    for loop, coordinates in zip(layer.data, uv[face_uv.reshape(-1)]):
                        # The MuJoCo OBJ compiler stores V as 1-original_v.
                        # Restore the source convention used by Blender / PNG.
                        loop.uv = (
                            coordinates[0],
                            1 - coordinates[1]
                            if record.get("uv_flip_v", True)
                            else coordinates[1],
                        )
                mesh_cache[mesh_id] = mesh
            # Per-object material slots must not leak onto other instances of a mesh.
            obj = bpy.data.objects.new(geom["name"], mesh_cache[mesh_id].copy())
            scene.collection.objects.link(obj)
        elif kind in (0, 6):
            bpy.ops.mesh.primitive_cube_add(size=2)
            obj = bpy.context.object
            obj.scale = size if kind == 6 else [2, 2, 0.001]
            if geom["name"] == "table":
                obj.scale = [2, 2, size[2]]
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
            bevel = config.get("visual_bevel_m", 0.00025)
            if geom["name"] != "table" and kind != 0 and bevel:
                modifier = obj.modifiers.new("Visual edge finish", "BEVEL")
                modifier.width, modifier.segments = min(bevel, min(size) * 0.3), 3
                obj.modifiers.new("Surface normals", "WEIGHTED_NORMAL")
        elif kind in (2, 3, 4):
            if kind == 3:
                # Capsule: a cylinder plus hemispheres built as a single smooth mesh.
                r, half = size[:2]
                vertices, faces = [], []
                rings = [(math.pi * ring / 32, half) for ring in range(17)]
                rings += [(math.pi * ring / 32, -half) for ring in range(16, 33)]
                for angle, offset in rings:
                    z = r * math.cos(angle) + offset
                    radial = r * math.sin(angle)
                    for j in range(64):
                        a = 2 * math.pi * j / 64
                        vertices.append((radial * math.cos(a), radial * math.sin(a), z))
                for ring in range(len(rings) - 1):
                    for j in range(64):
                        a, b = ring * 64 + j, ring * 64 + (j + 1) % 64
                        faces.append((a, b, b + 64, a + 64))
                mesh = bpy.data.meshes.new(geom["name"])
                mesh.from_pydata(vertices, [], faces)
                obj = bpy.data.objects.new(geom["name"], mesh)
                scene.collection.objects.link(obj)
            else:
                bpy.ops.mesh.primitive_uv_sphere_add(
                    segments=64, ring_count=32, radius=1
                )
                obj = bpy.context.object
                obj.scale = [size[0]] * 3 if kind == 2 else size
            for polygon in obj.data.polygons:
                polygon.use_smooth = True
        elif kind == 5:
            bpy.ops.mesh.primitive_cylinder_add(
                vertices=96, radius=size[0], depth=2 * size[1]
            )
            obj = bpy.context.object
            for polygon in obj.data.polygons:
                polygon.use_smooth = len(polygon.vertices) == 4
        else:
            raise ValueError(f"Unsupported visible geometry: {kind}")
        # Baked geometry must retain its physical size when the exact rotation /
        # translation matrix replaces matrix_world at each sampled frame.
        if any(abs(value - 1) > 1e-10 for value in obj.scale):
            obj.data.transform(Matrix.Diagonal((*obj.scale, 1)))
            obj.scale = (1, 1, 1)
        actual_extent = np.max(
            np.abs(np.asarray([tuple(v.co) for v in obj.data.vertices])), axis=0
        )
        if kind == 7:
            expected_extent = np.max(
                np.abs(
                    geometry[
                        payload["meshes"][str(geom["mesh"])]["prefix"] + "vertices"
                    ]
                ),
                axis=0,
            )
        elif kind == 2:
            expected_extent = np.full(3, size[0])
        elif kind == 3:
            expected_extent = np.asarray([size[0], size[0], size[0] + size[1]])
        elif kind == 5:
            expected_extent = np.asarray([size[0], size[0], size[1]])
        else:
            expected_extent = np.asarray(size)
        studio_floor = geom["name"] == "table" or kind == 0
        matches = bool(
            np.allclose(actual_extent, expected_extent, atol=1e-7, rtol=1e-6)
        )
        if not studio_floor and not matches:
            raise ValueError(
                f"The rendered local geometry size differs from MuJoCo: {geom['name']}"
            )
        geometry_audit.append(
            {
                "name": geom["name"],
                "matches_native_size": matches,
                "studio_floor_extension": studio_floor,
                "native_half_extent": expected_extent.tolist(),
                "render_half_extent": actual_extent.tolist(),
            }
        )
        obj.name = geom["name"]
        mid = geom["material"]
        if "visual_material" in geom:
            override = geom["visual_material"]
            chosen = material(
                f"Presentation {geom['name']}",
                override.get("rgba", geom["rgba"]),
                override.get("metallic", 0),
                override.get("roughness", 0.3),
                override.get("textures"),
                override.get("normal_strength", 1),
                override.get("transmission", 0),
                override.get("ior", 1.45),
                override.get("coat", 0),
                override.get("bump"),
            )
        elif geom["is_hand"]:
            native_name = payload["materials"][mid]["name"] if mid >= 0 else ""
            chosen = rubber if native_name == "green" else shell
        elif geom["name"] == "table" or kind == 0:
            chosen = surface
        elif mid >= 0:
            chosen = materials[mid]
        else:
            chosen = material(
                f"Primitive {geom['rgba']}",
                geom["rgba"],
                0,
                0.28 if "sticker" in geom["name"] else 0.38,
            )
        obj.data.materials.clear()
        obj.data.materials.append(chosen)
        objects.append(obj)

    initial = poses["positions"][0]
    subject = [
        initial[i]
        for i, geom in enumerate(payload["geoms"])
        if geom["name"] != "table" and geom["kind"] != 0
    ]
    center = np.mean(subject, axis=0)
    camera_config = config.get("camera", {})
    target = Vector(camera_config.get("target", center.tolist()))
    if "position" in camera_config:
        position = camera_config["position"]
    else:
        az = math.radians(camera_config.get("azimuth", 45))
        elevation = math.radians(-camera_config.get("elevation", -40))
        distance = camera_config.get("distance", 0.38)
        # MuJoCo's azimuth points the viewing direction, opposite camera position.
        position = (
            target
            + Vector(
                (
                    -math.cos(az) * math.cos(elevation),
                    -math.sin(az) * math.cos(elevation),
                    math.sin(elevation),
                )
            )
            * distance
        )
    camera_data = bpy.data.cameras.new("Fixed presentation camera")
    camera = bpy.data.objects.new("Fixed presentation camera", camera_data)
    scene.collection.objects.link(camera)
    camera.location = position
    camera.rotation_euler = (
        (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    )
    camera_data.lens, camera_data.clip_start, camera_data.clip_end = (
        camera_config.get("lens", 52),
        0.001,
        20,
    )
    scene.camera = camera
    scene.cycles.use_persistent_data = True
    default_lights = [
        ("Key softbox", (-0.3, -0.18, 0.44), 12, 0.45, (1, 0.92, 0.82)),
        ("Cool fill", (0.10, 0.28, 0.26), 6, 0.35, (0.8, 0.9, 1)),
        ("Top edge light", (-0.13, 0.08, 0.44), 7, 0.25, (1, 1, 1)),
    ]
    lights = (
        [
            (v["name"], v["offset"], v["energy"], v["size"], v["color"])
            for v in config["lights"]
        ]
        if "lights" in config
        else default_lights
    )
    for name, offset, energy, size, color in lights:
        light_data = bpy.data.lights.new(name, "AREA")
        light_data.energy, light_data.shape, light_data.size, light_data.color = (
            energy,
            "DISK",
            size,
            color,
        )
        light = bpy.data.objects.new(name, light_data)
        scene.collection.objects.link(light)
        light_target = Vector(config.get("light_target", list(target)))
        light.location = light_target + Vector(offset)
        light.rotation_euler = (
            (light_target - light.location).to_track_quat("-Z", "Y").to_euler()
        )
    indices = (
        [args.frame_start]
        if args.still
        else list(range(args.frame_start, len(payload["frames"])))
    )
    if args.limit:
        indices = indices[: args.limit]
    if not indices or indices[0] >= len(payload["frames"]):
        raise ValueError("Frame selection is empty or outside the saved trajectory")
    settings = {
        "manifest_sha256": sha(directory / "scene.json"),
        "renderer_source_sha256": sha(__file__),
        "width": args.width,
        "height": args.height,
        "samples": args.samples,
        "engine": args.engine,
        "camera_position": list(camera.location),
        "camera_target": list(target),
        "camera_lens": camera_data.lens,
    }
    cache_path = frames_dir / "settings.json"
    cached = json.loads(cache_path.read_text()) if cache_path.exists() else None
    reuse = args.resume and cached == settings
    cache_path.write_text(json.dumps(settings, indent=2) + "\n")
    metrics = []
    for index in indices:
        image_path = frames_dir / f"{index:06d}.png"
        if reuse and image_path.is_file():
            continue
        for geom, obj, position, rotation in zip(
            payload["geoms"],
            objects,
            poses["positions"][index],
            poses["rotations"][index],
        ):
            if geom.get("deformation_key"):
                if deformations is None:
                    raise ValueError("Missing declared deformations.npz")
                vertices = deformations[geom["deformation_key"]][index]
                if (
                    vertices.shape != (len(obj.data.vertices), 3)
                    or not np.isfinite(vertices).all()
                ):
                    raise ValueError(
                        "Finite fixed-topology local vertices are required"
                    )
                obj.data.vertices.foreach_set("co", vertices.astype(float).ravel())
                obj.data.update()
            matrix = Matrix(rotation).to_4x4()
            matrix.translation = Vector(position)
            obj.matrix_world = matrix
        if config.get("camera_tracking_pot"):
            tracked = Vector(poses["pot_positions"][index]) + Vector(
                config.get("camera_target_offset", [0, 0, 0.13])
            )
            delta = tracked - target
            camera.location = Vector(settings["camera_position"]) + delta
            camera.rotation_euler = (
                (tracked - camera.location).to_track_quat("-Z", "Y").to_euler()
            )
        if config.get("camera_frames"):
            shot = config["camera_frames"][index]
            camera.location = Vector(shot["position"])
            camera_data.lens = shot.get("lens", camera_config.get("lens", 52))
            camera.rotation_euler = (Vector(shot["target"])-camera.location).to_track_quat("-Z", "Y").to_euler()
        started = time.monotonic()
        scene.render.filepath = str(image_path)
        bpy.ops.render.render(write_still=True)
        metrics.append(
            {
                "frame": index,
                "step": payload["frames"][index].get("step", index),
                "elapsed_s": time.monotonic() - started,
            }
        )
        print("FRAME " + json.dumps(metrics[-1]), flush=True)
    (frames_dir / "render-metrics.json").write_text(
        json.dumps(
            {
                "blender_version": bpy.app.version_string,
                "devices": [
                    {"name": d.name, "type": d.type, "used": bool(d.use)}
                    for d in prefs.devices
                ]
                if prefs
                else [],
                "engine": args.engine,
                "evidence_type": payload.get("evidence_type"),
                "rendered_indices": indices,
                "settings": settings,
                "measurements": metrics,
                "geometry_audit": geometry_audit,
            },
            indent=2,
        )
        + "\n"
    )


def encode(args):
    import imageio.v2 as imageio
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

    payload = load_bundle(args.export)
    output = args.output.resolve()
    frames_dir = output.with_suffix("").with_name(output.stem + "-frames")
    scale = args.width / 1280
    font = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", round(18 * scale)
    )
    small = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", round(15 * scale)
    )

    def card(index):
        frame = payload["frames"][index]
        pic = Image.open(frames_dir / f"{index:06d}.png").convert("RGB")
        draw = ImageDraw.Draw(pic)
        status = frame.get("status", {"stage": 0, "success": False})
        stage = status["stage"]
        verdict = (
            "PASS"
            if status["success"]
            else "FAIL: " + str(status.get("reason", ""))
            if status.get("failed", False)
            else "IN PROGRESS"
        )
        title = payload.get("config", {}).get("display_title", payload["title"])
        hand_label = payload.get("hand_label", "")
        detail = (f"{hand_label} · {verdict} · t = {frame['time_s']:.2f} s · "
                  f"physics replay, {payload['playback_speed']:g}x")
        width = (
            max(draw.textlength(title, font=font), draw.textlength(detail, font=small))
            + 28 * scale
        )
        x, y = 20 * scale, 18 * scale
        draw.rounded_rectangle(
            (x, y, x + width, y + 57 * scale), radius=7 * scale, fill=(245, 244, 237)
        )
        draw.text((x + 12 * scale, y + 7 * scale), title, font=font, fill=(35, 45, 40))
        draw.text(
            (x + 12 * scale, y + 32 * scale),
            detail,
            font=small,
            fill=(61, 104, 75) if status["success"] else (90, 94, 88),
        )
        stage_label = (
            payload["stage_names"][stage].replace("_", " ")
            if stage < len(payload["stage_names"])
            else "terminal hold"
        )
        footer = f"{stage_label} | motor targets only, objects move by contact and gravity"
        footer_width = draw.textlength(footer, font=small) + 20 * scale
        bottom = args.height - 18 * scale
        draw.rounded_rectangle(
            (x, bottom - 28 * scale, x + footer_width, bottom),
            radius=4 * scale,
            fill=(245, 244, 237),
        )
        draw.text(
            (x + 10 * scale, bottom - 22 * scale), footer, font=small, fill=(90, 94, 88)
        )
        return np.asarray(pic)

    if args.still:
        Image.fromarray(card(args.frame_start)).save(output.with_suffix(".png"))
        return
    with imageio.get_writer(
        output,
        fps=args.fps,
        codec="libx264",
        macro_block_size=1,
        pixelformat="yuv420p",
        ffmpeg_params=["-crf", "17", "-preset", "fast", "-movflags", "+faststart"],
    ) as writer:
        for index in list(range(args.frame_start, len(payload["frames"])))[
            : args.limit or None
        ]:
            frame = card(index)
            writer.append_data(frame)
            if index == 0:
                Image.fromarray(frame).save(output.with_suffix(".png"))
        # The episode ends at success; the last saved state (the released, hanging frame) is shown for a moment.
        for _ in range(round(args.final_hold * args.fps)):
            writer.append_data(frame)
    metrics = json.loads((frames_dir / "render-metrics.json").read_text())
    result = {
        key: payload.get(key)
        for key in [
            "task",
            "evidence_type",
            "scripted_object_motion",
            "status",
            "initial_sha",
            "final_features",
            "instance_spec_sha256",
            "model_xml_sha256",
            "trajectory_sha256",
            "timeline",
            "physics_control_steps_per_video_frame",
            "playback_speed",
            "probe_only",
        ]
    }
    result.update(
        renderer="Blender " + args.engine,
        renderer_version=metrics["blender_version"],
        video_sha256=sha(output),
        video_frames=len(metrics["rendered_indices"]),
        video_fps=args.fps,
        pose_export_manifest_sha256=sha(args.export / "scene.json"),
        pose_data_sha256=sha(args.export / "poses.npz"),
        geometry_sha256=sha(args.export / "geometry.npz"),
        sampled_state_sha256=[fr.get("state_sha") for fr in payload["frames"]],
        presentation_config_sha256=payload.get("presentation_config_sha256"),
        prescribed_quantities=payload.get("prescribed_quantities", []),
        physics_claims=payload.get("physics_claims", []),
        render=metrics,
    )
    result["source_bundle_sha256"] = payload.get("source_bundle_sha256")
    output.with_suffix(".json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                "task": payload["task"],
                "status": payload["status"],
                "video": str(output),
                "probe_only": payload["probe_only"],
            }
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--blender", default=os.environ.get("DEXHAND_BLENDER", DEFAULT_BLENDER)
    )
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--samples", type=int, default=16)
    parser.add_argument("--engine", choices=["cycles", "eevee"], default="cycles")
    parser.add_argument("--fps", type=int, default=20)
    parser.add_argument("--frame-start", type=int, default=0)
    parser.add_argument(
        "--limit", type=int, default=0, help="Pilot only: cap rendered saved frames"
    )
    parser.add_argument("--still", action="store_true")
    parser.add_argument("--final-hold", type=float, default=0.0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--frames-only", action="store_true")
    parser.add_argument("--inside-blender", action="store_true", help=argparse.SUPPRESS)
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]
    args = parser.parse_args(argv)
    if (
        args.width < 64
        or args.height < 64
        or args.width % 2
        or args.height % 2
        or args.samples < 1
    ):
        parser.error("Dimensions must be even and >=64, and samples must be positive")
    args.export = args.export.resolve()
    args.output = args.output.resolve()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.inside_blender:
        inside_blender(args)
        return
    load_bundle(args.export)
    binary = shutil.which(args.blender) or (
        args.blender if Path(args.blender).is_file() else None
    )
    if not binary:
        parser.error(
            "Blender is required for authoring films; set --blender or DEXHAND_BLENDER"
        )
    log = args.output.with_suffix(".render.log")
    with log.open("w") as stream:
        subprocess.run(
            [
                binary,
                "-b",
                "-t",
                "1",
                "-P",
                str(Path(__file__).resolve()),
                "--",
                *argv,
                "--inside-blender",
            ],
            stdout=stream,
            stderr=subprocess.STDOUT,
            check=True,
            env={
                **os.environ,
                "OPENBLAS_NUM_THREADS": "1",
                "OMP_NUM_THREADS": "1",
            },
        )
    if not args.frames_only:
        encode(args)


if __name__ == "__main__":
    main()
