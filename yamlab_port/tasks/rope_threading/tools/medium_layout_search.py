"""Medium re-layout search (numpy only, multiprocessing; run on vast with OMP_NUM_THREADS=1).

world_xy = Rz(yaw) old_xy/1000 + (tx, ty), world_z = 0.75 + old_z/1000.
1. Fit: rope start (radius 4 mm), stand bases (50 x 80 boxes) and stand posts must lie on the tabletop collider
   (x 0.3025..0.8975, y -0.65..0.65) with `--margin`; rings may overhang (they are in the air).
2. Reach: for every ring k (travel direction d_k = sign_k n_k, the end tip is fed), a feed stroke (grip point
   0.25 -> 0.07 m before the plane) and a receive stroke (0.07 -> 0.20 m past the plane), each tested for both arms:
   rope along d_k (both rope-axis signs), approach perpendicular to d_k (horizontal / pitched 30, 60 deg down / down),
   grip point 12 mm inside the pads, IK-continuous along the stroke, capsule clearance >= 1 cm to rings/stands/table.
Prints, per layout, which arm can do each stroke. Usage: python medium_layout_search.py [--yaws ...]
"""
import argparse, itertools, json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import plan_np as PN
import yam_kin as K

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


def approaches(d):
    h = np.cross([0, 0, 1.0], d)
    if np.linalg.norm(h) < 1e-6:
        return []
    h /= np.linalg.norm(h)
    out = []
    for s in (1, -1):
        for p in (0, 30, 60):
            pr = np.radians(p)
            out.append(np.cos(pr) * s * h + np.array([0, 0, -np.sin(pr)]))
    hd = d - np.array([0, 0, d[2]])
    if np.linalg.norm(hd) > 1e-6:
        out.append(np.array([0, 0, -1.0]))
    return out


def stroke_ok(side, c, d, ts, fix):
    for a in approaches(d):
        a = a - d * (a @ d); a /= np.linalg.norm(a)
        for zs in (1, -1):
            q, ok = None, True
            for t in ts:
                g = c + t * d
                T = PN.grip_T(a, zs * d, g, np.array([0.012, 0, 0]))
                if q is None:
                    q = PN.solve(side, T, margin=0.03)
                    if q is None:
                        ok = False; break
                else:
                    qn, o, ep, er = K.ik(K.world_to_base(T, side), q, iters=200, margin=0.02)
                    if not (o or (ep < 1.5e-3 and er < 3e-2)) or np.abs(qn - q).max() > 0.6:
                        ok = False; break
                    q = qn
                if min(PN.arm_clearance(side, q, fix, grip_open=False).values()) < 0.01:
                    ok = False; break
            if ok:
                return True
    return False


def evaluate(args):
    yaw, tx, ty = args
    rings, _ = place(yaw, (tx, ty))
    fix = PN.fixture_capsules([dict(r, center=r["center"].tolist(), normal=r["normal"].tolist(),
                                    stand_center=r["stand_center"].tolist()) for r in rings])
    res = {}
    for r in rings:
        d = r["sign"] * r["normal"]
        for kind, ts in (("feed", np.linspace(-0.25, -0.07, 5)), ("recv", np.linspace(0.07, 0.20, 4))):
            res[f"{r['name']}{kind}"] = "".join(s[0].upper() if stroke_ok(s, r["center"], d, ts, fix) else "." for s in ("left", "right"))
    return args, res


if __name__ == "__main__":
    from multiprocessing import Pool
    ap = argparse.ArgumentParser()
    ap.add_argument("--margin", type=float, default=0.01)
    ap.add_argument("--yaws", type=float, nargs="*", default=list(range(0, 360, 15)))
    ap.add_argument("--nproc", type=int, default=12)
    ap.add_argument("--rings_only", action="store_true", help="fit only the stand bases (the rope start is placed later)")
    ap.add_argument("--step", type=int, default=2, help="evaluate every step-th tx/ty candidate")
    a = ap.parse_args()
    RINGS_ONLY = a.rings_only
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
            score = sum(1 for v in res.values() if v != "..")
            out.append(dict(yaw=args_[0], tx=args_[1], ty=args_[2], score=score, **res))
            print(f"yaw {args_[0]:5.1f} t ({args_[1]:.2f},{args_[2]:+.2f}) strokes {score}/6 ", res); sys.stdout.flush()
    json.dump(out, open("medium_layout_search.json", "w"), indent=1)
    print("DONE")
