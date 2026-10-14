"""Blender 4.5 Cycles presentation renderer for verified MuJoCo geometry/pose exports.

Run with blender -b --python render_blender.py -- --capture DIR --output DIR.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import time

import bpy
from mathutils import Quaternion, Vector
import numpy as np

p = argparse.ArgumentParser()
p.add_argument("--capture", type=Path, required=True)
p.add_argument("--output", type=Path, required=True)
p.add_argument("--preview", type=int)
p.add_argument("--width", type=int, default=1920)
p.add_argument("--samples", type=int, default=32)
p.add_argument("--start", type=int, default=0)
p.add_argument("--end", type=int)
a = p.parse_args(sys.argv[sys.argv.index("--") + 1 :])
a.output.mkdir(parents=True, exist_ok=True)
spec = json.loads((a.capture / "scene.json").read_text())
name = spec["name"]
render_config = {
    "renderer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "capture_sha256": {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(a.capture.iterdir())
        if p.is_file()
    },
    "width": a.width,
    "samples": a.samples,
    "engine": "Cycles",
    "denoiser": "OptiX",
}
config_path = a.output / "render-config.json"
if config_path.exists() and json.loads(config_path.read_text()) != render_config:
    raise RuntimeError(
        "Output directory belongs to a different renderer or capture; choose a new output"
    )
config_path.write_text(json.dumps(render_config, indent=2) + "\n")
geo = np.load(a.capture / "geometry.npz", allow_pickle=False)
motion = np.load(a.capture / "motion.npz", allow_pickle=False)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.samples = a.samples
scene.cycles.use_denoising = True
scene.cycles.denoiser = "OPTIX"
scene.cycles.denoising_use_gpu = True
scene.cycles.adaptive_threshold = 0.03
scene.cycles.max_bounces = 6
scene.cycles.diffuse_bounces = 2
scene.cycles.glossy_bounces = 2
scene.cycles.transmission_bounces = 2
scene.cycles.use_light_tree = True
scene.render.use_persistent_data = True
prefs = bpy.context.preferences.addons["cycles"].preferences
prefs.compute_device_type = "OPTIX"
prefs.get_devices()
for device in prefs.devices:
    device.use = device.type == "OPTIX"
if not any(d.use for d in prefs.devices):
    raise RuntimeError("No OptiX device")
scene.cycles.device = "GPU"
scene.render.threads_mode = "FIXED"
scene.render.threads = 8
scene.render.resolution_x = a.width
scene.render.resolution_y = round(a.width * 9 / 16)
scene.render.resolution_percentage = 100
scene.render.fps = 25
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGB"
scene.render.image_settings.compression = 15
scene.view_settings.view_transform = "AgX"
scene.view_settings.look = "AgX - Medium High Contrast"
scene.render.film_transparent = False
scene.view_settings.exposure = -1.7
world = bpy.data.worlds.new("Studio environment")
scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (
    0.48,
    0.57,
    0.68,
    1,
)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.3
materials = {}


def material(label, color, metal=0, rough=0.4, texture=None, noise=False, emission=0):
    key = (label, tuple(color), metal, rough, str(texture), noise, emission)
    if key in materials:
        return materials[key]
    m = bpy.data.materials.new(label)
    m.use_nodes = True
    n = m.node_tree.nodes
    links = m.node_tree.links
    bs = n.get("Principled BSDF")
    bs.inputs["Base Color"].default_value = (*color[:3], 1)
    bs.inputs["Metallic"].default_value = metal
    bs.inputs["Roughness"].default_value = rough
    if emission:
        bs.inputs["Emission Color"].default_value = (*color[:3], 1)
        bs.inputs["Emission Strength"].default_value = emission
    if texture:
        im = n.new("ShaderNodeTexImage")
        im.image = bpy.data.images.load(str(texture), check_existing=True)
        links.new(im.outputs["Color"], bs.inputs["Base Color"])
    if noise:
        tex = n.new("ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = 145
        tex.inputs["Detail"].default_value = 2.2
        bump = n.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.12
        bump.inputs["Distance"].default_value = 0.0005
        links.new(tex.outputs["Fac"], bump.inputs["Height"])
        links.new(bump.outputs["Normal"], bs.inputs["Normal"])
    materials[key] = m
    return m


floor_mat = material(
    "Micro-textured concrete", (0.33, 0.35, 0.37), 0.05, 0.47, noise=True
)
wall_mat = material(
    "Warm architectural plaster", (0.55, 0.56, 0.54), 0, 0.7, noise=True
)
dark = material("Anodized charcoal", (0.018, 0.027, 0.037), 0.65, 0.3)
chrome = material("Brushed stainless steel", (0.43, 0.5, 0.55), 0.85, 0.27)
white = material("Porcelain white", (0.75, 0.78, 0.77), 0.08, 0.3)
teal = material("Reference teal", (0.035, 0.48, 0.43), 0.15, 0.34, emission=0.5)
amber = material("Safety amber", (0.94, 0.28, 0.035), 0.15, 0.3)


def box(label, loc, scale, mat, bevel=0):
    bpy.ops.mesh.primitive_cube_add(size=2, location=loc)
    ob = bpy.context.object
    ob.name = label
    ob.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    ob.data.materials.append(mat)
    if bevel:
        mod = ob.modifiers.new("Soft machined edges", "BEVEL")
        mod.width = bevel
        mod.segments = 3
    return ob


def curve(label, points, radius, mat, cyclic=False):
    c = bpy.data.curves.new(label, "CURVE")
    c.dimensions = "3D"
    c.resolution_u = 1
    c.bevel_depth = radius
    c.bevel_resolution = 2
    sp = c.splines.new("POLY")
    sp.points.add(len(points) - 1)
    for point, value in zip(sp.points, points):
        point.co = (*value, 1)
    sp.use_cyclic_u = cyclic
    ob = bpy.data.objects.new(label, c)
    scene.collection.objects.link(ob)
    c.materials.append(mat)
    return ob


def text3d(label, value, loc, size, mat, rotation=(math.pi / 2, 0, 0)):
    c = bpy.data.curves.new(label, "FONT")
    c.body = value
    c.size = size
    c.extrude = 0.0008
    c.align_x = "CENTER"
    ob = bpy.data.objects.new(label, c)
    scene.collection.objects.link(ob)
    ob.location = loc
    ob.rotation_euler = rotation
    c.materials.append(mat)
    return ob


# Preserve every visible source geometry and all collision-course elevations.
objects = {}
mesh_cache = {}
for g in spec["geoms"]:
    kind = g["kind"]
    size = g["size"]
    mesh_id = g["mesh"]
    if kind == 7:
        key = (mesh_id, g.get("texture"))
        if key not in mesh_cache:
            me = bpy.data.meshes.new("Source mesh " + str(mesh_id))
            me.from_pydata(
                geo[f"vertices_{mesh_id}"].tolist(),
                [],
                geo[f"faces_{mesh_id}"].tolist(),
            )
            me.update()
            if f"uv_{mesh_id}" in geo:
                uv = me.uv_layers.new(name="Source UV")
                coords = geo[f"uv_{mesh_id}"]
                faceuv = geo[f"faceuv_{mesh_id}"]
                for face, ids in zip(me.polygons, faceuv):
                    for loop, idx in zip(face.loop_indices, ids):
                        if idx >= 0:
                            uv.data[loop].uv = coords[idx]
            for face in me.polygons:
                face.use_smooth = True
            me.set_sharp_from_angle(angle=math.radians(50))
            mesh_cache[key] = me
        ob = bpy.data.objects.new(g["name"], mesh_cache[key])
        scene.collection.objects.link(ob)
    elif kind == 6:
        bpy.ops.mesh.primitive_cube_add(size=2)
        ob = bpy.context.object
        ob.scale = size
    elif kind == 5:
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=32, radius=size[0], depth=2 * size[1]
        )
        ob = bpy.context.object
        for poly in ob.data.polygons:
            poly.use_smooth = len(poly.vertices) == 4
    elif kind in (2, 4):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=16, radius=1)
        ob = bpy.context.object
        ob.scale = size if kind == 4 else [size[0]] * 3
        for poly in ob.data.polygons:
            poly.use_smooth = True
    elif kind == 3:
        r, h = size[:2]
        verts = []
        faces = []
        segments = 20
        latitudes = 14
        for j in range(latitudes + 1):
            phi = math.pi * j / latitudes
            z = r * math.cos(phi) + (h if phi <= math.pi / 2 else -h)
            for k in range(segments):
                theta = 2 * math.pi * k / segments
                verts.append(
                    (
                        r * math.sin(phi) * math.cos(theta),
                        r * math.sin(phi) * math.sin(theta),
                        z,
                    )
                )
        for j in range(latitudes):
            for k in range(segments):
                x = j * segments + k
                y = j * segments + (k + 1) % segments
                faces.append((x, y, y + segments, x + segments))
        me = bpy.data.meshes.new("Capsule")
        me.from_pydata(verts, [], faces)
        me.update()
        ob = bpy.data.objects.new(g["name"], me)
        scene.collection.objects.link(ob)
        for poly in me.polygons:
            poly.use_smooth = True
    else:
        raise ValueError(("Unsupported source geom", kind, g["name"]))
    ob.name = g["name"]
    ob.location = g["position"]
    ob.rotation_mode = "QUATERNION"
    ob.rotation_quaternion = g["quaternion"]
    label = g["material"] or g["name"]
    rgb = np.array(g["rgba"][:3])
    rough = 0.38
    metal = 0.25
    if g["body"] == 0:
        rough = 0.65
        metal = 0
        if g["name"].startswith("terrain_step"):
            rgb = np.array([0.21, 0.24, 0.25])
            rough = 0.6
        if g["name"].startswith("surface"):
            rgb = np.array([0.31, 0.32, 0.3])
            rough = 0.7
        if mesh_id >= 0 and "road" in label:
            rough = 0.82
    elif np.max(rgb) < 0.1:
        rgb = np.maximum(rgb, 0.018)
        metal = 0.18
        rough = 0.37
    if any(k in label.lower() for k in ("alloy", "metal")):
        metal = 0.85
        rough = 0.25
    if "paint" in label:
        metal = 0.6
        rough = 0.22
    if "glass" in label:
        metal = 0.45
        rough = 0.13
    if "tire" in label or "carbon" in label:
        metal = 0.03
        rough = 0.62
    rgb = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    mat = material(
        label,
        rgb,
        metal,
        rough,
        a.capture / g["texture"] if g.get("texture") else None,
        noise=g["body"] > 0 and not g.get("texture"),
    )
    # Separate material slots per object, including instanced meshes with different colors.
    if not ob.data.materials:
        ob.data.materials.append(mat)
    ob.material_slots[0].link = "OBJECT"
    ob.material_slots[0].material = mat
    if name == "neural-fly" and kind == 7:
        # The pinned asset includes four thin disk meshes as rotor-blur proxies.
        # Identify their disconnected cap/rim components without changing vertices.
        vertices = geo[f"vertices_{mesh_id}"]
        faces = geo[f"faces_{mesh_id}"]
        parent = list(range(len(vertices)))

        def component(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for face in faces:
            root = component(int(face[0]))
            for vertex in face[1:]:
                parent[component(int(vertex))] = root
        groups = {}
        for vertex in range(len(vertices)):
            groups.setdefault(component(vertex), []).append(vertex)
        rotor_groups = set()
        for root, members in groups.items():
            spans = np.sort(np.ptp(vertices[members], axis=0))
            if spans[0] < 0.016 and spans[1] > 0.25 and spans[2] < 0.28:
                rotor_groups.add(root)
        assert len(rotor_groups) == 12, "Pinned Skydio rotor components changed"
        rotor = material("Translucent rotor blur", (0.035, 0.04, 0.045), 0, 0.65)
        rotor.node_tree.nodes["Principled BSDF"].inputs["Alpha"].default_value = 0.12
        ob.data.materials.append(rotor)
        count = 0
        for polygon, face in zip(ob.data.polygons, faces):
            if component(int(face[0])) in rotor_groups:
                polygon.material_index = len(ob.data.materials) - 1
                count += 1
        print("Skydio translucent rotor faces", count, flush=True)
    objects[g["id"]] = ob

# MuJoCo's saved free-body pose does not include the presentation blade angle.
# Animate only the four named propeller geometries; airframe transforms stay exact.
rotors = None
rotor_objects = []
if name == "neural-landing" and "rotor_animation" in spec:
    rotors = np.load(a.capture / "rotors.npz", allow_pickle=False)
    assert np.array_equal(rotors["time"], motion["time"])
    assert rotors["rpm"].shape == rotors["phase"].shape == (len(motion["time"]), 4)
    blur_material = material(
        "Propeller shutter samples", (0.01, 0.013, 0.016), 0.03, 0.62
    )
    blur_material.node_tree.nodes["Principled BSDF"].inputs["Alpha"].default_value = (
        1 / 48
    )
    scene.cycles.transparent_max_bounces = 64
    disk_material = material("Fast rotor blur envelope", (0.04, 0.05, 0.055), 0.05, 0.5)
    disk_material.node_tree.nodes["Principled BSDF"].inputs[
        "Alpha"
    ].default_value = 0.12
    for rotor_index in range(4):
        blade = next(
            objects[g["id"]]
            for g in spec["geoms"]
            if g["name"] == f"visual_blade_{rotor_index}"
        )
        ghosts = []
        for sample in range(48):
            ghost = blade.copy()
            ghost.name = f"Rotor {rotor_index} shutter sample {sample}"
            scene.collection.objects.link(ghost)
            ghost.material_slots[0].link = "OBJECT"
            ghost.material_slots[0].material = blur_material
            ghosts.append(ghost)
        bpy.ops.mesh.primitive_circle_add(vertices=96, radius=0.115, fill_type="NGON")
        disk = bpy.context.object
        disk.name = f"Rotor {rotor_index} high-speed blur envelope"
        disk.rotation_mode = "QUATERNION"
        disk.data.materials.append(disk_material)
        rotor_objects.append((blade, ghosts, disk))

qpos = motion["qpos"]
base_min = qpos[:, :3].min(axis=0)
base_max = qpos[:, :3].max(axis=0)
center = (base_min + base_max) / 2
room_center = np.array([center[0], center[1], 0])
half = max(6, float(np.max(base_max[:2] - base_min[:2])) / 2 + 5)
# G1 and Go2's actual floor is z=0; AnyCar's physical surface boxes top out at z=0.
ground_z = float(spec.get("ground_z", 0.0))
box(
    "Studio foundation",
    (room_center[0], room_center[1], ground_z - 0.142),
    (half + 8, half + 8, 0.14),
    floor_mat,
    0.045,
)
for sx in np.arange(room_center[0] - half, room_center[0] + half, 1.5):
    curve(
        "Concrete expansion seam",
        [
            (sx, room_center[1] - half, ground_z - 0.0015),
            (sx, room_center[1] + half, ground_z - 0.0015),
        ],
        0.002,
        dark,
    )
back_y = room_center[1] + (
    3.0 if name.startswith("go2") or name == "neural-landing" else half
)
box("Rear wall", (room_center[0], back_y, 2.8), (half + 8, 0.16, 2.8), wall_mat, 0.08)
box(
    "Rear skirting",
    (room_center[0], back_y - 0.18, 0.08),
    (half + 8, 0.035, 0.08),
    dark,
    0.015,
)
for x in np.arange(room_center[0] - half - 6, room_center[0] + half + 6, 1.8):
    box("Wall reveal", (x, back_y - 0.17, 2.8), (0.012, 0.012, 2.65), dark, 0.005)
    box("Window mullion", (x, back_y - 0.21, 3.7), (0.035, 0.03, 0.9), chrome, 0.008)
box(
    "Lab glazing",
    (room_center[0], back_y - 0.19, 3.7),
    (half + 5, 0.012, 0.86),
    material("Frosted daylight", (0.38, 0.57, 0.66), 0.3, 0.24, emission=0.35),
    0.01,
)
text3d(
    "Wall branding", "ROBOENGINEER", (room_center[0], back_y - 0.22, 2.06), 0.47, dark
)
text3d(
    "Wall subheading",
    "CONTROL  /  TRANSFER  /  ADAPTATION",
    (room_center[0], back_y - 0.23, 1.67),
    0.11,
    dark,
)
# Long warm ceiling fixtures and their reflection on the robot's bodywork.
for x in (room_center[0] - 3, room_center[0] + 3):
    box(
        "Linear luminaire",
        (x, room_center[1], 4.2),
        (0.05, half, 0.025),
        material("Luminaire", (0.85, 0.93, 1), 0, 0.2, emission=3),
        0.01,
    )


def area(label, loc, target, power, color, size):
    light = bpy.data.lights.new(label, "AREA")
    light.energy = power
    light.color = color
    light.shape = "DISK"
    light.size = size
    ob = bpy.data.objects.new(label, light)
    scene.collection.objects.link(ob)
    ob.location = loc
    ob.rotation_euler = (
        (Vector(target) - ob.location).to_track_quat("-Z", "Y").to_euler()
    )


c = room_center
area("Large warm softbox", c + [-3, -4, 7], c + [0, 0, 0.5], 2300, (1, 0.91, 0.8), 7)
area("Cool fill", c + [4, -1, 5], c + [0, 0, 0.7], 1500, (0.68, 0.82, 1), 5)
area("Rim light", c + [1, 5, 5], c + [0, 0, 0.8], 2300, (1, 0.78, 0.57), 4)
if name == "g1":
    for x in (1, 5, 9):
        area("Walking course light", [x, -2, 4], [x, 0, 0.5], 700, (0.8, 0.9, 1), 3)
if name == "anycar":
    for x in (center[0] - 4, center[0] + 4):
        area(
            "Circuit softbox",
            [x, center[1] + 1, 6],
            [x, center[1], 0],
            1100,
            (0.87, 0.94, 1),
            4,
        )

# Public target references: presentation geometry only, never private state estimates.
if "reference_curve" in spec:
    points = np.array(spec["reference_curve"])
    if name == "anycar":
        for k in range(0, len(points) - 2, 5):
            segment = points[k : k + 3].copy()
            segment[:, 2] = 0.0048
            tangents = np.gradient(segment, axis=0)
            sides = np.column_stack(
                [-tangents[:, 1], tangents[:, 0], np.zeros(len(segment))]
            )
            sides *= 0.009 / np.maximum(
                np.linalg.norm(sides, axis=1, keepdims=True), 1e-9
            )
            vertices = np.stack([segment - sides, segment + sides], axis=1).reshape(
                -1, 3
            )
            mesh = bpy.data.meshes.new("Painted reference dash")
            mesh.from_pydata(vertices.tolist(), [], [(0, 1, 3, 2), (2, 3, 5, 4)])
            ob = bpy.data.objects.new("Painted public centerline", mesh)
            scene.collection.objects.link(ob)
            mesh.materials.append(white)
    else:
        curve("Public timed trajectory", points, 0.008, teal)
if name == "neural-landing":
    px, py, _ = spec["pad"]
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=96, radius=0.44, depth=0.003, location=(px, py, 0.0015)
    )
    pad = bpy.context.object
    pad.data.materials.append(dark)
    for r in (0.355, 0.428):
        pts = [
            (px + r * math.cos(t), py + r * math.sin(t), 0.004)
            for t in np.linspace(0, 2 * math.pi, 100)
        ]
        curve("Landing pad ring", pts, 0.004, white if r < 0.4 else amber, True)
    for x in (-0.115, 0.115):
        box("Pad H upright", (px + x, py, 0.005), (0.02, 0.155, 0.001), white)
    box("Pad H crossbar", (px, py, 0.005), (0.115, 0.019, 0.001), white)
    for x in (-0.55, 0.55):
        for y in (-0.55, 0.55):
            box(
                "Pad approach marking",
                (px + x, py + y, 0.002),
                (0.045, 0.01, 0.001),
                teal,
            )
if name.startswith("go2-"):
    command = spec["command_spec"]
    if name in ("go2-forward-jump", "go2-yaw-jump"):
        target_x = qpos[0, 0] + (
            command["distance"] if name == "go2-forward-jump" else 0
        )
        target_y = qpos[0, 1]
        w, x, y, z = qpos[0, 3:7]
        yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
        yaw += command["yaw"] if name == "go2-yaw-jump" else 0
        ring = [
            (target_x + 0.27 * math.cos(t), target_y + 0.27 * math.sin(t), 0.007)
            for t in np.linspace(0, 2 * math.pi, 100)
        ]
        curve("Requested touchdown position", ring, 0.008, amber, True)
        curve(
            "Requested final heading",
            [
                (target_x, target_y, 0.008),
                (
                    target_x + 0.32 * math.cos(yaw),
                    target_y + 0.32 * math.sin(yaw),
                    0.008,
                ),
            ],
            0.01,
            amber,
        )
    elif name == "go2-weave":
        for x, y in command["poles"]:
            curve(
                "Pole boundary",
                [
                    (x + 0.1 * math.cos(t), y + 0.1 * math.sin(t), 0.007)
                    for t in np.linspace(0, 2 * math.pi, 50)
                ],
                0.005,
                white,
                True,
            )

# Camera motion changes only presentation, with all original robot samples in chronological order.
camera_data = bpy.data.cameras.new("Cinema camera")
camera = bpy.data.objects.new("Cinema camera", camera_data)
scene.collection.objects.link(camera)
scene.camera = camera
camera_data.lens = 48
camera_data.clip_start = 0.01
camera_data.clip_end = 250
focus = bpy.data.objects.new("Focus target", None)
scene.collection.objects.link(focus)
camera_data.dof.use_dof = True
camera_data.dof.focus_object = focus
camera_data.dof.aperture_fstop = 10
robot_ids = [g["id"] for g in spec["geoms"] if g["body"] > 0]
ids = motion["geom_ids"]
transforms = motion["transforms"]


def set_frame(index):
    for g, value in zip(ids, transforms[index]):
        ob = objects[int(g)]
        ob.location = value[:3]
        ob.rotation_quaternion = value[3:]
    if rotors is not None:
        for rotor_index, (blade, ghosts, disk) in enumerate(rotor_objects):
            body_rotation = blade.rotation_quaternion.copy()
            phase = float(rotors["phase"][index, rotor_index])
            omega = float(rotors["rpm"][index, rotor_index]) * 2 * math.pi / 60
            direction = 1 if rotor_index % 2 == 0 else -1
            # A two-blade propeller repeats every pi radians. Once a shutter
            # exposure spans a whole turn, sample that period without temporal
            # aliasing; at shutdown the original opaque blade returns.
            sweep = min(omega / 50, math.pi)
            blurred = sweep > 0.15
            blade.hide_render = blurred
            blade.rotation_quaternion = body_rotation @ Quaternion((0, 0, 1), phase)
            disk.hide_render = sweep < math.pi
            disk.location = blade.location
            disk.rotation_quaternion = body_rotation
            for sample, ghost in enumerate(ghosts):
                ghost.hide_render = not blurred or sweep >= math.pi
                ghost.location = blade.location
                angle = phase + direction * sweep * ((sample + 0.5) / len(ghosts) - 0.5)
                ghost.rotation_quaternion = body_rotation @ Quaternion((0, 0, 1), angle)
    pos = Vector(qpos[index, :3])
    if name == "anycar":
        # World-oriented chase camera avoids unnatural snap rotations through corners.
        target = pos + Vector((0, 0, 0.13))
        offset = Vector((1.0, -1.65, 0.72))
        camera_data.lens = 43
    elif name == "anycar-jump":
        # Broadside tracking preserves the physical gap and both ramp slopes.
        target = Vector((pos.x + 0.35, 0, 0.25))
        offset = Vector((0.45, -3.8, 1.5))
        camera_data.lens = 46
    elif name == "anycar-drift-v3":
        target = pos + Vector((0, 0, 0.05))
        offset = Vector((0.65, -2.4, 2.6))
        camera_data.lens = 46
    elif name == "g1":
        target = Vector((pos.x + 0.25, pos.y, 0.86))
        offset = Vector((2.35, -3.5, 1.1))
        camera_data.lens = 52
    elif name == "neural-fly":
        target = pos.lerp(Vector(center), 0.30)
        offset = Vector((2.5, -3.5, 1.55))
        camera_data.lens = 53
    elif name == "neural-landing":
        target = Vector(spec["pad"]) + Vector((0, 0, 0.4))
        offset = Vector((2.2, -3.1, 1.6))
        camera_data.lens = 48
    else:
        target = pos + Vector((0.08, 0, 0.04))
        offset = Vector((1.45, -2.2, 0.65))
        camera_data.lens = 55
        if name == "go2-weave":
            target.x += 0.25
            offset = Vector((2.05, -2.75, 0.95))
            camera_data.lens = 50
    camera.location = target + offset
    camera.rotation_euler = (
        (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    )
    focus.location = pos + Vector((0, 0, 0.05 if name != "g1" else 0))
    scene.frame_set(index + 1)


indices = (
    [a.preview]
    if a.preview is not None
    else range(a.start, min(a.end or len(qpos), len(qpos)))
)
start = time.perf_counter()
rendered = 0
for index in indices:
    path = a.output / (
        f"preview-{index:05d}.png" if a.preview is not None else f"{index:05d}.png"
    )
    if path.exists():
        continue
    set_frame(index)
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    rendered += 1
    if rendered % 25 == 0:
        print(
            "PROGRESS",
            name,
            index + 1,
            "/",
            len(qpos),
            "wall_s",
            round(time.perf_counter() - start, 2),
            flush=True,
        )
if a.preview is not None:
    bpy.ops.wm.save_as_mainfile(filepath=str(a.output / "preview.blend"))
receipt = dict(
    name=name,
    blender=bpy.app.version_string,
    engine="Cycles",
    device="OPTIX",
    devices=[d.name for d in prefs.devices if d.use],
    samples=a.samples,
    resolution=[scene.render.resolution_x, scene.render.resolution_y],
    frames_rendered=rendered,
    wall_seconds=time.perf_counter() - start,
    presentation_only=True,
    source_record_sha256=spec["source_record_sha256"],
    renderer_sha256=render_config["renderer_sha256"],
    total_expected_frames=len(qpos),
    frame_time_range_s=[float(motion["time"][0]), float(motion["time"][-1])],
    rotor_animation=spec.get("rotor_animation"),
)
(
    a.output
    / ("preview-receipt.json" if a.preview is not None else "render-receipt.json")
).write_text(json.dumps(receipt, indent=2) + "\n")
print("DONE", json.dumps(receipt), flush=True)
