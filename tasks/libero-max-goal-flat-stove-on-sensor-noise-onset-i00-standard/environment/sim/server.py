"""eai-standard/2.1 sim service for LIBERO-MAX -- the sidecar's entry point (`python /srv/server.py`).

The simulator-specific half only: `LiberoMax` implements rcb_service.Sim for one frozen instance (lmx_tool.Session).
The protocol, the episode, crash recovery and the finalize live in rcb_service.py (a byte copy of main's HumanoidBench /
VLABench service), which imports no simulator.
The verdict is the live episode's (docs/PROTOCOL.md H.4; owner, 2026-10-17, board 0151): the episode ends the moment
LIBERO's success check holds (step() reports it), and that is the success; nothing is replayed to grade it. The
frozen start is checked when the episode begins (start_sha: the instance's recorded start-state hash; a scene that
did not rebuild to it is refused as instance_mismatch, an infrastructure failure, before the agent is served).
live_verdict() adds LIBERO-MAX's event record of the live episode to final.json (event_fired, event_step).
The video is one video-only pass after the verdict is on disk: render_video() replays the trajectory in a fresh
process (one simulator per process, lmx_tool) with the camera on; it can neither change nor cost the verdict
(docs/benchmarks/libero-max.md, "Grading (standard mode)").
Settings come from environment/docker-compose.yaml:
  RCB_INSTANCE            the frozen instance (the privileged twin's instance.json)
  RCB_TASK_TEXT           the task as the instruction states it, for /spec
  RCB_EPISODE             what ends an episode, for /spec (the instruction's words)
  RCB_MAX_CONTROL_STEPS   technical episode cap (9000 = 450 s of robot time): the video pass of the longest episode
                          must finish inside the collect hook's wait (finalize.sh)
  LMX_VIDEO_BUDGET_S, LMX_VIDEO_MAX_FRAMES   the video's rendering bounds (lmx_tool: 240 s, 1200 frames)
  RCB_VIDEO_TIMEOUT_S     how long the video pass may take in all (5400 s, the collect hook's wait)
  RCB_IMAGE_HW            the side of every camera's image in pixels (256)
  RCB_RESET_BUDGET, RCB_WALL_CLOCK_S, RCB_DATA   the service's own (rcb_service.main)
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lmx_tool  # noqa: E402
from rcb_service import main  # noqa: E402

CAMERAS = ("agentview", "wrist")
# The video pass (render_video, after the verdict): a scene build, the episode's physics and the frames; at most this long
VIDEO_TIMEOUT_S = float(os.environ.get("RCB_VIDEO_TIMEOUT_S") or 5400)


def _result(line: str) -> dict | None:
    """A result line of `lmx_tool.py --replay` (JSON: the replay's outcome and its video), or None for anything else."""
    try:
        r = json.loads(line)
    except ValueError:
        return None
    return r if isinstance(r, dict) and "state_sha" in r and "success" in r else None


class LiberoMax:
    """One frozen LIBERO-MAX case behind the rcb_service.Sim contract. The agent never gets an object's pose, the goal
    or the success check, nor whether or when the event happened; they are live here only so the service can judge."""

    def __init__(self, instance: str, *, task_text: str = "", episode: str = "", image_hw: int = 256,
                 max_control_steps: int = 9000):  # fmt: skip
        self.instance = instance
        # check=False: the frozen start is checked by rcb_service when the episode begins (start_sha below), which
        # records a mismatch as instance_mismatch (infrastructure) instead of failing every start of the process
        self.s = lmx_tool.Session(instance, check=False)
        self.start_sha = str(self.s.inst.get("initial_state_sha") or "")   # the frozen instance's recorded start state
        self._live_sha: str | None = None    # the live episode's final state (live_verdict), for the video's record
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

    # ---------------------------------------------------------------- the verdict's record and the video
    def live_verdict(self, rows: np.ndarray, success: bool) -> dict:
        """LIBERO-MAX's record of the live episode, for final.json: whether, and at which control step (1-based; null if
        never), the case's event fired. No "success" key: LIBERO's rule is the live one (the episode ends the moment
        the success check holds, so no action can follow a success), applied by rcb_service as it ran."""
        live = self.s.report()
        self._live_sha = self.s.state_sha()
        return {"event_fired": bool(live["event_fired"]), "event_step": live["event_step"]}

    def save_trajectory(self, rows: np.ndarray, path: str, meta: dict) -> None:
        np.savez(path, actions=np.asarray(rows, np.float64), meta=np.array(lmx_tool.canonical(meta)))

    def render_video(self, rows: np.ndarray, path: str) -> None:
        """Called by rcb_service once the verdict is on disk: the episode's video, one replay of the trajectory in a fresh
        process (`lmx_tool.py --replay ... <video>`; one simulator per process) that renders agentview on the way. It
        decides nothing: what it says about success is not read, a failure raises (rcb_service then records video =
        false). Next to the video, replay.video.json says whether that replay ended in the live episode's final state
        (the video shows the live episode only then) and its stride (control steps per frame)."""
        tmp = tempfile.mkdtemp(prefix="video-")
        proc = None
        try:
            npy, video = os.path.join(tmp, "a.npy"), os.path.join(tmp, "replay.mp4")
            np.save(npy, lmx_tool.as_actions(rows))
            proc = subprocess.Popen(  # stderr: the service's own (the sidecar's log)
                [sys.executable, os.path.abspath(lmx_tool.__file__), "--replay", str(self.instance), npy, video],
                stdout=subprocess.PIPE, text=True,
            )  # fmt: skip
            try:
                out, _ = proc.communicate(timeout=VIDEO_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
                raise RuntimeError(f"the video pass did not finish in {VIDEO_TIMEOUT_S:g} s") from None
            # The last result line says whether the video is complete (the exit code may be a teardown's).
            results = [r for r in map(_result, out.splitlines()) if r is not None]
            if not (results and results[-1].get("video") and os.path.exists(video)):
                raise RuntimeError(f"the video pass recorded no video (exit {proc.returncode})")
            r = results[-1]
            shutil.move(video, path)
            png = video.removesuffix(".mp4") + ".last.png"
            if os.path.exists(png):
                shutil.move(png, path.removesuffix(".mp4") + ".last.png")
            rec = {"source": "video-only replay of trajectory.npz after the verdict (it decides nothing)",
                   "state_sha": r.get("state_sha"), "live_state_sha": self._live_sha,
                   "ends_in_live_state": r.get("state_sha") == self._live_sha, "event_step": r.get("event_step"),
                   "video_stride": r.get("video_stride"), "video_frames": r.get("video_frames"),
                   "video_skipped": r.get("video_skipped")}  # fmt: skip
            with contextlib.suppress(OSError):
                with open(os.path.join(os.path.dirname(path), "replay.video.json"), "w") as f:
                    json.dump(rec, f)
            if not rec["ends_in_live_state"]:
                print(f"[video] the video pass ended in {r.get('state_sha')}, the live episode in {self._live_sha}: "
                      "the video may not show the live episode", file=sys.stderr, flush=True)  # fmt: skip
        finally:
            if proc is not None and proc.poll() is None:
                proc.kill()
                proc.wait()
            shutil.rmtree(tmp, ignore_errors=True)


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
