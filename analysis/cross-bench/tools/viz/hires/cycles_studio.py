"""Render a RoboTwin film (rtfilm.py) in Blender Cycles from the agent's own cameras: path traced, same settings as
exam_media/film_blender.py (OptiX, adaptive sampling, OIDN albedo+normal, AgX).

  blender -b -P rt_blender.py -- FILM OUT --cams world_camera1:1920x1440,head_camera:640x480 [--frames a:b:step]
          [--samples 128 --min-samples 32] [--still FRAME]
Writes OUT/<camera>/<frame:04d>.png (frame = index into scene.json frames); existing files are kept (resumable).
Set, lights and colour: film_blender.py's cinematic studio; "cinema" is a dedicated 3/4 camera, other names are the
agent's cameras (they keep the room: wall and ground).
"""
import json, math, os, re, sys

import bpy
import numpy as np
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:]
o = {"film": argv[0], "out": argv[1], "cams": "world_camera1:1920x1440", "frames": None, "samples": 128,
     "min_samples": 32, "still": None, "elevation": 35.0, "fit": 1.95, "target_dz": 0.15, "az_offset": -70.0, "exposure": 0.0}
i = 2
while i < len(argv):
    k = argv[i].lstrip("-").replace("-", "_"); o[k] = argv[i + 1]; i += 2

film = o["film"]
S = json.load(open(os.path.join(film, "scene.json")))
G = np.load(os.path.join(film, "geometry.npz"))
P = np.load(os.path.join(film, "poses.npz"))
shapes_m = P["shapes"]                                        # (F, S, 4, 4)
F = shapes_m.shape[0]

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


def lin(c):
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]


_mats = {}


def material(p):
    key = json.dumps(p, sort_keys=True)
    if key in _mats:
        return _mats[key]
    m = bpy.data.materials.new(f"m{len(_mats)}")
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    r, g, b, a = p["base_color"]
    bsdf.inputs["Base Color"].default_value = (r, g, b, 1.0)    # SAPIEN's base colour is linear
    bsdf.inputs["Roughness"].default_value = p["roughness"]
    # glTF files without a metallic factor default to 1; SAPIEN's rasteriser hides it, a path tracer turns the part
    # into a dark mirror. A "metal" that is also rough is that default: treat it as a dielectric.
    # SAPIEN's rasteriser lights such a part by its ambient term and shows a silvery sheen (the dustbin's bag): an
    # opaque textured one becomes a half metal that reflects the world (bright for glossy rays, see below).
    default_metal = p["metallic"] >= 0.999 and p["roughness"] >= 0.5
    sheen = default_metal and p["texture"] and a >= 0.999
    bsdf.inputs["Metallic"].default_value = 0.5 if sheen else 0.0 if default_metal else p["metallic"]
    bsdf.inputs["Roughness"].default_value = 0.35 if sheen else min(p["roughness"], 0.6)
    bsdf.inputs["IOR"].default_value = max(1.0, p["ior"])
    if p["texture"]:
        img = bpy.data.images.load(os.path.join(film, "tex", p["texture"]), check_existing=True)
        if p.get("texture_srgb") is False:                     # SAPIEN reads this texture as linear values
            img = bpy.data.images.load(os.path.join(film, "tex", p["texture"]), check_existing=False)
            img.colorspace_settings.name = "Non-Color"
        tex = nt.nodes.new("ShaderNodeTexImage"); tex.image = img
        mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"; mix.blend_type = "MULTIPLY"
        mix.inputs["Factor"].default_value = 1.0
        nt.links.new(tex.outputs["Color"], mix.inputs[6]); mix.inputs[7].default_value = (r, g, b, 1.0)
        nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
        if img.channels == 4 and min(img.pixels[3::4]) < 0.98:  # a label or stripes: the texture's alpha cuts it out
            nt.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
            a = 1.0
    if a < 0.999:                                               # clear plastic of the bottles: glass-like, tinted
        bsdf.inputs["Transmission Weight"].default_value = 1.0 - a
        bsdf.inputs["Roughness"].default_value = min(p["roughness"], 0.15)
        bsdf.inputs["IOR"].default_value = 1.45
    e = p["emission"]
    if max(e[:3]) > 0:
        bsdf.inputs["Emission Color"].default_value = (*e[:3], 1); bsdf.inputs["Emission Strength"].default_value = 1.0
    _mats[key] = m
    return m


objs = []                                                       # (shape index, object)
for si, sh in enumerate(S["shapes"]):
    for pid in sh["parts"]:
        v = G[f"part_{pid}_vertices"]; f = G[f"part_{pid}_triangles"]
        me = bpy.data.meshes.new(f"p{pid}")
        me.from_pydata(v.tolist(), [], f.tolist())
        me.update()
        if f"part_{pid}_uv" in G:
            uv = G[f"part_{pid}_uv"]
            layer = me.uv_layers.new(name="uv")
            vi = np.empty(len(me.loops), dtype=np.int32); me.loops.foreach_get("vertex_index", vi)
            layer.data.foreach_set("uv", uv[vi].reshape(-1))
        if f"part_{pid}_normals" in G and sh["kind"] == "RenderShapeTriangleMesh":
            me.shade_smooth()
            n = G[f"part_{pid}_normals"]
            nn = np.linalg.norm(n, axis=1, keepdims=True); n = np.where(nn > 0, n / np.maximum(nn, 1e-9), n)
            me.normals_split_custom_set_from_vertices(n.tolist())
        me.materials.append(material(S["parts"][pid]))
        ob = bpy.data.objects.new(f"{sh['entity']}_{pid}", me)
        scene.collection.objects.link(ob)
        objs.append((si, ob))

# set and light: the cinematic studio of exam_media/film_blender.py (MEDIA_STANDARD.md section 2), from its own code:
# seamless studio floor, dim sky dome, large soft key, weak overhead softbox, rim light
FB = os.environ.get("FILM_BLENDER", "/data/pingyue/rcb-wt/exam-media-v2/scripts/exam_media/film_blender.py")
fb = {"__name__": "film_blender_lib"}
exec(compile(open(FB).read().rsplit("\nmain()", 1)[0], FB, "exec"), fb)   # its definitions, not its main()
look = dict(fb["LOOK"]); look["elevation_deg"] = float(o["elevation"]); look["fit"] = float(o["fit"])
ROOM = {"ground", "wall"}           # left out of the cinematic shot (the wall stands in front of it), kept for the agent's cameras
subject = [si for si, sh in enumerate(S["shapes"]) if sh["entity"] not in ROOM | {"table"}]
pos = shapes_m[:, subject, :3, 3]                               # (F, n, 3): the robot, the bottles, the bin
extent = float(np.linalg.norm((pos.max(axis=1) - pos.min(axis=1)).max(axis=0))) or 1.0
# aim at the task's objects (RoboTwin names them <id>_<name>: the bottles, the dustbin), where the action is
objects = [si for si, sh in enumerate(S["shapes"]) if re.match(r"\d{3}_", sh["entity"])] or subject
# ...and the robot's arms above them (the handoff happens in the air): halfway between the two
target = Vector((0.5 * shapes_m[:, objects, :3, 3].mean(axis=(0, 1)) + 0.5 * pos.mean(axis=(0, 1))).tolist()) \
    + Vector((0, 0, float(o["target_dz"])))
fwd = -P["cam_head_camera"][0][:3, 2]                            # the robot faces where its head camera looks
base_az = math.degrees(math.atan2(fwd[1], fwd[0])) + look["azimuth_deg"] + float(o["az_offset"])
fb["studio"](look, 0.0, extent)
fb["lights"](look, target, extent, base_az)
studio_floor = bpy.data.objects.get("studio_floor")
room = [ob for si, ob in objs if S["shapes"][si]["entity"] in ROOM]

# cameras: "cinema" = a dedicated 3/4 view (film_blender's lens and distance rule, fixed); the others are the agent's
# own (OpenGL camera-to-world == Blender camera axes)
cams = {}
for spec in o["cams"].split(","):
    name, res = spec.split(":"); w, h = (int(x) for x in res.split("x"))
    cd = bpy.data.cameras.new(name); cd.clip_start = 0.02; cd.clip_end = 100
    ob = bpy.data.objects.new(name, cd); scene.collection.objects.link(ob)
    if name == "cinema":
        cd.lens = look["lens_mm"]; cd.sensor_width = 36
        dist = look["fit"] * extent * look["lens_mm"] / 36
        az, el = math.radians(base_az), math.radians(look["elevation_deg"])
        ob.location = target + dist * Vector((math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)))
        ob.rotation_euler = (target - ob.location).to_track_quat("-Z", "Y").to_euler()
        cams[name] = (ob, w, h, None)
    else:
        cd.sensor_fit = "VERTICAL"; cd.angle_y = S["cameras"][name]["fovy"]
        cams[name] = (ob, w, h, P[f"cam_{name}"])

# render settings (film_blender.py)
prefs = bpy.context.preferences.addons["cycles"].preferences
prefs.compute_device_type = "OPTIX"; prefs.get_devices()
for d in prefs.devices:
    d.use = d.type == "OPTIX"
scene.render.engine = "CYCLES"; scene.cycles.device = "GPU"
scene.cycles.samples = int(o["samples"]); scene.cycles.adaptive_min_samples = int(o["min_samples"])
scene.cycles.use_adaptive_sampling = True; scene.cycles.adaptive_threshold = 0.01
scene.cycles.use_denoising = True; scene.cycles.denoiser = "OPENIMAGEDENOISE"
scene.cycles.denoising_input_passes = "RGB_ALBEDO_NORMAL"; scene.cycles.denoising_use_gpu = True
scene.cycles.max_bounces = 8; scene.cycles.transmission_bounces = 8
scene.view_settings.view_transform = "AgX"
for name in ("Medium High Contrast", "AgX - Medium High Contrast"):
    try:
        scene.view_settings.look = name; break
    except TypeError:
        pass
scene.view_settings.exposure = float(o["exposure"])
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"; scene.render.image_settings.color_mode = "RGB"

if o["still"] is not None:
    frames = [int(o["still"])]
elif o["frames"]:
    a, b, st = (int(x) for x in o["frames"].split(":")); frames = list(range(a, min(b, F), st))
else:
    frames = list(range(F))
for fi in frames:
    todo = [(n, c) for n, c in cams.items() if not os.path.exists(os.path.join(o["out"], n, f"{fi:04d}.png"))]
    if not todo:
        continue
    for si, ob in objs:
        ob.matrix_world = Matrix(shapes_m[fi, si].tolist())
    for name, (ob, w, h, M) in todo:
        if M is not None:
            ob.matrix_world = Matrix(M[fi].tolist())
        for r in room:
            r.hide_render = name == "cinema"
        if studio_floor is not None:
            studio_floor.hide_render = name != "cinema"
        scene.camera = ob; scene.render.resolution_x = w; scene.render.resolution_y = h
        os.makedirs(os.path.join(o["out"], name), exist_ok=True)
        scene.render.filepath = os.path.join(o["out"], name, f"{fi:04d}.png")
        bpy.ops.render.render(write_still=True)
    print(f"frame {fi} done", flush=True)
