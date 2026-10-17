"""Annotate a ctrl file: every 20 rows log tcp pos, grip ctrl/width, part held per hand, op metrics; engagement rows.
mode 'free' = no clamp (original physics of the demo), 'clamp' = Session clamp."""
import json, sys, time, pickle, numpy as np, mujoco, rcb_ikea as R
src, mode, out = sys.argv[1:4]
c = np.ascontiguousarray(np.load(src)['ctrl'], dtype=np.float64)
if len(sys.argv) > 4: c = c[:int(sys.argv[4])]
s = R.Session('vesken')
if mode == 'free':
    s.applied = lambda a: np.clip(a, s._clo, s._chi)
m, d = s.model, s.data; mech = s.S.mech
tcp = [m.site('left_tcp').id, m.site('right_tcp').id]
parts = s.S.task['parts']; pid = {m.body(p).id: p for p in parts}
hand = [set(b for b in range(m.nbody) if m.body(b).name.startswith(('left_hand', 'left_left_finger', 'left_right_finger', 'left_finger'))),
        set(b for b in range(m.nbody) if m.body(b).name.startswith(('right_hand', 'right_left_finger', 'right_right_finger', 'right_finger')))]
print([sorted(m.body(b).name for b in h) for h in hand])
gb = m.geom_bodyid
rec = []; eng = {}; ck = {}
t = time.time()
for i, row in enumerate(c):
    s.step(row)
    if i % 20 == 0:
        held = [set(), set()]
        for k in range(d.ncon):
            b1, b2 = gb[d.contact.geom1[k]], gb[d.contact.geom2[k]]
            for h in (0, 1):
                if b1 in hand[h] and b2 in pid: held[h].add(pid[b2])
                if b2 in hand[h] and b1 in pid: held[h].add(pid[b1])
        rec.append(dict(i=i, tcp=[d.site_xpos[x].round(4).tolist() for x in tcp], g=[float(d.ctrl[7]), float(d.ctrl[15])],
                        held=[sorted(x) for x in held], q=d.ctrl.round(4).tolist()))
        for k, v in mech.engaged_at.items():
            if k not in eng:
                eng[k] = i; print('engaged', k, i, round(time.time() - t), flush=True)
                if mode == 'free':
                    st = s.get_state(); st['rows'] = None
                    ck[k] = (i, st)
pickle.dump(dict(rec=rec, eng=eng), open(out + '.pkl', 'wb'))
if ck: pickle.dump(ck, open(out + '_ck.pkl', 'wb'))
print('done', time.time() - t)
