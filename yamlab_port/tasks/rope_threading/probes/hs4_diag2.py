import sys, json, numpy as np
sys.path.insert(0, '/workspace/yamlab_port/runs/rope_threading/task/tools')
import plan_np as PN
meta = json.load(open('/workspace/yamlab_port/runs/rope_threading/yamlab/yamlab/envs/tasks/rope_threading_lib/assets/easy/rope_meta.json'))
FIX = PN.fixture_capsules(meta['rings'])
READY_R = PN.solve("right", PN.frame((0.7071, 0, -0.7071), (0, 1, 0), (0.40, -0.30, 0.95)), margin=0.03)
EX, EY, EZ = PN.EX, PN.EY, PN.EZ
for G, td in (((0.40, 0.25, 0.83), -EY), ((0.40, 0.20, 0.83), -EY), ((0.36, 0.20, 0.83), EX), ((0.44, 0.30, 0.83), -EY)):
    G = np.array(G)
    for zl in (1, -1):
        qL = PN.solve("left", PN.frame_az(-EZ, zl * td, G + 0.035 * EZ))
        cl = None if qL is None else {k: round(v, 3) for k, v in PN.arm_clearance("left", qL, FIX, other=("right", READY_R, True), grip_open=False).items()}
        print("G", G, "td", td, "zl", zl, "left", None if qL is None else np.round(qL, 2), cl)
        if qL is None: continue
        pt = G + 0.15 * td - 0.008 * EZ
        for zr in (1, -1):
            T = PN.frame_az(-EZ, zr * td, pt + 0.012 * EZ); q = PN.solve("right", T)
            print("    right", np.round(pt, 3), zr, None if q is None else np.round(q, 2),
                  None if q is None else {k: round(v, 3) for k, v in PN.arm_clearance("right", q, FIX, other=("left", qL, False), grip_open=False).items()})
