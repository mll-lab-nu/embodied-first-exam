"""Straight-segment bight routes: node -> Q -> T (beside the ball) -> over the ball -> straddle P0.

The same centerline is used for the exact-word prediction and for the physical execution.
"""
import numpy as np
from .ribbon import densify
from .bight_search import fixture_distance
from .rope_sim import KS
from .topology import signature


def ball_points(lay, y_s, r=None):
    """T (end of the rise, right of the ball) and the over-the-ball arc ending pulled against P0."""
    p0 = lay.post_x[0]
    bz, br = lay.ball_z, lay.ball_radius_m
    r = br+.0096 if r is None else r
    neck = (lay.ring_z[0]+lay.ring_tube_radius_m+bz-br)/2
    T = np.array([p0+r*np.cos(np.radians(35)), y_s, bz+r*np.sin(np.radians(35))])
    arc = [np.array([p0+r*np.cos(np.radians(a)), 0., bz+r*np.sin(np.radians(a))]) for a in (70, 90, 115, 145, 175)]
    far = np.array([p0-r*.95, 0., neck])
    wrap = np.array([p0+.012, 0., neck])
    return T, arc, far, wrap


def final_hook(lay, T):
    """Centerline of the final hooked state after the pass: down to the neck right of P0, then
    through P0's axis to the apex on its far side (the strands straddle P0)."""
    p0 = lay.post_x[0]
    bz, br = lay.ball_z, lay.ball_radius_m
    neck = (lay.ring_z[0]+lay.ring_tube_radius_m+bz-br)/2
    return [np.array([T[0], 0., neck]), np.array([p0-.018, 0., neck])]


def excursion(lay, C, sign, d=None):
    d = .007*KS if d is None else d             # the two strands straddle P0, whose radius scales
    C = densify(C, .004)
    out, back = [], []
    prev = np.array([0, 1., 0])
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
    return np.vstack([out, arc, back[::-1]])


def q_grid(lay):
    zs = sorted(lay.ring_z)
    t = lay.ring_tube_radius_m
    levels = [lay.base_height_m+.03]+[z+t+.012 for z in zs]
    xs = sorted(set([round(x+dx, 4) for x in lay.post_x for dx in (-.02*KS, .02*KS)]+[round(c, 4) for c in lay.ring_x]))
    return [np.array([x, y, z]) for z in levels for x in xs for y in (-.035*KS, 0., .035*KS)]


def seg_clear(lay, a, b, step=.003):
    n = max(2, int(np.linalg.norm(b-a)/step)+1)
    pts = a+(b-a)*np.linspace(0, 1, n)[:, None]
    return float(fixture_distance(lay, pts).min())


def candidates(F, lay, P, nodes, min_clear=.004):
    bw = F.describe(P)
    Qs = q_grid(lay)
    res = []
    for i in nodes:
        p = P[i]+np.array([0, 0, .01])
        for y_s in (-.03*KS, .03*KS):
            T, arc, far, wrap = ball_points(lay, y_s)
            for Q in [None]+Qs:
                pts = [p] if Q is None else [p, Q]
                pts = pts+[T]
                ok = all(seg_clear(lay, a, b) >= min_clear for a, b in zip(pts[:-1], pts[1:]))
                if not ok:
                    continue
                C = np.array([P[i]]+pts+arc+[far, wrap])
                Cp = np.array([P[i]]+pts+final_hook(lay, T))
                L = float(np.linalg.norm(np.diff(C, axis=0), axis=1).sum())
                for s in (1, -1):
                    ex = excursion(lay, Cp, s)
                    if fixture_distance(lay, ex[6:-6]).min() < .0015:
                        continue
                    new_ = np.vstack([P[:i], ex, P[i+1:]])
                    w = F.describe(new_)
                    if w[2] < bw[2]:
                        res.append(dict(tangle=len(signature(new_, lay)), node=int(i), sign=s, Q=None if Q is None else Q.tolist(), y_s=y_s,
                                        need=2*L, word=w[0], b=w[2], C=C.tolist()))
    best = {}
    for r in res:
        key = (r['node'], str(r['Q']), r['y_s'])
        if key not in best:
            best[key] = r
    return bw, sorted(best.values(), key=lambda r: r['need'])


def escape_routes(lay, p, margin=.012):
    """Aperture-free rises from p: horizontally out of every ring footprint above p (8 headings),
    vertically up beside the fixture to above the top ring, then to T."""
    t = lay.ring_tube_radius_m
    z_hi = max(lay.ring_z)+t+.025
    out = []
    for ph in np.radians(np.arange(0, 360, 45)):
        d = np.array([np.cos(ph), np.sin(ph), 0.])
        above = [(cx, zr) for cx, zr in zip(lay.ring_x, lay.ring_z) if zr+t+.004 >= p[2]]
        s = 0.
        while any(np.hypot(p[0]+s*d[0]-cx, p[1]+s*d[1]) < lay.ring_radius_m+t+margin for cx, _ in above):
            s += .002                 # walk out until clear of every ring footprint above p
        W1 = p+s*d
        out.append([W1, np.array([W1[0], W1[1], z_hi])])
    return out


def escape_candidates(F, lay, P, nodes, min_clear=.004):
    """Like candidates(), but every rise leaves the ring footprints before climbing (no aperture)."""
    bw = F.describe(P)
    res = []
    for i in nodes:
        p = P[i]+np.array([0, 0, .01])
        for y_s in (-.03*KS, .03*KS):
            T, arc, far, wrap = ball_points(lay, y_s)
            for W in escape_routes(lay, p):
                pts = [p]+[w for w in W if np.linalg.norm(w-p) > 1e-6]+[T]
                if not all(seg_clear(lay, a, b) >= min_clear for a, b in zip(pts[:-1], pts[1:])):
                    continue
                C = np.array([P[i]]+pts+arc+[far, wrap])
                Cp = np.array([P[i]]+pts+final_hook(lay, T))
                L = float(np.linalg.norm(np.diff(C, axis=0), axis=1).sum())
                for s in (1, -1):
                    ex = excursion(lay, Cp, s)
                    if fixture_distance(lay, ex[6:-6]).min() < .0015:
                        continue
                    new_ = np.vstack([P[:i], ex, P[i+1:]])
                    w = F.describe(new_)
                    if w[2] < bw[2]:
                        res.append(dict(tangle=len(signature(new_, lay)), node=int(i), sign=s, Q=[x.tolist() for x in pts[1:-1]], y_s=y_s,
                                        need=2*L, word=w[0], b=w[2], C=C.tolist()))
    best = {}
    for r in res:
        key = (r['node'], str(r['Q']), r['y_s'])
        if key not in best:
            best[key] = r
    return bw, sorted(best.values(), key=lambda r: r['need'])


def aperture_center(lay, k):
    """Most open point of ring k's aperture (1-based): midway between the post it surrounds and the
    post it is mounted on -- where a gripper reaches deepest."""
    return np.array([(lay.post_x[k-1]+lay.post_x[k])/2, 0.])


def aperture_points(lay, k, margin=.025):
    """Open points of ring k's aperture for a vertical rise: the centre between its two posts and the
    points beside the post it surrounds, keeping those not above a lower ring and clear of posts/ball."""
    cx, R, t = lay.ring_x[k-1], lay.ring_radius_m, lay.ring_tube_radius_m
    inner = lay.post_x[k-1]
    behind = float(np.sign(inner-lay.post_x[k]))  # side of the inner post away from the mounting post
    # behind the inner post first: there both arms reach deep and the side arm's push-in and the top
    # arm's pick-up can come from different directions; beside the inner post only the same-side arm
    # reaches, so a hand-over there was never feasible
    cand = [np.array([inner+behind*.45*R, 0.])]+[np.array([inner+behind*.4*R, s*.3*R]) for s in (1, -1)] + \
           [aperture_center(lay, k)]+[np.array([cx, s*.4*R]) for s in (1, -1)]
    keep = []
    for c in cand:
        if np.hypot(c[0]-cx, c[1]) > R-t-margin:
            continue
        if np.hypot(c[0]-inner, c[1]) < (lay.ball_radius_m if k == 1 else lay.post_radius_m)+.02:
            continue
        if any(zr < lay.ring_z[k-1]-1e-9 and np.hypot(c[0]-x2, c[1]) < lay.ring_radius_m+t+.01
               for x2, zr in zip(lay.ring_x, lay.ring_z)):
            continue
        keep.append(c)
    return keep or [aperture_center(lay, k)]


def plumb_routes(lay, p):
    """Gripper-friendly rises: drag at the node's height to below an aperture centre, rise vertically
    through it; for two apertures shift between the ring levels and rise through the next one; or rise
    straight up from the node when it already lies in an open aperture area."""
    t = lay.ring_tube_radius_m
    z_hi = max(lay.ring_z)+t+.02*KS
    out = []
    n = len(lay.ring_z)
    seqs = [(k,) for k in range(1, n+1)]+[(k, k-1) for k in range(n, 1, -1)]
    for seq in seqs:
      # through two apertures the cord crosses the gap between the rings: low, middle or high in the gap
      # (dragging under the upper ring needs ~7 cm above the TCP, so only some heights are feasible)
      for g in ((0., .4, .7) if len(seq) > 1 else (0.,)):
        for c0 in aperture_points(lay, seq[0]):
            dy = c0[1]
            pts = []
            z = p[2]
            for j, k in enumerate(seq):
                c = np.array([c0[0], 0.]) if j == 0 else aperture_center(lay, k)
                if j == 0:
                    # drag well below ring k (the gripper's finger rail sits ~7.5 cm above the TCP, so a
                    # node hanging just under the ring is first lowered where it lies) ...
                    z = max(min(z, lay.ring_z[k-1]-t-.09), lay.base_height_m+.015)
                    # ... but above a lower ring under this aperture centre: the drag and the hand-over
                    # then happen between the two ring levels
                    for cx, zr in zip(lay.ring_x, lay.ring_z):
                        if zr < lay.ring_z[k-1]-1e-9 and np.hypot(c[0]-cx, c[1]+dy) < lay.ring_radius_m+t:
                            z = max(z, zr+t+.02*KS)
                    if abs(z-p[2]) > 1e-9:
                        pts.append(np.array([p[0], p[1], z]))
                pts.append(np.array([c[0], c[1]+dy, z]))
                # rise to just above ring k (or up the gap to the next ring; z_hi after the last aperture)
                if j < len(seq)-1:
                    lo_, hi_ = lay.ring_z[k-1]+t+.015*KS, lay.ring_z[seq[j+1]-1]-t-.03
                    z = lo_+g*max(0., hi_-lo_)
                else:
                    z = z_hi
                pts.append(np.array([c[0], c[1]+dy, z]))
            out.append((seq, pts))
    # a node already lying below a ring, inside the open part of its aperture: one arm picks it where it
    # lies and rises straight up through the ring -- no drag and no hand-over. Rings below the node do
    # not matter; any other ring above it must not cover it (the rise would cross that one too)
    for k in range(1, n+1):
        if lay.ring_z[k-1]-t <= p[2] or np.hypot(p[0]-lay.ring_x[k-1], p[1]) > lay.ring_radius_m-t-.025:
            continue
        if any(j != k-1 and zr-t > p[2] and np.hypot(p[0]-x2, p[1]) < lay.ring_radius_m+t+.01
               for j, (x2, zr) in enumerate(zip(lay.ring_x, lay.ring_z))):
            continue
        out.append(((k,), [np.array([p[0], p[1], z_hi])]))
    return out


def plumb_candidates(F, lay, P, nodes, min_clear=.004):
    bw = F.describe(P)
    res = []
    for i in nodes:
        p = P[i]+np.array([0, 0, .01])
        for y_s in (-.03*KS, .03*KS):
            T, arc, far, wrap = ball_points(lay, y_s)
            for seq, W in plumb_routes(lay, p):
                pts = [p]+W+[T]
                if not all(seg_clear(lay, a, b) >= min_clear for a, b in zip(pts[:-1], pts[1:])):
                    continue
                C = np.array([P[i]]+pts+arc+[far, wrap])
                Cp = np.array([P[i]]+pts+final_hook(lay, T))
                L = float(np.linalg.norm(np.diff(C, axis=0), axis=1).sum())
                for s in (1, -1):
                    ex = excursion(lay, Cp, s)
                    if fixture_distance(lay, ex[6:-6]).min() < .0015:
                        continue
                    new_ = np.vstack([P[:i], ex, P[i+1:]])
                    w = F.describe(new_)
                    if w[2] < bw[2]:
                        res.append(dict(tangle=len(signature(new_, lay)), node=int(i), sign=s, Q=[x.tolist() for x in W], y_s=y_s, need=2*L,
                                        word=w[0], b=w[2], C=C.tolist(), plumb=list(seq)))
    best = {}
    for r in res:
        key = (r['node'], str(r['Q']), r['y_s'])
        if key not in best:
            best[key] = r
    return bw, sorted(best.values(), key=lambda r: r['need'])


# corridor offsets for a route's intermediate waypoints (metres): the bight only has to keep its topology
VARIANT_OFFSETS = [(.03, 0, 0), (-.03, 0, 0), (0, .03, 0), (0, -.03, 0), (0, 0, .02), (0, 0, -.02),
                   (.05, 0, 0), (-.05, 0, 0), (0, .05, 0), (0, -.05, 0)]


def route_variants(F, lay, P, cand, offsets=VARIANT_OFFSETS, min_clear=.004, limit=8):
    """The candidate's route with its intermediate waypoints (after the lift above the node, before the
    point over the ball) shifted together by each offset; kept when it still clears the fixture and the
    exact word still loses a b. Used when the robot cannot follow the nominal waypoints."""
    C = np.asarray(cand['C'], float)
    T_idx = len(C)-8
    if T_idx < 3:
        return []
    i = cand['node']
    b0 = F.describe(P)[2]
    out = []
    for d in offsets:
        pts = [C[1]]+[c+np.asarray(d) for c in C[2:T_idx]]+[C[T_idx]]
        if not all(seg_clear(lay, a, b) >= min_clear for a, b in zip(pts[:-1], pts[1:])):
            continue
        Cp = np.array([P[i]]+pts+final_hook(lay, C[T_idx]))
        ex = excursion(lay, Cp, cand['sign'])
        if fixture_distance(lay, ex[6:-6]).min() < .0015:
            continue
        new_ = np.vstack([P[:i], ex, P[i+1:]])
        w = F.describe(new_)
        if w[2] < b0:
            C2 = C.copy()
            C2[2:T_idx] = np.array(pts[1:-1])
            out.append(dict(cand, C=C2.tolist(), word=w[0], b=w[2], variant=list(d),
                            tangle=len(signature(new_, lay))))
            if len(out) >= limit:
                break
    return out
