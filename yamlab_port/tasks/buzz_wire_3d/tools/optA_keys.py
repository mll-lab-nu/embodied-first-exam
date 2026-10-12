"""Option A key poses with the real (V-shaped) YAM finger: x-span layout, start post near the robot."""
import sys
import numpy as np
from scipy.spatial.transform import Rotation
from bw_geom import *
from grasps import *
from plan_r import Planner, frame_h_n

yaw, tx, ty = float(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3])
s = Scene(layout=Layout(yaw, (tx, ty, TABLE_Z)))
P = Planner(s)
rng = np.random.default_rng(0)
p0, p1 = s.rail[0, :2], s.rail[-1, :2]
print("start post", p0.round(3), "finish post", p1.round(3), "rest clear",
      {k: round(min(P.clear(k, np.zeros(6), -0.0475).values()) * 1000, 1) for k in ("left", "right")})
A = topdown("A", c=GRIP_XC, tip_gap=-0.0025)
GD = pen("down", 0.033 + 0.003, 0.0, 0.0)
RG = ring()


def best(side, T, fq):
    sols = P.ik[side].solve_multi(T[:3, 3], T[:3, :3], None, n_random=192, rng=rng)
    if not sols:
        return "--"
    c = max((P.clear(side, q, fq, ignore=("stops",)) for q in sols), key=lambda c_: min(c_.values()))
    return f"n{len(sols)} " + ",".join(f"{k[0]}{v*1000:.0f}" for k, v in c.items())


h_old = s.start_R.apply([1, 0, 0]); ang_old = np.degrees(np.arctan2(h_old[1], h_old[0]))
for hdeg in (90, -90, 180, 135, -135):
    h = np.array([np.cos(np.radians(hdeg)), np.sin(np.radians(hdeg)), 0])
    R = Rotation.from_euler("z", hdeg - ang_old, degrees=True) * s.start_R
    W = T_from(R.as_matrix(), np.r_[p0, s.start_p[2]])
    Wl = T_from(frame_h_n(h, [0, 0, 1]), np.r_[p0, s.deck_top + 0.05])
    print(f"start h {hdeg:4d}: A_left {best('left', W @ A, -0.0059)} | A_right {best('right', W @ A, -0.0059)} || "
          f"lift50: A_left {best('left', Wl @ A, -0.0059)} A_right {best('right', Wl @ A, -0.0059)} "
          f"Rg_left {best('left', Wl @ RG, -0.0023)} Rg_right {best('right', Wl @ RG, -0.0023)}", flush=True)
Rf = s.finish_R * Rotation.from_euler("x", 180, degrees=True)
hf = Rf.apply([1, 0, 0]); angf = np.degrees(np.arctan2(hf[1], hf[0]))
print("final handle yaw", round(angf, 1))
for hdeg in (90, -90, angf):
    h = np.array([np.cos(np.radians(hdeg)), np.sin(np.radians(hdeg)), 0])
    for hz in (0.012, 0.03):
        W = T_from(frame_h_n(h, [0, 0, -1]), np.r_[p1, s.deck_top + hz])
        print(f"finish h {hdeg:6.1f} hz {hz*1000:.0f}: Rg_left {best('left', W @ RG, -0.0023)} Rg_right {best('right', W @ RG, -0.0023)} "
              f"Gdn_left {best('left', W @ GD, -0.0035)} Gdn_right {best('right', W @ GD, -0.0035)}", flush=True)
