"""IK margin of the initial grasps (and pregrasps) at a settled state. usage: python grasp_probe.py tier states.npz step"""
import sys
import numpy as np
from scipy.spatial.transform import Rotation
import keyhole_geometry as kg, plan2 as pl, yam_kin as yk
from layout import Scene, T_from
tier, path, k = sys.argv[1], sys.argv[2], int(sys.argv[3])
sc = Scene(tier); z = np.load(path)
Tp = {n: T_from(Rotation.from_quat(z[f"keyhole_{n}"][k][[4, 5, 6, 3]]), z[f"keyhole_{n}"][k][:3]) @ sc.T_part_plate[n] for n in kg.NAMES}
rng = np.random.default_rng(0)
def solve(T, side):
    best = None
    for _ in range(80):
        q0 = yk.LOWER + rng.random(6) * (yk.UPPER - yk.LOWER)
        q, ok, _, _ = yk.ik(yk.world_to_base(T, side), q0, iters=150)
        if ok:
            m = float(np.min(np.minimum(q - yk.LOWER, yk.UPPER - q)))
            best = m if best is None else max(best, m)
    return best
cases = {"gold_fork": ("gold", lambda j: pl.gold_fork_grasp(0.056, -0.070, j)),
         "gold_band": ("gold", lambda j: pl.gold_grasp(float(__import__("os").environ.get("GY", -0.004)), 0.061, j)),
         "silver_edge": ("silver", lambda j: pl.silver_edge_grasp(-0.0024, -0.051, j))}
for name, (plate, mk) in cases.items():
    for side in ("left", "right"):
        for jaw in (1.0, -1.0):
            T = Tp[plate] @ mk(jaw)
            res = []
            for back in (0.0, 0.02, 0.06):
                Tb = T.copy(); Tb[:3, 3] -= back * T[:3, 0]
                res.append(solve(Tb, side))
            print(name, side, jaw, "approach", T[:3, 0].round(2), "tcp", T[:3, 3].round(3), "margins(back 0/2/6cm)", res, flush=True)
