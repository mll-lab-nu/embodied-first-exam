"""Finish-side compatibility: ring grip (left/right) on the finish post vs G_down (left/right) on the deck, per handle direction."""
import sys
import numpy as np
from scipy.spatial.transform import Rotation
from bw_geom import *
from grasps import *
from ik import BatchIK
from plan_r_keys import frame_h_n
from plan_r_keys2 import solve

yaw, tx, ty = float(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3])
s = Scene(layout=Layout(yaw_deg=yaw, t=(tx, ty, TABLE_Z)))
ik = {k: BatchIK(k) for k in ("left", "right")}
AP = {k: ArmPoints(ik[k].arm) for k in ik}
rng = np.random.default_rng(2)
p1 = s.rail[-1, :2]
Rfd = s.finish_R * Rotation.from_euler("x", 180, degrees=True)
for hdeg in range(-180, 180, 30):
    h = np.array([np.cos(np.radians(hdeg)), np.sin(np.radians(hdeg)), 0])
    row = {}
    for hz in (0.055, 0.06):
        W = T_from(frame_h_n(h, [0, 0, -1]).as_matrix(), np.r_[p1, s.deck_top + hz])
        for side in ("left", "right"):
            row[f"Rg_{side[0].upper()}_{hz*1000:.0f}"] = solve(ik[side], AP[side], s, W @ ring(), -0.0023, rng)
    ang = hdeg - np.degrees(np.arctan2(*Rfd.apply([1, 0, 0])[[1, 0]]))
    R = Rotation.from_euler("z", ang, degrees=True) * Rfd
    W = T_from(R.as_matrix(), np.r_[p1, s.finish_p[2] + 0.0015])
    for side in ("left", "right"):
        row[f"Gdn_{side[0].upper()}"] = solve(ik[side], AP[side], s, W @ pen("down", 0.033, -0.0275, 4.0), -0.0056, rng)
    print(hdeg, {k: (None if v is None else min(v[1].values())) for k, v in row.items()}, flush=True)
