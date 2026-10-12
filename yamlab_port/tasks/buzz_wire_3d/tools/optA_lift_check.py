"""Bounded check: can a (tilted) top-down tip pinch at the near start post lift the wand 20-60 mm? x-span layout."""
import sys
import numpy as np
from scipy.spatial.transform import Rotation
from bw_geom import *
from grasps import *
from plan_r import Planner, frame_h_n, PlanError
s = Scene(layout=Layout(0.0, (0.5144, 0.270, TABLE_Z)))
P = Planner(s)
rng = np.random.default_rng(0)
p0 = s.rail[0, :2]
h_old = np.degrees(np.arctan2(*s.start_R.apply([1, 0, 0])[[1, 0]]))


def tilted_A(alpha_deg, c=0.0525, tip_gap=-0.0025):
    G = topdown("A", c=c, tip_gap=tip_gap)
    tcp = np.array([c, 0.0, 0.0])
    Rt = Rotation.from_euler("y", alpha_deg, degrees=True).as_matrix()   # about the wand y (closing) axis
    T = np.eye(4); T[:3, :3] = Rt; T[:3, 3] = tcp - Rt @ tcp
    return T @ G


if __name__ == "__main__":
  for side in ("left", "right"):
      for hdeg in (180, 150, -150, 120, -120, 90, -90):
          Rz = Rotation.from_euler("z", hdeg - h_old, degrees=True)
          post = np.r_[p0, 0]
          W0 = T_from((Rz * s.start_R).as_matrix(), Rz.apply(s.start_p - post) + post)
          for alpha in (-45, -30, -15, 0, 15, 30, 45):
              G = tilted_A(alpha, tip_gap=-0.0025 + (0.004 if alpha else 0))
              T = W0 @ G
              sols = P.ik[side].solve_multi(T[:3, 3], T[:3, :3], None, n_random=128, rng=rng)
              best = -1
              for q in sols:
                  if not P.ok(side, q, -0.0059, ignore=("stops",))[0]:
                      continue
                  reached = 0
                  for dz in np.arange(0.003, 0.0605, 0.003):
                      W = W0.copy(); W[2, 3] += dz
                      try:
                          qs, _ = P.track(side, [W @ G], q, -0.0059, ignore=("stops",))
                          q = qs[-1]; reached = dz
                      except PlanError:
                          break
                  best = max(best, reached)
              print(f"{side} h {hdeg:4d} alpha {alpha:3d}: branches {len(sols)}, max straight lift {'--' if best < 0 else round(best*1000)} mm", flush=True)
