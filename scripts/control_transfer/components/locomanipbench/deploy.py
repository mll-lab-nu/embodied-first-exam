"""Native CPU MuJoCo deployment. Policy only sees noisy public observations."""

import os

os.environ.setdefault("MUJOCO_GL", "egl")
import json, hashlib, subprocess
from pathlib import Path
from collections import deque
import numpy as np
import mujoco
from .models import Robot, verify
from .task import Reference, MODES, DT, DURATION, errors, REFERENCE_VERSION, evaluation_class
from .policy import Policy
from . import visuals


def rollout(
    robot,
    policy=None,
    *,
    mode="coordinated",
    plant_seed=0,
    episode_seed=0,
    nominal=False,
    render=False,
    out=None,
    expert=False,
    reference_version=REFERENCE_VERSION,
):
    archive_hash = verify(robot)
    plant = Robot(robot)
    nom = Robot(robot)
    ref = Reference(robot, episode_seed, mode, version=reference_version)
    m = plant.m
    d = plant.d
    rng = np.random.default_rng(plant_seed)
    noise = np.random.default_rng(episode_seed + 1)
    params = {
        "mass_scale": 1.0 if nominal else float(rng.uniform(0.9, 1.1)),
        "motor_scale": 1.0 if nominal else float(rng.uniform(0.85, 1.15)),
        "damping_scale": 1.0 if nominal else float(rng.uniform(0.8, 1.2)),
        "delay_steps": 0 if nominal else int(rng.integers(0, 3)),
        "encoder_sigma": 0.001 if nominal else float(rng.uniform(0.002, 0.006)),
    }
    m.body_mass[1:] *= params["mass_scale"]
    m.body_inertia[1:] *= params["mass_scale"]
    m.actuator_gainprm[:, 0] *= params["motor_scale"]
    m.actuator_biasprm[:, 1] *= params["motor_scale"]
    m.actuator_biasprm[:, 2] *= params["damping_scale"]
    m.actuator_forcerange[:] *= params["motor_scale"]
    mujoco.mj_setConst(m, d)
    plant.set(plant.home)
    actor = Policy(policy, robot) if policy else None
    homectrl = np.array([plant.home[m.jnt_qposadr[m.actuator_trnid[i, 0]]] for i in range(m.nu)])
    queue = deque([homectrl.copy()] * (params["delay_steps"] + 1), maxlen=params["delay_steps"] + 1)
    bias = noise.normal(0, params["encoder_sigma"] / 2, m.nq)
    renderer = writer = None
    telemetry = []
    targets = []
    trajectory = []
    metric_rows = []
    actions = []
    states = []
    if render:
        out = Path(out)
        out.mkdir(parents=True, exist_ok=False)
        visuals.style(m)
        renderer = mujoco.Renderer(m, 240, 320)
        cam = mujoco.MjvCamera()
        cam.lookat[:] = [0, 0, 0.9]
        cam.distance = 3.7
        cam.azimuth = -65
        cam.elevation = -23
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
                "-pix_fmt",
                "yuv420p",
                str(out / "video.mp4"),
            ],
            stdin=subprocess.PIPE,
        )
    try:
        for step in range(round(DURATION / DT)):
            t = step * DT
            target, twist = ref.sample(t)
            q = d.qpos.copy() + bias + noise.normal(0, params["encoder_sigma"], m.nq)
            v = d.qvel.copy() + noise.normal(0, 0.015, m.nv)
            feature, err = nom.feature(q, v, target, twist)
            action = actor(feature) if actor else nom.expert(err, twist) if expert else np.zeros(nom.n)
            action = np.clip(action, -1, 1)
            vel = action * nom.speed
            command = homectrl.copy()
            kp = nom.m.actuator_gainprm[:, 0]
            kd = -nom.m.actuator_biasprm[:, 2]
            # The fixed servo wrapper uses nominal gravity, never target masses or true q.
            command += nom.d.qfrc_bias[nom.m.jnt_dofadr[nom.m.actuator_trnid[:, 0]]] / kp
            command[nom.aids] = (
                q[nom.qids] + kd[nom.aids] / kp[nom.aids] * vel + nom.d.qfrc_bias[nom.vids] / kp[nom.aids]
            )
            command = np.clip(command, m.actuator_ctrlrange[:, 0], m.actuator_ctrlrange[:, 1])
            queue.append(command)
            d.ctrl[:] = queue[0]
            observed = q[plant.qids]
            if step % 5 == 0:
                telemetry.append({"t": round(t, 2), "values": observed.tolist()})
                targets.append(
                    {
                        "t": round(t, 2),
                        "base": target[0].tolist(),
                        "hands": [{"position": p.tolist(), "rotation": r.tolist()} for p, r in target[1]],
                    }
                )
                if True:
                    m.site_pos[m.site("base_goal").id] = [target[0][0], target[0][1], 0.02]
                    for name, (p, r) in zip(["left_goal", "right_goal"], target[1]):
                        m.site_pos[m.site(name).id] = p
                    mujoco.mj_forward(m, d)
                    if renderer:
                        renderer.update_scene(d, camera=cam)
                        visuals.targets(renderer.scene, target, m.geom_pos[m.geom("floor").id, 2])
                        writer.stdin.write(renderer.render().tobytes())
            e = errors(plant.poses(), target)
            if t >= 1:
                metric_rows.append(e)
            states.append([*d.qpos, *d.qvel])
            trajectory.append({"t": round(t, 2), "errors": e.tolist(), "action": action.tolist()})
            actions.append(action)
            for _ in range(10):
                mujoco.mj_step(m, d)
            if not np.isfinite(d.qpos).all() or np.max(np.abs(d.qvel)) > 100:
                raise RuntimeError("Unstable plant")
    finally:
        if renderer:
            renderer.close()
        if writer:
            writer.stdin.close()
            code = writer.wait(timeout=60)
    if render and code:
        raise RuntimeError("Video encoding failed")
    mean = np.mean(metric_rows, 0)
    threshold = np.array([0.06, 0.12, 0.07, 0.07, 0.2, 0.2])
    success = bool(np.all(mean < threshold))
    score = float(100 * np.exp(-np.mean(mean / threshold)))
    metrics = dict(
        zip(
            [
                "base_xy_error_m",
                "base_yaw_error_rad",
                "left_position_error_m",
                "right_position_error_m",
                "left_orientation_error_rad",
                "right_orientation_error_rad",
            ],
            map(float, mean),
        )
    )
    metrics.update(
        score=score, success=success, duration_s=DURATION, action_rate=float(np.mean(np.diff(actions, axis=0) ** 2))
    )
    record = {
        "state_sha256": hashlib.sha256(np.asarray(states).tobytes()).hexdigest(),
        "evaluation_class": evaluation_class(mode),
        "reference_version": reference_version,
        "robot": robot,
        "mode": mode,
        "controller": "trained_network" if actor else "nominal_expert" if expert else "zero_velocity_baseline",
        "policy_sha256": hashlib.sha256(Path(policy).read_bytes()).hexdigest() if policy else None,
        "attachment_sha256": archive_hash,
        "plant_seed": plant_seed,
        "episode_seed": episode_seed,
        "nominal": nominal,
        "dynamics": params,
        "metrics": metrics,
        "feedback": {"telemetry": telemetry, "targets": targets},
        "channels": plant.names,
        "operator_trajectory": trajectory,
    }
    if out:
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        if render:
            record["visualization_revision"] = visuals.REVISION
            record["video_sha256"] = hashlib.sha256((out / "video.mp4").read_bytes()).hexdigest()
        (out / "record.json").write_text(json.dumps(record, allow_nan=False))
    return record


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--robot", choices=["linearbot", "vega"], required=True)
    p.add_argument("--policy", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--mode", choices=MODES, default="coordinated")
    p.add_argument("--expert", action="store_true")
    a = p.parse_args()
    print(json.dumps(rollout(a.robot, a.policy, mode=a.mode, expert=a.expert, render=True, out=a.out)["metrics"]))
