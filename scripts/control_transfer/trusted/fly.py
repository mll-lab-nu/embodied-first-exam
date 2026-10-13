"""Private CPU deployment model with flight-log-fitted aerodynamic forces."""

import hashlib
import json
from pathlib import Path

import mujoco
import numpy as np

from ..control_public.fly import Controller, DT, DURATION, Vehicle, target, validate
from ..neuralfly_video import Video

REVISION = "neuralfly-cpu/2"
ASSET_SHA256 = "551eeb0d8e2c75e157c087f1ab2f5e40e68400a84fdf0882ed719ddfcfd8108a"


def features(v, q, wind):
    q = np.asarray(q, dtype=float)
    q = q / np.linalg.norm(q)
    q = q if q[0] >= 0 else -q
    x = np.r_[v, q[1:], wind / 6.1]
    return np.r_[1, x, x * x, x[:3] * x[-1]]


def parameters(seed):
    if type(seed) is not int or not 0 <= seed < 2**63:
        raise ValueError("Plant seed")
    rng = np.random.default_rng(seed)
    return {
        "wind_phase": float(rng.uniform(-np.pi, np.pi)),
        "motor_tau": float(rng.uniform(0.02, 0.06)),
        "mass_scale": float(rng.uniform(0.97, 1.03)),
    }


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
    if set(case) != {"plant_seed", "episode_seed", "stratum"}:
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
    phase = float(rng.uniform(-np.pi, np.pi))
    center = np.r_[rng.uniform(-0.4, 0.4, 2), 1.8]
    initial_offset = rng.uniform(-0.15, 0.15, 3)
    vehicle = Vehicle(
        target(0, phase, 0, center)[0] + initial_offset, mass_scale=params["mass_scale"], motor_tau=params["motor_tau"]
    )
    model, data = vehicle.model, vehicle.data
    wind_id = case["stratum"]
    force_calls = clipped_forces = 0

    def residual(state):
        nonlocal force_calls, clipped_forces
        wind = [0.0, 4.2, 8.5, 12.1, 8.5][wind_id]
        if wind_id == 4:
            wind += 2.4 * np.sin(state.time + params["wind_phase"])
        raw = features(state.qvel[:3], state.qpos[3:7], wind) @ weights
        force_calls += 1
        clipped_forces += int(np.any(np.abs(raw) > 12))
        return np.clip(raw, -12, 12)

    telemetry, truth, errors = [], [], []
    crash = False
    video = Video(model, out / "video.mp4", center) if render else None
    steps = round(DURATION / DT)
    bad_warnings = [
        mujoco.mjtWarning.mjWARN_BADQPOS,
        mujoco.mjtWarning.mjWARN_BADQVEL,
        mujoco.mjtWarning.mjWARN_BADQACC,
    ]
    try:
        for k in range(steps):
            t = k * DT
            obs = vehicle.observation(t, target(t, phase, 0, center), rng)
            contact = vehicle.step(controller.action(obs), obs, policy, residual)
            finite = bool(np.isfinite(data.qpos).all() and np.isfinite(data.qvel).all())
            error = float(np.linalg.norm(data.qpos[:3] - target(t + DT, phase, 0, center)[0])) if finite else 5.0
            errors.append(error)
            truth.append([data.time, *data.qpos, *data.qvel, *vehicle.rotor])
            if k % 5 == 0:
                telemetry.append(obs)
                model.site_pos[0] = target(t + DT, phase, 0, center)[0]
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
        "revision": REVISION,
        "metrics": metrics,
        "dynamics": params,
        "scenario": {
            "stratum": wind_id,
            "phase": phase,
            "center": center.tolist(),
            "initial_offset": initial_offset.tolist(),
        },
        "feedback": {"telemetry": telemetry},
        "state_sha256": hashlib.sha256(states.tobytes()).hexdigest(),
        "calibration": "flight-data-surrogate",
        "asset_sha256": ASSET_SHA256,
    }
    (out / "record.json").write_text(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")
    return record
