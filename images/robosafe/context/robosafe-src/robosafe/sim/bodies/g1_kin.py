"""Kinematics of the gliding G1's arms for measuring and for a scripted controller: a Jacobian inverse kinematics
(damped least squares, joint limits by clipping, several seeds) and collision tests by MuJoCo's own contact detection.

It works on a `mujoco.MjData` of its own, so solving never touches a simulation that is running. Nothing here is the
bench's solver (`robosafe.sim.ik`), which needs a `World`; this one needs only the model `g1_glide.build` returns.
"""
from __future__ import annotations

import mujoco
import numpy as np

from . import g1_glide as _g1


def unit(v) -> np.ndarray:
    v = np.asarray(v, dtype=np.float64)
    return v / np.linalg.norm(v)


def frame(z, y) -> np.ndarray:
    """A rotation matrix from the direction the hand points in (`z`) and the direction its fingers close along (`y`,
    made square to `z`)."""
    z = unit(z)
    y = unit(np.asarray(y, dtype=np.float64) - np.dot(y, z) * z)
    return np.stack([np.cross(y, z), y, z], axis=1)


class Chain:
    """One arm (with the waist joints the model kept, if `waist`) as a chain to solve for."""

    def __init__(self, m: mujoco.MjModel, ix: dict, side: str, waist: bool = True, limit_margin: float = 0.02):
        self.m, self.ix, self.side = m, ix, side
        self.d = mujoco.MjData(m)
        a = ix["arms"][side]
        self.arm = a
        use_waist = waist and len(ix["waist_q"]) > 0
        self.q_adr = np.concatenate([ix["waist_q"], a["q"]]).astype(int) if use_waist else np.asarray(a["q"], dtype=int)
        self.v_adr = np.concatenate([ix["waist_v"], a["v"]]).astype(int) if use_waist else np.asarray(a["v"], dtype=int)
        self.n_waist = len(ix["waist_q"]) if use_waist else 0
        jid = [int(np.where(m.jnt_qposadr == q)[0][0]) for q in self.q_adr]
        self.lo = np.array([m.jnt_range[j][0] for j in jid]) + limit_margin
        self.hi = np.array([m.jnt_range[j][1] for j in jid]) - limit_margin
        self.site = a["pinch"]
        self._jp, self._jr = np.zeros((3, m.nv)), np.zeros((3, m.nv))
        other = "right" if side == "left" else "left"
        self.own = a["bodies"]                       # this arm's bodies
        self.hand = a["hand_bodies"]
        self.other = ix["arms"][other]["bodies"]
        mujoco.mj_forward(m, self.d)

    # ---- state ------------------------------------------------------------------------------------------------------------
    def put(self, q) -> None:
        self.d.qpos[self.q_adr] = q
        mujoco.mj_kinematics(self.m, self.d)
        mujoco.mj_comPos(self.m, self.d)

    def get(self) -> np.ndarray:
        return self.d.qpos[self.q_adr].copy()

    def pose(self):
        return self.d.site_xpos[self.site].copy(), self.d.site_xmat[self.site].reshape(3, 3).copy()

    def jacobian(self) -> np.ndarray:
        mujoco.mj_jacSite(self.m, self.d, self._jp, self._jr, self.site)
        return np.vstack([self._jp[:, self.v_adr], self._jr[:, self.v_adr]])

    def clip(self, q) -> np.ndarray:
        return np.clip(q, self.lo, self.hi)

    # ---- inverse kinematics -------------------------------------------------------------------------------------------------
    def solve(self, pos, rot=None, z=None, seed=None, iters: int = 120, damping: float = 0.05, tol_pos: float = 1e-3,
              tol_rot: float = 0.01, pull: float = 0.0):
        """Joint values that put the pinch point at `pos` (world frame) with the hand's frame equal to `rot`, or, with
        `z` instead, with the hand pointing along `z` and turned about that direction as it likes. None if this seed
        does not get there. `pull`: how strongly what the task leaves free is drawn back to the seed."""
        pos = np.asarray(pos, dtype=np.float64)
        q = self.clip(self.get() if seed is None else np.asarray(seed, dtype=np.float64))
        q0 = q.copy()
        n = len(q)
        best, since = np.inf, 0
        for _ in range(iters):
            self.put(q)
            p, r = self.pose()
            ep = pos - p
            if rot is not None:
                ew = 0.5 * (np.cross(r[:, 0], rot[:, 0]) + np.cross(r[:, 1], rot[:, 1]) + np.cross(r[:, 2], rot[:, 2]))
                if np.trace(r.T @ rot) < -0.9 and np.linalg.norm(ew) < 1e-3:      # half a turn away: any axis will do to start
                    ew = r[:, 0] * 0.5
            else:
                ew = np.cross(r[:, 2], z)
                if float(r[:, 2] @ z) < 0.0:                    # more than a quarter turn away: full speed about that axis
                    k = np.linalg.norm(ew)
                    ew = ew / k if k > 1e-6 else r[:, 0]
            if np.linalg.norm(ep) < tol_pos and np.linalg.norm(ew) < tol_rot and (rot is not None or float(r[:, 2] @ z) > 0.0):
                return q
            err = float(np.linalg.norm(ep) + 0.1 * np.linalg.norm(ew))
            if err < 0.98 * best:                               # still getting nearer
                best, since = err, 0
            else:
                since += 1
                if since >= 12:                                 # stuck (a joint limit, or out of reach): this seed will not do
                    return None
            J = self.jacobian()
            if rot is None:                                     # the turn about the hand's own axis is free
                J[3:] = (np.eye(3) - np.outer(r[:, 2], r[:, 2])) @ J[3:]
            kp, kw = np.linalg.norm(ep), np.linalg.norm(ew)
            e = np.concatenate([ep * min(1.0, 0.08 / max(kp, 1e-9)), ew * min(1.0, 0.4 / max(kw, 1e-9))])
            JJ = J @ J.T + damping ** 2 * np.eye(6)
            dq = J.T @ np.linalg.solve(JJ, e)
            if pull > 0.0:
                dq += pull * (np.eye(n) - J.T @ np.linalg.solve(JJ, J)) @ (q0 - q)
            q = self.clip(q + dq)
        return None

    def solve_any(self, pos, rot=None, z=None, seeds=(), check=None, **kw):
        """The first seed's solution that passes `check(q)` (default: any). Returns (q or None, how many seeds solved)."""
        solved = 0
        for seed in seeds:
            q = self.solve(pos, rot=rot, z=z, seed=seed, **kw)
            if q is None:
                continue
            solved += 1
            if check is None or check(q):
                return q, solved
        return None, solved

    def manipulability(self, q) -> float:
        """The smallest singular value of the pinch point's Jacobian at `q`."""
        self.put(q)
        return float(np.linalg.svd(self.jacobian(), compute_uv=False)[-1])

    # ---- collisions ---------------------------------------------------------------------------------------------------------
    def touching(self, q=None, ignore_bodies=()) -> list:
        """Pairs (owner, owner, distance) of everything this arm (and, with the waist in the chain, whatever the waist
        moves) is nearer to than the geoms' margins: another part of the robot, the floor, furniture. Contacts between
        things that are not the robot, and with the bodies named in `ignore_bodies` (a thing held), are left out."""
        if q is not None:
            self.put(q)
        m, d = self.m, self.d
        mujoco.mj_collision(m, d)
        robot = self.ix["bodies"]
        skip = {m.body(n).id for n in ignore_bodies}
        out = []
        for i in range(d.ncon):
            c = d.contact[i]
            b1, b2 = int(m.geom_bodyid[c.geom1]), int(m.geom_bodyid[c.geom2])
            if b1 in skip or b2 in skip or (b1 not in robot and b2 not in robot):
                continue
            # two links of an arm with one link between them stand a few millimetres apart by construction (the
            # wrist's roll and yaw links): for them only overlap counts
            if c.dist >= 0.0 and b1 in robot and b2 in robot and self._two_apart(b1, b2):
                continue
            out.append((self._owner(b1, int(c.geom1)), self._owner(b2, int(c.geom2)), float(c.dist)))
        return out

    def free(self, q=None, ignore_bodies=()) -> bool:
        return not self.touching(q, ignore_bodies)

    def _two_apart(self, b1: int, b2: int) -> bool:
        p = self.m.body_parentid
        return int(p[int(p[b1])]) == b2 or int(p[int(p[b2])]) == b1

    def _owner(self, b: int, g: int) -> str:
        m = self.m
        if b in self.hand:
            return f"{self.side}_hand"
        if b in self.own:
            return f"{self.side}_arm"
        if b in self.other:
            return "other_arm"
        if b in self.ix["bodies"]:
            name = m.body(b).name
            return "legs" if any(k in name for k in ("hip", "knee", "ankle")) else ("torso" if "torso" in name or "waist" in name else name)
        return m.geom(g).name or m.body(b).name


def set_margin(m: mujoco.MjModel, ix: dict, clearance: float) -> None:
    """Make MuJoCo report the robot's shapes as touching from `clearance` away (on this model: use a model of your own).
    Since MuJoCo 3.5 the margins of two geoms are summed, not maxed, so a margin on every geom of the robot would make
    two parts of the robot touch from twice `clearance`; the model-wide override gives every pair exactly `clearance`
    (`touching` leaves out pairs without a part of the robot). The override also replaces the contacts' solref, solimp
    and friction, so such a model is for collision tests, not for stepping. The geoms' own margins are set as well."""
    for g in range(m.ngeom):
        if int(m.geom_bodyid[g]) in ix["bodies"] and m.geom_contype[g]:
            m.geom_margin[g] = clearance
    m.opt.enableflags |= int(mujoco.mjtEnableBit.mjENBL_OVERRIDE)
    m.opt.o_margin = clearance


def seeds_for(chain: Chain, rng: np.random.Generator, n_random: int = 6, named=()) -> list:
    """Starting postures for the solver: the named ones first, then random ones within the limits."""
    out = [np.asarray(q, dtype=np.float64) for q in named]
    out += [rng.uniform(chain.lo, chain.hi) for _ in range(n_random)]
    return out


def arm_seed(chain: Chain, q7) -> np.ndarray:
    """An arm posture as a seed of the chain (waist joints, if any, at zero)."""
    return np.concatenate([np.zeros(chain.n_waist), np.asarray(q7 if chain.side == "left" else _g1.mirror(q7), dtype=np.float64)])


def line_free(chain: Chain, q0, q1, res: float = 0.02, ignore_bodies=()) -> bool:
    """Whether the straight line in joint space from `q0` to `q1` is free, tested every `res` radians of the joint
    that moves most."""
    q0, q1 = np.asarray(q0, dtype=np.float64), np.asarray(q1, dtype=np.float64)
    n = max(1, int(np.ceil(float(np.max(np.abs(q1 - q0))) / res)))
    return all(chain.free(q0 + (q1 - q0) * k / n, ignore_bodies) for k in range(n + 1))


def find_path(chain: Chain, q0, q1, rng: np.random.Generator, ignore_bodies=(), step: float = 0.35, tries: int = 1500):
    """Postures to pass through from `q0` to `q1` on free straight lines in joint space, both ends included: the line
    itself if it is free, else two trees grown towards each other from the two ends (RRT-connect) and the way through
    them shortened. None if no way was found."""
    q0, q1 = np.asarray(q0, dtype=np.float64), np.asarray(q1, dtype=np.float64)
    if line_free(chain, q0, q1, ignore_bodies=ignore_bodies):
        return [q0, q1]
    if not chain.free(q0, ignore_bodies) or not chain.free(q1, ignore_bodies):
        return None
    trees = [([q0], [-1]), ([q1], [-1])]

    def extend(tree, target):
        nodes, parents = tree
        i = int(np.argmin([np.max(np.abs(n - target)) for n in nodes]))
        d = target - nodes[i]
        far = float(np.max(np.abs(d)))
        new = target if far <= step else nodes[i] + d * (step / far)
        if not line_free(chain, nodes[i], new, ignore_bodies=ignore_bodies):
            return None, False
        nodes.append(new)
        parents.append(i)
        return len(nodes) - 1, far <= step

    def trace(tree, i):
        nodes, parents = tree
        out = []
        while i >= 0:
            out.append(nodes[i])
            i = parents[i]
        return out

    for k in range(tries):
        a, b = trees[k % 2], trees[1 - k % 2]
        i, _ = extend(a, rng.uniform(chain.lo, chain.hi))
        if i is None:
            continue
        j, reached = extend(b, a[0][i])
        while j is not None and not reached:
            j, reached = extend(b, a[0][i])
        if j is not None and reached:
            first, second = trace(a, i)[::-1], trace(b, j)
            path = first + second[1:] if k % 2 == 0 else second[::-1] + first[::-1][1:]
            for _ in range(60):                             # cut corners
                if len(path) <= 2:
                    break
                i0 = int(rng.integers(0, len(path) - 2))
                i1 = int(rng.integers(i0 + 2, len(path)))
                if line_free(chain, path[i0], path[i1], ignore_bodies=ignore_bodies):
                    path = path[:i0 + 1] + path[i1:]
            return path
    return None
