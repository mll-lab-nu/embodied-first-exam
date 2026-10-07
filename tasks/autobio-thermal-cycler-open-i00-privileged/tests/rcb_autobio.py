"""Robot Coding Bench tooling for the AutoBio tasks (privileged mode, the verifier's replays and the standard-mode
service all use this one module).

AutoBio (autobio-bench/AutoBio, MuJoCo 3.3.0) comes from the base image, with its scripted experts removed
(images/autobio/strip_experts.py); this module imports it from $AUTOBIO_ROOT and adds what a task needs:

    from rcb_autobio import Session
    s = Session(instance="/app/instance.json")
    s.reset(); s.step(a); s.status(); s.replay(actions); s.save_trajectory(actions, "/app/output/trajectory.npz")

- The scene is AutoBio's own: `Task(Task.load())` then `reset(seed)` with the instance's seed. Every load checks the
  hash of the compiled model and of the initial state against the instance (`instance_ok`).
- One control step is one physics step (2 ms): a row holds one position target per controlled actuator (AutoBio's
  `action_indices`), clipped to the actuator's range, written to `data.ctrl`, then AutoBio's own `manager.step()` runs.
  AutoBio's experts write their targets at arbitrary physics steps, so this is the rate at which their runs replay
  bit for bit.
- The verdict is AutoBio's own `check()`, evaluated after every control step. Rule `first` (AutoBio's `early_stop`
  tasks): the first step at which it holds ends the episode as a success. Rule `final` (the thermal mixer, whose
  `check()` is a score in [0, 1]): the episode is judged where it ends, success = score 1. A physics warning from
  MuJoCo (unstable state) ends the episode as a failure, as AutoBio's evaluator does.
- An episode lasts at most MAX_STEPS control steps (1200 s of simulated time), a technical cap that bounds the grader's
  replays; rule `final` is judged there, rule `first` has not succeeded by then.
- Nothing here calls mj_forward on the live MjData: observations (camera poses, tool poses, rendering) are computed on
  a scratch copy, so looking never changes the physics.

CLI:  python rcb_autobio.py replay --instance I --traj T [--out O.json] [--video V.mp4] [--repeat N]
      python rcb_autobio.py facts --family F --seed S
"""

from __future__ import annotations

import argparse
import atexit
import contextlib
import copy
import hashlib
import importlib
import json
import math
import os
import re
import sys
import time
import warnings

import numpy as np

ROOT = os.environ.get("AUTOBIO_ROOT", "/opt/AutoBio/autobio")
SESSION_LOG = os.environ.get("RCB_SESSION_LOG", "/app/output/rcb_session_log.jsonl")
CONTROL_DT = 0.002  # one control step = one physics step
MAX_STEPS = 600_000  # an episode lasts at most 1200 s of simulated time (a technical cap: it bounds the grader's replays)
W, H = 640, 480
# family (AutoBio's task id) -> (module, task class, rule)
FAMILIES = {
    "pickup": ("pickup_centrifuge_tube", "Pickup", "first"),
    "thermal_cycler_close": ("mani_thermal_cycler", "ThermalCyclerManipulate", "first"),
    "thermal_cycler_open": ("mani_thermal_cycler", "ThermalCyclerManipulate", "first"),
    "pipette": ("mani_pipette", "Pipette", "first"),
    "screw_loose": ("screw_loosen", "ScrewLoose", "first"),
    "screw_tighten": ("screw_tighten", "ScrewTighten", "first"),
    "insert": ("transfer_centrifuge_tube", "Insert", "first"),
    "thermal_mixer": ("mani_thermal_mixer", "ThermalMixerManipulate", "final"),
    "insert_centrifuge_5430": ("load_centrifuge_5430", "InsertCentrifuge5430", "first"),
}
GL2CV = np.diag([1.0, -1.0, -1.0, 1.0])
PAD_CLOSED_M = 0.0144  # Robotiq 2F-85: distance between the two pad bodies when the empty gripper is closed


@contextlib.contextmanager
def _in_root():
    """AutoBio loads its MuJoCo plugin and some assets by paths relative to its own directory."""
    cwd = os.getcwd()
    os.chdir(ROOT)
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    try:
        yield
    finally:
        os.chdir(cwd)


def _log(ev: dict) -> None:
    """The agent-side interaction log (self-reported cost; never evidence)."""
    if not SESSION_LOG:
        return
    try:
        os.makedirs(os.path.dirname(SESSION_LOG), exist_ok=True)
        with open(SESSION_LOG, "a") as f:
            f.write(json.dumps({"t": round(time.time(), 3), **ev}) + "\n")
    except OSError:
        pass


def _clean(name: str, prefix: str = "") -> str:
    s = name[len(prefix):] if prefix and name.startswith(prefix) else name
    if s.startswith("left/"):  # AutoBio instantiates ALOHA's left arm for every ALOHA arm
        s = s[5:]
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")


class Arm:
    """One arm of the scene, read from AutoBio's helper object (`task.arm`, or `task.arm1` / `task.arm2`)."""

    def __init__(self, model, key: str, helper, n_arms: int):
        self.key = key
        self.label = "" if n_arms == 1 else f"{key}_"
        self.prefix = helper.prefix
        self.site = helper.site_name
        self.base = helper.base_name
        j0 = model.joint(helper.jnt_name).id
        self.joint_ids = list(range(j0, j0 + int(helper.dof)))
        self.qadr = np.array([int(model.jnt_qposadr[j]) for j in self.joint_ids])
        self.vadr = np.array([int(model.jnt_dofadr[j]) for j in self.joint_ids])
        self.robot_joint_ids = [j for j in range(model.njnt) if model.joint(j).name.startswith(self.prefix)]
        self.kind = "aloha" if "aloha" in self.prefix else "ur5e"
        self.tcp = f"{self.label}tcp"


class PanelTexture:
    """The thermal mixer's display. AutoBio draws the panel's state with matplotlib (`ui_state.draw`) and its evaluator
    uploads the drawing as the display's texture; that helper (`evaluator.make_thermal_mixer_extra`) stops redrawing for
    good once two frames in a row find the panel unchanged, so every later frame would show a stale display. This does
    the same drawing with AutoBio's own calls and redraws whenever the panel's state differs from the last one drawn."""

    def __init__(self, mj, model, mixer):
        self._mj, self.mixer = mj, mixer
        self.model = copy.deepcopy(model)  # the texture's pixels are edited in a copy, never in the simulated model
        self.fig, self.ax = mixer.ui_state.make_canvas()
        self.drawn = None

    def update(self, _scene, context) -> None:
        ui = self.mixer.ui_state
        if self.drawn is not None and self.drawn == ui:
            return
        ui.draw(self.ax)
        self.model.tex(self.mixer.display).data[...] = ui.render_canvas(self.fig)
        self._mj.mjr_uploadTexture(self.model, context, self.mixer.display)
        self.drawn = copy.deepcopy(ui)

    def finish(self) -> None:
        import matplotlib.pyplot as plt

        plt.close(self.fig)


class Session:
    def __init__(self, family: str | None = None, instance: str = "/app/instance.json"):
        import mujoco

        self._mj = mujoco
        self.instance = json.load(open(instance))
        self.family = family or self.instance["family"]
        if self.family != self.instance["family"] or self.family not in FAMILIES:
            raise ValueError(f"family {self.family!r} does not match the instance ({self.instance['family']!r})")
        mod, cls, self.rule = FAMILIES[self.family]
        self.seed = int(self.instance["seed"])
        with _in_root():
            T = getattr(importlib.import_module(mod), cls)
            self.task = T(T.load())
            self.task.task = self.family  # the thermal cycler's module serves two tasks and reads this in reset()
        self.dt = CONTROL_DT
        self.resets = -1
        self.total_steps = 0
        self._rec = None
        self._renderer = None
        self._rsize = None
        self._extras = None
        self._view_key = None
        self._reset_task()
        m = self.model
        assert abs(float(m.opt.timestep) - CONTROL_DT) < 1e-12, m.opt.timestep
        helpers = [(k, getattr(self.task, k)) for k in ("arm", "arm1", "arm2") if getattr(self.task, k, None) is not None]
        self.arms = [Arm(m, k, h, len(helpers)) for k, h in helpers]
        self.n_act = len(self.act_idx)
        self.lo = m.actuator_ctrlrange[self.act_idx, 0].copy()
        self.hi = m.actuator_ctrlrange[self.act_idx, 1].copy()
        self.act_names = [self._act_name(i) for i in self.act_idx]
        self._kd = mujoco.MjData(m)  # observations: the live state copied, kinematics recomputed (never the live data)
        self._k0 = mujoco.MjData(m)  # stateless kinematics: the initial configuration with the arm joints replaced
        self._copy_state(self._k0)
        self._cams = self._camera_names()
        self.model_sha = self._model_sha()
        self.init_sha = self.state_sha()
        self.instance_ok = bool(
            self.model_sha == self.instance.get("model_sha") and self.init_sha == self.instance.get("init_sha")
        )
        atexit.register(self.close)
        _log({"ev": "session_start", "family": self.family, "instance_ok": self.instance_ok})

    # ------------------------------------------------------------------------------------------- episode
    def _reset_task(self) -> None:
        rng = np.random.get_state()  # AutoBio seeds numpy's global generator in reset(); the caller's stream is kept
        with _in_root():
            self.info = self.task.reset(seed=self.seed)
        np.random.set_state(rng)
        self.model, self.data = self.task.model, self.task.data
        self.act_idx = np.asarray(self.info["action_indices"], dtype=int).ravel()
        self.resets += 1
        self.steps = 0
        self.done = False
        self.success = False
        self.reason = None
        self._view_key = None
        self._drop_extras()  # the render helpers hold references into the task's state
        self.score = float(self.task.check())

    def reset(self) -> None:
        """Back to the frozen initial state (AutoBio's reset with the instance's seed)."""
        self._reset_task()
        if self._rec is not None:
            self._rec = []
        _log({"ev": "reset"})

    def _judge(self) -> None:
        self.score = float(self.task.check())
        w = self.data.warning.number.copy()
        w[int(self._mj.mjtWarning.mjWARN_VGEOMFULL)] = 0  # a renderer's warning, not a physics one
        if w.any():
            self.done, self.success, self.reason = True, False, "failure: simulator warning (unstable state)"
        elif self.rule == "first":
            if self.score >= 1.0:
                self.done, self.success, self.reason = True, True, "success"
        else:
            self.success = self.score >= 1.0

    def step(self, a, n: int = 1) -> bool:
        """One control step (2 ms) with the position targets `a` (one per controlled actuator), or `n` steps holding
        them. Returns False once the episode is over (then nothing is executed until reset())."""
        a = np.asarray(a, dtype=np.float64).reshape(-1)
        if a.shape[0] != self.n_act or not np.all(np.isfinite(a)):
            raise ValueError(f"an action is {self.n_act} finite numbers, got shape {a.shape}")
        if self.done:
            return False
        c = np.clip(a, self.lo, self.hi)
        for _ in range(int(n)):
            self.data.ctrl[self.act_idx] = c
            self.task.manager.step()
            self.steps += 1
            self.total_steps += 1
            if self._rec is not None:
                self._rec.append(c.copy())
            self._judge()
            if not self.done and self.steps >= MAX_STEPS:  # rule `final` is judged here; rule `first` has not succeeded
                self.done, self.reason = True, "max_control_steps"
            if self.done:
                break
        return not self.done

    def command(self) -> np.ndarray:
        """The position targets in effect (after reset: the targets that hold the initial pose)."""
        return self.data.ctrl[self.act_idx].copy()

    def status(self) -> dict:
        return {
            "family": self.family,
            "rule": self.rule,
            "success": bool(self.success),
            "done": bool(self.done),
            "reason": self.reason,
            "score": float(self.score),
            "steps": int(self.steps),
            "sim_time_s": round(self.steps * CONTROL_DT, 6),
            "resets": int(self.resets),
            "state_sha": self.state_sha(),
            "instance_ok": bool(self.instance_ok),
            "model_sha": self.model_sha,
            "init_sha": self.init_sha,
        }

    def record_start(self) -> None:
        self._rec = []

    def record_stop(self) -> np.ndarray:
        rows = np.asarray(self._rec or [], dtype=np.float64).reshape(-1, self.n_act)
        self._rec = None
        _log({"ev": "record", "rows": int(len(rows))})
        return rows

    def _rows(self, actions) -> np.ndarray:
        A = np.asarray(actions, dtype=np.float64)
        if A.ndim != 2 or A.shape[1] != self.n_act or not np.all(np.isfinite(A)):
            raise ValueError(f"a trajectory is a finite (T, {self.n_act}) array, got {A.shape}")
        return A

    def replay(self, actions, video: str | None = None, cameras=None, fps: int = 25) -> dict:
        """Reset, then execute the rows open-loop, one per control step, until the episode ends or the rows do; returns
        status(). This is what the grader does (in two fresh processes)."""
        A = self._rows(actions)
        rec, self._rec = self._rec, None
        self._reset_task()
        # real time at `fps`, or a time lapse when that would be more than 1500 frames
        frames, every = [], max(int(round(1.0 / (fps * CONTROL_DT))), -(-len(A) // 1500), 1)
        cams = list(cameras or self.default_cameras()) if video else []
        for k, row in enumerate(A):
            if video and k % every == 0:
                frames.append(np.hstack([self.render_frame(c) for c in cams]))
            if not self.step(row):
                break
        out = self.status()
        if video:
            frames.append(np.hstack([self.render_frame(c) for c in cams]))
            out["video"] = _write_video(video, frames, fps)
        self._rec = rec
        _log({"ev": "replay", "rows": int(len(A)), "success": out["success"]})
        return out

    def save_trajectory(self, actions, path: str, meta: dict | None = None) -> None:
        A = self._rows(actions)
        if len(A) > MAX_STEPS:
            raise ValueError(f"a trajectory has at most {MAX_STEPS} rows ({MAX_STEPS * CONTROL_DT:g} s of simulated time), got {len(A)}")
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        np.savez_compressed(path, actions=A, task=self.family, meta=json.dumps(meta or {}))

    def render_video(self, actions, path: str, cameras=None, fps: int = 25) -> dict:
        return self.replay(actions, video=path, cameras=cameras, fps=fps)

    # ------------------------------------------------------------------------------------------- hashes
    def _model_sha(self) -> str:
        mj = self._mj
        buf = np.zeros(mj.mj_sizeModel(self.model), dtype=np.uint8)
        mj.mj_saveModel(self.model, None, buf)
        return hashlib.sha256(buf.tobytes()).hexdigest()[:16]

    def _verdict_state(self) -> dict:
        out = {"steps": int(self.steps), "success": bool(self.success), "score": round(float(self.score), 12)}
        for k, v in sorted(vars(self.task).items()):  # the task's own flags (e.g. the pipette's below_liquid)
            if isinstance(v, (bool, int, float, str)) and not k.startswith("_"):
                out[f"task.{k}"] = v
        ui = getattr(getattr(self.task, "instrument", None), "ui_state", None)
        mp = getattr(ui, "main_parameter", None)
        if mp is not None:  # the thermal mixer's settings live in its panel, not in MjData
            out["panel"] = [int(mp.time.seconds), float(mp.set_temperature), int(mp.frequency)]
        return out

    def state_sha(self) -> str:
        """Hash of the full simulation state (MuJoCo's integration state: time, positions, velocities, controls,
        constraint switches, plugin and warm-start state) and of the task's own verdict state."""
        mj = self._mj
        spec = mj.mjtState.mjSTATE_INTEGRATION
        st = np.zeros(mj.mj_stateSize(self.model, spec))
        mj.mj_getState(self.model, self.data, st, spec)
        h = hashlib.sha256(st.tobytes())
        h.update(json.dumps(self._verdict_state(), sort_keys=True).encode())
        return h.hexdigest()[:16]

    # ------------------------------------------------------------------------------------------- the robot
    def _arm_of(self, name: str) -> Arm | None:
        best = None
        for a in self.arms:  # the longest matching prefix ("1/ur:" before "/ur:")
            if name.startswith(a.prefix) and (best is None or len(a.prefix) > len(best.prefix)):
                best = a
        return best

    def _act_name(self, i: int) -> str:
        n = self.model.actuator(int(i)).name
        a = self._arm_of(n)
        return (a.label + _clean(n, a.prefix)) if a else _clean(n)

    def _joint_name(self, j: int) -> str:
        n = self.model.joint(int(j)).name
        a = self._arm_of(n)
        return (a.label + _clean(n, a.prefix)) if a else _clean(n)

    def _link_name(self, b: int) -> str:
        n = self.model.body(int(b)).name
        a = self._arm_of(n)
        return (a.label + _clean(n, a.prefix)) if a else _clean(n)

    def actuators(self) -> list:
        """The controlled actuators in action order: MuJoCo position actuators (force = kp (target - q) - kv qdot)."""
        m, out = self.model, []
        for k, i in enumerate(self.act_idx):
            i = int(i)
            tendon = int(m.actuator_trntype[i]) == int(self._mj.mjtTrn.mjTRN_TENDON)
            tid = int(m.actuator_trnid[i][0])
            if tendon:
                kind, unit, drives = "gripper", "0 (open) .. 255 (closed)", m.tendon(tid).name
            else:
                slide = int(m.jnt_type[tid]) == int(self._mj.mjtJoint.mjJNT_SLIDE)
                kind, unit, drives = ("gripper" if slide else "joint"), ("m" if slide else "rad"), m.joint(tid).name
            a = self._arm_of(m.actuator(i).name)
            out.append({
                "index": k, "name": self.act_names[k], "mujoco_name": m.actuator(i).name, "kind": kind, "unit": unit,
                "drives": drives, "arm": a.key if a else None,
                "range": [float(self.lo[k]), float(self.hi[k])],
                "kp": float(m.actuator_gainprm[i][0]), "kv": float(-m.actuator_biasprm[i][2]) + 0.0,
                "force_range": [float(v) for v in m.actuator_forcerange[i]] if m.actuator_forcelimited[i] else None,
            })
        return out

    def robot_joints(self) -> list:
        """Every joint of the robot(s): the arm joints, then the gripper's or the hand's, per arm."""
        m, out = self.model, []
        for a in self.arms:
            for j in a.robot_joint_ids:
                slide = int(m.jnt_type[j]) == int(self._mj.mjtJoint.mjJNT_SLIDE)
                out.append({
                    "name": self._joint_name(j), "mujoco_name": m.joint(j).name, "arm": a.key,
                    "group": "arm" if j in a.joint_ids else "hand",
                    "qpos_adr": int(m.jnt_qposadr[j]), "dof_adr": int(m.jnt_dofadr[j]),
                    "type": "prismatic" if slide else "revolute", "unit": "m" if slide else "rad",
                    "range": [float(v) for v in m.jnt_range[j]] if m.jnt_limited[j] else None,
                })
        return out

    def kinematic_joints(self) -> list:
        """The arm joints the kinematics take, in q order (6 per arm)."""
        return [self._joint_name(j) for a in self.arms for j in a.joint_ids]

    def _view(self):
        """A scratch MjData holding the current state with its kinematics recomputed."""
        key = (self.resets, self.steps)
        if self._view_key != key:
            self._copy_state(self._kd)
            self._view_key = key
        return self._kd

    def _copy_state(self, dst) -> None:
        """The live state into a scratch MjData, with positions, cameras and tendons recomputed there."""
        mj = self._mj
        spec = mj.mjtState.mjSTATE_INTEGRATION
        st = np.zeros(mj.mj_stateSize(self.model, spec))
        mj.mj_getState(self.model, self.data, st, spec)
        mj.mj_setState(self.model, dst, st, spec)
        mj.mj_kinematics(self.model, dst)
        mj.mj_comPos(self.model, dst)
        mj.mj_camlight(self.model, dst)
        mj.mj_tendon(self.model, dst)

    def _site_pose(self, d, site: str) -> list:
        sid = self.model.site(site).id
        quat = np.zeros(4)
        self._mj.mju_mat2Quat(quat, d.site_xmat[sid])
        return [*d.site_xpos[sid].tolist(), *quat.tolist()]

    def tcp_poses(self) -> dict:
        """{frame: [x, y, z, qw, qx, qy, qz]} of each arm's tool frame in the world frame, at the current state."""
        d = self._view()
        return {a.tcp: self._site_pose(d, a.site) for a in self.arms}

    def gripper_openings(self) -> dict:
        """Metres between the fingertips, per gripper (the pipette arm's hand is not a gripper)."""
        m, d, out = self.model, self._view(), {}
        for a in self.arms:
            if a.kind == "aloha":
                out[f"{a.label}gripper"] = float(
                    d.qpos[m.joint(a.prefix + "left/left_finger").qposadr[0]]
                    + d.qpos[m.joint(a.prefix + "left/right_finger").qposadr[0]]
                )
            elif self._mj.mj_name2id(m, self._mj.mjtObj.mjOBJ_BODY, a.prefix + "2f85:left_pad") >= 0:
                lp, rp = d.xpos[m.body(a.prefix + "2f85:left_pad").id], d.xpos[m.body(a.prefix + "2f85:right_pad").id]
                out[f"{a.label}gripper"] = float(np.linalg.norm(lp - rp) - PAD_CLOSED_M)
        return out

    def _fk0(self, q) -> None:
        q = np.asarray(q, dtype=np.float64).reshape(-1)
        qadr = np.concatenate([a.qadr for a in self.arms])
        if q.shape[0] != len(qadr):
            raise ValueError(f"q is {len(qadr)} joint positions ({self.kinematic_joints()})")
        self._k0.qpos[qadr] = q
        self._mj.mj_kinematics(self.model, self._k0)
        self._mj.mj_comPos(self.model, self._k0)
        self._mj.mj_camlight(self.model, self._k0)

    def _link_pose(self, d, link: str) -> list:
        for a in self.arms:
            if link == a.tcp:
                return self._site_pose(d, a.site)
        b = self._links()[link]
        return [*d.xpos[b].tolist(), *d.xquat[b].tolist()]

    def _links(self) -> dict:
        """Bodies the kinematics answer for besides the tool frames: the links the wrist cameras are mounted on."""
        m, out = self.model, {}
        for c in range(m.ncam):
            b = int(m.cam_bodyid[c])
            if int(m.body_weldid[b]) != 0:
                out[self._link_name(b)] = b
        return out

    def fk(self, q, links=None) -> dict:
        """Tool frames and camera-mount links (world frame; x y z + wxyz quaternion) for arm joint positions `q` (see
        kinematic_joints()); every other joint as at the start. Stateless: the simulation is not touched."""
        self._fk0(q)
        names = list(links or (self.tcp_frames() + list(self._links())))
        return {n: self._link_pose(self._k0, n) for n in names}

    def tcp_frames(self) -> list:
        return [a.tcp for a in self.arms]

    def ik(self, targets: dict, seed=None, tol_pos_m: float = 1e-3, tol_rot_rad: float = 1e-2, max_iters: int = 300) -> dict:
        """Arm joint positions that put tool frames at `targets` ({frame: [x, y, z, qw, qx, qy, qz]}, world frame):
        damped least squares on each arm's 6 joints within their ranges, no collision checking. `tol_rot_rad` >= 3.1
        ignores orientation. Returns {"ok", "q", "error": {frame: (pos_m, rot_rad)}}; q covers every arm (an arm
        without a target keeps its seed)."""
        mj, m = self._mj, self.model
        qadr = np.concatenate([a.qadr for a in self.arms])
        q = np.array(seed if seed is not None else self.data.qpos[qadr], dtype=np.float64).reshape(-1)
        if q.shape[0] != len(qadr):
            raise ValueError(f"seed is {len(qadr)} joint positions")
        errors, off = {}, 0
        jacp, jacr = np.zeros((3, m.nv)), np.zeros((3, m.nv))
        for a in self.arms:
            sl = slice(off, off + len(a.qadr))
            off += len(a.qadr)
            if a.tcp not in targets:
                continue
            tgt = np.asarray(targets[a.tcp], dtype=np.float64)
            sid = m.site(a.site).id
            lo = np.array([m.jnt_range[j, 0] if m.jnt_limited[j] else -np.inf for j in a.joint_ids])
            hi = np.array([m.jnt_range[j, 1] if m.jnt_limited[j] else np.inf for j in a.joint_ids])
            use_rot = tol_rot_rad < 3.1

            def err(qa):
                qq = q.copy()
                qq[sl] = qa
                self._fk0(qq)
                e_p = tgt[:3] - self._k0.site_xpos[sid]
                cur, neg, dq3 = np.zeros(4), np.zeros(4), np.zeros(4)
                mj.mju_mat2Quat(cur, self._k0.site_xmat[sid])
                mj.mju_negQuat(neg, cur)
                mj.mju_mulQuat(dq3, tgt[3:] / np.linalg.norm(tgt[3:]), neg)
                e_r = np.zeros(3)
                mj.mju_quat2Vel(e_r, dq3, 1.0)
                return e_p, e_r

            qa, lam = q[sl].copy(), 1e-3
            e_p, e_r = err(qa)
            for _ in range(int(max_iters)):
                if np.linalg.norm(e_p) < tol_pos_m and (not use_rot or np.linalg.norm(e_r) < tol_rot_rad):
                    break
                err(qa)  # kinematics at qa for the Jacobian
                mj.mj_jacSite(m, self._k0, jacp, jacr, sid)
                J = np.vstack([jacp[:, a.vadr], jacr[:, a.vadr]]) if use_rot else jacp[:, a.vadr]
                e = np.concatenate([e_p, e_r]) if use_rot else e_p
                dq = J.T @ np.linalg.solve(J @ J.T + lam * np.eye(len(e)), e)
                nrm = np.linalg.norm(dq)
                if nrm > 0.3:
                    dq *= 0.3 / nrm
                qn = np.clip(qa + dq, lo, hi)
                n_p, n_r = err(qn)
                new = np.linalg.norm(np.concatenate([n_p, n_r]) if use_rot else n_p)
                if new < np.linalg.norm(e):
                    qa, e_p, e_r, lam = qn, n_p, n_r, max(lam / 2, 1e-7)
                else:
                    lam = min(lam * 4, 1e3)
                    if lam >= 1e3:
                        break
            q[sl] = qa
            e_p, e_r = err(qa)
            errors[a.tcp] = (float(np.linalg.norm(e_p)), float(np.linalg.norm(e_r)))
        ok = bool(errors) and all(
            p < tol_pos_m and (tol_rot_rad >= 3.1 or r < tol_rot_rad) for p, r in errors.values()
        )
        return {"ok": ok, "q": q.tolist(), "error": errors}

    def robot_spec(self) -> dict:
        """The robot's spec sheet (nothing about the scene): arms, joints and limits, grippers, drives, tool frames."""
        m, d = self.model, self._k0
        acts = self.actuators()
        by_joint = {a["drives"]: a for a in acts}
        joints = []
        for j in self.robot_joints():
            a = by_joint.get(j["mujoco_name"])
            joints.append({
                "name": j["name"], "type": j["type"], "unit": j["unit"], "position_limits": j["range"],
                "velocity_limit": None, "effort_limit": (a["force_range"][1] if a and a["force_range"] else None),
                "group": f"{j['arm']}:{j['group']}",
                "note": f"driven by the action entry `{a['name']}`" if a else "not driven by an action entry",
            })

        def pose7(pos, quat) -> list:
            q = np.asarray(quat, dtype=np.float64)
            q = -q if q[0] < 0 else q
            return [*(float(v) for v in pos), *(float(v) for v in q)]

        bases, tcp, grippers, names = {}, {}, {}, []
        for a in self.arms:
            b = m.body(a.base).id
            bases[a.key] = {"link": self._link_name(b), "pose": pose7(d.xpos[b], d.xquat[b])}
            sid = m.site(a.site).id
            T = np.eye(4)
            R = np.zeros(9)
            self._mj.mju_quat2Mat(R, m.site_quat[sid])
            T[:3, :3], T[:3, 3] = R.reshape(3, 3), m.site_pos[sid]
            tool = a.site.startswith("tl/")
            tcp[a.tcp] = {
                "parent_link": self._link_name(int(m.site_bodyid[sid])),
                "link_T_frame": T.tolist(),
                "definition": "the tip of the pipette this arm's hand holds" if tool
                else "the point between the fingertips (the gripper's pinch point)",
            }
            names.append("ALOHA arm (6 joints, parallel gripper)" if a.kind == "aloha"
                         else "UR5e (6 joints) with a dexterous hand holding a pipette" if tool
                         else "UR5e (6 joints) with a Robotiq 2F-85 gripper")
            hand = [j["name"] for j in self.robot_joints() if j["arm"] == a.key and j["group"] == "hand"]
            for act in acts:
                if act["arm"] == a.key and act["kind"] == "gripper":
                    robotiq = act["unit"].startswith("0")
                    grippers[f"{a.label}gripper"] = {
                        "joints": hand,
                        "opening_m": [0.0, 0.084] if robotiq else [0.016, 0.074],
                        "command": {"entry": act["name"], "index": act["index"], "range": act["range"], "unit": act["unit"],
                                    "rule": "0 opens, 255 closes (a tendon drive: the fingers stop on what they hold)"
                                    if robotiq else "the finger's sliding position: small closes, large opens"},
                        "tcp_frame": a.tcp,
                    }
        first = bases[self.arms[0].key]
        return {
            "name": " + ".join(names),
            "description": f"{len(self.arms)} arm(s) fixed to the bench: " + "; ".join(f"{a.key}: {n}" for a, n in zip(self.arms, names)),
            "base": {"type": "fixed", "link": first["link"], "pose": first["pose"], "arms": bases,
                     "note": "pose: x y z + wxyz quaternion of an arm's base link in the world frame (`pose` is the first arm's; `arms` has every arm's)"},
            "joints": joints,
            "grippers": grippers,
            "controller": {
                "type": "joint position targets: each driven joint has a PD position drive, force = stiffness * (target - q) - damping * qdot, limited to effort_limit",
                "control_hz": 1.0 / CONTROL_DT, "physics_hz": 1.0 / CONTROL_DT,
                "gains": {a["name"]: {"stiffness": a["kp"], "damping": a["kv"]} for a in acts},
                "note": "the gripper entry of an action is the gripper's own command (see grippers); joints that are not driven by an action entry keep their initial targets",
            },
            "tcp": tcp,
        }

    # ------------------------------------------------------------------------------------------- cameras
    def _camera_names(self) -> dict:
        m, out = self.model, {}
        for c in range(m.ncam):
            n = m.camera(c).name
            a = self._arm_of(n)
            out[(a.label + "wrist_cam") if a else _clean(n)] = n
        return out

    def cameras(self) -> list:
        return list(self._cams)

    def default_cameras(self) -> list:
        """The views AutoBio gives its policies for this task."""
        want = list(self.info.get("camera_mapping", {}).values())
        return [k for k, v in self._cams.items() if v in want] or self.cameras()[:1]

    def _cam(self, camera: str) -> int:
        return self.model.camera(self._cams.get(camera, camera)).id

    def camera_info(self, camera: str, size=(H, W)) -> dict:
        """Intrinsics (OpenCV), world -> camera (OpenCV axes) and camera -> world (OpenGL axes) at the current state."""
        m, d, c = self.model, self._view(), self._cam(camera)
        h, w = size
        f = 0.5 * h / math.tan(math.radians(float(m.cam_fovy[c])) / 2)
        c2w = np.eye(4)
        c2w[:3, :3] = d.cam_xmat[c].reshape(3, 3)
        c2w[:3, 3] = d.cam_xpos[c]
        return {
            "intrinsic_cv": [[f, 0.0, w / 2], [0.0, f, h / 2], [0.0, 0.0, 1.0]],
            "extrinsic_cv": np.linalg.inv(c2w @ GL2CV)[:3, :].tolist(),
            "cam2world_gl": c2w.tolist(),
            "image_size": [w, h],
        }

    def camera_mount(self, camera: str) -> dict:
        m, c = self.model, self._cam(camera)
        b = int(m.cam_bodyid[c])
        if int(m.body_weldid[b]) == 0:
            info = self.camera_info(camera)
            return {"type": "static", "extrinsic_cv": info["extrinsic_cv"], "cam2world_gl": info["cam2world_gl"]}
        d = self._k0
        Tb, Tc = np.eye(4), np.eye(4)
        Tb[:3, :3], Tb[:3, 3] = d.xmat[b].reshape(3, 3), d.xpos[b]
        Tc[:3, :3], Tc[:3, 3] = d.cam_xmat[c].reshape(3, 3), d.cam_xpos[c]
        return {"type": "link", "parent_link": self._link_name(b), "link_T_cam_cv": (np.linalg.inv(Tb) @ Tc @ GL2CV).tolist()}

    def _drop_extras(self) -> None:
        for _update, finish in self._extras or []:
            with contextlib.suppress(Exception):
                finish()
        self._extras = None

    def _ctx(self, size):
        mj = self._mj
        if self._renderer is not None and self._rsize != tuple(size):
            self._close_renderer()  # one GL context at a time (a second OSMesa context next to a live one reads garbage)
        if self._renderer is None:
            r = mj.Renderer(self.model, int(size[0]), int(size[1]))
            r.scene.flags[mj.mjtRndFlag.mjRND_SHADOW] = False  # as AutoBio's evaluator renders its policy views
            r.scene.flags[mj.mjtRndFlag.mjRND_REFLECTION] = False
            r._scene_option.sitegroup[:] = False
            self._renderer, self._rsize = r, tuple(size)
            self._drop_extras()
        if self._extras is None:  # what a frame shows beyond the model: the mixer's display, the liquid surface
            with _in_root():
                import evaluator as EV
                from instrument import Thermal_mixer_eppendorf_c

                mixers = self.task.manager.systems_by_type.get(Thermal_mixer_eppendorf_c, [])
                panels = [PanelTexture(mj, self.model, x) for x in mixers]
                liquid = EV.make_liquid_extra(self.task)  # AutoBio's own helper: the liquid's surface as a disc
            self._extras = [(x.update, x.finish) for x in panels] + ([liquid] if liquid is not None else [])
        return self._renderer

    def render_frame(self, camera: str, size=(H, W), depth: bool = False) -> np.ndarray:
        """RGB uint8 (h, w, 3) of a camera at the current state, or its z-depth in metres (float32) with depth=True.
        `size` up to (960, 1280)."""
        r = self._ctx(size)
        if depth:
            r.enable_depth_rendering()
        r.update_scene(self._view(), camera=self._cam(camera))
        with warnings.catch_warnings():  # AutoBio's liquid-surface helper calls deprecated scikit-image functions
            warnings.simplefilter("ignore", FutureWarning)
            for update, _finish in self._extras:
                update(r.scene, r._mjr_context)
        img = r.render().copy()
        if depth:
            r.disable_depth_rendering()
            img = img.astype(np.float32)
        return img

    def render_depth(self, camera: str, size=(H, W)) -> np.ndarray:
        return self.render_frame(camera, size, depth=True)

    def _close_renderer(self) -> None:
        self._drop_extras()
        if self._renderer is not None:
            with contextlib.suppress(Exception):
                self._renderer.close()
        self._renderer = None

    def close(self) -> None:
        """Release the renderer (also runs at interpreter exit)."""
        if getattr(self, "_closed", False):
            return
        self._closed = True
        self._close_renderer()
        _log({"ev": "session_end", "sim_steps": int(self.total_steps), "resets": int(max(self.resets, 0))})

    # ------------------------------------------------------------------------------------------- privileged view
    def state(self) -> dict:
        """Privileged view of the current state. `s.task` (AutoBio's task object: its scene helpers and `check()`),
        `s.model` and `s.data` (MuJoCo) are yours to read as well; only recorded actions are replayed."""
        d = self.data
        return {
            "time_s": round(self.steps * CONTROL_DT, 6),
            "qpos": d.qpos.copy(), "qvel": d.qvel.copy(), "ctrl": d.ctrl.copy(),
            "command": self.command(),
            "tcp": self.tcp_poses(),
            "gripper_opening": self.gripper_openings(),
            "score": float(self.score), "success": bool(self.success), "done": bool(self.done),
            "prompt": self.info.get("prefix"),
        }


def _write_video(path: str, frames: list, fps: int) -> bool:
    try:
        import imageio.v2 as imageio

        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with imageio.get_writer(path, fps=fps, codec="libx264", quality=6, macro_block_size=None) as w:
            for f in frames:
                h, wd = f.shape[0] // 2 * 2, f.shape[1] // 2 * 2
                w.append_data(f[:h, :wd])
        return os.path.getsize(path) > 0
    except Exception as exc:  # noqa: BLE001 -- a video never decides anything
        print(f"video not written: {exc!r}", file=sys.stderr)
        return False


def facts(family: str, seed: int) -> dict:
    """What an instance file records about `family` at `seed` (run inside the image by the generator)."""
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump({"family": family, "seed": seed}, f)
    global SESSION_LOG
    SESSION_LOG = ""
    s = Session(family, instance=f.name)
    os.unlink(f.name)
    mod, cls, rule = FAMILIES[family]
    out = {
        "benchmark": "autobio", "family": family, "seed": int(seed), "rule": rule,
        "upstream": {"repo": "autobio-bench/AutoBio", "commit": open("/opt/autobio-commit").read().strip()
                     if os.path.exists("/opt/autobio-commit") else None, "module": mod, "class": cls},
        "control_dt": CONTROL_DT, "model_sha": s.model_sha, "init_sha": s.init_sha,
        "prompt": s.info.get("prefix"),
        "n_action": s.n_act, "actuators": s.actuators(),
        "arms": [{"key": a.key, "kind": a.kind, "tcp": a.tcp, "joints": [s._joint_name(j) for j in a.joint_ids]} for a in s.arms],
        "robot_joints": [j["name"] for j in s.robot_joints()],
        "cameras": s.cameras(), "default_cameras": s.default_cameras(),
        "initial_command": [float(v) for v in s.command()],
        "initial_score": float(s.score),
    }
    panel = s._verdict_state().get("panel")
    if panel is not None:
        out["panel_initial"] = panel
        out["panel_target"] = [int(v) for v in s.task.set_params]
    s.close()
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("replay", help="replay a trajectory from the frozen instance (what the grader does)")
    r.add_argument("--instance", default="/app/instance.json")
    r.add_argument("--task", "--family", dest="family", default=None)
    r.add_argument("--traj", default="/app/output/trajectory.npz")
    r.add_argument("--out", default=None)
    r.add_argument("--video", default=None)
    r.add_argument("--repeat", type=int, default=1)
    f = sub.add_parser("facts", help="hashes and layout of a family at a seed (generator)")
    f.add_argument("--family", required=True)
    f.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    if a.cmd == "facts":
        print(json.dumps(facts(a.family, a.seed)))
        return 0
    d = np.load(a.traj, allow_pickle=False)
    acts = np.asarray(d["actions"], dtype=np.float64)
    s = Session(a.family, instance=a.instance)
    out, shas = {}, []
    for k in range(max(1, a.repeat)):
        out = s.replay(acts, video=a.video if k == 0 else None)
        shas.append(out["state_sha"])
        print(json.dumps(out), flush=True)
    if a.repeat > 1:
        out["deterministic"] = len(set(shas)) == 1
        print(json.dumps({"deterministic": out["deterministic"]}), flush=True)
    if a.out:
        json.dump(out, open(a.out, "w"))
    s.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
