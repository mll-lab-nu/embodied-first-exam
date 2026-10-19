"""Public figure-eight reference and numeric geometric controller, SI/world frame."""

import copy
import math
import numpy as np

try:
    from ..neuralfly_constants import BOUNDS, DEFAULT
except ImportError:  # Task-local public export.
    from neuralfly_constants import BOUNDS, DEFAULT

MASS = 2.53
DT = 0.02
DURATION = 6 * 2 * np.pi


def validate(p):
    if not isinstance(p, dict) or set(p) not in (set(DEFAULT), set(DEFAULT) - {"observer_gain"}):
        raise ValueError("Policy fields")
    p = copy.deepcopy(p)
    p.setdefault("observer_gain", 0.0)
    for k, (a, b) in BOUNDS.items():
        if type(p[k]) not in (int, float) or not math.isfinite(p[k]) or not a <= p[k] <= b:
            raise ValueError("Policy bounds")
    r = p["residual"]
    if not isinstance(r, list) or len(r) != 3 or any(not isinstance(row, list) or len(row) != 7 for row in r):
        raise ValueError("Residual shape")
    if any(type(v) not in (float, int) or not math.isfinite(v) or abs(v) > 20 for row in r for v in row):
        raise ValueError("Residual bounds")
    return p


def target(
    t,
    phase=0.0,
    yaw=0.0,
    center=(0.0, 0.0, 1.8),
    *,
    tilt=0.0,
    amplitude_x=1.25,
    amplitude_z=0.75,
    rate=1.0,
    direction=1,
):
    """World-frame figure eight with exact derivatives; tilt rotates its plane about local x.

    Amplitudes are half extents, rate is rad/s, direction is +1 or -1.
    tilt=0 is vertical; tilt=pi/2 is horizontal. No deployment draws here.
    """
    w = direction * rate
    a = w * t + phase
    c, s = np.cos(yaw), np.sin(yaw)
    ct, st = np.cos(tilt), np.sin(tilt)
    R = np.array([[c, -s * ct, s * st], [s, c * ct, -c * st], [0, st, ct]])
    p = np.array([amplitude_x * np.sin(a), 0, amplitude_z * np.sin(2 * a)])
    v = w * np.array([amplitude_x * np.cos(a), 0, 2 * amplitude_z * np.cos(2 * a)])
    acc = w * w * np.array([-amplitude_x * np.sin(a), 0, -4 * amplitude_z * np.sin(2 * a)])
    return R @ p + center, R @ v, R @ acc


class Controller:
    def __init__(self, p):
        self.p = validate(p)
        self.integral = np.zeros(3)
        self.previous_velocity = None
        self.previous_thrust = MASS * 9.81
        self.thrust_estimate = MASS * 9.81
        self.disturbance = np.zeros(3)

    def action(self, obs):
        p = self.p
        position = np.array(obs["position"])
        velocity = np.array(obs["velocity"])
        goal = np.array(obs["target_position"])
        speed = np.array(obs["target_velocity"])
        acc = np.array(obs["target_acceleration"])
        self.integral = np.clip(self.integral + DT * (goal - position), -2, 2)
        q = np.asarray(obs["quaternion"], dtype=float)
        q /= np.linalg.norm(q)
        if q[0] < 0:
            q = -q
        w, x, y, z = q
        body_z = np.array([2 * (x * z + w * y), 2 * (y * z - w * x), 1 - 2 * (x * x + y * y)])
        # Estimate thrust from our own prior command and a public nominal actuator lag.
        # Neither realized motor thrust nor evaluator forces are observations.
        self.thrust_estimate += (1 - np.exp(-DT / 0.04)) * (self.previous_thrust - self.thrust_estimate)
        if self.previous_velocity is not None and p["observer_gain"] > 0:
            apparent_force = MASS * ((velocity - self.previous_velocity) / DT + [0, 0, 9.81])
            innovation = apparent_force - self.thrust_estimate * body_z
            alpha = 1 - np.exp(-p["observer_gain"] * DT)
            self.disturbance += alpha * (np.clip(innovation, -20, 20) - self.disturbance)
        self.previous_velocity = velocity.copy()
        features = np.r_[1, velocity, q[1:]]
        f = (
            MASS
            * (
                acc
                + p["kp"] * (goal - position)
                + p["kd"] * (speed - velocity)
                + p["ki"] * self.integral
                + [0, 0, 9.81]
            )
            - np.array(p["residual"]) @ features
            - self.disturbance
        )
        # Fixed, public flight envelope: prevent inverted commands during acquisition.
        f[2] = max(f[2], 0.35 * MASS * 9.81)
        horizontal = np.linalg.norm(f[:2])
        limit = f[2] * np.tan(np.deg2rad(50.0))
        if horizontal > limit:
            f[:2] *= limit / horizontal
        f *= min(1.0, MASS * 9.81 * 2.2 / np.linalg.norm(f))
        self.previous_thrust = float(np.clip(f @ body_z, 0, MASS * 9.81 * 2.2))
        return f


def xml():
    return (
        """<mujoco><option timestep=".002" gravity="0 0 -9.81" integrator="RK4"/><visual><global offwidth="640" offheight="480"/><headlight ambient=".6 .6 .6" diffuse=".8 .8 .8"/></visual><worldbody><light pos="0 -3 5"/><geom type="plane" size="8 8 .1" rgba=".35 .38 .4 1"/><site name="goal" size=".055" rgba="1 .6 .1 0"/><body name="drone" pos="0 0 1.8"><freejoint/><inertial pos="0 0 0" mass="2.53" diaginertia=".04 .04 .07"/><geom type="box" size=".12 .08 .05" rgba=".95 .38 .12 1"/><geom type="capsule" fromto="-.195 -.195 0 .195 .195 0" size=".018"/><geom type="capsule" fromto="-.195 .195 0 .195 -.195 0" size=".018"/>"""
        + "".join(
            f'<geom type="cylinder" pos="{x} {y} .025" size=".1397 .008" rgba=".15 .19 .23 .7" contype="0" conaffinity="0"/>'
            for x, y in [(0.195, 0.195), (-0.195, 0.195), (-0.195, -0.195), (0.195, -0.195)]
        )
        + "</body></worldbody></mujoco>"
    )


class Vehicle:
    """Editable nominal rigid-body plant; deployment draws/forces are not defined here."""

    def __init__(self, position, mass_scale=1.0, motor_tau=0.04):
        import mujoco

        self.mj = mujoco
        self.model = mujoco.MjModel.from_xml_string(xml())
        self.data = mujoco.MjData(self.model)
        self.model.body_mass[1] *= mass_scale
        self.model.body_inertia[1] *= mass_scale
        mujoco.mj_setConst(self.model, self.data)
        self.data.qpos[:3] = position
        self.data.qpos[3:7] = [1, 0, 0, 0]
        mujoco.mj_forward(self.model, self.data)
        self.motor_tau = motor_tau
        self.rotor = np.full(4, MASS * 9.81 / 4)
        xy = [(0.195, 0.195), (-0.195, 0.195), (-0.195, -0.195), (0.195, -0.195)]
        self.allocation = np.array([[1] * 4, [y for x, y in xy], [-x for x, y in xy], [0.02, -0.02, 0.02, -0.02]])
        self.saturated_steps = 0

    def observation(self, t, command, rng):
        goal, vel, acc = command
        q = self.data.qpos[3:7] + rng.normal(0, 0.0005, 4)
        q /= np.linalg.norm(q)
        return {
            "t": float(t),
            "position": (self.data.qpos[:3] + rng.normal(0, 0.01, 3)).tolist(),
            "velocity": (self.data.qvel[:3] + rng.normal(0, 0.02, 3)).tolist(),
            "quaternion": q.tolist(),
            "omega": (self.data.qvel[3:] + rng.normal(0, 0.003, 3)).tolist(),
            "target_position": goal.tolist(),
            "target_velocity": vel.tolist(),
            "target_acceleration": acc.tolist(),
        }

    def step(self, force, obs, policy, external_force=None):
        mj, model, data = self.mj, self.model, self.data
        rotation = np.empty(9)
        mj.mju_quat2Mat(rotation, np.array(obs["quaternion"]))
        rotation = rotation.reshape(3, 3)
        z = force / max(np.linalg.norm(force), 1e-9)
        if np.linalg.norm(force) < 1e-9:
            z = np.array([0.0, 0.0, 1.0])
        heading = [1.0, 0.0, 0.0] if abs(z[0]) < 0.95 else [0.0, 1.0, 0.0]
        y = np.cross(z, heading)
        y /= np.linalg.norm(y)
        desired = np.column_stack([np.cross(y, z), y, z])
        error = 0.5 * sum(np.cross(rotation[:, i], desired[:, i]) for i in range(3))
        torque = np.array([0.04, 0.04, 0.07]) * (
            policy["attitude_gain"] * (rotation.T @ error) - policy["rate_gain"] * np.asarray(obs["omega"])
        )
        unconstrained = np.linalg.solve(self.allocation, np.r_[max(0.0, force @ rotation[:, 2]), torque])
        command = np.clip(unconstrained, 0, MASS * 9.81 * 2.2 / 4)
        self.saturated_steps += int(np.any(unconstrained != command))
        contact = False
        for _ in range(round(DT / model.opt.timestep)):
            self.rotor += (1 - np.exp(-model.opt.timestep / self.motor_tau)) * (command - self.rotor)
            wrench = self.allocation @ self.rotor
            rotation = data.xmat[1].reshape(3, 3)
            residual = np.zeros(3) if external_force is None else external_force(data)
            data.qfrc_applied[:] = 0
            mj.mj_applyFT(
                model,
                data,
                rotation @ np.array([0, 0, wrench[0]]) + residual,
                rotation @ wrench[1:],
                data.xpos[1],
                1,
                data.qfrc_applied,
            )
            mj.mj_step(model, data)
            contact |= bool(data.ncon)
        return contact
