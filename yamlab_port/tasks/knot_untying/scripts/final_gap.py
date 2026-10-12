"""Tightest non-local pairs (top view) of a run's final rope state. python final_gap.py <link_len_m> <run_dir>..."""
import os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "overlay", "yamlab", "envs", "tasks", "knot_untying_lib"))
sys.path.insert(0, "/workspace/yamlab_port/runs/knot_untying/yamlab/yamlab/envs/tasks/knot_untying_lib")
import rope_geom as G
d = float(sys.argv[1])
for run in sys.argv[2:]:
    S = np.load(os.path.join(run, "states.npz"))
    p, q = S["rope_pos"][-1].astype(float), S["rope_quat"][-1].astype(float)
    pts, s = G.stations_points(p, q, d); n = len(pts) - 1
    I, J = np.triu_indices(n, k=2)
    D = G._pair_segment_distance_2d(pts[I, :2], pts[I + 1, :2], pts[J, :2], pts[J + 1, :2])
    D = np.where(s[J] - s[I + 1] < 0.016, np.inf, D)
    k = np.argmin(D)
    print(run, "min non-local gap %.2f mm at s=%.3f / %.3f (L %.3f)" % (D[k] * 1000, s[I[k]], s[J[k]], s[-1]))
