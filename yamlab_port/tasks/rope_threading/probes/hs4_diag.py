import sys, json, numpy as np
sys.path.insert(0, '/workspace/yamlab_port/runs/rope_threading/task/tools')
import plan_np as PN
meta = json.load(open('/workspace/yamlab_port/runs/rope_threading/yamlab/yamlab/envs/tasks/rope_threading_lib/assets/easy/rope_meta.json'))
FIX = PN.fixture_capsules(meta['rings'])
READY_R = PN.solve("right", PN.frame((0.7071, 0, -0.7071), (0, 1, 0), (0.40, -0.30, 0.95)), margin=0.03)
EX, EZ = PN.EX, PN.EZ
print("ready_r", READY_R)
for G in ((0.55, 0.10, 0.83), (0.60, 0.05, 0.83), (0.55, 0.20, 0.83)):
    G = np.array(G)
    for zl in (1, -1):
        TL = PN.frame_az(-EZ, zl * EX, G + 0.035 * EZ); qL = PN.solve("left", TL)
        print("G", G, "zl", zl, "left q", None if qL is None else np.round(qL, 2),
              None if qL is None else {k: round(v, 3) for k, v in PN.arm_clearance("left", qL, FIX, other=("right", READY_R, True), grip_open=False).items()})
    for ft in (0.03,):
        pt = G - (0.18 - ft) * EX - 0.008 * EZ
        for zr in (1, -1):
            T = PN.frame_az(-EZ, zr * EX, pt + 0.012 * EZ)
            q = PN.solve("right", T)
            print("   right at", np.round(pt, 3), "zr", zr, "q", None if q is None else np.round(q, 2),
                  None if q is None else {k: round(v, 3) for k, v in PN.arm_clearance("right", q, FIX, grip_open=False).items()}, "finger_low", round(PN.finger_low_z(T), 3))
