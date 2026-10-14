"""Wuji Hand 2.2 controller for essential_cube_layer (authoring only; motor targets only).

The cube rests on the open Wuji palm (neutral reset; index/pinky proximal phalanges touch the base).
The thumb pad presses lightly on the top face of the passive top layer and drags it about the layer axis
(top_turn 0 -> +90 deg -> 0 -> +90 deg) while the other fingers stay at their reset targets.

A separate kinematic MjData solves a small least-squares IK for the four thumb joints so that the lowest
point of the thumb-tip mesh (along the top-face normal) sits on a point of the top face; the live session
only receives 26 actuator targets (6 locked wrist + 20 finger position targets).
"""
from __future__ import annotations

import math

import mujoco
import numpy as np
from scipy.optimize import least_squares

HALF = 0.025
TOP_FACE_Z = HALF * 0.68 + HALF * 0.31  # top face height in the object frame


def rot_z(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])


class ThumbIK:
    def __init__(self, session, finger="thumb", nvert=400):
        self.s = session
        self.m = session.model
        self.d = mujoco.MjData(self.m)
        names = session.actuator_names
        pre = {"thumb": "TH", "index": "FF", "middle": "MF", "ring": "RF", "pinky": "LF"}[finger]
        self.idx = np.array([names.index(f"r_wuji_r_{pre}J{i}") for i in range(4)])
        self.qa = session._act_qpos[self.idx]
        self.dofs = self.m.jnt_dofadr[session._act_jids[self.idx]]
        self.lo, self.hi = self.m.actuator_ctrlrange[self.idx].T
        self.kp = self.m.actuator_gainprm[self.idx, 0]
        self.tip = self.m.geom(f"right_{finger}_fingertip_collision").id
        mid = self.m.geom_dataid[self.tip]
        v = self.m.mesh_vert[self.m.mesh_vertadr[mid]:self.m.mesh_vertadr[mid] + self.m.mesh_vertnum[mid]]
        rng = np.random.default_rng(0)
        self.verts = v[rng.choice(len(v), size=min(nvert, len(v)), replace=False)].astype(float)
        self.others = [g for g in range(self.m.ngeom)
                       if (self.m.geom(g).name or "").startswith(f"right_{finger}_") and g != self.tip
                       and self.m.geom_contype[g] | self.m.geom_conaffinity[g]]
        # the distal phalanx next to the tip may touch the top face; the other phalanges must not
        self.others_top = [g for g in self.others if "distal" not in (self.m.geom(g).name or "")]
        self.base = self.m.geom("task_cube_base").id
        self.gverts = {}
        for g in self.others + [self.tip]:
            md = self.m.geom_dataid[g]
            vv = self.m.mesh_vert[self.m.mesh_vertadr[md]:self.m.mesh_vertadr[md] + self.m.mesh_vertnum[md]]
            self.gverts[g] = vv[rng.choice(len(vv), size=min(nvert, len(vv)), replace=False)].astype(float)
        self.top = self.m.geom("task_cube_top_collision").id
        self.q = session.data.qpos[self.qa].copy()
        # exact clearance: the physics collision pipeline on a model copy whose finger geoms carry a contact margin
        import copy
        self.mc = copy.deepcopy(self.m)
        self.dc = mujoco.MjData(self.mc)
        for g in self.others + [self.tip]:
            self.mc.geom_margin[g] = 0.015
        self.mc.opt.disableflags |= int(mujoco.mjtDisableBit.mjDSBL_FILTERPARENT) * 0

    def clearances(self, q, avoid_base, avoid_top):
        self.dc.qpos[:] = self.d.qpos
        self.dc.qpos[self.qa] = q
        mujoco.mj_kinematics(self.mc, self.dc)
        mujoco.mj_collision(self.mc, self.dc)
        out = []
        oth = set(self.others)
        top_set = set(self.others_top) if avoid_top is True else (oth | {self.tip} if avoid_top == "all" else set())
        base_set = (oth | {self.tip}) if avoid_base else set()
        for i in range(self.dc.ncon):
            c = self.dc.contact[i]
            g1, g2 = int(c.geom1), int(c.geom2)
            for a, b in ((g1, g2), (g2, g1)):
                if (b == self.top and a in top_set) or (b == self.base and a in base_set):
                    out.append(c.dist)
        return out

    def world_verts(self, g):
        R = self.d.geom_xmat[g].reshape(3, 3)
        return self.d.geom_xpos[g] + self.gverts[g] @ R.T

    def box_sdf(self, pts, box):
        R = self.d.geom_xmat[box].reshape(3, 3)
        local = np.abs((pts - self.d.geom_xpos[box]) @ R) - self.m.geom_size[box]
        outside = np.linalg.norm(np.maximum(local, 0), axis=1)
        inside = np.minimum(local.max(axis=1), 0)
        return float(np.min(outside + inside))

    def lowest(self, n):
        R = self.d.geom_xmat[self.tip].reshape(3, 3)
        p = self.d.geom_xpos[self.tip] + self.verts @ R.T
        h = p @ n
        k = np.argmin(h)
        # soft-min for a smoother residual
        w = np.exp(-(h - h[k]) / 0.00015)
        return (p * w[:, None]).sum(0) / w.sum()

    def solve(self, point, normal, pressure=0.0005, clearance=0.001, avoid_base=True, avoid_top=True,
              reg=0.02, seed=None, nfev=40):
        self.d.qpos[:] = self.s.data.qpos
        self.d.qvel[:] = 0
        prev = self.q.copy() if seed is None else np.asarray(seed, float)
        n = np.asarray(normal, float) / np.linalg.norm(normal)
        target = np.asarray(point, float) - n * pressure

        def residual(q):
            self.d.qpos[self.qa] = q
            mujoco.mj_kinematics(self.m, self.d)
            low = self.lowest(n)
            err = low - target
            terms = [300 * err, reg * (q - prev)]
            if avoid_base or avoid_top:
                ds = self.clearances(q, avoid_base, avoid_top)
                terms.append([200 * float(np.sum(np.maximum(clearance - np.array(ds + [1.0]), 0)))])
            return np.concatenate(terms)

        x0 = np.clip(prev, self.lo + 1e-6, self.hi - 1e-6)
        r = least_squares(residual, x0, bounds=(self.lo, self.hi), max_nfev=nfev, diff_step=1e-3,
                          ftol=1e-7, xtol=1e-7, gtol=1e-7)
        self.q = r.x
        return r.x, float(np.linalg.norm(residual(r.x)[:3]) / 300)

    def ctrl(self, q):
        """Position target with gravity feed-forward for the low-gain Wuji servos."""
        self.d.qpos[:] = self.s.data.qpos
        self.d.qpos[self.qa] = q
        self.d.qvel[:] = 0
        mujoco.mj_forward(self.m, self.d)
        c = q + self.d.qfrc_bias[self.dofs] / self.kp
        return np.clip(c, self.lo, self.hi)


def face_point(session, phi, radius):
    """World point and normal on the top face at angle phi (object frame) and radius."""
    body = session.data.body("object")
    R = body.xmat.reshape(3, 3)
    local = rot_z(phi) @ np.array([radius, 0, 0]) + np.array([0, 0, TOP_FACE_Z])
    return body.xpos + R @ local, R[:, 2]
