"""VLABench tooling for the VLABench tasks: one native VLABench task on a frozen instance.

Used by the privileged agent (importable as `vlb_tool`), by the privileged verifier, and by the standard-mode sim
service (environment/sim/server.py).

    import vlb_tool
    s = vlb_tool.Session("/app/instance.json")  # the frozen instance; s.env is the VLABench (dm_control) environment
    st = s.state()                      # privileged state: every entity's pose and grasp/place points, the robot
    s.step(a)                           # one control step (0.1 s): a = 7 arm joint targets (rad) + 2 finger targets (m)
    s.skill("pick", target_entity_name="banana")   # VLABench's general skills; their control steps are recorded too
    s.save_trajectory()                 # every control step since the last reset -> /app/output/trajectory.npz
    s.replay(actions)                   # reset, then replay (what the verifier does) -> {"success", "state_sha", ...}
    s.reset()                           # back to the frozen start, as often as you like
    o = s.observe("forward")            # RGB, depth, intrinsics, camera-to-world pose

The instance is VLABench's own episode configuration plus the hashes of the compiled model and of the initial state;
reset() rebuilds the scene from it (seeded) and refuses to run if either hash differs. Success is VLABench's own
termination predicate (`task.should_terminate_episode`): the episode ends the moment it holds, so a trajectory ends
there and its final state is the graded one.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import random
import zipfile
from pathlib import Path

import numpy as np

UPSTREAM = "cf588fe60c0c7282174fe979f5913170cfe69017"
SCHEMA = "eai-vlabench-trajectory/1"
MAX_STEPS = 4000  # privileged deliverable: at most this many control steps
N = 9
ACTION_NAMES = [f"joint{i}" for i in range(1, 8)] + ["finger1", "finger2"]
SKILLS = (
    "pick", "place", "moveto", "lift", "pull", "push", "open_door", "close_door", "open_drawer", "press",
    "open_gripper", "close_gripper", "wait", "move_offset", "pour", "flip", "open_laptop",
)  # fmt: skip
CAMERAS = {"forward": "forward", "left": "left", "right": "right", "wrist": "franka/Franka_wrist_cam"}


def canonical(value) -> str:
    def enc(x):
        if isinstance(x, np.ndarray):
            return enc(x.tolist())
        if isinstance(x, np.generic):
            return x.item()
        if isinstance(x, dict):
            return {str(k): enc(v) for k, v in x.items()}
        if isinstance(x, (list, tuple)):
            return [enc(v) for v in x]
        return x

    return json.dumps(enc(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def load_npz(path, max_bytes: int = 8 * 1024 * 1024) -> dict:
    """Pickle-free NPZ loader with size limits (trajectories come from the agent)."""
    path = Path(path)
    if path.stat().st_size > max_bytes:
        raise ValueError("archive too large")
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if len(infos) > 16 or sum(i.file_size for i in infos) > 4 * max_bytes:
            raise ValueError("expanded archive too large")
        names = [i.filename for i in infos]
        if len(set(names)) != len(names):
            raise ValueError("duplicate archive members")  # numpy would silently take the last one
        if any(not n.endswith(".npy") for n in names):
            raise ValueError("expected .npy members only")
        for info in infos:
            with archive.open(info) as f:
                version = np.lib.format.read_magic(f)
                shape, _, dtype = np.lib.format._read_array_header(f, version)
                if dtype.hasobject or math.prod(shape) * dtype.itemsize > 4 * max_bytes:
                    raise ValueError("unsafe array header")
    with np.load(path, allow_pickle=False) as data:
        return {k: data[k].copy() for k in data.files}


def build_env(spec: dict):
    """VLABench's own load_env for the frozen episode configuration, with every random source seeded."""
    import open3d as o3d
    import VLABench.envs as factory
    import VLABench.robots  # noqa: F401 -- registers the robots
    import VLABench.tasks  # noqa: F401 -- registers the native tasks

    seed = spec["seed"]
    random.seed(seed)
    np.random.seed(seed)
    o3d.utility.random.seed(seed)
    root = Path(os.environ["VLABENCH_ROOT"])  # load_env mutates module-level defaults: restore them on every build
    factory.TASK_CONFIG = json.loads((root / "configs/task_config.json").read_text())
    factory.ROBOT_CONFIG = json.loads((root / "configs/robot_config.json").read_text())
    original = factory.LM4ManipDMEnv

    def construct(**kwargs):
        for name, scale in spec.get("construction_scales", {}).items():  # instance geometry, before compilation
            kwargs["task"].entities[name].apply_scale(float(scale))
        return original(random_state=seed, **kwargs)

    factory.LM4ManipDMEnv = construct
    try:
        return factory.load_env(
            spec["native_task"],
            robot="franka",
            random_init=False,
            episode_config=copy.deepcopy(spec.get("episode")),
            time_limit=float("inf"),
            run_mode="efficient",
        )
    finally:
        factory.LM4ManipDMEnv = original


def physics_state(env) -> np.ndarray:
    import mujoco

    flags = mujoco.mjtState.mjSTATE_INTEGRATION
    state = np.empty(mujoco.mj_stateSize(env.physics.model.ptr, flags), np.float64)
    mujoco.mj_getState(env.physics.model.ptr, env.physics.data.ptr, state, flags)
    return state


def logic_state(env) -> dict:
    """The native task's and entities' event flags (part of the state the predicates read)."""
    out = {}
    for name, obj in [("task", env.task), *sorted(env.task.entities.items())]:
        for key, value in vars(obj).items():
            if isinstance(value, (bool, np.bool_)) or key in (
                "_num_activated_steps",
                "_reward",
                "condition_has_been_met",
            ):
                out[name + "/" + key] = value

    def conditions(obj, prefix):
        if obj is None:
            return
        if hasattr(obj, "condition_has_been_met"):
            out[prefix] = obj.condition_has_been_met
        for attr in ("conditions", "condition_sets", "_conditions"):
            children = getattr(obj, attr, [])
            if isinstance(children, (list, tuple)):
                for i, child in enumerate(children):
                    conditions(child, f"{prefix}/{i}")

    conditions(env.task.conditions, "conditions")
    return out


def state_hash(env) -> str:
    h = hashlib.sha256(physics_state(env).tobytes())
    h.update(canonical(logic_state(env)).encode())
    return h.hexdigest()


def model_hash(env) -> str:
    """Compiled geometry, physical parameters and the model randomization VLABench applies at build time."""
    h = hashlib.sha256()
    for name in sorted(dir(env.physics.model)):
        value = getattr(env.physics.model, name)
        if isinstance(value, np.ndarray) and value.dtype.kind in "fiu":
            h.update(name.encode() + np.ascontiguousarray(value).tobytes())
    return h.hexdigest()


class EpisodeOver(RuntimeError):
    """The native task has terminated (success): an episode has no control steps after that."""


class Session:
    def __init__(self, instance="/app/instance.json"):
        self.path = Path(instance)
        self.spec = json.loads(self.path.read_text())
        if self.spec["upstream_commit"] != UPSTREAM:
            raise ValueError("instance was made for another VLABench commit")
        self.instance_sha = digest(self.spec)
        self.instruction = self.spec["instruction"]
        self.env = None
        self.reset()

    # -- episode -------------------------------------------------------------------------------------------------
    def reset(self) -> dict:
        """Rebuild the frozen scene (bit-exact; refuses to run if the model or the initial state differs)."""
        if self.env is not None:
            self.env.physics.free()
        self.env = env = build_env(self.spec)
        if env.task.should_terminate_episode(env.physics):
            raise RuntimeError("invalid instance: solved at the start")
        if state_hash(env) != self.spec["initial_state_sha256"]:
            raise RuntimeError("initial state differs from the frozen instance")
        if model_hash(env) != self.spec["model_sha256"]:
            raise RuntimeError("compiled model differs from the frozen instance")
        self.dt = float(env.control_timestep())
        self.substeps = int(env._n_sub_steps)
        spec = env.action_spec()
        self.lower, self.upper = np.asarray(spec.minimum, float), np.asarray(spec.maximum, float)
        self._native_step = env.step
        env.step = self._env_step  # VLABench's skills call env.step: their control steps are recorded like any other
        native_obs = env.get_observation

        class LazyObservation(dict):  # skills ask for observations after every step; render only on demand
            def __missing__(self, key):
                self.update(native_obs())
                return self[key]

        env.get_observation = lambda **kwargs: LazyObservation(q_state=env.robot.get_qpos(env.physics))
        self.actions: list[np.ndarray] = []
        self.done = False
        self.targets = np.r_[env.robot.get_qpos(env.physics), [0.04, 0.04]].astype(np.float64)
        return self.status()

    def _env_step(self, action=None):
        if self.done:
            raise EpisodeOver("the task has terminated (success); reset() to start again")
        a = self.targets if action is None else np.asarray(action, dtype=np.float64).reshape(-1)
        if a.shape != (N,) or not np.all(np.isfinite(a)):
            raise ValueError(f"an action is {N} finite numbers: 7 arm joint targets (rad) and 2 finger targets (m)")
        a = np.clip(a, self.lower, self.upper)
        result = self._native_step(a.copy())
        self.actions.append(a.copy())
        self.targets = a.copy()
        self.done = bool(result.last())
        return result

    def step(self, action) -> dict:
        """One control step (0.1 s) with absolute targets: 7 arm joint angles (rad), 2 finger positions (m, 0..0.04)."""
        self._env_step(action)
        return self.status()

    def skill(self, name: str, **kwargs) -> dict:
        """One of VLABench's general skills (SKILLS; VLABench.utils.skill_lib.SkillLib). Its control steps are part of
        the recorded actions. Returns whether the skill reached its own stage predicate."""
        if name not in SKILLS:
            raise ValueError(f"unknown skill {name!r}; one of {SKILLS}")
        from VLABench.utils.skill_lib import SkillLib

        before = len(self.actions)
        try:
            result = getattr(SkillLib, name)(self.env, **kwargs)
            ok, failure = bool(result is not None and result[2]), None
        except (ValueError, TypeError, AssertionError, RuntimeError) as exc:
            ok, failure = False, f"{type(exc).__name__}: {exc}"
        return {"stage_success": ok, "failure": failure, "executed_steps": len(self.actions) - before, **self.status()}

    def ik(self, position, quaternion_wxyz) -> dict:
        ok, q = self.env.robot.get_qpos_from_ee_pos(
            self.env.physics, pos=np.asarray(position), quat=np.asarray(quaternion_wxyz)
        )
        return {"success": bool(ok), "joint_positions": np.asarray(q).copy()}

    def replay(self, actions) -> dict:
        """Reset, then execute `actions` (T, 9): what the verifier does. Steps after the task terminated are invalid."""
        a = self.as_actions(actions)
        self.reset()
        for i, row in enumerate(a):
            if self.done:
                raise EpisodeOver(f"action {i} of {len(a)} comes after the task terminated")
            self._env_step(row)
        return self.status()

    def save_trajectory(self, actions=None, path="/app/output/trajectory.npz") -> str:
        """Write (T, 9) actions (default: every control step since the last reset); 1 <= T <= MAX_STEPS."""
        a = self.as_actions(self.actions if actions is None else actions)
        if not 1 <= len(a) <= MAX_STEPS:
            raise ValueError(f"a trajectory has 1..{MAX_STEPS} actions, got {len(a)}")
        meta = {"schema": SCHEMA, "instance_sha": self.instance_sha, "control_dt": self.dt, "dtype": "float64"}
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        np.savez(path, actions=a, meta=np.array(canonical(meta)))
        return str(path)

    def as_actions(self, actions) -> np.ndarray:
        a = np.asarray(actions, dtype=np.float64)
        if a.size == 0:
            return np.zeros((0, N))
        if a.ndim != 2 or a.shape[1] != N:
            raise ValueError(f"actions must have shape (T, {N}), got {list(a.shape)}")
        if not np.all(np.isfinite(a)):
            raise ValueError("actions contain NaN or inf")
        return np.clip(a, self.lower, self.upper)

    # -- state -------------------------------------------------------------------------------------------------
    @property
    def physics(self):
        return self.env.physics

    def success(self) -> bool:
        return bool(self.env.task.should_terminate_episode(self.env.physics))

    def state_sha(self) -> str:
        return state_hash(self.env)

    def status(self) -> dict:
        return {"success": self.success(), "done": self.done, "control_steps": len(self.actions),
                "state_sha": self.state_sha()}  # fmt: skip

    check = status

    def state(self) -> dict:
        """Privileged state (world frame, metres, quaternions w x y z): every entity and the robot."""
        env, ph = self.env, self.env.physics
        entities = {}
        for name, entity in env.task.entities.items():
            item = {
                "category": type(entity).__name__,
                "position": entity.get_xpos(ph),
                "quaternion_wxyz": entity.get_xqaut(ph),
            }
            for method in ("get_grasped_keypoints", "get_place_point", "get_start_button_pos"):
                if hasattr(entity, method):
                    try:
                        item[method] = np.asarray(getattr(entity, method)(ph))
                    except (ValueError, AttributeError, IndexError):
                        pass
            if entity.joints:
                item["joint_positions"] = ph.bind(entity.joints).qpos.copy()
            entities[name] = item
        fingers = [env.robot.mjcf_model.find("joint", f"finger_joint{i}") for i in (1, 2)]
        robot = {
            "joint_positions": env.robot.get_qpos(ph),
            "joint_velocities": env.robot.get_qvel(ph),
            "finger_positions": ph.bind(fingers).qpos.copy(),
            "tcp_position": env.get_ee_pos(),
            "tcp_quaternion_wxyz": env.get_ee_quat(),
        }
        return json.loads(canonical({"instruction": self.instruction, "entities": entities, "robot": robot,
                                     "action_lower": self.lower, "action_upper": self.upper, "control_dt": self.dt,
                                     **self.status()}))  # fmt: skip

    # -- cameras ----------------------------------------------------------------------------------------------
    def camera_id(self, camera: str) -> int:
        return self.env.physics.model.name2id(CAMERAS.get(camera, camera), "camera")

    def render(self, camera: str = "forward", width: int = 320, height: int = 320, depth: bool = False) -> np.ndarray:
        return self.env.physics.render(height=height, width=width, camera_id=self.camera_id(camera), depth=depth).copy()

    def calibration(self, camera: str, width: int = 320, height: int = 320) -> dict:
        """Pinhole intrinsics (OpenCV convention) and camera-to-world pose (OpenGL convention: looks along -z, +y up)."""
        ph, cid = self.env.physics, self.camera_id(camera)
        f = height / (2 * np.tan(np.deg2rad(ph.model.cam_fovy[cid]) / 2))
        T = np.eye(4)
        T[:3, :3] = ph.data.cam_xmat[cid].reshape(3, 3)
        T[:3, 3] = ph.data.cam_xpos[cid]
        return {"intrinsic_cv": [[f, 0, width / 2], [0, f, height / 2], [0, 0, 1]], "cam2world_gl": T.tolist()}

    def observe(self, camera: str = "forward", width: int = 320, height: int = 320) -> dict:
        """RGB, depth (m), intrinsics and camera-to-world pose of one camera (forward, left, right, wrist)."""
        return {"rgb": self.render(camera, width, height), "depth_m": self.render(camera, width, height, depth=True),
                **self.calibration(camera, width, height)}  # fmt: skip

    def render_video(self, actions, path, camera: str = "forward", every: int = 1, fps: int = 10) -> dict:
        """Reset, replay `actions` and write an mp4 (every `every`-th control step) plus <path>.last.png."""
        import imageio.v2 as imageio
        from PIL import Image

        a = self.as_actions(actions)
        self.reset()
        frames = [self.render(camera)]
        for i, row in enumerate(a):
            if self.done:
                break
            self._env_step(row)
            if (i + 1) % every == 0 or i == len(a) - 1:
                frames.append(self.render(camera))
        with imageio.get_writer(str(path), format="FFMPEG", mode="I", fps=fps, codec="libx264", macro_block_size=1,
                                output_params=["-movflags", "+faststart"]) as w:  # fmt: skip
            for f in frames:
                w.append_data(f)
        Image.fromarray(frames[-1]).save(str(path).removesuffix(".mp4") + ".last.png")
        return {"frames": len(frames), "path": str(path)}

    def close(self) -> None:
        if self.env is not None:
            self.env.physics.free()
            self.env = None
