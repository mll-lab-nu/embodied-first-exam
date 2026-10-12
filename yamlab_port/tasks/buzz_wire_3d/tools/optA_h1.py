"""Option A handover 1 grid: top-down A (arm X) + ring grip (arm Y) on the start post, x-span yaw 0 layout."""
import numpy as np
from scipy.spatial.transform import Rotation
from bw_geom import *
from grasps import *
from plan_r import Planner, frame_h_n
s = Scene(layout=Layout(0.0, (0.5144, 0.270, TABLE_Z)))
P = Planner(s)
rng = np.random.default_rng(0)
p0 = s.rail[0, :2]
A = topdown("A", c=GRIP_XC, tip_gap=-0.0025)
RG = ring()


def ok(side, T, fq):
    sols = P.ik[side].solve_multi(T[:3, 3], T[:3, :3], None, n_random=128, rng=rng)
    if not sols:
        return None
    return max(min(v for k, v in P.clear(side, q, fq, ignore=("stops",)).items()) for q in sols)


for hdeg, X, Y in ((180, "right", "left"), (180, "left", "right"), (90, "right", "left"), (-90, "left", "right")):
    h = np.array([np.cos(np.radians(hdeg)), np.sin(np.radians(hdeg)), 0])
    for beta in (-40, -20, 0, 20, 40):
        row = []
        for hz in (0.02, 0.03, 0.04, 0.05, 0.06):
            n = Rotation.from_rotvec(np.radians(beta) * h).apply([0, 0, 1.0])
            W = T_from(frame_h_n(h, n), np.r_[p0, s.deck_top + hz])
            a, b = ok(X, W @ A, -0.0059), ok(Y, W @ RG, -0.0023)
            row.append(f"{'--' if a is None else round(a*1000)}/{'--' if b is None else round(b*1000)}")
        print(f"h {hdeg} A={X} Rg={Y} beta {beta:3d}  hz20..60: " + "  ".join(row), flush=True)
