"""rcb_kinder.py -- task-local tooling for KinDER: the frozen instance, recording, deterministic replay.

Concepts
--------
instance    instance.json: which KinDER environment, the seed its procedural generator builds the scene from, the
            episode length, and a digest of the scene that seed builds. KinDER regenerates a scene from its seed, bit
            for bit; the digest catches the day it stops doing so. Optionally `task_view`: where the camera of that
            name stands, for a task whose upstream camera looks down from high overhead.
scene       MuJoCo tasks (KinDER's Dynamic3D) stand in KinDER's MimicLabs lab (upstream's scene_bg): textured floor,
            walls and furniture. It changes the images; the physics only where upstream says so (Dynamo3D: the lab's
            walls are solid, like the room walls they stand in for). Every task's t=0 state and replayed trajectories
            are bit-identical either way. The PyBullet (Kinematic3D) tasks have upstream's one scene.
trajectory  (T, D) actions, one row per control step (10 Hz in MuJoCo), in KinDER's own action space
            (`s.action_space`). Replayed open-loop from the instance, it reproduces bit for bit (on the CPU).
success     KinDER's own goal check -- the environment's `terminated` -- at any step within the episode. The episode
            ends there.

Python API
----------
  from rcb_kinder import Session
  s = Session()                           # /app/instance.json
  obs = s.reset()                         # the frozen scene; obs is KinDER's state vector
  s.state()                               # the same state with names: s.state().pretty_str()
  with s.recording() as rec:
      for _ in range(s.max_steps):
          obs, success, done = s.step(my_controller(obs))
          if done:
              break
  s.replay(rec.actions)                   # self-check: from the frozen scene, open-loop
  s.save_trajectory(rec.actions, "/app/output/trajectory.npz")
  s.env                                   # the KinDER environment itself, with state access (get_state/set_state)
  s.images(["task_view"])                 # {camera: H x W x 3 uint8}; s.cameras lists them (PyBullet: "render")

CLI
---
  python rcb_kinder.py replay --traj /app/output/trajectory.npz [--instance /app/instance.json]
  python rcb_kinder.py render --traj /app/output/trajectory.npz --out replay.mp4 [--camera NAME]
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

import numpy as np

MUJOCO = "kinder.envs.dynamic3d"   # KinDER's MuJoCo environments: named cameras, the lab; the others render one view
CAMERA_HW = (480, 640)   # upstream's TidyBot3DConfig camera_height, camera_width
SCENE_BG = True          # the MimicLabs lab (see `scene` above); upstream's default is a bare white floor
NEAR_CLIP_M = 0.01       # the cameras' near clip, as in the bare scene: MuJoCo scales it with the scene, ten times larger


def _resolve_gl_backend() -> str:
    """MuJoCo's offscreen GL backend: an explicit MUJOCO_GL wins; else egl when the GPU can render (tried in a throwaway
    process, since MuJoCo binds its backend once, at import), else osmesa on the CPU."""
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


GL_BACKEND = _resolve_gl_backend()
os.environ["MUJOCO_GL"] = os.environ["PYOPENGL_PLATFORM"] = GL_BACKEND

import gymnasium  # noqa: E402
import kinder  # noqa: E402

# kinder.register_all_environments() sets MUJOCO_GL=osmesa whenever DISPLAY is unset, which would override the choice
# above (a CPU render takes ~50 ms at 640x480, egl ~1 ms). A placeholder DISPLAY for the call keeps the choice.
_display = os.environ.get("DISPLAY")
os.environ["DISPLAY"] = _display or ":rcb-unused"
kinder.register_all_environments()
if _display is None:
    del os.environ["DISPLAY"]


class _Recording:
    def __init__(self) -> None:
        self._rows: list[np.ndarray] = []

    @property
    def actions(self) -> np.ndarray:
        return np.asarray(self._rows, dtype=np.float64)

    def __len__(self) -> int:
        return len(self._rows)


class Session:
    """One frozen KinDER instance."""

    def __init__(self, instance: str | Path = "/app/instance.json") -> None:
        self.instance = json.loads(Path(instance).read_text())
        self.env_id, self.seed = self.instance["env_id"], int(self.instance["seed"])
        self.max_steps = int(self.instance["max_steps"])
        self.mujoco = gymnasium.spec(self.env_id).entry_point.startswith(MUJOCO)
        self.env = kinder.make(self.env_id, allow_state_access=True,
                               **({"scene_bg": SCENE_BG} if self.mujoco else {"render_mode": "rgb_array"}))
        if "task_view" in self.instance:   # KinDER builds its model from this config on every reset, the next included
            cams = self.env.unwrapped._object_centric_env.task_config["cameras"]
            cams["task_view"] = {**cams["task_view"], **self.instance["task_view"]}
        self.action_space = self.env.action_space
        self.t = 0
        self._rec: _Recording | None = None
        self._renderers: dict = {}
        self.reset()
        if "task_view" in self.instance and not np.allclose(
                self.model.cam_pos[self.model.camera("task_view").id], self.instance["task_view"]["position"]):
            raise RuntimeError("KinDER no longer builds task_view from its task config: the instance's camera is ignored")
        if self.instance.get("scene_sha") and self.state_sha() != self.instance["scene_sha"]:
            raise RuntimeError(f"seed {self.seed} no longer builds this instance's scene: KinDER has drifted")

    # ------------------------------------------------------------------ simulation
    def reset(self) -> np.ndarray:
        """Back to the frozen scene. (KinDER rebuilds its MuJoCo model on every reset.)"""
        self._obs, _ = self.env.reset(seed=self.seed)
        if self.mujoco:
            self.model.vis.map.znear = NEAR_CLIP_M / self.model.stat.extent   # images only: rendering reads it
        for r in self._renderers.values():   # each holds a GL context on the model just replaced
            r.close()
        self.t, self._renderers = 0, {}
        return self._obs

    def check_action(self, action) -> np.ndarray:
        a = np.asarray(action, dtype=np.float64)
        if a.shape != self.action_space.shape:
            raise ValueError(f"an action has {self.action_space.shape[0]} values, got shape {a.shape}")
        if not np.all(np.isfinite(a)):
            raise ValueError("action contains NaN/inf")
        low, high, tol = self.action_space.low, self.action_space.high, 1e-6
        if np.any(a < low - tol) or np.any(a > high + tol):
            bad = [i for i in range(a.size) if not low[i] - tol <= a[i] <= high[i] + tol]
            raise ValueError(f"action values {bad} are outside the action space's bounds")
        return a

    def step(self, action) -> tuple[np.ndarray, bool, bool]:
        """One control step: (obs, success, done). done = success, or the episode's last step."""
        a = self.check_action(action)
        self._obs, _, terminated, _, _ = self.env.step(a.astype(self.action_space.dtype))
        self.t += 1
        if self._rec is not None:
            self._rec._rows.append(a)
        success = bool(terminated)
        return self._obs, success, success or self.t >= self.max_steps

    def obs(self) -> np.ndarray:
        return self._obs

    def state(self):
        """KinDER's object-centric state: every object's features by name (`.pretty_str()` prints them)."""
        return self.env.observation_space.devectorize(self._obs)

    def state_sha(self) -> str:
        return hashlib.sha256(np.asarray(self._obs, dtype=np.float64).tobytes()).hexdigest()[:16]

    @contextlib.contextmanager
    def recording(self):
        """Records every action stepped inside the block."""
        self._rec = _Recording()
        try:
            yield self._rec
        finally:
            self._rec = None

    # ------------------------------------------------------------------ images
    @property
    def model(self):
        return self._sim().model.mj_model

    @property
    def data(self):
        return self._sim().data.mj_data

    def _sim(self):
        return self.env.unwrapped._object_centric_env._robot_env.sim

    @property
    def cameras(self) -> list[str]:
        return [self.model.camera(i).name for i in range(self.model.ncam)] if self.mujoco else ["render"]

    @property
    def view(self) -> str:
        """The camera that frames the whole task: the videos' default."""
        return "task_view" if self.mujoco else "render"

    def _renderer(self, hw: tuple[int, int]):
        import mujoco
        key = (id(self.model), hw)
        if key not in self._renderers:
            self._renderers[key] = mujoco.Renderer(self.model, *hw)
        return self._renderers[key]

    def images(self, cameras: list[str], hw: tuple[int, int] = CAMERA_HW, depth: bool = False) -> dict[str, np.ndarray]:
        """RGB (uint8, H x W x 3) or, with depth=True, depth in metres (float32, H x W) from the named cameras. One
        renderer serves both: with a second one (a second EGL context) the two hand each other's frames back. The
        PyBullet environments render one view, "render", RGB only, at upstream's size."""
        if not self.mujoco:
            if depth or set(cameras) - {"render"}:
                raise ValueError('this environment renders one RGB view, "render"')
            return {c: self.env.render() for c in cameras}
        r, out = self._renderer(hw), {}
        if depth:
            r.enable_depth_rendering()
        else:
            r.disable_depth_rendering()
        for c in cameras:
            r.update_scene(self.data, camera=c)
            out[c] = r.render()
        return out

    # ------------------------------------------------------------------ trajectories
    def check_trajectory(self, actions) -> np.ndarray:
        acts = np.asarray(actions, dtype=np.float64)
        if acts.ndim != 2 or acts.shape[1:] != self.action_space.shape:
            raise ValueError(f"a trajectory is (T, {self.action_space.shape[0]}), got shape {acts.shape}")
        for a in acts:
            self.check_action(a)
        return acts

    def replay(self, actions) -> dict:
        """From the frozen scene, open-loop. Actions after the goal is reached or past the episode's last step do not run."""
        acts = self.check_trajectory(actions)
        rec, self._rec = self._rec, None
        try:
            self.reset()
            success_step = None
            for a in acts[: self.max_steps]:
                _, success, _ = self.step(a)
                if success:
                    success_step = self.t
                    break
        finally:
            self._rec = rec
        return {"success": success_step is not None, "success_step": success_step, "steps": self.t,
                "n_actions": int(len(acts)), "state_sha": self.state_sha()}

    def save_trajectory(self, actions, path: str | Path, meta: dict | None = None) -> None:
        acts = self.check_trajectory(actions)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        np.savez(path, actions=acts, env_id=self.env_id, seed=self.seed, meta=json.dumps(meta or {}))

    def load_trajectory(self, path: str | Path) -> np.ndarray:
        d = np.load(path, allow_pickle=False)
        if str(d["env_id"]) != self.env_id or int(d["seed"]) != self.seed:
            raise ValueError(f"{path} was recorded for {d['env_id']} seed {d['seed']}, not this instance")
        return d["actions"]

    def render_video(self, actions, path: str | Path, camera: str | None = None, every: int | None = None,
                     fps: int = 10) -> dict:
        """Replays and films it from one camera, `s.view` by default, every `every`-th step: by default 2 (at 10 Hz
        control and fps=10, 2x speed), more on a long episode, for at most ~500 frames."""
        import imageio.v2 as imageio
        acts, camera = self.check_trajectory(actions), camera or self.view
        every = every or max(2, -(-min(len(acts), self.max_steps) // 500))
        rec, self._rec = self._rec, None   # a replay, not the agent's own steps: never recorded, as in replay()
        try:
            self.reset()
            frames = [self.images([camera])[camera]]
            success = False
            for a in acts[: self.max_steps]:
                _, success, _ = self.step(a)
                if self.t % every == 0 or success:
                    frames.append(self.images([camera])[camera])
                if success:
                    break
        finally:
            self._rec = rec
        h, w = (n // 2 * 2 for n in frames[0].shape[:2])    # H.264 wants even sides
        imageio.mimwrite(path, [f[:h, :w] for f in frames], fps=fps, macro_block_size=1)
        imageio.imwrite(str(Path(path).with_suffix(".last.png")), frames[-1])
        return {"frames": len(frames), "success": success, "every": every}


# ---------------------------------------------------------------------- CLI
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("replay", "render"):
        q = sub.add_parser(name)
        q.add_argument("--instance", default="/app/instance.json")
        q.add_argument("--traj", required=True)
    sub.choices["render"].add_argument("--out", required=True)
    sub.choices["render"].add_argument("--camera")
    a = ap.parse_args()
    s = Session(a.instance)
    acts = s.load_trajectory(a.traj)
    out = s.replay(acts) if a.cmd == "replay" else s.render_video(acts, a.out, camera=a.camera)
    print(("" if s.mujoco else "\n") + json.dumps(out))   # PyBullet prints "base_root", no newline, on loading
    return 0


if __name__ == "__main__":
    sys.exit(main())
