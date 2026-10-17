"""Shared pieces of the ikea365 closed-loop reference: the session wrapper that records the EXECUTED rows (data.ctrl after
the joint-speed clamp), true-state measurements (screw vs member_a, screwdriver tip vs screw head, contact forces) and
Jacobian IK on the TCP sites (damped least squares)."""
from __future__ import annotations
import math, os
import numpy as np
import mujoco
import rcb_ikea as R

ARM = {'left': np.arange(0, 7), 'right': np.arange(8, 15)}
GRIP = {'left': 7, 'right': 15}
DEMO = os.environ.get('I365_DEMO', 'refs/ikea365.npz')


def qmul(a, b):
    w, x, y, z = a; W, X, Y, Z = b
    return np.array([w*W-x*X-y*Y-z*Z, w*X+x*W+y*Z-z*Y, w*Y-x*Z+y*W+z*X, w*Z+x*Y-y*X+z*W])


def qconj(q):
    return np.array([q[0], -q[1], -q[2], -q[3]])


def rotvec(q):
    """Rotation vector of a unit quaternion (wxyz)."""
    q = q / np.linalg.norm(q)
    if q[0] < 0: q = -q
    s = np.linalg.norm(q[1:])
    return q[1:] / (s + 1e-300) * 2 * math.atan2(s, q[0])


def demo_rows():
    return R.load_trajectory(DEMO, 16)


class Rig:
    def __init__(self):
        self.s = R.Session('ikea365')
        self.m, self.d = self.s.model, self.s.data
        self.M = self.s.S.mech
        self.ex: list = []                 # executed rows (data.ctrl after the clamp)
        m = self.m
        self.site = {a: m.site(a + '_tcp').id for a in ARM}
        self.dof = {a: np.array([int(m.jnt_dofadr[m.joint(f'{a}_joint{k}').id]) for k in range(1, 8)]) for a in ARM}
        self.qadr = {a: np.array([int(m.jnt_qposadr[m.joint(f'{a}_joint{k}').id]) for k in range(1, 8)]) for a in ARM}
        self.bid = {n: m.body(n).id for n in ('member_a', 'member_b', 'same_screw', 'bowl', 'screwdriver')}
        self.jp = np.zeros((3, m.nv)); self.jr = np.zeros((3, m.nv))

    # ---- stepping / state
    def step(self, row):
        self.s.step(np.asarray(row, dtype=np.float64))
        self.ex.append(self.d.ctrl.copy())

    def get(self):
        st = self.s.get_state(); st['ex'] = list(self.ex); return st

    def set(self, st):
        self.s.set_state(st); self.ex = list(st['ex'])

    @property
    def ctrl(self):
        return self.d.ctrl.copy()

    def q(self, arm):
        return self.d.qpos[self.qadr[arm]].copy()

    # ---- measurements
    def pose(self, b):
        i = self.bid[b]; return self.d.xpos[i].copy(), self.d.xquat[i].copy()

    def fbody(self, a, b):
        m, d = self.m, self.d; n = d.ncon
        if not n: return 0.
        gb = m.geom_bodyid; c = d.contact
        ia = self.bid[a] if isinstance(a, str) else a; ib = self.bid[b] if isinstance(b, str) else b
        x, y = gb[c.geom1[:n]], gb[c.geom2[:n]]
        sel = ((x == ia) & (y == ib)) | ((x == ib) & (y == ia))
        adr = c.efc_address[:n][sel]
        return float(np.abs(d.efc_force[adr[adr >= 0]]).sum())

    def screw(self):
        """gap (m, along member_a z, + = above the seat), lateral (m), tilt (deg), speed of the screw (vs member_a)."""
        M = self.M
        p, q, sp = M.rel('same_screw')
        dl = p - M.screw_rel
        ax = R.np.array([2*(q[1]*q[3]+q[0]*q[2]), 2*(q[2]*q[3]-q[0]*q[1]), 1-2*(q[1]**2+q[2]**2)])
        tilt = math.degrees(math.acos(min(1., abs(ax[2]))))
        return float(dl[2]), float(np.linalg.norm(dl[:2])), tilt, sp

    def tip_offset(self):
        """The screwdriver tip's offset from the screw axis line (world, perpendicular part) and its height above the head
        top (m)."""
        d = self.d; ps = d.xpos[self.bid['screwdriver']]; pw = d.xpos[self.bid['same_screw']]
        Rw = d.xmat[self.bid['same_screw']].reshape(3, 3)
        head = pw + Rw @ np.array([0, 0, 0.01875]); ax = Rw[:, 2]
        v = ps - head; lat = v - np.dot(v, ax) * ax
        return lat, float(np.dot(v, ax))

    # ---- Jacobian IK
    def jac(self, arm):
        mujoco.mj_jacSite(self.m, self.d, self.jp, self.jr, self.site[arm])
        return np.vstack([self.jp[:, self.dof[arm]], self.jr[:, self.dof[arm]]])

    def ik(self, arm, v, w=np.zeros(3), lam=1e-3, joints=7):
        """Joint increments (7) moving the arm's TCP by v (m, world) and rotating it by w (rad, world), damped least
        squares over the first `joints` joints."""
        J = self.jac(arm)[:, :joints]
        x = np.r_[v, w]
        dq = np.zeros(7)
        dq[:joints] = J.T @ np.linalg.solve(J @ J.T + lam ** 2 * np.eye(6), x)
        return dq

    def ik_move(self, arm, dx):
        """Joints 1-6 increments moving the TCP by dx with its orientation kept (first order, plain least squares)."""
        J = self.jac(arm)[:, :6]
        out = np.zeros(7); out[:6] = np.linalg.lstsq(J, np.r_[dx, 0, 0, 0], rcond=None)[0]
        return out
