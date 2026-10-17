"""Camera rig of the IKEA MuJoCo standard-mode service (scripts/ikea_mujoco/standard/, copied unchanged into every
tasks/ikea-<task>-i00-standard/environment/sim/): ALOHA-style cameras added at service start WITHOUT touching the model.

The cameras are not model cameras. RGB is drawn by Nyx (ikea_nyx.py, RoboARC's renderer) at this rig's poses; depth (and
RGB under RCB_RENDER=egl, tests only) by MuJoCo's own renderer (mujoco.Renderer, EGL). Both read a scratch MjData that holds a copy of the live joint positions (mj_kinematics + mj_camlight on the copy), and the OpenGL camera of
the render scene is set to the rig camera's pose and field of view. The live MjData is only read (qpos, mocap), so
rendering can never change the physics.

rig.json (per task): {"width": 848, "height": 480, "cameras": {name: mount}} with mounts
    {"type": "static", "pos": [x, y, z], "lookat": [x, y, z], "fovy": deg}                      MuJoCo world frame
    {"type": "link", "body": b, "pos": [..], "lookat": [..], "up": [..], "fovy": deg}           b's body frame
    {"type": "link", "camera": c, "fovy": deg}                                                   at model camera c's pose
Conventions: intrinsic_cv = [[f, 0, cx], [0, f, cy], [0, 0, 1]] with f = (H / 2) / tan(fovy / 2), cx = W / 2 - 0.5,
cy = H / 2 - 0.5 (OpenCV pixel centres); extrinsic_cv = world -> camera (3, 4), OpenCV axes (x right, y down, z
forward); cam2world_gl = camera -> world (4, 4), OpenGL axes (x right, y up, z backward). Depth is z-depth (m) along the
optical axis, pixel-aligned with the RGB. Everything here is in the scene's MuJoCo world frame (internal to the sim
service): server.py re-expresses every extrinsic, cam2world and static mount in the robot frame before it leaves."""
from __future__ import annotations
import math

import numpy as np
import mujoco


def _unit(v) -> np.ndarray:
    v = np.asarray(v, dtype=np.float64)
    return v / max(1e-12, float(np.linalg.norm(v)))


def _frame(fwd, up) -> np.ndarray:
    """Rows: right, down, forward (world -> OpenCV camera rotation) from a forward and an approximate up vector."""
    f = _unit(fwd)
    r = np.cross(f, _unit(up))
    if np.linalg.norm(r) < 1e-6:
        r = np.cross(f, [1.0, 0.0, 0.0] if abs(f[0]) < 0.9 else [0.0, 1.0, 0.0])
    r = _unit(r)
    u = np.cross(r, f)
    return np.stack([r, -u, f])


class Rig:
    def __init__(self, model, rig: dict):
        self.m = model
        self.W, self.H = int(rig.get("width", 848)), int(rig.get("height", 480))
        self.mounts = dict(rig["cameras"])
        self.names = list(self.mounts)
        self.kd = mujoco.MjData(model)               # scratch copy: observation only
        self.renderer = None
        self.near = float(model.vis.map.znear * model.stat.extent)
        self.far = float(model.vis.map.zfar * model.stat.extent)
        for n, c in self.mounts.items():
            if c["type"] == "link":
                if "camera" in c:
                    cid = model.camera(c["camera"]).id
                    c["_body"] = int(model.cam_bodyid[cid])
                    # model camera axes (x right, y up, -z forward) in its body frame
                    Rm = np.zeros(9); mujoco.mju_quat2Mat(Rm, model.cam_quat[cid]); Rm = Rm.reshape(3, 3)
                    c["_p"] = model.cam_pos[cid].copy(); c["_f"] = -Rm[:, 2]; c["_u"] = Rm[:, 1]
                    c["body"] = model.body(c["_body"]).name
                else:
                    c["_body"] = int(model.body(c["body"]).id)
                    p = np.asarray(c["pos"], dtype=np.float64)
                    c["_p"] = p; c["_f"] = _unit(np.asarray(c["lookat"], dtype=np.float64) - p); c["_u"] = _unit(c.get("up", [0, 0, 1]))
        self._t = None
        self._pose: dict = {}

    # ---- poses
    def update(self, data, key=None) -> None:
        """Copy the live joint positions into the scratch data and run its kinematics (once per `key`)."""
        if key is not None and key == self._t:
            return
        kd = self.kd
        kd.qpos[:] = data.qpos
        if self.m.nmocap:
            kd.mocap_pos[:] = data.mocap_pos; kd.mocap_quat[:] = data.mocap_quat
        mujoco.mj_kinematics(self.m, kd); mujoco.mj_comPos(self.m, kd); mujoco.mj_camlight(self.m, kd)
        self._t = key; self._pose = {}

    def pose(self, name) -> tuple[np.ndarray, np.ndarray]:
        """(camera position (3,), world -> OpenCV camera rotation (3, 3)) at the last update()."""
        if name in self._pose:
            return self._pose[name]
        c = self.mounts[name]
        if c["type"] == "static":
            p = np.asarray(c["pos"], dtype=np.float64)
            R = _frame(np.asarray(c["lookat"], dtype=np.float64) - p, c.get("up", [0, 0, 1]))
        else:
            b = c["_body"]; xp = self.kd.xpos[b]; xm = self.kd.xmat[b].reshape(3, 3)
            p = xp + xm @ c["_p"]
            R = _frame(xm @ c["_f"], xm @ c["_u"])
        self._pose[name] = (p, R)
        return p, R

    def fovy(self, name) -> float:
        return float(self.mounts[name].get("fovy", 58.0))

    def intrinsic_cv(self, name) -> list:
        f = (self.H / 2.0) / math.tan(math.radians(self.fovy(name)) / 2.0)
        return [[f, 0.0, self.W / 2.0 - 0.5], [0.0, f, self.H / 2.0 - 0.5], [0.0, 0.0, 1.0]]

    def extrinsic_cv(self, name) -> np.ndarray:
        p, R = self.pose(name)
        return np.concatenate([R, (-R @ p)[:, None]], axis=1)

    def cam2world_gl(self, name) -> np.ndarray:
        p, R = self.pose(name)
        T = np.eye(4)
        T[:3, 0] = R[0]; T[:3, 1] = -R[1]; T[:3, 2] = -R[2]; T[:3, 3] = p
        return T

    def mount_info(self, name) -> dict:
        c = self.mounts[name]
        if c["type"] == "static":
            return {"type": "static", "extrinsic_cv": self.extrinsic_cv(name).tolist()}
        Rl = _frame(c["_f"], c["_u"])
        T = np.eye(4); T[:3, :3] = Rl.T; T[:3, 3] = c["_p"]
        return {"type": "link", "parent_link": c["body"], "T_link_from_camera_cv": T.tolist(),
                "note": "camera pose (OpenCV axes) in the parent link's frame"}

    # ---- images
    def _scene(self, name) -> None:
        if self.renderer is None:
            self.renderer = mujoco.Renderer(self.m, self.H, self.W)
            self._free = mujoco.MjvCamera()
        r = self.renderer
        r.update_scene(self.kd, camera=self._free)
        p, R = self.pose(name)
        top = self.near * math.tan(math.radians(self.fovy(name)) / 2.0)
        for gl in r.scene.camera:
            gl.pos[:] = p; gl.forward[:] = R[2]; gl.up[:] = -R[1]
            gl.frustum_near = self.near; gl.frustum_far = self.far
            gl.frustum_top = top; gl.frustum_bottom = -top; gl.frustum_center = 0.0; gl.orthographic = 0

    def rgb(self, name) -> np.ndarray:
        self._scene(name)
        return self.renderer.render().copy()

    def depth(self, name) -> np.ndarray:
        """z-depth (H, W) float32 m, MuJoCo's raster (0 = no reading); the RGB comes from Nyx (ikea_nyx.py)."""
        self._scene(name)
        r = self.renderer
        r.enable_depth_rendering()
        try:
            z = r.render().astype(np.float32).copy()
        finally:
            r.disable_depth_rendering()
        z[z >= 0.999 * self.far] = 0.0               # nothing hit: no reading
        return z

    def rgbd(self, name) -> tuple[np.ndarray, np.ndarray]:
        self._scene(name)
        r = self.renderer
        img = r.render().copy()
        r.enable_depth_rendering()
        try:
            z = r.render().astype(np.float32).copy()
        finally:
            r.disable_depth_rendering()
        z[z >= 0.999 * self.far] = 0.0               # nothing hit: no reading
        return img, z
