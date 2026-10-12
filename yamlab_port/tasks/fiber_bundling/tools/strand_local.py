"""Strand shape in the trunk_05 frame over time (detects joint motion of the strands) + contacts proxy."""
import sys, json, numpy as np
S = dict(np.load(sys.argv[1]+"/states.npz", allow_pickle=True))
names = list(S["link_names"]); L = S["links"]; ph = S["phase"]
def R(q):
    w, x, y, z = q
    return np.array([[1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)], [2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x)], [2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)]])
i5 = names.index("trunk_05"); tips = [names.index("fiber_00_09"), names.index("fiber_01_09")]
a, b = int(sys.argv[2]), int(sys.argv[3]); st = int(sys.argv[4]) if len(sys.argv) > 4 else 10
for k in range(a, b, st):
    R5 = R(L[k, i5, 3:].astype(float)); p5 = L[k, i5, :3].astype(float)
    loc = [np.round((L[k, t, :3]-p5) @ R5 * 1000, 1) for t in tips]
    w = np.linalg.norm(np.diff(L[max(k-1,0):k+1, i5, :3], axis=0))*30*1000 if k else 0
    sn = S["strand_net"][k] if "strand_net" in S else float("nan")
    print(k, ph[k], f"strand net contact {sn:.2e} N", "tip0 local", loc[0], "tip1 local", loc[1], f"t5 speed {w:.1f} mm/s")
