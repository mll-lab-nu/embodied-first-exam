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
    # set 3 (2026-10-06)
    "sarc_key_turn": "myoSarcHandKeyTurnFixed-v0",          # key_turn with sarcopenic (weaker) muscles
    "table_tennis": "myoChallengeTableTennisP1-v0",         # MyoChallenge 2025: return a served ball with a paddle
    "bimanual": "myoChallengeBimanual-v0",                  # MyoChallenge 2024: MyoArm hands an object to a robotic arm
    "soccer": "myoChallengeSoccerP1-v0",                    # MyoChallenge 2025: MyoLegs kick the ball into the goal
    "chase_tag": "myoChallengeChaseTagP1-v0",               # MyoChallenge 2023: MyoLegs catch a moving opponent
    "osl_run": "myoChallengeOslRunFixed-v0",                # MyoChallenge 2024: MyoLeg + a prosthetic leg run a track
    "dex_apple_lift": "MyoHandAppleLift-v0",                # MyoDex: track a recorded object motion (GRAB / TCDM)
    "dex_cylinder_pass": "MyoHandCylindersmallPass-v0",
    "dex_bunny_inspect": "MyoHandStanfordbunnyInspect-v0",
    "dex_hammer_use": "MyoHandHammerUse-v0",
    "dex_cup_pour": "MyoHandCupPour-v0",
    "dex_airplane_fly": "MyoHandAirplaneFly-v0",
}
BODY = {t: "arm" if t in ("arm_reach", "relocate") else "hand" for t in TASKS}
BODY.update(table_tennis="body", bimanual="bimanual", soccer="legs", chase_tag="legs", osl_run="osl")
# How an episode is judged (set 3 adds two rules; the first ten families keep "hold"):
#   hold  : MyoSuite's `solved` held HOLD_S seconds in a row; its `done` is a failure.
#   event : a MyoChallenge's own `solved` is its success event and ends the episode (the challenge's official
#           definition: goal scored, opponent tagged, ball returned, object placed, track finished); `done` without it
#           (a fall, out of bounds, the challenge's own time limit) is a failure.
#   track : MyoDex gives no binary success (its `solved` is always 0). The episode is the whole recorded motion; it
#           succeeds iff MyoDex's termination never fires, the object's MOTION follows the reference's (its displacement
#           from where it started within TRACK_POS_M of the reference's displacement from where the reference started,
#           and, where orientation matters, its rotation since the start within TRACK_ROT_RAD of the reference's) at
#           >= TRACK_FRAC of the control steps and at the last one, and the displacement error never exceeds
#           TRACK_MAX_M. Relative, because a reference may start a few centimetres off the resting object (the apple's
#           starts 2.9 cm below it: with absolute errors, leaving the apple on the table passed); the cap, because a
#           small motion (the apple is lifted 6.8 cm) could otherwise be skipped within the 10 % allowance.
RULE = {t: "hold" for t in TASKS}
RULE.update({t: "event" for t in ("table_tennis", "bimanual", "soccer", "chase_tag", "osl_run")})
RULE.update({t: "track" for t in TASKS if t.startswith("dex_")})
HOLD_S["sarc_key_turn"] = 1.0
TRACK_POS_M, TRACK_ROT_RAD, TRACK_FRAC, TRACK_MAX_M = 0.03, 0.5, 0.9, 0.05
TRACK_ROT = {"dex_apple_lift": False, "dex_cylinder_pass": False, "dex_bunny_inspect": True, "dex_hammer_use": True,
             "dex_cup_pour": True, "dex_airplane_fly": True}
# Set 3 families restore every piece of episode state on reset: the env's random generator (opponents, goalkeepers and
# terrains draw from it during reset or the episode) and its Python-side objects (OSL controller, reference cursor,
# opponent policy, ...), deep-copied once after the instance is loaded. The first ten keep their original reset.
STATE_SET3 = {t for t in TASKS if t not in ("key_turn", "obj_hold", "pen_twirl", "die_reorient", "baoding", "hand_reach",
                                             "hand_pose", "obj_reorient", "arm_reach", "relocate")}
_NO_COPY = ("mj_", "obsd_", "robot", "action_space", "observation_space", "spec", "mj_renderer", "_np_random", "np_random",
            "sim", "sim_obsd", "viewer", "renderer")
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
        self._set3 = task in STATE_SET3
        self.rule = RULE[task]
        self._rng0 = copy.deepcopy(self._rng().bit_generator.state) if self._set3 else None
        self.base.reset(seed=0)
        self.model, self.data = self.base.mj_model, self.base.mj_data
        self.nu = int(self.model.nu)
        self.dt = float(self.base.dt)
        self.hold_steps = max(1, int(round(HOLD_S[task] / self.dt))) if task in HOLD_S else 1
        self._renderer = None
        self._image_size = image_size
        self._rec: list[np.ndarray] | None = None
        self.resets = 0
        self.instance_meta: dict[str, Any] = {}
        if instance is not None:
            self.load_instance(instance)
        else:
            self._snapshot = self.snapshot()
        self._extras = self._copy_extras() if self._set3 else {}
        self._rng_after = copy.deepcopy(self._rng().bit_generator.state) if self._set3 else None
        self.track_steps = self._track_steps() if self.rule == "track" else None
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

    def _rng(self):
        g = self.base.np_random
        return getattr(g, "_np_random", g)          # MyoSuite wraps the generator (NPRandomVersionWrapper)

    def _copy_extras(self) -> dict[str, Any]:
        """Set 3: deep copies of the env's Python-side episode state (controllers, opponent policies, the reference
        cursor), taken once after the instance is loaded and put back on every reset. Objects that cannot be copied
        (they hold MuJoCo views) are rebuilt by the env's own reset from the restored random generator."""
        out = {}
        for k, v in vars(self.base).items():
            if k.startswith("__") or _plain(v) or k.startswith(_NO_COPY) or k in ("mujoco_render_frames",):
                continue
            try:
                out[k] = copy.deepcopy(v)
            except Exception:  # noqa: BLE001
                pass
        return out

    def _track_steps(self) -> int:
        t = np.asarray(self.base.ref.reference["time"], dtype=np.float64).reshape(-1)
        return max(1, int(round((t[-1] - t[0]) / self.dt)))

    def snapshot(self) -> dict[str, Any]:
        attrs = {k: copy.deepcopy(v) for k, v in vars(self.base).items()
                 if not k.startswith("__") and _plain(v) and k not in ("mujoco_render_frames",)}
        snap = {"physics": self._phys(), "attrs": attrs, "model": {k: v.copy() for k, v in _model_arrays(self.model).items()}}
        if self._set3 and self.model.nmocap:
            snap["mocap"] = self._mocap()
        return snap

    def _mocap(self) -> np.ndarray:
        # set 3: opponents, goalkeepers and the like are mocap bodies that MyoSuite moves in base.mj_data (the robot's own
        # data keeps them at the origin): part of the state the observations and the success test read
        return np.concatenate([self.data.mocap_pos.ravel(), self.data.mocap_quat.ravel()]).copy()

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
        if "mocap" in snap:
            m = np.asarray(snap["mocap"], dtype=np.float64)
            n = self.model.nmocap
            for d in datas[1:]:
                d.mocap_pos[:] = m[: 3 * n].reshape(n, 3)
                d.mocap_quat[:] = m[3 * n:].reshape(n, 4)
                mj.mj_forward(self.model, d)
        for k, v in snap["attrs"].items():
            setattr(self.base, k, copy.deepcopy(v))
        self.base.robot._sensor_cache.clear()               # readings of the abandoned branch
        self.base.forward()                                 # refresh obs_dict / rwd_dict from the restored state

    def state_sha(self) -> str:
        h = hashlib.sha1(self._phys().tobytes())
        for k, v in sorted(_model_arrays(self.model).items()):
            h.update(k.encode()); h.update(np.ascontiguousarray(v).tobytes())
        if self._set3 and self.model.nmocap:
            h.update(self._mocap().tobytes())
        if self._set3 and self.model.nhfielddata:          # terrains are drawn at reset: part of the instance
            h.update(np.ascontiguousarray(self.model.hfield_data).tobytes())
        return h.hexdigest()[:16]

    def save_instance(self, path: str | Path, meta: dict | None = None) -> None:
        snap = self.snapshot()
        np.savez_compressed(path, task=self.task, env_id=self.env_id, physics=snap["physics"],
                            **{"model__" + k: v for k, v in snap["model"].items()},
                            attrs=json.dumps(_to_json(snap["attrs"])), attr_types=json.dumps(_types(snap["attrs"])),
                            sha=self.state_sha(), meta=json.dumps(meta or {}),
                            **({"mocap": snap["mocap"]} if "mocap" in snap else {}))

    def load_instance(self, path: str | Path) -> None:
        d = np.load(path, allow_pickle=False)
        if str(d["task"]) != self.task:
            raise ValueError(f"instance is for task {str(d['task'])!r}, not {self.task!r}")
        self._snapshot = {"physics": d["physics"], "attrs": _from_json(json.loads(str(d["attrs"])), json.loads(str(d["attr_types"]))),
                          "model": {k[len("model__"):]: d[k] for k in d.files if k.startswith("model__")}}
        if "mocap" in d.files:
            self._snapshot["mocap"] = d["mocap"]
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
        if self._set3:                      # the same draws as the instance's own reset, every episode
            self._rng().bit_generator.state = copy.deepcopy(self._rng0)
        self.base.reset(seed=0)
        self.restore(self._snapshot)
        if self._set3:
            for k, v in self._extras.items():
                setattr(self.base, k, copy.deepcopy(v))
            self._rng().bit_generator.state = copy.deepcopy(self._rng_after)
            self.base.forward()
        self.track_ok = 0
        self.track_max = 0.0
        if self.rule == "track":
            od = self.base.obs_dict
            self._track0 = {k: np.asarray(od[k], dtype=np.float64).reshape(-1).copy()
                            for k in ("curr_obj_com", "targ_obj_com", "curr_obj_rot", "targ_obj_rot")}
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
        failed = bool(np.asarray(info.get("done", False)).any())
        if self.rule == "track":
            pos, rot = self.track_errors()
            ok = pos <= TRACK_POS_M and (not TRACK_ROT[self.task] or rot <= TRACK_ROT_RAD)
            self.track_ok += int(ok)
            self.track_max = max(self.track_max, pos)
            self.last_info.update(track_pos_err=round(pos, 5), track_rot_err=round(rot, 4), track_ok=self.track_ok)
            if failed:
                self.done, self.reason = True, "failure: " + _FAILURE.get(self.task, "task terminated")
            elif self.steps >= self.track_steps:
                self.done = True
                self.success = ok and self.track_ok >= TRACK_FRAC * self.track_steps and self.track_max <= TRACK_MAX_M
                self.reason = "success" if self.success else (
                    f"failure: on track at {self.track_ok} of {self.track_steps} steps"
                    + ("" if ok else ", off track at the end")
                    + (f", {self.track_max:.3f} m off at worst" if self.track_max > TRACK_MAX_M else ""))
        elif self.solved_run >= self.hold_steps and self.task == "bimanual" and not self._bimanual_contacts_ok():
            self.done, self.reason = True, "failure: placed without a clean hand-over (MyoChallenge's contact check)"
        elif self.solved_run >= self.hold_steps:
            self.done, self.success, self.reason = True, True, "success"
        elif failed:
            self.done, self.reason = True, "failure: " + _FAILURE.get(self.task, "task terminated")
        # Baoding's targets come from a precomputed trajectory of 1000 points (baoding_v1.create_goal_trajectory,
        # "assumes that it's greater than env horizon"): with MyoSuite's step budget lifted, step 1001 would index past
        # it (IndexError, board 0086). The episode ends there instead, as a failure unless it succeeded on that step.
        n_goal = len(getattr(self.base, "goal", ())) if self.task == "baoding" else 0
        if not self.done and n_goal and self.steps >= n_goal:
            self.done, self.reason = True, f"failure: the targets' trajectory ends after {n_goal} control steps"
        return not self.done

    def _bimanual_contacts_ok(self) -> bool:
        """MyoChallenge 2024's own evaluation of the object's contact history: the MyoHand held it, then the prosthesis,
        then only the goal pillar, and it never touched the table or the floor (bimanual_v0.evaluate_contact_trajectory)."""
        from myosuite.envs.myo.myochallenge.bimanual_v0 import evaluate_contact_trajectory
        return evaluate_contact_trajectory(self.base.touch_history) is None

    def track_errors(self) -> tuple[float, float]:
        """MyoDex families: how far the object's motion since the episode start is from the reference's: the
        displacement error (m) of the centre of mass and the angle (rad) between the two rotations since the start."""
        od, t0 = self.base.obs_dict, self._track0
        v = lambda k: np.asarray(od[k], dtype=np.float64).reshape(-1)  # noqa: E731
        pos = float(np.linalg.norm((v("curr_obj_com") - t0["curr_obj_com"]) - (v("targ_obj_com") - t0["targ_obj_com"])))
        rot = _quat_angle(_qmul(v("curr_obj_rot"), _qconj(t0["curr_obj_rot"])), _qmul(v("targ_obj_rot"), _qconj(t0["targ_obj_rot"])))
        return pos, rot

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
                "rule": self.rule, "track_steps": self.track_steps, "track_ok": int(getattr(self, "track_ok", 0)),
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

    def actuators(self) -> list[dict]:
        """Every actuator in action order: muscles (`kind` "muscle": the command a maps to the excitation
        1/(1+exp(-5(a-0.5)))) and the few non-muscle ones of some families (`kind` "position" servo or "motor"): their
        command is the raw MuJoCo control in `ctrlrange` (MuJoCo clips it), except where `command` says otherwise."""
        mj, m = self._mj, self.model
        out = []
        for i in range(m.nu):
            name = mj.mj_id2name(m, mj.mjtObj.mjOBJ_ACTUATOR, i)
            if m.actuator_dyntype[i] == mj.mjtDyn.mjDYN_MUSCLE:
                out.append({"index": i, "name": name, "kind": "muscle", "command": "excitation 1/(1+exp(-5(a-0.5)))"})
                continue
            kp, b1 = float(m.actuator_gainprm[i, 0]), float(m.actuator_biasprm[i, 1])
            kind = "position" if b1 != 0 and abs(b1 + kp) < 1e-9 else "motor"
            trn = int(m.actuator_trnid[i, 0])
            target = mj.mj_id2name(m, mj.mjtObj.mjOBJ_JOINT, trn) if m.actuator_trntype[i] == mj.mjtTrn.mjTRN_JOINT else None
            lo, hi = (float(x) for x in m.actuator_ctrlrange[i])
            cmd = (f"position target of joint {target} in [{lo:g}, {hi:g}]" if kind == "position" else
                   f"control in [{lo:g}, {hi:g}] (force or torque = {float(m.actuator_gear[i, 0]):g} x control)")
            if self.task in ("bimanual", "table_tennis"):   # their env's step maps [-1, 1] onto the control range
                cmd = f"normalized: a in [-1, 1] maps linearly onto [{lo:g}, {hi:g}] ({kind} of joint {target})"
            if self.task == "osl_run":             # RunTrack.step overwrites them with the prosthesis's own controller
                cmd = "ignored: the prosthesis's own impedance controller (MyoSuite's OSL state machine) sets it"
            out.append({"index": i, "name": name, "kind": kind, "joint": target, "ctrlrange": [lo, hi], "command": cmd})
        return out

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
            "relocate": "object dropped (palm more than 0.5 m from it)",
            "sarc_key_turn": "fingertips too far from the key", "table_tennis": "the rally ended without a return",
            "bimanual": "object dropped or the time limit passed", "soccer": "fallen, or the time limit passed without a goal",
            "chase_tag": "the opponent was not tagged in time, out of bounds or fallen",
            "osl_run": "fallen, off the track or out of time",
            **{t: "object more than 0.25 m from the reference (or from the wrist)" for t in TASKS if t.startswith("dex_")}}


def _qconj(q):
    q = np.asarray(q, dtype=np.float64)
    return np.array([q[0], -q[1], -q[2], -q[3]]) / max(np.dot(q, q), 1e-12)


def _qmul(a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return np.array([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])


def _quat_angle(a, b) -> float:
    """Angle (rad) of the rotation between two wxyz quaternions."""
    a = a / np.linalg.norm(a); b = b / np.linalg.norm(b)
    return float(2.0 * np.arccos(min(1.0, abs(float(np.dot(a, b))))))


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
