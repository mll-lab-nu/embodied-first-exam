"""Apply a rigid re-layout (yaw about Z + translation) to the plate poses of a states.npz (for offline planning
only: a settle on the flat, uniform table is invariant under such a motion).
usage: python relayout_states.py in.npz out.npz x0_old y0_old yaw_old x0_new y0_new yaw_new"""
import sys
import numpy as np
from scipy.spatial.transform import Rotation
z = np.load(sys.argv[1]); a = list(map(float, sys.argv[3:9]))
R = Rotation.from_euler("z", a[5] - a[2], degrees=True)
out = {}
for k in ("keyhole_gold", "keyhole_silver"):
    s = z[k].copy()
    p = s[:, :3] - np.r_[a[0], a[1], 0]
    s[:, :3] = R.apply(p) + np.r_[a[3], a[4], 0]
    q = (R * Rotation.from_quat(s[:, [4, 5, 6, 3]])).as_quat()
    s[:, 3:7] = q[:, [3, 0, 1, 2]]
    s[:, 7:10] = R.apply(s[:, 7:10]); s[:, 10:13] = R.apply(s[:, 10:13])
    out[k] = s
np.savez(sys.argv[2], **out)
