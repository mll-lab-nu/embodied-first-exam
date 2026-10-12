"""Which top-down (approach -z) poses can the right YAM arm reach? Sweep x, y, z, roll."""
import numpy as np
from scipy.spatial.transform import Rotation
from ik import IK
ik = IK("right")
rng = np.random.default_rng(1)
for z in [0.90, 1.0, 1.1]:
    for x in [0.35, 0.45, 0.55]:
        row = []
        for y in [-0.45, -0.3, -0.15, 0.0, 0.15]:
            rolls = []
            for roll in range(0, 360, 45):
                # link6: z = down, y rotated by roll about z
                R = Rotation.from_euler("z", roll, degrees=True).as_matrix() @ np.column_stack([[1, 0, 0], [0, -1, 0], [0, 0, -1]])
                # link6 origin above the TCP (tips 0.145 below link6)
                p = np.array([x, y, z + 0.146])
                q, sols = ik.solve_multi(p, R, np.eye(4), n_random=25, rng=rng)
                if q is not None:
                    rolls.append(roll)
            row.append(f"y{y:+.2f}:{rolls}")
        print(f"z{z:.2f} x{x:.2f}", " ".join(row), flush=True)
