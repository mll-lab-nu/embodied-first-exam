"""Public nominal CPU training simulator. No deployment assets or parameter draws."""

import json
from pathlib import Path

import numpy as np

try:
    from .control_public.fly import Controller, Vehicle, DT, DURATION, target, validate
    from .neuralfly_video import Video
except ImportError:  # Task-local exported modules, outside the repository package.
    from control_public.fly import Controller, Vehicle, DT, DURATION, target, validate
    from neuralfly_video import Video


def rollout(
    policy, *, phase=0.0, center=(0.0, 0.0, 1.8), initial_offset=(0.0, 0.0, 0.0), noise_seed=0, out=None, render=False
):
    """User-selected training scenarios, fixed nominal mass and actuator response."""
    policy = validate(policy)
    controller = Controller(policy)
    vehicle = Vehicle(target(0, phase, 0, center)[0] + initial_offset)
    rng = np.random.default_rng(noise_seed)
    telemetry, errors = [], []
    folder = Path(out) if out is not None else None
    if folder:
        folder.mkdir(parents=True, exist_ok=False)
    if render and folder is None:
        raise ValueError("A video output directory is required")
    video = Video(vehicle.model, folder / "video.mp4", center) if render else None
    try:
        for k in range(round(DURATION / DT)):
            t = k * DT
            obs = vehicle.observation(t, target(t, phase, 0, center), rng)
            contact = vehicle.step(controller.action(obs), obs, policy)
            errors.append(float(np.linalg.norm(vehicle.data.qpos[:3] - target(t + DT, phase, 0, center)[0])))
            if k % 5 == 0:
                telemetry.append(obs)
                vehicle.model.site_pos[0] = target(t + DT, phase, 0, center)[0]
                vehicle.mj.mj_forward(vehicle.model, vehicle.data)
                if video:
                    video.frame(vehicle.data)
            if contact or np.linalg.norm(vehicle.data.qpos[:3] - center) > 5:
                break
    finally:
        if video:
            video.close()
    result = {"telemetry": telemetry, "tracking_rmse_m": float(np.sqrt(np.mean(np.square(errors))))}
    if folder:
        (folder / "training.json").write_text(json.dumps(result, allow_nan=False) + "\n")
    return result
