"""Authoring helpers: forward kinematics on a scratch MjData, wrist orientation solve, smooth execution."""

from __future__ import annotations

import mujoco
import numpy as np
from scipy.optimize import least_squares

HAND_ROOT = "right_hand_C_MC"


def rot(*columns):
    """Rotation matrix from hand axes given in world coordinates: palm normal, thumb side, finger direction."""
    x, y, z = (np.asarray(c, dtype=float) for c in columns)
    return np.c_[x, y, z]


class Rig:
    def __init__(self, session):
        self.s = session
        self.m = session.model
        self.d = mujoco.MjData(self.m)
        self.root = self.m.body(HAND_ROOT).id
        self.qadr = session.qadr
        self.dofs = self.m.jnt_dofadr[self.m.actuator_trnid[:, 0]]

    def fk(self, q):
        self.d.qpos[:] = self.s.data.qpos
        self.d.qpos[self.qadr] = q
        mujoco.mj_kinematics(self.m, self.d)
        return self.d

    def hand_rot(self, q):
        return self.fk(q).xmat[self.root].reshape(3, 3).copy()

    def orient(self, R, q, guess=None):
        q = np.array(q, dtype=float)
        x0 = q[3:6] if guess is None else np.asarray(guess, dtype=float)

        def res(a):
            q[3:6] = a
            return (self.hand_rot(q) - R).ravel()

        best = None
        for start in [x0, x0 + [0.3, 0, 0], x0 + [0, 0.3, 0], x0 + [0, 0, 0.3], np.zeros(3)]:
            fit = least_squares(res, np.clip(start, -3.1399, 3.1399), bounds=(-3.14, 3.14))
            if best is None or fit.cost < best.cost:
                best = fit
        q[3:6] = best.x
        return q, best.cost

    def point(self, q, kind, name, local=(0, 0, 0)):
        d = self.fk(q)
        if kind == "site":
            i = self.m.site(name).id
            return d.site_xpos[i] + d.site_xmat[i].reshape(3, 3) @ np.asarray(local)
        if kind == "geom":
            i = self.m.geom(name).id
            return d.geom_xpos[i] + d.geom_xmat[i].reshape(3, 3) @ np.asarray(local)
        i = self.m.body(name).id
        return d.xpos[i] + d.xmat[i].reshape(3, 3) @ np.asarray(local)

    def place(self, q, kind, name, target, local=(0, 0, 0)):
        """Shift the wrist slides so the named point lands on ``target`` (orientation and fingers unchanged)."""
        q = np.array(q, dtype=float)
        p = self.point(q, kind, name, local)
        q[:3] += np.asarray(target) - p
        return q

    def hand_geoms(self):
        return [g for g in range(self.m.ngeom) if self.s.checker.is_hand[g] and self.m.geom_contype[g]]

    def low_points(self, q, geoms=None):
        """World points sampling each hand collision geom's surface bottom: mesh vertices or primitive extremes."""
        d = self.fk(q)
        pts = []
        for g in geoms or self.hand_geoms():
            R = d.geom_xmat[g].reshape(3, 3)
            c = d.geom_xpos[g]
            t = self.m.geom_type[g]
            size = self.m.geom_size[g]
            if t == mujoco.mjtGeom.mjGEOM_MESH:
                mid = self.m.geom_dataid[g]
                a, n = self.m.mesh_vertadr[mid], self.m.mesh_vertnum[mid]
                pts.append(c + self.m.mesh_vert[a:a + n] @ R.T)
            elif t == mujoco.mjtGeom.mjGEOM_CAPSULE:
                axis = R[:, 2]
                ring = []
                for e in (-1, 1):
                    for ang in np.linspace(0, 2 * np.pi, 16, endpoint=False):
                        v = np.cos(ang) * R[:, 0] + np.sin(ang) * R[:, 1]
                        ring.append(c + e * size[1] * axis + size[0] * v)
                    ring.append(c + e * size[1] * axis - size[0] * np.array([0, 0, 1.0]))
                pts.append(np.asarray(ring))
            elif t == mujoco.mjtGeom.mjGEOM_CYLINDER:
                ring = []
                for e in (-1, 1):
                    for ang in np.linspace(0, 2 * np.pi, 24, endpoint=False):
                        v = np.cos(ang) * R[:, 0] + np.sin(ang) * R[:, 1]
                        ring.append(c + e * size[1] * R[:, 2] + size[0] * v)
                pts.append(np.asarray(ring))
            elif t == mujoco.mjtGeom.mjGEOM_SPHERE:
                pts.append(np.asarray([c - [0, 0, size[0]], c + [size[0], 0, 0], c - [size[0], 0, 0],
                                       c + [0, size[0], 0], c - [0, size[0], 0]]))
            else:
                signs = np.array([[sx, sy, sz] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)], dtype=float)
                pts.append(c + (signs * size[:3]) @ R.T)
        return np.vstack(pts)

    def gap(self, q, other, geoms=None, distmax=0.05):
        """Smallest signed distance between the hand's collision geoms and geom ``other`` (and the closest geom)."""
        d = self.fk(q)
        oid = self.m.geom(other).id if isinstance(other, str) else other
        best = (distmax, None)
        for g in geoms or self.hand_geoms():
            dist = mujoco.mj_geomDistance(self.m, d, g, oid, distmax, None)
            if dist < best[0]:
                best = (dist, self.m.geom(g).name)
        return best

    def extent(self, q, geoms=None):
        """Per hand collision geom: world AABB (min xyz, max xyz) from its local AABB corners."""
        d = self.fk(q)
        out = {}
        signs = np.array([[sx, sy, sz] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)], dtype=float)
        for g in geoms or self.hand_geoms():
            R = d.geom_xmat[g].reshape(3, 3)
            aabb = self.m.geom_aabb[g]
            pts = d.geom_xpos[g] + (aabb[:3] + signs * aabb[3:]) @ R.T
            out[self.m.geom(g).name] = (pts.min(0), pts.max(0))
        return out
