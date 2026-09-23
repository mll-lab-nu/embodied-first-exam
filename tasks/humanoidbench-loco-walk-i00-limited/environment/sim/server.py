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

# HumanoidBench's own non-privileged sensors (humanoid_bench/wrappers.py, ObservationWrapper): `image` renders
# these two head cameras; `proprio` is the robot's joint angles and velocities, without the root pose.
CAMERAS = ("left_eye_camera", "right_eye_camera")


def png_b64(img: np.ndarray) -> str:
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(np.ascontiguousarray(img)).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


class HumanoidBench:
    """One frozen HumanoidBench instance behind the rcb_service.Sim contract. The agent never gets the root
    pose, object or goal state, or the reward -- the reward is live here only so the service can judge."""

    def __init__(self, task: str | None, instance: str, *, proprio: bool = True, imu: bool = False,
                 room_camera: bool = False, task_text: str = ""):
        self.s = Session(task, instance=instance, enable_render=True)
        if not self.s.scored:
            raise RuntimeError("the reward was not restored: this service could not judge success")
        self.proprio, self.imu, self.task_text, self._acts = proprio, imu, task_text, []
        self.robot, m = self.s.low.robot, self.s.model
        assert m.jnt_type[0] == mujoco.mjtJoint.mjJNT_FREE and m.body(int(m.jnt_bodyid[0])).name == "pelvis"
        self.joints = [m.joint(j).name for j in range(m.njnt) if 7 <= m.jnt_qposadr[j] < self.robot.dof]
        self.cameras = CAMERAS + (("room_camera",) if room_camera else ())
        self._room = self._frozen_camera(self.s.low.camera_name or "cam_default") if room_camera else None
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

    def _render(self, camera: str) -> np.ndarray:
        r = self.s.low.mujoco_renderer
        if camera != "room_camera":
            return r.render("rgb_array", camera_name=camera)
        cam = r.viewer.cam                                            # the viewer exists: __init__ rendered once
        cam.lookat[:], cam.distance, cam.azimuth, cam.elevation = self._room
        return r.render("rgb_array", camera_id=-1)                   # -1 = the free camera just set

    def _imu(self) -> dict:
        """What an IMU on the pelvis reads, noise-free: the angular velocity in the pelvis frame (the root free
        joint's qvel[3:6] already is that), and the gravity direction in that frame (tilt, not heading)."""
        rot = np.zeros(9); mujoco.mju_quat2Mat(rot, self.s.data.qpos[3:7])
        return {"gyro": self.s.data.qvel[3:6].tolist(), "gravity": (rot.reshape(3, 3).T @ [0.0, 0.0, -1.0]).tolist()}

    def spec(self) -> dict:
        m = self.s.model
        return {
            "simulator": "humanoidbench", "robot": self.s.env_id.split("-")[0], "task_text": self.task_text,
            "action_types": ["qpos"],
            "qpos": {"dim": self.s.nu, "layout": [m.actuator(i).name for i in range(self.s.nu)], "limits": [-1.0, 1.0],
                     "units": "position-servo targets, normalised to [-1, 1] per actuator (HumanoidBench's action space)"},
            "control_hz": round(1 / self.s.low.dt), "max_episode_steps": self.s.max_steps,
            "proprio": {"joints": self.joints, "units": "joint_pos rad, joint_vel rad/s"} if self.proprio else None,
            "imu": {"mounted": "pelvis", "gyro": "angular velocity, rad/s, pelvis frame",
                    "gravity": "unit gravity direction, pelvis frame"} if self.imu else None,
            "cameras": {c: {"mounted": "room (fixed)" if c == "room_camera" else "head", "rgb": True, "depth": False,
                            "hw": self.image_hw} for c in self.cameras},
            "gl_backend": GL_BACKEND,
        }

    def observe(self, cameras: list[str]) -> dict:
        obs = {"images": {c: png_b64(self._render(c)) for c in cameras}}
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
    sim = HumanoidBench(env("RCB_TASK"), env("RCB_INSTANCE", "/srv/instance.npz"),
                        proprio=env("RCB_OBS_PROPRIO", "1") == "1", imu=env("RCB_OBS_IMU", "0") == "1",
                        room_camera=env("RCB_OBS_ROOM_CAMERA", "0") == "1", task_text=env("RCB_TASK_TEXT", ""))
    Service(sim, reset_budget=int(env("RCB_RESET_BUDGET", "0")),
            wall_clock_s=float(env("RCB_WALL_CLOCK_S", "3600"))).serve(8000)
