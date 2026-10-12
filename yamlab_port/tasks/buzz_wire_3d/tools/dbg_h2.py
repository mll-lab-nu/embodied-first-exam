import numpy as np
from scipy.spatial.transform import Rotation
from bw_geom import *
from grasps import *
from plan_r import Planner, frame_h_n, interp_T, n_steps, PlanError
from stages_r import GDN, Rz, yaw_of
s = Scene(layout=Layout(-90.0, (0.96, 0.055679, TABLE_Z)))
P = Planner(s)
p1 = s.rail[-1, :2]
Rfd = (s.finish_R * Rotation.from_euler("x", 180, degrees=True)).as_matrix(); ang_f = yaw_of(Rfd)
h = np.array([np.cos(np.radians(-120)), np.sin(np.radians(-120)), 0])
Wm = T_from(frame_h_n(h, [0, 0, -1]), np.r_[p1, s.deck_top + 0.057])
T = Wm @ GDN
sols = P.ik["right"].solve_multi(T[:3, 3], T[:3, :3], None, n_random=512, rng=np.random.default_rng(1))
print("branches", len(sols))
def deckW(yaw, dz=0.0015):
    return T_from(Rz(yaw - ang_f) @ Rfd, np.r_[p1, s.finish_p[2] + dz])
for target in (-150, -165, -180):
    for order in ("lower_then_yaw", "yaw_then_lower", "yaw_mid"):
        if order == "lower_then_yaw":
            W6 = deckW(-120); seq = interp_T(Wm, W6, n_steps(Wm, W6)) + P.wand_yaw(W6, p1, target + 120)
        elif order == "yaw_then_lower":
            Wy = P.wand_yaw(Wm, p1, target + 120); seq = Wy + interp_T(Wy[-1], deckW(target), n_steps(Wy[-1], deckW(target)))
        else:
            Wh = deckW(-120, 0.02); Wy = P.wand_yaw(Wh, p1, target + 120)
            seq = interp_T(Wm, Wh, n_steps(Wm, Wh)) + Wy + interp_T(Wy[-1], deckW(target), n_steps(Wy[-1], deckW(target)))
        for i, q in enumerate(sols):
            try:
                P.track("right", [W @ GDN for W in seq], q, -0.0056, ignore=("stops",))
                print(target, order, "branch", i, "OK")
            except PlanError as e:
                print(target, order, "branch", i, e)
