"""Plan R key poses, part 2: handover heights/tilts at both posts and the top-down pick on the right."""
import json
import sys
import numpy as np
from scipy.spatial.transform import Rotation
from bw_geom import *
from grasps import *
from ik import BatchIK
from plan_r_keys import frame_h_n


def solve(ik, AP, s, T, fq, rng, extra=None):
    sols = ik.solve_multi(T[:3, 3], T[:3, :3], None, n_random=128, rng=rng)
    if not sols:
        return None
    cl = [clearances(s, AP.world(q, fq)) for q in sols]
    i = max(range(len(sols)), key=lambda k: min(cl[k].values()))
    return (len(sols), {a: round(b * 1000, 1) for a, b in cl[i].items()})


def main(yaw, tx, ty):
    s = Scene(layout=Layout(yaw_deg=yaw, t=(tx, ty, TABLE_Z)))
    ik = {k: BatchIK(k) for k in ("left", "right")}
    AP = {k: ArmPoints(ik[k].arm) for k in ik}
    rng = np.random.default_rng(1)
    p0, p1 = s.rail[0, :2], s.rail[-1, :2]
    h_start = s.start_R.apply([1, 0, 0]); h_start[2] = 0; h_start /= np.linalg.norm(h_start)
    Gup, Rg = pen("up", 0.033, -0.0275, 4.0), ring()
    print("== handover 1 (start post): G_up right + ring left; tilt about the handle axis")
    for beta in (0, 20, 30, 40, 50):
        for hz in (0.045, 0.05, 0.055, 0.06):
            n = Rotation.from_rotvec(np.radians(beta) * h_start).apply([0, 0, 1.0])
            W = T_from(frame_h_n(h_start, n).as_matrix(), np.r_[p0, s.deck_top + hz])
            a = solve(ik["right"], AP["right"], s, W @ Gup, -0.0056, rng)
            b = solve(ik["left"], AP["left"], s, W @ Rg, -0.0023, rng)
            print(f"beta {beta:2d} hz {hz*1000:.0f}: Gup_R {a}  Rg_L {b}", flush=True)
    print("== handover 2 (finish post): ring left (h=-y) + top-down B right")
    for beta in (0, 20, 30):
        for hz in (0.05, 0.055, 0.06, 0.065, 0.07):
            h = np.array([0, -1.0, 0])
            n = Rotation.from_rotvec(np.radians(beta) * h).apply([0, 0, -1.0])
            W = T_from(frame_h_n(h, n).as_matrix(), np.r_[p1, s.deck_top + hz])
            a = solve(ik["left"], AP["left"], s, W @ Rg, -0.0023, rng)
            b = solve(ik["right"], AP["right"], s, W @ topdown("B"), -0.0059, rng)
            print(f"beta {beta:2d} hz {hz*1000:.0f}: Rg_L {a}  B_R {b}", flush=True)
    print("== top-down B right on the deck at the finish (face-down), handle directions")
    Rfd = s.finish_R * Rotation.from_euler("x", 180, degrees=True)
    for hdeg in (-90, -135, 180, -45):
        h = np.array([np.cos(np.radians(hdeg)), np.sin(np.radians(hdeg)), 0])
        ang = hdeg - np.degrees(np.arctan2(*Rfd.apply([1, 0, 0])[[1, 0]]))
        R = Rotation.from_euler("z", ang, degrees=True) * Rfd
        W = T_from(R.as_matrix(), np.r_[p1, s.finish_p[2] + 0.0015])
        print(f"h {hdeg}: B_R {solve(ik['right'], AP['right'], s, W @ topdown('B'), -0.0059, rng)}  "
              f"B_L {solve(ik['left'], AP['left'], s, W @ topdown('B'), -0.0059, rng)}", flush=True)


if __name__ == "__main__":
    main(float(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3]))
