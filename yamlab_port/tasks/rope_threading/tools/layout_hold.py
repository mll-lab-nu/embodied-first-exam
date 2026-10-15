"""Offline evaluation of two ways to push a held rope tip through R3 (yaw 15 ring group, mirror rope; numpy, OMP_NUM_THREADS=1).

Geometry (t = (0.532, -0.241)): R3 centre c, normal n, feed travel d = -n (reverse route, start tip first). The tip starts 4 cm before the ring
plane (xy (0.5245, 0.1845), z 1.02 'given'; or 'aimed': the same distance before the plane but on the line that passes through the ring centre).
(a) two-hand carry: rope horizontal (u = horizontal projection of d). Left: top-down pinch at ft from the tip (TCP = grip point + 0.035 up, z_tcp = +-u).
    Right: k (0.08 .. 0.15 step 0.01) behind the left grip on the rope; mode 'top' = pinch from above (approach tilt 0/15/30 deg from vertical, az every
    15 deg), mode 'below' = support from below (approach up, same tilts); z_tcp = +-u; TCP = rope point - 0.035 approach. Both arms lift
    vertically from the table (mode 'below': the right only starts after the lift) in 1 cm steps to rope height z 1.02, then push together along u in 1 cm steps.
(b) left only, wrist kept (approach vertical down): the rope is pivoted up by theta in the fingertip pinch: chord u = (cos th * h, sin th), tip at ring-centre
    height, grip below it. The TCP is lifted vertically (1 cm steps) and pushed along u.
Per frame: IK continuous (step <= 0.6 rad; first pose: q_ready + seeds_for + 60 random seeds, margin 0.03), every capsule of both arms >= 1 cm from fixtures/table,
the arms >= 1 cm from each other, (a) TCP distance >= 12 cm and gripper envelope clearance >= 1 cm, rope axis >= 0 from the R3 rim (rope r 4 mm + tube 6 mm).
pass = distance of the tip beyond the ring plane along d, (tip - c).d (pass_arc: along the rope, /(u.d)); the 0.105 m receive requirement is in the d direction. Reported at the last frame that satisfies everything ('limit').
"""
import argparse, itertools, json, os, sys, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layout_eval as L
import layout_drag as D
import medium_layout_search as M
import plan_np as PN
import yam_kin as K
from reach_map import seeds_for

W = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
EZ = np.array([0, 0, 1.0])
RS60 = [K.LOWER + 0.03 + (K.UPPER - K.LOWER - 0.06) * np.random.default_rng(1).random(6) for _ in range(60)]
TIP_GIVEN = np.array([0.5245, 0.1845, 1.02])
STEP = 0.01


class Ctx:
    def __init__(self, t=(0.532, -0.241)):
        self.rings, self.fix, self.order, self.q = D.setup(t)
        r3 = self.rings[2]
        assert r3["name"] == "R3"
        self.c = np.asarray(r3["center"], float); self.n = np.asarray(r3["normal"], float)
        self.d = -r3["sign"] * self.n                            # reverse route: travel d
        self.h = np.r_[self.d[:2], 0]; self.h /= np.linalg.norm(self.h)
        fa, fb, fr = self.fix
        self.ring_idx = np.arange(2 * 25, 2 * 25 + 24)           # R3's rim capsules in the fixture list
        self.stand3 = 2 * 25 + 24
        self.fa, self.fb, self.fr = fa, fb, fr


def cap_clear(side, q, ctx, other=None):
    """-> dict(fix=min over all fixtures+table, link6_ring=link6/gripper-body capsule to R3's rim, arms=to the other arm, ring_any=all capsules to R3 rim)."""
    A, B, Rr = PN.arm_capsules(side, q, grip_open=False)
    dm = PN.seg_seg_dist(A, B, ctx.fa, ctx.fb) - Rr[:, None] - ctx.fr[None, :]
    c = PN.arm_clearance(side, q, ctx.fix, other=other, grip_open=False)
    out = dict(fix=c["fixtures"], table=c["table"], link6_ring=float(dm[4, ctx.ring_idx].min()), ring_any=float(dm[:, ctx.ring_idx].min()))
    if other is not None:
        out["arms"] = c["arms"]
    return out


def first_solutions(side, Ts, q_ready, ctx, margin=0.03, max_sol=2):
    """per pose a list of distinct IK solutions (<= max_sol) with single-arm fixture/table clearance >= 1 cm."""
    if not len(Ts):
        return []
    Tb = np.array(Ts, float); Tb[:, :3, 3] -= K.BASES[side]
    sd = [np.array([q_ready] + seeds_for(t[:3, 3]) + RS60) for t in Tb]
    ns = len(sd[0])
    q, ep, er = M.ik_batch(np.repeat(Tb, ns, 0), np.concatenate(sd), 200, margin)
    ok = (ep < 1e-4) & (er < 1e-3)
    out = []
    for i in range(len(Tb)):
        sols = []
        for j in np.flatnonzero(ok[i * ns:(i + 1) * ns]):
            qq = q[i * ns + j]
            if all(np.abs(qq - o).max() > 0.3 for o in sols):
                c = PN.arm_clearance(side, qq, ctx.fix, grip_open=False)
                if min(c.values()) >= 0.01:
                    sols.append(qq)
                    if len(sols) >= max_sol:
                        break
        out.append(sols)
    return out


def step_ik(side, Ts, prevs, margin=0.03):
    """one continuation step for chains prevs (n,6) towards the poses Ts (n,4,4): (q, ok)."""
    Tb = np.array(Ts, float); Tb[:, :3, 3] -= K.BASES[side]
    qn, ep, er = M.ik_batch(Tb, np.array(prevs), 100, margin)
    return qn, (ep < 1.5e-3) & (er < 3e-2) & (np.abs(qn - np.array(prevs)).max(1) < 0.6)


def pass_len(tip, u, ctx):
    """(distance of the tip beyond the ring plane along the travel d, rope arc length beyond the plane)."""
    return float((tip - ctx.c) @ ctx.d), float((tip - ctx.c) @ ctx.d / (u @ ctx.d))


def rope_ring_clear(g, tip, ctx):
    """rope axis segment g->tip to R3's rim / stand, minus rope radius (4 mm) and tube (6 mm) / post (5 mm)."""
    d_ring = PN.seg_seg_dist(g[None], tip[None], ctx.fa[ctx.ring_idx], ctx.fb[ctx.ring_idx]) - 0.004 - 0.006
    d_st = PN.seg_seg_dist(g[None], tip[None], ctx.fa[[ctx.stand3]], ctx.fb[[ctx.stand3]]) - 0.004 - 0.005
    return float(d_ring.min()), float(d_st.min())


def radial_dev(tip, u, ctx):
    """distance from R3's centre of the point where the rope axis crosses the ring plane."""
    s = (ctx.c - tip) @ ctx.n / (u @ ctx.n)
    return float(np.linalg.norm(tip + s * u - ctx.c))


def aimed_tip(u, ctx, dist_before):
    """tip such that the line along u passes through the ring centre, `dist_before` (m, along n) before the plane."""
    s0 = dist_before / abs(u @ ctx.n)
    return ctx.c - s0 * u


def tip_before_dist(ctx):
    return float(abs((TIP_GIVEN - ctx.c) @ ctx.n))


def cands_vertical(h, zs_list=(1, -1)):
    """left top-down pinch candidates (approach down, z_tcp = +-h), joined from the table (frame 0)."""
    return [(PN.frame_az(np.array([0, 0, -1.0]), zs * h)[:3, :3], "down zs%+d" % zs, 0) for zs in zs_list]


def cands_tilted(h, mode, f0, tilts=(0, 15, 30)):
    """approach every 15 deg azimuth, tilt from vertical 0/15/30 (mode 'top': down, 'below': up), z_tcp = +-h; they join at frame f0."""
    out = []
    for tilt in tilts:
        for az in (range(0, 360, 15) if tilt else [0]):
            p, a_ = np.radians(tilt), np.radians(az)
            a = np.array([np.sin(p) * np.cos(a_), np.sin(p) * np.sin(a_), (-1 if mode == "top" else 1) * np.cos(p)])
            for zs in (1, -1):
                out.append((PN.frame_az(a, zs * h)[:3, :3], "%s tilt%d az%d zs%+d" % (mode, tilt, az, zs), f0))
    return out


def run_case(ctx, u, tip0, ft, push_dir=None, left_c=None, right_c=None, k=None, max_push=0.20):
    """Lift + push of a held rope. u: unit rope direction (grip -> tip); push_dir: unit push direction (default u).
    left_c / right_c: candidate lists (Rm, label, first frame) (right_c None: the right stays at ready). The left grips at ft from the tip,
    the right k behind the left grip along the rope axis. -> result dict (limit frame, pass, clearances, alive right poses ...)."""
    pd = u if push_dir is None else push_dir
    g_L = tip0 - ft * u
    g_R = None if right_c is None else g_L - k * u
    lift_z0 = 0.754 + 0.004
    n_lift = int(np.ceil((g_L[2] - lift_z0) / STEP - 1e-9))
    left_c = None if left_c is None else [(a, b, n_lift if f0 < 0 else f0) for a, b, f0 in left_c]
    right_c = None if right_c is None else [(a, b, n_lift if f0 < 0 else f0) for a, b, f0 in right_c]
    lift_z = [g_L[2] - STEP * (n_lift - i) for i in range(n_lift + 1)]
    n_push = int(max_push / STEP); nf = n_lift + 1 + n_push

    def gp_of(g, f):
        return np.array([g[0], g[1], lift_z[f]]) if f <= n_lift else g + (f - n_lift) * STEP * pd

    def T_of(g, Rm, f):
        T = np.eye(4); T[:3, :3] = Rm; T[:3, 3] = gp_of(g, f) - 0.035 * Rm[:, 0]
        return T

    chains = []        # dict(side, cand label, f0, g, Rm, q, alive)
    res = dict(n_frames=nf, n_lift=n_lift)
    for side, cl, g in (("left", left_c, g_L), ("right", right_c, g_R)):
        if cl is None:
            continue
        f0s = sorted({c[2] for c in cl})
        for f0 in f0s:
            cc = [c for c in cl if c[2] == f0]
            sols = first_solutions(side, [T_of(g, c[0], f0) for c in cc], ctx.q[side], ctx)
            for c, ss in zip(cc, sols):
                for q in ss:
                    chains.append(dict(side=side, lab=c[1], f0=f0, g=g, Rm=c[0], q=q, alive=True))
        res[side + "_cands"] = len(cl); res[side + "_start_chains"] = sum(1 for c in chains if c["side"] == side)
        if not any(c["side"] == side for c in chains):
            res.update(limit_frame=-1, stop_reason="%s手抓取位姿 IK 无解（多起点 margin 0.03）或撞" % ("左" if side == "left" else "右")); return res
    L_ = [i for i, c in enumerate(chains) if c["side"] == "left"]
    R_ = [i for i, c in enumerate(chains) if c["side"] == "right"]
    pairs = {(a, b) for a in L_ for b in (R_ if R_ else [None])}
    last_ok = None; reason = None
    for f in range(nf):
        started = [i for i, c in enumerate(chains) if c["f0"] <= f and c["alive"]]
        # advance
        for side in ("left", "right"):
            idx = [i for i in started if chains[i]["side"] == side and chains[i]["f0"] < f]
            if idx:
                qn, ok = step_ik(side, [T_of(chains[i]["g"], chains[i]["Rm"], f) for i in idx], [chains[i]["q"] for i in idx])
                for i, q_, o in zip(idx, qn, ok):
                    if o: chains[i]["q"] = q_
                    else: chains[i]["alive"] = False
        # evaluation of every pair that is still alive
        why = {"IK 不连续/出可达范围": 0, "左臂撞固定物/桌": 0, "右臂撞固定物/桌": 0, "两臂相撞": 0, "两手间距/夹爪包络": 0}
        surv = set(); best = None
        for a, b in pairs:
            ca = chains[a]; cb = chains[b] if b is not None else None
            if not ca["alive"] or (cb is not None and not cb["alive"]):
                why["IK 不连续/出可达范围"] += 1; continue
            a_on = ca["f0"] <= f; b_on = cb is not None and cb["f0"] <= f
            if not a_on and not b_on:
                surv.add((a, b)); continue
            oth = ("right", cb["q"], True) if b_on else ("right", ctx.q["right"], True)
            if a_on:
                cl_ = cap_clear("left", ca["q"], ctx, other=oth)
                if min(cl_["fix"], cl_["table"]) < 0.01: why["左臂撞固定物/桌"] += 1; continue
                if cl_["arms"] < 0.01: why["两臂相撞"] += 1; continue
            if b_on:
                oth_l = ("left", ca["q"], True) if a_on else ("left", ctx.q["left"], True)
                cr = PN.arm_clearance("right", cb["q"], ctx.fix, other=oth_l, grip_open=False)
                if min(cr["fixtures"], cr["table"]) < 0.01: why["右臂撞固定物/桌"] += 1; continue
                if cr.get("arms", 1) < 0.01: why["两臂相撞"] += 1; continue
            if a_on and b_on:
                TL, TR = T_of(ca["g"], ca["Rm"], f), T_of(cb["g"], cb["Rm"], f)
                if np.linalg.norm(TL[:3, 3] - TR[:3, 3]) < 0.12 or PN.gripper_clearance(TL, TR) < 0.01:
                    why["两手间距/夹爪包络"] += 1; continue
            surv.add((a, b))
            if a_on and (best is None or cl_["link6_ring"] > best[0]):
                best = (cl_["link6_ring"], a, b, cl_)
        gpL = gp_of(g_L, f); tip = gpL + ft * u
        rr, rs = rope_ring_clear(gpL, tip, ctx)
        if surv and f > n_lift and (rr < 0 or rs < 0):
            reason = "绳撞环/立柱（绳轴到环管余量 %.1f mm，到立柱 %.1f mm）" % (rr * 1000, rs * 1000); surv = set()
        if not surv:
            reason = reason or "；".join("%s×%d" % kv for kv in why.items() if kv[1]) or "无存活链"
            res["fail_detail"] = why; break
        pairs = surv
        if best is not None:
            last_ok = dict(frame=f, link6_ring_mm=round(best[0] * 1000, 1), pairs=len(surv), pass_m=round(pass_len(tip, u, ctx)[0], 4), pass_arc_m=round(pass_len(tip, u, ctx)[1], 4),
                           tip=np.round(tip, 4).tolist(), tcp_left=np.round(T_of(g_L, chains[best[1]]["Rm"], f)[:3, 3], 4).tolist(), rope_ring_mm=round(rr * 1000, 1),
                           rope_radial_dev_mm=round(radial_dev(tip, u, ctx) * 1000, 1), left=chains[best[1]]["lab"],
                           right=(chains[best[2]]["lab"] if best[2] is not None else None), fix_clear_mm=round(min(best[3]["fix"], best[3]["table"]) * 1000, 1),
                           ring_any_mm=round(best[3]["ring_any"] * 1000, 1))
            if f == n_lift:
                res["at_push_start"] = dict(last_ok, right_alive=sorted({chains[b]["lab"] for _, b in surv if b is not None}),
                                            left_alive=sorted({chains[a]["lab"] for a, _ in surv}))
    res["limit_frame"] = -1 if last_ok is None else last_ok["frame"]
    res["limit"] = last_ok
    res["push_m"] = None if last_ok is None else round(max(0, last_ok["frame"] - n_lift) * STEP, 3)
    res["pass_at_limit_m"] = None if last_ok is None else last_ok.get("pass_m")
    res["pass_arc_at_limit_m"] = None if last_ok is None else last_ok.get("pass_arc_m")
    res["stop_reason"] = reason or "推入到 %.2f m 仍可行（扫描上限）" % max_push
    if R_ and last_ok is not None:
        res["right_alive_at_limit"] = sorted({chains[b]["lab"] for _, b in pairs if b is not None})
        res["n_pairs_at_limit"] = len(pairs)
    return res


def th_u(ctx, th):
    t = np.radians(th)
    return np.r_[np.cos(t) * ctx.h[:2], np.sin(t)]


def job_b(a):
    ft, th, aim, push = a
    ctx = _CTX
    u = th_u(ctx, th)
    tip0 = TIP_GIVEN if aim == "given" else aimed_tip(u, ctx, tip_before_dist(ctx))
    pd = {"chord": u, "horiz": ctx.h, "half": th_u(ctx, th / 2)}[push]
    r = run_case(ctx, u, tip0, ft, push_dir=pd, left_c=cands_vertical(ctx.h))
    r.update(case="b", ft=ft, theta=th, aim=aim, push=push, tip0=np.round(tip0, 4).tolist(), rope_radial_dev0_mm=round(radial_dev(tip0, u, ctx) * 1000, 1))
    return r


def job_a(a):
    ft, k, mode, left_mode = a
    ctx = _CTX
    u = ctx.h
    if mode == "left_only":
        r = run_case(ctx, u, TIP_GIVEN, ft, left_c=cands_vertical(ctx.h))
    else:
        rc = cands_tilted(ctx.h, "top" if mode.startswith("top") else "below", 0 if mode == "top_table" else -1)
        lc = cands_vertical(ctx.h)
        r = run_case(ctx, u, TIP_GIVEN, ft, left_c=lc, right_c=rc, k=k)
    r.update(case="a", ft=ft, k=k, mode=mode)
    return r


_CTX = None
if __name__ == "__main__":
    from multiprocessing import Pool
    ap = argparse.ArgumentParser()
    ap.add_argument("--nproc", type=int, default=6)
    ap.add_argument("--part", default="ab")
    a = ap.parse_args()
    _CTX = Ctx()
    out = {}
    fn = W + "/evidence/medium_layout/yaw15_hold_eval.json"
    jobs_b = [(ft, th, aim, push) for ft in (0.12, 0.15, 0.19) for th in (0, 20, 30, 40, 45, 50, 60) for aim in ("given", "aimed") for push in ("chord", "horiz", "half")]
    jobs_a = [(ft, None, "left_only", None) for ft in (0.12, 0.15, 0.19)] + [(ft, round(k, 2), mode, None) for ft in (0.19, 0.15, 0.12) for k in np.arange(0.08, 0.1501, 0.01)
                                                                          for mode in ("top_table", "top_lifted", "below_lifted")]
    with Pool(a.nproc) as pool:
        resb = pool.map(job_b, jobs_b) if "b" in a.part else []
        resa = pool.map(job_a, jobs_a) if "a" in a.part else []
    json.dump(dict(ctx=dict(c=_CTX.c.tolist(), n=_CTX.n.tolist(), d=_CTX.d.tolist(), h=_CTX.h.tolist(), tip_given=TIP_GIVEN.tolist()), b=resb, a=resa), open(fn, "w"), indent=1, default=str)
    print("DONE", len(resb), len(resa))
