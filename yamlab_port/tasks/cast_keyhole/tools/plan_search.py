"""Grid search over work pose / turn split / slide split / jaw signs for IK feasibility (run on vast)."""
import itertools, json, sys
from multiprocessing import Pool
import numpy as np
from plan import Plan, Grasps, check

SETTLED = None
if len(sys.argv) > 2:
    _z = np.load(sys.argv[2]); _k = int(sys.argv[3]) if len(sys.argv) > 3 else 74
    SETTLED = (_z["keyhole_gold"][_k, :7], _z["keyhole_silver"][_k, :7])


def run(args):
    gamma, split, dx, dy, h, gj, sj, tilt = args
    p = Plan(sys.argv[1], gamma_deg=gamma, split=split, work=(dx, dy, h), tilt_deg=tilt,
             grasps=Grasps(gold_jaw=gj, silver_jaw=sj))
    if SETTLED is not None:
        p.set_initial_from_parts(*SETTLED)
    try:
        res, _, _ = check(p, verbose=False)
    except Exception as e:
        return dict(args=args, error=repr(e))
    out = dict(args=args)
    for side in ("left", "right"):
        r = res[side]
        out[side] = r if isinstance(r, str) else dict(fails=r["stats"]["fails"], margin=round(r["stats"]["min_margin_rad"], 3),
                                                      ph={k: (v["fails"], round(v["margin"], 2)) for k, v in r["phases"].items()},
                                                      jump=round(r["stats"]["max_jump_rad"], 3), seed=round(r["seed_margin"], 3))
    return out

if __name__ == "__main__":
    grid = list(itertools.product([0, 45], [0.5, 1.0], [-0.15, -0.08], [-0.25, -0.18, -0.12], [0.12, 0.16], [1], [-1],
                                  [-45, -30, -15]))
    with Pool(8) as pool:
        for o in pool.imap_unordered(run, grid):
            print(json.dumps(o), flush=True)
