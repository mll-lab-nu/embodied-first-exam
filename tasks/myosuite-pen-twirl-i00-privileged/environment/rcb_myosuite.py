"""
rcb_myosuite.py — task-local tooling for MyoSuite (2.12.2, MuJoCo): the MyoHand (a musculoskeletal model of the human
forearm and hand, 39 muscles) and the MyoArm (shoulder, arm and hand, 34 or 63 muscles). Frozen scene instance / privileged state / muscle-level actions / recording /
fresh-process deterministic replay.

Concepts
--------
instance   : the task's env after `reset(seed=0)` (the `Fixed` / `P1` variants: fixed goal). Instance.npz stores the full
             MuJoCo integration state (solver warm start included), every numeric model array (resets edit the model:
             goal sites, object sizes) and the env's Python-side state; Session(instance=...) builds the env, resets it
             and loads that snapshot. Every episode (reset, replay) starts from it. `state_sha` covers state + model.
action     : one row per control step = 39 real numbers, one per muscle. MyoSuite maps each to the muscle's excitation
             u = 1 / (1 + exp(-5 (a - 0.5))) in (0, 1) and does not clip a: a = -1 gives u ~ 0.0006, a = 0.5 gives 0.5,
             a = 1 gives 0.92, a = 2 gives 0.9994. Muscles only pull; activation follows excitation with a first-order
             delay (~10 ms up, ~40 ms down); one muscle can cross several joints; force also depends on muscle length and
             velocity. There is no joint-level command: turning excitations into motion is the agent's job.
episode    : ends in success once the task's own `solved` flag has held for HOLD_S (1 s; baoding 5 s) of consecutive control steps,
             or in failure at the task's own `done` (object dropped, fingers far from the key, ...). MyoSuite's step
             budget (50-200 steps) is lifted; MAX_STEPS only stops runaway trajectories. MuJoCo on the CPU is
             deterministic: the same rows from the same snapshot give the same final state bit for bit.

CLI
---
  python rcb_myosuite.py make-instance --task key_turn --out instance.npz
  python rcb_myosuite.py replay        --task key_turn --instance instance.npz --traj traj.npz [--repeat N] [--out r.json] [--video replay.mp4]

Python (what the agent gets)
----------------------------
  from rcb_myosuite import Session
  s = Session("key_turn", instance="/app/instance.npz")
  s.reset()                          # back to the frozen instance state (unlimited)
  s.state()                          # the task's observation dict (privileged): hand joints, object / goal poses, errors, ...
  s.muscles(); s.joints()            # muscle and joint names (+ ranges); s.moment_arms() -> (39, nv) at the current pose
  s.model, s.data                    # the MuJoCo model / data, read-only by convention (only actions are replayed)
  s.step(a)                          # one control step: 39 muscle commands (excitation = sigmoid(5 (a-0.5))); False once over
  s.status()                         # {'success', 'done', 'reason', 'steps', 'resets', 'solved_run', 'state_sha', 'info'}
  s.record_start(); ...; A = s.record_stop();  s.replay(A);  s.save_trajectory(A, "/app/output/trajectory.npz")
  s.render_frame("front_view");  s.render_video(A, "/app/output/check.mp4")
"""
from __future__ import annotations

import os
os.environ.setdefault("MUJOCO_GL", "osmesa")
os.environ.setdefault("PYOPENGL_PLATFORM", "osmesa")

import argparse
import copy
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

MAX_STEPS = 10_000_000          # runaway guard only; the wall clock is the budget
# the task's `solved` must hold this long (consecutive control steps) to count. 1 s for a fixed goal, so passing
# through it does not count; baoding's targets circle the palm once every 5 s, so there it is one full orbit (the balls
# must really rotate: parking them where the moving targets sweep past was enough at 0.25 s).
HOLD_S = {"key_turn": 1.0, "obj_hold": 1.0, "pen_twirl": 1.0, "die_reorient": 1.0, "baoding": 5.0,
          "hand_reach": 1.0, "hand_pose": 1.0, "obj_reorient": 1.0, "arm_reach": 1.0, "relocate": 1.0}
TASKS = {
    "key_turn": "myoHandKeyTurnFixed-v0",
    "obj_hold": "myoHandObjHoldFixed-v0",
    "pen_twirl": "myoHandPenTwirlFixed-v0",
    "die_reorient": "myoChallengeDieReorientP1-v0",
    "baoding": "myoChallengeBaodingP1-v1",
    "hand_reach": "myoHandReachFixed-v0",       # all five fingertips to fixed targets
    "hand_pose": "myoHandPoseFixed-v0",         # the hand's 23 joints to a fixed target pose
    "obj_reorient": "myoHandReorient8-v0",      # MyoDex / SAR: reorient one of 8 objects (one frozen draw)
    "arm_reach": "myoArmReachFixed-v0",         # MyoArm (34 muscles): index fingertip to a target in space
    "relocate": "myoChallengeRelocateP1-v0",    # MyoChallenge 2023: MyoArm (63 muscles) moves an object into a box
}
BODY = {t: "arm" if t in ("arm_reach", "relocate") else "hand" for t in TASKS}
_SIMPLE = (bool, int, float, str, type(None), np.integer, np.floating, np.bool_, np.ndarray)
_MODEL_SKIP = ("mesh_", "tex_", "hfield_", "skin_", "name_", "names", "paths", "text_", "flex_", "bvh_", "oct_")

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
    print("[rcb_myosuite]", *a, file=sys.stderr, flush=True)


class PrimitiveError(RuntimeError):
    pass


def _plain(v: Any) -> bool:
    if isinstance(v, _SIMPLE):
        return True
    if isinstance(v, (list, tuple)):
        return all(_plain(x) for x in v)
    if isinstance(v, dict):
        return all(isinstance(k, (str, int)) and _plain(x) for k, x in v.items())
    return False


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


def _jsonable(v: Any) -> Any:
    if isinstance(v, np.ndarray):
        return v.round(6).tolist()
    if isinstance(v, (np.floating,)):
        return round(float(v), 6)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items()}
    return v


def _types(attrs: dict) -> dict:
    def t(v):
        if isinstance(v, np.ndarray):
            return {"nd": str(v.dtype), "shape": list(v.shape)}
        if isinstance(v, (np.bool_, np.integer, np.floating)):
            return {"np": str(np.asarray(v).dtype)}
        if isinstance(v, bool):
            return "bool"
        if isinstance(v, int):
            return "int"
        if isinstance(v, float):
            return "float"
        if isinstance(v, tuple):
            return {"tuple": [t(x) for x in v]}
        if isinstance(v, list):
            return {"list": [t(x) for x in v]}
        if isinstance(v, dict):
            return {"dict": {str(k): t(x) for k, x in v.items()}, "keys": [type(k).__name__ for k in v]}
        return type(v).__name__
    return {k: t(v) for k, v in attrs.items()}


def _to_json(attrs: dict) -> dict:
    def j(v):
        if isinstance(v, np.ndarray):
            return v.tolist()
        if isinstance(v, (np.bool_,)):
            return bool(v)
        if isinstance(v, np.integer):
            return int(v)
        if isinstance(v, np.floating):
            return float(v)
        if isinstance(v, (list, tuple)):
            return [j(x) for x in v]
        if isinstance(v, dict):
            return {str(k): j(x) for k, x in v.items()}
        return v
    return {k: j(v) for k, v in attrs.items()}


def _from_json(vals: dict, types: dict) -> dict:
    def f(v, t):
        if isinstance(t, dict) and "np" in t:
            return np.asarray(v, dtype=t["np"])[()]
        if isinstance(t, dict) and "nd" in t:
            return np.asarray(v, dtype=t["nd"]).reshape(t["shape"])
        if isinstance(t, dict) and "tuple" in t:
            return tuple(f(x, tt) for x, tt in zip(v, t["tuple"]))
        if isinstance(t, dict) and "list" in t:
            return [f(x, tt) for x, tt in zip(v, t["list"])]
        if isinstance(t, dict) and "dict" in t:
            out = {}
            for (k, x), kt in zip(v.items(), t["keys"]):
                out[int(k) if kt == "int" else k] = f(x, t["dict"][k])
            return out
        if t == "bool":
            return bool(v)
        if t == "int":
            return int(v)
        if t == "float":
            return float(v)
        return v
    return {k: f(v, types[k]) for k, v in vals.items()}


class Session:
    """One MyoSuite env on a frozen instance. Every episode starts from the instance snapshot."""

    def __init__(self, task: str, instance: str | Path | None = None, *, max_steps: int = MAX_STEPS,
                 image_size: tuple[int, int] = (480, 640)):
        import mujoco
        from myosuite.utils import gym as mgym
        if task not in TASKS:
            raise KeyError(f"unknown task {task!r}; known: {sorted(TASKS)}")
        self._mj = mujoco
        self.task, self.env_id = task, TASKS[task]
        self.max_steps = int(max_steps)
        self.env = mgym.make(self.env_id)
        self.base = self.env.unwrapped                     # no TimeLimit wrapper: MyoSuite's step budget is lifted
        self.base.seed(0)            # the challenge envs sample goal / mass / size in reset() before reset(seed=) reseeds
        self.base.reset(seed=0)
        self.model, self.data = self.base.mj_model, self.base.mj_data
        self.nu = int(self.model.nu)
        self.dt = float(self.base.dt)
        self.hold_steps = max(1, int(round(HOLD_S[task] / self.dt)))
        self._renderer = None
        self._image_size = image_size
        self._rec: list[np.ndarray] | None = None
        self.resets = 0
        self.instance_meta: dict[str, Any] = {}
        if instance is not None:
            self.load_instance(instance)
        else:
            self._snapshot = self.snapshot()
        self._episode_reset()
        self._total_steps = 0
        _slog("session_start", task=task)
        import atexit
        atexit.register(lambda: _slog("session_end", task=task, resets=self.resets, sim_steps=self._total_steps + self.steps))

    # ------------------------------------------------------------------ snapshots
    # MyoSuite steps the physics in its robot wrapper's own MjData (base.robot.mj_data); base.mj_data / obsd_mj_data are
    # mirrors it refreshes from sensor readings. The snapshot is the robot's data; restore writes it back there and to both
    # mirrors, and base.forward() then re-derives the observations from it.
    def _phys(self) -> np.ndarray:
        mj = self._mj
        sz = mj.mj_stateSize(self.model, mj.mjtState.mjSTATE_INTEGRATION)
        s = np.empty(sz); mj.mj_getState(self.model, self.base.robot.mj_data, s, mj.mjtState.mjSTATE_INTEGRATION)
        return s

    def snapshot(self) -> dict[str, Any]:
        attrs = {k: copy.deepcopy(v) for k, v in vars(self.base).items()
                 if not k.startswith("__") and _plain(v) and k not in ("mujoco_render_frames",)}
        return {"physics": self._phys(), "attrs": attrs, "model": {k: v.copy() for k, v in _model_arrays(self.model).items()}}

    def restore(self, snap: dict[str, Any]) -> None:
        mj = self._mj
        live = _model_arrays(self.model)
        for k, v in snap.get("model", {}).items():
            if k in live and live[k].shape == v.shape:
                live[k][...] = v
        phys = np.asarray(snap["physics"])
        datas = [self.base.robot.mj_data, self.data] + ([self.base.obsd_mj_data] if self.base.obsd_mj_data is not self.data else [])
        for d in datas:
            mj.mj_setState(self.model, d, phys, mj.mjtState.mjSTATE_INTEGRATION)
            mj.mj_forward(self.model, d)
        for k, v in snap["attrs"].items():
            setattr(self.base, k, copy.deepcopy(v))
        self.base.robot._sensor_cache.clear()               # readings of the abandoned branch
        self.base.forward()                                 # refresh obs_dict / rwd_dict from the restored state

    def state_sha(self) -> str:
        h = hashlib.sha1(self._phys().tobytes())
        for k, v in sorted(_model_arrays(self.model).items()):
            h.update(k.encode()); h.update(np.ascontiguousarray(v).tobytes())
        return h.hexdigest()[:16]

    def save_instance(self, path: str | Path, meta: dict | None = None) -> None:
        snap = self.snapshot()
        np.savez_compressed(path, task=self.task, env_id=self.env_id, physics=snap["physics"],
                            **{"model__" + k: v for k, v in snap["model"].items()},
                            attrs=json.dumps(_to_json(snap["attrs"])), attr_types=json.dumps(_types(snap["attrs"])),
                            sha=self.state_sha(), meta=json.dumps(meta or {}))

    def load_instance(self, path: str | Path) -> None:
        d = np.load(path, allow_pickle=False)
        if str(d["task"]) != self.task:
            raise ValueError(f"instance is for task {str(d['task'])!r}, not {self.task!r}")
        self._snapshot = {"physics": d["physics"], "attrs": _from_json(json.loads(str(d["attrs"])), json.loads(str(d["attr_types"]))),
                          "model": {k[len("model__"):]: d[k] for k in d.files if k.startswith("model__")}}
        self.instance_meta = json.loads(str(d["meta"]))
        self.restore(self._snapshot)
        self.instance_sha = str(d["sha"])
        self.instance_exact = self.state_sha() == self.instance_sha
        if not self.instance_exact:
            _log(f"WARNING: restored state sha {self.state_sha()} != instance sha {self.instance_sha}")

    # ------------------------------------------------------------------ episode
    def _episode_reset(self) -> None:
        # a full env reset first: MyoSuite's robot wrapper caches sensor readings outside mjData (not in the snapshot),
        # so restoring the snapshot alone left the previous episode's key angle / object pose in the observations
        self.base.reset(seed=0)
        self.restore(self._snapshot)
        self.steps = 0
        self.done = False
        self.success = False
        self.reason: str | None = None
        self.solved_run = 0
        self.last_info: dict[str, Any] = {}

    def reset(self) -> None:
        """Back to the frozen instance state (unlimited). Starts a new episode."""
        _slog("reset", task=self.task, n=self.resets + 1, sim_steps_before=self.steps)
        self._total_steps += self.steps
        self._episode_reset()
        self.resets += 1

    def step(self, action) -> bool:
        """One control step with 39 muscle commands a (excitation = sigmoid(5 (a - 0.5))). True while the episode runs."""
        a = np.asarray(action, dtype=np.float64).reshape(-1)
        if a.shape != (self.nu,):
            raise ValueError(f"action must have {self.nu} muscle commands, got {a.shape}")
        if not np.all(np.isfinite(a)):
            raise ValueError("action contains NaN or inf")
        if self.done:
            raise PrimitiveError(f"episode is over ({self.reason}); call reset()")
        if self.steps >= self.max_steps:
            raise PrimitiveError(f"runaway guard: {self.max_steps} steps")
        _, _, terminated, _, info = self.base.step(a)
        self.steps += 1
        if self._rec is not None:
            self._rec.append(a.copy())
        solved = bool(np.asarray(info.get("solved", False)).any())
        self.solved_run = self.solved_run + 1 if solved else 0
        self.last_info = {k: _jsonable(v) for k, v in dict(info).items() if k in ("solved", "done", "rwd_sparse", "rwd_dense")}
        self.last_info["solved_run"] = self.solved_run
        if self.solved_run >= self.hold_steps:
            self.done, self.success, self.reason = True, True, "success"
        elif bool(np.asarray(info.get("done", False)).any()):
            self.done, self.reason = True, "failure: " + _FAILURE.get(self.task, "task terminated")
        return not self.done

    def rest_action(self) -> np.ndarray:
        """All muscles relaxed (a = -1: excitation ~0.0006)."""
        return -np.ones(self.nu)

    @staticmethod
    def excitation(a):
        """MyoSuite's command -> excitation map, u = 1 / (1 + exp(-5 (a - 0.5)))."""
        return 1.0 / (1.0 + np.exp(-5.0 * (np.asarray(a, float) - 0.5)))

    @staticmethod
    def command_for(u):
        """Inverse of excitation(): the command a that gives excitation u in (0, 1)."""
        u = np.clip(np.asarray(u, float), 1e-6, 1 - 1e-6)
        return 0.5 + np.log(u / (1 - u)) / 5.0

    def status(self) -> dict[str, Any]:
        return {"success": bool(self.success), "done": bool(self.done), "reason": self.reason, "steps": int(self.steps),
                "resets": int(self.resets), "solved_run": int(self.solved_run), "hold_steps": int(self.hold_steps),
                "state_sha": self.state_sha(), "info": self.last_info}

    # ------------------------------------------------------------------ recording / replay
    def record_start(self) -> None:
        self._rec = []

    def record_stop(self) -> np.ndarray:
        rec, self._rec = self._rec or [], None
        _slog("record", task=self.task, n_actions=len(rec), success=bool(self.success))
        return np.asarray(rec, dtype=np.float64).reshape(-1, self.nu)

    def save_trajectory(self, actions, path: str | Path, meta: dict | None = None) -> None:
        A = np.asarray(actions, dtype=np.float64)
        if A.ndim != 2 or A.shape[1] != self.nu:
            raise ValueError(f"trajectory must be (T, {self.nu}), got {A.shape}")
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        np.savez(path, actions=A, task=self.task, instance_sha=getattr(self, "instance_sha", ""), meta=json.dumps(meta or {}))

    def replay(self, actions) -> dict[str, Any]:
        """Reset to the instance and replay open-loop until the episode ends or the rows run out."""
        A = np.asarray(actions, dtype=np.float64)
        self.reset()
        n = 0
        for row in A:
            n += 1
            if not self.step(row):
                break
        st = self.status(); st["replayed_rows"] = n; st["rows"] = int(len(A))
        _slog("replay", task=self.task, n_actions=int(len(A)), success=st["success"])
        return st

    # ------------------------------------------------------------------ privileged state
    def state(self) -> dict[str, list]:
        """The task's observation dict (privileged): hand joints and velocities, object / goal / target poses and
        their errors, muscle activations (`act`)."""
        return {k: np.asarray(v, float).reshape(-1).round(6).tolist() for k, v in self.base.obs_dict.items() if k != "time"}

    def muscles(self) -> list[dict]:
        mj, m = self._mj, self.model
        return [{"index": i, "name": mj.mj_id2name(m, mj.mjtObj.mjOBJ_ACTUATOR, i),
                 "ctrlrange": m.actuator_ctrlrange[i].round(3).tolist()} for i in range(m.nu)]

    def joints(self) -> list[dict]:
        mj, m = self._mj, self.model
        return [{"index": j, "name": mj.mj_id2name(m, mj.mjtObj.mjOBJ_JOINT, j), "qpos_adr": int(m.jnt_qposadr[j]),
                 "dof_adr": int(m.jnt_dofadr[j]), "range": m.jnt_range[j].round(3).tolist(), "qpos": float(self.data.qpos[m.jnt_qposadr[j]])}
                for j in range(m.njnt) if m.jnt_type[j] in (2, 3)]

    def moment_arms(self) -> np.ndarray:
        """(nu, nv) muscle moment arms at the current pose (d muscle length / d q, MuJoCo's actuator_moment)."""
        mj, m, d = self._mj, self.model, self.data
        if hasattr(d, "actuator_moment") and d.actuator_moment.ndim == 2:
            return d.actuator_moment.copy()
        out = np.zeros((m.nu, m.nv))
        mj.mju_sparse2dense(out, d.actuator_moment, d.moment_rownnz, d.moment_rowadr, d.moment_colind)
        return out

    # ------------------------------------------------------------------ rendering (on demand)
    def cameras(self) -> list[str]:
        mj = self._mj
        return [mj.mj_id2name(self.model, mj.mjtObj.mjOBJ_CAMERA, i) for i in range(self.model.ncam)]

    def default_camera(self) -> str:
        return "front_view" if "front_view" in self.cameras() else self.cameras()[0]

    def render_frame(self, camera: str | None = None, size: tuple[int, int] | None = None) -> np.ndarray:
        mj = self._mj
        h, w = size or self._image_size
        if self._renderer is None or (self._renderer.height, self._renderer.width) != (h, w):
            if self._renderer is not None:
                self._renderer.close(); self._renderer = None   # a second OSMesa context next to a live one reads garbage
            self.model.vis.global_.offheight = max(self.model.vis.global_.offheight, h)
            self.model.vis.global_.offwidth = max(self.model.vis.global_.offwidth, w)
            self._renderer = mj.Renderer(self.model, height=h, width=w)
        self._renderer.update_scene(self.data, camera=camera or self.default_camera())
        return self._renderer.render().copy()

    def render_video(self, actions, path: str | Path, *, cameras: list[str] | None = None, every: int = 1, fps: int = 25,
                     size: tuple[int, int] = (240, 320)) -> dict[str, Any]:
        import imageio.v2 as imageio
        A = np.asarray(actions, dtype=np.float64)
        self.reset()
        cams = cameras or [c for c in ("hand_top", "hand_side_inter") if c in self.cameras()] or [self.default_camera()]
        w = imageio.get_writer(str(path), fps=fps, codec="libx264", quality=7, macro_block_size=8)
        try:
            w.append_data(np.concatenate([self.render_frame(c, size) for c in cams], axis=1))
            for i, row in enumerate(A):
                running = self.step(row)
                if i % every == 0 or not running:
                    w.append_data(np.concatenate([self.render_frame(c, size) for c in cams], axis=1))
                if not running:
                    break
        finally:
            w.close()
        return self.status()

    def close(self) -> None:
        try:
            self.env.close()
        except Exception:
            pass


_FAILURE = {"key_turn": "fingertips too far from the key", "obj_hold": "object dropped", "pen_twirl": "pen dropped",
            "die_reorient": "die dropped", "baoding": "a ball dropped or left its target", "pose": "task terminated", "hand_reach": "fingertips too far from their targets", "hand_pose": "hand pose too far from the target",
            "obj_reorient": "object dropped", "arm_reach": "fingertip too far from the target",
            "relocate": "object dropped (palm more than 0.5 m from it)"}


def _load_traj(path: str) -> np.ndarray:
    return np.asarray(np.load(path, allow_pickle=False)["actions"], dtype=np.float64)


def cmd_make_instance(a) -> None:
    s = Session(a.task)
    s.save_instance(a.out, {"source": f"{TASKS[a.task]} after reset(seed=0)", "myosuite": "2.12.2"})
    _log("instance", a.out, "sha", s.state_sha())


def cmd_replay(a) -> None:
    """Replay a trajectory from the frozen instance, `--repeat` times in this process (the graders run it once per fresh
    process); prints, and with --out writes, the result as JSON. --video renders the first replay (after the verdict)."""
    A = _load_traj(a.traj)
    a.task = a.task or str(np.load(a.instance, allow_pickle=False)["task"])
    runs, instance_ok = [], True
    for _ in range(a.repeat):
        s = Session(a.task, instance=a.instance)
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
            s = Session(a.task, instance=a.instance)
            s.render_video(A, a.video, every=max(1, -(-len(A) // 1500)))
            out["video"] = os.path.isfile(a.video)
            s.close()
        except Exception as exc:  # noqa: BLE001 -- the video never changes the verdict
            _log("video failed:", repr(exc))
        if a.out:
            with open(a.out, "w") as f:
                json.dump(out, f)
    print(json.dumps(out))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make-instance"); m.add_argument("--task", required=True); m.add_argument("--out", required=True)
    r = sub.add_parser("replay"); r.add_argument("--task", help="default: the instance's task"); r.add_argument("--instance", required=True)
    r.add_argument("--traj", required=True); r.add_argument("--repeat", type=int, default=1); r.add_argument("--video")
    r.add_argument("--out", help="write the result JSON here")
    a = ap.parse_args()
    {"make-instance": cmd_make_instance, "replay": cmd_replay}[a.cmd](a)


if __name__ == "__main__":
    main()
