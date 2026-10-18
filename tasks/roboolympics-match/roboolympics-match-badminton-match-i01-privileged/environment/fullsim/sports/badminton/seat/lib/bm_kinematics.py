"""The badminton robot's kinematics library: the low-level toolkit's IK library (agent side, seat/toolkit.toml).

Low level = "Agent as Robotics Engineer" (docs/construction_zh.md step 3): the platform gives the robot's own model
(the x-y base, the 1.0 m pedestal, the Franka Panda, the racket), the joint-target interface (traj of 9 targets
[base_x, base_y, q1..q7] per 10 ms, real limits), the servo model (bm_servo.py) and this library; the stroke itself
(where the base stands, when to swing, the swing trajectory, head speed and face control at contact, compensating the
servo's lag) is the player's to develop. The library is generic kinematics plus the base's documented go-to law and
knows nothing about badminton: no shuttle, no timing, no stroke planner (the high level's act skill is not in the
low-level toolkit; seat/toolkit.toml lists what is and what is not).

It needs only numpy and mujoco (the seat's MuJoCo, CPU) and the robot-only model (/opt/robot/robot_only.xml).
Deterministic: no randomness at run time, no threads, a fixed iteration budget.

    import sys; sys.path.insert(0, "/opt/robot/lib")
    from bm_kinematics import RacketKinematics
    K = RacketKinematics()                                   # /opt/robot/robot_only.xml
    p, R = K.fk(q)                                           # q: 9 [base_x, base_y, q1..q7]; head centre (3,),
                                                             # rotation (3, 3): column 0 = the string-face normal,
                                                             # column 2 = along the shaft (towards the head)
    J = K.jacobian(q)                                        # (6, 9) [linear; angular] of the head centre
    v, w = K.racket_velocity(q, qd)                          # the head centre's linear / angular velocity
    qa, err = K.solve(pos, normal=n, q0=qa_start, base=b)    # arm IK (7 joints) with the base at b = [bx, by]: head
                                                             # centre at pos, face normal along n (rotation about n
                                                             # free); or R=... (full pose), or position only
    qa, err = K.solve_near(pos, normal=n, q_ref=qa_now, base=b, vel_limit=arm_speed_limits)
    d = K.clearance(q, exclude=K.close_pairs(q_ready))       # least distance (m, capped at 0.05) between the arm /
                                                             # racket and the robot's own links, pedestal, platform
    rows, arrived = K.base_plan(b, v, goal, n, a)            # the base's go-to law (the return to its spot after a
                                                             # traj, /spec base): n rows of [bx, by] within its limits

`err` = position error (m) + face-normal error (rad); check it. The string bed has two faces: a contact law reads
the face the head moves towards, so `normal` and `-normal` are the same racket face for a stroke; solve() fits the
face normal as given (call it with -normal for the other face). Units: metres, radians. Version 1.0.0.

The base's limits (BASE below: the gantry's, as `game spec` base gives them) are the only base-specific numbers; a
sport revision that changes the base changes them (or pass base_limits=spec['base']).
"""
from __future__ import annotations

import math
import os
import re
from pathlib import Path

import numpy as np

VERSION = "1.0.0"
ARM_JOINTS = [f"joint{i}" for i in range(1, 8)]
JOINTS = ["base_x", "base_y"] + ARM_JOINTS
SITE = "racket_center"
DEFAULT_XML = os.environ.get("RO_ROBOT_XML", "/opt/robot/robot_only.xml")
N_STARTS = 12                    # solve_near: q_ref plus 12 fixed offsets (seeded once, at import: deterministic)
_OFFSETS = np.random.default_rng(0).normal(0.0, 0.8, (N_STARTS, 7))
DT = 0.01
CLEAR_CUT = 0.05                 # clearance(): distances are measured up to this (m)
# the base (/spec base): speed, acceleration and jerk (norm of the x-y vector), travel
BASE = {"max_speed_mps": 2.0, "max_accel_mps2": 15.0, "max_jerk_mps3": 375.0, "max_accel_per_axis_mps2": [15.0, 15.0],
        "range": {"x": [-1.5, 1.5], "y": [-3.53, -0.5]}}     # the Festo EGC-185-BS-KF-40P gantry (game spec base)


class RacketKinematics:
    """Forward / inverse kinematics of the racket head centre (site racket_center) of the robot-only model."""

    def __init__(self, xml_path: str | os.PathLike = DEFAULT_XML, meshdir: str | os.PathLike | None = None,
                 base_limits: dict | None = None):
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
            raise ValueError("not the 9-joint badminton robot (base_x, base_y, joint1..joint7)")
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
        b = dict(BASE, **(base_limits or {}))
        self.base_v, self.base_a = float(b["max_speed_mps"]), float(b["max_accel_mps2"])
        self.base_j = float(b.get("max_jerk_mps3") or 25.0 * self.base_a)
        ax = b.get("max_accel_per_axis_mps2") or b.get("axis_accel_mps2") or [self.base_a, self.base_a]
        self.base_axis_a = np.asarray(ax, float).reshape(2)          # per axis (x: left-right, y: forward)
        r = b["range"]
        self.base_lo = np.array([r["x"][0], r["y"][0]], float)
        self.base_hi = np.array([r["x"][1], r["y"][1]], float)
        self._clr = None

    # ------------------------------------------------------------------ forward kinematics
    def _set(self, q):
        self.d.qpos[self.qadr] = np.asarray(q, float).reshape(9)
        self.mj.mj_kinematics(self.m, self.d)
        self.mj.mj_comPos(self.m, self.d)

    def fk(self, q):
        """(head centre (3,), rotation (3, 3)) at the 9 joints q; R[:, 0] = string-face normal."""
        self._set(q)
        return self.d.site_xpos[self.site].copy(), self.d.site_xmat[self.site].reshape(3, 3).copy()

    def jacobian(self, q):
        """(6, 9) Jacobian of the head centre at q: rows 0-2 linear, rows 3-5 angular (world frame)."""
        self._set(q)
        self.mj.mj_jacSite(self.m, self.d, self._jp, self._jr, self.site)
        return np.vstack([self._jp[:, self.vadr], self._jr[:, self.vadr]])

    def racket_velocity(self, q, qd):
        J = self.jacobian(q)
        qd = np.asarray(qd, float).reshape(9)
        return J[:3] @ qd, J[3:] @ qd

    def within_limits(self, q, margin: float = 0.0) -> bool:
        q = np.asarray(q, float)
        return bool(np.all(q >= self.lo + margin) and np.all(q <= self.hi - margin))

    # ------------------------------------------------------------------ inverse kinematics (the arm, base fixed)
    def solve(self, pos, normal=None, R=None, q0=None, base=(0.0, -1.6), iters: int = 200, tol: float = 1e-4,
              damping: float = 1e-3, max_step: float = 0.25, margin: float = 1e-4):
        """Damped-least-squares arm IK (7 joints) with the base at `base`: the head centre at `pos` and either the
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

    def solve_near(self, pos, normal=None, R=None, q_ref=None, base=(0.0, -1.6), vel_limit=None, tol: float = 1e-4,
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

    # ------------------------------------------------------------------ self-collision clearance
    def pair_distances(self, q):
        """{pair name: distance (m, capped at CLEAR_CUT; negative = penetration)} of the robot's self-collision pairs
        (the arm and the racket against its links, pedestal and platform; the model's <pair>s) at the 9 joints q.
        Kinematics only (MuJoCo's collision detection with the pairs' margin raised to CLEAR_CUT)."""
        mj = self.mj
        if self._clr is None:
            import copy
            mc = copy.deepcopy(self.m)
            mc.pair_margin[:] = CLEAR_CUT
            key = {(min(int(mc.pair_geom1[i]), int(mc.pair_geom2[i])), max(int(mc.pair_geom1[i]), int(mc.pair_geom2[i]))):
                   mj.mj_id2name(mc, mj.mjtObj.mjOBJ_PAIR, i) or f"pair{i}" for i in range(mc.npair)}
            self._clr = (mc, mj.MjData(mc), key)
        mc, d, key = self._clr
        d.qpos[self.qadr] = np.asarray(q, float).reshape(9)
        mj.mj_kinematics(mc, d)
        mj.mj_collision(mc, d)
        out = {n: CLEAR_CUT for n in key.values()}
        for c in d.contact[:d.ncon]:
            n = key.get((min(int(c.geom[0]), int(c.geom[1])), max(int(c.geom[0]), int(c.geom[1]))))
            if n is not None:
                out[n] = min(out[n], float(c.dist))
        return out

    def clearance(self, q, exclude=()):
        """The least distance (m, capped at CLEAR_CUT) over the self-collision pairs at q, leaving out the pairs named
        in `exclude` (e.g. those that are structurally close in every pose: close_pairs(ready pose))."""
        return float(min([v for k, v in self.pair_distances(q).items() if k not in exclude] or [CLEAR_CUT]))

    def close_pairs(self, q, below: float = 0.04):
        """The names of the self-collision pairs closer than `below` at q (at the ready pose: the wrist's links that
        are always that close, which no motion can keep clear of)."""
        return {k for k, v in self.pair_distances(q).items() if v < below}

    # ------------------------------------------------------------------ the base (its documented go-to law)
    def base_goto(self, b, v, goal, a_prev=None):
        """One 10 ms step of the base's go-to law (what the robot does by itself to reach a `move` point or a stance;
        game spec base): speed on the norm <= 0.98 x max, acceleration <= 0.8 x the smallest axis limit (and 0.8 x
        each axis' limit), its change <= max jerk x 10 ms, a braking curve with room for the jerk ramp. Returns
        (target, velocity)."""
        V, Jm = self.base_v, self.base_j
        A = 0.8 * float(self.base_axis_a.min())
        tj = A / Jm
        b, v, goal = (np.asarray(x, float) for x in (b, v, goal))
        e = goal - b
        dist = float(np.hypot(e[0], e[1]))
        sp = float(np.hypot(v[0], v[1]))
        amin = float(self.base_axis_a.min())
        if dist < min(0.004, 0.4 * amin * DT ** 2) and sp < min(0.05, 0.4 * amin * DT):
            return goal.copy(), np.zeros(2)
        d_eff = max(0.0, dist - sp * tj * 0.5)
        vdes = e / max(dist, 1e-9) * min(V * 0.98, math.sqrt(2 * A * 0.7 * d_eff), dist / (2 * tj + 0.02))
        a_cmd = (vdes - v) / DT
        na = float(np.hypot(*a_cmd))
        amax = (min(A, math.sqrt(2 * Jm * max(0.0, V * 0.98 - sp)) + Jm * DT) if float(a_cmd @ v) > 0 else A)
        if na > amax:
            a_cmd = a_cmd * (amax / na)
        a_cmd = np.clip(a_cmd, -0.8 * self.base_axis_a, 0.8 * self.base_axis_a)
        ap = np.zeros(2) if a_prev is None else np.asarray(a_prev, float)
        da = a_cmd - ap
        nda = float(np.hypot(*da))
        if nda > Jm * DT:
            a_cmd = ap + da * (Jm * DT / nda)
        v = v + a_cmd * DT
        nv = float(np.hypot(v[0], v[1]))
        if nv > V * 0.98:
            v = v * (V * 0.98 / nv)
        return np.clip(b + v * DT, self.base_lo, self.base_hi), v

    def base_plan(self, b, v, goal, n, a=None):
        """n rows of the go-to law from target b moving at v (acceleration a): (rows (n, 2), index of the first row
        within 1.5 cm of the goal, or None)."""
        out, arrived = np.zeros((n, 2)), None
        b, v = np.asarray(b, float), np.asarray(v, float)
        acc = np.zeros(2) if a is None else np.asarray(a, float)
        goal = np.clip(np.asarray(goal, float), self.base_lo, self.base_hi)
        for i in range(n):
            v0 = v
            b, v = self.base_goto(b, v, goal, acc)
            acc = (v - v0) / DT
            out[i] = b
            if arrived is None and float(np.hypot(*(b - goal))) < 0.015:
                arrived = i
        return out, arrived

    def base_rows_problem(self, rows, b0, v0):
        """Why base rows (n x 2, one per 10 ms) after the target b0 moving at v0 break the base's limits (speed and
        acceleration on the norm, acceleration per axis, as the low level checks them), or None."""
        q = np.vstack([np.asarray(b0, float)[None], np.asarray(rows, float).reshape(-1, 2)])
        v = np.vstack([np.asarray(v0, float)[None], np.diff(q, axis=0) / DT])
        if (np.hypot(v[1:, 0], v[1:, 1]) > self.base_v * 1.001 + 1e-9).any():
            return f"the base faster than {self.base_v:g} m/s"
        acc = np.diff(v, axis=0) / DT
        if (np.hypot(acc[:, 0], acc[:, 1]) > self.base_a * 1.001 + 1e-9).any():
            return f"the base accelerating at more than {self.base_a:g} m/s^2"
        if (np.abs(acc) > self.base_axis_a * 1.001 + 1e-9).any():
            return f"the base accelerating beyond its per-axis limits {self.base_axis_a.tolist()} m/s^2"
        return None
