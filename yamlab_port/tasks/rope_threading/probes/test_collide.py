import sys, json, numpy as np
sys.path.insert(0, '/workspace/yamlab_port/runs/rope_threading/task/tools')
import plan_np as PN, yam_kin as K
meta = json.load(open('/workspace/yamlab_port/runs/rope_threading/yamlab/yamlab/envs/tasks/rope_threading_lib/assets/easy/rope_meta.json'))
fix = PN.fixture_capsules(meta['rings'])
S = np.load(sys.argv[1]); Q = S['q']; A = S['actions']
for k in range(int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])):
    cl = PN.arm_clearance('left', A[k][0:6], fix, other=('right', A[k][7:13]))
    print(k, {kk: round(v, 3) for kk, v in cl.items()}, 'left j1 err %.3f' % (A[k][0] - Q[k][0]))
