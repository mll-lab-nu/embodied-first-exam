"""Feasibility map of the left tilted pinch (alpha 30) on the start post: handle yaw x tilt at a few heights."""
import numpy as np
from scipy.spatial.transform import Rotation
from bw_geom import *
from grasps import *
from plan_r import Planner, frame_h_n
from optA_lift_check import tilted_A
s = Scene(layout=Layout(0.0, (0.5144, 0.270, TABLE_Z)))
P = Planner(s)
rng = np.random.default_rng(2)
p0 = s.rail[0, :2]
G = tilted_A(30.0, tip_gap=-0.0025 + 0.004)
for hz in (0.03, 0.045, 0.055):
    print("hz", hz)
    print("beta\\h " + " ".join(f"{h:5d}" for h in range(-180, 180, 30)))
    for beta in (-45, -30, -15, 0, 15):
        row = []
        for hdeg in range(-180, 180, 30):
            h = np.array([np.cos(np.radians(hdeg)), np.sin(np.radians(hdeg)), 0])
            n = Rotation.from_rotvec(np.radians(beta) * h).apply([0, 0, 1.0])
            T = T_from(frame_h_n(h, n), np.r_[p0, s.deck_top + hz]) @ G
            sols = P.ik["left"].solve_multi(T[:3, 3], T[:3, :3], None, n_random=64, rng=rng)
            c = max((min(P.clear("left", q, -0.0059, ignore=("stops",)).values()) for q in sols), default=None)
            row.append("   --" if c is None else f"{c*1000:5.0f}")
        print(f"{beta:6d} " + " ".join(row), flush=True)
