"""Fresh-process replay: re-runs the match from the logged (control step, act) list only, with the recorded seed and
a verified simulator fingerprint. Every act is planned and applied at its logged step with `Match.rt_act` (the
reference semantics the live planner process reproduces); no wall time is involved."""
import hashlib
import json
import os
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc import REVISION, source_sha, apply_inline  # noqa: E402


def main(ep_path, k_end, out_path):
    with open(ep_path) as f:
        events = [json.loads(line) for line in f if line.strip()]
    metadata = next(e for e in events if e.get('ev') == 'start')
    if metadata.get('revision') != REVISION or metadata.get('source_sha') != source_sha():
        raise ValueError('recorded simulator version/fingerprint differs; use the original task version')
    os.environ['MATCH_SEED'] = str(metadata['seed'])
    import bm
    acts = [(int(e['k']), e['decision']) for e in events if e.get('ev') == 'act_applied']
    if any(k < 0 or k >= k_end for k, _ in acts) or any(a[0] > b[0] for a, b in zip(acts, acts[1:])):
        raise ValueError('invalid command step sequence')
    r = bm.Match(metadata['level']); i = 0
    if r.lv['seed'] != metadata['seed']:
        raise ValueError('seed mismatch')
    while r.k < k_end and not r.done:
        while i < len(acts) and acts[i][0] == r.k:
            apply_inline(r, acts[i][1])
            i += 1
        r.rt_advance(1)
    if i != len(acts) or r.k != k_end:
        raise ValueError('replay did not consume the complete command/step record')
    a = np.ascontiguousarray(r.s.actions(), dtype=np.float64)
    out = {'score': list(r.score), 'steps': r.k, 'n_acts': len(acts), 'acts_applied': i,
           'state_sha': r.s.state_sha(), 'actions_sha': hashlib.sha256(a.tobytes()).hexdigest(),
           'seed': metadata['seed'], 'revision': REVISION, 'source_sha': metadata['source_sha'],
           'done': r.done, 'winner': r.winner, 'points': [{k: p[k] for k in ('winner', 'how', 'score', 'step')} for p in r.points]}
    Path(out_path).write_text(json.dumps(out, default=float))
    print(json.dumps({k: out[k] for k in ('score', 'steps', 'n_acts', 'done')}))


if __name__ == '__main__':
    main(sys.argv[1], int(sys.argv[2]), sys.argv[3])
