"""Authoring helpers for the arm rig (not shipped): hand-root pose IK and fingertip grasp fits (kinematics only).

Frames: a Sharpa Wave hand root (``<side>_hand_C_MC``) has fingers +Z, palm normal +X and thumb +Y (right) / -Y
(left, the y-mirrored model). ``R`` arguments are 3x3 world rotations whose columns are those hand axes.
"""

from __future__ import annotations

import math

import mujoco
import numpy as np
from scipy.optimize import least_squares

FINGERS = ("thumb", "index", "middle", "ring", "pinky")
# Finger columns inside one hand's 22 (Sharpa) / 20 (Wuji) finger actuators.
FINGER_COLS = {
    "sharpa": {"thumb": range(0, 5), "index": range(5, 9), "middle": range(9, 13), "ring": range(13, 17),
               "pinky": range(17, 22)},
    "wuji": {"thumb": range(0, 4), "index": range(4, 8), "middle": range(8, 12), "ring": range(12, 16),
             "pinky": range(16, 20)},
}
HAND_ROOT = {"sharpa": {"left": "left_hand_C_MC", "right": "right_hand_C_MC"}}
# Natural arm postures (pot_shelf_transfer's working poses): elbows down and out, clear of the stand.
NOMINAL = {"left": np.array([0.5, -0.6, 0.0, -1.5, 0.3, 0.1, 0.5]),
           "right": np.array([-0.54, -0.46, 0.04, -1.31, -0.29, -0.19, -0.62])}


def tip_geom(model, hand, side, finger):
    if hand == "sharpa":
        return model.geom(f"{side}_{finger}_fingertip_collision").id
    s = side[0]
    name = {"thumb": "thumb_tip", "index": "index_finger_tip", "middle": "middle_finger_tip",
            "ring": "ring_finger_tip", "pinky": "little_finger_tip"}[finger]
    return model.geom(f"{s}_wuji_{s}_{name}_sensor_frame_collision1").id


def pad_radius(model, gid):
    if model.geom_type[gid] == mujoco.mjtGeom.mjGEOM_CAPSULE:
        return float(model.geom_size[gid, 0])
    return float(min(model.geom_aabb[gid, 3:5]))


def rotvec(R):
    q = np.empty(4)
    mujoco.mju_mat2Quat(q, np.asarray(R, float).ravel())
    v = np.empty(3)
    mujoco.mju_quat2Vel(v, q, 1.0)
    return v


def rot_z(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])


class Kin:
    """Kinematic scratch copy of a session's model for IK / grasp fits."""

    def __init__(self, session):
        self.s = session
        self.m = session.model
        self.d = mujoco.MjData(self.m)
        lay = session.layout
        self.arm_cols = lay["arm"]
        self.finger_cols = lay["fingers"]
        self.qadr = session.qadr
        self.dofadr = self.m.jnt_dofadr[self.m.actuator_trnid[:, 0]]
        self.lo, self.hi = self.m.actuator_ctrlrange.T
        root = HAND_ROOT.get(session.hand, {"left": None, "right": None})
        self.root = {}
        for side in ("left", "right"):
            name = root.get(side) or self._mount_child(side)
            self.root[side] = self.m.body(name).id

    def _mount_child(self, side):
        import arm_rig

        return arm_rig._mount_names(self.m)[arm_rig.SIDES.index(side)]

    def load(self, qpos, row):
        self.d.qpos[:] = qpos
        self.d.qpos[self.qadr] = row
        mujoco.mj_kinematics(self.m, self.d)
        mujoco.mj_comPos(self.m, self.d)

    def root_pose(self, side):
        b = self.root[side]
        return self.d.xpos[b].copy(), self.d.xmat[b].reshape(3, 3).copy()

    def pose_ik(self, side, row, qpos, pos, R, iters=60, wrot=0.3, damping=1e-3, point=None, nominal=0.05):
        """Arm joints (in ``row``) so that the hand root (or ``point`` in the root frame) reaches pos / R."""
        row = np.array(row, float)
        cols = np.arange(self.m.nu)[self.arm_cols[side]]
        dofs = self.dofadr[cols]
        b = self.root[side]
        jp, jr = np.zeros((3, self.m.nv)), np.zeros((3, self.m.nv))
        off = np.zeros(3) if point is None else np.asarray(point, float)
        for _ in range(iters):
            self.load(qpos, row)
            p = self.d.xpos[b] + self.d.xmat[b].reshape(3, 3) @ off
            Rc = self.d.xmat[b].reshape(3, 3)
            ep = pos - p
            er = rotvec(R @ Rc.T) if R is not None else np.zeros(3)
            if np.linalg.norm(ep) < 1e-5 and np.linalg.norm(er) < 1e-4:
                break
            mujoco.mj_jac(self.m, self.d, jp, jr, p, b)
            J = np.vstack([jp[:, dofs], wrot * jr[:, dofs]]) if R is not None else jp[:, dofs]
            e = np.r_[ep, wrot * er] if R is not None else ep
            JJ = J @ J.T + damping * np.eye(len(e))
            dq = J.T @ np.linalg.solve(JJ, e)
            if nominal:
                # Null-space pull toward the natural posture keeps the elbow out and away from the stand.
                null = np.eye(len(cols)) - J.T @ np.linalg.solve(JJ, J)
                dq += null @ (nominal * (NOMINAL[side] - row[cols]))
            row[cols] = np.clip(row[cols] + dq, self.lo[cols] + 1e-4, self.hi[cols] - 1e-4)
        self.load(qpos, row)
        p = self.d.xpos[b] + self.d.xmat[b].reshape(3, 3) @ off
        return row, float(np.linalg.norm(pos - p)), (
            float(np.linalg.norm(rotvec(R @ self.d.xmat[b].reshape(3, 3).T))) if R is not None else 0.0)

    def grasp(self, side, row, qpos, tips, fingers_used, R=None, wrot=1.0, avoid=(), avoid_margin=0.003,
              free_arm=True, seed_weight=0.01, max_nfev=200):
        """Least-squares fit of arm (optional) + finger joints: fingertip pads at ``tips[finger]`` (world points)."""
        hand = self.s.hand
        row = np.array(row, float)
        fcols = np.arange(self.m.nu)[self.finger_cols[side]]
        var = []
        if free_arm:
            var += list(np.arange(self.m.nu)[self.arm_cols[side]])
        for f in fingers_used:
            var += [int(fcols[i]) for i in FINGER_COLS[hand][f]]
        var = np.asarray(var)
        tipg = {f: tip_geom(self.m, hand, side, f) for f in tips}
        b = self.root[side]
        hand_geoms = [g for g in range(self.m.ngeom) if self._in_hand(g, side) and self.m.geom_contype[g]
                      and g not in tipg.values()]
        seed = row[var].copy()

        def residual(x):
            row[var] = x
            self.load(qpos, row)
            err = []
            for f, t in tips.items():
                err.extend((self.d.geom_xpos[tipg[f]] - t) * 100)
            if R is not None:
                err.extend(wrot * rotvec(R @ self.d.xmat[b].reshape(3, 3).T))
            for g in hand_geoms:
                for o in avoid:
                    dist = mujoco.mj_geomDistance(self.m, self.d, g, o, 0.02, None)
                    err.append(min(0.0, dist - avoid_margin) * 300)
            err.extend((x - seed) * seed_weight)
            return np.asarray(err)

        lo, hi = self.lo[var] + 1e-6, self.hi[var] - 1e-6
        fit = least_squares(residual, np.clip(row[var], lo, hi), bounds=(lo, hi), max_nfev=max_nfev)
        residual(fit.x)
        errs = {f: float(np.linalg.norm(self.d.geom_xpos[tipg[f]] - t)) for f, t in tips.items()}
        return row.copy(), fit.cost, errs

    def collisions(self, side, row, qpos, depth=0.001):
        """Penetrating contacts (> ``depth``) of this side's arm/hand with anything but its own fingers' objects."""
        self.load(qpos, row)
        mujoco.mj_fwdPosition(self.m, self.d)
        arm_root = self.m.body({"left": "shoulder_pitch_l_j1_link", "right": "shoulder_pitch_r_j1_link"}[side]).id
        count = 0
        for c in self.d.contact[: self.d.ncon]:
            if c.dist > -depth:
                continue
            for g in (c.geom1, c.geom2):
                b = int(self.m.geom_bodyid[g])
                while b > 0 and b != arm_root:
                    b = int(self.m.body_parentid[b])
                if b == arm_root:
                    count += 1
                    break
        return count

    def _in_hand(self, g, side):
        b = int(self.m.geom_bodyid[g])
        root = self.root[side]
        while b > 0:
            if b == root:
                return True
            b = int(self.m.body_parentid[b])
        return False


def multi_seed_ik(kin, side, row, qpos, pos, R, seeds=None, n_random=24, rng_seed=0, iters=200, point=None):
    """Best ``pose_ik`` over several arm seeds (the given row first, then fixed random seeds)."""
    rng = np.random.default_rng(rng_seed)
    cols = np.arange(kin.m.nu)[kin.arm_cols[side]]
    lo, hi = kin.lo[cols], kin.hi[cols]
    cands = [NOMINAL[side], np.array(row, float)[cols]] + [np.asarray(x, float) for x in (seeds or [])]
    cands += [NOMINAL[side] + rng.normal(0, 0.4, len(cols)) for _ in range(n_random)]
    best = None
    for c in cands:
        trial = np.array(row, float)
        trial[cols] = np.clip(c, lo, hi)
        out, ep, er = kin.pose_ik(side, trial, qpos, pos, R, iters=iters, point=point)
        score = ep + 0.05 * er + 0.02 * kin.collisions(side, out, qpos) + 0.002 * float(
            np.linalg.norm(out[cols] - NOMINAL[side]))
        if best is None or score < best[0]:
            best = (score, out, ep, er)
        if ep < 1e-4 and er < 1e-3:
            break
    return best[1], best[2], best[3]


AA_INDEX = {"sharpa": {"thumb": (1, 3), "index": (1,), "middle": (1,), "ring": (1,), "pinky": (2,)},
            "wuji": {"thumb": (1,), "index": (1,), "middle": (1,), "ring": (1,), "pinky": (1,)}}


def grasp_cylinder(kin, side, row, qpos, centre_xy, radius, heights, avoid=(), avoid_margin=0.002, max_nfev=200,
                   angle_hint=None, angle_weight=0.0, fix_aa=True):
    """Finger joints only (arm fixed): each fingertip pad centre on the vertical cylinder ``radius`` around
    ``centre_xy`` at the world height ``heights[finger]`` (no angle constraint unless ``angle_hint``)."""
    m, hand = kin.m, kin.s.hand
    row = np.array(row, float)
    fcols = np.arange(m.nu)[kin.finger_cols[side]]
    var = np.asarray([int(fcols[i]) for f in heights for j, i in enumerate(FINGER_COLS[hand][f])
                      if not (fix_aa and f != "thumb" and j in AA_INDEX[hand][f])])
    tipg = {f: tip_geom(m, hand, side, f) for f in heights}
    hand_geoms = [g for g in range(m.ngeom) if kin._in_hand(g, side) and m.geom_contype[g]
                  and g not in tipg.values()]
    seed = row[var].copy()
    c = np.asarray(centre_xy, float)

    def residual(x):
        row[var] = x
        kin.load(qpos, row)
        err = []
        for f, z in heights.items():
            p = kin.d.geom_xpos[tipg[f]]
            rr = math.hypot(p[0] - c[0], p[1] - c[1])
            err += [(rr - radius) * 100, (p[2] - z) * 50]
            if angle_hint and f in angle_hint:
                a = math.atan2(p[1] - c[1], p[0] - c[0])
                err.append(((a - angle_hint[f] + math.pi) % (2 * math.pi) - math.pi) * angle_weight)
        for g in hand_geoms:
            for o in avoid:
                dist = mujoco.mj_geomDistance(m, kin.d, g, o, 0.02, None)
                err.append(min(0.0, dist - avoid_margin) * 300)
        err.extend((x - seed) * 0.01)
        return np.asarray(err)

    lo, hi = kin.lo[var] + 1e-6, kin.hi[var] - 1e-6
    fit = least_squares(residual, np.clip(row[var], lo, hi), bounds=(lo, hi), max_nfev=max_nfev)
    residual(fit.x)
    out = {}
    for f, z in heights.items():
        p = kin.d.geom_xpos[tipg[f]]
        out[f] = (round((math.hypot(p[0] - c[0], p[1] - c[1]) - radius) * 1000, 1), round((p[2] - z) * 1000, 1),
                  round(math.degrees(math.atan2(p[1] - c[1], p[0] - c[0]))))
    return row.copy(), fit.cost, out


def palm_ik(kin, side, row, qpos, point_world, normal_world, palm_point=(0.024, 0.0, 0.05), fingers_pref=None,
            pref_weight=0.2, avoid=(), avoid_margin=0.01, n_seeds=12, rng_seed=0, normal_weight=3.0):
    """Arm joints placing the palm point at ``point_world`` with the palm normal (+X of the hand root) along
    ``normal_world``; rotation about the normal is free (``fingers_pref`` softly prefers a finger direction).
    ``avoid``: world geoms the arm links + hand palm must keep ``avoid_margin`` from (e.g. the worktop)."""
    m = kin.m
    cols = np.arange(m.nu)[kin.arm_cols[side]]
    b = kin.root[side]
    arm_root = m.body({"left": "shoulder_pitch_l_j1_link", "right": "shoulder_pitch_r_j1_link"}[side]).id
    link_geoms = []
    for g in range(m.ngeom):
        if not m.geom_contype[g]:
            continue
        x = int(m.geom_bodyid[g])
        chain = []
        while x > 0 and x != arm_root:
            chain.append(x)
            x = int(m.body_parentid[x])
        # arm links and the palm (not the fingers: they may touch the object)
        name = m.body(int(m.geom_bodyid[g])).name
        if x == arm_root and (int(m.geom_bodyid[g]) == b or b not in chain or name.endswith(("thumb_CMC_VL", "thumb_MC"))):
            link_geoms.append(g)
    n = np.asarray(normal_world, float) / np.linalg.norm(normal_world)
    pp = np.asarray(palm_point, float)
    work = np.array(row, float)

    def residual(x):
        work[cols] = x
        kin.load(qpos, work)
        R = kin.d.xmat[b].reshape(3, 3)
        p = kin.d.xpos[b] + R @ pp
        err = list((p - point_world) * 100) + list(np.cross(R[:, 0], n) * normal_weight) + [
            (1 - R[:, 0] @ n) * normal_weight]
        if fingers_pref is not None:
            err += list((R[:, 2] - fingers_pref) * pref_weight)
        for g in link_geoms:
            for o in avoid:
                dist = mujoco.mj_geomDistance(m, kin.d, g, o, 0.05, None)
                err.append(min(0.0, dist - (avoid_margin if o == avoid[0] else 0.004)) * 100)
        err += list((x - NOMINAL[side]) * 0.02)
        return np.asarray(err)

    rng = np.random.default_rng(rng_seed)
    lo, hi = kin.lo[cols] + 1e-4, kin.hi[cols] - 1e-4
    best = None
    seeds = [np.array(row, float)[cols], NOMINAL[side]] + [NOMINAL[side] + rng.normal(0, 0.5, 7) for _ in range(n_seeds)]
    for s0 in seeds:
        fit = least_squares(residual, np.clip(s0, lo, hi), bounds=(lo, hi), max_nfev=150)
        if best is None or fit.cost < best.cost:
            best = fit
    residual(best.x)
    work[cols] = best.x
    kin.load(qpos, work)
    R = kin.d.xmat[b].reshape(3, 3)
    p = kin.d.xpos[b] + R @ pp
    return work.copy(), float(np.linalg.norm(p - point_world)), float(math.acos(max(-1, min(1, R[:, 0] @ n)))), best.cost
