"""Authoring-only (not shipped): closed-loop Cartesian control of the Marvin arms of a Session, recorded as rows.

Each control the desired hand-mount pose of every driven arm is converted to joint targets by damped least squares
(``arm_ik.ArmIK``, warm-started from the previous command), plus a clipped joint-space integral that removes servo
sag under gravity and contact loads (as ``arm_ik.track``). Fingers take absolute targets. Only the executed rows
form the trajectory; replay.py re-executes them open loop.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation, Slerp


def _arm_ik():
    try:
        import arm_ik

        return arm_ik
    except ModuleNotFoundError:
        path = Path(__file__).resolve().parent.parent.parent.parent / "shared" / "arm_ik.py"
        spec = importlib.util.spec_from_file_location("arm_ik", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules["arm_ik"] = module
        spec.loader.exec_module(module)
        return module


arm_ik = _arm_ik()
arm_rig = arm_ik.arm_rig


def smooth(u):
    u = np.clip(u, 0.0, 1.0)
    return u * u * (3 - 2 * u)


class ArmCtl:
    def __init__(self, session, sides=("left", "right"), ki=0.2, bias_limit=0.25, log=print, null_gain=0.0):
        self.s = session
        m = self.m = session.model
        self.d = session.data
        self.lay = arm_rig.layout(m)
        self.sides = tuple(sides)
        self.ik = {side: arm_ik.ArmIK(m, side) for side in self.sides}
        self.row = np.array(self.d.ctrl, dtype=float)
        self.lo, self.hi = m.actuator_ctrlrange.T
        self.ki, self.bias_limit = ki, bias_limit
        self.null_gain = null_gain  # null-space pull toward mid-range joints (keeps the shoulder off its limits)
        # Start the joint integral at the reset's own offset (its targets carry the gravity feed-forward of the
        # settled reset), so the first commands continue the held state without a sag transient.
        self.bias = {side: np.clip(self.row[self.lay["arm"][side]] - self.d.qpos[self.ik[side].qadr], -bias_limit,
                                   bias_limit) for side in self.sides}
        self.q_cmd = {side: self.row[self.lay["arm"][side]].copy() for side in self.sides}
        self.goal = {side: self.pose(side) for side in self.sides}
        self.rows, self.phases = [], []
        self.log = log
        self.on_step = None

    # ------------------------------------------------------------------ state
    def pose(self, side):
        b = self.ik[side].body
        return self.d.xpos[b].copy(), self.d.xmat[b].reshape(3, 3).copy()

    def fingers(self, side):
        return self.row[self.lay["fingers"][side]].copy()

    # ------------------------------------------------------------------ one control
    def step(self, phase, goals=None, fingers=None):
        """Advance one control. ``goals[side] = (pos, R)`` updates that arm's goal (others keep theirs);
        ``fingers[side]`` sets absolute finger targets."""
        if self.s.done:
            return False
        for side, g in (goals or {}).items():
            self.goal[side] = (np.asarray(g[0], float), np.asarray(g[1], float))
        d = self.d
        for side in self.sides:
            pos, R = self.goal[side]
            ik = self.ik[side]
            q_meas = d.qpos[ik.qadr].copy()
            q_star, _, _ = ik.solve(pos, R, q0=self.q_cmd[side] - self.bias[side], qpos=d.qpos, iters=60,
                                    null_gain=self.null_gain)
            self.bias[side] = np.clip(self.bias[side] + self.ki * (q_star - q_meas), -self.bias_limit,
                                      self.bias_limit)
            sl = self.lay["arm"][side]
            self.q_cmd[side] = np.clip(q_star + self.bias[side], self.lo[sl], self.hi[sl])
            self.row[sl] = self.q_cmd[side]
        for side, f in (fingers or {}).items():
            self.row[self.lay["fingers"][side]] = f
        self.row = np.clip(self.row, self.lo, self.hi)
        self.s.step(self.row.copy())
        self.rows.append(self.row.copy())
        self.phases.append(phase)
        if self.on_step is not None:
            self.on_step(self)
        return not self.s.done

    # ------------------------------------------------------------------ segments
    def move(self, phase, count, goals=None, fingers=None):
        """Smoothstep interpolation of hand goals (position + slerp) and finger targets over ``count`` controls."""
        start = {side: self.goal[side] for side in (goals or {})}
        f0 = {side: self.fingers(side) for side in (fingers or {})}
        slerps = {side: Slerp([0, 1], Rotation.from_matrix([start[side][1], np.asarray(goals[side][1], float)]))
                  for side in (goals or {})}
        for i in range(1, count + 1):
            u = smooth(i / count)
            g = {side: (start[side][0] + (np.asarray(goals[side][0], float) - start[side][0]) * u,
                        slerps[side]([u]).as_matrix()[0]) for side in (goals or {})}
            f = {side: f0[side] + (np.asarray(fingers[side], float) - f0[side]) * u for side in (fingers or {})}
            if not self.step(phase, g, f):
                return False
        return True

    def hold(self, phase, count):
        for _ in range(count):
            if not self.step(phase):
                return False
        return True
