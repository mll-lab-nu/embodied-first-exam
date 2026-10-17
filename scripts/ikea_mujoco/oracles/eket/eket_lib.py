"""Shared pieces of the eket closed-loop reference: the session wrapper that records the EXECUTED rows (data.ctrl after
the joint-speed clamp), true-state measurements of the current operation, and a Jacobian servo that steers a held panel
onto its goal pose relative to the top panel."""
from __future__ import annotations
import math, os, sys
import numpy as np
import mujoco
import rcb_ikea as R

ARM = {'left': np.arange(0, 7), 'right': np.arange(8, 15)}
GRIP = {'left': 7, 'right': 15}
DOF = {'left': np.arange(0, 7), 'right': np.arange(9, 16)}      # arm hinge dofs (fingers at 7-8, 16-17)
DEMO = os.environ.get('EKET_DEMO', 'refs/eket.npz')


def qmul(a, b):
    w, x, y, z = a; W, X, Y, Z = b
    return np.array([w*W-x*X-y*Y-z*Z, w*X+x*W+y*Z-z*Y, w*Y-x*Z+y*W+z*X, w*Z+x*Y-y*X+z*W])


def qconj(q):
    return np.array([q[0], -q[1], -q[2], -q[3]])


def demo_rows():
    return np.load(DEMO)['ctrl']


class Rig:
    def __init__(self):
        self.s = R.Session('eket')
        self.m, self.d = self.s.model, self.s.data
        self.ex: list = []                 # executed rows (data.ctrl after the clamp)
        mech = self.s.S.mech
        self.tr = mech.tracker
        self.ops = sys.modules['eket_ops']
        self.site = {a: self.m.site(a + '_tcp').id for a in ARM}
        self.jp = np.zeros((3, self.m.nv)); self.jr = np.zeros((3, self.m.nv))

    # ---- stepping / state
    def step(self, row):
        self.s.step(row)
        self.ex.append(self.d.ctrl.copy())

    def get(self):
        st = self.s.get_state(); st['ex'] = list(self.ex); return st

    def set(self, st):
        self.s.set_state(st); self.ex = list(st['ex'])

    @property
    def ctrl(self):
        return self.d.ctrl.copy()

    # ---- measurements
    def cur(self):
        return self.tr.current()

    def spec(self, name=None):
        return self.ops.operation_spec(name or self.cur(), self.tr.canon)

    def rel(self, role):
        return self.tr.meas.relative(role)

    def err(self, name=None):
        """goal error (top frame, m), rotation vector of the part in the top frame (rad), rel speed, ang speed."""
        sp = self.spec(name)
        p, q, v, w = self.rel(sp['role'])
        q = q / np.linalg.norm(q)
        if q[0] < 0: q = -q
        ang = 2 * math.atan2(np.linalg.norm(q[1:]), q[0])
        r = q[1:] / (np.linalg.norm(q[1:]) + 1e-300) * ang
        return sp['goal'] - p, r, np.linalg.norm(v), w

    def jac(self, arm):
        mujoco.mj_jacSite(self.m, self.d, self.jp, self.jr, self.site[arm])
        return np.vstack([self.jp[:, DOF[arm]], self.jr[:, DOF[arm]]])

    def servo_dq(self, arm, role, kp=0.05, kr=0.05, lam=1e-3, cap=None, ep=None, r=None):
        """Joint target increment of `arm` that moves the held `role` panel by kp x its goal error and rotates it by
        kr x its angle error (relative to the top), through the TCP twist and a damped least-squares Jacobian."""
        m, d = self.m, self.d
        if ep is None:
            ep, r, _, _ = self.err()
        ia = m.body('top').id; ib = m.body(role).id
        Ra = d.xmat[ia].reshape(3, 3)
        dp_w = Ra @ ep * kp
        om = -(Ra @ r) * kr
        ptcp = d.site_xpos[self.site[arm]]
        v = dp_w + np.cross(om, ptcp - d.xpos[ib])
        J = self.jac(arm)
        x = np.r_[v, om]
        dq = J.T @ np.linalg.solve(J @ J.T + lam ** 2 * np.eye(6), x)
        if cap is not None:
            dq = np.clip(dq, -cap, cap)
        return dq

    def status(self):
        st = self.tr.status(); return st.get('current_metrics') or {}, st['completed']
