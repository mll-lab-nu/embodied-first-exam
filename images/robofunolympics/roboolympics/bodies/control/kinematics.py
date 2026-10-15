"""Kinematics library for low-level players of the library's legged robots (optional control library,
bodies/README.md; the "IK library" of the low-level toolkit, agent side): the Unitree G1 (29 joints) and H1-2 (27).

It is self-contained (copied as one file into a player's toolkit): it needs only numpy and mujoco (pip-installable, CPU, deterministic: no random restarts, no threads, a fixed number of
iterations) and the robot-only model (`g1_robot_only.xml`: the floating-base G1, no world, no ball; exported by
pilots/g1_modes/export_model.py from body.robot_only_xml(fixed_base=False)). It knows nothing about any sport or skill.

    from kinematics import Kinematics, layout
    K = Kinematics("g1_robot_only.xml", robot="unitree_g1")      # or "unitree_h1" (layout(robot): joints, groups)
    K.set_state(base_pos, base_quat, q, base_linvel, base_angvel, dq)     # q, dq: the robot's joints in order
    p, R = K.site_pose("right_foot"); c, v = K.com(), K.com_velocity(); Jp, Jr = K.site_jacobian("left_foot")
    tau_g = K.bias()                     # gravity + Coriolis torques at the joints (qfrc_bias), for feed-forward
    q_new, err = K.solve([{"site": "left_foot", "pos": p_l, "R": R_l}, {"site": "right_foot", "pos": p_r, "R": R_r}],
                         base_pos, base_quat, q0, joints=K.groups["legs"])  # damped least squares, base held fixed
    K.min_self_distance()                # the closest self-collision pair (m, < 0: penetrating) at the last pose

Self-collision (bodies/selfcollision.py, real limits B0): a robot model from the library carries its self-collision
pairs (MuJoCo <pair>s named <prefix>selfcol_<i>: arm x body, left x right arm, tool x body). When the model has them,
solve() keeps every pair the solved joints move at least `self_min_dist` apart (default 2 cm): each iteration, the
pairs closer than `self_act_dist` (5 cm) give a distance row J_d = n . (J(p2) - J(p1)) (closest points and the
separating normal from mj_geomDistance, oriented from the first geom's side to the second's; point Jacobians from
mj_jac), and the step is corrected by the smallest change that keeps every such row at or above the minimum (an
active-set projection, damped, a few passes); then a line search on the true distances (halving the step) refuses
any step that brings a pair closer than self_min_dist / 4, so a long step cannot tunnel through a thin link. The
target is reached only as far as the body allows: a target behind the body leaves a position error instead of an
arm through the chest. `avoid_self_collision=False` gives the plain solver (bit-identical to before). Deterministic.
"""
from __future__ import annotations

import numpy as np

DIST_CUT = 0.1   # mj_geomDistance's distmax for the self-collision pairs. MuJoCo 3.3's mesh distance depends on it:
                 # with distmax <= 0.05 it misses a few deep intersections (returns distmax), with distmax >= 0.2 it
                 # returns 0.0 for some pairs centimetres apart; at 0.1 neither happened on 31,040 G1 / H1-2 pair
                 # distances at random arm poses. A reading <= 0 is an intersection (deep hulls read 0.0).

LAYOUTS = {   # legs (left 6, right 6), waist / torso, left arm, right arm: the order of bodies/control/arbiter.py
    "unitree_g1": (("hip_pitch", "hip_roll", "hip_yaw", "knee", "ankle_pitch", "ankle_roll"),
                   ("waist_yaw_joint", "waist_roll_joint", "waist_pitch_joint"),
                   ("shoulder_pitch", "shoulder_roll", "shoulder_yaw", "elbow", "wrist_roll", "wrist_pitch",
                    "wrist_yaw")),
    "unitree_h1": (("hip_yaw", "hip_pitch", "hip_roll", "knee", "ankle_pitch", "ankle_roll"),
                   ("torso_joint",),
                   ("shoulder_pitch", "shoulder_roll", "shoulder_yaw", "elbow_pitch", "elbow_roll", "wrist_pitch",
                    "wrist_yaw")),
}


def layout(robot="unitree_g1"):
    """(joint names, groups {legs, waist, arms: index arrays}) of a legged robot."""
    leg, torso, arm = LAYOUTS[robot]
    joints = [f"{s}_{j}_joint" for s in ("left", "right") for j in leg] + list(torso) + \
        [f"left_{j}_joint" for j in arm] + [f"right_{j}_joint" for j in arm]
    nt = len(torso)
    return joints, {"legs": np.arange(0, 12), "waist": np.arange(12, 12 + nt), "arms": np.arange(12 + nt, len(joints))}


JOINTS, GROUPS = layout("unitree_g1")          # the G1's (the pilot's names)


class Kinematics:
    def __init__(self, xml_path, prefix="", robot="unitree_g1"):
        import mujoco as mj
        self.mj = mj
        self.m = mj.MjModel.from_xml_path(str(xml_path))
        self.d = mj.MjData(self.m)
        m = self.m
        self.joints, self.groups = layout(robot)
        self.nj = len(self.joints)
        jid = [mj.mj_name2id(m, mj.mjtObj.mjOBJ_JOINT, prefix + j) for j in self.joints]
        if min(jid) < 0:
            raise ValueError(f"not a {robot} model ({self.nj} joints)")
        self.qadr = np.array([m.jnt_qposadr[i] for i in jid])
        self.vadr = np.array([m.jnt_dofadr[i] for i in jid])
        self.lo, self.hi = m.jnt_range[jid, 0].copy(), m.jnt_range[jid, 1].copy()
        self.base = mj.mj_name2id(m, mj.mjtObj.mjOBJ_BODY, prefix + "pelvis")
        fj = next(j for j in range(m.njnt) if m.jnt_bodyid[j] == self.base)
        self.fq, self.fv = int(m.jnt_qposadr[fj]), int(m.jnt_dofadr[fj])
        self.prefix = prefix
        self.mass = float(m.body_subtreemass[self.base])
        tag = prefix + "selfcol_"                  # the library's self-collision pairs (bodies/selfcollision.py)
        self.pairs = [(int(m.pair_geom1[i]), int(m.pair_geom2[i])) for i in range(m.npair)
                      if (mj.mj_id2name(m, mj.mjtObj.mjOBJ_PAIR, i) or "").startswith(tag)]

    # ------------------------------------------------------------------ state
    def set_state(self, base_pos, base_quat, q, base_linvel=None, base_angvel=None, dq=None):
        """The robot's state (world frame base, joints in SDK order); computes positions, CoM and bias forces.
        base_linvel / base_angvel: the free joint's velocity (world linear, body-frame angular, as MuJoCo's qvel)."""
        d, mj = self.d, self.mj
        d.qpos[self.fq:self.fq + 3] = base_pos
        d.qpos[self.fq + 3:self.fq + 7] = base_quat
        d.qpos[self.qadr] = q
        d.qvel[:] = 0.0
        if base_linvel is not None:
            d.qvel[self.fv:self.fv + 3] = base_linvel
        if base_angvel is not None:
            d.qvel[self.fv + 3:self.fv + 6] = base_angvel
        if dq is not None:
            d.qvel[self.vadr] = dq
        mj.mj_forward(self.m, d)

    def _sid(self, site):
        i = self.mj.mj_name2id(self.m, self.mj.mjtObj.mjOBJ_SITE, self.prefix + site)
        if i < 0:
            raise ValueError(f"no site {site!r}")
        return i

    def site_pose(self, site):
        i = self._sid(site)
        return self.d.site_xpos[i].copy(), self.d.site_xmat[i].reshape(3, 3).copy()

    def body_pose(self, body):
        i = self.mj.mj_name2id(self.m, self.mj.mjtObj.mjOBJ_BODY, self.prefix + body)
        return self.d.xpos[i].copy(), self.d.xmat[i].reshape(3, 3).copy()

    def com(self):
        return self.d.subtree_com[self.base].copy()

    def com_velocity(self):
        """The centre of mass's world velocity at the set state."""
        self.mj.mj_subtreeVel(self.m, self.d)
        return self.d.subtree_linvel[self.base].copy()

    def site_velocity(self, site):
        """(linear, angular) world velocity of a site at the set state."""
        v = np.zeros(6)
        self.mj.mj_objectVelocity(self.m, self.d, self.mj.mjtObj.mjOBJ_SITE, self._sid(site), v, 0)
        return v[3:].copy(), v[:3].copy()

    def site_jacobian(self, site, joints=None, base=False):
        """(Jp, Jr) of a site: columns for the given joints (indices into the robot's joints; default all), the 6 base dofs first if
        base=True."""
        m = self.m
        jp, jr = np.zeros((3, m.nv)), np.zeros((3, m.nv))
        self.mj.mj_jacSite(m, self.d, jp, jr, self._sid(site))
        cols = self.vadr[np.arange(self.nj) if joints is None else np.asarray(joints)]
        if base:
            cols = np.r_[np.arange(self.fv, self.fv + 6), cols]
        return jp[:, cols], jr[:, cols]

    def bias(self, joints=None):
        """Gravity + Coriolis generalized forces at the joints (MuJoCo qfrc_bias) at the set state."""
        return self.d.qfrc_bias[self.vadr[np.arange(self.nj) if joints is None else np.asarray(joints)]].copy()

    # ------------------------------------------------------------------ inverse kinematics
    def solve(self, targets, base_pos, base_quat, q0, joints=None, iters=10, damping=1e-3, max_step=0.15,
              lo=None, hi=None, avoid_self_collision=None, self_min_dist=0.02, self_act_dist=0.05):
        """Damped-least-squares IK with the base held at (base_pos, base_quat). targets: dicts {site, pos, R (3x3 or
        None: position only), rot_w (1.0)}. Each target moves only the joints of its own chain among `joints`
        (columns where its Jacobian is non-zero), with its step scaled to at most max_step rad per iteration;
        joints stay within [lo, hi] (default the model's ranges). avoid_self_collision (default: on when the model
        has self-collision pairs): every pair stays >= self_min_dist apart (see the module docstring); a pair already
        closer at q0 is pushed apart. Returns (q, position errors per target; with the avoidance, measured at the
        returned q)."""
        mj, m, d = self.mj, self.m, self.d
        joints = np.arange(self.nj) if joints is None else np.asarray(joints)
        lo = self.lo if lo is None else np.asarray(lo, float)
        hi = self.hi if hi is None else np.asarray(hi, float)
        q = np.asarray(q0, float).copy()
        d.qpos[self.fq:self.fq + 3] = base_pos
        d.qpos[self.fq + 3:self.fq + 7] = base_quat
        jp, jr = np.zeros((3, m.nv)), np.zeros((3, m.nv))
        errs = [0.0] * len(targets)
        avoid = bool(self.pairs) if avoid_self_collision is None else bool(avoid_self_collision and self.pairs)
        moving = self._moving_pairs(joints) if avoid else []
        for _ in range(iters):
            d.qpos[self.qadr] = q
            mj.mj_kinematics(m, d)
            mj.mj_comPos(m, d)
            dq_all = np.zeros(self.nj)
            for k, t in enumerate(targets):
                sid = self._sid(t["site"])
                p = d.site_xpos[sid]
                R = d.site_xmat[sid].reshape(3, 3)
                ep = np.asarray(t["pos"], float) - p
                mj.mj_jacSite(m, d, jp, jr, sid)
                Jp, Jr = jp[:, self.vadr[joints]], jr[:, self.vadr[joints]]
                chain = np.nonzero(np.abs(np.vstack([Jp, Jr])).sum(0) > 0)[0]
                if t.get("R") is not None:
                    Rt = np.asarray(t["R"], float)
                    er = 0.5 * (np.cross(R[:, 0], Rt[:, 0]) + np.cross(R[:, 1], Rt[:, 1]) + np.cross(R[:, 2], Rt[:, 2]))
                    e = np.r_[ep, er * t.get("rot_w", 1.0)]
                    J = np.vstack([Jp[:, chain], Jr[:, chain] * t.get("rot_w", 1.0)])
                else:
                    e, J = ep, Jp[:, chain]
                dq = J.T @ np.linalg.solve(J @ J.T + damping * np.eye(len(e)), e)
                n = np.abs(dq).max() if dq.size else 0.0
                if n > max_step:
                    dq *= max_step / n
                dq_all[joints[chain]] += dq
                errs[k] = float(np.linalg.norm(ep))
            if avoid:                              # the step kept apart (linearised), then checked on the geometry
                dq_all[joints] = self._keep_apart(dq_all[joints], joints, self_min_dist, self_act_dist, damping,
                                                  max_step)
                q = self._line_search(q, dq_all, lo, hi, moving, self_min_dist)
                continue
            q = np.clip(q + dq_all, lo, hi)
        if avoid:                                  # the errors at the returned pose
            d.qpos[self.qadr] = q
            mj.mj_kinematics(m, d)
            errs = [float(np.linalg.norm(np.asarray(t["pos"], float) - d.site_xpos[self._sid(t["site"])]))
                    for t in targets]
        return q, errs

    # ------------------------------------------------------------------ self-collision
    def _pair_rows(self, joints, act):
        """(rows J_d over `joints`, distances) of the self-collision pairs closer than act at the current pose."""
        mj, m, d = self.mj, self.m, self.d
        ft = np.zeros(6)
        jp1, jp2 = np.zeros((3, m.nv)), np.zeros((3, m.nv))
        cols = self.vadr[joints]
        rows, dists = [], []
        for g1, g2 in self.pairs:
            dist = mj.mj_geomDistance(m, d, g1, g2, DIST_CUT, ft)
            if dist >= act:
                continue
            p1, p2 = ft[:3].copy(), ft[3:].copy()
            c = d.geom_xpos[g2] - d.geom_xpos[g1]     # geom origins: inside each shape (a mesh is centred on its mass)
            gap = p2 - p1
            if dist > 1e-6 and float(np.linalg.norm(gap)) > 1e-9:
                # MuJoCo 3.3 may give a mesh pair's fromto in the other geom order: of two disjoint convex shapes the
                # separating direction always points from the first's interior towards the second's
                if gap @ c < 0:
                    p1, p2, gap = p2, p1, -gap
                n = gap / float(np.linalg.norm(gap))
            else:                                   # touching or intersecting: push the origins apart
                if float(np.linalg.norm(c)) < 1e-9:
                    continue
                n = c / float(np.linalg.norm(c))
                mid = 0.5 * (p1 + p2) if float(np.linalg.norm(gap)) > 0 else 0.5 * (d.geom_xpos[g1] + d.geom_xpos[g2])
                p1 = p2 = mid
            b1, b2 = int(m.geom_bodyid[g1]), int(m.geom_bodyid[g2])
            mj.mj_jac(m, d, jp1, None, p1, b1)
            mj.mj_jac(m, d, jp2, None, p2, b2)
            row = n @ (jp2[:, cols] - jp1[:, cols])
            if np.abs(row).max() < 1e-9:            # neither geom moves with these joints
                continue
            rows.append(row)
            dists.append(dist)
        return np.array(rows), np.array(dists)

    def _moving_pairs(self, joints):
        """the pairs with a geom moved by `joints` (one geom's body below a solved joint, the other's not, or both on
        different chains)"""
        m = self.m
        jb = {int(m.jnt_bodyid[j]) for j in range(m.njnt) if m.jnt_dofadr[j] in set(self.vadr[joints].tolist())}

        def movers(b):
            out = set()
            while b > 0:
                if b in jb:
                    out.add(b)
                b = int(m.body_parentid[b])
            return out
        return [(g1, g2) for g1, g2 in self.pairs
                if movers(int(m.geom_bodyid[g1])) != movers(int(m.geom_bodyid[g2]))]

    def _min_dist(self, pairs, cut):
        mj, m, d = self.mj, self.m, self.d
        best = cut
        for g1, g2 in pairs:
            best = min(best, mj.mj_geomDistance(m, d, g1, g2, DIST_CUT, None))
        return best

    def _line_search(self, q, dq, lo, hi, pairs, dmin, halvings=5):
        """q + s dq for the largest s in 1, 1/2, ... that brings no pair closer than a quarter of dmin (or, already
        closer, no closer than it is): the linearised step can tunnel through a thin link, and MuJoCo's distance of
        two intersecting hulls can read 0; else q unchanged. (The margin up to dmin is the projection's job.)"""
        mj, m, d = self.mj, self.m, self.d
        d.qpos[self.qadr] = q
        mj.mj_kinematics(m, d)
        floor = min(0.25 * dmin, self._min_dist(pairs, dmin)) - 1e-4
        s = 1.0
        for _ in range(halvings + 1):
            qt = np.clip(q + s * dq, lo, hi)
            d.qpos[self.qadr] = qt
            mj.mj_kinematics(m, d)
            if self._min_dist(pairs, dmin) >= floor:
                mj.mj_comPos(m, d)
                return qt
            s *= 0.5
        d.qpos[self.qadr] = q
        mj.mj_kinematics(m, d)
        mj.mj_comPos(m, d)
        return q

    def _keep_apart(self, dq, joints, dmin, act, damping, max_step, passes=4):
        """The smallest change of the step dq that keeps every close pair's linearised distance >= dmin."""
        A, dist = self._pair_rows(joints, act)
        if not len(A):
            return dq
        b = dmin - dist                             # J_d dq >= dmin - dist
        dq = dq.copy()
        for _ in range(passes):
            viol = A @ dq < b - 1e-6
            if not viol.any():
                break
            Av = A[viol]
            dq += Av.T @ np.linalg.solve(Av @ Av.T + damping * np.eye(len(Av)), b[viol] - Av @ dq)
        n = np.abs(dq).max()
        if n > max_step:
            dq *= max_step / n
        return dq

    def min_self_distance(self, q=None, base_pos=None, base_quat=None):
        """(distance, (geom1, geom2)) of the closest self-collision pair (m; <= 0: intersecting, MuJoCo reads two
        deeply intersecting hulls as 0) at the set state, or
        at joints q (and base) if given. (inf, None) without pairs."""
        mj, m, d = self.mj, self.m, self.d
        if q is not None:
            if base_pos is not None:
                d.qpos[self.fq:self.fq + 3] = base_pos
            if base_quat is not None:
                d.qpos[self.fq + 3:self.fq + 7] = base_quat
            d.qpos[self.qadr] = q
            mj.mj_kinematics(m, d)
        best = (float("inf"), None)
        for g1, g2 in self.pairs:
            x = mj.mj_geomDistance(m, d, g1, g2, DIST_CUT, None)
            if x < best[0]:
                gn = lambda g: mj.mj_id2name(m, mj.mjtObj.mjOBJ_GEOM, g)
                best = (float(x), (gn(g1), gn(g2)))
        return best


G1Kinematics = Kinematics                      # the pilot's name


def export_robot_only(path, meshdir=None, robot="unitree_g1"):
    """Write the robot-only model (floating base, no hand) for this library: the low-level toolkit's model file
    (a developer step in a checkout of the repository: it reads bodies/)."""
    import sys
    from pathlib import Path
    here = Path(__file__).resolve().parent
    sys.path.insert(0, str(here.parents[1]))
    from bodies import load_body
    B = load_body(robot)
    xml = B.robot_only_xml(hand=None, fixed_base=False, meshdir=meshdir,
                           header=f" {B.decl['body']['title']} alone (floating base, no hand): the low-level toolkit's "
                                  "robot model (bodies/control/kinematics.py export_robot_only). ")
    xml = xml.replace(f'model="{robot}_None_robot_only"', f'model="{robot}_robot_only"')
    Path(path).write_text(xml)
    return path
