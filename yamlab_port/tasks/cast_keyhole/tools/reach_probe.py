"""Reach envelope of one YAM arm (base frame): for approach cases, the max horizontal distance per bearing
at which IK exists with joint margin >= 0.1 rad.  usage: python reach_probe.py case [case...]"""
import sys, numpy as np, yam_kin as yk
from plan import frame
from layout import T_from
rng = np.random.default_rng(1)
def solve(T, tries=40):
    best = None
    for _ in range(tries):
        q0 = yk.LOWER + rng.random(6) * (yk.UPPER - yk.LOWER)
        q, ok, ep, er = yk.ik(T, q0, iters=200)
        if ok:
            m = float(np.min(np.minimum(q - yk.LOWER, yk.UPPER - q)))
            if best is None or m > best[1]: best = (q, m)
    return best
cases = {"down": ([0, 0, -1], [0, 1, 0]), "down_jx": ([0, 0, -1], [1, 0, 0]), "fwd_jy": ([1, 0, 0], [0, 1, 0]), "down45_fwd": ([.707, 0, -.707], [0, 1, 0]),
         "horiz_fwd": ([1, 0, 0], [0, 0, 1]), "horiz_right": ([0, -1, 0], [0, 0, 1]),
         "horiz_left": ([0, 1, 0], [0, 0, 1]),
         "down45_right": ([0, -.707, -.707], [0, .707, -.707]), "down45_left": ([0, .707, -.707], [0, .707, .707])}
for name in sys.argv[1:]:
    a, j = cases[name]
    R = frame(a, j)
    for dz in [float(x) for x in __import__("os").environ.get("DZ", "0.03,0.10,0.2").split(",")]:
        row = []
        for ang in (90, 60, 30, 0, -30, -60, -90):
            ok_r = [r for r in np.arange(0.10, 0.66, 0.05)
                    if (s := solve(T_from(R, np.r_[r*np.cos(np.radians(ang)), r*np.sin(np.radians(ang)), dz]))) is not None and s[1] >= 0.1]
            row.append((ang, (round(min(ok_r), 2), round(max(ok_r), 2)) if ok_r else None))
        print(name, "dz", dz, row, flush=True)
