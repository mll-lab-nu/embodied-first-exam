"""eai-standard/2.1 sim service for BiGym 2.0 -- the sidecar's entry point (`python /srv/server.py`; the standard-realtime
twin runs `python /srv/rcb_realtime.py`, which uses this adapter unchanged).

The simulator-specific half only: `BiGym2` implements rcb_service.Sim for one frozen instance, through rcb_bigym2.Episode
(upstream's official env and its coding-agent action contract). The protocol, the episode, crash recovery and the
finalize live in rcb_service.py / rcb_realtime.py, which import no simulator.
Settings come from environment/docker-compose.yaml:
  RCB_INSTANCE     the frozen instance (the privileged twin's instance.json)
  RCB_TASK_TEXT    the task, for /spec (the instruction's sentence)
  RCB_EPISODE      what ends an episode, for /spec (the instruction's words)
  RCB_IMAGE_HW     the side of every onboard camera's square image, pixels (default 84, upstream's)
  RCB_RESET_BUDGET, RCB_WALL_CLOCK_S, RCB_DATA, RCB_SLOWDOWN   the service's own
The verdict is the live episode's: step() reports upstream's is_success (the task's success held for 1 s,
no fall) and the episode ends where upstream ends it, so nothing is replayed to grade it; render_video() re-runs the
trajectory once, after the verdict, to film it. The frozen start is checked when the scene is built (instance_check: the
instance's t0 state exactly, or within upstream's tolerance on another CPU): a scene that does not rebuild it is
InstanceMismatch, and start_sha (the start this image accepts) is checked by rcb_service when an episode begins.
What leaves this process: the three onboard cameras' images and upstream's low-dimensional observation (the robot's
joint angles and velocities, gripper states, the pelvis pose its base controller tracks). Never an object's pose, the
success check or its parts.
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rcb_bigym2 import CAMERAS, Episode, load_instance, replay  # noqa: E402
from rcb_service import InstanceMismatch, main  # noqa: E402

ACTION = "whole_body"


class BiGym2:
    """One frozen BiGym 2.0 instance behind the rcb_service.Sim contract."""

    def __init__(self, instance: str, task_text: str = "", episode: str = "", image_hw: int = 84):
        self.instance = load_instance(instance)
        self.ep = Episode(self.instance, image_hw=image_hw)
        check = self.ep.instance_check(self.instance)
        if not check["ok"]:
            raise InstanceMismatch(f"this image does not rebuild the frozen instance's starting state (state "
                                   f"{self.ep.t0_sha}, instance {self.instance['t0']['state_sha']}, max joint deviation "
                                   f"{check['max_joint_dev']:.2e})")
        self.start_sha = self.ep.t0_sha   # the instance's start (exact, or within tolerance): every episode begins there
        self.task_text, self.episode = task_text, episode
        self.control_dt, self.max_control_steps = self.ep.control_dt, self.ep.horizon
        self.cameras, self.depth_cameras = CAMERAS, ()
        self.proprio_layout = list(self.ep.proprio_layout)
        self.raw_dim = self.ep.action_dim
        self.hw = int(image_hw)
        self.mounts = self.instance["t0"]["cameras"]
        self.facts = self.instance["t0"]["robot"]  # the robot's description: joint axes, camera mounts
        self.cmd = self.ep.hold_row()

    # ------------------------------------------------------------------ the rcb_service.Sim contract
    def spec(self) -> dict:
        ep = self.ep
        return {
            "simulator": "bigym2 (BiGym 2.0, bigym 1.0.0 at 93ad4b3; MuJoCo 3.8.1)",
            "robot": "Unitree G1 29-DoF with Dex1-1 two-finger grippers; NVIDIA's GR00T-WBC drives the legs and waist",
            "task_text": self.task_text,
            "episode": self.episode,
            "action_types": {ACTION: {
                "dim": ep.action_dim, "layout": ep.layout,
                "lower": [round(float(x), 4) for x in ep.lo], "upper": [round(float(x), 4) for x in ep.hi],
                "units": "vx, vy: walking velocity command, m/s, the robot's frame (x forward, y left); height: pelvis "
                         "height command, m; wz: turning rate command, rad/s (+ turns left); pitch (when present): torso "
                         "lean command, rad (+ leans forward); *_joint: absolute arm joint targets, rad; left_gripper, "
                         "right_gripper: 0 open .. 1 closed",
                "semantics": "rows dt apart (a multiple of control_dt); each control step's command is the row (hold) or "
                             "a straight line from the previous row's (linear); values outside lower/upper are clipped "
                             "and reported. The whole-body controller turns the base commands into leg and waist "
                             "motion every control step; it keeps the robot balanced but does not stop it from "
                             "walking into things"}},
            "cameras": {c: {"mounted": "head" if c == "head" else "wrist", "hw": [self.hw, self.hw],
                            "fovy_deg": self.mounts[c]["fovy_deg"],
                            "pose_t0": {"frame": "the robot at t = 0: origin on the floor under the pelvis, x the way it "
                                                 "faces, y left, z up", **{k: self.mounts[c][k] for k in
                                                                           ("position_m", "forward", "up", "right")}},
                            "mount": {"frame": self.facts["camera_mount_frame"], **self.facts["camera_mounts"][c]}}
                        for c in CAMERAS},
            "joints": self.facts["joints"],
            "joint_frame": self.facts["frame"],
            "joint_sign": self.facts["joint_sign"],
            "grippers": {"meaning": self.facts["gripper_point"], **self.facts["grippers"]},
            "proprio": {"source": "upstream's low-dimensional observation (bigym), as its learned policies receive it",
                        "units": "*_pos: rad for the hinge joints, m for the grippers' finger joints (*_dex1_finger_joint_*, "
                                 "slides) and for pelvis_x_pos, pelvis_y_pos, pelvis_z_pos (pelvis_rz_pos: rad); *_vel: "
                                 "the same per second; *_gripper_state 0 open .. 1 closed; pelvis_x, pelvis_y, pelvis_z m "
                                 "and pelvis_yaw rad: the pelvis pose the base controller tracks, in the room's frame "
                                 "(z up)"},
        }

    def interpolable(self, typ: str) -> bool:
        return True

    def images(self, cameras: list[str], depth: bool) -> tuple[dict, dict]:
        return {c: self.ep.image(c) for c in cameras}, {}

    def proprio(self) -> np.ndarray:
        return self.ep.proprio()

    def clip(self, typ: str, rows: np.ndarray) -> tuple[np.ndarray, list]:
        if typ != ACTION:
            raise ValueError(f"the action type is {ACTION!r}")
        out = np.clip(rows, self.ep.lo, self.ep.hi)
        report = [{"row": int(i), "index": int(j), "reason": f"{self.ep.layout[j]} outside "
                   f"[{self.ep.lo[j]:g}, {self.ep.hi[j]:g}]"} for i, j in np.argwhere(out != rows)]
        # At the precision the simulator applies (float32, upstream's EnvTools), which command() also gives back.
        return out.astype(np.float32).astype(np.float64), report

    def to_sim(self, typ: str, row: np.ndarray) -> np.ndarray:
        return np.asarray(row, dtype=np.float32).astype(np.float64)

    def command(self, typ: str) -> np.ndarray:
        return self.cmd

    def hold(self) -> tuple[str, np.ndarray]:
        """Stand still: the last command with zero walking and turning velocity (rcb_bigym2.Episode.hold_row)."""
        return ACTION, self.ep.hold_row()

    def step(self, row: np.ndarray) -> tuple[bool, bool, dict]:
        done = self.ep.step(row)
        self.cmd = np.asarray(row, dtype=np.float64)
        return done, self.ep.success(), ({"outcome": self.ep.outcome()} if done else {})

    def reset(self) -> None:
        self.ep.reset()
        self.cmd = self.ep.hold_row()

    def state_sha(self) -> str:
        return self.ep.state_sha()

    def save_trajectory(self, rows: np.ndarray, path: str, meta: dict) -> None:
        np.savez(path, actions=np.asarray(rows, dtype=np.float64).reshape(-1, self.raw_dim),
                 layout=np.array(self.ep.layout), task=self.ep.task,
                 **{k: str(v) for k, v in meta.items()})

    def render_video(self, rows: np.ndarray, path: str) -> None:
        """The episode's video, after the verdict: the trajectory re-run once from the frozen instance, filmed."""
        replay(self.instance, rows, video=path)
        try:  # the last frame, for the verifier's evidence
            import subprocess
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-sseof", "-0.1", "-i", path, "-frames:v", "1",
                            path[: -len(".mp4")] + ".last.png"], check=False, timeout=60)
        except Exception:  # noqa: BLE001
            pass


def build() -> BiGym2:
    env = os.environ.get
    return BiGym2(env("RCB_INSTANCE", "/srv/instance.json"), task_text=env("RCB_TASK_TEXT", ""),
                  episode=env("RCB_EPISODE", ""), image_hw=int(env("RCB_IMAGE_HW") or 84))


if __name__ == "__main__":
    main(build)
