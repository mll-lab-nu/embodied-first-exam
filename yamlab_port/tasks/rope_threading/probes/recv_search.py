"""Receiver grasp search on a logged state: arm `side` grasps the rope `dist` past ring `ring` along `axis`; rope along
the local tangent; approach scanned in the plane perpendicular to the tangent (angle phi from +x/up), both rope-axis
signs, pre-grasp 9 cm back along the approach; IK + capsule clearance (fixtures, table, other arm at its logged q).
Usage: recv_search.py run step side ring(R1|R2) axis(-y|-x)"""
import sys, json, numpy as np
sys.path.insert(0, '/workspace/yamlab_port/runs/rope_threading/task/tools')
import plan_np as PN, yam_kin as K
run, step, side, ring, axn = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4], sys.argv[5]
meta = json.load(open('/workspace/yamlab_port/runs/rope_threading/yamlab/yamlab/envs/tasks/rope_threading_lib/assets/easy/rope_meta.json'))
FIX = PN.fixture_capsules(meta['rings'])
rg = [r for r in meta['rings'] if r['name'] == ring][0]
c = np.array(rg['center'])
axis = {"-y": -PN.EY, "-x": -PN.EX}[axn]
S = np.load(f"{run}/states.npz"); P = S["rope_pos"][step].astype(float)[::-1]; Q = S["q"][step].astype(float)
oth = "left" if side == "right" else "right"
qo = Q[0:6] if oth == "left" else Q[7:13]
d = (P - c) @ axis
print("tip axial past plane %.3f" % d[0])
for dist in [float(x) for x in (sys.argv[6].split(",") if len(sys.argv) > 6 else ["0.04", "0.05", "0.06", "0.07"])]:
    i = next((i for i in range(len(P) - 1) if (d[i] - dist) * (d[i + 1] - dist) <= 0), None)
    if i is None:
        print(dist, "no rope point"); continue
    f = (dist - d[i]) / (d[i + 1] - d[i]); pt = P[i] + f * (P[i + 1] - P[i]); t = P[i] - P[i + 1]; t /= np.linalg.norm(t)
    u = np.cross(t, PN.EZ); u /= np.linalg.norm(u); v = np.cross(u, t)
    oks = []
    for phi in range(0, 360, 15):
        a = np.cos(np.radians(phi)) * u + np.sin(np.radians(phi)) * v
        for zs in (1, -1):
            T = PN.grip_T(a, zs * t, pt, np.array([0.012, 0, 0]))
            Tpre = T.copy(); Tpre[:3, 3] -= 0.09 * a
            q = PN.solve(side, T, margin=0.03)
            if q is None: continue
            qp = PN.solve(side, Tpre, q_seed=q, margin=0.03)
            if qp is None: continue
            c1 = min(PN.arm_clearance(side, q, FIX, other=(oth, qo, False), grip_open=False).values())
            c2 = min(PN.arm_clearance(side, qp, FIX, other=(oth, qo, False)).values())
            if min(c1, c2) > 0.005:
                oks.append(f"phi{phi}a{np.round(a,2).tolist()}{'+' if zs>0 else '-'}")
    print(f"dist {dist}: pt {np.round(pt,3)} t {np.round(t,2)} ->", " | ".join(oks) or "-"); sys.stdout.flush()
