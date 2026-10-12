"""Rope direction at the held station in the TCP frame over a run (detects pivoting in the jaws).
Usage: grip_axis_trace.py run side from_tip k0 k1 every"""
import sys, numpy as np
import yam_kin as K
from plan_np import polyline_station
run, side, ft, k0, k1, ev = sys.argv[1], sys.argv[2], float(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6])
S = np.load(f"{run}/states.npz"); P, Q = S["rope_pos"], S["q"]
o = 0 if side == "left" else 7
for k in range(k0, min(k1, len(P)), ev):
    T = K.base_to_world(K.fk_tcp(Q[k][o:o + 6].astype(float)), side)
    pt, t = polyline_station(P[k].astype(float), ft)
    tip = P[k][-1]
    print(k, "station local", np.round(T[:3, :3].T @ (pt - T[:3, 3]), 4), "tangent local", np.round(T[:3, :3].T @ t, 3),
          "tip z %.3f grip z %.3f" % (tip[2], pt[2]), "finger %.4f" % Q[k][o + 6])
