"""Top-down tip pinch at the start post with the handle yawed out from under the span (both arms)."""
import numpy as np
from scipy.spatial.transform import Rotation
from bw_geom import *
from grasps import *
from plan_r import Planner, frame_h_n
s = Scene(layout=Layout(-90.0, (0.96, 0.055679, TABLE_Z)))
P = Planner(s)
rng = np.random.default_rng(0)
p0 = s.rail[0, :2]
for hdeg in (180, 150, 120, 90, -150, -120):
    h = np.array([np.cos(np.radians(hdeg)), np.sin(np.radians(hdeg)), 0])
    R = Rotation.from_euler("z", hdeg - np.degrees(np.arctan2(*s.start_R.apply([1, 0, 0])[[1, 0]])), degrees=True) * s.start_R
    W = T_from(R.as_matrix(), np.r_[p0, s.start_p[2]])
    for c in (0.0466, 0.054):
        T = W @ topdown("A", c=c, tip_gap=-0.0025)   # tips 1 mm above the deck
        row = []
        for side in ("left", "right"):
            sols = P.ik[side].solve_multi(T[:3, 3], T[:3, :3], None, n_random=192, rng=rng)
            if not sols:
                row.append(f"{side}: --"); continue
            cl = max((P.clear(side, q, -0.0059, ignore=("stops",)) for q in sols), key=lambda c_: min(c_.values()))
            row.append(f"{side}: n={len(sols)} " + ",".join(f"{k}={v*1000:.0f}" for k, v in cl.items()))
        print(f"h {hdeg:4d} c {c*1000:.1f}: " + " | ".join(row), flush=True)
