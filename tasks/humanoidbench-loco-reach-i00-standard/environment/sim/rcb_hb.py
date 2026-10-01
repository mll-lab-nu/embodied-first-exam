"""rcb_hb.py — task-local tooling for HumanoidBench: frozen instances, recording, deterministic replay.

Mirrors tasks/robosuite-cube-stack-i00-privileged/environment/rcb_traj.py so the agent's experience is the same
across simulators; the differences HumanoidBench forces are marked [HB].

Concepts
--------
instance    the frozen scene, saved as .npz: the MuJoCo state (qpos, qvel, time, qacc_warmstart) plus
            the task state that lives outside it -- goals drawn at reset, subtask counters, and the
            model arrays a task writes its target into. Upstream draws the latter from the global
            np.random, which reset(seed=) does not reach, so make_instance() seeds both generators and
            the snapshot restores both; an instance is therefore reproducible from its seed and pins
            the scene for the agent and the verifier alike.
trajectory  (T, nu) normalised joint-position targets in [-1, 1], one row per control step (50 Hz).
            Replayed open-loop from the same instance it reproduces bit-for-bit (CPU MuJoCo).
success     [HB] episode_return >= task.success_bar -- a threshold on the accumulated dense reward,
            not a predicate on the final state. NOT computed here: the image ships no reward function
            (see below), so scoring happens in the verifier.

CLI
---
  python rcb_hb.py run-oracle --instance inst.npz --code gen.py --out traj.npz
  python rcb_hb.py replay     --instance inst.npz --traj traj.npz [--repeat 2]
  python rcb_hb.py render     --instance inst.npz --traj traj.npz --out replay.mp4

Python API
----------
  from rcb_hb import Session
  s = Session(instance="/app/instance.npz")   # which task and env this is comes from the instance
  s.reset()                                  # back to the frozen state (unlimited)
  obs = s.obs()                              # state vector (its layout: instruction.md)
  with s.recording() as rec:                 # [HB] context manager, not record_start/record_stop
      for _ in range(s.max_steps):
          obs, r, done = s.step(my_controller(obs))
          if done:
              break
  s.replay(rec.actions)                      # self-check: resets, replays open-loop, returns status()
  s.save_trajectory(rec.actions, "/app/output/trajectory.npz")

Scoring is not visible from here
--------------------------------
`s.scored` is False and `s.step()` returns `None` for the reward. HumanoidBench's reward functions are
dense and hand-tuned, so reading one turns a control problem into an algebra problem -- the formula is
therefore removed from the image and restored only inside the verifier, after the agent is finished.

What you have instead is the full physical state: `s.obs()` (its layout is in instruction.md: qpos and, for most
tasks, qvel, plus this task's goal where it has one), and the MuJoCo model is right there in `s.model`. Everything the reward could tell you
-- how fast the centre of mass is moving, how upright the torso is, how far the hand is from the target
-- is computable from that, and `instruction.md` says which of those things the task is judged on. Define
the measure you think the task calls for, and optimise against it.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np


# --- the part of a task's state that does NOT live in (qpos, qvel) -----------------------------------
# Upstream keeps some of it on the Task object and some in `model`: a goal drawn at reset, a destination
# or target orientation written into the model, a placement permutation, and counters that reset_model
# forgets to clear. None of it is reachable from a qpos/qvel snapshot, and the random draws come from the
# LEGACY GLOBAL np.random, which gym's reset(seed=) does not touch. Without freezing it, this session and
# the verifier would solve different problems, and a second rollout in one process would be scored by a
# different reward function than the first. Snapshotting vars(task) covers that with no special-casing;
# where the environment was already well behaved it is simply a no-op.
_TASK_STATE_SKIP = ("_env", "robot", "unwrapped")   # back-references to the env, not state


def _task_state(task) -> dict[str, Any]:
    """vars(task) minus the back-references and anything reward-shaped (a name containing "reward", the scrub's own
    rule): the instance ships into the agent's image, and push keeps its scoring weights in `reward_dict`, which the
    image strips and only the verifier puts back (rcb_rewards.py)."""
    return {k: v for k, v in vars(task).items() if k not in _TASK_STATE_SKIP and "reward" not in k.lower()}


def _unscored_bookkeeping(task) -> None:
    """[HB] Bookkeeping that upstream does only inside get_reward(), which the image deletes, but that the agent
    can otherwise see: a `step_counter` that moves a target in the observation, and a checkpoint pointer and
    heading that `update_move_direction()` advances (recolouring the checkpoints). Neither is the formula, so
    where this process cannot score, step() does it here and the agent sees what the verifier's replay sees.
    The other progress get_reward() keeps (which object is current, what is done) is the bonus test itself and
    stays out; instruction.md says where it does not advance."""
    if hasattr(task, "update_move_direction"):
        task.update_move_direction()
    if hasattr(task, "step_counter"):
        task.step_counter += 1


def _task_state_dumps(state: dict) -> str:
    """Serialise to JSON, never pickle: an instance file is data the verifier loads with
    allow_pickle=False, and it must stay that way -- a pickle in that position is code execution."""
    def enc(o):
        if isinstance(o, np.ndarray):
            return {"__ndarray__": o.tolist(), "dtype": str(o.dtype)}
        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.floating):
            return float(o)
        if isinstance(o, np.bool_):
            return bool(o)
        raise TypeError(f"task state field of type {type(o).__name__} is not JSON-serialisable: {o!r}")
    return json.dumps(state, default=enc)


def _task_state_loads(blob: str) -> dict:
    def dec(d):
        if "__ndarray__" in d:
            return np.array(d["__ndarray__"], dtype=np.dtype(d["dtype"]))
        return d
    return json.loads(blob, object_hook=dec)


def _resolve_gl_backend() -> str:
    """Pick MuJoCo's offscreen GL backend. An explicit MUJOCO_GL always wins.

    `egl` renders on the GPU (~0.4 ms/frame), `osmesa` on the CPU (~130 ms/frame); physics is CPU-only
    either way, so rendering is the only thing a GPU changes here.

    "Has a GPU" and "can render on it" are different questions: the container runtime mounts the device
    node and the driver's GL libraries under separate capabilities, and whether libglvnd can actually
    reach the vendor driver depends on the host's driver packaging. Guessing from file paths got this
    wrong once already, so just try it -- MuJoCo binds its backend at `import mujoco`, once per process,
    which is why the attempt has to happen in a throwaway subprocess. The device-node check keeps that
    cost at zero on CPU-only machines, and exporting the result means forked workers inherit it instead
    of each paying for their own probe.
    """
    if explicit := os.environ.get("MUJOCO_GL"):
        return explicit
    if not os.path.exists("/dev/nvidiactl"):
        return "osmesa"
    probe = "import os; os.environ['MUJOCO_GL'] = 'egl'; import mujoco; mujoco.GLContext(8, 8).free()"
    try:
        ok = subprocess.run([sys.executable, "-c", probe], capture_output=True, timeout=120).returncode == 0
    except (OSError, subprocess.SubprocessError):
        ok = False
    return "egl" if ok else "osmesa"


# MuJoCo reads this once, at `import mujoco`, so import this module before anything imports mujoco.
GL_BACKEND = _resolve_gl_backend()
os.environ["MUJOCO_GL"] = GL_BACKEND
os.environ["PYOPENGL_PLATFORM"] = GL_BACKEND


class _Recording:
    """The actions captured inside a `with session.recording()` block."""

    def __init__(self) -> None:
        self._rows: list[np.ndarray] = []

    def append(self, action: np.ndarray) -> None:
        self._rows.append(np.asarray(action, dtype=np.float64).copy())

    def clear(self) -> None:
        self._rows.clear()

    @property
    def actions(self) -> np.ndarray:
        """(T, nu), or an empty (0, 0) when the block stepped nothing -- np.stack would raise on an
        empty list, and a traceback here hides the thing the caller actually needs to be told."""
        if not self._rows:
            return np.zeros((0, 0), dtype=np.float64)
        return np.stack(self._rows)

    def __len__(self) -> int:
        return len(self._rows)


class Session:
    """One HumanoidBench environment pinned to one frozen scene instance."""

    def __init__(self, task: str | None = None, instance: str | Path | None = None,
                 enable_render: bool = False, env_id: str | None = None, image_hw: int | None = None):
        """Open the environment this instance belongs to.

        The instance file records which HumanoidBench task and env id it was drawn from, so normally
        neither has to be passed: `Session(instance="/app/instance.npz")` is enough. Passing `task` as
        well turns it into an assertion -- that is what the verifier does, so a trajectory produced for
        one task cannot be graded against another's scene.

        `env_id` is only for creating an instance from scratch, when there is no file to read it from.
        `image_hw` is the side of every rendered image in pixels (None: upstream's 256).
        """
        if instance is not None:
            inst = np.load(instance, allow_pickle=False)
            file_task, file_env = str(inst["task"]), str(inst["env_id"])
            if task is not None and task != file_task:
                raise ValueError(f"instance is for task {file_task!r}, session asked for {task!r}")
            if env_id is not None and env_id != file_env:
                raise ValueError(f"instance is for env {file_env!r}, session asked for {env_id!r}")
            task, env_id = file_task, file_env
        if task is None or env_id is None:
            raise ValueError("pass instance=..., or both task= and env_id= to build a fresh scene")
        self.task, self.env_id = task, env_id

        import gymnasium as gym
        import humanoid_bench  # noqa: F401  (registers every robot x task env id)

        # [HB] HumanoidEnv defaults to render_mode="rgb_array" and Task.__init__ then builds an offscreen
        # viewer eagerly, so even a physics-only gym.make() would need a GL context. render_mode=None
        # skips the viewer entirely and is markedly faster.
        self.env = gym.make(self.env_id, render_mode="rgb_array" if enable_render else None,
                            **({"width": image_hw, "height": image_hw} if image_hw else {}))
        self.enable_render = enable_render
        self.low = self.env.unwrapped
        self.model, self.data = self.low.model, self.low.data
        self.nu = int(self.model.nu)
        self.max_steps = int(self.env.spec.max_episode_steps)
        self.success_bar = float(self.low.task.success_bar)
        # [HB] Whether this process can score at all. The image deletes every Task subclass's get_reward
        # (images/humanoidbench/scrub_oracles.py), which leaves upstream's base returning (0, {}); the
        # verifier patches the real one back before opening its Session. Detecting it beats a flag file:
        # there is exactly one truth, and it is the object that would do the scoring.
        from humanoid_bench.tasks import Task as _Task
        self.scored = type(self.low.task).get_reward is not _Task.get_reward

        self.instance_state: np.ndarray | None = None
        self.instance_extra: dict[str, Any] | None = None   # task state + the model arrays tasks write
        self._geom_rgba: np.ndarray | None = None           # the model's colours at the frozen start
        self._recording: _Recording | None = None
        self._ret = 0.0            # accumulated reward since the last reset
        self._steps = 0
        self._last_info: dict[str, Any] = {}
        self._sim_steps_total = 0  # simulation budget, reported by status() (PROTOCOL.md §5)
        self._resets = 0

        self.env.reset(seed=0)     # one reset so the gym wrappers start in a legal state
        if instance is not None:
            self.instance_state = np.array(inst["state"], dtype=np.float64)
            self.instance_extra = {"task_state": str(inst["task_state"]),
                                   "body_pos": np.array(inst["body_pos"], dtype=np.float64),
                                   "body_quat": np.array(inst["body_quat"], dtype=np.float64)}
            self._geom_rgba = self.model.geom_rgba.copy()   # nothing has stepped yet: the scene as it starts
            self.reset()

    # ---- instances ---------------------------------------------------------
    def _snapshot(self) -> np.ndarray:
        d = self.data
        return np.concatenate([
            np.asarray(d.qpos, dtype=np.float64),
            np.asarray(d.qvel, dtype=np.float64),
            np.array([d.time], dtype=np.float64),
            np.asarray(d.qacc_warmstart, dtype=np.float64),   # the field everyone forgets
        ])

    def _snapshot_extra(self) -> dict[str, Any]:
        """The other half of the frozen instance: everything outside (qpos, qvel). See _TASK_STATE_SKIP.

        `body_pos` / `body_quat` are here because two tasks write their goal into the MODEL rather than
        into data -- package puts the destination in body_pos[-1], cube the target orientation in
        body_quat[-1]. Copying the whole array is a few KB and keeps this free of per-task knowledge.
        """
        return {
            "task_state": _task_state_dumps(_task_state(self.low.task)),
            "body_pos": np.asarray(self.model.body_pos, dtype=np.float64).copy(),
            "body_quat": np.asarray(self.model.body_quat, dtype=np.float64).copy(),
        }

    def _restore_extra(self) -> None:
        """Must run between env.reset() and mj_forward: reset() redraws the goal and leaves accumulated
        counters alone, and body_pos feeds the kinematics that mj_forward is about to recompute."""
        if self._geom_rgba is not None:              # maze recolours its checkpoints in the model as they are
            self.model.geom_rgba[:] = self._geom_rgba   # passed, and upstream's reset leaves them as they were
        vars(self.low.task).update(_task_state_loads(self.instance_extra["task_state"]))
        self.model.body_pos[:] = self.instance_extra["body_pos"]
        self.model.body_quat[:] = self.instance_extra["body_quat"]

    def _restore(self, snap: np.ndarray) -> None:
        """Put the simulator back on the frozen state.

        A full env.reset() MUST come first. Writing qpos/qvel into a dirty `data` leaves hidden state
        behind -- data.ctrl still holds the last action, plus data.act, applied forces and the wrapper
        counters. mj_forward then folds that stale ctrl into the constraint solve, so the "restored"
        state silently differs from the snapshot and replays diverge within a step or two.
        rcb_traj.py does the same thing (_fresh_reset before _restore); it is not optional.
        """
        import mujoco
        nq, nv = self.model.nq, self.model.nv
        self.env.reset()                                   # 1. clear ctrl / act / forces / counters
        self._restore_extra()                              # 1b. goals, counters, model-side targets
        self.data.qpos[:] = snap[:nq]                      # 2. overwrite the pose
        self.data.qvel[:] = snap[nq:nq + nv]
        self.data.time = float(snap[nq + nv])
        self.data.ctrl[:] = 0.0
        mujoco.mj_forward(self.model, self.data)           # 3. recompute derived quantities
        self.data.qacc_warmstart[:] = snap[nq + nv + 1:]   # 4. AFTER forward -- forward overwrites it
        self._restore_bookkeeping()

    def _restore_bookkeeping(self) -> None:
        """[HB] Much lighter than robosuite's: no controllers to re-anchor and no cached observables, and gymnasium's
        TimeLimit counter is zeroed by the env.reset() every restore starts with. Only this session's own counters."""
        self._ret, self._steps, self._last_info = 0.0, 0, {}

    def make_instance(self, seed: int | None = None) -> np.ndarray:
        """Draw a scene and freeze it. Reproducible: the same seed gives the same instance anywhere.

        Two RNGs have to be pinned, not one. `reset(seed=)` seeds gymnasium's per-instance generator,
        which is what perturbs every qpos by +-0.01. Task-level draws -- a goal position, a destination,
        a target orientation, a placement order -- come from the LEGACY GLOBAL np.random instead, which
        `reset(seed=)` does not touch; without seeding it
        here, make_instance() returns a different scene in every process and an instance file could only
        ever be copied, never regenerated. The global state is saved and restored so that seeding it is
        invisible to whatever else the caller is doing with numpy's random module.
        """
        rng_state = np.random.get_state()
        try:
            np.random.seed(0 if seed is None else seed)
            self.env.reset(seed=seed)
        finally:
            np.random.set_state(rng_state)
        self.instance_state = self._snapshot()
        self.instance_extra = self._snapshot_extra()   # raises if a task keeps unserialisable state
        self._restore_bookkeeping()
        return self.instance_state

    def instance_sha(self) -> str:
        """Digest of the WHOLE frozen instance. Two instances can share a pose and differ only in the
        goal, so this has to cover the extra as well -- state_sha() hashes the live pose and is a
        different question (it is what the determinism check compares)."""
        h = hashlib.sha1(np.ascontiguousarray(self.instance_state).tobytes())
        h.update(self.instance_extra["task_state"].encode())
        for k in ("body_pos", "body_quat"):
            h.update(np.ascontiguousarray(self.instance_extra[k]).tobytes())
        return h.hexdigest()[:12]

    def save_instance(self, path: str | Path, seed: int | None = None) -> None:
        if self.instance_state is None:
            raise RuntimeError("call make_instance() first")
        np.savez(path, state=self.instance_state, task=self.task, env_id=self.env_id,
                 seed=-1 if seed is None else seed, sha=self.instance_sha(), **self.instance_extra)

    def state_sha(self) -> str:
        return hashlib.sha1(np.ascontiguousarray(self._snapshot()).tobytes()).hexdigest()[:12]

    def reset(self) -> np.ndarray:
        """Return to the frozen instance state. Unlimited.

        Inside a `with recording()` block this restarts the take instead of ending it: a reset means
        "this attempt again", so the actions recorded so far are dropped and recording continues.
        """
        if self.instance_state is None:
            raise RuntimeError("no instance: open the Session with instance=..., or call make_instance()")
        if self._recording is not None:
            self._recording.clear()
        self._resets += 1
        self._restore(self.instance_state)
        return self.obs()

    # ---- stepping ----------------------------------------------------------
    def obs(self) -> np.ndarray:
        return self.low.task.get_obs()

    def step(self, action) -> tuple[np.ndarray, float | None, bool]:
        """One control step at 50 Hz. `action` is (nu,) and is clipped to [-1, 1].

        Returns (obs, reward, done). **`reward` is None unless this process can score** -- see the module
        docstring; inside the agent's container it always is. `obs` and `done` are always real.
        """
        a = np.clip(np.asarray(action, dtype=np.float32).reshape(self.nu), -1.0, 1.0)
        if self._recording is not None:
            self._recording.append(a)
        obs, r, term, trunc, info = self.env.step(a)
        if self.scored:
            self._ret += float(r)
        else:
            _unscored_bookkeeping(self.low.task)
        self._steps += 1
        self._sim_steps_total += 1
        self._last_info = info
        return obs, (float(r) if self.scored else None), bool(term or trunc)

    @contextlib.contextmanager
    def _not_recording(self):
        """A self-check or a video is not part of the take: suspend recording for its duration."""
        rec, self._recording = self._recording, None
        try:
            yield
        finally:
            self._recording = rec

    @contextlib.contextmanager
    def recording(self):
        """Capture every action stepped inside the block:

            with s.recording() as rec:
                ...
            actions = rec.actions        # (T, nu)

        Actions taken before an exception are kept, so a crashed rollout is still inspectable.
        """
        rec = _Recording()
        self._recording = rec
        try:
            yield rec
        finally:
            self._recording = None

    # ---- status / replay ---------------------------------------------------
    def status(self) -> dict[str, Any]:
        """What this process can honestly say about the episode just run.

        [HB] `scored` is False in the agent's container, and then the scoring fields are absent rather
        than zero -- a missing key is a question you cannot answer, a zero is a wrong answer. What stays
        is what is observable either way: how many steps ran, and the hash of the state they ended in
        (which is what makes an open-loop replay checkable without a reward).
        """
        out = {
            "scored": self.scored,
            "sim_steps": int(self._steps),
            "state_sha": self.state_sha(),
            "sim_steps_total": int(self._sim_steps_total),
            "resets": int(self._resets),
        }
        if not self.scored:
            return out
        return out | {
            "success": bool(self._ret >= self.success_bar),
            "episode_return": float(self._ret),
            "success_bar": self.success_bar,
            "final_reward": float(self._last_info.get("per_timestep_reward", 0.0)),
        }

    def replay(self, actions: np.ndarray) -> dict[str, Any]:
        """Reset, replay open-loop, return status(). Use this to self-check before submitting.

        Safe to call from inside a `with recording()` block: a self-check is not part of the take,
        so recording is suspended for the duration.
        """
        with self._not_recording():
            self.reset()
            for a in np.asarray(actions, dtype=np.float64):
                if self.step(a)[2]:
                    break
            return self.status()

    def save_trajectory(self, actions: np.ndarray, path: str | Path, meta: dict | None = None) -> None:
        if self.instance_state is None:
            raise RuntimeError("no instance loaded")
        acts = np.asarray(actions, dtype=np.float64)
        if acts.ndim != 2 or acts.shape[1] != self.nu:
            raise ValueError(f"actions must be (T, {self.nu}), got {acts.shape}")
        if len(acts) > self.max_steps:
            raise ValueError(f"trajectory longer than the episode limit ({len(acts)} > {self.max_steps})")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        np.savez(
            path,
            actions=acts,
            task=self.task,
            env_id=self.env_id,
            instance_sha=self.instance_sha(),
            action_layout=f"{self.nu} normalised joint-position targets in [-1,1], one row per 50 Hz step",
            meta=json.dumps(meta or {}),
        )

    def render_video(self, actions: np.ndarray, path: str | Path, *, every: int = 5, fps: int = 20) -> dict[str, Any]:
        """Replay and write an MP4. Needs Session(..., enable_render=True). Like replay(), not part of a take.
        Rendering is for humans; the verdict always comes from replay()."""
        import imageio.v2 as imageio
        if not self.enable_render:
            raise RuntimeError("render_video needs Session(..., enable_render=True)")
        with self._not_recording():
            self.reset()
            frames = [self.env.render()]
            for i, a in enumerate(np.asarray(actions, dtype=np.float64)):
                done = self.step(a)[2]
                if (i + 1) % every == 0:
                    frames.append(self.env.render())
                if done:
                    break
            frames.append(self.env.render())
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with imageio.get_writer(str(path), fps=fps, format="FFMPEG", codec="libx264", macro_block_size=1) as w:
            for f in frames:
                w.append_data(np.ascontiguousarray(f))
        imageio.imwrite(str(path.with_suffix(".last.png")), np.ascontiguousarray(frames[-1]))
        return {**self.status(), "n_frames": len(frames), "video": str(path), "gl_backend": GL_BACKEND}

    def exec_code(self, code: str) -> dict[str, Any]:
        """Run a script with this session (as `s` and `session`) and numpy in scope."""
        g: dict[str, Any] = {"__name__": "__main__", "np": np, "s": self, "session": self}
        try:
            exec(code, g, g)
            return {"ok": True}
        except BaseException as exc:  # noqa: BLE001
            return {"ok": False, "error": repr(exc)}

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self.env.close()


# --------------------------------------------------------------------------- CLI
def _load_traj(path: str) -> np.ndarray:
    return np.load(path, allow_pickle=False)["actions"]


def _record(s: Session, code_path: str) -> tuple[np.ndarray | None, dict]:
    with s.recording() as rec:
        r = s.exec_code(Path(code_path).read_text())
    return (rec.actions if r["ok"] else None), r


def cmd_run_oracle(a) -> int:
    s = Session(a.task, instance=a.instance)  # task is optional; when given it asserts
    acts, r = _record(s, a.code)
    if acts is None:
        print(json.dumps({"error": r["error"]}), file=sys.stderr)
        return 1
    s.save_trajectory(acts, a.out, meta={"source": Path(a.code).name})
    # status() drops the scoring fields where there is no reward function, so this prints fewer keys
    # inside the task image than it does verifier-side. The trajectory is written either way.
    print(json.dumps({"out": a.out, "n_actions": len(acts), **s.replay(acts)}))
    return 0


def cmd_replay(a) -> int:
    """Replay a trajectory `--repeat` times and report what this process can see.

    Determinism is the part that is always available, and it is the part worth checking before
    submitting: identical state_sha across repeats means the grader's replay will land where yours did.
    The scoring fields appear only when this process can score (see Session.status).
    """
    s = Session(a.task, instance=a.instance)
    outs = [s.replay(_load_traj(a.traj)) for _ in range(a.repeat)]
    out = {"deterministic": len({o["state_sha"] for o in outs}) == 1, **outs[0]}
    if s.scored:
        out |= {"all_success": all(o["success"] for o in outs),
                "returns": [o["episode_return"] for o in outs]}
    print(json.dumps(out))
    return 0


def cmd_render(a) -> int:
    s = Session(a.task, instance=a.instance, enable_render=True)
    print(json.dumps(s.render_video(_load_traj(a.traj), a.out, every=a.every, fps=a.fps)))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="rcb_hb.py")
    sub = p.add_subparsers(dest="cmd", required=True)

    # --task is optional wherever an --instance is given: the instance names its own task, and passing
    # it anyway turns it into an assertion (which is what the verifier wants).
    q = sub.add_parser("run-oracle"); q.add_argument("--task")
    q.add_argument("--instance", required=True); q.add_argument("--code", required=True)
    q.add_argument("--out", required=True); q.set_defaults(fn=cmd_run_oracle)

    q = sub.add_parser("replay"); q.add_argument("--task")
    q.add_argument("--instance", required=True); q.add_argument("--traj", required=True)
    q.add_argument("--repeat", type=int, default=2); q.set_defaults(fn=cmd_replay)

    q = sub.add_parser("render"); q.add_argument("--task")
    q.add_argument("--instance", required=True); q.add_argument("--traj", required=True)
    q.add_argument("--out", required=True); q.add_argument("--every", type=int, default=5)
    q.add_argument("--fps", type=int, default=20); q.set_defaults(fn=cmd_render)

    a = p.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
