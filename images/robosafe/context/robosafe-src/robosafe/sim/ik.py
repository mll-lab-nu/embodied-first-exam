"""Inverse kinematics of the arm by damped least squares, always on a scratch copy of the simulation data.

A UR arm reaches most poses in up to eight joint configurations ("branches"). An IK step that lands on another branch
asks the arm to swing through itself; the position servo then drives it at full torque, and a previous project lost
trials to exactly that. So every solution here is checked against the configuration it was seeded from, and one that
lies far away is refused and reported (`reason == "branch_flip"`) instead of being handed to the controller.
"""
from __future__ import annotations

from dataclasses import dataclass

import mujoco
import numpy as np

from . import tf


@dataclass
class IKResult:
    q: np.ndarray           # joint positions (the seed when not ok)
    ok: bool
    reason: str             # "ok" | "not_converged" | "branch_flip" | "joint_limit"
    pos_err: float          # m
    rot_err: float          # rad
    iters: int
    jump: float             # largest joint displacement from the seed, rad

    def __bool__(self) -> bool:
        return self.ok


class IK:
    def __init__(self, world):
        self.model = world.model
        self.site = world.tcp_site
        self.qadr = world._arm_qadr
        self.dadr = world._arm_dadr
        # stay a little inside the joint ranges so that the servo is never asked to sit on a limit
        self.lo = world.arm_range[:, 0] + 0.02
        self.hi = world.arm_range[:, 1] - 0.02
        self.data = mujoco.MjData(self.model)       # scratch: never the live data
        self.data.qpos[:] = world.data.qpos
        self._jp = np.zeros((3, self.model.nv))
        self._jr = np.zeros((3, self.model.nv))
        self._world = world
        # A base that drives: the scratch data has to stand where the base stands now, not where it stood when this
        # solver was made or last tested a posture for collisions (`_place`). None on a robot that is bolted down.
        self._base = world._base_qadr if getattr(world, "base", None) else None
        self.n = world.spec.n
        self.nullspace = float(world.spec.nullspace)
        self._carry = np.array(world.spec.carry_matrix, dtype=np.float64) if world.spec.carry == "parallel" else None
        # pairs of the robot's own bodies that touch in its named postures (neighbouring links, the finger linkage):
        # these never count as the arm running into itself
        self._self_ok: set = set()
        m, d = self.model, self.data
        for q in (world.home, world.ready):
            d.qpos[self.qadr] = q
            mujoco.mj_kinematics(m, d)
            mujoco.mj_collision(m, d)
            for i in range(d.ncon):
                b1, b2 = int(m.geom_bodyid[d.contact[i].geom1]), int(m.geom_bodyid[d.contact[i].geom2])
                if world._body_owner[b1] == "robot" and world._body_owner[b2] == "robot":
                    self._self_ok.add((min(b1, b2), max(b1, b2)))
        # what the robot's bodies are near in its named postures without it being a near miss (the base on the table)
        self._near_ok: set = set()
        flags, margin = int(m.opt.enableflags), float(m.opt.o_margin)
        m.opt.enableflags = flags | int(mujoco.mjtEnableBit.mjENBL_OVERRIDE)
        m.opt.o_margin = 0.02
        try:
            for q in (world.home, world.ready):
                d.qpos[self.qadr] = q
                mujoco.mj_kinematics(m, d)
                mujoco.mj_collision(m, d)
                for i in range(d.ncon):
                    g1, g2 = int(d.contact[i].geom1), int(d.contact[i].geom2)
                    b1, b2 = int(m.geom_bodyid[g1]), int(m.geom_bodyid[g2])
                    for b, g, other in ((b1, g2, b2), (b2, g1, b1)):
                        if world._body_owner[b] == "robot" and other == 0:        # against the table, the pedestal, the floor
                            self._near_ok.add((b, g))
        finally:
            m.opt.enableflags, m.opt.o_margin = flags, margin
        d.qpos[:] = world.data.qpos

    def collision(self, q, ignore=(), carried=(), depth: float = 5e-4, arm_vs_load: bool = False, clearance: float = 0.0) -> tuple[str, str] | None:
        """Would the robot, with its arm at `q`, be inside something? Returns (who, what) or None.

        Everything else (objects, fingers) is taken where it is now, except the objects in `carried`
        (`(name, pose in the tool frame)` pairs), which move with the tool and count as part of the robot: what they
        would run into is reported as `(name, what)`, and their contact with the gripper is not a collision.
        The arm folded onto itself is reported as `("robot", "robot")`.
        Contacts with the names in `ignore` (objects, or single bodies such as `rig/bob_1`) and penetrations
        shallower than `depth` do not count. With `arm_vs_load` a carried object inside a link of the arm (not of the
        hand that holds it) counts too, as `("robot", name)`: a vessel tipped back into the wrist. With `clearance`
        (m) the hand and its load must stay that far from everything else, not merely out of it: a way that only
        just misses something does not miss it once the arm trails its targets by a hundredth of a radian. (The
        arm's own links may pass closer: next to a tall cabinet they have to.)
        Computed on the scratch data.
        """
        w, m, d = self._world, self.model, self.data
        d.qpos[:] = w.data.qpos
        d.qpos[self.qadr] = q
        mujoco.mj_kinematics(m, d)
        moving = {"robot"}
        if carried:
            tool = (d.site_xpos[self.site].copy(), tf.mat_to_quat(d.site_xmat[self.site].reshape(3, 3)))
            for name, rel in carried:
                adr = int(m.jnt_qposadr[m.body_jntadr[w.objects[name]["body_id"]]])
                pos, quat = tf.compose(tool, rel)
                d.qpos[adr:adr + 3], d.qpos[adr + 3:adr + 7] = pos, quat
                moving.add(name)
            mujoco.mj_kinematics(m, d)
        if clearance > 0.0:                               # contacts are then reported from that distance on
            flags, margin = int(m.opt.enableflags), float(m.opt.o_margin)
            m.opt.enableflags = flags | int(mujoco.mjtEnableBit.mjENBL_OVERRIDE)
            m.opt.o_margin = clearance
            try:
                mujoco.mj_collision(m, d)
            finally:
                m.opt.enableflags, m.opt.o_margin = flags, margin
        else:
            mujoco.mj_collision(m, d)
        for i in range(d.ncon):
            c = d.contact[i]
            if c.dist > -depth:
                if not (clearance > 0.0 and c.dist < clearance):
                    continue
                g1, g2 = int(c.geom1), int(c.geom2)
                if (int(m.geom_bodyid[g1]), g2) in self._near_ok or (int(m.geom_bodyid[g2]), g1) in self._near_ok:
                    continue                              # the base standing on the table is not a near miss
                near = [int(m.geom_bodyid[g]) for g in (g1, g2)]
                if not any(w._body_owner[b] in moving and (w._body_owner[b] != "robot" or b in w._hand_bodies) for b in near):
                    continue                              # the clearance is for the hand and its load; the arm's links may pass close
            owners, bodies = [], []
            for g in (int(c.geom1), int(c.geom2)):
                b = int(m.geom_bodyid[g])
                owners.append(w._body_owner[b] if b else w.static_owner(m.geom(g).name))
                bodies.append(m.body(b).name)
            if (owners[0] in moving) == (owners[1] in moving):
                if c.dist > -depth:
                    continue                              # the arm against itself and its load: only when inside
                b1, b2 = int(m.geom_bodyid[int(c.geom1)]), int(m.geom_bodyid[int(c.geom2)])
                if owners[0] == owners[1] == "robot":     # the arm folded onto itself (the hand's own linkage aside)
                    if not (b1 in w._hand_bodies and b2 in w._hand_bodies) and (min(b1, b2), max(b1, b2)) not in self._self_ok:
                        return ("robot", "robot")
                elif arm_vs_load and "robot" in owners:
                    k = owners.index("robot")
                    if (b1 if k == 0 else b2) not in w._hand_bodies and owners[1 - k] not in ignore:
                        return ("robot", owners[1 - k])
                continue                                  # otherwise only what moves against what does not
            k = 1 if owners[0] in moving else 0
            if owners[k] not in ignore and bodies[k] not in ignore:
                return (owners[1 - k], owners[k])
        return None

    def first_collision(self, configs, ignore=(), carried=(), arm_vs_load: bool = False, clearance: float = 0.0) -> tuple[str, str] | None:
        for q in configs:
            hit = self.collision(q, ignore, carried, arm_vs_load=arm_vs_load, clearance=clearance)
            if hit is not None:
                return hit
        return None

    def _place(self) -> None:
        if self._base is not None:
            self.data.qpos[self._base] = self._world.data.qpos[self._base]

    def fk(self, q) -> tf.Pose:
        """Tool pose for arm joint positions `q`."""
        d = self.data
        self._place()
        d.qpos[self.qadr] = q
        mujoco.mj_kinematics(self.model, d)
        return (d.site_xpos[self.site].copy(), tf.mat_to_quat(d.site_xmat[self.site].reshape(3, 3)))

    def jacobian(self, q) -> np.ndarray:
        d = self.data
        self._place()
        d.qpos[self.qadr] = q
        mujoco.mj_kinematics(self.model, d)
        mujoco.mj_comPos(self.model, d)
        mujoco.mj_jacSite(self.model, d, self._jp, self._jr, self.site)
        return np.vstack([self._jp[:, self.dadr], self._jr[:, self.dadr]])

    def solve(self, pos, quat, q_seed, *, max_jump: float = 0.6, pos_tol: float = 2e-5, rot_tol: float = 2e-4,
              damping: float = 1e-3, max_iters: int = 100, max_step: float = 0.2) -> IKResult:
        """Find joint positions near `q_seed` that put the tool at (`pos`, `quat`).

        Damped least squares with the damping growing with the error (Levenberg-Marquardt style): far from the goal
        or near a singularity the step is short and safe, close to the goal it is a Newton step.
        `max_jump`: the largest joint displacement from the seed that is accepted (rad). Callers that move far split
        the way into short steps (`solve_path`) so that this bound can stay tight.
        """
        pos = np.asarray(pos, dtype=np.float64)
        quat = tf.unit(quat)
        seed = np.array(q_seed, dtype=np.float64)
        q = seed.copy()
        d = self.data
        pe = re = float("inf")
        it = 0
        for it in range(1, max_iters + 1):
            jac = self.jacobian(q)
            ep = pos - d.site_xpos[self.site]
            er = tf.rotvec(tf.mat_to_quat(d.site_xmat[self.site].reshape(3, 3)), quat)
            pe, re = float(np.linalg.norm(ep)), float(np.linalg.norm(er))
            if pe < pos_tol and re < rot_tol:
                break
            err = np.concatenate([ep, er])
            lam2 = damping * damping + 0.05 * float(err @ err)
            dq = jac.T @ np.linalg.solve(jac @ jac.T + lam2 * np.eye(6), err)
            if self.nullspace > 0.0:                  # a redundant arm: what the task leaves free goes back towards the seed
                pull = self.nullspace * (seed - q)
                dq = dq + pull - jac.T @ np.linalg.solve(jac @ jac.T + lam2 * np.eye(6), jac @ pull)
            big = float(np.max(np.abs(dq)))
            if big > max_step:
                dq *= max_step / big
            q = q + dq
        else:
            p, r = self.fk(q)
            pe, re = float(np.linalg.norm(pos - p)), float(np.linalg.norm(tf.rotvec(r, quat)))
        jump = float(np.max(np.abs(q - seed)))
        if not (pe < pos_tol and re < rot_tol):
            return IKResult(seed, False, "not_converged", pe, re, it, jump)
        if np.any(q < self.lo) or np.any(q > self.hi):
            return IKResult(seed, False, "joint_limit", pe, re, it, jump)
        if jump > max_jump:
            return IKResult(seed, False, "branch_flip", pe, re, it, jump)
        return IKResult(q, True, "ok", pe, re, it, jump)

    def solve_path(self, poses, q_seed, *, max_jump: float = 0.35) -> tuple[np.ndarray, IKResult]:
        """Solve a sequence of nearby tool poses, each seeded by the solution before it.

        Returns the joint positions found so far (one row per pose solved) and the last result; when that result is
        not ok the path stops there.
        """
        q = np.array(q_seed, dtype=np.float64)
        out = []
        res = IKResult(q, True, "ok", 0.0, 0.0, 0, 0.0)
        for p, r in poses:
            res = self.solve(p, r, q, max_jump=max_jump)
            if not res.ok:
                break
            q = res.q
            out.append(q)
        return (np.array(out).reshape(-1, len(q)), res)

    # ---- level carry: position only, with the joints that cannot tip what is held ---------------------------------
    # Columns: shoulder pan; shoulder lift with wrist_1 turned back by as much; elbow likewise. The pan turns the
    # whole arm about the vertical; lift, elbow and wrist_1 have parallel axes, so with their sum unchanged the tool
    # does not rotate at all. Wrist_2 and wrist_3 stay as they are, which makes this indifferent to the wrist
    # singularity (tool axis square to the arm plane) where the full solver loses a direction.
    # An arm without three such joints (`RobotSpec.carry == "general"`) is held level by the solver instead: the
    # carried point is brought to the target while the tool turns about the vertical only (five constraints).

    def carried_point(self, q, offset=None) -> np.ndarray:
        """World position of a point fixed to the tool (`offset` in the tool frame; default: the tool centre point)."""
        pos, quat = self.fk(q)
        return pos if offset is None else pos + tf.rotate(quat, offset)

    def solve_carry(self, target, q_seed, offset=None, *, max_jump: float = 0.35, pos_tol: float = 2e-5,
                    max_iters: int = 60, max_step: float = 0.2, level=None) -> IKResult:
        """Joint positions near `q_seed` that bring a point fixed to the tool to `target` without tilting the tool.

        Only the shoulder pan, the shoulder lift and the elbow are free; wrist_1 undoes the turn of lift and elbow.
        Whatever is held keeps its angle to the vertical exactly and turns about the vertical with the pan.
        """
        target = np.asarray(target, dtype=np.float64)
        seed = np.array(q_seed, dtype=np.float64)
        q = seed.copy()
        d = self.data
        pe = float("inf")
        it = 0
        up_in_tool = None
        if self._carry is None:                       # the vertical as the tool sees it at the seed: this is kept
            if level is None:
                self.fk(seed)
                level = d.site_xmat[self.site].reshape(3, 3).T @ np.array([0.0, 0.0, 1.0])
            up_in_tool = np.asarray(level, dtype=np.float64)
        for it in range(1, max_iters + 1):
            jac = self.jacobian(q)
            p = d.site_xpos[self.site].copy()
            jp = jac[:3]
            if offset is not None:
                r = d.site_xmat[self.site].reshape(3, 3) @ np.asarray(offset, dtype=np.float64)
                p = p + r
                jp = jp - np.cross(r[:, None], jac[3:], axis=0)      # velocity of the offset point: v + w x r
            e = target - p
            pe = float(np.linalg.norm(e))
            if self._carry is None:
                tilt = np.cross(d.site_xmat[self.site].reshape(3, 3) @ up_in_tool, [0.0, 0.0, 1.0])   # turn that brings it upright again
                te = float(np.linalg.norm(tilt[:2]))
                if pe < pos_tol and te < 1e-4:
                    break
                a = np.vstack([jp, jac[3:5]])
                err = np.concatenate([e, tilt[:2]])
                dq = a.T @ np.linalg.solve(a @ a.T + (1e-8 + 0.05 * float(err @ err)) * np.eye(5), err)
                big = float(np.max(np.abs(dq)))
                if big > max_step:
                    dq *= max_step / big
                q = q + dq
                continue
            if pe < pos_tol:
                break
            a = jp @ self._carry
            u = np.linalg.solve(a.T @ a + (1e-8 + 0.05 * pe * pe) * np.eye(3), a.T @ e)
            big = float(np.max(np.abs(u)))
            if big > max_step:
                u *= max_step / big
            q = q + self._carry @ u
        else:
            pe = float(np.linalg.norm(target - self.carried_point(q, offset)))
        jump = float(np.max(np.abs(q - seed)))
        if not pe < pos_tol:
            return IKResult(seed, False, "not_converged", pe, 0.0, it, jump)
        if np.any(q < self.lo) or np.any(q > self.hi):
            return IKResult(seed, False, "joint_limit", pe, 0.0, it, jump)
        if jump > max_jump:
            return IKResult(seed, False, "branch_flip", pe, 0.0, it, jump)
        return IKResult(q, True, "ok", pe, 0.0, it, jump)

    def carry_path(self, targets, q_seed, offset=None, step: float = 0.004) -> tuple[np.ndarray, IKResult]:
        """Straight lines of the carried point through `targets`, solved every `step` metres. Returns the joint path
        (start included) and the last result; when that is not ok the path stops there."""
        q = np.array(q_seed, dtype=np.float64)
        out = [q.copy()]
        res = IKResult(q, True, "ok", 0.0, 0.0, 0, 0.0)
        at = self.carried_point(q, offset)
        level = None
        if self._carry is None:                       # one reference for the whole way, so that nothing drifts
            level = self.data.site_xmat[self.site].reshape(3, 3).T @ np.array([0.0, 0.0, 1.0])
        for target in targets:
            target = np.asarray(target, dtype=np.float64)
            n = max(int(np.ceil(float(np.linalg.norm(target - at)) / step)), 1)
            for k in range(1, n + 1):
                res = self.solve_carry(at + (target - at) * (k / n), q, offset, level=level)
                if not res.ok:
                    return np.array(out), res
                q = res.q
                out.append(q)
            at = target
        return np.array(out), res


def interpolate_poses(a: tf.Pose, b: tf.Pose, n: int) -> list[tf.Pose]:
    """`n` poses from just after `a` to `b` inclusive: straight line for the position, slerp for the orientation."""
    return [(a[0] + (b[0] - a[0]) * (k / n), tf.slerp(a[1], b[1], k / n)) for k in range(1, n + 1)]
