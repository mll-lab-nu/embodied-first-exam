import sys, json, numpy as np
sys.path.insert(0, '/workspace/yamlab_port/runs/rope_threading/task/tools')
import plan_np as PN, yam_kin as K
meta = json.load(open('/workspace/yamlab_port/runs/rope_threading/yamlab/yamlab/envs/tasks/rope_threading_lib/assets/easy/rope_meta.json'))
FIX = PN.fixture_capsules(meta['rings'])
for side, sg in (("right", -1), ("left", 1)):
    for x, y, z in ((0.38, 0.22, 0.93), (0.35, 0.25, 0.95), (0.40, 0.30, 0.95), (0.35, 0.30, 1.00), (0.45, 0.30, 0.90)):
        for a, jh in (((1, 0, 0), (0, 0, 1)), ((1, 0, 0), (0, 1, 0)), ((0.7, 0, -0.7), (0, 1, 0)), ((0, 0, -1), (0, 1, 0))):
            T = PN.frame(a, jh, (x, sg * y, z))
            q = PN.solve(side, T, margin=0.03)
            if q is None:
                print(side, (x, y, z), a, jh, "no IK"); continue
            c = PN.arm_clearance(side, q, FIX, other=("left" if side == "right" else "right", np.zeros(6), True))
            okpath = all(min(PN.arm_clearance(side, f * q, FIX, other=("left" if side == "right" else "right", np.zeros(6), True)).values()) > 0.004 for f in np.linspace(0.1, 1, 10))
            print(side, (x, y, z), a, jh, {k: round(v, 3) for k, v in c.items()}, "path_ok", okpath, np.round(q, 2))
