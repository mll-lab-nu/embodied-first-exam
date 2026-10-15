"""Per-step offline evaluation of medium layouts (numpy only; OMP_NUM_THREADS=1), built on medium_layout_search.

For one ring-group placement (yaw, t) and one route (forward = END tip first R1->R2->R3, left picks, or --reverse = START
tip first R3->R2->R1, right picks) it reports the number of feasible poses of every step, in feeding order:
  ready (both arms; 3 candidates each) -> pick (pick_detail = pick_ok split up: first pinch, two more pinches, drag-edge pose; pass = first pinch and edge pose) -> transition
  (new: pick end state -> first feed frame) -> per ring: feed (both arms) -> receive (both arms) -> hand-over pairs.
Feed / receive strokes are medium_layout_search.stroke_solutions with a large `keep` (a diagnostic copy counts where
the candidates die). Hand-over pairs: feeder end pose + receiver start pose with capsule clearance >= 1 cm AND the two
TCPs >= 12 cm apart.

Transition (offline version of oracle.pick's flip + oracle.to_feed_frame): after the flip the picking arm holds the rope
at the flip point (0.60, +-0.40, ring-1 height - 0.01) with TCP z along the ring-1 travel direction and approach a1 =
pitched(+x, 30 deg) (oracle.pick's settle onto frame_az(a1, zs*travel)). The held chord (grip point -> tip) is assumed to
sit `theta` deg off z_tcp (rotation about the jaw axis y; theta = 0 is the ideal rope, the measured pivot of the
yaw-195 runs is ~36 deg). to_feed_frame's logic: keep the pose if the chord is within 15 deg of the travel and the feed
start/end grip poses (0.24 / 0.07 m before the plane) are reachable; else look for a feed direction (travel, then 10 / 18 /
25 deg off it up to --cone, every 45 deg) x chord-correction fraction (1, 2/3, 1/3, 0) x approach (perp_approaches)
whose feed frame has reachable start+end poses AND an in-place rotation (about the held rope point, slerp, 13 steps, IK
continuous, capsule clearance >= 8 mm, other arm at its ready q) from the flip pose. Nothing about the rope's physics
beyond `theta` is modelled (reseat press and the pick's drags are not simulated).
"""
import json, sys, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import medium_layout_search as M
import plan_np as PN
import yam_kin as K
from reach_map import seeds_for
from scipy.spatial.transform import Rotation as Rot, Slerp

EZ = np.array([0, 0, 1.0])
OFF = np.array([0.012, 0, 0])            # held rope point in the TCP frame (rope 12 mm inside the pads)
A1 = PN.pitched(np.array([1.0, 0, 0]), 30.0)
KEEP = 50
SEQ = ("ready", "pick", "transition")


def fixture(rings):
    return PN.fixture_capsules([dict(r, center=r["center"].tolist(), normal=r["normal"].tolist(),
                                     stand_center=r["stand_center"].tolist()) for r in rings])


def stroke_diag(side, c, d, ts, fix, cone, keep=KEEP):
    """medium_layout_search.stroke_solutions with counts of where the candidates die."""
    cand = M.stroke_frames(c, d, cone, ts)
    diag = dict(cand=len(cand), ik0=0, path=0, clear=0)
    devs, strokes = zip(*cand)
    base = K.BASES[side]
    first = np.array([s[0] for s in strokes]); first[:, :3, 3] -= base
    seeds = np.array(seeds_for(first[0, :3, 3]))
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
    diag["ik0"] = len(chains)
    for i in range(1, len(ts)):
        if not chains:
            break
        Tb = np.array([strokes[k][i] for k, _ in chains]); Tb[:, :3, 3] -= base
        prev = np.array([qs[-1] for _, qs in chains])
        qn, ep, er = M.ik_batch(Tb, prev, 100, 0.02)
        good = (ep < 1.5e-3) & (er < 3e-2) & (np.abs(qn - prev).max(1) < 0.6)
        chains = [(k, qs + [qn[j]]) for j, (k, qs) in enumerate(chains) if good[j]]
    diag["path"] = len(chains)
    out = []
    for k, qs in chains:
        if all(min(PN.arm_clearance(side, qq, fix, grip_open=False).values()) >= 0.01 for qq in qs):
            out.append((devs[k], np.array(qs)))
    diag["clear"] = len(out)
    out.sort(key=lambda x: x[0])
    poses = {tuple(np.round(K.fk_tcp(p[0])[:3, :3].ravel(), 1)) for _, p in out}
    return out, dict(diag, poses=len(poses), dev_min=round(out[0][0], 1) if out else None)


def why(diag):
    if diag["cand"] == 0:
        return "无候选姿态"
    if diag["ik0"] == 0:
        return "行程起点姿态无 IK 解（够不到）"
    if diag["path"] == 0:
        return "行程中 IK 不连续或出可达范围（起点可达 %d 条）" % diag["ik0"]
    if diag["clear"] == 0:
        return "行程 IK 通但碰撞余量 <1 cm（%d 条）" % diag["path"]
    return ""


def tcp_world(side, q):
    return K.base_to_world(K.fk_tcp(q), side)[:3, 3]


def hand_pairs(feeds, recvs, fa, ra, fix):
    """(#pairs with capsule clearance >= 1 cm, #pairs with TCP distance >= 12 cm, #both)."""
    n_c = n_d = n_b = 0
    rt = [tcp_world(ra, r[0]) for _, r in recvs]
    for _, f in feeds:
        ft = tcp_world(fa, f[-1])
        for (_, r), p in zip(recvs, rt):
            c = PN.arm_clearance(fa, f[-1], fix, other=(ra, r[0], False))["arms"] >= 0.01
            d = np.linalg.norm(ft - p) >= 0.12
            n_c += c; n_d += d; n_b += c and d
    return n_c, n_d, n_b


# ------------------------------------------------------------------ transition (offline to_feed_frame)
def at_grip(Rm, g, off=OFF):
    T = np.eye(4); T[:3, :3] = Rm; T[:3, 3] = g - Rm @ off
    return T


def perp_approaches(d, s, target):
    h = np.cross(EZ, d); h /= np.linalg.norm(h)
    up = np.cross(d, h)
    hs = sorted((h, -h), key=lambda hh: -(hh @ (np.asarray(target) - K.BASES[s])))
    return [np.cos(np.radians(p_)) * hh - np.sin(np.radians(p_)) * up for hh in hs for p_ in (0, 30, 15, 45, 60)]


def feed_dirs(d, cone):
    h = np.cross(EZ, d); h /= np.linalg.norm(h); v = np.cross(d, h)
    return [d] + [np.cos(np.radians(dv)) * d + np.sin(np.radians(dv)) * (np.cos(np.radians(az)) * h + np.sin(np.radians(az)) * v)
                  for dv in (10, 18, 25) if dv <= cone for az in range(0, 360, 45)]


def slerp_np(side, T0, R_goal, fix, other, n=13):
    gp = T0[:3, :3] @ OFF + T0[:3, 3]
    sl = Slerp([0, 1], Rot.from_matrix(np.stack([T0[:3, :3], R_goal])))
    q = None
    for f in np.linspace(0, 1, n):
        Rm = sl(f).as_matrix(); T = np.eye(4); T[:3, :3] = Rm; T[:3, 3] = gp - Rm @ OFF
        if q is None:
            q = PN.solve(side, T, margin=0.03)
            if q is None:
                return False
        else:
            qn, o, ep, er = K.ik(K.world_to_base(T, side), q, iters=200, margin=0.02)
            if not (o or (ep < 1.5e-3 and er < 3e-2)) or np.abs(qn - q).max() > 0.5:
                return False
            q = qn
        if min(PN.arm_clearance(side, q, fix, other=(other[0], other[1], True), grip_open=False).values()) < 0.008:
            return False
    return True


def reach_many(side, Ts, q_seed, fix, other, clear=0.01, grip_open=False, margin=0.05):
    """oracle_reachable for many poses at once (batched IK from [q_seed] + seeds_for, same criteria): list of bool."""
    if not len(Ts):
        return []
    Tb = np.array(Ts, float); Tb[:, :3, 3] -= K.BASES[side]
    sd = [np.array([q_seed] + seeds_for(t[:3, 3])) for t in Tb]
    ns = len(sd[0])
    q, ep, er = M.ik_batch(np.repeat(Tb, ns, 0), np.concatenate(sd), 200, margin)
    ok = (ep < 1e-4) & (er < 1e-3)
    out = []
    for i in range(len(Tb)):
        out.append(any(min(PN.arm_clearance(side, q[i * ns + j], fix, other=other, grip_open=grip_open).values()) >= 0.004 + clear
                       for j in np.flatnonzero(ok[i * ns:(i + 1) * ns])))
    return out


def transition_zs(side, ring, fix, q_ready, q_other, theta, zs, cone=25.0, start=0.24, stop=0.07):
    """-> dict(start_ok, keep, n_frames (feed frames reachable), n_plans (feed frame + in-place rotation from the flip pose))."""
    sg = 1.0 if side == "left" else -1.0
    oside = "right" if side == "left" else "left"
    other = (oside, q_other, True)
    d, c = ring["travel"], ring["center"]
    R0 = PN.frame_az(A1, zs * d)[:3, :3]
    T0 = at_grip(R0, np.array([0.60, sg * 0.40, c[2] - 0.01]))
    out = dict(theta=theta, zs=zs, start_ok=reach_many(side, [T0], q_ready, fix, other)[0])
    th = np.radians(theta)
    c_t = np.array([np.sin(th), 0, zs * np.cos(th)])     # the held rope's chord (grip point -> tip) in the TCP frame
    ax = np.cross(c_t, zs * EZ); n = np.linalg.norm(ax)
    q_rv = np.zeros(3) if n < 1e-9 else ax / n * np.arctan2(n, c_t @ (zs * EZ))
    fracs = (1.0, 2 / 3, 1 / 3, 0.0) if n > 1e-9 else (1.0,)
    cands, seen = [], set()                      # (dd, Rm): keep-pose first, then every feed frame of oracle.feed_frames
    cands.append((d, R0))
    for dd in feed_dirs(d, cone):
        for frac in fracs:
            Q = Rot.from_rotvec(frac * q_rv).as_matrix()
            for a in perp_approaches(dd, side, c):
                Rm = PN.frame_az(a, zs * dd)[:3, :3] @ Q
                key = (tuple(np.round(dd, 4)), tuple(np.round(Rm.ravel(), 4)))
                if key not in seen:
                    seen.add(key); cands.append((dd, Rm))
    g0 = lambda dd: c - start * dd - 0.01 * EZ
    g1 = lambda dd: c - stop * dd - 0.01 * EZ
    a_ok = reach_many(side, [at_grip(Rm, g0(dd)) for dd, Rm in cands], q_ready, fix, other)
    idx = [i for i, ok in enumerate(a_ok) if ok]
    b_ok = reach_many(side, [at_grip(cands[i][1], g1(cands[i][0])) for i in idx], q_ready, fix, other, clear=-0.002)
    feed_ok = [i for i, ok in zip(idx, b_ok) if ok]
    out["keep"] = bool(out["start_ok"] and 0 in feed_ok and (R0 @ c_t) @ d > np.cos(np.radians(15)))
    frames = [i for i in feed_ok if i != 0]
    plans = sum(bool(out["start_ok"] and slerp_np(side, T0, cands[i][1], fix, (oside, q_other))) for i in frames)
    out.update(n_dirs=len(feed_dirs(d, cone)), n_cand=len(cands) - 1, n_frames=len(frames), n_plans=int(plans),
               ok=bool(out["keep"] or plans > 0))
    return out


def transition(side, ring, fix, q_ready, q_other, theta, **kw):
    """oracle.pick settles on frame_az(a1, zs * travel) with either sign of z_tcp: both are tried; counts are summed."""
    parts = [transition_zs(side, ring, fix, q_ready, q_other, theta, zs, **kw) for zs in (1, -1)]
    return dict(theta=theta, start_ok=any(p["start_ok"] for p in parts), keep=any(p["keep"] for p in parts),
                n_dirs=parts[0]["n_dirs"], n_cand=sum(p["n_cand"] for p in parts), n_frames=sum(p["n_frames"] for p in parts),
                n_plans=sum(p["n_plans"] for p in parts), ok=any(p["ok"] for p in parts),
                by_zs={str(p["zs"]): dict(start_ok=p["start_ok"], n_frames=p["n_frames"], n_plans=p["n_plans"]) for p in parts})


def pick_detail(xy, fix, side, q_ready, q_other, tip_is_start=None):
    """medium_layout_search.pick_ok with the parts kept apart: first pinch (0.15 m from the tip, grasp + 8 cm pre-grasp,
    top-down, either rope sense), the other two pinches (0.12 / 0.20 m) and the drag target pose at the table edge."""
    sg = 1 if side == "left" else -1
    P = np.c_[xy, np.full(len(xy), M.TABLE + 0.004)][::sg * -1]
    if tip_is_start is not None:       # xy in material order; the picked tip is the start (True) or the end (False)
        P = np.c_[xy, np.full(len(xy), M.TABLE + 0.004)]
        P = P if tip_is_start else P[::-1]
    s_ = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    other = ("right" if side == "left" else "left", q_other, True)

    def pinch(i):
        t = P[max(i - 1, 0)] - P[i]; t[2] = 0; t /= np.linalg.norm(t)
        for zs in (-1, 1):
            Tg = PN.frame_az(np.array([0, 0, -1.0]), zs * t); Tg[:3, 3] = P[i] + (0, 0, 0.035)
            Tp = Tg.copy(); Tp[:3, 3] += (0, 0, 0.08)
            if M.oracle_reachable(side, Tg, q_ready, fix, other) and M.oracle_reachable(side, Tp, q_ready, fix, other):
                return True
        return False

    i12, i15, i20 = [int(np.searchsorted(s_, d)) for d in (0.12, 0.15, 0.20)]
    first = pinch(i15)
    out = dict(first=first, p12=None, p20=None, edge=None)
    if first:
        out["p12"], out["p20"] = pinch(i12), pinch(i20)
        T = PN.frame_az(np.array([0, 0, -1.0]), np.array([0, sg * 1.0, 0]))
        T[:3, 3] = np.array([P[0, 0], sg * 0.60, M.TABLE + 0.004]) + (0, 0, 0.035)
        out["edge"] = bool(M.oracle_reachable(side, T, q_ready, fix, other))
    out["n"] = int(first + (out["p12"] or 0) + (out["p20"] or 0) + (out["edge"] or 0)) if first else 0
    out["ok"] = bool(first and out["edge"])
    return out


def chain_search(order, res):
    """Arm assignments (feeder f_k, receiver r_k per ring but the last) whose hand-overs are valid and where the receiver of
    ring k feeds ring k+1 itself (r_k == f_k+1: no arm-to-arm transfer between rings). f_k == r_k (the oracle's 'LL': the
    feeder pushes again while the other arm clamps) is allowed and marked with '*'; it is not checked offline.
    -> (list of chain strings like 'R>L L>L* L', reason when there is none)."""
    n = len(order)
    feed = [{s[0].upper() for s in ("left", "right") if res[r["name"] + "_feed"][s]["clear"]} for r in order]
    recv = [{s[0].upper() for s in ("left", "right") if res[r["name"] + "_recv"][s]["clear"]} for r in order[:-1]]
    chains, deepest = [], 0

    def rec(k, f, acc):
        nonlocal deepest
        deepest = max(deepest, k)
        if k == n - 1:
            chains.append(" ".join(acc + [f]))
            return
        for r in sorted(recv[k]):
            if f != r and not res[order[k]["name"] + "_hand"][f + r]["both"]:
                continue
            if r in feed[k + 1]:
                rec(k + 1, r, acc + [f + ">" + r + ("*" if f == r else "")])
    for f in sorted(feed[0]):
        rec(0, f, [])
    if chains:
        return chains, None
    return [], "第 %d 环（%s）之后接不上：上一环的接收臂不能喂下一环，需要臂间转交（未做离线检查）" % (deepest + 1, order[deepest]["name"]) if deepest else "第一环无臂可喂"


# ------------------------------------------------------------------ one layout, one route
def evaluate_layout(args):
    """args: dict(yaw, t, rope_t, rope_yaw, reverse, thetas) -> result dict."""
    yaw, t, reverse = args["yaw"], tuple(args["t"]), args["reverse"]
    M.RINGS_ONLY = True
    res = dict(args, fits_rings=M.fits(yaw, t, 0.01))
    rings, _ = M.place(yaw, t)
    fix = fixture(rings)
    # ready: how many of the 3 candidates each arm reaches (as Runner.goto from home); the first one is used downstream
    q_ready = {}
    for side in ("left", "right"):
        sg = 1 if side == "left" else -1
        other = ("right" if side == "left" else "left", M.HOME, True)
        qs = [M.goto_q(side, PN.frame((0.7071, 0, -0.7071), (0, 1, 0), (x, sg * y, z)), M.HOME, fix, other) for x, y, z in M.READY]
        res["ready_" + side] = sum(q is not None for q in qs)
        q_ready[side] = next((q for q in qs if q is not None), None)
    res["ready_ok"] = all(q_ready[s] is not None for s in q_ready)
    # rope: yaw 90 (U arms along y, start on -y), t from the config when given, else M.rope_place
    side = "right" if reverse else "left"
    if args.get("rope_t") is not None:
        rxy = M.M_ROPE_XY @ M.rot(args["rope_yaw"])[:2, :2].T + np.asarray(args["rope_t"])
        res["rope_ty"] = args["rope_t"][1]
    else:
        rp = M.rope_place(rings)
        rxy = rp[2] if rp else None
        res["rope_ty"] = rp[1] if rp else None
        res["rope_clear"] = round(rp[0], 3) if rp else None
    if rxy is not None and res["ready_ok"]:
        pk = pick_detail(rxy, fix, side, q_ready[side], q_ready["right" if side == "left" else "left"])
        res["pick"] = "%d/4" % pk["n"]; res["pick_detail"] = pk; res["pick_ok"] = pk["ok"]
    else:
        res["pick"] = None; res["pick_ok"] = False
    # rings in feeding order
    rr = [dict(r, travel=r["sign"] * r["normal"]) for r in rings]
    order = rr[::-1] if reverse else rr
    if reverse:
        order = [dict(r, travel=-r["travel"]) for r in order]
    res["order"] = [r["name"] for r in order]
    # transition
    res["transition"] = {}
    if res["ready_ok"]:
        for th in args["thetas"]:
            res["transition"][str(th)] = transition(side, order[0], fix, q_ready[side], q_ready["right" if side == "left" else "left"], th)
    # strokes
    for i, r in enumerate(order):
        for kind in ("feed", "recv"):
            if kind == "recv" and i == len(order) - 1:
                continue
            ts = M.FEED_TS if kind == "feed" else M.RECV_TS
            sol, entry = {}, {}
            for s in ("left", "right"):
                sol[s], dg = stroke_diag(s, r["center"], r["travel"], ts, fix, 25.0)
                dg["why"] = why(dg)
                entry[s] = dg
            res[f"{r['name']}_{kind}"] = entry
            res.setdefault("_sol", {})[(r["name"], kind)] = sol
        if i < len(order) - 1:
            hp = {}
            fs, rs = res["_sol"][(r["name"], "feed")], res["_sol"][(r["name"], "recv")]
            for fa, ra in (("left", "right"), ("right", "left")):
                if fs[fa] and rs[ra]:
                    hp[fa[0].upper() + ra[0].upper()] = dict(zip(("clear1cm", "dist12cm", "both"), map(int, hand_pairs(fs[fa], rs[ra], fa, ra, fix))))
                else:
                    hp[fa[0].upper() + ra[0].upper()] = dict(clear1cm=0, dist12cm=0, both=0)
            res[f"{r['name']}_hand"] = hp
    res.pop("_sol")
    res["chains"], res["chain_fail"] = chain_search(order, res)
    # first failing step, in feeding order
    steps = []
    steps.append(("ready", res["ready_ok"], "左 %d/3，右 %d/3 个 ready 候选可达" % (res["ready_left"], res["ready_right"])))
    steps.append(("pick", res["pick_ok"], ("捡绳 %s：首抓点%s，拖到桌边姿态%s" % (res["pick"], "可达" if res["pick_detail"]["first"] else "不可达", {True: "可达", False: "不可达", None: "未算"}[res["pick_detail"]["edge"]])) if res.get("pick_detail") else "绳起点无法放入桌面或 ready 失败"))
    tr = res["transition"].get("0.0") or res["transition"].get("0")
    steps.append(("transition", bool(tr and tr["ok"]),
                  "捡绳末态→喂入：起点可达=%s，保持=%s，喂入姿态 %d，带旋转路径的可行方案 %d" % (
                      tr["start_ok"], tr["keep"], tr["n_frames"], tr["n_plans"]) if tr else "ready 失败，未算"))
    for i, r in enumerate(order):
        nm = r["name"]
        e = res[nm + "_feed"]
        steps.append((nm + "_feed", any(e[s]["clear"] for s in e), "; ".join(f"{'左' if s == 'left' else '右'}: {e[s]['why'] or '可行'}" for s in e)))
        if i < len(order) - 1:
            e = res[nm + "_recv"]
            steps.append((nm + "_recv", any(e[s]["clear"] for s in e), "; ".join(f"{'左' if s == 'left' else '右'}: {e[s]['why'] or '可行'}" for s in e)))
            h = res[nm + "_hand"]
            steps.append((nm + "_hand", any(v["both"] for v in h.values()),
                          "; ".join(f"{k}:{v['both']}对(余量≥1cm {v['clear1cm']}，间距≥12cm {v['dist12cm']})" for k, v in h.items())))
    steps.append(("chain", bool(res["chains"]), "；".join(res["chains"][:6]) if res["chains"] else res["chain_fail"]))
    res["steps"] = [dict(step=a, ok=bool(b), note=c) for a, b, c in steps]
    bad = next((s for s in res["steps"] if not s["ok"]), None)
    res["all_ok"] = bad is None and res["fits_rings"]
    res["first_fail"] = None if bad is None else bad["step"]
    res["first_fail_reason"] = None if bad is None else bad["note"]
    return res


if __name__ == "__main__":
    import time
    t0 = time.time()
    r = evaluate_layout(dict(yaw=195.0, t=(0.54, 0.12), rope_t=(0.58, -0.05), rope_yaw=90.0, reverse=True, thetas=[0.0, 36.0, -36.0]))
    print(json.dumps({k: v for k, v in r.items() if k != "steps"}, indent=1, default=str)[:4000])
    for s in r["steps"]:
        print(s)
    print("time", time.time() - t0)
