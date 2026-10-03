"""Fresh-process verification of the actual joint commands, independent of HTTP scheduling."""
import hashlib
import json
import os
from pathlib import Path
import sys
import numpy as np


def main(directory, video=False):
    path = Path(directory)
    raw = json.loads((path/'trajectory.json').read_text())
    os.environ['DUEL_SEED'] = str(raw['seed'])
    os.environ['FIRST_RECEIVER'] = raw['first_receiver']
    import duel
    from server_duel import fingerprint
    if raw['source_sha'] != fingerprint() or raw['revision'] != duel.REVISION:
        raise ValueError('simulator fingerprint mismatch')
    arrays = {s: np.asarray(raw[s], dtype=float) for s in duel.SIDES}
    for a in arrays.values():
        if a.size and (a.ndim != 2 or a.shape[1] != 7 or not np.isfinite(a).all()):
            raise ValueError('invalid trajectory shape or nonfinite value')
    if len(arrays['A']) != len(arrays['B']):
        raise ValueError('unequal trajectory lengths')
    g = duel.Duel()
    g.replay(arrays['A'], arrays['B'])
    if video:
        duel.render_video(arrays['A'], arrays['B'], str(path/'replay.mp4'))
        return
    targets = {s: [q.tolist() for q in g.actions[s]] for s in duel.SIDES}
    sha = hashlib.sha256(json.dumps(targets, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    out = dict(state_sha=g.state_sha(), score=g.score, points=g.points, steps=g.k, done=g.done, winner=g.winner,
               targets_sha=sha, seed=duel.SEED, first_receiver=duel.FIRST_RECEIVER,
               source_sha=raw['source_sha'], revision=duel.REVISION)
    (path/'replay_check.json').write_text(json.dumps(out))


if __name__ == '__main__':
    main(sys.argv[1], '--video' in sys.argv[2:])
