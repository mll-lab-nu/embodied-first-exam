"""Trace a gripper's hold on the rope from a run's states.npz: per step, the nearest rope point to the TCP in the
TCP frame (x = approach depth, y = jaw, z = along the pads) and the finger joint. Usage: grip_trace.py run side k0 k1 [every]"""
import sys, numpy as np
import yam_kin as K
run, side, k0, k1 = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
ev = int(sys.argv[5]) if len(sys.argv) > 5 else 10
S = np.load(f"{run}/states.npz"); P, Q, A = S["rope_pos"], S["q"], S["actions"]
o = 0 if side == "left" else 7
for k in range(k0, min(k1, len(P)), ev):
    T = K.base_to_world(K.fk_tcp(Q[k][o:o + 6].astype(float)), side)
    # densify the polyline of link centres
    loc = (P[k] - T[:3, 3]) @ T[:3, :3]
    d = np.linalg.norm(loc, axis=1); i = d.argmin()
    print(k, "link", i, "local", np.round(loc[i], 4), "finger %.4f cmd %.4f" % (Q[k][o + 6], A[k][o + 6]), "tcp", np.round(T[:3, 3], 3))
