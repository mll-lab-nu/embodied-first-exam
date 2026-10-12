"""Feasibility map of finish grips (easier): for wand poses at the finish post (handle yaw h, loop height hz above the
deck, finish pitch), the best collision clearance over IK solutions of one arm and grip.
Usage: python finish_grip_map.py <tier> <side> <grip spec> ...   grip spec: pen:<roll>:<yaw>:<xc>:<x_tip>[:<tilt>]
Env FGM_HZ / FGM_H: comma lists of loop heights (m) and handle yaws (deg; "f" = finish yaw).
"""
import sys
import numpy as np
from bw_geom import Scene, Layout, TABLE_Z
from plan_r import Planner
from stages_r import Rz, yaw_of
from grasps import T_from
import stages_a

tier, side = sys.argv[1], sys.argv[2]
specs = sys.argv[3:]
s = Scene(tier, layout=Layout(0.0, (0.5144, 0.270, TABLE_Z)))
P = Planner(s)
Rfd = (s.finish_R * stages_a.Rotation.from_euler("x", 180, degrees=True)).as_matrix()
ang_f = yaw_of(Rfd)
p1 = s.rail[-1, :2]
rng = np.random.default_rng(0)
for spec in specs:
    f = spec.split(":")
    roll, yaw, xc, xt = f[1:5]
    tilt = float(f[5]) if len(f) > 5 else 0.0
    G, fqh, fqo = stages_a.gdown_grip(float(roll), float(yaw), xc=float(xc), x_tip=float(xt), tilt_deg=tilt)
    print(f"== {side} {spec}  fq {fqh:.4f}", flush=True)
    import os
    HZ = [float(v) for v in os.environ.get("FGM_HZ", "0.020,0.030,0.040,0.055").split(",")]
    HS = [ang_f if v == "f" else float(v) for v in os.environ.get("FGM_H", "90,110,130,150,f").split(",")]
    for hz in HZ:
        row = []
        for h in HS:
            W = T_from(Rz(h - ang_f) @ Rfd, np.r_[p1, s.deck_top + hz])
            T = W @ G
            sols = P.ik[side].solve_multi(T[:3, 3], T[:3, :3], None, n_random=192, rng=rng)
            best = None
            for q in sols:
                c = P.clear(side, q, fqh, ignore=("stops",))
                m = min(c["wire"], c["deck"], c["frame"], c["table"])
                if best is None or m > best[0]:
                    best = (m, c)
            row.append("  ---  " if best is None else f"{best[0]*1000:6.1f}{'w' if best[1]['wire'] == best[0] else 'd'}")
        print(f"hz {hz*1000:4.0f} mm | " + " ".join(row) + f"   (h = {' '.join(str(round(v)) for v in HS)})", flush=True)
