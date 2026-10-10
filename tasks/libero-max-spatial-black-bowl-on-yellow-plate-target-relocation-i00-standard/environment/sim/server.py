"""eai-standard/2.1 sim service for LIBERO-MAX -- the sidecar's entry point (`python /srv/server.py`).

The simulator-specific half only: `LiberoMax` implements rcb_service.Sim for one frozen instance (lmx_tool.Session).
The protocol, the episode, crash recovery and the finalize live in rcb_service.py (a byte copy of main's HumanoidBench /
VLABench service), which imports no simulator. One simulator per process (lmx_tool): the fresh replay that grades the
episode runs in a new process and records the replay video on the way. verify() returns the verdict the moment that
process prints it (rcb_service writes it to final.json at once); the process then finishes the video on its own and
render_video() only collects it. The video can neither change nor cost the verdict, and never causes a second replay
(lmx_tool._ReplayVideo; the budget is in docs/benchmarks/libero-max.md, "Collect budget").
Settings come from environment/docker-compose.yaml:
  RCB_INSTANCE            the frozen instance (the privileged twin's instance.json)
  RCB_TASK_TEXT           the task as the instruction states it, for /spec
  RCB_EPISODE             what ends an episode, for /spec (the instruction's words)
  RCB_MAX_CONTROL_STEPS   technical episode cap (9000 = 450 s of robot time): the fresh replay that grades the episode
                          must finish inside the collect hook's wait (finalize.sh)
  LMX_VIDEO_BUDGET_S, LMX_VIDEO_MAX_FRAMES   the replay video's bounds (lmx_tool: 240 s, 1200 frames)
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
import traceback

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lmx_tool  # noqa: E402
from rcb_service import main  # noqa: E402

CAMERAS = ("agentview", "wrist")
VIDEO_CLOSE_S = 120.0  # after the verdict: how long the replay process may take to finish its video (render_video)


def _result(line: str) -> dict | None:
    """A result line of `lmx_tool.py --replay` (JSON with the verdict), or None for anything else on its stdout."""
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
        self._replay: tuple | None = None  # the grading replay still finishing its video (verify -> render_video)
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
        # The replay that grades the episode also records the video, in the same fresh process: a second replay for
        # the video would start after the verdict and outlast the collect hook for every long episode. The verdict
        # comes first: the process prints it when the last action is executed, verify() returns it at once, and
        # rcb_service puts it on disk before render_video() waits for the video. Rendering reads the scene and never
        # steps physics (the state hash is the same), a failing video only switches itself off inside that process,
        # and its cost before the verdict is bounded (lmx_tool._ReplayVideo). Only a replay process that dies before
        # its verdict (a crash in native code) is replayed again, without a video.
        r = self._replay_with_video(rows)
        if r is None:
            try:
                r = lmx_tool.replay_fresh(rows, self.instance)
            except subprocess.CalledProcessError as exc:  # no verdict: say why in the sidecar's log, then fail
                print(f"[verify] the replay failed (exit {exc.returncode}):\n{(exc.stderr or '')[-3000:]}",
                      file=sys.stderr, flush=True)  # fmt: skip
                raise
        live = self.s.report()
        return {
            "success": r["success"] and "invalid" not in r,
            "state_sha": r["state_sha"],
            # final.json evidence (rcb_service merges `extra` into the verdict): whether, and at which control step
            # (1-based; null if never), the case's event fired in the live episode and in the fresh replay; and how
            # many control steps one frame of replay.mp4 stands for (2 = real time; more = a time-lapse).
            "extra": {
                "event_fired": bool(live["event_fired"]),
                "event_step": live["event_step"],
                "replay_event_fired": bool(r.get("event_fired")),
                "replay_event_step": r.get("event_step"),
                "replay_video_stride": r.get("video_stride"),
            },
        }

    def _replay_with_video(self, rows: np.ndarray) -> dict | None:
        """Start the grading replay with a video in a fresh process and return its verdict as soon as it is printed;
        the process is left running to finish the video (render_video). None if it ended without a verdict."""
        self._drop_replay()
        tmp = tempfile.mkdtemp(prefix="verdict-")
        proc = None
        try:
            npy, video = os.path.join(tmp, "a.npy"), os.path.join(tmp, "replay.mp4")
            np.save(npy, lmx_tool.as_actions(rows))
            proc = subprocess.Popen(  # stderr: the service's own (the sidecar's log)
                [sys.executable, os.path.abspath(lmx_tool.__file__), "--replay", str(self.instance), npy, video],
                stdout=subprocess.PIPE, text=True,
            )  # fmt: skip
            while True:
                line = proc.stdout.readline()
                if not line:
                    break
                r = _result(line)
                if r is not None:
                    self._replay = (proc, tmp, video)
                    return r
            print(f"[verify] the replay with a video ended without a verdict (exit {proc.wait()}); replaying without "
                  "one", file=sys.stderr, flush=True)  # fmt: skip
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait()
        shutil.rmtree(tmp, ignore_errors=True)
        return None

    def _drop_replay(self) -> None:
        if self._replay is not None:
            (proc, tmp, _), self._replay = self._replay, None
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            shutil.rmtree(tmp, ignore_errors=True)

    def save_trajectory(self, rows: np.ndarray, path: str, meta: dict) -> None:
        np.savez(path, actions=np.asarray(rows, np.float64), meta=np.array(lmx_tool.canonical(meta)))

    def render_video(self, rows: np.ndarray, path: str) -> None:
        """Called by rcb_service once the verdict is on disk: wait for the replay that graded these rows to finish its
        video (the final frame and the encoder's flush: seconds) and move it into place. Raises when there is none
        (rcb_service then records video = false and finalizes); the episode is never replayed again for a video."""
        if self._replay is None:
            raise RuntimeError("the grading replay recorded no video")
        (proc, tmp, video), self._replay = self._replay, None
        try:
            try:
                proc.wait(timeout=VIDEO_CLOSE_S)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                raise RuntimeError(f"the replay did not finish its video {VIDEO_CLOSE_S:g} s after its verdict") from None
            # The last result line says whether the video is complete (the exit code may be a teardown's).
            results = [r for r in map(_result, proc.stdout.read().splitlines()) if r is not None]
            if not (results and results[-1].get("video") and os.path.exists(video)):
                raise RuntimeError(f"the replay recorded no video (exit {proc.returncode})")
            shutil.move(video, path)
            png = video.removesuffix(".mp4") + ".last.png"
            if os.path.exists(png):
                shutil.move(png, path.removesuffix(".mp4") + ".last.png")
        finally:
            with contextlib.suppress(Exception):
                proc.stdout.close()
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
