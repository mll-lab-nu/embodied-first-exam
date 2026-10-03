"""Replay logged step/commands using the recorded seed and a verified simulator fingerprint."""
import hashlib
import json
import os
from pathlib import Path
import sys
import numpy as np
import match


def source_sha():
    root = Path(__file__).resolve().parent
    h = hashlib.sha256()
    names = ['match.py', 'rally.py', 'rcb_tt.py', 'instance.npz', 'serves_pool.json', 'rally.json']
    names += [str(p.relative_to(root)) for p in sorted((root/'scene').rglob('*')) if p.is_file()]
    for name in names:
        h.update(name.encode()); h.update((root/name).read_bytes())
    return h.hexdigest()


def main(ep_path, k_end, out_path):
    with open(ep_path) as f:
        events = [json.loads(line) for line in f if line.strip()]
    metadata = next(e for e in events if e.get('ev') == 'start')
    if metadata.get('revision') != match.REVISION or metadata.get('source_sha') != source_sha():
        raise ValueError('recorded simulator version/fingerprint differs; use the original task version')
    os.environ['MATCH_SEED'] = str(metadata['seed'])
    acts = [(int(e['k']), e['decision']) for e in events if e.get('ev') == 'act_applied']
    if any(k < 0 or k >= k_end for k, _ in acts) or any(a[0] > b[0] for a, b in zip(acts, acts[1:])):
        raise ValueError('invalid command step sequence')
    r = match.Match(metadata['level']); i = 0
    while r.k < k_end and not r.done:
        while i < len(acts) and acts[i][0] == r.k:
            dec = acts[i][1]
            if dec['type'] == 'none': r.rt_clear()
            else: r.rt_act(dec['t'], dec['pos'], dec['normal'], dec['vel'])
            i += 1
        r.rt_advance(1)
    if i != len(acts) or r.k != k_end:
        raise ValueError('replay did not consume the complete command/step record')
    a = np.ascontiguousarray(r.s.actions(), dtype=np.float64)
    out = {'score': list(r.score), 'steps': r.k, 'n_acts': len(acts), 'acts_applied': i,
           'state_sha': r.s.state_sha(), 'actions_sha': hashlib.sha256(a.tobytes()).hexdigest(),
           'seed': metadata['seed'], 'revision': match.REVISION, 'source_sha': metadata['source_sha'],
           'done': r.done, 'points': [{k: p[k] for k in ('winner','how','score','step')} for p in r.points]}
    Path(out_path).write_text(json.dumps(out, default=float))
    print(json.dumps({k:out[k] for k in ('score','steps','n_acts','done')}))


if __name__ == '__main__':
    main(sys.argv[1], int(sys.argv[2]), sys.argv[3])
