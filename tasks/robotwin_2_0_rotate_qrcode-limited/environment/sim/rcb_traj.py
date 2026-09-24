"""
rcb_traj.py — task-local tooling: frozen-instance / record / deterministic-replay utilities for RoboTwin 2.0
(SAPIEN 3 / PhysX, dual-arm ALOHA-AgileX, CuRobo planning).

Concepts
--------
instance   : a RoboTwin scene rebuilt from (task, seed, embodiment, config) — RoboTwin seeds numpy before
             `load_actors`, then settles the scene for 2500 physics steps, so the same seed gives the same
             initial state. `instance.json` records that recipe plus the expected initial-state hash; every
             `reset()` rebuilds the scene and checks the hash.
trajectory : the per-physics-step control record (T, 34) = for the 16 active joints of the articulation
             [drive position targets (16) | drive velocity targets (16) | left, right gripper command (2)].
             Every `scene.step()` that RoboTwin's primitives take goes through a hook that (a) applies gravity
             compensation, (b) records this row. Replaying the rows open-loop from the same instance must
             reproduce the outcome (PhysX CPU is deterministic on the same build).

CLI
---
  python rcb_traj.py make-instance --task stack_blocks_two --seed 0 --out inst.json
  python rcb_traj.py run-oracle    --task stack_blocks_two --instance inst.json --code solution/oracle.py --out traj.npz
  python rcb_traj.py replay        --task stack_blocks_two --instance inst.json --traj traj.npz [--repeat 2]
  python rcb_traj.py selftest      --task stack_blocks_two --seed 0 --code oracle.py   # make-instance + oracle + replay
  python rcb_traj.py render        --task stack_blocks_two --instance inst.json --traj traj.npz --out replay.mp4 [--cameras head_camera,front_camera]

Python (what the agent gets)
----------------------------
  from rcb_traj import Session
  s = Session("stack_blocks_two", instance="/app/instance.json")
  s.reset()                                     # rebuild the frozen instance (unlimited)
  env = s.env                                   # the RoboTwin task env: env.block1, env.grasp_actor(...), env.move(...)
  s.record_start(); ...; actions = s.record_stop()
  s.replay(actions) -> dict(success=bool, sim_steps=int, state_sha=str)
  s.save_trajectory(actions, "traj.npz")
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np

ROBOTWIN_ROOT = os.environ.get("ROBOTWIN_ROOT", "/opt/RoboTwin")
# Interaction log: every Session (any process) appends one line per session start/reset/record/replay/exit, with the
# physics steps consumed, to RCB_SESSION_LOG (default /app/output/rcb_session_log.jsonl, collected with the artifacts).
# It records the agent's whole debugging history, not just the trajectory it hands in (the verifier reports it as
# cost: agent_sessions / agent_resets / agent_sim_steps). Set RCB_SESSION_LOG="" to disable (the verifier does).
SESSION_LOG = os.environ.get("RCB_SESSION_LOG", "/app/output/rcb_session_log.jsonl")


def _slog(ev: str, **kw) -> None:
    if not SESSION_LOG:
        return
    try:
        os.makedirs(os.path.dirname(SESSION_LOG), exist_ok=True)
        with open(SESSION_LOG, "a") as f:
            f.write(json.dumps({"ts": time.time(), "pid": os.getpid(), "ev": ev, **kw}) + "\n")
    except OSError:
        pass

# --------------------------------------------------------------------------- task family registry
# Any RoboTwin task name (envs/<name>.py) is accepted; entries here only add the human-readable goal text.
TASKS: dict[str, dict] = {
    "stack_blocks_two": dict(
        text="Stack the green block on top of the red block (either arm may be used), then open both grippers.",
    ),
    'rotate_qrcode': dict(text='Use arm to catch the qrcode board on the table, pick it up and rotate to let the qrcode face towards the robot.'),
}
DEFAULT_EMBODIMENT = "aloha-agilex"

# RoboTwin task config (env_cfg/task_config/demo_clean.yml without data collection / domain randomisation).
BASE_ARGS: dict[str, Any] = {
    "render_freq": 0,
    "episode_num": 1,
    "use_seed": True,
    "save_freq": None,          # never take pictures inside primitives (no data collection)
    "language_num": 1,
    "eval_instruction": "seen",
    "domain_randomization": {
        "random_background": False, "cluttered_table": False, "clean_background_rate": 1,
        "random_head_camera_dis": 0, "random_table_height": 0, "random_light": False, "crazy_random_light_rate": 0,
    },
    "camera": {"head_camera_type": "D435", "wrist_camera_type": "D435",
               "collect_head_camera": True, "collect_wrist_camera": True},
    "data_type": {"rgb": True, "third_view": False, "depth": False, "pointcloud": False, "observer": False,
                  "endpose": True, "qpos": True, "mesh_segmentation": False, "actor_segmentation": False},
    "pcd_down_sample_num": 1024, "pcd_crop": True, "save_path": "/tmp/rcb_robotwin_data",
    "clear_cache_freq": 5, "collect_data": False, "eval_video_log": False,
    "save_data": False, "need_plan": True, "eval_mode": False, "dual_arm": True,
}


def _chdir_root() -> None:
    # RoboTwin resolves assets/config paths relative to the repo root and via ROOT_PATH
    if os.getcwd() != ROBOTWIN_ROOT and os.path.isdir(ROBOTWIN_ROOT):
        os.chdir(ROBOTWIN_ROOT)


def _build_args(task: str, embodiment: str, seed: int) -> dict[str, Any]:
    import yaml
    from envs._GLOBAL_CONFIGS import CONFIGS_PATH
    args = json.loads(json.dumps(BASE_ARGS))
    args["task_name"] = task
    args["task_config"] = "rcb"
    args["embodiment"] = [embodiment]
    with open(os.path.join(CONFIGS_PATH, "_embodiment_config.yml")) as f:
        emb = yaml.safe_load(f)
    robot_file = emb[embodiment]["file_path"]
    with open(os.path.join(robot_file, "config.yml")) as f:
        emb_cfg = yaml.safe_load(f)
    args.update(left_robot_file=robot_file, right_robot_file=robot_file, dual_arm_embodied=True,
                left_embodiment_config=emb_cfg, right_embodiment_config=emb_cfg, embodiment_name=embodiment,
                seed=int(seed), now_ep_num=0)
    return args


class _SceneProxy:
    """Wraps env.scene so every physics step taken by RoboTwin's primitives passes through Session._on_step."""

    def __init__(self, scene, on_step: Callable[[], None]):
        object.__setattr__(self, "_scene", scene)
        object.__setattr__(self, "_on_step", on_step)

    def step(self):
        self._on_step()
        self._scene.step()

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_scene"), name)

    def __setattr__(self, name, value):
        setattr(object.__getattribute__(self, "_scene"), name, value)


# --------------------------------------------------------------------------- session
class Session:
    def __init__(self, task: str, instance: str | Path | None = None, seed: int = 0,
                 embodiment: str | None = None, enable_render: bool = False, render_shader: str = "default"):
        if not os.path.isfile(os.path.join(ROBOTWIN_ROOT, "envs", f"{task}.py")):
            raise KeyError(f"unknown RoboTwin task {task!r} (no envs/{task}.py)")
        self.task = task
        self.spec = TASKS.get(task, {"text": f"RoboTwin 2.0 task {task}"})
        self.embodiment = embodiment or DEFAULT_EMBODIMENT
        self.seed = int(seed)
        self.expected_sha: str | None = None
        self.enable_render = enable_render
        self.render_shader = render_shader
        _chdir_root()
        sys.path.insert(0, ROBOTWIN_ROOT)
        import importlib
        envs_module = importlib.import_module(f"envs.{task}")
        self.env = getattr(envs_module, task)()      # RoboTwin Base_Task subclass (not yet set up)
        self._recording: list[np.ndarray] | None = None
        self._sim_steps = 0
        self._resets = 0
        self._joints = None
        self._total_steps = 0
        _slog("session_start", task=task, seed=self.seed, render=enable_render)
        import atexit
        atexit.register(lambda: _slog("session_end", task=task, resets=self._resets, sim_steps=self._total_steps + self._sim_steps))
        if instance is not None:
            self.load_instance(instance)
        else:
            self.reset()

    # ---- instance handling
    def load_instance(self, path: str | Path) -> None:
        d = json.load(open(path))
        if d["task"] != self.task:
            raise ValueError(f"instance task {d['task']} != session task {self.task}")
        self.seed = int(d["seed"]); self.embodiment = d.get("embodiment", self.embodiment)
        self.expected_sha = d.get("state_sha")
        self.reset()

    def save_instance(self, path: str | Path) -> None:
        json.dump({"task": self.task, "seed": self.seed, "embodiment": self.embodiment, "state_sha": self.state_sha(),
                   "text": self.spec["text"], "n_active_joints": len(self._joints)}, open(path, "w"), indent=1)

    def reset(self) -> None:
        """Rebuild the frozen instance: RoboTwin re-seeds numpy, re-creates the scene, places the objects and
        settles them. Then the physics-step hook is (re)installed. Verifies the initial-state hash if known."""
        import sapien
        self._recording = None
        if self.enable_render:
            sapien.render.set_camera_shader_dir(self.render_shader)
        args = _build_args(self.task, self.embodiment, self.seed)
        self.env.setup_demo(**args)
        if self.enable_render:  # setup_scene() switches the shader to ray tracing; put it back for cheap frames
            sapien.render.set_camera_shader_dir(self.render_shader)
        self._raw_scene = self.env.scene
        self.env.scene = _SceneProxy(self._raw_scene, self._on_step)
        r = self.env.robot  # the driven joints only (arms + gripper fingers); wheels/casters are never commanded
        self._joints = list(r.left_arm_joints) + [g[0] for g in r.left_gripper] + \
            list(r.right_arm_joints) + [g[0] for g in r.right_gripper]
        self._entities = [r.left_entity] + ([r.right_entity] if r.right_entity is not r.left_entity else [])
        self._total_steps += self._sim_steps
        _slog("reset", task=self.task, n=self._resets + 1, sim_steps_before=self._sim_steps)
        self._sim_steps = 0
        self._resets += 1
        sha = self.state_sha()
        if self.expected_sha is not None and sha != self.expected_sha:
            raise RuntimeError(f"instance state hash {sha} != expected {self.expected_sha}: non-deterministic rebuild")

    # ---- physics-step hook
    def _on_step(self) -> None:
        for e in self._entities:  # gravity/coriolis compensation, as RoboTwin does before every joint command
            e.set_qf(e.compute_passive_force(gravity=True, coriolis_and_centrifugal=True))
        if self._recording is not None:
            self._recording.append(self._current_row())
        self._sim_steps += 1

    def _current_row(self) -> np.ndarray:
        pos = [float(np.asarray(j.get_drive_target()).reshape(-1)[0]) for j in self._joints]
        vel = [float(np.asarray(j.get_drive_velocity_target()).reshape(-1)[0]) for j in self._joints]
        return np.array(pos + vel + [self.env.robot.left_gripper_val, self.env.robot.right_gripper_val], dtype=np.float64)

    def _apply_row(self, row: np.ndarray) -> None:
        n = len(self._joints)
        for j, p, v in zip(self._joints, row[:n], row[n:2 * n]):
            j.set_drive_target(float(p)); j.set_drive_velocity_target(float(v))
        self.env.robot.left_gripper_val = float(row[2 * n]); self.env.robot.right_gripper_val = float(row[2 * n + 1])

    @property
    def action_dim(self) -> int:
        return 2 * len(self._joints) + 2

    @property
    def action_layout(self) -> str:
        n = len(self._joints)
        names = [j.get_name() for j in self._joints]
        return (f"one row per physics step (1/250 s): {n} joint drive position targets (rad/m) {names}, "
                f"then {n} drive velocity targets, then the left and right gripper commands (0 = closed, 1 = open)")

    def step(self, row: np.ndarray | None = None) -> None:
        """Advance one physics step; `row` (action_dim,) sets the drive targets first. Records if recording."""
        if row is not None:
            self._apply_row(np.asarray(row, dtype=np.float64))
        self.env.scene.step()

    # ---- state hashing
    def _state_vector(self) -> np.ndarray:
        parts = []
        for a in self._raw_scene.get_all_actors():
            p = a.get_pose(); parts += [p.p, p.q]
        for art in self._raw_scene.get_all_articulations():
            parts += [art.get_qpos(), art.get_qvel()]
        return np.concatenate([np.asarray(x, dtype=np.float64).reshape(-1) for x in parts])

    def state_sha(self) -> str:
        return hashlib.sha1(np.ascontiguousarray(self._state_vector()).tobytes()).hexdigest()[:12]

    # ---- code execution (oracle)
    def exec_code(self, code: str) -> dict[str, Any]:
        """Run code with `env` (the RoboTwin task env), `s` (this Session), `np`, `ArmTag`, `Actor` in scope."""
        from envs.utils import ArmTag, Actor
        g: dict[str, Any] = {"__name__": "__main__", "np": np, "env": self.env, "s": self, "ArmTag": ArmTag, "Actor": Actor}
        try:
            exec(code, g, g)
            return {"ok": True}
        except BaseException as exc:  # noqa: BLE001
            return {"ok": False, "error": repr(exc)}

    # ---- recording
    def record_start(self) -> None:
        self._recording = []

    def record_stop(self) -> np.ndarray:
        acts = np.array(self._recording or [], dtype=np.float64).reshape(-1, self.action_dim)
        self._recording = None
        _slog("record", task=self.task, n_actions=int(len(acts)), success=bool(self.env.check_success()))
        return acts

    def save_trajectory(self, actions: np.ndarray, path: str | Path, meta: dict | None = None) -> None:
        np.savez(path, actions=np.asarray(actions, dtype=np.float64), task=self.task, seed=self.seed,
                 instance_sha=self.expected_sha or "", action_layout=self.action_layout, meta=json.dumps(meta or {}))

    # ---- status / replay
    def status(self) -> dict[str, Any]:
        return {"success": bool(self.env.check_success()), "sim_steps": int(self._sim_steps),
                "resets": int(self._resets), "state_sha": self.state_sha()}

    def replay(self, actions: np.ndarray) -> dict[str, Any]:
        self.reset()
        acts = np.asarray(actions, dtype=np.float64)
        if acts.ndim != 2 or acts.shape[1] != self.action_dim:
            raise ValueError(f"actions must be (T, {self.action_dim}), got {acts.shape}")
        for row in acts:
            self.step(row)
        st = self.status(); _slog("replay", task=self.task, n_actions=int(len(acts)), success=st["success"]); return st

    # Cameras: RoboTwin's head_camera / front_camera / left_camera / right_camera (wrist) plus the free third-person
    # observer_camera (front, wide) and world_camera1 (diagonal from above) that RoboTwin adds to every scene.
    VIDEO_CAMERAS: tuple[str, ...] = ("world_camera1", "observer_camera", "head_camera", "front_camera", "left_camera", "right_camera")

    def render_frame(self, camera: str = "head_camera", size: tuple[int, int] | None = None) -> np.ndarray:
        """RGB (H, W, 3) uint8 from one camera; `size=(w, h)` resizes. See VIDEO_CAMERAS for the names."""
        cams = self.env.cameras
        self.env._update_render()
        if hasattr(cams, camera):  # free cameras: observer_camera, world_camera1, ...
            cam = getattr(cams, camera); cam.take_picture()
            img = (np.asarray(cam.get_picture("Color"))[..., :3] * 255).clip(0, 255).astype(np.uint8)
        else:
            cams.update_picture(); img = np.asarray(cams.get_rgb()[camera]["rgb"])[..., :3]
        if size is not None and (img.shape[1], img.shape[0]) != tuple(size):
            from PIL import Image
            img = np.asarray(Image.fromarray(np.ascontiguousarray(img)).resize(size, Image.BILINEAR))
        return img

    def render_grid(self, cameras: tuple[str, ...] = VIDEO_CAMERAS, cols: int = 3, size: tuple[int, int] = (320, 240)) -> np.ndarray:
        """One image tiling `cameras` (row-major, `cols` per row; each resized to `size`)."""
        tiles = [self.render_frame(c, size=size) for c in cameras]
        while len(tiles) % cols:
            tiles.append(np.zeros_like(tiles[0]))
        rows = [np.concatenate(tiles[i:i + cols], axis=1) for i in range(0, len(tiles), cols)]
        return np.concatenate(rows, axis=0)

    def render_video(self, actions: np.ndarray, path: str | Path, *, every: int = 10, fps: int = 25,
                     cameras: tuple[str, ...] = VIDEO_CAMERAS, cols: int = 3, size: tuple[int, int] = (320, 240)) -> dict[str, Any]:
        """Replay `actions` from the frozen instance and write a human-viewable MP4 (needs enable_render=True):
        a grid of `cameras` (default: world, observer, head / front, left wrist, right wrist), one frame every `every` steps."""
        import imageio.v2 as imageio
        if not self.enable_render:
            raise RuntimeError("render_video needs Session(..., enable_render=True)")
        self.reset()
        grab = lambda: self.render_grid(cameras, cols=cols, size=size)
        frames = [grab()]
        for i, row in enumerate(np.asarray(actions, dtype=np.float64)):
            self.step(row)
            if (i + 1) % every == 0:
                frames.append(grab())
        frames.append(grab())
        path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
        with imageio.get_writer(str(path), fps=fps, format="FFMPEG", codec="libx264", macro_block_size=1) as w:
            for f in frames:
                w.append_data(np.ascontiguousarray(f[..., :3]))
        imageio.imwrite(str(path.with_suffix(".last.png")), np.ascontiguousarray(frames[-1][..., :3]))
        return {**self.status(), "n_frames": len(frames), "video": str(path)}

    def close(self) -> None:
        try:
            self.env.close_env(clear_cache=True)
        except Exception:  # noqa: BLE001
            pass


# --------------------------------------------------------------------------- CLI
def _load_traj(path: str) -> np.ndarray:
    return np.load(path, allow_pickle=False)["actions"]


def cmd_make_instance(a):
    s = Session(a.task, seed=a.seed)
    sha0 = s.state_sha(); s.reset()
    assert s.state_sha() == sha0, "scene rebuild is not deterministic for this seed"
    s.save_instance(a.out)
    print(json.dumps({"instance": a.out, "sha": sha0, **s.status()}))


def cmd_run_oracle(a):
    """Run the reference code and record it. CuRobo planning is not deterministic run-to-run, so the expert can
    fail a plan on some attempts; like an agent, the oracle may reset and retry (up to --retries) and keeps the
    first attempt that completes the task. Replay of the recorded attempt is deterministic regardless."""
    s = Session(a.task, instance=a.instance)
    code = open(a.code).read(); t0 = time.time(); attempts = []
    for i in range(max(1, a.retries)):
        if i:
            s.reset()
        s.record_start(); r = s.exec_code(code); acts = s.record_stop(); st = s.status()
        attempts.append({"exec": r, "success": st["success"], "n_actions": int(len(acts))})
        if st["success"]:
            break
    s.save_trajectory(acts, a.out, meta={"source": "oracle", "attempts": attempts, "wall_s": time.time() - t0})
    print(json.dumps({"traj": a.out, "n_actions": int(len(acts)), "attempts": len(attempts), "exec": r, **st}))


def cmd_replay(a):
    s = Session(a.task, instance=a.instance)
    acts = _load_traj(a.traj)
    outs = [s.replay(acts) for _ in range(a.repeat)]
    print(json.dumps({"n_actions": int(len(acts)), "replays": outs, "all_success": all(o["success"] for o in outs),
                      "deterministic": len({o["state_sha"] for o in outs}) == 1}))


def cmd_render(a):
    s = Session(a.task, instance=a.instance, enable_render=True)
    cams = tuple(a.cameras.split(",")) if a.cameras else Session.VIDEO_CAMERAS
    print(json.dumps(s.render_video(_load_traj(a.traj), a.out, every=a.every, fps=a.fps, cameras=cams, cols=a.cols)))


def cmd_selftest(a):
    s = Session(a.task, seed=a.seed)
    sha0 = s.state_sha(); s.reset(); assert s.state_sha() == sha0, "reset() does not restore instance state"
    s.record_start(); t0 = time.time(); r = s.exec_code(open(a.code).read()); acts = s.record_stop()
    live = s.status()
    rep = [s.replay(acts) for _ in range(a.repeat)]
    ok = live["success"] and all(x["success"] for x in rep) and len({x["state_sha"] for x in rep}) == 1 \
        and rep[0]["state_sha"] == live["state_sha"]
    print(json.dumps({"oracle_exec": r, "oracle_wall_s": time.time() - t0, "live": live, "replays": rep,
                      "n_actions": int(len(acts)), "action_dim": s.action_dim, "PASS": ok}, indent=1))
    if a.out:
        s.save_trajectory(acts, a.out, meta={"source": "selftest"})
    sys.exit(0 if ok else 1)


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("make-instance"); q.add_argument("--task", required=True); q.add_argument("--out", required=True); q.add_argument("--seed", type=int, default=0); q.set_defaults(fn=cmd_make_instance)
    q = sub.add_parser("run-oracle"); q.add_argument("--task", required=True); q.add_argument("--instance", required=True); q.add_argument("--code", required=True); q.add_argument("--out", required=True); q.add_argument("--retries", type=int, default=5); q.set_defaults(fn=cmd_run_oracle)
    q = sub.add_parser("replay"); q.add_argument("--task", required=True); q.add_argument("--instance", required=True); q.add_argument("--traj", required=True); q.add_argument("--repeat", type=int, default=2); q.set_defaults(fn=cmd_replay)
    q = sub.add_parser("render"); q.add_argument("--task", required=True); q.add_argument("--instance", required=True); q.add_argument("--traj", required=True); q.add_argument("--out", required=True); q.add_argument("--every", type=int, default=10); q.add_argument("--fps", type=int, default=25); q.add_argument("--cameras", default="", help="comma list; default = all six views"); q.add_argument("--cols", type=int, default=3); q.set_defaults(fn=cmd_render)
    q = sub.add_parser("selftest"); q.add_argument("--task", default='rotate_qrcode'); q.add_argument("--code", required=True); q.add_argument("--seed", type=int, default=0); q.add_argument("--repeat", type=int, default=2); q.add_argument("--out"); q.set_defaults(fn=cmd_selftest)
    a = p.parse_args(); a.fn(a)


if __name__ == "__main__":
    main()
