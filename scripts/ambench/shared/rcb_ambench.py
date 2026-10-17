"""
rcb_ambench.py — task-local tooling for AM-Bench (github.com/ambench/ambench @ 60bf5b7, Apache-2.0: aerial manipulation on
Isaac Lab / Isaac Sim 5.1): frozen task instance, privileged state, action recording, fresh-process replay. Same shape as
the other benchmarks' rcb_<bench>.py.

Concepts
--------
instance   : one AM-Bench environment (a task with one robot and controller profile, e.g.
             PressButton-Am-FAHexa-Abs-PID-Direct-v0) and the seed of its reset (instance.json). AM-Bench draws the task's
             variation (where the button, the slider, the valve or the ball is) from the seeded reset; `initial_sha` is the
             hash of the start it builds, which every replay checks (`instance_matches`).
trajectory : the (T, 8) actions handed to the environment, one row per control step (120 Hz: one physics step of 1/120 s):
             the absolute end-effector target, position x y z (m, world frame, relative to the environment's origin),
             orientation as a unit quaternion w x y z, and the gripper command (-1 = closed .. +1 = open). AM-Bench's own
             low-level controller (the profile's PID) and floating-base inverse kinematics turn it into rotor thrusts and arm
             joint targets inside every step. Physics is PhysX on the GPU: a fresh process replays the same rows to the
             same state (the first episode of a process; later resets in the same process need not be bit-identical).
             Two things make that hold (both measured): the controller's IK solve is synchronized with the GPU (SYNC,
             sync_ik), and the onboard cameras are never rendered in the physics process (CAMERAS, Renderer: a second,
             render-only Isaac process draws them from the physics state).
success    : AM-Bench's own `_get_success` of the task (its `terminated` signal); the episode ends at the first control step
             where it holds, or at the task's episode length (a time-out, not a success). Rows after the end never run.
             Isaac Lab resets the scene inside the step that ends an episode; the tooling keeps the end state's hash
             (taken just before that reset) as the episode's `state_sha`.
             RotateValve: the valve's `base_to_shaft` joint has no limits, and PhysX reports an articulation's unlimited
             revolute joint wrapped into [-pi, pi] (omni.physx 107.3, Isaac Sim 5.1), so AM-Bench's check `joint_pos >=
             17/18 pi` would also pass a counter-clockwise turn of 190 degrees. The tooling gives that task's
             `_get_success` the unwrapped angle instead: the sum of the joint's per-step changes since the reset (one
             physics step moves it at most 5 rad/s / 120 Hz, far less than pi), so only the clockwise turn the
             instruction asks for counts. Physics, states and hashes are unchanged; the episode just does not end on a
             wrapped reading.

CLI
---
  python rcb_ambench.py replay --instance instance.json --traj traj.npz      # one fresh-process replay (the grader's, no cameras)
  python rcb_ambench.py film --instance instance.json --traj traj.npz --video replay.mp4   # the same rows, filmed (both cameras)
  python rcb_ambench.py make-instance --env-id <id> --seed 0 --out instance.json
  python rcb_ambench.py run-actions --instance instance.json --actions actions.npy --out traj.npz
"""
from __future__ import annotations

import os
for _k, _v in (("OMNI_KIT_ACCEPT_EULA", "YES"), ("ACCEPT_EULA", "Y"), ("OMNI_KIT_ALLOW_ROOT", "1"), ("PYTHONUNBUFFERED", "1"),
               ("JAX_PLATFORMS", "cpu")):
    os.environ.setdefault(_k, _v)

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

ACTION_DIM = 8
CONTROL_HZ = 120
MAX_STEPS = 8000                       # a technical cap above every task's episode length (at most 60 s = 7200 steps)
QUAT_MIN_NORM = 1e-9                   # a row's quaternion (qw qx qy qz) must be longer than this: AM-Bench cannot use it


class BadTrajectory(ValueError):
    """The rows themselves are not a trajectory of this task (the agent's input, never the simulator's failure)."""


def bad_quaternion_rows(A) -> int:
    """How many rows of a (T, 8) array have a quaternion of zero (< QUAT_MIN_NORM) or non-finite length."""
    q = np.asarray(A, dtype=np.float64).reshape(-1, ACTION_DIM)[:, 3:7]
    with np.errstate(over="ignore", invalid="ignore"):
        n = np.linalg.norm(q, axis=1)
    return int(np.count_nonzero(~np.isfinite(n) | (n < QUAT_MIN_NORM)))
ASSET_ROOT = "/opt/isaac-assets/Assets/Isaac/5.1"   # baked web assets (images/ambench/web_assets.txt)
CAMERAS = ("ee_camera", "base_camera")  # the robot profile's onboard cameras (384 x 384 RGB), only with Session(cameras=True)
SESSION_LOG = os.environ.get("RCB_SESSION_LOG", "/app/output/rcb_session_log.jsonl")
_APP = None
_APP_CAMERAS = False


def _slog(ev: str, **kw) -> None:
    if not SESSION_LOG:
        return
    try:
        os.makedirs(os.path.dirname(SESSION_LOG) or ".", exist_ok=True)
        with open(SESSION_LOG, "a") as f:
            f.write(json.dumps({"ev": ev, "t": round(time.time(), 3), "pid": os.getpid(), **kw}) + "\n")
    except OSError:
        pass


def _launch_app(cameras: bool = False):
    """Isaac Sim, headless, the asset root pointed at the baked copies (no network needed); rendering only with cameras.
    Once per process: the first Session decides."""
    global _APP, _APP_CAMERAS
    if _APP is not None and cameras != _APP_CAMERAS:
        raise RuntimeError(f"this process launched Isaac Sim with cameras={_APP_CAMERAS}: one Session (one setting) per process")
    if _APP is None:
        _APP_CAMERAS = cameras
        from isaaclab.app import AppLauncher
        ns = argparse.Namespace()
        p = argparse.ArgumentParser(); AppLauncher.add_app_launcher_args(p)
        ns = p.parse_args([])
        ns.headless = True; ns.enable_cameras = bool(cameras); ns.device = "cuda:0"
        ns.kit_args = f"--/persistent/isaac/asset_root/cloud={ASSET_ROOT}"
        _APP = AppLauncher(ns).app
    return _APP


def sync_ik(env, torch) -> None:
    """SYNC. AM-Bench's controller solves its floating-base IK on the CPU (Pyroki / jaxls) from GPU tensors and hands the
    result back to the GPU inside every step. Measured: without a device synchronization around that solve, fresh processes
    replaying identical rows part (OpenDoor: three different end states over twelve replays, from step 1 or later); with
    it, every replay is identical. So the solve is wrapped in torch.cuda.synchronize() on both sides (no change to what it
    computes)."""
    ikc = getattr(getattr(env, "control_pipeline", None), "ik_controller", None)
    if ikc is None or getattr(ikc, "_rcb_synced", False):
        return
    compute = ikc.compute

    def synced(*args, **kw):
        torch.cuda.synchronize()
        out = compute(*args, **kw)
        torch.cuda.synchronize()
        return out
    ikc.compute = synced; ikc._rcb_synced = True


DEPTH_TYPE = "distance_to_image_plane"   # z-depth (distance from the camera plane along the optical axis), metres
DEPTH_MAX_M = 65.535                     # standard mode's uint16-millimetre depth: a farther surface reads 0 (no reading)
GL2CV = np.diag([1.0, -1.0, -1.0, 1.0])  # OpenGL camera axes (x right, y up, z back) -> OpenCV (x right, y down, z forward)
# standard-mode proprio: (group, columns) in order; the column names are proprio_layout()
PROPRIO_ORDER = ("joint_pos", "joint_vel", "tcp_pose", "gripper_opening", "gripper_cmd", "joint_effort", "base_pose", "base_vel", "ee_cmd")


# --------------------------------------------------------------------------- small rigid-body helpers (numpy, wxyz)
def hom(R=None, p=None) -> np.ndarray:
    T = np.eye(4)
    if R is not None:
        T[:3, :3] = R
    if p is not None:
        T[:3, 3] = np.asarray(p, dtype=np.float64).reshape(3)
    return T


def quat_to_mat(q) -> np.ndarray:
    w, x, y, z = (float(v) for v in np.asarray(q, dtype=np.float64).reshape(4) / max(1e-12, float(np.linalg.norm(q))))
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def mat_to_quat(R) -> np.ndarray:
    R = np.asarray(R, dtype=np.float64); tr = float(np.trace(R))
    if tr > 0:
        s = 2.0 * np.sqrt(tr + 1.0); q = [0.25 * s, (R[2, 1] - R[1, 2]) / s, (R[0, 2] - R[2, 0]) / s, (R[1, 0] - R[0, 1]) / s]
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = 2.0 * np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]); q = [(R[2, 1] - R[1, 2]) / s, 0.25 * s, (R[0, 1] + R[1, 0]) / s, (R[0, 2] + R[2, 0]) / s]
    elif R[1, 1] > R[2, 2]:
        s = 2.0 * np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]); q = [(R[0, 2] - R[2, 0]) / s, (R[0, 1] + R[1, 0]) / s, 0.25 * s, (R[1, 2] + R[2, 1]) / s]
    else:
        s = 2.0 * np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]); q = [(R[1, 0] - R[0, 1]) / s, (R[0, 2] + R[2, 0]) / s, (R[1, 2] + R[2, 1]) / s, 0.25 * s]
    q = np.asarray(q); q = q / np.linalg.norm(q)
    return q if q[0] >= 0 else -q


def pose7(T) -> list[float]:
    T = np.asarray(T, dtype=np.float64)
    return [float(v) for v in T[:3, 3]] + [float(v) for v in mat_to_quat(T[:3, :3])]


def pose7_to_T(p) -> np.ndarray:
    p = np.asarray(p, dtype=np.float64).reshape(7)
    return hom(quat_to_mat(p[3:]), p[:3])


def axis_rot(axis, a: float) -> np.ndarray:
    k = np.asarray(axis, dtype=np.float64); k = k / np.linalg.norm(k)
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + np.sin(a) * K + (1 - np.cos(a)) * (K @ K)


def rotvec(R) -> np.ndarray:
    c = max(-1.0, min(1.0, (float(np.trace(R)) - 1.0) / 2.0)); ang = float(np.arccos(c))
    if ang < 1e-9:
        return np.zeros(3)
    v = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]])
    n = float(np.linalg.norm(v))
    if n < 1e-9:                                   # ~180 degrees: the axis from the symmetric part
        w, V = np.linalg.eigh((R + np.eye(3)) / 2.0); return V[:, int(np.argmax(w))] * ang
    return v / n * ang


def rot_angle(R1, R2) -> float:
    return float(np.linalg.norm(rotvec(np.asarray(R1) @ np.asarray(R2).T)))


class ChainModel:
    """Stateless kinematics of the arm on the airframe, in numpy (no simulator call): the chain of joints from `base_link`
    to `ee_link` read from the robot's USD joint frames (child = parent . A . Rot(axis, q) . B^-1; fixed joints have no
    axis), poses relative to `base_link` (a base pose turns them into world poses). FK, the geometric Jacobian, and a
    damped-least-squares IK that starts from the seed (then the home pose, then mid-range) and clamps every step to the
    joint limits."""

    def __init__(self, root: str, chain: list, lo, hi, home, extra: dict | None = None):
        self.root, self.chain = root, chain       # chain: (name, kind, parent, child, A, axis | None, Binv)
        self.lo, self.hi, self.home = (np.asarray(x, dtype=np.float64) for x in (lo, hi, home))
        self.extra = dict(extra or {})            # named frames fixed in a chain link: {name: (parent link, 4x4)}
        self.links = [root] + [c[3] for c in chain] + list(self.extra)
        self.n = sum(1 for c in chain if c[1] == "revolute")

    def _fk(self, q, base_T=None):
        T = {self.root: np.eye(4) if base_T is None else np.asarray(base_T, dtype=np.float64)}; P, Ax, owner = [], [], {}
        i = 0
        for name, kind, parent, child, A, axis, Binv in self.chain:
            J = T[parent] @ A
            if kind == "revolute":
                P.append(J[:3, 3].copy()); Ax.append(J[:3, :3] @ axis)
                T[child] = J @ hom(axis_rot(axis, float(q[i]))) @ Binv; i += 1
            else:
                T[child] = J @ Binv
            owner[child] = i
        for name, (parent, M) in self.extra.items():
            T[name] = T[parent] @ M; owner[name] = owner.get(parent, 0)
        return T, P, Ax, owner

    def fk(self, q, base_T=None) -> dict[str, np.ndarray]:
        return self._fk(np.asarray(q, dtype=np.float64).reshape(-1), base_T)[0]

    def ik(self, targets: dict, seed=None, base_T=None, tol_p: float = 1e-3, tol_r: float = 1e-2, max_iters: int = 300,
           lam: float = 0.05, max_step: float = 0.25):
        """targets {frame: 4x4} (in the base frame, or the world when base_T is given) -> (q, ok, {frame: (pos err m,
        rot err rad)}) of the best q found. Four joints cannot reach every 6-D pose: errors are reported, never hidden."""
        best = None
        seeds = ([np.asarray(seed, dtype=np.float64).reshape(-1)] if seed is not None else []) + [self.home, (self.lo + self.hi) / 2.0]
        for s0 in seeds:
            q = np.clip(s0, self.lo, self.hi)
            for _ in range(int(max_iters)):
                T, P, Ax, owner = self._fk(q, base_T)
                es, Js, errs = [], [], {}
                for f, Tt in targets.items():
                    ep = Tt[:3, 3] - T[f][:3, 3]; er = rotvec(Tt[:3, :3] @ T[f][:3, :3].T)
                    errs[f] = (float(np.linalg.norm(ep)), float(np.linalg.norm(er)))
                    J = np.zeros((6, self.n)); pf = T[f][:3, 3]
                    for k in range(owner[f]):
                        J[:3, k] = np.cross(Ax[k], pf - P[k]); J[3:, k] = Ax[k]
                    es += [ep, er]; Js.append(J)
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


def sync_phases(env, torch) -> None:
    """SYNC, continued. Synchronizing around the IK solve alone left another race (measured on CabinetPickPlace: fresh
    replays of the same rows ended in two different states; with CUDA_LAUNCH_BLOCKING=1 every replay was identical, at a
    3.8x slowdown). So every phase of a control step is also bracketed by a device synchronization: the environment's
    pre-physics step, the action's application, the writes to PhysX, the physics step, the buffers' update, the dones,
    rewards, resets and observations. Nothing they compute changes; only their ordering against the GPU is fixed."""
    if getattr(env, "_rcb_sync_phases", False):
        return

    def wrap(obj, name):
        fn = getattr(obj, name, None)
        if fn is None:
            return

        def synced(*args, **kw):
            torch.cuda.synchronize()
            out = fn(*args, **kw)
            torch.cuda.synchronize()
            return out
        setattr(obj, name, synced)
    for name in ("_pre_physics_step", "_apply_action", "_get_dones", "_get_rewards", "_reset_idx", "_get_observations"):
        wrap(env, name)
    for name in ("write_data_to_sim", "update"):
        wrap(env.scene, name)
    wrap(env.sim, "step")
    env._rcb_sync_phases = True


# GPU faults in an Isaac process's output (its stderr): PhysX kernels that could not be launched and CUDA allocations that
# failed, both from a GPU out of memory or resources (measured on a shared GPU: PegInHole's frozen rows ended 7f8ce9f9,
# not the frozen 88054491, in the one replay of 25 that logged them). PhysX goes on stepping without the failed kernels,
# so that run's physics is not the trajectory's: a replay with any is no result (the graders run it once more, then
# report an infrastructure error). Errors that a trajectory itself can cause (non-finite forces) are not in the list.
GPU_FAULT = r"PhysX error: GPU \S+ fail to launch|CUDA error|out of memory|Unable to allocate memory|CUBLAS_STATUS_ALLOC_FAILED|Failed to fetch DOF"


def count_gpu_faults(text: str) -> int:
    """The number of output lines that report a GPU fault."""
    import re
    pat = re.compile(GPU_FAULT)
    return sum(1 for line in (text or "").splitlines() if pat.search(line))

class _SyncedView:
    """A PhysX tensor view (Isaac Lab's root / body / contact view of an asset) whose getters and setters are bracketed by
    a device synchronization; everything else passes through unchanged."""
    def __init__(self, view, torch):
        object.__setattr__(self, "_v", view); object.__setattr__(self, "_t", torch)

    def __getattr__(self, name):
        a = getattr(self._v, name)
        if callable(a) and name.startswith(("get_", "set_", "apply_")):
            t = self._t

            def synced(*args, **kw):
                t.cuda.synchronize()
                out = a(*args, **kw)
                t.cuda.synchronize()
                return out
            return synced
        return a


def sync_views(env, torch) -> int:
    """SYNC, last part. With the IK and every phase of a step synchronized (above), fresh replays still parted now and then
    on a loaded host (measured on OpenDoor's frozen rows, load average 50-76 on 32 cores: one of four plain replays, two
    of three Harbor runs ended in another state): inside a phase, PhysX's tensor views copy state out of and targets into
    GPU buffers that Isaac Lab's torch kernels use right away. So every get_* / set_* / apply_* call on those views is
    bracketed by a device synchronization too (with it: eight of eight replays identical, the frozen end state). Returns
    the number of views wrapped. Nothing they compute changes; only their ordering against the GPU is fixed."""
    n = 0
    sc = env.scene
    for group in (sc.articulations, sc.rigid_objects, getattr(sc, "rigid_object_collections", None) or {}, sc.sensors):
        for asset in group.values():
            for attr in ("_root_physx_view", "_body_physx_view", "_contact_physx_view"):
                v = getattr(asset, attr, None)
                if v is None or isinstance(v, _SyncedView):
                    continue
                sv = _SyncedView(v, torch)
                setattr(asset, attr, sv); n += 1
                data = getattr(asset, "_data", None)        # ArticulationData / RigidObjectData keep their own reference
                if data is not None and hasattr(data, attr):
                    setattr(data, attr, sv)
    return n


def still_propellers(env) -> bool:
    """PROPELLERS. AM-Bench animates the propellers for the cameras: every step it writes their new orientations into the
    robot's USD prims (robot_io's PropAnimation). Writing USD under the articulation while PhysX runs is a timing-dependent
    input to the simulation (measured: with it, fresh replays of OpenDoor's rows still parted now and then). It is purely
    visual, so the tooling switches it off: the propellers stand still in the images, everything else is unchanged."""
    anim = getattr(getattr(env, "robot_io", None), "_propeller_animation", None)
    if anim is None:
        return False
    anim.update = lambda *args, **kw: None
    return True


VISUAL_ONLY_EVENTS = ("randomize_visual_color", "randomize_visual_texture_material")


def drop_visual_randomization(cfg) -> list[str]:
    """Remove the event terms that only re-colour or re-texture objects (Isaac Lab's randomize_visual_color /
    randomize_visual_texture_material: PullLever re-colours its lever and tip at every reset). They call a Replicator API
    (rep.functional.get) that Isaac Sim 5.1's Replicator does not have, so the scene could not be built with them; they
    change no physics, only colours, which then stay the asset's own."""
    ev = getattr(cfg, "events", None)
    dropped = []
    if ev is None:
        return dropped
    for name in list(vars(ev)):
        func = getattr(getattr(ev, name), "func", None)
        if getattr(func, "__name__", "") in VISUAL_ONLY_EVENTS:
            setattr(ev, name, None); dropped.append(name)
    return dropped


# --------------------------------------------------------------------------- the render worker (cameras without touching physics)
def _send(fd: int, obj) -> None:
    import pickle
    data = pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)
    os.write(fd, len(data).to_bytes(8, "little"))
    view = memoryview(data)
    while view:
        n = os.write(fd, view); view = view[n:]


def _recv(fd: int):
    import pickle

    def read(n: int) -> bytes:
        buf = bytearray()
        while len(buf) < n:
            chunk = os.read(fd, n - len(buf))
            if not chunk:
                raise EOFError("the other process closed the pipe")
            buf += chunk
        return bytes(buf)
    return pickle.loads(read(int.from_bytes(read(8), "little")))


class Renderer:
    """CAMERAS. The robot's onboard cameras are rendered by a SECOND Isaac process (this file's `render-worker` command) that
    builds the same scene with the cameras, never steps it, and draws the states the physics process sends it (every
    articulation's and rigid object's root state and joint state, plus task state that only shows: WipeWindow's wiped
    stains). Measured: rendering inside the physics process (Isaac renders after every physics step when cameras exist)
    makes AM-Bench's GPU physics timing-dependent, so a run with cameras would not replay; this way the physics process is
    the same with or without cameras and every replay of it reproduces it."""

    def __init__(self, instance: dict, depth: bool = False):
        self.instance, self.depth, self.info = instance, depth, None
        self._start()

    def _start(self) -> None:
        import subprocess
        r_req, w_req = os.pipe(); r_rep, w_rep = os.pipe()
        self.proc = subprocess.Popen([sys.executable, os.path.abspath(__file__), "render-worker", "--instance-json", json.dumps(self.instance),
                                      "--rfd", str(r_req), "--wfd", str(w_rep)] + (["--depth"] if self.depth else []),
                                     pass_fds=(r_req, w_rep), stdout=subprocess.DEVNULL, env={**os.environ, "RCB_SESSION_LOG": ""},
                                     # RCB_RENDER_LOG: the worker's own log (the standard service), so that its messages are
                                     # never counted as the physics process's GPU faults
                                     stderr=open(os.environ["RCB_RENDER_LOG"], "ab") if os.environ.get("RCB_RENDER_LOG") else None)
        os.close(r_req); os.close(w_rep)
        self.w, self.r = w_req, r_rep

    def ready(self) -> dict:
        """Waits until the worker has built its scene: {cam: K, size, range, link, link_T_cv}. A worker that fails to build
        (Isaac's GPU initialisation can fail on a crowded GPU) is started once more."""
        if self.info is None:
            for attempt in (1, 2):
                try:
                    msg = _recv(self.r)
                except EOFError:
                    msg = {"error": "the render worker exited"}
                if "error" not in msg:
                    self.info = msg["cams"]; break
                print(f"[rcb_ambench] render worker failed to start (attempt {attempt}): {msg['error'][:300]}", file=sys.stderr, flush=True)
                if attempt == 2:
                    raise RuntimeError(f"the render worker failed: {msg['error']}")
                try:
                    self.proc.kill()
                except Exception:  # noqa: BLE001
                    pass
                self._start()
        return self.info

    def render(self, snapshot: dict, cams: list[str], depth: bool) -> tuple[dict, dict]:
        self.ready()
        _send(self.w, {"op": "render", "snapshot": snapshot, "cams": list(cams), "depth": bool(depth)})
        msg = _recv(self.r)
        if "error" in msg:
            raise RuntimeError(f"the render worker failed: {msg['error']}")
        return msg["frames"], msg.get("depth", {})

    def close(self) -> None:
        try:
            _send(self.w, {"op": "close"})
        except Exception:  # noqa: BLE001
            pass
        try:
            self.proc.wait(timeout=30)
        except Exception:  # noqa: BLE001
            self.proc.kill()


def _render_worker(instance: dict, rfd: int, wfd: int, depth: bool) -> int:
    """The render-only process: a Session with the cameras that never steps; draws the snapshots it is sent."""
    try:
        s = Session(instance, cameras=True, depth=depth, _render_only=True)
        _send(wfd, {"cams": {c: {k: (v.tolist() if hasattr(v, "tolist") else v) for k, v in m.items()} for c, m in s._cams.items()}})
    except BaseException as exc:  # noqa: BLE001
        import traceback
        traceback.print_exc(); _send(wfd, {"error": repr(exc)[:500]}); return 1
    torch = s.torch; env = s.env; dev = env.device
    while True:
        try:
            msg = _recv(rfd)
        except EOFError:
            return 0
        if msg.get("op") == "close":
            return 0
        try:
            snap = msg["snapshot"]
            with torch.inference_mode():
                for name, (root, q, qd) in snap["art"].items():
                    art = env.scene.articulations[name]
                    art.write_root_state_to_sim(torch.as_tensor(root, device=dev).reshape(1, -1))
                    art.write_joint_state_to_sim(torch.as_tensor(q, device=dev).reshape(1, -1), torch.as_tensor(qd, device=dev).reshape(1, -1))
                for name, root in snap["rig"].items():
                    env.scene.rigid_objects[name].write_root_state_to_sim(torch.as_tensor(root, device=dev).reshape(1, -1))
                vis = snap.get("stain_visible")
                if vis is not None and getattr(env, "_dot_visibility_views", None) is not None:
                    for i, view in enumerate(env._dot_visibility_views):
                        view.set_visibility(torch.as_tensor([bool(vis[i])], device=dev), indices=torch.tensor([0], device=dev))
                env.sim.forward()
                env.sim.render()
                frames, depths = {}, {}
                for c in msg["cams"]:
                    cam = getattr(env, c)
                    cam.update(0.0, force_recompute=True)
                    frames[c] = s._rgb_now(c)
                    if msg.get("depth") and s.depth:
                        depths[c] = s._depth_now(c)
            _send(wfd, {"frames": frames, "depth": depths})
        except BaseException as exc:  # noqa: BLE001
            import traceback
            traceback.print_exc(); _send(wfd, {"error": repr(exc)[:500]})


def load_instance(instance) -> dict:
    return instance if isinstance(instance, dict) else json.loads(Path(instance).read_text())


def _np(x) -> np.ndarray:
    return x.detach().cpu().numpy() if hasattr(x, "detach") else np.asarray(x)


class Session:
    """One AM-Bench environment of one frozen instance. One per process (Isaac Sim runs once per process)."""

    def __init__(self, instance="/app/instance.json", *, strict: bool = False, cameras: bool = False, depth: bool = False,
                 _render_only: bool = False):
        # cameras=True: the physics stays camera-free (as the grader's) and a render worker draws the cameras (Renderer)
        self.render_only = bool(_render_only)
        self.cameras = bool(cameras); self.depth = bool(cameras and depth)
        self.renderer = None
        if self.cameras and not self.render_only:      # start the worker first: the two scenes build at the same time
            self.renderer = Renderer(load_instance(instance), depth=self.depth)
        _launch_app(self.render_only)
        import gymnasium as gym
        import torch
        import ambench.tasks  # noqa: F401  (registers the environments)
        from isaaclab_tasks.utils.parse_cfg import parse_env_cfg
        self.torch = torch
        self.instance = load_instance(instance)
        I = self.instance
        self.env_id, self.seed = I["env_id"], int(I["seed"])
        # the render worker's scene is built exactly as the physics process's (the same device: the seeded reset draws the same
        # numbers, so every fixed body is where it is in the physics process; the snapshot moves the rest)
        cfg = parse_env_cfg(self.env_id, device="cuda:0", num_envs=1)
        cfg.seed = self.seed
        if self.render_only:     # the render worker never simulates: PhysX's GPU buffers at their minimum (GPU memory)
            for k, v in (("gpu_max_rigid_contact_count", 2**16), ("gpu_max_rigid_patch_count", 2**14), ("gpu_found_lost_pairs_capacity", 2**14),
                         ("gpu_found_lost_aggregate_pairs_capacity", 2**14), ("gpu_total_aggregate_pairs_capacity", 2**14),
                         ("gpu_collision_stack_size", 2**20), ("gpu_heap_capacity", 2**22), ("gpu_temp_buffer_capacity", 2**20),
                         ("gpu_max_soft_body_contacts", 2**10), ("gpu_max_particle_contacts", 2**10)):
                if hasattr(cfg.sim.physx, k):
                    setattr(cfg.sim.physx, k, v)
        else:                    # PHYSX BUFFERS. Isaac Lab sizes PhysX's GPU buffers for thousands of environments; this is one.
            # One environment's worth (measured: a replay's process 1.2 GB of GPU memory instead of 3.2 GB; the eight tasks' frozen
            # rows replay to their frozen end states with these, no buffer overflow reported: capacities, not the computation)
            for k, v in (("gpu_max_rigid_contact_count", 2**18), ("gpu_max_rigid_patch_count", 2**16), ("gpu_found_lost_pairs_capacity", 2**18),
                         ("gpu_found_lost_aggregate_pairs_capacity", 2**18), ("gpu_total_aggregate_pairs_capacity", 2**18),
                         ("gpu_collision_stack_size", 2**24), ("gpu_heap_capacity", 2**24), ("gpu_temp_buffer_capacity", 2**22),
                         ("gpu_max_soft_body_contacts", 2**10), ("gpu_max_particle_contacts", 2**10)):
                if hasattr(cfg.sim.physx, k):
                    setattr(cfg.sim.physx, k, v)
        if not self.render_only:  # the physics process never builds the cameras (and no scene camera): no rendering in it
            cfg.robot_profile.ee_camera = None; cfg.robot_profile.base_camera = None; cfg.scene_camera_cfg = None
        self.dropped_events = drop_visual_randomization(cfg)
        if self.depth:           # z-depth from the same renders as the RGB
            for cam in (cfg.robot_profile.ee_camera, cfg.robot_profile.base_camera):
                if cam is not None and DEPTH_TYPE not in cam.data_types:
                    cam.data_types = list(cam.data_types) + [DEPTH_TYPE]
        self.env = gym.make(self.env_id, cfg=cfg).unwrapped
        # Isaac Lab resets an environment whose episode ended INSIDE that step (DirectRLEnv.step -> _reset_idx), so after the
        # last step the scene is already the next episode's start: keep the end state's hash, taken just before that reset
        # (and, for the standard-mode service, what the robot sensed at the end: proprio, frames, camera poses)
        self._in_step = False; self.end_sha = None; self._end = None; self._cur_row = None
        _reset_idx = self.env._reset_idx

        def _keep_end_state(env_ids, _reset_idx=_reset_idx):
            if self._in_step:
                self.end_sha = self.state_sha()
                try:
                    self._end = self._capture_end()
                except Exception as exc:  # noqa: BLE001 -- the end's observation is a convenience, never the episode's verdict
                    print(f"[rcb_ambench] end-of-episode capture failed: {exc!r}", file=sys.stderr, flush=True); self._end = None
            return _reset_idx(env_ids)
        self.env._reset_idx = _keep_end_state
        sync_ik(self.env, torch)
        sync_phases(self.env, torch)
        self.synced_views = sync_views(self.env, torch)
        self.propellers_still = still_propellers(self.env)
        self._valve = None
        if self.env_id.startswith("RotateValve-"):
            self._unwrap_valve_angle()
        self._cams: dict = {}; self._model = None; self.kinematics_check: dict = {}; self._frame_cache = None
        self.n_resets = 0; self.n_steps_total = 0; self.n_clipped = 0
        self._video = None
        self.reset()
        self.initial_sha = self.state_sha()
        try:
            self._kin_setup()
        except Exception as exc:  # noqa: BLE001 -- privileged mode never needs the model; the standard service checks it
            print(f"[rcb_ambench] WARNING: the robot model could not be built: {exc!r}", file=sys.stderr, flush=True)
        if self.render_only:
            self._camera_setup()
        elif self.renderer is not None:
            self._cams = {c: {**m, "K": np.asarray(m["K"]), "link_T_cv": np.asarray(m["link_T_cv"])} for c, m in self.renderer.ready().items()}
        want = I.get("initial_sha")
        self.instance_matches = want is None or want == self.initial_sha
        if strict and not self.instance_matches:
            raise RuntimeError(f"the rebuilt scene differs from the frozen instance: {self.initial_sha} != {want}")
        _slog("session_start", env_id=self.env_id, instance_matches=self.instance_matches, cameras=self.cameras)

    # ------------------------------------------------------------------ episode
    def reset(self) -> None:
        """Back to the frozen instance (the seeded reset). Only the first episode of a process is guaranteed bit-identical
        to a fresh process's: check a trajectory with the `replay` CLI."""
        with self.torch.inference_mode():         # as step(): after a step Isaac Lab's buffers are inference tensors
            self.torch.cuda.synchronize()
            self.obs, _ = self.env.reset(seed=self.seed)
            self.torch.cuda.synchronize()
        self.end_sha = None; self._end = None
        if self._valve is not None:
            self._valve.update(prev=None, angle=None)    # the joint is back at 0 rad: count from here
        self.rows: list[np.ndarray] = []
        self.done = False; self.succeeded = False; self.timed_out = False
        self.n_resets += 1
        if self.n_resets > 1:
            _slog("reset", env_id=self.env_id)

    def _unwrap_valve_angle(self) -> None:
        """RotateValve's success on the valve's unwrapped angle (see the module docstring): AM-Bench's `_get_success`, with
        the joint position PhysX reports in [-pi, pi] replaced by the sum of its per-step changes since the reset."""
        env, torch, v = self.env, self.torch, {"prev": None, "angle": None}
        self._valve = v
        two_pi = 2.0 * float(np.pi)

        def _get_success():
            q = env.valve_object.data.joint_pos[:, env.valve_joint_idx].clone()
            if v["prev"] is None:                     # the first step after a reset, from 0 rad (|q| < 0.05 rad here)
                angle = q
            else:
                angle = v["angle"] + torch.remainder(q - v["prev"] + np.pi, two_pi) - np.pi
            v.update(prev=q, angle=angle)
            target = env.cfg.valve_target_angle
            rotated = angle >= target
            return rotated, {"valve_engaged": angle >= env.cfg.valve_engagement_ratio * target, "valve_rotated": rotated}
        env._get_success = _get_success

    def valve_angle(self) -> float | None:
        """RotateValve: the valve's unwrapped angle in rad since the reset (positive = clockwise from the robot's side),
        what the success check reads; None in other tasks or before the first step."""
        if self._valve is None or self._valve["angle"] is None:
            return None
        return float(_np(self._valve["angle"]).reshape(-1)[0])

    @property
    def n_steps(self) -> int:
        return len(self.rows)

    def clip(self, row) -> tuple[np.ndarray, int]:
        a = np.asarray(row, dtype=np.float64).reshape(-1).copy()
        if a.size != ACTION_DIM or not np.all(np.isfinite(a)):
            raise BadTrajectory(f"an action row has {ACTION_DIM} finite values (x y z qw qx qy qz gripper), got {a.size}")
        n = 0
        g = float(np.clip(a[7], -1.0, 1.0)); n += int(g != a[7]); a[7] = g
        if float(np.linalg.norm(a[3:7])) < 1e-9:      # passed on as it is (AM-Bench's controller takes the quaternion it gets)
            raise BadTrajectory("the action's quaternion has zero length")
        return a, n

    def step(self, row) -> bool:
        """One control step (1/120 s). Returns True when the episode is over; a step after that executes nothing."""
        if self.done:
            return True
        a, n = self.clip(row)
        self.n_clipped += n
        t = self.torch.as_tensor(a, dtype=self.torch.float32, device=self.env.device).reshape(1, ACTION_DIM)
        self._in_step = True; self._cur_row = a
        try:
            with self.torch.inference_mode():
                self.torch.cuda.synchronize()
                self.obs, _, term, trunc, _ = self.env.step(t)
                self.torch.cuda.synchronize()        # see SYNC below: without it the controller's GPU/CPU hand-off races
        finally:
            self._in_step = False
        self.rows.append(a)
        self.n_steps_total += 1
        self.succeeded = bool(_np(term).reshape(-1)[0])
        self.timed_out = bool(_np(trunc).reshape(-1)[0]) and not self.succeeded
        self.done = self.succeeded or self.timed_out or self.n_steps >= MAX_STEPS
        if self._video is not None:
            self._video_add()
        return self.done

    def success(self) -> bool:
        return self.succeeded

    def end_reason(self) -> str | None:
        if self.succeeded:
            return "success"
        if self.timed_out:
            return "timeout"
        return "step_cap" if self.done else None

    def hold_action(self) -> np.ndarray:
        """A row that keeps the current end-effector target and gripper command."""
        cp = self.env.control_pipeline
        pos = _np(cp.ee_cmd_pos_w[0] - self.env.scene.env_origins[0]).astype(np.float64)
        quat = _np(cp.ee_cmd_quat_w[0]).astype(np.float64)
        g = self._cur_row[7] if self._in_step and self._cur_row is not None else (self.rows[-1][7] if self.rows else 1.0)
        return np.r_[pos, quat, g]

    def status(self) -> dict[str, Any]:
        # state_sha: the episode's end state once it is over (taken before Isaac Lab's reset), else the current state
        return {"success": self.succeeded, "done": self.done, "end_reason": self.end_reason(), "control_steps": self.n_steps,
                "sim_time_s": round(self.n_steps / CONTROL_HZ, 4), "episode_length_s": float(self.env.cfg.episode_length_s),
                "resets": self.n_resets, "state_sha": self.end_sha if (self.done and self.end_sha) else self.state_sha()}

    def actions(self) -> np.ndarray:
        return np.asarray(self.rows, dtype=np.float64).reshape(-1, ACTION_DIM)

    def record_start(self) -> None:
        self.reset()

    def record_stop(self) -> np.ndarray:
        return self.actions()

    def replay(self, actions) -> dict[str, Any]:
        A = np.asarray(actions, dtype=np.float64).reshape(-1, ACTION_DIM)
        self.reset()
        for row in A:
            if self.step(row):
                break
        _slog("replay", env_id=self.env_id, rows=int(len(A)), executed=self.n_steps)
        return {**self.status(), "executed_rows": self.n_steps}

    def save_trajectory(self, actions, path="/app/output/trajectory.npz", meta: dict | None = None) -> None:
        A = np.asarray(actions, dtype=np.float64).reshape(-1, ACTION_DIM)
        if not np.all(np.isfinite(A)) or bad_quaternion_rows(A):
            raise BadTrajectory(f"{bad_quaternion_rows(A)} row(s) with a zero-length or non-finite quaternion, or a "
                                "non-finite value: the grader would score this file 0 (bad_trajectory)")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        np.savez(path, task=np.array(self.env_id), actions=A, meta=np.array(json.dumps(meta or {})))

    # ------------------------------------------------------------------ state (privileged)
    def state_sha(self) -> str:
        """sha256 over every articulation's and rigid object's root state, joint positions and velocities."""
        m = hashlib.sha256()
        sc = self.env.scene
        for group in (sc.articulations, sc.rigid_objects):
            for name in sorted(group):
                d = group[name].data
                for t in (d.root_state_w, getattr(d, "joint_pos", None), getattr(d, "joint_vel", None)):
                    if t is not None:
                        m.update(name.encode()); m.update(_np(t).tobytes())
        return m.hexdigest()

    def state(self) -> dict[str, Any]:
        """Privileged observation of the task (AM-Bench's own `policy` observation: robot, end effector, task objects and
        goal positions, relative to the environment's origin)."""
        obs = self.obs["policy"][0] if isinstance(self.obs.get("policy"), list) else self.obs.get("policy")
        return {k: _np(v).reshape(-1).tolist() for k, v in (obs.items() if isinstance(obs, dict) else [])}

    def objects(self) -> dict[str, dict]:
        """Every articulation (but the robot) and rigid object of the scene: root pose (wxyz) and velocities, joint state."""
        out, o = {}, _np(self.env.scene.env_origins[0])
        sc = self.env.scene
        for group in (sc.articulations, sc.rigid_objects):
            for name, obj in group.items():
                if name == "robot":
                    continue
                rs = _np(obj.data.root_state_w[0])
                ent = {"position": (rs[:3] - o).tolist(), "orientation_wxyz": rs[3:7].tolist(), "velocity": rs[7:10].tolist(),
                       "angular_velocity": rs[10:13].tolist()}
                if getattr(obj.data, "joint_pos", None) is not None:
                    ent["joint_pos"] = _np(obj.data.joint_pos[0]).tolist(); ent["joint_names"] = list(obj.joint_names)
                out[name] = ent
        return out

    def proprio(self) -> dict[str, Any]:
        """The robot's own state: base and end-effector poses (world, relative to the env origin; wxyz) and velocities, the
        gripper opening and the arm joints, the current end-effector command."""
        e = self.env; o = _np(e.scene.env_origins[0])
        base = _np(e.robot.data.body_link_state_w[0, e.base_link_idx]); ee = _np(e.robot.data.body_link_state_w[0, e.ee_link_idx])
        jp = _np(e.robot.data.joint_pos[0]); jv = _np(e.robot.data.joint_vel[0])
        return {"base_pose": np.r_[base[:3] - o, base[3:7]].tolist(), "base_vel": base[7:13].tolist(),
                "ee_pose": np.r_[ee[:3] - o, ee[3:7]].tolist(), "ee_vel": ee[7:13].tolist(),
                "gripper_width": float(np.sum(jp[e.gripper_joint_ids])),
                "arm_joint_pos": jp[e.arm_joint_ids].tolist(), "arm_joint_vel": jv[e.arm_joint_ids].tolist(),
                "command": self.hold_action().tolist()}

    # ------------------------------------------------------------------ standard mode: what the robot senses
    def _ids(self, x) -> list[int]:
        return [int(i) for i in np.asarray(_np(x)).reshape(-1)]

    def _std_proprio_now(self) -> dict[str, list[float]]:
        e = self.env; d = e.robot.data; o = _np(e.scene.env_origins[0])
        arm, grip = self._ids(e.arm_joint_ids), self._ids(e.gripper_joint_ids)
        jp = _np(d.joint_pos[0]); jv = _np(d.joint_vel[0]); tau = _np(d.applied_torque[0])
        base = _np(d.body_link_state_w[0, e.base_link_idx]); ee = _np(d.body_link_state_w[0, e.ee_link_idx])
        cmd = self.hold_action()
        f = lambda xs: [float(x) for x in xs]  # noqa: E731
        return {"joint_pos": f(jp[arm + grip]), "joint_vel": f(jv[arm + grip]), "tcp_pose": f(np.r_[ee[:3] - o, ee[3:7]]),
                "gripper_opening": [float(np.sum(jp[grip]))], "gripper_cmd": [float(cmd[7])], "joint_effort": f(tau[arm]),
                "base_pose": f(np.r_[base[:3] - o, base[3:7]]), "base_vel": f(base[7:13]), "ee_cmd": f(cmd[:7])}

    def std_proprio(self) -> dict[str, list[float]]:
        """Standard mode's proprioception, by group (PROPRIO_ORDER): measured joints (the arm's four, then the two fingers),
        their velocities, the tool frame (ee_link) pose, the gripper opening and command, the arm's joint efforts, the
        airframe's pose and velocity, the current end-effector target. Once the episode is over: the values at its end
        (Isaac Lab has reset the scene by then)."""
        if self.done and self._end:
            return self._end["proprio"]
        return self._std_proprio_now()

    def proprio_layout(self) -> list[str]:
        names = list(self.env.robot.joint_names); e = self.env
        arm = [names[i] for i in self._ids(e.arm_joint_ids)]; grip = [names[i] for i in self._ids(e.gripper_joint_ids)]
        cols = {"joint_pos": arm + grip, "joint_vel": [f"{n}_vel" for n in arm + grip],
                "tcp_pose": [f"tcp_{k}" for k in ("x", "y", "z", "qw", "qx", "qy", "qz")], "gripper_opening": ["gripper_opening_m"],
                "gripper_cmd": ["gripper_cmd"], "joint_effort": [f"{n}_effort" for n in arm],
                "base_pose": [f"base_{k}" for k in ("x", "y", "z", "qw", "qx", "qy", "qz")],
                "base_vel": [f"base_{k}" for k in ("vx", "vy", "vz", "wx", "wy", "wz")],
                "ee_cmd": [f"ee_cmd_{k}" for k in ("x", "y", "z", "qw", "qx", "qy", "qz")]}
        return [c for g in PROPRIO_ORDER for c in cols[g]]

    def proprio_row(self) -> np.ndarray:
        P = self.std_proprio()
        return np.array([v for g in PROPRIO_ORDER for v in P[g]], dtype=np.float32)

    def snapshot(self) -> dict:
        """What the render worker needs to draw the current state: every articulation's root state and joint state, every
        rigid object's root state (world frame, float32 as simulated), and task state that only shows (WipeWindow's stains)."""
        sc = self.env.scene; f = lambda x: _np(x[0]).astype(np.float32).copy()  # noqa: E731
        snap = {"art": {n: (f(a.data.root_state_w), f(a.data.joint_pos), f(a.data.joint_vel)) for n, a in sc.articulations.items()},
                "rig": {n: f(r.data.root_state_w) for n, r in sc.rigid_objects.items()}}
        stains = getattr(self.env, "_stain_visible_buf", None)
        if stains is not None:
            snap["stain_visible"] = [bool(v) for v in _np(stains[0]).reshape(-1)]
        return snap

    def _capture_end(self) -> dict:
        """Inside the step that ends the episode, before Isaac Lab resets the scene: what the robot senses at the end (its
        proprioception, the state the cameras will draw, the camera poses)."""
        end = {"proprio": self._std_proprio_now(), "step": self.n_steps + 1}
        if self.renderer is not None:
            end["snap"] = self.snapshot(); end["cams"] = self._camera_info_now(list(self._cams))
        return end

    # ------------------------------------------------------------------ standard mode: the robot's model and spec sheet
    def _need_model(self) -> None:
        if self._model is None:
            raise RuntimeError("the robot model could not be built at startup (see the WARNING in the log)")

    def _body_T(self, link: str) -> np.ndarray:
        e = self.env; i = list(e.robot.body_names).index(link); s = _np(e.robot.data.body_link_state_w[0, i]); o = _np(e.scene.env_origins[0])
        return hom(quat_to_mat(s[3:7]), s[:3] - o)

    def _kin_setup(self) -> None:
        """The arm on the airframe as a numpy chain (base_link -> ee_link) from the robot's USD joint frames, checked against
        the simulator's link poses; the joint limits and drive gains; the spec sheet. Reads the stage, writes nothing."""
        import re
        import omni.usd
        from pxr import Usd, UsdPhysics
        stage = omni.usd.get_context().get_stage()
        gq = lambda q: np.array([q.GetReal(), *q.GetImaginary()], dtype=np.float64)  # noqa: E731
        e = self.env; robot = e.robot
        root_path = re.sub(r"env_\.\*", "env_0", str(robot.cfg.prim_path).replace("{ENV_REGEX_NS}", "/World/envs/env_0"))
        by_child = {}
        for p in Usd.PrimRange(stage.GetPrimAtPath(root_path)):
            if not p.IsA(UsdPhysics.Joint):
                continue
            j = UsdPhysics.Joint(p); b0, b1 = j.GetBody0Rel().GetTargets(), j.GetBody1Rel().GetTargets()
            if not b0 or not b1:
                continue
            A = hom(quat_to_mat(gq(j.GetLocalRot0Attr().Get())), list(j.GetLocalPos0Attr().Get()))
            B = hom(quat_to_mat(gq(j.GetLocalRot1Attr().Get())), list(j.GetLocalPos1Attr().Get()))
            axis = None; kind = "fixed"
            if p.IsA(UsdPhysics.RevoluteJoint):
                kind = "revolute"; axis = np.zeros(3); axis["XYZ".index(str(UsdPhysics.RevoluteJoint(p).GetAxisAttr().Get()))] = 1.0
            elif p.IsA(UsdPhysics.PrismaticJoint):
                kind = "prismatic"
            by_child[b1[0].name] = (p.GetName(), kind, b0[0].name, b1[0].name, A, axis, np.linalg.inv(B))
        base_link, ee_link = robot.body_names[e.base_link_idx], robot.body_names[e.ee_link_idx]
        chain, cur = [], ee_link
        while cur != base_link:
            if cur not in by_child:
                raise RuntimeError(f"no joint leads to {cur} (walking from {ee_link} to {base_link})")
            chain.insert(0, by_child[cur]); cur = by_child[cur][2]
        if any(c[1] == "prismatic" for c in chain):
            raise RuntimeError("a prismatic joint between the airframe and the end effector")
        names = list(robot.joint_names); arm = self._ids(e.arm_joint_ids)
        rev = [c[0] for c in chain if c[1] == "revolute"]
        if rev != [names[i] for i in arm]:
            raise RuntimeError(f"the chain's revolute joints {rev} are not the arm joints {[names[i] for i in arm]}")
        d = robot.data; a1 = lambda x: _np(x)[0]  # noqa: E731
        lim, vel, eff, kp, kd = (a1(x) for x in (d.joint_pos_limits, d.joint_vel_limits, d.joint_effort_limits, d.joint_stiffness, d.joint_damping))
        q0 = _np(d.joint_pos[0])[arm]
        self._model = ChainModel(base_link, chain, lim[arm, 0], lim[arm, 1], np.clip(q0, lim[arm, 0], lim[arm, 1]),
                                 extra={"tcp": (ee_link, np.eye(4))})
        Tb = self._body_T(base_link); T = self._model.fk(q0, Tb); ep = er = 0.0
        for link in self._model.links:
            if link in robot.body_names:
                Ts = self._body_T(link); ep = max(ep, float(np.linalg.norm(T[link][:3, 3] - Ts[:3, 3]))); er = max(er, rot_angle(T[link][:3, :3], Ts[:3, :3]))
        self.kinematics_check = {"links_max_pos_err_m": ep, "links_max_rot_err_rad": er, "chain": [c[0] for c in chain]}
        if ep > 1e-3 or er > 1e-2:
            print(f"[rcb_ambench] WARNING: the arm model disagrees with the simulator: {self.kinematics_check}", file=sys.stderr, flush=True)
        r6 = lambda x: round(float(x), 6)  # noqa: E731
        grip = self._ids(e.gripper_joint_ids)
        def arm_joint(i):
            # AM-Bench's asset gives three arm joints a range of +-10 rad (more than a turn each way): PhysX enforces it, but
            # it is no joint stop an arm meets, so it is reported as no limit, with the asset's range in a note
            j = {"name": names[i], "type": "revolute", "unit": "rad", "position_limits": [r6(lim[i, 0]), r6(lim[i, 1])],
                 "velocity_limit": r6(vel[i]), "effort_limit": r6(eff[i]), "group": "arm"}
            if min(-float(lim[i, 0]), float(lim[i, 1])) >= 2 * np.pi:
                j.update(type="continuous", position_limits=None,
                         note=f"the asset's range is [{r6(lim[i, 0])}, {r6(lim[i, 1])}] rad (PhysX enforces it; more than a turn each way)")
            return j
        joints = [arm_joint(i) for i in arm]
        joints += [{"name": names[i], "type": "prismatic", "unit": "m", "position_limits": [r6(lim[i, 0]), r6(lim[i, 1])],
                    "velocity_limit": r6(vel[i]), "effort_limit": r6(eff[i]), "group": "gripper"} for i in grip]
        open_m = [r6(sum(lim[i, 0] for i in grip)), r6(sum(lim[i, 1] for i in grip))]
        self._robot_spec = {
            "name": "ambench-fahexa",
            "description": "AM-Bench's FA-Hexa: a fully actuated hexarotor (six tilted rotors: it can hold any attitude while hovering) "
                           "carrying a 4-joint arm (three pitch joints and a roll joint) with a two-finger gripper; AM-Bench @ 60bf5b7 "
                           "on Isaac Lab / Isaac Sim 5.1",
            "base": {"type": "mobile", "link": base_link,
                     "note": "a free-flying airframe: no fixed base; its measured pose is the proprio group base_pose (world frame, "
                             "relative to the environment's origin) and /kinematics takes it as base_pose"},
            "joints": joints,
            "grippers": {"gripper": {"joints": [names[i] for i in grip], "opening_m": open_m,
                                     "command": {"index": 7, "range": [-1.0, 1.0], "unit": "1",
                                                 "rule": "the action row's 8th value: -1 = closed .. +1 = open (AM-Bench's gripper command)"},
                                     "tcp_frame": "tcp"}},
            "controller": {
                "type": "AM-Bench's whole-body controller (FA-Hexa, Abs-PID profile): every control step the end-effector target goes "
                        "through a floating-base IK (Pyroki) to an airframe pose and arm joint targets; a PID turns the airframe pose "
                        "into the six rotor thrusts; the arm and the fingers track their targets with PD joint drives",
                "control_hz": float(CONTROL_HZ), "physics_hz": float(CONTROL_HZ),
                "gains": {names[i]: {"stiffness": r6(kp[i]), "damping": r6(kd[i])} for i in arm + grip},
                "note": "the joint drives' stiffness (N m/rad, N/m) and damping (N m s/rad, N s/m); the airframe has no joint"},
            "tcp": {"tcp": {"parent_link": ee_link, "link_T_frame": np.eye(4).tolist(),
                            "definition": f"the {ee_link} frame itself: AM-Bench's end-effector command frame for the FA-Hexa (the "
                                          "ee_pose action, the proprio tcp_pose and ee_cmd use it)"}}}
        self._kin_spec = {
            "endpoint": "/kinematics", "joint_names": [names[i] for i in arm], "frame": "base", "quaternion_order": "wxyz",
            "links": list(self._model.links), "tcp_frames": ["tcp"], "ee_frames": ["tcp"], "ik_targets": ["tcp", ee_link],
            "base_pose_proprio": [f"base_{k}" for k in ("x", "y", "z", "qw", "qx", "qy", "qz")],
            "ik": {"solver": "damped least squares on the model's Jacobian from the seed (then the reset pose, then mid-range), every "
                             "step clamped to the joint limits; the airframe is not moved (four joints cannot reach every 6-D pose: "
                             "the error is reported)", "joints": [names[i] for i in arm], "tol_pos_m": 0.001, "tol_rot_rad": 0.01,
                   "max_iters": 300, "default_seed": [r6(x) for x in self._model.home], "collision_checking": "none"},
            "stateless": True,
            "note": "a numpy model of the arm chain read from the robot's USD joint frames at startup and checked against the "
                    f"simulator's link poses (max error {ep:.1e} m). Poses are relative to {base_link} (frame 'base'), or world "
                    "poses (relative to the environment's origin) when the request gives base_pose. AM-Bench's own controller "
                    "moves the airframe too (its floating-base IK): this model is the arm alone"}

    def robot_spec(self) -> dict:
        self._need_model(); return json.loads(json.dumps(self._robot_spec))

    def kinematics_spec(self) -> dict:
        self._need_model(); return json.loads(json.dumps(self._kin_spec))

    def kinematics(self, req: dict) -> dict:
        """Stateless FK / IK of the arm (never reads or changes the simulator). `req` as rcb_limited.parse_kinematics returns
        it: {"op": "fk", "q", "links", "base_pose"} or {"op": "ik", "targets", "seed", "base_pose", "tol_pos_m",
        "tol_rot_rad", "max_iters"}; poses x y z qw qx qy qz."""
        self._need_model()
        base_T = None if req.get("base_pose") is None else pose7_to_T(req["base_pose"])
        frame = "base" if base_T is None else "world"
        if req["op"] == "fk":
            T = self._model.fk(req["q"], base_T)
            return {"ok": True, "op": "fk", "frame": frame, "poses": {k: pose7(T[k]) for k in req["links"]}}
        targets = {k: pose7_to_T(v) for k, v in req["targets"].items()}
        q, ok, errs = self._model.ik(targets, seed=req.get("seed"), base_T=base_T, tol_p=float(req["tol_pos_m"]),
                                     tol_r=float(req["tol_rot_rad"]), max_iters=int(req["max_iters"]))
        return {"ok": bool(ok), "op": "ik", "frame": frame, "q": [float(v) for v in q],
                "error": {k: {"pos_m": float(e[0]), "rot_rad": float(e[1])} for k, e in errs.items()}}

    # ------------------------------------------------------------------ cameras
    def _camera_setup(self) -> None:
        """Per onboard camera, once: intrinsics, image size, clipping range and the mount (the camera prim's parent link and
        its fixed link -> camera transform, OpenCV axes), checked against the sensor's own pose."""
        from pxr import Usd, UsdGeom
        cache = UsdGeom.XformCache(Usd.TimeCode.Default())
        self._cams = {}; self.camera_check = {}
        for cam in CAMERAS:
            sen = getattr(self.env, cam, None)
            if sen is None:
                continue
            prim = sen._sensor_prims[0].GetPrim(); parent = prim.GetParent()
            K = _np(sen.data.intrinsic_matrices)[0]; H, W = (int(x) for x in sen.data.image_shape)
            near, far = (float(x) for x in UsdGeom.Camera(prim).GetClippingRangeAttr().Get())
            link_T_cv = np.array(cache.ComputeRelativeTransform(prim, parent)[0], dtype=np.float64).T @ GL2CV
            self._cams[cam] = {"K": K, "size": [W, H], "range": [near, min(far, DEPTH_MAX_M)], "link": parent.GetName(), "link_T_cv": link_T_cv}
            o = _np(self.env.scene.env_origins[0])
            Ts = hom(quat_to_mat(_np(sen.data.quat_w_ros)[0]), _np(sen.data.pos_w)[0] - o)
            Tm = self._body_T(parent.GetName()) @ link_T_cv
            self.camera_check[cam] = {"pos_err_m": float(np.linalg.norm(Ts[:3, 3] - Tm[:3, 3])), "rot_err_rad": rot_angle(Ts[:3, :3], Tm[:3, :3])}

    def _camera_info_now(self, cameras) -> dict[str, dict]:
        out = {}
        for c in cameras:
            m = self._cams[c]; Tw = self._body_T(m["link"]) @ m["link_T_cv"]
            out[c] = {"intrinsic_cv": m["K"].tolist(), "extrinsic_cv": np.linalg.inv(Tw)[:3].tolist(), "cam2world_gl": (Tw @ GL2CV).tolist(),
                      "image_size": list(m["size"]), "mount": {"type": "link", "parent_link": m["link"], "link_T_cam_cv": m["link_T_cv"].tolist()},
                      "moves": True, "depth_range_m": list(m["range"])}
        return out

    def camera_info(self, cameras=None) -> dict[str, dict]:
        """{cam: {"intrinsic_cv": 3x3, "extrinsic_cv": 3x4 world -> camera (OpenCV axes: x right, y down, z forward),
        "cam2world_gl": 4x4 camera -> world (OpenGL axes), "image_size": [W, H], "mount": parent link + fixed link_T_cam_cv,
        "moves": True, "depth_range_m": [near, far]}}; world = relative to the environment's origin. Cameras=True only."""
        if not self._cams:
            raise RuntimeError("no cameras in this Session (Session(..., cameras=True))")
        cams = list(cameras) if cameras is not None else list(self._cams)
        if self.done and self._end and "cams" in self._end and all(c in self._end["cams"] for c in cams):
            return {c: self._end["cams"][c] for c in cams}
        return self._camera_info_now(cams)

    def _rgb_now(self, camera: str) -> np.ndarray:      # the render worker's own cameras
        cam = getattr(self.env, camera, None)
        if cam is None:
            raise KeyError(f"no camera {camera!r}; cameras: {[c for c in CAMERAS if getattr(self.env, c, None) is not None]}")
        return np.ascontiguousarray(_np(cam.data.output["rgb"][0])[..., :3].astype(np.uint8))

    def _depth_now(self, camera: str) -> np.ndarray:    # the render worker's own cameras
        W, H = self._cams[camera]["size"]
        z = np.array(_np(getattr(self.env, camera).data.output[DEPTH_TYPE][0]), dtype=np.float32).reshape(H, W)
        z[~np.isfinite(z) | (z <= 0) | (z > DEPTH_MAX_M)] = 0.0
        return z

    def _drawn(self, depth: bool) -> tuple[dict, dict]:
        """Both cameras for the current state (once the episode is over: its end), drawn by the render worker; cached per
        control step."""
        if self.renderer is None:
            raise RuntimeError("no cameras in this Session: start it with Session(..., cameras=True)")
        key = ("end", self._end.get("step")) if (self.done and self._end and "snap" in self._end) else ("now", self.n_steps, self.n_resets)
        c = self._frame_cache
        if c is None or c[0] != key or (depth and not c[2]):
            snap = self._end["snap"] if key[0] == "end" else self.snapshot()
            frames, depths = self.renderer.render(snap, list(self._cams), depth and self.depth)
            self._frame_cache = c = (key, frames, depths)
        return c[1], c[2]

    def render_depth(self, camera: str = "ee_camera") -> np.ndarray:
        """float32 (H, W) z-depth in metres, pixel-aligned with render_frame(camera); 0 = no reading. Needs
        Session(..., cameras=True, depth=True)."""
        if not self.depth:
            raise RuntimeError("this Session renders no depth: Session(..., cameras=True, depth=True)")
        return self._drawn(True)[1][camera]

    def render_frame(self, camera: str = "ee_camera") -> np.ndarray:
        """RGB uint8 (384, 384, 3) of the robot's onboard camera `ee_camera` (at the end effector) or `base_camera` (on the
        airframe, looking forward), as of the last step (once the episode is over: its end). Session(cameras=True) only:
        drawn by the render worker from the physics state, so looking never changes the physics."""
        if camera not in self._cams:
            raise KeyError(f"no camera {camera!r}; cameras: {list(self._cams)}" if self._cams else
                           "no cameras in this Session: start it with Session(..., cameras=True)")
        return self._drawn(False)[0][camera]

    def start_video(self, path, fps: int = 30, camera: str = "ee_camera") -> None:
        import imageio.v2 as imageio
        self._video = {"w": imageio.get_writer(str(path), fps=fps, codec="libx264", quality=7, macro_block_size=8),
                       "every": max(1, round(CONTROL_HZ / fps)), "camera": camera, "path": str(path)}
        self._video_add(force=True)

    def _video_add(self, force: bool = False) -> None:
        v = self._video
        if force or self.n_steps % v["every"] == 0 or self.done:
            frames = [self.render_frame(c) for c in CAMERAS if c in self._cams]
            v["w"].append_data(np.concatenate(frames, axis=1))

    def stop_video(self):
        v, self._video = self._video, None
        if v:
            v["w"].close()
            return v["path"]

    def close(self) -> None:
        _slog("session_end", env_id=self.env_id, sim_steps=self.n_steps_total, resets=self.n_resets)
        if self.renderer is not None:
            self.renderer.close()
        try:
            self.env.close()
        except Exception:  # noqa: BLE001
            pass


def load_trajectory(path, env_id: str) -> np.ndarray:
    try:
        d = np.load(path, allow_pickle=False)
        task = str(d["task"])
        A = np.asarray(d["actions"], dtype=np.float64)
    except Exception as exc:  # noqa: BLE001 — whatever the file is, it is the agent's
        raise BadTrajectory(f"not a trajectory npz: {exc!r}"[:300]) from exc
    if task != env_id:
        raise BadTrajectory(f"trajectory is for {task!r}, not {env_id!r}")
    if A.ndim != 2 or A.shape[1] != ACTION_DIM or A.shape[0] > MAX_STEPS or not np.all(np.isfinite(A)):
        raise BadTrajectory(f"actions must be a finite (T, {ACTION_DIM}) array with T <= {MAX_STEPS}, got {list(A.shape)}")
    if bad_quaternion_rows(A):
        raise BadTrajectory(f"{bad_quaternion_rows(A)} action row(s) with a zero-length or non-finite quaternion")
    return A


def _replay_rows(s: "Session", A: np.ndarray) -> dict:
    for row in A:                                     # the process's first episode
        if s.step(row):
            break
    res = s.status()
    return {**{k: res[k] for k in ("success", "state_sha", "end_reason", "control_steps", "sim_time_s")}, "executed_rows": s.n_steps}


def _cli_replay(a) -> int:
    """The grader's replay: a fresh process, no cameras (bit-reproducible), the process's first episode."""
    t0 = time.time()
    s = Session(a.instance)
    out: dict[str, Any] = {"task": s.env_id, "instance_matches": bool(s.instance_matches), "initial_sha": s.initial_sha}
    try:
        A = load_trajectory(a.traj, s.env_id)
        rows = _replay_rows(s, A)
    except BadTrajectory as exc:          # the agent's input (a verdict: the grader scores it 0), never the simulator's
        out["error"] = f"bad trajectory: {exc}"[:300]; out["bad_trajectory"] = 1
        print(json.dumps(out), flush=True); return 2
    out["replays"] = [rows]
    out["n_actions"] = int(len(A)); out["replay_wall_s"] = round(time.time() - t0, 2)
    print(json.dumps(out), flush=True)
    s.close()
    return 0


def _cli_film(a) -> int:
    """An illustration, never a verdict: the rows with the onboard cameras on, filmed (both cameras side by side) plus the
    last end-effector frame. The cameras are drawn by the render worker, so the physics process is the replay's; the film
    still decides nothing (its time-out only costs the video)."""
    t0 = time.time()
    s = Session(a.instance, cameras=True)
    A = load_trajectory(a.traj, s.env_id)
    s.start_video(a.video, fps=a.fps)
    res = _replay_rows(s, A)
    s.stop_video()
    from PIL import Image
    Image.fromarray(s.render_frame("ee_camera")).save(str(Path(a.video).with_suffix(".last.png")))
    print(json.dumps({"task": s.env_id, "film": res, "video": a.video, "film_wall_s": round(time.time() - t0, 2)}), flush=True)
    s.close()
    return 0


def _cli_make_instance(a) -> int:
    inst = {"env_id": a.env_id, "seed": int(a.seed)}
    s = Session(inst)
    inst.update({"task": a.env_id.split("-")[0], "action_dim": ACTION_DIM, "control_hz": CONTROL_HZ,
                 "episode_length_s": float(s.env.cfg.episode_length_s), "initial_sha": s.initial_sha})
    Path(a.out).write_text(json.dumps(inst, indent=1) + "\n")
    print(json.dumps({"env_id": a.env_id, "initial_sha": s.initial_sha}), flush=True)
    s.close()
    return 0


def _cli_run_actions(a) -> int:
    s = Session(a.instance, strict=True)
    for row in np.load(a.actions):                    # the process's first episode (no second reset), as the grader's
        if s.step(row):
            break
    res = {**s.status(), "executed_rows": s.n_steps}
    s.save_trajectory(s.actions(), a.out, meta={"source": "reference rows"})
    print(json.dumps({k: res[k] for k in ("success", "end_reason", "state_sha", "control_steps", "executed_rows", "sim_time_s")}), flush=True)
    s.close()
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("replay"); r.add_argument("--instance", required=True); r.add_argument("--traj", required=True)
    w = sub.add_parser("render-worker"); w.add_argument("--instance-json", required=True); w.add_argument("--rfd", type=int, required=True)
    w.add_argument("--wfd", type=int, required=True); w.add_argument("--depth", action="store_true")
    f = sub.add_parser("film"); f.add_argument("--instance", required=True); f.add_argument("--traj", required=True)
    f.add_argument("--video", required=True); f.add_argument("--fps", type=int, default=30)
    m = sub.add_parser("make-instance"); m.add_argument("--env-id", required=True); m.add_argument("--seed", type=int, default=0); m.add_argument("--out", required=True)
    x = sub.add_parser("run-actions"); x.add_argument("--instance", required=True); x.add_argument("--actions", required=True); x.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    global SESSION_LOG
    SESSION_LOG = os.environ.get("RCB_SESSION_LOG", "")     # the CLI logs nothing unless asked
    try:
        if a.cmd == "render-worker":
            rc = _render_worker(json.loads(a.instance_json), a.rfd, a.wfd, a.depth)
        else:
            rc = {"replay": _cli_replay, "film": _cli_film, "make-instance": _cli_make_instance, "run-actions": _cli_run_actions}[a.cmd](a)
    except BaseException:  # noqa: BLE001 — Isaac Sim can hang at exit after an error: report it and leave at once
        import traceback
        traceback.print_exc(); rc = 3
    sys.stdout.flush(); sys.stderr.flush()
    os._exit(rc)          # Isaac Sim's shutdown can hang or crash after the result line; the result is printed


if __name__ == "__main__":
    main()
