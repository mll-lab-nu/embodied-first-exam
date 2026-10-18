"""Private CPU deployment model with flight-log-fitted aerodynamic forces."""

import hashlib
import json
from pathlib import Path

import mujoco
import numpy as np

from ..control_public.fly import Controller, DT, DURATION, Vehicle, target, validate
from ..neuralfly_video import Video

REVISION = "neuralfly-cpu/3"
ASSET_SHA256 = "8e1c148ed034b9f4c541dfaa71b70b48a652f43c7abcc381416040d7901459b9"   # = gen_tasks.py FLY_ASSET_SHA256 (image 0.2.0)


def features(v, q, wind):
    q = np.asarray(q, dtype=float)
    q = q / np.linalg.norm(q)
    q = q if q[0] >= 0 else -q
    x = np.r_[v, q[1:], wind / 6.1]
    return np.r_[1, x, x * x, x[:3] * x[-1]]


def wind_vector(t, stratum, params):
    """World-frame air velocity (m/s), pointing toward airflow travel direction.

    Synthetic isotropic extension; not a directional fit to flight experiments.
    Existing wind_phase supplies deterministic plant heading without new RNG draws.
    """
    speed = [0.0, 4.2, 8.5, 12.1, 8.5][stratum]
    if stratum == 4:
        speed += 2.4 * np.sin(t + params["wind_phase"])
    yaw = params["wind_phase"]
    return speed * np.array([np.cos(yaw), np.sin(yaw), 0.0])


def wind_drag_increment(velocity, wind, coefficient=0.045):
    """Quadratic air-relative drag minus calm-air drag already in the surrogate.

    coefficient is an assumed 0.045 kg/m, not identified from paper data.
    Adding this to the zero-wind fitted residual avoids double-counting calm drag.
    """
    velocity, wind = np.asarray(velocity), np.asarray(wind)
    relative = wind - velocity
    return coefficient * (np.linalg.norm(relative) * relative + np.linalg.norm(velocity) * velocity)


def parameters(seed):
    if type(seed) is not int or not 0 <= seed < 2**63:
        raise ValueError("Plant seed")
    rng = np.random.default_rng(seed)
    return {
        "wind_phase": float(rng.uniform(-np.pi, np.pi)),
        "motor_tau": float(rng.uniform(0.02, 0.06)),
        "mass_scale": float(rng.uniform(0.97, 1.03)),
    }


def episode_trajectory(seed):
    """Private command draw, independent of plant. Seeds are never public feedback.

    Five-separated held-out seeds give opposite traversal directions per wind stratum.
    Three plane classes and both directions occur in each ten-case held-out bank.
    """
    rng = np.random.default_rng(seed)
    plane = ("vertical", "horizontal", "inclined")[seed % 3]
    tilt = {"vertical": 0.0, "horizontal": np.pi / 2, "inclined": float(rng.uniform(np.pi / 12, 5 * np.pi / 12))}[plane]
    command = dict(
        phase=float(rng.uniform(-np.pi, np.pi)),
        yaw=float(rng.uniform(-np.pi, np.pi)),
        center=[*rng.uniform(-0.4, 0.4, 2), float(rng.uniform(1.8, 2.2))],
        tilt=tilt,
        amplitude_x=float(rng.uniform(0.9, 1.5)),
        amplitude_z=float(rng.uniform(0.45, 0.85)),
        rate=float(rng.uniform(0.8, 1.1)),
        direction=1 if seed % 2 == 0 else -1,
    )
    return plane, command


def load_force_asset(path):
    if path is None or hashlib.sha256(Path(path).read_bytes()).hexdigest() != ASSET_SHA256:
        raise ValueError("Missing or mismatched private force asset")
    with np.load(path, allow_pickle=False) as archive:
        if set(archive.files) != {"weights"}:
            raise ValueError("Force asset fields")
        weights = archive["weights"].copy()
    if weights.shape != (18, 3) or weights.dtype.kind not in "fi" or not np.isfinite(weights).all():
        raise ValueError("Force asset shape/values")
    return weights


def rollout(policy, case, out, asset=None, render=False):
    """Policy may be a validated JSON object or a path; never execute agent code."""
    if isinstance(policy, (str, Path)):
        raw = Path(policy).read_bytes()
        if len(raw) > 16384:
            raise ValueError("Policy size")
        policy = json.loads(raw)
    policy = validate(policy)
    revision = case.get("trajectory_revision", "fixed-eight/1")
    if revision not in ("fixed-eight/1", "general-eight/1"):
        raise ValueError("Trajectory revision")
    dynamics_revision = case.get("dynamics_revision", "scalar-wind/1")
    if dynamics_revision not in ("scalar-wind/1", "vector-wind/1"):
        raise ValueError("Dynamics revision")
    fields = {"plant_seed", "episode_seed", "stratum"}
    if not fields <= set(case) or set(case) - fields - {"trajectory_revision", "dynamics_revision"}:
        raise ValueError("Case fields")
    if type(case["stratum"]) is not int or not 0 <= case["stratum"] < 5:
        raise ValueError("Wind stratum")
    if type(case["episode_seed"]) is not int or not 0 <= case["episode_seed"] < 2**63:
        raise ValueError("Episode seed")
    params = parameters(case["plant_seed"])
    weights = load_force_asset(asset)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    controller = Controller(policy)
    rng = np.random.default_rng(case["episode_seed"])
    if revision == "fixed-eight/1":
        # Preserve the exact legacy RNG consumption before sensor-noise draws.
        phase = float(rng.uniform(-np.pi, np.pi))
        center = np.r_[rng.uniform(-0.4, 0.4, 2), 1.8]
        plane, command = "vertical", dict(phase=phase, yaw=0, center=center, rate=1.0)
    else:
        plane, command = episode_trajectory(case["episode_seed"])
        center = np.array(command["center"])
    initial_offset = rng.uniform(-0.15, 0.15, 3)
    vehicle = Vehicle(
        target(0, **command)[0] + initial_offset, mass_scale=params["mass_scale"], motor_tau=params["motor_tau"]
    )
    model, data = vehicle.model, vehicle.data
    wind_id = case["stratum"]
    force_calls = clipped_forces = 0

    def residual(state):
        nonlocal force_calls, clipped_forces
        wind = [0.0, 4.2, 8.5, 12.1, 8.5][wind_id]
        if wind_id == 4:
            wind += 2.4 * np.sin(state.time + params["wind_phase"])
        if dynamics_revision == "vector-wind/1":
            air = wind_vector(state.time, wind_id, params)
            raw = features(state.qvel[:3], state.qpos[3:7], 0.0) @ weights
            raw += wind_drag_increment(state.qvel[:3], air)
        else:
            raw = features(state.qvel[:3], state.qpos[3:7], wind) @ weights
        force_calls += 1
        clipped_forces += int(np.any(np.abs(raw) > 12))
        return np.clip(raw, -12, 12)

    telemetry, truth, errors = [], [], []
    crash = False
    curve = [target(t, **command)[0] for t in np.linspace(0, 2 * np.pi / command["rate"], 100, endpoint=False)]
    video = (
        Video(model, out / "video.mp4", center, curve=curve if revision == "general-eight/1" else None)
        if render
        else None
    )
    steps = round(DURATION / (command["rate"] * DT))
    bad_warnings = [
        mujoco.mjtWarning.mjWARN_BADQPOS,
        mujoco.mjtWarning.mjWARN_BADQVEL,
        mujoco.mjtWarning.mjWARN_BADQACC,
    ]
    try:
        for k in range(steps):
            t = k * DT
            obs = vehicle.observation(t, target(t, **command), rng)
            contact = vehicle.step(controller.action(obs), obs, policy, residual)
            finite = bool(np.isfinite(data.qpos).all() and np.isfinite(data.qvel).all())
            error = float(np.linalg.norm(data.qpos[:3] - target(t + DT, **command)[0])) if finite else 5.0
            errors.append(error)
            truth.append([data.time, *data.qpos, *data.qvel, *vehicle.rotor])
            if k % 5 == 0:
                telemetry.append(obs)
                model.site_pos[0] = target(t + DT, **command)[0]
                mujoco.mj_forward(model, data)
                if video:
                    video.frame(data)
            if (
                contact
                or not finite
                or any(data.warning[w].number for w in bad_warnings)
                or np.linalg.norm(data.qpos[:3] - center) > 5
            ):
                crash = True
                break
    finally:
        if video:
            video.close()
    rmse = float(np.sqrt(np.mean(np.square(errors))))
    complete = k + 1 == steps
    metrics = {
        "score": 0.0 if crash else float(100 * np.exp(-max(0, rmse - 0.03) / 0.25)),
        "success": bool(complete and not crash and rmse < 0.25),
        "rmse_m": rmse,
        "crash": crash,
        "duration_s": (k + 1) * DT,
        "complete": complete,
        "motor_saturation_fraction": vehicle.saturated_steps / (k + 1),
        "residual_clipping_fraction": clipped_forces / max(1, force_calls),
    }
    states = np.asarray(truth, dtype="<f8")
    np.savez_compressed(out / "trajectory.npz", state=states)
    record = {
        "revision": REVISION if revision == "general-eight/1" else "neuralfly-cpu/2",
        "metrics": metrics,
        "dynamics": params,
        "scenario": {
            "stratum": wind_id,
            **({"trajectory": command, "plane": plane} if revision == "general-eight/1" else {"phase": phase}),
            "center": center.tolist(),
            "initial_offset": initial_offset.tolist(),
        },
        "feedback": {"telemetry": telemetry},
        "state_sha256": hashlib.sha256(states.tobytes()).hexdigest(),
        "calibration": "flight-data-surrogate",
        "asset_sha256": ASSET_SHA256,
    }
    if dynamics_revision == "vector-wind/1":
        record["revision"] = "neuralfly-cpu/4"
        record["calibration"] = "zero-wind-flight-surrogate-plus-synthetic-vector-drag"
        record["dynamics"].update(dynamics_revision=dynamics_revision, drag_coefficient_kg_per_m=0.045)
        # Operator evidence only: adapter continues to receive feedback.telemetry.
        np.savez_compressed(
            out / "wind.npz",
            time=states[:, 0],
            velocity_world=np.array([wind_vector(t, wind_id, params) for t in states[:, 0]]),
        )
    (out / "record.json").write_text(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")
    return record
