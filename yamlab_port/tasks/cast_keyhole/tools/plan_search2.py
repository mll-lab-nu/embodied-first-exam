"""Grid search of the design-v4 work pose for IK feasibility of both arms (run on vast, multiprocessing).

Parameters: psi (assembly yaw about the bar's vertical axis applied in the setup), bar XY, gamma (part of the
90 deg key turn done by yawing the gold, the silver yaws gamma-90), split (part of the channel translation done
by the gold).  Seeds (IK branches at the pregrasp) are computed once per arm.

usage: python plan_search2.py <tier> <states.npz> <settled_step> > out.jsonl
"""
import itertools
import json
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

sys.path.insert(0, str(Path(__file__).resolve().parent))
import keyhole_geometry as kg
import plan2 as pl
import yam_kin as yk
from layout import Scene, T_from, TABLE_Z

tier, path, k = sys.argv[1], sys.argv[2], int(sys.argv[3])
import os as _os
BASE = dict(gold_y=-0.004, gold_x_tcp=0.061, silver_y=float(_os.environ.get("SILVER_Y", -0.0024)), silver_x_tcp=-0.051, h_bar=0.0405, lift=0.02,
            chan_extra=0.04, pre_back=0.06, gold_jaw=float(_os.environ.get("GOLD_JAW", 1.0)), silver_jaw=-1.0)
sc = Scene(tier)
REL = pl.Relative(sc.record, tier)
z = np.load(path)
Tp = {}
for n in kg.NAMES:
    st = z[f"keyhole_{n}"][k]
    Tp[n] = T_from(Rotation.from_quat(st[[4, 5, 6, 3]]), st[:3]) @ sc.T_part_plate[n]
import os
GOLD_GRASP = os.environ.get("GOLD_GRASP", "band")


def gold_G(a=None, b=None, jaw=BASE["gold_jaw"]):
    if GOLD_GRASP == "fork":
        return pl.gold_fork_grasp(0.056 if a is None else a, -0.068 if b is None else b, jaw)
    return pl.gold_grasp(BASE["gold_y"] if b is None else b, BASE["gold_x_tcp"], jaw)


G = {"gold": gold_G(),
     "silver": pl.silver_edge_grasp(BASE["silver_y"], BASE["silver_x_tcp"], BASE["silver_jaw"])}
SIDE = {"gold": "left", "silver": "right"}
f_turn, _ = REL.sampler(REL.stage("turn"))
f_ch, _ = REL.sampler(REL.stage("channel"), extra=np.array([0.0, -BASE["chan_extra"], 0.0]))


def tr(T, d):
    o = T.copy(); o[:3, 3] += d; return o


def frames(psi, bx, by, gamma, split, gold_y=None):
    """Oracle-faithful nominal object path: stand (silver pivots about its lower edge to the nominal relative
    pose, gold keeps its orientation), move (lift, then rigid motion to the work pose), turn, channel."""
    out = [("lift", Tp["gold"], Tp["silver"])]
    Tg1, Ts1 = Tp["gold"], Tp["silver"]
    R_piv = (Tg1[:3, :3] @ REL.r0.as_matrix()) @ Ts1[:3, :3].T
    edge = [Ts1 @ np.r_[0.039, yy, zz, 1.0] for yy in (-0.06, 0.06) for zz in (-0.0045, 0.0045)]
    pivot = min(edge, key=lambda q: q[2])[:3]
    rv = Rotation.from_matrix(R_piv).as_rotvec()
    align1 = REL.align(Tg1, Ts1)
    for u in np.linspace(0, 1, 9)[1:]:
        Ts = pl.rot_about(Ts1, Rotation.from_rotvec(rv * u).as_matrix(), pivot)
        out.append(("stand", Ts @ np.linalg.inv(align1(u)), Ts))
    Tg2, Ts2 = out[-1][1], out[-1][2]
    Trel2 = np.linalg.inv(Tg2) @ Ts2
    R_lv = Rotation.align_vectors([[0, 0, -1.0]], [Tg2[:3, 2]])[0].as_matrix()
    R_lv = Rotation.from_euler("z", psi, degrees=True).as_matrix() @ R_lv
    bar2 = Tg2[:3, :3] @ REL.c0 + Tg2[:3, 3]
    Tgg = pl.rot_about(Tg2, R_lv, bar2)
    Tgg[:3, 3] += np.r_[bx, by, TABLE_Z + BASE["h_bar"]] - bar2
    Tup = tr(Tg2, [0, 0, BASE["lift"]])
    for u in np.linspace(0, 1, 3)[1:]:
        Tg = pl.interp_T(Tg2, Tup, u); out.append(("setup", Tg, Tg @ Trel2))
    for u in np.linspace(0, 1, 9)[1:]:
        Tg = pl.interp_T(Tup, Tgg, u); out.append(("setup", Tg, Tg @ Trel2))
    bw = np.r_[bx, by, 0]
    for u in np.linspace(0, 1, 10)[1:]:
        Tg = pl.rot_about(Tgg, Rotation.from_euler("z", gamma * u, degrees=True).as_matrix(), bw)
        out.append(("turn", Tg, Tg @ f_turn(u)))
    Tg3 = out[-1][1]
    rel0 = f_ch(0.0)
    for u in np.linspace(0, 1, 13)[1:]:
        rel = f_ch(u)
        d = Tg3[:3, :3] @ (rel[:3, 3] - rel0[:3, 3])
        Tg = tr(Tg3, -split * d)
        out.append(("channel", Tg, Tg @ rel))
    return out


def seeds(name, n=80):
    rng = np.random.default_rng(1)
    T0 = (Tp[name] @ G[name])
    pre = T0.copy(); pre[:3, 3] -= BASE["pre_back"] * T0[:3, 0]
    sols = []
    for _ in range(n):
        q0 = yk.LOWER + rng.random(6) * (yk.UPPER - yk.LOWER)
        q, ok, _, _ = yk.ik(yk.world_to_base(pre, SIDE[name]), q0, iters=150)
        if ok and all(np.abs(q - s).max() > 0.2 for s in sols):
            sols.append(q)
    return sols


SEEDS = {n: seeds(n) for n in kg.NAMES}


def track(name, fr, Gn=None, seeds_=None):
    idx = 1 if name == "gold" else 2
    Gn = G[name] if Gn is None else Gn
    best = None
    for q in (SEEDS[name] if seeds_ is None else seeds_):
        qc, fails, worst = q, 0, np.inf
        per = {}
        for ph, *T in fr:
            qn, ok, ep, er = yk.ik(yk.world_to_base(T[idx - 1] @ Gn, SIDE[name]), qc, iters=60, margin=0.0)
            m = float(np.min(np.minimum(qn - yk.LOWER, yk.UPPER - qn)))
            fails += (not ok); worst = min(worst, m)
            per[ph] = per.get(ph, 0) + (not ok)
            qc = qn
        sc_ = (-fails, worst)
        if best is None or sc_ > best[0]:
            best = (sc_, per)
    return best


def seeds_for(name, Gn, n=40):
    rng = np.random.default_rng(1)
    T0 = Tp[name] @ Gn
    pre = T0.copy(); pre[:3, 3] -= BASE["pre_back"] * T0[:3, 0]
    sols = []
    for _ in range(n):
        q0 = yk.LOWER + rng.random(6) * (yk.UPPER - yk.LOWER)
        q, ok, _, _ = yk.ik(yk.world_to_base(pre, SIDE[name]), q0, iters=150)
        if ok and all(np.abs(q - s_).max() > 0.2 for s_ in sols):
            sols.append(q)
    return sols


def seeds_at(name, T, n=40):
    rng = np.random.default_rng(2)
    sols = []
    for _ in range(n):
        q0 = yk.LOWER + rng.random(6) * (yk.UPPER - yk.LOWER)
        q, ok, _, _ = yk.ik(yk.world_to_base(T, SIDE[name]), q0, iters=150)
        if ok and all(np.abs(q - s_).max() > 0.2 for s_ in sols):
            sols.append(q)
    return sols


def run_regrasp(args):
    """Gold grasp A (args[5]) for lift/stand/setup, grasp B (args[6]) after a regrasp for turn/channel."""
    fr = frames(*args[:5])
    out = {"args": args}
    GA = gold_G(None, args[5]); GB = gold_G(None, args[6])
    frA = [f for f in fr if f[0] not in ("turn", "channel")]
    frB = [f for f in fr if f[0] in ("turn", "channel")]
    a = track("gold", frA, GA, seeds_for("gold", GA))
    b = track("gold", frB, GB, seeds_at("gold", frB[0][1] @ GB)) if frB else None
    out["gold"] = None if (a is None or b is None) else dict(
        fails=-a[0][0] - b[0][0], margin=round(min(a[0][1], b[0][1]), 3), per={**a[1], **b[1]})
    s_ = track("silver", fr)
    out["silver"] = None if s_ is None else dict(fails=-s_[0][0], margin=round(s_[0][1], 3), per=s_[1])
    return out


def run(args):
    if os.environ.get("REGRASP"):
        return run_regrasp(args)
    fr = frames(*args[:5])
    out = {"args": args}
    for n in kg.NAMES:
        if n == "gold" and len(args) > 5:
            Gn = gold_G(args[6] if len(args) > 6 else None, args[5]) if GOLD_GRASP == "fork" else gold_G(None, args[5])
            b = track(n, fr, Gn, seeds_for(n, Gn))
        else:
            b = track(n, fr)
        out[n] = None if b is None else dict(fails=-b[0][0], margin=round(b[0][1], 3), per=b[1])
    return out


if __name__ == "__main__":
    print(json.dumps({"seeds": {n: len(v) for n, v in SEEDS.items()}}), flush=True)
    rng = np.random.default_rng(int(sys.argv[4]) if len(sys.argv) > 4 else 0)
    if os.environ.get("REGRASP"):
        bxr = [float(v) for v in os.environ.get("BX", "0.44,0.64").split(",")]
        byr = [float(v) for v in os.environ.get("BY", "-0.28,-0.04").split(",")]
        grid = [(float(rng.uniform(-60, 60)), float(rng.uniform(*bxr)), float(rng.uniform(*byr)),
                 float(rng.uniform(0, 90)), float(rng.uniform(0, 1)), float(rng.uniform(-0.03, 0.015)),
                 float(rng.uniform(-0.100, -0.093))) for _ in range(int(os.environ.get("NSAMP", 300)))]
    elif GOLD_GRASP == "fork":   # args[5] = tip_y, args[6] = x_tcp; jaw sign from env
        bxr = [float(v) for v in os.environ.get("BX", "0.44,0.62").split(",")]
        byr = [float(v) for v in os.environ.get("BY", "-0.26,0.0").split(",")]
        psr = [float(v) for v in os.environ.get("PSI", "-90,60").split(",")]
        grid = [(float(rng.uniform(*psr)), float(rng.uniform(*bxr)), float(rng.uniform(*byr)),
                 float(rng.uniform(0, 90)), float(rng.uniform(0, 1)), float(rng.uniform(-0.075, -0.068)),
                 float(rng.uniform(0.052, 0.060))) for _ in range(int(os.environ.get("NSAMP", 300)))]
    else:
        gyr = [float(v) for v in os.environ.get("GOLD_Y", "-0.08,0.015").split(",")]
        grid = [(float(rng.uniform(-60, 40)), float(rng.uniform(0.46, 0.62)), float(rng.uniform(-0.26, -0.06)),
                 float(rng.uniform(0, 90)), float(rng.uniform(0, 1)), float(rng.uniform(*gyr)))
                for _ in range(int(os.environ.get("NSAMP", 300)))]
    with Pool(8) as pool:
        for o in pool.imap_unordered(run, grid, chunksize=2):
            print(json.dumps(o), flush=True)
