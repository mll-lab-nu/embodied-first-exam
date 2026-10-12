"""Clearance of the convex collision cells along the relative route (fcl GJK on convex cells).

usage: python route_check.py <tier> [turn_sign]
Prints min clearance per stage and the overall minimum; writes route_<tier>_<sign>.npz
"""
import json, sys
from pathlib import Path
import numpy as np
import fcl
from scipy.spatial.transform import Rotation
sys.path.insert(0, str(Path(__file__).resolve().parent))
import keyhole_geometry as kg
import route as rt


def convex(cell_vertices):
    import trimesh
    h = trimesh.convex.convex_hull(cell_vertices)
    faces = np.c_[np.full(len(h.faces), 3), h.faces].ravel()
    return fcl.Convex(np.asarray(h.vertices, float), len(h.faces), faces)


def plate_cells(plate):
    """cells in the plate frame (inverse of plate_to_asm)."""
    T = np.linalg.inv(plate.plate_to_asm)
    return [(T[:3, :3] @ c.vertices.T).T + T[:3, 3] for c in plate.cells]


class Checker:
    def __init__(self, record):
        plates = kg.build_plates(record)
        self.g = [fcl.CollisionObject(convex(v), fcl.Transform()) for v in plate_cells(plates["gold"])]
        self.s_geom = [convex(v) for v in plate_cells(plates["silver"])]
        self.scale = record["scale"]

    def distance(self, r_rel, c):
        """min signed-ish distance (m) between gold cells and silver cells; negative if penetrating."""
        p = rt.silver_plate_pose_in_gold(r_rel, c, self.scale)
        tf = fcl.Transform(r_rel.as_matrix(), p)
        best = np.inf
        for sg in self.s_geom:
            so = fcl.CollisionObject(sg, tf)
            for go in self.g:
                req = fcl.DistanceRequest(enable_signed_distance=True)
                res = fcl.DistanceResult()
                d = fcl.distance(go, so, req, res)
                best = min(best, d)
        return best


if __name__ == "__main__":
    tier = sys.argv[1]
    sign = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    rec = kg.load_record(tier)
    ch = Checker(rec)
    r0, c0 = rt.nominal_relative(rec)
    print("start bar point (plate units):", (c0 * 1000 / rec["scale"]).round(3).tolist(),
          "start clearance mm", round(ch.distance(r0, c0) * 1000, 3))
    path = rt.route(rec, tier, sign)
    d = np.array([ch.distance(r, c) for r, c, _ in path])
    stages = [s for _, _, s in path]
    out = {}
    for s in dict.fromkeys(stages):
        m = np.array([x == s for x in stages])
        i = np.argmin(np.where(m, d, np.inf))
        out[s] = dict(min_mm=round(float(d[i] * 1000), 3), at_index=int(i), n=int(m.sum()))
    print(json.dumps(out))
    print("overall min mm", round(float(d.min() * 1000), 3), "end clearance mm", round(float(d[-1] * 1000), 2))
    np.savez(Path(__file__).parent / f"route_{tier}_{sign:+d}.npz", d=d,
             quat=np.array([r.as_quat() for r, _, _ in path]), c=np.array([c for _, c, _ in path]),
             stage=np.array(stages))
