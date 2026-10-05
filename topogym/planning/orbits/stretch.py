"""Per-phase cord stretch of a recorded oracle run (max segment ratio and total length ratio)."""
import numpy as np

from .rope_sim import initial_cord


def stretch_by_phase(frames_path, variant):
    fr = np.load(frames_path, allow_pickle=True)
    pts, ph, t = fr['pts'], fr['phase'], fr['t']
    rest = np.linalg.norm(np.diff(initial_cord(variant), axis=0), axis=1)
    seg = np.linalg.norm(np.diff(pts, axis=1), axis=2)/rest
    tot = np.linalg.norm(np.diff(pts, axis=1), axis=2).sum(1)/rest.sum()
    best = {}
    for k in range(len(t)):
        p, m = str(ph[k]), seg[k].max()
        if p not in best or m > best[p]['max_segment_stretch']:
            best[p] = dict(max_segment_stretch=round(float(m), 3), segment=int(seg[k].argmax()),
                           t_s=round(float(t[k]), 2), total_length_ratio=round(float(tot[k]), 4))
    return best
