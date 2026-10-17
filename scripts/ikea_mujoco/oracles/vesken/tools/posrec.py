"""The unclamped reference run of the demo (ref/pos_free.npz): every part pose (pos + quat) and both TCPs every 20 rows.
usage: posrec.py demo.npz out.npz   (about 10 min; IKEA_SCENES with the vesken scene)"""
import sys, numpy as np, rcb_ikea as R
demo, outp = sys.argv[1:3]
c = np.ascontiguousarray(np.load(demo)['ctrl'], dtype=np.float64)
s = R.Session('vesken'); s.applied = lambda a: np.clip(a, s._clo, s._chi)        # the demo as recorded (no clamp)
m, d = s.model, s.data; parts = s.S.task['parts']; bid = [m.body(n).id for n in parts]
tcp = [m.site('left_tcp').id, m.site('right_tcp').id]
P, T, I = [], [], []
for i, row in enumerate(c):
    if i % 20 == 0:
        P.append(np.c_[d.xpos[bid], d.xquat[bid]].copy()); T.append(d.site_xpos[tcp].copy()); I.append(i)
    s.step(row)
np.savez_compressed(outp, pose=np.array(P), tcp=np.array(T), i=np.array(I), parts=np.array(parts))
