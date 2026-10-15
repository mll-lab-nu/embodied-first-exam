"""D12 (user-approved 2026-10-14): the yaw 15 ring group is translated (t only; yaw 15 and the mirrored rope start of D11 kept,
rope t re-chosen per t). This screens t on a 2 cm grid and picks a t with margin: every neighbour within +-2 cm in x and y passes
every check too.

Per ring-group t (offline, numpy):
  * fits: all stand bases on the table collider (1 cm margin, medium_layout_search.fits);
  * rope t, ready, left pick of the start tip at the left edge (pick_detail tip_is_start=True), pick end -> R3 feed transition:
    layout_eval_mirror.evaluate (rope t re-chosen per t exactly as there);
  * easy transfer: easy's left-arm commands from or3 (evidence/or3/actions.npy, steps 2700..3440 every 20 = 38 samples:
    flip pose, 180 deg wrist roll, settle on the feed frame, push through R1) moved rigidly from easy R1 (centre
    (0.599, 0.075, 1.0819), travel -y) onto R3 (travel -sign n, frame (d, h = z x d, d x h)); per sample IK (margin 0.02)
    seeded with the previous sample (continuous = solved from it with max joint jump < 0.5 rad), else re-seeded with
    seeds_for; capsule clearance of the left arm to rings / stands / table / the right arm at ready (diagnostic);
  * oracle flip replica (the oracle's own motion, not easy's): oracle.pick's 18 x 10 deg wrist roll about the approach a1 at
    the flip grip point (flip_x, flip_y, R3 z - 0.01), the settle onto frame_az(a1, zs * travel_R3), the line to the R3 feed start
    (0.24 m before the plane) and the push to 0.07 m; ideal rope (chord = z_tcp, held 12 mm inside the pads); Runner.plan_line
    criteria (IK margin 0.02, joint jump <= 0.25 rad, clearance >= 4 mm every 3rd point, right arm at ready). Flip points: the
    oracle default (0.60, 0.40), easy's flip point moved with the same rigid transform, and a grid x 0.56..0.64 x y 0.30..0.42;
  * strokes (layout_eval.stroke_diag, cone 25, as yaw15_mirror_eval.md): poses per arm for R3 feed / recv, R2 feed / recv, R1 feed.
  * sim rope (sim_rope, the rope t used from here on): layout_eval_mirror's choice puts the start tip at the left table edge, where
    oracle.pick's first step (pinch 0.15 m from the tip, yaw the tip toward +y) has no IK (drag1_check; run X1a_ropeEdge failed there),
    so the rope t is the valid placement (clearance >= 3 cm, pick_detail ok, drag1 ok) whose start tip is nearest the D11 rope's (0.58, -0.09).
A t passes when: bases fit, a sim rope exists, ready, easy transfer 38/38, some oracle flip point passes, R3 feed (left) and every
other stroke (either arm) has a pose. Choice: passing t whose 8 grid neighbours (+-2 cm) pass, ranked by choice_key (weakest stroke
step, R1 feed poses, smallest margin, the other stroke counts); margin = passing grid distance from t in +-x / +-y until the first
failing t (or the grid end).
Results of earlier runs in the json are reused (only missing fields are computed).
Usage: python layout_eval_shift.py --nproc 6        -> evidence/medium_layout/yaw15_shift_eval.json
       python layout_eval_shift.py --report         -> evidence/medium_layout/yaw15_shift_eval.md + yaw15_shift_best.png
"""
import argparse, json, os, sys, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layout_eval as L
import layout_eval_mirror as LM
import medium_layout_search as M
import plan_np as PN
import yam_kin as K
from reach_map import seeds_for
from scipy.spatial.transform import Rotation as Rot, Slerp

W = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUT = W + "/evidence/medium_layout/yaw15_shift_eval"
EZ = np.array([0, 0, 1.0])
XS = tuple(round(0.532 + 0.02 * i, 3) for i in range(7))          # 0.532 .. 0.652
YS = tuple(round(-0.271 - 0.02 * i, 3) for i in range(7))         # -0.271 .. -0.391 (-0.391: the -y margin of the y -0.351 row)
T_NOW = (0.532, -0.241)                       # current (D11) ring group t, reference row
EASY_C, EASY_D = np.array([0.599, 0.075, 1.0819]), np.array([0.0, -1.0, 0.0])
STEPS = list(range(2700, 3451, 20))
FLIP_EASY = np.array([0.60, 0.40, 1.0719])   # easy's flip grip point (oracle default flip_x / flip_y, R1 z - 0.01)
FLIP_GRID = [(x, y) for y in (0.30, 0.33, 0.36, 0.385, 0.40, 0.42) for x in (0.56, 0.58, 0.60, 0.62, 0.64)]
OFF = np.array([0.012, 0, 0])
STROKES = (("R3", "feed"), ("R3", "recv"), ("R2", "feed"), ("R2", "recv"), ("R1", "feed"))


def ring_frame(d):
    d = d / np.linalg.norm(d); h = np.cross(EZ, d); h /= np.linalg.norm(h)
    return np.c_[d, h, np.cross(d, h)]


def easy_transfer(ring, fix, q_right, margin=0.02):
    A = np.load(W + "/evidence/or3/actions.npy")
    G = ring_frame(ring["travel"]) @ ring_frame(EASY_D).T
    q, n_ok, n_cont, first_bad, clears, rows = None, 0, 0, None, [], []
    for i in STEPS:
        T = K.base_to_world(K.fk_tcp(A[i, 0:6]), "left")
        T2 = np.eye(4); T2[:3, :3] = G @ T[:3, :3]; T2[:3, 3] = ring["center"] + G @ (T[:3, 3] - EASY_C)
        Tb = K.world_to_base(T2, "left")
        cont = False
        if q is not None:
            qn, ok, _, _ = K.ik(Tb, q, margin=margin)
            if ok and np.abs(qn - q).max() < 0.5:
                cont, q = True, qn
        solved = cont
        if not cont:
            for sd in ([q] if q is not None else []) + seeds_for(Tb[:3, 3]):
                qn, ok, _, _ = K.ik(Tb, sd, margin=margin)
                if ok:
                    q, solved = qn, True
                    break
        if not solved and first_bad is None:
            first_bad = i
        n_ok += solved; n_cont += cont
        c = min(PN.arm_clearance("left", q, fix, other=("right", q_right, True), grip_open=False).values()) if solved else None
        clears.append(c)
        rows.append(dict(step=i, ok=bool(solved), cont=bool(cont), clear=None if c is None else round(float(c), 4)))
    cs = [c for c in clears if c is not None]
    return dict(n=len(STEPS), ok=int(n_ok), cont=int(n_cont), first_fail_step=first_bad, all_ok=n_ok == len(STEPS),
                min_clear=round(float(min(cs)), 4) if cs else None, n_clear_lt4mm=int(sum(c < 0.004 for c in cs)), samples=rows)


def _line(q, T0, T1, n, fix, oth):
    """Runner.plan_line offline (left arm): joint targets along the line, None + reason on failure."""
    sl = Slerp([0, 1], Rot.from_matrix(np.stack([T0[:3, :3], T1[:3, :3]])))
    for i in range(1, n + 1):
        f = 0.5 - 0.5 * np.cos(np.pi * i / n)
        T = np.eye(4); T[:3, :3] = sl(f).as_matrix(); T[:3, 3] = T0[:3, 3] + f * (T1[:3, 3] - T0[:3, 3])
        qn, ok, ep, er = K.ik(K.world_to_base(T, "left"), q, iters=200, margin=0.02)
        if not (ok or (ep < 1.5e-3 and er < 3e-2)) or np.abs(qn - q).max() > 0.25:
            return None, "ik %d/%d" % (i, n)
        if (i % 3 == 0 or i == n) and min(PN.arm_clearance("left", qn, fix, other=oth, grip_open=False).values()) < 0.004:
            return None, "clear %d/%d" % (i, n)
        q = qn
    return q, ""


def _n(T0, T1, speed, ang_speed):
    d = np.linalg.norm(T1[:3, 3] - T0[:3, 3]); a = np.linalg.norm(Rot.from_matrix(T1[:3, :3] @ T0[:3, :3].T).as_rotvec())
    return max(8, int(np.ceil(30 * max(d / speed, a / ang_speed))))


def oracle_flip(ring, fix, q_right, gp):
    """oracle.pick's flip + settle, to_feed_frame's line to the feed start, feed's push (see the module docstring).
    -> 'ok' or the first failing part ('flip<k> ik i/n', 'settle ...', 'tostart ...', 'push ...', 'no start')."""
    at = lambda Rm, g: np.r_[np.c_[Rm, g - Rm @ OFF], [[0, 0, 0, 1.0]]]
    a1 = PN.pitched(np.array([1.0, 0, 0]), 30.0)
    c, d = ring["center"], ring["travel"]
    gp = np.asarray(gp, float)
    oth = ("right", q_right, True)
    T = at(PN.frame_az(a1, np.array([0, 1.0, 0]))[:3, :3], gp)          # before the flip: approach a1, tip toward +y
    q = PN.solve("left", T, margin=0.05)
    if q is None:
        return "no start"
    for k in range(18):
        T1 = at(Rot.from_rotvec(T[:3, 0] * np.radians(10.0)).as_matrix() @ T[:3, :3], gp)
        q, why = _line(q, T, T1, _n(T, T1, 0.03, 0.5), fix, oth)
        if q is None:
            return "flip%d %s" % (k, why)
        T = T1
    zs = 1 if T[:3, 2] @ d > 0 else -1
    T1 = at(PN.frame_az(a1, zs * d)[:3, :3], gp)
    q, why = _line(q, T, T1, _n(T, T1, 0.03, 0.4), fix, oth)
    if q is None:
        return "settle " + why
    T = T1
    for nm, g, sp in (("tostart", c - 0.24 * d - 0.01 * EZ, 0.03), ("push", c - 0.07 * d - 0.01 * EZ, 0.05)):
        T1 = at(T[:3, :3], g)
        q, why = _line(q, T, T1, _n(T, T1, sp, 0.8), fix, oth)
        if q is None:
            return nm + " " + why
        T = T1
    return "ok"


def drag1_check(rope_t, fix, q_left, q_right):
    """oracle.pick's first step offline: top-down pinch 0.15 m from the start tip (either jaw sense, grasp + 8 cm pre-grasp
    reachable), lift 3 cm, yaw about the vertical through the rope point until the tip points +y: Runner.plan_line, else a
    collision-free joint-space move (medium_layout_search.goto_q, as Runner.goto). -> 'line' / 'route' / reason."""
    P = np.c_[LM.rope_xy(rope_t), np.full(len(M.ROPE), M.TABLE + 0.004)]          # material order: the start tip first
    s_ = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    i = int(np.searchsorted(s_, 0.15)); f = (0.15 - s_[i - 1]) / (s_[i] - s_[i - 1])
    pt = P[i - 1] + f * (P[i] - P[i - 1]); th = P[i - 1] - P[i]; th[2] = 0; th /= np.linalg.norm(th)
    oth = ("right", q_right, True)
    for zs in (-1, 1):
        Tg = PN.frame_az(-EZ, zs * th); Tg[:3, 3] = pt + 0.035 * EZ
        Tp = Tg.copy(); Tp[:3, 3] += 0.08 * EZ
        if M.oracle_reachable("left", Tg, q_left, fix, oth) and M.oracle_reachable("left", Tp, q_left, fix, oth):
            break
    else:
        return "pinch unreachable"
    T = Tg.copy(); T[:3, 3] += 0.03 * EZ
    q, why = _line(PN.solve("left", Tg, q_left), Tg, T, 8, fix, oth)
    if q is None:
        return "lift " + why
    ang = np.arctan2(np.cross(th, [0, 1.0, 0]) @ EZ, th @ [0, 1.0, 0])
    T1 = np.eye(4); T1[:3, :3] = Rot.from_rotvec(EZ * ang).as_matrix() @ T[:3, :3]; T1[:3, 3] = pt + 0.03 * EZ - T1[:3, :3] @ [0.035, 0, 0]
    q1, why = _line(q, T, T1, max(8, int(np.ceil(30 * abs(ang) / 0.4))), fix, oth)
    if q1 is not None:
        return "line"
    return "route" if M.goto_q("left", T1, q, fix, oth) is not None else "yaw %.0f deg: line %s, no joint route" % (np.degrees(ang), why)


def sim_rope(t):
    """Rope t for the sim (see the module docstring) -> (rope t, clearance, drag1 of the layout_eval_mirror choice)."""
    M.RINGS_ONLY = True
    rings, _ = M.place(15.0, t)
    fix = L.fixture(rings)
    q = {s: next((q_ for q_ in (M.goto_q(s, PN.frame((0.7071, 0, -0.7071), (0, 1, 0), (x, sg * y, z)), M.HOME, fix, (o, M.HOME, True))
                                for x, y, z in M.READY) if q_ is not None), None)
         for s, sg, o in (("left", 1, "right"), ("right", -1, "left"))}
    if any(v is None for v in q.values()):
        return None, None, q
    tip0 = LM.rope_xy((0.58, -0.09))[0]
    for c in sorted(LM.place_rope(rings, 15.0), key=lambda c: np.linalg.norm(LM.rope_xy(c["t"])[0] - tip0)):
        if c["clear"] >= 0.03 and L.pick_detail(LM.rope_xy(c["t"]), fix, "left", q["left"], q["right"], tip_is_start=True)["ok"] \
                and drag1_check(c["t"], fix, q["left"], q["right"]) in ("line", "route"):
            return c["t"], c["clear"], q
    return None, None, q


def evaluate(a):
    t0 = time.time()
    t = tuple(a["t"])
    if a.get("prev"):
        res = a["prev"]
        if "sim_rope" not in res:
            rt, cl, _ = sim_rope(t)
            res["sim_rope"] = dict(t=rt, clear=cl, start_tip=None if rt is None else np.round(LM.rope_xy(rt)[0], 3).tolist())
        print("reused", t); sys.stdout.flush()
        return res
    res = LM.evaluate(dict(yaw=15.0, t=t))         # fits, rope t, ready, pick, transition (sets M.RINGS_ONLY)
    rings, _ = M.place(15.0, t)
    fix = L.fixture(rings)
    order = [dict(r, travel=-r["sign"] * r["normal"]) for r in rings[::-1]]     # reverse route: R3, R2, R1
    byn = {r["name"]: r for r in order}
    res["ring_centres"] = {r["name"]: np.round(r["center"], 3).tolist() for r in order}
    q_right = next((q for q in (M.goto_q("right", PN.frame((0.7071, 0, -0.7071), (0, 1, 0), (x, -y, z)), M.HOME, fix, ("left", M.HOME, True))
                                for x, y, z in M.READY) if q is not None), None)
    if q_right is None:          # no right ready pose (oracle.ready's candidates): the t fails at ready, nothing else is computed
        res.update(transfer=dict(n=len(STEPS), ok=0, cont=0, first_fail_step=None, all_ok=False, min_clear=None, n_clear_lt4mm=0, samples=[]),
                   flip=dict(default="no ready", easy_rel_xy=[0, 0], easy_rel="no ready", grid_ok=[], grid={}),
                   strokes={nm + "_" + kind: {s_: dict(poses=0) for s_ in ("left", "right")} for nm, kind in STROKES},
                   sim_rope=dict(t=None, clear=None, start_tip=None), secs=round(time.time() - t0, 1))
        print("done (no right ready)", t); sys.stdout.flush()
        return res
    res["transfer"] = easy_transfer(byn["R3"], fix, q_right)
    G = ring_frame(byn["R3"]["travel"]) @ ring_frame(EASY_D).T
    g_easy = byn["R3"]["center"] + G @ (FLIP_EASY - EASY_C)
    z = byn["R3"]["center"][2] - 0.01
    grid = {"%.3f,%.3f" % xy: oracle_flip(byn["R3"], fix, q_right, (*xy, z)) for xy in FLIP_GRID}
    res["flip"] = dict(default=oracle_flip(byn["R3"], fix, q_right, (0.60, 0.40, z)), easy_rel_xy=np.round(g_easy[:2], 3).tolist(),
                       easy_rel=oracle_flip(byn["R3"], fix, q_right, (g_easy[0], g_easy[1], z)),
                       grid_ok=[k for k, v in grid.items() if v == "ok"], grid=grid)
    res["strokes"] = {}
    for nm, kind in STROKES:
        ts = M.FEED_TS if kind == "feed" else M.RECV_TS
        e = {}
        for s in ("left", "right"):
            _, dg = L.stroke_diag(s, byn[nm]["center"], byn[nm]["travel"], ts, fix, 25.0)
            dg["why"] = L.why(dg)
            e[s] = dg
        res["strokes"][nm + "_" + kind] = e
    rt, cl, _ = sim_rope(t)
    res["sim_rope"] = dict(t=rt, clear=cl, start_tip=None if rt is None else np.round(LM.rope_xy(rt)[0], 3).tolist())
    res["secs"] = round(time.time() - t0, 1)
    print("done", t, res["rope_t"], res["pick"], res["transfer"]["ok"], res["secs"]); sys.stdout.flush()
    return res


# ------------------------------------------------------------------ report
def steps_of(r):
    """(step, ok, count used for ranking, note) in feeding order."""
    st = r["strokes"]; P = lambda k, s: st[k][s]["poses"]
    tr = r["transfer"]
    return [
        ("底座在桌面", r["fits_rings"], None, ""),
        ("绳位+捡绳+drag1", r["sim_rope"]["t"] is not None, None, ""),
        ("ready", r["ready_ok"], None, ""),
        ("easy 迁移", tr["all_ok"], tr["ok"], "%d/%d" % (tr["ok"], tr["n"])),
        ("oracle 翻转", r["flip"]["easy_rel"] == "ok" or bool(r["flip"]["grid_ok"]), len(r["flip"]["grid_ok"]), ""),
        ("R3 喂(左)", P("R3_feed", "left") > 0, P("R3_feed", "left"), ""),
        ("R3 接", max(P("R3_recv", "left"), P("R3_recv", "right")) > 0, max(P("R3_recv", "left"), P("R3_recv", "right")), ""),
        ("R2 喂", max(P("R2_feed", "left"), P("R2_feed", "right")) > 0, max(P("R2_feed", "left"), P("R2_feed", "right")), ""),
        ("R2 接", max(P("R2_recv", "left"), P("R2_recv", "right")) > 0, max(P("R2_recv", "left"), P("R2_recv", "right")), ""),
        ("R1 喂", max(P("R1_feed", "left"), P("R1_feed", "right")) > 0, max(P("R1_feed", "left"), P("R1_feed", "right")), ""),
    ]


def rank_key(r):
    """all steps feasible, the most poses at the weakest stroke step, more R1 feed poses, then the other stroke counts
    ascending (leximin), then the number of feasible oracle flip points."""
    s = steps_of(r)
    all_ok = all(ok for _, ok, _, _ in s)
    counts = sorted(c for _, _, c, _ in s[5:])
    r1 = r["strokes"]["R1_feed"]["left"]["poses"] + r["strokes"]["R1_feed"]["right"]["poses"]
    return (all_ok, counts[0], r1, *counts[1:], len(r["flip"]["grid_ok"]))


def passes(r):
    return all(ok for _, ok, _, _ in steps_of(r))


def key_t(t):
    return (round(t[0], 3), round(t[1], 3))


def margin(t, by, numeric=False):
    """Passing grid distance (2 cm steps) from t along +x, -x, +y, -y before the first failing t; '>=k' at the grid end."""
    out, num = {}, {}
    for nm, (dx, dy) in (("+x", (0.02, 0)), ("-x", (-0.02, 0)), ("+y", (0, 0.02)), ("-y", (0, -0.02))):
        k = 0
        while True:
            r = by.get(key_t((t[0] + (k + 1) * dx, t[1] + (k + 1) * dy)))
            if r is None:
                out[nm] = ">=%d cm" % (2 * k); break
            if not passes(r):
                out[nm] = "%d cm" % (2 * k); break
            k += 1
        num[nm] = 2 * k
    return num if numeric else out


def choice_key(r, by):
    """rank_key's weakest stroke step and R1 feed poses first, then the smallest margin (cm), then the other stroke counts."""
    k = rank_key(r)
    return (k[1], k[2], min(margin(r["t"], by, numeric=True).values()), *k[3:])


def report():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import plot_layout as PL
    d = json.load(open(OUT + ".json"))
    res = sorted(d["results"], key=lambda r: (tuple(r["t"]) != T_NOW, -r["t"][0], r["t"][1]))
    by = {key_t(r["t"]): r for r in res}
    nbr = lambda t: [by.get(key_t((t[0] + dx, t[1] + dy))) for dx in (-0.02, 0, 0.02) for dy in (-0.02, 0, 0.02) if dx or dy]
    inner = [r for r in res if tuple(r["t"]) != T_NOW and passes(r) and all(n is not None and passes(n) for n in nbr(r["t"]))]
    ranked = sorted(inner, key=lambda r: choice_key(r, by), reverse=True)
    best = ranked[:2]
    lr = lambda r, k: "%d/%d" % (r["strokes"][k]["left"]["poses"], r["strokes"][k]["right"]["poses"])
    md = ["# yaw 15 + 镜像绳：环组平移 t 的选择（D12，离线 numpy）与仿真", "",
          "**D12（用户 2026-10-14 批准）**：yaw 15 环组整体平移（只改环组 t；yaw 15 与 D11 的镜像绳保持，绳 t 按每个 t 重选）。要求有余量：所选 t 在 ±2 cm 内的 8 个邻点也全部通过。D11 原 t=(0.532,−0.241) 为第一行对照。", "",
          "工具：`tools/layout_eval_shift.py`（复用 layout_eval_mirror.evaluate、layout_eval.stroke_diag、layout_eval.pick_detail）。",
          "网格：x ∈ {%s}，y ∈ {%s}（步长 2 cm），yaw 15。" % (",".join("%.3f" % x for x in XS), ",".join("%.3f" % y for y in YS)), "",
          "列说明：",
          "- 底座：三个支架底座全在桌面内（余量 1 cm）。",
          "- 绳 t：仿真用绳位 sim_rope = 有效绳位（桌内 1.4 cm、离底座/立柱间隙 ≥3 cm、左手捡起点 pick_detail(tip_is_start=True) 通过、drag1_check 通过）中起点绳头离 D11 绳位 (0.58,−0.09) 的绳头最近者。layout_eval_mirror 规则选的绳位（括号内）把起点绳头放在左桌边，oracle.pick 第一步（离绳头 0.15 m 捏住、绕竖直轴把绳头转向 +y）在那里没有 IK（drag1_check；仿真 X1a_ropeEdge 在 step 307 同样失败：line IK 62/86，无关节路线），所以不用。",
          "- easy 迁移：or3 左臂指令第 2700–3440 步（每 20 步，38 个样本：翻转位姿、180° 腕滚、落到喂入帧、推过 R1），从 easy R1（中心 (0.599,0.075,1.0819)，行进 −y）刚性变换到 R3（中心、行进方向 = −sign·n；帧 (d, z×d, d×h)）。逐样本 IK（余量 0.02），以上一样本为种子；“连续” = 由上一样本解出且关节跳变 <0.5 rad。最小间隙 = 左臂胶囊到环/立柱/桌面/右臂(ready) 的最小间隙，各 t 都是 45 mm：出现在最后一个样本（3440，推入）到 R3 本身，动作随 R3 一起刚性移动，所以与 t 无关；只作参考。",
          "- oracle 翻转复现（oracle 自己的动作）：在翻转点 (flip_x, flip_y, R3 高度−0.01) 绕 approach a1 做 18×10° 腕滚 → 落到 frame_az(a1, ±R3 行进) → 直线到 R3 喂入起点（环前 0.24 m）→ 推到 0.07 m；理想绳（弦=z_tcp），判据同 Runner.plan_line（IK 余量 0.02、关节跳变 ≤0.25 rad、每 3 点间隙 ≥4 mm、右臂在 ready）。列：默认翻转点 (0.60,0.40) / easy 翻转点按同一刚性变换搬到 R3 的点 / 网格 x 0.56–0.64 × y 0.30–0.42（30 点）通过数。",
          "- R3/R2/R1 喂、接：左/右手可行的不同夹爪朝向数（stroke 版，cone 25°，approach 每 30°，余量 ≥1 cm），与 yaw15_mirror_eval.md 同定义。过渡：捡绳末态→R3 喂入（layout_eval.transition）方案数 θ0/+36/−36（参考）。",
          "- 通过 = 底座 + 绳位 + ready + easy 迁移 38/38 + 至少一个 oracle 翻转点 + R3 喂(左) + 其余每个行程至少一只手有姿态。第一个不行的步骤按此顺序。", "",
          "## 通过图（✓ 通过，✗ 不通过；数字 = 最弱行程步骤的姿态数，括号 = R1 喂 左/右）", "",
          "| y \\ x | " + " | ".join("%.3f" % x for x in XS) + " |", "|---|" + "---|" * len(XS)]
    for y in YS:
        row = []
        for x in XS:
            r = by.get(key_t((x, y)))
            if r is None:
                row.append("-"); continue
            k = rank_key(r)
            row.append("%s %d (%s)" % ("✓" if passes(r) else "✗", k[1], lr(r, "R1_feed")))
        md.append("| %.3f | " % y + " | ".join(row) + " |")
    md += ["", "## 每个 t 一行", "",
           "| 环组 t | R3 中心 | 底座 | 绳 t 仿真用 / 间隙 cm (规则绳位) | easy 迁移 可解/连续 (首个失败步) | 迁移最小间隙 mm | 过渡 θ0/+36/−36 | oracle 翻转：默认点 / easy 相对点 / 网格通过 | R3喂 左/右 | R3接 | R2喂 | R2接 | R1喂 | 第一个不行的步骤 |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in res:
        tr, fl, sr = r["transfer"], r["flip"], r["sim_rope"]
        rope = ("(%.2f,%.2f) / %.1f" % (*sr["t"], 100 * sr["clear"]) if sr["t"] else "无") + " (%.2f,%.2f)" % tuple(r["rope_t"])
        bad = next((n for n, ok, _, _ in steps_of(r) if not ok), None)
        trn = "/".join(str(r["transition"][k]["n_plans"]) for k in ("0.0", "36.0", "-36.0")) if r["transition"] else "-"
        name = "(%.3f,%.3f)%s" % (r["t"][0], r["t"][1], " D11" if tuple(r["t"]) == T_NOW else "")
        flip = "%s / (%.3f,%.3f) %s / %d/30" % (fl["default"], *fl["easy_rel_xy"], fl["easy_rel"], len(fl["grid_ok"]))
        md.append("| %s | (%.3f,%.3f) | %s | %s | %d/%d · %d (%s) | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            name, *r["ring_centres"]["R3"][:2], "是" if r["fits_rings"] else "否", rope, tr["ok"], tr["n"], tr["cont"],
            tr["first_fail_step"] or "无", "-" if tr["min_clear"] is None else "%.0f" % (1000 * tr["min_clear"]), trn, flip,
            lr(r, "R3_feed"), lr(r, "R3_recv"), lr(r, "R2_feed"), lr(r, "R2_recv"), lr(r, "R1_feed"), bad or "无"))
    md += ["", "## 选择（D12）", "",
           "候选 = 通过且 8 个邻点（±2 cm）都通过的 t（%d 个）。排序键：最弱行程步骤（R3 喂取左手，其余取两手中较大者）的姿态数最多 → R1 喂入姿态（左+右）多 → 四个方向中最小的余量最大 → 其余行程步骤姿态数从小到大逐个比较 → oracle 翻转网格通过点多。y=−0.391 一行只用来量 y=−0.351 候选向 −y 的余量。" % len(inner), ""]
    for i, r in enumerate(ranked[:5]):
        k = rank_key(r)
        md.append("%d. t=(%.3f,%.3f)：最弱步骤姿态 %d，R1 喂 %s，其余行程姿态（升序）%s，迁移连续 %d/38，翻转网格通过 %d/30，余量 %s，仿真绳位 %s" % (
            i + 1, r["t"][0], r["t"][1], k[1], lr(r, "R1_feed"), list(k[3:-1]), r["transfer"]["cont"], k[-1],
            ", ".join("%s %s" % kv for kv in margin(r["t"], by).items()), tuple(r["sim_rope"]["t"])))
    if best:
        md += ["", "选定 t=(%.3f,%.3f)（备用 %s）。余量 = 从 t 沿该方向有几个 2 cm 网格步仍全部通过（到网格边为 ≥）。图：`yaw15_shift_best.png`（左：D11 原 t；右：选定 t，画仿真用绳位）。" % (
            *best[0]["t"], "t=(%.3f,%.3f)" % tuple(best[1]["t"]) if len(best) > 1 else "无"), ""]
    old = open(OUT + ".md").read() if os.path.exists(OUT + ".md") else ""
    sim = old[old.index("## 仿真"):] if "## 仿真" in old else ""          # the hand-written sim section is kept
    open(OUT + ".md", "w").write("\n".join(md) + "\n" + sim)
    # figure: D11 t vs the chosen t
    fig, axs = plt.subplots(1, 2, figsize=(26, 13.5), dpi=100)
    now = by[key_t(T_NOW)]
    for ax, r, tag in ((axs[0], now, "D11 原 t"), (axs[1], best[0], "D12 选定 t")):
        rings, _ = M.place(15.0, tuple(r["t"]))
        for g in rings:
            g["yaw"] = 15.0
        rt = tuple(r["sim_rope"]["t"] or r["rope_t"])
        rope = np.c_[LM.rope_xy(rt), M.ROPE[:, 2] + M.TABLE]
        tr = r["transfer"]
        PL.draw(ax, rings, rope, "%s：yaw 15，t=(%.3f,%.3f)，镜像绳 t=(%.2f,%.2f)\neasy 迁移 IK %d/38（连续 %d），R1 喂 左/右 %s" % (
            tag, r["t"][0], r["t"][1], rt[0], rt[1], tr["ok"], tr["cont"], lr(r, "R1_feed")),
            chain=[["L", "R"], ["L", "R"], ["R"]], feed_tip="start")
    fig.tight_layout()
    fig.savefig(W + "/evidence/medium_layout/yaw15_shift_best.png")
    print("\n".join(md))


if __name__ == "__main__":
    from multiprocessing import Pool
    ap = argparse.ArgumentParser()
    ap.add_argument("--nproc", type=int, default=6)
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--only", default="", help="JSON [x, y]: one t only (test)")
    a = ap.parse_args()
    if a.report:
        report()
        sys.exit(0)
    ts = [T_NOW] + [(x, y) for x in XS for y in YS]
    if a.only:
        ts = [tuple(json.loads(a.only))]
    prev = {key_t(r["t"]): r for r in json.load(open(OUT + ".json"))["results"]} if os.path.exists(OUT + ".json") else {}
    out = []
    with Pool(a.nproc) as pool:
        for r in pool.imap_unordered(evaluate, [dict(t=t, prev=prev.get(key_t(t))) for t in ts]):
            out.append(r)
            json.dump(dict(grid=dict(x=XS, y=YS), t_now=T_NOW, steps=STEPS, results=out), open(OUT + ("_only" if a.only else "") + ".json", "w"),
                      indent=1, default=str)
    print("ALL DONE")
