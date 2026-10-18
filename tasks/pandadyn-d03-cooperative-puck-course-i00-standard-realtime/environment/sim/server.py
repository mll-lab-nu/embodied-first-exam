"""eai-standard/2.3 sim service for Panda Dynamic Scenes' standard-realtime tasks -- the adapter behind the shared
realtime layer (`python /srv/rcb_realtime.py`, which imports this module and calls build(); docs/protocol/README.md §4b,
docs/benchmarks/pandadyn.md "Standard-realtime").

The simulator-specific half only: `PandaDyn` implements rcb_service.Sim (the contract documented in rcb_service.py) for
one frozen instance, on the benchmark's own tooling rcb_pandadyn.Session (ManiSkill 3.0.1 / SAPIEN 3.0.3, CPU PhysX at
1000 Hz, one or two Franka Pandas behind their Ruckig + torque servos) -- the same scene, action, success rule and
trajectory as the standard twin's eai-standard/2.2 service. The protocol, the clock, the plan, the episode, crash recovery
and the finalize are rcb_realtime.py's and rcb_service.py's, unchanged copies of the HumanoidBench sources
(ci_checks/check-tooling-identity.sh).

What the agent gets is what the standard twin gives, minus the 2.2 additions the realtime layer does not serve
(`/kinematics`, per-frame camera poses, depth modes): the two static cameras (RGB, z-depth on request) with their
calibration, the robot's own proprioception (the standard twin's columns: joints, fingers, hand TCP and tool poses,
velocities, apertures, motor torques, the targets in force) and the `joint_position` action (per arm 7 absolute joint
targets + the total aperture, clipped to the limits). Nothing about objects or fixtures leaves this process.

The verdict is the live episode's (owner, 2026-10-17, board 0151; docs/benchmarks/pandadyn.md "Grading"): the task's
own check as the graded episode ended in this process, judged by rcb_service after the agent's container is gone; nothing
is replayed to grade it. The task's check is the episode's end (the first control step where it succeeded or failed), so
there is no settle window to add (live_verdict below only records the phase and the end reason). The frozen start is
checked when the first episode begins: `start_sha` is the instance's recorded `initial_sha` (rcb_service refuses a scene
that starts elsewhere: instance_mismatch, an infrastructure failure). The video is rendered after the verdict from the
graded episode's rows by this process's Session (render_video: the scene rebuilt, the rows filmed).

Settings (environment/docker-compose.yaml): RCB_INSTANCE (the frozen instance), RCB_TEXTS (texts.json: the task text),
RCB_DATA, RCB_RESET_BUDGET, RCB_WALL_CLOCK_S, RCB_SLOWDOWN (rcb_realtime / rcb_service).
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ["RCB_SESSION_LOG"] = ""
import rcb_pandadyn as M  # noqa: E402

M.SESSION_LOG = ""           # the sidecar's Session is not the agent's interaction log
from rcb_service import main  # noqa: E402

JOINTS = [f"joint{i}" for i in range(1, 8)]
MOUNT = {"overview": "static, looking at the whole workspace from the front right, above the table",
         "closeup": "static, closer to the task's working area"}


class PandaDyn:
    """One frozen Panda Dynamic Scenes instance behind the rcb_service.Sim contract (see the module docstring)."""

    def __init__(self, instance: str, texts: dict):
        self.instance, self.texts = instance, texts
        self.I = json.load(open(instance))
        self.s = M.Session(self.I)               # not strict: rcb_service checks start_sha when the first episode begins
        self.start_sha = str(self.I["initial_sha"])  # the frozen instance's recorded start (rcb_pandadyn make-instance)
        self.arms = list(self.s.arm_ids)
        self.raw_dim = int(self.s.dim)
        self.control_dt = 1.0 / M.CONTROL_HZ
        self.max_control_steps = int(M.MAX_ROWS)                # the environment's cap; the task's horizon ends it first
        self.horizon_s = float(self.I["horizon_s"])
        self.cameras = tuple(M.CAMERAS)
        self.depth_cameras = self.cameras
        self.layout = [f"{a}_{j}" for a in self.arms for j in JOINTS + ["aperture"]]
        L = M._limits()
        self.lim = np.array([[lo, hi] for _a in self.arms for lo, hi in list(zip(L.LOWER, L.UPPER)) + [(0.0, M.APERTURE_MAX)]],
                            dtype=np.float64)
        qpos = [f"{a}_{j}" for a in self.arms for j in JOINTS + ["finger_left", "finger_right"]]
        self.proprio_layout = (qpos + [f"{a}_tcp_{k}" for a in self.arms for k in ("x", "y", "z", "qw", "qx", "qy", "qz")]
                               + [f"{q}_vel" for q in qpos] + [f"{a}_aperture_m" for a in self.arms]
                               + [f"{a}_{j}_torque" for a in self.arms for j in JOINTS]
                               + [f"{a}_tool_{k}" for a in self.arms for k in ("x", "y", "z", "qw", "qx", "qy", "qz")]
                               + [f"{a}_target_{j}" for a in self.arms for j in JOINTS + ["aperture"]])
        self.cam_info = self.s.camera_info(list(self.cameras))
        self.hw = {c: list(self.s.render_frame(c).shape[:2]) for c in self.cameras}   # warms up the renderer
        self.rs = self.s.robot_spec()
        self.cmd = np.asarray(self.s.hold_action(), dtype=np.float64)

    # ------------------------------------------------------------------ the rcb_service.Sim contract
    def spec(self) -> dict:
        na, nq = len(self.arms), 9 * len(self.arms)
        return {
            "simulator": "maniskill (Panda Dynamic Scenes on ManiSkill 3.0.1 / SAPIEN 3.0.3, CPU PhysX at 1000 Hz)",
            "robot": "franka-panda" if na == 1 else "franka-panda-bimanual",
            "task_text": self.texts["task_text"],
            "episode": ("an episode ends at the first control step where the task has succeeded (every phase in order) or "
                        "failed (a failure event, a forbidden contact, a safety-limit violation, an object out of bounds, or "
                        f"the task's horizon of {self.horizon_s:g} s of robot time, {int(round(self.horizon_s * M.CONTROL_HZ))} "
                        "control steps), when your time is up, or on a simulator error"),
            "action_types": {"joint_position": {
                "dim": self.raw_dim, "layout": self.layout,
                "lower": self.lim[:, 0].round(4).tolist(), "upper": self.lim[:, 1].round(4).tolist(),
                "units": "rad for <arm>_joint1..7 (absolute targets); <arm>_aperture: the total gripper opening target in "
                         "metres (0 = closed .. 0.08 = open)",
                "semantics": "the environment's own action, one row per 10 ms control step: each arm's servo turns its "
                             "latest targets into a jerk-limited reference motion (Ruckig, joints synchronised) within its "
                             "speed, acceleration and jerk limits (robot_spec.servo) and tracks it with torque control; rows "
                             "dt apart (a multiple of control_dt), `linear` (default: a straight line from the targets in "
                             "force) or `hold`; out-of-limit values are clipped and reported (meta clipped)"}},
            "cameras": {c: {"hw": self.hw[c], "mounted": MOUNT[c], "intrinsic_cv": self.cam_info[c]["intrinsic_cv"],
                            "extrinsic_cv": self.cam_info[c]["extrinsic_cv"], "cam2world_gl": self.cam_info[c]["cam2world_gl"],
                            "depth_range_m": self.cam_info[c]["depth_range_m"]} for c in self.cameras},
            "proprio_groups": {
                "joint_pos": [0, nq, "measured joint positions per arm (panda-0 first): joint1..7 (rad), finger_left, "
                                     "finger_right (m)"],
                "tcp_pose": [nq, 7 * na, "measured hand TCP pose per arm, x y z (m) + quaternion wxyz, world frame"],
                "joint_vel": [nq + 7 * na, nq, "measured joint velocities, the joints of joint_pos"],
                "gripper_opening": [2 * nq + 7 * na, na, "measured aperture per arm (m): 0 closed .. 0.08 open"],
                "joint_effort": [2 * nq + 8 * na, 7 * na, "the servo's commanded motor torques per arm, joint1..7 (N m)"],
                "tool_pose": [2 * nq + 15 * na, 7 * na, "each arm's task tool frame (the hand TCP without a tool), x y z + "
                                                        "wxyz, world frame"],
                "target": [2 * nq + 22 * na, 8 * na, "each arm's targets in force (joint1..7, aperture)"]},
            "static": {"arms": {a: {"role": self.rs["arms"][a]["role"], "tool": self.rs["arms"][a]["tool"]} for a in self.arms}},
            "world": {"frame": "the scene's world frame: z up, the table top is the plane z = 0; the arm bases are in "
                               "robot_spec.arms", "up": "+z", "units": {"length": "m", "angle": "rad", "time": "s"},
                      "quaternion_order": "wxyz",
                      "camera_axes": "intrinsic_cv / extrinsic_cv: OpenCV camera axes (x right, y down, z forward); "
                                     "cam2world_gl: OpenGL axes"},
            "robot_spec": self.rs,
            "depth": {"cameras": list(self.depth_cameras), "units": "z-depth in metres along the optical axis, pixel for "
                      "pixel with the camera's image; 0 = no reading"},
        }

    def interpolable(self, typ: str) -> bool:
        return True

    def images(self, cameras: list[str], depth: bool) -> tuple[dict, dict]:
        rgb, dep = {}, {}
        for c in cameras:
            rgb[c] = self.s.render_frame(c)                       # captures the camera (rendering never steps physics)
            if depth:
                dep[c] = self.s._depth_of(c)                      # the same capture's depth buffer
        return rgb, dep

    def proprio(self) -> np.ndarray:
        P, A = self.s.proprio(), self.arms
        cols = ([v for a in A for v in P[a]["q"]] + [v for a in A for v in P[a]["tcp_pose"]]
                + [v for a in A for v in P[a]["qd"]] + [P[a]["aperture"] for a in A]
                + [v for a in A for v in P[a]["torque"]] + [v for a in A for v in P[a]["tool_pose"]]
                + [v for a in A for v in P[a]["target"]])
        return np.array(cols, dtype=np.float32)

    def clip(self, typ: str, rows: np.ndarray) -> tuple[np.ndarray, list]:
        rows = np.asarray(rows, dtype=np.float64)
        out = np.clip(rows, self.lim[:, 0], self.lim[:, 1])
        report = [{"row": int(i), "index": int(j), "reason": f"{self.layout[j]} limit [{self.lim[j, 0]:.4f},{self.lim[j, 1]:.4f}]"}
                  for i, j in np.argwhere(out != rows)]
        return out, report

    def to_sim(self, typ: str, row: np.ndarray) -> np.ndarray:
        return np.asarray(row, dtype=np.float64)                  # clipped already: Session.step executes it as it is

    def command(self, typ: str) -> np.ndarray:
        return self.cmd

    def hold(self) -> tuple[str, np.ndarray]:
        return "joint_position", self.cmd

    def step(self, row: np.ndarray) -> tuple[bool, bool, dict]:
        over = self.s.step(row)
        self.cmd = np.asarray(row, dtype=np.float64).copy()
        return bool(over), bool(self.s.success()), ({"why": self.s.end_reason()} if over else {})

    def reset(self) -> None:
        self.s.reset()                                            # the scene rebuilt and reset with the instance's seed
        self.cmd = np.asarray(self.s.hold_action(), dtype=np.float64)

    def state_sha(self) -> str:
        return self.s.state_sha()

    def live_verdict(self, rows: np.ndarray, success: bool) -> dict:
        """The benchmark's own record of the live episode as it ended (no "success": the task's check already is the
        episode's end, so nothing is taken away): the phases completed and why the episode ended."""
        return {"phase": int(self.s.u.phase), "end_reason": self.s.end_reason() or ""}

    def save_trajectory(self, rows: np.ndarray, path: str, meta: dict) -> None:
        self.s.save_trajectory(rows, path, meta)

    def render_video(self, rows: np.ndarray, path: str) -> None:
        from PIL import Image
        self.s.render_video(rows, path, fps=25, camera="overview")
        Image.fromarray(self.s.render_frame("overview")).save(os.path.splitext(path)[0] + ".last.png")


def build() -> PandaDyn:
    env = os.environ.get
    texts = json.load(open(env("RCB_TEXTS", os.path.join(HERE, "texts.json"))))
    return PandaDyn(env("RCB_INSTANCE", os.path.join(HERE, "instance.json")), texts)


if __name__ == "__main__":
    main(build)
