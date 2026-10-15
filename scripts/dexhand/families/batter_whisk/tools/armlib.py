"""Authoring only: geometry + two-arm IK helpers for the Marvin batter-whisk controller (not shipped)."""

from __future__ import annotations

import math
from pathlib import Path
import sys

import numpy as np
import mujoco

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
for _parent in HERE.parents:
    if (_parent / "shared/arm_ik.py").is_file():
        sys.path.append(str(_parent / "shared"))
        break

import arm_ik  # noqa: E402
import arm_rig  # noqa: E402

# Grip point of the right Wave in its root frame (palm normal +x, thumb +y, fingers +z): where a 25 mm handle axis
# sits in the closed grasp of the wave-2 reset (frozen-grasp analysis: the handle axis passes within 1 cm of it).
GRIP_IN_HAND = np.array([0.0421, 0.0, 0.0669])


def smooth(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * x * (10 + x * (-15 + 6 * x))


def frame(palm, index):
    """Right-hand root rotation with palm normal ~``palm`` (made orthogonal) and thumb/index side ``index``."""
    g = np.asarray(index, float)
    g = g / np.linalg.norm(g)
    b = np.asarray(palm, float)
    b = b - (b @ g) * g
    b = b / np.linalg.norm(b)
    n = np.cross(b, g)
    return np.c_[b, g, n]


def slerp(R0, R1, a):
    q0, q1 = np.zeros(4), np.zeros(4)
    mujoco.mju_mat2Quat(q0, R0.ravel())
    mujoco.mju_mat2Quat(q1, R1.ravel())
    if q0 @ q1 < 0:
        q1 = -q1
    dot = min(1.0, float(q0 @ q1))
    th = math.acos(dot)
    if th < 1e-6:
        q = q0
    else:
        q = (math.sin((1 - a) * th) * q0 + math.sin(a * th) * q1) / math.sin(th)
    M = np.zeros(9)
    mujoco.mju_quat2Mat(M, q / np.linalg.norm(q))
    return M.reshape(3, 3)


def root_for_grip(grip, R):
    """Hand-root position that puts the grip point at ``grip`` for root rotation ``R``."""
    return np.asarray(grip, float) - R @ GRIP_IN_HAND


class TwoArm:
    """Closed-loop two-arm pose tracking (IK from the measured arm state + joint integral), like arm_ik.track."""

    def __init__(self, session, ki=0.25, bias_limit=0.25, rest=None):
        self.s = session
        m = session.model
        self.lay = arm_rig.layout(m)
        self.ik = {side: arm_ik.ArmIK(m, side) for side in ("left", "right")}
        self.bias = {side: np.zeros(7) for side in ("left", "right")}
        self.prev = {side: np.array(session.data.ctrl[self.lay["arm"][side]], float) for side in ("left", "right")}
        self.ki, self.bias_limit = ki, bias_limit
        self.row = np.array(session.data.ctrl, float)
        self.rows = []
        self.log = []
        self.phases = []

    def mount_pose(self, side):
        d = self.s.data
        b = self.ik[side].body
        return d.xpos[b].copy(), d.xmat[b].reshape(3, 3).copy()

    def command(self, targets, phase=""):
        """targets: {side: {"pos", "R", "fingers"}} for any subset of sides; others keep their last command."""
        m, d = self.s.model, self.s.data
        lo, hi = m.actuator_ctrlrange.T
        errs = {}
        for side, t in targets.items():
            sl = self.lay["arm"][side]
            if t.get("pos") is not None:
                ik = self.ik[side]
                q_meas = d.qpos[ik.qadr].copy()
                q_star, ep, er = ik.solve(np.asarray(t["pos"]), t.get("R"), q0=self.prev[side] - self.bias[side],
                                          qpos=d.qpos)
                self.bias[side] = np.clip(self.bias[side] + self.ki * (q_star - q_meas), -self.bias_limit,
                                          self.bias_limit)
                q_cmd = np.clip(q_star + self.bias[side], lo[sl], hi[sl])
                self.row[sl] = q_cmd
                self.prev[side] = q_cmd
                errs[side] = (ep, er)
            if t.get("fingers") is not None:
                self.row[self.lay["fingers"][side]] = t["fingers"]
        # Rows are authored as float32 values (exactly representable), so a float32 round trip of the archive is
        # lossless; clipping first keeps them inside the control ranges.
        self.row = np.clip(self.row, lo, hi).astype(np.float32).astype(np.float64)
        self.row = np.clip(self.row, lo, hi)
        self.s.step(self.row.copy())
        self.rows.append(self.row.copy())
        self.phases.append(phase)
        self.log.append(errs)
        return self.s.done
