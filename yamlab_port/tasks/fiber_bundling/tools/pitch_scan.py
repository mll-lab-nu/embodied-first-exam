"""Pick the grasp tool pitch with the best joint-limit margin over the oracle workspace (numpy only)."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from yam_kin import *
lay = json.load(open(sys.argv[1]))
c = np.array(lay["ring"]["center"]); n = np.array(lay["ring"]["normal"])
rng = np.random.default_rng(0); seeds = [rng.uniform(LOWER, UPPER) for _ in range(40)]
def R_pitch(a_deg, sign):
    a=np.radians(a_deg); z=np.array([np.sin(a),0,-np.cos(a)]); x=sign*np.array([np.cos(a),0,np.sin(a)]); return np.column_stack([x,np.cross(z,x),z])
D = 0.066
for a in (30, 45, 60, 75, 90):
  for sign in (1, -1):
    margins=[]; bad=0
    for s_face in (-0.110, -0.069, 0.022):       # park, comb approach, final
      for off in (-0.062, 0.0, 0.062):
        p = c + n*(s_face-D) + np.array([off, 0, 0])
        Td=np.eye(4); Td[:3,:3]=R_pitch(a,sign); Td[:3,3]=p
        r=min((ik(Td,s) for s in seeds), key=lambda r:r[1]+0.1*r[2])
        if r[1]>1e-4 or r[2]>1e-3: bad+=1; continue
        margins.append(np.min(np.minimum(r[0]-LOWER, UPPER-r[0])[[0,3,4,5]]))
    print(f"pitch {a} sign {sign:+d}: unreachable {bad}/9, min joint margin (j1,j4-6) {np.degrees(min(margins)) if margins else float('nan'):.1f} deg")
