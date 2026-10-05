"""Exact homotopy class of the closed cord loop in the Orbits complement (infinite-ball model).

Model: post P0 continues upward to infinity (the ball is removed), posts P1..Pn end at their
ring junctions and all posts continue downward below the table (floor attachment). pi_1 of the
complement is free on b (meridian of P0) and m_k (meridian of ring k, first arc after its
junction). A ball pass is exactly where the cord crosses P0's upward continuation, so the
class changes only there.

Oblique view: u=x, v=z cos e + y sin e, depth w=y cos e - z sin e (smaller = nearer viewer).
Generator g_a: pass under arc a from its right to its left (image orientation).
Crossing (over o, under u1->u2): g_u2 = g_o^s g_u1 g_o^-s, s=+1 iff o crosses u from right to left.
Vertex: product over incident arcs in counter-clockwise order, g^{+1} outgoing / g^{-1} incoming, = 1.
"""
import numpy as np

EPS = 0.3


def proj(p):
    p = np.asarray(p, float)
    c, s = np.cos(EPS), np.sin(EPS)
    return np.stack([p[..., 0], p[..., 2]*c+p[..., 1]*s, p[..., 1]*c-p[..., 2]*s], -1)


# ---- free group words: list of (gen, exp) with exp +-1
def red(w):
    out = []
    for g in w:
        if out and out[-1][0] == g[0] and out[-1][1] == -g[1]:
            out.pop()
        else:
            out.append(g)
    return out


def inv(w):
    return [(g, -e) for g, e in reversed(w)]


def mul(*ws):
    r = []
    for w in ws:
        r = red(r+list(w))
    return r


def conj(a, w, s):
    """a^s w a^-s"""
    return mul(a if s > 0 else inv(a), w, inv(a) if s > 0 else a)


def cyc(w):
    w = red(w)
    while len(w) > 1 and w[0][0] == w[-1][0] and w[0][1] == -w[-1][1]:
        w = w[1:-1]
    return w


def canon(w):
    """Canonical cyclic representative (lexicographically minimal rotation)."""
    w = cyc(w)
    if not w:
        return ()
    rots = [tuple(w[i:]+w[:i]) for i in range(len(w))]
    return min(rots)


def fmt(w, names):
    if not w:
        return '1'
    return ' '.join(names[g]+('' if e > 0 else "'") for g, e in w)


class Fixture:
    def __init__(self, lay, ring_pts=720):
        self.lay = lay
        n = lay.ring_count
        self.n = n
        H, D = 20., -20.
        edges = []  # (name, polyline3d)
        edges.append(('P0', np.array([[lay.post_x[0], 0, D], [lay.post_x[0], 0, H]])))
        for k in range(1, n+1):
            J = [lay.post_x[k], 0, lay.ring_z[k-1]]
            edges.append((f'P{k}', np.array([[lay.post_x[k], 0, D], J])))
            th = np.linspace(0, 2*np.pi, ring_pts+1)
            c = lay.ring_x[k-1]
            ring = np.column_stack([c+lay.ring_radius_m*np.cos(th), lay.ring_radius_m*np.sin(th),
                                    np.full(len(th), lay.ring_z[k-1])])
            ring[0] = ring[-1] = J
            edges.append((f'R{k}', ring))
        self.edges = edges
        self.names = ['b']+[f'm{k}' for k in range(1, n+1)]
        self._solve()

    def _seg_cross(self, A, B, C, D):
        """2D segment intersection params (t on AB, s on CD) or None."""
        r, q = B-A, D-C
        den = r[0]*q[1]-r[1]*q[0]
        if abs(den) < 1e-15:
            return None
        w = C-A
        t = (w[0]*q[1]-w[1]*q[0])/den
        s = (w[0]*r[1]-w[1]*r[0])/den
        if 0 <= t < 1 and 0 <= s < 1:
            return t, s
        return None

    def crossings(self, P, Q):
        """All crossings between polylines P,Q (3D). Returns list of (i+t, j+s, depthP, depthQ, dP, dQ)."""
        p, q = proj(P), proj(Q)
        out = []
        # bounding-box prefilter per segment
        pa, pb = p[:-1], p[1:]
        qa, qb = q[:-1], q[1:]
        pmin = np.minimum(pa, pb)[:, :2]; pmax = np.maximum(pa, pb)[:, :2]
        qmin = np.minimum(qa, qb)[:, :2]; qmax = np.maximum(qa, qb)[:, :2]
        for i in range(len(pa)):
            cand = np.flatnonzero((qmin[:, 0] <= pmax[i, 0]) & (qmax[:, 0] >= pmin[i, 0]) &
                                  (qmin[:, 1] <= pmax[i, 1]) & (qmax[:, 1] >= pmin[i, 1]))
            for j in cand:
                r = self._seg_cross(pa[i, :2], pb[i, :2], qa[j, :2], qb[j, :2])
                if r is None:
                    continue
                t, s = r
                dp = pa[i, 2]+t*(pb[i, 2]-pa[i, 2])
                dq = qa[j, 2]+s*(qb[j, 2]-qa[j, 2])
                out.append((i+t, j+s, dp, dq, (pb[i, :2]-pa[i, :2]), (qb[j, :2]-qa[j, :2])))
        return out

    def _solve(self):
        E = self.edges
        name_idx = {nm: i for i, (nm, _) in enumerate(E)}
        # under-crossings on each edge: positions where it passes under another edge
        unders = {i: [] for i in range(len(E))}  # edge -> list of (pos, over_edge, over_pos, sign)
        for i in range(len(E)):
            for j in range(i+1, len(E)):
                for pi, pj, di, dj, vi, vj in self.crossings(E[i][1], E[j][1]):
                    if di > dj:   # i under j
                        s = np.sign(vi[0]*vj[1]-vi[1]*vj[0])  # over (j) crosses under (i) right->left?
                        unders[i].append((pi, j, pj, s))
                    else:
                        s = np.sign(vj[0]*vi[1]-vj[1]*vi[0])
                        unders[j].append((pj, i, pi, s))
        for i in unders:
            unders[i].sort()
        self.unders = unders
        # arcs: edge i, arc index a = number of undercrossings before position
        gen = {}  # (edge, arc) -> word
        gen[(name_idx['P0'], len(unders[name_idx['P0']]))] = [(0, 1)]   # top arc of P0 (above all)
        for k in range(1, self.n+1):
            gen[(name_idx[f'R{k}'], 0)] = [(k, 1)]

        def arc_of(edge, pos):
            return sum(1 for u in unders[edge] if u[0] < pos)

        changed = True
        it = 0
        while changed and it < 1000:
            it += 1
            changed = False
            # crossing propagation, forward and backward along each edge
            for e in range(len(E)):
                us = unders[e]
                for a, (pos, o, opos, s) in enumerate(us):
                    og = gen.get((o, arc_of(o, opos)))
                    if og is None:
                        continue
                    if (e, a) in gen and (e, a+1) not in gen:
                        gen[(e, a+1)] = conj(og, gen[(e, a)], s); changed = True
                    elif (e, a+1) in gen and (e, a) not in gen:
                        gen[(e, a)] = conj(og, gen[(e, a+1)], -s); changed = True
            # junction vertex relations
            for k in range(1, self.n+1):
                pe, re_ = name_idx[f'P{k}'], name_idx[f'R{k}']
                ptop = (pe, len(unders[pe]))
                rout, rin = (re_, 0), (re_, len(unders[re_]))
                if ptop in gen:
                    continue
                if rout in gen and rin in gen:
                    # ccw order of incident edge directions around J in the image
                    J = E[pe][1][-1]
                    dirs = {}
                    ring = proj(E[re_][1])
                    post = proj(E[pe][1])
                    dirs['rout'] = ring[3, :2]-ring[0, :2]      # outgoing from J
                    dirs['rin'] = ring[-4, :2]-ring[-1, :2]     # points away from J along the incoming arc
                    dirs['post'] = post[0, :2]-post[-1, :2]     # away from J (downwards)
                    ang = {kk: np.arctan2(vv[1], vv[0]) for kk, vv in dirs.items()}
                    order = sorted(ang, key=lambda kk: ang[kk])
                    # relation: prod over ccw order of g^{+1} (outgoing) / g^{-1} (incoming) = 1
                    sgn = dict(rout=1, rin=-1, post=-1)
                    # solve for post: rotate so post is last: X * post^-1 = 1 -> post = X
                    i0 = order.index('post')
                    rot = order[i0+1:]+order[:i0]
                    X = []
                    for kk in rot:
                        w = gen[rout] if kk == 'rout' else gen[rin]
                        X = mul(X, w if sgn[kk] > 0 else inv(w))
                    gen[ptop] = X   # post incoming: X * g_post^-1 = 1
                    changed = True
        self.gen = gen
        missing = [(E[e][0], a) for e in range(len(E)) for a in range(len(unders[e])+1) if (e, a) not in gen]
        if missing:
            raise RuntimeError(f'unsolved arcs {missing}')
        self.arc_of = arc_of

    def word(self, pts, close=True):
        """Reduced (cyclic) word of the closed cord loop."""
        P = np.asarray(pts, float)
        if close:
            P = np.vstack([P, P[:1]])
        events = []
        for e, (nm, poly) in enumerate(self.edges):
            for pc, pf, dc, df, vc, vf in self.crossings(P, poly):
                if df < dc:   # fixture in front, cord passes under arc
                    a = self.arc_of(e, pf)
                    # cord crosses arc from right to left?  (arc dir vf, cord dir vc)
                    s = np.sign(vf[0]*vc[1]-vf[1]*vc[0])
                    g = self.gen[(e, a)]
                    events.append((pc, g if s > 0 else inv(g)))
        events.sort(key=lambda x: x[0])
        w = []
        for _, g in events:
            w = mul(w, g)
        return cyc(w)

    def describe(self, pts):
        w = self.word(pts)
        return fmt(w, self.names), len(w), sum(1 for g, e in w if g == 0)
