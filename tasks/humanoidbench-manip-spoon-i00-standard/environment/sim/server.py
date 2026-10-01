"""eai-standard/2.1 sim service for HumanoidBench -- the sidecar's entry point (`python /srv/server.py`).

The simulator-specific half only: `HumanoidBench` implements rcb_service.Sim for one frozen instance. The protocol,
the episode, crash recovery and the finalize live in rcb_service.py, which imports no simulator.
Settings come from environment/docker-compose.yaml:
  RCB_TASK, RCB_INSTANCE   which HumanoidBench task, which frozen scene (the privileged twin's instance)
  RCB_TASK_TEXT            one sentence for /spec
  RCB_EPISODE              what ends an episode, for /spec (the instruction's words)
  RCB_OBS_PROPRIO          1 (standard): + joint angles and velocities; 0: images only
  RCB_OBS_IMU              1 (standard): + a pelvis IMU (angular velocity, gravity direction)
  RCB_OBS_ROOM_CAMERA      1 (standard): + `room_camera`, a camera fixed in the room
  RCB_OBS_DEPTH            0 (standard); 1: + depth from both head cameras, as from an RGB-D camera
  RCB_ROOM_CAMERA_POSE     where room_camera stands, "lookat_x,lookat_y,lookat_z,distance,azimuth,elevation" (a MuJoCo
                           free camera, metres and degrees); empty: the recording camera frozen at t=0
  RCB_IMAGE_HW             the side of every camera's image in pixels; empty: upstream's 256
  RCB_RESET_BUDGET, RCB_WALL_CLOCK_S, RCB_DATA   the service's own (rcb_service.main)
"""
from __future__ import annotations

import itertools
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# rcb_hb first: it picks MuJoCo's GL backend, which `import mujoco` binds once per process. Imported after it, the
# depth renderer's context ended up inside the viewer's and head-camera images came back as another camera's.
from rcb_hb import GL_BACKEND, Session  # noqa: E402
import mujoco  # noqa: E402
from rcb_rewards import restore  # noqa: E402

restore()  # the scoring formula lives in this sidecar only, and must be back before a Session is opened
from rcb_service import main  # noqa: E402
from humanoid_bench.tasks import Task  # noqa: E402

# HumanoidBench's own non-privileged sensors (humanoid_bench/wrappers.py, ObservationWrapper): `image` renders
# these two head cameras; `proprio` is the robot's joint angles and velocities, without the root pose.
CAMERAS = ("left_eye_camera", "right_eye_camera")
# The head cameras' near plane. MuJoCo's default is 1% of the scene's extent (5.5 cm in door), and the crouch agents
# brace against the door puts an eye 4 cm from it: the door was clipped away and the eye saw the floor behind it.
HEAD_NEAR_M = 0.01
DEPTH_MAX_M = 10.0   # how far the depth reaches (a RealSense D435i, the H1's head RGB-D camera, reads to about 10 m)
IMU = ("imu_gyro_x", "imu_gyro_y", "imu_gyro_z", "imu_gravity_x", "imu_gravity_y", "imu_gravity_z")


class HumanoidBench:
    """One frozen HumanoidBench instance behind the rcb_service.Sim contract. The agent never gets the root pose,
    object or goal state, or the reward -- the reward is live here only so the service can judge."""

    def __init__(self, task: str | None, instance: str, *, proprio: bool = True, imu: bool = False,
                 room_camera: bool = False, room_pose: tuple | None = None, depth: bool = False, task_text: str = "",
                 episode: str = "", image_hw: int | None = None):
        self.task, self.instance = task, instance
        self.s = Session(task, instance=instance, enable_render=True, image_hw=image_hw)
        if not self.s.scored:
            raise RuntimeError("the reward was not restored: this service could not judge success")
        self.task_text, self.episode = task_text, episode
        self.robot, m = self.s.low.robot, self.s.model
        assert m.jnt_type[0] == mujoco.mjtJoint.mjJNT_FREE and m.body(int(m.jnt_bodyid[0])).name == "pelvis"
        self.joints = [m.joint(j).name for j in range(m.njnt) if 7 <= m.jnt_qposadr[j] < self.robot.dof]
        self.nu = self.raw_dim = int(self.s.nu)
        self.control_dt, self.max_control_steps = float(self.s.low.dt), int(self.s.max_steps)
        self.lo, self.hi = (np.asarray(v, dtype=np.float64) for v in m.actuator_ctrlrange[:self.nu].T)
        self.proprio_on, self.imu = proprio, imu
        self.proprio_layout = ([f"{j}_pos" for j in self.joints] + [f"{j}_vel" for j in self.joints] if proprio else []) \
            + (list(IMU) if imu else [])
        self.depth_cameras = CAMERAS if depth else ()
        self._depth_renderer = None
        # reach and push override upstream's Task.render() to draw their goal as a marker; every image here goes
        # through the same viewer, so running that hook puts the goal in the head and room cameras too.
        self._marks = type(self.s.low.task).render is not Task.render
        self.cameras = CAMERAS + (("room_camera",) if room_camera else ())
        self._room = (room_pose or self._frozen_camera(self.s.low.camera_name or "cam_default")) if room_camera else None
        self._axes, self._anchors, self._links, self._camera_facts = self._hardware()
        self.image_hw = list(self._render(CAMERAS[0]).shape[:2])   # also warms up the GL context
        self.cmd = self._command_now()

    def _command_now(self) -> np.ndarray:
        """The servo targets the actuators hold now, in the action's normalised units."""
        return 2.0 * (np.asarray(self.s.data.ctrl[:self.nu], dtype=np.float64) - self.lo) / (self.hi - self.lo) - 1.0

    def _frozen_camera(self, name: str) -> tuple:
        """`room_camera`: the task's recording camera (which follows the robot) frozen where it is at the
        instance's initial state -- a tripod in the room. Kept as free-camera parameters for the shared
        offscreen viewer; pixel-identical to the recording camera at t=0 (checked on sit_simple)."""
        m = self.s.model
        d = mujoco.MjData(m); d.qpos[:], d.qvel[:] = self.s.data.qpos, self.s.data.qvel
        mujoco.mj_forward(m, d)                                       # a scratch copy: the live sim is untouched
        c, dist = m.camera(name).id, 3.0                              # the free camera orbits a point 3 m ahead
        fwd = -d.cam_xmat[c].reshape(3, 3)[:, 2]
        return d.cam_xpos[c] + dist * fwd, dist, math.degrees(math.atan2(fwd[1], fwd[0])), math.degrees(math.asin(fwd[2]))

    def _hardware(self) -> tuple[list, list, dict, dict]:
        """What a real robot's documentation (its URDF) gives, read off the model: each joint's axis and a point on
        it, each link's parent, mass and centre of mass, each foot's collision shape as a box, and each head
        camera's pose, all in the pelvis frame with every joint at 0; and where room_camera stands in the robot's
        starting frame (origin on the floor under the pelvis at t = 0, x the way the robot faces then, z up). The
        robot is the pelvis's subtree: the scene's objects are subtrees of their own, so none of them is here."""
        m, r3 = self.s.model, lambda v: [round(float(x), 3) for x in v]
        d = mujoco.MjData(m)
        d.qpos[:] = m.qpos0
        d.qpos[7:self.robot.dof] = 0                                  # a scratch copy: the live sim is untouched
        mujoco.mj_forward(m, d)
        pelvis = m.body("pelvis").id
        R, p = d.xmat[pelvis].reshape(3, 3), d.xpos[pelvis]
        axes = [r3(R.T @ d.xaxis[m.joint(n).id]) for n in self.joints]
        anchors = [r3(R.T @ (d.xanchor[m.joint(n).id] - p)) for n in self.joints]
        robot = [b for b in range(m.nbody) if m.body_rootid[b] == pelvis]

        def box(b):   # the link's colliding geoms' bounding boxes, corner by corner, in the pelvis frame
            pts = [d.geom_xpos[g] + d.geom_xmat[g].reshape(3, 3) @ (m.geom_aabb[g, :3] + m.geom_aabb[g, 3:] * np.array(c))
                   for g in range(m.ngeom) if m.geom_bodyid[g] == b and (m.geom_contype[g] or m.geom_conaffinity[g])
                   for c in itertools.product((-1, 1), repeat=3)]
            q = np.array([R.T @ (x - p) for x in pts])
            return [r3(q.min(0)), r3(q.max(0))]
        links = {"frame": "pelvis (x forward, y left, z up), every joint at 0", "names": [m.body(b).name for b in robot],
                 "parent": [None if b == pelvis else m.body(int(m.body_parentid[b])).name for b in robot],
                 "mass_kg": [round(float(m.body_mass[b]), 3) for b in robot],   # a massless link (the bare H1's hands):
                 "com_m": [r3(R.T @ ((d.xipos[b] if m.body_mass[b] > 0 else d.xpos[b]) - p)) for b in robot],   # its origin
                 "feet": {m.body(b).name: box(b) for b in robot if "ankle" in m.body(b).name},
                 "feet_units": "each foot's collision shape as a box: [min xyz, max xyz], m"}
        cams = {}
        for c in CAMERAS:
            i, C = m.camera(c).id, d.cam_xmat[m.camera(c).id].reshape(3, 3)   # a camera looks down its -z
            cams[c] = {"mounted": "head", "fovy_deg": round(float(m.cam_fovy[i]), 1),
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
            cams["room_camera"] = {"mounted": "room (fixed)", "fovy_deg": round(float(m.vis.global_.fovy), 1), "pose": {
                "frame": "the robot's start: origin on the floor under the pelvis at t = 0, x the way it faces, y left, z up",
                "position_m": r3(Y.T @ (np.asarray(lookat) - dist * fwd - [x0[0], x0[1], 0])),
                "forward": r3(Y.T @ fwd), "up": r3(Y.T @ up), "right": r3(Y.T @ np.cross(fwd, up))}}
        return axes, anchors, links, cams

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
        return np.where(d < DEPTH_MAX_M, d, 0.0).astype(np.float32)

    def _imu(self) -> list[float]:
        """What an IMU on the pelvis reads, noise-free: the angular velocity in the pelvis frame (the root free
        joint's qvel[3:6] already is that), and the gravity direction in that frame (tilt, not heading)."""
        rot = np.zeros(9); mujoco.mju_quat2Mat(rot, self.s.data.qpos[3:7])
        return [*self.s.data.qvel[3:6], *(rot.reshape(3, 3).T @ [0.0, 0.0, -1.0])]

    # ------------------------------------------------------------------ the rcb_service.Sim contract
    def spec(self) -> dict:
        m = self.s.model
        tendons = any(m.actuator_trntype[i] == mujoco.mjtTrn.mjTRN_TENDON for i in range(self.nu))
        return {
            "simulator": "humanoidbench", "robot": self.s.env_id.split("-")[0], "task_text": self.task_text,
            "episode": self.episode,
            "action_types": {"joint_position": {
                "dim": self.nu, "layout": [m.actuator(i).name for i in range(self.nu)],
                "lower": [-1.0] * self.nu, "upper": [1.0] * self.nu,
                "range_rad": [[round(float(lo), 4), round(float(hi), 4)] for lo, hi in zip(self.lo, self.hi)],
                "units": "HumanoidBench's own action: position-servo targets, -1 and +1 commanding the two ends of each "
                         "actuator's range (range_rad), linearly, so 0 is mid-range, not 0 rad"
                         + ("; a tendon actuator's range is the summed angle of the two joints it moves" if tendons else ""),
                "dtype": "float32: the simulator applies each target as a 32-bit float",
                "semantics": "rows dt apart (a multiple of control_dt); each control step's targets are the row (hold) or "
                             "a straight line from the previous row's (linear); values outside [-1, 1] are clipped and "
                             "reported"}},
            "cameras": {c: {**self._camera_facts[c], "hw": self.image_hw} for c in self.cameras},
            "proprio": {"joints": self.joints, "units": "*_pos rad, *_vel rad/s", "axis": self._axes,
                        "axis_frame": "the joint's rotation axis in the pelvis frame, every joint at 0; a positive "
                                      "angle turns the joint's child link about it by the right-hand rule: about an axis "
                                      "near +y (left), a link hanging below the joint swings backward",
                        "position_m": self._anchors, "position_frame": "a point on that axis (the joint's centre), m, same frame"}
            if self.proprio_on else None,
            "imu": {"mounted": "pelvis", "frame": "pelvis: x forward, y left, z up",
                    "gyro": "imu_gyro_*: angular velocity, rad/s, pelvis frame, right-hand rule: y > 0 while pitching "
                            "forward (nose down), x > 0 while rolling to the right, z > 0 while turning left",
                    "gravity": "imu_gravity_*: unit gravity direction, pelvis frame: (0, 0, -1) when upright; it tips "
                               "toward the way the pelvis leans: x > 0 leaning forward, y > 0 leaning left"} if self.imu else None,
            "links": self._links,
            "depth": {"cameras": list(CAMERAS), "units": "metres along the camera's forward axis (planar depth, as an "
                      "RGB-D camera reports it), pixel for pixel with that camera's image; noise-free",
                      "range_m": [HEAD_NEAR_M, DEPTH_MAX_M], "nothing_in_range": 0.0} if self.depth_cameras else None,
            "gl_backend": GL_BACKEND,
        }

    def interpolable(self, typ: str) -> bool:
        return True

    def images(self, cameras: list[str], depth: bool) -> tuple[dict, dict]:
        rgb = {c: self._render(c) for c in cameras}
        dep = {c: self._depth(c) for c in cameras if depth and c in self.depth_cameras}
        return rgb, dep

    def proprio(self) -> np.ndarray:
        own = [*self.robot.joint_angles(), *self.robot.joint_velocities()] if self.proprio_on else []
        return np.array(own + (self._imu() if self.imu else []), dtype=np.float32)

    def clip(self, typ: str, rows: np.ndarray) -> tuple[np.ndarray, list]:
        out = np.clip(rows, -1.0, 1.0)
        report = [{"row": int(i), "index": int(j), "reason": "outside [-1, 1]"} for i, j in np.argwhere(out != rows)]
        # At the precision the simulator applies (to_sim), which is also what command() gives back: a chunk then
        # interpolates from exactly the targets the same rows sent one by one would start from.
        return out.astype(np.float32).astype(np.float64), report

    def to_sim(self, typ: str, row: np.ndarray) -> np.ndarray:
        return np.asarray(row, dtype=np.float32).astype(np.float64)   # what Session.step applies

    def command(self, typ: str) -> np.ndarray:
        return self.cmd

    def hold(self) -> tuple[str, np.ndarray]:
        return "joint_position", self.cmd

    def step(self, row: np.ndarray) -> tuple[bool, bool, dict]:
        done = self.s.step(row)[2]
        self.cmd = np.asarray(row, dtype=np.float64)
        return done, bool(self.s.status()["success"]), {}

    def reset(self) -> None:
        self.s.reset()
        self.cmd = self._command_now()

    def state_sha(self) -> str:
        return self.s.state_sha()

    def verify(self, rows: np.ndarray) -> dict:
        """The recorded episode from the frozen scene, in a fresh HumanoidBench environment (physics only)."""
        st = Session(self.task, instance=self.instance).replay(rows)
        return {"success": st["success"], "state_sha": st["state_sha"]}

    def save_trajectory(self, rows: np.ndarray, path: str, meta: dict) -> None:
        self.s.save_trajectory(rows, path, meta)

    def render_video(self, rows: np.ndarray, path: str) -> None:
        self.s.render_video(rows, path, every=5, fps=20)


def build() -> HumanoidBench:
    env = os.environ.get
    pose = [float(v) for v in env("RCB_ROOM_CAMERA_POSE", "").split(",") if v.strip()]
    if pose and len(pose) != 6:
        raise SystemExit("RCB_ROOM_CAMERA_POSE needs 6 numbers: lookat_x,lookat_y,lookat_z,distance,azimuth,elevation")
    return HumanoidBench(env("RCB_TASK"), env("RCB_INSTANCE", "/srv/instance.npz"),
                         proprio=env("RCB_OBS_PROPRIO", "1") == "1", imu=env("RCB_OBS_IMU", "1") == "1",
                         room_camera=env("RCB_OBS_ROOM_CAMERA", "1") == "1", depth=env("RCB_OBS_DEPTH", "0") == "1",
                         room_pose=(np.array(pose[:3]), *pose[3:]) if pose else None, task_text=env("RCB_TASK_TEXT", ""),
                         episode=env("RCB_EPISODE", ""), image_hw=int(env("RCB_IMAGE_HW") or 0) or None)


if __name__ == "__main__":
    main(build)
