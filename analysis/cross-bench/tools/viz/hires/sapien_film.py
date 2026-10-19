"""Record a RoboTwin replay for Blender: the scene's render geometry once, every shape's and camera's pose per frame.

Runs inside the RoboTwin image (the task's sim dir mounted at /srv). It replays trajectory.npz exactly as the service
did (rcb_traj.Session: same instance, one row per physics step) and samples the state the physics reached at step 0,
every `--every` steps and at the end -- the frames of the service's replay.mp4. It refuses a replay whose final
state hash differs from `--expect-sha` (final.json `live_sha`).

usage: python rtfilm.py --task put_bottles_dustbin --instance /srv/instance.json --traj T.npz --out FILM [--every 25]
       (without --traj: the initial state only, to check the look)
Film directory:
  scene.json    shapes (entity, part ids), parts (material), cameras (fovy, size), frames (physics step)
  geometry.npz  part_<i>_{vertices,triangles,normals,uv} (vertices already scaled by the shape's scale)
  poses.npz     shapes (F, S, 4, 4) world matrices; cam_<name> (F, 4, 4) camera-to-world, OpenGL axes (-z forward)
  tex/          the texture files the materials use
"""
import argparse, hashlib, json, os, shutil, sys

sys.path.insert(0, "/srv")
import numpy as np
import sapien
from rcb_traj import Session

ap = argparse.ArgumentParser()
ap.add_argument("--task", required=True); ap.add_argument("--instance", required=True)
ap.add_argument("--traj"); ap.add_argument("--out", required=True)
ap.add_argument("--every", type=int, default=25); ap.add_argument("--expect-sha")
a = ap.parse_args()
os.makedirs(os.path.join(a.out, "tex"), exist_ok=True)

s = Session(a.task, instance=a.instance, enable_render=True)
scene = s._raw_scene


def mat4(pose):
    return np.asarray(pose.to_transformation_matrix(), dtype=np.float64)


def tex_file(t):
    if t is None:
        return None
    fn = getattr(t, "filename", "") or ""
    if not fn or not os.path.exists(fn):                         # embedded in a .glb: take the pixels themselves
        from PIL import Image
        px = np.asarray(t.download())
        if px.ndim != 3 or px.size == 0:
            return None
        if px.dtype != np.uint8:
            px = (np.clip(px, 0, 1) * 255).astype(np.uint8)
        dst = f"{hashlib.md5(px.tobytes()).hexdigest()[:10]}.png"
        if not os.path.exists(os.path.join(a.out, "tex", dst)):
            Image.fromarray(px).save(os.path.join(a.out, "tex", dst))
        return dst
    dst = f"{hashlib.md5(fn.encode()).hexdigest()[:8]}_{os.path.basename(fn)}"
    if not os.path.exists(os.path.join(a.out, "tex", dst)):
        shutil.copy(fn, os.path.join(a.out, "tex", dst))
    return dst


arrays, parts, shapes, live = {}, [], [], []
for e in scene.entities:
    rb = e.find_component_by_type(sapien.render.RenderBodyComponent)
    if rb is None or not rb.is_enabled:
        continue
    for sh in rb.render_shapes:
        R = sapien.render                                        # primitives are unit meshes: scale them by their size
        if isinstance(sh, R.RenderShapeBox):
            scale = np.asarray(sh.half_size, dtype=np.float64)
        elif isinstance(sh, R.RenderShapeSphere):
            scale = np.repeat(float(sh.radius), 3)
        else:
            scale = np.asarray(getattr(sh, "scale", [1, 1, 1]), dtype=np.float64).reshape(-1)
        if scale.size == 1:
            scale = np.repeat(scale, 3)
        if isinstance(sh, (R.RenderShapeCapsule, R.RenderShapeCylinder)):
            raise SystemExit(f"{type(sh).__name__} on {e.name}: not handled")
        ids = []
        for p in sh.parts:
            v = np.asarray(p.get_vertices(), dtype=np.float32)
            f = np.asarray(p.get_triangles(), dtype=np.int32)
            if len(v) == 0 or len(f) == 0:
                continue
            i = len(parts)
            arrays[f"part_{i}_vertices"] = v * scale.astype(np.float32)
            arrays[f"part_{i}_triangles"] = f
            n = np.asarray(p.get_vertex_normal(), dtype=np.float32)
            if n.shape == v.shape:
                arrays[f"part_{i}_normals"] = n
            uv = np.asarray(p.get_vertex_uv(), dtype=np.float32)
            if uv.ndim == 2 and len(uv) == len(v):
                arrays[f"part_{i}_uv"] = uv
            m = p.material
            parts.append({"base_color": [float(x) for x in m.base_color], "texture": tex_file(m.base_color_texture),
                          "texture_srgb": bool(getattr(m.base_color_texture, "is_srgb", True)) if m.base_color_texture else None,
                          "normal_texture": tex_file(m.normal_texture), "roughness": float(m.roughness),
                          "metallic": float(m.metallic), "specular": float(m.specular), "transmission": float(m.transmission),
                          "ior": float(m.ior), "emission": [float(x) for x in m.emission]})
            ids.append(i)
        if ids:
            shapes.append({"entity": e.name, "kind": type(sh).__name__, "parts": ids})
            live.append((rb, sh))

cams = {}
for e in scene.entities:
    c = e.find_component_by_type(sapien.render.RenderCameraComponent)
    if c is not None and c.name not in cams:
        cams[c.name] = c
world = getattr(s.env.cameras, "world_camera1", None) or cams.get("world_camera1")   # the one the agent was given
if world is not None:
    cams["world_camera1"] = getattr(world, "camera", world)

frames, P, C = [], [], {k: [] for k in cams}


def sample(step):
    s.env._update_render()                                       # RoboTwin moves the wrist cameras with their links here
    frames.append(int(step))
    P.append(np.stack([mat4(rb.entity_pose) @ mat4(sh.local_pose) for rb, sh in live]).astype(np.float32))
    for k, c in cams.items():
        C[k].append(np.asarray(c.get_model_matrix(), dtype=np.float32))


sample(0)
n = 0
if a.traj:
    acts = np.load(a.traj)["actions"]
    for n, row in enumerate(acts, 1):
        s.step(row)
        if n % a.every == 0:
            sample(n)
    sample(n)
st = s.status()
np.savez_compressed(os.path.join(a.out, "geometry.npz"), **arrays)
np.savez_compressed(os.path.join(a.out, "poses.npz"), shapes=np.stack(P), **{f"cam_{k}": np.stack(v) for k, v in C.items()})
lights = []
for e in scene.entities:
    for comp in e.components:
        kind = type(comp).__name__
        if "Light" in kind:
            lights.append({"kind": kind, "color": [float(x) for x in comp.color], "pose": (mat4(comp.entity_pose) @ mat4(comp.local_pose)).tolist()})
json.dump({"task": a.task, "every": a.every, "frames": frames, "shapes": shapes, "parts": parts, "lights": lights,
           "ambient": [float(x) for x in scene.render_system.ambient_light],
           "cameras": {k: {"fovy": float(c.fovy), "width": int(c.width), "height": int(c.height)} for k, c in cams.items()},
           "status": st, "sapien": sapien.__version__},
          open(os.path.join(a.out, "scene.json"), "w"), indent=1)
print(json.dumps({"frames": len(frames), "shapes": len(shapes), "parts": len(parts), "steps": n, **st}))
if a.expect_sha and st["state_sha"] != a.expect_sha:
    print(f"final state {st['state_sha']} != expected {a.expect_sha}", file=sys.stderr)
    sys.exit(1)
