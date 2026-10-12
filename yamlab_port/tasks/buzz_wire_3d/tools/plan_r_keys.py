"""Plan R key poses (numpy IK, both arms): G_up pick -> handover to the ring grip at the start post ->
carry -> handover to G_down at the finish post -> deck yaws. Prints IK solution counts and clearances."""
import json
import sys
import numpy as np
from scipy.spatial.transform import Rotation
from bw_geom import *
from grasps import *
from ik import BatchIK


def frame_h_n(h, n):
    h = np.asarray(h, float); h /= np.linalg.norm(h)
    n = np.asarray(n, float); n = n - h * np.dot(h, n); n /= np.linalg.norm(n)
    return Rotation.from_matrix(np.column_stack([h, np.cross(n, h), n]))


def main(yaw, tx, ty, hz=0.045):
    s = Scene(layout=Layout(yaw_deg=yaw, t=(tx, ty, TABLE_Z)))
    ik = {k: BatchIK(k) for k in ("left", "right")}
    AP = {k: ArmPoints(ik[k].arm) for k in ik}
    rng = np.random.default_rng(0)
    p0, p1 = s.rail[0, :2], s.rail[-1, :2]
    tang = s.tangents()
    h_start = s.start_R.apply([1, 0, 0]); h_start[2] = 0
    Gup, Gdn, Rg = pen("up", 0.033, -0.0275, 4.0), pen("down", 0.033, -0.0275, 4.0), ring()
    K = {}
    K["P1_Gup_R_start"] = ("right", T_from(s.start_R.as_matrix(), s.start_p + [0, 0, 0.0015]) @ Gup, -0.0056)
    W2 = T_from(frame_h_n(h_start, [0, 0, 1]).as_matrix(), np.r_[p0, s.deck_top + hz])
    K["P2_Gup_R_lift"] = ("right", W2 @ Gup, -0.0056)
    K["P3_Rg_L_hand1"] = ("left", W2 @ Rg, -0.0023)
    K["P3b_Rg_L_hand1_open"] = ("left", W2 @ Rg @ T_from(np.eye(3), [0, 0, -0.03]), -0.0053)
    W4 = T_from(frame_h_n([1, 0, 0], [0, 0, 1]).as_matrix(), np.r_[p0, s.deck_top + hz])
    K["P4_Rg_L_yawed"] = ("left", W4 @ Rg, -0.0023)
    for name, frac in [("P5a_post0_top", 0.12), ("P5b_elbow1", 0.25), ("P5c_span1", 0.4), ("P5d_span2", 0.6), ("P5e_elbow2", 0.75), ("P5f_post1_top", 0.88)]:
        sa = frac * s.arc[-1]
        p = np.array([np.interp(sa, s.arc, s.rail[:, k]) for k in range(3)])
        t = np.array([np.interp(sa, s.arc, tang[:, k]) for k in range(3)])
        K[name] = ("left", T_from(frame_h_n([1, 0, 0], t).as_matrix(), p) @ Rg, -0.0023)
    W6 = T_from(frame_h_n([1, 0, 0], [0, 0, -1]).as_matrix(), np.r_[p1, s.deck_top + hz])
    K["P6a_Rg_L_post1_low"] = ("left", W6 @ Rg, -0.0023)
    W6b = T_from(frame_h_n([0, -1, 0], [0, 0, -1]).as_matrix(), np.r_[p1, s.deck_top + hz])
    K["P6b_Rg_L_post1_yawed"] = ("left", W6b @ Rg, -0.0023)
    K["P7_Gdn_R_hand2"] = ("right", W6b @ Gdn, -0.0056)
    fz = s.finish_p[2] + 0.0015
    Rfd = s.finish_R * Rotation.from_euler("x", 180, degrees=True)
    for name, hdir, side in [("P8a_Gdn_R_deck_right", [0, -1, 0], "right"), ("P8b_Gdn_R_deck_front", [-1, 0, 0], "right"),
                             ("P9a_Gdn_L_deck_front", [-1, 0, 0], "left")]:
        ang = np.degrees(np.arctan2(hdir[1], hdir[0])) - np.degrees(np.arctan2(*Rfd.apply([1, 0, 0])[[1, 0]]))
        R = Rotation.from_euler("z", ang, degrees=True) * Rfd
        K[name] = (side, T_from(R.as_matrix(), np.r_[p1, fz]) @ Gdn, -0.0056)
    K["P9b_Gdn_L_final"] = ("left", T_from(Rfd.as_matrix(), np.r_[p1, fz]) @ Gdn, -0.0056)
    out = {}
    for k, (side, T, fq) in K.items():
        sols = ik[side].solve_multi(T[:3, 3], T[:3, :3], None, n_random=128, rng=rng)
        if not sols:
            out[k] = None
        else:
            cl = [clearances(s, AP[side].world(q, fq)) for q in sols]
            best = max(range(len(sols)), key=lambda i: min(cl[i].values()))
            out[k] = dict(side=side, n=len(sols), q=np.round(sols[best], 3).tolist(),
                          clear={a: round(b * 1000, 1) for a, b in cl[best].items()})
        print(k, None if out[k] is None else (side, out[k]["n"], out[k]["clear"]), flush=True)
    json.dump(out, open(f"../../results/plan_r_keys_{yaw:.0f}_{tx:.3f}.json", "w"), indent=1)


if __name__ == "__main__":
    main(float(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3]))
