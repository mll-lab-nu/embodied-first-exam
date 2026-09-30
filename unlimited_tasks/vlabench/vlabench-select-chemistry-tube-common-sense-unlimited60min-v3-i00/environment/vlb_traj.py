"""Privileged-state VLABench sessions. Record simulator controls, never skill names.

WORLD metres, WXYZ quaternions; actions follow the compiled actuator order.
The trusted descriptor fixes construction, physics and native task semantics.
"""
from __future__ import annotations

import uuid
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import random
import time
import zipfile

import numpy as np

UPSTREAM = "cf588fe60c0c7282174fe979f5913170cfe69017"
MAX_ACTIONS = 4000
MAX_BYTES = 1024 * 1024 * 1024
SCHEMA = "vlabench-controls-v1"
SKILLS = ("pick", "place", "moveto", "lift", "pull", "push", "open_door",
          "close_door", "open_drawer", "press", "open_gripper", "close_gripper",
          "wait", "move_offset", "pour", "flip", "open_laptop", "reset")


def canonical(value):
    def encode(x):
        if isinstance(x, np.ndarray): return x.tolist()
        if isinstance(x, np.generic): return x.item()
        raise TypeError(type(x).__name__)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=encode)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def load_archive(path):
    if Path(path).stat().st_size > MAX_BYTES:
        raise ValueError("trajectory archive exceeds 8 MiB")
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or len(names) > 16:
            raise ValueError("duplicate/excess archive members")
        if sum(i.file_size for i in archive.infolist()) > MAX_BYTES:
            raise ValueError("expanded archive exceeds 8 MiB")
        for name in names:
            with archive.open(name) as f:
                version = np.lib.format.read_magic(f)
                shape, _, dtype = np.lib.format._read_array_header(f, version)
                import math
                if dtype.hasobject or math.prod(shape) * dtype.itemsize > MAX_BYTES:
                    raise ValueError("unsafe array header")
    with np.load(path, allow_pickle=False) as archive:
        return {key: archive[key] for key in archive.files}


def build_env(spec):
    import VLABench.envs as factory
    import VLABench.tasks  # registers native tasks
    import VLABench.robots
    import open3d as o3d
    seed = spec["seed"]
    random.seed(seed)
    np.random.seed(seed)
    o3d.utility.random.seed(seed)
    # Upstream load_env mutates module-level defaults. Restore them on every build.
    root = Path(os.environ["VLABENCH_ROOT"])
    factory.TASK_CONFIG = json.loads((root / "configs/task_config.json").read_text())
    factory.ROBOT_CONFIG = json.loads((root / "configs/robot_config.json").read_text())
    original = factory.LM4ManipDMEnv
    def construct(**kwargs):
        # Explicit author-specified geometry for a fixed instance, before model
        # compilation. Never applied during agent interaction or replay stepping.
        for name, scale in spec.get("construction_scales", {}).items():
            kwargs["task"].entities[name].apply_scale(float(scale))
        return original(random_state=seed, **kwargs)
    factory.LM4ManipDMEnv = construct
    try:
        env = factory.load_env(spec["native_task"], robot="franka", random_init=False,
                               episode_config=copy.deepcopy(spec.get("episode")),
                               time_limit=float("inf"), run_mode="efficient")
    finally:
        factory.LM4ManipDMEnv = original
    return env


def physics_state(env):
    import mujoco
    flags = mujoco.mjtState.mjSTATE_INTEGRATION
    state = np.empty(mujoco.mj_stateSize(env.physics.model.ptr, flags), np.float64)
    mujoco.mj_getState(env.physics.model.ptr, env.physics.data.ptr, state, flags)
    return state


def logic_state(env):
    """Audit native task/entity event flags alongside the integration state."""
    out = {}
    for name, obj in [("task", env.task), *sorted(env.task.entities.items())]:
        for key, value in vars(obj).items():
            if isinstance(value, (bool, np.bool_)) or key in (
                    "_num_activated_steps", "_reward", "condition_has_been_met"):
                out[name + "/" + key] = value
    def conditions(obj, prefix):
        if obj is None: return
        if hasattr(obj, "condition_has_been_met"):
            out[prefix] = obj.condition_has_been_met
        for attr in ("conditions", "condition_sets", "_conditions"):
            children = getattr(obj, attr, [])
            if isinstance(children, (list, tuple)):
                for i, child in enumerate(children): conditions(child, f"{prefix}/{i}")
    conditions(env.task.conditions, "conditions")
    return out


def state_hash(env):
    h = hashlib.sha256(physics_state(env).tobytes())
    h.update(canonical(logic_state(env)).encode())
    return h.hexdigest()


def model_hash(env):
    # Include compiled geometry, physical parameters and runtime model randomization.
    h = hashlib.sha256()
    for name in sorted(dir(env.physics.model)):
        value = getattr(env.physics.model, name)
        if isinstance(value, np.ndarray) and value.dtype.kind in "fiu":
            h.update(name.encode() + np.ascontiguousarray(value).tobytes())
    return h.hexdigest()


class Session:
    def __init__(self, instance="/app/instance.json", budget_path="/app/output/budget.json"):
        self.path = Path(instance)
        self.spec = json.loads(self.path.read_text())
        if self.spec["upstream_commit"] != UPSTREAM:
            raise ValueError("upstream version mismatch")
        self.instance_sha = digest(self.spec)
        self._env = None
        self._recording = None
        self.started = time.monotonic()
        self.budget_path = Path(budget_path) if budget_path else None
        self.counters = dict(resets=0, sim_steps=0, physics_steps=0, tool_calls=0,
                             replay_steps=0, initialization_steps=0, wall_seconds=0.0)
        self.session_id = uuid.uuid4().hex
        if self.budget_path:
            self.budget_path = self.budget_path.parent / 'sim-usage' / (self.session_id + '.json')
        self._prior_wall = 0.0
        self.reset()

    def _count(self):
        self.counters["tool_calls"] += 1

    def _flush(self):
        self.counters["session_id"] = self.session_id
        self.counters["reset_count"] = max(0,self.counters["resets"]-1)
        self.counters["wall_seconds"] = self._prior_wall + time.monotonic() - self.started
        if self.budget_path:
            self.budget_path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.budget_path.with_suffix(".tmp")
            temp.write_text(canonical(self.counters) + "\n")
            temp.replace(self.budget_path)

    def reset(self):
        """Reconstruct native task, model, RNG and all Composer/entity logic."""
        self._count()
        self.counters["resets"] += 1
        self._flush()
        if self._env is not None: self._env.physics.free()
        self._recording = None
        self._env = build_env(self.spec)
        self.sim_steps = 0
        self.done = bool(self._env.task.should_terminate_episode(self._env.physics))
        if self.done: raise RuntimeError("invalid instance: initially successful")
        self.initial_hash = state_hash(self._env)
        self.model_sha = model_hash(self._env)
        if self.initial_hash != self.spec["initial_state_sha256"]:
            raise RuntimeError("initial physical/task state differs from frozen instance")
        if self.model_sha != self.spec["model_sha256"]:
            raise RuntimeError("compiled model differs from frozen instance")
        self.dt = float(self._env.control_timestep())
        self.substeps = self._env._n_sub_steps
        # Native reset settles twice for reset_wait_step control intervals.
        initialization_steps = 2*self._env.reset_wait_step
        self.counters["initialization_steps"] += initialization_steps
        self.counters["sim_steps"] += initialization_steps
        self.counters["physics_steps"] += initialization_steps*self.substeps
        spec = self._env.action_spec()
        self.lower = np.asarray(spec.minimum)
        self.upper = np.asarray(spec.maximum)
        self._original_step = self._env.step
        self._env.step = self._step
        # Skills collect images after every action. Retain geometry-based planning,
        # but make that internal data collector lightweight. observe() renders on demand.
        original_observation = self._env.get_observation
        class LazyObservation(dict):
            def __missing__(self, key):
                self.update(original_observation())
                return self[key]
        self._env.get_observation = lambda **kwargs: LazyObservation(
            q_state=self._env.robot.get_qpos(self._env.physics))
        self._last_action = np.r_[self._env.robot.get_qpos(self._env.physics), [0.04, 0.04]]
        self._flush()
        return self.status()

    def _validate(self, actions):
        a = np.asarray(actions)
        if a.dtype.kind not in "fi" or a.ndim != 2 or a.shape[1:] != self.lower.shape:
            raise ValueError(f"actions must have shape (T, {self.lower.size})")
        if len(a) < 1 or not np.isfinite(a).all():
            raise ValueError("actions must contain one or more finite rows")
        if np.any(a < self.lower - 1e-8) or np.any(a > self.upper + 1e-8):
            raise ValueError("actuator command outside compiled action bounds")
        return a.astype(np.float64)

    def _step(self, action=None):
        if self.done: raise RuntimeError("episode finished; reset before further actions")
        if action is None: action = np.r_[self._env.robot.get_qpos(self._env.physics), [0.04, 0.04]]
        # Native open_door emits finger targets above its ctrlrange (stale loop
        # index). MuJoCo clamps these anyway. Record the exact bounded command
        # we send, making this normalization explicit and identical in replay.
        action = np.asarray(action, dtype=np.float64)
        if action.shape != self.lower.shape or not np.isfinite(action).all():
            raise ValueError("invalid simulator control")
        action = self._validate(np.clip(action, self.lower, self.upper).reshape(1, -1))[0]
        # Record precisely what is passed to Composer, including gripper loops.
        if self._recording is not None: self._recording.append(action.copy())
        result = self._original_step(action.copy())
        self._last_action = action.copy()
        self.sim_steps += 1
        self.counters["sim_steps"] += 1
        self.counters["physics_steps"] += self.substeps
        self.done = bool(result.last())
        self._flush()
        return result

    def step(self, action):
        self._count()
        self._validate(np.asarray(action).reshape(1, -1))
        self._step(action)
        return self.status()

    def state(self):
        """Physical entity state only: no target IDs, conditions or expert sequence."""
        self._count()
        env = self._env
        entities = {}
        for name, entity in env.task.entities.items():
            item = dict(category=type(entity).__name__, position=entity.get_xpos(env.physics),
                        quaternion_wxyz=entity.get_xqaut(env.physics))
            for method in ("get_grasped_keypoints", "get_place_point", "get_start_button_pos"):
                if hasattr(entity, method):
                    try: item[method] = np.asarray(getattr(entity, method)(env.physics))
                    except (ValueError, AttributeError, IndexError): pass
            if entity.joints:
                item["joint_positions"] = env.physics.bind(entity.joints).qpos.copy()
            entities[name] = item
        result = dict(entities=entities, robot=dict(
            joint_positions=env.robot.get_qpos(env.physics),
            joint_velocities=env.robot.get_qvel(env.physics),
            tcp_position=env.get_ee_pos(), tcp_quaternion_wxyz=env.get_ee_quat(),
            gripper_positions=env.physics.bind([
                env.robot.mjcf_model.find("joint", "finger_joint1"),
                env.robot.mjcf_model.find("joint", "finger_joint2")]).qpos.copy()),
            action_lower=self.lower, action_upper=self.upper, control_dt=self.dt)
        self._flush()
        return json.loads(canonical(result))

    def observe(self, camera=2, width=320, height=320, point_cloud=False):
        self._count()
        env = self._env
        rgb = env.render(camera_id=camera, width=width, height=height)
        depth = env.render(camera_id=camera, width=width, height=height, depth=True)
        # MuJoCo cameras look along local -Z; local +Y is up.
        f = height / (2 * np.tan(np.deg2rad(env.physics.model.cam_fovy[camera]) / 2))
        K = np.array([[f, 0, width / 2], [0, f, height / 2], [0, 0, 1]])
        T = np.eye(4)
        T[:3, :3] = env.physics.data.cam_xmat[camera].reshape(3, 3) @ np.diag([1, -1, -1])
        T[:3, 3] = env.physics.data.cam_xpos[camera]
        result = dict(rgb=rgb, depth_m=depth, intrinsic=K, camera_to_world=T)
        if point_cloud:
            y, x = np.indices(depth.shape)
            xyz = np.stack([(x-K[0,2])*depth/f, (y-K[1,2])*depth/f, depth], axis=-1)
            result["points_world"] = xyz.reshape(-1, 3) @ T[:3,:3].T + T[:3,3]
        self._flush()
        return result

    def skill(self, name, **kwargs):
        self._count()
        if name not in SKILLS: raise ValueError(f"unknown general skill: {name}")
        from VLABench.utils.skill_lib import SkillLib
        before = self.sim_steps
        try:
            result = getattr(SkillLib, name)(self._env, **kwargs)
            stage_ok = bool(result is not None and result[2])
            feedback = dict(stage_success=stage_ok, executed_actions=self.sim_steps-before,
                            failure=None if stage_ok else "skill did not reach its own stage predicate")
        except (ValueError, TypeError, AssertionError, RuntimeError) as exc:
            feedback = dict(stage_success=False, executed_actions=self.sim_steps-before,
                            failure=f"{type(exc).__name__}: {exc}")
        feedback.update(self.status())
        self._flush()
        return feedback

    def ik(self, position, quaternion_wxyz):
        self._count()
        ok, joints = self._env.robot.get_qpos_from_ee_pos(
            self._env.physics, pos=np.asarray(position), quat=np.asarray(quaternion_wxyz))
        return dict(success=bool(ok), joint_positions=np.asarray(joints).copy())

    def record_start(self):
        self._count()
        if self.sim_steps: raise ValueError("record immediately after reset")
        self._recording = []

    def record_stop(self):
        self._count()
        if self._recording is None: raise RuntimeError("record_start required")
        actions = np.asarray(self._recording, dtype=np.float64).reshape(-1, len(self.lower))
        self._recording = None
        return actions

    def status(self):
        self._count()
        success = bool(self._env.task.should_terminate_episode(self._env.physics))
        return dict(success=success, sim_steps=self.sim_steps,
                    physics_steps=self.sim_steps*self.substeps, state_sha=state_hash(self._env),
                    initial_state_sha=self.initial_hash, budget=self.counters.copy())

    def save_trajectory(self, actions, path="/app/output/trajectory.npz"):
        self._count()
        actions = self._validate(actions)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        metadata = dict(schema=SCHEMA, upstream_commit=UPSTREAM, instance_sha=self.instance_sha,
                        native_task=self.spec["native_task"], control_dt=self.dt,
                        action_semantics="absolute_actuator_position_targets",
                        n_substeps=self.substeps, dtype="float64")
        np.savez_compressed(path, actions=actions, metadata=canonical(metadata),
                            times=np.arange(len(actions), dtype=np.float64)*self.dt)
        self._flush()

    def load_trajectory(self, path):
        data = load_archive(path)
        meta = json.loads(str(data["metadata"]))
        for key, expected in dict(schema=SCHEMA, upstream_commit=UPSTREAM,
                instance_sha=self.instance_sha, native_task=self.spec["native_task"],
                control_dt=self.dt, n_substeps=self.substeps,
                action_semantics="absolute_actuator_position_targets", dtype="float64").items():
            if meta.get(key) != expected: raise ValueError(f"trajectory {key} mismatch")
        actions = self._validate(data["actions"])
        if data["actions"].dtype != np.float64:
            raise ValueError("trajectory controls must be float64 as declared")
        if not np.array_equal(data["times"], np.arange(len(actions))*self.dt):
            raise ValueError("trajectory timestamp mismatch")
        return actions

    def replay(self, actions, video=None):
        actions = self._validate(actions)
        self.reset()
        writer = None
        if video:
            import imageio.v2 as imageio
            writer = imageio.get_writer(video, fps=round(1/self.dt))
        try:
            for action in actions:
                if self.done:
                    raise ValueError("trajectory contains controls after native termination")
                self._step(action)
                self.counters["replay_steps"] += 1
                if writer: writer.append_data(self.observe()["rgb"])
            return self.status()
        finally:
            if writer: writer.close()
            self._flush()

    def close(self):
        if self._env is not None:
            self._env.physics.free()
            self._env = None
        self._flush()

    def __enter__(self): return self
    def __exit__(self, *exc): self.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["inspect", "replay"])
    parser.add_argument("--instance", default="/app/instance.json")
    parser.add_argument("--traj", default="/app/output/trajectory.npz")
    parser.add_argument("--result")
    parser.add_argument("--video")
    args = parser.parse_args()
    with Session(args.instance, budget_path=None) as session:
        if args.command == "inspect":
            result = session.status()
        else:
            result = session.replay(session.load_trajectory(args.traj), args.video)
        if args.result:
            Path(args.result).write_text(canonical(result)+"\n")
            np.savez_compressed(args.result+".state.npz", integration=physics_state(session._env))
        print(canonical(result))


if __name__ == "__main__": main()

# Trusted runner preinitializes the first simulator outside the agent clock.
if __name__ != "__main__":
 import sys as _sys
 from warm_session import install as _install
 _install(_sys.modules[__name__])
