"""Roll capability about a fixed horizontal approach axis for one YAM arm (numpy model)."""
import sys
import numpy as np
from scipy.spatial.transform import Rotation
from ik import IK
side = sys.argv[1]
a = np.array([float(v) for v in sys.argv[2].split(",")])   # approach direction
P = [np.array([float(v) for v in p.split(",")]) for p in sys.argv[3:]]  # link6 positions
ik = IK(side)
a = a / np.linalg.norm(a)
up = np.array([0, 0, 1.0])
for p in P:
    feas = []
    for roll in range(0, 360, 15):
        # camera (link6 y) = up rotated by roll about the approach
        y = Rotation.from_rotvec(np.deg2rad(roll) * a).apply(up - a * np.dot(up, a))
        y /= np.linalg.norm(y)
        x = np.cross(y, a)
        R = np.column_stack([x, y, a])
        q, sols = ik.solve_multi(p, R, np.eye(4), n_random=30, rng=np.random.default_rng(roll))
        feas.append(roll if q is not None else None)
    print(side, "a", a.round(2), "p", p.round(3), "feasible rolls:", [r for r in feas if r is not None], flush=True)
