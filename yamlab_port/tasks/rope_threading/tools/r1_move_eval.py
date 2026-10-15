"""Offline eval of moving single rings (R1 / R2 / both) from the fixed medium layout (yaw 195, t (0.54, 0.12), rope start yaw 90 t (0.58,-0.05)),
reverse route (START tip first R3 -> R2 -> R1, right picks). numpy only; OMP_NUM_THREADS=1.
A move = {ring name: (dx, dy, rot_deg)}: the ring, its base and its post translate by (dx, dy) and turn rot_deg about the vertical axis through the ring centre
(ring height / tilt / normal elevation kept). Per move: layout_eval.evaluate_layout (every step) + R2 exit receive probe (static grasps) + R2->R1 pairs + geometry.
Usage: python r1_move_eval.py --out r1_move_eval.json [--procs 6]
"""
import argparse, json, os, sys, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layout_eval as L, medium_layout_search as M, plan_np as PN, yam_kin as K
from reach_map import seeds_for

YAW, T0, ROPE_T, ROPE_YAW = 195.0, (0.54, 0.12), (0.58, -0.05), 90.0
SPEC = {}
REC = {}
OFF = np.array([0.012, 0, 0])
_place0, _sd0 = M.place, L.stroke_diag


def rotz(a):
    a = np.radians(a); return np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])


def move_rings(rings, spec, yaw=YAW):
    out = []
    for r in rings:
        r = dict(r); dx, dy, rot = spec.get(r["name"], (0.0, 0.0, 0.0)); R = rotz(rot)
        c = r["center"].copy(); n = r["normal"].copy(); sc = r["stand_center"].copy(); bc = r["base_center"].copy()
        for k in ("stand_center", "base_center"):
            p = r[k].copy(); p[:2] = c[:2] + R @ (p[:2] - c[:2]) + (dx, dy); r[k] = p
        n[:2] = R @ n[:2]; c[:2] += (dx, dy)
        r["center"], r["normal"], r["yaw"] = c, n, yaw + rot
        out.append(r)
    return out


def place_patched(yaw, t):
    rings, rope = _place0(yaw, t)
    return move_rings(rings, SPEC, yaw), rope


def stroke_diag_rec(side, c, d, ts, fix, cone, keep=L.KEEP):
    sol, dg = _sd0(side, c, d, ts, fix, cone, keep)
    REC[(side, tuple(np.round(c, 3)), round(float(ts[0]), 3))] = sol
    return sol, dg


M.place, L.stroke_diag = place_patched, stroke_diag_rec
BOX = np.array([[0.025, 0.04], [-0.025, 0.04], [-0.025, -0.04], [0.025, -0.04]])


def base_poly(r, n=12):
    cs = r["base_center"][:2] + BOX @ rotz(r["yaw"]).T
    pts = [cs[i] + (cs[(i + 1) % 4] - cs[i]) * f for i in range(4) for f in np.linspace(0, 1, n, endpoint=False)]
    return cs, np.array(pts)


def inside(p, cs):
    s = [np.cross(cs[(i + 1) % 4] - cs[i], p - cs[i]) for i in range(4)]
    return all(x >= 0 for x in s) or all(x <= 0 for x in s)


def geometry(rings, rope, order):
    g = {}
    ok = True
    for r in rings:
        cs, _ = base_poly(r)
        ok &= bool(cs[:, 0].min() >= PN.TABLE_X[0] + 0.01 and cs[:, 0].max() <= PN.TABLE_X[1] - 0.01 and np.abs(cs[:, 1]).max() <= PN.TABLE_Y - 0.01)
        s = r["stand_center"]
        ok &= bool(PN.TABLE_X[0] + 0.01 <= s[0] <= PN.TABLE_X[1] - 0.01 and abs(s[1]) <= PN.TABLE_Y - 0.01)
    g["fits"] = bool(ok)
    gaps = {}
    for i in range(3):
        for j in range(i + 1, 3):
            a, b = rings[i], rings[j]
            csa, pa = base_poly(a); csb, pb = base_poly(b)
            d = 0.0 if (any(inside(p, csb) for p in pa) or any(inside(p, csa) for p in pb)) else float(np.min(np.linalg.norm(pa[:, None] - pb[None], axis=2)))
            gaps[a["name"] + b["name"]] = round(d, 4)
    g["base_gap"] = gaps
    g["base_gap_min"] = min(gaps.values())
    th = np.linspace(0, 2 * np.pi, 97)
    circ = {}
    for r in rings:
        u = np.cross([0, 0, 1.0], r["normal"]); u /= np.linalg.norm(u); v = np.cross(r["normal"], u)
        circ[r["name"]] = r["center"] + 0.075 * (np.cos(th)[:, None] * u + np.sin(th)[:, None] * v)
    cd, rg = {}, {}
    for a, b in (("R1", "R2"), ("R2", "R3"), ("R1", "R3")):
        ca = next(r for r in rings if r["name"] == a)["center"]; cb = next(r for r in rings if r["name"] == b)["center"]
        cd[a + b] = round(float(np.linalg.norm(ca - cb)), 3)
        rg[a + b] = round(float(np.min(np.linalg.norm(circ[a][:, None] - circ[b][None], axis=2))), 3)
    g["center_dist"], g["ring_gap"] = cd, rg
    # rope: straight lower bounds on the arc (m); reverse route R3 -> R2 -> R1, tip protrudes e = 0.10 m past R1
    byn = {r["name"]: r for r in rings}
    d21, d32 = cd["R1R2"], cd["R2R3"]
    g["arc_final_from_start_tip"] = dict(R1=0.10, R2=round(0.10 + d21, 3), R3=round(0.10 + d21 + d32, 3))
    g["start_to_R3"] = round(float(np.linalg.norm(rope[0] - byn["R3"]["center"])), 3)
    r2, r1, r3 = byn["R2"], byn["R1"], byn["R3"]
    t2 = -r2["sign"] * r2["normal"]; t1 = -r1["sign"] * r1["normal"]
    g["r2exit_vs_r1travel_deg"] = round(float(np.degrees(np.arccos(np.clip(t2 @ t1, -1, 1)))), 1)   # 90 = the exit is parallel to R1's face
    ch0 = r1["center"] - r2["center"]
    g["r2_to_r1plane_normal"] = round(float(ch0 @ t1), 3)           # distance from R2's centre to R1's plane along R1's travel direction
    g["r2_to_r1_inplane"] = round(float(np.linalg.norm(ch0 - (ch0 @ t1) * t1)), 3)
    ch = r1["center"] - r2["center"]; chn = ch / np.linalg.norm(ch)
    g["chord_R2R1_vs_R1_travel_deg"] = round(float(np.degrees(np.arccos(np.clip(chn @ t1, -1, 1)))), 1)
    g["chord_R2R1_vs_R2_exit_deg"] = round(float(np.degrees(np.arccos(np.clip(chn @ t2, -1, 1)))), 1)
    c32 = r2["center"] - r3["center"]; c32 /= np.linalg.norm(c32); t3 = -r3["sign"] * r3["normal"]
    g["r3_to_r2_normal"] = round(float((r2["center"] - r3["center"]) @ t3), 3)      # >0: R2 lies ahead of R3's face (exit side), as the rope must go on from R3
    g["r3_to_r2_entry"] = round(float((r2["center"] - r3["center"]) @ t2), 3)      # >0: R3 lies on R2's entry side
    g["chord_R3R2_vs_R3_travel_deg"] = round(float(np.degrees(np.arccos(np.clip(c32 @ t3, -1, 1)))), 1)
    # post of R1 vs the straight chord R2c -> R1c (distance in the horizontal plane)
    s = r1["stand_center"][:2]; a_, b_ = r2["center"][:2], r1["center"][:2]
    f = np.clip((s - a_) @ (b_ - a_) / ((b_ - a_) @ (b_ - a_)), 0, 1)
    g["r1_post_to_chord"] = round(float(np.linalg.norm(a_ + f * (b_ - a_) - s)), 3)
    return g


def r2_probe(rings, cone=20.0, dists=(0.05, 0.07, 0.10)):
    """R2 exit receive, static grasps behind R2's face (reverse route: exit direction = -sign*normal): for both arms
    count candidates (direction within `cone` of the exit, approach every 30 deg, rope across pads +-z, grip point `dists` behind the plane)
    that have no IK (multi-start, margin 0.03), or only IK with clearance < 1 cm (split: which ring / table), or are feasible."""
    r2 = next(r for r in rings if r["name"] == "R2"); d = -r2["sign"] * r2["normal"]
    fixall = L.fixture(rings); fixr = {r["name"]: L.fixture([r]) for r in rings}
    cand = []
    for dev, poses in M.stroke_frames(r2["center"], d, cone, list(dists)):
        for j, T in enumerate(poses):
            cand.append((dev, j, T))
    out = dict(n_cand=len(cand))
    for side in ("left", "right"):
        Tb = np.array([c[2] for c in cand]); Tb[:, :3, 3] -= K.BASES[side]
        seeds = np.array(seeds_for(Tb[0, :3, 3])); ns = len(seeds)
        q, ep, er = M.ik_batch(np.repeat(Tb, ns, 0), np.tile(seeds, (len(Tb), 1)), 200, 0.03)
        okm = (ep < 1e-4) & (er < 1e-3)
        cnt = dict(ik_unsolvable=0, feasible=0, collide={}); feas_poses = set(); first_bad = None
        for k in range(len(cand)):
            sols = []
            for jj in np.flatnonzero(okm[k * ns:(k + 1) * ns]):
                qq = q[k * ns + jj]
                if all(np.abs(qq - o).max() > 0.3 for o in sols):
                    sols.append(qq)
            if not sols:
                cnt["ik_unsolvable"] += 1; continue
            best, who = -9.0, None
            for qq in sols[:6]:
                c = PN.arm_clearance(side, qq, fixall, grip_open=False); m = min(c.values())
                if m < 0.01:
                    w = "table" if c["table"] < c["fixtures"] else min(fixr, key=lambda nm: PN.arm_clearance(side, qq, fixr[nm], grip_open=False)["fixtures"])
                else:
                    w = None
                if m > best:
                    best, who = m, w
            if best >= 0.01:
                cnt["feasible"] += 1; feas_poses.add((round(cand[k][0], 1),) + tuple(np.round(cand[k][2][:3, :3].ravel(), 1)))
            else:
                cnt["collide"][who] = cnt["collide"].get(who, 0) + 1
        cnt["poses"] = len(feas_poses)
        out[side] = cnt
    return out


def run(job):
    global SPEC
    SPEC = job["spec"]; REC.clear()
    t0 = time.time()
    res = L.evaluate_layout(dict(yaw=YAW, t=T0, rope_t=ROPE_T, rope_yaw=ROPE_YAW, reverse=True, thetas=[0.0]))
    rings, rope = place_patched(YAW, T0)
    rope = M.ROPE.copy(); rope = rope[:, :2] @ rotz(ROPE_YAW).T + np.asarray(ROPE_T)
    rope = np.c_[rope, np.full(len(rope), M.TABLE)]
    geo = geometry(rings, rope, ["R3", "R2", "R1"])
    out = dict(job=job, geo=geo, time=0.0)
    out["ready_ok"], out["pick_ok"] = res["ready_ok"], res["pick_ok"]
    tr = res["transition"]
    out["transition"] = {k: dict(ok=v["ok"], keep=v["keep"], frames=v["n_frames"], plans=v["n_plans"]) for k, v in tr.items()}
    for nm in ("R3_feed", "R3_recv", "R2_feed", "R2_recv", "R1_feed"):
        out[nm] = {s[0]: res[nm][s]["poses"] for s in ("left", "right")}
        out[nm + "_clear"] = {s[0]: res[nm][s]["clear"] for s in ("left", "right")}
    out["R2_recv_why"] = {s[0]: res["R2_recv"][s]["why"] for s in ("left", "right")}
    out["R1_feed_why"] = {s[0]: res["R1_feed"][s]["why"] for s in ("left", "right")}
    out["R3_hand"] = {k: v["both"] for k, v in res["R3_hand"].items()}
    out["R2_hand"] = {k: v["both"] for k, v in res["R2_hand"].items()}
    out["chains"], out["chain_fail"] = res["chains"], res["chain_fail"]
    out["first_fail_layout_eval"] = res["first_fail"]
    # R2 exit receive: static probe + the stroke version with cone 20
    out["R2_probe"] = r2_probe(rings)
    fix = L.fixture(rings)
    r2 = next(r for r in rings if r["name"] == "R2"); d = -r2["sign"] * r2["normal"]
    sc = {}
    for s in ("left", "right"):
        _, dg = _sd0(s, r2["center"], d, M.RECV_TS, fix, 20.0)
        sc[s[0]] = dict(poses=dg["poses"], clear=dg["clear"], ik0=dg["ik0"], path=dg["path"], cand=dg["cand"])
    out["R2_recv_cone20"] = sc
    # R2 receiver -> R1 feeder hand-over pairs (receiver end pose at R2, taker start pose at R1 feed), distinct arms
    r1 = next(r for r in rings if r["name"] == "R1")
    k2 = lambda s: (s, tuple(np.round(r2["center"], 3)), round(float(M.RECV_TS[0]), 3))
    k1 = lambda s: (s, tuple(np.round(r1["center"], 3)), round(float(M.FEED_TS[0]), 3))
    hp = {}
    for fa, ra in (("left", "right"), ("right", "left")):
        a, b = REC.get(k2(fa), []), REC.get(k1(ra), [])
        hp[fa[0].upper() + ra[0].upper()] = int(L.hand_pairs(a, b, fa, ra, fix)[2]) if a and b else 0
    out["R2recv_R1feed_pairs"] = hp
    out["time"] = round(time.time() - t0, 1)
    return out


def pose_ok(o):
    """Every step of the reverse route has > 0 feasible poses (R2 exit receive = the static probe, either arm)."""
    tr = o["transition"].get("0.0", {})
    steps = dict(ready=o["ready_ok"], pick=o["pick_ok"], transition=bool(tr.get("ok")),
                 R3_feed=sum(o["R3_feed"].values()) > 0, R3_recv=sum(o["R3_recv"].values()) > 0, R3_hand=sum(o["R3_hand"].values()) > 0,
                 R2_feed=sum(o["R2_feed"].values()) > 0, R2_recv_probe=sum(o["R2_probe"][s]["poses"] for s in ("left", "right")) > 0,
                 R2_hand=sum(o["R2_hand"].values()) > 0, R1_feed=sum(o["R1_feed"].values()) > 0, chain=bool(o["chains"]),
                 geometry=o["geo"]["fits"] and o["geo"]["base_gap_min"] >= 0.02)
    return steps


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="r1_move_eval.json")
    ap.add_argument("--procs", type=int, default=6)
    ap.add_argument("--jobs", default=None, help="json file with a list of jobs [{group,spec}]")
    ap.add_argument("--test", action="store_true")
    a = ap.parse_args()
    if a.test:
        r = run(dict(group="test", spec={}))
        print(json.dumps(r, indent=1, default=str)); print(pose_ok(r)); sys.exit()
    from multiprocessing import Pool
    jobs = json.load(open(a.jobs))
    res = []
    with Pool(a.procs) as P:
        for o in P.imap_unordered(run, jobs):
            res.append(o); print(o["job"]["group"], o["job"]["spec"], "time", o["time"], flush=True)
            json.dump(res, open(a.out, "w"), default=str)
