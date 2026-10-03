"""Fresh-process replay of the badminton duel: re-runs the match from the logged (control step, seat, act) list only,
with the recorded seed, first receiver and a verified simulator fingerprint. Every act is planned and applied at its
logged step with `bduel.apply_inline` (the reference semantics the live planner processes reproduce); no wall time is
involved. `--video` renders replay.mp4 instead."""
import hashlib
import json
import os
from pathlib import Path
import sys


def load(directory):
    path = Path(directory)
    events = [json.loads(line) for line in (path/'episode.jsonl').read_text().splitlines() if line.strip()]
    meta = next(e for e in events if e.get('ev') == 'start')
    end = [e for e in events if e.get('ev') == 'end']
    if not end:
        raise ValueError('the episode has no end record')
    os.environ['DUEL_SEED'] = str(meta['seed'])
    os.environ['FIRST_RECEIVER'] = meta['first_receiver']
    acts = [(int(e['k']), e['seat'], e['decision']) for e in events if e.get('ev') == 'act_applied']
    return path, meta, int(end[-1]['k_end']), acts


def main(directory, video=False):
    path, meta, k_end, acts = load(directory)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import bduel
    from server_duel import fingerprint
    if meta['source_sha'] != fingerprint() or meta['revision'] != bduel.REVISION:
        raise ValueError('simulator fingerprint mismatch')
    if any(k < 0 or k >= max(k_end, 1) for k, _, _ in acts) or any(a[0] > b[0] for a, b in zip(acts, acts[1:])):
        raise ValueError('invalid command step sequence')
    if video:
        tmp = str(path/'replay.tmp.mp4')
        bduel.render_video(acts, k_end, tmp)
        os.replace(tmp, path/'replay.mp4')
        return
    w = bduel.World(); i = 0
    while w.k < k_end and not w.done:
        while i < len(acts) and acts[i][0] == w.k:
            bduel.apply_inline(w.sides[acts[i][1]], acts[i][2]); i += 1
        w.advance()
    if i != len(acts) or w.k != k_end:
        raise ValueError('replay did not consume the complete command/step record')
    out = dict(state_sha=w.state_sha(), score=w.score, points=w.points, steps=w.k, done=w.done, winner=w.winner,
               targets_sha=w.targets_sha(), n_acts=len(acts), seed=bduel.SEED, first_receiver=bduel.FIRST_RECEIVER,
               source_sha=meta['source_sha'], revision=bduel.REVISION,
               actions_sha={s: hashlib.sha256(json.dumps(w.actions()[s]).encode()).hexdigest() for s in bduel.SIDES})
    (path/'replay_check.json').write_text(json.dumps(out, default=float))
    print(json.dumps({k: out[k] for k in ('score', 'steps', 'n_acts', 'done')}))


if __name__ == '__main__':
    main(sys.argv[1], '--video' in sys.argv[2:])
