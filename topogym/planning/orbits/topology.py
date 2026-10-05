"""Ordered passage signature of the cord (diagnostic, not an invariant).

Events along the cord from node 0 to node n-1:
  R{k}{+/-}      crossing ring k's aperture disk upward/downward
  P{j}<{hi/lo}   crossing y=0 just on the -x side of post j (wrapping its far side)
                 hi/lo = above/below the ring that post j passes through (j>=1: R{j+1}? no: R_j's top)
"""
import numpy as np


def signature(pts, lay, closing=True):
    P = np.asarray(pts)
    if closing:
        P = np.vstack([P, P[:1]])
    a, b = P[:-1], P[1:]
    ev = []
    inner = lay.ring_radius_m-lay.ring_tube_radius_m
    for k, (x, z) in enumerate(zip(lay.ring_x, lay.ring_z)):
        ids = np.flatnonzero((a[:, 2]-z)*(b[:, 2]-z) < 0)
        for i in ids:
            t = (z-a[i, 2])/(b[i, 2]-a[i, 2])
            h = a[i]+t*(b[i]-a[i])
            if np.hypot(h[0]-x, h[1]) < inner:
                ev.append((i+t, f'R{k+1}{"+" if b[i,2] > a[i,2] else "-"}'))
    tops = [lay.ball_z+lay.ball_radius_m, *lay.ring_z]
    ids = np.flatnonzero(a[:, 1]*b[:, 1] < 0)
    for i in ids:
        t = a[i, 1]/(a[i, 1]-b[i, 1])
        h = a[i]+t*(b[i]-a[i])
        for j, px in enumerate(lay.post_x):
            if px-.045 < h[0] < px and lay.base_height_m < h[2] < tops[j]+.03:
                # which level band: index of the lowest ring above h (ring numbering 1..n from top)
                band = sum(1 for zz in lay.ring_z if zz > h[2])  # rings above this point
                tag = 'ball' if (j == 0 and h[2] > lay.ball_z-lay.ball_radius_m) else f'L{band}'
                ev.append((i+t, f'P{j}<{tag}{"+" if b[i,1] > a[i,1] else "-"}'))
                break
    ev.sort()
    return ev


def fmt(ev):
    return ' '.join(f'{name}@{int(s)}' for s, name in ev)
