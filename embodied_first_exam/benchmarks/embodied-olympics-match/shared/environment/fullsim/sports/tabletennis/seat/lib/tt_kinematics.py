"""The table-tennis robot's kinematics library: the low-level toolkit's IK library (agent side, seat/toolkit.toml).

Low level = "Agent as Robotics Engineer" (docs/construction_zh.md step 3): the platform gives the robot's own model
(the x-y rail base, the Franka Panda, the paddle), the joint-target interface (traj / slew / hold of 9 targets
[base_x, base_y, q1..q7], real limits) and this library; the stroke itself (when to swing, the swing trajectory,
paddle speed and face control, where the base stands) is the player's to develop. The library is generic kinematics
plus the rail's documented go-to law and knows nothing about table tennis: no ball, no timing, no stroke planner (the
high level's hit skill is not in the low-level toolkit; seat/toolkit.toml lists what is and what is not).

It needs only numpy and mujoco (the seat's pinned MuJoCo 3.3.7, CPU) and the robot-only model
(/opt/robot/robot_only.xml). Deterministic: no randomness at run time, no threads, a fixed iteration budget.

    import sys; sys.path.insert(0, "/opt/robot/lib")
    from tt_kinematics import PaddleKinematics
    K = PaddleKinematics()                                   # /opt/robot/robot_only.xml
    p, R = K.fk(q)                                           # q: 9 [base_x, base_y, q1..q7]; blade centre (3,),
                                                             # rotation (3, 3): column 0 = face normal, 2 = handle
    J = K.jacobian(q)                                        # (6, 9) [linear; angular] of the blade centre
    v, w = K.paddle_velocity(q, qd)                          # the blade centre's linear / angular velocity
    qa, err = K.solve(pos, normal=n, q0=qa_start, base=b)    # arm IK (7 joints) with the base at b = [bx, by]:
                                                             # blade centre at pos, face normal along n (rotation about
                                                             # n free); or R=... (full pose), or position only
    qa, err = K.solve_near(pos, normal=n, q_ref=qa_now, base=b, vel_limit=arm_speed_limits)
    b = K.stance(p_c, b_now)                                 # a base position that brings p_c into the arm's
                                                             # comfortable zone (moves only as much as needed)
    rows, arrived = K.base_plan(b, v, goal, n, a)            # the rail's go-to law (the slew's base motion, /spec
                                                             # limits.base): n rows of [bx, by] within its limits

`err` = position error (m) + face-normal error (rad); check it. Units: metres, radians. Version 2.0.0 (revision
12/10 of the sport: the rail base, 9 joints).
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import numpy as np

VERSION = "2.0.0"
ARM_JOINTS = [f"joint{i}" for i in range(1, 8)]
JOINTS = ["base_x", "base_y"] + ARM_JOINTS
SITE = "paddle_center"
DEFAULT_XML = os.environ.get("RO_ROBOT_XML", "/opt/robot/robot_only.xml")
N_STARTS = 12                    # solve_near: q_ref plus 12 fixed offsets (seeded once, at import: deterministic)
_OFFSETS = np.random.default_rng(0).normal(0.0, 0.8, (N_STARTS, 7))
DT = 0.01
# the rail (/spec limits.base): travel, speed, acceleration, jerk; the go-to law of the slew's base motion
BASE_LO, BASE_HI = np.array([-1.0, -2.40]), np.array([1.0, -1.50])
BASE_V, BASE_A, BASE_J = 2.0, 8.0, 200.0
STANCE_BOX, STANCE_PREF = np.array([0.25, 0.10]), np.array([0.0, 0.45])


def _sqrt_ctrl(err, k, d):
    lin = d / (k * k)
    a = np.abs(err)
    return np.where(a <= lin, k * err, np.sign(err) * np.sqrt(np.maximum(0.0, 2.0 * d * (a - 0.5 * lin))))


class PaddleKinematics:
    """Forward / inverse kinematics of the blade centre (site paddle_center) of the robot-only model."""

    def __init__(self, xml_path: str | os.PathLike = DEFAULT_XML, meshdir: str | os.PathLike | None = None):
        import mujoco as mj
        self.mj = mj
        if meshdir is None:
            self.m = mj.MjModel.from_xml_path(str(xml_path))
        else:
            xml = Path(xml_path).read_text()
            xml = re.sub(r'meshdir="[^"]*"', f'meshdir="{Path(meshdir).resolve()}"', xml, count=1)
            self.m = mj.MjModel.from_xml_string(xml)
        m = self.m
        jid = [mj.mj_name2id(m, mj.mjtObj.mjOBJ_JOINT, j) for j in JOINTS]
        if min(jid) < 0:
            raise ValueError("not the 9-joint table-tennis robot (base_x, base_y, joint1..joint7)")
        self.qadr = np.array([m.jnt_qposadr[i] for i in jid])
        self.vadr = np.array([m.jnt_dofadr[i] for i in jid])
        self.lo = m.jnt_range[jid, 0].copy()
        self.hi = m.jnt_range[jid, 1].copy()
        self.site = mj.mj_name2id(m, mj.mjtObj.mjOBJ_SITE, SITE)
        if self.site < 0:
            raise ValueError(f"no site {SITE!r} in the model")
        self.d = mj.MjData(m)                    # scratch data: kinematics only, never stepped
        self._jp = np.zeros((3, m.nv))
        self._jr = np.zeros((3, m.nv))

    # ------------------------------------------------------------------ forward kinematics
    def _set(self, q):
        self.d.qpos[self.qadr] = np.asarray(q, float).reshape(9)
        self.mj.mj_kinematics(self.m, self.d)
        self.mj.mj_comPos(self.m, self.d)

    def fk(self, q):
        """(blade centre (3,), rotation (3, 3)) at the 9 joints q; R[:, 0] = face normal, R[:, 2] = along the handle."""
        self._set(q)
        return self.d.site_xpos[self.site].copy(), self.d.site_xmat[self.site].reshape(3, 3).copy()

    def jacobian(self, q):
        """(6, 9) Jacobian of the blade centre at q: rows 0-2 linear, rows 3-5 angular (world frame)."""
        self._set(q)
        self.mj.mj_jacSite(self.m, self.d, self._jp, self._jr, self.site)
        return np.vstack([self._jp[:, self.vadr], self._jr[:, self.vadr]])

    def paddle_velocity(self, q, qd):
        J = self.jacobian(q)
        qd = np.asarray(qd, float).reshape(9)
        return J[:3] @ qd, J[3:] @ qd

    def within_limits(self, q, margin: float = 0.0) -> bool:
        q = np.asarray(q, float)
        return bool(np.all(q >= self.lo + margin) and np.all(q <= self.hi - margin))

    # ------------------------------------------------------------------ inverse kinematics (the arm, base fixed)
    def solve(self, pos, normal=None, R=None, q0=None, base=(0.0, -1.75), iters: int = 200, tol: float = 1e-4,
              damping: float = 1e-3, max_step: float = 0.5, margin: float = 1e-4):
        """Damped-least-squares arm IK (7 joints) with the base at `base`: the blade centre at `pos` and either the
        face normal `normal` (rotation about it free), the full rotation `R`, or neither. Starts at q0 (7; default the
        middle of the ranges). Returns (qa (7,), err)."""
        pos = np.asarray(pos, float).reshape(3)
        b = np.asarray(base, float).reshape(2)
        lo, hi = self.lo[2:] + margin, self.hi[2:] - margin
        q = np.clip(np.array(0.5 * (lo + hi) if q0 is None else q0, float).reshape(7), lo, hi)
        n_t = None if normal is None else np.asarray(normal, float) / np.linalg.norm(normal)
        R_t = None if R is None else np.asarray(R, float).reshape(3, 3)
        err = np.inf
        for _ in range(iters):
            J = self.jacobian(np.r_[b, q])[:, 2:]
            p = self.d.site_xpos[self.site]
            Rc = self.d.site_xmat[self.site].reshape(3, 3)
            ep = pos - p
            if R_t is not None:
                er = 0.5 * (np.cross(Rc[:, 0], R_t[:, 0]) + np.cross(Rc[:, 1], R_t[:, 1]) + np.cross(Rc[:, 2], R_t[:, 2]))
                ang = float(np.arccos(np.clip((np.trace(Rc.T @ R_t) - 1.0) / 2.0, -1.0, 1.0)))
                e, Jx, err = np.r_[ep, er], J, float(np.linalg.norm(ep)) + ang
            elif n_t is not None:
                n = Rc[:, 0]
                er = np.cross(n, n_t)
                err = float(np.linalg.norm(ep) + np.arcsin(min(1.0, float(np.linalg.norm(er)))))
                if n @ n_t < 0:
                    er = er + 0.5 * np.cross(n, Rc[:, 1])
                    err += np.pi / 2
                e, Jx = np.r_[ep, er], J
            else:
                e, Jx, err = ep, J[:3], float(np.linalg.norm(ep))
            if err < tol:
                break
            dq = Jx.T @ np.linalg.solve(Jx @ Jx.T + damping * np.eye(len(e)), e)
            s = float(np.max(np.abs(dq)))
            if s > max_step:
                dq *= max_step / s
            q = np.clip(q + dq, lo, hi)
        else:
            p, Rc = self.fk(np.r_[b, q])
            err = self._err(p, Rc, pos, n_t, R_t)
        return q, float(err)

    @staticmethod
    def _err(p, Rc, pos, n_t, R_t):
        e = float(np.linalg.norm(pos - p))
        if R_t is not None:
            return e + float(np.arccos(np.clip((np.trace(Rc.T @ R_t) - 1.0) / 2.0, -1.0, 1.0)))
        if n_t is not None:
            return e + float(np.arccos(np.clip(Rc[:, 0] @ n_t, -1.0, 1.0)))
        return e

    def solve_near(self, pos, normal=None, R=None, q_ref=None, base=(0.0, -1.75), vel_limit=None, tol: float = 1e-4,
                   travel_ok: float = 0.35, **kw):
        """Several deterministic starts (q_ref, then q_ref + 12 fixed offsets clipped to the ranges): among the
        accurate solutions (err < tol) the one with the least travel from q_ref, max_j |q_j - q_ref_j| / vel_limit_j;
        stops early at one within travel_ok. Without an accurate solution: the smallest error. Returns (qa, err)."""
        lo, hi = self.lo[2:], self.hi[2:]
        q_ref = np.array(0.5 * (lo + hi) if q_ref is None else q_ref, float).reshape(7)
        vl = np.ones(7) if vel_limit is None else np.asarray(vel_limit, float).reshape(-1)[-7:]

        def travel(c):
            return float(np.max(np.abs(c[0] - q_ref) / vl))

        def rank(c):
            return (0, travel(c)) if c[1] < tol else (1, c[1])

        best = self.solve(pos, normal, R, q_ref, base, tol=tol, **kw)
        if best[1] < tol and travel(best) <= travel_ok:
            return best
        for off in _OFFSETS:
            c = self.solve(pos, normal, R, np.clip(q_ref + off, lo + 0.05, hi - 0.05), base, tol=tol, **kw)
            if rank(c) < rank(best):
                best = c
            if best[1] < tol and travel(best) <= travel_ok:
                break
        return best

    # ------------------------------------------------------------------ the rail base (the documented laws)
    @staticmethod
    def stance(p_c, b_now):
        """A base position for a blade contact at p_c: the base moves only as much as needed to bring the contact within
        0.25 m sideways and 0.10 m in depth of the point 0.45 m in front of it, clipped to the travel."""
        b_now = np.asarray(b_now, float)
        rel = np.asarray(p_c[:2], float) - (b_now + STANCE_PREF)
        shift = rel - np.clip(rel, -STANCE_BOX, STANCE_BOX)
        return np.clip(b_now + shift, BASE_LO, BASE_HI)

    @staticmethod
    def base_goto(b, v, goal, a=None, vmax=BASE_V):
        """One 10 ms step of the rail's go-to law (the slew's base motion; at 98 % of the speed, 85 % of the
        acceleration and jerk limits): (new target, its velocity, its acceleration)."""
        V, A, J = 0.98 * vmax, 0.85 * BASE_A, 0.85 * BASE_J
        KP, KV, BRAKE = 12.0, 30.0, 0.55
        b = np.asarray(b, float); v = np.clip(np.asarray(v, float), -V, V)
        a = np.zeros(2) if a is None else np.clip(np.asarray(a, float), -A, A)
        goal = np.clip(np.asarray(goal, float), BASE_LO, BASE_HI)
        e = goal - b
        ab = BRAKE * A
        d = np.abs(e)
        v_stop = 0.5 * (-ab * ab / J + np.sqrt((ab * ab / J) ** 2 + 8.0 * ab * d))
        v_cmd = np.clip(np.sign(e) * np.minimum(v_stop, KP * d), -V, V)
        a_cmd = np.clip(_sqrt_ctrl(v_cmd - v, KV, J), -A, A)
        a_cmd = np.clip(a_cmd, -np.sqrt(2.0 * J * np.maximum(0.0, V + v)), np.sqrt(2.0 * J * np.maximum(0.0, V - v)))
        an = a + np.clip(a_cmd - a, -J * DT, J * DT)
        vn = np.clip(v + an * DT, -V, V)
        nb = np.clip(b + vn * DT, BASE_LO, BASE_HI)
        if np.max(np.abs(goal - nb)) < 5e-4 and np.max(np.abs(vn)) < 0.02:
            nb = goal.copy()
        vn = (nb - b) / DT
        an = (vn - v) / DT
        if np.array_equal(nb, goal) and np.max(np.abs(vn)) < 0.06:
            return nb, np.zeros(2), np.zeros(2)
        return nb, vn, an

    @classmethod
    def base_plan(cls, b, v, goal, n, a=None):
        """n rows of the go-to law from (b, v, a): (rows (n, 2), index of the first row at rest at the goal or None)."""
        out, arrived = np.zeros((n, 2)), None
        goal = np.clip(np.asarray(goal, float), BASE_LO, BASE_HI)
        for i in range(n):
            b, v, a = cls.base_goto(b, v, goal, a=a)
            out[i] = b
            if arrived is None and np.array_equal(b, goal) and not v.any():
                arrived = i
        return out, arrived

    @classmethod
    def base_reach(cls, b, v, goal, n_avail, margin=5, a=None):
        """The goal the base can reach and stop at `margin` steps before step n_avail, on the line from b to goal:
        (goal used, metres short)."""
        b = np.asarray(b, float); goal = np.clip(np.asarray(goal, float), BASE_LO, BASE_HI)
        _, arr = cls.base_plan(b, v, goal, max(1, n_avail), a)
        if arr is not None and arr <= n_avail - margin:
            return goal, 0.0
        lo, hi = 0.0, 1.0
        for _ in range(10):
            mid = 0.5 * (lo + hi)
            _, a2 = cls.base_plan(b, v, b + mid * (goal - b), max(1, n_avail), a)
            if a2 is not None and a2 <= n_avail - margin:
                lo = mid
            else:
                hi = mid
        g = b + lo * (goal - b)
        return g, float(np.linalg.norm(goal - g))
