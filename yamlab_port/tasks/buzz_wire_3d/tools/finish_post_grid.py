"""Finish-post feasibility for the pen grip G_up: handle yaw x loop tilt x height (numpy IK + clearances)."""
import json
import sys
import numpy as np
from scipy.spatial.transform import Rotation
from bw_geom import *
from grasps import *
from ik import IK, BatchIK

side = sys.argv[1]
yaw, tx, ty = float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4])
s = Scene(layout=Layout(yaw_deg=yaw, t=(tx, ty, TABLE_Z)))
ik = BatchIK(side)
AP = ArmPoints(ik.arm)
Gup = pen("up", 0.033, -0.0275, 4.0)
post = s.rail[-1, :2]
rng = np.random.default_rng(0)
res = []
for hyaw in [int(v) for v in (sys.argv[5].split(',') if len(sys.argv) > 5 else range(0, 360, 45))]:
    h = np.array([np.cos(np.radians(hyaw)), np.sin(np.radians(hyaw)), 0.0])
    for beta in (-65, -50, -30, 0, 30, 50, 65):
        # loop normal: -z tilted by beta about the handle axis
        n = Rotation.from_rotvec(np.radians(beta) * h).apply([0, 0, -1.0])
        R = Rotation.from_matrix(np.column_stack([h, np.cross(n, h), n]))
        row = []
        for dz in (0.12, 0.09, 0.06, 0.04):
            p = np.r_[post, s.deck_top + dz]
            T = T_from(R.as_matrix(), p) @ Gup
            sols = ik.solve_multi(T[:3, 3], T[:3, :3], None, n_random=96, rng=rng)
            if not sols:
                row.append(None)
                continue
            best = max(min(clearances(s, AP.world(qq, -0.0056)).values()) for qq in sols)
            row.append(round(best * 1000, 1))
        print(f"{side} hyaw {hyaw:3d} beta {beta:2d} min-clear(mm) at loop z+[120,90,60,40]mm: {row}", flush=True)
