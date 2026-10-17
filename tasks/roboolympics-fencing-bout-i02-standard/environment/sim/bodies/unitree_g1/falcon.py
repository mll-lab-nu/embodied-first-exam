"""FALCON's walking policy for the G1 (optional; body.toml [walk.falcon]): a whole-body-trained walking and balance
policy that a sport may choose instead of Unitree's legs-only policy (body.py WalkPolicy, the default):

    rig = B.rig(model, prefix, hand="paddle", walker="falcon")        # the arm actor's wrist residual on (below)
    rig = B.rig(model, prefix, hand="paddle", walker="falcon_legs")   # FALCON drives the legs only (below)

Source: LeCAR-Lab/FALCON (MIT, Copyright (c) 2025 Yuanhang Zhang; policy/LICENSE.falcon), the released policy
sim2real/models/falcon/g1_29dof.onnx; Y. Zhang et al., "FALCON: Learning Force-Adaptive Humanoid Loco-Manipulation",
arXiv:2505.06776. Trained in IsaacGym on the 29-DOF G1 (PD at 200 Hz, policy at 50 Hz) with upper-body motions
replayed on the arms and external forces on the hands (x, y within +-40 N, z within -50..5 N). policy/falcon_g1_29dof.npz holds the ONNX graph's weights
unchanged (float32, evaluated in float64; tools/export_falcon.py) and a parity fixture: observations with the outputs
onnxruntime gave for them (parity() checks this port against them).

The network: two MLPs on the same input, 575 -> 512 -> 256 -> 128 (ELU) -> 15 (legs + waist) and -> 14 (arms). The
observation is the last 5 frames (oldest first) of 115 numbers, its terms sorted by name as FALCON's deployment code
(sim2real/rl_policy, config/g1/g1_29dof_falcon.yaml) builds them:
    [0:29]    last action (clipped to +-100)          [29:32]   pelvis angular velocity (pelvis frame) x 0.25
    [32]      yaw-rate command                        [33]      base height command (m) x 2
    [34:36]   vx, vy command (m/s, robot frame)       [36]      stepping flag (1 stepping, 0 standing)
    [37:40]   waist yaw, roll, pitch command (rad)    [40:69]   q - default (29 joints, Unitree's motor order)
    [69:98]   joint speeds x 0.05                     [98:101]  gravity (0, 0, -1) in the pelvis frame
    [101:115] arm joint targets (rad; left arm 7, right arm 7)
Targets: default + 0.25 x action. On the rig (body.py G1Rig) and under the arbiter (bodies/control/arbiter.py) the
legs follow FALCON's 12 leg targets on its PD gains (body.toml [walk.falcon] kp, kd); the waist and the arms stay the
sport's (the rig's u, the arbiter's plans or holds): FALCON gets the arm targets and the waist's yaw as its commands
(roll and pitch go in as 0: training never commanded them, their input weights are untrained), its waist targets are
not used, and of its arm actor's output (a residual that FALCON adds to the arm targets) only the wrists' part is
kept, clipped to wrist_residual_max_rad (without it that output runs away within seconds and the standing robot slides
off; measured on this model).

walker="falcon_legs" (Falcon(decl, arm_actor=False)): the arm actor's output is not applied at all and its part of the
last action in the observation is 0 (as if the arms tracked their targets perfectly), no wrist residual: the arms
are wholly the sport's (the rig's servo, the arbiter's plans and holds). This is how basketball's low level (PR #58,
sports/basketball3x3/falcon.py) and the fencing study (docs/screening/fencing) use FALCON. Without the residual but
with the unapplied arm output fed back the standing robot shuffles away (2.5 m in 5 s, PR #58); with it zeroed it
stands and walks (conformance 3b: 10 s at rest with the paddle 7.3 cm, "falcon" 1.4 cm; on guard with an epee 0.08 m
and 2 deg, "falcon" 0.03 m and 10 deg; footwork at the joystick cap 0.77 m/s forward, 0.86 back, no fall in 34
footwork and disturbance runs), and the arms follow their plans undisturbed: on the same 7 reachable targets a re-planned arm
thrust comes within 0.4-0.8 cm (median), 1.0-2.2 cm with "falcon", though "falcon" is closer at the planned end
time (4.4 against 5.7-6.6 cm; fencing F0, docs/screening/fencing.md). Its waist output is not used either way (the
waist is the sport's).

As in its training: a walking speed |(vx, vy)| below 0.2 m/s is 0; here a yaw rate below 0.2 rad/s with no speed is 0
too, then the robot stands (stepping flag 0). Its yaw-rate input was a heading controller there, 0.5 (heading target -
heading) clipped to +-1, so here the yaw-rate command turns a heading target and the input is the command plus that
feedback (the robot keeps its heading when walking straight), clipped to the training range; base height 0.75 m.
FALCON saw a waist command (yaw within +-1 rad) only when standing: a sport that turns the waist while walking is
outside its training. Deterministic: plain float64 numpy.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
N_LOWER, N_ARM, N_FRAME = 15, 14, 115


def mlp(layers, x):
    """An actor: Gemm + ELU per hidden layer, a linear output."""
    for k, (w, b) in enumerate(layers):
        x = w @ x + b
        if k < len(layers) - 1:
            x = np.where(x > 0, x, np.expm1(np.minimum(x, 0.0)))
    return x


def gravity_in(quat):
    """(0, 0, -1) in the frame of the quaternion (w, x, y, z)."""
    w, x, y, z = quat
    return np.array([2 * (-z * x + w * y), -2 * (z * y + w * x), 1 - 2 * (w * w + z * z)])


def heading_of(quat):
    """The yaw (rad) of the quaternion (w, x, y, z)."""
    w, x, y, z = quat
    return math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))


class Falcon:
    """FALCON for one robot: the observation history, the last action, the heading target; step() every 20 ms.
    For the rig like body.py WalkPolicy (default: the legs' stance, reset, state); its step() sees more."""

    WRISTS = [4, 5, 6, 11, 12, 13]  # of the 14 arm joints (left, right): the wrists' roll, pitch, yaw

    def __init__(self, decl, arm_actor=True):
        F = decl["walk"]["falcon"]
        self.arm_actor = bool(arm_actor)  # False: walker "falcon_legs" (no residual, its arm output fed back as 0)
        z = np.load(HERE / F["weights"])
        self.lower, self.upper = (
            [(z[f"{a}_w{k}"].astype(float), z[f"{a}_b{k}"].astype(float)) for k in range(4)] for a in ("lower", "upper")
        )
        self.fixture = z["parity_obs"], z["parity_action"]
        self.default_all = np.array(F["default_angles"], float)  # 29 joints, Unitree's motor order
        self.default = self.default_all[:12]  # the legs' stance (as WalkPolicy.default)
        self.kp, self.kd = np.array(F["kp"], float), np.array(F["kd"], float)  # the legs' PD (12)
        self.scale, self.clip = float(F["action_scale"]), float(F["action_clip"])
        self.history_len = int(F["history"])
        S = F["obs_scales"]
        self.s_ang, self.s_vel, self.s_height = S["ang_vel"], S["dof_vel"], S["base_height"]
        self.height = float(F["base_height_m"])
        self.cmd_max = np.array(F["command_max"], float)
        self.speed_min, self.turn_min = float(F["speed_min_m_s"]), float(F["turn_min_rad_s"])
        self.k_heading, self.heading_err_max = float(F["heading_gain"]), float(F["heading_error_max_rad"])
        self.dt = 1.0 / float(F["rate_hz"])
        self.wrist_max = float(F["wrist_residual_max_rad"])
        self.reset()

    def reset(self):
        self.action = np.zeros(N_LOWER + N_ARM)
        self.history = np.zeros(self.history_len * N_FRAME)
        self.heading = None  # the heading target: taken from the robot when it starts stepping
        self.targets = self.default_all[:N_LOWER].copy()

    def command(self, cmd):
        """The walking command as FALCON was trained on it: clipped to its range, small speeds and turns zeroed."""
        c = np.clip(np.asarray(cmd, float), -self.cmd_max, self.cmd_max)
        if math.hypot(c[0], c[1]) < self.speed_min:
            c[0:2] = 0.0
            if abs(c[2]) < self.turn_min:
                c[2] = 0.0
        return c

    def frame(self, quat, gyro, q, dq, cmd, arms, waist_yaw):
        """One observation frame (115) and the next heading target."""
        c = self.command(cmd)
        stepping = bool(np.any(c != 0.0))
        yaw = heading_of(quat)
        wz = 0.0
        if stepping:
            ref = yaw if self.heading is None else self.heading + c[2] * self.dt
            err = (ref - yaw + math.pi) % (2 * math.pi) - math.pi
            err = min(max(err, -self.heading_err_max), self.heading_err_max)
            wz = min(max(c[2] + self.k_heading * err, -self.cmd_max[2]), self.cmd_max[2])
            heading = yaw + err
        else:
            heading = None
        f = np.empty(N_FRAME)
        f[0:29] = self.action
        f[29:32] = np.asarray(gyro, float) * self.s_ang
        f[32] = wz
        f[33] = self.height * self.s_height
        f[34:36] = c[0:2]
        f[36] = float(stepping)
        f[37:40] = (waist_yaw, 0.0, 0.0)  # yaw, roll, pitch
        f[40:69] = np.asarray(q, float) - self.default_all
        f[69:98] = np.asarray(dq, float) * self.s_vel
        f[98:101] = gravity_in(quat)
        f[101:115] = arms
        return f, heading

    def forward(self, obs):
        """The two actors on an observation (575): the action (29: legs + waist, arms), clipped as in deployment."""
        return np.clip(np.r_[mlp(self.lower, obs), mlp(self.upper, obs)], -self.clip, self.clip)

    def step(self, quat, gyro, q, dq, cmd, arms, waist_yaw):
        """One policy tick. quat (w, x, y, z) and gyro (pelvis frame) of the pelvis; q, dq: the 29 joints in Unitree's
        motor order (legs, waist yaw / roll / pitch, left arm, right arm); cmd: vx, vy, wz (robot frame); arms: the 14
        arm targets (left, right); waist_yaw: the waist's yaw command. Returns the 15 leg + waist targets."""
        f, self.heading = self.frame(quat, gyro, q, dq, cmd, arms, waist_yaw)
        self.history = np.r_[self.history[N_FRAME:], f]
        self.action = self.forward(self.history)
        if not self.arm_actor:                # falcon_legs: the arm actor's output is never applied, so it is not fed back
            self.action[N_LOWER:] = 0.0
        self.targets = self.default_all[:N_LOWER] + self.scale * self.action[:N_LOWER]
        return self.targets

    def wrist_offsets(self):
        """The arm actor's residual on the six wrist joints (rad), clipped: added to their targets (0 for falcon_legs)."""
        if not self.arm_actor:
            return np.zeros(len(self.WRISTS))
        return np.clip(self.scale * self.action[N_LOWER:][self.WRISTS], -self.wrist_max, self.wrist_max)

    def wrist_torque(self, kp):
        """The residual as extra PD torque on the 14 arm joints (left, right) at their gains kp: kp x wrist_offsets()
        on the wrists, 0 elsewhere (= the wrists' targets moved by the offsets). The rig and the arbiter add it while
        FALCON has the legs."""
        t = np.zeros(N_ARM)
        t[self.WRISTS] = np.asarray(kp, float)[self.WRISTS] * self.wrist_offsets()
        return t

    def state(self):
        """The policy's memory (last action, history, heading target): for hashing and copying."""
        return np.r_[self.action, self.history, self.heading is not None, self.heading or 0.0]

    def parity(self):
        """max |this port - onnxruntime| over the fixture stored with the weights (tools/export_falcon.py)."""
        obs, ref = self.fixture
        return float(max(np.max(np.abs(self.forward(o.astype(float)) - r)) for o, r in zip(obs, ref)))
