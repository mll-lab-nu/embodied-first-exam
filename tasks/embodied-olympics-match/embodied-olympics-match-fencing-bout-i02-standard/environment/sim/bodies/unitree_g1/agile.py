"""NVIDIA WBC-AGILE's velocity-height walking policy for the G1 (optional; body.toml [walk.agile]): a legs-only walking
and balance policy, trained while the arms and the waist moved, that a sport may choose instead of Unitree's policy
(body.py WalkPolicy, the default) or FALCON (falcon.py):

    rig = B.rig(model, prefix, hand="paddle", walker="agile")

Source: nvidia-isaac/WBC-AGILE (Apache-2.0, Copyright (c) NVIDIA CORPORATION & AFFILIATES; policy/LICENSE.agile), the
released LEAPP bundle agile/data/policy/velocity_height_g1/leapp/Velocity-Height-G1-History-v0 (S9); H. Zhao et al.,
"AGILE: A Comprehensive Workflow for Humanoid Loco-Manipulation Learning", arXiv:2603.20147. Trained with PPO in Isaac
Lab on the 29-DOF G1 (physics 200 Hz, policy 50 Hz), legs only: the waist yaw (within +-15 degrees) and the arms
moved to random targets while it stood, the waist roll and pitch held at 0; while it walked, the arms and the waist
went to their default pose (all 0), so walking with the arms elsewhere (the library's rest pose too) or the waist
turned further is outside its training. policy/agile_g1_velocity_height.npz holds the ONNX graph's weights and
constants unchanged (float32, evaluated in float64; tools/export_agile.py), the joint order of the bundle, and a
parity fixture: graph inputs (with their histories) and the outputs onnxruntime gave for them (parity() checks this
port against them).

The graph builds its observation itself and keeps a 5-frame history of each term, fed back every tick (LEAPP feedback):
each tick the oldest frame is dropped and the new one appended, then the terms' histories (oldest frame first) are
concatenated, 5 x 80 = 400 numbers:
    velocity-height command (vx, vy, wz, height)   4      pelvis angular velocity (pelvis frame)   3
    gravity (0, 0, -1) in the pelvis frame         3      q - default (29 joints, Isaac Lab order) 29
    joint speeds x 0.1                             29     last action, clipped to +-10             12
MLP 400 -> 512 -> 256 -> 128 (ELU) -> 12: the action (Isaac Lab's leg order); targets = default + scale x action,
clipped to +-6 rad. graph() is that computation; step() maps Unitree's motor order to the bundle's by joint name.

On the rig (body.py G1Rig) and under the arbiter (bodies/control/arbiter.py) the legs follow AGILE's 12 targets on its
PD gains (body.toml [walk.agile] kp, kd: the graph's gain outputs); the waist and the arms stay the sport's (the rig's
u, the arbiter's plans or holds). AGILE has no waist or arm output and no residual: it reads all 29 joints' measured
positions and speeds.

The command as in training: clipped to the training ranges (after [limits.walk]); a command (vx, vy, wz) of norm
below 0.1 is 0 (training zeroed such samples); height 0.72 m (training's walking height). The history starts as in
training (Isaac Lab's history buffer: the first frame fills it, the last action is 0) after place(), a kick and an
arbiter hand-back. NVIDIA's MuJoCo runner starts from the bundle's initial values instead: the export run's first frame
after a reset (9 degrees of tilt, randomised legs, a walking command (0.20, 0.16, 0.23) in all five frames). Measured on
this model: an in-place turn below about 0.7 rad/s barely turns (0.35 rad/s turns 0.03-0.05 rad/s after the first
second; walking at 0.2 m/s or faster it turns as commanded), and it stands with the pelvis at 0.67-0.70 m (FALCON
0.74 m). Deterministic: plain float64 numpy.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from .body import ARM, LEGS, TORSO
from .falcon import mlp

HERE = Path(__file__).resolve().parent
UNITREE = LEGS + TORSO + [f"{s}_{a}_joint" for s in ("left", "right") for a in ARM]  # Unitree's motor order (29)
TERMS = ("velocity_height_commands", "base_ang_vel", "projected_gravity", "joint_pos", "joint_vel", "actions")
INPUTS = ("base_velocity", "robot_root_ang_vel_b", "robot_root_quat_w", "robot_joint_pos", "robot_joint_vel")


class Agile:
    """AGILE for one robot: the six term histories and the last action; step() every 20 ms. For the rig like body.py
    WalkPolicy (default: the legs' stance, reset, state); its step() takes falcon.py's arguments."""

    def __init__(self, decl):
        A = decl["walk"]["agile"]
        z = np.load(HERE / A["weights"])
        self.layers = [(z[f"w{k}"].astype(float), z[f"b{k}"].astype(float)) for k in range(4)]
        self.q0, self.dq0 = z["joint_pos_default"].astype(float), z["joint_vel_default"].astype(float)
        self.s_vel, self.act_clip = float(z["joint_vel_scale"]), float(z["action_clip"])
        self.scale, self.offset = z["action_scale"].astype(float), z["action_offset"].astype(float)
        self.t_min, self.t_max = z["target_min"].astype(float), z["target_max"].astype(float)
        self.gravity = z["gravity"].astype(float)
        self.fixture = {k[len("parity_") :]: z[k] for k in z.files if k.startswith("parity_")}
        self.ix = np.array([UNITREE.index(n) for n in z["obs_joints"]])  # Unitree index of each graph joint (29)
        legs = list(z["action_joints"])
        self.out = np.array([legs.index(n) for n in LEGS])  # Unitree leg i <- graph output out[i]
        self.default = self.offset[self.out]  # the legs' stance (as WalkPolicy.default)
        self.kp, self.kd = np.array(A["kp"], float), np.array(A["kd"], float)  # the legs' PD (12)
        self.history_len = int(A["history"])
        self.height = float(A["base_height_m"])
        self.cmd_min, self.cmd_max = np.array(A["command_min"], float), np.array(A["command_max"], float)
        self.cmd_min_norm = float(A["command_min_norm"])
        self.sizes = [4, 3, 3, len(UNITREE), len(UNITREE), len(LEGS)]  # one frame of each term
        self.reset()

    def reset(self):
        self.action = np.zeros(len(LEGS))
        self.hist = tuple(np.zeros((self.history_len, n)) for n in self.sizes)
        self.fresh = True  # the next tick's frame fills the history (Isaac Lab's history buffer after a reset)
        self.targets = self.default.copy()

    def command(self, cmd):
        """The walking command as AGILE was trained on it: clipped to its ranges, a small command zeroed."""
        c = np.clip(np.asarray(cmd, float)[:3], self.cmd_min, self.cmd_max)
        return c if math.sqrt(c @ c) >= self.cmd_min_norm else np.zeros(3)

    def frame(self, cmd4, gyro, quat_xyzw, q, dq, last_action):
        """One frame of the six terms, as the graph computes it (graph's order: Isaac Lab joints, quaternion x, y, z,
        w); gravity by Isaac Lab's quat_apply_inverse: v - w t + xyz x t, t = 2 xyz x v."""
        xyz, w = np.asarray(quat_xyzw[:3], float), float(quat_xyzw[3])
        t = 2.0 * np.cross(xyz, self.gravity)
        grav = self.gravity - w * t + np.cross(xyz, t)
        return (
            np.asarray(cmd4, float),
            np.asarray(gyro, float),
            grav,
            np.asarray(q, float) - self.q0,
            (np.asarray(dq, float) - self.dq0) * self.s_vel,
            np.clip(last_action, -self.act_clip, self.act_clip),
        )

    def graph(self, cmd4, gyro, quat_xyzw, q, dq, last_action, hist):
        """The ONNX graph: the new frame appended to each term's history (the oldest dropped), the network on the
        histories. Returns (targets 12, action 12, histories), the legs in the graph's order."""
        hist = tuple(np.vstack([h[1:], f]) for h, f in zip(hist, self.frame(cmd4, gyro, quat_xyzw, q, dq, last_action)))
        action = mlp(self.layers, np.concatenate([h.ravel() for h in hist]))
        return np.clip(self.offset + self.scale * action, self.t_min, self.t_max), action, hist

    def step(self, quat, gyro, q, dq, cmd, arms=None, waist_yaw=None):
        """One policy tick. quat (w, x, y, z) and gyro (pelvis frame) of the pelvis; q, dq: the 29 joints in Unitree's
        motor order (measured); cmd: vx, vy, wz (robot frame). arms, waist_yaw: not used (falcon.py's arguments).
        Returns the 12 leg targets (Unitree's order)."""
        w, x, y, z = quat
        q, dq = np.asarray(q, float), np.asarray(dq, float)
        inputs = (np.r_[self.command(cmd), self.height], gyro, (x, y, z, w), q[self.ix], dq[self.ix], self.action)
        if self.fresh:
            self.hist = tuple(np.tile(f, (self.history_len, 1)) for f in self.frame(*inputs))
            self.fresh = False
        t, self.action, self.hist = self.graph(*inputs, self.hist)
        self.targets = t[self.out]
        return self.targets

    def state(self):
        """The policy's memory (last action, histories, fresh): for hashing and copying."""
        return np.r_[self.action, np.concatenate([h.ravel() for h in self.hist]), self.fresh]

    def parity(self):
        """max |this port - onnxruntime| over the fixture stored with the weights (tools/export_agile.py): all the
        graph's outputs (targets, action, the six histories)."""
        F = self.fixture
        err = 0.0
        for k in range(len(F["joint_pos"])):
            ins = [F[n][k] for n in INPUTS + ("last_action_in",)] + [tuple(F[f"h_policy_{n}_in"][k] for n in TERMS)]
            t, a, hist = self.graph(*ins)
            ref = [F["joint_pos"][k], F["last_action_out"][k]] + [F[f"h_policy_{n}_out"][k] for n in TERMS]
            err = max(err, max(float(np.max(np.abs(g - r))) for g, r in zip([t, a, *hist], ref)))
        return err
