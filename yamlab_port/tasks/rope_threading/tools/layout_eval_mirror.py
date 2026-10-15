"""yaw 15 ring group + the rope start MIRRORED about the U's symmetry axis (offline, numpy).

Mirror: the rope shape (old table frame) is reflected about the U's axis x_old = XC (the mid-point of its two end x), the
point order (material order) is kept; then the usual rigid placement world_xy = Rz(90) old' + t. Start tip on the LEFT (+y),
end tip on the right, the U still bulges away from the robot (+x). The rope t is re-chosen per ring placement: the whole rope on
the table (1.4 cm margin), clearance to every stand base box and stand post >= 2 cm, maximal (bases inside the U preferred).
Route: reverse (start tip first, R3 -> R2 -> R1), the LEFT arm picks the start tip at the left table edge and feeds R3.
Stroke / hand-over numbers do not depend on the rope or on who picks: reused from yaw15_eval.json (same ring placements);
pick (left, start tip: layout_eval.pick_detail(tip_is_start=True)) and the pick-end -> R3 feed transition (left) are new.
Usage: python layout_eval_mirror.py [--nproc 6]   -> evidence/medium_layout/yaw15_mirror_eval.json
"""
import argparse, json, os, sys, time
import numpy as np
from matplotlib.path import Path as MPath
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layout_eval as L
import medium_layout_search as M
import plan_np as PN
import yam_kin as K

W = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
XC = 0.5 * (M.ROPE[0, 0] + M.ROPE[-1, 0])


def mirrored_old():
    p = M.ROPE[:, :2].copy(); p[:, 0] = 2 * XC - p[:, 0]
    return p


def rope_xy(t, mirror=True):
    return (mirrored_old() if mirror else M.ROPE[:, :2]) @ M.rot(90.0)[:2, :2].T + np.asarray(t)


def clearance(xy, rings, yaw):
    """min rope-surface distance to the stand base boxes (50 x 80 mm) and stand posts (r 5 mm)."""
    Rz = M.rot(yaw)[:2, :2]
    out = 9.0
    for r in rings:
        loc = (xy - r["base_center"][:2]) @ Rz
        out = min(out, float(np.linalg.norm(loc - np.clip(loc, (-0.025, -0.04), (0.025, 0.04)), axis=1).min()) - 0.004)
        out = min(out, float(np.linalg.norm(xy - r["stand_center"][:2], axis=1).min()) - 0.009)
    return out


def inside_U(xy, pts):
    return bool(MPath(np.vstack([xy, xy[:1]])).contains_points(np.asarray(pts)).all())


def place_rope(rings, yaw, k=3, margin=0.014, min_clear=0.02):
    """Candidates (tx, ty) sorted: bases-inside-U first, then clearance. -> list of dict(t, clear, inside)."""
    cands = []
    for tx in np.arange(0.36, 0.60, 0.01):
        for ty in np.arange(-0.26, 0.32, 0.01):
            xy = rope_xy((tx, ty))
            if xy[:, 0].min() < PN.TABLE_X[0] + margin or xy[:, 0].max() > PN.TABLE_X[1] - margin or np.abs(xy[:, 1]).max() > PN.TABLE_Y - margin:
                continue
            c = clearance(xy, rings, yaw)
            if c >= min_clear:
                cands.append(dict(t=(round(float(tx), 2), round(float(ty), 2)), clear=round(c, 3),
                                  inside=inside_U(xy, [r["base_center"][:2] for r in rings])))
    cands.sort(key=lambda c: (not c["inside"], -c["clear"]))
    return cands


def evaluate(a):
    t0 = time.time()
    yaw, t = a["yaw"], tuple(a["t"])
    M.RINGS_ONLY = True
    rings, _ = M.place(yaw, t)
    fix = L.fixture(rings)
    res = dict(yaw=yaw, t=t, fits_rings=M.fits(yaw, t, 0.01))
    cands = place_rope(rings, yaw)
    res["rope_candidates_n"] = len(cands); res["rope_candidates_top"] = cands[:5]
    qr = {}
    for side in ("left", "right"):
        sg = 1 if side == "left" else -1
        qs = [M.goto_q(side, PN.frame((0.7071, 0, -0.7071), (0, 1, 0), (x, sg * y, z)), M.HOME, fix, ("right" if side == "left" else "left", M.HOME, True))
              for x, y, z in M.READY]
        res["ready_" + side] = sum(q is not None for q in qs)
        qr[side] = next((q for q in qs if q is not None), None)
    res["ready_ok"] = all(v is not None for v in qr.values())
    res["pick_tries"] = []
    ins = [c for c in cands if c["inside"]][:3]
    far = sorted(cands, key=lambda c: -c["clear"])
    far = [c for c in far if all(abs(c["t"][0] - o["t"][0]) + abs(c["t"][1] - o["t"][1]) >= 0.03 for o in ins)][:3]
    best = None
    for c in ins + far:
        pk = L.pick_detail(rope_xy(c["t"]), fix, "left", qr["left"], qr["right"], tip_is_start=True)
        res["pick_tries"].append(dict(t=c["t"], clear=c["clear"], inside=c["inside"], **pk))
    ok = [x for x in res["pick_tries"] if x["ok"]]
    pick_best = max(ok or res["pick_tries"], key=lambda x: (x["ok"], x["inside"], x["n"], x["clear"])) if res["pick_tries"] else None
    best = pick_best and dict(t=pick_best["t"])
    res["rope_t"] = best["t"] if best else None
    pk = pick_best
    res["pick_detail"] = pk; res["pick"] = ("%d/4" % pk["n"]) if pk else None; res["pick_ok"] = bool(pk and pk["ok"])
    # transition: the left holds the rope at the pick end state (flip pose), onto R3's left feed frames
    rr = [dict(r, travel=-r["sign"] * r["normal"]) for r in rings[::-1]]
    res["transition"] = {str(th): L.transition("left", rr[0], fix, qr["left"], qr["right"], th) for th in (0.0, 36.0, -36.0)} if res["ready_ok"] else {}
    res["secs"] = round(time.time() - t0, 1)
    print("done", yaw, t, res["rope_t"], res["pick"], res["secs"]); sys.stdout.flush()
    return res


if __name__ == "__main__":
    from multiprocessing import Pool
    ap = argparse.ArgumentParser()
    ap.add_argument("--nproc", type=int, default=6)
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    d15 = json.load(open(W + "/evidence/medium_layout/yaw15_eval.json"))
    ts = [tuple(r["t"]) for r in d15["results"] if r["yaw"] == 15.0 and not r.get("skipped")]
    if a.only:
        ts = [tuple(json.loads(a.only))]
    out = []
    with Pool(a.nproc) as pool:
        for r in pool.imap_unordered(evaluate, [dict(yaw=15.0, t=t) for t in ts]):
            out.append(r)
            json.dump(dict(xc_old=XC, results=out), open(W + "/evidence/medium_layout/yaw15_mirror_eval.json", "w"), indent=1, default=str)
    print("ALL DONE")
