"""Layout choice by YAM reach at the threading strokes (numpy only, single-threaded workers).

Layout: yaw +90 deg (old +Y -> world -X), old origin -> (tx, ty). Rings (easy): R1 centre old (75, -19, 331.9),
normal old +x -> world +y; R2 centre old (-25, 120, 310.9), normal old +y -> world -x. The END tip (last CSV row)
is fed: through R1 travelling -y (R1-), then through R2 travelling -x (R2+).
Strokes (rope held across the pads, i.e. along z_tcp = +-feed; approach a perpendicular to the feed):
  F1 left  feeds R1:   TCP = R1c + (0, +s, dz),  s 0.25 -> 0.12
  G1 right receives:   TCP = R1c + (0, -s, dz),  s 0.06 -> 0.25 (pull)
  F2 right feeds R2:   TCP = R2c + (+s, 0, dz),  s 0.25 -> 0.12
  G2 left  receives:   TCP = R2c + (-s, 0, dz),  s 0.06 -> 0.28 (pull)
For each stroke and approach option the whole stroke must be IK-reachable (joint margin 0.05 rad), solved
continuously (each sample seeded by the previous one).
Usage: python keypose_study.py
"""
import itertools, json, os, sys
import numpy as np
import yam_kin as K
from reach_map import frame, seeds_for

TABLE = 0.75
R1_OLD, R2_OLD = np.array([75.0, -19.0, 331.9]), np.array([-25.0, 120.0, 310.9])


def to_world(p_old, tx, ty):
    p = p_old / 1000.0
    return np.array([-p[1] + tx, p[0] + ty, TABLE + p[2]])


def approaches(feed):
    f = np.asarray(feed, float)
    out = {}
    side = np.cross([0, 0, 1.0], f); side /= np.linalg.norm(side)  # horizontal perpendicular to the feed
    for name, a in (("fwd+x", [1, 0, 0]), ("back-x", [-1, 0, 0]), ("side+y", [0, 1, 0]), ("side-y", [0, -1, 0]),
                    ("down", [0, 0, -1])):
        a = np.asarray(a, float)
        if abs(a @ f) > 1e-6:
            continue
        out[name] = a
    for name, h in (("fwd+x", [1, 0, 0]), ("side+y", [0, 1, 0]), ("side-y", [0, -1, 0])):
        h = np.asarray(h, float)
        if abs(h @ f) > 1e-6:
            continue
        for p in (30, 45, 60):
            pr = np.radians(p)
            out[f"{name}_p{p}"] = np.cos(pr) * h + np.array([0, 0, -np.sin(pr)])
    return out


def stroke_ok(side, centre, axis, s_values, feed, a, dz):
    jaw = np.cross(a, feed)
    best = None
    for jsign in (1, -1):
        q_prev, ok_all, qs = None, True, []
        for k, s in enumerate(s_values):
            T = frame(a, jsign * jaw); T[:3, 3] = centre + s * axis + np.array([0, 0, dz])
            Tb = K.world_to_base(T, side)
            sol = None
            seeds = ([q_prev] if q_prev is not None else []) + (seeds_for(Tb[:3, 3]) if q_prev is None else [])
            for sd in seeds:
                q, ok, ep, er = K.ik(Tb, sd, iters=200, margin=0.05)
                if ok and (q_prev is None or np.abs(q - q_prev).max() < 0.6):
                    sol = q; break
            if sol is None:
                ok_all = False; break
            qs.append(sol); q_prev = sol
        if ok_all:
            return True, [np.round(q, 3).tolist() for q in qs]
    return False, None


def study(args):
    tx, ty, dz = args
    r1, r2 = to_world(R1_OLD, tx, ty), to_world(R2_OLD, tx, ty)
    strokes = {
        "F1_left_feed_R1": ("left", r1, np.array([0, 1.0, 0]), np.linspace(0.25, 0.12, 6), np.array([0, -1.0, 0])),
        "G1_right_recv_R1": ("right", r1, np.array([0, -1.0, 0]), np.linspace(0.06, 0.25, 6), np.array([0, -1.0, 0])),
        "F2_right_feed_R2": ("right", r2, np.array([1.0, 0, 0]), np.linspace(0.25, 0.12, 6), np.array([-1.0, 0, 0])),
        "G2_left_recv_R2": ("left", r2, np.array([-1.0, 0, 0]), np.linspace(0.06, 0.28, 6), np.array([-1.0, 0, 0])),
    }
    out = {}
    for name, (side, c, ax, sv, feed) in strokes.items():
        out[name] = [an for an, a in approaches(feed).items() if stroke_ok(side, c, ax, sv, feed, a, dz)[0]]
    return (tx, ty, dz), out


if __name__ == "__main__":
    from multiprocessing import Pool
    jobs = list(itertools.product((0.50, 0.54, 0.58, 0.62), (-0.08, -0.04, 0.0, 0.04), (-0.03, 0.0)))
    with Pool(int(os.environ.get("NPROC", "12"))) as pool:
        res = pool.map(study, jobs, chunksize=1)
    rows = []
    for (tx, ty, dz), o in res:
        score = sum(1 for v in o.values() if v)
        rows.append(dict(tx=tx, ty=ty, dz=dz, n_strokes_ok=score, **o))
        print(f"tx={tx:.2f} ty={ty:+.2f} dz={dz:+.2f} strokes_ok={score}  " + "  ".join(f"{k.split('_')[0]}:{','.join(v) or '-'}" for k, v in o.items()))
        sys.stdout.flush()
    json.dump(rows, open("keypose_study.json", "w"), indent=1)
