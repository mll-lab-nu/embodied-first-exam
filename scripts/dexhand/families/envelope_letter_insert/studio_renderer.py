"""Blender studio look for the envelope-letter film on exact native poses (authoring only, not shipped).

Materials, camera path and lighting follow the approved T38 scene film (paper whites, blue-grey open flap, warm wood
desk, window daylight / fill / paper rim lights, camera from the overview towards the mouth). Only appearance differs
from the native preview; every object pose comes from the MuJoCo replay.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import time


FLIP_V = True


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    import bpy
    import numpy as np
    from mathutils import Matrix, Vector

    parser = argparse.ArgumentParser()
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=16)
    parser.add_argument("--frame-step", type=int, default=1)
    parser.add_argument("--engine", choices=["cycles", "eevee"], default="eevee")
    parser.add_argument("--still", type=int)
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
    if args.engine == "eevee":
        scene.render.engine = "BLENDER_EEVEE_NEXT"
        scene.eevee.taa_render_samples = max(args.samples, 16)
        scene.eevee.use_shadows = True
        if hasattr(scene.eevee, "use_raytracing"):
            scene.eevee.use_raytracing = False
    else:
        scene.render.engine = "CYCLES"
        scene.cycles.samples = args.samples
        scene.cycles.use_denoising = True
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "OPTIX"
        prefs.get_devices()
        for device in prefs.devices:
            device.use = device.type == "OPTIX"
        scene.cycles.device = "GPU"
    scene.render.resolution_x, scene.render.resolution_y = 1280, 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -1.3
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.62, 0.64, 0.61, 1)
    bg.inputs["Strength"].default_value = 0.35

    def linear(rgb):
        return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb)

    def material(name, color, roughness=0.5, metallic=0.0, coat=0.0, sss=0.0):
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes["Principled BSDF"]
        bsdf.inputs["Base Color"].default_value = (*linear(color), 1)
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
        bsdf.inputs["Coat Weight"].default_value = coat
        bsdf.inputs["Subsurface Weight"].default_value = sss
        bsdf.inputs["Subsurface Scale"].default_value = 0.001
        return mat

    def bump(mat, scale, distance, strength):
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        coord = nodes.new("ShaderNodeTexCoord")
        tex = nodes.new("ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = scale
        tex.inputs["Detail"].default_value = 4
        links.new(coord.outputs["Object"], tex.inputs["Vector"])
        node = nodes.new("ShaderNodeBump")
        node.inputs["Distance"].default_value = distance
        node.inputs["Strength"].default_value = strength
        links.new(tex.outputs["Fac"], node.inputs["Height"])
        links.new(node.outputs["Normal"], nodes["Principled BSDF"].inputs["Normal"])
        return tex

    def wood(name):
        mat = material(name, (0.62, 0.42, 0.26), 0.5, coat=0.08)
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        coord = nodes.new("ShaderNodeTexCoord")
        mapping = nodes.new("ShaderNodeMapping")
        mapping.inputs["Scale"].default_value = (1.0, 14.0, 1.0)
        tex = nodes.new("ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = 6.0
        tex.inputs["Detail"].default_value = 6
        tex.inputs["Distortion"].default_value = 2.0
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].position = 0.35
        ramp.color_ramp.elements[0].color = (*linear((0.50, 0.33, 0.20)), 1)
        ramp.color_ramp.elements[1].position = 0.75
        ramp.color_ramp.elements[1].color = (*linear((0.64, 0.45, 0.29)), 1)
        links.new(coord.outputs["Object"], mapping.inputs["Vector"])
        links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
        links.new(tex.outputs["Fac"], ramp.inputs[0])
        links.new(ramp.outputs["Color"], nodes["Principled BSDF"].inputs["Base Color"])
        return mat

    arm_materials = {}
    shell = material("Pearl white polymer housing", (0.89, 0.91, 0.89), 0.30, 0.08)
    rubber = material("Green silicone fingertips", (0.18, 0.62, 0.30), 0.62)
    steel = material("Brushed stainless mechanics", (0.36, 0.39, 0.41), 0.30, 0.8)
    wuji_shell = material("Wuji lavender housing", (0.55, 0.48, 0.70), 0.38, 0.05)
    envelope = material("Cool white envelope paper", (0.965, 0.967, 0.947), 0.82, sss=0.05)
    bump(envelope, 900.0, 0.00002, 0.12)
    flap = material("Open flap gummed paper", (0.79, 0.85, 0.86), 0.78)
    bump(flap, 900.0, 0.00002, 0.12)
    band = material("Glue band paper", (0.90, 0.90, 0.87), 0.8)
    paper = material("Ivory letter paper", (0.99, 0.98, 0.94), 0.80, sss=0.05)
    bump(paper, 900.0, 0.00002, 0.10)
    printed = material("Printed letterhead", (1, 1, 1), 0.78)
    image = bpy.data.images.load(str((args.export / "letter.png").resolve()))
    nodes, links = printed.node_tree.nodes, printed.node_tree.links
    texture = nodes.new("ShaderNodeTexImage")
    texture.image = image
    links.new(texture.outputs["Color"], nodes["Principled BSDF"].inputs["Base Color"])
    desk = wood("Warm wooden writing desk")
    legs = material("Dark desk legs", (0.22, 0.23, 0.21), 0.6, 0.3)
    floor = material("Grey studio floor", (0.42, 0.44, 0.42), 0.85)

    objects, audit, cache = [], [], {}
    for record in payload["geoms"]:
        name, kind, size, owner = record["name"], record["kind"], record["size"], record["owner"]
        if kind == 7:
            mid = str(record["mesh"])
            source = payload["meshes"][mid]
            if mid not in cache:
                mesh = bpy.data.meshes.new(source["name"])
                verts = geometry[source["prefix"] + "vertices"]
                mesh.from_pydata(verts.tolist(), [], geometry[source["prefix"] + "faces"].tolist())
                mesh.update()
                if name == "letter_print":
                    uv = mesh.uv_layers.new(name="UVMap")
                    coords = geometry[source["prefix"] + "uv"]
                    for loop in mesh.loops:
                        u, v = coords[loop.vertex_index]
                        uv.data[loop.index].uv = (float(u), float(1.0 - v) if FLIP_V else float(v))
                if owner in ("hand", "left_hand", "robot"):
                    for polygon in mesh.polygons:
                        polygon.use_smooth = True
                cache[mid] = mesh
            obj = bpy.data.objects.new(name, cache[mid])
            scene.collection.objects.link(obj)
        elif kind == 6:
            bpy.ops.mesh.primitive_cube_add(size=2)
            obj = bpy.context.object
            obj.data.transform(Matrix.Diagonal((*size, 1)))
        elif kind == 0:
            bpy.ops.mesh.primitive_plane_add(size=2)
            obj = bpy.context.object
            obj.data.transform(Matrix.Diagonal((size[0] * 3, size[1] * 3, 1, 1)))
        elif kind == 5:
            bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=size[0], depth=2 * size[1])
            obj = bpy.context.object
        elif kind in (2, 4):
            bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=1)
            obj = bpy.context.object
            obj.data.transform(Matrix.Diagonal((*(size if kind == 4 else [size[0]] * 3), 1)))
        elif kind == 3:
            r, half = size[:2]
            bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=r, depth=2 * half)
            obj = bpy.context.object
            for z in (-half, half):
                bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=r, location=(0, 0, z))
                cap = bpy.context.object
                cap.select_set(True)
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.join()
            obj = bpy.context.object
            for p in obj.data.polygons:
                p.use_smooth = True
        else:
            raise ValueError(f"Unsupported geometry {kind}")
        obj.name = name
        bevel = 0.0
        if owner in ("hand", "left_hand"):
            if payload["hand"] == "wuji":
                chosen = wuji_shell
            else:
                chosen = rubber if record["material"] == "green" else steel if "_VL" in name else shell
        elif owner == "robot":
            # Tianji Marvin arm: the factory rgba per sub-mesh, roughness 0.29 / metallic 0.15 (pot T17 film look)
            key = tuple(round(float(c), 3) for c in record["rgba"][:3])
            if key not in arm_materials:
                arm_materials[key] = material(f"Marvin arm {key}", key, 0.29, 0.15)
            chosen = arm_materials[key]
        elif name == "floor":
            chosen = floor
        elif name == "desk":
            chosen, bevel = desk, 0.003
        elif name.startswith("desk_leg"):
            chosen = legs
        elif name == "letter_print":
            chosen = printed
        elif owner == "letter":
            chosen = paper
        elif name in ("envelope_open_flap", "envelope_flap_fold"):
            chosen = flap
        elif "band" in name:
            chosen = band
        else:
            chosen = envelope
            bevel = 0.0002 if kind == 6 else 0.0
        obj.data.materials.clear()
        obj.data.materials.append(chosen)
        if bevel > 0 and kind == 6:
            mod = obj.modifiers.new("Presentation edge rounding", "BEVEL")
            mod.width, mod.segments = bevel, 2
        objects.append((obj, record["id"]))
        audit.append({"geom": name, "material": chosen.name, "bevel_m": bevel})

    target0 = Vector((0.52, 0.03, 0.703))

    def area(name, offset, energy, size, color):
        data = bpy.data.lights.new(name, "AREA")
        data.energy, data.shape, data.size, data.color = energy, "DISK", size, color
        obj = bpy.data.objects.new(name, data)
        scene.collection.objects.link(obj)
        obj.location = target0 + Vector(offset)
        obj.rotation_euler = (target0 - obj.location).to_track_quat("-Z", "Y").to_euler()

    # T38 film lights (offsets from the camera target), energies scaled for this exposure
    area("Window daylight", (-0.26, -0.28, 0.60), 40, 0.55, (1, 0.95, 0.88))
    area("Gentle fill", (0.30, 0.30, 0.50), 18, 0.45, (0.86, 0.93, 1))
    area("Paper rim", (0.10, 0.40, 0.50), 10, 0.30, (1, 1, 1))
    camdata = bpy.data.cameras.new("Studio camera")
    camera = bpy.data.objects.new("Studio camera", camdata)
    scene.collection.objects.link(camera)
    scene.camera = camera
    camdata.lens = 42
    camdata.clip_start, camdata.clip_end = 0.005, 20
    frames = payload["frames"]
    success_step = payload["success_step"]
    indices = [args.still] if args.still is not None else list(range(0, len(frames), args.frame_step))
    if args.still is None and indices[-1] != len(frames) - 1:
        indices.append(len(frames) - 1)
    id_index = {g["id"]: i for i, g in enumerate(payload["geoms"])}
    # The robot stands at the desk's +x edge: overview from the -x side facing it, then a raised side view of the mouth
    p0, t0 = Vector((-0.12, -0.78, 1.42)), Vector((0.58, 0.0, 0.84))
    p1, t1 = Vector((0.66, 0.62, 1.02)), Vector((0.55, 0.12, 0.72))
    measurements = []
    for index in indices:
        record = frames[index]
        # camera: overview while the letter is carried, then the T38 close view of the mouth for the insertion
        r = min(max((record["step"] - 0.40 * success_step) / (0.25 * success_step), 0.0), 1.0)
        a = r * r * (3 - 2 * r)
        camera.location = p0.lerp(p1, a)
        target = t0.lerp(t1, a)
        camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
        for obj, gid in objects:
            j = id_index[gid]
            matrix = Matrix(pose_rotations[index, j].tolist()).to_4x4()
            matrix.translation = Vector(pose_positions[index, j].tolist())
            obj.matrix_world = matrix
        started = time.monotonic()
        scene.render.filepath = str(frame_dir / f"{index:06d}.png")
        bpy.ops.render.render(write_still=True)
        measurements.append({"frame": index, "native_step": record["step"], "seconds": time.monotonic() - started})
        print("FRAME " + json.dumps(measurements[-1]), flush=True)
    settings = {
        "renderer_source_sha256": sha(__file__), "export_sha256": sha(args.export / "scene.json"),
        "engine": "Eevee Next" if args.engine == "eevee" else "Cycles OptiX", "samples": args.samples,
        "width": 1280, "height": 720, "frame_step": args.frame_step, "video_fps": payload["fps"],
        "native_pose_interpolation": False, "appearance_only": True, "materials": audit, "indices": indices,
        "measurements": measurements, "blender_version": bpy.app.version_string,
    }
    if args.still is None:
        (frame_dir / "render.json").write_text(json.dumps(settings, indent=1) + "\n")


if __name__ == "__main__":
    main()
