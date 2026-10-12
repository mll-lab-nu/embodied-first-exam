"""Plan R for the YAM buzz-wire oracle (numpy; used offline and by the Isaac oracle).

Sequence (y-span layout, start post left, finish post right):
  1 R  pen grip G_up on the start rest pose (only grasp that fits under the span)
  2 R  lift on the start post to ~55 mm, loop tilted 40 deg toward the robot (camera clear of the span)
  3 L  ring grip on the far side of the loop (handover 1); R opens and leaves
  4 L  untilt, yaw the handle to +x, carry the loop along the whole rail (loop normal = tangent,
       handle perpendicular to the wire plane), down the finish post to ~60 mm
  5 L  yaw the handle to -120 deg on the finish post
  6 R  pen grip G_down on the handle (handover 2); L opens and leaves
  7 R  lower the face-down wand onto the deck, yaw the handle to 180 deg (toward the robot), release, leave
  8 L  pen grip G_down from the front, yaw the handle to the finish pose, release, leave
All targets are link_6 poses from wand poses via grasp transforms; IK = BatchIK continuation.
"""
import numpy as np
from scipy.spatial.transform import Rotation, Slerp
from bw_geom import *
from grasps import *
from ik import BatchIK

OPEN, CLOSED = -0.0475, 0.0


def frame_h_n(h, n):
    h = np.asarray(h, float); h = h / np.linalg.norm(h)
    n = np.asarray(n, float); n = n - h * np.dot(h, n); n = n / np.linalg.norm(n)
    return np.column_stack([h, np.cross(n, h), n])


def W_of(R, p):
    return T_from(R, p)


def interp_T(Ta, Tb, n):
    """n poses from Ta to Tb (inclusive of Tb, exclusive of Ta)."""
    sl = Slerp([0, 1], Rotation.from_matrix(np.stack([Ta[:3, :3], Tb[:3, :3]])))
    out = []
    for u in np.linspace(0, 1, n + 1)[1:]:
        out.append(T_from(sl(u).as_matrix(), (1 - u) * Ta[:3, 3] + u * Tb[:3, 3]))
    return out


def n_steps(Ta, Tb, lin=0.002, ang=np.radians(1.5)):
    d = np.linalg.norm(Tb[:3, 3] - Ta[:3, 3])
    a = Rotation.from_matrix(Tb[:3, :3] @ Ta[:3, :3].T).magnitude()
    return max(1, int(np.ceil(max(d / lin, a / ang))))


class PlanError(RuntimeError):
    pass


class Planner:
    def __init__(self, scene, min_clear=0.002):
        self.s = scene
        self.ik = {k: BatchIK(k) for k in ("left", "right")}
        self.AP = {k: ArmPoints(self.ik[k].arm, spacing=0.007) for k in ("left", "right")}
        self.min_clear = min_clear
        self.rng = np.random.default_rng(0)

    # ----------------------------------------------------------------- checks
    other_state = None  # callable -> {side: (q, finger)}; the other arm is an obstacle
    other_override = None  # {side: (q, finger)} used instead (e.g. where the other arm will be parked)

    def _other_tree(self, side):
        if self.other_state is None:
            return None
        o = "left" if side == "right" else "right"
        q, fq = (self.other_override or self.other_state())[o] if (self.other_override or {}).get(o) is not None \
            else self.other_state()[o]
        key = (o, tuple(np.round(q, 4)), round(float(fq), 4))
        if getattr(self, "_otree_key", None) != key:
            from scipy.spatial import cKDTree
            pts = np.concatenate(list(self.AP[o].world(np.asarray(q), fq).values()))
            self._otree, self._otree_key = cKDTree(pts), key
        return self._otree

    def clear(self, side, q, fq, wand=None, ignore=()):
        W = self.AP[side].world(q, fq)
        c = clearances(self.s, W)
        tree = self._other_tree(side)
        if tree is not None:
            d, _ = tree.query(np.concatenate(list(W.values())), distance_upper_bound=0.1)
            c["arm"] = float(min(d.min(), 0.1))
        return {k: v for k, v in c.items() if k not in ignore}

    def ok(self, side, q, fq, ignore=(), margin=None):
        """margin: float (all categories) or dict {category: metres} (others: min_clear)."""
        c = self.clear(side, q, fq, ignore=ignore)
        if isinstance(margin, dict):
            good = all(v >= margin.get(k, self.min_clear) for k, v in c.items())
        else:
            m = self.min_clear if margin is None else margin
            good = min(c.values()) >= m
        return good, c

    # ----------------------------------------------------------------- IK
    def ik_best(self, side, T, fq, prefer=None, n_random=192, ignore=(), margin=None):
        sols = self.ik[side].solve_multi(T[:3, 3], T[:3, :3], None, n_random=n_random, rng=self.rng,
                                         seeds=None if prefer is None else [prefer])
        best = None
        for q in sols:
            good, c = self.ok(side, q, fq, ignore, margin)
            sc = (good, -np.abs(q - prefer).max() if prefer is not None else min(c.values()))
            if best is None or sc > best[0]:
                best = (sc, q, c)
        if best is None:
            raise PlanError(f"no IK for {side}")
        return best[1], best[2]

    def track(self, side, Ts, q0, fq, max_jump=0.15, check_every=4, ignore=(), margin=None):
        """IK continuation along link6 targets; returns joint waypoints (one per target)."""
        if margin is None:
            margin = {"wire": 0.004, "arm": 0.008}
        ik = self.ik[side]
        q = np.array(q0, float)
        out = []
        worst = {}
        for k, T in enumerate(Ts):
            Q, okv, ep, er = ik.solve(T[:3, 3], T[:3, :3], np.eye(4), q[None], iters=100, tol_p=3e-4, tol_r=3e-3)
            if not okv[0]:
                raise PlanError(f"{side} track IK failed at {k}/{len(Ts)} (ep {ep[0]:.2e} er {er[0]:.2e})")
            qn = Q[0]
            jump = np.abs(qn - q).max()
            if jump > max_jump:
                # allowed only if the joint-space segment keeps the gripper on the Cartesian segment (near-singular
                # wrist, not a branch flip): check intermediate TCP deviation
                Tprev = ik.fk(q[None], np.eye(4))[0][0]
                for u in (0.25, 0.5, 0.75):
                    Tm = ik.fk(((1 - u) * q + u * qn)[None], np.eye(4))[0][0]
                    pm = (1 - u) * Tprev[:3, 3] + u * T[:3, 3]
                    if np.linalg.norm(Tm[:3, 3] - pm) > 0.003 or jump > 0.6:
                        raise PlanError(f"{side} track jump {jump:.3f} rad at {k}/{len(Ts)}")
            q = qn
            out.append(q.copy())
            if k % check_every == 0 or k == len(Ts) - 1:
                good, c = self.ok(side, q, fq, ignore, margin)
                for a, b in c.items():
                    worst[a] = min(worst.get(a, 1.0), b)
                if not good:
                    raise PlanError(f"{side} track collision at {k}/{len(Ts)}: { {a: round(b * 1000, 1) for a, b in c.items()} }")
        return out, worst

    def joint_move(self, side, qa, qb, fq, step=0.03, ignore=(), margin=None):
        n = max(1, int(np.ceil(np.abs(np.asarray(qb) - qa).max() / step)))
        out = []
        worst = {}
        for u in np.linspace(0, 1, n + 1)[1:]:
            q = (1 - u) * np.asarray(qa) + u * np.asarray(qb)
            good, c = self.ok(side, q, fq, ignore, margin)
            for a, b in c.items():
                worst[a] = min(worst.get(a, 1.0), b)
            if not good:
                raise PlanError(f"{side} joint move collision at u={u:.2f}: { {a: round(b * 1000, 1) for a, b in c.items()} }")
            out.append(q)
        return out, worst

    def cart_move(self, side, T_from_, T_to, q0, fq, **kw):
        Ts = interp_T(T_from_, T_to, n_steps(T_from_, T_to))
        return self.track(side, Ts, q0, fq, **kw)

    # ----------------------------------------------------------------- wand paths (wand poses as 4x4)
    def wand_yaw(self, W, post_xy, deg, step=2.0):
        out = []
        c = np.r_[post_xy, 0.0]
        n = max(1, int(np.ceil(abs(deg) / step)))
        for a in np.linspace(0, deg, n + 1)[1:]:
            Rz = Rotation.from_euler("z", a, degrees=True).as_matrix()
            p = Rz @ (W[:3, 3] - c) + c
            p[2] = W[2, 3]
            out.append(T_from(Rz @ W[:3, :3], p))
        return out

    def wand_route(self, s_from, s_to, h=(1.0, 0.0, 0.0), ds=0.002):
        s = self.s
        tang = s.tangents()
        out = []
        n = max(1, int(np.ceil(abs(s_to - s_from) / ds)))
        for a in np.linspace(s_from, s_to, n + 1)[1:]:
            p = np.array([np.interp(a, s.arc, s.rail[:, k]) for k in range(3)])
            t = np.array([np.interp(a, s.arc, tang[:, k]) for k in range(3)])
            out.append(T_from(frame_h_n(h, t), p))
        return out


def _edge_ok(P, side, qa, qb, fq, step, ignore, margin):
    n = max(1, int(np.ceil(np.abs(np.asarray(qb) - qa).max() / step)))
    for u in np.linspace(0, 1, n + 1)[1:]:
        if not P.ok(side, (1 - u) * np.asarray(qa) + u * np.asarray(qb), fq, ignore, margin)[0]:
            return False
    return True


FREE_MARGINS = {"wire": 0.005, "deck": 0.004, "stops": 0.004, "table": 0.01, "arm": 0.02, "frame": 0.015}


def rrt_connect(P, side, qa, qb, fq, step=0.012, iters=3000, ignore=(), margin=FREE_MARGINS, seed=0):
    """Joint-space RRT-Connect with the numpy collision model, then shortcut smoothing."""
    rng = np.random.default_rng(seed)
    lo, hi = P.ik[side].lo, P.ik[side].hi
    qa, qb = np.asarray(qa, float), np.asarray(qb, float)
    if _edge_ok(P, side, qa, qb, fq, step, ignore, margin):
        return [qa, qb]
    Ta, Tb = [qa], [qb]
    pa, pb = [-1], [-1]
    ext = 0.25

    def extend(T, par, target):
        d = [np.abs(x - target).max() for x in T]
        i = int(np.argmin(d))
        q = T[i]
        delta = target - q
        nrm = np.abs(delta).max()
        qn = target if nrm <= ext else q + delta * ext / nrm
        if _edge_ok(P, side, q, qn, fq, step, ignore, margin):
            T.append(qn)
            par.append(i)
            return len(T) - 1
        return None

    for it in range(iters):
        qr = rng.uniform(lo, hi) if rng.random() > 0.2 else (qb if len(Ta) % 2 else qa)
        ia = extend(Ta, pa, qr)
        if ia is None:
            Ta, Tb, pa, pb = Tb, Ta, pb, pa
            continue
        # connect
        while True:
            ib = extend(Tb, pb, Ta[ia])
            if ib is None:
                break
            if np.abs(Tb[ib] - Ta[ia]).max() < 1e-9:
                pathA, i = [], ia
                while i != -1:
                    pathA.append(Ta[i]); i = pa[i]
                pathB, i = [], ib
                while i != -1:
                    pathB.append(Tb[i]); i = pb[i]
                path = pathA[::-1] + pathB[1:]
                if np.abs(path[0] - qa).max() > 1e-9:
                    path = path[::-1]
                # shortcut
                for _ in range(80):
                    if len(path) < 3:
                        break
                    i, j = sorted(rng.choice(len(path), 2, replace=False))
                    if j - i < 2:
                        continue
                    if _edge_ok(P, side, path[i], path[j], fq, step, ignore, margin):
                        path = path[:i + 1] + path[j:]
                return path
        Ta, Tb, pa, pb = Tb, Ta, pb, pa
    raise PlanError(f"{side} RRT failed")


def densify(path, step=0.03):
    out = []
    for a, b in zip(path[:-1], path[1:]):
        n = max(1, int(np.ceil(np.abs(np.asarray(b) - a).max() / step)))
        for u in np.linspace(0, 1, n + 1)[1:]:
            out.append((1 - u) * np.asarray(a) + u * np.asarray(b))
    return out


def plan_grasp(P, side, q_start, T_grasp, follow_Ts, fq_open, fq_hold, dists=(0.04, 0.03, 0.05, 0.02),
               approach_ignore=(), follow_ignore=(), follow_check_every=6, n_random=256, max_branches=12,
               follow_other=None, approach_axes=((0, 0, 1),),
               staging=((-0.10, 0, 0), (-0.15, 0, 0.02), (0, -0.10, 0), (-0.08, -0.08, 0), (0, 0.10, 0), (0, 0, 0.06))):
    """Choose an IK branch at the grasp such that (a) the following held motion `follow_Ts` tracks from it,
    (b) a straight approach of length d along the gripper axis reaches it, (c) a collision-free joint path
    leads from q_start to the pre-grasp. Returns dict(path, approach, q_grasp, d, follow)."""
    sols = P.ik[side].solve_multi(T_grasp[:3, 3], T_grasp[:3, :3], None, n_random=n_random, rng=P.rng)
    scored = []
    for q in sols:
        good, c = P.ok(side, q, fq_hold, approach_ignore)
        scored.append((min(c.values()), q))
    scored.sort(key=lambda x: -x[0])
    errs = []
    for clear0, qg in scored[:max_branches]:
        try:
            P.other_override = follow_other
            fol, _ = P.track(side, follow_Ts, qg, fq_hold, check_every=follow_check_every, ignore=follow_ignore) if follow_Ts else ([], {})
        except PlanError as e:
            errs.append(f"follow: {e}")
            continue
        finally:
            P.other_override = None
        for d, ax in [(d, a) for a in approach_axes for d in dists[:2]]:
            Tpre = T_grasp @ T_from(np.eye(3), -d * np.asarray(ax, float))
            Ts = interp_T(T_grasp, Tpre, n_steps(T_grasp, Tpre, lin=0.001))
            try:
                back_qs, _ = P.track(side, Ts, qg, fq_open, ignore=approach_ignore)
            except PlanError as e:
                errs.append(f"approach d={d}: {e}")
                continue
            # free path to the pre-grasp, directly or via a staging pose reached by a straight Cartesian slide
            for stage in [None] + list(staging):
                try:
                    if stage is None:
                        path = rrt_connect(P, side, q_start, back_qs[-1], fq_open, iters=3000)
                        slide, slide_T = [], []
                    else:
                        Tst = Tpre.copy(); Tst[:3, 3] += np.asarray(stage)
                        sT = interp_T(Tpre, Tst, n_steps(Tpre, Tst))
                        sq, _ = P.track(side, sT, back_qs[-1], fq_open, ignore=approach_ignore,
                                        margin={"wire": 0.006, "arm": 0.01})
                        path = rrt_connect(P, side, q_start, sq[-1], fq_open, iters=1500)
                        slide, slide_T = sq[::-1][1:] + [back_qs[-1]], sT[::-1][1:] + [Tpre]
                    appr = back_qs[::-1][1:] + [qg]
                    return dict(path=path, slide=slide, slide_T=slide_T, approach=appr,
                                approach_T=Ts[::-1][1:] + [T_grasp], q_grasp=qg, d=d, follow=fol, staging=stage)
                except PlanError as e:
                    errs.append(f"approach d={d} staging={stage}: {e}")
    raise PlanError(f"{side} plan_grasp failed ({len(sols)} IK branches): " + " | ".join(errs[-6:]))
