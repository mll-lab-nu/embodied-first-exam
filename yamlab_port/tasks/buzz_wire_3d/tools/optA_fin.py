"""Finish release grid at the far post: G_down pen (V-finger, handle on the centre line) by either arm,
handle yaw near the finish yaw, height, tilt about the closing axis."""
import numpy as np
from scipy.spatial.transform import Rotation
from bw_geom import *
from grasps import *
from plan_r import Planner
s = Scene(layout=Layout(0.0, (0.5144, 0.270, TABLE_Z)))
P = Planner(s)
rng = np.random.default_rng(3)
p1 = s.rail[-1, :2]
Rfd = (s.finish_R * Rotation.from_euler("x", 180, degrees=True)).as_matrix()
angf = np.degrees(np.arctan2(Rfd[1, 0], Rfd[0, 0]))
print("finish yaw", round(angf, 1))
for side in ("left", "right"):
    for dyaw in (-9, -6, -3, 0):
        for tilt in (-10, 0, 10):
            row = []
            for hz in (0.034, 0.038, 0.042, 0.046, 0.050):
                R = Rotation.from_euler("z", dyaw, degrees=True).as_matrix() @ Rfd
                W = T_from(R, np.r_[p1, s.deck_top + hz])
                T = W @ pen("down", 0.036, 0.0, tilt)
                sols = P.ik[side].solve_multi(T[:3, 3], T[:3, :3], None, n_random=96, rng=rng)
                if not sols:
                    row.append("   --  "); continue
                c = max((P.clear(side, q, -0.0059, ignore=("stops",)) for q in sols), key=lambda c_: min(c_["wire"], c_["deck"]))
                row.append(f"{c['wire']*1000:3.0f}/{c['deck']*1000:3.0f}")
            print(f"{side} yaw {angf + dyaw:6.1f} tilt {tilt:3d} hz34..50: " + " ".join(row), flush=True)
