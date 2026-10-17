"""Op-by-op search driver: from the checkpoint of op k-1, try CANDIDATES for op k in parallel; keep the first that welds."""
import json, os, pickle, sys, time, argparse
import multiprocessing as mp
import numpy as np
import vesken_oracle as V

ap = argparse.ArgumentParser()
ap.add_argument('--demo', default='refs/vesken.npz')
ap.add_argument('--ref', default='tools/ref')
ap.add_argument('--dir', default='ck')
ap.add_argument('--from-op', type=int, default=0)
ap.add_argument('--to-op', type=int, default=22)
ap.add_argument('--workers', type=int, default=6)
ap.add_argument('--cands', default=None, help='json list overriding CANDIDATES')
ap.add_argument('--dev-max', type=float, default=3.0)
a = ap.parse_args()
os.makedirs(a.dir, exist_ok=True)
RUN = V.Runner(a.demo, a.ref)
CANDS = json.loads(a.cands) if a.cands else V.CANDIDATES
CK = None

def trial(args):
    k, idx = args
    RUN.restore(CK) if CK is not None else None
    t = time.time(); log = []
    res = RUN.run_op(k, CANDS[idx], log)
    res['wall'] = round(time.time() - t, 1); res['idx'] = idx; res['log'] = log
    ck = RUN.checkpoint() if res['ok'] else None
    return res, ck

for k in range(a.from_op, a.to_op + 1):
    prevp = os.path.join(a.dir, f'op{k-1:02d}.pkl')
    CK = pickle.load(open(prevp, 'rb')) if k > 0 else None
    if k == 0:
        CK = RUN.checkpoint()
    with mp.get_context('fork').Pool(min(a.workers, len(CANDS))) as pool:
        results = pool.map(trial, [(k, i) for i in range(len(CANDS))])
    best = None
    later = [x['part'] for x in RUN.ops[k + 1:]]
    for res, ck in results:
        res['later_dev'] = max([res['dev'][n] for n in later], default=0.)
        dv = sorted(res['dev'].items(), key=lambda x: -x[1])[:4]
        print(json.dumps({x: res[x] for x in ('key', 'idx', 'ok', 'waited', 'rows', 'disturb_mm', 'disturb_part', 'gap_mm', 'lat_mm', 'ax', 'wall', 'rr')}, default=str), 'dev', dv, flush=True)
        print('   later_dev', res['later_dev'], flush=True)
        if res['ok'] and res['later_dev'] < a.dev_max and (best is None or res['later_dev'] < best[0]['later_dev'] - 0.5):
            best = (res, ck)
    json.dump([r for r, _ in results], open(os.path.join(a.dir, f'op{k:02d}_results.json'), 'w'), default=str, indent=1)
    if best is None:
        print('FAIL op', k, flush=True); sys.exit(1)
    print('KEEP op', k, best[0]['key'], 'cand', best[0]['idx'], best[0]['params'], flush=True)
    pickle.dump(best[1], open(os.path.join(a.dir, f'op{k:02d}.pkl'), 'wb'))
