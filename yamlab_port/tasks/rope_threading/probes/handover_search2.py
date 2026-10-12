"""Handover search with arm/fixture collisions: left (pinch, gripper down) at H, right support grasp on the rope
(logged rope translated rigidly with the left grasp). Usage: handover_search2.py <run> <step>"""
import sys, itertools, json, numpy as np
sys.path.insert(0, '/workspace/yamlab_port/runs/rope_threading/task/tools')
from multiprocessing import Pool
import yam_kin as K
import plan_np as PN
run, step = sys.argv[1], int(sys.argv[2])
meta = json.load(open('/workspace/yamlab_port/runs/rope_threading/yamlab/yamlab/envs/tasks/rope_threading_lib/assets/easy/rope_meta.json'))
FIX = PN.fixture_capsules(meta['rings'])
S = np.load(f"{run}/states.npz"); P0 = S["rope_pos"][step].astype(float); Q = S["q"][step].astype(float)
TL0 = K.base_to_world(K.fk_tcp(Q[0:6]), "left")
gp0, _ = PN.polyline_station(P0, 0.15)
QH = np.zeros(6)


def ok_pose(side, T, other, grip_open):
    q = PN.solve(side, T)
    if q is None:
        return None
    c = PN.arm_clearance(side, q, FIX, other=other, grip_open=grip_open)
    return q if min(c.values()) > 0.015 else None


def job(args):
    hx, hy, hz = args
    d = np.array([hx, hy, hz]) - gp0
    TL = TL0.copy(); TL[:3, 3] += d
    qL = ok_pose("left", TL, ("right", QH, True), False)
    if qL is None:
        return args, None
    P = P0 + d
    out = []
    for ft in list(np.arange(0.0, 0.07, 0.02)) + list(np.arange(0.24, 0.42, 0.04)):
        pt, t = PN.polyline_station(P, ft)
        for name, a in PN.APPROACHES.items():
            if abs(a @ t) > 0.5:
                continue
            for zs in (1, -1):
                T = PN.grip_T(a, zs * t, pt, np.array([0.012, 0, 0]))
                Tpre = T.copy(); Tpre[:3, 3] -= 0.09 * T[:3, 0]
                if PN.finger_low_z(T) < PN.TABLE + 0.015:
                    continue
                if ok_pose("right", T, ("left", qL, False), True) is not None and ok_pose("right", Tpre, ("left", qL, False), True) is not None:
                    out.append(f"{ft:.2f}:{name}{'+' if zs > 0 else '-'}")
    return args, out


jobs = list(itertools.product((0.33, 0.36, 0.39, 0.42), (-0.05, 0.0, 0.05, 0.10, 0.15, 0.20), (0.84, 0.88)))
with Pool(12) as pool:
    for args, out in pool.imap(job, jobs):
        if out:
            print(args, " ".join(out)); sys.stdout.flush()
        elif out is None:
            print(args, "left blocked/unreachable"); sys.stdout.flush()
print("DONE")
