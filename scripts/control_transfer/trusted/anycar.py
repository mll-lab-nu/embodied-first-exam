"""Private multi-surface deployment family. Never install in the agent image."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import numpy as np
from ..control_public.anycar import CHANNELS, UNITS, DEFAULT, BOUNDS, DT, HORIZON, Controller, reference, validate, wrap
from ..components.anycarbench.model import Vehicle, mujoco

NOISE = np.array([0.008, 0.008, 0.005, 0.035, 0.02, 0.012, 0.15, 0.15, 0.15, 0.15, 0.002])


def plant_parameters(seed):
    rng = np.random.default_rng(seed)
    return dict(
        mass_scale=float(rng.uniform(0.85, 1.15)),
        inertia_scale=float(rng.uniform(0.85, 1.15)),
        com_x=float(rng.uniform(-0.015, 0.015)),
        com_y=float(rng.uniform(-0.008, 0.008)),
        motor_gain=float(rng.uniform(0.8, 1.15)),
        steering_gain=float(rng.uniform(0.85, 1.15)),
        steering_bias=float(rng.uniform(-0.025, 0.025)),
        motor_tau=float(rng.uniform(0.03, 0.09)),
        steering_tau=float(rng.uniform(0.025, 0.065)),
        delay_steps=int(rng.integers(1, 5)),
    )


def episode_parameters(seed):
    rng = np.random.default_rng(seed)
    command = dict(
        a=float(rng.uniform(4.2, 4.8)),
        b=float(rng.uniform(3.2, 3.7)),
        phase=float(rng.uniform(-np.pi, np.pi)),
        direction=int(rng.choice([-1, 1])),
    )
    boundaries = [-12, float(rng.uniform(-2.7, -1.3)), float(rng.uniform(-0.4, 0.4)), float(rng.uniform(1.3, 2.7)), 12]
    mus = rng.permutation(
        [
            float(rng.uniform(0.32, 0.42)),
            float(rng.uniform(0.5, 0.65)),
            float(rng.uniform(0.75, 0.9)),
            float(rng.uniform(0.95, 1.05)),
        ]
    )
    surfaces = [(boundaries[i], boundaries[i + 1], float(mus[i])) for i in range(4)]
    offset = rng.uniform(-0.08, 0.08, 2)
    return command, surfaces, offset, float(rng.uniform(-0.05, 0.05))


def make_spec(index):
    plant_seed = 91000 + index

    def cases(start, n):
        return [dict(plant_seed=plant_seed, episode_seed=92000 + index * 1000 + start + i) for i in range(n)]

    public = dict(
        schema="control-transfer/1",
        protocol="eai-policy/1.1",
        name="anycar",
        goal="Track one prescribed-time lap of a randomized ellipse across rigid traction patches; avoid barriers, rollover and offtrack excursions.",
        score="Ordered completion and time-indexed position/heading/speed accuracy. Safety violation gives zero. No nearest-waypoint score.",
        max_rounds=3,
        adaptation_cases=3,
        held_out_cases=10,
        training_backend="nominal MuJoCo CPU",
        evaluation_backend="native MuJoCo CPU + OSMesa + NumPy CPU",
        policy_abi="anycar-controller/1 bounded numeric JSON",
        default_policy=DEFAULT,
        bounds=BOUNDS,
        channels=CHANNELS,
        units=UNITS,
        image_interval_s=1.0,
        limitations="Procedural chassis with retained contact-wheel mechanism. Rigid Coulomb friction is not deformable sand. No AnyCar learned transformer is evaluated.",
    )
    return dict(
        schema="control-transfer-instance/1",
        family="anycar",
        name="anycar",
        index=index,
        public=public,
        bank=dict(adaptation=cases(0, 3), held_out=cases(100, 10)),
    )


class Video:
    def __init__(self, vehicle, out):
        if os.environ.get("MUJOCO_GL") != "osmesa":
            raise RuntimeError("Evaluation video requires OSMesa")
        self.renderer = mujoco.Renderer(vehicle.model, height=480, width=640)
        from OpenGL.GL import glGetString, GL_RENDERER, GL_VENDOR

        self.gl_renderer = glGetString(GL_RENDERER).decode()
        self.gl_vendor = glGetString(GL_VENDOR).decode()
        if not any(name in self.gl_renderer.lower() for name in ("llvmpipe", "softpipe")):
            self.renderer.close()
            raise RuntimeError("A software OpenGL renderer is required")
        self.camera = mujoco.MjvCamera()
        self.camera.lookat[:] = [0, 0, 0]
        self.camera.distance = 13
        self.camera.azimuth = 90
        self.camera.elevation = -70
        self.process = subprocess.Popen(
            [
                "ffmpeg",
                "-v",
                "error",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "-s",
                "640x480",
                "-r",
                "10",
                "-i",
                "-",
                "-an",
                "-c:v",
                "libx264",
                "-threads",
                "1",
                "-preset",
                "fast",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                str(out / "video.mp4"),
            ],
            stdin=subprocess.PIPE,
        )

    def frame(self, v, target):
        self.renderer.update_scene(v.data, camera=self.camera)
        scene = self.renderer.scene
        # Public commanded target marker, no privileged trajectory/score overlays.
        geom = scene.geoms[scene.ngeom]
        mujoco.mjv_initGeom(
            geom,
            mujoco.mjtGeom.mjGEOM_SPHERE,
            np.array([0.09, 0.09, 0.09]),
            np.array([target[0], target[1], 0.13]),
            np.eye(3).ravel(),
            np.array([0.1, 0.85, 0.55, 0.85]),
        )
        scene.ngeom += 1
        self.process.stdin.write(self.renderer.render().tobytes())

    def close(self):
        self.process.stdin.close()
        rc = self.process.wait(timeout=60)
        self.renderer.close()
        if rc:
            raise RuntimeError("Video encoding failed")


def score_trajectory(states, targets, command, collision=False, body_contact=False, rollover=False):
    states, targets = np.asarray(states), np.asarray(targets)
    errors = np.linalg.norm(states[:, :2] - targets[:, :2], axis=1)
    heading = np.abs(wrap(states[:, 2] - targets[:, 2]))
    speed = np.abs(states[:, 3] - targets[:, 3])
    phase = np.unwrap(np.arctan2(states[:, 1] / command["b"], states[:, 0] / command["a"]))
    progress = command["direction"] * (phase - phase[0])
    # Gates must be crossed in order and near the center line, not via chord shortcuts.
    radial = np.abs(np.sqrt((states[:, 0] / command["a"]) ** 2 + (states[:, 1] / command["b"]) ** 2) - 1) * min(
        command["a"], command["b"]
    )
    gate = 1
    for angle, err in zip(progress, radial):
        if gate <= 24 and angle >= gate * 2 * np.pi / 24 and err < 0.45:
            gate += 1
    completion = min((gate - 1) / 24, 1.0)
    offtrack = bool(np.max(radial) > 0.70)
    rmse = float(np.sqrt(np.mean(errors**2)))
    mae_heading = float(np.mean(heading))
    mae_speed = float(np.mean(speed))
    unsafe = bool(collision or body_contact or rollover or offtrack)
    success = bool(
        not unsafe
        and completion >= 23 / 24
        and rmse < 0.30
        and mae_heading < 0.18
        and mae_speed < 0.25
        and errors[-1] < 0.35
    )
    quality = float(np.exp(-rmse / 0.35 - mae_heading / 0.3 - mae_speed / 0.4))
    score = 0.0 if unsafe else 100 * completion * quality
    return dict(
        success=success,
        score=score,
        tracking_rmse_m=rmse,
        heading_mae_rad=mae_heading,
        speed_mae_m_s=mae_speed,
        ordered_gate_fraction=completion,
        offtrack=offtrack,
        collision=bool(collision),
        body_contact=bool(body_contact),
        rollover=bool(rollover),
    )


def rollout(policy_path, case, out, render=True):
    policy = json.loads(Path(policy_path).read_text())
    raw = validate(policy)
    plant = plant_parameters(case["plant_seed"])
    command, surfaces, offset, angle = episode_parameters(case["episode_seed"])
    rng = np.random.default_rng(case["episode_seed"] + 300000)
    v = Vehicle(plant, surfaces, command)
    start = reference(0, command)
    v.reset(start[0] + offset[0], start[1] + offset[1], start[2] + angle)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    video = Video(v, out) if render else None
    controller = Controller(policy)
    telemetry = []
    states = []
    targets = []
    sha = hashlib.sha256()
    rollover = False
    try:
        for i in range(round(HORIZON / DT) + 1):
            t = i * DT
            state = v.state()
            target = reference(t, command)
            observation = state + rng.normal(0, NOISE)
            action = controller.step(observation, reference(min(t + policy["preview"], HORIZON), command))
            states.append(state)
            targets.append(target)
            sha.update(np.asarray(np.r_[t, v.data.qpos, v.data.qvel, v.data.act, v.applied], dtype="<f8").tobytes())
            rollover |= bool(v.data.xmat[1].reshape(3, 3)[2, 2] < 0.5)
            if i % 5 == 0:
                telemetry.append(dict(t=t, values=[*observation.tolist(), *target.tolist(), *action.tolist()]))
                if video:
                    video.frame(v, target)
            if i < round(HORIZON / DT):
                v.advance(action)
    finally:
        if video:
            video.close()
    metrics = score_trajectory(states, targets, command, v.collision, v.body_contact, rollover)
    metrics["surface_contacts"] = len(v.contacts_seen)
    record = dict(
        state_sha256=sha.hexdigest(),
        metrics=metrics,
        feedback=dict(telemetry=telemetry),
        dynamics=dict(plant=plant, surfaces=surfaces, command=command),
        policy_sha256=hashlib.sha256(raw).hexdigest(),
        backend=dict(
            physics="mujoco-cpu",
            mujoco_version=mujoco.__version__,
            inference="numpy-cpu",
            renderer="osmesa" if render else "none",
            gl_renderer=video.gl_renderer if video else None,
            gl_vendor=video.gl_vendor if video else None,
        ),
    )
    (out / "record.json").write_text(json.dumps(record, sort_keys=True, allow_nan=False))
    # Exact telemetry bytes for operator audit; adapter separately retains delivered images/response.
    (out / "feedback.json").write_text(json.dumps(record["feedback"], sort_keys=True, allow_nan=False))
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--plant-seed", type=int, default=91000)
    parser.add_argument("--episode-seed", type=int, default=92100)
    parser.add_argument("--no-render", action="store_true")
    a = parser.parse_args()
    r = rollout(a.policy, dict(plant_seed=a.plant_seed, episode_seed=a.episode_seed), a.out, not a.no_render)
    print(json.dumps(dict(state_sha256=r["state_sha256"], metrics=r["metrics"])))


if __name__ == "__main__":
    main()
