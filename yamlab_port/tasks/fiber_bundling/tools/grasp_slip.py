"""Grasp relation over time: trunk_05 pose in the link_6 frame, hand path, finger opening."""
import sys, numpy as np
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import yam_kin as K
S = dict(np.load(sys.argv[1]+"/states.npz", allow_pickle=True))
names = list(S["link_names"]); i5 = names.index("trunk_05"); i4 = names.index("trunk_04")
H = S["hand"]; Lk = S["links"]; q = S["q"]; ph = S["phase"]; A = S["action"]
def T(p, qq):
    w, x, y, z = qq
    R = np.array([[1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)], [2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x)], [2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)]])
    M = np.eye(4); M[:3, :3] = R; M[:3, 3] = p; return M
step = int(sys.argv[2]) if len(sys.argv) > 2 else 25
for k in range(0, len(ph), step):
    X = np.linalg.inv(H[k]) @ T(Lk[k, i5, :3], Lk[k, i5, 3:])
    Tc = K.fk_all(A[k, :6].astype(float))[-1]
    print(f"{k:5d} {ph[k]:7s} hand {np.round(H[k][:3,3],4)} cmd-err {np.linalg.norm(Tc[:3,3]-H[k][:3,3])*1000:6.1f}mm  X.t {np.round(X[:3,3]*1000,1)} "
          f"t5 {np.round(Lk[k,i5,:3],4)} t4 {np.round(Lk[k,i4,:3],4)} grip q {q[k,6]:.4f} cmd {A[k,6]:.4f}")
