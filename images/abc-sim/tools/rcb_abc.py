"""
rcb_abc.py — the tooling of the ABC Sim tasks: `abc_sim` (Apache-2.0) on MuJoCo 3.6.0, two I2RT YAM arms (6 joints and
a parallel gripper each) at a table. Frozen scene instance / privileged state / joint-position actions / recording /
fresh-process deterministic replay / rendering / kinematics.

Concepts
--------
instance   : instance.npz, one frozen scene: the assembled scene XML (every object, its size and pose already chosen),
             the full initial qpos, and the scene's randomization record (the directive, the targets, the per-task
             parameters the task's evaluator and runtime read). Session(instance=...) builds the scene from it, and
             every episode (reset, replay) starts from it. `state_sha` covers the MuJoCo state and the model's numeric
             arrays; the instance records the sha its scene starts at.
action     : one row per control step, 14 numbers: [left joint1..6 (rad), left gripper, right joint1..6 (rad), right
             gripper]. The joints are position servos (targets in rad, MuJoCo clamps them to the joint ranges); the
             gripper is a position servo on the finger opening, 0 = closed, 1 = open (each finger 0.0475 m from closed).
             One control step = 17 physics steps of 2 ms = 0.034 s.
episode    : starts at the frozen instance; ends in success once the task's evaluator has reported success after
             HOLD_STEPS consecutive control steps (30 steps = 1.02 s: passing through the goal does not count). Hanging a
             mug also requires every mug to touch neither the table nor a gripper (hanging from the rack, let go).
             Ball-tray balancing instead ends in success when the tray's countdown completes with the ball on the tray
             and both handles held throughout; it fails the moment the ball leaves the tray or a handle is let go during
             the countdown. MAX_STEPS only stops runaway trajectories. MuJoCo on the CPU is deterministic: the same rows
             from the same instance give the same final state, bit for bit, in any fresh process.

CLI
---
  python rcb_abc.py replay --instance instance.npz --traj trajectory.npz [--repeat N] [--out r.json] [--video replay.mp4]
  python rcb_abc.py info   --instance instance.npz

Python (what the agent gets in privileged mode)
-----------------------------------------------
  from rcb_abc import Session
  s = Session(instance="/app/instance.npz")
  s.prompt                            # the task's directive, e.g. "spell abc"
  s.reset()                           # back to the frozen instance state (unlimited)
  s.state()                           # privileged: robot joints, every object's pose, the evaluator's view, the runtime's
  s.model, s.data, s.env              # MuJoCo model / data and the abc_sim env (read them; only actions are replayed)
  s.step(a)                           # one control step (14 numbers); False once the episode is over
  s.status()                          # {'success', 'done', 'reason', 'steps', 'resets', 'state_sha', 'info'}
  snap = s.snapshot(); ...; s.restore(snap)   # save / restore a mid-episode state (search, planning); exact
  s.record_start(); ...; A = s.record_stop(); s.replay(A); s.save_trajectory(A, "/app/output/trajectory.npz")
  s.render_frame("top"); s.render_depth("top"); s.camera_info("left"); s.render_video(A, "/app/output/check.mp4")
  s.kinematics({"op": "fk", "q": q14}) ; s.kinematics({"op": "ik", "targets": {"left_tcp": [x, y, z, qw, qx, qy, qz]}})
"""
from __future__ import annotations

import os
import subprocess
import sys


def _pick_gl() -> str:
    """The rendering backend, chosen before MuJoCo loads: EGL on an NVIDIA GPU when it works (5-20 ms a frame), else
    OSMesa on the CPU (0.2-1 s a frame). RCB_GL / MUJOCO_GL = egl | osmesa forces one; auto probes EGL in a throwaway
    process (a failed EGL context cannot be undone in this one). Rendering never changes the physics."""
    want = os.environ.get("RCB_GL") or os.environ.get("MUJOCO_GL") or "auto"
    if want not in ("egl", "osmesa"):
        probe = "import mujoco; c = mujoco.GLContext(8, 8); c.make_current(); c.free()"
        try:
            ok = subprocess.run([sys.executable, "-c", probe], env={**os.environ, "MUJOCO_GL": "egl",
                                "PYOPENGL_PLATFORM": "egl"}, capture_output=True, timeout=60).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            ok = False
        want = "egl" if ok else "osmesa"
    os.environ["MUJOCO_GL"] = want
    os.environ["PYOPENGL_PLATFORM"] = want
    return want


GL = _pick_gl()

import argparse  # noqa: E402
import copy  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402

import mujoco  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, os.environ.get("ABC_SIM_ROOT", "/opt/abc"))

MAX_STEPS = 10_000_000          # runaway guard only; the wall clock is the budget
HOLD_STEPS = 30                 # the evaluator's success must hold this many consecutive control steps (1.02 s)
TRAY_GRACE_S = 0.1              # ball tray: both handles count as held when both were touched this recently (the runtime's)
CONTROL_DT = 0.034              # 17 physics steps of 2 ms (abc_sim's control_decimation)
GRIPPER_M = 0.0475              # the gripper command 1.0 = each finger 0.0475 m from closed
SIDES = ("left", "right")
ARM_JOINTS = [f"{s}_joint{i}" for s in SIDES for i in range(1, 7)]
ACTION_LAYOUT = [*(f"left_joint{i}" for i in range(1, 7)), "left_gripper", *(f"right_joint{i}" for i in range(1, 7)),
                 "right_gripper"]
CAMERAS = ("top", "left", "right", "overhead", "left_side", "right_side")
DEFAULT_CAMERAS = ("top", "left", "right")
_MODEL_SKIP = ("mesh_", "tex_", "hfield_", "skin_", "name_", "names", "paths", "text_", "flex_", "bvh_", "oct_", "plugin")

SESSION_LOG = os.environ.get("RCB_SESSION_LOG", "/app/output/rcb_session_log.jsonl")
SESSION_LOG_KEEP = os.environ.get("RCB_SESSION_LOG_KEEP", "/logs/agent/rcb_session_log.jsonl")


def _slog(ev: str, **kw) -> None:
    if not SESSION_LOG:
        return
    line = json.dumps({"ts": time.time(), "pid": os.getpid(), "ev": ev, **kw}) + "\n"
    for path, must_exist in ((SESSION_LOG, False), (SESSION_LOG_KEEP, True)):
        if not path or (must_exist and not os.path.isdir(os.path.dirname(path))):
            continue
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a") as f:
                f.write(line)
        except OSError:
            pass


def _log(*a: Any) -> None:
    print("[rcb_abc]", *a, file=sys.stderr, flush=True)


class PrimitiveError(RuntimeError):
    pass


def _jsonable(v: Any) -> Any:
    if isinstance(v, np.ndarray):
        return _jsonable(v.tolist())
    if isinstance(v, (np.floating, float)):
        return round(float(v), 6) if math.isfinite(float(v)) else None
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.bool_):
        return bool(v)
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items()}
    return v


def _model_arrays(model) -> dict[str, np.ndarray]:
    out = {}
    for k in dir(model):
        if k.startswith("_") or k.startswith(_MODEL_SKIP):
            continue
        try:
            v = getattr(model, k)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(v, np.ndarray) and v.dtype.kind in "fiub" and v.size:
            out[k] = v
    return out


def load_instance(path: str | Path) -> dict[str, Any]:
    d = np.load(path, allow_pickle=False)
    return {"family": str(d["family"]), "task": str(d["task"]), "scene_xml": str(d["scene_xml"]),
            "qpos0": np.asarray(d["qpos0"], dtype=np.float64), "randomization": json.loads(str(d["randomization"])),
            "rule": str(d["rule"]), "sha": str(d["sha"]), "meta": json.loads(str(d["meta"]))}


def build_env(task: str, scene_xml: str):
    """The abc_sim env of catalogue task `task` on the scene `scene_xml` (no randomizer: the scene is the instance's).
    The same construction for every task: the env on its default scene, then the instance's scene in its place (the
    path abc_sim takes for its model-swapping tasks), then the task's evaluator and runtime on that model."""
    from abc_sim.config import get_i2rt_sim_config
    from abc_sim.env import MuJoCoYAMEnv
    from abc_sim.task_registry import get_task_physics_defaults, resolve_task

    rt = resolve_task(task)
    env_task = rt.env_task or task
    prompt = rt.task_spec.prompt if rt.task_spec is not None else task.replace("_", " ")
    env = MuJoCoYAMEnv(config=get_i2rt_sim_config(), render_cameras=False, prompt=prompt, scene_xml=None,
                       **get_task_physics_defaults(env_task), max_episode_steps=None, terminate_on_success=False)
    env.reload_from_xml(scene_xml)
    env.set_task(task)
    env._task_randomizer = None
    return env


def _subtree_geoms(model, roots: list[str]) -> set[int]:
    ids = {model.body(r).id for r in roots if mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, r) >= 0}
    out = set()
    for g in range(model.ngeom):
        b = int(model.geom_bodyid[g])
        while b > 0 and b not in ids:
            b = int(model.body_parentid[b])
        if b in ids:
            out.add(g)
    return out


def _touching(data, a: set[int], b: set[int]) -> bool:
    for i in range(data.ncon):
        c = data.contact[i]
        g1, g2 = int(c.geom1), int(c.geom2)
        if (g1 in a and g2 in b) or (g2 in a and g1 in b):
            return True
    return False


class Session:
    """One abc_sim scene on a frozen instance. Every episode starts from the instance."""

    def __init__(self, instance: str | Path = "/app/instance.npz", *, max_steps: int = MAX_STEPS,
                 image_size: tuple[int, int] = (480, 640)):
        from abc_sim.randomization.core import RandomizationState

        self.inst = load_instance(instance)
        self.family, self.task, self.rule = self.inst["family"], self.inst["task"], self.inst["rule"]
        self.instance_sha = self.inst["sha"]
        self.max_steps = int(max_steps)
        self.env = build_env(self.task, self.inst["scene_xml"])
        self.model, self.data = self.env.model, self.env.data
        self.nu = 14
        self.dt = CONTROL_DT
        assert abs(self.model.opt.timestep * self.env._control_decimation - CONTROL_DT) < 1e-12
        if self.inst["qpos0"].shape != (self.model.nq,):
            raise ValueError(f"instance qpos has {self.inst['qpos0'].shape}, the scene nq = {self.model.nq}")
        self._rstate = RandomizationState.from_dict(self.inst["randomization"])
        self._renderers: dict[tuple[int, int], Any] = {}
        self._rec: list[np.ndarray] | None = None
        self.resets = 0
        self._total_steps = 0
        self._qadr = np.array([int(self.model.jnt_qposadr[self.model.joint(j).id]) for j in ARM_JOINTS[:6]]
                              + [int(self.model.jnt_qposadr[self.model.joint("left_left_finger").id])]
                              + [int(self.model.jnt_qposadr[self.model.joint(j).id]) for j in ARM_JOINTS[6:]]
                              + [int(self.model.jnt_qposadr[self.model.joint("right_left_finger").id])])
        self._vadr = np.array([int(self.model.jnt_dofadr[self.model.joint(j).id]) for j in ARM_JOINTS[:6]]
                              + [int(self.model.jnt_dofadr[self.model.joint("left_left_finger").id])]
                              + [int(self.model.jnt_dofadr[self.model.joint(j).id]) for j in ARM_JOINTS[6:]]
                              + [int(self.model.jnt_dofadr[self.model.joint("right_left_finger").id])])
        self._fingers = _subtree_geoms(self.model, [f"{a}_link_{b}_finger" for a in SIDES for b in SIDES])
        self._mugs = {b: _subtree_geoms(self.model, [b]) for b in self.objects() if self.family == "hang_mug"
                      and b.startswith("mug_") and b != "mug_tree"}
        self._table = {self.model.geom("table_plane").id} if self.family == "hang_mug" else set()
        self._episode_reset()
        self.instance_exact = self.state_sha() == self.instance_sha
        if not self.instance_exact:
            _log(f"WARNING: the scene starts at {self.state_sha()}, the frozen instance records {self.instance_sha}")
        _slog("session_start", family=self.family)
        import atexit
        atexit.register(lambda: _slog("session_end", family=self.family, resets=self.resets,
                                      sim_steps=self._total_steps + self.steps))

    # ------------------------------------------------------------------ episode
    def _episode_reset(self) -> None:
        """The instance's start, in env.reset()'s order: clean data, the frozen qpos at rest, then the runtime and the
        evaluator configured from the instance's randomization record."""
        env, st = self.env, self._rstate
        env.reset(seed=0, randomize=False)
        mujoco.mj_resetData(self.model, self.data)
        self.data.qpos[:] = self.inst["qpos0"]
        self.data.qvel[:] = 0.0
        env._last_randomization = st
        if st.metadata.get("prompt") is not None:
            env.prompt = str(st.metadata["prompt"])
        if env._task_runtime is not None:
            env._task_runtime.after_reset(self.model, self.data, randomization=st)
            env._sync_prompt_from_task_runtime()
        ev = env._task_evaluator
        if ev is not None:
            ev.reset(nworld=1)
            if hasattr(ev, "configure_from_randomization"):
                ev.configure_from_randomization(self.model, st)
            for hook, key in (("set_active_trash_joints", "trash_joints"),
                              ("set_active_object_joints", "active_object_joints")):
                if hasattr(ev, hook) and st.metadata.get(key) is not None:
                    getattr(ev, hook)(st.metadata[key])
        env.cur_step = 0
        mujoco.mj_forward(self.model, self.data)
        self.steps = 0
        self.done = False
        self.success = False
        self.reason: str | None = None
        self.success_run = 0
        self.last_info: dict[str, Any] = {}

    def reset(self) -> None:
        """Back to the frozen instance state (unlimited). Starts a new episode."""
        _slog("reset", family=self.family, n=self.resets + 1, sim_steps_before=self.steps)
        self._total_steps += self.steps
        self._episode_reset()
        self.resets += 1

    @property
    def prompt(self) -> str:
        return str(self.env.prompt)

    def step(self, action) -> bool:
        """One control step (14 numbers, ACTION_LAYOUT). True while the episode runs."""
        a = np.asarray(action, dtype=np.float64).reshape(-1)
        if a.shape != (self.nu,):
            raise ValueError(f"action must have {self.nu} numbers (ACTION_LAYOUT), got {a.shape}")
        if not np.all(np.isfinite(a)):
            raise ValueError("action contains NaN or inf")
        if self.done:
            raise PrimitiveError(f"episode is over ({self.reason}); call reset()")
        if self.steps >= self.max_steps:
            raise PrimitiveError(f"runaway guard: {self.max_steps} steps")
        _, reward, _, _, info = self.env.step(a, render_obs=False)
        self.steps += 1
        if self._rec is not None:
            self._rec.append(a.copy())
        ok = bool(info.get("task_success", False))
        self.last_info = {"task_success": ok, "task_reward": _jsonable(info.get("task_reward", 0.0))}
        if self.rule == "tray":
            rt = self.env._task_runtime
            rs = self.env.task_runtime_debug_state() or {}
            last = getattr(rt, "_last_both_handles_contact_at_s", None)
            held = last is not None and float(self.data.time) - float(last) <= TRAY_GRACE_S + 1e-9
            self.last_info.update(state=rs.get("state"), handles_held=held)
            if not ok:
                self.done, self.reason = True, "failure: the ball left the tray"
            elif getattr(rt, "_started_at_s", None) is not None and not held:
                self.done, self.reason = True, "failure: a handle was let go during the countdown"
            elif bool(rs.get("complete")):
                self.done, self.success, self.reason = True, True, "success"
            return not self.done
        if ok and self._mugs:
            ok = self.hanging()
            self.last_info["hanging"] = ok
        self.success_run = self.success_run + 1 if ok else 0
        self.last_info["success_run"] = self.success_run
        if self.success_run >= HOLD_STEPS:
            self.done, self.success, self.reason = True, True, "success"
        return not self.done

    def hanging(self) -> bool:
        """Hang a mug: no mug touches the table or a gripper finger (it hangs from the rack, let go)."""
        for g in self._mugs.values():
            if _touching(self.data, g, self._table | self._fingers):
                return False
        return True

    def status(self) -> dict[str, Any]:
        return {"success": bool(self.success), "done": bool(self.done), "reason": self.reason, "steps": int(self.steps),
                "resets": int(self.resets), "state_sha": self.state_sha(), "rule": self.rule,
                "success_run": int(self.success_run), "hold_steps": HOLD_STEPS, "info": self.last_info}

    # ------------------------------------------------------------------ state
    def _integration_state(self) -> np.ndarray:
        sig = mujoco.mjtState.mjSTATE_INTEGRATION
        s = np.empty(mujoco.mj_stateSize(self.model, sig))
        mujoco.mj_getState(self.model, self.data, s, sig)
        return s

    def state_sha(self) -> str:
        h = hashlib.sha1(self._integration_state().tobytes())
        for k, v in sorted(_model_arrays(self.model).items()):
            h.update(k.encode())
            h.update(np.ascontiguousarray(v).tobytes())
        return h.hexdigest()[:16]

    def snapshot(self) -> dict[str, Any]:
        """The exact mid-episode state (MuJoCo's integration state and the task's Python-side state: the evaluator's
        latches, the runtime's countdown or target sequence, its random generator). restore() continues bit for bit."""
        e = self.env
        return {"physics": self._integration_state(), "runtime": copy.deepcopy(e._task_runtime),
                "evaluator": copy.deepcopy(e._task_evaluator), "prompt": e.prompt, "cur_step": e.cur_step,
                "steps": self.steps, "done": self.done, "success": self.success, "reason": self.reason,
                "success_run": self.success_run, "last_info": copy.deepcopy(self.last_info)}

    def restore(self, snap: dict[str, Any]) -> None:
        e = self.env
        mujoco.mj_setState(self.model, self.data, snap["physics"], mujoco.mjtState.mjSTATE_INTEGRATION)
        e._task_runtime = copy.deepcopy(snap["runtime"])
        e._task_evaluator = copy.deepcopy(snap["evaluator"])
        e.prompt, e.cur_step = snap["prompt"], snap["cur_step"]
        self.steps, self.done, self.success, self.reason = snap["steps"], snap["done"], snap["success"], snap["reason"]
        self.success_run = snap["success_run"]
        self.last_info = copy.deepcopy(snap["last_info"])
        mujoco.mj_forward(self.model, self.data)

    def robot_q(self) -> np.ndarray:
        """The 14 action-space coordinates of the robot now: joint angles (rad) and gripper openings (0 closed .. 1 open)."""
        q = self.data.qpos[self._qadr].astype(np.float64).copy()
        q[[6, 13]] /= GRIPPER_M
        return q

    def robot_qd(self) -> np.ndarray:
        v = self.data.qvel[self._vadr].astype(np.float64).copy()
        v[[6, 13]] /= GRIPPER_M
        return v

    def site_pose(self, name: str) -> list[float]:
        i = self.model.site(name).id
        quat = np.zeros(4)
        mujoco.mju_mat2Quat(quat, self.data.site_xmat[i])
        return [*self.data.site_xpos[i].tolist(), *quat.tolist()]

    def objects(self) -> dict[str, list[float]]:
        """Every free-moving body (objects, tools, the ball ...): its pose, [x, y, z, qw, qx, qy, qz] in the world frame."""
        out = {}
        for j in range(self.model.njnt):
            if int(self.model.jnt_type[j]) == 0:
                a = int(self.model.jnt_qposadr[j])
                out[self.model.body(int(self.model.jnt_bodyid[j])).name] = self.data.qpos[a:a + 7].round(6).tolist()
        return out

    def evaluate(self) -> dict[str, Any]:
        """The task evaluator's view of the current state (reward, success and its metrics)."""
        r = self.env.evaluate_task()
        return {} if r is None else _jsonable(r.to_info(squeeze=True))

    def state(self) -> dict[str, Any]:
        """Privileged: the directive, the robot, every free body's pose, the evaluator's and the runtime's view."""
        return {"prompt": self.prompt, "robot_q": self.robot_q().round(6).tolist(),
                "tcp": {s: self.site_pose(f"{s}_tcp_site") for s in SIDES},
                "grasp_site": {s: self.site_pose(f"{s}_grasp_site") for s in SIDES},
                "objects": self.objects(), "evaluator": self.evaluate(),
                "runtime": _jsonable(self.env.task_runtime_debug_state() or {}),
                "randomization": _jsonable(self._rstate.metadata)}

    def action_limits(self) -> dict[str, list[float]]:
        lo, hi = self.model.actuator_ctrlrange[:14, 0].copy(), self.model.actuator_ctrlrange[:14, 1].copy()
        lo[[6, 13]] /= GRIPPER_M
        hi[[6, 13]] /= GRIPPER_M
        return {"low": lo.tolist(), "high": hi.tolist()}

    def hold_action(self) -> np.ndarray:
        """The row that holds the robot where it is now (its current joint angles and gripper openings)."""
        return self.robot_q()

    # ------------------------------------------------------------------ recording / replay
    def record_start(self) -> None:
        self._rec = []

    def record_stop(self) -> np.ndarray:
        rec, self._rec = self._rec or [], None
        _slog("record", family=self.family, n_actions=len(rec), success=bool(self.success))
        return np.asarray(rec, dtype=np.float64).reshape(-1, self.nu)

    def save_trajectory(self, actions, path: str | Path, meta: dict | None = None) -> None:
        A = np.asarray(actions, dtype=np.float64)
        if A.ndim != 2 or A.shape[1] != self.nu:
            raise ValueError(f"trajectory must be (T, {self.nu}), got {A.shape}")
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        np.savez(path, actions=A, family=self.family, instance_sha=self.instance_sha, meta=json.dumps(meta or {}))

    def replay(self, actions) -> dict[str, Any]:
        """Reset to the instance and replay open loop until the episode ends or the rows run out."""
        A = np.asarray(actions, dtype=np.float64)
        self.reset()
        n = 0
        for row in A:
            n += 1
            if not self.step(row):
                break
        st = self.status()
        st["replayed_rows"], st["rows"] = n, int(len(A))
        _slog("replay", family=self.family, n_actions=int(len(A)), success=st["success"])
        return st

    # ------------------------------------------------------------------ cameras
    def cameras(self) -> list[str]:
        return [mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_CAMERA, i) for i in range(self.model.ncam)]

    def _renderer(self, h: int, w: int):
        r = self._renderers.get((h, w))
        if r is None:
            if GL == "osmesa":   # a second OSMesa context next to a live one reads garbage
                for old in self._renderers.values():
                    old.close()
                self._renderers.clear()
            self.model.vis.global_.offheight = max(self.model.vis.global_.offheight, h)
            self.model.vis.global_.offwidth = max(self.model.vis.global_.offwidth, w)
            r = self._renderers[(h, w)] = mujoco.Renderer(self.model, height=h, width=w)
        return r

    def render_frame(self, camera: str = "top", size: tuple[int, int] = (480, 640)) -> np.ndarray:
        """RGB uint8 (H, W, 3) from a camera of the scene."""
        r = self._renderer(*size)
        r.update_scene(self.data, camera=camera)
        return r.render().copy()

    def render_depth(self, camera: str = "top", size: tuple[int, int] = (480, 640)) -> np.ndarray:
        """z-depth float32 (H, W) in metres from a camera of the scene."""
        r = self._renderer(*size)
        r.enable_depth_rendering()
        try:
            r.update_scene(self.data, camera=camera)
            return r.render().astype(np.float32).copy()
        finally:
            r.disable_depth_rendering()

    def camera_info(self, camera: str, size: tuple[int, int] = (480, 640)) -> dict[str, Any]:
        """The camera's intrinsics (OpenCV), world -> camera (OpenCV axes) and camera -> world (OpenGL axes) now."""
        h, w = size
        i = self.model.camera(camera).id
        f = 0.5 * h / math.tan(math.radians(float(self.model.cam_fovy[i])) / 2)
        c2w = np.eye(4)
        c2w[:3, :3] = self.data.cam_xmat[i].reshape(3, 3)
        c2w[:3, 3] = self.data.cam_xpos[i]
        ext = np.linalg.inv(c2w @ np.diag([1.0, -1.0, -1.0, 1.0]))[:3, :]
        return {"intrinsic_cv": [[f, 0.0, w / 2], [0.0, f, h / 2], [0.0, 0.0, 1.0]], "extrinsic_cv": ext.tolist(),
                "cam2world_gl": c2w.tolist(), "image_size": [w, h]}

    def render_video(self, actions, path: str | Path, *, cameras: list[str] | None = None, every: int = 1,
                     fps: float = 1 / CONTROL_DT, size: tuple[int, int] = (240, 320)) -> dict[str, Any]:
        import imageio.v2 as imageio
        A = np.asarray(actions, dtype=np.float64)
        self.reset()
        cams = list(cameras or DEFAULT_CAMERAS)
        w = imageio.get_writer(str(path), fps=fps / max(1, every), codec="libx264", quality=7, macro_block_size=8)
        try:
            w.append_data(np.concatenate([self.render_frame(c, size) for c in cams], axis=1))
            for i, row in enumerate(A):
                running = self.step(row)
                if i % every == 0 or not running or i == len(A) - 1:
                    w.append_data(np.concatenate([self.render_frame(c, size) for c in cams], axis=1))
                if not running:
                    break
        finally:
            w.close()
        return self.status()

    # ------------------------------------------------------------------ kinematics
    def kinematics(self, req: dict) -> dict[str, Any]:
        """The robot's kinematic model, stateless (it never touches the episode): fk of links / tool frames for 14
        action-space coordinates q, or ik for tool-frame targets (see Kinematics)."""
        if self._kin is None:
            self._kin = Kinematics(self.model, self.data)
        return self._kin.answer(req, self.robot_q())

    _kin = None

    def close(self) -> None:
        for r in self._renderers.values():
            try:
                r.close()
            except Exception:  # noqa: BLE001
                pass
        self._renderers.clear()


class Kinematics:
    """FK / IK on a private copy of the model's data (never stepped). Frames: the tool centre points `left_tcp` /
    `right_tcp` (the `<side>_tcp_site`), the grasp points `left_grasp` / `right_grasp` (`<side>_grasp_site`, between the
    finger pads), and the arm links. IK solves each requested frame with its own arm's six joints (damped least
    squares, several starts, within the joint ranges): position, and orientation when the target has a quaternion."""

    FRAMES = {f"{s}_{k}": f"{s}_{k}_site" for s in SIDES for k in ("tcp", "grasp")}

    def __init__(self, model, data):
        self.m = model
        self.d = mujoco.MjData(model)
        self.d.qpos[:] = data.qpos
        self.links = [f"{s}_link_{i}" for s in SIDES for i in range(1, 7)] + [f"{s}_camera_frame" for s in SIDES]
        self.jq = {s: np.array([int(model.jnt_qposadr[model.joint(f"{s}_joint{i}").id]) for i in range(1, 7)]) for s in SIDES}
        self.jv = {s: np.array([int(model.jnt_dofadr[model.joint(f"{s}_joint{i}").id]) for i in range(1, 7)]) for s in SIDES}
        self.lo = {s: model.jnt_range[[model.joint(f"{s}_joint{i}").id for i in range(1, 7)], 0].copy() for s in SIDES}
        self.hi = {s: model.jnt_range[[model.joint(f"{s}_joint{i}").id for i in range(1, 7)], 1].copy() for s in SIDES}
        self.fq = {s: (int(model.jnt_qposadr[model.joint(f"{s}_left_finger").id]),
                       int(model.jnt_qposadr[model.joint(f"{s}_right_finger").id])) for s in SIDES}

    def _set(self, q14) -> None:
        q = np.asarray(q14, dtype=np.float64).reshape(-1)
        if q.shape != (14,):
            raise ValueError("q must have 14 numbers (the action layout)")
        for k, s in enumerate(SIDES):
            self.d.qpos[self.jq[s]] = q[7 * k:7 * k + 6]
            g = q[7 * k + 6] * GRIPPER_M
            self.d.qpos[self.fq[s][0]], self.d.qpos[self.fq[s][1]] = g, -g
        mujoco.mj_kinematics(self.m, self.d)
        mujoco.mj_comPos(self.m, self.d)

    def _pose(self, name: str) -> list[float]:
        quat = np.zeros(4)
        if name in self.FRAMES:
            i = self.m.site(self.FRAMES[name]).id
            mujoco.mju_mat2Quat(quat, self.d.site_xmat[i])
            return [*self.d.site_xpos[i].tolist(), *quat.tolist()]
        b = self.m.body(name).id
        return [*self.d.xpos[b].tolist(), *self.d.xquat[b].tolist()]

    def answer(self, req: dict, q_now: np.ndarray) -> dict[str, Any]:
        op = req.get("op")
        if op == "fk":
            self._set(req["q"])
            names = req.get("links") or [*self.FRAMES, *self.links]
            bad = [n for n in names if n not in self.FRAMES and n not in self.links]
            if bad:
                raise ValueError(f"unknown links {bad}; links: {[*self.FRAMES, *self.links]}")
            return {"ok": True, "op": "fk", "frame": "world", "poses": {n: self._pose(n) for n in names}}
        if op != "ik":
            raise ValueError("op must be fk or ik")
        targets = req.get("targets") or {}
        if not targets or any(k not in self.FRAMES for k in targets):
            raise ValueError(f"targets: a dict of frames {list(self.FRAMES)} -> [x, y, z] or [x, y, z, qw, qx, qy, qz]")
        seed = np.asarray(req["seed"], dtype=np.float64) if req.get("seed") is not None else np.asarray(q_now, float)
        tol_p, tol_r = float(req.get("tol_pos_m", 0.002)), float(req.get("tol_rot_rad", 0.02))
        iters = int(req.get("max_iters", 300))
        q, errors = seed.copy(), {}
        for side in SIDES:   # each arm solves all of its frames at once, with its own six joints
            tg = {f: np.asarray(v, dtype=np.float64) for f, v in targets.items() if f.startswith(side + "_")}
            if not tg:
                continue
            k = 7 * SIDES.index(side)
            rng = np.random.default_rng(0)
            starts = [q[k:k + 6].copy()] + [rng.uniform(self.lo[side], self.hi[side])
                                            for _ in range(int(req.get("restarts", 8)))]
            best = None
            for q6 in starts:
                q6, errs = self._ik_arm(side, tg, q6, q, iters, tol_p, tol_r)
                score = max(e[0] + 0.1 * e[1] for e in errs.values())
                if best is None or score < best[2]:
                    best = (q6, errs, score)
                if all(e[0] <= tol_p and e[1] <= tol_r for e in errs.values()):
                    break
            q[k:k + 6] = best[0]
            errors.update({f: {"pos_m": float(e[0]), "rot_rad": float(e[1])} for f, e in best[1].items()})
        ok = all(e["pos_m"] <= tol_p and e["rot_rad"] <= tol_r for e in errors.values())
        return {"ok": bool(ok), "op": "ik", "frame": "world", "q": q.tolist(), "error": errors,
                "note": "each arm solves its frames with its own six joints within their ranges; no collision check"}

    def _frame_err(self, frame: str, tgt: np.ndarray):
        """Position error (world) and, for a 7-number target, the rotation error as a world-frame rotation vector."""
        i = self.m.site(self.FRAMES[frame]).id
        ep = tgt[:3] - self.d.site_xpos[i]
        if tgt.size != 7:
            return ep, None
        cur = np.zeros(4)
        mujoco.mju_mat2Quat(cur, self.d.site_xmat[i])
        tq = tgt[3:] / np.linalg.norm(tgt[3:])
        qe = np.zeros(4)
        mujoco.mju_mulQuat(qe, tq, np.array([cur[0], -cur[1], -cur[2], -cur[3]]))
        if qe[0] < 0:
            qe = -qe
        er = np.zeros(3)
        mujoco.mju_quat2Vel(er, qe, 1.0)
        return ep, er

    def _ik_arm(self, side, tg: dict, q6, q14, iters, tol_p, tol_r):
        jp, jr = np.zeros((3, self.m.nv)), np.zeros((3, self.m.nv))
        q = np.asarray(q14, float).copy()
        k = 7 * SIDES.index(side)
        lam = 1e-3
        for _ in range(iters):
            q[k:k + 6] = q6
            self._set(q)
            rows, jac, done = [], [], True
            for f, t in tg.items():
                ep, er = self._frame_err(f, t)
                mujoco.mj_jacSite(self.m, self.d, jp, jr, self.m.site(self.FRAMES[f]).id)
                rows.append(ep)
                jac.append(jp[:, self.jv[side]].copy())
                done = done and np.linalg.norm(ep) <= tol_p
                if er is not None:
                    rows.append(er)
                    jac.append(jr[:, self.jv[side]].copy())
                    done = done and np.linalg.norm(er) <= tol_r
            if done:
                break
            e, J = np.concatenate(rows), np.vstack(jac)
            dq = J.T @ np.linalg.solve(J @ J.T + lam * np.eye(J.shape[0]), e)
            n = np.linalg.norm(dq)
            if n > 0.3:
                dq *= 0.3 / n
            q6 = np.clip(q6 + dq, self.lo[side], self.hi[side])
        q[k:k + 6] = q6
        self._set(q)
        errs = {}
        for f, t in tg.items():
            ep, er = self._frame_err(f, t)
            errs[f] = (float(np.linalg.norm(ep)), 0.0 if er is None else float(np.linalg.norm(er)))
        return q6, errs


# ------------------------------------------------------------------ CLI
def _load_traj(path: str) -> np.ndarray:
    return np.asarray(np.load(path, allow_pickle=False)["actions"], dtype=np.float64)


def cmd_replay(a) -> None:
    """Replay a trajectory from the frozen instance, `--repeat` times in this process (the graders run it once per fresh
    process); prints, and with --out writes, the result as JSON. --video renders the first replay (after the verdict)."""
    A = _load_traj(a.traj)
    runs, instance_ok = [], True
    for _ in range(a.repeat):
        s = Session(instance=a.instance)
        instance_ok = instance_ok and bool(s.instance_exact)
        st = s.replay(A)
        runs.append({k: st[k] for k in ("success", "reason", "steps", "state_sha", "replayed_rows", "rows")})
        s.close()
    out = {"n_actions": int(len(A)), "replays": runs, "success": all(r["success"] for r in runs),
           "state_sha": runs[0]["state_sha"] if runs else None, "steps": runs[0]["steps"] if runs else 0,
           "reason": runs[0]["reason"] if runs else None, "instance_ok": instance_ok,
           "deterministic": len({r["state_sha"] for r in runs}) == 1, "video": False}
    if a.out:
        with open(a.out, "w") as f:
            json.dump(out, f)
    if a.video:
        try:
            s = Session(instance=a.instance)
            s.render_video(A, a.video, every=max(1, -(-len(A) // 1500)))
            out["video"] = os.path.isfile(a.video)
            s.close()
        except Exception as exc:  # noqa: BLE001 -- the video never changes the verdict
            _log("video failed:", repr(exc))
        if a.out:
            with open(a.out, "w") as f:
                json.dump(out, f)
    print(json.dumps(out))


def cmd_info(a) -> None:
    s = Session(instance=a.instance)
    print(json.dumps({"family": s.family, "task": s.task, "prompt": s.prompt, "rule": s.rule, "gl": GL,
                      "instance_sha": s.instance_sha, "state_sha": s.state_sha(), "instance_exact": s.instance_exact,
                      "cameras": s.cameras(), "nq": int(s.model.nq), "objects": sorted(s.objects())}))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("replay")
    r.add_argument("--instance", required=True)
    r.add_argument("--traj", required=True)
    r.add_argument("--repeat", type=int, default=1)
    r.add_argument("--video")
    r.add_argument("--out", help="write the result JSON here")
    i = sub.add_parser("info")
    i.add_argument("--instance", required=True)
    a = ap.parse_args()
    {"replay": cmd_replay, "info": cmd_info}[a.cmd](a)


if __name__ == "__main__":
    main()
