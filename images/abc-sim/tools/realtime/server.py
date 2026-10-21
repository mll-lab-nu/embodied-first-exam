"""eai-standard/2.3 sim service for ABC Sim's standard-realtime tasks -- the adapter behind the shared realtime layer
(`python /srv/rcb_realtime.py`, which imports this module and calls build(); docs/protocol/README.md §3,
docs/protocol/standard_mode.md Part 3).

The simulator-specific half only: `AbcSim` implements rcb_service.Sim (the contract documented in rcb_service.py, a
byte-identical copy of the other realtime benchmarks') for one frozen instance, on the benchmark's tooling module
rcb_abc.Session -- the same scene, action and success rule as the standard twin's eai-standard/2.2 service. The
protocol, the clock, the plan, the episode, crash recovery and the finalize are rcb_realtime.py's and rcb_service.py's.

Grading: the verdict is the live episode's, judged by the layer from step(): the task's rule as Session.step applies it
to the steps this service ran (the 1.02 s success hold; ball tray: the countdown completed with the ball on the tray and
both handles held). There is no live_verdict(). Nothing is replayed to grade it; the video is rendered from the
trajectory after the verdict (render_video). `start_sha` is the frozen instance's recorded state hash: the layer refuses
a fresh episode whose scene does not start there (instance_mismatch, infrastructure).

What the agent gets is what the standard twin gives, minus the 2.2 additions the realtime layer does not serve
(`/kinematics`, per-frame camera poses, depth modes): the cameras (RGB and depth), the robot's own proprioception and the
14-number joint-position action. Nothing about the scene leaves this process.

Settings (environment/docker-compose.yaml): RCB_INSTANCE, RCB_TASK_INFO (task.json: task text, default cameras),
RCB_IMAGE_HW (default "480,640"), RCB_DATA, RCB_RESET_BUDGET, RCB_WALL_CLOCK_S, RCB_SLOWDOWN, RCB_GL (auto: EGL when it
works, else OSMesa; rcb_abc picks it before MuJoCo loads).
"""
from __future__ import annotations

import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ["RCB_SESSION_LOG"] = ""
import rcb_abc as M  # noqa: E402  (first: it picks the rendering backend before mujoco loads)
import mujoco  # noqa: E402

M.SESSION_LOG = ""           # the sidecar's Session is not the agent's interaction log
from rcb_service import main  # noqa: E402

GL2CV = np.diag([1.0, -1.0, -1.0, 1.0])
JOINT_TEXT = ("one row per control step, 14 numbers in `layout` order: each arm's six joint position targets (rad) and its "
              "gripper opening (0 = closed, 1 = open: each finger 0.0475 m from closed; up to 1.042); rows dt apart (a "
              "whole multiple of control_dt), `linear` (default: a straight line from the target in force) or `hold` "
              "between rows. The simulator rounds each command to float32; a value outside `lower` / `upper` is clamped "
              "to it by the servo (the row is executed as sent)")


class AbcSim:
    """One frozen ABC Sim instance behind the rcb_service.Sim contract (see the module docstring)."""

    def __init__(self, instance: str, task_info: dict, image_hw: tuple[int, int] = (480, 640)):
        self.instance = instance
        self.info = task_info
        self.s = M.Session(instance=instance)
        self.start_sha = self.s.instance_sha                    # the frozen instance's recorded start (the layer checks it)
        m = self.m = self.s.model
        self.H, self.W = image_hw
        self.control_dt = float(self.s.dt)
        self.max_control_steps = int(self.s.max_steps)          # a runaway guard: the task's own rule ends an episode
        self.raw_dim = 14
        lim = self.s.action_limits()
        self.lo, self.hi = np.array(lim["low"]), np.array(lim["high"])
        self.cameras = tuple(c for c in M.CAMERAS if c in self.s.cameras())
        self.depth_cameras = self.cameras
        self.fingers = {s: (m.joint(f"{s}_left_finger").id, m.joint(f"{s}_right_finger").id) for s in M.SIDES}
        self.grip_act = {s: m.actuator(f"{s}_gripper").id for s in M.SIDES}
        self.proprio_layout = ([f"q_{n}" for n in M.ACTION_LAYOUT] + [f"qd_{n}" for n in M.ACTION_LAYOUT]
                               + ["left_gripper_opening_m", "right_gripper_opening_m"]
                               + [f"{s}_tcp_{k}" for s in M.SIDES for k in ("x", "y", "z", "qw", "qx", "qy", "qz")]
                               + [f"effort_{n}" for n in M.ACTION_LAYOUT])
        self.s.render_frame(self.cameras[0], (self.H, self.W))  # warms up the GL context
        self.cmd = self.s.hold_action()

    # ------------------------------------------------------------------ what the agent may know
    def _intrinsic(self, cam: str) -> list:
        return self.s.camera_info(cam, (self.H, self.W))["intrinsic_cv"]

    def _camera_fact(self, cam: str) -> dict:
        m, i = self.m, self.m.camera(cam).id
        info = self.s.camera_info(cam, (self.H, self.W))
        out = {"hw": [self.H, self.W], "intrinsic_cv": info["intrinsic_cv"], "fovy_deg": round(float(m.cam_fovy[i]), 2)}
        b = int(m.cam_bodyid[i])
        chain, x = [], b
        while x > 0:
            chain.append(x)
            x = int(m.body_parentid[x])
        if all(int(m.body_jntnum[x]) == 0 for x in chain):
            return {**out, "mounted": "static", "extrinsic_cv": np.asarray(info["extrinsic_cv"]).round(6).tolist(),
                    "pose_note": "extrinsic_cv: world -> camera, OpenCV axes (x right, y down, z forward)"}
        Tb = np.eye(4)
        Tb[:3, :3] = self.s.data.xmat[b].reshape(3, 3)
        Tb[:3, 3] = self.s.data.xpos[b]
        link_T_cam = np.linalg.inv(Tb) @ np.asarray(info["cam2world_gl"]) @ GL2CV
        return {**out, "mounted": f"on the arm link {m.body(b).name}: it moves with it", "link": m.body(b).name,
                "link_T_cam_cv": link_T_cam.round(6).tolist()}

    # ------------------------------------------------------------------ the rcb_service.Sim contract
    def spec(self) -> dict:
        m = self.m
        action = {"dim": 14, "layout": list(M.ACTION_LAYOUT), "lower": self.lo.tolist(), "upper": self.hi.tolist(),
                  "units": "rad (joints), opening in [0, 1.042] (grippers)", "semantics": JOINT_TEXT}
        episode = ("an episode ends in success the moment the task's goal has held for "
                   f"{M.HOLD_STEPS} control steps in a row ({round(M.HOLD_STEPS * self.control_dt, 2)} s), when your "
                   "time is up, or on a simulator error" if self.s.rule != "tray" else
                   "an episode ends in success when the tray's countdown completes with the ball on the tray and both "
                   "handles held throughout, in failure the moment the ball leaves the tray or a handle is let go during "
                   "the countdown, when your time is up, or on a simulator error")
        return {
            "simulator": "ABC Sim (abc_sim) on MuJoCo 3.6.0 (CPU physics; cameras rendered over EGL)",
            "robot": "two I2RT YAM arms (6 revolute joints and a parallel two-finger gripper each) at a table",
            "task_text": self.info["task_text"],
            "episode": episode,
            "action_types": {"joint_position": action},
            "cameras": {c: self._camera_fact(c) for c in self.cameras},
            "default_camera": (self.info.get("default_cameras") or list(M.DEFAULT_CAMERAS))[0],
            "default_cameras": list(self.info.get("default_cameras") or M.DEFAULT_CAMERAS),
            "proprio": {"groups": {
                "q_*": "the 14 action coordinates measured: joint angles (rad) and gripper openings (0 closed .. 1 open)",
                "qd_*": "their velocities",
                "*_gripper_opening_m": "metres the two fingers of each gripper have travelled apart from closed (0 .. 0.095)",
                "*_tcp_*": "each arm's tool centre point in the world frame: position (m), wxyz quaternion",
                "effort_*": "each servo's force: joint torques (N m) and gripper force (N)"}},
            "static": {"arms": list(M.SIDES)},
            "world": {"frame": "the table's world frame: x forward (away from the arms' bases), y to the left as the arms "
                      "face, z up (no positions of the scene are given)", "up": "+z",
                      "units": {"length": "m", "angle": "rad", "time": "s"}, "quaternion_order": "wxyz"},
            "robot_spec": {
                "name": "I2RT YAM, bimanual",
                "joints": [{"name": n, "type": "revolute", "position_limits": m.jnt_range[m.joint(n).id].tolist()}
                           for n in M.ARM_JOINTS],
                "grippers": {s: {"command": f"action entry {s}_gripper: 0 = closed, 1 = open (each finger 0.0475 m from "
                                 "closed), up to 1.042"} for s in M.SIDES},
                "controller": "joint position servos (MuJoCo position actuators with velocity damping) on the 12 arm "
                              "joints and the 2 grippers; the targets are held for the whole control step",
                "physics_hz": round(1.0 / self.control_dt * int(self.s.env._control_decimation), 3),
            },
            "depth": {"cameras": list(self.depth_cameras),
                      "units": "z-depth in metres, pixel for pixel with the camera's image; noise-free"},
            "gl_backend": M.GL,
        }

    def interpolable(self, typ: str) -> bool:
        return True

    def images(self, cameras: list[str], depth: bool) -> tuple[dict, dict]:
        rgb = {c: self.s.render_frame(c, (self.H, self.W)) for c in cameras}
        dep = {}
        if depth:
            for c in cameras:
                z = self.s.render_depth(c, (self.H, self.W))
                dep[c] = np.where(np.isfinite(z) & (z > 0), z, 0.0).astype(np.float32)
        return rgb, dep

    def proprio(self) -> np.ndarray:
        s, m, d = self.s, self.m, self.s.data
        eff = np.array([float(d.qfrc_actuator[m.jnt_dofadr[m.joint(n).id]]) if not n.endswith("_gripper")
                        else float(d.actuator_force[self.grip_act[n.split("_")[0]]]) for n in M.ACTION_LAYOUT])
        opening = [float(d.qpos[m.jnt_qposadr[self.fingers[x][0]]] - d.qpos[m.jnt_qposadr[self.fingers[x][1]]])
                   for x in M.SIDES]
        tcp = [v for x in M.SIDES for v in s.site_pose(f"{x}_tcp_site")]
        return np.concatenate([s.robot_q(), s.robot_qd(), opening, tcp, eff]).astype(np.float32)

    def clip(self, typ: str, rows: np.ndarray) -> tuple[np.ndarray, list]:
        """Rows are executed as sent (as in the standard twin); the entries the servos clamp are reported."""
        A = np.asarray(rows, dtype=np.float64)
        A32 = A.astype(np.float32).astype(np.float64)
        bad = np.argwhere((A32 < self.lo) | (A32 > self.hi))
        return A, [{"row": int(r), "index": int(i), "reason": f"{M.ACTION_LAYOUT[i]} clamped by the servo"}
                   for r, i in bad[:200]]

    def to_sim(self, typ: str, row: np.ndarray) -> np.ndarray:
        return np.asarray(row, dtype=np.float64)

    def command(self, typ: str) -> np.ndarray:
        return self.cmd

    def hold(self) -> tuple[str, np.ndarray]:
        return "joint_position", self.cmd

    def step(self, row: np.ndarray) -> tuple[bool, bool, dict]:
        running = self.s.step(row)
        self.cmd = np.asarray(row, dtype=np.float64).copy()
        return (not running), bool(self.s.success), ({} if running else {"why": self.s.reason})

    def reset(self) -> None:
        self.s.reset()
        self.cmd = self.s.hold_action()

    def state_sha(self) -> str:
        return self.s.state_sha()

    def save_trajectory(self, rows: np.ndarray, path: str, meta: dict) -> None:
        self.s.save_trajectory(rows, path, meta)

    def render_video(self, rows: np.ndarray, path: str) -> None:
        """The episode's video, after the verdict (it decides nothing): the rows replayed on this service's session."""
        import imageio.v2 as imageio
        rows = np.asarray(rows, dtype=np.float64)
        every = max(1, -(-len(rows) // 1500))
        self.s.render_video(rows, path, cameras=list(M.DEFAULT_CAMERAS), every=every, size=(240, 320))
        imageio.imwrite(os.path.splitext(path)[0] + ".last.png", self.s.render_frame("top", (self.H, self.W)))


def build() -> AbcSim:
    env = os.environ.get
    hw = [int(v) for v in env("RCB_IMAGE_HW", "480,640").split(",")]
    info = json.load(open(env("RCB_TASK_INFO", "/srv/task.json")))
    return AbcSim(env("RCB_INSTANCE", "/srv/instance.npz"), info, (hw[0], hw[1]))


if __name__ == "__main__":
    main(build)
