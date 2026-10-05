"""Kinematic search for ball passes made with a fresh bight pulled from anywhere on the cord.

A candidate takes material node i, lifts a narrow bight vertically to z_up, carries it above the
stopper ball and hooks (straddles) post P0 just below the ball with either orientation. The exact
infinite-ball word of the resulting loop tells whether the pass deletes a b. Candidates whose
vertical rise or carry path comes too close to the fixture are rejected.
"""
import numpy as np
from .ribbon import densify
from .rope_sim import KS


def fixture_distance(lay, P):
    """Approximate clearance of polyline points to fixture primitives (centerline distances)."""
    P = np.asarray(P)
    d = np.full(len(P), np.inf)
    tops = [lay.ball_z, *lay.ring_z]
    for x, top in zip(lay.post_x, tops):
        inside = (P[:, 2] >= lay.base_height_m) & (P[:, 2] <= top)
        r = np.hypot(P[:, 0]-x, P[:, 1])-lay.post_radius_m
        d = np.where(inside, np.minimum(d, r), d)
    d = np.minimum(d, np.linalg.norm(P-[lay.post_x[0], 0, lay.ball_z], axis=1)-lay.ball_radius_m)
    for cx, z in zip(lay.ring_x, lay.ring_z):
        rho = np.hypot(P[:, 0]-cx, P[:, 1])
        d = np.minimum(d, np.hypot(rho-lay.ring_radius_m, P[:, 2]-z)-lay.ring_tube_radius_m)
    base = (np.abs(P[:, 0]) < lay.base_length_m/2) & (np.abs(P[:, 1]) < lay.base_width_m/2)
    d = np.where(base, np.minimum(d, P[:, 2]-lay.base_height_m), d)
    return d


def excursion(lay, p, sign, z_up=None, d=None, neck=None, via=None):
    """Loop segment leaving p and returning to p: up, over the ball, straddle P0 with orientation.

    via: optional horizontal point (x, y) at p's height to move to before rising.
    """
    x0 = lay.post_x[0]
    d = .008*KS if d is None else d
    top = lay.ball_z+lay.ball_radius_m
    z_up = z_up or top+.05
    neck = neck or (lay.ring_z[0]+lay.ring_tube_radius_m+lay.ball_z-lay.ball_radius_m)/2
    q = np.array(p, float) if via is None else np.array([via[0], via[1], p[2]])
    C = [p, q, [q[0], q[1], z_up], [x0-.035*KS, 0, z_up], [x0-.035*KS, 0, neck], [x0+.02*KS, 0, neck]]
    C = densify(C, .004)
    # horizontal offset: +-y around the ball region; along the vertical rise use +-x offsets
    out, back = [], []
    for q in C:
        off = np.array([0, d, 0]) if q[2] > lay.ball_z-lay.ball_radius_m-.02 or abs(q[0]-x0) < .05 else np.array([d, 0, 0])
        out.append(q+sign*off)
        back.append(q-sign*off)
    # straddle: at the end the centerline passes P0 (x0) at y=0 -> strands at +-d*sign; tip beyond x0
    tipc = C[-1]
    arc = [tipc+np.array([.006*np.sin(t), sign*d*np.cos(t), 0]) for t in np.linspace(0, np.pi, 9)[1:-1]]
    return np.vstack([out, arc, back[::-1]])


def vias(lay, p):
    out = [None]
    for cx, z in zip(lay.ring_x, lay.ring_z):
        if p[2] < z and np.hypot(p[0]-cx, p[1]) < lay.ring_radius_m+lay.ring_tube_radius_m+.004:
            # candidate rise points inside this ring's aperture, on either side of the enclosed post
            for dx in (-.03, -.015, .015, .03):
                for dy in (0., .02, -.02):
                    out.append((cx+dx, dy))
    return out


def candidates(F, lay, P, nodes, signs=(1, -1), min_clear=.003):
    base_w = F.describe(P)
    res = []
    for i in nodes:
        for v in vias(lay, P[i]):
            for s in signs:
                e = excursion(lay, P[i], s, via=v)
                clear = float(fixture_distance(lay, e[3:-3]).min())
                if clear < min_clear:
                    continue
                L = np.vstack([P[:i], e, P[i+1:]])
                w = F.describe(L)
                res.append(dict(node=int(i), sign=s, via=v, b=w[2], length=w[1], word=w[0], clear=clear, loop=L))
    return base_w, res


def route_excursion(lay, p, sign, waypoints, d=None, z_margin=.015):
    """Bight from p along axis-aligned legs through waypoints, then over the ball to straddle P0."""
    d = .0085*KS if d is None else d
    x0 = lay.post_x[0]
    top = lay.ball_z+lay.ball_radius_m
    z_up = top+z_margin
    neck = (lay.ring_z[0]+lay.ring_tube_radius_m+lay.ball_z-lay.ball_radius_m)/2
    C = [np.array(p, float), np.array(p, float)+[0, 0, .012]]
    for w in waypoints:
        w = np.array(w, float)
        c = C[-1]
        if abs(w[2]-c[2]) > 1e-9:            # horizontal first at current height, then vertical
            C.append(np.array([w[0], w[1], c[2]]))
        C.append(w)
    c = C[-1]
    C += [np.array([c[0], c[1], max(z_up, c[2])]), np.array([x0-.03*KS, 0, z_up]), np.array([x0-.03*KS, 0, neck]),
          np.array([x0+.012*KS, 0, neck])]
    C = [c for k, c in enumerate(C) if k == 0 or np.linalg.norm(c-C[k-1]) > 1e-9]
    C = densify(C, .004)
    out, back = [], []
    prev = np.array([1., 0, 0])
    for i, q in enumerate(C):
        t = C[min(i+1, len(C)-1)]-C[max(i-1, 0)]
        h = np.array([t[0], t[1], 0.])
        if np.linalg.norm(h) > 1e-9:
            h /= np.linalg.norm(h)
            nrm = np.array([-h[1], h[0], 0])
            if nrm @ prev < 0:
                nrm = -nrm
            prev = nrm
        out.append(q+sign*d*prev)
        back.append(q-sign*d*prev)
    tipc = C[-1]
    arc = [tipc+np.array([.006*np.sin(t), 0, 0])+sign*d*prev*np.cos(t) for t in np.linspace(0, np.pi, 9)[1:-1]]
    return np.vstack([out, arc, back[::-1]]), C


def waypoint_sets(lay):
    """One- and two-waypoint routes through ring apertures / beside posts at the level bands."""
    zs = sorted(lay.ring_z)
    bands = [(lay.base_height_m+zs[0]-lay.ring_tube_radius_m)/2]
    for lo, hi in zip(zs[:-1], zs[1:]):
        bands.append((lo+hi)/2)
    bands.append((zs[-1]+lay.ring_tube_radius_m+lay.ball_z-lay.ball_radius_m)/2)
    xs = sorted(set([round(x+dx, 4) for x in lay.post_x for dx in (-.02, .02)] +
                    [round(c, 4) for c in lay.ring_x]))
    pts = [(x, y, z) for z in bands for x in xs for y in (-.035, 0., .035)]
    return pts, bands
