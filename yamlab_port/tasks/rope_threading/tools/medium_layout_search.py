"""Medium re-layout search (numpy only, multiprocessing; OMP_NUM_THREADS=1).

world_xy = Rz(yaw) old_xy/1000 + (tx, ty), world_z = 0.75 + old_z/1000.
1. Fit: rope start (radius 4 mm), stand bases (50 x 80 boxes) and stand posts must lie on the tabletop collider
   (x 0.3025..0.8975, y -0.65..0.65) with `--margin`; rings may overhang (they are in the air).
2. Reach: the END tip is fed through R1, R2, R3 in order (travel d_k = sign_k n_k). Strokes: feed (grip point
   0.18 -> 0.07 m before the plane; the tip leads the grip by ~0.15 m) and receive (0.07 -> 0.20 m past the plane)
   for every ring but the last (its feed completes the route, as R2 in easy). The stroke runs through the ring
   centre within `--cone` deg of d_k (at 30 deg the aperture still leaves 56 mm around the rope). Rope across the
   pads (z_tcp = +-stroke), approach every 30 deg around the stroke but not from below (a_z <= 0.5), grip point
   12 mm inside the pads, IK continuous along the stroke (batched DLS), capsule clearance >= 1 cm to
   rings/stands/table. Per ring the feeder and the receiver are different arms that clear each other by >= 1 cm
   at the handover (feed end + receive start).
Strokes are checked hardest first (the last ring's feed); a layout stops at its first impossible stroke unless --all.
--reverse feeds the START tip instead (R3 first, each travel reversed; the right arm picks it at the right edge).
Prints, per layout, which arm can do each stroke and the handover pairs. Usage: python medium_layout_search.py [--yaws ...]
"""
import argparse, itertools, json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import plan_np as PN
import yam_kin as K
from reach_map import seeds_for
from scipy.spatial.transform import Rotation as Rot

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "overlay", "yamlab", "envs", "tasks",
                   "rope_threading_lib", "src_data", "medium")
if not os.path.isdir(SRC):   # on vast the overlay lives in the yamlab copy
    SRC = "/workspace/yamlab_port/runs/rope_threading/yamlab/yamlab/envs/tasks/rope_threading_lib/src_data/medium"
TABLE = 0.75
lay = json.load(open(os.path.join(SRC, "layout.json")))
parts = {p["name"]: p["pose"]["table"]["position_mm"] for p in lay["parts"]}
route = lay["non_printable"][0]["route"]
ROPE = np.loadtxt(os.path.join(SRC, "rope_start_centerline.csv"), delimiter=",", skiprows=2) / 1000.0
RINGS_OLD = []
for r, o in zip(route["rings"], route["order"]):
    RINGS_OLD.append(dict(name=r["name"], c=np.array(r["centre_table_mm"]) / 1000.0, n=np.array(r["normal"]) / np.linalg.norm(r["normal"]),
                          sign=1 if o[-1] == "+" else -1, stand=np.array(parts[r["name"] + "_stand"]) / 1000.0,
                          base=np.array(parts[r["name"] + "_base"]) / 1000.0))


def rot(yaw):
    a = np.radians(yaw)
    return np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1.0]])


def place(yaw, t):
    Rz = rot(yaw)
    tt = np.array([t[0], t[1], TABLE])
    rings = []
    for r in RINGS_OLD:
        rings.append(dict(name=r["name"], center=Rz @ r["c"] + tt, normal=Rz @ r["n"], radius=0.075, tube=0.006,
                          stand_center=Rz @ r["stand"] + tt, base_center=Rz @ r["base"] + tt, sign=r["sign"]))
    rope = ROPE @ Rz.T + tt
    return rings, rope


RINGS_ONLY = False


def footprint(yaw, t):
    rings, rope = place(yaw, t)
    pts = [] if RINGS_ONLY else [rope[:, :2] + 0.004 * s for s in (np.array([1, 1]), np.array([-1, -1]))]
    Rz = rot(yaw)[:2, :2]
    for rg in rings:
        b = rg["base_center"][:2]
        for cx, cy in ((0.025, 0.04), (-0.025, 0.04), (0.025, -0.04), (-0.025, -0.04)):
            pts.append((b + Rz @ np.array([cx, cy]))[None])
    return np.vstack(pts)


def fits(yaw, t, margin):
    p = footprint(yaw, t)
    return bool(p[:, 0].min() >= PN.TABLE_X[0] + margin and p[:, 0].max() <= PN.TABLE_X[1] - margin
                and np.abs(p[:, 1]).max() <= PN.TABLE_Y - margin)


_L0, _L1i = np.array(K._L0), np.array(K._L1i)


def fk_batch(q):
    """q (N,6) -> link transforms (N,6,4,4), TCP (N,4,4), geometric Jacobian (N,6,6), all in the arm base frame."""
    N = len(q)
    T = np.broadcast_to(np.eye(4), (N, 4, 4))
    links, axes, orig = [], [], []
    for i in range(6):
        Tj = T @ _L0[i]
        axes.append(Tj[:, :3, 0]); orig.append(Tj[:, :3, 3])
        c, s = np.cos(q[:, i]), np.sin(q[:, i])
        R = np.zeros((N, 4, 4)); R[:, 0, 0] = R[:, 3, 3] = 1; R[:, 1, 1] = R[:, 2, 2] = c; R[:, 1, 2] = -s; R[:, 2, 1] = s
        T = Tj @ R @ _L1i[i]
        links.append(T)
    Tt = T @ K.T6_TCP
    ax, og = np.stack(axes, 1), np.stack(orig, 1)
    J = np.concatenate([np.cross(ax, Tt[:, None, :3, 3] - og), ax], axis=2).transpose(0, 2, 1)
    return np.stack(links, 1), Tt, J


def ik_batch(Tb, q0, iters, margin):
    """Batched K.ik (same DLS step, step clip and tolerances). Tb (N,4,4) base frame -> q (N,6), err_p, err_r."""
    lo, hi = K.LOWER + margin, K.UPPER - margin
    q = np.clip(np.array(q0, float), lo, hi)
    for _ in range(iters):
        _, T, J = fk_batch(q)
        e = np.concatenate([Tb[:, :3, 3] - T[:, :3, 3],
                            Rot.from_matrix(Tb[:, :3, :3] @ T[:, :3, :3].transpose(0, 2, 1)).as_rotvec()], 1)
        if np.all((np.linalg.norm(e[:, :3], axis=1) < 1e-5) & (np.linalg.norm(e[:, 3:], axis=1) < 1e-4)):
            break
        dq = (J.transpose(0, 2, 1) @ np.linalg.solve(J @ J.transpose(0, 2, 1) + 1e-3 * np.eye(6), e[..., None]))[..., 0]
        n = np.linalg.norm(dq, axis=1, keepdims=True)
        q = np.clip(q + dq * np.minimum(1.0, 0.2 / np.maximum(n, 1e-12)), lo, hi)
    _, T, _ = fk_batch(q)
    ep = np.linalg.norm(Tb[:, :3, 3] - T[:, :3, 3], axis=1)
    er = np.linalg.norm(Rot.from_matrix(Tb[:, :3, :3] @ T[:, :3, :3].transpose(0, 2, 1)).as_rotvec(), axis=1)
    return q, ep, er


def stroke_dirs(d, cone):
    """(deviation deg, unit direction) within `cone` deg of d (azimuth / elevation offsets of 0, 15, 30 deg)."""
    h = np.cross([0, 0, 1.0], d); h /= np.linalg.norm(h)
    v = np.cross(d, h)
    out = []
    for az in (0, 15, -15, 30, -30):
        for el in (0, 15, -15):
            if np.hypot(az, el) <= cone + 1e-6:
                a, e = np.radians(az), np.radians(el)
                out.append((float(np.hypot(az, el)), np.cos(e) * (np.cos(a) * d + np.sin(a) * h) + np.sin(e) * v))
    return out


def stroke_frames(c, d, cone, ts):
    """Candidate strokes: list of (deviation deg, world TCP poses along the stroke (n,4,4))."""
    out = []
    for dev, dd in stroke_dirs(d, cone):
        h = np.cross([0, 0, 1.0], dd); h /= np.linalg.norm(h)
        v = np.cross(dd, h)
        for ph in np.radians(np.arange(0, 360, 30)):
            a = np.cos(ph) * h + np.sin(ph) * v
            if a[2] > 0.5:
                continue
            for zs in (1, -1):
                out.append((dev, np.array([PN.grip_T(a, zs * dd, c + t * dd, np.array([0.012, 0, 0])) for t in ts])))
    return out


def stroke_solutions(side, c, d, ts, fix, cone, keep=3):
    """All feasible (IK-continuous, collision-free) strokes of arm `side`: list of (deviation deg, joint path (n,6))."""
    cand = stroke_frames(c, d, cone, ts)
    if not cand:
        return []
    devs, strokes = zip(*cand)
    base = K.BASES[side]
    first = np.array([s[0] for s in strokes]); first[:, :3, 3] -= base
    seeds = np.array(seeds_for(first[0, :3, 3]))
    ns = len(seeds)
    q, ep, er = ik_batch(np.repeat(first, ns, 0), np.tile(seeds, (len(strokes), 1)), 200, 0.03)
    ok = (ep < 1e-4) & (er < 1e-3)
    chains = []                                   # (stroke index, [q per point])
    for k in range(len(strokes)):
        sols = []
        for j in np.flatnonzero(ok[k * ns:(k + 1) * ns]):
            qq = q[k * ns + j]
            if all(np.abs(qq - o).max() > 0.3 for o in sols):
                sols.append(qq)
        chains += [(k, [qq]) for qq in sols[:keep]]
    for i in range(1, len(ts)):
        if not chains:
            return []
        Tb = np.array([strokes[k][i] for k, _ in chains]); Tb[:, :3, 3] -= base
        prev = np.array([qs[-1] for _, qs in chains])
        qn, ep, er = ik_batch(Tb, prev, 100, 0.02)
        good = (ep < 1.5e-3) & (er < 3e-2) & (np.abs(qn - prev).max(1) < 0.6)
        chains = [(k, qs + [qn[j]]) for j, (k, qs) in enumerate(chains) if good[j]]
    out = []
    for k, qs in chains:
        if all(min(PN.arm_clearance(side, qq, fix, grip_open=False).values()) >= 0.01 for qq in qs):
            out.append((devs[k], np.array(qs)))
    return sorted(out, key=lambda x: x[0])


FEED_TS, RECV_TS = np.linspace(-0.18, -0.07, 4), np.linspace(0.07, 0.20, 4)
CONE = 30.0
ALL = False
REVERSE = False
ARMS = ("left", "right")


def handover(feeds, recvs, fix):
    """(feeder, receiver) arm pairs whose feed end and receive start clear each other by >= 1 cm."""
    pairs = []
    for fa, ra in (("left", "right"), ("right", "left")):
        if any(PN.arm_clearance(fa, f[-1], fix, other=(ra, r[0], False))["arms"] >= 0.01
               for _, f in feeds[fa][:20] for _, r in recvs[ra][:20]):
            pairs.append(fa[0].upper() + ra[0].upper())
    return pairs


def evaluate(args):
    yaw, tx, ty = args
    rings, _ = place(yaw, (tx, ty))
    fix = PN.fixture_capsules([dict(r, center=r["center"].tolist(), normal=r["normal"].tolist(),
                                    stand_center=r["stand_center"].tolist()) for r in rings])
    if REVERSE:     # the START tip is fed: through R3 first, against each ring's travel direction
        rings = [dict(r, sign=-r["sign"]) for r in rings[::-1]]
    last = rings[-1]["name"]
    jobs = [(rings[-1], "feed")] + [(r, "feed") for r in rings[-2::-1]] + [(r, "recv") for r in rings[-2::-1]]
    sols, res = {}, {}
    for r, kind in jobs:
        d = r["sign"] * r["normal"]
        sol = {s: stroke_solutions(s, r["center"], d, FEED_TS if kind == "feed" else RECV_TS, fix, CONE) if s in ARMS else []
               for s in ("left", "right")}
        sols[(r["name"], kind)] = sol
        res[r["name"] + kind] = "".join(s[0].upper() if sol[s] else "." for s in ("left", "right"))
        res[r["name"] + kind + "_dev_n"] = [[sol[s][0][0], len(sol[s])] if sol[s] else None for s in ("left", "right")]
        if res[r["name"] + kind] == ".." and not ALL:
            return args, res
    if len(ARMS) == 1:      # one arm feeds, lets go and receives on the other side: no handover pair needed
        res["ok"] = all(v != ".." for k, v in res.items() if k.endswith(("feed", "recv")))
        return args, res
    for r in rings[:-1]:
        res[r["name"] + "hand"] = ",".join(handover(sols[(r["name"], "feed")], sols[(r["name"], "recv")], fix)) or "-"
    res["ok"] = res[last + "feed"] != ".." and all(res[r["name"] + "hand"] != "-" for r in rings[:-1])
    return args, res


# ------------------------------------------------------------------ refine: task-level checks of stroke-feasible layouts
READY = ((0.40, 0.30, 0.95), (0.36, 0.42, 0.92), (0.34, 0.50, 0.90))     # oracle.ready() candidates (y mirrored)
HOME = np.zeros(6)


def _clear(side, q, fix, other):
    return min(PN.arm_clearance(side, q, fix, other=other).values())


def _path_ok(side, qa, qb, fix, other):
    return all(_clear(side, qa + (0.5 - 0.5 * np.cos(np.pi * f)) * (qb - qa), fix, other) >= 0.004
               for f in np.linspace(1 / 12, 1, 12))


def _ik_all(side, T, q0, fix, other):
    Tb = K.world_to_base(T, side)
    sols = []
    for sd in [q0] + seeds_for(Tb[:3, 3]):
        q, ok, _, _ = K.ik(Tb, sd, iters=300, margin=0.03)
        if ok and _clear(side, q, fix, other) >= 0.004:
            sols.append(q)
    return sorted(sols, key=lambda q: np.abs(q - q0).max())


def goto_q(side, T, q0, fix, other):
    """Runner.goto offline: a collision-free joint path q0 -> an IK solution of T, direct or via one via pose."""
    from rt_common import Runner
    sols = _ik_all(side, T, q0, fix, other)
    for q in sols[:6]:
        if _path_ok(side, q0, q, fix, other):
            return q
    for Tv in Runner.via_poses(None, side):
        for qv in _ik_all(side, Tv, q0, fix, other)[:2]:
            if _path_ok(side, q0, qv, fix, other):
                q = next((q for q in sols[:6] if _path_ok(side, qv, q, fix, other)), None)
                if q is not None:
                    return q
    return None


def ready_ok(side, fix):
    """oracle.ready(): first candidate reachable from home (the other arm at home) as Runner.goto would. -> (pose, q)"""
    sg = 1 if side == "left" else -1
    other = ("right" if side == "left" else "left", HOME, True)
    for x, y, z in READY:
        q = goto_q(side, PN.frame((0.7071, 0, -0.7071), (0, 1, 0), (x, sg * y, z)), HOME, fix, other)
        if q is not None:
            return (x, sg * y, z), q
    return None, None


def rope_place(rings, rope_yaw=90.0, tx=0.58, ty=None):
    """rope_t_xy (tx, ty) with every stand base between the U's arms (the end arm on +y, so the end can be dragged
    to the left edge clear of them), maximising the clearance to the bases (table fit 1 cm). None if impossible."""
    best = None
    for ty in (np.arange(-0.15, 0.26, 0.01) if ty is None else [ty]):
        xy = M_ROPE_XY @ rot(rope_yaw)[:2, :2].T + (tx, ty)
        if xy[:, 0].min() < PN.TABLE_X[0] + 0.014 or xy[:, 0].max() > PN.TABLE_X[1] - 0.014 or np.abs(xy[:, 1]).max() > PN.TABLE_Y - 0.014:
            continue
        lo = [r["base_center"][:2] - (0.04, 0.04) for r in rings]; hi = [r["base_center"][:2] + (0.04, 0.04) for r in rings]
        if not (xy[0, 1] < min(l[1] for l in lo) and xy[-1, 1] > max(h[1] for h in hi)):
            continue
        cl = min(np.linalg.norm(xy - np.clip(xy, l, h), axis=1).min() for l, h in zip(lo, hi)) - 0.004
        if best is None or cl > best[0]:
            best = (float(cl), round(float(ty), 2), xy)
    return best


def oracle_reachable(side, T, q_seed, fix, other, clear=0.01, grip_open=True):
    """Runner.reachable offline: IK seeded with the arm's current q, then seeds_for; margin 0.05; clearance to the
    fixtures, the table and the other arm >= 4 mm + clear."""
    Tb = K.world_to_base(T, side)
    for sd in [q_seed] + seeds_for(Tb[:3, 3]):
        q, ok, _, _ = K.ik(Tb, sd, iters=200, margin=0.05)
        if ok and min(PN.arm_clearance(side, q, fix, other=other, grip_open=grip_open).values()) >= 0.004 + clear:
            return True
    return False


def pick_ok(xy, fix, side="left", q_ready=None, q_other=None):
    """Picking arm (left: the end tip, right: the start tip), as oracle.pinch: top-down, z_tcp along the rope's
    horizontal tangent (either sign), fingertips 3.5 cm above the rope, grasp and 8 cm pre-grasp reachable from the
    ready q with the other arm at its ready q. The first pinch (0.15 m from the tip, --drag1_from_tip) must be reachable
    (else 0); counted: pinches 0.12 / 0.15 / 0.20 m from the tip and the drag path to the table edge."""
    sg = 1 if side == "left" else -1
    P = np.c_[xy, np.full(len(xy), TABLE + 0.004)][::sg * -1]
    s_ = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    other = ("right" if side == "left" else "left", HOME if q_other is None else q_other, True)
    q0 = HOME if q_ready is None else q_ready

    def pinch(i, t_h):
        for zs in (-1, 1):
            Tg = PN.frame_az(np.array([0, 0, -1.0]), zs * t_h); Tg[:3, 3] = P[i] + (0, 0, 0.035)
            Tp = Tg.copy(); Tp[:3, 3] += (0, 0, 0.08)
            if oracle_reachable(side, Tg, q0, fix, other) and oracle_reachable(side, Tp, q0, fix, other):
                return True
        return False

    def tangent(i):
        t = P[max(i - 1, 0)] - P[i]; t[2] = 0
        return t / np.linalg.norm(t)

    idx = [int(np.searchsorted(s_, d)) for d in (0.12, 0.15, 0.20)]
    if not pinch(idx[1], tangent(idx[1])):
        return 0, len(idx) + 1
    n = sum(pinch(i, tangent(i)) for i in idx)
    edge = np.array([P[0, 0], sg * 0.60, TABLE + 0.004])          # the drag target region at the table edge
    T = PN.frame_az(np.array([0, 0, -1.0]), np.array([0, sg * 1.0, 0])); T[:3, 3] = edge + (0, 0, 0.035)
    n += oracle_reachable(side, T, q0, fix, other)
    return n, len(idx) + 1


M_ROPE_XY = ROPE[:, :2]


def refine(row):
    yaw, tx, ty = row["yaw"], row["tx"], row["ty"]
    rings, _ = place(yaw, (tx, ty))
    fix = PN.fixture_capsules([dict(r, center=r["center"].tolist(), normal=r["normal"].tolist(),
                                    stand_center=r["stand_center"].tolist()) for r in rings])
    rp = rope_place(rings)
    (rl, ql), (rr, qr) = ready_ok("left", fix), ready_ok("right", fix)
    out = dict(ready_left=rl, ready_right=rr, rope_ty=rp[1] if rp else None, rope_clear=round(rp[0], 3) if rp else None)
    side = "right" if REVERSE else "left"
    q_ready, q_other = (qr, ql) if REVERSE else (ql, qr)
    out["pick"] = "%d/%d" % pick_ok(rp[2], fix, side, q_ready, q_other) if rp and q_ready is not None else None
    return row, out


if __name__ == "__main__":
    from multiprocessing import Pool
    ap = argparse.ArgumentParser()
    ap.add_argument("--margin", type=float, default=0.01)
    ap.add_argument("--yaws", type=float, nargs="*", default=list(range(0, 360, 15)))
    ap.add_argument("--nproc", type=int, default=12)
    ap.add_argument("--rings_only", action="store_true", help="fit only the stand bases (the rope start is placed later)")
    ap.add_argument("--step", type=int, default=2, help="evaluate every step-th tx/ty candidate")
    ap.add_argument("--cone", type=float, default=30.0, help="max stroke deviation from the ring's travel direction (deg)")
    ap.add_argument("--all", action="store_true", help="check every stroke (default: stop at the first impossible one)")
    ap.add_argument("--out", default="medium_layout_search.json")
    ap.add_argument("--refine", default="", help="results json: run the task-level checks on its feasible layouts")
    ap.add_argument("--reverse", action="store_true", help="feed the START tip (R3 first, right arm picks)")
    ap.add_argument("--arms", nargs="+", default=["left", "right"], help="arms allowed for the strokes (one arm: it "
                    "feeds, lets go and receives itself)")
    a = ap.parse_args()
    RINGS_ONLY, CONE, ALL, REVERSE, ARMS = a.rings_only, a.cone, a.all, a.reverse, tuple(a.arms)
    if a.refine:
        rows = [r for r in json.load(open(a.refine)) if r.get("ok")]
        from multiprocessing import Pool
        with Pool(a.nproc) as pool:
            res = sorted(pool.map(refine, rows), key=lambda x: (x[0]["yaw"], x[0]["tx"], x[0]["ty"]))
        for row, o in res:
            print(f"yaw {row['yaw']:5.1f} t ({row['tx']:.2f},{row['ty']:+.2f})",
                  {k: v for k, v in row.items() if k.endswith(("hand", "feed"))}, o)
        json.dump([dict(r, **o) for r, o in res], open(a.out, "w"), indent=1, default=str)
        sys.exit(0)
    cands = []
    for yaw in a.yaws:
        for tx in np.arange(0.30, 0.95, 0.02):
            for ty in np.arange(-0.40, 0.41, 0.04):
                if fits(yaw, (tx, ty), a.margin):
                    cands.append((yaw, round(float(tx), 3), round(float(ty), 3)))
    by_yaw = {}
    for c in cands:
        by_yaw.setdefault(c[0], []).append(c)
    print("FIT yaws:", {y: len(v) for y, v in by_yaw.items()})
    sys.stdout.flush()
    # evaluate a thinned set per yaw (every 2nd tx/ty)
    jobs = []
    for y, v in by_yaw.items():
        xs = sorted({c[1] for c in v}); ys = sorted({c[2] for c in v})
        for c in v:
            if xs.index(c[1]) % a.step == 0 and ys.index(c[2]) % a.step == 0:
                jobs.append(c)
    print("evaluating", len(jobs), "layouts"); sys.stdout.flush()
    out = []
    with Pool(a.nproc) as pool:
        for args_, res in pool.imap_unordered(evaluate, jobs):
            out.append(dict(yaw=args_[0], tx=args_[1], ty=args_[2], **res))
            print(f"yaw {args_[0]:5.1f} t ({args_[1]:.2f},{args_[2]:+.2f})", res); sys.stdout.flush()
            json.dump(out, open(a.out, "w"), indent=1)
    print("DONE")
