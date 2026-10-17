"""A stand-in for lmx_tool (scripts/libero-max/shared/lmx_tool.py) with no simulator, for the standard service's tests.

The robot is a point on a line: each control step moves it by 0.1 x dx; LIBERO's success check holds once it reaches
the instance's `goal` (the episode then ends: `done`), and the event fires the first time it passes `event_at`. The
instance JSON also says how the video pass behaves (`video`: ok | fail | hang | diverge). Every `--replay` run is logged
to $LMX_STUB_LOG with whether $RCB_DATA/final.json was already finalized at that moment (no replay may grade).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

N = 7
ACTION_NAMES = ["dx", "dy", "dz", "drx", "dry", "drz", "grip"]
DUMMY = [0.0] * 6 + [-1.0]


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def sha_of(x: float, t: int) -> str:
    return hashlib.sha256(np.array([x, t], np.float64).tobytes()).hexdigest()


def as_actions(a) -> np.ndarray:
    a = np.asarray(a, dtype=np.float64)
    if a.size == 0:
        return np.zeros((0, N))
    return np.clip(a.reshape(-1, N), -1.0, 1.0)


class Session:
    def __init__(self, instance="/app/instance.json", check: bool = True):
        self.inst = json.loads(Path(instance).read_text())
        if self.inst.get("crash_on_build"):
            raise RuntimeError("stub: the scene did not build")
        self.goal, self.event_at = float(self.inst.get("goal", 1.0)), float(self.inst.get("event_at", 0.3))
        self.x, self.t = float(self.inst.get("start_x", 0.0)), 0
        self.initial_state_sha = self.state_sha()
        if check and self.initial_state_sha != self.inst.get("initial_state_sha"):
            raise RuntimeError("stub RebuildMismatch")
        self.actions: list = []
        self.targets = np.array(DUMMY)
        self.done = self.success = False
        self.trigger_step = None
        self.instruction = "reach the goal"

    def step(self, action) -> dict:
        if self.done:
            raise RuntimeError("the episode is over")
        a = as_actions(action)[0]
        self.x = round(self.x + 0.1 * float(a[0]), 10)
        self.t += 1
        self.actions.append(a)
        self.targets = a
        if self.trigger_step is None and self.x >= self.event_at - 1e-9:
            self.trigger_step = self.t
        if self.x >= self.goal - 1e-9:
            self.done = self.success = True
        return self.report()

    def report(self) -> dict:
        return {"success": self.success, "done": self.done, "control_steps": self.t,
                "event_fired": self.trigger_step is not None, "event_step": self.trigger_step, "steps_left": 0}

    def result(self) -> dict:
        return {**self.report(), "state_sha": self.state_sha(), "initial_state_sha": self.initial_state_sha}

    def state_sha(self) -> str:
        return sha_of(self.x, self.t)

    def controller(self) -> dict:
        return {"control_freq": 20.0, "output_max": [0.05] * 3 + [0.5] * 3}

    def calibration(self, camera: str, hw: int) -> dict:
        return {"intrinsic_cv": [[1, 0, hw / 2], [0, 1, hw / 2], [0, 0, 1]], "cam2world_gl": np.eye(4).tolist(),
                "fovy_deg": 45.0, "hw": [hw, hw]}

    def robot_base(self) -> dict:
        return {"pos": [-0.66, 0.0, 0.912], "quat_wxyz": [1, 0, 0, 0]}

    def render(self, camera: str, hw: int = 256, depth: bool = False):
        img = np.full((4, 4, 3), int(self.x * 100) % 256, np.uint8)
        return (img, np.zeros((4, 4), np.float32)) if depth else img

    def proprio(self) -> np.ndarray:
        return np.r_[[self.x] + [0.0] * 22, self.targets].astype(np.float32)


def _replay_main(instance, actions_path, video=None) -> None:
    log = os.environ.get("LMX_STUB_LOG")
    if log:
        fin = Path(os.environ.get("RCB_DATA", "/data"), "final.json")
        try:
            finalized = bool(json.loads(fin.read_text()).get("finalized"))
        except (OSError, ValueError):
            finalized = False
        with open(log, "a") as f:
            f.write(json.dumps({"replay": True, "video": bool(video), "after_verdict": finalized}) + "\n")
    s = Session(instance)
    mode = s.inst.get("video", "ok")
    for row in np.load(actions_path):
        if s.done:
            break
        s.step(row)
    r = {**s.result(), "video_stride": 2}
    if mode == "diverge":
        r["state_sha"] = "0" * 64
    print(json.dumps(r), flush=True)
    if not video:
        return
    if mode == "hang":
        time.sleep(60)
    ok = mode != "fail"
    if ok:
        Path(video).write_bytes(b"mp4")
        Path(video.removesuffix(".mp4") + ".last.png").write_bytes(b"png")
    print(json.dumps({**r, "video": ok, "video_frames": 3, "video_skipped": 0}), flush=True)


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "--replay":
        _replay_main(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
