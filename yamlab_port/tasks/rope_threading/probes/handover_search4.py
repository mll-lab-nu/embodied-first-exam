"""Low handover: left top-down pinch at grip G (rope along x, tip toward -x, GF from tip); right top-down deep grasp
(rope 12 mm inside the pads) at `ft` from the tip, i.e. at G - (GF - ft) x with a small droop. Checks reach, capsule
clearances (fixtures, table, arms) and the right's joint path from its ready pose. Usage: handover_search4.py GF"""
import sys, itertools, json, numpy as np
sys.path.insert(0, '/workspace/yamlab_port/runs/rope_threading/task/tools')
from multiprocessing import Pool
import plan_np as PN
meta = json.load(open('/workspace/yamlab_port/runs/rope_threading/yamlab/yamlab/envs/tasks/rope_threading_lib/assets/easy/rope_meta.json'))
FIX = PN.fixture_capsules(meta['rings'])
READY_R = PN.solve("right", PN.frame((0.7071, 0, -0.7071), (0, 1, 0), (0.40, -0.30, 0.95)), margin=0.03)
EX, EZ = PN.EX, PN.EZ
GF = float(sys.argv[1]) if len(sys.argv) > 1 else 0.18


def path_ok(qa, qb, other):
    for f in np.linspace(0.1, 1.0, 10):
        if min(PN.arm_clearance("right", qa + (0.5 - 0.5 * np.cos(np.pi * f)) * (qb - qa), FIX, other=other).values()) < 0.008:
            return False
    return True


TIPDIRS = {"-x": -EX, "-y": -PN.EY, "+x": EX}


def job(args):
    G, tdn = args
    G = np.asarray(G, float)
    td = TIPDIRS[tdn]
    best = None
    for zl in (1, -1):
        TL = PN.frame_az(-EZ, zl * td, G + 0.035 * EZ)
        qL = PN.solve("left", TL)
        if qL is None or min(PN.arm_clearance("left", qL, FIX, other=("right", READY_R, True), grip_open=False).values()) < 0.01:
            continue
        out = []
        for ft in (0.03, 0.05):
            pt = G + (GF - ft) * td - 0.008 * EZ
            for zr in (1, -1):
                T = PN.frame_az(-EZ, zr * td, pt + 0.012 * EZ)
                Tpre = T.copy(); Tpre[:3, 3] += 0.06 * EZ
                oth = ("left", qL, False)
                q = PN.solve("right", T); qp = PN.solve("right", Tpre, q_seed=q) if q is not None else None
                if q is None or qp is None:
                    continue
                c1 = min(PN.arm_clearance("right", q, FIX, other=oth, grip_open=False).values())
                c2 = min(PN.arm_clearance("right", qp, FIX, other=oth).values())
                if c1 < 0.005 or c2 < 0.005 or PN.finger_low_z(T) < PN.TABLE + 0.012:
                    continue
                if path_ok(READY_R, qp, oth):
                    out.append(f"L{zl:+d}:ft{ft:.2f}:R{zr:+d}(cl {min(c1,c2)*100:.1f}cm)")
        if out:
            best = out
    return (tuple(G), tdn), best


jobs = [((x, y, z), td) for x in (0.36, 0.40, 0.44) for y in (0.10, 0.15, 0.20, 0.25, 0.30) for z in (0.81, 0.83)
        for td in ("-x", "-y", "+x")]
with Pool(12) as pool:
    for G, out in pool.imap(job, jobs):
        print(G, out if out else "-"); sys.stdout.flush()
print("DONE")
