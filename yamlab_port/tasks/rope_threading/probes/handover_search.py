"""Offline search of (handover position for the left pinch, right support grasp). The logged rope (at the left's
handover pose) is translated rigidly with the left grasp. Usage: handover_search.py <run> <step> [depth]"""
import sys, itertools, numpy as np
sys.path.insert(0, '/workspace/yamlab_port/runs/rope_threading/task/tools')
from multiprocessing import Pool
import yam_kin as K
import plan_np as PN
run, step = sys.argv[1], int(sys.argv[2])
depth = float(sys.argv[3]) if len(sys.argv) > 3 else 0.012
S = np.load(f"{run}/states.npz"); P0 = S["rope_pos"][step].astype(float); Q = S["q"][step].astype(float)
TL0 = K.base_to_world(K.fk_tcp(Q[0:6]), "left")
gp0, _ = PN.polyline_station(P0, 0.15)


def job(args):
    hx, hy, hz = args
    d = np.array([hx, hy, hz]) - gp0
    TL = TL0.copy(); TL[:3, 3] += d
    if PN.solve("left", TL) is None:
        return args, None
    P = P0 + d
    out = []
    for ft in list(np.arange(0.0, 0.07, 0.02)) + list(np.arange(0.24, 0.42, 0.04)):
        pt, t = PN.polyline_station(P, ft)
        for name, a in PN.APPROACHES.items():
            if abs(a @ t) > 0.5:
                continue
            for zs in (1, -1):
                T = PN.grip_T(a, zs * t, pt, np.array([depth, 0, 0]))
                Tpre = T.copy(); Tpre[:3, 3] -= 0.09 * T[:3, 0]
                if PN.finger_low_z(T) < PN.TABLE + 0.015:
                    continue
                cl = min(PN.gripper_clearance(T, TL), PN.gripper_clearance(Tpre, TL))
                if cl < 0.03:
                    continue
                if PN.solve("right", T) is not None and PN.solve("right", Tpre) is not None:
                    out.append(f"{ft:.2f}:{name}{'+' if zs > 0 else '-'}")
    return args, out


jobs = list(itertools.product((0.45, 0.50, 0.55, 0.60), (-0.05, 0.0, 0.05, 0.10), (0.88, 0.93)))
with Pool(12) as pool:
    for args, out in pool.imap(job, jobs):
        print(args, "left unreachable" if out is None else (" ".join(out) or "-")); sys.stdout.flush()
