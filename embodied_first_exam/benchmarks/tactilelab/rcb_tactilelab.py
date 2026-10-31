"""
rcb_tactilelab.py - task-local tooling for the TactileLab tasks (dual-arm X-Trainer whose right gripper carries two GelSight Mini
tactile sensors; Isaac Sim 5.1 / Isaac Lab 2.3.2): frozen instance, action recording, fresh-process replay.

Concepts
--------
instance   : one task in its fixed nominal scene (`seed`), the physics device it is frozen on (`device`: PhysX on the GPU,
             as the tasks were developed; a fresh process replays a scene bit for bit on the same machine, the Newton
             sidecar's deformable body included) and the hash of the full scene state after reset (`state_sha`: robot
             joint positions / velocities / targets, every rigid object's pose and velocity, the deformable body's
             particles). On load, `instance_exact` = `instance_matches` = hash equality: a scene that rebuilds to another
             hash is not the frozen instance (PROTOCOL §4: `instance_mismatch`, no verdict). The reset settles the scene
             with PhysX on the GPU, so the hash is exact on the GPU model the instances were frozen on (an L40S) and is
             not guaranteed on another model (the tasks' `gpu_types`). `frozen_on` records the GPU, its driver and the
             CUDA runtime the hash was taken with (host_gpu(); a record, not part of the check); every replay and the
             standard service record the host's own beside the hash they rebuilt.
trajectory : the (T, 22) rows handed to the robot, one per control step (60 Hz: physics 1/120 s, decimation 2):
               0-6   right end-effector target  x y z qw qx qy qz   (env frame, metres; the tactile gripper)
               7-13  left end-effector target   x y z qw qx qy qz
               14,15 right / left gripper: 0 = open, 1 = closed (exactly 0 or 1)
               16,17 optional right / left finger gap override in metres (NaN = use the open / closed command)
               18-21 optional right finger drive settings, applied from this step on (NaN = unchanged): velocity limit
                     (m/s), effort limit (N), stiffness (N/m), damping (N s/m); each within FINGER_DRIVE_RANGE (the
                     drive's own maxima: the stock 0.2 m/s and 20 N are as fast and as strong as it gets); stock values
                     FINGER_DRIVE_STOCK. They act only in the tasks of FINGER_DRIVE_TASKS (the rigid assembly tasks);
                     elsewhere they are checked and recorded but change nothing
             The right gripper's final release is physical: an open command (1 -> 0 on column 14) after a close counts as
             a release once the fingers have opened; a new close command withdraws it.
             An arm's seven numbers are all NaN (that arm holds where it is) or all finite: a target within +-2 m of
             the robot base (ROBOT_BASE, per axis) with a quaternion of non-zero length. The targets are tracked by a
             differential IK and the joint PD drives. Every finite number must fit a float32 (|x| < 3.4e38); the
             standard twin refuses the same rows (row_problem). A trajectory holds at most max_rows(task) rows; a
             replay holds the last row for SETTLE_STEPS more steps before the task is judged.
             Task code a scripted policy calls to change the drive (set_finger_limits, set_finger_gains,
             restore_finger_limits) is turned into the next row's columns 18-21 (restore: the explicit stock values), so
             a replay reproduces it.
budget     : no step budget. One technical episode cap per task, max_control_steps(task) = max_rows(task) + SETTLE_STEPS:
             the most control steps a replay steps (the row cap, 30,000 rows, 4,800 for the tasks with a deformable body,
             whose replays step at 1-4 control steps/s, and the settle), and the most a standard episode runs (its
             /spec max_control_steps; its recorded trajectory stays within max_rows, so the privileged CLI replays it).
grading    : replays(task) fresh-process replays (2, whose final-state hashes must agree; 1 for the dough tasks by the
             task's declared choice: their MPM solver is not guaranteed to replay bit for bit). replay_limit_s(task, rows):
             each replay's wall clock, from the trajectory's length and the task's slowest measured replay pace (oracle
             replays and stress trajectories, TASK_LIMITS). Whose failure a replay's failure is: tests/grade.py and
             tasks/tactilelab/README.md (from the first row on, an error the simulator raises on the rows is the agent's;
             a time-out, a Newton sidecar failure, a GPU or host error (HOST_FAULT) or an own-signal crash is replayed
             once more and is the agent's only when it repeats at about the same step, a reference replay shows the
             host healthy, a time-out is slow even scaled to the measurement host, and no replay got past it).

CLI
---
  python rcb_tactilelab.py make-instance --task insert_hdmi --seed 0 --out instance.json
  python rcb_tactilelab.py replay        --task insert_hdmi --instance instance.json --traj traj.npz [--result r.json]
                                         [--video replay.mp4 [--fps 15] [--video-deadline-s S]] [--final-state f.npz]
  python rcb_tactilelab.py run-oracle    --task insert_hdmi --instance instance.json --code oracle.py --out traj.npz

Python (what the agent gets)
----------------------------
  from rcb_tactilelab import Session
  s = Session("insert_hdmi", instance="/app/instance.json")   # ~1 min: Isaac Sim launch + scene build
  s.reset()                       # back to the frozen initial state (unlimited)
  s.objects()                     # name -> {"position", "orientation_wxyz"}
  s.proprio()                     # joint_pos (16), right / left end-effector pose, gripper widths
  s.tactile()                     # per gel pad: height map (60, 80) mm, contact mask, press depth; RGB with tactile_rgb=True
  s.step(row)                     # one control step with a (22,) row (layout above; 16 or 18 numbers are padded with NaN)
  s.move_ee(arm, pose7, steps)    # straight-line interpolation of one arm's target over `steps` control steps
  s.set_gripper(arm, closed, steps)
  s.record_start(); ...; actions = s.record_stop()
  s.render_frame("wrist_right_rgb", hfov_deg=90)   # cameras=True: a wrist image, optionally a narrower field of view
  s.camera_intrinsics("wrist_right_rgb", hfov_deg=90)
  s.status()                      # {'success', 'sim_steps', 'resets', 'state_sha', 'metrics'}
  s.replay(actions)               # resets (not in a fresh process), replays open loop, returns status
  s.save_trajectory(actions, "/app/output/trajectory.npz")
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

ACTION_DIM = 22
MAX_ROWS = 30000  # the most rows a trajectory may hold (the grader rejects a longer one); max_rows(task) per task
SETTLE_STEPS = 60
MAX_STEPS = MAX_ROWS + SETTLE_STEPS  # runaway guard of one episode: a full trajectory and the replay's settle fit
# Per task: (the most rows a trajectory may hold, the slowest replay pace measured on an L40S in control steps per second
# of wall clock after Isaac's start; the soft tasks' pace includes their Newton sidecar). The pace is the slower of the
# oracle's grading replays and a stress replay: the oracle's rows with the right wrist 3 cm lower (pressed into the
# objects and the table), a +-3 cm random walk on both wrists and the finger drive at its maxima, four replays sharing two
# GPUs on a loaded host. The stress replay was up to 2.2 x slower than the oracle's (cloth_edge_feed).
TASK_LIMITS = {
    "cable_needle_thread": (4800, 2.31), "cable_route_channel": (4800, 2.5), "cable_slack_reduce": (4800, 3.18),
    "cloth_edge_feed": (4800, 1.3), "cloth_fold_half": (4800, 1.48), "dough_fill_tray": (4800, 8.53),
    "dough_press_thickness": (4800, 3.93), "dough_target_shape": (4800, 3.9), "drawer_container": (30000, 12.3),
    "fem_plug_insert": (4800, 1.38), "gear_mesh": (30000, 10.7), "handover": (30000, 12), "insert_hdmi": (30000, 10.8),
    "insert_tube": (30000, 10.9), "lamp_bulb": (30000, 13.1), "lift": (30000, 10.9), "nut_thread": (30000, 10.9),
    "one_leg": (30000, 12.7), "sleeve_pull_on_forearm": (4800, 1.06), "square_table": (30000, 11.3),
}
ONE_REPLAY = ("dough_fill_tray", "dough_press_thickness", "dough_target_shape")  # MPM: not guaranteed bit for bit
# The right fingers' drive (action columns 18-21): stock values (PhysX, as the robot is built) and accepted ranges
# (lo, hi]: velocity limit m/s, effort limit N, stiffness N/m, damping N s/m. 0.2 m/s and 20 N are the drive's maxima
# (its stock values); a stiffness of 10,000 saturates the drive at its effort limit (a constant-force jaw).
FINGER_DRIVE_STOCK = (0.2, 20.0, 200.0, 40.0)
FINGER_DRIVE_RANGE = ((0.0, 0.2), (0.0, 20.0), (0.0, 10000.0), (0.0, 1000.0))
FINGER_DRIVE_NAMES = ("velocity limit (m/s)", "effort limit (N)", "stiffness (N/m)", "damping (N s/m)")
# the tasks whose robot takes the drive settings (the rigid assembly tasks); in the others columns 18-21 change nothing
FINGER_DRIVE_TASKS = ("drawer_container", "gear_mesh", "insert_hdmi", "insert_tube", "lamp_bulb", "nut_thread", "one_leg",
                      "square_table")
F32_MAX = 3.4e38
ROBOT_BASE = (-0.5, 0.0, 1.1)   # the robot base in the env frame (tactilelab_tasks.core.types.ROBOT_BASE_POS; Session checks it)
BOX_M = 2.0                     # an end-effector target lies within +-BOX_M of ROBOT_BASE on every axis


def row_problem(r) -> str | None:
    """Why a (22,) action row cannot be stepped (None: it can); rows_problem() over one row."""
    return rows_problem(np.asarray(r, dtype=np.float64).reshape(1, -1), numbered=False)


def rows_problem(acts, numbered: bool = True) -> str | None:
    """The first reason a (T, 22) array's rows cannot be stepped, or None. The same checks as the standard twin's
    (a 400 there): inf or a number too large for a float32; a gripper command other than 0 or 1; an arm whose seven
    numbers are neither all NaN (hold) nor all finite; a target outside +-BOX_M of ROBOT_BASE on some axis; a
    quaternion of (almost) zero length; a finger drive setting outside FINGER_DRIVE_RANGE (NaN = unchanged)."""
    a = np.asarray(acts, dtype=np.float64)
    if a.ndim != 2 or a.shape[1] != ACTION_DIM:
        return f"rows have {ACTION_DIM} numbers"
    at = (lambda k: f"row {k}: ") if numbered else (lambda k: "")
    fin = np.isfinite(a)
    big = np.isinf(a) | (np.abs(np.where(fin, a, 0.0)) >= F32_MAX)
    if np.any(big):
        return at(int(np.argmax(big.any(1)))) + "a number is inf or too large for a float32"
    g = a[:, 14:16]
    bad = ~((g == 0.0) | (g == 1.0))
    if np.any(bad):
        return at(int(np.argmax(bad.any(1)))) + "gripper commands (columns 14, 15) must be 0 (open) or 1 (closed)"
    base = np.asarray(ROBOT_BASE)
    for arm, name in ((0, "right"), (1, "left")):
        s7, f7 = a[:, 7 * arm:7 * arm + 7], fin[:, 7 * arm:7 * arm + 7]
        part = f7.any(1) & ~f7.all(1)
        if np.any(part):
            return at(int(np.argmax(part))) + f"the {name} target has some but not all of its seven numbers NaN (all NaN = hold)"
        on = f7.all(1)
        out = on & (np.max(np.abs(np.where(on[:, None], s7[:, :3] - base, 0.0)), axis=1) > BOX_M)
        if np.any(out):
            k = int(np.argmax(out))
            return at(k) + (f"the {name} target {[round(float(v), 4) for v in s7[k, :3]]} is outside the +-{BOX_M:g} m box "
                            "around the robot's base (metres, env frame)")
        short = on & (np.linalg.norm(np.where(on[:, None], s7[:, 3:], 1.0), axis=1) < 1e-6)
        if np.any(short):
            return at(int(np.argmax(short))) + f"the {name} quaternion has (almost) zero length"
    for i, (lo, hi) in enumerate(FINGER_DRIVE_RANGE):
        c = a[:, 18 + i]
        bad = np.isfinite(c) & ~((c > lo) & (c <= hi))
        if np.any(bad):
            k = int(np.argmax(bad))
            return at(k) + (f"column {18 + i}, the right finger {FINGER_DRIVE_NAMES[i]}, must be in ({lo:g}, {hi:g}] or NaN, "
                            f"got {float(c[k])!r}")
    return None


def host_gpu() -> dict[str, str]:
    """The GPU model, its driver and the CUDA runtime of this process (a record beside an instance hash)."""
    out: dict[str, str] = {}
    try:
        import subprocess

        q = subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader", "-i", "0"],
                           capture_output=True, text=True, timeout=30).stdout.strip().splitlines()
        if q:
            out["gpu"], out["driver"] = (x.strip() for x in q[0].split(",", 1))
    except Exception:  # noqa: BLE001 - a record only
        pass
    try:
        import torch

        out["cuda"] = str(torch.version.cuda)
    except Exception:  # noqa: BLE001
        pass
    return out


# The host's kinds of an error raised while a trajectory's rows are stepped (never the rows' at once: the privileged grader
# replays once more and needs a healthy host and a repeat, tests/grade.py; the standard service resumes the first one and
# checks the host before it counts a second, sim/server.py): the GPU (CUDA, Warp, PhysX, torch, cuBLAS / cuDNN, out of
# memory, a lost device, an illegal access or a failed launch, Vulkan), the operating system (an OSError: no space left,
# an I/O error) and memory. An error the rows themselves cause repeats and is still theirs.
HOST_FAULT = re.compile(
    r"out of memory|\bOOM\b|MemoryError|cuda|cublas|cudnn|cufft|cusolver|nvrtc|illegal (memory )?access|launch failure|"
    r"device[ _-]?lost|\bxid\b|vulkan|vk_error|\bgpu\b|warp|physx|OSError|IOError|No space left|Input/output error|"
    r"Errno (5|12|28|122)\b", re.IGNORECASE)


def host_fault_error(text: str | None) -> bool:
    """An error message of one of the host's kinds (HOST_FAULT)."""
    return bool(text) and HOST_FAULT.search(str(text)) is not None


def sidecar_failure() -> str | None:
    """The last Newton sidecar failure of this process (it died, timed out or did not start: the host's, never the
    agent's), or None. Only the deformable tasks run a sidecar."""
    nc = sys.modules.get("tactilelab_tasks.backends.newton_client")
    fails = getattr(nc, "FAILURES", None) if nc is not None else None
    return str(fails[-1]) if fails else None
REPLAY_START_S = 1200.0  # Isaac Sim start + scene build + (deformable tasks) the Newton sidecar's kernel compile, generous


def max_rows(task: str) -> int:
    return int(TASK_LIMITS.get(task, (MAX_ROWS, 1.0))[0])


def max_control_steps(task: str) -> int:
    """The task's technical episode cap: its longest trajectory and the replay's settle."""
    return max_rows(task) + SETTLE_STEPS


def replays(task: str) -> int:
    """Fresh-process replays the grader runs: 2 with equal final-state hashes, 1 by the task's declared choice."""
    return 1 if task in ONE_REPLAY else 2


def replay_limit_s(task: str, rows: int) -> float:
    """Wall clock of one grading replay of `rows` rows: the start, plus the rows and the settle at half the task's slowest
    measured pace (agent-independent: a function of the trajectory's length only)."""
    pace = float(TASK_LIMITS.get(task, (MAX_ROWS, 1.0))[1])
    return float(round(REPLAY_START_S + 2.0 * (int(rows) + SETTLE_STEPS) / pace))


def collect_end_s(task: str) -> float:
    """The standard twin's collect hook budget for ending the episode (RCB_COLLECT_END_TIMEOUT_S): a resume at collect
    time replays the journal of the longest episode, the time a grading replay of it gets (replay_limit_s)."""
    return replay_limit_s(task, max_rows(task))


def video_limit_s(task: str, rows: int) -> float:
    """Wall clock of the video replay (the video camera on: slower): the start, plus the rows at a third of the slowest
    pace."""
    pace = float(TASK_LIMITS.get(task, (MAX_ROWS, 1.0))[1])
    return float(round(REPLAY_START_S + 3.0 * (int(rows) + SETTLE_STEPS) / pace))
DEVICE = os.environ.get(
    "RCB_TACTILELAB_DEVICE", "cuda:0"
)  # PhysX on the GPU, as the tasks were developed (rendering and tactile on the GPU too)
os.environ.setdefault("TACTILELAB_ENHANCED_DETERMINISM", "0")  # the physics settings the tasks were developed with
_APP = None


def _log(*a: Any) -> None:
    print("[rcb_tactilelab]", *a, file=sys.stderr, flush=True)


def _launch_app(cameras: bool):
    global _APP
    if _APP is None:
        from tactilelab_tasks.backends.isaaclab_scene import launch_app

        _APP = launch_app(headless=True, enable_cameras=bool(cameras))
    return _APP


def _flat(tree: Any) -> np.ndarray:
    parts: list[np.ndarray] = []

    def walk(x: Any) -> None:
        if isinstance(x, dict):
            for k in sorted(x):
                walk(x[k])
        elif isinstance(x, (list, tuple)):
            for v in x:
                walk(v)
        else:
            try:
                parts.append(np.asarray(x, dtype=np.float64).ravel())
            except (TypeError, ValueError):
                pass

    walk(tree)
    return np.concatenate(parts) if parts else np.zeros(0)


class Session:
    def __init__(
        self,
        task: str,
        instance: str | Path | None = None,
        *,
        seed: int | None = None,
        cameras: bool = False,
        tactile: bool = True,
        tactile_rgb: bool = False,
        video_camera: bool = False,
    ):
        self.task_name = str(task)
        self.instance = json.loads(Path(instance).read_text()) if instance else {}
        if self.instance and self.instance.get("task") != self.task_name:
            raise ValueError(f"instance is for task {self.instance.get('task')!r}, not {self.task_name!r}")
        self.seed = int(self.instance.get("seed", 0) if seed is None else seed)
        self.device = str(self.instance.get("device", DEVICE))
        self.max_steps = max_control_steps(self.task_name)
        _launch_app(cameras or video_camera)
        import tactilelab_tasks
        from tactilelab_tasks.backends.isaaclab_scene import enable_video_camera

        enable_video_camera(bool(video_camera))  # the recorded video's third-person camera: no observation, no physics

        if self.task_name not in tactilelab_tasks.TASKS:
            raise KeyError(f"unknown task {self.task_name!r}; known: {sorted(tactilelab_tasks.TASKS)}")
        spec = tactilelab_tasks.TASKS[self.task_name]
        self.cfg = spec.load_cfg()
        # "full" with the video camera too: the dough tasks draw their deformable body's visual mesh only then (without
        # wrist cameras or tactile sensors a "full" observation renders nothing and steps nothing)
        obs_mode = "full" if (cameras or tactile_rgb or video_camera) else "state"
        self.task = spec.task_cls(
            self.cfg, obs_mode=obs_mode, device=self.device, cameras=bool(cameras), tactile=bool(tactile)
        )
        self.task.build()
        self.cameras = bool(cameras)
        self.video_camera = bool(video_camera)
        self.resets = -1
        self.sim_steps = 0
        self._rec: list[np.ndarray] | None = None
        self._last = None
        self._pending: dict[int, float] | None = None
        self._grip_prev: int | None = None
        self.obs = None
        # the task methods a scripted policy calls to change the gripper: the Session applies them from the action rows
        # (so a replay reproduces them); calls made directly on the task are turned into the next row's columns 18-21,
        # and the policy's own release announcements are replaced by the physical rule above
        self._orig = {
            n: getattr(self.task, n)
            for n in ("set_finger_limits", "set_finger_gains", "restore_finger_limits", "note_finish_release",
                      "clear_finish_release")
            if hasattr(self.task, n)
        }
        self.finger_drive_applies = "set_finger_limits" in self._orig
        if self.finger_drive_applies != (self.task_name in FINGER_DRIVE_TASKS):
            raise RuntimeError(f"FINGER_DRIVE_TASKS is out of date for {self.task_name!r}")
        self.finger_drive = list(FINGER_DRIVE_STOCK)  # the drive in force (stock after every reset)
        self.sidecar_at: int | None = None   # the control step at which a Newton sidecar failure was first seen
        self._in_reset = False
        if "set_finger_limits" in self._orig:
            self.task.set_finger_limits = self._capture_limits
        if "set_finger_gains" in self._orig:
            self.task.set_finger_gains = self._capture_gains
        if "restore_finger_limits" in self._orig:
            self.task.restore_finger_limits = self._capture_restore
        if "note_finish_release" in self._orig:
            self.task.note_finish_release = lambda: None
            self.task.clear_finish_release = lambda: None
        self.reset()
        self._check_robot()

    def _check_robot(self) -> None:
        """The constants the row checks and the published stock drive rest on, against the simulator: the robot base at
        ROBOT_BASE, and the right fingers' PhysX drive (velocity limit, effort limit, stiffness, damping) at
        FINGER_DRIVE_STOCK after the reset. A difference stops the Session (no episode runs on wrong constants)."""
        from tactilelab_tasks.core.types import JOINT_NAMES, ROBOT_BASE_POS

        rob = self.task.scene.robot
        base = np.asarray(rob.base_pose(), dtype=np.float64).reshape(-1)[:3]
        if not (np.allclose(base, ROBOT_BASE, atol=1e-4) and np.allclose(ROBOT_BASE_POS, ROBOT_BASE, atol=1e-9)):
            raise RuntimeError(f"robot base {base.tolist()} (types {ROBOT_BASE_POS}) is not ROBOT_BASE {ROBOT_BASE}")
        art = rob.articulation
        view = art.root_physx_view
        idx = [i for i, n in enumerate(JOINT_NAMES) if n.startswith(("J1_7", "J1_8"))]

        def col(values) -> list[float]:
            v = np.asarray(values.cpu() if hasattr(values, "cpu") else values, dtype=np.float64).reshape(-1)
            return [float(v[i]) for i in idx]

        got = (col(view.get_dof_max_velocities()[0, rob._joint_ids]), col(view.get_dof_max_forces()[0, rob._joint_ids]),
               col(view.get_dof_stiffnesses()[0, rob._joint_ids]), col(view.get_dof_dampings()[0, rob._joint_ids]))
        for name, want, vals in zip(FINGER_DRIVE_NAMES, FINGER_DRIVE_STOCK, got):
            if len(vals) != 2 or not np.allclose(vals, want, rtol=1e-5, atol=1e-6):
                raise RuntimeError(f"the right fingers' {name} is {vals} in PhysX, not the stock {want} (FINGER_DRIVE_STOCK)")

    def _capture_limits(self, vel_limit: float = 0.0, effort_limit: float = 0.0) -> None:
        self._pending = dict(self._pending or {})
        if vel_limit > 0.0:
            self._pending[18] = float(vel_limit)
        if effort_limit > 0.0:
            self._pending[19] = float(effort_limit)

    def _capture_gains(self, stiffness: float = 0.0, damping: float = 0.0) -> None:
        self._pending = dict(self._pending or {})
        if stiffness > 0.0:
            self._pending[20] = float(stiffness)
        if damping > 0.0:
            self._pending[21] = float(damping)

    def _capture_restore(self) -> None:
        """The task's restore_finger_limits(): during a reset the task's own (the reset restores the stock drive);
        otherwise the explicit stock values in the next row's columns 18-21, so a replay restores at the same step."""
        if self._in_reset:
            self._orig["restore_finger_limits"]()
            return
        self._pending = {**(self._pending or {}), **{18 + i: float(v) for i, v in enumerate(FINGER_DRIVE_STOCK)}}

    # ------------------------------------------------------------------ state
    def _state(self) -> np.ndarray:
        st = dict(self.task.get_state())
        st.pop("_task", None)
        return _flat(st)

    def state_sha(self) -> str:
        return hashlib.sha1(self._state().tobytes()).hexdigest()

    def reset(self) -> None:
        self._in_reset = True
        try:
            self.obs = self.task.reset(seed=self.seed)
        finally:
            self._in_reset = False
        self.finger_drive = list(FINGER_DRIVE_STOCK)
        self.resets += 1
        self.sim_steps = 0
        self._last = None
        self._pending = None
        self._grip_prev = None
        s0 = self._state()
        self.reset_sha = hashlib.sha1(s0.tobytes()).hexdigest()
        if self.resets == 0:  # the instance is checked on the first reset of the process (later resets are not bit-exact)
            want = self.instance.get("state_sha")
            self.instance_exact = (want is None) or (want == self.reset_sha)
            self.instance_matches = self.instance_exact  # the exact hash, nothing else (PROTOCOL §4)

    # ------------------------------------------------------------------ actions
    def _action(self, row):
        from tactilelab_tasks.core.types import Action

        r = np.asarray(row, dtype=np.float64).reshape(-1)
        if r.size in (16, 18):
            r = np.concatenate([r, np.full(ACTION_DIM - r.size, np.nan)])
        if r.size != ACTION_DIM:
            raise ValueError(f"a row has {ACTION_DIM} numbers (16 or 18 are padded with NaN), got {r.size}")
        why = row_problem(r)
        if why is not None:
            raise ValueError(why)
        gap = None if np.all(np.isnan(r[16:18])) else r[16:18].copy()
        return r, Action(r[:14].copy(), np.rint(r[14:16]).astype(np.int64), gap)

    def _apply_extras(self, r: np.ndarray) -> np.ndarray:
        """Finger drive settings (columns 18-21) and the release bookkeeping of the right gripper; returns the row as
        recorded (with any drive settings the task code requested since the last step merged in)."""
        if self._pending is not None:
            for i, v in self._pending.items():
                if np.isnan(r[i]):
                    r[i] = v
            self._pending = None
        t = self.task
        why = row_problem(r)   # a setting the task code asked for is held to the same ranges
        if why is not None:
            raise ValueError(why)
        vel, eff, kp, kd = (float(x) for x in r[18:22])
        if (np.isfinite(vel) or np.isfinite(eff)) and "set_finger_limits" in self._orig:
            self._orig["set_finger_limits"](vel if np.isfinite(vel) else 0.0, eff if np.isfinite(eff) else 0.0)
        if (np.isfinite(kp) or np.isfinite(kd)) and "set_finger_gains" in self._orig:
            self._orig["set_finger_gains"](kp if np.isfinite(kp) else 0.0, kd if np.isfinite(kd) else 0.0)
        if self.finger_drive_applies:
            for i in range(4):
                if np.isfinite(r[18 + i]):
                    self.finger_drive[i] = float(r[18 + i])
        cmd = int(round(r[14]))
        if hasattr(t, "note_finish_release") and self._grip_prev is not None and cmd != self._grip_prev:
            if cmd == 0:
                self._orig["note_finish_release"]()
            else:
                self._orig["clear_finish_release"]()
        self._grip_prev = cmd
        return r

    def step(self, row) -> None:
        if self.sim_steps >= self.max_steps:
            raise RuntimeError(f"the task's episode cap ({self.max_steps} control steps) reached")
        r, act = self._action(row)
        r = self._apply_extras(r)
        try:
            self.obs, _info = self.task.step(act)
        finally:
            if self.sidecar_at is None and sidecar_failure() is not None:
                self.sidecar_at = self.sim_steps + 1   # this step (1-based): where the sidecar failed
        self.sim_steps += 1
        self._last = r
        if self._rec is not None:
            self._rec.append(r)

    def hold_action(self) -> np.ndarray:
        """A row that holds both arms and keeps the current gripper commands (drive settings unchanged)."""
        if self._last is not None:
            row = self._last.copy()
            row[18:22] = np.nan
            return row
        row = np.full(ACTION_DIM, np.nan)
        row[14:16] = 0.0
        return row

    def move_ee(self, arm: int, pose7, steps: int = 60) -> None:
        """Interpolate one arm's target (position linearly, orientation by slerp) from its current pose to `pose7`."""
        cur = np.asarray(self.task.scene.robot.ee_pose(int(arm)), dtype=np.float64)
        goal = np.asarray(pose7, dtype=np.float64).reshape(7)
        q0, q1 = cur[3:] / np.linalg.norm(cur[3:]), goal[3:] / np.linalg.norm(goal[3:])
        if float(np.dot(q0, q1)) < 0.0:
            q1 = -q1
        for i in range(1, max(1, int(steps)) + 1):
            u = i / max(1, int(steps))
            row = self.hold_action()
            pos = (1.0 - u) * cur[:3] + u * goal[:3]
            d = float(np.clip(np.dot(q0, q1), -1.0, 1.0))
            if d > 0.9995:
                q = (1.0 - u) * q0 + u * q1
            else:
                th = math.acos(d)
                q = (math.sin((1.0 - u) * th) * q0 + math.sin(u * th) * q1) / math.sin(th)
            row[7 * arm : 7 * arm + 7] = np.concatenate([pos, q / np.linalg.norm(q)])
            self.step(row)

    def set_gripper(self, arm: int, closed: bool, steps: int = 30) -> None:
        for _ in range(max(1, int(steps))):
            row = self.hold_action()
            row[14 + int(arm)] = 1.0 if closed else 0.0
            self.step(row)

    # ------------------------------------------------------------------ recording / replay
    def record_start(self) -> None:
        self._rec = []

    def record_stop(self) -> np.ndarray:
        rows, self._rec = self._rec or [], None
        return np.stack(rows) if rows else np.zeros((0, ACTION_DIM))

    def save_trajectory(self, actions: np.ndarray, path: str | Path) -> None:
        a = np.asarray(actions, dtype=np.float64)
        if a.ndim != 2 or a.shape[1] != ACTION_DIM:
            raise ValueError(f"actions must be (T, {ACTION_DIM})")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        np.savez(path, task=np.array(self.task_name), actions=a)

    def settle(self) -> None:
        row = self.hold_action()
        for _ in range(SETTLE_STEPS):
            self.step(row)

    def _frame(self) -> np.ndarray:
        """The video frame, rendered now (only for a video: a graded replay renders nothing): the third-person video
        camera (Session(..., video_camera=True)), else the two wrist cameras side by side."""
        img = self.task.scene.render_video() if self.video_camera else None
        if img is not None:
            return img
        obs = self.task.scene.render_cameras()
        return np.concatenate([np.asarray(obs["wrist_right_rgb"]), np.asarray(obs["wrist_left_rgb"])], axis=1)

    def replay(
        self,
        actions: np.ndarray,
        settle: bool = True,
        video: str | None = None,
        fps: int = 15,
        video_deadline: float | None = None,
        on_first_row=None,
        on_progress=None,
    ) -> dict[str, Any]:
        """Resets (unless nothing has run since the first reset of the process: then the replay is that first episode,
        exactly what the grader's fresh-process replay runs), replays the rows open loop, holds the last row.
        With `video` (a Session with cameras=True or video_camera=True), frames are rendered every 60/fps steps and
        streamed to the file;
        at the wall-clock time `video_deadline` (time.time()) the replay stops and the video is closed
        (`video_truncated` in the status). `on_first_row` is called once, before the first row is stepped;
        `on_progress(steps_done, seconds_since_first_row)` every 30 s of wall clock."""
        if not (self.resets == 0 and self.sim_steps == 0):
            self.reset()
        every = max(1, int(round(60 / max(1, int(fps)))))  # 60 Hz control -> `fps` video frames per second
        rows = list(np.asarray(actions, dtype=np.float64))
        if settle and rows:
            hold = rows[-1].copy()
            hold[18:22] = np.nan  # the hold keeps the drive settings in force, as settle() does
            rows += [hold] * SETTLE_STEPS
        writer, truncated = None, False
        if video and (self.cameras or self.video_camera):
            import imageio.v2 as imageio

            writer = imageio.get_writer(video, fps=int(fps), codec="libx264", quality=7, macro_block_size=8)
        try:
            if on_first_row is not None:
                on_first_row()
            t0 = t_last = time.time()
            for i, r in enumerate(rows):
                if writer is not None and video_deadline is not None and time.time() > video_deadline:
                    truncated = True
                    break
                self.step(r)
                if on_progress is not None and time.time() - t_last >= 30.0:
                    t_last = time.time()
                    on_progress(i + 1, t_last - t0)
                if writer is not None and i % every == 0:
                    writer.append_data(self._frame())  # streamed: no frame buffer in memory
        finally:
            if writer is not None:
                try:
                    writer.close()
                except Exception as exc:  # noqa: BLE001
                    _log(f"video not closed: {exc!r}")
        st = self.status()
        if writer is not None:
            st["video_truncated"] = bool(truncated)
        return st

    # ------------------------------------------------------------------ queries
    def sim_error(self) -> str | None:
        """The simulator error the task recorded in this episode (a Newton sidecar call or the soft-body judge that
        failed: the episode cannot succeed), or None."""
        e = getattr(self.task, "sim_error_reason", None)
        return str(e) if e else None

    def status(self) -> dict[str, Any]:
        m = {}
        try:
            for k, v in self.task.metrics().items():
                if np.isscalar(v) and not isinstance(v, str):
                    m[k] = float(v)
                elif isinstance(v, str) and v:
                    m[k] = v
        except Exception:
            pass
        err = self.sim_error()
        out = {
            "success": bool(self.task.is_success()) and err is None and sidecar_failure() is None,
            "sim_steps": int(self.sim_steps),
            "resets": int(self.resets),
            "state_sha": self.state_sha(),
            "metrics": m,
        }
        if err is not None:
            out["sim_error"] = err
        if sidecar_failure() is not None:
            out["sidecar_failure"] = sidecar_failure()
        return out

    def objects(self) -> dict[str, dict]:
        out = {}
        for o in self.cfg.get("scene", {}).get("objects", []):
            n = str(o["name"])
            try:
                p = np.asarray(self.task.object_pose(n), dtype=np.float64)
            except Exception:
                continue
            out[n] = {"position": p[:3].tolist(), "orientation_wxyz": p[3:7].tolist()}
        return out

    def proprio(self) -> dict[str, Any]:
        rob = self.task.scene.robot
        return {
            "joint_pos": np.asarray(rob.joint_pos(), dtype=np.float64).tolist(),
            "right_ee_pose": np.asarray(rob.ee_pose(0), dtype=np.float64).tolist(),
            "left_ee_pose": np.asarray(rob.ee_pose(1), dtype=np.float64).tolist(),
            "gripper_width": [float(rob.gripper_width(0)), float(rob.gripper_width(1))],
        }

    def tactile(self) -> dict[str, np.ndarray]:
        read = getattr(self.task, "sensors", {}).get("tactile")
        return {} if read is None else dict(read())

    def render_frame(self, camera: str = "wrist_right_rgb", hfov_deg: float | None = None) -> np.ndarray:
        """The image of `camera` (an image key of the policy observation: "wrist_right_rgb", "wrist_left_rgb"; or
        "wrist_right" / "wrist_left"), rendered now. hfov_deg (the wrist cameras only): the horizontal field of view of
        this render, in WRIST_CAM_HFOV_RANGE_DEG (30 degrees up to the default 166.1; same mount, same 640 x 480, square
        pixels, principal point at the centre; rendered by a second camera at that mount, so the wrist camera itself
        never changes; from the first request on, every render also renders that second camera); None is the default
        lens. camera_intrinsics(camera, hfov_deg) is its intrinsic matrix. Rendering never steps physics and never
        changes the state."""
        if not self.cameras:
            raise RuntimeError("cameras are off: Session(..., cameras=True)")
        if hfov_deg is None:
            obs = self.task.get_observation()
            key = f"{camera}_rgb" if camera in ("wrist_right", "wrist_left") else camera
            return np.asarray(obs["policy"][key])
        name = _wrist_name(camera)
        return np.asarray(self.task.scene.render_cameras(hfov_deg={name: hfov_deg})[f"{name}_rgb"])

    def camera_intrinsics(self, camera: str = "wrist_right_rgb", hfov_deg: float | None = None) -> np.ndarray:
        """intrinsic_cv (3, 3; OpenCV: x right, y down, z forward) of a wrist camera's image from render_frame(camera,
        hfov_deg): fx = fy = 320 / tan(hfov / 2), principal point (320, 240); None is the default lens (fx = 39.0)."""
        if not self.cameras:
            raise RuntimeError("cameras are off: Session(..., cameras=True)")
        return self.task.scene.wrist_intrinsics(_wrist_name(camera), hfov_deg)


def _wrist_name(camera: str) -> str:
    """"wrist_right_rgb" / "wrist_right" -> "wrist_right" (the cameras a field of view applies to); else a ValueError."""
    name = str(camera)[:-4] if str(camera).endswith("_rgb") else str(camera)
    if name not in ("wrist_right", "wrist_left"):
        raise ValueError(f"hfov_deg applies to the wrist cameras (wrist_right_rgb, wrist_left_rgb), not {camera!r}")
    return name


# ---------------------------------------------------------------------- CLI
def _shutdown(code: int) -> None:
    import threading

    if _APP is not None:
        th = threading.Thread(target=_APP.close, daemon=True)
        th.start()
        th.join(timeout=20.0)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


def _write_json(path: str | None, obj: dict) -> None:
    """Write obj to path atomically (the grader reads the file, never this process's stdout)."""
    if not path:
        return
    tmp = f"{path}.part"
    with open(tmp, "w") as f:
        json.dump(obj, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _replay_cli(a) -> dict[str, Any]:
    """`replay`: the phases the grader tells apart through the --result file.
    setup  - Isaac start, scene build, reset and the instance check: a failure here is the host's (no agent row ran);
    agent  - written just before the first trajectory row is stepped, then every 30 s with the rows done and the pace
             (`rows_done`, `pace`: control steps per second since the first row): from here on an exception raised on
             the agent's rows is a simulator error (the agent's 0, `sim_error`); a Newton sidecar failure is recorded
             with the step it was first seen at (`sidecar_failure`, `sidecar_at`); what the grader makes of a failure,
             a crash of this process and a replay out of its time: tests/grade.py classify();
    done   - the verdict of this replay."""
    res: dict[str, Any] = {"phase": "setup"}
    _write_json(a.result, res)
    d = np.load(a.traj, allow_pickle=False)
    acts = np.asarray(d["actions"], dtype=np.float64)
    s = Session(a.task, instance=a.instance, tactile=False, video_camera=bool(a.video))
    res.update(instance_exact=bool(s.instance_exact), instance_matches=bool(s.instance_matches), host=host_gpu())
    _write_json(a.result, res)
    if not s.instance_matches:  # the scene rebuilt here is not the frozen instance: the host's, before any agent row
        raise RuntimeError("the rebuilt scene does not match the instance (instance_mismatch)")
    if s.sim_error() or sidecar_failure():  # the sidecar failed while the scene was built and reset: no agent row has run
        raise RuntimeError(f"simulator error before the first row: {s.sim_error() or sidecar_failure()}")
    t0 = time.time()
    deadline = (t0 + float(a.video_deadline_s)) if (a.video and a.video_deadline_s) else None

    def first_row() -> None:
        res["phase"] = "agent"
        _write_json(a.result, res)

    def progress(done: int, secs: float) -> None:
        res.update(rows_done=int(done), pace=round(done / max(secs, 1e-6), 3), agent_wall_s=round(secs, 1))
        _write_json(a.result, res)

    try:
        st = s.replay(acts, video=a.video, fps=a.fps, video_deadline=deadline, on_first_row=first_row,
                      on_progress=progress)
    except Exception as exc:  # noqa: BLE001 - raised while the agent's rows were stepped: the agent's result
        import traceback

        traceback.print_exc()
        if res["phase"] != "agent":
            raise
        res.update(
            phase="done", success=False, sim_error=f"{type(exc).__name__}: {exc}"[:2000], sim_steps=int(s.sim_steps)
        )
        if sidecar_failure() is not None:
            res["sidecar_failure"] = sidecar_failure()[:2000]
            res["sidecar_at"] = int(s.sidecar_at or s.sim_steps + 1)
        res["wall_s"] = round(time.time() - t0, 1)
        _write_json(a.result, res)
        return res
    res.update(
        phase="done",
        success=bool(st["success"]),
        state_sha=st["state_sha"],
        sim_steps=st["sim_steps"],
        metrics=st["metrics"],
        wall_s=round(time.time() - t0, 1),
    )
    if st.get("sim_error"):
        res["sim_error"] = st["sim_error"]
    if st.get("sidecar_failure"):
        res["sidecar_failure"] = st["sidecar_failure"][:2000]
        res["sidecar_at"] = int(s.sidecar_at or s.sim_steps)
    if "video_truncated" in st:
        res["video_truncated"] = st["video_truncated"]
    if a.final_state:  # the full final state vector (the grader measures the spread between replays)
        np.save(a.final_state, s._state(), allow_pickle=False)
    _write_json(a.result, res)
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make-instance")
    m.add_argument("--task", required=True)
    m.add_argument("--seed", type=int, default=0)
    m.add_argument("--out", required=True)
    r = sub.add_parser("replay")
    r.add_argument("--task", required=True)
    r.add_argument("--instance", required=True)
    r.add_argument("--traj", required=True)
    r.add_argument("--result", default=None, help="write the phases and the verdict of this replay to this JSON file")
    r.add_argument("--video", default=None, help="render the third-person video camera to this mp4 (slower)")
    r.add_argument("--fps", type=int, default=15)
    r.add_argument("--video-deadline-s", type=float, default=None, help="with --video: stop after this many seconds")
    r.add_argument("--final-state", default=None, help="save the final state vector (.npy)")
    o = sub.add_parser("run-oracle")
    o.add_argument("--task", required=True)
    o.add_argument("--instance", required=True)
    o.add_argument("--code", required=True)
    o.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    code = 1
    try:
        if a.cmd == "make-instance":
            s = Session(a.task, seed=a.seed, tactile=False)
            inst = {"task": a.task, "seed": a.seed, "device": s.device, "state_sha": s.reset_sha, "frozen_on": host_gpu()}
            Path(a.out).write_text(json.dumps(inst, indent=1) + "\n")
            print(json.dumps({"task": a.task, "state_sha": s.reset_sha}), flush=True)
        elif a.cmd == "replay":
            res = _replay_cli(a)
            print(json.dumps({k: v for k, v in res.items() if k != "metrics"}), flush=True)
        elif a.cmd == "run-oracle":
            s = Session(a.task, instance=a.instance)
            ns = {"s": s, "Session": Session, "np": np}
            exec(compile(Path(a.code).read_text(), a.code, "exec"), ns)
            acts = ns.get("actions")
            if acts is None:
                raise RuntimeError("the oracle code must leave its rows in `actions`")
            s.settle()  # the live first episode, as a replay would end it
            st = s.status()
            s.save_trajectory(acts, a.out)
            print(
                json.dumps({"rows": int(len(acts)), **{k: st[k] for k in ("success", "state_sha", "sim_steps")}}),
                flush=True,
            )
        code = 0
    except Exception:
        import traceback

        traceback.print_exc()
    _shutdown(code)
    return code


if __name__ == "__main__":
    main()
