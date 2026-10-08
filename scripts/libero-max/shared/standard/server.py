"""eai-standard/2.1 sim service for LIBERO-MAX -- the sidecar's entry point (`python /srv/server.py`).

The simulator-specific half only: `LiberoMax` implements rcb_service.Sim for one frozen instance (lmx_tool.Session).
The protocol, the episode, crash recovery and the finalize live in rcb_service.py (a byte copy of main's HumanoidBench /
VLABench service), which imports no simulator. One simulator per process (lmx_tool): the fresh replay that grades the
episode and the replay video each run in a new process.
Settings come from environment/docker-compose.yaml:
  RCB_INSTANCE            the frozen instance (the privileged twin's instance.json)
  RCB_TASK_TEXT           the task as the instruction states it, for /spec
  RCB_EPISODE             what ends an episode, for /spec (the instruction's words)
  RCB_MAX_CONTROL_STEPS   technical episode cap (9000 = 450 s of robot time): the fresh replay that grades the episode
                          must finish inside the collect hook's timeout
  RCB_IMAGE_HW            the side of every camera's image in pixels (256)
  RCB_RESET_BUDGET, RCB_WALL_CLOCK_S, RCB_DATA   the service's own (rcb_service.main)
"""

from __future__ import annotations

import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lmx_tool  # noqa: E402
from rcb_service import main  # noqa: E402

CAMERAS = ("agentview", "wrist")


class LiberoMax:
    """One frozen LIBERO-MAX case behind the rcb_service.Sim contract. The agent never gets an object's pose, the goal
    or the success check, nor whether or when the event happened; they are live here only so the service can judge."""

    def __init__(self, instance: str, *, task_text: str = "", episode: str = "", image_hw: int = 256,
                 max_control_steps: int = 9000):  # fmt: skip
        self.instance = instance
        self.s = lmx_tool.Session(instance)
        self.task_text = task_text or self.s.instruction
        self.episode = episode
        self.hw = int(image_hw)
        ctl = self.s.controller()
        self.control_dt = 1.0 / ctl["control_freq"]
        self.max_control_steps = int(max_control_steps)
        self.cameras = CAMERAS
        self.depth_cameras = CAMERAS
        self.raw_dim = lmx_tool.N
        self.lower, self.upper = -np.ones(lmx_tool.N), np.ones(lmx_tool.N)
        self.out_max = ctl["output_max"]
        self.proprio_layout = (
            ["eef_x", "eef_y", "eef_z", "eef_qw", "eef_qx", "eef_qy", "eef_qz", "finger_left", "finger_right"]
            + [f"joint{i}_pos" for i in range(1, 8)]
            + [f"joint{i}_vel" for i in range(1, 8)]
            + [f"cmd_{a}" for a in lmx_tool.ACTION_NAMES]
        )

    # ---------------------------------------------------------------- what the agent may know
    def calibrations(self) -> dict:
        return {c: self.s.calibration(c, self.hw) for c in CAMERAS}

    def spec(self) -> dict:
        cams = {}
        for c, cal in self.calibrations().items():
            cams[c] = {"hw": [self.hw, self.hw], "intrinsic_cv": cal["intrinsic_cv"], "cam2world_gl": cal["cam2world_gl"],
                       "mounted": "on the hand (moves with it)" if c == "wrist" else "fixed",
                       "note": "the pose and intrinsics at the start; every submit response carries the current ones "
                               "(meta['cameras_now'])"}  # fmt: skip
        base = self.s.robot_base()["pos"]
        return {
            "simulator": "LIBERO (robosuite 1.4.0, MuJoCo 3.2.6) with LIBERO-PRO's task variant and LIBERO-MAX's event",
            "robot": "Franka Emika Panda on a fixed mount, 2-finger gripper, LIBERO's OSC_POSE controller",
            "task_text": self.task_text,
            "episode": self.episode,
            "frames": (
                f"world frame: metres; the robot's base is at ({', '.join(f'{v:g}' for v in base)}) facing +x: x forward "
                "(away from the base, across the table), y to the robot's left, z up; quaternions w x y z"
            ),
            "action_types": {
                "ee_delta": {
                    "dim": lmx_tool.N,
                    "layout": lmx_tool.ACTION_NAMES,
                    "lower": self.lower.tolist(),
                    "upper": self.upper.tolist(),
                    "units": (
                        f"dx, dy, dz: 1.0 = {self.out_max[0]:g} m of hand-target motion per control step; drx, dry, drz: "
                        f"1.0 = {self.out_max[3]:g} rad of rotation per control step (axis-angle, world frame); "
                        "grip: -1 open, +1 close"
                    ),
                    "dtype": "float64",
                    "semantics": (
                        "LIBERO's native action: a delta for the operational-space controller (OSC_POSE), applied for one "
                        "control step (1/20 s); values outside [-1, 1] are clipped"
                    ),
                },
                "not_yet": ["joint_position", "ee_pose"],
            },
            "cameras": cams,
        }

    def interpolable(self, type: str) -> bool:
        return True

    def images(self, cameras: list[str], depth: bool) -> tuple[dict, dict]:
        rgb, dep = {}, {}
        for c in cameras:
            if depth and c in self.depth_cameras:
                rgb[c], dep[c] = self.s.render(c, self.hw, depth=True)
            else:
                rgb[c] = self.s.render(c, self.hw)
        return rgb, dep

    def proprio(self) -> np.ndarray:
        return self.s.proprio()

    # ---------------------------------------------------------------- actions
    def clip(self, type: str, rows: np.ndarray) -> tuple[np.ndarray, list]:
        out = np.clip(rows, self.lower, self.upper)
        clipped = [
            {"row": int(r), "index": int(i), "reason": "outside [-1, 1]"}
            for r, i in zip(*np.nonzero(out != rows), strict=True)
        ]
        return out, clipped

    def to_sim(self, type: str, row: np.ndarray) -> np.ndarray:
        return np.asarray(row, dtype=np.float64)

    def command(self, type: str) -> np.ndarray:
        return self.s.targets.copy()

    def hold(self) -> tuple[str, np.ndarray]:
        return "ee_delta", np.r_[np.zeros(6), self.s.targets[6]]  # no motion, the gripper as commanded last

    def step(self, row: np.ndarray) -> tuple[bool, bool, dict]:
        r = self.s.step(row)
        return r["done"], r["success"], {"cameras_now": self.calibrations()}

    def reset(self) -> None:
        raise RuntimeError("this service runs one episode per process (no reset capability)")

    def state_sha(self) -> str:
        return self.s.state_sha()

    # ---------------------------------------------------------------- grading and evidence
    def verify(self, rows: np.ndarray) -> dict:
        r = lmx_tool.replay_fresh(rows, self.instance)
        live = self.s.report()
        return {
            "success": r["success"] and "invalid" not in r,
            "state_sha": r["state_sha"],
            # final.json evidence (rcb_service merges `extra` into the verdict): whether, and at which control step
            # (1-based; null if never), the case's event fired in the live episode and in the fresh replay.
            "extra": {
                "event_fired": bool(live["event_fired"]),
                "event_step": live["event_step"],
                "replay_event_fired": bool(r.get("event_fired")),
                "replay_event_step": r.get("event_step"),
            },
        }

    def save_trajectory(self, rows: np.ndarray, path: str, meta: dict) -> None:
        np.savez(path, actions=np.asarray(rows, np.float64), meta=np.array(lmx_tool.canonical(meta)))

    def render_video(self, rows: np.ndarray, path: str) -> None:
        lmx_tool.replay_fresh(rows, self.instance, video=path)


def build() -> LiberoMax:
    env = os.environ.get
    return LiberoMax(
        env("RCB_INSTANCE", "/srv/instance.json"),
        task_text=env("RCB_TASK_TEXT", ""),
        episode=env("RCB_EPISODE", ""),
        image_hw=int(env("RCB_IMAGE_HW") or 256),
        max_control_steps=int(env("RCB_MAX_CONTROL_STEPS") or 9000),
    )


if __name__ == "__main__":
    os.environ.setdefault("LMX_TRACE", os.path.join(tempfile.gettempdir(), "lmx-trace.jsonl"))
    main(build)
