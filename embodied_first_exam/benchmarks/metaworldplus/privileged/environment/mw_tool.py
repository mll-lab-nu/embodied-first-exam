"""MetaWorld+ tooling: one Meta-World v3 environment on a frozen instance.

Used by the privileged agent (importable as `mw_tool`), by the privileged verifier, and by the standard-mode sim
service (images/metaworld/standard/server_mw.py).

    import mw_tool
    s = mw_tool.Session("/app/instance.npz")  # the frozen instance; s.env is the Meta-World env, s.model / s.data MuJoCo
    st = s.state()                             # privileged state: tcp, gripper, mocap, joints, objects, target, bodies
    r = s.step([dx, dy, dz, grip])             # one control step (1/80 s) -> {"success": ..., "control_steps": ...}
    s.save_trajectory()                        # the actions since the last reset -> /app/output/trajectory.npz
    s.replay(actions)                          # reset, then replay (what the verifier does) -> {"success", "state_sha"}
    s.reset()                                  # back to the frozen start, as often as you like
    img = s.render("front")                    # RGB (240, 320, 3); views in CAMERA_VIEWS

Actions are Meta-World's own: [dx, dy, dz, grip], clipped to [-1, 1]. dx, dy, dz move the mocap target that drags the
hand by action x 1 cm per control step (world frame); grip drives the two fingers (+1 closes, -1 opens). Success is
Meta-World's own check (`evaluate_state`) on the state after the last action.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import mujoco
import numpy as np
from metaworld.env_dict import ENV_CLS_MAP

INSTANCE_SCHEMA = "eai-metaworld-instance/1"
STATE_SPEC = mujoco.mjtState.mjSTATE_INTEGRATION
# Model arrays Meta-World's reset rewrites (object and goal placement): part of the frozen instance.
MODEL_FIELDS = ("body_pos", "body_quat", "site_pos", "site_quat", "geom_pos", "geom_quat", "geom_size", "eq_data")
CONTROL_DT = 0.0125  # MuJoCo timestep 0.0025 s x Meta-World frame_skip 5 (80 Hz)
N = 4
ACTION_NAMES = ["dx", "dy", "dz", "grip"]
MAX_STEPS = 500  # privileged deliverable: at most Meta-World's max_path_length actions
ACTION_TYPE = {
    "name": "ee_delta",
    "dtype": "float64",
    "units": "dx, dy, dz: 1.0 = 1 cm of hand-target motion per control step (world frame); grip: -1 open .. +1 close",
    "semantics": (
        "Meta-World's native action, applied once per control step: the hand's mocap target moves by "
        "[dx, dy, dz] x 0.01 m (kept inside the workspace box), the arm follows it through a weld constraint, and grip "
        "is the finger actuators' command (+1 closes, -1 opens). The wrist orientation is fixed."
    ),
}
# Fixed views: free cameras around the table (looking at the workspace centre) and Meta-World's own top view.
_LOOKAT = (0.0, 0.65, 0.05)
CAMERA_VIEWS = {
    "front": {"lookat": _LOOKAT, "distance": 1.5, "azimuth": 270.0, "elevation": -30.0},
    "left": {"lookat": _LOOKAT, "distance": 1.5, "azimuth": 0.0, "elevation": -30.0},
    "right": {"lookat": _LOOKAT, "distance": 1.5, "azimuth": 180.0, "elevation": -30.0},
    "topview": {"camera": "topview"},
}
ARM_JOINTS = [f"right_j{i}" for i in range(7)]
FINGER_JOINTS = ["r_close", "l_close"]
PROPRIO_LAYOUT = (
    ["tcp_x", "tcp_y", "tcp_z", "gripper_opening", "mocap_x", "mocap_y", "mocap_z"]
    + [f"{j}_pos" for j in ARM_JOINTS]
    + [f"{j}_vel" for j in ARM_JOINTS]
    + [f"{j}_pos" for j in FINGER_JOINTS]
    + [f"cmd_{a}" for a in ACTION_NAMES]
)


def encode(x):
    """JSON-safe encoding of numpy values, tuples and dicts (raises TypeError for anything else)."""
    if isinstance(x, np.ndarray):
        if x.dtype.hasobject:
            raise TypeError("object array")
        return {"__array__": x.tolist(), "dtype": x.dtype.str}
    if isinstance(x, np.generic):
        return x.item()
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
        if "__array__" in x:
            return np.asarray(x["__array__"], dtype=x["dtype"])
        if "__tuple__" in x:
            return tuple(decode(v) for v in x["__tuple__"])
        return {k: decode(v) for k, v in x.items()}
    if isinstance(x, list):
        return [decode(v) for v in x]
    return x


def digest(data: dict) -> str:
    sha = hashlib.sha256()
    for key, value in sorted(data.items()):
        arr = np.ascontiguousarray(value)
        sha.update(key.encode())
        sha.update(arr.dtype.str.encode())
        sha.update(str(arr.shape).encode())
        sha.update(arr.tobytes())
    return sha.hexdigest()


def load_npz(path, max_bytes: int = 2_000_000) -> dict:
    """Pickle-free NPZ loader with size limits (trajectories come from the agent)."""
    path = Path(path)
    if path.stat().st_size > max_bytes:
        raise ValueError("archive too large")
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if len(infos) > 64 or sum(i.file_size for i in infos) > 4 * max_bytes:
            raise ValueError("expanded archive too large")
        if any(not i.filename.endswith(".npy") for i in infos):
            raise ValueError("expected .npy members only")
    with np.load(path, allow_pickle=False) as data:
        return {k: data[k].copy() for k in data.files}


def as_actions(actions) -> np.ndarray:
    a = np.asarray(actions, dtype=np.float64)
    if a.size == 0:
        return np.zeros((0, N))
    if a.ndim != 2 or a.shape[1] != N:
        raise ValueError(f"actions must have shape (T, {N}), got {list(a.shape)}")
    if not np.all(np.isfinite(a)):
        raise ValueError("actions contain NaN or inf")
    return np.clip(a, -1.0, 1.0)


def integration(env) -> np.ndarray:
    a = np.empty(mujoco.mj_stateSize(env.model, STATE_SPEC))
    mujoco.mj_getState(env.model, env.data, a, STATE_SPEC)
    return a


def caches(env) -> dict:
    """Every JSON-encodable attribute of the env (positions, goal, flags, previous observation)."""
    out = {}
    for key, value in vars(env).items():
        try:
            encoded = encode(value)
            json.dumps(encoded, allow_nan=False)
        except (TypeError, ValueError):
            continue
        out[key] = encoded
    return out


def snapshot(env) -> dict:
    out = {"integration": integration(env)}
    out.update({"model_" + k: getattr(env.model, k).copy() for k in MODEL_FIELDS})
    out["caches"] = np.array(json.dumps(caches(env), sort_keys=True, allow_nan=False))
    out["rng"] = np.array(json.dumps(encode(env.np_random.bit_generator.state), sort_keys=True))
    out["global_rng"] = np.array(json.dumps(encode(np.random.get_state()), sort_keys=True))
    return out


def make_env(env_id: str, seed: int, rand_vec=None):
    """Meta-World's goal-observable v3 env (reward v2) with its task randomization drawn from `seed`."""
    np.random.seed(seed)
    env = ENV_CLS_MAP[env_id](reward_function_version="v2")
    env._set_task_called = True
    env._partially_observable = False
    env.__dict__.pop("sawyer_observation_space", None)  # cached for the hidden-goal mode; drop it as upstream does
    env.seed(seed)
    env.seeded_rand_vec = True
    env._freeze_rand_vec = rand_vec is not None
    if rand_vec is not None:
        env._last_rand_vec = np.asarray(rand_vec)
    env.reset()
    return env


def create_instance(env_id: str, seed: int, text: str) -> dict:
    env = make_env(env_id, seed)
    try:
        data = {
            "env_id": np.array(env_id),
            "seed": np.array(seed),
            "text": np.array(text),
            "observation": env._get_obs().copy(),
            "rand_vec": env._last_rand_vec.copy(),
            "schema": np.array(INSTANCE_SCHEMA),
        }
        data.update(snapshot(env))  # after _get_obs, which updates the previous-observation cache
        data["instance_sha"] = np.array(digest(data))
        return data
    finally:
        env.close()


def load_instance(path) -> dict:
    d = load_npz(path)
    sha = str(d.pop("instance_sha"))
    if str(d.get("schema")) != INSTANCE_SCHEMA or digest(d) != sha:
        raise ValueError(f"{path}: not a valid frozen instance (hash mismatch)")
    d["instance_sha"] = sha
    return d


class Session:
    mj = mujoco

    def __init__(self, instance="/app/instance.npz", enable_render: bool = False):
        self.instance_path = Path(instance)
        self.frozen = load_instance(self.instance_path)
        self.instance_sha = self.frozen["instance_sha"]
        self.inst = {"text": str(self.frozen["text"]), "env_id": str(self.frozen["env_id"])}
        self.lower = np.full(N, -1.0)
        self.upper = np.full(N, 1.0)
        self.env = None
        self._renderer = None
        self.reset()

    # -- episode -------------------------------------------------------------------------------------------------
    def reset(self) -> dict:
        """Back to the frozen start (bit-exact)."""
        f = self.frozen
        self._close_renderer()
        if self.env is not None:
            self.env.close()
        self.env = env = make_env(str(f["env_id"]), int(f["seed"]), f["rand_vec"])
        for k in MODEL_FIELDS:
            getattr(env.model, k)[:] = f["model_" + k]
        for k, v in decode(json.loads(str(f["caches"]))).items():
            setattr(env, k, v)
        env.np_random.bit_generator.state = decode(json.loads(str(f["rng"])))
        np.random.set_state(decode(json.loads(str(f["global_rng"]))))
        mujoco.mj_setState(env.model, env.data, f["integration"], STATE_SPEC)
        mujoco.mj_forward(env.model, env.data)
        mujoco.mj_setState(env.model, env.data, f["integration"], STATE_SPEC)
        env.max_path_length = float("inf")  # the deliverable's length is checked by save_trajectory and the verifier
        self._jq = [env.model.joint(j).qposadr[0] for j in ARM_JOINTS + FINGER_JOINTS]
        self._jv = [env.model.joint(j).dofadr[0] for j in ARM_JOINTS]
        self.obs = f["observation"].copy()
        self.actions: list[np.ndarray] = []
        self.targets = np.array([0.0, 0.0, 0.0, float(env.data.ctrl[0])])
        self.reward, self.info = env.evaluate_state(self.obs, np.zeros(N))
        self.reward = float(self.reward)
        return self._report()

    def step(self, action) -> dict:
        """One control step with a = [dx, dy, dz, grip] (clipped to [-1, 1])."""
        a = np.asarray(action, dtype=np.float64).reshape(-1)
        if a.shape != (N,) or not np.all(np.isfinite(a)):
            raise ValueError("an action is 4 finite numbers [dx, dy, dz, grip]")
        a = np.clip(a, -1.0, 1.0)
        self.obs, reward, _, _, info = self.env.step(a.copy())
        if self.env._did_see_sim_exception:
            raise RuntimeError("MuJoCo reported a simulation instability")
        self.actions.append(a)
        self.targets = a
        self.reward, self.info = float(reward), info
        return self._report()

    def hold_targets(self) -> np.ndarray:
        """The action that keeps the hand where it is and the fingers as they are."""
        return np.array([0.0, 0.0, 0.0, self.targets[3]])

    def replay(self, actions) -> dict:
        """Reset, then execute `actions` (T, 4): what the verifier does."""
        a = as_actions(actions)
        self.reset()
        for row in a:
            self.step(row)
        return {
            "success": bool(self.info["success"]),
            "state_sha": self.state_sha(),
            "control_steps": len(a),
            "final_reward": self.reward,
        }

    def save_trajectory(self, actions=None, path="/app/output/trajectory.npz", meta: dict | None = None) -> str:
        """Write (T, 4) actions (default: those since the last reset); 1 <= T <= MAX_STEPS."""
        a = as_actions(self.actions if actions is None else actions)
        if not 1 <= len(a) <= MAX_STEPS:
            raise ValueError(f"a trajectory has 1..{MAX_STEPS} actions, got {len(a)}")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        np.savez(path, actions=a, instance_sha=np.array(self.instance_sha), meta=np.array(json.dumps(meta or {})))
        return str(path)

    # -- state -------------------------------------------------------------------------------------------------
    @property
    def model(self):
        return self.env.model

    @property
    def data(self):
        return self.env.data

    @property
    def target_pos(self) -> np.ndarray:
        return np.asarray(self.env._target_pos, float).copy()

    def check(self) -> dict:
        """Meta-World's success check on the current state."""
        return self._report()

    def state_sha(self) -> str:
        return hashlib.sha256(integration(self.env).tobytes()).hexdigest()

    def proprio(self) -> np.ndarray:
        d = self.env.data
        return np.concatenate(
            [
                self.env.tcp_center,
                [self.obs[3]],
                d.mocap_pos[0],
                d.qpos[self._jq[:7]],
                d.qvel[self._jv],
                d.qpos[self._jq[7:]],
                self.targets,
            ]
        ).astype(np.float32)

    def state(self) -> dict:
        """Privileged state (world frame, metres, quaternions w x y z)."""
        m, d, o = self.env.model, self.env.data, self.obs
        return {
            "tcp": self.env.tcp_center.copy(),
            "gripper_opening": float(o[3]),
            "mocap_pos": d.mocap_pos[0].copy(),
            "target_pos": self.target_pos,
            "object_pos": o[4:7].copy(),
            "object_quat_wxyz": o[7:11].copy(),
            "object2_pos": o[11:14].copy(),
            "object2_quat_wxyz": o[14:18].copy(),
            "observation": o.copy(),
            "qpos": d.qpos.copy(),
            "qvel": d.qvel.copy(),
            "bodies": {
                m.body(i).name: {"pos": d.xpos[i].copy(), "quat_wxyz": d.xquat[i].copy()} for i in range(m.nbody)
            },
            "proprio": dict(zip(PROPRIO_LAYOUT, self.proprio().tolist(), strict=True)),
            **self._report(),
        }

    def _report(self) -> dict:
        out = {k: float(v) for k, v in self.info.items() if np.isscalar(v)}
        out.update(success=bool(self.info["success"]), reward=self.reward, control_steps=len(self.actions))
        return out

    # -- rendering ---------------------------------------------------------------------------------------------
    def _view(self, renderer, camera: str) -> None:
        v = CAMERA_VIEWS[camera]
        if "camera" in v:
            renderer.update_scene(self.env.data, camera=v["camera"])
            return
        c = mujoco.MjvCamera()
        c.lookat[:] = v["lookat"]
        c.distance, c.azimuth, c.elevation = v["distance"], v["azimuth"], v["elevation"]
        renderer.update_scene(self.env.data, camera=c)

    def render(self, camera: str = "front", size: tuple[int, int] = (320, 240)) -> np.ndarray:
        w, h = size
        if self._renderer is None or self._renderer[0] != (w, h):
            self._close_renderer()
            self._renderer = ((w, h), mujoco.Renderer(self.env.model, h, w))
        r = self._renderer[1]
        self._view(r, camera)
        return r.render().copy()

    def render_grid(self, size: tuple[int, int] = (320, 240)) -> np.ndarray:
        imgs = [self.render(c, size) for c in CAMERA_VIEWS]
        return np.concatenate([np.concatenate(imgs[:2], 1), np.concatenate(imgs[2:4], 1)], 0)

    def render_video(self, actions, path, every: int = 2, fps: int = 40, camera: str = "front") -> dict:
        """Reset, replay `actions` and write an mp4 (every `every`-th control step) plus <path>.last.png."""
        import imageio.v2 as imageio
        from PIL import Image

        a = as_actions(actions)
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
            output_params=["-movflags", "+faststart", "-pix_fmt", "yuv420p"],
        ) as w:
            for f in frames:
                w.append_data(f)
        Image.fromarray(frames[-1]).save(str(path).removesuffix(".mp4") + ".last.png")
        return {"frames": len(frames), "path": str(path)}

    def _close_renderer(self) -> None:
        if self._renderer is not None:
            self._renderer[1].close()
            self._renderer = None

    def close(self) -> None:
        self._close_renderer()
        if self.env is not None:
            self.env.close()
            self.env = None
