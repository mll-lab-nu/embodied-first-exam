"""RoboCasa-series tooling: one robosuite / RoboCasa kitchen environment on a frozen instance.

Used by the privileged agent (importable as `casa_tool`), by the privileged verifier, and by the standard-mode sim
service (images/<benchmark>/standard/server_casa.py).

    import casa_tool
    s = casa_tool.Session("/app/instance.npz")  # the frozen instance; s.env is the robosuite env, s.model/s.data MuJoCo
    s.action_spec                               # the native controller's channels: names, units, limits, frames
    st = s.state()                              # privileged state: instruction, joints, every body's pose, objects
    r = s.step(action)                          # one native control step (1/20 s) -> {"success", "control_steps", ...}
    s.save_trajectory()                         # the actions since the last reset -> /app/output/trajectory.npz
    s.replay(actions)                           # reset, then replay (what the verifier does) -> {"success", "state_sha"}
    s.reset()                                   # back to the frozen start, as often as you like
    img = s.render("robot0_agentview_center")   # RGB (240, 320, 3); views in s.camera_views

Actions are the robot's native composite-controller commands, one row per control step, in the layout of
s.action_spec (clipped to its limits). Success is the environment's own check (`_check_success`) on the state after
the last action. The check runs exactly twice after every control step and once at reset (the call pattern the
frozen instances and references were validated with): some checks keep timers, so the pattern is part of the task.
"""

from __future__ import annotations

import copy
import ctypes
import glob
import hashlib
import json
import os
import random
import zipfile
from pathlib import Path

import mujoco
import numpy as np
import robocasa  # noqa: F401  (registers the kitchen environments)
import robosuite


def _disable_mesh_cache() -> None:
    """MuJoCo keeps a process-wide cache of compiled meshes (mj_globalCache). A mesh served from it can differ from a
    freshly compiled one (mesh_polynormal), so a scene built twice in one process could step differently from a scene
    built once, depending on what the process loaded before. With the cache off, every build compiles its meshes
    afresh, exactly as the first build in a fresh process does: one behaviour for the agent, verifier and service.
    Determinism depends on it, so a MuJoCo build without these symbols is an error, never a silent no-op."""
    libs = glob.glob(os.path.join(os.path.dirname(mujoco.__file__), "libmujoco.so*"))
    if not libs:
        raise RuntimeError(f"casa_tool: no libmujoco.so next to {mujoco.__file__}; cannot turn off the mesh cache")
    lib = ctypes.CDLL(libs[0])
    missing = [s for s in ("mj_globalCache", "mj_setCacheSize") if not hasattr(lib, s)]
    if missing:
        raise RuntimeError(
            f"casa_tool: {libs[0]} (MuJoCo {mujoco.__version__}) has no {', '.join(missing)}; the mesh cache cannot be "
            "turned off and replays would not be deterministic (this tooling is pinned to MuJoCo 3.3.1)"
        )
    lib.mj_globalCache.restype = ctypes.c_void_p
    lib.mj_setCacheSize.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    lib.mj_setCacheSize(lib.mj_globalCache(), 0)


_disable_mesh_cache()

INSTANCE_SCHEMA = "rcb-casa-instance-v1"
STATE_SPEC = mujoco.mjtState.mjSTATE_INTEGRATION
# Model arrays the kitchen's reset rewrites (fixture and object placement): part of the frozen instance.
MODEL_FIELDS = (
    "body_pos",
    "body_quat",
    "site_pos",
    "site_quat",
    "geom_pos",
    "geom_quat",
    "geom_size",
    "eq_data",
    "geom_rgba",
    "site_rgba",
)
MAX_STEPS = 3000  # privileged deliverable: at most this many control steps (the references' authoring cap)
ROBOT_PREFIXES = ("robot0_", "mobilebase0_", "gripper0_")
CAMERA_PREFERENCE = (
    "robot0_agentview_center",
    "robot0_agentview_left",
    "robot0_agentview_right",
    "egoview",
    "robot0_eye_in_hand",
    "robot0_eye_in_right_hand",
    "robot0_eye_in_left_hand",
)


# -- frozen instances -------------------------------------------------------------------------------------------
def encode(x):
    """JSON-safe encoding of numpy values, sets, tuples and dicts (raises TypeError for anything else)."""
    if isinstance(x, np.ndarray):
        if x.dtype.hasobject:
            raise TypeError("object array")
        return {"__array__": x.tolist(), "dtype": x.dtype.str}
    if isinstance(x, np.generic):
        return x.item()
    if isinstance(x, (set, frozenset)):
        values = sorted((encode(v) for v in x), key=lambda v: json.dumps(v, sort_keys=True))
        return {"__frozenset__" if isinstance(x, frozenset) else "__set__": values}
    if isinstance(x, tuple):
        return {"__tuple__": [encode(v) for v in x]}
    if isinstance(x, list):
        return [encode(v) for v in x]
    if isinstance(x, dict):
        if any(not isinstance(k, str) for k in x):
            raise TypeError("non-string key")
        return {k: encode(v) for k, v in x.items()}
    if x is None or isinstance(x, (int, float, str, bool)):
        return x
    raise TypeError(type(x).__name__)


def decode(x):
    if isinstance(x, dict):
        if "__set__" in x:
            return set(decode(v) for v in x["__set__"])
        if "__frozenset__" in x:
            return frozenset(decode(v) for v in x["__frozenset__"])
        if "__array__" in x:
            return np.asarray(x["__array__"], dtype=x["dtype"])
        if "__tuple__" in x:
            return tuple(decode(v) for v in x["__tuple__"])
        return {k: decode(v) for k, v in x.items()}
    if isinstance(x, list):
        return [decode(v) for v in x]
    return x


def caches(obj) -> dict:
    out = {}
    for k, v in vars(obj).items():
        try:
            value = encode(v)
            json.dumps(value, allow_nan=False)
        except (TypeError, ValueError):
            continue
        out[k] = value
    return out


def graph(env) -> dict:
    """The env's Python objects whose attributes make up the task state (no pickle, no dotted eval)."""
    out = {"env": env}
    for k, v in env.fixtures.items():
        out["fixture:" + k] = v
    for i, r in enumerate(env.robots):
        out["robot:" + str(i)] = r
        out["composite:" + str(i)] = r.composite_controller
        for k, v in r.part_controllers.items():
            out[f"controller:{i}:{k}"] = v
        for k, v in r.gripper.items():
            out[f"gripper:{i}:{k}"] = v
        for k, v in vars(r).items():
            if type(v).__module__ == "robosuite.utils.buffers":
                out[f"buffer:{i}:{k}"] = v
    for k, v in env._observables.items():
        out["observable:" + k] = v
    return out


def raw(env):
    return env.sim.model._model, env.sim.data._data


def physical(env) -> dict:
    m, d = raw(env)
    state = np.empty(mujoco.mj_stateSize(m, STATE_SPEC))
    mujoco.mj_getState(m, d, state, STATE_SPEC)
    out = {"integration": state}
    out.update({"model_" + k: getattr(m, k).copy() for k in MODEL_FIELDS})
    return out


def snapshot(env) -> dict:
    g = graph(env)
    out = physical(env)
    out["caches"] = np.array(json.dumps({k: caches(v) for k, v in g.items()}, sort_keys=True, allow_nan=False))
    out["attribute_names"] = np.array(json.dumps({k: sorted(vars(v)) for k, v in g.items()}, sort_keys=True))
    out["rng"] = np.array(json.dumps(encode(env.rng.bit_generator.state), sort_keys=True))
    out["global_rng"] = np.array(json.dumps(encode(np.random.get_state()), sort_keys=True))
    out["python_rng"] = np.array(json.dumps(encode(random.getstate())))
    return out


def restore(env, frozen: dict) -> None:
    m, d = raw(env)
    for k in MODEL_FIELDS:
        getattr(m, k)[:] = frozen["model_" + k]
    # Rebuilding from XML can create lazy task history (e.g. ScrubBowl.prev_sponge_pos): restore its absence too.
    if "attribute_names" in frozen:
        objects = graph(env)
        for name, names in json.loads(str(frozen["attribute_names"])).items():
            obj = objects[name]
            for key in set(vars(obj)) - set(names):
                delattr(obj, key)
    for name, values in decode(json.loads(str(frozen["caches"]))).items():
        obj = graph(env)[name]
        for k, v in values.items():
            setattr(obj, k, v)
    env.rng.bit_generator.state = decode(json.loads(str(frozen["rng"])))
    np.random.set_state(decode(json.loads(str(frozen["global_rng"]))))
    random.setstate(decode(json.loads(str(frozen["python_rng"]))))
    mujoco.mj_setState(m, d, frozen["integration"], STATE_SPEC)
    mujoco.mj_forward(m, d)
    mujoco.mj_setState(m, d, frozen["integration"], STATE_SPEC)  # forward changes warm-start fields: set them again


def make_env(config: dict, meta: dict | None = None, xml: str | None = None):
    random.seed(0)
    np.random.seed(0)
    kw = copy.deepcopy(config)
    kw.update(has_renderer=False, has_offscreen_renderer=False, use_camera_obs=False, seed=0)
    env = robosuite.make(**kw)
    if meta is not None:
        env.set_ep_meta(copy.deepcopy(meta))
    env.reset()
    if xml is not None:
        env.reset_from_xml_string(env.edit_model_xml(xml))
        env.sim.reset()
    return env


def digest(data: dict) -> str:
    sha = hashlib.sha256()
    for key, value in sorted(data.items()):
        arr = np.ascontiguousarray(value)
        sha.update(key.encode())
        sha.update(arr.dtype.str.encode())
        sha.update(str(arr.shape).encode())
        sha.update(arr.tobytes())
    return sha.hexdigest()


def load_npz(path, max_bytes: int = 8_000_000) -> dict:
    """Pickle-free NPZ loader with size limits (trajectories come from the agent)."""
    path = Path(path)
    if path.stat().st_size > max_bytes:
        raise ValueError("archive too large")
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if len(infos) > 64 or sum(i.file_size for i in infos) > 8 * max_bytes:
            raise ValueError("expanded archive too large")
        if any(not i.filename.endswith(".npy") for i in infos):
            raise ValueError("expected .npy members only")
    with np.load(path, allow_pickle=False) as data:
        return {k: data[k].copy() for k in data.files}


def load_instance(path) -> tuple[dict, str]:
    with np.load(path, allow_pickle=False) as z:
        data = {k: z[k].copy() for k in z.files}
    sha = str(data.pop("instance_sha"))
    if str(data.get("schema")) != INSTANCE_SCHEMA or digest(data) != sha:
        raise ValueError(f"{path}: not a valid frozen instance (hash mismatch)")
    return data, sha


def task_state(env) -> dict:
    """The task's own Python state (timers, previous positions, fixture flags), for the state hash."""
    skip = {"_obs_cache", "_ep_meta", "_cam_configs", "object_cfgs", "fixture_cfgs", "_curr_gen_fixtures"}
    tags = ("__array__", "__tuple__", "__set__", "__frozenset__")
    simple = {}
    for k, v in caches(env).items():
        if k in skip:
            continue
        if not isinstance(v, (dict, list, str)) or (isinstance(v, dict) and any(t in v for t in tags)):
            simple[k] = v
    fixture = {
        name: {k: v for k, v in caches(obj).items() if k.startswith("_") and isinstance(v, (int, float, bool))}
        for name, obj in env.fixtures.items()
    }
    return {"env": simple, "fixtures": fixture}


def state_hash(env) -> str:
    data = physical(env)
    data["task_state"] = np.array(json.dumps(task_state(env), sort_keys=True))
    return digest(data)


# -- the native action layout -------------------------------------------------------------------------------
def action_spec(env) -> dict:
    """Every channel of the robot's composite controller: name, unit, kind (delta | absolute | grip | mode), limits."""
    robot = env.robots[0]
    lo, hi = (np.asarray(x, float) for x in env.action_spec)
    dim = int(env.action_dim)
    if type(robot.robot_model).__name__ == "GR1ArmsAndWaistFourierHands":
        if dim != 24:
            raise ValueError("unsupported GR1 layout")
        names = [f"{arm}_{a}" for arm in ("right", "left") for a in ("x", "y", "z", "rx", "ry", "rz")]
        fingers = ("little", "ring", "middle", "index", "thumb_flexion", "thumb_rotation")
        names += [f"{arm}_{f}" for arm in ("right", "left") for f in fingers]
        units = ["m", "m", "m", "rad", "rad", "rad"] * 2 + ["hand_command"] * 12
        kinds = ["absolute"] * 24
        lower, upper = [-10.0] * 12 + [-3.0] * 12, [10.0] * 12 + [3.0] * 12
        frame = (
            "arm channels: absolute pose targets of each hand's grip site in the robot's base frame (XYZ metres, "
            "axis-angle radians), solved by the whole-body inverse-kinematics controller (mink); hand channels: "
            "unscaled Fourier hand commands, six per hand in the listed finger order (not a binary grip)"
        )
        parts = {"right": [0, 6], "left": [6, 12], "right_hand": [12, 18], "left_hand": [18, 24]}
    else:
        if dim not in (12, 13) or not (np.all(np.isfinite(lo)) and np.all(np.isfinite(hi))):
            raise ValueError("unsupported mobile Panda layout")
        parts = {k: list(v) for k, v in robot._action_split_indexes.items()}
        parts["hybrid_mode"] = [dim - 1, dim]
        if dim == 13:
            names = [f"arm_joint{i + 1}" for i in range(7)]
            units, kinds = ["rad"] * 7, ["absolute"] * 7
            frame = "arm channels: absolute joint position targets (rad); base and torso channels: robot base frame"
        else:
            names = ["arm_dx", "arm_dy", "arm_dz", "arm_drx", "arm_dry", "arm_drz"]
            units, kinds = ["normalised_translation"] * 3 + ["normalised_axis_angle"] * 3, ["delta"] * 6
            frame = (
                "arm channels: end-effector deltas in the robot base frame, scaled by the controller "
                "(1.0 = 5 cm / 0.5 rad per control step); base and torso channels: robot base frame"
            )
        names += ["grip", "base_x", "base_y", "base_yaw", "torso", "hybrid_mode"]
        units += ["normalised_grip", "normalised_velocity", "normalised_velocity", "normalised_yaw_velocity"]
        units += ["normalised_torso_velocity", "mode"]
        kinds += ["grip", "delta", "delta", "delta", "delta", "mode"]
        lower, upper = lo.tolist(), hi.tolist()
    if not (len(names) == len(units) == len(kinds) == dim):
        raise ValueError("action layout does not cover every channel")
    channels = [
        {"index": i, "name": n, "unit": u, "kind": k, "lower": lower[i], "upper": upper[i]}
        for i, (n, u, k) in enumerate(zip(names, units, kinds, strict=True))
    ]
    out = {
        "dim": dim,
        "control_hz": int(env.control_freq),
        "names": names,
        "lower": lower,
        "upper": upper,
        "channels": channels,
        "parts": parts,
        "frame": frame,
    }
    if dim in (12, 13):
        out["grip"] = "positive closes, negative opens"
        out["hybrid_mode"] = "> 0: base mode (the arm goal moves with the base); <= 0: arm mode (default -1)"
    return out


# -- the session ----------------------------------------------------------------------------------------------
def scene_option() -> mujoco.MjvOption:
    """What robosuite's own cameras draw (its defaults render_collision_mesh=False, render_visual_mesh=True): the visual
    geoms (group 1), not the collision geoms (group 0). MuJoCo's default MjvOption also draws group 0, which paints the
    collision shells over the scene (red fixtures, a green robot) and into the depth image."""
    opt = mujoco.MjvOption()
    opt.geomgroup[0] = 0
    opt.geomgroup[1] = 1
    return opt


class Session:
    mj = mujoco

    def __init__(self, instance="/app/instance.npz", enable_render: bool = False):
        self.instance_path = Path(instance)
        self.frozen, self.instance_sha = load_instance(self.instance_path)
        self.meta = json.loads(str(self.frozen["ep_meta"]))
        self.inst = {"text": self.meta.get("lang", ""), "env_name": json.loads(str(self.frozen["config"]))["env_name"]}
        self.env = None
        self._renderers: dict = {}
        self.reset()
        self.action_spec = action_spec(self.env)
        self.action_dim = self.action_spec["dim"]
        self.action_names = self.action_spec["names"]
        self.lower = np.asarray(self.action_spec["lower"], float)
        self.upper = np.asarray(self.action_spec["upper"], float)
        self.control_dt = 1.0 / float(self.env.control_freq)
        cams = [self.model.camera(i).name for i in range(self.model.ncam)]
        self.camera_views = {c: {"camera": c} for c in CAMERA_PREFERENCE if c in cams}
        self.proprio_layout = self._proprio_layout()
        self.targets = self.initial_command()

    # -- episode -------------------------------------------------------------------------------------------------
    def reset(self) -> dict:
        """Back to the frozen start (bit-exact)."""
        f = self.frozen
        self._close_renderers()
        if self.env is not None:
            self.env.close()
        self.env = make_env(json.loads(str(f["config"])), copy.deepcopy(self.meta), str(f["xml"]))
        restore(self.env, f)
        self.actions: list[np.ndarray] = []
        self.success = bool(self.env._check_success())
        self.initial_success = self.success
        self.reward = 0.0
        if hasattr(self, "action_spec"):
            self.targets = self.initial_command()
        return self._report()

    def step(self, action) -> dict:
        """One native control step; the action is clipped to the controller's limits."""
        a = np.asarray(action, dtype=np.float64).reshape(-1)
        if a.shape != (self.action_dim,) or not np.all(np.isfinite(a)):
            raise ValueError(f"an action is {self.action_dim} finite numbers (see action_spec)")
        a = np.clip(a, self.lower, self.upper)
        _, reward, _, _ = self.env.step(a.copy())
        self.env._check_success()  # first of the two checks per step (see the module docstring)
        self.success = bool(self.env._check_success())
        self.actions.append(a)
        self.targets = a
        self.reward = float(reward)
        return self._report()

    def initial_command(self) -> np.ndarray:
        """A command that holds the robot where it is: zero motion, the current joints or hand poses, grip open."""
        spec, a = self.action_spec, np.zeros(self.action_dim)
        m, d = self.model, self.data
        if self.action_dim == 13:
            arm = [m.joint(f"robot0_joint{i}").qposadr[0] for i in range(1, 8)]
            a[:7] = d.qpos[arm]
        for c in spec["channels"]:
            if c["kind"] in ("grip", "mode"):
                a[c["index"]] = -1.0
        if self.action_dim == 24:
            a[:] = self._gr1_hold()
        return a

    def _gr1_hold(self) -> np.ndarray:
        """GR1: each grip site's current pose in the base frame, and hand commands at the current finger positions."""
        from scipy.spatial.transform import Rotation

        r, m, d = self.env.robots[0], self.model, self.data
        base = m.body(r.robot_model.root_body).id
        rb, pb = d.xmat[base].reshape(3, 3), d.xpos[base]
        a = np.zeros(24)
        for k, arm in enumerate(("right", "left")):
            site = m.site(f"gripper0_{arm}_grip_site").id
            a[6 * k : 6 * k + 3] = rb.T @ (d.site_xpos[site] - pb)
            a[6 * k + 3 : 6 * k + 6] = Rotation.from_matrix(rb.T @ d.site_xmat[site].reshape(3, 3)).as_rotvec()
        ctrl = np.asarray(d.ctrl, float)
        for k, arm in enumerate(("right", "left")):
            idx = r._ref_actuators_indexes_dict[f"{arm}_gripper"] if hasattr(r, "_ref_actuators_indexes_dict") else []
            if len(idx) >= 6:
                a[12 + 6 * k : 18 + 6 * k] = ctrl[list(idx)[:6]]
        return a

    def hold_targets(self) -> np.ndarray:
        """The last command with every delta / velocity channel set to zero: the robot holds still."""
        h = np.asarray(self.targets, float).copy()
        for c in self.action_spec["channels"]:
            if c["kind"] == "delta":
                h[c["index"]] = 0.0
        return h

    def replay(self, actions) -> dict:
        """Reset, then execute `actions` (T, dim): what the verifier does."""
        a = as_actions(actions, self.action_dim)
        self.reset()
        for row in a:
            self.step(row)
        return {
            "success": self.success,
            "initial_success": self.initial_success,
            "state_sha": self.state_sha(),
            "control_steps": len(a),
            "final_reward": self.reward,
        }

    def save_trajectory(self, actions=None, path="/app/output/trajectory.npz", meta: dict | None = None) -> str:
        """Write (T, dim) actions (default: those since the last reset); 1 <= T <= MAX_STEPS."""
        a = as_actions(self.actions if actions is None else actions, self.action_dim)
        if not 1 <= len(a) <= MAX_STEPS:
            raise ValueError(f"a trajectory has 1..{MAX_STEPS} actions, got {len(a)}")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        np.savez(path, actions=a, instance_sha=np.array(self.instance_sha), meta=np.array(json.dumps(meta or {})))
        return str(path)

    # -- state -------------------------------------------------------------------------------------------------
    @property
    def model(self):
        return raw(self.env)[0]

    @property
    def data(self):
        return raw(self.env)[1]

    def check(self) -> dict:
        """The success check's last result (no extra call: the call pattern is part of the task)."""
        return self._report()

    def state_sha(self) -> str:
        return state_hash(self.env)

    def _robot_joints(self) -> list[str]:
        m = self.model
        names = [m.joint(i).name for i in range(m.njnt)]
        return [n for n in names if n.startswith(ROBOT_PREFIXES) and m.joint(n).type[0] != mujoco.mjtJoint.mjJNT_FREE]

    def _proprio_layout(self) -> list[str]:
        joints = self._robot_joints()
        arms = sorted(self.env.robots[0].eef_site_id)
        return (
            [f"{j}_pos" for j in joints]
            + [f"{j}_vel" for j in joints]
            + [f"eef_{arm}_{a}" for arm in arms for a in "xyz"]
            + [f"cmd_{n}" for n in self.action_names]
        )

    def proprio(self) -> np.ndarray:
        m, d = self.model, self.data
        joints = self._robot_joints()
        q = [d.qpos[m.joint(j).qposadr[0]] for j in joints]
        qd = [d.qvel[m.joint(j).dofadr[0]] for j in joints]
        sites = self.env.robots[0].eef_site_id
        eef = [d.site_xpos[sites[arm]] for arm in sorted(sites)]
        return np.concatenate([q, qd, *eef, self.targets]).astype(np.float32)

    def state(self) -> dict:
        """Privileged state (world frame, metres, quaternions w x y z)."""
        m, d = self.model, self.data
        bodies = {}
        for i in range(m.nbody):
            if m.body(i).name:
                bodies[m.body(i).name] = {"pos": d.xpos[i].copy(), "quat_wxyz": d.xquat[i].copy()}
        return {
            "instruction": self.inst["text"],
            "qpos": d.qpos.copy(),
            "qvel": d.qvel.copy(),
            "joint_names": [m.joint(i).name for i in range(m.njnt)],
            "bodies": bodies,
            "objects": self.meta.get("object_cfgs", []),
            "proprio": dict(zip(self.proprio_layout, self.proprio().tolist(), strict=True)),
            **self._report(),
        }

    def _report(self) -> dict:
        return {"success": self.success, "reward": self.reward, "control_steps": len(self.actions)}

    # -- rendering ---------------------------------------------------------------------------------------------
    def render(self, camera: str = "robot0_agentview_center", size: tuple[int, int] = (320, 240)) -> np.ndarray:
        w, h = size
        if (w, h) not in self._renderers:
            self._renderers[(w, h)] = mujoco.Renderer(self.model, h, w)
        r = self._renderers[(w, h)]
        cam = self.camera_views.get(camera, {"camera": camera})["camera"]
        r.update_scene(self.data, camera=cam, scene_option=scene_option())
        return r.render().copy()

    def render_grid(self, size: tuple[int, int] = (320, 240)) -> np.ndarray:
        imgs = [self.render(c, size) for c in list(self.camera_views)[:4]]
        while len(imgs) < 4:
            imgs.append(np.zeros_like(imgs[0]))
        return np.concatenate([np.concatenate(imgs[:2], 1), np.concatenate(imgs[2:4], 1)], 0)

    def render_video(self, actions, path, every: int = 2, fps: int = 10, camera: str | None = None) -> dict:
        """Reset, replay `actions` and write an mp4 (every `every`-th control step) plus <path>.last.png."""
        import imageio.v2 as imageio
        from PIL import Image

        a = as_actions(actions, self.action_dim)
        camera = camera or next(iter(self.camera_views))
        self.reset()
        frames = [self.render(camera)]
        for i, row in enumerate(a):
            self.step(row)
            if (i + 1) % every == 0 or i == len(a) - 1:
                frames.append(self.render(camera))
        with imageio.get_writer(
            str(path),
            format="FFMPEG",
            mode="I",
            fps=fps,
            codec="libx264",
            macro_block_size=1,
            output_params=["-movflags", "+faststart"],
        ) as w:
            for f in frames:
                w.append_data(f)
        Image.fromarray(frames[-1]).save(str(path).removesuffix(".mp4") + ".last.png")
        return {"frames": len(frames), "path": str(path)}

    def _close_renderers(self) -> None:
        for r in self._renderers.values():
            r.close()
        self._renderers = {}

    def close(self) -> None:
        self._close_renderers()
        if self.env is not None:
            self.env.close()
            self.env = None


def as_actions(actions, dim: int) -> np.ndarray:
    a = np.asarray(actions, dtype=np.float64)
    if a.size == 0:
        return np.zeros((0, dim))
    if a.ndim != 2 or a.shape[1] != dim:
        raise ValueError(f"actions must have shape (T, {dim}), got {list(a.shape)}")
    if not np.all(np.isfinite(a)):
        raise ValueError("actions contain NaN or inf")
    return a
