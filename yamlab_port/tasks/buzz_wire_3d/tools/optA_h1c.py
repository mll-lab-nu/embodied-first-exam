"""Decisive check: with the only liftable start grasp (right arm, tilted tip pinch, handle toward the robot),
is there ANY start-post pose where the left (or right) ring grip can take over? Prints feasible pairs."""
import sys
import numpy as np
from scipy.spatial.transform import Rotation
from bw_geom import *
from grasps import *
from plan_r import Planner, frame_h_n
from optA_lift_check import tilted_A
s = Scene(layout=Layout(0.0, (0.5144, 0.270, TABLE_Z)))
P = Planner(s)
rng = np.random.default_rng(1)
p0 = s.rail[0, :2]
alpha = float(sys.argv[1])
AS, RS = (sys.argv[2], sys.argv[3]) if len(sys.argv) > 3 else ("right", "left")
G = tilted_A(alpha, tip_gap=-0.0025 + 0.004)
RG = ring()
found = 0
for hdeg in range(-180, 180, 15):
    h = np.array([np.cos(np.radians(hdeg)), np.sin(np.radians(hdeg)), 0])
    for beta in (-45, -30, -15, 0, 15, 30, 45):
        for hz in (0.035, 0.045, 0.055):
            n = Rotation.from_rotvec(np.radians(beta) * h).apply([0, 0, 1.0])
            W = T_from(frame_h_n(h, n), np.r_[p0, s.deck_top + hz])
            T = W @ G
            sa = P.ik[AS].solve_multi(T[:3, 3], T[:3, :3], None, n_random=64, rng=rng)
            ca = max((min(P.clear(AS, q, -0.0059, ignore=("stops",)).values()) for q in sa), default=None)
            if ca is None or ca < 0.002:
                continue
            T2 = W @ RG
            sb = P.ik[RS].solve_multi(T2[:3, 3], T2[:3, :3], None, n_random=64, rng=rng)
            cb = max((min(P.clear(RS, q, -0.0023, ignore=("stops",)).values()) for q in sb), default=None)
            print(f"h {hdeg:4d} b {beta:3d} hz {hz*1000:.0f}: A_{AS} {ca*1000:.0f} mm, ring_{RS} {'--' if cb is None else round(cb*1000)}", flush=True)
            if cb is not None and cb > 0.002:
                found += 1
print("FEASIBLE_PAIRS", found)
