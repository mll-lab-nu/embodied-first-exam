"""Right arm: positions g where the slerp from the regrasp frame (approach a0, rope axis z0) to the feed frame
(approach +y, rope axis -x) is IK-continuous and collision-free (left arm at ready); also checks the straight move
from g to the R2 feed start. Usage: reorient_search.py"""
import sys, json, itertools, numpy as np
sys.path.insert(0, '/workspace/yamlab_port/runs/rope_threading/task/tools')
from multiprocessing import Pool
import plan_np as PN, yam_kin as K
from scipy.spatial.transform import Rotation as Rot, Slerp
meta = json.load(open('/workspace/yamlab_port/runs/rope_threading/yamlab/yamlab/envs/tasks/rope_threading_lib/assets/easy/rope_meta.json'))
FIX = PN.fixture_capsules(meta['rings'])
QL = PN.solve("left", PN.frame((0.7071, 0, -0.7071), (0, 1, 0), (0.40, 0.30, 0.95)), margin=0.03)
EX, EY = PN.EX, PN.EY
a0 = np.array([-0.11, 0.84, -0.54]); z0 = np.array([0.07, -0.54, -0.84])
F0 = PN.frame_az(a0, z0)[:3, :3]
F1 = PN.frame_az(EY, -EX)[:3, :3]
sl = Slerp([0, 1], Rot.from_matrix(np.stack([F0, F1])))
off = np.array([0.012, 0, 0])


def ok_path(g):
    q = None
    for f in np.linspace(0, 1, 13):
        Rm = sl(f).as_matrix(); T = np.eye(4); T[:3, :3] = Rm; T[:3, 3] = g - Rm @ off
        if q is None:
            q = PN.solve("right", T, margin=0.03)
            if q is None:
                return False
        else:
            qn, o, ep, er = K.ik(K.world_to_base(T, "right"), q, iters=200, margin=0.02)
            if not (o or (ep < 1.5e-3 and er < 3e-2)) or np.abs(qn - q).max() > 0.5:
                return False
            q = qn
        if min(PN.arm_clearance("right", q, FIX, other=("left", QL, True), grip_open=False).values()) < 0.01:
            return False
    return True


def job(g):
    return g, ok_path(np.array(g))


jobs = list(itertools.product((0.50, 0.55, 0.60, 0.65, 0.70), (-0.30, -0.25, -0.20, -0.15, -0.10, -0.05), (0.90, 0.95, 1.00, 1.05)))
with Pool(12) as pool:
    res = pool.map(job, jobs)
for z in (0.90, 0.95, 1.00, 1.05):
    print("z", z)
    for x in (0.50, 0.55, 0.60, 0.65, 0.70):
        print("  x %.2f y -0.30..-0.05:" % x, "".join("Y" if dict(res)[(x, y, z)] else "." for y in (-0.30, -0.25, -0.20, -0.15, -0.10, -0.05)))
