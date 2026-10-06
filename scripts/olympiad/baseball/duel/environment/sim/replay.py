"""Fresh-process verification of a baseball duel from its recorded commands only (trajectory.json): the seed, the
first batter, every command with the pitch and control step at which it took effect, and the final step. No wall
time is read. The recorded simulator fingerprint must match this copy.

    python3 replay.py DATA_DIR [--video]      writes DATA_DIR/replay_check.json (or DATA_DIR/replay.mp4)
"""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bbduel  # noqa: E402


def fingerprint():
    h = hashlib.sha256()
    for name in ('bb.py', 'bbrt.py', 'bbduel.py', 'replay.py', 'server_duel.py'):
        h.update(name.encode()); h.update((HERE / name).read_bytes())
    return h.hexdigest()


class _Video:
    """bb.render_video's view of a duel: the thrown pitches (an automatic ball has no flight) and the overlay line."""

    def __init__(self, g):
        self.history = [r for r in g.history if r['pitch_obj'] is not None]
        self.pa_results = g.pa_results

    def head(self, rec):
        runs = {s: sum(r['runs'] for r in self.pa_results[:rec['pa']] if r['batter'] == s) for s in bbduel.SIDES}
        bases = ' '.join(('1st', '2nd', '3rd')[b - 1] for b in rec['on_base']) or 'empty'
        return (f"{rec['half']} {rec['inning']}  {rec['outs']} out  bases {bases}  {rec['batter']} batting  "
                f"count {rec['count'][0]}-{rec['count'][1]}  runs A {runs['A']} B {runs['B']}   "
                f"pitch {rec['pitch'] + 1}: {rec['type']} {rec['radar']} m/s")


def main(directory, video=False):
    path = Path(directory)
    raw = json.loads((path / 'trajectory.json').read_text())
    if raw['source_sha'] != fingerprint() or raw['revision'] != bbduel.REVISION:
        raise ValueError('simulator fingerprint mismatch')
    cmds = [(int(p), int(k), s, d) for p, k, s, d in raw['commands']]
    if any(s not in bbduel.SIDES for _, _, s, _ in cmds) or any(
            (a[0], a[1]) > (b[0], b[1]) for a, b in zip(cmds, cmds[1:])):
        raise ValueError('invalid command sequence')
    g = bbduel.replay(int(raw['seed']), raw['first_batter'], cmds, int(raw['k_end']))
    if video:
        import bb
        v = _Video(g)
        bb.render_video(v, str(path / 'replay.mp4'), head=v.head)
        return
    out = dict(state_sha=g.state_sha(), score=g.score, steps=g.k, done=g.done, pitches=len(g.history),
               decisions_sha=bbduel.decisions_sha([list(c) for c in cmds]), seed=g.seed, first_batter=g.first,
               source_sha=raw['source_sha'], revision=bbduel.REVISION, pa_results=g.pa_results)
    (path / 'replay_check.json').write_text(json.dumps(out, default=float))
    print(json.dumps({k: out[k] for k in ('score', 'steps', 'done', 'pitches')}))


if __name__ == '__main__':
    main(sys.argv[1], '--video' in sys.argv[2:])
