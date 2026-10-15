"""Authoring helpers: wrist-stage rotations and fingertip inverse kinematics on a scratch copy of the model.

Used only by the authoring controller (tools/author.py); never by the task runtime or the graders.
"""

from __future__ import annotations

import mujoco
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

TIPS_BY_HAND = {
    "sharpa": {
        "thumb": "right_thumb_fingertip_collision",
        "index": "right_index_fingertip_collision",
        "middle": "right_middle_fingertip_collision",
        "ring": "right_ring_fingertip_collision",
        "pinky": "right_pinky_fingertip_collision",
    },
    "wuji": {
        "thumb": "r_wuji_r_thumb_tip_sensor_frame_collision1",
        "index": "r_wuji_r_index_finger_tip_sensor_frame_collision1",
        "middle": "r_wuji_r_middle_finger_tip_sensor_frame_collision1",
        "ring": "r_wuji_r_ring_finger_tip_sensor_frame_collision1",
        "pinky": "r_wuji_r_pinky_tip_sensor_frame_collision1",
    },
}
# Actuator index ranges per hand: 0..5 wrist, then the fingers in native order.
SLICES_BY_HAND = {
    "sharpa": {"thumb": range(6, 11), "index": range(11, 15), "middle": range(15, 19), "ring": range(19, 23),
               "pinky": range(23, 28)},
    "wuji": {"thumb": range(6, 10), "index": range(10, 14), "middle": range(14, 18), "ring": range(18, 22),
             "pinky": range(22, 26)},
}
TIPS = TIPS_BY_HAND["sharpa"]
FINGER_SLICES = SLICES_BY_HAND["sharpa"]


def stage_rotation(angles):
    return Rotation.from_euler("XYZ", angles).as_matrix()


def stage_angles(matrix, near=None, limit=3.14):
    """Serial XYZ wrist angles for ``matrix`` within the joint range; the solution closest to ``near``."""
    a = Rotation.from_matrix(matrix).as_euler("XYZ")
    branches = [a, np.array([a[0] + np.pi, np.pi - a[1], a[2] + np.pi])]
    cands = []
    for b in branches:
        b = (b + np.pi) % (2 * np.pi) - np.pi
        for k0 in (-1, 0, 1):
            for k1 in (-1, 0, 1):
                for k2 in (-1, 0, 1):
                    c = b + 2 * np.pi * np.array([k0, k1, k2])
                    if np.all(np.abs(c) <= limit):
                        cands.append(c)
    if not cands:
        raise ValueError("orientation outside the wrist-stage range")
    if near is None:
        return min(cands, key=lambda c: np.abs(c).sum())
    return min(cands, key=lambda c: np.abs(c - near).sum())


def hand_frame(fingers, palm):
    """Stage rotation whose hand points its fingers along ``fingers`` with the palm normal along ``palm``."""
    f = np.asarray(fingers, float)
    f /= np.linalg.norm(f)
    n = np.asarray(palm, float)
    n = n - (n @ f) * f
    n /= np.linalg.norm(n)
    # stage x = fingers, stage z = palm normal, stage y = z cross x
    return np.column_stack([f, np.cross(n, f), n])


class Kinematics:
    """Forward/inverse kinematics of the wrist stage + fingers on a scratch MjData of ``session.model``."""

    def __init__(self, session):
        self.s = session
        self.m = session.model
        self.d = mujoco.MjData(self.m)
        self.qadr = session.qadr
        self.lo, self.hi = self.m.actuator_ctrlrange.T.copy()
        self.tips = TIPS_BY_HAND[session.hand]
        self.slices = SLICES_BY_HAND[session.hand]
        self.tip_ids = {k: self.m.geom(v).id for k, v in self.tips.items()}
        self.hand_geoms = [g for g in range(self.m.ngeom) if session.checker.hand_geom[g] and self.m.geom_contype[g]]

    def fk(self, q, base_qpos=None):
        self.d.qpos[:] = self.s.data.qpos if base_qpos is None else base_qpos
        self.d.qpos[self.qadr] = q
        mujoco.mj_kinematics(self.m, self.d)
        mujoco.mj_collision(self.m, self.d) if False else None
        return {k: self.d.geom_xpos[g].copy() for k, g in self.tip_ids.items()}

    def tip_offset(self, q, tip):
        """Fingertip position in the wrist-stage frame (constant while the fingers keep their targets)."""
        self.fk(q)
        w = self.d.body("wrist_stage")
        return w.xmat.reshape(3, 3).T @ (self.d.geom_xpos[self.tip_ids[tip]] - w.xpos)

    def wrist_for_tip(self, q, tip, point, rotation):
        """Wrist translation targets that put ``tip`` at ``point`` with the stage at ``rotation`` (fingers as in q)."""
        q = np.array(q, float)
        q[3:6] = stage_angles(rotation, q[3:6])
        off = self.tip_offset(q, tip)
        origin = np.asarray(self.s.config["wrist_stage"]["origin"], float)
        q[:3] = point - rotation @ off - origin
        return q

    def solve(self, q0, targets, variables, avoid=(), weights=None, reg=0.01, margin=0.002, max_nfev=300,
              base_qpos=None, rotation=None):
        """Least squares on actuator targets ``variables`` so each named tip reaches its world target.

        ``avoid``: task geom ids the hand collision geoms must stay ``margin`` away from. ``rotation``: optional
        fixed stage rotation (variables then should exclude 3..5).
        """
        q = np.array(q0, float)
        if rotation is not None:
            q[3:6] = stage_angles(rotation, q[3:6])
        var = np.asarray(list(variables))
        init = np.clip(q[var], self.lo[var] + 1e-6, self.hi[var] - 1e-6)
        weights = weights or {}

        def residual(x):
            q[var] = x
            tips = self.fk(q, base_qpos)
            err = []
            for name, target in targets.items():
                err.extend((tips[name] - target) * 100 * weights.get(name, 1.0))
            for g in self.hand_geoms:
                for a in avoid:
                    dist = mujoco.mj_geomDistance(self.m, self.d, g, a, 0.02, None)
                    err.append(min(0.0, dist - margin) * 300)
            err.extend((x - init) * reg)
            return np.asarray(err)

        fit = least_squares(residual, init, bounds=(self.lo[var] + 1e-8, self.hi[var] - 1e-8), max_nfev=max_nfev)
        q[var] = fit.x
        residual(fit.x)
        return q, fit.cost
