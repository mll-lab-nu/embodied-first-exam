"""Authoring-only helpers (not shipped to tasks): Marvin arm IK, least-squares fingertip grasps, gravity feed-forward.

Everything here computes actuator targets from the simulator state; nothing writes object state during an episode.
"""

from __future__ import annotations

import mujoco
import numpy as np
from scipy.optimize import least_squares

from scene import arm_rig

FINGERS = ("thumb", "index", "middle", "ring", "pinky")


def frame(R, p):
    T = np.eye(4)
    T[:3, :3], T[:3, 3] = R, p
    return T


class Rig:
    """Index bookkeeping for the two arm-mounted hands of a compiled model."""

    def __init__(self, model, data, hand="sharpa"):
        m = self.m = model
        self.d = data
        self.hand = hand
        self.scratch = mujoco.MjData(m)
        self.lay = arm_rig.layout(m)
        self.lo, self.hi = m.actuator_ctrlrange.T
        self.act_joint = m.actuator_trnid[:, 0]
        self.act_qadr = m.jnt_qposadr[self.act_joint]
        self.act_dof = m.jnt_dofadr[self.act_joint]
        self.gain = m.actuator_gainprm[:, 0].copy()
        mounts = arm_rig._mount_names(m)
        self.root = {side: m.body(mounts[i]).id for i, side in enumerate(arm_rig.SIDES)}
        self.arm = {side: np.arange(self.lay["arm"][side].start, self.lay["arm"][side].stop) for side in arm_rig.SIDES}
        self.fing = {side: np.arange(self.lay["fingers"][side].start, self.lay["fingers"][side].stop)
                     for side in arm_rig.SIDES}
        self.groups = {}
        self.tips = {}
        for side in arm_rig.SIDES:
            groups = {f: [] for f in FINGERS}
            for a in self.fing[side]:
                name = m.joint(int(self.act_joint[a])).name.lower()
                for f in FINGERS:
                    if f in name:
                        groups[f].append(int(a))
                        break
            self.groups[side] = {f: np.array(v, dtype=int) for f, v in groups.items()}
            if hand == "sharpa":
                self.tips[side] = {f: m.geom(f"{side}_{f}_fingertip_collision").id for f in FINGERS}
            else:
                p_ = side[0]
                names = {"thumb": "thumb", "index": "index_finger", "middle": "middle_finger",
                         "ring": "ring_finger", "pinky": "pinky"}
                self.tips[side] = {f: m.geom(f"{p_}_wuji_{p_}_{n}_tip_sensor_frame_collision1").id
                                   for f, n in names.items()}
                self.tip_site = getattr(self, "tip_site", {})
                self.tip_site[side] = {f: m.site(f"{p_}_wuji_{p_}_{n}_tip").id for f, n in names.items()}
                self.distal = getattr(self, "distal", {})
                self.distal[side] = {f: m.body(f"{p_}_wuji_{p_}_{n}_distal").id for f, n in names.items()}
        self.hand_bodies = {side: arm_rig.hand_body_ids(m, side) for side in arm_rig.SIDES}

    # ------------------------------------------------------------------ poses
    def hand_pose(self, side, d=None):
        d = d or self.d
        return frame(d.xmat[self.root[side]].reshape(3, 3).copy(), d.xpos[self.root[side]].copy())

    def body_pose(self, body, d=None):
        d = d or self.d
        b = self.m.body(body).id
        return frame(d.xmat[b].reshape(3, 3).copy(), d.xpos[b].copy())

    def tip_end(self, side, f, d):
        if self.hand != "sharpa":
            end = d.site_xpos[self.tip_site[side][f]].copy()
            axis = end - d.xpos[self.distal[side][f]]
            return end, axis / np.linalg.norm(axis)
        g = self.tips[side][f]
        axis = d.geom_xmat[g].reshape(3, 3)[:, 2]
        return d.geom_xpos[g] + axis * self.m.geom_size[g, 1], axis

    def tip_radius(self, side, f):
        """Pad radius of the fingertip end sphere (Sharpa capsule radius; Wuji: an effective pad radius)."""
        return float(self.m.geom_size[self.tips[side][f], 0]) if self.hand == "sharpa" else 0.007

    # ------------------------------------------------------------------ commands
    def command(self, target, boost=2.0):
        """Actuator row for joint targets ``target``: gravity/bias feed-forward on every servo, plus a finger
        boost toward the target (as the wave-2 controllers)."""
        d = self.d
        action = target + d.qfrc_bias[self.act_dof] / self.gain
        f = np.r_[self.fing["left"], self.fing["right"]]
        action[f] += boost * (target[f] - d.qpos[self.act_qadr[f]])
        return np.clip(action, self.lo, self.hi)

    # ------------------------------------------------------------------ inverse kinematics
    def ik(self, side, R_goal, p_goal, q, iters=200, tol=1e-5, rot_w=0.3, lam=0.02, offset=None):
        """Damped least squares on the 7 arm joints of ``side`` so the hand root frame (or the point ``offset`` in
        it) reaches (R_goal, p_goal). ``q`` is a full joint-target vector (actuator order); returns a copy."""
        m, d = self.m, self.scratch
        q = q.copy()
        d.qpos[:] = self.d.qpos
        idx = self.arm[side]
        dofs = self.act_dof[idx]
        lo, hi = self.lo[idx], self.hi[idx]
        jp, jr = np.zeros((3, m.nv)), np.zeros((3, m.nv))
        off = np.zeros(3) if offset is None else np.asarray(offset, float)
        for _ in range(iters):
            d.qpos[self.act_qadr] = q
            mujoco.mj_kinematics(m, d)
            mujoco.mj_comPos(m, d)
            b = self.root[side]
            R = d.xmat[b].reshape(3, 3)
            p = d.xpos[b] + R @ off
            mujoco.mj_jac(m, d, jp, jr, p, b)
            e_p = p_goal - p
            e_r = 0.5 * sum(np.cross(R[:, i], R_goal[:, i]) for i in range(3))
            err = np.r_[e_p, rot_w * e_r]
            if np.linalg.norm(err) < tol:
                break
            J = np.vstack([jp[:, dofs], rot_w * jr[:, dofs]])
            dq = J.T @ np.linalg.solve(J @ J.T + lam**2 * np.eye(6), err)
            q[idx] = np.clip(q[idx] + dq, lo, hi)
        return q, float(np.linalg.norm(err))

    def grasp(self, side, R_goal, faces, seed, clearance, fingers=("thumb", "index", "middle"), obstacles=(),
              rot_weight=0.3, axis_weight=0.3, tilt=None, nfev=400, avoid=0.003, joint_margin=0.6):
        """Least-squares arm + finger targets: each fingertip capsule end sphere touches ``faces[f] = (point,
        normal)`` (world; normal points out of the object toward the finger) at ``clearance`` (negative =
        squeeze), the hand root orientation stays near ``R_goal``, other hand geoms keep ``avoid`` from
        ``obstacles``. ``tilt[f]`` optionally gives the desired distal-pad direction (tip -> base)."""
        m, d = self.m, self.scratch
        # Finger abduction (MCP_AA) of the long fingers stays fixed: free abduction lets a pinching index cross
        # into the middle finger.
        fvars = [a for f in fingers for a in self.groups[side][f]
                 if f == "thumb" or not ("AA" in m.joint(int(self.act_joint[a])).name
                                         or "abd" in m.joint(int(self.act_joint[a])).name)]
        var = np.r_[self.arm[side], np.asarray(fvars, dtype=int)]
        q = seed.copy()
        lo, hi = self.lo[var] + 1e-6, self.hi[var] - 1e-6
        x0 = np.clip(q[var], lo, hi)
        tipset = {self.tips[side][f] for f in FINGERS}
        others = [g for g in range(m.ngeom) if int(m.geom_bodyid[g]) in self.hand_bodies[side] and m.geom_contype[g]
                  and g not in tipset]
        idle_tips = [self.tips[side][f] for f in FINGERS if f not in fingers]

        def residual(x):
            q[var] = x
            d.qpos[:] = self.d.qpos
            d.qpos[self.act_qadr] = q
            mujoco.mj_kinematics(m, d)
            mujoco.mj_comPos(m, d)
            err = []
            for f in fingers:
                point, normal = faces[f]
                g = self.tips[side][f]
                end, axis = self.tip_end(side, f, d)
                goal = np.asarray(point) + np.asarray(normal) * (self.tip_radius(side, f) + clearance)
                err.extend((end - goal) * 300)
                if tilt is not None and f in tilt:
                    err.extend((-axis - tilt[f]) * axis_weight)
            R = d.xmat[self.root[side]].reshape(3, 3)
            err.extend((R - R_goal).ravel() * rot_weight)
            active = [self.tips[side][f] for f in fingers] if clearance >= 0 else []
            for g in others + idle_tips + active:
                margin = (clearance - 0.0015) if g in active else avoid
                for o in obstacles:
                    # Bounding-sphere prefilter (the counter plane/box has a large rbound).
                    if (np.linalg.norm(d.geom_xpos[g] - d.geom_xpos[o]) > m.geom_rbound[g] + m.geom_rbound[o] + 0.01
                            and m.geom_rbound[o] > 0):
                        err.append(0.0)
                        continue
                    dist = mujoco.mj_geomDistance(m, d, g, o, 0.01 + max(margin, 0), None)
                    err.append(min(0.0, dist - margin) * 300)
            err.extend((x - x0) * 0.01)
            # Keep the arm joints off their limits (room for the task's later motions).
            qa = q[self.arm[side]]
            margin = np.minimum(qa - self.lo[self.arm[side]], self.hi[self.arm[side]] - qa)
            err.extend(np.maximum(0.0, joint_margin - margin) * 0.3)
            return np.asarray(err)

        fit = least_squares(residual, x0, bounds=(lo, hi), max_nfev=nfev)
        residual(fit.x)
        return q.copy(), float(fit.cost)
