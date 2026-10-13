"""Paper-geometry-inspired six-DoF CPU model, with separately fitted private force surrogate."""

import json, hashlib, subprocess
from pathlib import Path
import numpy as np
import mujoco
from ..control_public.fly import Controller, target, MASS, DT, DURATION


def features(v, q, wind):
    q = np.asarray(q, dtype=float)
    q = q / np.linalg.norm(q)
    q = q if q[0] >= 0 else -q
    x = np.r_[v, q[1:], wind / 6.1]
    return np.r_[1, x, x * x, x[:3] * x[-1]]


def xml():
    return (
        """<mujoco><option timestep=".002" gravity="0 0 -9.81" integrator="RK4"/><visual><global offwidth="640" offheight="480"/><headlight ambient=".45 .45 .45"/></visual><worldbody><light pos="0 -3 5"/><geom type="plane" size="8 8 .1" rgba=".23 .24 .25 1"/><site name="goal" size=".055" rgba="1 .6 .1 .8"/><body name="drone" pos="0 0 1.8"><freejoint/><inertial pos="0 0 0" mass="2.53" diaginertia=".04 .04 .07"/><geom type="box" size=".12 .08 .05" rgba=".28 .32 .36 1"/><geom type="capsule" fromto="-.195 -.195 0 .195 .195 0" size=".018"/><geom type="capsule" fromto="-.195 .195 0 .195 -.195 0" size=".018"/>"""
        + "".join(
            f'<geom type="cylinder" pos="{x} {y} .025" size=".1397 .008" rgba=".15 .19 .23 .7" contype="0" conaffinity="0"/>'
            for x, y in [(0.195, 0.195), (-0.195, 0.195), (-0.195, -0.195), (0.195, -0.195)]
        )
        + "</body></worldbody></mujoco>"
    )


def rollout(policy, case, out, asset=None, render=False):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    c = Controller(policy)
    rng = np.random.default_rng(case["episode_seed"])
    plant_rng = np.random.default_rng(case["plant_seed"])
    phase = float(rng.uniform(-np.pi, np.pi))
    yaw = 0.0
    center = np.r_[rng.uniform(-0.4, 0.4, 2), 1.8]
    model = mujoco.MjModel.from_xml_string(xml())
    data = mujoco.MjData(model)
    data.qpos[:3] = target(0, phase, yaw, center)[0] + rng.uniform(-0.15, 0.15, 3)
    data.qpos[3] = 1
    mujoco.mj_forward(model, data)
    # Wind families are fixed strata; phase and plant lag vary independently by deployment bank.
    winds = [0.0, 4.2, 8.5, 12.1, 8.5]
    wind_id = int(case.get("stratum", 0)) % 5
    params = {
        "wind_id": wind_id,
        "wind_phase": float(plant_rng.uniform(-np.pi, np.pi)),
        "motor_tau": float(plant_rng.uniform(0.02, 0.06)),
        "mass_scale": float(plant_rng.uniform(0.97, 1.03)),
    }
    model.body_mass[1] *= params["mass_scale"]
    model.body_inertia[1] *= params["mass_scale"]
    mujoco.mj_setConst(model, data)
    weights = None
    if asset:
        with np.load(asset, allow_pickle=False) as z:
            weights = z["weights"].copy()
        if weights.shape != (18, 3) or not np.isfinite(weights).all():
            raise ValueError("Force asset")
    rotor = np.full(4, MASS * 9.81 / 4)
    xy = [(0.195, 0.195), (-0.195, 0.195), (-0.195, -0.195), (0.195, -0.195)]
    A = np.array([[1] * 4, [y for x, y in xy], [-x for x, y in xy], [0.02, -0.02, 0.02, -0.02]])
    telemetry = []
    truth = []
    errors = []
    crash = False
    renderer = writer = None
    if render:
        renderer = mujoco.Renderer(model, 480, 640)
        cam = mujoco.MjvCamera()
        cam.lookat[:] = [0, 0, 1.6]
        cam.distance = 6
        cam.azimuth = 110
        cam.elevation = -18
        writer = subprocess.Popen(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "-s",
                "640x480",
                "-r",
                "10",
                "-i",
                "pipe:0",
                "-an",
                "-c:v",
                "libx264",
                "-threads",
                "1",
                "-pix_fmt",
                "yuv420p",
                str(out / "video.mp4"),
            ],
            stdin=subprocess.PIPE,
        )
    try:
        for k in range(round(DURATION / DT)):
            t = k * DT
            goal, vel, acc = target(t, phase, yaw, center)
            q = data.qpos[3:7] + rng.normal(0, 0.0005, 4)
            q /= np.linalg.norm(q)
            obs = {
                "t": t,
                "position": (data.qpos[:3] + rng.normal(0, 0.01, 3)).tolist(),
                "velocity": (data.qvel[:3] + rng.normal(0, 0.02, 3)).tolist(),
                "quaternion": q.tolist(),
                "omega": (data.qvel[3:] + rng.normal(0, 0.003, 3)).tolist(),
                "target_position": goal.tolist(),
                "target_velocity": vel.tolist(),
                "target_acceleration": acc.tolist(),
            }
            f = c.action(obs)
            rot = np.empty(9)
            mujoco.mju_quat2Mat(rot, q)
            rot = rot.reshape(3, 3)
            z = f / max(np.linalg.norm(f), 1e-9)
            y = np.cross(z, [1.0, 0, 0])
            y /= max(np.linalg.norm(y), 1e-9)
            desired = np.column_stack([np.cross(y, z), y, z])
            err = 0.5 * sum(np.cross(rot[:, i], desired[:, i]) for i in range(3))
            torque = np.array([0.04, 0.04, 0.07]) * (
                policy["attitude_gain"] * (rot.T @ err) - policy["rate_gain"] * np.array(obs["omega"])
            )
            cmd = np.clip(np.linalg.solve(A, np.r_[max(0, f @ rot[:, 2]), torque]), 0, MASS * 9.81 * 2.2 / 4)
            wind = winds[wind_id] + (2.4 * np.sin(t + params["wind_phase"]) if wind_id == 4 else 0)
            force = (
                np.zeros(3)
                if weights is None
                else np.clip(features(data.qvel[:3], data.qpos[3:7], wind) @ weights, -12, 12)
            )
            for _ in range(10):
                rotor += (1 - np.exp(-0.002 / params["motor_tau"])) * (cmd - rotor)
                wrench = A @ rotor
                rot = data.xmat[1].reshape(3, 3)
                data.qfrc_applied[:] = 0
                mujoco.mj_applyFT(
                    model,
                    data,
                    rot @ np.array([0, 0, wrench[0]]) + force,
                    rot @ wrench[1:],
                    data.xpos[1],
                    1,
                    data.qfrc_applied,
                )
                mujoco.mj_step(model, data)
            error = float(np.linalg.norm(data.qpos[:3] - target(t + DT, phase, yaw, center)[0]))
            errors.append(error)
            truth.append([*data.qpos, *data.qvel])
            if k % 5 == 0:
                telemetry.append(obs)
                model.site_pos[0] = goal
                mujoco.mj_forward(model, data)
                if renderer:
                    renderer.update_scene(data, camera=cam)
                    writer.stdin.write(renderer.render().tobytes())
            if data.ncon or not np.isfinite(data.qpos).all() or np.linalg.norm(data.qpos[:3] - center) > 5:
                crash = True
                break
    finally:
        if renderer:
            renderer.close()
        if writer:
            writer.stdin.close()
            code = writer.wait(timeout=60)
    if writer and code:
        raise RuntimeError("Video encoding failed")
    rmse = float(np.sqrt(np.mean(np.square(errors))))
    success = not crash and rmse < 0.25
    metrics = {
        "score": 0.0 if crash else float(100 * np.exp(-max(0, rmse - 0.03) / 0.25)),
        "success": success,
        "rmse_m": rmse,
        "crash": crash,
        "duration_s": (k + 1) * DT,
    }
    record = {
        "metrics": metrics,
        "dynamics": params,
        "feedback": {"telemetry": telemetry},
        "state_sha256": hashlib.sha256(np.array(truth).tobytes()).hexdigest(),
        "calibration": "flight-data-surrogate" if weights is not None else "nominal-zero-residual",
    }
    (out / "record.json").write_text(json.dumps(record, allow_nan=False))
    return record
