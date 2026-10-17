import pickle, json, numpy as np
ann = pickle.load(open('runs/ann_free.pkl', 'rb')); zf = pickle.load(open('runs/zone_free.pkl', 'rb'))
c = np.load('refs/vesken.npz')['ctrl']
task = json.load(open('scenes/vesken/task.json')); ops = task['operations']
rec = ann['rec']; eng = ann['eng']; byi = {r['i']: r for r in rec}
GI = {'left': 7, 'right': 15}
plan = []
for o in ops:
    k, P = o['key'], o['part']; e = eng[k]
    r0 = byi[(e // 20) * 20 - 100]
    arms = [a for j, a in enumerate(('left', 'right')) if P in r0['held'][j] and r0['g'][j] < 127]
    # H: first row >= e - 200 where a holding gripper's command increases
    H = None
    for r in range(e - 200, e + 4000):
        if any(c[r, GI[a]] > c[r - 1, GI[a]] + 1e-9 for a in arms):
            H = r; break
    # G: start of the last continuous holding interval before H (annotation)
    G = None
    for r in reversed([x for x in rec if x['i'] < H]):
        if all(P in r['held'][('left', 'right').index(a)] for a in arms[:1]):
            G = r['i']
        else:
            break
    ser = zf['ser'][k]
    Z = None
    for (i, g, l, a, gl, gr) in reversed([x for x in ser if x[0] < H]):
        if l < 0.005 and -0.003 < g < 0.05 and a < 15:
            Z = i
        else:
            break
    plan.append(dict(key=k, part=P, eng=e, arms=arms, G=G, Z=Z, H=H))
    print(plan[-1])
rr = zf['rr']
print('rr top', sorted(rr, key=lambda x: -x[1])[:10])
json.dump(dict(ops=plan), open('tools/plan.json', 'w'), indent=1)
