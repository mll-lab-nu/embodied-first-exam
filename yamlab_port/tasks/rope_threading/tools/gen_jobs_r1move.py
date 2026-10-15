"""Job lists for r1_move_eval.py: python gen_jobs_r1move.py A|B > jobs.json  (geometry-invalid moves are listed with invalid=true and not evaluated)."""
import json, sys, itertools
import numpy as np
import r1_move_eval as R
cm = 0.01
def jobs_A():
    pos = [(x, y) for x in (0, 3, 6, 9, 12) for y in (0, 3, 6, 9, 12)] + [(-3, 0), (-6, 0), (0, -3), (0, -6)]
    return [dict(group="A", spec={"R1": (x * cm, y * cm, rot)}) for x, y in pos for rot in (-15, 0, 15)]
def jobs_B():
    v = (-10, -6, -3, 0, 3, 6, 10)
    return [dict(group="B", spec={"R2": (x * cm, y * cm, rot)}) for x in v for y in v for rot in (-20, 0, 20)]
def check(j):
    rings, rope = R.place_patched(195.0, (0.54, 0.12)) if False else (None, None)
    R.SPEC = j["spec"]
    rings, _ = R.place_patched(195.0, (0.54, 0.12))
    g = R.geometry(rings, np.c_[R.M.ROPE[:, :2], np.full(len(R.M.ROPE), .75)], None)
    return g["fits"] and g["base_gap_min"] >= 0.02 and min(g["ring_gap"].values()) >= 0.02, g
def jobs_C():
    """R1 and R2 move by the same vector (cm below); rotations separately (R1 +-15 | R2 +-20 | none), plus both for the best vectors."""
    vecs = [(0, 0), (3, 0), (0, 3), (3, 3), (0, 6), (3, 6), (6, 3), (6, 6)]
    rots = [(0, 0), (-15, 0), (15, 0), (0, -20), (0, 20)]
    out = [(v, r) for v in vecs for r in rots]
    out += [(v, r) for v in [(0, 3), (3, 3), (0, 6), (3, 6)] for r in [(15, -20), (-15, -20)]]
    return [dict(group="C", spec={"R1": (v[0] * cm, v[1] * cm, r[0]), "R2": (v[0] * cm, v[1] * cm, r[1])}) for v, r in out]


if __name__ == "__main__":
    js = {"A": jobs_A, "B": jobs_B, "C": jobs_C}[sys.argv[1]]()
    out = [j for j in js if check(j)[0]]
    print(len(js), "->", len(out), file=sys.stderr)
    json.dump(out, sys.stdout)
