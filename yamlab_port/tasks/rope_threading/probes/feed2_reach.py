"""Right arm holding the rope along x (tip toward -x) at grip point g near R2, approach sideways +y pitched p,
rope-axis sign zs (z_tcp = zs * -x): IK + capsule clearance (fixtures, table, left arm at ready)."""
import sys, json, numpy as np
sys.path.insert(0, '/workspace/yamlab_port/runs/rope_threading/task/tools')
import plan_np as PN
meta = json.load(open('/workspace/yamlab_port/runs/rope_threading/yamlab/yamlab/envs/tasks/rope_threading_lib/assets/easy/rope_meta.json'))
FIX = PN.fixture_capsules(meta['rings'])
QL = PN.solve("left", PN.frame((0.7071, 0, -0.7071), (0, 1, 0), (0.40, 0.30, 0.95)), margin=0.03)
EX, EY = PN.EX, PN.EY
c2 = np.array([0.46, -0.025, 1.0609])
for zs in (1, -1):
    for p in (0, 15, 30, 45, 60):
        a = PN.pitched(EY, p)
        row = []
        for gx in (0.50, 0.52, 0.55, 0.60, 0.65, 0.70):
            for dz in (-0.03, 0.0):
                g = c2 + np.array([gx - 0.46, 0, dz])
                T = PN.grip_T(a, zs * -EX, g, np.array([0.012, 0, 0]))
                q = PN.solve("right", T, margin=0.03)
                if q is None:
                    row.append("."); continue
                cl = PN.arm_clearance("right", q, FIX, other=("left", QL, True), grip_open=False)
                row.append("%d" % min(9, max(0, int(min(cl.values()) * 100))) if min(cl.values()) > 0 else "x")
        print(f"zs {zs:+d} pitch {p:2d}: gx 0.50/.52/.55/.60/.65/.70 x dz(-3,0) ->", " ".join(row))
