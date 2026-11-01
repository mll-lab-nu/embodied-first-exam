"""The learned whole-body striking controller (HITTER's interface, Su et al. 2025, arXiv 2508.21043, reproduced in our
MuJoCo stack: olympiad_review/screening/g1_tt_zh.md; trained with PPO on MJX, branch g1-tt checkpoint p1_last, about
113 Delta GPU-h in all): an MLP (512-256-128, elu) at 50 Hz that maps the robot's proprioception and a racket command
to 29 joint position targets, played at its own PD gains through the robot's joint interface (a peer of any player:
the same joint command, the same limits). Pure numpy: the opponent (sim/opponent.py) and the reference player
(lowlevel/reference, the task's solution/skill) run this same file.

    S = Striker(path)                  # the checkpoint (controller/g1tt_striker.npz)
    S.reset()                          # at each point (its last action is part of its observation)
    out = S(state, cmd, t)             # {"q": 29 targets, "kp": 29, "kd": 29} for the next 20 ms

state (the robot's own frame): gyro (pelvis angular velocity, pelvis frame), gravity (pelvis frame), quat (pelvis
orientation, w x y z) or yaw, pelvis (x, y[, z]), q, qd (29, Unitree SDK order). cmd: base [x, y] (the pelvis target),
p (blade centre at the strike), v (blade velocity at the strike), n (face normal), t_strike (time of the strike, the
same clock as t), rest (0: strike, 1: stand ready). The controller's own stance rule for a racket target p is
base_for(p, pelvis_now) (the rule it was trained with: the checkpoint's base_gap and base_dx).
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path

import numpy as np

END_Y = -1.37


def _qrot(q, v):
    w, x, y, z = q
    qv = np.array([x, y, z])
    t = 2.0 * np.cross(qv, v)
    return v + w * t + np.cross(qv, t)


class Striker:
    def __init__(self, path):
        z = np.load(path)
        self.mean, self.var = z["mean"].astype(np.float64), z["var"].astype(np.float64)
        self.W = []
        i = 0
        while f"pi{i}_w" in z:
            self.W.append((z[f"pi{i}_w"].astype(np.float64), z[f"pi{i}_b"].astype(np.float64)))
            i += 1
        self.q0, self.scale = z["q0"].astype(np.float64), z["scale"].astype(np.float64)
        self.kp, self.kd = z["kp"].astype(np.float64), z["kd"].astype(np.float64)
        self.rest_pad = np.asarray(z["rest_pad"], float)
        self.base_gap = float(z["base_gap"])
        self.base_dx = tuple(float(x) for x in z["base_dx"])
        self.sha256 = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        self.reset()

    def reset(self):
        self.last_act = np.zeros(len(self.q0))

    def net(self, obs):
        x = np.clip((obs - self.mean) / np.sqrt(self.var + 1e-6), -10, 10)
        for i, (w, b) in enumerate(self.W):
            x = x @ w + b
            if i < len(self.W) - 1:
                x = np.where(x > 0, x, np.expm1(np.minimum(x, 0)))
        return x

    def obs(self, st, cmd, t_now):
        quat = np.asarray(st["quat"], float)
        fwd = _qrot(quat, np.array([1.0, 0.0, 0.0]))[:2]
        fwd = fwd / (np.linalg.norm(fwd) + 1e-6)
        base = np.asarray(st["pelvis"], float)[:2]
        t_left = np.clip(float(cmd["t_strike"]) - t_now, 0.0, 2.0)
        p_rel = np.asarray(cmd["p"], float) - np.r_[base, 0.0]
        return np.concatenate([np.asarray(st["gyro"], float), np.asarray(st["gravity"], float), fwd,
                               np.asarray(cmd["base"], float) - base, p_rel, np.asarray(cmd["v"], float),
                               np.asarray(cmd["n"], float), [t_left], [float(cmd["rest"])], base,
                               np.asarray(st["q"], float) - self.q0, np.asarray(st["qd"], float), self.last_act])

    def __call__(self, st, cmd, t_now) -> dict:
        a = self.net(self.obs(st, cmd, t_now))
        self.last_act = a
        return {"q": self.q0 + self.scale * np.clip(a, -6, 6), "kp": self.kp, "kd": self.kd}

    # ---------------------------------------------------------------- the commands it was trained with
    def base_for(self, p, base_now):
        """The pelvis target for a racket target p (the training's stance rule): forehand (p not far left of the
        pelvis): the pelvis dx left of p (dx from dx0 for contacts up to d0 over the end line, linearly to dx1 at d1);
        backhand: 2 cm right of p; 0.42 m behind p but at least base_gap behind the end line."""
        fore = p[0] - base_now[0] > -0.12
        dx0, d0, d1, dx1 = self.base_dx
        dx = dx0 + (dx1 - dx0) * min(max((p[1] - END_Y - d0) / (d1 - d0), 0.0), 1.0)
        bx = p[0] - dx if fore else p[0] + 0.02
        by = min(p[1] - 0.42, END_Y - self.base_gap)
        return np.array([bx, by])

    def rest_command(self, base, t_now, lead=0.6):
        """Stand ready with the pelvis at `base`: a strike command at the ready spot with zero blade velocity that stays
        `lead` s ahead (the controller's own rest flag lets the pelvis drift; this keeps it within ~5 cm)."""
        base = np.asarray(base, float)
        pad = self.rest_pad
        return {"base": base, "p": np.r_[base + pad[:2], pad[2]], "v": np.zeros(3), "n": np.array([0.0, 1.0, 0.0]),
                "t_strike": t_now + lead, "rest": 0}
