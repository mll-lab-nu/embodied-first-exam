"""Grasps and object-motion primitives of the CastKeyhole oracle (design v2, weak-gripper aware).

Measured facts that drive the design (runs/smoke_ve, runs/orc_t1 on vast):
 - the authored X-shaped start is not self-supporting: within ~1 s both plates fall nearly flat (gold ~17 deg,
   silver ~24 deg), still interlocked;
 - the YAM gripper squeezes a 9 mm plate with only ~9-14 N (finger kp 2000 N/m): a face clamp at a plate edge
   with the COM 5-10 cm away (gold held flat by its edge) slips and drops the plate under the pry moment.
Design:
 - gold: face clamp on the +x prong band (x 20..39 mm, the band the silver never sweeps for the +90 deg key
   turn), first approached from the side; the gold is then PIVOTED about its lower (-x) edge on the table until
   it stands vertical (+x up), so the table carries it, and lifted with the gripper top-down (COM below);
 - silver: width clamp (jaws across the 78 mm width, on the two outer edges) near its centre, approached from
   above; the clamp stays valid through the whole key turn (rotation about the silver's own width axis) and the
   slide (the gold passes through the silver hole at |x_s| <= 4.5 mm, the blades are at |x_s| >= 39 mm).
"""
from __future__ import annotations

import numpy as np
from scipy.spatial.transform import Rotation, Slerp

import route as rt
from layout import T_from


def frame(a, j):
    a = np.asarray(a, float); a /= np.linalg.norm(a)
    j = np.asarray(j, float); j = j - a * (j @ a); j /= np.linalg.norm(j)
    return np.c_[a, j, np.cross(a, j)]


def gold_grasp(y=-0.010, x_tcp=0.059, jaw=1.0):
    """TCP in the gold plate frame: approach -x (into the +x edge), jaw along +-z."""
    return T_from(frame([-1, 0, 0], [0, 0, jaw]), [x_tcp, y, 0.0])


def gold_fork_grasp(x_tcp=0.056, tip_y=-0.068, jaw=1.0):
    """TCP in the gold plate frame: face clamp on the +x prong at the fork end, approached along +y from the
    open end; fingertips at y = tip_y, blades x in [x_tcp-31, x_tcp+29] mm (outside the silver sweep x <= 17)."""
    return T_from(frame([0, 1, 0], [0, 0, jaw]), [x_tcp, tip_y - 0.037, 0.0])


def silver_grasp(y=0.020, k=1.0, depth=0.028, jaw=1.0):
    """TCP in the silver plate frame: approach k*z (through the plate face), jaw along +-x (across the width);
    the plate mid-plane sits `depth` ahead of the TCP (near the fingertips)."""
    return T_from(frame([0, 0, k], [jaw, 0, 0]), [0.0, y, -k * depth])


def silver_edge_grasp(y=-0.0024, x_tcp=-0.051, jaw=1.0):
    """TCP in the silver plate frame: face clamp on the -x side bar (x -39..-24.3 mm), approach +x, jaw +-z.
    The gold only ever occupies |x_s| <= 4.5 mm (it is a plate in the silver's x_s ~ 0 plane), so the fingers
    (tips at x_s = x_tcp + 37 mm = -14 mm) can never touch the gold.  y = the silver COM (-2.4 mm)."""
    return T_from(frame([1, 0, 0], [0, 0, jaw]), [x_tcp, y, 0.0])


def interp_T(A, B, u):
    T = np.eye(4)
    T[:3, 3] = A[:3, 3] + u * (B[:3, 3] - A[:3, 3])
    T[:3, :3] = Slerp([0, 1], Rotation.from_matrix([A[:3, :3], B[:3, :3]]))(u).as_matrix()
    return T


def rot_about(T, R, pivot):
    out = T.copy()
    out[:3, :3] = R @ T[:3, :3]
    out[:3, 3] = R @ (T[:3, 3] - pivot) + pivot
    return out


class Relative:
    """Silver-relative-to-gold configurations (plate frames)."""

    def __init__(self, record, tier):
        self.rec, self.tier = record, tier
        self.scale = record["scale"]
        self.r0, self.c0 = rt.nominal_relative(record)
        self.path = rt.route(record, tier, +1, n_turn=40, step_m=.0005)

    def T_rel(self, r, c):
        return T_from(r, rt.silver_plate_pose_in_gold(r, c, self.scale))

    def nominal(self):
        return self.T_rel(self.r0, self.c0)

    def measured(self, Tg, Ts):
        Trel = np.linalg.inv(Tg) @ Ts
        r = Rotation.from_matrix(Trel[:3, :3])
        c = Trel[:3, 3] + r.apply(rt.bar_point(self.scale))
        return r, c

    def align(self, Tg, Ts):
        """u -> relative transform from the measured to the nominal configuration."""
        r_m, c_m = self.measured(Tg, Ts)
        sl = Slerp([0, 1], Rotation.from_quat([r_m.as_quat(), self.r0.as_quat()]))
        return lambda u: self.T_rel(sl(u), c_m + u * (self.c0 - c_m))

    def stage(self, prefix):
        return [(r, c) for r, c, s in self.path if s.startswith(prefix)]

    def sampler(self, samples, extra=None):
        """u -> relative transform along route samples (+ optional extra straight translation of c)."""
        seq = list(samples)
        if extra is not None:
            r, c = seq[-1]
            n = max(2, int(np.linalg.norm(extra) / .0005))
            seq += [(r, c + extra * k / n) for k in range(1, n + 1)]
        Ts = [self.T_rel(r, c) for r, c in seq]

        def f(u):
            x = u * (len(Ts) - 1)
            i = min(int(np.floor(x)), len(Ts) - 2)
            return interp_T(Ts[i], Ts[i + 1], x - i)
        length = sum(np.linalg.norm(b[1] - a[1]) for a, b in zip(seq[:-1], seq[1:]))
        return f, length


def pivot_rotation(Tg):
    """Rotation (world) about the gold's long axis that brings gold +x straight up, and the pivot point
    (lowest point of the -x edge)."""
    x, y = Tg[:3, 0], Tg[:3, 1]
    axis = y / np.linalg.norm(y)
    # angle about axis taking x to the vertical component orthogonal to the axis
    up = np.array([0, 0, 1.0]); up_p = up - axis * (up @ axis); up_p /= np.linalg.norm(up_p)
    ang = np.arctan2(np.cross(x, up_p) @ axis, x @ up_p)
    return Rotation.from_rotvec(axis * ang).as_matrix(), ang
