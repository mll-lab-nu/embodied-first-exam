#!/usr/bin/env python3
"""The phase guide's relative-pose track: the original demo replayed WITHOUT the arm clamp (as it was made; it passes
there) and, per row, each panel's pose relative to the top (position, wxyz quaternion), plus the TCP poses. The
closed-loop reference servos the held panel onto this track; the track itself is never executed.
  rec_guide.py OUT.npz"""
import sys, numpy as np
from eket_lib import Rig, demo_rows
g = Rig(); s = g.s
s.applied = lambda a: np.clip(a, s._clo, s._chi)          # the demo as made (no clamp): the guide only
c = demo_rows()
roles = ('side_a', 'side_b', 'back', 'bottom')
rel = np.zeros((len(c), len(roles), 7)); done = []
for i, row in enumerate(c):
    s.step(row)
    for k, r in enumerate(roles):
        p, q, v, w = g.rel(r); rel[i, k, :3] = p; rel[i, k, 3:] = q
    if len(g.tr.records) > len(done):
        done.append((g.tr.records[-1]['name'], i))
np.savez_compressed(sys.argv[1], rel=rel, roles=np.array(roles), accepts=np.array([d[1] for d in done]),
                    accept_names=np.array([d[0] for d in done]))
print(done, s.final_check()['success'])
