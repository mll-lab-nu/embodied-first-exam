"""Bounded base-velocity trajectories in the native RoboCasa NavigateKitchen environment."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import random

os.environ.setdefault("MUJOCO_GL", "osmesa")
os.environ.setdefault("PYOPENGL_PLATFORM", "osmesa")
import numpy as np

MAX_ACTIONS = 1200
HERE = Path(__file__).resolve().parent


def make_env(render=False):
    import robosuite
    import robocasa
    from robosuite.controllers import load_composite_controller_config
    random.seed(0)
    np.random.seed(0)
    env = robosuite.make("NavigateKitchen", robots="PandaOmron",
        controller_configs=load_composite_controller_config(robot="PandaOmron"),
        has_renderer=False, has_offscreen_renderer=render, use_camera_obs=False,
        initialization_noise=None, seed=0, layout_ids=[0], style_ids=[0],
        randomize_cameras=False, generative_textures=None, hard_reset=False,
        control_freq=20, ignore_done=True, translucent_robot=False)
    env.reset()
    return env


def snapshot(env):
    data = env.sim.data
    return dict(qpos=data.qpos.copy(), qvel=data.qvel.copy(),
        qacc_warmstart=data.qacc_warmstart.copy(), ctrl=data.ctrl.copy(),
        act=data.act.copy(), time=np.array(data.time))


def state_sha(env):
    return hashlib.sha256(b"".join(v.tobytes() for v in snapshot(env).values())).hexdigest()


def freeze(path):
    env = make_env()
    np.savez_compressed(path, **snapshot(env), target_pos=env.target_pos,
        target_ori=env.target_ori, source=np.array(env.src_fixture.name),
        target=np.array(env.target_fixture.name),
        model_sha=np.array(hashlib.sha256(env.sim.model.get_xml().encode()).hexdigest()))
    print(json.dumps(dict(initial_success=int(env._check_success()), source=env.src_fixture.name,
        target=env.target_fixture.name, state_sha=state_sha(env))))
    env.close()


def load_actions(path):
    import io
    import zipfile
    if Path(path).stat().st_size > 1024 * 1024:
        raise ValueError("archive too large")
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) != 1 or members[0].filename != "actions.npy" or members[0].file_size > 1024 * 1024:
            raise ValueError("expected one bounded actions array")
        payload = io.BytesIO(archive.read(members[0]))
    version = np.lib.format.read_magic(payload)
    if version == (1, 0):
        shape, fortran, dtype = np.lib.format.read_array_header_1_0(payload)
    elif version == (2, 0):
        shape, fortran, dtype = np.lib.format.read_array_header_2_0(payload)
    else:
        raise ValueError("unsupported NPY version")
    if dtype.kind not in "fi" or len(shape) != 2 or shape[1] != 3 or not 1 <= shape[0] <= MAX_ACTIONS:
        raise ValueError("actions must be numeric (T, 3)")
    body = payload.read()
    if len(body) != shape[0] * shape[1] * dtype.itemsize:
        raise ValueError("invalid NPY payload length")
    actions = np.frombuffer(body, dtype=dtype).reshape(shape, order="F" if fortran else "C")
    if not 1 <= len(actions) <= MAX_ACTIONS or not np.isfinite(actions).all():
        raise ValueError("invalid trajectory length or nonfinite action")
    if np.any(actions < -1) or np.any(actions > 1):
        raise ValueError("actions must be within [-1, 1]")
    return actions.astype(np.float64)


class Session:
    def __init__(self, instance=HERE / "instance.npz", render=False):
        self.instance = Path(instance)
        self.env = make_env(render)
        self.actions = []
        self.resets = 0
        self.reset()

    def reset(self):
        env = self.env
        env.reset()
        with np.load(self.instance, allow_pickle=False) as z:
            if hashlib.sha256(env.sim.model.get_xml().encode()).hexdigest() != str(z["model_sha"]):
                raise ValueError("scene model differs from frozen instance")
            if env.target_fixture.name != str(z["target"]) or env.src_fixture.name != str(z["source"]):
                raise ValueError("fixture identity differs")
            for key in ("qpos", "qvel", "qacc_warmstart", "ctrl", "act"):
                getattr(env.sim.data, key)[:] = z[key]
            env.sim.data.time = float(z["time"])
            env.target_pos = z["target_pos"].copy()
            env.target_ori = z["target_ori"].copy()
        env.sim.forward()
        for controller in env.robots[0].part_controllers.values():
            controller.update(force=True)
            controller.reset_goal()
        env._update_observables(force=True)
        self.actions = []
        self.resets += 1
        return self.observe()

    def observe(self):
        env = self.env
        pos = env.sim.data.get_body_xpos("mobilebase0_base").copy()
        mat = env.sim.data.get_body_xmat("mobilebase0_base").copy()
        yaw = float(np.arctan2(mat[1, 0], mat[0, 0]))
        return dict(base_pos=pos, base_yaw=yaw, target_pos=env.target_pos.copy(),
            target_yaw=float(env.target_ori[2]), target_fixture=env.target_fixture.name,
            success=bool(env._check_success()), sim_steps=len(self.actions), resets=self.resets)

    def step(self, action):
        action = np.asarray(action, dtype=np.float64)
        if action.shape != (3,) or not np.isfinite(action).all() or np.abs(action).max() > 1:
            raise ValueError("expected three finite controls in [-1, 1]")
        if len(self.actions) >= MAX_ACTIONS:
            raise ValueError("trajectory budget exhausted")
        full = np.zeros(self.env.action_dim)
        start, end = self.env.robots[0]._action_split_indexes["base"]
        full[start:end] = action
        # The final mode selector enables mobile-base control in the native hybrid controller.
        full[-1] = 1
        self.env.step(full)
        self.actions.append(action.copy())
        return self.observe()

    def save(self, path="/app/output/trajectory.npz"):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, actions=np.asarray(self.actions))
        load_actions(path)

    def frame(self):
        return self.env.sim.render(height=480, width=640, camera_name="robot0_agentview_center")[::-1]

    def close(self):
        self.env.close()


def replay(instance, trajectory, video=None):
    actions = load_actions(trajectory)
    s = Session(instance, render=video is not None)
    writer = None
    if video:
        import imageio.v2 as imageio
        writer = imageio.get_writer(video, fps=20, codec="libx264", quality=8)
        writer.append_data(s.frame())
    try:
        for action in actions:
            s.step(action)
            if writer:
                writer.append_data(s.frame())
        obs = s.observe()
        result = dict(success=int(obs["success"]), state_sha=state_sha(s.env),
            n_actions=len(actions), sim_steps=len(actions),
            position_error=float(np.linalg.norm(obs["target_pos"][:2] - obs["base_pos"][:2])),
            orientation_cos=float(np.cos(obs["target_yaw"] - obs["base_yaw"])),
            final_reward=float(s.env.reward()))
    finally:
        if writer:
            writer.close()
        s.close()
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["freeze", "replay"])
    p.add_argument("--instance", default=str(HERE / "instance.npz"))
    p.add_argument("--traj", default="/app/output/trajectory.npz")
    p.add_argument("--result")
    p.add_argument("--video")
    args = p.parse_args()
    if args.command == "freeze":
        freeze(args.instance)
    else:
        result = replay(args.instance, args.traj, args.video)
        if args.result:
            Path(args.result).write_text(json.dumps(result) + "\n")
        print(json.dumps(result))


if __name__ == "__main__":
    main()
