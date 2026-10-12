"""Offline search of a support grasp for one arm on a logged rope state.
Usage: support_search.py <run> <step> <side> [depth]"""
import sys, numpy as np
sys.path.insert(0, '/workspace/yamlab_port/runs/rope_threading/task/tools')
import yam_kin as K
import plan_np as PN
run, step, side = sys.argv[1], int(sys.argv[2]), sys.argv[3]
depth = float(sys.argv[4]) if len(sys.argv) > 4 else 0.012
S = np.load(f"{run}/states.npz"); Pl = S["rope_pos"][step].astype(float); Q = S["q"][step].astype(float)
# centreline ~ link centres (good enough for planning) with the end points extrapolated
P = Pl
oth = "left" if side == "right" else "right"
To = K.base_to_world(K.fk_tcp(Q[0:6] if oth == "left" else Q[7:13]), oth)
print("other TCP", np.round(To[:3, 3], 3), "approach", np.round(To[:3, 0], 2))
for ft in np.arange(0.0, 0.50, 0.02):
    pt, t = PN.polyline_station(P, ft)
    oks = []
    for name, a in PN.APPROACHES.items():
        if abs(a @ t) > 0.5:
            continue
        for zs in (1, -1):
            T = PN.grip_T(a, zs * t, pt, np.array([depth, 0, 0]))
            Tpre = T.copy(); Tpre[:3, 3] -= 0.09 * T[:3, 0]
            fl = PN.finger_low_z(T)
            cl = min(PN.gripper_clearance(T, To), PN.gripper_clearance(Tpre, To))
            if fl < PN.TABLE + 0.015 or cl < 0.03:
                continue
            if PN.solve(side, T) is not None and PN.solve(side, Tpre) is not None:
                oks.append(f"{name}{'+' if zs > 0 else '-'}(cl{cl*100:.0f})")
    print(f"from_tip {ft:.2f} pt {np.round(pt,3)} t {np.round(t,2)} :", " ".join(oks) or "-")
    sys.stdout.flush()
