"""
rcb_pandadyn.py — task-local tooling for Panda Dynamic Scenes (25 multi-stage dynamic tasks for one or two stock Franka
Panda arms on ManiSkill 3.0.1 / SAPIEN 3.0.3, CPU PhysX at 1000 Hz; the environment package is /opt/pandadyn/panda_dynamics
in the image): frozen task instance, privileged state, action recording, fresh-process replay. Same shape as the other
benchmarks' rcb_<bench>.py, so agents and verifiers share one mental model.

Concepts
--------
instance   : one task (e.g. S02-PlateCatchTransportRelease) with its resolved physical parameters and the seed of its
             reset (instance.json). Session(instance=...) builds the scene and resets it with that seed; the environment
             rebuilds the whole scene on every reset, so a reset is exact. `state_sha` = sha256 over the physics state
             (every actor's and articulation's pose, velocity, joint positions and velocities), both servos' states, the
             simulated time and the task's phase / verdict flags. On load the rebuilt start is compared with the instance's
             `initial_sha` (`instance_matches`).
trajectory : the (T, D) actions handed to the environment, one row per control step (100 Hz: 10 physics steps of 1 ms),
             D = 8 per arm (16 for the two-arm tasks: panda-0 = left, then panda-1 = right): 7 absolute joint-position
             targets (rad, panda_joint1..7) + the total gripper aperture target (m, 0 = closed .. 0.08 = open). Each arm's
             torque servo turns its latest target into a jerk-limited reference (Ruckig, at most 65 % of the Panda's joint
             speed limits, 55 % (or the task's own fraction) of its acceleration and 5 % of its jerk limits) and tracks it
             with PD + inverse dynamics under the Panda's torque and torque-rate limits. Out-of-range values are clipped
             to the joint limits (and the aperture to [0, 0.08]) before they are executed and recorded. Physics is CPU
             PhysX with enhanced determinism: a run and a fresh-process replay of the same rows end in the same state.
success    : the task's own event ledger: every phase of the task completed in order (each phase has its own physical
             predicate), with no safety-limit violation and no failure event. The episode ends at the first control step
             where the task has succeeded or failed (a failure event: an object out of bounds, a spill, a limit violation,
             the task's horizon reached, ...); later rows are never executed.
budget     : no step budget: the agent's wall clock is the limit; the task's own horizon (simulated seconds) ends an
             episode as a failure, and MAX_ROWS (the environment's own step cap) bounds a trajectory.

CLI
---
  python rcb_pandadyn.py replay --instance instance.json --traj traj.npz [--video replay.mp4]   # one fresh-process replay
  python rcb_pandadyn.py make-instance --trial <dir with trial.json> --out instance.json [--actions-out actions.npy]
  python rcb_pandadyn.py run-actions --instance instance.json --actions actions.npy --out traj.npz

Python (what the agent gets in privileged mode)
-----------------------------------------------
  from rcb_pandadyn import Session
  s = Session(instance="/app/instance.json")   # ~5-15 s: builds the scene, resets it to the frozen instance
  s.reset()                                    # back to the frozen instance (exact; as often as you like)
  s.step(row)                                  # one control step (10 ms); returns True when the episode is over
  s.state(); s.proprio(); s.status()           # privileged state (objects, fixtures, phase, goals), robot, verdict
  s.snapshot() / s.restore(snap)               # exact save / restore of the whole episode
  s.actions()                                  # (T, D) rows executed since the last reset: the trajectory
  s.replay(actions); s.save_trajectory(actions, "/app/output/trajectory.npz")
None of the camera / kinematics / state calls steps physics or changes the simulator state.
"""
from __future__ import annotations

import os
for _k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_k, "1")

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

CONTROL_HZ = 100                     # one action per 10 ms
PHYSICS_HZ = 1000                    # 10 physics steps per action
MAX_ROWS = 4500                      # the environment's own episode cap (its registration's max_episode_steps)
ARM_DIM = 8                          # 7 joint targets (rad) + total aperture (m)
APERTURE_MAX = 0.08
CAMERAS = {"overview": "overview", "closeup": "event"}      # our name -> the environment's human-render camera
CAM_W, CAM_H = 640, 480
# Interaction log (privileged mode): every Session appends one line per session start / reset / replay / exit with the
# control steps consumed, to RCB_SESSION_LOG (default /app/output/rcb_session_log.jsonl, collected with the artifacts).
# The verifier reports it as self-reported cost and sets RCB_SESSION_LOG="" for its own sessions.
SESSION_LOG = os.environ.get("RCB_SESSION_LOG", "/app/output/rcb_session_log.jsonl")


def _slog(ev: str, **kw) -> None:
    if not SESSION_LOG:
        return
    try:
        os.makedirs(os.path.dirname(SESSION_LOG) or ".", exist_ok=True)
        with open(SESSION_LOG, "a") as f:
            f.write(json.dumps({"ev": ev, "t": round(time.time(), 3), "pid": os.getpid(), **kw}) + "\n")
    except OSError:
        pass


def _np(x) -> np.ndarray:
    if hasattr(x, "detach"):
        x = x.detach().cpu().numpy()
    return np.asarray(x)


def load_instance(instance: str | Path | dict) -> dict:
    if isinstance(instance, dict):
        return instance
    return json.loads(Path(instance).read_text())


def _limits():
    from panda_dynamics.robots import panda_limits as L
    return L


class Session:
    """One scene of one frozen instance. Build one per process (a Session holds a SAPIEN scene)."""

    def __init__(self, instance: str | Path | dict = "/app/instance.json", *, strict: bool = False):
        import gymnasium as gym
        import panda_dynamics  # noqa: F401  (registers the 25 tasks)
        from panda_dynamics.manifest import ensure_registered
        self.instance = load_instance(instance)
        I = self.instance
        self.task = I["task"]
        spec = ensure_registered(self.task)
        cams = {name: {"width": CAM_W, "height": CAM_H} for name in CAMERAS.values()}
        # render_backend "cpu": SAPIEN still renders on the GPU (Vulkan), and ManiSkill hands the images over in host memory
        # (its default copies them through CUDA, which the image's CPU build of torch does not have). Physics is unaffected.
        self.env = gym.make(spec.env_id, difficulty=I["difficulty"], parameters=I["parameters"], physics_hz=int(I["physics_hz"]),
                            quality="preview", human_render_camera_configs=cams, render_backend="cpu")
        self.u = self.env.unwrapped
        self.arm_ids = list(self.u.arms)
        self.dim = ARM_DIM * len(self.arm_ids)
        self.n_resets = 0
        self.n_steps_total = 0
        self.n_clipped = 0
        self._video = None
        self._pin = {uid: arm.robot.create_pinocchio_model() for uid, arm in self.u.arms.items()}
        self._links = {uid: {l.entity.name: i for i, l in enumerate(arm.robot.links)} for uid, arm in self.u.arms.items()}
        self.reset()
        self.initial_sha = self.state_sha()
        want = I.get("initial_sha")
        self.instance_matches = (want is None) or (want == self.initial_sha)
        if strict and not self.instance_matches:
            raise RuntimeError(f"the rebuilt scene differs from the frozen instance: state {self.initial_sha[:16]} != {str(want)[:16]}")
        _slog("session_start", task=self.task, instance_matches=self.instance_matches)

    # ------------------------------------------------------------------ episode
    def reset(self) -> None:
        """Back to the frozen instance: the scene is rebuilt and reset with the instance's seed (exact)."""
        self.env.reset(seed=int(self.instance["seed"]))
        self.done = False
        self.truncated = False
        self.n_resets += 1
        if self.n_resets > 1:
            _slog("reset", task=self.task)

    @property
    def n_steps(self) -> int:
        """Control steps executed since the last reset."""
        return len(self.u.action_history)

    def clip(self, row) -> tuple[np.ndarray, int]:
        """The row the servo executes: joint targets clipped to the joint limits, the aperture to [0, 0.08]."""
        L = _limits()
        a = np.asarray(row, dtype=np.float64).reshape(-1).copy()
        if a.size != self.dim:
            raise ValueError(f"an action row has {self.dim} values ({len(self.arm_ids)} arm(s) x 8), got {a.size}")
        if not np.all(np.isfinite(a)):
            raise ValueError("an action row contains NaN/inf")
        n = 0
        for i in range(len(self.arm_ids)):
            s = slice(ARM_DIM * i, ARM_DIM * i + 7)
            c = np.clip(a[s], L.LOWER, L.UPPER); n += int(np.sum(c != a[s])); a[s] = c
            g = float(np.clip(a[ARM_DIM * i + 7], 0.0, APERTURE_MAX)); n += int(g != a[ARM_DIM * i + 7]); a[ARM_DIM * i + 7] = g
        return a, n

    def step(self, row) -> bool:
        """One control step (10 ms of simulated time, 10 physics steps). `row`: D values (8 per arm, panda-0 first).
        Returns True when the episode is over (success or failure); a step after that executes nothing."""
        if self.done:
            return True
        a, n = self.clip(row)
        self.n_clipped += n
        act = a if len(self.arm_ids) == 1 else {uid: a[ARM_DIM * i:ARM_DIM * (i + 1)] for i, uid in enumerate(self.arm_ids)}
        _, _, term, trunc, _ = self.env.step(act)
        self.n_steps_total += 1
        self.truncated = bool(_np(trunc).reshape(-1)[0])
        self.done = bool(_np(term).reshape(-1)[0]) or self.truncated
        if self._video is not None:
            self._video_add()
        return self.done

    def hold_action(self) -> np.ndarray:
        """A row that commands every arm to stay where it is now (its measured joints and aperture)."""
        return np.concatenate([np.r_[_np(arm.robot.qpos)[:7], float(np.sum(_np(arm.robot.qpos)[7:9]))] for arm in self.u.arms.values()])

    def success(self) -> bool:
        ev = self.u.events
        return bool(ev.physical_success and ev.valid and not ev.failure_reason)

    def end_reason(self) -> str | None:
        if self.success():
            return "success"
        if self.u.events.failure_reason:
            return str(self.u.events.failure_reason)
        if self.truncated:
            return "step_cap"
        return None

    def status(self) -> dict[str, Any]:
        u = self.u; ev = u.events
        return {"success": self.success(), "done": self.done, "end_reason": self.end_reason(), "phase": int(u.phase),
                "phase_name": u.phase_name, "phases": list(u.PHASES), "valid": bool(ev.valid), "failure_reason": ev.failure_reason,
                "sim_time_s": round(float(u.time), 4), "control_steps": self.n_steps, "horizon_s": float(u.params["horizon"]),
                "events": [dict(e) for e in ev.history[-12:]], "resets": self.n_resets, "state_sha": self.state_sha()}

    def actions(self) -> np.ndarray:
        """(T, D) float64: the rows executed since the last reset (as clipped), i.e. the trajectory of this episode."""
        rows = []
        for h in self.u.action_history:
            rows.append(np.concatenate([np.asarray(h[uid], dtype=np.float64) for uid in self.arm_ids]) if isinstance(h, dict)
                        else np.asarray(h, dtype=np.float64))
        return np.asarray(rows, dtype=np.float64).reshape(-1, self.dim)

    def record_start(self) -> None:
        """Kept for familiarity: a trajectory always starts at the frozen state, so this resets."""
        self.reset()

    def record_stop(self) -> np.ndarray:
        return self.actions()

    def snapshot(self) -> dict:
        """The whole episode (the environment's own exact snapshot: restoring it replays its rows from the frozen state)."""
        return {"env": self.u.snapshot(), "done": self.done, "truncated": self.truncated}

    def restore(self, snap: dict) -> None:
        self.u.restore(snap["env"])
        self.done, self.truncated = snap["done"], snap["truncated"]

    def replay(self, actions) -> dict[str, Any]:
        """Reset, run the rows open-loop until the episode ends, return status() (+ executed_rows)."""
        A = np.asarray(actions, dtype=np.float64).reshape(-1, self.dim)
        self.reset()
        for row in A:
            if self.step(row):
                break
        _slog("replay", task=self.task, rows=int(len(A)), executed=self.n_steps)
        return {**self.status(), "executed_rows": self.n_steps}

    def save_trajectory(self, actions, path: str | Path = "/app/output/trajectory.npz", meta: dict | None = None) -> None:
        A = np.asarray(actions, dtype=np.float64).reshape(-1, self.dim)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        np.savez(path, task=np.array(self.task), actions=A, meta=np.array(json.dumps(meta or {})))

    # ------------------------------------------------------------------ state (privileged)
    def state_sha(self) -> str:
        """sha256 of the physics state, both servos, the simulated time and the task's phase / verdict flags."""
        m = hashlib.sha256()
        sd = self.u.get_state_dict()
        for group in sorted(sd):
            for name in sorted(sd[group]):
                m.update(f"{group}/{name}".encode()); m.update(np.ascontiguousarray(_np(sd[group][name])).tobytes())
        for uid in self.arm_ids:
            sv = self.u.arms[uid].servo
            m.update(uid.encode()); m.update(np.asarray(sv.torque, dtype=np.float64).tobytes())
            for k in ("current_position", "current_velocity", "current_acceleration", "target_position"):
                m.update(np.asarray(getattr(sv.input, k), dtype=np.float64).tobytes())
        ev = self.u.events
        m.update(json.dumps([round(float(self.u.time), 9), int(self.u.phase), bool(ev.physical_success), bool(ev.valid),
                             ev.failure_reason, len(ev.history)]).encode())
        return m.hexdigest()

    def state(self) -> dict[str, Any]:
        """Privileged state: every object's pose (position, quaternion wxyz), linear and angular velocity, every fixture's
        joint position / velocity, the tool poses, the task's phase and the goals it announced at reset."""
        info = self.u.get_info()
        return {k: _np(v).reshape(-1).tolist() for k, v in self.u._get_obs_extra(info).items()}

    def objects(self) -> dict[str, dict]:
        from panda_dynamics.props.primitives import body
        out = {}
        for name, obj in self.u.objects.items():
            rb = body(obj)
            out[name] = {"position": _np(rb.entity_pose.p).tolist(), "orientation_wxyz": _np(rb.entity_pose.q).tolist(),
                         "velocity": _np(rb.linear_velocity).tolist(), "angular_velocity": _np(rb.angular_velocity).tolist()}
        return out

    def fixtures(self) -> dict[str, dict]:
        return {n: {"q": float(f.q), "v": float(f.v)} for n, f in self.u.fixtures.items()}

    def params(self) -> dict[str, Any]:
        """The instance's physical parameters (masses, speeds, sizes, horizon; SI units)."""
        return dict(self.u.params)

    # ------------------------------------------------------------------ robot (proprioception, kinematics)
    def tcp_pose(self, uid: str = "panda-0") -> np.ndarray:
        arm = self.u.arms[uid]
        p = arm.agent.tcp._objs[0].entity_pose
        return np.r_[_np(p.p), _np(p.q)]

    def tool_pose(self, uid: str = "panda-0") -> np.ndarray:
        p = self.u.arms[uid].tool_pose
        return np.r_[_np(p.p), _np(p.q)]

    def proprio(self) -> dict[str, dict]:
        """Per arm: measured joints (7 rad + 2 fingers m), velocities, hand TCP and tool poses (world, wxyz), the servo's
        commanded torques (N m), its current target row (8) and the measured aperture (m)."""
        out = {}
        for uid, arm in self.u.arms.items():
            q = _np(arm.robot.qpos).astype(np.float64); v = _np(arm.robot.qvel).astype(np.float64); sv = arm.servo
            tgt = np.asarray(sv.input.target_position, dtype=np.float64)
            out[uid] = {"q": q[:9].tolist(), "qd": v[:9].tolist(), "tcp_pose": self.tcp_pose(uid).tolist(),
                        "tool_pose": self.tool_pose(uid).tolist(), "torque": np.asarray(sv.torque, dtype=np.float64)[:7].tolist(),
                        "target": np.r_[tgt[:7], tgt[7] + tgt[8]].tolist(), "aperture": float(q[7] + q[8])}
        return out

    def base_pose(self, uid: str = "panda-0") -> np.ndarray:
        p = self.u.arms[uid].robot.pose
        return np.r_[_np(p.p), _np(p.q)]

    def fk(self, q7, uid: str = "panda-0") -> dict[str, list]:
        """Stateless forward kinematics: world poses (x y z qw qx qy qz) of the hand TCP and the tool for joint angles q7."""
        import sapien
        arm = self.u.arms[uid]; pin = self._pin[uid]; links = self._links[uid]
        q = np.r_[np.asarray(q7, dtype=np.float64).reshape(7), 0.04, 0.04]
        pin.compute_forward_kinematics(q)
        base = arm.robot.pose
        out = {}
        for name, link in (("tcp", "panda_hand_tcp"), ("tool", "tool"), ("hand", "panda_hand")):
            if link in links:
                p = base * pin.get_link_pose(links[link])
                out[name] = np.r_[_np(p.p), _np(p.q)].tolist()
        if "tool" not in out:
            out["tool"] = out["tcp"]
        return out

    def ik(self, pose7, uid: str = "panda-0", frame: str = "tcp", seed=None) -> np.ndarray:
        """Joint angles (7) that put the hand TCP (frame="tcp") or the tool (frame="tool") at a world pose
        (x y z qw qx qy qz); raises ValueError when unreachable within the joint limits. Stateless."""
        import sapien
        arm = self.u.arms[uid]
        target = sapien.Pose(np.asarray(pose7[:3], dtype=np.float64), np.asarray(pose7[3:7], dtype=np.float64))
        if frame == "tool" and arm.tool is not None:
            target = target * arm.mount_pose.inv()
        q0 = _np(arm.robot.qpos).astype(np.float64) if seed is None else np.r_[np.asarray(seed, dtype=np.float64).reshape(7), 0.04, 0.04]
        return np.asarray(arm.ik.solve(target, initial=q0), dtype=np.float64)[:7]

    def robot_spec(self) -> dict[str, Any]:
        L = _limits()
        sv = self.u.primary.servo
        return {"arms": {uid: {"role": arm.role, "base_pose": self.base_pose(uid).tolist(), "tool": arm.setup.tool,
                               "tool_mount": {"parent": "panda_hand_tcp", "pose": [*arm.setup.mount, 0, 1, 0, 0]} if arm.setup.tool else None}
                         for uid, arm in self.u.arms.items()},
                "joint_lower": L.LOWER.tolist(), "joint_upper": L.UPPER.tolist(), "aperture_range_m": [0.0, APERTURE_MAX],
                "servo": {"max_joint_velocity": list(sv.input.max_velocity)[:7], "max_joint_acceleration": list(sv.input.max_acceleration)[:7],
                          "max_joint_jerk": list(sv.input.max_jerk)[:7], "finger_max_velocity_m_s": float(sv.input.max_velocity[7]),
                          "torque_limit_nm": L.TORQUE.tolist(), "torque_rate_limit_nm_s": L.TORQUE_RATE.tolist(),
                          "finger_force_limit_n": float(L.FINGER_FORCE), "kp": sv.kp.tolist(), "kd": sv.kd.tolist()},
                "safety_limits": {"joint_velocity": L.VELOCITY.tolist(), "joint_acceleration": L.ACCELERATION.tolist(),
                                  "joint_jerk": L.JERK.tolist(), "cartesian_speed_m_s": L.CART_SPEED, "cartesian_omega_rad_s": L.CART_OMEGA,
                                  "cartesian_acceleration_m_s2": L.CART_ACCELERATION, "cartesian_alpha_rad_s2": L.CART_ALPHA,
                                  "finger_speed_m_s": 0.051}}

    # ------------------------------------------------------------------ cameras
    def _camera(self, camera: str):
        if camera not in CAMERAS:
            raise KeyError(f"unknown camera {camera!r}; known: {list(CAMERAS)}")
        return self.u.scene.human_render_cameras[CAMERAS[camera]]

    def render_frame(self, camera: str = "overview") -> np.ndarray:
        """RGB uint8 (480, 640, 3) of "overview" (the whole workspace) or "closeup" (the task's working area). Rendering
        never steps physics."""
        self._camera(camera)
        self.u.scene.update_render(update_sensors=False, update_human_render_cameras=True)
        img = self.u.scene.get_human_render_camera_images(CAMERAS[camera])[CAMERAS[camera]]
        return _np(img)[0].astype(np.uint8)

    def render_depth(self, camera: str = "overview") -> np.ndarray:
        """z-depth float32 (480, 640) in metres along the optical axis, pixel-aligned with render_frame(camera); 0 = no
        reading. From the renderer's depth buffer; reads the state, never steps it."""
        cam = self._camera(camera)
        self.u.scene.update_render(update_sensors=False, update_human_render_cameras=True)
        cam.capture()
        return self._depth_of(camera)

    def _depth_of(self, camera: str) -> np.ndarray:
        """z-depth of the camera's last capture (render_frame / render_depth), from its [0, 1] depth buffer."""
        cam = self._camera(camera)
        d = cam.camera.get_picture(["GbufferDepth"])[0]
        d = _np(d).astype(np.float64).reshape(int(cam.config.height), int(cam.config.width))
        n, f = float(cam.config.near), float(cam.config.far)
        z = n * f / (f - d * (f - n))                    # the perspective depth mapping inverted (d = 1: the far plane, nothing there)
        z[~(d < 1.0)] = 0.0
        return z.astype(np.float32)

    def camera_info(self, cameras=None) -> dict[str, dict]:
        """Per camera: intrinsic_cv (3x3), extrinsic_cv (3x4, world -> camera, OpenCV axes), cam2world_gl (4x4), image size,
        near / far planes; every camera is static."""
        out = {}
        for name in ((cameras,) if isinstance(cameras, str) else (cameras or CAMERAS)):
            cam = self._camera(name)
            prm = cam.get_params()
            p = {k: np.asarray(_np(prm[k])[0], np.float64).tolist() for k in ("intrinsic_cv", "extrinsic_cv", "cam2world_gl")}
            out[name] = {**p, "image_size": [int(cam.config.width), int(cam.config.height)],
                         "depth_range_m": [float(cam.config.near), float(cam.config.far)],
                         "mount": {"type": "static", "extrinsic_cv": p["extrinsic_cv"], "cam2world_gl": p["cam2world_gl"]}, "moves": False}
        return out

    def start_video(self, path: str | Path, fps: int = 25, camera: str = "overview") -> None:
        import imageio.v2 as imageio
        self._video = {"w": imageio.get_writer(str(path), fps=fps, codec="libx264", quality=7, macro_block_size=8),
                       "every": max(1, round(CONTROL_HZ / fps)), "camera": camera, "n": 0, "path": str(path)}
        self._video_add(force=True)

    def _video_add(self, force: bool = False) -> None:
        v = self._video
        if force or self.n_steps % v["every"] == 0 or self.done:
            v["w"].append_data(self.render_frame(v["camera"])); v["n"] += 1

    def stop_video(self) -> str | None:
        v, self._video = self._video, None
        if v is None:
            return None
        v["w"].close()
        return v["path"]

    def render_video(self, actions, path: str | Path, fps: int = 25, camera: str = "overview") -> dict[str, Any]:
        """Replay `actions` from the frozen state while filming; returns the replay's status."""
        A = np.asarray(actions, dtype=np.float64).reshape(-1, self.dim)
        self.reset(); self.start_video(path, fps=fps, camera=camera)
        try:
            for row in A:
                if self.step(row):
                    break
        finally:
            self.stop_video()
        return {**self.status(), "executed_rows": self.n_steps}

    def close(self) -> None:
        _slog("session_end", task=self.task, sim_steps=self.n_steps_total, resets=self.n_resets)
        try:
            self.env.close()
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------- trajectories
def load_trajectory(path: str | Path, task: str, dim: int) -> np.ndarray:
    """(T, dim) float64 rows of a trajectory file of this task; ValueError when it is not one."""
    d = np.load(path, allow_pickle=False)
    if str(d["task"]) != task:
        raise ValueError(f"trajectory is for task {str(d['task'])!r}, not {task!r}")
    A = np.asarray(d["actions"], dtype=np.float64)
    if A.ndim != 2 or A.shape[1] != dim or A.shape[0] > MAX_ROWS or not np.all(np.isfinite(A)):
        raise ValueError(f"actions must be a finite (T, {dim}) array with T <= {MAX_ROWS}, got {list(A.shape)}")
    return A


def _cli_replay(a) -> int:
    t0 = time.time()
    s = Session(a.instance)
    out: dict[str, Any] = {"task": s.task, "instance_matches": bool(s.instance_matches), "initial_sha": s.initial_sha}
    try:
        A = load_trajectory(a.traj, s.task, s.dim)
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"bad trajectory: {exc!r}"[:300]; print(json.dumps(out), flush=True); return 2
    res = s.replay(A)
    out["replays"] = [{k: res[k] for k in ("success", "state_sha", "end_reason", "control_steps", "executed_rows", "phase",
                                           "phase_name", "sim_time_s", "valid", "failure_reason")}]
    out["n_actions"] = int(len(A)); out["replay_wall_s"] = round(time.time() - t0, 2)
    print(json.dumps(out), flush=True)                      # the verdict line, before any video
    if a.video:
        try:
            v = s.render_video(A, a.video, fps=a.fps)
            out["video_ok"] = v["state_sha"] == res["state_sha"]
            from PIL import Image
            Image.fromarray(s.render_frame("overview")).save(str(Path(a.video).with_suffix(".last.png")))
        except Exception as exc:  # noqa: BLE001  (a video never decides the replay)
            out["video_ok"] = False; out["video_error"] = repr(exc)[:200]
        print(json.dumps(out), flush=True)
    s.close()
    return 0


def _cli_make_instance(a) -> int:
    """instance.json (and the recorded rows as (T, D) .npy) from a recorded rollout directory (trial.json, actions.npz)."""
    trial = Path(a.trial)
    r = json.loads((trial / "trial.json").read_text())
    task = r["task_id"].split("/")[1].removesuffix("-v0")
    inst = {"task": task, "env_id": r["task_id"], "difficulty": r["difficulty"], "seed": int(r["seed"]), "parameters": r["parameters"],
            "physics_hz": int(r["physics_hz"])}
    s = Session(inst)
    inst.update({"arms": {uid: s.u.arms[uid].role for uid in s.arm_ids}, "action_dim": s.dim, "control_hz": CONTROL_HZ,
                 "horizon_s": float(s.u.params["horizon"]), "phases": list(s.u.PHASES), "initial_sha": s.initial_sha})
    Path(a.out).write_text(json.dumps(inst, indent=1) + "\n")
    if a.actions_out:
        d = np.load(trial / "actions.npz")
        A = np.asarray(d["actions"], dtype=np.float64).reshape(len(d["actions"]), -1)
        np.save(a.actions_out, A)
    print(json.dumps({"task": task, "initial_sha": s.initial_sha}), flush=True)
    s.close()
    return 0


def _cli_run_actions(a) -> int:
    s = Session(a.instance, strict=True)
    A = np.load(a.actions).astype(np.float64)
    res = s.replay(A)
    s.save_trajectory(s.actions(), a.out, meta={"source": "reference rows"})
    print(json.dumps({k: res[k] for k in ("success", "end_reason", "state_sha", "control_steps", "executed_rows", "sim_time_s")}), flush=True)
    s.close()
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("replay"); r.add_argument("--instance", required=True); r.add_argument("--traj", required=True)
    r.add_argument("--video"); r.add_argument("--fps", type=int, default=25); r.add_argument("--task", help="ignored (the instance names it)")
    m = sub.add_parser("make-instance"); m.add_argument("--trial", required=True); m.add_argument("--out", required=True); m.add_argument("--actions-out")
    x = sub.add_parser("run-actions"); x.add_argument("--instance", required=True); x.add_argument("--actions", required=True); x.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    os.environ["RCB_SESSION_LOG"] = os.environ.get("RCB_SESSION_LOG", "")
    return {"replay": _cli_replay, "make-instance": _cli_make_instance, "run-actions": _cli_run_actions}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
