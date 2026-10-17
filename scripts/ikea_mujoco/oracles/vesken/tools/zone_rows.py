"""Free demo: per op, time series (every 20 rows) of geometry of the active op (the first not engaged) + hand holding + rr contact."""
import sys, pickle, numpy as np, mujoco, vlib
c = np.load('refs/vesken.npz')['ctrl']
s = vlib.session(free=sys.argv[1] == 'free') if len(sys.argv) > 1 else vlib.session(True)
if len(sys.argv) > 2: c = np.load(sys.argv[2])['ctrl']
m, d = s.model, s.data
ops = s.S.task['operations']; mech = s.S.mech
robot = set(R.tolist()) if (R := __import__('rcb_ikea').robot_bodies(m)) is not None else set()
gb = m.geom_bodyid; f6 = np.zeros(6)
ser = {o['key']: [] for o in ops}; rr = []
k = 0
for i, row in enumerate(c):
    s.step(row)
    # robot-robot contacts force max
    best = 0.; pair = None
    for j in range(d.ncon):
        b1, b2 = gb[d.contact.geom1[j]], gb[d.contact.geom2[j]]
        if b1 in robot and b2 in robot:
            mujoco.mj_contactForce(m, d, j, f6)
            if f6[0] > best: best = f6[0]; pair = (m.body(b1).name, m.body(b2).name)
    if best > 50: rr.append((i, best, pair))
    if i % 20: continue
    while k < len(ops) and mech.connected(ops[k]['key']): k += 1
    if k >= len(ops): continue
    o = ops[k]
    g, l, a = mech.geometry(o)
    ser[o['key']].append((i, g, l, a, float(d.ctrl[7]), float(d.ctrl[15])))
pickle.dump(dict(ser=ser, rr=rr), open(sys.argv[3] if len(sys.argv) > 3 else 'zone_free.pkl', 'wb'))
print('rr', len(rr), sorted(rr, key=lambda x: -x[1])[:20])
