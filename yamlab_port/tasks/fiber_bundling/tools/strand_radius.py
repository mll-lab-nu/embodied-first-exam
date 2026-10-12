"""Per-strand max radius from the trunk_05 axis (and tip ahead of the face) over a step range."""
import sys, json, numpy as np
S = dict(np.load(sys.argv[1]+"/states.npz", allow_pickle=True)); lay = json.load(open(sys.argv[2]))
names = list(S["link_names"]); L = S["links"]; ph = S["phase"]; sn = S.get("strand_net")
def R(q):
    w, x, y, z = q
    return np.array([[1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)], [2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x)], [2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)]])
i5 = names.index("trunk_05"); c = np.array(lay["ring"]["center"]); n = np.array(lay["ring"]["normal"])
a, b, st = int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
for k in range(a, min(b, len(L)), st):
    p5 = L[k, i5, :3].astype(float); ax = R(L[k, i5, 3:].astype(float))[:, 0]; front = p5+ax*0.04
    out = []
    for fs in lay["fibers"]["names"]:
        pts = np.array([L[k, names.index(f), :3] for f in fs], float); v = pts-p5
        out.append(round(float(np.linalg.norm(v-np.outer(v @ ax, ax), axis=1).max())*1000, 1))
    print(k, ph[k], "front ahead", round(float((front-c) @ n)*1000, 1), "strand r", out, "net", None if sn is None else f"{sn[k]:.1e}")
