"""Offline version of the old task's physical guard "task contact penetration exceeded 1 mm":
signed distance between the gold and silver convex colliders (exact slab prisms) at the logged poses,
plus each plate's lowest point vs the table top.

usage: python penetration_audit.py <tier> <states.npz> [every]   -> prints JSON
"""
import json
import sys
from pathlib import Path

import fcl
import numpy as np
from scipy.spatial.transform import Rotation

sys.path.insert(0, str(Path(__file__).resolve().parent))
import keyhole_geometry as kg
from route_check import convex
from layout import TABLE_Z

tier, path = sys.argv[1], sys.argv[2]
every = int(sys.argv[3]) if len(sys.argv) > 3 else 1
plates = kg.build_plates(kg.load_record(tier))
geoms = {n: [convex(c.vertices) for c in plates[n].cells_part()] for n in kg.NAMES}
verts = {n: plates[n].visual_part().vertices for n in kg.NAMES}
z = np.load(path)
n = len(z["keyhole_gold"])
worst, worst_step, lowest = np.inf, None, np.inf
for i in range(0, n, every):
    objs = {}
    for name in kg.NAMES:
        st = z[f"keyhole_{name}"][i]
        R = Rotation.from_quat(st[[4, 5, 6, 3]]).as_matrix()
        tf = fcl.Transform(R, st[:3])
        objs[name] = [fcl.CollisionObject(g, tf) for g in geoms[name]]
        lowest = min(lowest, float((verts[name] @ R.T + st[:3])[:, 2].min() - TABLE_Z))
    d = np.inf
    for a in objs["gold"]:
        for b in objs["silver"]:
            d = min(d, fcl.distance(a, b, fcl.DistanceRequest(enable_signed_distance=True), fcl.DistanceResult()))
    if d < worst:
        worst, worst_step = d, i
out = dict(steps_checked=len(range(0, n, every)), min_signed_distance_mm=worst * 1000, at_step=worst_step,
           max_penetration_mm=max(0.0, -worst * 1000), penetration_guard_1mm_ok=bool(-worst * 1000 <= 1.0),
           lowest_point_rel_table_mm=lowest * 1000)
print(json.dumps(out, indent=1))
