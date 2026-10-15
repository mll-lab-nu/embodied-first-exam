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
             same state (the first episode of a process; later resets in the same process need not be bit-identical)
             WITHOUT the onboard cameras. With them (`Session(cameras=True)`), the per-step rendering makes PhysX's results
             depend on timing (measured: two fresh replays of the same rows part after a few hundred steps), so the
             grader, the reference recordings and a default Session run without them; cameras are for looking only.
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
  python rcb_ambench.py film --instance instance.json --traj traj.npz --video replay.mp4   # the same rows with the cameras on,
             filmed: an illustration only (camera rendering changes the numerics; never a verdict)
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


def load_instance(instance) -> dict:
    return instance if isinstance(instance, dict) else json.loads(Path(instance).read_text())


def _np(x) -> np.ndarray:
    return x.detach().cpu().numpy() if hasattr(x, "detach") else np.asarray(x)


class Session:
    """One AM-Bench environment of one frozen instance. One per process (Isaac Sim runs once per process)."""

    def __init__(self, instance="/app/instance.json", *, strict: bool = False, cameras: bool = False):
        _launch_app(cameras)
        self.cameras = bool(cameras)
        import gymnasium as gym
        import torch
        import ambench.tasks  # noqa: F401  (registers the environments)
        from isaaclab_tasks.utils.parse_cfg import parse_env_cfg
        self.torch = torch
        self.instance = load_instance(instance)
        I = self.instance
        self.env_id, self.seed = I["env_id"], int(I["seed"])
        cfg = parse_env_cfg(self.env_id, device="cuda:0", num_envs=1)
        cfg.seed = self.seed
        if not self.cameras:     # the robot profile's onboard cameras (and any scene camera) are not built: no rendering
            cfg.robot_profile.ee_camera = None; cfg.robot_profile.base_camera = None; cfg.scene_camera_cfg = None
        self.env = gym.make(self.env_id, cfg=cfg).unwrapped
        # Isaac Lab resets an environment whose episode ended INSIDE that step (DirectRLEnv.step -> _reset_idx), so after the
        # last step the scene is already the next episode's start: keep the end state's hash, taken just before that reset
        self._in_step = False; self.end_sha = None
        _reset_idx = self.env._reset_idx

        def _keep_end_state(env_ids, _reset_idx=_reset_idx):
            if self._in_step:
                self.end_sha = self.state_sha()
            return _reset_idx(env_ids)
        self.env._reset_idx = _keep_end_state
        self._valve = None
        if self.env_id.startswith("RotateValve-"):
            self._unwrap_valve_angle()
        self.n_resets = 0; self.n_steps_total = 0; self.n_clipped = 0
        self._video = None
        self.reset()
        self.initial_sha = self.state_sha()
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
            self.obs, _ = self.env.reset(seed=self.seed)
        self.end_sha = None
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
        self._in_step = True
        try:
            with self.torch.inference_mode():
                self.obs, _, term, trunc, _ = self.env.step(t)
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
        g = self.rows[-1][7] if self.rows else 1.0
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

    # ------------------------------------------------------------------ cameras
    def render_frame(self, camera: str = "ee_camera") -> np.ndarray:
        """RGB uint8 (384, 384, 3) of the robot's onboard camera `ee_camera` (at the end effector) or `base_camera` (on the
        airframe, looking forward), as of the last step. Only in a Session(cameras=True): the cameras render every step
        and that makes the physics timing-dependent, so check what you find there with the replay CLI (no cameras)."""
        if not self.cameras:
            raise RuntimeError("no cameras in this Session: start the process with Session(..., cameras=True) to look "
                               "(its numerics differ from the grader's camera-free replay; check trajectories with the CLI)")
        cam = getattr(self.env, camera, None)
        if cam is None:
            raise KeyError(f"no camera {camera!r}; cameras: {[c for c in CAMERAS if getattr(self.env, c, None) is not None]}")
        return _np(cam.data.output["rgb"][0])[..., :3].astype(np.uint8)

    def start_video(self, path, fps: int = 30, camera: str = "ee_camera") -> None:
        import imageio.v2 as imageio
        self._video = {"w": imageio.get_writer(str(path), fps=fps, codec="libx264", quality=7, macro_block_size=8),
                       "every": max(1, round(CONTROL_HZ / fps)), "camera": camera, "path": str(path)}
        self._video_add(force=True)

    def _video_add(self, force: bool = False) -> None:
        v = self._video
        if force or self.n_steps % v["every"] == 0 or self.done:
            frames = [self.render_frame(c) for c in CAMERAS if getattr(self.env, c, None) is not None]
            v["w"].append_data(np.concatenate(frames, axis=1))

    def stop_video(self):
        v, self._video = self._video, None
        if v:
            v["w"].close()
            return v["path"]

    def close(self) -> None:
        _slog("session_end", env_id=self.env_id, sim_steps=self.n_steps_total, resets=self.n_resets)
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
    last end-effector frame. Camera rendering makes the physics timing-dependent, so this episode may end differently."""
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
    f = sub.add_parser("film"); f.add_argument("--instance", required=True); f.add_argument("--traj", required=True)
    f.add_argument("--video", required=True); f.add_argument("--fps", type=int, default=30)
    m = sub.add_parser("make-instance"); m.add_argument("--env-id", required=True); m.add_argument("--seed", type=int, default=0); m.add_argument("--out", required=True)
    x = sub.add_parser("run-actions"); x.add_argument("--instance", required=True); x.add_argument("--actions", required=True); x.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    global SESSION_LOG
    SESSION_LOG = os.environ.get("RCB_SESSION_LOG", "")     # the CLI logs nothing unless asked
    try:
        rc = {"replay": _cli_replay, "film": _cli_film, "make-instance": _cli_make_instance, "run-actions": _cli_run_actions}[a.cmd](a)
    except BaseException:  # noqa: BLE001 — Isaac Sim can hang at exit after an error: report it and leave at once
        import traceback
        traceback.print_exc(); rc = 3
    sys.stdout.flush(); sys.stderr.flush()
    os._exit(rc)          # Isaac Sim's shutdown can hang or crash after the result line; the result is printed


if __name__ == "__main__":
    main()
