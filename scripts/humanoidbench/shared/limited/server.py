"""rcb-limited/1.1 sim service for HumanoidBench -- the sidecar's entry point (`python /srv/server.py`).

The simulator-specific half only: `HumanoidBench` implements rcb_service.Sim for one frozen instance. The
protocol, episode bookkeeping, batching and the finalize live in rcb_service.py, which imports no simulator.
Settings come from environment/docker-compose.yaml:
  RCB_TASK, RCB_INSTANCE   which HumanoidBench task, which frozen scene (the unlimited twin's instance)
  RCB_TASK_TEXT            one sentence for /spec
  RCB_RESET_BUDGET         resets allowed (default 0: one episode, as on a real robot)
  RCB_OBS_PROPRIO          1 (default): images + joint proprioception; 0: images only
  RCB_OBS_IMU              0 (default); 1: + a pelvis IMU (angular velocity, gravity direction)
  RCB_OBS_ROOM_CAMERA      0 (default); 1: + `room_camera`, a camera fixed in the room
  RCB_OBS_DEPTH            0 (default); 1: + depth with each head-camera image, as from an RGB-D camera
  RCB_ROOM_CAMERA_POSE     where it stands, "lookat_x,lookat_y,lookat_z,distance,azimuth,elevation" (a MuJoCo free
                           camera, metres and degrees); empty (default): the recording camera frozen at t=0
  RCB_IMAGE_HW             the side of every camera's image in pixels; empty (default): upstream's 256
"""
from __future__ import annotations

import base64
import io
import math
import os
import sys

import mujoco
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rcb_rewards import restore  # noqa: E402

restore()  # the scoring formula lives in this sidecar only, and must be back before a Session is opened
from rcb_hb import GL_BACKEND, Session  # noqa: E402
from rcb_service import Service  # noqa: E402
from humanoid_bench.tasks import Task  # noqa: E402

# HumanoidBench's own non-privileged sensors (humanoid_bench/wrappers.py, ObservationWrapper): `image` renders
# these two head cameras; `proprio` is the robot's joint angles and velocities, without the root pose.
CAMERAS = ("left_eye_camera", "right_eye_camera")
# The head cameras' near plane. MuJoCo's default is 1% of the scene's extent (5.5 cm in door), and the crouch agents
# brace against the door puts an eye 4 cm from it: the door was clipped away and the eye saw the floor behind it.
HEAD_NEAR_M = 0.01
DEPTH_MAX_M = 10.0   # how far the depth reaches (a RealSense D435i, the H1's head RGB-D camera, reads to about 10 m)


def png_b64(img: np.ndarray) -> str:
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(np.ascontiguousarray(img)).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def depth_png_b64(depth_m: np.ndarray) -> str:
    """Depth as a 16-bit greyscale PNG in millimetres, 0 where nothing is in range (an RGB-D camera's z16)."""
    return png_b64(np.clip(np.rint(depth_m * 1000), 0, 65535).astype(np.uint16))


class HumanoidBench:
    """One frozen HumanoidBench instance behind the rcb_service.Sim contract. The agent never gets the root
    pose, object or goal state, or the reward -- the reward is live here only so the service can judge."""

    def __init__(self, task: str | None, instance: str, *, proprio: bool = True, imu: bool = False,
                 room_camera: bool = False, room_pose: tuple | None = None, depth: bool = False, task_text: str = "",
                 image_hw: int | None = None):
        self.s = Session(task, instance=instance, enable_render=True, image_hw=image_hw)
        if not self.s.scored:
            raise RuntimeError("the reward was not restored: this service could not judge success")
        self.proprio, self.imu, self.depth, self.task_text, self._acts = proprio, imu, depth, task_text, []
        self._depth_renderer = None
        self.robot, m = self.s.low.robot, self.s.model
        assert m.jnt_type[0] == mujoco.mjtJoint.mjJNT_FREE and m.body(int(m.jnt_bodyid[0])).name == "pelvis"
        self.joints = [m.joint(j).name for j in range(m.njnt) if 7 <= m.jnt_qposadr[j] < self.robot.dof]
        # reach and push override upstream's Task.render() to draw their goal as a marker; every image here goes
        # through the same viewer, so running that hook puts the goal in the head and room cameras too.
        self._marks = type(self.s.low.task).render is not Task.render
        self.cameras = CAMERAS + (("room_camera",) if room_camera else ())
        self._room = (room_pose or self._frozen_camera(self.s.low.camera_name or "cam_default")) if room_camera else None
        self._axes, self._camera_facts = self._hardware()
        self.image_hw = list(self._render(CAMERAS[0]).shape[:2])   # also warms up the GL context

    def _frozen_camera(self, name: str, dist: float = 3.0) -> tuple:
        """`room_camera`: the task's recording camera (which follows the robot) frozen where it is at the
        instance's initial state -- a tripod in the room. Kept as free-camera parameters for the shared
        offscreen viewer; pixel-identical to the recording camera at t=0 (checked on sit_simple)."""
        m = self.s.model
        d = mujoco.MjData(m); d.qpos[:], d.qvel[:] = self.s.data.qpos, self.s.data.qvel
        mujoco.mj_forward(m, d)                                       # a scratch copy: the live sim is untouched
        c = m.camera(name).id; fwd = -d.cam_xmat[c].reshape(3, 3)[:, 2]
        return d.cam_xpos[c] + dist * fwd, dist, math.degrees(math.atan2(fwd[1], fwd[0])), math.degrees(math.asin(fwd[2]))

    def _hardware(self) -> tuple[list, dict]:
        """What a real robot's documentation gives, read off the model: each joint's axis and each head camera's
        pose in the pelvis frame with every joint at 0, and where room_camera stands in the robot's starting
        frame (origin on the floor under the pelvis at t = 0, x the way the robot faces then, z up)."""
        m, r3 = self.s.model, lambda v: [round(float(x), 3) for x in v]
        d = mujoco.MjData(m)
        d.qpos[:] = m.qpos0
        d.qpos[7:self.robot.dof] = 0                                  # a scratch copy: the live sim is untouched
        mujoco.mj_forward(m, d)
        pelvis = m.body("pelvis").id
        R, p = d.xmat[pelvis].reshape(3, 3), d.xpos[pelvis]
        axes = [r3(R.T @ d.xaxis[m.joint(n).id]) for n in self.joints]
        cams = {}
        for c in CAMERAS:
            i, C = m.camera(c).id, d.cam_xmat[m.camera(c).id].reshape(3, 3)   # a camera looks down its -z
            cams[c] = {"fovy_deg": round(float(m.cam_fovy[i]), 1),
                       "pose": {"frame": "pelvis (x forward, y left, z up), every joint at 0",
                                "position_m": r3(R.T @ (d.cam_xpos[i] - p)), "forward": r3(R.T @ -C[:, 2]),
                                "up": r3(R.T @ C[:, 1]), "right": r3(R.T @ C[:, 0])}}   # right: the image's +x
        if self._room is not None:
            lookat, dist, az, el = self._room
            a, e = math.radians(az), math.radians(el)                 # MuJoCo's free camera, as the viewer places it
            fwd = np.array([math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)])
            up = np.array([-math.sin(e) * math.cos(a), -math.sin(e) * math.sin(a), math.cos(e)])
            x0, R0 = self.s.data.xpos[pelvis], self.s.data.xmat[pelvis].reshape(3, 3)
            yaw = math.atan2(R0[1, 0], R0[0, 0])
            Y = np.array([[math.cos(yaw), -math.sin(yaw), 0], [math.sin(yaw), math.cos(yaw), 0], [0, 0, 1]])
            cams["room_camera"] = {"fovy_deg": round(float(m.vis.global_.fovy), 1), "pose": {
                "frame": "the robot's start: origin on the floor under the pelvis at t = 0, x the way it faces, y left, z up",
                "position_m": r3(Y.T @ (np.asarray(lookat) - dist * fwd - [x0[0], x0[1], 0])),
                "forward": r3(Y.T @ fwd), "up": r3(Y.T @ up), "right": r3(Y.T @ np.cross(fwd, up))}}
        return axes, cams

    def _render(self, camera: str) -> np.ndarray:
        r = self.s.low.mujoco_renderer
        if self._marks:
            if r.viewer is None or not r.viewer._markers:
                self.s.low.task.render()                              # adds the marker, which the viewer keeps
            for mk in r.viewer._markers:                              # and, like that hook on every call, puts it on the
                if mk["objid"] == 789:                                # goal: a reset gives task.goal a new array (push's
                    mk["pos"] = self.s.low.task.goal                  # reset_model first rewrites the old one in place)
        if camera != "room_camera":
            vis, znear = self.s.model.vis.map, self.s.model.vis.map.znear
            vis.znear = min(znear, HEAD_NEAR_M / self.s.model.stat.extent)   # the room camera keeps the default
            try:
                return r.render("rgb_array", camera_name=camera)
            finally:
                vis.znear = znear
        cam = r.viewer.cam                                            # the viewer exists: __init__ rendered once
        cam.lookat[:], cam.distance, cam.azimuth, cam.elevation = self._room
        return r.render("rgb_array", camera_id=-1)                   # -1 = the free camera just set

    def _depth(self, camera: str) -> np.ndarray:
        """What an RGB-D camera in a head camera's place reads, noise-free: metres along its forward axis (planar
        depth), pixel for pixel with its image; 0 where nothing is within DEPTH_MAX_M. MuJoCo's own renderer:
        the viewer's gives no metric depth, and its markers (reach's and push's goal) are pictures, not things."""
        m = self.s.model
        if self._depth_renderer is None:
            self._depth_renderer = mujoco.Renderer(m, *self.image_hw)
            self._depth_renderer.enable_depth_rendering()
        vis, znear = m.vis.map, m.vis.map.znear
        vis.znear = min(znear, HEAD_NEAR_M / m.stat.extent)           # as the head cameras' images
        try:
            self._depth_renderer.update_scene(self.s.data, camera=camera)
            d = self._depth_renderer.render()
        finally:
            vis.znear = znear
            self.s.low.mujoco_renderer.viewer.make_context_current()  # the viewer's GL context again, for its images
        return np.where(d < DEPTH_MAX_M, d, 0.0)

    def _imu(self) -> dict:
        """What an IMU on the pelvis reads, noise-free: the angular velocity in the pelvis frame (the root free
        joint's qvel[3:6] already is that), and the gravity direction in that frame (tilt, not heading)."""
        rot = np.zeros(9); mujoco.mju_quat2Mat(rot, self.s.data.qpos[3:7])
        return {"gyro": self.s.data.qvel[3:6].tolist(), "gravity": (rot.reshape(3, 3).T @ [0.0, 0.0, -1.0]).tolist()}

    def spec(self) -> dict:
        m = self.s.model
        tendons = any(m.actuator_trntype[i] == mujoco.mjtTrn.mjTRN_TENDON for i in range(self.s.nu))
        return {
            "simulator": "humanoidbench", "robot": self.s.env_id.split("-")[0], "task_text": self.task_text,
            "action_types": ["qpos"],
            # HumanoidBench's action space: each value maps linearly onto the actuator's ctrlrange (Task.step)
            "qpos": {"dim": self.s.nu, "layout": [m.actuator(i).name for i in range(self.s.nu)], "limits": [-1.0, 1.0],
                     "range": [[round(float(lo), 4), round(float(hi), 4)] for lo, hi in m.actuator_ctrlrange[:self.s.nu]],
                     "units": "position-servo targets: -1 and +1 command the two ends of the actuator's range (rad), "
                              "linearly, so 0 is mid-range, not 0 rad" + ("; a tendon actuator's range is the summed "
                                                                          "angle of the two joints it moves" if tendons else "")},
            "control_hz": round(1 / self.s.low.dt), "max_episode_steps": self.s.max_steps,
            "proprio": {"joints": self.joints, "units": "joint_pos rad, joint_vel rad/s", "axis": self._axes,
                        "axis_frame": "the joint's rotation axis in the pelvis frame, every joint at 0; a positive "
                                      "angle turns the joint's child link about it by the right-hand rule: about an axis "
                                      "near +y (left), a link hanging below the joint swings backward"}
            if self.proprio else None,
            "imu": {"mounted": "pelvis", "frame": "pelvis: x forward, y left, z up",
                    "gyro": "angular velocity, rad/s, pelvis frame, right-hand rule: y > 0 while pitching forward "
                            "(nose down), x > 0 while rolling to the right, z > 0 while turning left",
                    "gravity": "unit gravity direction, pelvis frame: (0, 0, -1) when upright; it tips toward the way "
                               "the pelvis leans: x > 0 leaning forward, y > 0 leaning left"} if self.imu else None,
            "cameras": {c: {"mounted": "room (fixed)" if c == "room_camera" else "head", "rgb": True,
                            "depth": self.depth and c in CAMERAS, "hw": self.image_hw, **self._camera_facts[c]} for c in self.cameras},
            "depth": {"cameras": list(CAMERAS), "units": "metres along the camera's forward axis (planar depth, as an RGB-D "
                      "camera reports it), pixel for pixel with that camera's image; noise-free",
                      "range_m": [HEAD_NEAR_M, DEPTH_MAX_M], "nothing_in_range": 0.0} if self.depth else None,
            "gl_backend": GL_BACKEND,
        }

    def observe(self, cameras: list[str]) -> dict:
        obs = {"images": {c: png_b64(self._render(c)) for c in cameras}}
        if self.depth and (heads := [c for c in cameras if c in CAMERAS]):
            obs["depth"] = {c: depth_png_b64(self._depth(c)) for c in heads}
        if self.proprio:
            obs["proprio"] = {"joint_pos": self.robot.joint_angles().tolist(),
                              "joint_vel": self.robot.joint_velocities().tolist()}
        if self.imu:
            obs["imu"] = self._imu()
        return obs

    def validate(self, typ: str, a: np.ndarray) -> str | None:
        if typ != "qpos":
            return "type must be 'qpos'"
        if a.shape[0] != self.s.nu:
            return f"qpos action must have {self.s.nu} values"
        if np.abs(a).max() > 1 + 1e-6:
            return "qpos values must be in [-1, 1]"
        return None

    def apply(self, typ: str, a: np.ndarray) -> tuple[bool, bool, dict]:
        done = self.s.step(a)[2]
        self._acts.append(a)
        return done, self.s.status()["success"], {}

    def reset(self) -> None:
        self.s.reset()
        self._acts = []

    def actions(self) -> np.ndarray:
        return np.asarray(self._acts, dtype=np.float64).reshape(-1, self.s.nu)

    def state_sha(self) -> str:
        return self.s.state_sha()

    def save_trajectory(self, actions: np.ndarray, path: str, meta: dict) -> None:
        self.s.save_trajectory(actions, path, meta)

    def replay(self, actions: np.ndarray) -> dict:
        st = self.s.replay(actions)
        return {"success": st["success"], "state_sha": st["state_sha"]}

    def render_video(self, actions: np.ndarray, path: str) -> None:
        self.s.render_video(actions, path, every=5, fps=20)


if __name__ == "__main__":
    env = os.environ.get
    pose = [float(v) for v in env("RCB_ROOM_CAMERA_POSE", "").split(",") if v.strip()]
    if pose and len(pose) != 6:
        raise SystemExit("RCB_ROOM_CAMERA_POSE needs 6 numbers: lookat_x,lookat_y,lookat_z,distance,azimuth,elevation")
    sim = HumanoidBench(env("RCB_TASK"), env("RCB_INSTANCE", "/srv/instance.npz"),
                        proprio=env("RCB_OBS_PROPRIO", "1") == "1", imu=env("RCB_OBS_IMU", "0") == "1",
                        room_camera=env("RCB_OBS_ROOM_CAMERA", "0") == "1", depth=env("RCB_OBS_DEPTH", "0") == "1",
                        room_pose=(np.array(pose[:3]), *pose[3:]) if pose else None, task_text=env("RCB_TASK_TEXT", ""),
                        image_hw=int(env("RCB_IMAGE_HW") or 0) or None)
    Service(sim, reset_budget=int(env("RCB_RESET_BUDGET", "0"))).serve(8000)
