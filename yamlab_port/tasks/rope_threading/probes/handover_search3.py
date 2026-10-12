"""Handover after the yaw: left top-down pinch at grip point H with the rope along y, tip side toward -y (0.15 m,
straight, 1 cm droop at the tip). Right: deep grasp at 0.02-0.06 m from the tip; its pre-grasp (9 cm back along the
approach) and the joint path from its ready pose must be collision-free (capsule model; left at H, closed).
Usage: handover_search3.py"""
import sys, itertools, json, numpy as np
sys.path.insert(0, '/workspace/yamlab_port/runs/rope_threading/task/tools')
from multiprocessing import Pool
import yam_kin as K
import plan_np as PN
meta = json.load(open('/workspace/yamlab_port/runs/rope_threading/yamlab/yamlab/envs/tasks/rope_threading_lib/assets/easy/rope_meta.json'))
FIX = PN.fixture_capsules(meta['rings'])
READY_R = PN.solve("right", PN.frame((0.7071, 0, -0.7071), (0, 1, 0), (0.40, -0.30, 0.95)), margin=0.03)
EY, EZ = PN.EY, PN.EZ


def path_ok(side, qa, qb, other):
    for f in np.linspace(0.1, 1.0, 10):
        if min(PN.arm_clearance(side, qa + (0.5 - 0.5 * np.cos(np.pi * f)) * (qb - qa), FIX, other=other).values()) < 0.01:
            return False
    return True


def job(H):
    H = np.asarray(H, float)
    TL = PN.frame_az(-EZ, EY, H + 0.035 * EZ)          # rope along y, grip point 3.5 cm below the TCP
    qL = PN.solve("left", TL)
    if qL is None or min(PN.arm_clearance("left", qL, FIX, other=("right", READY_R, True), grip_open=False).values()) < 0.015:
        return tuple(H), None
    out = []
    for ft in (0.02, 0.04, 0.06):
        s = 0.15 - ft
        pt = H - s * EY - 0.01 * (s / 0.15) ** 2 * EZ
        for name, a in PN.APPROACHES.items():
            if abs(a @ EY) > 0.3:
                continue
            for zs in (1, -1):
                T = PN.grip_T(a, zs * EY, pt, np.array([0.012, 0, 0]))
                Tpre = T.copy(); Tpre[:3, 3] -= 0.09 * T[:3, 0]
                if PN.finger_low_z(T) < PN.TABLE + 0.015:
                    continue
                oth = ("left", qL, False)
                q = PN.solve("right", T); qp = PN.solve("right", Tpre, q_seed=q) if q is not None else None
                if q is None or qp is None:
                    continue
                if min(PN.arm_clearance("right", q, FIX, other=oth).values()) < 0.01 or min(PN.arm_clearance("right", qp, FIX, other=oth).values()) < 0.01:
                    continue
                if not path_ok("right", READY_R, qp, oth):
                    continue
                out.append(f"{ft:.2f}:{name}{'+' if zs > 0 else '-'}")
    return tuple(H), out


jobs = list(itertools.product((0.40, 0.45, 0.50, 0.55, 0.60, 0.65), (0.10, 0.15, 0.20, 0.25, 0.30), (0.84, 0.88)))
with Pool(12) as pool:
    for H, out in pool.imap(job, jobs):
        print(np.round(H, 2), "left blocked/unreachable" if out is None else (" ".join(out) or "-")); sys.stdout.flush()
print("DONE")
