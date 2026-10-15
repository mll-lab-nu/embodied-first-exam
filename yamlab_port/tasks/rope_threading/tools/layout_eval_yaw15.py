"""yaw 15 layout evaluation (offline, numpy): the ring group turned 180 deg about its centre, rope start unchanged.
Reuses layout_eval (per-step stroke / pick / transition / hand-over numbers) and adds
  * air_handover(): the picking right hand holds the rope (pick end orientation, rope along ring-3's reversed travel) at a
    grid of positions; the left hand grasps the rope `s` m from the right grip (s = +0.12 / +0.135 toward the tip, -0.12 / -0.16 /
    -0.20 toward the tail; rope across the pads, approach every 30 deg, not from below). A pair counts when both IK solutions
    exist (margin 0.05, capsule clearance as Runner.reachable), the arms clear each other by >= 1 cm and the two TCPs are >= 12 cm apart.
  * stroke_diag_ms(): stroke_diag with 60 random seeds added to seeds_for (margin 0.03, as probe_orient3.reach_rs).
Usage: python layout_eval_yaw15.py [--nproc 6]   (writes evidence/medium_layout/yaw15_eval.json)
"""
import argparse, json, os, sys, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layout_eval as L
import medium_layout_search as M
import plan_np as PN
import yam_kin as K
from reach_map import seeds_for

W = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
ROPE_T, ROPE_YAW = (0.58, -0.05), 90.0
EZ = np.array([0, 0, 1.0])
RS = [K.LOWER + 0.03 + (K.UPPER - K.LOWER - 0.06) * np.random.default_rng(0).random(6) for _ in range(60)]


def layout_t():
    rings, _ = M.place(195.0, (0.54, 0.12))
    P = np.mean([r["center"][:2] for r in rings], 0)
    return P, 2 * P - np.array([0.54, 0.12])


def base_box_dist(yaw, t, rope_xy):
    """min distance (m) between the rope centreline and the stand base boxes (50 x 80 mm), minus the rope radius 4 mm; -1 if inside."""
    rings, _ = M.place(yaw, t)
    Rz = M.rot(yaw)[:2, :2]
    out = []
    for r in rings:
        loc = (rope_xy - r["base_center"][:2]) @ Rz           # rope points in the base frame
        d = np.linalg.norm(loc - np.clip(loc, (-0.025, -0.04), (0.025, 0.04)), axis=1)
        out.append(float(d.min()) - 0.004)
    return min(out)


def stroke_diag_ms(side, c, d, ts, fix, cone, keep=L.KEEP):
    """stroke_diag with the 60 random seeds added at the first stroke point."""
    cand = M.stroke_frames(c, d, cone, ts)
    devs, strokes = zip(*cand)
    base = K.BASES[side]
    first = np.array([s[0] for s in strokes]); first[:, :3, 3] -= base
    seeds = np.array(seeds_for(first[0, :3, 3]) + RS)
    ns = len(seeds)
    q, ep, er = M.ik_batch(np.repeat(first, ns, 0), np.tile(seeds, (len(strokes), 1)), 200, 0.03)
    ok = (ep < 1e-4) & (er < 1e-3)
    chains = []
    for k in range(len(strokes)):
        sols = []
        for j in np.flatnonzero(ok[k * ns:(k + 1) * ns]):
            qq = q[k * ns + j]
            if all(np.abs(qq - o).max() > 0.3 for o in sols):
                sols.append(qq)
        chains += [(k, [qq]) for qq in sols[:keep]]
    diag = dict(cand=len(cand), ik0=len(chains))
    for i in range(1, len(ts)):
        if not chains:
            break
        Tb = np.array([strokes[k][i] for k, _ in chains]); Tb[:, :3, 3] -= base
        prev = np.array([qs[-1] for _, qs in chains])
        qn, ep, er = M.ik_batch(Tb, prev, 100, 0.02)
        good = (ep < 1.5e-3) & (er < 3e-2) & (np.abs(qn - prev).max(1) < 0.6)
        chains = [(k, qs + [qn[j]]) for j, (k, qs) in enumerate(chains) if good[j]]
    diag["path"] = len(chains)
    out = [(devs[k], np.array(qs)) for k, qs in chains
           if all(min(PN.arm_clearance(side, qq, fix, grip_open=False).values()) >= 0.01 for qq in qs)]
    diag["clear"] = len(out)
    diag["poses"] = len({tuple(np.round(K.fk_tcp(p[0])[:3, :3].ravel(), 1)) for _, p in out})
    return out, dict(diag, why=L.why(diag))


def ik_q(side, Ts, q_seed, fix, other, margin=0.05, clear=0.01):
    """batched Runner.reachable: per pose the first IK solution that clears fixtures/table/other arm, else None."""
    if not len(Ts):
        return []
    Tb = np.array(Ts, float); Tb[:, :3, 3] -= K.BASES[side]
    sd = [np.array([q_seed] + seeds_for(t[:3, 3])) for t in Tb]
    ns = len(sd[0])
    q, ep, er = M.ik_batch(np.repeat(Tb, ns, 0), np.concatenate(sd), 200, margin)
    ok = (ep < 1e-4) & (er < 1e-3)
    res = []
    for i in range(len(Tb)):
        sol = None
        for j in np.flatnonzero(ok[i * ns:(i + 1) * ns]):
            if min(PN.arm_clearance(side, q[i * ns + j], fix, other=other, grip_open=False).values()) >= 0.004 + clear:
                sol = q[i * ns + j]; break
        res.append(sol)
    return res


def air_handover(order, fix, q_ready):
    """Right (picker) holds the rope, left receives, in the air. -> dict with counts and the first-failure reason."""
    ring = order[0]; d, c = ring["travel"], ring["center"]
    R0 = PN.frame_az(L.A1, d)[:3, :3]
    rights = [(R0, np.array([x, y, z])) for x in (0.36, 0.44, 0.52, 0.60) for y in (-0.40, -0.30, -0.20, -0.10, 0.0, 0.10)
              for z in (0.85, 0.95, 1.05)]
    oth = ("left", q_ready["left"], True)
    qr = ik_q("right", [L.at_grip(Rm, g) for Rm, g in rights], q_ready["right"], fix, oth)
    good = [(Rm, g, q) for (Rm, g), q in zip(rights, qr) if q is not None]
    res = dict(n_right_grips=len(rights), n_right_ok=len(good), pairs_geom=0, pairs_dist=0, pairs=0, grips_with_pair=0, left_reach=0,
               n_left_cand=0, pairs_feed_ok=0, left_orients_feed_ok=0)
    ok_orient = set()
    other_r = ("right", q_ready["right"], True)
    for Rm, g, qR in good:
        cand = []
        for s in (0.12, 0.135, -0.12, -0.16, -0.20):
            p = g + s * d
            h = np.cross(EZ, d); h /= np.linalg.norm(h); v = np.cross(d, h)
            for ph in np.radians(np.arange(0, 360, 30)):
                a = np.cos(ph) * h + np.sin(ph) * v
                if a[2] > 0.5:
                    continue
                for zs in (1, -1):
                    cand.append(PN.grip_T(a, zs * d, p, np.array([0.012, 0, 0])))
        qL = ik_q("left", cand, q_ready["left"], fix, ("right", qR, False))
        res["n_left_cand"] += len(cand)
        n_ok = n_both = 0
        for T, q in zip(cand, qL):
            if q is None:
                continue
            res["left_reach"] += 1
            geom = PN.arm_clearance("left", q, fix, other=("right", qR, False))["arms"] >= 0.01
            dist = np.linalg.norm(T[:3, 3] - L.at_grip(Rm, g)[:3, 3]) >= 0.12
            res["pairs_geom"] += geom; res["pairs_dist"] += dist; res["pairs"] += geom and dist
            n_both += geom and dist
            if geom and dist:       # the left then feeds R3 with this orientation (to_feed_frame's "keep" case): feed start / end reachable
                Rl = T[:3, :3]
                o_l = ("right", q_ready["right"], True)
                fo = ik_q("left", [L.at_grip(Rl, c - 0.24 * d - 0.01 * EZ)], q_ready["left"], fix, o_l, clear=0.01) \
                    + ik_q("left", [L.at_grip(Rl, c - 0.07 * d - 0.01 * EZ)], q_ready["left"], fix, o_l, clear=-0.002)
                if all(q is not None for q in fo):
                    res["pairs_feed_ok"] += 1; ok_orient.add(tuple(np.round(Rl.ravel(), 1)))
        res["grips_with_pair"] += n_both > 0
    res["left_orients_feed_ok"] = len(ok_orient)
    res = {k: int(v) for k, v in res.items()}
    return res


def feed_frames_left(side, ring, fix, q_ready, q_other, theta, cone=25.0, start=0.24, stop=0.07):
    """Feed frames of `ring` for arm `side` (start / end grip poses reachable, oracle.perp_approaches x feed directions up to
    `cone` x chord-correction fractions for chord angle `theta`): list of (direction, TCP orientation). Independent of the start pose."""
    from scipy.spatial.transform import Rotation as Rot
    oside = "right" if side == "left" else "left"
    other = (oside, q_other, True)
    d, c = ring["travel"], ring["center"]
    th = np.radians(theta); c_t = np.array([np.sin(th), 0, np.cos(th)])
    ax = np.cross(c_t, EZ); n = np.linalg.norm(ax)
    q_rv = np.zeros(3) if n < 1e-9 else ax / n * np.arctan2(n, c_t @ EZ)
    fracs = (1.0, 2 / 3, 1 / 3, 0.0) if n > 1e-9 else (1.0,)
    cands, seen = [], set()
    for dd in L.feed_dirs(d, cone):
        for frac in fracs:
            Q = Rot.from_rotvec(frac * q_rv).as_matrix()
            for a in L.perp_approaches(dd, side, c):
                Rm = PN.frame_az(a, dd)[:3, :3] @ Q
                key = (tuple(np.round(dd, 4)), tuple(np.round(Rm.ravel(), 4)))
                if key not in seen:
                    seen.add(key); cands.append((dd, Rm))
    g0 = lambda dd: c - start * dd - 0.01 * EZ
    g1 = lambda dd: c - stop * dd - 0.01 * EZ
    a_ok = L.reach_many(side, [L.at_grip(Rm, g0(dd)) for dd, Rm in cands], q_ready, fix, other)
    idx = [i for i, ok in enumerate(a_ok) if ok]
    b_ok = L.reach_many(side, [L.at_grip(cands[i][1], g1(cands[i][0])) for i in idx], q_ready, fix, other, clear=-0.002)
    return [cands[i] for i, ok in zip(idx, b_ok) if ok]


def handover_chain(ring, fix, q_ready, thetas=(0.0, 36.0, -36.0), tips=(0.05, 0.075, 0.10, 0.15, 0.20, 0.25), max_trans=6):
    """Air hand-over at the start. A: the right keeps its pick end state (grip point (0.60, -0.40, ring-3 height - 0.01), z_tcp along
    the travel, approach a1); the left grasps the rope `u` m from the tip (tip = right grip + 0.19 d), rope across the pads, approach every
    30 deg, not from below. B: the right first carries the rope to a grid of positions in the middle (x .36-.60, y -.40-.10, z .85-1.05).
    Per case: n_right_ok, left grasps IK-reachable, arm clearance >= 1 cm, TCP gap >= 12 cm (pairs), and the left's in-place
    rotation (slerp, 13 steps, IK continuous, clearance >= 8 mm, right at ready) from the receive pose onto its R3 feed frames per theta."""
    d, c = ring["travel"], ring["center"]
    R0 = PN.frame_az(L.A1, d)[:3, :3]
    h = np.cross(EZ, d); h /= np.linalg.norm(h); v = np.cross(d, h)
    left_T = lambda p: [PN.grip_T(np.cos(ph) * h + np.sin(ph) * v, zs * d, p, np.array([0.012, 0, 0]))
                        for ph in np.radians(np.arange(0, 360, 30)) if (np.cos(ph) * h + np.sin(ph) * v)[2] <= 0.5 for zs in (1, -1)]
    frames = {th: feed_frames_left("left", ring, fix, q_ready["left"], q_ready["right"], th) for th in thetas}
    out = dict(n_left_feed_frames={str(th): len(f) for th, f in frames.items()}, cases={})
    for case, grips in (("A_right_stays", [np.array([0.60, -0.40, c[2] - 0.01])]),
                        ("B_right_carries", [np.array([x, y, z]) for x in (0.36, 0.44, 0.52, 0.60) for y in (-0.40, -0.30, -0.20, -0.10, 0.0, 0.10)
                                             for z in (0.85, 0.95, 1.05)])):
        res = dict(right_grips=len(grips), right_ok=0, left_cand=0, left_reach=0, geom=0, dist=0, pairs=0, tip_dist_pairs={},
                   trans={str(th): dict(pairs_tried=0, ok=0, plans=0) for th in thetas})
        qR = ik_q("right", [L.at_grip(R0, g) for g in grips], q_ready["right"], fix, ("left", q_ready["left"], True))
        tried = 0
        for g, qr in zip(grips, qR):
            if qr is None:
                continue
            res["right_ok"] += 1
            Tr = L.at_grip(R0, g); tip = g + 0.19 * d
            cand, us = [], []
            for u in tips:
                for T in left_T(tip - u * d):
                    cand.append(T); us.append(u)
            qL = ik_q("left", cand, q_ready["left"], fix, ("right", qr, False))
            res["left_cand"] += len(cand)
            for T, q, u in zip(cand, qL, us):
                if q is None:
                    continue
                res["left_reach"] += 1
                geom = PN.arm_clearance("left", q, fix, other=("right", qr, False))["arms"] >= 0.01
                dist = np.linalg.norm(T[:3, 3] - Tr[:3, 3]) >= 0.12
                res["geom"] += geom; res["dist"] += dist
                if geom and dist:
                    res["pairs"] += 1; res["tip_dist_pairs"][str(u)] = res["tip_dist_pairs"].get(str(u), 0) + 1
                    if tried < max_trans:
                        tried += 1
                        for th in thetas:
                            tr = res["trans"][str(th)]; tr["pairs_tried"] += 1
                            n = sum(bool(L.slerp_np("left", T, Rm, fix, ("right", q_ready["right"]))) for _, Rm in frames[th][:25])
                            tr["plans"] += n; tr["ok"] += n > 0
        out["cases"][case] = res
    return out


def evaluate(a):
    t0 = time.time()
    yaw, t = a["yaw"], tuple(a["t"])
    rope_t, rope_yaw = a["rope_t"], a["rope_yaw"]
    rxy = M.M_ROPE_XY @ M.rot(rope_yaw)[:2, :2].T + np.asarray(rope_t)
    fits_all = bool(rxy[:, 0].min() >= PN.TABLE_X[0] + 0.014 and rxy[:, 0].max() <= PN.TABLE_X[1] - 0.014 and np.abs(rxy[:, 1]).max() <= PN.TABLE_Y - 0.014)
    M.RINGS_ONLY = True
    fits_rings = M.fits(yaw, t, 0.01)
    r = dict(yaw=yaw, t=t, fits_rope=fits_all, fits_rings=fits_rings, rope_base_clear=round(base_box_dist(yaw, t, rxy), 3))
    if not (fits_rings and fits_all and r["rope_base_clear"] > 0):
        r["skipped"] = True
        return r
    r.update(L.evaluate_layout(dict(yaw=yaw, t=t, rope_t=rope_t, rope_yaw=rope_yaw, reverse=True, thetas=[0.0, 36.0, -36.0])))
    r["fits_rope"], r["fits_rings"] = fits_all, fits_rings
    rings, _ = M.place(yaw, t)
    fix = L.fixture(rings)
    rr = [dict(x, travel=-x["sign"] * x["normal"]) for x in rings[::-1]]          # reverse route: R3, R2, R1
    q_ready = {}
    for side in ("left", "right"):
        sg = 1 if side == "left" else -1
        q_ready[side] = M.goto_q(side, PN.frame((0.7071, 0, -0.7071), (0, 1, 0), (0.40, sg * 0.30, 0.95)), M.HOME, fix,
                                 ("right" if side == "left" else "left", M.HOME, True))
    # random multi-start repeats (cone 25 as the stroke version, and cone 20)
    r["multistart"] = {}
    for nm in ("R3", "R2", "R1"):
        ring = next(x for x in rr if x["name"] == nm)
        for kind, ts in (("recv", M.RECV_TS), ("feed", M.FEED_TS)):
            if nm == "R1" and kind == "recv":
                continue
            e = {}
            for s in ("left", "right"):
                _, e[s] = stroke_diag_ms(s, ring["center"], ring["travel"], ts, fix, 25.0)
            r["multistart"][nm + "_" + kind] = e
    # air hand-over at the start
    if q_ready["left"] is not None and q_ready["right"] is not None:
        r["air"] = air_handover(rr, fix, q_ready)
        r["air2"] = handover_chain(rr[0], fix, q_ready)
    r["secs"] = round(time.time() - t0, 1)
    print("done", yaw, t, r.get("first_fail"), r["secs"]); sys.stdout.flush()
    return r


if __name__ == "__main__":
    from multiprocessing import Pool
    ap = argparse.ArgumentParser()
    ap.add_argument("--nproc", type=int, default=6)
    ap.add_argument("--step", type=float, default=0.015)
    a = ap.parse_args()
    P, t = layout_t()
    t = np.round(t, 3)
    print("P", P.round(4), "t", t); sys.stdout.flush()
    jobs = [dict(yaw=195.0, t=(0.54, 0.12), rope_t=ROPE_T, rope_yaw=ROPE_YAW)]
    for dx in (-2, -1, 0, 1, 2):
        for dy in (-2, -1, 0, 1, 2):
            jobs.append(dict(yaw=15.0, t=(round(t[0] + dx * a.step, 4), round(t[1] + dy * a.step, 4)), rope_t=ROPE_T, rope_yaw=ROPE_YAW))
    out = []
    with Pool(a.nproc) as pool:
        for r in pool.imap_unordered(evaluate, jobs):
            out.append(r)
            json.dump(dict(P=P.tolist(), t_centre=t.tolist(), results=out), open(W + "/evidence/medium_layout/yaw15_eval.json", "w"), indent=1, default=str)
    print("ALL DONE")
