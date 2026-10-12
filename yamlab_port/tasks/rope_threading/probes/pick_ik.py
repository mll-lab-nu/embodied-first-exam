import sys, numpy as np
sys.path.insert(0, '/workspace/yamlab_port/runs/rope_threading/task/tools')
import yam_kin as K
from reach_map import seeds_for
from rt_common import frame_az
for x in (0.60, 0.64, 0.68):
  for zsign in (1, -1):
    for zt in (0.789, 0.80, 0.869):
      T = frame_az([0,0,-1], [zsign,0,0], [x, 0.33, zt]); Tb = K.world_to_base(T, 'left')
      res = [K.ik(Tb, s, iters=300, margin=0.03) for s in seeds_for(Tb[:3,3])]
      ok = [r for r in res if r[1]]
      best = min(res, key=lambda r: r[2])
      print(x, zsign, zt, 'ok', len(ok), 'best ep %.4f er %.4f'%(best[2], best[3]), np.round(best[0],2))
