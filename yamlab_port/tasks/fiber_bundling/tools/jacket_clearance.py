"""Jacket-ring clearance during the run: for every trunk link crossing the ring plane, the radial offset of
the jacket axis at the plane and the remaining radial gap to the polygonal aperture (13.479 mm)."""
import json, sys, numpy as np
S = dict(np.load(sys.argv[1]+"/states.npz", allow_pickle=True)); lay = json.load(open(sys.argv[2]))
LK = S["links"]; names = list(S["link_names"]); c = np.array(lay["ring"]["center"]); n = np.array(lay["ring"]["normal"])
ap = lay["ring"]["min_aperture_radius"]; r = lay["trunk"]["radius"]
def R(q):
    w, x, y, z = q
    return np.array([[1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)], [2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x)], [2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)]])
worst = (np.inf, None)
for k in range(len(LK)):
    for nm in lay["trunk"]["names"]:
        i = names.index(nm); p = LK[k, i, :3].astype(float); a = R(LK[k, i, 3:].astype(float))[:, 0]
        L = lay["links"][nm]["length"]; d0 = (p-c) @ n; d1 = (p+a*L-c) @ n
        if d0 <= 0 <= d1 and d1 > d0:
            t = -d0/(d1-d0); x = p+a*L*t-c; off = np.linalg.norm(x-(x @ n)*n)
            gap = ap-r-off
            if gap < worst[0]: worst = (gap, (k, nm, off))
print(f"min radial jacket gap at the ring plane {worst[0]*1000:.3f} mm (nominal {1000*(ap-r):.3f} mm); step/link/axis offset {worst[1]}")
