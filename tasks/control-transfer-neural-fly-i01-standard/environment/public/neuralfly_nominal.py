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
    policy,
    *,
    phase=0.0,
    center=(0.0, 0.0, 1.8),
    initial_offset=(0.0, 0.0, 0.0),
    noise_seed=0,
    out=None,
    render=False,
    yaw=0.0,
    tilt=0.0,
    amplitude_x=1.25,
    amplitude_z=0.75,
    rate=1.0,
    direction=1,
):
    """User-selected training scenarios, fixed nominal mass and actuator response."""
    policy = validate(policy)
    if not 0.8 <= rate <= 1.1 or direction not in (-1, 1):
        raise ValueError("Trajectory rate/direction")
    command = dict(
        phase=phase,
        yaw=yaw,
        center=center,
        tilt=tilt,
        amplitude_x=amplitude_x,
        amplitude_z=amplitude_z,
        rate=rate,
        direction=direction,
    )
    controller = Controller(policy)
    vehicle = Vehicle(target(0, **command)[0] + initial_offset)
    rng = np.random.default_rng(noise_seed)
    telemetry, errors = [], []
    folder = Path(out) if out is not None else None
    if folder:
        folder.mkdir(parents=True, exist_ok=False)
    if render and folder is None:
        raise ValueError("A video output directory is required")
    curve = [target(t, **command)[0] for t in np.linspace(0, 2 * np.pi / rate, 100, endpoint=False)]
    video = Video(vehicle.model, folder / "video.mp4", center, curve=curve) if render else None
    try:
        for k in range(round(DURATION / (rate * DT))):
            t = k * DT
            obs = vehicle.observation(t, target(t, **command), rng)
            contact = vehicle.step(controller.action(obs), obs, policy)
            errors.append(float(np.linalg.norm(vehicle.data.qpos[:3] - target(t + DT, **command)[0])))
            if k % 5 == 0:
                telemetry.append(obs)
                vehicle.model.site_pos[0] = target(t + DT, **command)[0]
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
