"""Grasp schedule of the demo (ref/sched.json): per arm, every gripper close -> open interval of the demo ctrl and the
part it carries in the unclamped reference run (pos_free.npz: the part that moves > 1 cm and keeps its distance to the TCP);
the interval that holds an operation's part at its release row H (plan.json) is that part's. Also packs eref_free.npz.
usage: mksched.py demo.npz pos_free.npz eref_free.pkl plan.json out_dir"""
import sys, json, pickle, numpy as np
demo, posf, erefp, planp, out = sys.argv[1:6]
z = np.load(posf); P = z['pose']; T = z['tcp']; parts = list(z['parts'])
c = np.load(demo)['ctrl']; plan = json.load(open(planp))
def events(j):
    g = c[:, j]; ch = np.flatnonzero(np.diff(g) != 0) + 1
    groups = np.split(ch, np.flatnonzero(np.diff(ch) > 5) + 1)
    return [(int(gr[0]), int(gr[-1]), float(g[gr[0] - 1]), float(g[gr[-1]])) for gr in groups if len(gr)]
sched = {}
for arm, j, ti in (('left', 7, 0), ('right', 15, 1)):
    ev = events(j); closes = [e for e in ev if e[3] < e[2] and e[3] < 100]; opens = [e for e in ev if e[3] > e[2]]
    L = []
    for cl in closes:
        op = next((o for o in opens if o[0] > cl[1]), None)
        a = cl[1] // 20 + 5; b = (op[0] // 20 if op else len(P) - 1)
        dp = np.linalg.norm(P[b, :, :3] - P[a, :, :3], axis=1)
        da = np.linalg.norm(P[a, :, :3] - T[a, ti], axis=1); db = np.linalg.norm(P[b, :, :3] - T[b, ti], axis=1)
        cand = [k for k in range(len(parts)) if dp[k] > 0.01 and abs(db[k] - da[k]) < 0.01 and da[k] < 0.25]
        carried = parts[min(cand, key=lambda k: da[k])] if cand else None
        L.append(dict(cs=cl[0], ce=cl[1], os=op[0] if op else len(c), oe=op[1] if op else len(c),
                      part=str(carried or parts[int(np.argmin(da))]), carried=carried is not None))
    sched[arm] = L
for o in plan['ops']:
    for arm in o['arms']:
        for it in sched[arm]:
            if it['cs'] < o['H'] <= it['os'] + 5:
                it['part'] = o['part']; it['carried'] = True
                o.setdefault('intervals', {})[arm] = [it['cs'], it['os']]
json.dump(sched, open(out + '/sched.json', 'w'), indent=0); json.dump(plan, open(out + '/plan.json', 'w'), indent=1)
e = pickle.load(open(erefp, 'rb'))
np.savez_compressed(out + '/eref_free.npz', **{k: np.array([[i] + list(v) + list(w) for i, v, w in s]) for k, s in e['ser'].items()})
