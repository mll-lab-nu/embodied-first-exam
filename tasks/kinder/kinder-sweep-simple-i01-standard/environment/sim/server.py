"""eai-standard/2.1 sim service for KinDER -- the sidecar's entry point (`python /srv/server.py`).

The simulator-specific half only: one adapter per KinDER robot implements rcb_service.Sim for one frozen instance
(`make` picks it by the robot in the scene); the protocol, the episode, crash recovery and the finalize live in
rcb_service.py, which imports no simulator. Settings come from environment/docker-compose.yaml:
  RCB_INSTANCE            the frozen scene (the privileged twin's instance.json)
  RCB_TASK_TEXT           one sentence for /spec
  RCB_OBS_DEPTH           1 (standard): depth with robot_wrist, as from the Gen3 wrist's RealSense D410 (TidyBot++'s base
                          camera is an RGB webcam); 0: RGB only
  RCB_OBS_ROOM_CAMERA     0 (standard); 1: + `room_camera`, fixed in the room (MuJoCo: KinDER's `task_view` camera,
                          moved by instance.json where upstream's looks down from overhead; PyBullet: KinDER's view)
  RCB_RESET_BUDGET, RCB_WALL_CLOCK_S, RCB_DATA   the service's own (rcb_service.main)

What the agent gets is what the real robot reports: its own cameras, its joint encoders and the base's odometry.
  TidyBot     KinDER's Dynamic3D TidyBot++ (MuJoCo): holonomic base, Kinova Gen3 arm, Robotiq 2F-85 gripper; its base
              and wrist cameras.
  Kinova      KinDER's Kinematic3D robot (PyBullet): the same base, arm and gripper, kinematic; TidyBot++'s base and
              wrist cameras on the same links (the wrist one 3 cm forward, clear of this model's camera housing),
              near-clipped at 1 cm. A move it refuses (a collision) comes back as blocked.
Odometry is kept in the frame the base starts in, so no world coordinate reaches the agent: actions arrive in that
frame and are turned into KinDER's world-frame action here (to_sim). The journal, the trajectory and the video are in
KinDER's own (world) frame; calls/NNNNNN/actions.npy has what the agent sent.

The verdict is the live episode's: step() reports KinDER's own goal check (`terminated`) at every control
step and the episode ends there, so nothing is replayed to grade it; render_video() re-runs the trajectory once, after
the verdict, to film it. start_sha is the frozen instance's recorded scene_sha (the state hash right after reset), which
rcb_service checks when an episode begins; a KinDER that no longer builds the instance is InstanceMismatch.
"""
from __future__ import annotations

import math
import os
import sys

import mujoco
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rcb_kinder import CAMERA_HW, GL_BACKEND, Session  # noqa: E402
from rcb_service import InstanceMismatch, main  # noqa: E402

CAMERAS = ("robot_base", "robot_wrist")       # the robot's own cameras
DEPTH = ("robot_wrist",)                     # the one that is RGB-D on the real robot
ROOM = "task_view"                           # upstream's camera framing the task, served as `room_camera`
BASE_JOINTS = ("robot_joint_x", "robot_joint_y", "robot_joint_th")
ARM_JOINTS = tuple(f"robot_joint_{i}" for i in range(1, 8))
GRIPPER_JOINT = "robot_right_driver_joint"   # the Robotiq 2F-85's own position sensor reads this joint
BASE_STEP_M = 0.1                            # upstream's per-step bound on each base axis; see clip()
DEPTH_MAX_M = 10.0
CONTROL_DT = 0.1                             # TidyBot++'s 10 Hz; nominal for the kinematic robot
BASE_FRAME = "the base frame: x forward, y left, z up, origin on the floor under the base's centre"
ODOMETRY = {"frame": "where the base started the episode: origin on the floor under the base's centre, x the way it "
                     "faced, y left, z up; noise-free"}
ARM = [f"arm_{i}" for i in range(1, 8)]


def rot(yaw: float) -> np.ndarray:
    c, s = math.cos(yaw), math.sin(yaw)
    return np.array([[c, -s], [s, c]])


def wrap(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


def r3(v) -> list[float]:
    return [round(float(x), 4) for x in v]


def stated(v: float, side: int) -> float | None:
    """A bound as spec() states it: 4 decimals, stepped inward where rounding lands outside the true bound, so an
    action at a stated bound is never clipped. None: unbounded."""
    if not math.isfinite(v):
        return None
    r = round(float(v), 4)
    return round(r - side * 1e-4, 4) if side * (r - float(v)) > 0 else r


def pose(p, R, C) -> dict:
    """A camera's pose: its position, and its axes C (columns: the image's right, its up, the way it looks from) turned
    by R into the frame the pose is given in."""
    return {"position_m": r3(p), "forward": r3(R @ -C[:, 2]), "up": r3(R @ C[:, 1]), "right": r3(R @ C[:, 0])}


def depth_spec() -> dict:
    return {"cameras": list(DEPTH), "units": "metres along the camera's forward axis (planar depth, as an RGB-D camera "
            "reports it), pixel for pixel with that camera's image; noise-free", "range_m": [0.0, DEPTH_MAX_M],
            "nothing_in_range": 0.0}


class _Robot:
    """What both adapters share: one frozen Session, the base's odometry (the frame it starts in) and its moves turned
    from that frame into KinDER's world frame, clipping, the frozen start's hash. KinDER bounds each world axis per step; a move
    within that bound in any direction (a disc) stays inside them whatever the start heading. A subclass says which
    robot (`robot_type`, its type in KinDER's state), how to render a camera, and its proprioception."""
    robot_type = ""
    base_step = BASE_STEP_M
    control_dt = CONTROL_DT

    def __init__(self, s: Session, instance: str, *, room_camera: bool = False, depth: bool = False,
                 task_text: str = ""):
        self.s, self.instance, self.task_text = s, instance, task_text
        self.start_sha = s.instance.get("scene_sha")  # the frozen start (rcb_service checks it when an episode begins)
        self.depth_cameras = DEPTH if depth else ()
        self.cameras = CAMERAS + (("room_camera",) if room_camera else ())
        self.raw_dim = self.dim = int(self.s.action_space.shape[0])
        self.max_control_steps = int(self.s.max_steps)
        self.lo = self.s.action_space.low.astype(np.float64)
        self.hi = self.s.action_space.high.astype(np.float64)
        f = self._robot()
        self._start = f["pos_base_x"], f["pos_base_y"], f["pos_base_rot"]   # the odometry frame, every episode

    def _robot(self) -> dict[str, float]:
        """The robot's features in KinDER's state, by name."""
        st = self.s.state()
        r = next(o for o in st if o.type.name == self.robot_type)
        return {f: float(st.get(r, f)) for f in st.type_features[r.type]}

    def _odom_pose(self, f: dict) -> list[float]:
        x0, y0, th0 = self._start
        return [*(rot(-th0) @ (np.array([f["pos_base_x"], f["pos_base_y"]]) - [x0, y0])).tolist(),
                wrap(f["pos_base_rot"] - th0)]

    def layout(self) -> list[str]:
        return ["base_x", "base_y", "base_yaw", *ARM, "gripper"] + ([f"{a}_vel" for a in ARM] if self.dim == 18 else [])

    def interpolable(self, typ: str) -> bool:
        return False                            # a delta is one control step's move

    def clip(self, typ: str, rows: np.ndarray) -> tuple[np.ndarray, list]:
        """Each value into its bound, then the base's move into the disc of radius base_step."""
        out = np.clip(rows, self.lo, self.hi)
        clipped = [{"row": int(i), "index": int(j), "reason": f"bound [{stated(self.lo[j], -1)}, {stated(self.hi[j], 1)}]"}
                   for i, j in np.argwhere(out != rows)]
        for i, row in enumerate(out):
            r = math.hypot(row[0], row[1])
            if r > self.base_step:
                row[:2] *= self.base_step / r
                clipped.append({"row": i, "index": 0, "reason": f"base_x, base_y together at most {self.base_step} m"})
        return out, clipped

    def to_sim(self, typ: str, row: np.ndarray) -> np.ndarray:
        w = np.array(row, dtype=np.float64)
        w[:2] = rot(self._start[2]) @ row[:2]
        return w

    def command(self, typ: str) -> np.ndarray:
        return np.zeros(self.dim)

    def reset(self) -> None:
        self.s.reset()

    def state_sha(self) -> str:
        return self.s.state_sha()

    def save_trajectory(self, rows: np.ndarray, path: str, meta: dict) -> None:
        self.s.save_trajectory(rows, path, meta)

    def render_video(self, rows: np.ndarray, path: str) -> None:
        """The episode's video, after the verdict: the trajectory re-run once on this simulator, from the frozen start."""
        self.s.render_video(rows, path)         # the view that frames the task (MuJoCo: task_view)


class TidyBot(_Robot):
    """One frozen KinDER (Dynamic3D, TidyBot++) instance. The agent never gets an object's pose, a goal region's
    coordinates or the goal check -- only that the episode ended and why."""
    robot_type = "mujoco_tidybot_robot"
    # where the finger pads meet when the gripper closes on nothing, in the frame of the arm's last link (measured on
    # tidybot.xml; open, the pads' centre is 1.3 cm nearer the wrist). Upstream's pinch_site sits 2.4 cm short of it.
    PINCH = np.array([0.0, 0.0, -0.2054])

    def __init__(self, s: Session, instance: str, **kw):
        super().__init__(s, instance, **kw)
        self.proprio_layout = ["base_x", "base_y", "base_yaw", "base_vx", "base_vy", "base_yaw_rate", *ARM,
                               *(f"{a}_vel" for a in ARM), "gripper", "gripper_vel"]
        self._grip = self._robot()["pos_gripper"]   # the gripper command that holding keeps
        self._facts = self._hardware()

    def _hardware(self) -> dict:
        """What the robot's documentation (its URDF) gives, read off the model with the base at the origin and every arm
        joint at 0: each arm joint's axis and a point on it, its limits, and the robot cameras' poses -- all in the base
        frame (x forward, y left, z up, origin on the floor under the base's centre); room_camera in the odometry frame."""
        m = self.s.model
        d = mujoco.MjData(m)                                         # a scratch copy: the live sim is untouched
        for j in BASE_JOINTS + ARM_JOINTS:
            d.qpos[m.jnt_qposadr[m.joint(j).id]] = 0.0
        mujoco.mj_forward(m, d)

        def cam(c: str, R=np.eye(3), p=np.zeros(3)) -> dict:
            i = m.camera(c).id
            return pose(R @ (d.cam_xpos[i] - p), R, d.cam_xmat[i].reshape(3, 3))

        last = m.body("robot_bracelet_link").id
        arm = {"joints": ARM,
               "axis": [r3(d.xaxis[m.joint(j).id]) for j in ARM_JOINTS],
               "position_m": [r3(d.xanchor[m.joint(j).id]) for j in ARM_JOINTS],
               "limits_rad": [r3(m.jnt_range[m.joint(j).id]) if m.jnt_limited[m.joint(j).id] else None for j in ARM_JOINTS],
               "torque_limit_nm": [round(float(m.actuator(j).ctrlrange[1]), 1) for j in ARM_JOINTS],
               "end_effector": {"position_m": r3(d.xpos[last] + d.xmat[last].reshape(3, 3) @ self.PINCH),
                                "fixed_to": "the arm's last link"},
               "frame": BASE_FRAME + ", every arm joint at 0; a positive angle turns the child link about the axis by "
                                     "the right-hand rule; limits_rad None: the joint turns without limit; end_effector: "
                                     "where the finger pads meet when the gripper closes on nothing (open, their centre "
                                     "is 1.3 cm nearer the wrist)"}
        cams = {c: {"mounted": "base" if c == "robot_base" else "wrist (the arm's last link: it moves with the arm)",
                    "fovy_deg": round(float(m.cam_fovy[m.camera(c).id]), 1), "hw": list(CAMERA_HW),
                    "pose": {"frame": BASE_FRAME + ", every arm joint at 0", **cam(c)}} for c in CAMERAS}
        if "room_camera" in self.cameras:            # fixed in the room, so the scratch copy has its pose too
            x0, y0, th0 = self._start
            R = np.eye(3)
            R[:2, :2] = rot(-th0)
            cams["room_camera"] = {"mounted": "room (fixed)", "fovy_deg": round(float(m.cam_fovy[m.camera(ROOM).id]), 1),
                                   "hw": list(CAMERA_HW), "pose": {"frame": "odometry", **cam(ROOM, R, np.array([x0, y0, 0.0]))}}
        return {"arm": arm, "cameras": cams}

    def spec(self) -> dict:
        return {
            "simulator": "kinder", "robot": "TidyBot++: holonomic base, Kinova Gen3 7-DoF arm, Robotiq 2F-85 gripper",
            "task_text": self.task_text,
            "episode": f"ends when the task succeeds (KinDER's own goal check), after {self.max_control_steps} control "
                       "steps, when your time is up, or on a simulator error",
            "action_types": {"delta": {
                "dim": self.dim, "layout": self.layout(),
                "low": [stated(v, -1) for v in self.lo], "high": [stated(v, 1) for v in self.hi],
                "units": "base_x, base_y: metres to move the base in the odometry frame, together at most "
                         f"{BASE_STEP_M} m a step; base_yaw: radians to turn it (+ = counter-clockwise); arm_i: radians "
                         "added to joint i's measured angle, which becomes its new target; gripper: 0 = open, "
                         "1 = closed (a command, not a change)" + ("; arm_i_vel: joint velocity targets, rad/s"
                                                                  if self.dim == 18 else ""),
                "semantics": "one row is one control step (dt = control_dt): the base's position controller and the "
                             "arm's PD controller track the new targets for 0.1 s; values outside low/high, and a base "
                             "move beyond the disc, are clipped and reported"}},
            "cameras": self._facts["cameras"],
            "proprio": {"base_x, base_y, base_yaw": "m, m, rad, odometry frame",
                        "base_vx, base_vy, base_yaw_rate": "m/s, m/s, rad/s, odometry frame",
                        "arm_i, arm_i_vel": "joint angles (rad) and velocities (rad/s), arm joint order",
                        "gripper": "the fingers' position: 0 open, 1 at their joint's closed limit; closing on nothing "
                                   "they stop at about 0.98, where the pads meet, and on an object short of that",
                        "gripper_vel": "gripper per second"},
            "odometry": ODOMETRY, "arm": self._facts["arm"],
            "depth": depth_spec() if self.depth_cameras else None, "gl_backend": GL_BACKEND,
        }

    def images(self, cameras: list[str], depth: bool) -> tuple[dict, dict]:
        names = [ROOM if c == "room_camera" else c for c in cameras]
        rgb = self.s.images(names)
        out = {c: rgb[n] for c, n in zip(cameras, names)}
        rgbd = [c for c in cameras if c in self.depth_cameras] if depth else []
        dep = {c: np.where(v < DEPTH_MAX_M, v, 0.0).astype(np.float32)
               for c, v in self.s.images(rgbd, depth=True).items()} if rgbd else {}
        return out, dep

    def proprio(self) -> np.ndarray:
        f, th0 = self._robot(), self._start[2]
        m, j = self.s.model, self.s.model.joint(GRIPPER_JOINT)
        closed = float(m.jnt_range[j.id][1])       # the fingers' measured position, not KinDER's pos_gripper (a command)
        return np.array([*self._odom_pose(f), *(rot(-th0) @ [f["vel_base_x"], f["vel_base_y"]]), f["vel_base_rot"],
                         *(f[f"pos_arm_joint{i}"] for i in range(1, 8)), *(f[f"vel_arm_joint{i}"] for i in range(1, 8)),
                         float(self.s.data.qpos[m.jnt_qposadr[j.id]]) / closed,
                         float(self.s.data.qvel[m.jnt_dofadr[j.id]]) / closed], dtype=np.float32)

    def hold(self) -> tuple[str, np.ndarray]:
        row = np.zeros(self.dim)
        row[10] = self._grip
        return "delta", row

    def step(self, row: np.ndarray) -> tuple[bool, bool, dict]:
        _, success, done = self.s.step(row)
        self._grip = float(row[10])
        return done, success, {"blocked": False}

    def reset(self) -> None:
        super().reset()
        self._grip = self._robot()["pos_gripper"]


class Kinova(_Robot):
    """KinDER's Kinematic3D robot (PyBullet): a TidyBot++ base and Kinova Gen3 arm with a Robotiq 2F-85, moved
    kinematically. Its cameras are TidyBot++'s, as tidybot.xml mounts them: the base camera on the base, the wrist camera
    on the Gen3's bracelet link, whose frames the two models share (the shoulder joint and the gripper sit at the same
    place in both); KinDER's own render_base_camera/render_ee_camera turn their mounts by a mis-ordered quaternion.
    Obstruction3D and Packing3D sink the robot 0.4 m into the floor (robot_base_z); there the base camera stays 0.335 m
    above the floor, as KinDER renders it, and the base frame's origin stays on the floor. room_camera is KinDER's own
    view of the scene."""
    robot_type = "Kinematic3DRobot"
    NEAR_M, FAR_M = 0.01, 100.0
    ROOM_FOVY = 60.0                            # KinDER's render() (pybullet_helpers' capture_image)
    FINGERS_CLOSED = 0.8                        # finger_state at the gripper's closed limit (0: open)
    STILL = 1e-9                                # m or rad: less is no move (KinDER's undo can leave round-off on the yaw)
    h = math.sqrt(0.5)                          # TidyBot++'s cameras: position, axes (as MuJoCo's), vertical field of view
    BASE_CAM = (np.array([0.2525, 0.0, 0.335]), np.array([[0, h, -h], [-1, 0, 0], [0, h, h]]), 52.2338)   # base frame
    # on bracelet_link; 3 cm further along its view than tidybot.xml's, because this model's gripper carries its own
    # camera housing there (robotiq_arg2f_85_base_link_realsense), which would otherwise fill the image
    WRIST_CAM = (np.array([0.0, -0.05639, -0.088475]), np.diag([-1.0, -1.0, 1.0]), 41.8379)

    def __init__(self, s: Session, instance: str, **kw):
        super().__init__(s, instance, **kw)
        self.env = self.s.env.unwrapped._object_centric_env
        self.base_step = round(float(self.s.action_space.high[0]), 4)
        self.proprio_layout = ["base_x", "base_y", "base_yaw", *ARM, "gripper"]
        self._facts = self._hardware()
        self.s.reset()                          # _hardware moved the arm: back to the frozen scene
        self._frames: dict = {}                 # this state's renders: {camera: (rgb, depth)}, one draw for both

    def step(self, row: np.ndarray) -> tuple[bool, bool, dict]:
        """One step, and whether KinDER refused the move: the pose it was sent to differs from the one it was in (from
        the action KinDER receives, in its dtype; the arm's targets clipped to its limits, as KinDER does), yet the robot
        did not move (by more than STILL)."""
        self._frames = {}
        q0, arm = self._pose(), self.env.robot.arm
        w = row.astype(self.s.action_space.dtype).astype(np.float64)
        target = np.concatenate([q0[:3] + w[:3], np.clip(q0[3:] + w[3:10], arm.joint_lower_limits[:7],
                                                           arm.joint_upper_limits[:7])])
        _, success, done = self.s.step(row)
        asked, moved = np.abs(target - q0) > self.STILL, np.abs(self._pose() - q0) > self.STILL
        return done, success, {"blocked": bool(asked.any() and not moved.any())}

    def hold(self) -> tuple[str, np.ndarray]:
        return "delta", np.zeros(self.dim)      # gripper 0: leave it as it is

    def _pose(self) -> np.ndarray:
        """The base's (x, y, yaw) and the arm's 7 joint angles, as the simulator holds them."""
        b = self.env.robot.get_base()
        return np.array([b.x, b.y, b.rot, *self.env.robot.arm.get_joint_positions()[:7]], dtype=np.float64)

    def reset(self) -> None:
        self._frames = {}
        super().reset()

    def _link(self, name: str) -> int:
        import pybullet as pb
        arm, cid = self.env.robot.arm, self.env.physics_client_id
        return next(j for j in range(pb.getNumJoints(arm.robot_id, physicsClientId=cid))
                    if pb.getJointInfo(arm.robot_id, j, physicsClientId=cid)[12].decode() == name)

    def _camera(self, c: str) -> tuple[np.ndarray, np.ndarray, float]:
        """A robot camera's world position and axes, and its field of view."""
        import pybullet as pb
        if c == "robot_base":
            b = self.env.robot.get_base()
            P, R = np.array([b.x, b.y, 0.0]), np.eye(3)
            R[:2, :2] = rot(b.rot)
            p, r, fov = self.BASE_CAM
        else:
            ls = pb.getLinkState(self.env.robot.arm.robot_id, self._link("bracelet_link"), computeForwardKinematics=True,
                                 physicsClientId=self.env.physics_client_id)
            P, R = np.asarray(ls[4]), np.asarray(pb.getMatrixFromQuaternion(ls[5])).reshape(3, 3)
            p, r, fov = self.WRIST_CAM
        return P + R @ p, R @ r, fov

    def _render(self, c: str) -> tuple[np.ndarray, np.ndarray]:
        if c not in self._frames:
            self._frames[c] = self._draw(c)
        return self._frames[c]

    def _draw(self, c: str) -> tuple[np.ndarray, np.ndarray]:
        """One camera's RGB and depth (metres, planar), drawn once. room_camera: KinDER's own view (render()'s),
        drawn at the robot cameras' size (at KinDER's own 360 x 640, a scene's image can change by a pixel from draw to
        draw)."""
        import pybullet as pb
        H, W = CAMERA_HW
        cid = self.env.physics_client_id
        if c == "room_camera":
            view, fov = self._room_view(), self.ROOM_FOVY
        else:
            pos, R, fov = self._camera(c)
            view = pb.computeViewMatrix(pos.tolist(), (pos - R[:, 2]).tolist(), R[:, 1].tolist(), physicsClientId=cid)
        proj = pb.computeProjectionMatrixFOV(fov=fov, aspect=W / H, nearVal=self.NEAR_M, farVal=self.FAR_M,
                                             physicsClientId=cid)
        _, _, rgba, zbuf, _ = pb.getCameraImage(W, H, view, proj, renderer=pb.ER_BULLET_HARDWARE_OPENGL,
                                                physicsClientId=cid)
        z = np.asarray(zbuf, dtype=np.float64).reshape(H, W)
        d = self.FAR_M * self.NEAR_M / (self.FAR_M - (self.FAR_M - self.NEAR_M) * z)
        return (np.asarray(rgba, dtype=np.uint8).reshape(H, W, 4)[:, :, :3],
                np.where(d < DEPTH_MAX_M, d, 0.0).astype(np.float32))

    def images(self, cameras: list[str], depth: bool) -> tuple[dict, dict]:
        rgb = {c: self._render(c)[0] for c in cameras}
        dep = {c: self._render(c)[1] for c in cameras if depth and c in self.depth_cameras}
        return rgb, dep

    def proprio(self) -> np.ndarray:
        f = self._robot()
        return np.array([*self._odom_pose(f), *(f[f"joint_{i}"] for i in range(1, 8)),
                         f["finger_state"] / self.FINGERS_CLOSED], dtype=np.float32)

    def _room_view(self) -> list[float]:
        """KinDER's render() viewpoint, as PyBullet's view matrix (column-major, world to camera)."""
        import pybullet as pb
        kw = self.env.config.get_camera_kwargs()
        return pb.computeViewMatrixFromYawPitchRoll(cameraTargetPosition=kw["camera_target"], distance=kw["camera_distance"],
                                                    yaw=kw["camera_yaw"], pitch=kw["camera_pitch"], roll=0, upAxisIndex=2,
                                                    physicsClientId=self.env.physics_client_id)

    def _hardware(self) -> dict:
        """As TidyBot's: the arm's joints with every arm joint at 0, and the cameras, in the base frame; room_camera in
        the odometry frame."""
        import pybullet as pb
        from scipy.spatial.transform import Rotation
        arm, cid = self.env.robot.arm, self.env.physics_client_id
        names = [f"joint_{i}" for i in range(1, 8)]
        idx = {pb.getJointInfo(arm.robot_id, j, physicsClientId=cid)[1].decode(): j
               for j in range(pb.getNumJoints(arm.robot_id, physicsClientId=cid))}
        for n in names:                         # the live sim: __init__ resets it afterwards
            pb.resetJointState(arm.robot_id, idx[n], 0.0, physicsClientId=cid)
        b = self.env.robot.get_base()
        Rb, pb0 = np.eye(3), np.array([b.x, b.y, 0.0])
        Rb[:2, :2] = rot(-b.rot)

        def link(j: int) -> tuple[np.ndarray, np.ndarray]:
            ls = pb.getLinkState(arm.robot_id, j, computeForwardKinematics=True, physicsClientId=cid)
            return np.asarray(ls[4]), np.asarray(pb.getMatrixFromQuaternion(ls[5])).reshape(3, 3)

        axes, points, limits = [], [], []
        for n in names:                         # each axis as its link turns: 0.01 rad about it, then back to 0
            info, (p0, R0) = pb.getJointInfo(arm.robot_id, idx[n], physicsClientId=cid), link(idx[n])
            pb.resetJointState(arm.robot_id, idx[n], 0.01, physicsClientId=cid)
            axis = Rotation.from_matrix(link(idx[n])[1] @ R0.T).as_rotvec() / 0.01
            pb.resetJointState(arm.robot_id, idx[n], 0.0, physicsClientId=cid)
            axes.append(r3(Rb @ axis))
            points.append(r3(Rb @ (p0 - pb0)))
            limits.append(r3(info[8:10]) if info[8] < info[9] else None)
        frame = BASE_FRAME + ", every arm joint at 0"
        ee = np.asarray(arm.get_end_effector_pose().position)
        cams = {}
        for c in CAMERAS:
            p, R, fov = self._camera(c)
            cams[c] = {"mounted": "base" if c == "robot_base" else "wrist (the arm's last link: it moves with the arm)",
                       "fovy_deg": round(float(fov), 1), "hw": list(CAMERA_HW),
                       "pose": {"frame": frame, **pose(Rb @ (p - pb0), Rb, R)}}
        if "room_camera" in self.cameras:        # the view matrix inverted: camera axes (right, up, back) and position
            V = np.asarray(self._room_view()).reshape(4, 4).T
            C, x0, y0, th0 = V[:3, :3].T, *self._start
            Ro = np.eye(3)
            Ro[:2, :2] = rot(-th0)
            cams["room_camera"] = {"mounted": "room (fixed)", "fovy_deg": self.ROOM_FOVY, "hw": list(CAMERA_HW),
                                   "pose": {"frame": "odometry", **pose(Ro @ (-C @ V[:3, 3] - [x0, y0, 0.0]), Ro, C)}}
        return {"arm": {"joints": ARM, "axis": axes, "position_m": points, "limits_rad": limits,
                        "end_effector": {"position_m": r3(Rb @ (ee - pb0)), "fixed_to": "the arm's last link"},
                        "frame": frame + "; a positive angle turns the child link about the axis by the right-hand "
                                         "rule; limits_rad None: the joint turns without limit; end_effector: the arm's "
                                         "end-effector point"},
                "cameras": cams}

    def spec(self) -> dict:
        mag, cfg = self.base_step, self.env.config
        z = 2 * np.asarray(cfg.end_effector_viz_half_extents) * 100
        return {
            "simulator": "kinder", "robot": "TidyBot++-style mobile manipulator, kinematic (PyBullet): base, Kinova "
                                            "Gen3 7-DoF arm, Robotiq 2F-85 gripper",
            "task_text": self.task_text,
            "episode": f"ends when the task succeeds (KinDER's own goal check), after {self.max_control_steps} control "
                       "steps, when your time is up, or on a simulator error",
            "action_types": {"delta": {
                "dim": self.dim, "layout": self.layout(),
                "low": [stated(v, -1) for v in self.lo], "high": [stated(v, 1) for v in self.hi],
                "units": f"base_x, base_y: metres to move the base in the odometry frame, together at most {mag} m a "
                         "step; base_yaw: radians to turn it (+ = counter-clockwise); arm_i: radians added to joint i's "
                         "angle; gripper: below -0.5 closes, above 0.5 opens, in between leaves it",
                "semantics": "one row is one step (dt = control_dt; the robot is kinematic: a step moves it there at "
                             "once, and control_dt only times the video). Closing takes hold of an object only if "
                             "exactly one object touches the grasp zone, a "
                             f"{z[0]:g} x {z[1]:g} x {z[2]:g} cm box at the arm's end-effector point (arm.end_effector); "
                             "otherwise the fingers do not move. Opening lets go of what it holds only if the object is "
                             f"within {cfg.min_placement_dist * 1000:g} mm of a surface it can rest on; otherwise it "
                             "stays held. A step that would bring the arm or what it holds into collision is not carried "
                             "out: the robot stays where it was, the answer says blocked: true, and a chunk stops there. "
                             "That holds for a base move too, which carries the arm along; "
                             + ("the base itself is checked for collisions too" if cfg.check_base_collisions
                                else "the base itself is not checked for collisions")
                             + ". Values outside low/high, and a base move beyond the disc, are clipped and reported"}},
            "cameras": self._facts["cameras"],
            "proprio": {"base_x, base_y, base_yaw": "m, m, rad, odometry frame", "arm_i": "joint angles, rad (arm joint "
                        "order)", "gripper": "the fingers' position: 0 open, 1 at their closed limit (short of 1 when "
                        "they close on an object)"},
            "odometry": ODOMETRY, "arm": self._facts["arm"],
            "depth": depth_spec() if self.depth_cameras else None,
        }


ROBOTS = {cls.robot_type: cls for cls in (TidyBot, Kinova)}


def make(instance: str, **kw) -> _Robot:
    """The adapter for the robot in this instance's scene."""
    try:
        s = Session(instance)
    except RuntimeError as exc:                 # rcb_kinder refuses a scene that no longer builds the frozen instance
        if "drifted" in str(exc) or "task_view" in str(exc):
            raise InstanceMismatch(str(exc)) from exc
        raise
    return ROBOTS[next(o.type.name for o in s.state() if o.type.name in ROBOTS)](s, instance, **kw)


def build() -> _Robot:
    env = os.environ.get
    return make(env("RCB_INSTANCE", "/srv/instance.json"), room_camera=env("RCB_OBS_ROOM_CAMERA", "0") == "1",
                depth=env("RCB_OBS_DEPTH", "1") == "1", task_text=env("RCB_TASK_TEXT", ""))


if __name__ == "__main__":
    main(build)
