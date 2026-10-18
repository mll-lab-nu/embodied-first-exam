"""Trusted nonlinear orbital/rigid-body dynamics, observation generation and scoring."""

import os

os.environ.setdefault("MUJOCO_GL", "egl")
from dataclasses import dataclass
import subprocess, hashlib
import numpy as np
import mujoco
from .contract import validate

MU = 3.986004418e14
RADIUS = 6971100.0
DT = 0.1
PHYSICS_DT = 0.02
HORIZON = 120.0
GOAL = np.array([0.65, 0.0, 0.0])


def quat_mul(a, b):
    w, x, y, z = a
    v, i, j, k = b
    return np.array(
        [
            w * v - x * i - y * j - z * k,
            w * i + x * v + y * k - z * j,
            w * j - x * k + y * v + z * i,
            w * k + x * j - y * i + z * v,
        ]
    )


def quat_exp(v):
    v = np.asarray(v, dtype=float)
    a = np.linalg.norm(v)
    return np.r_[np.cos(a / 2), v * (0.5 if a < 1e-10 else np.sin(a / 2) / a)]


def quat_log(q):
    q = np.asarray(q) / np.linalg.norm(q)
    if q[0] < 0:
        q = -q
    n = np.linalg.norm(q[1:])
    return 2 * q[1:] if n < 1e-10 else 2 * np.arctan2(n, q[0]) * q[1:] / n


def rotation(q):
    out = np.empty(9)
    mujoco.mju_quat2Mat(out, np.asarray(q))
    return out.reshape(3, 3)


def orbital_accel(r, v, radius=RADIUS):
    """Exact two-body relative acceleration about a circular reference, in LVLH."""
    omega = np.array([0.0, 0.0, np.sqrt(MU / radius**3)])
    absolute = r + np.array([radius, 0.0, 0.0])
    return (
        -MU * absolute / np.linalg.norm(absolute) ** 3
        + np.array([MU / radius**2, 0.0, 0.0])
        - 2 * np.cross(omega, v)
        - np.cross(omega, np.cross(omega, r))
    )


def parameters(seed):
    rng = np.random.default_rng(seed)
    return {
        "mass": float(rng.uniform(8, 13)),
        "inertia": (np.array([0.55, 0.65, 0.5]) * rng.uniform(0.8, 1.2, 3)).tolist(),
        "radius": float(rng.uniform(6871100, 7071100)),
        "force_scale": rng.uniform(0.85, 1.15, 3).tolist(),
        "torque_scale": rng.uniform(0.85, 1.15, 3).tolist(),
        "misalignment": rng.normal(0, 0.025, 3).tolist(),
        "lag": float(rng.uniform(0.08, 0.3)),
        "delay": int(rng.integers(0, 3)),
        "force_bias": rng.uniform(-0.001, 0.001, 3).tolist(),
        "torque_bias": rng.uniform(-0.00015, 0.00015, 3).tolist(),
    }


def xml(p):
    inertia = " ".join(map(str, p["inertia"]))
    return f'''<mujoco model="rendezvous"><option timestep="{PHYSICS_DT}" gravity="0 0 0" integrator="RK4"/><visual><global offwidth="320" offheight="240"/><rgba haze="0 0 0 1"/></visual><worldbody>
    <light pos="4 -5 8" diffuse=".8 .8 .8"/><light pos="-2 3 5" diffuse=".5 .5 .6"/>
    <geom name="station" type="box" pos="-1.2 0 0" size="1 .65 .65" rgba=".65 .7 .78 1"/>
    <geom name="panel_left" type="box" pos="-1.4 2 0" size=".8 1 .035" rgba=".08 .2 .55 1"/>
    <geom name="panel_right" type="box" pos="-1.4 -2 0" size=".8 1 .035" rgba=".08 .2 .55 1"/>
    <geom name="port" type="cylinder" pos="-.13 0 0" size=".28 .08" euler="0 1.57079632679 0" rgba=".2 .85 .7 1"/>
    <site name="capture_center" type="sphere" pos=".65 0 0" size=".045" rgba=".1 1 .6 1"/>
    <body name="chaser" pos="5 0 0"><freejoint/><inertial pos="0 0 0" mass="{p["mass"]}" diaginertia="{inertia}"/>
      <geom name="hull" type="box" size=".32 .22 .22" rgba=".85 .86 .94 1"/>
      <geom name="nose" type="cylinder" pos="-.34 0 0" size=".15 .04" euler="0 1.57079632679 0" rgba=".1 .9 .75 1"/>
      <geom name="orientation_marker" type="box" pos="0 0 .235" size=".2 .08 .015" rgba="1 .5 .15 1"/>
    </body></worldbody></mujoco>'''


class Plant:
    def __init__(self, plant_seed, episode_seed):
        self.params = parameters(plant_seed)
        self.model = mujoco.MjModel.from_xml_string(xml(self.params))
        self.data = mujoco.MjData(self.model)
        self.body = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, "chaser")
        rng = np.random.default_rng(episode_seed)
        self.rng = rng
        self.data.qpos[:3] = [rng.uniform(4, 6), rng.uniform(-0.9, 0.9), rng.uniform(-0.7, 0.7)]
        self.data.qpos[3:7] = quat_exp(rng.uniform(-0.3, 0.3, 3))
        self.data.qvel[:] = rng.normal(0, 0.006, 6)
        self.bias = (
            rng.normal(0, 1, 12) * np.r_[np.full(3, 0.002), np.full(3, 0.0008), np.full(3, 0.002), np.full(3, 0.0007)]
        )
        self.pending = [np.zeros(6) for _ in range(self.params["delay"])]
        self.actuator = np.zeros(6)
        mujoco.mj_forward(self.model, self.data)

    def observation(self):
        d = self.data
        rng = self.rng
        b = self.bias
        p = d.qpos[:3] + b[:3] + rng.normal(0, 0.006, 3)
        v = d.qvel[:3] + b[3:6] + rng.normal(0, 0.002, 3)
        q = quat_mul(d.qpos[3:7], quat_exp(b[6:9] + rng.normal(0, 0.003, 3)))
        w = d.qvel[3:] + b[9:] + rng.normal(0, 0.0015, 3)
        return np.r_[p, v, q / np.linalg.norm(q), w]

    def advance(self, command):
        self.pending.append(np.clip(command, [-0.4] * 3 + [-0.08] * 3, [0.4] * 3 + [0.08] * 3))
        command = self.pending.pop(0)
        p = self.params
        mis = rotation(quat_exp(p["misalignment"]))
        impulse = 0.0
        for _ in range(5):
            self.actuator += (1 - np.exp(-PHYSICS_DT / p["lag"])) * (command - self.actuator)
            d = self.data
            rot = rotation(d.qpos[3:7])
            force_body = mis @ (np.array(p["force_scale"]) * self.actuator[:3]) + p["force_bias"]
            torque_body = np.array(p["torque_scale"]) * self.actuator[3:] + p["torque_bias"]
            omega = rot.T @ np.array([0.0, 0.0, np.sqrt(MU / p["radius"] ** 3)])
            w = d.qvel[3:]
            inertia = np.array(p["inertia"])
            absolute = w + omega
            correction = (
                -np.cross(absolute, inertia * absolute) + np.cross(w, inertia * w) + inertia * np.cross(w, omega)
            )
            force = rot @ force_body + p["mass"] * orbital_accel(d.qpos[:3], d.qvel[:3], p["radius"])
            d.qfrc_applied[:] = 0
            mujoco.mj_applyFT(
                self.model, d, force, rot @ (torque_body + correction), d.xpos[self.body], self.body, d.qfrc_applied
            )
            mujoco.mj_step(self.model, d)
            impulse += np.linalg.norm(force_body) * PHYSICS_DT
            if d.ncon:
                return impulse, True
        return impulse, False


class Controller:
    def __init__(self, config):
        self.config = validate(config)
        self.filtered = None

    def action(self, obs):
        c = self.config
        p, v, q, w = obs[:3], obs[3:6], obs[6:10], obs[10:]
        # Low-pass only measurements; quaternion sign ambiguity handled by logarithm.
        vector = np.r_[p, v, quat_log(q), w]
        a = 1 if c["filter_tau"] == 0 else 1 - np.exp(-DT / c["filter_tau"])
        self.filtered = vector.copy() if self.filtered is None else self.filtered + a * (vector - self.filtered)
        p, v, att, w = np.split(self.filtered, 4)
        rot = rotation(quat_exp(att))
        target = GOAL.copy()
        if c["approach_gate"] and (np.linalg.norm(p[1:]) > 0.12 or np.linalg.norm(att) > 0.08):
            target[0] = max(1.5, p[0])
        speed = min(c["max_speed"], 0.04) if c["approach_gate"] and p[0] < 1.5 else c["max_speed"]
        if c["family"] == "velocity_shaping":
            desired = -speed * np.tanh(c["position_gain"] * (p - target) / speed)
            acceleration = c["velocity_gain"] * (desired - v)
        else:
            acceleration = c["position_gain"] * (target - p) - c["velocity_gain"] * v
        world_force = c["estimated_mass"] * (acceleration - orbital_accel(p, v))
        torque = -c["estimated_inertia"] * (c["attitude_gain"] * att + c["angular_gain"] * w)
        return np.clip(np.r_[rot.T @ world_force, torque], [-0.4] * 3 + [-0.08] * 3, [0.4] * 3 + [0.08] * 3)


@dataclass
class Episode:
    feedback: dict
    metrics: dict
    dynamics: dict
    video: bytes | None


def run_episode(config, plant_seed, episode_seed, render=False):
    plant = Plant(plant_seed, episode_seed)
    controller = Controller(config)
    d = plant.data
    states = []
    telemetry = []
    frames = []
    collision = False
    escape = False
    impulse = 0.0
    dwell = 0
    renderer = None
    if render:
        renderer = mujoco.Renderer(plant.model, height=240, width=320)
        cam = mujoco.MjvCamera()
        cam.lookat[:] = [1.5, 0, 0]
        cam.distance = 11
        cam.azimuth = 125
        cam.elevation = -23
    try:
        for k in range(round(HORIZON / DT)):
            states.append([*d.qpos, *d.qvel])
            obs = plant.observation()
            if k % 5 == 0:
                telemetry.append({"t": round(k * DT, 3), "values": obs.tolist()})
            if renderer is not None and k % 2 == 0:
                renderer.update_scene(d, camera=cam)
                frames.append(renderer.render().copy())
            used, collision = plant.advance(controller.action(obs))
            impulse += used
            escape = bool(not np.isfinite(d.qpos).all() or np.linalg.norm(d.qpos[:3]) > 15)
            pos = float(np.linalg.norm(d.qpos[:3] - GOAL))
            speed = float(np.linalg.norm(d.qvel[:3]))
            angle = float(np.linalg.norm(quat_log(d.qpos[3:7])))
            rate = float(np.linalg.norm(d.qvel[3:]))
            in_bounds = pos < 0.08 and speed < 0.025 and angle < 0.07 and rate < 0.025
            dwell = dwell + DT if in_bounds else 0.0
            if collision or escape:
                break
        success = dwell >= 3 - 1e-8 and not (collision or escape)
        quality = (
            0.45 * np.exp(-pos / 0.2)
            + 0.2 * np.exp(-speed / 0.04)
            + 0.2 * np.exp(-angle / 0.15)
            + 0.1 * np.exp(-rate / 0.05)
            + 0.05 * np.exp(-impulse / 15)
        )
        score = 0.0 if collision or escape else min(float(100 * quality), 100.0 if success else 49.0)
        metrics = {
            "state_sha256": hashlib.sha256(np.asarray(states).tobytes()).hexdigest(),
            "score": score,
            "captured": success,
            "collision": collision,
            "escape": escape,
            "position_error_m": pos,
            "speed_m_s": speed,
            "attitude_error_rad": angle,
            "angular_rate_rad_s": rate,
            "final_dwell_s": dwell,
            "impulse_Ns": float(impulse),
            "duration_s": round(d.time, 3),
        }
    finally:
        if renderer is not None:
            renderer.close()
    video = None
    if frames:
        video = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "-s",
                "320x240",
                "-r",
                "5",
                "-i",
                "pipe:0",
                "-an",
                "-c:v",
                "libx264",
                "-crf",
                "29",
                "-threads",
                "1",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "frag_keyframe+empty_moov",
                "-f",
                "mp4",
                "pipe:1",
            ],
            input=b"".join(f.tobytes() for f in frames),
            capture_output=True,
            check=True,
            timeout=60,
        ).stdout
    return Episode({"telemetry": telemetry}, metrics, plant.params, video)
