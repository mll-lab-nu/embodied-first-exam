import sys; import os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from yam_kin import *
rng=np.random.default_rng(0)
seeds = [rng.uniform(LOWER, UPPER) for _ in range(30)]
def R_pitch(a_deg, sign):
    a=np.radians(a_deg); z=np.array([np.sin(a),0,-np.cos(a)]); x=sign*np.array([np.cos(a),0,np.sin(a)]); return np.column_stack([x,np.cross(z,x),z])
for X0 in (0.42, 0.48, 0.54):
  for a in (20, 40, 60, 90):
    fails=[]; qs=[]
    for dx in (-0.07,0,0.07):
      for y in (0.13,0.24,0.36):
        Td=np.eye(4); Td[:3,3]=[X0+dx,y,0.9917]
        best=None
        for sign in (1,-1):
          Td[:3,:3]=R_pitch(a,sign)
          r=min((ik(Td,s) for s in seeds),key=lambda r:r[1]+0.1*r[2])
          if best is None or r[1]+0.1*r[2]<best[1]+0.1*best[2]: best=r
        if best[1]>1e-4 or best[2]>1e-3: fails.append((dx,y,round(best[1]*1000,1)))
        qs.append(best[0])
    print(f"X0={X0} pitch={a}: fails {fails}  j4 range {np.min(qs,0)[3]:.2f}..{np.max(qs,0)[3]:.2f}")
