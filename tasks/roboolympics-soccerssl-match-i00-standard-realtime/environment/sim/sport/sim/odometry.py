"""The onboard perception mode's internal sensors (formats *_onboard): wheel odometry (4 omni wheels with encoders)
and a yaw gyro, with drift. Taken unchanged in its model and numbers from the onboard line's prototype
(docs/screening/soccer_ssl/onboard/sensors.py, report olympiad_review/screening/soccer_ssl_onboard_zh.md §1.3);
sim/world.py runs one per robot when the world is built with onboard=True, its random numbers from a core.rng stream
per robot ("odometry:<team><number>").

Model, per control step of dt = 10 ms (the world's step; the real loops run at 1 kHz, the error terms below are
per-step equivalents):
  wheels   The robot's true body-frame velocity (vx, vy, w) maps to the four wheel speeds through the omni-wheel
           kinematics (wheel angles, radius, centre distance of PARAMS). The encoders count the wheel's rotation:
             - each wheel's radius is off by a fixed factor drawn once per robot (tyre tolerance and wear);
             - slip: while the base pushes against something or is pushed (the motor controller's setpoint and
               the true motion disagree by more than SLIP_ON m/s), the wheels turn at the setpoint's speed, not at
               the body's: the encoders report the commanded motion (the robot "thinks" it moves while blocked, and
               misses a push). Otherwise a small random slip proportional to the wheel speed and to the
               acceleration (a traction-limited omni wheel slips more when the base accelerates hard);
             - quantisation to whole encoder ticks per step.
           The four counts are turned back into (vx, vy, w) by least squares (as the robot's firmware does) and
           integrated in the odometry frame.
  gyro     rate = (1 + scale error) * true rate + bias + white noise; the bias is a constant residual left after
           the at-rest calibration plus a random walk. The heading of the odometry is the integrated gyro (SSL
           robots fuse the gyro for the heading: the wheel-derived rotation slips most).
The odometry starts at the pose it is given (the told kick-off spot) or at (0, 0, 0)."""

from __future__ import annotations

import math

import numpy as np

PARAMS = dict(
    # four omni wheels of the TIGERs v2020 robot (2020 TIGERs ETDP Table 1, sec. 2): Nanotec DF45 direct drive,
    # 62 mm wheels, shafts at 31 deg (front) and 45 deg (rear) to the x axis -> wheel positions at +-31 and +-135 deg
    wheel_pos_deg=(31.0, 135.0, 225.0, 329.0),
    wheel_radius=0.031,  # m (62 mm wheels, TIGERs v2020)
    wheel_dist=0.080,  # m, centre to wheel contact (ESTIMATE: inside the 89 mm radius)
    ticks_per_rev=23040,  # encoder counts per wheel revolution (TIGERs v2020: iC-PX2604, 23040 ppr)
    radius_err_sd=0.01,  # per wheel, fixed per robot (ESTIMATE, 1 %: tyre tolerance and wear)
    slip_sd=0.02,  # random slip per 10 ms step, fraction of the wheel speed (ESTIMATE)
    slip_acc_sd=0.01,  # extra slip per m/s^2 of base acceleration (ESTIMATE; KIKS 2022/2024 ETDP: slip
    # during acceleration, encoder-only x velocity "went around in a circle")
    slip_on=0.15,  # m/s: setpoint vs true speed beyond which the wheels follow the setpoint (ESTIMATE)
    # yaw gyro: TDK ICM-42688-P class (KIKS 2022 ETDP; datasheet: noise 0.0028 deg/s/sqrt(Hz), scale tolerance
    # +-0.5 %, offset drift +-0.005 deg/s/degC); residual bias after the at-rest calibration: ZJUNlict 2020 ETDP
    # sec. 3.2 measured < 0.5 deg in 5 min standing (0.0017 deg/s); we take 0.01 deg/s (a few degC of warming)
    gyro_bias_sd=math.radians(0.01),  # rad/s
    gyro_bias_rw=math.radians(0.001),  # rad/s / sqrt(s) (ESTIMATE)
    gyro_noise_density=math.radians(0.0028),  # rad/s / sqrt(Hz)
    gyro_scale_sd=0.005,  # scale factor error (datasheet tolerance, uncalibrated)
    gyro_rate=1000.0,  # Hz
)


def wheel_matrix(P=PARAMS):
    """(4 x 3): wheel rim speed (m/s) from body (vx, vy, w)."""
    rows = []
    for a in P["wheel_pos_deg"]:
        t = math.radians(a)
        rows.append((-math.sin(t), math.cos(t), P["wheel_dist"]))
    return np.array(rows)


class Odometry:
    """One robot's wheel odometry and gyro. step(true body velocity, setpoint body velocity, dt) -> None; .pose is
    the odometry pose (x, y, yaw) in the odometry frame; .gyro_yaw the integrated gyro."""

    def __init__(self, rng, pose0=(0.0, 0.0, 0.0), P=None, scale=1.0):
        P = dict(PARAMS, **(P or {}))
        self.P, self.rng = P, rng
        # scale: one knob for "how bad" (multiplies every error term) for the sensitivity runs
        self.s = float(scale)
        self.J = wheel_matrix(P)
        self.Jinv = np.linalg.pinv(self.J)
        self.rerr = 1.0 + self.s * P["radius_err_sd"] * rng.standard_normal(4)
        self.bias = self.s * P["gyro_bias_sd"] * rng.standard_normal()
        self.gscale = 1.0 + self.s * P["gyro_scale_sd"] * rng.standard_normal()
        self.pose = np.array(pose0, float)
        self.gyro_yaw = float(pose0[2])
        self.tick_m = 2 * math.pi * P["wheel_radius"] / P["ticks_per_rev"]
        self.resid = np.zeros(4)
        self.v_prev = np.zeros(3)
        self.slipping = False

    def step(self, v_body, v_sp_body, dt):
        P, rng, s = self.P, self.rng, self.s
        v = np.asarray(v_body, float)
        vsp = np.asarray(v_sp_body, float)
        acc = float(np.hypot(*(v[:2] - self.v_prev[:2]))) / dt
        self.v_prev = v
        self.slipping = bool(np.hypot(*(vsp[:2] - v[:2])) > P["slip_on"] or abs(vsp[2] - v[2]) > 3.0)
        vw = self.J @ (vsp if self.slipping and s > 0 else v)  # the wheels' rim speeds
        sd = s * (P["slip_sd"] + P["slip_acc_sd"] * min(acc, 10.0))
        vw = vw * (1.0 + sd * rng.standard_normal(4))
        # the encoders count the wheel's angle: rim distance / (true radius) -> what firmware thinks with the
        # nominal radius is off by the radius error
        dist = vw * dt / self.rerr + self.resid
        ticks = np.round(dist / self.tick_m)
        self.resid = dist - ticks * self.tick_m
        vb = self.Jinv @ (ticks * self.tick_m / dt)
        # gyro
        n = s * P["gyro_noise_density"] * math.sqrt(P["gyro_rate"]) / math.sqrt(P["gyro_rate"] * dt)
        self.bias += s * P["gyro_bias_rw"] * math.sqrt(dt) * rng.standard_normal()
        rate = self.gscale * v[2] + self.bias + n * rng.standard_normal()
        yaw_mid = self.gyro_yaw + 0.5 * rate * dt
        self.gyro_yaw += rate * dt
        c, sn = math.cos(yaw_mid), math.sin(yaw_mid)
        self.pose[0] += (c * vb[0] - sn * vb[1]) * dt
        self.pose[1] += (sn * vb[0] + c * vb[1]) * dt
        self.pose[2] = self.gyro_yaw
        return vb, rate


def body_velocity(vel_world, yaw):
    c, s = math.cos(yaw), math.sin(yaw)
    vx, vy, w = vel_world
    return np.array([c * vx + s * vy, -s * vx + c * vy, w])
