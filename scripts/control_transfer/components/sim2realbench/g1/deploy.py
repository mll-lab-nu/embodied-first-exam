"""Operator-owned native MuJoCo CPU evaluator. Actor IMU is not LLM feedback."""

import os

os.environ["MUJOCO_GL"] = "osmesa"
os.environ["PYOPENGL_PLATFORM"] = "osmesa"
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "4"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["LP_NUM_THREADS"] = "4"
import argparse, json, subprocess, hashlib
from pathlib import Path
import mujoco
import numpy as np
from .assets import SCENE, POLICY, COMMIT, digest, verify
from .policy import Policy
from .terrain import build_model, terrain_parameters, ground_height


def parameters(seed, nominal=False):
    r = np.random.default_rng(seed)
    return {
        "mass_scale": 1.0 if nominal else float(r.uniform(0.85, 1.15)),
        "friction": 1.0 if nominal else float(r.uniform(0.45, 1.15)),
        "strength": ([1.0] * 29 if nominal else r.uniform(0.85, 1.15, 29).tolist()),
        "delay_steps": 0 if nominal else int(r.integers(0, 3)),
        "angle_sigma": 0.002 if nominal else float(r.uniform(0.003, 0.012)),
        "angle_bias": ([0.0] * 29 if nominal else r.normal(0, 0.004, 29).tolist()),
        "velocity_sigma": 0.02 if nominal else 0.06,
        "gyro_sigma": 0.005 if nominal else 0.015,
        "gravity_sigma": 0.002 if nominal else 0.005,
    }


def rollout(
    policy=POLICY,
    *,
    out,
    plant_seed=0,
    episode_seed=0,
    nominal=False,
    render=True,
    duration=20.0,
    speed=0.6,
    terrain="flat",
    initial_roll=0.0,
):
    if not np.isfinite(duration) or not 3 <= duration <= 120 or not np.isfinite(speed) or not 0 < speed <= 1:
        raise ValueError("Invalid operator episode specification")
    # no CPU pinning: the container's CPU quota bounds it, and pinning to the first four host CPUs put every
    # trial on a host on the same cores (board 0165); the thread counts above / below bound the parallelism
    verify()
    actor = Policy(policy)
    terrain_config = terrain_parameters(terrain, episode_seed)
    model = build_model(SCENE, terrain_config)
    model.opt.timestep = 0.002
    data = mujoco.MjData(model)
    rng = np.random.default_rng(episode_seed)
    plant = parameters(plant_seed, nominal)
    model.body_mass[1:] *= plant["mass_scale"]
    model.body_inertia[1:] *= plant["mass_scale"]
    model.geom_friction[:, 0] = plant["friction"]
    mujoco.mj_setConst(model, data)
    ids = np.array([mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, n) for n in actor.joints])
    assert np.all(ids >= 0)
    qp = model.jnt_qposadr[ids]
    qv = model.jnt_dofadr[ids]
    motors = []
    for j in ids:
        matches = np.flatnonzero(model.actuator_trnid[:, 0] == j)
        if len(matches) != 1:
            raise RuntimeError("Actuator mapping mismatch")
        motors.append(int(matches[0]))
    motors = np.array(motors)
    if not np.isfinite(initial_roll) or abs(initial_roll) > 1.6:
        raise ValueError("Invalid operator initial pose")
    initial_rng = np.random.default_rng(np.random.SeedSequence([episode_seed, 917]))
    data.qpos[:3] = [float(initial_rng.uniform(-0.15, 0.15)), float(initial_rng.uniform(-0.15, 0.15)), 0.79]
    data.qpos[3:7] = [np.cos(initial_roll / 2), np.sin(initial_roll / 2), 0, 0]
    data.qpos[qp] = actor.default
    mujoco.mj_forward(model, data)
    renderer = mujoco.Renderer(model, height=240, width=320) if render else None
    scene_option = mujoco.MjvOption()
    scene_option.geomgroup[5] = 1  # Terrain ray group is hidden by MuJoCo viewer defaults.
    camera = mujoco.MjvCamera()
    camera.distance = 2.8
    camera.azimuth = 135
    camera.elevation = -15
    gyro = model.sensor("imu_gyro").adr[0]
    quat = model.sensor("imu_quat").adr[0]
    last = np.zeros(29, np.float32)
    queue = [actor.default.copy() for _ in range(plant["delay_steps"])]
    state_hash = hashlib.sha256()
    frames = []
    telemetry = []
    commands = []
    errors = []
    fallen = False
    start = None
    phase = 0.0
    frame_times = []
    policy_steps = int(round(duration / 0.02))
    control = actor.default.copy()
    try:
        for step in range(policy_steps):
            time_s = step * 0.02
            command = np.array([speed if time_s >= 2 else 0.0, 0.0, 0.0])
            phase = (phase + 0.02 / 0.6) % 1
            q = data.qpos[qp].copy() + np.array(plant["angle_bias"]) + rng.normal(0, plant["angle_sigma"], 29)
            dq = data.qvel[qv].copy() + rng.normal(0, plant["velocity_sigma"], 29)
            omega = data.sensordata[gyro : gyro + 3].copy() + rng.normal(0, plant["gyro_sigma"], 3)
            rot = np.empty(9)
            mujoco.mju_quat2Mat(rot, data.sensordata[quat : quat + 4])
            gravity = rot.reshape(3, 3).T @ np.array([0, 0, -1.0])
            gravity += rng.normal(0, plant["gravity_sigma"], 3)
            gravity /= np.linalg.norm(gravity)
            clock = (
                np.array([np.sin(2 * np.pi * phase), np.cos(2 * np.pi * phase)])
                if np.linalg.norm(command) >= 0.1
                else np.zeros(2)
            )
            obs = np.concatenate([omega, gravity, command, clock, q - actor.default, dq, last])
            last = actor(obs)
            queue.append(actor.default + actor.scale * last)
            control = queue.pop(0)
            if step % 5 == 0:
                telemetry.append({"t": round(time_s, 6), "values": q.tolist()})
                commands.append({"t": round(time_s, 6), "values": command.tolist()})
                frame_times.append(round(time_s, 6))
                if renderer:
                    camera.lookat[:] = [data.qpos[0], data.qpos[1], 0.8]
                    renderer.update_scene(data, camera, scene_option=scene_option)
                    frames.append(renderer.render())
            previous = float(data.qpos[0])
            if step == 100:
                start = data.qpos[:2].copy()
            for _ in range(10):
                torque = actor.kp * (control - data.qpos[qp]) - actor.kd * data.qvel[qv]
                data.ctrl[motors] = np.clip(
                    torque * np.array(plant["strength"]),
                    model.actuator_ctrlrange[motors, 0],
                    model.actuator_ctrlrange[motors, 1],
                )
                mujoco.mj_step(model, data)
                state_hash.update(np.concatenate([data.qpos, data.qvel, data.act, data.ctrl]).astype("<f8").tobytes())
            if step >= 100:
                errors.append(abs((float(data.qpos[0]) - previous) / 0.02 - speed))
            body_up = 1 - 2 * (data.qpos[4] ** 2 + data.qpos[5] ** 2)
            clearance = data.qpos[2] - ground_height(model, data, *data.qpos[:2])
            if clearance < 0.45 or body_up < 0.5 or not np.isfinite(data.qpos).all():
                fallen = True
                break
        elapsed = (step + 1) * 0.02
        travel = data.qpos[:2] - (start if start is not None else np.zeros(2))
        mae = float(np.mean(errors)) if errors else float(abs(speed))
        survival = max(0, elapsed - 2) / (duration - 2)
        metrics = {
            "score": float(
                100
                * survival
                * np.exp(-mae / max(abs(speed), 0.1))
                * np.clip(travel[0] / (speed * (duration - 2)), 0, 1)
            ),
            "duration_s": elapsed,
            "forward_displacement_m": float(travel[0]),
            "lateral_displacement_m": float(travel[1]),
            "mean_abs_speed_error_m_s": mae,
            "fell": fallen,
            "walking_success": bool(
                not fallen
                and elapsed >= duration
                and mae < 0.25
                and travel[0] > 0.65 * speed * (duration - 2)
                and abs(travel[1]) < 2
            ),
        }
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        result = {
            "state_sha256": state_hash.hexdigest(),
            "task": "unitree_g1_terrain_transfer_v1",
            "upstream_commit": COMMIT,
            "kind": "operator_policy_validation",
            "policy_sha256": digest(policy),
            "policy_metadata": {"abi": "g1-numeric/1"},
            "plant_seed": plant_seed,
            "episode_seed": episode_seed,
            "nominal": nominal,
            "command_speed_m_s": speed,
            "requested_duration_s": duration,
            "feedback": {"telemetry": telemetry, "commands": commands},
            "frame_times_s": frame_times,
            "joint_names": actor.joints,
            "dynamics": plant,
            "terrain": terrain_config,
            "metrics": metrics,
            "physics": "native MuJoCo CPU",
            "renderer": "OSMesa software",
            "mujoco_version": mujoco.__version__,
            "policy_provider": ["numpy-cpu"],
        }
        metrics["success"] = metrics["walking_success"]
        if render:
            subprocess.run(
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
                    "320x240",
                    "-r",
                    "10",
                    "-i",
                    "pipe:0",
                    "-an",
                    "-c:v",
                    "libx264",
                    "-threads",
                    "1",
                    "-crf",
                    "31",
                    "-pix_fmt",
                    "yuv420p",
                    "-movflags",
                    "+faststart",
                    str(out / "video.mp4"),
                ],
                input=np.stack(frames).tobytes(),
                capture_output=True,
                check=True,
                timeout=60,
            )
            result["video_sha256"] = digest(out / "video.mp4")
        (out / "record.json").write_text(json.dumps(result, allow_nan=False))
        return result
    finally:
        if renderer:
            renderer.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--policy", type=Path, default=POLICY)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--plant-seed", type=int, default=0)
    p.add_argument("--episode-seed", type=int, default=0)
    p.add_argument("--nominal", action="store_true")
    p.add_argument("--no-video", action="store_true")
    p.add_argument("--duration", type=float, default=20.0)
    p.add_argument("--terrain", choices=["flat", "slope", "rough", "steps"], default="flat")
    p.add_argument("--speed", type=float, default=0.6)
    p.add_argument("--initial-roll", type=float, default=0.0)
    a = p.parse_args()
    print(
        json.dumps(
            rollout(
                a.policy,
                out=a.out,
                plant_seed=a.plant_seed,
                episode_seed=a.episode_seed,
                nominal=a.nominal,
                render=not a.no_video,
                duration=a.duration,
                terrain=a.terrain,
                speed=a.speed,
                initial_roll=a.initial_roll,
            )["metrics"]
        )
    )
