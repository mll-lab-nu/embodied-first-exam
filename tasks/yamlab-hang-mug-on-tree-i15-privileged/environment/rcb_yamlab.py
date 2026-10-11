"""
rcb_yamlab.py — task-local tooling for YAMLab (github.com/ARISE-Initiative/yamlab @ ec0455d, MIT; Isaac Lab @ f4aa17f /
Isaac Sim 5.1): frozen task instance / privileged primitives / action recording / fresh-process replay. Same shape as the
RoboLab tasks' rcb_robolab.py, so agents and verifiers share one mental model.

Concepts
--------
instance   : one YAMLab task (PutPotOnCooktop-v0 or HangMugOnTree-v0: two I2RT YAM arms with parallel grippers on a
             workstation table) with one pair of object assets from YAMLab's dataset (e.g. Pot/pot_007 + Cooktop/cooktop_007,
             baked into the image under /opt/yamlab-data) and the full scene state the episode starts from: both arms' root
             pose/velocity and joint positions/velocities, both objects' root pose/velocity, in Isaac Lab's
             `InteractiveScene.get_state()` layout ("initial_state" in instance.json). Session(instance=...) builds the env
             from the pinned YAMLab code and restores that state with `env.reset_to(...)`. `state_sha` = sha1 over the
             flattened state. On load, `instance_exact` = sha equality and `instance_matches` = sha equality or every object
             pose / joint position within tolerance (a different GPU or driver may change the last bits).
trajectory : the (T, 14) low-level actions handed to `env.step`, one row per control step (30 Hz: sim dt 1/120 s, decimation
             4), YAMLab's own action: [left joint1..6, left gripper, right joint1..6, right gripper], absolute joint-position
             targets (rad) tracked by the arms' PD drives; a gripper entry is the target of the arm's `left_finger` joint (m,
             -0.0475 = fully open .. 0.0 = closed; YAMLab mirrors it onto `right_finger`). Physics is PhysX on the CPU (YAMLab's
             own device for replay and data generation): a live run and a fresh-process replay of the same actions end in the
             same state. Only actions enter scoring.
success    : YAMLab's own staged success check with its EVALUATION thresholds (`is_evaluation_mode`): PutPotOnCooktop = pick
             (pot > 5 cm above its resting height, both grippers grasping it, 8 consecutive steps) then place (pot on the
             cooktop: centre within the XY tolerance, at the resting height +- 2 cm, upright within 0.2 rad, both grippers
             released, 30 consecutive steps); HangMugOnTree = pick (left gripper grasping, mug > 5 cm up, 8 steps), handover
             (right grasping, left released, mug up, 30 steps), hang (mug at the tree, > 5 cm above the table, both grippers
             released, height stable within 3 cm, 30 steps). Stages latch in order. As in YAMLab's evaluation (its
             `task_success` termination), the episode ends at the first control step where every stage has latched: later
             rows are never executed.
budget     : no step budget: the agent's wall clock is the limit. MAX_STEPS only stops a runaway trajectory.

CLI
---
  python rcb_yamlab.py make-instance --task put_pot_on_cooktop --dataset <recording> --demo 0 --out instance.json --oracle-out oracle_actions.npy
  python rcb_yamlab.py run-actions   --task put_pot_on_cooktop --instance instance.json --actions oracle_actions.npy --out traj.npz
  python rcb_yamlab.py replay        --task put_pot_on_cooktop --instance instance.json --traj traj.npz [--video replay.mp4]
  python rcb_yamlab.py render        --task put_pot_on_cooktop --instance instance.json --traj traj.npz --out replay.mp4

Python (what the agent gets)
----------------------------
  from rcb_yamlab import Session
  s = Session("put_pot_on_cooktop", instance="/app/instance.json")   # ~1-2 min: Isaac Sim launch + scene build
  s.reset()                          # back to the frozen instance state (unlimited)
  p = s.primitives()                 # thin wrappers of the low-level action: move_ee, move_joints, set_gripper, hold, ...
  s.objects()                        # task objects: name -> position, orientation_wxyz, size, bounds, velocity
  s.render_frame("top")              # RGB (H, W, 3) uint8; cameras "top", "left_wrist", "right_wrist"; s.render_grid()
  s.record_start(); ...; actions = s.record_stop()   # (T, 14) low-level actions, one row per control step
  s.status()                         # {'success', 'stages', 'progress', 'sim_steps', 'resets', 'state_sha', 'terminated'}
  s.replay(actions)                  # resets, replays open-loop, returns status; the first replay in a process is exact
  s.save_trajectory(actions, "/app/output/trajectory.npz")
None of the camera / kinematics / proprio calls steps physics or changes the simulator state.
"""
from __future__ import annotations

import os
os.environ.setdefault("OMNI_KIT_ACCEPT_EULA", "YES")
os.environ.setdefault("ACCEPT_EULA", "Y")
os.environ.setdefault("OMNI_KIT_ALLOW_ROOT", "1")
os.environ.setdefault("PYTHONUNBUFFERED", "1")

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np

YAMLAB_ROOT = Path(os.environ.get("YAMLAB_ROOT", "/opt/yamlab"))
DATA_ROOT = Path(os.environ.get("YAMLAB_DATA", "/opt/yamlab-data/tasks_data"))
# Interaction log: every Session (any process) appends one line per session start/reset/record/replay/exit, with the
# control steps consumed, to RCB_SESSION_LOG (default /app/output/rcb_session_log.jsonl, collected with the artifacts) and
# to RCB_SESSION_LOG_KEEP (default /logs/agent/rcb_session_log.jsonl, where that directory exists). The verifier reports it
# as self-reported cost (agent_sessions / agent_resets / agent_sim_steps) and sets RCB_SESSION_LOG="" for its own sessions.
SESSION_LOG = os.environ.get("RCB_SESSION_LOG", "/app/output/rcb_session_log.jsonl")
SESSION_LOG_KEEP = os.environ.get("RCB_SESSION_LOG_KEEP", "/logs/agent/rcb_session_log.jsonl")


def _slog(ev: str, **kw) -> None:
    if not SESSION_LOG:
        return
    line = json.dumps({"ts": time.time(), "pid": os.getpid(), "ev": ev, **kw}) + "\n"
    try:
        os.makedirs(os.path.dirname(SESSION_LOG), exist_ok=True)
        with open(SESSION_LOG, "a") as f:
            f.write(line)
    except OSError:
        pass
    if SESSION_LOG_KEEP and os.path.isdir(os.path.dirname(SESSION_LOG_KEEP)):
        try:
            with open(SESSION_LOG_KEEP, "a") as f:
                f.write(line)
        except OSError:
            pass


# The two YAMLab tasks. `text` is the goal as the instructions state it; `stages` are YAMLab's stage flags in order.
TASKS: dict[str, dict[str, Any]] = {
    "put_pot_on_cooktop": {
        "env": "PutPotOnCooktop-v0", "data": "PutPotOnCooktop", "objects": ("pot", "cooktop"), "stages": ("pick", "place"),
        "text": "Pick up the pot with both arms (both grippers grasping it) and put it down on the cooktop, upright, then "
                "release it with both grippers.",
    },
    "hang_mug_on_tree": {
        "env": "HangMugOnTree-v0", "data": "HangMugOnTree", "objects": ("mug", "mug_tree"), "stages": ("pick", "handover", "hang"),
        "text": "Pick up the mug with the left arm, hand it over to the right arm (the right gripper takes it and the left one "
                "lets go while the mug stays lifted), and hang the mug on the mug tree, released by both grippers.",
    },
}

ACTION_DIM = 14
CONTROL_HZ = 30                      # sim dt 1/120 s x decimation 4
MAX_STEPS = 100_000                  # no step budget (the wall clock is); this only stops a runaway trajectory (~55 min of sim time)
MAX_VIDEO_FRAMES = 9000              # the `replay` CLI's video holds at most this many frames (10 min at 15 fps): a longer
                                     # trajectory is filmed as a time lapse, so filming never multiplies a long replay's cost
ARMS = ("left", "right")
ARM_ASSET = {"left": "left_arm", "right": "right_arm"}
ARM_SLICE = {"left": slice(0, 6), "right": slice(7, 13)}
GRIP_INDEX = {"left": 6, "right": 13}
ARM_JOINTS = tuple(f"joint{i}" for i in range(1, 7))
FINGER_OPEN, FINGER_CLOSED = -0.0475, 0.0     # the gripper command = left_finger target (m); YAMLab mirrors it onto right_finger
ACTION_LAYOUT = ("14 entries per control step (30 Hz), YAMLab's action: left joint1..6, left gripper, right joint1..6, right "
                 "gripper. Joints: absolute position targets (rad) tracked by PD drives. Gripper: the target of the arm's "
                 "left_finger joint (m), -0.0475 = fully open .. 0.0 = closed (YAMLab mirrors it onto right_finger). Poses are "
                 "in the world frame (x forward from the arm bases towards the table, y to the left, z up), quaternions WXYZ.")
CAMERAS = ("top", "left_wrist", "right_wrist")    # scene sensors "<name>_camera"
DEPTH_TYPE = "distance_to_image_plane"
DEPTH_MAX_M = 65.535
DEFAULT_DEPTH = os.environ.get("RCB_YAMLAB_DEPTH", "0") == "1"
ENHANCED_DETERMINISM = os.environ.get("RCB_YAMLAB_ENHANCED_DETERMINISM", "0") == "1"
GROUND_USD = "/opt/isaac-assets/Isaac/Environments/Grid/default_environment.usd"   # baked into eai-yamlab (images/yamlab/Dockerfile)
ENV_SEED = 0                               # Isaac Lab env seed (torch, numpy, random, replicator), fixed: see Session._make_env
GL2CV = np.diag([1.0, -1.0, -1.0, 1.0])     # OpenGL camera axes (x right, y up, z back) <-> OpenCV (x right, y down, z forward)
FLANGE_BODY = "link_6"                      # the last arm link: the gripper and the wrist camera sit on it

_APP = None


def _log(*a: Any) -> None:
    print("[rcb]", *a, file=sys.stderr, flush=True)


class PrimitiveError(RuntimeError):
    """A primitive could not be planned or executed (the episode is still alive unless said otherwise)."""


# --------------------------------------------------------------------------- small geometry helpers (numpy, wxyz)
def quat_to_mat(q) -> np.ndarray:
    w, x, y, z = [float(v) for v in q]
    n = math.sqrt(w * w + x * x + y * y + z * z) or 1.0
    w, x, y, z = w / n, x / n, y / n, z / n
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def mat_to_quat(R) -> np.ndarray:
    R = np.asarray(R, dtype=np.float64)
    t = np.trace(R)
    if t > 0:
        s = math.sqrt(t + 1.0) * 2; w = 0.25 * s; x = (R[2, 1] - R[1, 2]) / s; y = (R[0, 2] - R[2, 0]) / s; z = (R[1, 0] - R[0, 1]) / s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2; w = (R[2, 1] - R[1, 2]) / s; x = 0.25 * s; y = (R[0, 1] + R[1, 0]) / s; z = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2; w = (R[0, 2] - R[2, 0]) / s; x = (R[0, 1] + R[1, 0]) / s; y = 0.25 * s; z = (R[1, 2] + R[2, 1]) / s
    else:
        s = math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2; w = (R[1, 0] - R[0, 1]) / s; x = (R[0, 2] + R[2, 0]) / s; y = (R[1, 2] + R[2, 1]) / s; z = 0.25 * s
    q = np.array([w, x, y, z]); return q / np.linalg.norm(q)


def quat_mul(a, b) -> np.ndarray:
    w1, x1, y1, z1 = a; w2, x2, y2, z2 = b
    return np.array([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])


def quat_inv(q) -> np.ndarray:
    q = np.asarray(q, dtype=np.float64); return np.array([q[0], -q[1], -q[2], -q[3]]) / float(q @ q)


def quat_from_axis_angle(axis, angle: float) -> np.ndarray:
    a = np.asarray(axis, dtype=np.float64); a = a / np.linalg.norm(a); s = math.sin(angle / 2)
    return np.array([math.cos(angle / 2), a[0] * s, a[1] * s, a[2] * s])


def rot_angle(Ra, Rb) -> float:
    c = (np.trace(np.asarray(Ra).T @ np.asarray(Rb)) - 1.0) / 2.0
    return float(math.acos(max(-1.0, min(1.0, c))))


def quat_angle(qa, qb) -> float:
    return rot_angle(quat_to_mat(qa), quat_to_mat(qb))


def wrap_angle(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


def pose_compose(p1, q1, p2, q2) -> tuple[np.ndarray, np.ndarray]:
    """T1 * T2 for (position, wxyz quaternion) pairs."""
    return np.asarray(p1, dtype=np.float64) + quat_to_mat(q1) @ np.asarray(p2, dtype=np.float64), quat_mul(q1, q2)


def pose_inverse(p, q) -> tuple[np.ndarray, np.ndarray]:
    qi = quat_inv(q); return -(quat_to_mat(qi) @ np.asarray(p, dtype=np.float64)), qi


def hom(R=None, p=None) -> np.ndarray:
    T = np.eye(4)
    if R is not None:
        T[:3, :3] = R
    if p is not None:
        T[:3, 3] = np.asarray(p, dtype=np.float64).reshape(3)
    return T


def pose7(T) -> list[float]:
    """4x4 -> [x, y, z, qw, qx, qy, qz] (qw >= 0)."""
    q = mat_to_quat(np.asarray(T)[:3, :3])
    q = -q if q[0] < 0 else q
    return [float(v) for v in np.asarray(T)[:3, 3]] + [float(v) for v in q]


def pose7_to_T(p) -> np.ndarray:
    p = np.asarray(p, dtype=np.float64).reshape(7)
    return hom(quat_to_mat(p[3:]), p[:3])


def axis_rot(axis, a: float) -> np.ndarray:
    x, y, z = [float(v) for v in axis]; c, s = math.cos(a), math.sin(a); C = 1.0 - c
    return np.array([[c + x * x * C, x * y * C - z * s, x * z * C + y * s], [y * x * C + z * s, c + y * y * C, y * z * C - x * s],
                     [z * x * C - y * s, z * y * C + x * s, c + z * z * C]])


def rotvec(R) -> np.ndarray:
    """Axis * angle (rad) of a rotation matrix."""
    R = np.asarray(R, dtype=np.float64)
    ang = math.acos(max(-1.0, min(1.0, (float(np.trace(R)) - 1.0) / 2.0)))
    v = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]])
    if ang < 1e-9:
        return v / 2.0
    if math.pi - ang < 1e-4:
        A = (R + np.eye(3)) / 2.0; i = int(np.argmax(np.diag(A))); ax = A[:, i] / math.sqrt(max(A[i, i], 1e-12))
        return ax / np.linalg.norm(ax) * ang
    return v / (2.0 * math.sin(ang)) * ang


class ArmModel:
    """Stateless kinematics of one fixed-base serial arm in numpy (no simulator call): revolute joints given by their USD
    joint frames (child = parent . A . Rot(axis, q) . B), then fixed mounts and named tool frames. FK, the geometric
    Jacobian and a damped-least-squares IK that starts from the seed (then the home pose, then mid-range) and clamps every
    step to the limits."""

    def __init__(self, root: str, base_T, joints: list, fixed: list, lo, hi, home):
        self.root, self.base_T = root, np.asarray(base_T, dtype=np.float64)
        self.joints, self.fixed = joints, fixed                # joints: (name, parent, child, A, axis, B); fixed: (parent, child, M)
        self.lo, self.hi, self.home = (np.asarray(x, dtype=np.float64) for x in (lo, hi, home))
        self.links = [root] + [j[2] for j in joints] + [f[1] for f in fixed]
        parent = {j[2]: j[1] for j in joints}; parent.update({f[1]: f[0] for f in fixed})
        jidx = {j[2]: i for i, j in enumerate(joints)}
        self._n_moving = {}
        for f in self.links:
            g = f
            while g not in jidx and g in parent:
                g = parent[g]
            self._n_moving[f] = jidx[g] + 1 if g in jidx else 0

    def _fk(self, q):
        T = {self.root: self.base_T}; P, Ax = [], []
        for i, (_n, parent, child, A, axis, B) in enumerate(self.joints):
            J = T[parent] @ A
            P.append(J[:3, 3].copy()); Ax.append(J[:3, :3] @ axis)
            T[child] = J @ hom(axis_rot(axis, float(q[i]))) @ B
        for parent, child, M in self.fixed:
            T[child] = T[parent] @ M
        return T, P, Ax

    def fk(self, q) -> dict[str, np.ndarray]:
        return self._fk(np.asarray(q, dtype=np.float64).reshape(-1))[0]

    def jacobian(self, T, P, Ax, frame: str) -> np.ndarray:
        J = np.zeros((6, len(self.joints))); pf = T[frame][:3, 3]
        for i in range(self._n_moving[frame]):
            J[:3, i] = np.cross(Ax[i], pf - P[i]); J[3:, i] = Ax[i]
        return J

    def ik(self, targets: dict, seed=None, tol_p: float = 1e-3, tol_r: float = 1e-2, max_iters: int = 300,
           lam: float = 0.05, max_step: float = 0.25):
        """targets {frame: 4x4} -> (q, ok, {frame: (position error m, rotation error rad)}) of the best q found."""
        best = None
        seeds = ([np.asarray(seed, dtype=np.float64).reshape(-1)] if seed is not None else []) + [self.home, (self.lo + self.hi) / 2.0]
        for s0 in seeds:
            q = np.clip(s0, self.lo, self.hi)
            for _ in range(int(max_iters)):
                T, P, Ax = self._fk(q)
                es, Js, errs = [], [], {}
                for f, Tt in targets.items():
                    ep = Tt[:3, 3] - T[f][:3, 3]; er = rotvec(Tt[:3, :3] @ T[f][:3, :3].T)
                    errs[f] = (float(np.linalg.norm(ep)), float(np.linalg.norm(er)))
                    es += [ep, er]; Js.append(self.jacobian(T, P, Ax, f))
                score = max(max(e[0] / tol_p, e[1] / tol_r) for e in errs.values())
                if best is None or score < best[0]:
                    best = (score, q.copy(), errs)
                if score <= 1.0:
                    return q, True, errs
                e = np.concatenate(es); Jm = np.vstack(Js)
                dq = Jm.T @ np.linalg.solve(Jm @ Jm.T + lam * lam * np.eye(len(e)), e)
                m = float(np.max(np.abs(dq)))
                q = np.clip(q + (dq * (max_step / m) if m > max_step else dq), self.lo, self.hi)
        return best[1], False, best[2]


# --------------------------------------------------------------------------- Isaac app (one per process)
def _launch_app():
    global _APP
    if _APP is None:
        from isaaclab.app import AppLauncher
        argv, sys.argv = sys.argv, [sys.argv[0]]   # Kit must not see our CLI flags
        try:
            _APP = AppLauncher({"headless": True, "enable_cameras": True, "device": "cpu"}).app
        finally:
            sys.argv = argv
    return _APP


def _tt(x):
    """warp array or torch tensor -> torch tensor."""
    import torch
    if isinstance(x, torch.Tensor):
        return x
    import warp as wp
    return wp.to_torch(x)


def _np(x) -> np.ndarray:
    return _tt(x).detach().cpu().numpy().astype(np.float64)


def asset_paths(task: str, assets: dict[str, str]) -> dict[str, str]:
    """{object: "Category/instance"} (as YAMLab's dataset records it) -> {object: instance dir in the image}."""
    root = DATA_ROOT / TASKS[task]["data"] / "objects"
    return {k: str(root / v) for k, v in assets.items()}


# --------------------------------------------------------------------------- session
class Session:
    def __init__(self, task: str, instance: str | Path | dict | None = None, *, strict: bool = False, max_steps: int | None = None,
                 depth: bool | None = None, assets: dict[str, str] | None = None):
        if task not in TASKS:
            raise KeyError(f"unknown task {task!r}; known: {list(TASKS)}")
        self.task, self.spec = task, TASKS[task]
        self.depth_enabled = DEFAULT_DEPTH if depth is None else bool(depth)
        inst = None
        if instance is not None:
            inst = instance if isinstance(instance, dict) else json.load(open(instance))
            if inst.get("task") != task:
                raise ValueError(f"instance task {inst.get('task')} != session task {task}")
            assets = dict(inst["assets"])
        if not assets:
            raise ValueError("a Session needs an instance (or, to make one, the object assets)")
        self.assets = dict(assets)
        self.max_steps = int(max_steps or MAX_STEPS)
        t0 = time.time()
        _log(f"launching Isaac Sim (headless, cameras on) for {self.spec['env']} with {self.assets}; ~2-3 min (the first start in a "
             f"container also compiles shaders: ~10 min) ...")
        self.app = _launch_app()
        import torch
        self.th = torch
        self.env = self._make_env()
        self.device = self.env.device
        self.control_dt = float(self.env.step_dt)
        self.arm = {a: self.env.scene[ARM_ASSET[a]] for a in ARMS}
        self.joint_ids = {}
        for a in ARMS:
            names = list(self.arm[a].joint_names)
            self.joint_ids[a] = [names.index(j) for j in ARM_JOINTS] + [names.index("left_finger"), names.index("right_finger")]
        self._recording: list[np.ndarray] | None = None
        self._video: dict | None = None
        self.episode_done = False
        self.end_reason: str | None = None
        self.n_steps = 0
        self._resets = 0
        self._frame_mark = None
        self._n_restores = 0
        self._pristine = False
        self._total_steps = 0
        self._end_logged = False
        _slog("session_start", task=task)
        import atexit
        atexit.register(self._log_end)
        self._ik: dict = {}
        # YAMLab's own reset (scene build, reset events, 4 warm-up physics steps), then the frozen state if given
        self.env.reset()
        if inst is not None:
            self._restore(inst["initial_state"])
        self._pristine = inst is not None    # nothing has stepped since the frozen state was restored
        self.initial_state = self._tree_to_lists(self.env.scene.get_state(is_relative=True))
        self.instance_sha = self.state_sha()
        expected = inst.get("state_sha") if inst else None
        self.instance_exact = expected is None or expected == self.instance_sha
        self.instance_matches = self.instance_exact or (inst is not None and self._poses_match(inst))
        if not self.instance_exact:
            if self.instance_matches:
                _log(f"WARNING: state sha {self.instance_sha} != {expected} but every object pose / joint matches within tolerance (different host?)")
            else:
                msg = f"instance state sha {self.instance_sha} != expected {expected} and poses differ (asset / simulator version drift?)"
                if strict:
                    raise RuntimeError(msg)
                _log("WARNING:", msg)
        self._targets = self._current_targets()
        self._model, self._cams = None, {}
        try:
            self._kin_setup()
        except Exception as exc:  # noqa: BLE001
            self._model = None; _log(f"WARNING: no kinematic model / robot spec / proprio extras: {repr(exc)[:300]}")
        try:
            self._camera_setup()
        except Exception as exc:  # noqa: BLE001
            self._cams = {}; _log(f"WARNING: no camera info / depth: {repr(exc)[:300]}")
        _log(f"instance ready in {time.time() - t0:.0f}s; state_sha={self.instance_sha}; control {1 / self.control_dt:.0f} Hz; "
             f"goal: {self.spec['text']}")

    # ---- env construction
    def _make_env(self):
        from yamlab.utils.task_creation import create_task_environment
        from yamlab.envs.tasks.yam_bimanual_env import YamBimanualEnv
        orig = YamBimanualEnv.__init__
        depth = self.depth_enabled
        self._fall_terms: list[tuple[str, str, float]] = []

        def init(env_self, cfg, render_mode=None, **kw):
            # every camera renders RGB at the sensor's 640x480; with depth on, also z-depth (read by render_depth; never physics)
            from isaaclab.sensors import TiledCameraCfg
            for name in [f"{c}_camera" for c in CAMERAS]:
                cam = getattr(cfg.scene, name, None)
                if isinstance(cam, TiledCameraCfg) and depth and DEPTH_TYPE not in cam.data_types:
                    cam.data_types = [*cam.data_types, DEPTH_TYPE]
            # YAMLab's "<object>_below_table" terminations (object root more than `margin` below the table top): its env
            # would reset the scene there; this tooling ends the episode there instead (a failure), with the scene as it is
            for tname in list(vars(cfg.terminations)):
                term = getattr(cfg.terminations, tname)
                if tname.endswith("_below_table") and term is not None:
                    pr = term.params
                    self._fall_terms.append((tname, pr["asset_cfg"].name, float(pr["table_z"]) - float(pr.get("margin", 0.01))))
                    setattr(cfg.terminations, tname, None)
            # the ground plane: the image's copy of Isaac Lab's default ground (otherwise fetched from NVIDIA's asset bucket at
            # run time; the tasks have no general network access); same file, same physics
            ground = getattr(cfg.scene, "ground", None)
            if ground is not None and os.path.isfile(GROUND_USD):
                ground.spawn.usd_path = GROUND_USD
            if ENHANCED_DETERMINISM:
                cfg.sim.physx.enable_enhanced_determinism = True
            # A fixed seed: YAMLab sets none, so its reset events (random object poses, then 4 warm-up physics steps) differ
            # from process to process, and PhysX keeps contact data from them that a later state restore does not overwrite
            # (measured: identical restored states, different velocities after the first step). With the seed every fresh
            # process makes the same calls before the frozen state is restored, so fresh-process runs are bit-identical.
            cfg.seed = ENV_SEED
            orig(env_self, cfg, render_mode, **kw)
        YamBimanualEnv.__init__ = init
        try:
            # "replay": YAMLab's single-env CPU configuration without its time-out / success terminations (this tooling ends
            # the episode at the first success itself) and without domain randomization; is_evaluation_mode: YAMLab's
            # evaluation thresholds. No image observation terms: frames are rendered when asked for (render_frame).
            env = create_task_environment(task_name=self.spec["env"], assets_instance_paths=asset_paths(self.task, self.assets),
                                          objects_randomization=None, init_joint_pos_randomization=0.0, mode="replay", device="cpu",
                                          observation_modalities=["proprioception"], enable_self_collisions=False,
                                          enable_gripper_grasp_clamp=False, is_evaluation_mode=True)
        finally:
            YamBimanualEnv.__init__ = orig
        # Rendering never steps physics: the cameras render only when a frame is asked for (one sim.render() per new state),
        # not inside every env.step (~3x faster stepping; the physics and the state hashes are the same either way).
        env.cfg.sim.render_interval = 10 ** 9
        return env

    # ---- state tree helpers (InteractiveScene.get_state layout, env 0)
    def _tree_to_lists(self, tree: dict) -> dict:
        out = {}
        for k in sorted(tree):
            v = tree[k]
            out[k] = self._tree_to_lists(v) if isinstance(v, dict) else v[0].detach().cpu().numpy().astype(np.float32).tolist()
        return out

    def _lists_to_tree(self, tree_lists: dict) -> dict:
        out = {}
        for k, v in tree_lists.items():
            out[k] = self._lists_to_tree(v) if isinstance(v, dict) else self.th.as_tensor(np.asarray(v, dtype=np.float32), device=self.device).unsqueeze(0)
        return out

    def _flat_state(self) -> np.ndarray:
        parts: list[np.ndarray] = []

        def rec(t):
            for k in sorted(t):
                v = t[k]
                if isinstance(v, dict):
                    rec(v)
                else:
                    parts.append(v[0].detach().cpu().numpy().astype(np.float32).ravel())
        rec(self.env.scene.get_state(is_relative=True))
        return np.concatenate(parts) if parts else np.zeros(0, np.float32)

    def state_sha(self) -> str:
        return hashlib.sha1(np.ascontiguousarray(self._flat_state()).tobytes()).hexdigest()[:16]

    def _restore(self, tree_lists: dict) -> None:
        """env.reset_to(...) with the stored state (Isaac Lab's recipe: the reset events run, then the scene state is
        written, joint targets = the stored joint positions), then YAMLab's stage flags and counters are cleared."""
        self.env.reset_to(self._lists_to_tree(tree_lists), env_ids=None, is_relative=True)
        self.env.reset_success_check()
        # One render right after the restore, always: measured on Isaac Sim 5.1 / CPU PhysX, a run that starts without a
        # render after reset_to depends on what ran before the restore (the state hashes of a live run and of a replay after
        # a second restore differ), while with this render every run from the frozen state ends in the same state, whether
        # frames are rendered after every step, now and then (render_frame, videos) or never.
        self.env.sim.render()
        self._n_restores += 1
        self._frame_mark = ((self._n_restores, self.n_steps), set())

    def _poses_match(self, inst: dict, pos_tol: float = 2e-3, quat_tol: float = 2e-2, joint_tol: float = 2e-3) -> bool:
        try:
            objs = self.objects()
            for name, ref in (inst.get("objects") or {}).items():
                cur = objs.get(name)
                if cur is None or np.max(np.abs(np.asarray(cur["position"]) - np.asarray(ref["position"]))) > pos_tol:
                    return False
                q0, q1 = np.asarray(cur["orientation_wxyz"]), np.asarray(ref["orientation_wxyz"])
                if min(np.max(np.abs(q0 - q1)), np.max(np.abs(q0 + q1))) > quat_tol:
                    return False
            for a in ARMS:
                ref_q = (inst.get("robot_joint_positions") or {}).get(a)
                if ref_q is None or np.max(np.abs(self.joint_positions(a) - np.asarray(ref_q))) > joint_tol:
                    return False
            return bool(inst.get("objects"))
        except Exception as exc:  # noqa: BLE001
            _log("pose comparison failed:", repr(exc)[:120])
            return False

    # ---- episode control
    def reset(self) -> None:
        """Return to the frozen instance state (state restore through env.reset_to; joint targets back to the stored joint
        positions; YAMLab's stage flags cleared). In a fresh Session that has not stepped yet this is a no-op, so the first
        run or replay in a process makes exactly the calls of any other fresh process: that run is bit-identical to the
        grader's fresh-process replays. After stepping, PhysX keeps contact data across a restore, so later in-process
        runs of the same actions can end slightly differently (the CLI `replay`, a fresh process, is the reference)."""
        _slog("reset", task=self.task, n=self._resets + 1, sim_steps_before=self.n_steps)
        self._resets += 1
        self._total_steps += self.n_steps
        self._recording = None
        if self._pristine and self.n_steps == 0:
            return
        self.episode_done = False
        self.end_reason = None
        self.n_steps = 0
        self._restore(self.initial_state)
        self._targets = self._current_targets()

    def _current_targets(self) -> np.ndarray:
        out = np.zeros(ACTION_DIM, np.float64)
        for a in ARMS:
            q = _np(self.arm[a].data.joint_pos)[0]
            ids = self.joint_ids[a]
            out[ARM_SLICE[a]] = q[ids[:6]]; out[GRIP_INDEX[a]] = q[ids[6]]
        return out

    def success(self) -> bool:
        return bool(self.env.get_task_success()[0].item())

    def stages(self) -> dict[str, bool]:
        return {name: bool(getattr(self.env, f"stage{i + 1}_success")[0].item()) for i, name in enumerate(self.spec["stages"])}

    def success_params(self) -> dict[str, Any]:
        """The numbers of YAMLab's success check on this instance (its task computes them from the two assets' sizes)."""
        e = self.env; r = lambda x: round(float(x), 5)  # noqa: E731
        table_z = float(__import__("yamlab.robot.yam", fromlist=["ROBOT"]).ROBOT.table_position[2])
        if self.task == "put_pot_on_cooktop":
            return {"table_z": r(table_z), "pot_height": r(e.pot_height), "cooktop_height": r(e.cooktop_height),
                    "pot_rest_z": r(e.pot_init_z), "pick_lift_m": 0.05, "pick_steps": int(e._pick_required_consecutive_steps),
                    "place_xy_tol_m": r(e.ontop_xy_threshold), "place_z_tol_m": 0.02, "upright_tol_rad": 0.2,
                    "place_steps": int(e._ontop_required_consecutive_steps)}
        return {"table_z": r(table_z), "mug_height": r(e.mug_height), "mug_rest_z": r(e.mug_init_z), "pick_lift_m": 0.05,
                "pick_steps": int(e._pick_required_consecutive_steps), "handover_lift_m": 0.05,
                "handover_steps": int(e._handover_required_consecutive_steps), "hang_xy_tol_m": r(e.hang_xy_tolerance),
                "hang_min_z": r(table_z + float(e.mug_height) / 2.0 + 0.05), "hang_z_stability_m": r(e._hang_stability_threshold),
                "hang_steps": int(e._hang_required_consecutive_steps)}

    def step(self, action) -> bool:
        """Apply one low-level action (14 entries, see ACTION_LAYOUT) for one control step (1/30 s). Returns True when the
        episode is over: every stage of the task has latched (success; YAMLab's evaluation ends the episode there), a task
        object fell off the table (failure; YAMLab's evaluation ends it there too) or MAX_STEPS ran (a runaway guard, not a
        budget); further steps raise."""
        a = np.asarray(action, dtype=np.float32).reshape(-1)
        if a.size != ACTION_DIM:
            raise ValueError(f"action must have {ACTION_DIM} entries, got {a.size}")
        if not np.all(np.isfinite(a)):
            raise ValueError("action contains nan/inf")
        if self.episode_done:
            raise PrimitiveError(f"episode is over ({self.end_reason}); call reset() before stepping again")
        if self._recording is not None:
            self._recording.append(a.copy())
        self.env.step(self.th.as_tensor(a, device=self.device).unsqueeze(0))
        self._pristine = False
        self._targets = a.astype(np.float64)
        self.n_steps += 1
        if self._video is not None and self.n_steps % self._video["every"] == 0:
            self._video_add()
        if self.success():
            self.episode_done, self.end_reason = True, "success"
        elif self.fallen():
            self.episode_done, self.end_reason = True, f"{self.fallen()} fell off the table"
        elif self.n_steps >= self.max_steps:
            self.episode_done, self.end_reason = True, "step_guard"
        return self.episode_done

    def fallen(self) -> str | None:
        """The task object that has fallen below the table top (YAMLab's `<object>_below_table` rule: its root more than
        1 cm below the table surface), if any. YAMLab's evaluation ends the episode there (a failure); so does this tooling."""
        for _tname, obj, z_min in self._fall_terms:
            if float(_np(self.env.scene.rigid_objects[obj].data.root_pos_w)[0, 2]) < z_min:
                return obj
        return None

    def hold_action(self) -> np.ndarray:
        """The action that keeps the current joint targets and gripper commands (what the robot does when idle)."""
        return self._targets.copy()

    def status(self) -> dict[str, Any]:
        st = self.stages()
        return {"success": self.success(), "stages": st, "progress": round(sum(st.values()) / len(st), 4), "sim_steps": int(self.n_steps),
                "resets": self._resets, "state_sha": self.state_sha(), "terminated": bool(self.episode_done), "end_reason": self.end_reason}

    # ---- recording / trajectories
    def record_start(self) -> None:
        self._recording = []

    def record_stop(self) -> np.ndarray:
        acts = np.stack(self._recording) if self._recording else np.zeros((0, ACTION_DIM), np.float32)
        self._recording = None
        _slog("record", task=self.task, n_actions=int(len(acts)))
        return acts.astype(np.float32)

    def save_trajectory(self, actions: np.ndarray, path: str | Path, meta: dict | None = None) -> None:
        np.savez(path, actions=np.asarray(actions, dtype=np.float32), task=self.task, yamlab_env=self.spec["env"],
                 instance_sha=self.instance_sha, action_dim=ACTION_DIM, action_layout=ACTION_LAYOUT, meta=json.dumps(meta or {}))

    def replay(self, actions: np.ndarray) -> dict[str, Any]:
        """Open-loop replay after reset(). In a fresh Session (nothing stepped yet) it is bit-identical to the grader's
        fresh-process replays; after other runs in the same process it can end slightly differently (PhysX keeps contact
        data across a restore), which is why the verifier replays in fresh processes. Stops at the first success."""
        self.reset()
        for a in np.asarray(actions, dtype=np.float32):
            if self.step(a):
                break
        st = self.status()
        _slog("replay", task=self.task, n_actions=int(len(actions)), success=st["success"])
        return st

    # ---- cameras (Isaac Lab TiledCameras: "top" is static above the table, the wrist cameras ride on each arm's link_6)
    VIDEO_CAMERAS: tuple[str, ...] = CAMERAS

    def _sensor(self, camera: str):
        sen = self.env.scene.sensors.get(f"{camera}_camera")
        if sen is None:
            raise KeyError(f"unknown camera {camera!r}; known: {list(CAMERAS)}")
        return sen

    def _fresh(self, camera: str):
        """The camera sensor with its output rendered for the current state: one sim.render() per new state (never steps
        physics), then the sensor reads it."""
        mark = (self._n_restores, self.n_steps)
        if self._frame_mark is None or self._frame_mark[0] != mark:
            self.env.sim.render()
            self._frame_mark = (mark, set())
        sen = self._sensor(camera)
        if camera not in self._frame_mark[1]:
            sen.update(0.0, force_recompute=True); self._frame_mark[1].add(camera)
        return sen

    def render_frame(self, camera: str = "top", size: tuple[int, int] | None = None) -> np.ndarray:
        """RGB (H, W, 3) uint8 of one camera ("top", "left_wrist", "right_wrist") for the current state; `size=(w, h)` resizes."""
        img = np.ascontiguousarray(_tt(self._fresh(camera).data.output["rgb"])[0, ..., :3].detach().cpu().numpy().astype(np.uint8))
        if size is not None and (img.shape[1], img.shape[0]) != tuple(size):
            import cv2
            img = cv2.resize(img, tuple(size), interpolation=cv2.INTER_AREA)
        return img

    def render_depth(self, camera: str = "top") -> np.ndarray:
        """float32 (H, W) z-depth in metres of one camera for the current state (distance from the camera plane along the
        optical axis), pixel-aligned with render_frame(camera); 0 = no reading. Needs Session(..., depth=True)."""
        if not self.depth_enabled:
            raise RuntimeError("this Session renders no depth: create it with Session(..., depth=True)")
        out = self._fresh(camera).data.output
        z = np.array(_tt(out[DEPTH_TYPE])[0, ..., 0].detach().cpu().numpy(), dtype=np.float32)
        z[~np.isfinite(z) | (z <= 0) | (z > DEPTH_MAX_M)] = 0.0
        return z

    def _camera_setup(self) -> None:
        """Per camera, once: the pinhole intrinsics, the image size, the clipping range and the mount. A camera prim under a
        robot link rides on it (link -> camera read from the USD; its world pose is the link's measured pose times that
        offset); any other is static."""
        from pxr import Usd, UsdGeom, UsdPhysics
        cache = UsdGeom.XformCache(Usd.TimeCode.Default())
        origin = _np(self.env.scene.env_origins)[0]
        self._cams = {}
        for cam in CAMERAS:
            sen = self._sensor(cam)
            prim = sen._sensor_prims[0].GetPrim(); parent = prim.GetParent()
            K = _np(sen.data.intrinsic_matrices)[0]
            H, W = (int(x) for x in sen.data.image_shape)
            near, far = (float(x) for x in UsdGeom.Camera(prim).GetClippingRangeAttr().Get())
            m = {"K": K, "size": [W, H], "range": [near, min(far, DEPTH_MAX_M)], "link_T_cv": None, "world_T_cv": None}
            arm = next((a for a in ARMS if f"/{ARM_ASSET[a].split('_')[0].capitalize()}Arm/" in str(prim.GetPath())), None)
            if arm is not None and parent.GetName() == FLANGE_BODY and parent.HasAPI(UsdPhysics.RigidBodyAPI):
                m["link_T_cv"] = np.array(cache.ComputeRelativeTransform(prim, parent)[0], dtype=np.float64).T @ GL2CV
                m["arm"] = arm
                m["mount"] = {"type": "link", "parent_link": f"{arm}_{FLANGE_BODY}", "link_T_cam_cv": m["link_T_cv"].tolist()}
            else:
                gl = np.array(cache.GetLocalToWorldTransform(prim), dtype=np.float64).T; gl[:3, 3] -= origin
                m["world_T_cv"] = gl @ GL2CV
                m["mount"] = {"type": "static", "extrinsic_cv": np.linalg.inv(m["world_T_cv"])[:3].tolist(), "cam2world_gl": gl.tolist()}
            self._cams[cam] = m

    def _cam_world_T_cv(self, cam: str) -> np.ndarray:
        m = self._cams[cam]
        if m["world_T_cv"] is not None:
            return m["world_T_cv"]
        p, q = self.body_pose(m["arm"], FLANGE_BODY)
        return hom(quat_to_mat(q), p) @ m["link_T_cv"]

    def camera_info(self, cameras=None) -> dict[str, dict]:
        """{cam: {"intrinsic_cv": 3x3, "extrinsic_cv": 3x4 world -> camera (OpenCV axes: x right, y down, z forward),
        "cam2world_gl": 4x4 camera -> world (OpenGL axes), "image_size": [W, H], "mount": static world pose | parent link
        + fixed link_T_cam_cv, "moves": bool, "depth_range_m": [near, far]}} for the current state. Reads only."""
        out = {}
        for c in (list(cameras) if cameras is not None else list(self._cams)):
            if c not in self._cams:
                raise KeyError(f"unknown camera {c!r}; known: {list(self._cams)}")
            m = self._cams[c]; Tw = self._cam_world_T_cv(c)
            out[c] = {"intrinsic_cv": m["K"].tolist(), "extrinsic_cv": np.linalg.inv(Tw)[:3].tolist(), "cam2world_gl": (Tw @ GL2CV).tolist(),
                      "image_size": list(m["size"]), "mount": json.loads(json.dumps(m["mount"])), "moves": m["mount"]["type"] == "link",
                      "depth_range_m": list(m["range"])}
        return out

    def render_grid(self, cameras: tuple[str, ...] = CAMERAS, cols: int = 3, size: tuple[int, int] = (320, 240)) -> np.ndarray:
        """One image tiling `cameras` (row-major, `cols` per row; each resized to `size`)."""
        tiles = [self.render_frame(c, size=size) for c in cameras]
        while len(tiles) % cols:
            tiles.append(np.zeros_like(tiles[0]))
        return np.concatenate([np.concatenate(tiles[i:i + cols], axis=1) for i in range(0, len(tiles), cols)], axis=0)

    def _video_frame(self) -> np.ndarray:
        """The top camera at 640x480 with both wrist cameras stacked on its right (320x240 each): 960x480."""
        top = self.render_frame("top", size=(640, 480))
        side = np.concatenate([self.render_frame("left_wrist", size=(320, 240)), self.render_frame("right_wrist", size=(320, 240))], axis=0)
        return np.ascontiguousarray(np.concatenate([top, side], axis=1))

    def render_video(self, actions: np.ndarray, path: str | Path, *, every: int = 2, fps: int = 15) -> dict[str, Any]:
        """Replay `actions` from the frozen instance (reset() first) and write an MP4 (top camera + both wrist cameras), one
        frame every `every` control steps (+ `<path>.last.png`). Returns the final status plus n_frames and the video path."""
        self.reset()
        self.start_video(path, fps=fps, every=every)
        for a in np.asarray(actions, dtype=np.float32):
            if self.step(a):
                break
        n = self._video["n"] if self._video else 0
        self.stop_video()
        return {**self.status(), "n_frames": n, "video": str(path)}

    def start_video(self, path: str | Path, fps: int = 15, every: int | None = None) -> None:
        """Film the steps from now on (every `every` control steps; default 30 Hz / fps) to `path` (mp4) until stop_video()."""
        import imageio.v2 as imageio
        every = every or max(1, CONTROL_HZ // fps)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        w = imageio.get_writer(str(path), fps=fps, format="FFMPEG", codec="libx264", macro_block_size=1)
        self._video = {"path": str(path), "every": every, "writer": w, "last": None, "n": 0, "error": None}
        self._video_add()

    def _video_add(self) -> None:
        """One frame to the encoder. Filming never decides a run: a frame that cannot be rendered or written stops the
        filming (the reason is logged and stop_video() returns None), never the control step it belongs to."""
        v = self._video
        if v is None or v["error"]:
            return
        try:
            f = self._video_frame(); v["writer"].append_data(f); v["last"] = f; v["n"] += 1
        except Exception as exc:  # noqa: BLE001
            v["error"] = repr(exc)[:200]; _log("video: filming stopped:", v["error"])

    def stop_video(self) -> str | None:
        """End the filming started by start_video(). Returns the video's path, or None when nothing was being filmed or
        the video could not be written (logged; a failed video never raises here, it must not undo the run it filmed)."""
        if self._video is None:
            return None
        v, self._video = self._video, None
        try:
            if not v["error"] and (v["n"] == 0 or self.n_steps % v["every"] != 0):
                try:
                    v["last"] = self._video_frame(); v["writer"].append_data(v["last"])     # the final state is always the last frame
                except Exception:  # noqa: BLE001
                    pass
            v["writer"].close()
            if v["error"] or v["last"] is None:
                raise RuntimeError(v["error"] or "no frame was filmed")
            import imageio.v2 as imageio
            imageio.imwrite(str(Path(v["path"]).with_suffix(".last.png")), v["last"])
            return v["path"]
        except Exception as exc:  # noqa: BLE001
            _log("video: not written:", repr(exc)[:200])
            return None

    # ---- objects (world frame = env-local frame of the single env)
    def object_names(self) -> list[str]:
        return list(self.spec["objects"])

    def object_pose(self, name: str) -> tuple[np.ndarray, np.ndarray]:
        """(position(3), quaternion wxyz(4)) of a task object (its root: the centre of its bounding box)."""
        objs = self.env.scene.rigid_objects
        if name not in objs:
            raise KeyError(f"unknown object {name!r}; known: {self.object_names()}")
        o = objs[name]
        pos = _np(o.data.root_pos_w)[0] - _np(self.env.scene.env_origins)[0]
        return pos, _np(o.data.root_quat_w)[0]

    def object_size(self, name: str) -> np.ndarray:
        """Extents (x, y, z) of the object in its own frame (YAMLab's asset_size.json; the root is the box centre)."""
        if not hasattr(self, "_sizes"):
            self._sizes = {}
        if name not in self._sizes:
            d = json.load(open(Path(asset_paths(self.task, self.assets)[name]) / "asset_size.json"))["size"]
            self._sizes[name] = np.array([d["x"], d["y"], d["z"]], dtype=np.float64)
        return self._sizes[name]

    def object_bounds(self, name: str) -> np.ndarray:
        """Axis-aligned bounding box [[xmin,ymin,zmin],[xmax,ymax,zmax]] of the object's (rotated) box, world frame."""
        p, q = self.object_pose(name); h = self.object_size(name) / 2.0
        c = np.array([[sx, sy, sz] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)], dtype=np.float64) * h
        w = c @ quat_to_mat(q).T + p
        return np.stack([w.min(axis=0), w.max(axis=0)])

    def objects(self) -> dict[str, dict]:
        """Task objects by name -> position, orientation_wxyz, size (own frame), bounds (AABB [[min],[max]]), velocity."""
        out = {}
        for n in self.object_names():
            p, q = self.object_pose(n)
            b = self.object_bounds(n)
            v = _np(self.env.scene.rigid_objects[n].data.root_lin_vel_w)[0]
            out[n] = {"position": [round(float(x), 5) for x in p], "orientation_wxyz": [round(float(x), 6) for x in q],
                      "size": [round(float(x), 5) for x in self.object_size(n)], "bounds": [[round(float(x), 5) for x in r] for r in b],
                      "velocity": [round(float(x), 5) for x in v]}
        return out

    def object_points(self, name: str, max_points: int = 4000) -> np.ndarray:
        """Surface points (N, 3) of a task object's meshes in the world frame: the USD mesh vertices (cached, in the
        object's frame) transformed by the object's current pose."""
        if not hasattr(self, "_pts_cache"):
            self._pts_cache = {}
        if name not in self._pts_cache:
            import omni.usd
            from pxr import Usd, UsdGeom
            obj = self.env.scene.rigid_objects[name]
            stage = omni.usd.get_context().get_stage()
            path = re.sub(r"env_\.\*", "env_0", str(obj.cfg.prim_path).replace("{ENV_REGEX_NS}", "/World/envs/env_0"))
            prim = stage.GetPrimAtPath(path)
            if not prim or not prim.IsValid():
                raise KeyError(f"no USD prim at {path} for object {name!r}")
            cache = UsdGeom.XformCache(Usd.TimeCode.Default())
            groups: dict[str, list] = {"visual": [], "collision": []}
            for qp in Usd.PrimRange(prim):
                if not qp.IsA(UsdGeom.Mesh):
                    continue
                arr = UsdGeom.Mesh(qp).GetPointsAttr().Get()
                if not arr:
                    continue
                M = np.array(cache.ComputeRelativeTransform(qp, prim)[0]).reshape(4, 4)
                a = np.array([[v[0], v[1], v[2], 1.0] for v in arr], dtype=np.float64) @ M
                groups["collision" if "collision" in str(qp.GetPath()).lower() else "visual"].append(a[:, :3])
            pts_l = groups["visual"] or groups["collision"]
            pts = np.concatenate(pts_l) if pts_l else np.zeros((0, 3))
            if len(pts) > max_points:
                pts = pts[np.linspace(0, len(pts) - 1, max_points).astype(int)]
            self._pts_cache[name] = pts
        p, q = self.object_pose(name)
        return (quat_to_mat(q) @ self._pts_cache[name].T).T + p

    # ---- the robot (measured; reads only)
    def body_pose(self, arm: str, body: str) -> tuple[np.ndarray, np.ndarray]:
        """(position, quaternion wxyz) of one link of an arm ("left" / "right"), world frame."""
        art = self.arm[arm]
        idx = list(art.body_names).index(body)
        pose = _np(art.data.body_pose_w)[0, idx]
        return pose[:3] - _np(self.env.scene.env_origins)[0], pose[3:7]

    def joint_positions(self, arm: str) -> np.ndarray:
        """The arm's joint1..6 (rad) and its gripper (left_finger, m) positions: 7 values."""
        q = _np(self.arm[arm].data.joint_pos)[0]
        return q[self.joint_ids[arm][:7]]

    def joint_velocities(self, arm: str) -> np.ndarray:
        q = _np(self.arm[arm].data.joint_vel)[0]
        return q[self.joint_ids[arm][:7]]

    def finger_positions(self, arm: str) -> tuple[float, float]:
        """(left_finger, right_finger) joint positions (m): -0.0475 = fully open, 0.0 = closed."""
        q = _np(self.arm[arm].data.joint_pos)[0]
        return float(q[self.joint_ids[arm][6]]), float(q[self.joint_ids[arm][7]])

    def gripper_opening(self, arm: str) -> float:
        """How far the two fingers are open (m): -(left_finger + right_finger); 0.0 closed on nothing, 0.095 fully open."""
        lf, rf = self.finger_positions(arm)
        return float(max(0.0, -(lf + rf)))

    def ee_pose(self, arm: str) -> tuple[np.ndarray, np.ndarray]:
        """(position, quaternion wxyz) of the arm's tool frame `<arm>_tcp` (see robot_spec()["tcp"]), world frame."""
        self._need_model()
        p, q = self.body_pose(arm, FLANGE_BODY)
        T = hom(quat_to_mat(q), p) @ self._M_tcp[arm]
        return T[:3, 3].copy(), mat_to_quat(T[:3, :3])

    def joint_efforts(self, arm: str) -> np.ndarray:
        """Drive-effort estimate of joint1..6 (N m): stiffness * (target - q) + damping * (target velocity - qdot), clipped to
        the effort limit (a motor-current analogue: it grows when the arm pushes on something)."""
        self._need_model(); d = self.arm[arm].data; ids = self.joint_ids[arm][:6]
        g = lambda x: _np(x)[0, ids]  # noqa: E731
        e = self._kp[arm] * (g(d.joint_pos_target) - g(d.joint_pos)) + self._kd[arm] * (g(d.joint_vel_target) - g(d.joint_vel))
        return np.clip(e, -self._effort_lim[arm], self._effort_lim[arm])

    def proprio(self) -> dict[str, Any]:
        """Measured proprioception, per arm (left first): joint_pos (joint1..6 rad, left_finger m), joint_vel (same), tcp_pose
        (x y z qw qx qy qz, world), gripper_opening (m), joint_effort (joint1..6, N m), gripper_cmd (the gripper target in
        force, m). Reads, never steps."""
        out: dict[str, Any] = {"joint_pos": [], "joint_vel": [], "tcp_pose": [], "gripper_opening": [], "joint_effort": [], "gripper_cmd": []}
        for a in ARMS:
            p, q = self.ee_pose(a)
            out["joint_pos"] += [float(x) for x in self.joint_positions(a)]
            out["joint_vel"] += [float(x) for x in self.joint_velocities(a)]
            out["tcp_pose"] += [float(x) for x in p] + [float(x) for x in q]
            out["gripper_opening"].append(self.gripper_opening(a))
            out["joint_effort"] += [float(x) for x in self.joint_efforts(a)]
            out["gripper_cmd"].append(float(self._targets[GRIP_INDEX[a]]))
        return out

    def state_summary(self) -> dict:
        out = {"joints": {a: [round(float(x), 6) for x in self.joint_positions(a)] for a in ARMS}, "objects": {}}
        for n in self.object_names():
            p, q = self.object_pose(n)
            out["objects"][n] = {"position": [round(float(x), 6) for x in p], "orientation_wxyz": [round(float(x), 6) for x in q]}
        return out

    # ---- the robot's kinematic model and spec sheet (read once at startup; stateless afterwards)
    def _need_model(self) -> None:
        if self._model is None:
            raise RuntimeError("the robot model could not be built at startup (see the [rcb] WARNING in the log)")

    def _kin_setup(self) -> None:
        """Per arm: a numpy model from the arm's USD joint frames (base -> joint1..6 -> link_6) plus the tool frame `<arm>_tcp`
        (the midpoint of the two fingertips, fixed in link_6: the fingers close symmetrically), checked against the
        simulator's link poses; the joint limits, gains and the spec sheet. Reads the stage, writes nothing."""
        import omni.usd
        from pxr import Usd, UsdPhysics
        stage = omni.usd.get_context().get_stage()
        gq = lambda q: np.array([q.GetReal(), *q.GetImaginary()], dtype=np.float64)  # noqa: E731
        self._model, self._M_tcp, self._kp, self._kd, self._effort_lim = {}, {}, {}, {}, {}
        self.kinematics_check = {}
        from yamlab.robot.yam import ROBOT
        tips = {k: np.asarray(v["keypoints"][0], dtype=np.float64) for k, v in ROBOT.fingers.items()} if hasattr(ROBOT, "fingers") else {}
        for a in ARMS:
            art = self.arm[a]
            root_path = re.sub(r"env_\.\*", "env_0", str(art.cfg.prim_path).replace("{ENV_REGEX_NS}", "/World/envs/env_0"))
            rev = {}
            for p in Usd.PrimRange(stage.GetPrimAtPath(root_path)):
                if not p.IsA(UsdPhysics.RevoluteJoint):
                    continue
                j = UsdPhysics.Joint(p)
                b0, b1 = j.GetBody0Rel().GetTargets(), j.GetBody1Rel().GetTargets()
                if not b0 or not b1:
                    continue
                A = hom(quat_to_mat(gq(j.GetLocalRot0Attr().Get())), list(j.GetLocalPos0Attr().Get()))
                B = hom(quat_to_mat(gq(j.GetLocalRot1Attr().Get())), list(j.GetLocalPos1Attr().Get()))
                axis = np.zeros(3); axis["XYZ".index(str(UsdPhysics.RevoluteJoint(p).GetAxisAttr().Get()))] = 1.0
                rev[p.GetName()] = (b0[0].name, b1[0].name, A, axis, np.linalg.inv(B))
            joints = [(n, *rev[n]) for n in ARM_JOINTS]
            if joints[-1][2] != FLANGE_BODY:
                raise RuntimeError(f"{a} arm: joint6 ends at {joints[-1][2]}, not {FLANGE_BODY}")
            # tool frame: the midpoint of the two fingertips (YAMLab's finger keypoints, in the finger link frames), in link_6;
            # orientation = link_6's
            fp, fq = self.body_pose(a, FLANGE_BODY); T6 = hom(quat_to_mat(fq), fp)
            mids = []
            for fk, link in (("lf", "left_finger"), ("rf", "right_finger")):
                lp, lq = self.body_pose(a, link)
                mids.append(quat_to_mat(lq) @ tips.get(fk, np.zeros(3)) + lp)
            tcp_w = (mids[0] + mids[1]) / 2.0
            self._M_tcp[a] = hom(None, (np.linalg.inv(T6) @ np.append(tcp_w, 1.0))[:3])
            d = art.data
            arr = lambda x: _np(x)[0]  # noqa: E731
            lim, vel, eff, kp, kd = (arr(x) for x in (d.joint_pos_limits, d.joint_vel_limits, d.joint_effort_limits, d.joint_stiffness, d.joint_damping))
            ids = self.joint_ids[a][:6]
            self._kp[a], self._kd[a], self._effort_lim[a] = kp[ids], kd[ids], eff[ids]
            base = joints[0][1]
            bp, bq = self.body_pose(a, base)
            self._model[a] = ArmModel(base, hom(quat_to_mat(bq), bp), joints, [(FLANGE_BODY, "tcp", self._M_tcp[a])],
                                      lim[ids, 0], lim[ids, 1], np.zeros(6))
            T = self._model[a].fk(self.joint_positions(a)[:6]); ep_max = er_max = 0.0
            for name in self._model[a].links:
                if name in art.body_names:
                    p, q = self.body_pose(a, name)
                    ep_max = max(ep_max, float(np.linalg.norm(T[name][:3, 3] - p))); er_max = max(er_max, rot_angle(T[name][:3, :3], quat_to_mat(q)))
            self.kinematics_check[a] = {"links_max_pos_err_m": ep_max, "links_max_rot_err_rad": er_max,
                                        "tcp_from_link6_m": [round(float(x), 5) for x in self._M_tcp[a][:3, 3]]}
            _log(f"{a} arm model vs simulator: links {ep_max * 1e3:.4f} mm / {math.degrees(er_max):.4f} deg; tcp in link_6 "
                 f"{np.round(self._M_tcp[a][:3, 3], 4).tolist()}")
            if ep_max > 1e-3 or er_max > 1e-2:
                _log(f"WARNING: the {a} arm model disagrees with the simulator: {self.kinematics_check[a]}")
            self._limits = getattr(self, "_limits", {}); self._limits[a] = (lim, vel, eff, kp, kd)
        self._build_specs()

    def _build_specs(self) -> None:
        r6 = lambda x: round(float(x), 6)  # noqa: E731
        joints = []
        for a in ARMS:
            lim, vel, eff, kp, kd = self._limits[a]
            names = list(self.arm[a].joint_names)
            for n in list(ARM_JOINTS) + ["left_finger"]:
                i = names.index(n)
                joints.append({"name": f"{a}_{n}", "type": "prismatic" if n == "left_finger" else "revolute", "unit": "m" if n == "left_finger" else "rad",
                               "position_limits": [r6(lim[i, 0]), r6(lim[i, 1])], "velocity_limit": r6(vel[i]), "effort_limit": r6(eff[i]),
                               "group": f"{a}_gripper" if n == "left_finger" else f"{a}_arm"})
        gains = {}
        for a in ARMS:
            lim, vel, eff, kp, kd = self._limits[a]; names = list(self.arm[a].joint_names)
            for n in list(ARM_JOINTS) + ["left_finger", "right_finger"]:
                i = names.index(n); gains[f"{a}_{n}"] = {"stiffness": r6(kp[i]), "damping": r6(kd[i])}
        self._robot_spec = {
            "name": "i2rt-yam-bimanual",
            "description": "two I2RT YAM arms (6 revolute joints each, fixed bases on a workstation table) with parallel two-finger "
                           "grippers (two prismatic fingers per arm, the second mirroring the first): YAMLab's bimanual setup (Isaac "
                           "Lab / Isaac Sim 5.1)",
            "base": {"type": "fixed", "link": f"left_{self._model['left'].root}", "pose": pose7(self._model["left"].base_T),
                     "per_arm": {a: {"type": "fixed", "link": f"{a}_{self._model[a].root}", "pose": pose7(self._model[a].base_T)} for a in ARMS},
                     "note": "two fixed-base arms; `pose` is the left arm's, `per_arm` has both"},
            "joints": joints,
            "grippers": {f"{a}_gripper": {
                "joints": [f"{a}_left_finger", f"{a}_right_finger (mirrors {a}_left_finger)"], "finger_travel_m": [FINGER_OPEN, FINGER_CLOSED],
                "command": {"index": GRIP_INDEX[a], "range": [FINGER_OPEN, FINGER_CLOSED], "unit": "m",
                            "rule": f"the position target of {a}_left_finger: {FINGER_OPEN} = fully open .. {FINGER_CLOSED} = closed; "
                                    "the other finger gets the same target (YAMLab mirrors it); a closed gripper stops at the object"},
                "opening_m": [0.0, round(-2 * FINGER_OPEN, 4)], "tcp_frame": f"{a}_tcp"} for a in ARMS},
            "controller": {
                "type": "joint-position PD: PhysX implicit joint drives tracking absolute targets that are held for each control step "
                        "(YAMLab's high_pd gains)",
                "control_hz": round(1.0 / self.control_dt, 6), "physics_hz": round(1.0 / float(self.env.physics_dt), 6), "gains": gains,
                "note": "effort = stiffness * (target - q) + damping * (0 - qdot), clipped to effort_limit; stiffness N m/rad (N/m for the "
                        "fingers), damping N m s/rad (N s/m)"},
            "tcp": {f"{a}_tcp": {"parent_link": f"{a}_{FLANGE_BODY}", "link_T_frame": self._M_tcp[a].tolist(),
                                 "definition": f"the midpoint of the {a} gripper's two fingertips (fixed in {FLANGE_BODY}: the fingers move "
                                               f"symmetrically), with {FLANGE_BODY}'s orientation; ee_pose(), the ee_pose action and the "
                                               "proprio tcp_pose use it"} for a in ARMS}}
        links = [f"{a}_{n}" for a in ARMS for n in self._model[a].links]
        self._kin_spec = {
            "endpoint": "/kinematics", "joint_names": [f"{a}_{j}" for a in ARMS for j in ARM_JOINTS], "frame": "world", "quaternion_order": "wxyz",
            "links": links, "tcp_frames": [f"{a}_tcp" for a in ARMS], "ee_frames": [f"{a}_tcp" for a in ARMS],
            "ik_targets": [f"{a}_{f}" for a in ARMS for f in ("tcp", FLANGE_BODY)],
            "ik": {"solver": "per arm, damped least squares on the model's Jacobian from the seed (then the home pose, then mid-range); "
                             "every step is clamped to the joint limits; an arm without a target keeps its seed", "joints": [f"{a}_{j}" for a in ARMS for j in ARM_JOINTS],
                   "tol_pos_m": 0.001, "tol_rot_rad": 0.01, "max_iters": 300, "default_seed": [0.0] * 12, "collision_checking": "none"},
            "stateless": True,
            "note": "numpy models of both arm chains read from the robots' USD joint frames at startup and checked against the "
                    "simulator's link poses (max error {:.1e} m). Frame names are prefixed with the arm (left_ / right_)".format(
                        max(v["links_max_pos_err_m"] for v in self.kinematics_check.values()))}

    def robot_spec(self) -> dict:
        """The robot's spec sheet: joints with the simulator's limits, the grippers and their command, the controller and its
        gains, the tool frames. Nothing about the scene."""
        self._need_model(); return json.loads(json.dumps(self._robot_spec))

    def kinematics_spec(self) -> dict:
        self._need_model(); return json.loads(json.dumps(self._kin_spec))

    def kinematics(self, req: dict) -> dict:
        """Stateless FK / IK on the numpy models (never reads or changes the simulator):
          {"op": "fk", "q": [12] (left joint1..6, right joint1..6), "links": [...]?} -> {"ok", "op", "frame", "poses": {link: pose7}}
          {"op": "ik", "targets": {frame: pose7}, "seed": [12]?, "tol_pos_m"?, "tol_rot_rad"?, "max_iters"?}
            -> {"ok", "op", "frame", "q": [12], "error": {frame: {"pos_m", "rot_rad"}}}
        Frames: kinematics_spec()["links"] (prefixed left_ / right_); IK targets: kinematics_spec()["ik_targets"]."""
        self._need_model(); ks = self._kin_spec; n = len(ks["joint_names"])
        if not isinstance(req, dict):
            raise ValueError("the request must be a dict")
        if req.get("base_pose") is not None:
            raise ValueError("base_pose is only accepted by a mobile robot (these arms have fixed bases; kinematics frame 'world')")

        def vec(x, what):
            v = None if x is None else np.asarray(x, dtype=np.float64).reshape(-1)
            if v is None or v.size != n or not np.all(np.isfinite(v)):
                raise ValueError(f"{what} must be {n} finite numbers")
            return v

        def tpose(x, what):
            v = None if x is None else np.asarray(x, dtype=np.float64).reshape(-1)
            if v is None or v.size != 7 or not np.all(np.isfinite(v)) or np.linalg.norm(v[3:]) < 1e-6:
                raise ValueError(f"{what} must be [x, y, z, qw, qx, qy, qz] with a non-zero quaternion")
            return pose7_to_T(v)

        def split(name):
            a, _, rest = name.partition("_")
            return a, rest
        if req.get("op") == "fk":
            links = req.get("links") or ks["links"]
            if not isinstance(links, (list, tuple)) or any(k not in ks["links"] for k in links):
                raise ValueError(f"links must be names from {ks['links']}")
            q = vec(req.get("q"), "q")
            T = {a: self._model[a].fk(q[6 * i:6 * i + 6]) for i, a in enumerate(ARMS)}
            return {"ok": True, "op": "fk", "frame": ks["frame"], "poses": {k: pose7(T[split(k)[0]][split(k)[1]]) for k in links}}
        if req.get("op") == "ik":
            tg = req.get("targets")
            if not isinstance(tg, dict) or not tg or any(k not in ks["ik_targets"] for k in tg):
                raise ValueError(f"targets must map frames from {ks['ik_targets']} to poses")
            tol_p = float(req.get("tol_pos_m") or ks["ik"]["tol_pos_m"]); tol_r = float(req.get("tol_rot_rad") or ks["ik"]["tol_rot_rad"])
            it = int(req.get("max_iters") or ks["ik"]["max_iters"])
            if not (1e-5 <= tol_p <= 0.5 and 1e-4 <= tol_r <= 3.2 and 1 <= it <= 5000):
                raise ValueError("tol_pos_m in [1e-5, 0.5], tol_rot_rad in [1e-4, 3.2], max_iters in [1, 5000]")
            seed = np.zeros(n) if req.get("seed") is None else vec(req["seed"], "seed")
            q_out, ok_all, errs_all = seed.copy(), True, {}
            for i, a in enumerate(ARMS):
                t_a = {split(k)[1]: tpose(v, f"targets[{k}]") for k, v in tg.items() if split(k)[0] == a}
                if not t_a:
                    continue
                q, ok, errs = self._model[a].ik(t_a, seed=seed[6 * i:6 * i + 6], tol_p=tol_p, tol_r=tol_r, max_iters=it)
                q_out[6 * i:6 * i + 6] = q; ok_all = ok_all and bool(ok)
                errs_all.update({f"{a}_{k}": {"pos_m": float(e[0]), "rot_rad": float(e[1])} for k, e in errs.items()})
            return {"ok": bool(ok_all), "op": "ik", "frame": ks["frame"], "q": [float(v) for v in q_out], "error": errs_all}
        raise ValueError("op must be 'fk' or 'ik'")

    # ---- differential IK (Isaac Lab's DLS controller on the PhysX Jacobian; closed loop, one update per control step)
    def _ik_setup(self, arm: str) -> None:
        from isaaclab.controllers import DifferentialIKController, DifferentialIKControllerCfg
        cfg = DifferentialIKControllerCfg(command_type="pose", use_relative_mode=False, ik_method="dls")
        art = self.arm[arm]
        body = list(art.body_names).index(FLANGE_BODY)
        self._ik[arm] = {"ctl": DifferentialIKController(cfg, num_envs=1, device=self.device), "body": body,
                         "jac": body - 1 if art.is_fixed_base else body}

    def ik_step(self, arm: str, pos, quat_wxyz) -> np.ndarray:
        """One differential-IK update of `arm` towards the tool-frame pose (pos, quat) in the world frame -> 6 joint targets (rad)."""
        self._need_model()
        if arm not in self._ik:
            self._ik_setup(arm)
        from isaaclab.utils.math import subtract_frame_transforms
        th = self.th; ik = self._ik[arm]; art = self.arm[arm]; ids = self.joint_ids[arm][:6]
        Tt = hom(quat_to_mat(quat_wxyz), pos) @ np.linalg.inv(self._M_tcp[arm])          # tcp target -> link_6 target
        bq = mat_to_quat(Tt[:3, :3]); bp = Tt[:3, 3] + _np(self.env.scene.env_origins)[0]
        jac = _tt(art.root_physx_view.get_jacobians())[:, ik["jac"], :, ids]
        body = _tt(art.data.body_pose_w)[:, ik["body"]]
        root = _tt(art.data.root_pose_w)
        ee_pos_b, ee_quat_b = subtract_frame_transforms(root[:, :3], root[:, 3:7], body[:, :3], body[:, 3:7])
        tgt = th.as_tensor(np.concatenate([bp, bq]), dtype=th.float32, device=self.device).unsqueeze(0)
        tgt_pos_b, tgt_quat_b = subtract_frame_transforms(root[:, :3], root[:, 3:7], tgt[:, :3], tgt[:, 3:7])
        q = art.data.joint_pos[:, ids]
        ik["ctl"].set_command(th.cat([tgt_pos_b, tgt_quat_b], dim=-1))
        q_des = ik["ctl"].compute(ee_pos_b, ee_quat_b, jac, q)
        lo = art.data.soft_joint_pos_limits[0, ids, 0]; hi = art.data.soft_joint_pos_limits[0, ids, 1]
        return th.clamp(q_des[0], lo, hi).detach().cpu().numpy().astype(np.float64)

    # ---- primitives for the agent: deliberately thin wrappers of the low-level action (joint targets, gripper commands,
    # differential-IK moves of one or both arms). Grasping, lifting, handing over and placing are the agent's to build.
    def primitives(self) -> dict[str, Callable]:
        s = self

        def hold(steps: int = 10):
            """Keep the current targets for `steps` control steps. No-op once the episode is over."""
            for _ in range(int(steps)):
                if s.episode_done or s.step(s.hold_action()):
                    break

        def set_joint_targets(targets, steps: int = 1):
            """Command a full 14-vector (see ACTION_LAYOUT) for `steps` control steps (no interpolation)."""
            for _ in range(int(steps)):
                if s.episode_done or s.step(targets):
                    break

        def set_gripper(arm: str, closed: float, steps: int = 20, ramp: int = 10):
            """Command `arm`'s gripper: `closed` in [0, 1] (0 = fully open, 1 = closed; the finger target is interpolated
            between -0.0475 and 0.0 m) over `ramp` control steps, then hold until `steps` steps have passed."""
            if s.episode_done:
                return
            t0 = s.hold_action(); g1 = FINGER_OPEN + (FINGER_CLOSED - FINGER_OPEN) * float(np.clip(closed, 0.0, 1.0))
            g0 = t0[GRIP_INDEX[arm]]
            for i in range(1, max(int(steps), 1) + 1):
                t = s.hold_action(); t[GRIP_INDEX[arm]] = g0 + (g1 - g0) * min(1.0, i / max(1, int(ramp)))
                if s.step(t):
                    break

        def open_gripper(arm: str, steps: int = 20):
            set_gripper(arm, 0.0, steps)

        def close_gripper(arm: str, steps: int = 20):
            set_gripper(arm, 1.0, steps)

        def move_joints(left=None, right=None, *, max_dq: float = 0.03, steps: int | None = None, settle: int = 0):
            """Interpolate the joint targets of one or both arms (6 values each, rad; None keeps an arm) linearly from the
            current targets, at most `max_dq` rad per control step (or exactly `steps` steps), then hold `settle` steps."""
            if s.episode_done:
                return
            cur = s.hold_action(); goal = cur.copy()
            for a, q in (("left", left), ("right", right)):
                if q is not None:
                    goal[ARM_SLICE[a]] = np.asarray(q, dtype=np.float64).reshape(6)
            n = int(steps) if steps else max(2, int(math.ceil(float(np.max(np.abs(goal - cur))) / max_dq)))
            for i in range(1, n + 1):
                if s.step(cur + (goal - cur) * (i / n)):
                    return
            for _ in range(int(settle)):
                if s.step(goal):
                    return

        def move_ee(left=None, right=None, *, speed: float = 0.15, max_dq: float = 0.05, tol: float = 0.005, rot_tol: float = 0.05,
                    max_steps: int = 300, settle: int = 0):
            """Move the tool frame of one or both arms (left / right = (pos, quat_wxyz) or (pos, None) to keep the current
            orientation; None keeps an arm still) along straight lines at `speed` m/s, together: every control step one
            differential-IK update per moving arm towards its moving waypoint (joint change clamped to `max_dq` rad/step),
            until every target is within `tol` m / `rot_tol` rad, then hold `settle` steps. Raises PrimitiveError if
            `max_steps` pass without converging. Returns {arm: final position error (m)}."""
            if s.episode_done:
                return None
            goals = {}
            for a, tgt in (("left", left), ("right", right)):
                if tgt is None:
                    continue
                p0, q0 = s.ee_pose(a)
                p1 = np.asarray(tgt[0], dtype=np.float64); q1 = np.asarray(tgt[1] if tgt[1] is not None else q0, dtype=np.float64)
                goals[a] = (p0, p1, q1, max(1, int(math.ceil(float(np.linalg.norm(p1 - p0)) / (speed * s.control_dt)))))
            if not goals:
                return {}
            n_way = max(g[3] for g in goals.values())
            for i in range(int(max_steps)):
                a14 = s.hold_action()
                for a, (p0, p1, q1, _n) in goals.items():
                    wp = p1 if i >= n_way else p0 + (p1 - p0) * ((i + 1) / n_way)
                    q_des = s.ik_step(a, wp, q1)
                    cur = a14[ARM_SLICE[a]]
                    a14[ARM_SLICE[a]] = cur + np.clip(q_des - cur, -max_dq, max_dq)
                if s.step(a14):
                    return None
                errs = {}
                for a, (_p0, p1, q1, _n) in goals.items():
                    pe, qe = s.ee_pose(a); errs[a] = (float(np.linalg.norm(pe - p1)), quat_angle(qe, q1))
                if i >= n_way and all(e[0] < tol and e[1] < rot_tol for e in errs.values()):
                    for _ in range(int(settle)):
                        if s.step(s.hold_action()):
                            break
                    return {a: e[0] for a, e in errs.items()}
            if s.episode_done:
                return None
            raise PrimitiveError("move_ee did not converge in %d steps: %s" % (max_steps, {a: f"{e[0] * 1000:.1f} mm / {math.degrees(e[1]):.1f} deg" for a, e in errs.items()}))

        return {"hold": hold, "set_joint_targets": set_joint_targets, "set_gripper": set_gripper, "open_gripper": open_gripper,
                "close_gripper": close_gripper, "move_joints": move_joints, "move_ee": move_ee, "ik_step": s.ik_step,
                "get_object_pose": s.object_pose, "get_object_bounds": s.object_bounds, "get_object_points": s.object_points,
                "get_ee_pose": s.ee_pose, "get_joint_targets": s.hold_action}

    def exec_code(self, code: str, extra: dict | None = None) -> dict[str, Any]:
        """Run agent/oracle code with the primitives in scope (also: session, np, math, PrimitiveError, the quaternion helpers)."""
        g: dict[str, Any] = {"__name__": "__main__", "np": np, "math": math, "session": self, "objects": self.objects,
                             "TASK": dict(self.spec), "PrimitiveError": PrimitiveError, "quat_to_mat": quat_to_mat, "mat_to_quat": mat_to_quat,
                             "quat_mul": quat_mul, "quat_inv": quat_inv, "quat_from_axis_angle": quat_from_axis_angle, "wrap_angle": wrap_angle,
                             **self.primitives(), **(extra or {})}
        try:
            exec(code, g, g)
            return {"ok": True}
        except BaseException as exc:  # noqa: BLE001
            import traceback
            traceback.print_exc(file=sys.stderr)
            return {"ok": False, "error": repr(exc)[:300]}

    def _log_end(self) -> None:
        if not self._end_logged:
            self._end_logged = True
            _slog("session_end", task=self.task, resets=self._resets, sim_steps=self._total_steps + self.n_steps)

    def close(self) -> None:
        self._log_end()
        try:
            self.env.close()
        except Exception as exc:  # noqa: BLE001
            _log("env.close:", repr(exc)[:120])
        try:
            if _APP is not None:
                _APP.close()
        except Exception as exc:  # noqa: BLE001
            _log("app.close:", repr(exc)[:120])


# --------------------------------------------------------------------------- CLI
def _load_traj(path: str) -> dict[str, Any]:
    """The trajectory file's entries. A replay needs `actions` and `task` only: any other entry that cannot be read
    without pickle (an object array somebody added) is skipped, it never stops the replay."""
    d = np.load(path, allow_pickle=False)
    out: dict[str, Any] = {}
    for k in d.files:
        try:
            v = d[k]
        except Exception:  # noqa: BLE001
            if k in ("actions", "task"):
                raise
            continue
        out[k] = v.item() if v.shape == () else v
    return out


def _video_every(n_actions: int, fps: int) -> int:
    """Control steps per video frame for the `replay` CLI: real time (CONTROL_HZ / fps) up to MAX_VIDEO_FRAMES frames,
    a time lapse beyond."""
    return max(1, CONTROL_HZ // max(1, int(fps)), math.ceil(int(n_actions) / MAX_VIDEO_FRAMES))


def _versions() -> dict:
    out = {}
    for mod in ("isaaclab", "isaacsim", "torch"):
        try:
            m = __import__(mod); out[mod] = str(getattr(m, "__version__", ""))
        except Exception:  # noqa: BLE001
            pass
    for name, path in (("yamlab_commit", YAMLAB_ROOT), ("isaaclab_commit", Path("/opt/IsaacLab"))):
        try:
            out[name] = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10).stdout.strip()[:12]
        except Exception:  # noqa: BLE001
            pass
    return out


def _h5_tree(g, idx: int | None = None) -> dict:
    import h5py
    out = {}
    for k in sorted(g.keys()):
        v = g[k]
        if isinstance(v, h5py.Group):
            out[k] = _h5_tree(v, idx)
        else:
            arr = np.asarray(v[0] if idx is None else v[idx], dtype=np.float32)
            out[k] = arr.tolist()
    return out


def cmd_make_instance(a) -> None:
    """Instance + oracle from one human teleoperation demonstration of YAMLab's dataset: the instance is the demo's recorded
    initial state (YAMLab's reset: both arms at the home pose, joints 0 and grippers open, both objects as placed for that
    demo); the oracle is a RAMP-step linear move from the home targets to the demo's first action, then the demo's recorded
    actions. Writes instance.json (state + hash) and, with --oracle-out, the (T, 14) oracle actions."""
    import h5py
    with h5py.File(a.dataset, "r") as h:
        d = h["data"]; at = d.attrs["ASSETS_INSTANCE_PATHS"]
        assets = json.loads(at.decode() if isinstance(at, bytes) else at)
        g = d[f"demo_{a.demo}"]
        state = _h5_tree(g["initial_state"])
        acts = np.asarray(g["actions"][:], dtype=np.float32)
    s = Session(a.task, assets=assets, depth=False)
    s._restore(state)
    s.initial_state = s._tree_to_lists(s.env.scene.get_state(is_relative=True)); s.instance_sha = s.state_sha()
    home = s._current_targets().astype(np.float32)
    ramp = np.stack([home + (acts[0] - home) * (k / a.ramp) for k in range(1, a.ramp + 1)]).astype(np.float32)
    oracle = np.concatenate([ramp, acts])
    out = {"task": a.task, "yamlab_env": s.spec["env"], "assets": assets, "text": s.spec["text"], "stages": list(s.spec["stages"]),
           "initial_state": s.initial_state, "state_sha": s.instance_sha, "action_dim": ACTION_DIM, "control_hz": CONTROL_HZ,
           "sim_dt": float(s.env.physics_dt), "decimation": int(s.env.cfg.decimation), "physics": {"device": "cpu"},
           "robot_joint_positions": {arm: [round(float(x), 6) for x in s.joint_positions(arm)] for arm in ARMS},
           "objects": s.objects(), "success_params": s.success_params(), "table_top_z": None,
           # no provenance here: the instance is in the agent's container, and where its scene came from is the address
           # of a solution (PROTOCOL §2.7); the maintainers' record is scripts/yamlab/instances.json
           "versions": _versions()}
    try:
        from yamlab.robot.yam import ROBOT
        out["table_top_z"] = float(ROBOT.table_position[2])
    except Exception:  # noqa: BLE001
        pass
    Path(a.out).write_text(json.dumps(out, indent=1))
    if a.oracle_out:
        np.save(a.oracle_out, oracle)
    print(json.dumps({"instance": a.out, "state_sha": s.instance_sha, "assets": assets, "n_demo_actions": int(len(acts)),
                      "n_oracle_actions": int(len(oracle))}), flush=True)
    s.close()


def cmd_run_actions(a) -> None:
    """Execute pre-recorded actions on the frozen instance in this fresh process (stopping at the first success) and save
    the rows that ran as the trajectory."""
    s = Session(a.task, instance=a.instance, strict=True, depth=False)
    acts = np.load(a.actions).astype(np.float32)
    t0 = time.time()
    s.record_start()
    for row in acts:
        if s.step(row):
            break
    rec = s.record_stop()
    st = s.status()
    s.save_trajectory(rec, a.out, meta={"source": a.source, "wall_s": round(time.time() - t0, 1)})
    print(json.dumps({"traj": a.out, "n_actions": int(len(rec)), **st, "wall_s": round(time.time() - t0, 1)}), flush=True)
    s.close()


def cmd_replay(a) -> None:
    traj = _load_traj(a.traj)
    if str(traj.get("task")) != a.task:
        print(json.dumps({"error": f"trajectory task {traj.get('task')} != {a.task}"}), flush=True); sys.exit(2)
    s = Session(a.task, instance=a.instance, strict=a.strict, depth=False)
    acts = np.asarray(traj["actions"], dtype=np.float32)
    t0 = time.time()
    outs = []; video_ok = None
    for i in range(a.repeat):
        if a.video and i == 0:
            # the video shows the first (fresh-process-exact) replay. It never decides the replay: a video that cannot be
            # started, filmed or encoded is reported (`video_ok` false) and the replay's result stands.
            s.reset(); s._resets -= 1
            filming = False
            try:
                s.start_video(a.video, fps=a.fps, every=_video_every(len(acts), a.fps)); filming = True
            except Exception as exc:  # noqa: BLE001
                s._video = None; video_ok = False; _log("video: not started:", repr(exc)[:200])
            for row in acts:
                if s.step(row):
                    break
            if filming:
                try:
                    video_ok = s.stop_video() is not None
                except Exception as exc:  # noqa: BLE001
                    video_ok = False; _log("video: not written:", repr(exc)[:200])
            outs.append(s.status())
        else:
            outs.append(s.replay(acts))
    out = {"n_actions": int(len(acts)), "instance_sha": s.instance_sha, "instance_matches": s.instance_matches,
           "instance_exact": s.instance_exact, "replays": outs, "all_success": all(o["success"] for o in outs),
           "deterministic": len({o["state_sha"] for o in outs}) == 1, "wall_s": round(time.time() - t0, 1), "video": a.video,
           "video_ok": video_ok}
    print(json.dumps(out), flush=True)
    s.close()


def cmd_render(a) -> None:
    s = Session(a.task, instance=a.instance, depth=False)
    print(json.dumps(s.render_video(_load_traj(a.traj)["actions"], a.out, every=a.every, fps=a.fps)), flush=True)
    s.close()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("make-instance"); q.add_argument("--task", required=True); q.add_argument("--dataset", required=True)
    q.add_argument("--demo", type=int, default=0); q.add_argument("--out", required=True); q.add_argument("--oracle-out", default=None)
    q.add_argument("--ramp", type=int, default=30, help="control steps from the home targets to the demo's first action")
    q.set_defaults(fn=cmd_make_instance)
    q = sub.add_parser("run-actions"); q.add_argument("--task", required=True); q.add_argument("--instance", required=True)
    q.add_argument("--actions", required=True); q.add_argument("--out", required=True); q.add_argument("--source", default="pre-recorded actions")
    q.set_defaults(fn=cmd_run_actions)
    q = sub.add_parser("replay"); q.add_argument("--task", required=True); q.add_argument("--instance", required=True); q.add_argument("--traj", required=True)
    q.add_argument("--repeat", type=int, default=1, help="in-process repeats; only the first is fresh-process exact"); q.add_argument("--video", default=None)
    q.add_argument("--fps", type=int, default=15)
    q.add_argument("--strict", action="store_true", help="fail if the rebuilt frozen scene does not match instance.json (poses within tolerance)")
    q.set_defaults(fn=cmd_replay)
    q = sub.add_parser("render"); q.add_argument("--task", required=True); q.add_argument("--instance", required=True); q.add_argument("--traj", required=True)
    q.add_argument("--out", required=True); q.add_argument("--every", type=int, default=2); q.add_argument("--fps", type=int, default=15)
    q.set_defaults(fn=cmd_render)
    a = p.parse_args(); a.fn(a)


if __name__ == "__main__":
    main()
