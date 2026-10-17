"""Nyx RGB for the IKEA MuJoCo standard sim service (scripts/ikea_mujoco/standard/, copied unchanged into every
tasks/ikea-<task>-i00-standard/environment/sim/): RoboARC's renderer and look, driven through RoboARC's nyx_direct.py
(scripts/robotangle/shared/, copied unchanged next to this file), fed from the IKEA scene's compiled MjModel.

Two processes. The physics process (server.py: the base image's python + numpy 2.5.4 + the patched mujoco 3.14.0) builds
`NyxRig` once: it writes the compiled model (scene.mjb), the floor's texture (PNG) and scene.json into a work folder and
starts the render process, `<RCB_NYX_PYTHON> ikea_nyx.py serve <folder>` (the image's venv /opt/nyx: gs-nyx 0.1.3,
numpy 2.3.5, trimesh 5.1.0, stock mujoco 3.14.0 to read the model; images/ikea-mujoco/sim/Dockerfile). Per image request it
sends the body poses of the rig's scratch MjData (RIG.kd: a copy of the live joint positions after mj_kinematics) and the
rig's camera poses over a pipe, and gets the RGB frames back. The live MjData is never touched: rendering cannot change
the physics.

The render process builds the Nyx scene as nyx_direct builds an MJCF entity: one Mesh instance per visible geom (MuJoCo's
default visible groups 0-2, alpha > 0: what MuJoCo's own renderer drew), its trimesh from nyx_direct._mj_geom_trimesh
(geom mesh or primitive, vertex split per normal), its colour as nyx_direct.color_material (the geom's material or rgba);
a MuJoCo plane is a Nyx Plane primitive with the plane's own texture (the scene's checker, exported from the model's
texture data) at MuJoCo's repeat. Every frame each instance gets its geom's world pose (body pose x the geom's local
pose, nyx_direct.quat_mul / quat_rotate). Cameras: the rig's poses and vertical field of view (ikea_rig.py; the
calibration the service reports is unchanged), 848 x 480; RoboARC's renderer settings (configs/presentation_configs/
nyx_lab.yaml, nyx_direct.NyxScene.export): FastPathTracer, 32 spp, denoiser, Reinhard tone mapping, SMAA, the studio_small_09
HDRI at intensity 1.0, RoboARC's four point lights (positions in rig.json, mk_standard_tasks.py: RoboARC's offsets from
its table centre, 1.48 m above the work surface). Depth stays MuJoCo's raster (ikea_rig.Rig.depth), as RoboARC's.

Protocol (render process stdout is the reply pipe; Nyx's own console output goes to stderr):
  request:  one JSON line {"op": "render", "cams": [indices], "nbody": n} + xpos (n, 3) + xquat (n, 4) + camera poses
            (ncam, 9: pos, lookat, up), float64
  reply:    one JSON line {"ok": true, "ms": ...} + the frames (H, W, 3) uint8 of the requested cameras, in order
"""
from __future__ import annotations
import hashlib, json, os, subprocess, sys, time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
VISIBLE_GROUPS = (0, 1, 2)          # mjvOption.geomgroup's default: what MuJoCo's renderer drew


# ============================================================================================ physics process side
def visible_geoms(model) -> list[int]:
    """The geoms MuJoCo's renderer draws with the default options: groups 0-2, alpha > 0."""
    out = []
    for i in range(model.ngeom):
        rgba = model.mat_rgba[model.geom_matid[i]] if model.geom_matid[i] >= 0 else model.geom_rgba[i]
        if int(model.geom_group[i]) in VISIBLE_GROUPS and float(rgba[3]) > 0.0:
            out.append(i)
    return out


def _plane_texture(model, g, folder) -> dict | None:
    """A plane geom's RGB texture (the scene's checker) as a PNG, with MuJoCo's repeat."""
    import mujoco
    from PIL import Image
    mat = int(model.geom_matid[g])
    if mat < 0:
        return None
    tex = int(model.mat_texid[mat][int(mujoco.mjtTextureRole.mjTEXROLE_RGB)])
    if tex < 0:
        return None
    w, h, nc = int(model.tex_width[tex]), int(model.tex_height[tex]), int(model.tex_nchannel[tex])
    data = np.asarray(model.tex_data[int(model.tex_adr[tex]):int(model.tex_adr[tex]) + w * h * nc], dtype=np.uint8)
    img = data.reshape(h, w, nc)[:, :, :3]
    name = f"plane_{g}_tex{tex}.png"
    Image.fromarray(np.ascontiguousarray(img)).save(os.path.join(folder, name))
    return {"png": name, "texrepeat": [float(v) for v in model.mat_texrepeat[mat]], "texuniform": bool(model.mat_texuniform[mat])}



class RenderError(RuntimeError):
    """The Nyx render process failed (it died, refused or sent a short frame): the service's infrastructure, never the
    agent's doing (server.py ends the episode with reason "error", an infrastructure failure)."""

class NyxRig:
    """The render process of one scene and rig (physics-process side)."""

    def __init__(self, model, rig, rig_spec: dict, folder: str, log_path: str | None = None):
        import mujoco
        self.rig, self.names = rig, list(rig.names)
        self.folder = os.path.abspath(folder)
        os.makedirs(self.folder, exist_ok=True)
        mujoco.mj_saveModel(model, os.path.join(self.folder, "scene.mjb"), None)
        geoms = visible_geoms(model)
        planes = {g: _plane_texture(model, g, self.folder) for g in geoms if int(model.geom_type[g]) == int(mujoco.mjtGeom.mjGEOM_PLANE)}
        nyx = rig_spec["nyx"]
        cams = [{"name": c, "res": [rig.W, rig.H], "fov": rig.fovy(c), "near": nyx["near"],
                 "far": nyx["far_link"] if rig.mounts[c]["type"] == "link" else nyx["far"]} for c in self.names]
        scene = {"geoms": geoms, "planes": {str(g): v for g, v in planes.items()}, "cameras": cams, "lights": nyx["lights"],
                 "spp": nyx["spp"], "denoise": nyx["denoise"], "env_intensity": nyx["env_intensity"],
                 "env_map": os.environ.get("RCB_NYX_ENV_MAP", "/opt/nyx-assets/studio_small_09_2k.hdr")}
        with open(os.path.join(self.folder, "scene.json"), "w") as f:
            json.dump(scene, f)
        self.nbody = int(model.nbody)
        self.log_path = log_path
        self.timing = {"frames": 0, "calls": 0, "render_ms": 0.0, "roundtrip_ms": 0.0}
        self._start()

    def _start(self) -> None:
        python = os.environ.get("RCB_NYX_PYTHON", "/opt/nyx/bin/python")
        log = open(self.log_path, "ab") if self.log_path else subprocess.DEVNULL
        t = time.time()
        self.proc = subprocess.Popen([python, "-I", os.path.join(HERE, "ikea_nyx.py"), "serve", self.folder],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, cwd=self.folder,
                                     env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"})
        ready = self._line()
        if not ready.get("ready"):
            raise RenderError(f"Nyx render process failed to start: {ready}")
        self.startup = {**ready, "startup_s": round(time.time() - t, 2)}

    def _line(self) -> dict:
        line = self.proc.stdout.readline()
        if not line:
            raise RenderError(f"Nyx render process ended (exit {self.proc.poll()})")
        return json.loads(line)

    def render(self, kd, cameras: list) -> dict:
        """RGB (H, W, 3) uint8 of `cameras` at the state of the rig's scratch data `kd` (after rig.update)."""
        idx = [self.names.index(c) for c in cameras]
        poses = np.zeros((len(self.names), 9))
        for i, c in enumerate(self.names):
            p, R = self.rig.pose(c)
            poses[i] = np.concatenate([p, p + R[2], -R[1]])
        payload = (np.ascontiguousarray(kd.xpos, dtype=np.float64).tobytes() + np.ascontiguousarray(kd.xquat, dtype=np.float64).tobytes()
                   + poses.tobytes())
        t = time.perf_counter()
        head = json.dumps({"op": "render", "cams": idx, "nbody": self.nbody}).encode() + b"\n"
        self.proc.stdin.write(head + payload)
        self.proc.stdin.flush()
        reply = self._line()
        if not reply.get("ok"):
            raise RenderError(f"Nyx render failed: {reply}")
        out = {}
        for c in cameras:
            n = self.rig.H * self.rig.W * 3
            buf = self.proc.stdout.read(n)
            if len(buf) != n:
                raise RenderError("Nyx render process: short frame")
            out[c] = np.frombuffer(buf, dtype=np.uint8).reshape(self.rig.H, self.rig.W, 3).copy()
        self.timing["roundtrip_ms"] += 1e3 * (time.perf_counter() - t)
        self.timing["render_ms"] += float(reply.get("ms", 0.0))
        self.timing["frames"] += len(cameras)
        self.timing["calls"] += 1
        return out

    def close(self) -> None:
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=30)
        except Exception:  # noqa: BLE001
            self.proc.kill()


# ============================================================================================ render process side
def _serve(folder: str) -> int:
    reply = os.fdopen(os.dup(1), "wb")         # the reply pipe; fd 1 then goes to stderr (Nyx's console output)
    os.dup2(2, 1)
    sys.path.insert(0, HERE)
    import mujoco
    import nyx_direct as N
    spec = json.load(open(os.path.join(folder, "scene.json")))
    mj = mujoco.MjModel.from_binary_path(os.path.join(folder, "scene.mjb"))
    t0 = time.perf_counter()
    scene = IkeaScene(mj, spec)
    nyx = IkeaNyx(scene, os.path.join(folder, "nyx"))
    reply.write((json.dumps({"ready": True, "instances": len(scene.slots), "meshes": scene.n_mesh_files,
                             "build_s": round(time.perf_counter() - t0, 2)}) + "\n").encode())
    reply.flush()
    inp = sys.stdin.buffer
    cams = len(spec["cameras"])
    while True:
        line = inp.readline()
        if not line:
            break
        req = json.loads(line)
        n = int(req["nbody"])
        xpos = np.frombuffer(inp.read(n * 24), dtype=np.float64).reshape(n, 3).copy()
        xquat = np.frombuffer(inp.read(n * 32), dtype=np.float64).reshape(n, 4).copy()
        poses = np.frombuffer(inp.read(cams * 72), dtype=np.float64).reshape(cams, 9).copy()
        try:
            t = time.perf_counter()
            nyx.set_state(xpos, xquat, poses)
            frames = nyx.render_cameras([int(i) for i in req["cams"]])
            ms = 1e3 * (time.perf_counter() - t)
        except Exception as exc:  # noqa: BLE001
            reply.write((json.dumps({"ok": False, "error": repr(exc)}) + "\n").encode())
            reply.flush()
            continue
        reply.write((json.dumps({"ok": True, "ms": round(ms, 3)}) + "\n").encode())
        for f in frames:
            reply.write(np.ascontiguousarray(f).tobytes())
        reply.flush()
    nyx.close()
    return 0


def srgb_to_linear(c):
    c = np.asarray(c, dtype=np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_color_material(nps, N, rgba_u8):
    """nyx_direct.color_material with the colour taken as what it is in the IKEA scenes: a display (sRGB) colour, the one
    MuJoCo's raster shows. Nyx shades in linear light, so the albedo is the colour converted to linear (alpha kept);
    without it every colour renders washed out (the Panda's 0.25 grey as near white)."""
    mat = N.color_material(nps, rgba_u8)
    c = np.asarray(rgba_u8, dtype=np.float64) / 255.0
    lin = srgb_to_linear(c[:3])
    mat.albedoColor = nps.float4(float(lin[0]), float(lin[1]), float(lin[2]), float(c[3]))
    return mat


class IkeaScene:
    """The Nyx scene of a compiled IKEA MjModel, written as nyx_direct.NyxScene.export writes an MJCF entity (render
    process side; the interface NyxDirect reads: export())."""

    def __init__(self, mj, spec: dict):
        import mujoco
        import nyx_direct as N
        self.mj, self.spec = mj, spec
        self.planes = {int(g): v for g, v in spec["planes"].items()}
        self.geoms = [int(g) for g in spec["geoms"]]
        self.meshes = {}                 # geom -> nyx_direct._mj_geom_trimesh dict
        self.slots = []
        for g in self.geoms:
            if g not in self.planes:
                self.meshes[g] = N._mj_geom_trimesh(mj, g, is_col=False)
            self.slots.append(N.Slot("ikea", f"g{g}", None, np.array(mj.geom_pos[g], dtype=np.float64),
                                     np.array(mj.geom_quat[g], dtype=np.float64), np.zeros(3), np.array([1.0, 0, 0, 0])))
        self.body = np.array([int(mj.geom_bodyid[g]) for g in self.geoms])
        self.n_mesh_files = 0

    def export(self, folder, *, camera_device: str = "cpu") -> dict:
        """nyx_scene.json and the meshes (nyx_direct.NyxScene.export's conventions: Z-up -> Y-up, wxyz -> xyzw, the
        exporter's camera rotation, OBJ meshes named by their content)."""
        import math
        from pathlib import Path
        import gs_nyx.nyx_py_sdk as nps
        import nyx_direct as N
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        asset = nps.SceneAsset()
        asset.version = 1
        asset.rootFolder = os.path.relpath(os.getcwd(), folder.resolve()).replace("\\", "/") + "/"
        cams, lights = self.spec["cameras"], self.spec["lights"]
        asset.instance_resize(len(self.slots))
        asset.camera_resize(len(cams))
        asset.light_resize(len(lights))
        asset.env_map_resize(1)
        asset.light_field_resize(0)
        I, P = nps.EInstanceType, nps.EPrimitiveType
        yup = nps.float3_z_up_to_y_up_a
        uuids = [nps.generate_uuid() for _ in self.slots]     # one per instance: Nyx keys an instance's material by it
        names = set()
        for index, (g, s) in enumerate(zip(self.geoms, self.slots)):
            inst = asset.get_instance(index)
            inst.position = yup(nps.float3(0.0, 0.0, 0.0))
            inst.rotation = nps.quaternion_z_up_to_y_up_a(nps.quaternion_wxyz_to_xyzw(nps.quaternion(1.0, 0.0, 0.0, 0.0)))
            if g in self.planes:
                size = self.mj.geom_size[g]
                extent = (float(2 * size[0]) if size[0] > 0 else 1e3, float(2 * size[1]) if size[1] > 0 else 1e3)
                inst.type = I.Primitive
                inst.primitive_type = P.Plane
                inst.scale = yup(nps.float3(extent[0], extent[1], 1.0))
                tex = self.planes[g]
                if tex is not None:
                    surface = N.Surface(kind="Default", diffuse=("image", str(Path(tex["png"]).resolve()), None))
                    mat = N.material_override(nps, surface, plane_size=extent)
                    rep = tex["texrepeat"]
                    # MuJoCo: texuniform repeats texrepeat times per unit length, else over the geom (an infinite plane
                    # renders as one of its zfar-sized squares: per unit length too)
                    mat.uvScale = nps.float2(extent[0] * rep[0] / 2.0, extent[1] * rep[1] / 2.0)
                else:
                    mat = linear_color_material(nps, N, N._u8_color(self.mj.geom_rgba[g]))
                inst.matOverride = mat
            else:
                m = self.meshes[g]
                inst.type = I.Mesh
                inst.convertAxis = True
                inst.scale = yup(nps.float3(1.0, 1.0, 1.0))
                data = m["trimesh"].export(file_type="obj")
                data = data.encode() if isinstance(data, str) else data
                mesh_name = hashlib.sha256(data).hexdigest()[:16] + ".obj"
                if not (folder / mesh_name).exists():
                    (folder / mesh_name).write_bytes(data)
                    self.n_mesh_files += 1
                inst.mesh_uri = os.path.relpath(folder / mesh_name).replace("\\", "/")
                inst.matOverride = linear_color_material(nps, N, m["rgba_u8"])
            assert s.node not in names
            names.add(s.node)
            inst.smooth, inst.enabled, inst.uuid = False, True, uuids[index]
            inst.name = s.node
            asset.set_instance(index, inst)
        defs = []
        for i, cam in enumerate(cams):
            d = dict(name=cam["name"], res=list(cam["res"]), pos=[0.0, 0.0, 1.0], lookat=[0.0, 0.0, 0.0], up=[0.0, 1.0, 0.0],
                     fov=float(cam["fov"]), near=float(cam["near"]), far=float(cam["far"]), spp=int(self.spec["spp"]),
                     denoise=bool(self.spec["denoise"]), attach=None)
            c = asset.get_camera(i)
            c.position = yup(nps.float3(*d["pos"]))
            _, q = N.camera_quat_f32(d["pos"], d["lookat"], d["up"], device=camera_device)
            qx = nps.quaternion_conjugate(nps.quaternion_z_up_to_y_up_a(nps.quaternion_wxyz_to_xyzw(
                nps.quaternion(float(q[0]), float(q[1]), float(q[2]), float(q[3])))))
            c.rotation = nps.quaternion_mul(nps.quaternion(0.5, 0.5, 0.5, 0.5), qx)
            c.fovY = math.radians(d["fov"])
            c.resolution = nps.uint2(int(d["res"][0]), int(d["res"][1]))
            c.aperture, c.focalLength = 2.8, 10.0
            c.nearPlane, c.farPlane = d["near"], d["far"]
            c.spp, c.denoise = d["spp"], d["denoise"]
            c.toneMapper, c.antiAliasing = nps.EToneMapper.Reinhard, nps.EAntiAliasing.SMAA
            asset.set_camera(i, c)
            defs.append(d)
        for i, light in enumerate(lights):
            asset.set_light(i, N.light_asset(nps, light))
        env = nps.EnvironmentMapAsset()
        env.texture = str(self.spec["env_map"])
        env.layout = nps.EEnvMapLayout.LongLat
        env.multiplier = float(self.spec["env_intensity"])
        asset.set_env_map(0, env)
        path = folder / N.SCENE_FILE
        nps.export_scene_file(str(path), asset)
        return dict(path=path, references=[(u, s.node) for u, s in zip(uuids, self.slots)], slots=self.slots, cameras=defs, deformables=[])


def _nyx_direct_class():
    sys.path.insert(0, HERE)
    import nyx_direct as N
    return N


class IkeaNyx(_nyx_direct_class().NyxDirect if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "serve" else object):
    """nyx_direct.NyxDirect with the IKEA scene's per-frame input: every geom at body pose x local pose, every camera at
    the rig's pose; renders the requested cameras in the plugin's call order."""

    def set_state(self, xpos, xquat, poses) -> None:
        import nyx_direct as N
        s = self.scene
        bpos, bquat = xpos[s.body], xquat[s.body]
        local_pos = np.array([sl.local_pos for sl in self.slots])
        local_quat = np.array([sl.local_quat for sl in self.slots])
        pos = bpos + N.quat_rotate(bquat, local_pos)
        quat = N.quat_mul(bquat, local_quat)
        self.geom_pos[:] = pos.astype(np.float32)
        self.geom_quat[:] = quat.astype(np.float32)
        self.cam_pos[:], self.cam_quat[:] = N.camera_quats_f32([(p[:3], p[3:6], p[6:9]) for p in poses], device=self.camera_device)
        self._frames = None

    def render_cameras(self, idx: list) -> list:
        """NyxDirect.render's sequence (update, upload, update_scene_buffers, set_env_map, render_frame) for the
        requested cameras only."""
        import nyx_direct as N
        self.cuda.current()
        self.renderer.update()
        self.cuda.upload(self._dev_inputs, self._host_inputs)
        self.renderer.update_scene_buffers(self._data)
        self.renderer.set_env_map(0)
        out = []
        for i in idx:
            self.cuda.synchronize()
            ptr, shape = N._dlpack_pointer(self.renderer.render_frame(i))
            if shape != self._frame_shapes[i]:
                raise RuntimeError(f"camera {self.names[i]}: Nyx frame {shape}, expected {self._frame_shapes[i]}")
            self.cuda.copy_device(self._dev_frames + int(self._frame_offsets[i]), ptr, int(np.prod(shape)))
        self.cuda.synchronize()
        self.cuda.download(self._dev_frames, self._host_frames)
        for i in idx:
            out.append(self._host_frames[self._frame_offsets[i]:self._frame_offsets[i + 1]].reshape(self._frame_shapes[i]).copy())
        return out


if __name__ == "__main__" and len(sys.argv) > 2 and sys.argv[1] == "serve":
    sys.exit(_serve(sys.argv[2]))
