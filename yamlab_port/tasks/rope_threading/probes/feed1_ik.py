import sys, numpy as np
sys.path.insert(0, '/workspace/yamlab_port/runs/rope_threading/task/tools')
import yam_kin as K
from reach_map import seeds_for, frame
R1c = np.array([0.599, 0.075, 1.0819])
def frame_az(a, z, pos):
    a = np.asarray(a, float); a /= np.linalg.norm(a); z = np.asarray(z, float); z = z - a*(a@z); z /= np.linalg.norm(z)
    return frame(a, np.cross(z, a)) if pos is None else (lambda T: (T.__setitem__((slice(0,3),3), pos), T)[1])(frame(a, np.cross(z, a)))
def ok(side, T, margin=0.05):
    Tb = K.world_to_base(T, side)
    for s in seeds_for(Tb[:3,3]):
        q, o, ep, er = K.ik(Tb, s, iters=200, margin=margin)
        if o: return np.round(q,2)
    return None
for zs in (1,-1):
  for pitch in (0, 30, 45, 60):
    pr = np.radians(pitch); a = np.array([np.cos(pr),0,-np.sin(pr)])
    res = []
    for dy in (0.30, 0.20, 0.10, 0.065):
      gp = R1c + [0, dy, -0.01]
      T = frame_az(a, zs*np.array([0,-1.0,0]), gp - 0.035*a)
      q = ok('left', T)
      res.append('Y' if q is not None else '.')
    print('zs', zs, 'pitch', pitch, ''.join(res))
