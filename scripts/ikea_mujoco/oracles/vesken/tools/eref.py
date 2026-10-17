"""The unclamped reference run of the demo: the connector error vector (world, mean over the connectors, as
vesken_oracle.Runner.conn_error) of the active operation (the first not welded) every 20 rows -> eref_free.pkl.
usage: eref.py demo.npz out.pkl"""
import sys, pickle, numpy as np, rcb_ikea as R
from ikea_runtime import rotate
demo, outp = sys.argv[1:3]
c = np.ascontiguousarray(np.load(demo)['ctrl'], dtype=np.float64)
s = R.Session('vesken'); s.applied = lambda a: np.clip(a, s._clo, s._chi)
mech, d = s.S.mech, s.data; ops = s.S.task['operations']
def conn_error(o):
    P = o['part']; pp = d.xpos[mech.bid[P]]; qp = d.xquat[mech.bid[P]]; qh = d.xquat[mech.bid[o['host']]]
    out = rotate(qh, o['outward']); errs = []
    for cn in o['connectors']:
        r = cn['receiver']; pt = np.asarray(cn['point'], float)
        errs.append(pp + rotate(qp, pt - mech.c[P]) - (d.xpos[mech.bid[r]] + rotate(d.xquat[mech.bid[r]], pt - mech.c[r])))
    return np.mean(errs, axis=0), out
ser = {o['key']: [] for o in ops}; k = 0
for i, row in enumerate(c):
    s.step(row)
    if i % 20: continue
    while k < len(ops) and mech.connected(ops[k]['key']): k += 1
    if k < len(ops):
        e, out = conn_error(ops[k]); ser[ops[k]['key']].append((i, e.tolist(), out.tolist()))
pickle.dump(dict(ser=ser), open(outp, 'wb'))
