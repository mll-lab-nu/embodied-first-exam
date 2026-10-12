"""Run tools/dry_run_a.py and print, for each rejected arm-to-wire configuration, the nearest arm links and wire points.
Usage: python diag_wire_hits.py <tools dir> <start yaw deg> <tier>"""
import sys, numpy as np
sys.path.insert(0, sys.argv[1])
import plan_r, grasps
from grasps import wire_tree
from bw_geom import WIRE_R
orig_ok = plan_r.Planner.ok
seen = {}
def ok(self, side, q, fq, ignore=(), margin=None):
    good, c = orig_ok(self, side, q, fq, ignore, margin)
    if not good and c.get("wire", 1) < 0.004 and "wire" not in ignore:
        W = self.AP[side].world(q, fq)
        t = wire_tree(self.s)
        rows = []
        for link, P in W.items():
            d, i = t.query(P)
            k = int(np.argmin(d))
            rows.append((d[k] - WIRE_R, link, P[k].round(4), t.data[i[k]].round(4).tolist()))
        rows.sort(key=lambda r: r[0])
        key = (side, rows[0][1])
        seen[key] = seen.get(key, 0) + 1
        if seen[key] <= 3:
            print("  WIRE-HIT", side, [(round(r[0]*1000,1), r[1], r[2].tolist(), r[3]) for r in rows[:3]], "q", np.round(q,3).tolist(), flush=True)
    return good, c
plan_r.Planner.ok = ok
sys.argv = ["dry_run_a.py", sys.argv[2], sys.argv[3]]
exec(open(sys.path[0] + "/dry_run_a.py").read())
