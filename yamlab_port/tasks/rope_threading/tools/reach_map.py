"""Numpy reach maps of one YAM arm at ring heights (no Isaac). TCP frame (yam_kin): x = approach,
y = jaw axis; a rope held across the fingers runs along z_tcp.

For each (x, y) cell and TCP height above the table: try approach directions given as
(yaw of the horizontal approach component, pitch down) and jaw roll; print the count of
reachable orientations. Usage: python reach_map.py [left|right] [height_above_table ...]
"""
import sys
import numpy as np
from scipy.spatial.transform import Rotation as Rot
import yam_kin as K

TABLE = 0.7517


def frame(approach, jaw_hint):
    a = np.asarray(approach, float); a /= np.linalg.norm(a)
    j = np.asarray(jaw_hint, float); j = j - a * (a @ j); j /= np.linalg.norm(j)
    T = np.eye(4); T[:3, :3] = np.c_[a, j, np.cross(a, j)]
    return T


def seeds_for(p_base):
    yaw = np.arctan2(p_base[1], p_base[0])
    out = []
    for q2, q3 in ((0.6, 0.6), (1.2, 1.0), (1.6, 1.4), (2.2, 1.9), (0.9, 1.6), (1.4, 2.2)):
        for q4 in (-0.8, 0.8):
            for q6 in (-1.2, 1.2):
                out.append(np.array([yaw, q2, q3, q4, 0.0, q6]))
    return out


def reachable(T_world, side, margin=0.05):
    Tb = K.world_to_base(T_world, side)
    for s in seeds_for(Tb[:3, 3]):
        q, ok, ep, er = K.ik(Tb, s, iters=150, margin=margin)
        if ok:
            return q
    return None


def orientations():
    """(name, approach, jaw_hint) candidates."""
    out = []
    for yaw in (0, 45, 90, -45, -90, 135, -135):
        for pitch in (0, 30, 60):
            y, p = np.radians(yaw), np.radians(pitch)
            a = np.array([np.cos(p) * np.cos(y), np.cos(p) * np.sin(y), -np.sin(p)])
            for jn, jh in (("jv", [0, 0, 1.0]), ("jh", [-np.sin(y), np.cos(y), 0.0])):
                out.append((f"y{yaw}p{pitch}{jn}", a, jh))
    return out


def cell(args):
    side, x, y, h = args
    hits = []
    for name, a, jh in orientations():
        T = frame(a, jh); T[:3, 3] = (x, y, TABLE + h)
        if reachable(T, side) is not None:
            hits.append(name)
    return (x, y, h), hits


if __name__ == "__main__":
    import json
    from multiprocessing import Pool
    side = sys.argv[1] if len(sys.argv) > 1 else "left"
    heights = [float(h) for h in sys.argv[2:]] or [0.27, 0.31]
    ors = orientations()
    jobs = [(side, x, y, h) for h in heights for x in np.arange(0.30, 0.86, 0.05) for y in np.arange(-0.45, 0.46, 0.05)]
    with Pool(16) as pool:
        res = dict(pool.map(cell, jobs, chunksize=2))
    json.dump({"%s,%.2f,%.2f,%.3f" % (side, *k): v for k, v in res.items()}, open(f"reach_{side}.json", "w"))
    for h in heights:
        print(f"REACH {side} TCP {h*1000:.0f} mm above table; cell = count of {len(ors)} orientations reachable (hex, capped at F)")
        print("        y: " + " ".join(f"{y:+.2f}"[1:] if False else f"{y:+.1f}"[-2:] for y in np.arange(-0.45, 0.46, 0.05)))
        for x in np.arange(0.30, 0.86, 0.05):
            row = ""
            for y in np.arange(-0.45, 0.46, 0.05):
                n = len(res[(x, y, h)])
                row += "%3s" % ("%X" % min(n, 15) if n else ".")
            print(f"  x={x:.2f} {row}")
        sys.stdout.flush()
