"""The platform's `run`: the G1 running policy of C1801SYQ/g1_running (policy/NOTICE.md; Apache-2.0) in numpy.

One policy step every 20 ms from the robot's own sensors (pelvis gyro and orientation, joint encoders), the walking
command (vx, vy, wz) and its last action; its joint targets go to the robot as a plan of two 10 ms rows for all three
joint groups at the policy's PD gains (the arbiter's `plan`: ranges, speed limits, the motor curves). The same code
serves the simulator side (the high level's skill, track.World) and the low level's API test (its platform row:
lowlevel/evaluator.py) from the observation state, so both are the same implementation.

The command is rate-limited (CMD_RATE per second) as a joystick would be; forward speeds above about 4 m/s make the
robot fall (measured on the athletics G1 with the motor curves: 4.0 m/s holds, 5.1 m/s falls within about 5 s)."""
from __future__ import annotations

import math
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
W = np.load(os.path.join(HERE, "policy", "g1_running.npz"))
MAP = W["map"]                                          # policy index i -> Unitree SDK joint MAP[i]
KP = W["stiffness"].copy()                              # deploy.yaml: SDK order
KD = W["damping"].copy()
DEFAULT = np.zeros(29)
DEFAULT[MAP] = W["default"]                             # deploy.yaml: policy order
ACTION_SCALE = 0.25
RANGES = {"vx": (0.0, 5.0), "vy": (-0.12, 0.12), "wz": (-0.5, 0.5)}   # the policy's command ranges (vx: < its 5.1)
CMD_RATE = np.array([1.5, 0.5, 1.0])                    # command change per second (m/s, m/s, rad/s)
DT = 0.02


def _elu(x):
    return np.where(x > 0, x, np.expm1(np.minimum(x, 0.0)))


def actor(obs: np.ndarray) -> np.ndarray:
    h = _elu(W["actor_0_weight"] @ obs + W["actor_0_bias"])
    h = _elu(W["actor_2_weight"] @ h + W["actor_2_bias"])
    h = _elu(W["actor_4_weight"] @ h + W["actor_4_bias"])
    return W["actor_6_weight"] @ h + W["actor_6_bias"]


assert np.abs(actor(W["test_x"][0]) - W["test_y"][0]).max() < 1e-3, "the numpy port differs from the TorchScript"


def gravity(quat_wxyz) -> np.ndarray:
    """The unit gravity vector in the frame of a body with orientation quat (w, x, y, z)."""
    w, x, y, z = quat_wxyz
    return np.array([2 * (-z * x + w * y), -2 * (z * y + w * x), -(1 - 2 * (x * x + y * y))])


def clip_cmd(vx, vy, wz) -> np.ndarray:
    return np.array([min(max(float(vx), RANGES["vx"][0]), RANGES["vx"][1]),
                     min(max(float(vy), RANGES["vy"][0]), RANGES["vy"][1]),
                     min(max(float(wz), RANGES["wz"][0]), RANGES["wz"][1])])


class RunPolicy:
    """One robot's running policy: its memory is the last action and the rate-limited command."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.last = np.zeros(29)
        self.cmd = np.zeros(3)

    def step(self, quat_wxyz, gyro, q, dq, cmd) -> np.ndarray:
        """One 20 ms policy step -> the 29 joint targets (SDK order, not yet clipped to the ranges)."""
        self.cmd = self.cmd + np.clip(clip_cmd(*cmd) - self.cmd, -CMD_RATE * DT, CMD_RATE * DT)
        q, dq = np.asarray(q, float), np.asarray(dq, float)
        obs = np.concatenate([np.asarray(gyro, float) * 0.2, gravity(quat_wxyz), self.cmd, (q - DEFAULT)[MAP],
                              dq[MAP] * 0.05, self.last])
        act = actor(obs)
        self.last = act
        tgt = DEFAULT.copy()
        tgt[MAP] = DEFAULT[MAP] + ACTION_SCALE * act
        return tgt

    def memory(self):
        return [self.last, self.cmd]


def plan_rows(target, current, lo, hi, speed_step, n=2) -> list:
    """n 10 ms rows from the current targets toward `target`, within the joint ranges and speed limits."""
    tgt = np.clip(np.asarray(target, float), np.asarray(lo) + 1e-6, np.asarray(hi) - 1e-6)
    prev, rows = np.asarray(current, float), []
    for _ in range(n):
        prev = prev + np.clip(tgt - prev, -speed_step, speed_step)
        rows.append(prev.copy())
    return rows


class PlatformRun:
    """`run` from the low level's observation state (the low level's plan interface): what the platform does, as a
    skill object with run(vx, vy, wz, *, state, spec) (lowlevel/evaluator.py's platform row)."""

    def __init__(self):
        self.p = RunPolicy()
        self.last = None                        # the last row it sent: where its next plan starts

    def run(self, vx, vy, wz, *, state=None, spec=None):
        rob = state["robot"]
        lo, hi = (np.array(v, float) for v in zip(*spec["robot"]["joint_range_rad"]))
        step = np.array(spec["robot"]["speed_limit_rad_s"], float) * 0.01 * 0.999
        tgt = self.p.step(rob["imu_pelvis"]["quat_wxyz"], rob["imu_pelvis"]["gyro"], rob["q"], rob["dq"], (vx, vy, wz))
        # in real time the observation is a control step or two old when the plan takes effect: its q_target may be
        # behind the plan under way, so the rows continue from the last row sent (the arbiter's continuity check)
        rows = plan_rows(tgt, rob["q_target"] if self.last is None else self.last, lo, hi, step)
        self.last = rows[-1]
        return {"type": "plan", "groups": ["legs", "waist", "arms"], "q": [[round(float(x), 6) for x in r] for r in rows],
                "kp": [round(float(x), 4) for x in KP], "kd": [round(float(x), 4) for x in KD]}


def yaw_of(quat_wxyz) -> float:
    w, x, y, z = quat_wxyz
    return math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
