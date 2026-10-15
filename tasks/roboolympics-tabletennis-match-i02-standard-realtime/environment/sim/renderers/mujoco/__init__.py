"""The default renderer: MuJoCo's own rasterizer (CPU with MUJOCO_GL=osmesa, GPU with egl), real time.

The scene is compiled once from its MJCF text with spare world-body cameras added; each CameraDef is drawn by
setting one spare camera's pose and vertical field of view exactly (cam_pos / cam_quat / cam_fovy), so the picture
follows CameraDef.project to the pixel. The renderer keeps its own MjModel / MjData: the match's world is never
touched. A presentation scene (Scene.match set; spectators only) is drawn only when its kinematics equal the match
scene's (scene_check.same_kinematics); every renderer built on this one inherits the check."""
from __future__ import annotations

import numpy as np

from ..base import CameraDef, Renderer, RendererUnavailable, Scene, as_cameras

SPARE = "_ro_cam"


def camera_quat(cam: CameraDef):
    """MuJoCo camera frame: x = image right, y = image up, looking along -z."""
    import mujoco as mj
    right, up, fwd = cam.basis()
    R = np.column_stack([right, up, -fwd])
    q = np.zeros(4)
    mj.mju_mat2Quat(q, R.reshape(-1))
    return q


def compile_spec(spec, n_cams: int, size):
    """Add n spare cameras and make the off-screen buffer at least `size` (w, h); returns the compiled model."""
    g = spec.visual.global_
    g.offwidth, g.offheight = max(int(g.offwidth), int(size[0])), max(int(g.offheight), int(size[1]))
    for i in range(n_cams):
        spec.worldbody.add_camera(name=f"{SPARE}{i}", pos=[0, 0, 0], quat=[1, 0, 0, 0], fovy=45)
    return spec.compile()


def load_spec(scene: Scene):
    import mujoco as mj
    if scene.engine != "mujoco":
        raise RendererUnavailable("mujoco", f"scene engine {scene.engine!r} is not MJCF")
    return mj.MjSpec.from_string(scene.xml, assets=dict(scene.assets or {}))


class MujocoRenderer(Renderer):
    name = "mujoco"
    title = "MuJoCo"
    realtime = True
    needs_gpu = False
    label = None                           # the competition picture: no tag

    def __init__(self, scene: Scene, n_cams: int = 8, size=(640, 480), **opts):
        super().__init__(scene, **opts)
        try:
            import mujoco  # noqa: F401
        except ImportError as exc:                     # pragma: no cover - the sim images have it
            raise RendererUnavailable(self.name, "the mujoco Python package is missing", "mujoco") from exc
        self._n, self._size = int(n_cams), tuple(size)
        self._build()

    # ---------------------------------------------------------------- model
    def make_spec(self):
        """The MjSpec to draw (subclasses change only visual properties)."""
        return load_spec(self.scene)

    def _build(self):
        import mujoco as mj
        self.close()
        self.m = compile_spec(self.make_spec(), self._n, self._size)
        if self.scene.match is not None:                # a presentation scene: same kinematics as the match scene
            from ..scene_check import same_kinematics
            bad = same_kinematics(compile_spec(load_spec(self.scene.match), self._n, self._size), self.m)
            if bad:
                raise RuntimeError(f"{self.name}: the presentation scene's kinematics differ from the match scene: "
                                   f"{bad[:8]}")
        self.d = mj.MjData(self.m)
        self.cam_ids = [self.m.camera(f"{SPARE}{i}").id for i in range(self._n)]
        self._r = {}

    def _renderer(self, w, h):
        import mujoco as mj
        if (w, h) not in self._r:
            self._r[w, h] = mj.Renderer(self.m, height=h, width=w)
        return self._r[w, h]

    def set_state(self, state: dict):
        import mujoco as mj
        m, d = self.m, self.d
        q = np.asarray(state.get("qpos", d.qpos), dtype=float)
        if q.shape != (m.nq,):
            raise ValueError(f"state qpos has {q.size} values, the scene has nq={m.nq}")
        d.qpos[:] = q
        if m.nmocap:
            if "mocap_pos" in state:
                d.mocap_pos[:] = np.asarray(state["mocap_pos"], float).reshape(m.nmocap, 3)
            if "mocap_quat" in state:
                d.mocap_quat[:] = np.asarray(state["mocap_quat"], float).reshape(m.nmocap, 4)
        mj.mj_kinematics(m, d)
        mj.mj_comPos(m, d)
        mj.mj_camlight(m, d)

    # ---------------------------------------------------------------- drawing
    def render(self, state: dict, cameras: list) -> list:
        import mujoco as mj
        cams = as_cameras(cameras)
        w_max, h_max = max([c.width for c in cams] + [1]), max([c.height for c in cams] + [1])
        if len(cams) > self._n or w_max > self.m.vis.global_.offwidth or h_max > self.m.vis.global_.offheight:
            self._n = max(self._n, len(cams))
            self._size = (max(self._size[0], w_max), max(self._size[1], h_max))
            self._build()
        self.set_state(state)
        for cam, cid in zip(cams, self.cam_ids):
            self.m.cam_pos[cid] = cam.pos
            self.m.cam_quat[cid] = camera_quat(cam)
            self.m.cam_fovy[cid] = cam.fovy_deg
        mj.mj_camlight(self.m, self.d)                 # camera world poses from the new cam_pos / cam_quat
        self._clip(cams)
        out = []
        for cam, cid in zip(cams, self.cam_ids):
            r = self._renderer(cam.width, cam.height)
            r.update_scene(self.d, camera=cid)
            out.append(self.post(np.array(r.render(), dtype=np.uint8, copy=True), cam))
        return out

    def _clip(self, cams):
        """MuJoCo clips at zfar * stat.extent: keep every geom of the current state inside every camera's far plane
        (a small scene seen from afar, or a body far from the scene centre, would otherwise vanish). Visualization
        only, on our own model copy."""
        m, d = self.m, self.d
        ext = max(float(m.stat.extent), 1e-6)
        pts = np.asarray(d.geom_xpos) if m.ngeom else np.zeros((1, 3))
        rb = float(np.max(m.geom_rbound)) if m.ngeom else 0.0
        reach = max(float(np.max(np.linalg.norm(pts - np.asarray(c.pos), axis=1))) for c in cams) + rb
        if m.vis.map.zfar * ext < 1.05 * reach:
            m.vis.map.zfar = 1.05 * reach / ext

    def post(self, img, cam):
        return img

    def close(self):
        for r in getattr(self, "_r", {}).values():
            r.close()
        self._r = {}


RENDERER = MujocoRenderer
