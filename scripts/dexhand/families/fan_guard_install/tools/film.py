"""Authoring film: exact native poses of the physical replay, rendered in Blender 4.5.3 (presentation only).

export  (pinned MuJoCo venv): replay the trajectory, sample every ``stride`` controls, write per-body meshes in
        body-local coordinates (bucketed by presentation material) and the exact body poses of every sample.
render  (Blender, ``blender -b -P film.py -- render ...``): rebuild the meshes, apply T26's studio materials, lights
        and camera path, set each body's native pose per frame and render PNG frames.
encode  (pinned venv): caption and encode H.264.

No object or hand motion is synthesized or interpolated; frames show sampled native states only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ----------------------------------------------------------------------------------------------- export (MuJoCo)
def _quat_mat(q):
    import numpy as np

    w, x, y, z = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def _capsule(r, half, seg, rings):
    import numpy as np

    pts = [(r * math.sin(math.pi / 2 * k / rings), half + r * math.cos(math.pi / 2 * k / rings)) for k in range(rings + 1)]
    pts += [(r * math.sin(math.pi / 2 + math.pi / 2 * k / rings), -half + r * math.cos(math.pi / 2 + math.pi / 2 * k / rings))
            for k in range(rings + 1)]
    verts, faces = [], []
    for radial, z in pts:
        for j in range(seg):
            a = 2 * math.pi * j / seg
            verts.append((radial * math.cos(a), radial * math.sin(a), z))
    for i in range(len(pts) - 1):
        for j in range(seg):
            a, b = i * seg + j, i * seg + (j + 1) % seg
            faces.append((a, b, b + seg))
            faces.append((a, b + seg, a + seg))
    return np.asarray(verts, float), np.asarray(faces, int)


def _cylinder(r, half, seg):
    import numpy as np

    verts = [(r * math.cos(2 * math.pi * j / seg), r * math.sin(2 * math.pi * j / seg), z) for z in (half, -half)
             for j in range(seg)]
    verts += [(0, 0, half), (0, 0, -half)]
    faces = []
    for j in range(seg):
        a, b = j, (j + 1) % seg
        faces += [(a, b, b + seg), (a, b + seg, a + seg), (2 * seg, b, a), (2 * seg + 1, a + seg, b + seg)]
    return np.asarray(verts, float), np.asarray(faces, int)


def _sphere(radii, seg=48, rings=24):
    import numpy as np

    verts, faces = [], []
    for i in range(rings + 1):
        t = math.pi * i / rings
        for j in range(seg):
            a = 2 * math.pi * j / seg
            verts.append((radii[0] * math.sin(t) * math.cos(a), radii[1] * math.sin(t) * math.sin(a), radii[2] * math.cos(t)))
    for i in range(rings):
        for j in range(seg):
            a, b = i * seg + j, i * seg + (j + 1) % seg
            faces += [(a, b, b + seg), (a, b + seg, a + seg)]
    return np.asarray(verts, float), np.asarray(faces, int)


def _box(size):
    import numpy as np

    x, y, z = size
    verts = np.array([(sx * x, sy * y, sz * z) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)], float)
    quads = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    faces = [(a, b, c) for a, b, c, d in quads] + [(a, c, d) for a, b, c, d in quads]
    return verts, np.asarray(faces, int)


def material_key(session, gid):
    m = session.model
    name = m.geom(gid).name or ""
    body = m.body(int(m.geom_bodyid[gid])).name
    owner = session.checker.owner[int(m.geom_bodyid[gid])]
    mat = m.material(int(m.geom_matid[gid])).name if m.geom_matid[gid] >= 0 else ""
    if owner == "hand":
        if session.hand == "sharpa":
            return "hand_rubber" if mat == "green" else ("hand_steel" if "_VL" in name else "hand_shell")
        return "wuji_dark" if m.geom_rgba[gid][:3].mean() < 0.4 else "hand_shell"
    if name == "floor":
        return "floor"
    if name == "table_top":
        return "oak"
    if name.startswith("table_leg"):
        return "leg"
    if mat:
        return mat
    return "fan_black"


def export(trajectory, directory, stride, hand="sharpa"):
    import numpy as np

    sys.path.insert(0, str(HERE.parent))
    from replay import load_trajectory
    from runtime import Session

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    actions, recorded_hand, _ = load_trajectory(trajectory)
    session = Session(hand=recorded_hand)
    m = session.model
    buckets = {}
    for gid in range(m.ngeom):
        if m.geom_group[gid] > 2 or m.geom_rgba[gid, 3] == 0:
            continue
        name = m.geom(gid).name or ""
        if recorded_hand == "wuji" and name.startswith("r_wuji_") and "_collision" in name:
            continue
        kind, size = int(m.geom_type[gid]), m.geom_size[gid]
        if kind == 3:
            thin = size[0] < 0.003
            v, f = _capsule(size[0], size[1], 10 if thin else 32, 2 if thin else 8)
            smooth = True
        elif kind == 5:
            v, f = _cylinder(size[0], size[1], 96)
            smooth = True
        elif kind in (2, 4):
            v, f = _sphere([size[0]] * 3 if kind == 2 else size)
            smooth = True
        elif kind == 6:
            v, f = _box(size)
            smooth = False
        elif kind == 7:
            mid = int(m.geom_dataid[gid])
            va, vn = int(m.mesh_vertadr[mid]), int(m.mesh_vertnum[mid])
            fa, fn = int(m.mesh_faceadr[mid]), int(m.mesh_facenum[mid])
            v, f = m.mesh_vert[va:va + vn].astype(float), m.mesh_face[fa:fa + fn].astype(int)
            smooth = True
        elif kind == 0:
            v, f = _box([4.0, 4.0, 0.0005])
            smooth = False
        else:
            continue
        local = v @ _quat_mat(m.geom_quat[gid]).T + m.geom_pos[gid]
        body = int(m.geom_bodyid[gid])
        key = (body, material_key(session, gid))
        bucket = buckets.setdefault(key, {"v": [], "f": [], "s": [], "n": 0})
        bucket["v"].append(local)
        bucket["f"].append(f + bucket["n"])
        bucket["s"].append(np.full(len(f), smooth))
        bucket["n"] += len(v)
    arrays, objects = {}, []
    for i, ((body, mat), b) in enumerate(sorted(buckets.items())):
        arrays[f"o{i}_v"] = np.concatenate(b["v"]).astype(np.float32)
        arrays[f"o{i}_f"] = np.concatenate(b["f"]).astype(np.int32)
        arrays[f"o{i}_s"] = np.concatenate(b["s"])
        objects.append({"index": i, "body": body, "body_name": m.body(body).name, "material": mat})
    np.savez_compressed(directory / "geometry.npz", **arrays)
    bodies = sorted({o["body"] for o in objects})
    phases = np.full(len(actions), "actuator replay")
    with np.load(trajectory, allow_pickle=False) as archive:
        if "phases" in archive and archive["phases"].shape == (len(actions),):
            phases = archive["phases"].copy()
    frames, positions, rotations = [], [], []

    def sample(phase):
        f = session.features()
        frames.append({"step": session.steps, "time_s": round(float(session.data.time), 4), "phase": str(phase),
                       "stage": f["stage"], "success": f["success"], "failure": f["failure"],
                       "guard": session.data.body("front_guard").xpos.tolist(), "state_sha": session.state_sha()})
        positions.append(session.data.xpos[bodies].copy())
        rotations.append(session.data.xmat[bodies].reshape(-1, 3, 3).copy())

    sample("initial state")
    for i, action in enumerate(actions):
        session.step(action)
        if (i + 1) % stride == 0 or session.done:
            sample(phases[i])
        if session.done:
            break
    np.savez_compressed(directory / "poses.npz", positions=np.asarray(positions), rotations=np.asarray(rotations))
    payload = {
        "schema_version": 1,
        "task": "fan_guard_install",
        "title": "Install a desk fan front guard",
        "hand": session.hand_info["model"],
        "evidence_type": "physical_actuator_replay",
        "scripted_object_motion": False,
        "trajectory_sha256": sha(trajectory),
        "final_sha": session.state_sha(),
        "success": session.success,
        "failure": session.failure,
        "stride": stride,
        "control_dt": session.control_dt,
        "fps": 25,
        "playback_speed": round(stride * session.control_dt * 25, 3),
        "bodies": bodies,
        "objects": objects,
        "frames": frames,
        "files": {name: sha(directory / name) for name in ("geometry.npz", "poses.npz")},
    }
    (directory / "scene.json").write_text(json.dumps(payload, indent=1) + "\n")
    session.close()
    print(json.dumps({"frames": len(frames), "objects": len(objects), "success": payload["success"],
                      "final_sha": payload["final_sha"]}))


# ----------------------------------------------------------------------------------------------- render (Blender)
CAMERA_WIDE = ((-1.30, -1.18, 1.86), (0.60, -0.06, 0.84), 46.0)
CAMERA_FAN = ((-0.62, -0.64, 1.66), (0.72, 0.17, 1.0), 44.0)  # the approved T26 film installation view, widened


def camera_for(record):
    """Wide view while the guard is away from the fan, the T26 installation view near it, smoothly blended."""
    gx, gy, gz = record["guard"]
    distance = math.dist((gx, gy, gz), (0.726, 0.18, 0.952))
    t = min(1.0, max(0.0, (0.55 - distance) / 0.45))
    t = t * t * (3 - 2 * t)
    lerp = lambda a, b: tuple(x + (y - x) * t for x, y in zip(a, b))  # noqa: E731
    return lerp(CAMERA_WIDE[0], CAMERA_FAN[0]), lerp(CAMERA_WIDE[1], CAMERA_FAN[1]), CAMERA_WIDE[2] + (CAMERA_FAN[2] - CAMERA_WIDE[2]) * t


def render(export_dir, frames_dir, samples, limit=None, only=None):
    import bpy
    import numpy as np
    from mathutils import Matrix, Vector

    export_dir, frames_dir = Path(export_dir), Path(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)
    payload = json.loads((export_dir / "scene.json").read_text())
    for name, expected in payload["files"].items():
        if sha(export_dir / name) != expected:
            raise ValueError("export integrity mismatch: " + name)
    geometry = np.load(export_dir / "geometry.npz")
    poses = np.load(export_dir / "poses.npz")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.eevee.taa_render_samples = samples
    if hasattr(scene.eevee, "use_raytracing"):
        scene.eevee.use_raytracing = True
    scene.render.resolution_x, scene.render.resolution_y = 1280, 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.4  # T26 film
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.72, 0.75, 0.77, 1)
    bg.inputs["Strength"].default_value = 0.45

    def linear(c):
        return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c[:3])

    def mat(name, rgba, metallic=0.0, roughness=0.4, coat=0.0, bump=None):
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        nodes, links = m.node_tree.nodes, m.node_tree.links
        bsdf = nodes["Principled BSDF"]
        bsdf.inputs["Base Color"].default_value = (*linear(rgba), 1)
        bsdf.inputs["Metallic"].default_value = metallic
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Coat Weight"].default_value = coat
        if bump:
            coord = nodes.new("ShaderNodeTexCoord")
            noise = nodes.new("ShaderNodeTexNoise")
            noise.inputs["Scale"].default_value = bump
            links.new(coord.outputs["Object"], noise.inputs["Vector"])
            node = nodes.new("ShaderNodeBump")
            node.inputs["Strength"].default_value = 0.12
            node.inputs["Distance"].default_value = 0.00003
            links.new(noise.outputs["Fac"], node.inputs["Height"])
            links.new(node.outputs["Normal"], bsdf.inputs["Normal"])
        return m

    # T26 film materials (export/scene.json of the approved film) plus the hamburger film's hand materials.
    materials = {
        "fan_black": mat("fan_black", (0.065, 0.073, 0.08), 0.0, 0.48, bump=2500),
        "fan_badge": mat("fan_badge", (0.10, 0.105, 0.11), 0.3, 0.3, coat=0.4),
        "fan_wire": mat("fan_wire", (0.055, 0.065, 0.075), 0.22, 0.42),
        "fan_clip": mat("fan_clip", (0.08, 0.09, 0.10), 0.0, 0.6),
        "fan_rubber": mat("fan_rubber", (0.045, 0.05, 0.05), 0.0, 0.8),
        "plug_metal": mat("plug_metal", (0.58, 0.60, 0.62), 0.85, 0.24),
        "oak": mat("oak", (0.61, 0.47, 0.34), 0.0, 0.65, bump=400),
        "leg": mat("leg", (0.27, 0.29, 0.27), 0.3, 0.45),
        "floor": mat("floor", (0.65, 0.68, 0.66), 0.0, 0.85),
        "hand_shell": mat("hand_shell", (0.90, 0.92, 0.92), 0.0, 0.24),
        "hand_rubber": mat("hand_rubber", (0.22, 0.29, 0.25), 0.0, 0.65),
        "hand_steel": mat("hand_steel", (0.35, 0.39, 0.40), 0.8, 0.30),
        "wuji_dark": mat("wuji_dark", (0.12, 0.12, 0.13), 0.2, 0.4),
    }
    body_index = {b: i for i, b in enumerate(payload["bodies"])}
    objects = []
    for record in payload["objects"]:
        i = record["index"]
        v, f, s = geometry[f"o{i}_v"], geometry[f"o{i}_f"], geometry[f"o{i}_s"]
        mesh = bpy.data.meshes.new(f"{record['body_name']}:{record['material']}")
        mesh.from_pydata(v.tolist(), [], f.tolist())
        mesh.update()
        mesh.polygons.foreach_set("use_smooth", s.astype(bool).tolist())
        obj = bpy.data.objects.new(mesh.name, mesh)
        scene.collection.objects.link(obj)
        obj.data.materials.append(materials.get(record["material"], materials["fan_black"]))
        objects.append((obj, body_index[record["body"]]))
    light_target = Vector((0.62, 0.07, 0.94))
    for name, offset, energy, size, color in [
        ("Large warm softbox", (-0.5, -0.5, 0.75), 24, 0.8, (1, 0.94, 0.85)),
        ("Broad cool fill", (-0.2, 0.6, 0.4), 18, 0.65, (0.84, 0.93, 1)),
        ("Rim reflection strip", (0.5, 0.3, 0.75), 22, 0.5, (1, 1, 1)),
    ]:
        data = bpy.data.lights.new(name, "AREA")
        data.energy, data.shape, data.size, data.color = energy, "DISK", size, color
        light = bpy.data.objects.new(name, data)
        scene.collection.objects.link(light)
        light.location = light_target + Vector(offset)
        light.rotation_euler = (light_target - light.location).to_track_quat("-Z", "Y").to_euler()
    cam_data = bpy.data.cameras.new("Presentation camera")
    camera = bpy.data.objects.new("Presentation camera", cam_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    cam_data.clip_start, cam_data.clip_end = 0.005, 20
    positions, rotations = poses["positions"], poses["rotations"]
    indices = list(range(len(payload["frames"])))
    if only:
        indices = [i for i in only if i < len(indices)]
    if limit:
        indices = indices[:limit]
    for index in indices:
        record = payload["frames"][index]
        for obj, j in objects:
            matrix = Matrix(rotations[index, j].tolist()).to_4x4()
            matrix.translation = Vector(positions[index, j].tolist())
            obj.matrix_world = matrix
        position, target, lens = camera_for(record)
        camera.location = Vector(position)
        camera.rotation_euler = (Vector(target) - camera.location).to_track_quat("-Z", "Y").to_euler()
        cam_data.lens = lens
        scene.render.filepath = str(frames_dir / f"{index:06d}.png")
        bpy.ops.render.render(write_still=True)
        print("FRAME", index, flush=True)
    (frames_dir / "render.json").write_text(json.dumps({
        "blender": bpy.app.version_string, "engine": "EEVEE Next", "samples": samples, "width": 1280, "height": 720,
        "export_sha256": sha(export_dir / "scene.json"), "renderer_sha256": sha(__file__),
        "appearance_only": True, "native_pose_interpolation": False, "frames": len(indices)}, indent=1) + "\n")


# ----------------------------------------------------------------------------------------------- encode
def encode(export_dir, frames_dir, output, hold_s=2.0, crf=24):
    import imageio.v2 as imageio
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

    payload = json.loads(Path(export_dir, "scene.json").read_text())
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
    small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 15)
    speed = payload["playback_speed"]
    detail = f"{payload['hand']} | physics replay, {speed:g}x | motor targets only"
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage_names = {0: "", 1: "guard seated", 2: "all clips locked", 3: "released hold complete"}
    with imageio.get_writer(output, fps=payload["fps"], codec="libx264", macro_block_size=1, pixelformat="yuv420p",
                            ffmpeg_params=["-crf", str(crf), "-preset", "slow", "-movflags", "+faststart"]) as writer:
        pic = None
        for index, record in enumerate(payload["frames"]):
            path = Path(frames_dir) / f"{index:06d}.png"
            if not path.is_file():
                continue
            pic = Image.open(path).convert("RGB")
            draw = ImageDraw.Draw(pic)
            title = payload["title"]
            width = max(draw.textlength(title, font=font), draw.textlength(detail, font=small)) + 30
            draw.rounded_rectangle((20, 18, 20 + width, 80), radius=8, fill=(245, 244, 237))
            draw.text((32, 25), title, font=font, fill=(35, 45, 40))
            draw.text((32, 56), detail, font=small, fill=(85, 92, 88))
            status = "PASS" if record["success"] else (("FAIL: " + record["failure"]) if record["failure"] else stage_names[record["stage"]])
            label = f"{record['phase']}" + (f" | {status}" if status else "") + f" | {record['time_s']:.1f} s"
            lw = draw.textlength(label, font=small) + 25
            draw.rounded_rectangle((20, 720 - 48, 20 + lw, 720 - 17), radius=5, fill=(245, 244, 237))
            draw.text((32, 720 - 43), label, font=small, fill=(35, 58, 43))
            writer.append_data(np.asarray(pic))
        for _ in range(round(payload["fps"] * hold_s)):
            writer.append_data(np.asarray(pic))
        pic.save(output.with_suffix(".png"))
    report = {"video": str(output), "video_sha256": sha(output), "bytes": output.stat().st_size,
              "trajectory_sha256": payload["trajectory_sha256"], "native_final_sha": payload["final_sha"],
              "success": payload["success"], "playback_speed": speed, "presentation_only": True,
              "scripted_object_motion": False}
    output.with_suffix(".json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["export", "render", "encode"])
    p.add_argument("--trajectory", type=Path)
    p.add_argument("--export", type=Path, required=True)
    p.add_argument("--frames", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--stride", type=int, default=4)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument("--limit", type=int)
    p.add_argument("--only", type=str)
    p.add_argument("--crf", type=int, default=24)
    a = p.parse_args(argv)
    if a.command == "export":
        export(a.trajectory, a.export, a.stride)
    elif a.command == "render":
        render(a.export, a.frames, a.samples, a.limit, [int(x) for x in a.only.split(",")] if a.only else None)
    else:
        encode(a.export, a.frames, a.output, crf=a.crf)
