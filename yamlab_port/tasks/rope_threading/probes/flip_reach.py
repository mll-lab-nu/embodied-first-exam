"""Left arm: grip point g, rope along +y (tip +y), approach a1 = +x pitched p. Rotate 180 deg about the approach
axis (tip -> -y) in 10 deg steps with IK continuity (each seeded by the previous); report where it is feasible and
collision-free, for both rotation senses."""
import sys, json, numpy as np
sys.path.insert(0, '/workspace/yamlab_port/runs/rope_threading/task/tools')
import plan_np as PN, yam_kin as K
from scipy.spatial.transform import Rotation as Rot
meta = json.load(open('/workspace/yamlab_port/runs/rope_threading/yamlab/yamlab/envs/tasks/rope_threading_lib/assets/easy/rope_meta.json'))
FIX = PN.fixture_capsules(meta['rings'])
EX, EY, EZ = PN.EX, PN.EY, PN.EZ
for p in (30, 45):
    a1 = PN.pitched(EX, p)
    for z in (0.85, 0.95, 1.05):
        for x in (0.50, 0.55, 0.60):
            res = ""
            for y in (0.30, 0.38, 0.46):
                g = np.array([x, y, z])
                T0 = PN.frame_az(a1, EY); T0[:3, 3] = g - 0.012 * a1
                best = "."
                for sense in (1, -1):
                    q = PN.solve("left", T0, margin=0.03)
                    ok = q is not None
                    for k in range(1, 19):
                        if not ok: break
                        Rm = Rot.from_rotvec(a1 * sense * np.radians(10 * k)).as_matrix()
                        T = np.eye(4); T[:3, :3] = Rm @ T0[:3, :3]; T[:3, 3] = g - 0.012 * (Rm @ T0[:3, :3])[:, 0]
                        qn, o, ep, er = K.ik(K.world_to_base(T, "left"), q, iters=200, margin=0.02)
                        if not o or np.abs(qn - q).max() > 0.5 or min(PN.arm_clearance("left", qn, FIX).values()) < 0.005:
                            ok = False; break
                        q = qn
                    if ok:
                        best = "+" if sense > 0 else "-"; break
                res += best
            print(f"pitch {p} z {z:.2f} x {x:.2f}: y 0.30/0.38/0.46 -> {res}"); sys.stdout.flush()
