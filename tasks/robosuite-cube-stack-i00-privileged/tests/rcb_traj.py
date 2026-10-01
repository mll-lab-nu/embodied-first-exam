"""
rcb_traj.py — task-local tooling: frozen-instance / record / deterministic-replay utilities for cap-x robosuite envs.

Concepts
--------
instance   : a frozen initial MuJoCo state (qpos/qvel after cap-x reset+settle) saved to .npz.
             This *is* the task instance; seeds alone are not enough because robosuite's robot
             initialization noise uses an unseeded RNG.
trajectory : the sequence of low-level robosuite actions (T, 9) = 7 joint targets + 2 gripper,
             captured by hooking `_do_robosuite_step`. Replaying it open-loop from the same
             instance state must reproduce the outcome (MuJoCo is deterministic on CPU).

CLI
---
  python rcb_traj.py make-instance --task cube_stack --out inst.npz [--seed 3]
  python rcb_traj.py run-oracle    --task cube_stack --instance inst.npz --code solution/oracle_cube_stack.py --out traj.npz
  python rcb_traj.py replay        --task cube_stack --instance inst.npz --traj traj.npz [--repeat 3]
  python rcb_traj.py selftest      --task cube_stack --seed 3 --code oracle.py   # make-instance + oracle + replay, asserts equality
  python rcb_traj.py render        --task cube_stack --instance inst.npz --traj traj.npz --out replay.mp4 [--wrist]

Python (what the agent gets)
----------------------------
  from rcb_traj import Session
  s = Session("cube_stack", instance="inst.npz")   # starts pyroki IK server if needed
  s.reset()                                       # always back to the frozen instance state
  s.primitives()                                  # dict of privileged primitives (goto_pose, ...)
  s.record_start(); ...; actions = s.record_stop()
  s.save_trajectory(actions, "traj.npz")
  s.replay(actions) -> dict(success=bool, reward=float, n_steps=int)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np

os.environ.setdefault("MUJOCO_GL", "egl")

# --------------------------------------------------------------------------- task family registry
TASKS: dict[str, dict] = {
    "cube_stack": dict(
        exec_env="capx.envs.tasks.franka.franka_pick_place.FrankaPickPlaceCodeEnv",
        low_level="franka_robosuite_cubes_low_level",
        apis=["FrankaControlPrivilegedApi"],
        text="Stack the red cube on top of the green cube with the Franka arm, then release it so it stays stacked.",
        simulator="robosuite", robot="franka-panda", image="robosuite",
    ),
}


PYROKI_PORT = int(os.environ.get("CAPX_PYROKI_PORT", "8116"))


def _import(path: str):
    mod, _, name = path.rpartition(".")
    return getattr(__import__(mod, fromlist=[name]), name)


def _port_open(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex((host, port)) == 0


def ensure_pyroki_server(port: int = PYROKI_PORT, timeout: float = 120.0) -> subprocess.Popen | None:
    """Start cap-x's pyroki IK server in a subprocess if nothing listens on `port`."""
    if _port_open(port):
        return None
    code = (
        "from capx.serving.launch_pyroki_server import main;"
        f"main(robot='panda_description', target_link='panda_hand', port={port}, host='127.0.0.1')"
    )
    log = open(os.environ.get("CAPX_PYROKI_LOG", "/tmp/pyroki_server.log"), "ab")
    proc = subprocess.Popen([sys.executable, "-c", code], stdout=log, stderr=subprocess.STDOUT)
    t0 = time.time()
    while time.time() - t0 < timeout:
        if _port_open(port):
            return proc
        if proc.poll() is not None:
            raise RuntimeError(f"pyroki server exited early (rc={proc.returncode}); see {log.name}")
        time.sleep(0.5)
    raise TimeoutError("pyroki server did not come up")


# --------------------------------------------------------------------------- session
class Session:
    def __init__(self, task: str, instance: str | Path | None = None, enable_render: bool = False):
        if task not in TASKS:
            raise KeyError(f"unknown task {task!r}; known: {list(TASKS)}")
        self.task = task
        self._pyroki = ensure_pyroki_server()

        # cap-x resolves its controller config relative to the repo root; make the Session cwd-independent
        capx_root = os.environ.get("CAPX_ROOT", "/opt/cap-x")
        if not os.path.isdir("capx/integrations") and os.path.isdir(capx_root):
            os.chdir(capx_root)
        import capx.envs.tasks  # noqa: F401  (registers envs/apis)
        from capx.envs.tasks.base import CodeExecEnvConfig

        spec = TASKS[task]
        cfg = CodeExecEnvConfig(
            low_level=spec["low_level"],
            apis=spec["apis"],
            privileged=True,
            enable_render=enable_render,
        )
        self.env = _import(spec["exec_env"])(cfg)
        self.low = self.env.low_level_env

        self._recording: list[np.ndarray] | None = None
        self._orig_step: Callable = self.low._do_robosuite_step
        self.low._do_robosuite_step = self._hooked_step  # type: ignore[method-assign]

        self.instance_state: np.ndarray | None = None
        if instance is not None:
            self.load_instance(instance)

    @property
    def sim(self):
        # robosuite hard-resets recreate MjSim, so never cache it
        return self.low.robosuite_env.sim

    # ---- hooks
    def _hooked_step(self, action: np.ndarray) -> None:
        if self._recording is not None:
            self._recording.append(np.array(action, dtype=np.float64, copy=True))
        self._orig_step(action)

    # ---- instance handling
    def _fresh_reset(self, seed: int | None = None) -> None:
        if seed is not None:
            # in-place reseed so the placement sampler (which shares this rng) follows
            self.low.robosuite_env.rng.bit_generator.state = np.random.default_rng(seed).bit_generator.state
            np.random.seed(seed)
        self.env.reset(seed=seed)

    def _restore_wrapper_bookkeeping(self) -> None:
        """After sim.set_state: sync MuJoCo derived quantities, controller goals, robosuite's
        cached observables, and the cap-x wrapper's cached robot state."""
        rs = self.low.robosuite_env
        self.sim.forward()
        # controller interpolators were initialised from the (noisy) fresh-reset pose; re-anchor them
        for c in rs.robots[0].composite_controller.part_controllers.values():
            c.update(force=True)
            c.reset_goal()
        # robosuite caches observables (object poses!) — refresh so primitives see the restored scene
        rs._update_observables(force=True)
        idx = rs.robots[0]._ref_joint_pos_indexes
        self.low._current_joints = np.array(self.sim.data.qpos[idx], dtype=np.float64)
        self.low._set_gripper(1.0)
        self.low.gripper_link_wxyz_xyz = np.concatenate(
            [self.sim.data.xquat[self.low.gripper_link_idx], self.sim.data.xpos[self.low.gripper_link_idx]]
        )
        self.low._step_count = 0
        self.low._sim_step_count = 0
        for api in self.env._apis.values():  # drop IK warm-start caches
            if hasattr(api, "cfg"):
                api.cfg = None

    def _snapshot(self) -> np.ndarray:
        d = self.sim.data
        return np.concatenate([self.sim.get_state().flatten(), np.asarray(d.qacc_warmstart, dtype=np.float64)])

    def _restore(self, snap: np.ndarray) -> None:
        nwarm = self.sim.model.nv
        self.sim.set_state_from_flattened(snap[:-nwarm].copy())
        self.sim.data.qacc_warmstart[:] = snap[-nwarm:]

    def make_instance(self, seed: int | None = None) -> np.ndarray:
        self._fresh_reset(seed)
        self.instance_state = self._snapshot()
        return self.instance_state

    def save_instance(self, path: str | Path, seed: int | None = None) -> None:
        assert self.instance_state is not None
        np.savez(path, state=self.instance_state, task=self.task, seed=-1 if seed is None else seed,
                 sha=self.state_sha())

    def load_instance(self, path: str | Path) -> None:
        d = np.load(path, allow_pickle=False)
        if str(d["task"]) != self.task:
            raise ValueError(f"instance task {d['task']} != session task {self.task}")
        self.instance_state = np.array(d["state"], dtype=np.float64)
        self.reset()

    def state_sha(self) -> str:
        return hashlib.sha1(np.ascontiguousarray(self._snapshot()).tobytes()).hexdigest()[:12]

    def reset(self) -> None:
        """Return to the frozen instance state (fresh controller, then restore qpos/qvel)."""
        if self.instance_state is None:
            raise RuntimeError("no instance loaded; call make_instance() or load_instance()")
        self._recording = None
        self._fresh_reset()
        self._restore(self.instance_state)
        self._restore_wrapper_bookkeeping()

    # ---- primitives for the agent
    def primitives(self) -> dict[str, Callable]:
        fns: dict[str, Callable] = {}
        for api in self.env._apis.values():
            fns.update(api.functions())
        return fns

    def exec_code(self, code: str) -> dict[str, Any]:
        """Run agent code with primitives in scope (same semantics as cap-x's executor)."""
        g: dict[str, Any] = {"__name__": "__main__", "np": np, "env": self.low, **self.primitives()}
        try:
            exec(code, g, g)
            return {"ok": True}
        except BaseException as exc:  # noqa: BLE001
            return {"ok": False, "error": repr(exc)}

    # ---- recording
    def record_start(self) -> None:
        self._recording = []

    def record_stop(self) -> np.ndarray:
        acts = np.array(self._recording or [], dtype=np.float64).reshape(-1, 9)
        self._recording = None
        return acts

    def save_trajectory(self, actions: np.ndarray, path: str | Path, meta: dict | None = None) -> None:
        assert self.instance_state is not None
        np.savez(
            path,
            actions=np.asarray(actions, dtype=np.float64),
            task=self.task,
            instance_sha=hashlib.sha1(np.ascontiguousarray(self.instance_state).tobytes()).hexdigest()[:12],
            action_layout="7 joint position targets (rad) + 2 gripper (-1 open, +1 closed), one row per sim control step",
            meta=json.dumps(meta or {}),
        )

    # ---- status / replay
    def status(self) -> dict[str, Any]:
        return {
            "success": bool(self.low.task_completed()),
            "reward": float(self.low.compute_reward()),
            "sim_steps": int(self.low._sim_step_count),
            "state_sha": self.state_sha(),
        }

    def replay(self, actions: np.ndarray) -> dict[str, Any]:
        self.reset()
        for a in np.asarray(actions, dtype=np.float64):
            self._orig_step(a)
            self.low._sim_step_count += 1
        return self.status()

    def render_video(self, actions: np.ndarray, path: str | Path, *, every: int = 5, fps: int = 20,
                     wrist: bool = False) -> dict[str, Any]:
        """Replay `actions` from the frozen instance and write a human-viewable MP4 (needs enable_render=True).
        Frames are taken every `every` sim steps from the scene camera (and the wrist camera if `wrist`).
        Returns status() plus n_frames. Rendering is for humans; the verdict comes from replay()."""
        import imageio.v2 as imageio
        if not getattr(self.env.cfg, "enable_render", False):
            raise RuntimeError("render_video needs Session(..., enable_render=True)")
        self.reset()
        grab = (lambda: np.concatenate([self.low.render(), self.low.render_wrist()], axis=1)) if wrist else self.low.render
        frames = [grab()]
        for i, a in enumerate(np.asarray(actions, dtype=np.float64)):
            self._orig_step(a)
            self.low._sim_step_count += 1
            if (i + 1) % every == 0:
                frames.append(grab())
        frames.append(grab())
        path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
        with imageio.get_writer(str(path), fps=fps, format="FFMPEG", codec="libx264", macro_block_size=1) as w:
            for f in frames:
                w.append_data(np.ascontiguousarray(f))
        imageio.imwrite(str(path.with_suffix(".last.png")), np.ascontiguousarray(frames[-1]))
        return {**self.status(), "n_frames": len(frames), "video": str(path)}

    def close(self) -> None:
        if self._pyroki is not None:
            self._pyroki.terminate()


# --------------------------------------------------------------------------- CLI
def _load_traj(path: str) -> np.ndarray:
    return np.load(path, allow_pickle=False)["actions"]


def cmd_make_instance(a):
    s = Session(a.task)
    s.make_instance(a.seed)
    s.save_instance(a.out, a.seed)
    print(json.dumps({"instance": a.out, "sha": s.state_sha(), **s.status()}))


def cmd_run_oracle(a):
    s = Session(a.task, instance=a.instance)
    code = open(a.code).read()
    s.record_start()
    r = s.exec_code(code)
    acts = s.record_stop()
    st = s.status()
    s.save_trajectory(acts, a.out, meta={"source": "oracle", "exec": r})
    print(json.dumps({"traj": a.out, "n_actions": int(len(acts)), "exec": r, **st}))


def cmd_replay(a):
    s = Session(a.task, instance=a.instance)
    acts = _load_traj(a.traj)
    outs = [s.replay(acts) for _ in range(a.repeat)]
    print(json.dumps({"n_actions": int(len(acts)), "replays": outs,
                      "all_success": all(o["success"] for o in outs),
                      "deterministic": len({o["state_sha"] for o in outs}) == 1}))


def cmd_render(a):
    s = Session(a.task, instance=a.instance, enable_render=True)
    out = s.render_video(_load_traj(a.traj), a.out, every=a.every, fps=a.fps, wrist=a.wrist)
    print(json.dumps(out))


def cmd_selftest(a):
    s = Session(a.task)
    s.make_instance(a.seed)
    sha0 = s.state_sha()
    s.reset(); assert s.state_sha() == sha0, "reset() does not restore instance state"
    s.record_start(); r = s.exec_code(open(a.code).read()); acts = s.record_stop()
    live = s.status()
    rep = [s.replay(acts) for _ in range(a.repeat)]
    ok = live["success"] and all(x["success"] for x in rep) and len({x["state_sha"] for x in rep}) == 1 \
        and rep[0]["state_sha"] == live["state_sha"]
    print(json.dumps({"oracle_exec": r, "live": live, "replays": rep, "n_actions": int(len(acts)), "PASS": ok}, indent=1))
    sys.exit(0 if ok else 1)


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("make-instance"); q.add_argument("--task", required=True); q.add_argument("--out", required=True); q.add_argument("--seed", type=int); q.set_defaults(fn=cmd_make_instance)
    q = sub.add_parser("run-oracle"); q.add_argument("--task", required=True); q.add_argument("--instance", required=True); q.add_argument("--code", required=True, help="python file run with primitives in scope"); q.add_argument("--out", required=True); q.set_defaults(fn=cmd_run_oracle)
    q = sub.add_parser("replay"); q.add_argument("--task", required=True); q.add_argument("--instance", required=True); q.add_argument("--traj", required=True); q.add_argument("--repeat", type=int, default=2); q.set_defaults(fn=cmd_replay)
    q = sub.add_parser("render"); q.add_argument("--task", required=True); q.add_argument("--instance", required=True); q.add_argument("--traj", required=True); q.add_argument("--out", required=True); q.add_argument("--every", type=int, default=5); q.add_argument("--fps", type=int, default=20); q.add_argument("--wrist", action="store_true"); q.set_defaults(fn=cmd_render)
    q = sub.add_parser("selftest"); q.add_argument("--task", default="cube_stack"); q.add_argument("--code", required=True); q.add_argument("--seed", type=int, default=0); q.add_argument("--repeat", type=int, default=2); q.set_defaults(fn=cmd_selftest)
    a = p.parse_args(); a.fn(a)


if __name__ == "__main__":
    main()
