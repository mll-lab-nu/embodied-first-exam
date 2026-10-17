"""Authoring helpers (not shipped to the task): kinematic pinch IK and smooth target execution for Sharpa."""

from __future__ import annotations

import json

import mujoco
import numpy as np
from scipy.optimize import least_squares

THUMB = list(range(6, 11))
INDEX = list(range(11, 15))
MIDDLE = list(range(15, 19))
RING = list(range(19, 23))
PINKY = list(range(23, 28))


class Ctl:
    def __init__(self, session, log=print):
        self.s = session
        self.m = session.model
        self.scratch = mujoco.MjData(self.m)
        self.target = session.hold_action().copy()
        self.dofs = self.m.jnt_dofadr[self.m.actuator_trnid[:, 0]]
        self.gains = self.m.actuator_gainprm[:, 0]
        self.phases = []
        self.log = log
        m = self.m
        self.hand_geoms = [g for g in range(m.ngeom) if m.geom_contype[g] and session.owner.get(int(m.geom_bodyid[g])) == "hand"]
        self.tip = {f: m.geom(f"right_{f}_fingertip_collision").id for f in ("thumb", "index", "middle", "ring", "pinky")}

    # ------------------------------------------------------------------ kinematics
    def fk(self, q):
        d = self.scratch
        d.qpos[:] = self.s.data.qpos
        d.qpos[self.s.qadr] = q
        mujoco.mj_kinematics(self.m, d)
        return d

    def pinch(self, q0, center, axis, half_width, clearance, fingers=("index",), spread=None, obstacles=(),
              avoid=(), variable=None, lift_min=None, weight_reg=0.012, along=None):
        """Place the thumb tip on +axis side and the finger tips on -axis side of a bar centred at ``center``."""
        m, d = self.m, self.scratch
        q = np.asarray(q0, dtype=float).copy()
        axis = np.asarray(axis, float) / np.linalg.norm(axis)
        variable = np.asarray(variable if variable is not None else [0, 1, 2] + THUMB + INDEX, dtype=int)
        lo, hi = m.actuator_ctrlrange[variable].T.copy()
        initial = q[variable].copy()
        tips = [("thumb", 1.0, np.zeros(3))]
        offsets = spread or {}
        for f in fingers:
            tips.append((f, -1.0, np.asarray(offsets.get(f, (0, 0, 0)), float)))
        tip_ids = {self.tip[f] for f, _, _ in tips}
        others = [g for g in self.hand_geoms if g not in tip_ids]

        def residual(values):
            q[variable] = values
            d.qpos[:] = self.s.data.qpos
            d.qpos[self.s.qadr] = q
            mujoco.mj_kinematics(m, d)
            errors = []
            for f, sign, off in tips:
                gid = self.tip[f]
                ax = d.geom_xmat[gid].reshape(3, 3)[:, 2]
                pad = m.geom_size[gid, 0] + m.geom_size[gid, 1] * abs(ax @ axis)
                target = np.asarray(center, float) + off + sign * axis * (half_width + pad + clearance)
                errors.extend((d.geom_xpos[gid] - target) * 100)
            for gid in others:
                for ob in avoid:
                    dist = mujoco.mj_geomDistance(m, d, gid, ob, 0.02, None)
                    errors.append(min(0, dist - 0.003) * 250)
            for gid in self.hand_geoms:
                for ob in obstacles:
                    dist = mujoco.mj_geomDistance(m, d, gid, ob, 0.02, None)
                    errors.append(min(0, dist - 0.002) * 250)
            errors.extend((values - initial) * weight_reg)
            return np.asarray(errors)

        fit = least_squares(residual, np.clip(initial, lo + 1e-6, hi - 1e-6), bounds=(lo + 1e-8, hi - 1e-8),
                            max_nfev=400)
        residual(fit.x)
        return q.copy(), float(fit.cost)

    # ------------------------------------------------------------------ execution
    def execute(self, target, count, phase, boost=2.0, stop_on_done=True):
        s = self.s
        start = self.target.copy()
        target = np.asarray(target, dtype=float)
        for ratio in np.linspace(0, 1, count + 1)[1:]:
            if s.done and stop_on_done:
                break
            blend = ratio * ratio * (3 - 2 * ratio)
            self.target = start + (target - start) * blend
            action = self.target + s.data.qfrc_bias[self.dofs] / self.gains
            action[6:] += boost * (self.target[6:] - s.data.qpos[s.qadr[6:]])
            action = np.clip(action, *self.m.actuator_ctrlrange.T)
            s.step(action)
            self.phases.append(phase)
        st = s.status()
        self.log(phase, json.dumps({k: st[k] for k in ("stage", "reason", "hand_contact_parts", "seated_interfaces")}),
                 "brace", np.round(st["brace_pos"], 4).tolist(), flush=True)
        return st


def rotate_about(target, origin, R_err, pivot):
    """New wrist targets after applying the world rotation ``R_err`` to the hand about the world point ``pivot``."""
    from scipy.spatial.transform import Rotation as Rot

    out = np.asarray(target, dtype=float).copy()
    R_ws = Rot.from_euler("XYZ", out[3:6]).as_matrix()
    W = np.asarray(origin) + out[0:3]
    W2 = pivot + R_err @ (W - pivot)
    out[3:6] = Rot.from_matrix(R_err @ R_ws).as_euler("XYZ")
    out[0:3] = W2 - origin
    return out


def rotation_between(a, b):
    """Rotation matrix taking unit vector a to unit vector b (shortest arc)."""
    from scipy.spatial.transform import Rotation as Rot

    a = np.asarray(a, float) / np.linalg.norm(a)
    b = np.asarray(b, float) / np.linalg.norm(b)
    axis = np.cross(a, b)
    s = np.linalg.norm(axis)
    if s < 1e-12:
        return np.eye(3)
    angle = np.arctan2(s, a @ b)
    return Rot.from_rotvec(axis / s * angle).as_matrix()
