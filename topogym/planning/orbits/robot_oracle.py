"""Robot-aware word-guided executor: every grasp point and carried path is ALOHA IK/collision checked.

A = left arm, B = right arm. Single-node carry; lasso hook beside the ball at its equator.
Derived from auto.py (rope-only executor).

Original auto.py notes:

Loop: search the current physical state for fresh-bight ball passes that delete one b in the exact
infinite-ball word; execute the shortest candidate (bight along its route, two-point spread over
the stopper ball, wrap P0 just below it); keep it only if the physical word really drops, otherwise
restore the checkpoint and try the other orientation / next candidate.
"""
import argparse
import json
import shutil
from itertools import islice, product
import sys
import time
from pathlib import Path

import numpy as np

from .rope_sim import Oracle, SCALE, KS, FROM_TASK  # noqa: E402
from .render import snap_oracle  # noqa: E402
from .invariant import Fixture  # noqa: E402
from .topology import signature, fmt as sfmt  # noqa: E402
from .bight_search import route_excursion, fixture_distance, waypoint_sets  # noqa: E402
from .routes import aperture_center  # noqa: E402
from . import routes as direct  # noqa: E402
from .aloha_ik import AlohaIK, approach_rotation  # noqa: E402
from .ik_audit import APPROACH, track, _track, rich_approaches, resting  # noqa: E402
from .local_contract import MAX_SEGMENT_STRETCH, MAX_GRIP_ERROR_M, MAX_IK_STEP_RAD


def search(o, F, nodes=None, max_route=None):
    P = o.points(); lay = o.lay
    bw = F.describe(P)
    wps, _ = waypoint_sets(lay)
    nodes = nodes if nodes is not None else range(4, len(P)-4, 2)
    found = []
    for i in nodes:
        for W in [()] + [(w,) for w in wps]:
            for s in (1, -1):
                e, C = route_excursion(lay, P[i], s, W)
                cl = fixture_distance(lay, e[8:-8]).min()
                if cl < .0015:
                    continue
                w = F.describe(np.vstack([P[:i], e, P[i+1:]]))
                if w[2] < bw[2]:
                    Lr = float(np.linalg.norm(np.diff(C, axis=0), axis=1).sum())
                    if max_route is None or Lr <= max_route:
                        found.append(dict(node=int(i), sign=s, via=[list(map(float, x)) for x in W], route=Lr,
                                          clear=float(cl), word=w[0], b=w[2], C=C))
    for f in found:
        f['need'] = executed_path(lay, P[f['node']], f, 1)[2]
    best = {}
    for f in found:
        key = (f['node'], tuple(map(tuple, f['via'])))
        if key not in best:
            best[key] = f
    return bw, sorted(best.values(), key=lambda f: f['need'])


def staircase(lay, start, y_s):
    """Waypoints from start (above any ring containing its xy) to just right of the ball, passing
    above every ring junction in between; stays above all rings, so homotopic to a high carry."""
    p0 = lay.post_x[0]
    top = lay.ball_z+lay.ball_radius_m
    t = lay.ring_tube_radius_m
    wp = []
    x = start[0]
    for j in range(len(lay.ring_z), 0, -1):          # lowest ring first
        xj = lay.post_x[j]
        if p0+.02 < xj < x+.005:
            wp.append([xj+.012, y_s, lay.ring_z[j-1]+t+.02])
    wp.append([p0+.03, y_s, top+.015])
    # monotone in z
    out = []
    zc = start[2]
    for w in wp:
        zc = max(zc, w[2])
        out.append([w[0], w[1], zc])
    return out


def rise_clear(lay, p):
    """Height above every ring whose footprint contains the xy of p (vertical rise target)."""
    z = p[2]
    for cx, zr in zip(lay.ring_x, lay.ring_z):
        if np.hypot(p[0]-cx, p[1]) < lay.ring_radius_m+lay.ring_tube_radius_m+.004 and zr+.02 > z:
            z = max(z, zr+lay.ring_tube_radius_m+.016)
    return z


def executed_path(lay, p_node, cand, orient):
    """Waypoints actually followed by the bight apex, and the cord length the doubled bight needs."""
    p0 = lay.post_x[0]
    bz, br = lay.ball_z, lay.ball_radius_m
    neck = (lay.ring_z[0]+lay.ring_tube_radius_m+bz-br)/2
    top = bz+br
    C = np.asarray(cand['C'])
    nvia = len(cand['via'])
    if nvia:
        idx = int(np.argmin(np.linalg.norm(C-np.asarray(cand['via'][-1]), axis=1)))
        head = [np.asarray(c) for c in C[1:idx+1]]
    else:
        head = [np.asarray(C[1])]
    last = head[-1]
    z1 = rise_clear(lay, last)
    path = head+[np.array([last[0], last[1], z1])]
    y_s = last[1] if abs(last[1]) > .02 else (.035 if orient > 0 else -.035)
    path += [np.array(w) for w in staircase(lay, path[-1], y_s)]
    L = float(np.linalg.norm(np.diff(np.vstack([p_node]+path), axis=0), axis=1).sum())
    # over the ball and down to the neck on the far side, back to the wrap point
    L_over = abs(path[-1][0]-(p0-.035))+abs(path[-1][2]-neck)+.05
    return path, L, 2*(L+L_over)


def execute(o, cand, orient, tag, k=8):
    lay = o.lay
    p0 = lay.post_x[0]
    bz, br = lay.ball_z, lay.ball_radius_m
    neck = (lay.ring_z[0]+lay.ring_tube_radius_m+bz-br)/2
    top = bz+br
    i = cand['node']
    for g in 'ABCD':
        o.release(g)
    path, L, _ = executed_path(lay, o.points()[i], cand, orient)
    # carry the bight with two grasps side by side (i-k, i+k); the apex hangs between them
    a, b = i-k, i+k
    o.grasp('A', a)
    o.grasp('B', b)
    off = np.array([0, .007*orient, 0])
    o.move(f'{tag}_bight', {'A': [p+off for p in path], 'B': [p-off for p in path]}, max(3., L/.04))
    if getattr(o, 'fixture', None) is not None:
        P = o.points()
        b0 = o.fixture.describe(P)[2]
        pred = []
        for s_ in (1, -1):
            e, _ = route_excursion(lay, P[i], s_, ())
            pred.append(o.fixture.describe(np.vstack([P[:i], e, P[i+1:]]))[2])
        if min(pred) >= b0:
            raise RuntimeError(f'{tag}: bight mismatch, predicted b after hook {pred} vs {b0}')
    ya, yb = .028*orient, -.028*orient
    pa, pb = o.grip_pos('A'), o.grip_pos('B')
    zc = max(pa[2], pb[2], top+.01)
    o.move(f'{tag}_spread', {'A': [pa[0], ya, zc], 'B': [pb[0], yb, zc]}, 2.)
    o.move(f'{tag}_over', {'A': [[p0-.028, 1.1*ya, zc], [p0-.032, 1.1*ya, neck]],
                           'B': [[p0-.028, 1.1*yb, zc], [p0-.032, 1.1*yb, neck]]}, 3.)
    o.move(f'{tag}_wrap', {'A': [p0+.012, ya, neck], 'B': [p0+.012, yb, neck]}, 2.)
    o.release('A'); o.release('B')
    o.settle(.8, f'{tag}_settle')


SIDE = {'A': 'left', 'B': 'right'}
GRIP = {'left': 'A', 'right': 'B'}


class RobotCheck:
    def __init__(self, lay):
        self.lay = lay
        self.K = AlohaIK(lay)
        self.cache = {}
        self.episodes = []

    def reach(self, side, p):
        key = (side, tuple(np.round(p, 3)))
        if key not in self.cache:
            K = self.K
            hit = None
            for app in APPROACH[side]:
                for roll in (0, 90):
                    q, e1, e2 = K.solve(side, p, approach_rotation(side, app, roll), K.home)
                    if e1 <= 2e-3 and e2 <= 3e-2 and not K.collisions(q, sides=(side,)):
                        hit = q[K.qadr[side]].copy()
                        break
                if hit is not None:
                    break
            self.cache[key] = hit
        return self.cache[key]

    def path(self, side, pts, rich=False):
        pts = np.asarray(pts, float)
        r = self._path(side, pts, rich)
        if not r['ok'] and resting(self.lay, pts[0]):
            # Pinch the supported cord's upper half, within its actual radius.
            for dz in (min(.0015, self.lay.cord_radius_m/2), min(.003, self.lay.cord_radius_m)):
                p2 = pts.copy()
                p2[0, 2] += dz
                r2 = self._path(side, p2, rich)
                if r2['ok']:
                    return r2
        return r

    def _path(self, side, pts, rich=False):
        dense = [pts[0]]
        idx = [0]
        for a_, b_ in zip(pts[:-1], pts[1:]):
            n = max(1, int(np.ceil(np.linalg.norm(b_-a_)/.012)))
            dense += [a_+(b_-a_)*t for t in np.linspace(0, 1, n+1)[1:]]
            idx.append(len(dense)-1)
        r = track(self.K, side, np.array(dense), self.K.home, approaches=rich_approaches(side) if rich else None)
        r['wp'] = idx
        return r

    def path_options(self, side, pts, rich=False):
        """Every complete track of the waypoint path, one per feasible starting orientation."""
        pts = np.asarray(pts, float)
        dense = [pts[0]]
        idx = [0]
        for a_, b_ in zip(pts[:-1], pts[1:]):
            n = max(1, int(np.ceil(np.linalg.norm(b_-a_)/.012)))
            dense += [a_+(b_-a_)*t for t in np.linspace(0, 1, n+1)[1:]]
            idx.append(len(dense)-1)
        rots = [(app, roll, approach_rotation(side, app, roll)) for app in (rich_approaches(side) if rich else APPROACH[side])
                for roll in (0, 90)]
        for start in range(len(rots)):
            r = _track(self.K, side, np.array(dense), self.K.home, MAX_IK_STEP_RAD, rots, start)
            if r['ok']:
                r['wp'] = idx
                yield r

    def joint(self, rl, rr, n=12, off=None):
        """Both arms moving through their waypoint paths in lockstep: arm-arm and arm-fixture contacts.
        off: {side: first waypoint index of the shared segment} for a track that starts earlier."""
        K = self.K
        qq = K.home.copy()
        off = off or {}
        for u in np.linspace(0, 1, n):
            for side, r in (('left', rl), ('right', rr)):
                w = np.asarray(r['wp'][off.get(side, 0):], float)
                j = int(round(np.interp(u*(len(w)-1), np.arange(len(w)), w)))
                qq[K.qadr[side]] = r['q'][min(j, len(r['q'])-1)]
            c = K.collisions(qq)
            if c:
                return c[:2]
        return []


class _FreeK:
    """Kinematics stand-in for the object-level (armless) mode: no arm, nothing to collide."""
    PAD = .012

    def __init__(self):
        self.home = np.zeros(12)
        self.qadr = {'left': list(range(6)), 'right': list(range(6, 12))}

    def collisions(self, q, sides=('left', 'right'), margin=.0):
        return []


class FreeCheck:
    """Object-level mode: every gripper path is accepted (virtual point grippers). The rope physics,
    guards and the exact word still decide; robot IK is transferred afterwards."""
    def __init__(self, lay):
        self.lay, self.K, self.episodes = lay, _FreeK(), []

    def reach(self, side, p):
        return np.zeros(6)

    def path(self, side, pts, rich=False):
        n = len(pts)
        return dict(ok=True, q=np.zeros((max(n, 1), 6)), wp=list(range(n)))

    def path_options(self, side, pts, rich=False):
        yield self.path(side, pts)

    def joint(self, rl, rr, n=12, off=None):
        return []


def route_holes(lay, cand):
    """Ring apertures crossed by the bight's rise (node -> lift -> Q -> T), e.g. ['R2u']. The robot
    cannot carry a bight through an aperture: the gripper's 15 cm finger rail sits 6 cm behind the TCP."""
    C = np.asarray(cand['C'])
    n = len(C)-7                 # C = node, rise..., T, 5 arc points, far, wrap
    out = []
    for a_, b_ in zip(C[:n-1], C[1:n]):
        for k, (cx, z) in enumerate(zip(lay.ring_x, lay.ring_z)):
            if (a_[2]-z)*(b_[2]-z) < 0:
                p = a_+(z-a_[2])/(b_[2]-a_[2])*(b_-a_)
                if np.hypot(p[0]-cx, p[1]) < lay.ring_radius_m:
                    out.append(f"R{k+1}{'u' if b_[2] > a_[2] else 'd'}")
    return out


def hook_targets(lay, y=None):
    p0 = lay.post_x[0]
    bz, br = lay.ball_z, lay.ball_radius_m
    y = br+.0146 if y is None else y
    top = bz+br
    neck = (lay.ring_z[0]+lay.ring_tube_radius_m+bz-br)/2
    # pull back at the neck below the ball: pulling at the equator wedges the cord into the ball/post corner
    return dict(over=(p0-.012, top+.012), lasso=(p0-.008, bz), pull=(p0+.015, neck), y=y, top=top)


def execute_robot(o, rc, cand, orient, tag, k2s=None, H=None):
    """Single-arm carry of the bight apex along the predicted route (IK-checked); the other arm takes the
    strand k2 nodes from the apex (first k2 in k2s that is IK-feasible for both arms); lasso over the ball down to its equator and pull back below it."""
    lay = o.lay
    i = cand['node']
    for g in 'ABCD':
        o.release(g)
    P = o.points()
    C = np.asarray(cand['C'])
    T_idx = len(C)-5-3
    rise = [np.asarray(c) for c in C[1:T_idx+1]]
    H = H or hook_targets(lay)
    carrier = None
    order = ['left', 'right'] if P[i][1] >= 0 else ['right', 'left']
    # dense orientation set (with in-place reorientations) and a few lift heights above the ball
    for dz in (.045, .03, .07):
        T_hi = np.array([rise[-1][0], rise[-1][1], H['top']+dz])
        path = rise+[T_hi]
        for side in order:
            if rc.path(side, [P[i]]+path, rich=True)['ok']:
                carrier = side
                break
        if carrier:
            break
    if carrier is None:
        raise RuntimeError(f'{tag}: ik_skip carry node {i}')
    g = GRIP[carrier]
    o.grasp(g, i)
    L = float(np.linalg.norm(np.diff(np.vstack([P[i]]+path), axis=0), axis=1).sum())
    o.move(f'{tag}_bight', {g: path}, max(3., L/.04))
    hook_phase(o, rc, carrier, i, orient, tag, [P[i]]+path, T_hi, H, k2s)


def execute_assisted(o, rc, cand, orient, tag, k2s=None, H=None):
    """In-place rise through the lowest ring with a helper: the cord lying on the base under a ring is too
    deep for a gripper reaching down through the aperture (~10 cm below the ring plane at most) and a tilted
    grasp from the side cannot rise through it. The helper arm takes the cord just outside the aperture and
    lifts it to just under the ring (the stretch under the ring rises with it); the carrier reaches down
    through the aperture, takes the raised stretch next to node i and rises straight up; the helper lets go;
    then the hook."""
    lay = o.lay
    K = rc.K
    i = cand['node']
    for g_ in 'ABCD':
        o.release(g_)
    P = o.points()
    C = np.asarray(cand['C'])
    T_idx = len(C)-8
    rise = [np.asarray(c) for c in C[1:T_idx+1]]
    H = H or hook_targets(lay)
    k = cand['plumb'][-1]
    cx, zr, t = lay.ring_x[k-1], lay.ring_z[k-1], lay.ring_tube_radius_m
    rim = lay.ring_radius_m-t-.012
    z_help = zr-t-.03
    Qz = rise[0][2]
    dz_free = lambda p_: min(.25, max(.10, max(lay.ring_z)+t+.06-p_[2]))
    import tempfile
    tmp_ = Path(tempfile.mkdtemp())
    o.save(tmp_/'pre')
    mark_ = (len(o.frames), len(o.log))
    tried = 0
    diag = []
    try:
        # helper grasps: just outside the aperture (vertical lift to under the ring) or inside it, near node i
        # (a tilted grasp from the side, lifted as high as the ring above allows) -- a slack cord only rises
        # next to the lifted point
        hs = [(i+d, False) for d in (8, -8, 12, -12, 16, -16)]+[(i+d, True) for d in (12, -12, 18, -18)]
        for h, outside in hs:
            if not 0 <= h < o.n or tried >= 4:     # each executed lift costs seconds of physics: at most 4
                continue
            r_ = np.hypot(P[h][0]-cx, P[h][1])
            if outside != (r_ >= lay.ring_radius_m+t+.01):
                continue
            ph = P[h]
            r_h = None
            for helper in ('left', 'right'):
                carrier = 'right' if helper == 'left' else 'left'
                for zl in ((z_help,) if outside else (zr-t-.045, zr-t-.06, zr-t-.075, zr-t-.09)):
                    lift = np.array([ph[0], ph[1], zl])
                    pre_ = [ph+np.array([0, 0, dz_free(ph)])] if outside else []
                    r_h = rc.path(helper, pre_+[ph, lift], rich=True)
                    if r_h['ok']:
                        break
                if not r_h['ok']:
                    continue
                if tried:
                    o.restore(tmp_/'pre')
                    del o.frames[mark_[0]:]; del o.log[mark_[1]:]
                tried += 1
                gh, gc = GRIP[helper], GRIP[carrier]
                o.grasp(gh, h)
                o.move(f'{tag}_prop', {gh: [lift]}, 2.5)
                o.settle(.5, f'{tag}_prop_hold')
                Pc = o.points()
                qq = K.home.copy()
                qq[K.qadr[helper]] = r_h['q'][-1]
                # within the carrier's reach: a gripper gets at most ~9 cm below the ring plane through it
                js = [j for j in range(max(0, i-12), min(o.n, i+13))
                      if np.hypot(Pc[j][0]-cx, Pc[j][1]) < rim and np.linalg.norm(Pc[j]-Pc[h]) >= .035
                      and Pc[j][2] > zr-t-.09]
                js.sort(key=lambda j: (-round(float(Pc[j][2]), 3), abs(j-i)))
                plan = None
                diag.append(dict(h=h, helper=helper[0], n=len(js), ztop=round(float(Pc[js[0]][2]), 3) if js else None,
                                 ik=0, clash=0))
                for j in js[:4]:
                    for dz in (.045,):
                        T_hi = np.array([rise[-1][0], rise[-1][1], H['top']+dz])
                        path = [np.array([Pc[j][0], Pc[j][1], Qz])]+rise[1:]+[T_hi]
                        above = Pc[j]+np.array([0, 0, dz_free(Pc[j])])
                        opts_ = list(islice(rc.path_options(carrier, [above, Pc[j]]+path, rich=True), 4))
                        diag[-1]['ik' if not opts_ else 'clash'] += 1
                        for rt in opts_:
                            clear = True
                            for q_ in rt['q']:
                                qq[K.qadr[carrier]] = q_
                                if K.collisions(qq):
                                    clear = False
                                    break
                            if clear:
                                plan = (j, path, T_hi)
                                break
                        if plan:
                            break
                    if plan:
                        break
                if plan is None:
                    continue
                j, path, T_hi = plan
                o.grasp(gc, j)
                L = float(np.linalg.norm(np.diff(np.vstack([Pc[j]]+path), axis=0), axis=1).sum())
                o.move(f'{tag}_bight', {gc: path}, max(3., L/.04))
                o.release(gh)
                o.settle(.5, f'{tag}_prop_release')
                hook_phase(o, rc, carrier, j, orient, tag, [Pc[j]]+path, T_hi, H, k2s)
                return
    finally:
        shutil.rmtree(tmp_, ignore_errors=True)
    raise RuntimeError(f'{tag}: ik_skip assisted rise node {i} ({tried} helper lifts tried) {diag[:4]}')


def hook_phase(o, rc, carrier, i, orient, tag, prefix, T_hi, H, k2s=None):
    """Carrier holds the bight apex (node i) at T_hi after following the waypoint list prefix.

    1. carrier moves the apex 4.5 cm out to its own side (and up if needed);
    2. the other arm takes the strand k2 nodes from the apex (two strands of a bight lie ~1 cm apart,
       too close for two grippers whose finger rails are 15 cm wide); both open the bight sideways;
    3. the carrier lets the apex go and takes the other strand k3 nodes from the apex, so the cord
       between the grasps (k2+k3 nodes) is long enough to go half way round the ball unstretched;
    4. both lasso the ball down to its equator and pull back below it; release.
    """
    lay = o.lay
    g = GRIP[carrier]
    free = 'right' if carrier == 'left' else 'left'
    gf = GRIP[free]
    if getattr(o, 'fixture', None) is not None:
        Pc = o.points()
        b0 = o.fixture.describe(Pc)[2]
        pred = []
        for s_ in (1, -1):
            e, _ = route_excursion(lay, Pc[i], s_, ())
            pred.append(o.fixture.describe(np.vstack([Pc[:i], e, Pc[i+1:]]))[2])
        if min(pred) >= b0:
            raise RuntimeError(f'{tag}: bight mismatch, predicted b after hook {pred} vs {b0}')
    sgn = -1 if orient > 0 else 1                 # node-index direction of the strand for the left (+y) arm
    sf = sgn if free == 'left' else -sgn          # direction of the free arm's strand from the apex
    cr, br, pr = lay.cord_radius_m, lay.ball_radius_m, lay.post_radius_m
    y = H['y']
    pull = H['pull'] or H['lasso']
    L_loop = max(np.pi*(br+cr)+2*max(0., y-br-cr), 2*np.hypot(pull[0]-lay.post_x[0], y)+np.pi*(pr+cr))
    k_tot = int(np.ceil(1.15*L_loop/float(np.mean(o._rest))))
    k2s = list(k2s) if k2s is not None else list(range(10, 22, 2))
    ys = {'left': y, 'right': -y}

    def wps(side, start, zc, z_over=None):
        # cross behind the ball high enough that the sagging loop between the grasps clears its top
        yy = ys[side]
        z_over = H['over'][1] if z_over is None else max(H['over'][1], z_over)
        return [start, [start[0], yy, max(zc, z_over)], [H['over'][0], yy, z_over],
                [H['lasso'][0], yy, H['lasso'][1]], [pull[0], yy, pull[1]]]
    def opts(side, pts):
        # at most 4 complete tracks: the standard orientation set first, the dense one if that has none
        return list(islice(rc.path_options(side, pts), 4)) or list(islice(rc.path_options(side, pts, rich=True), 4))
    why = []
    found = None
    for dz in (.02, .05, .08):
        aside = T_hi+np.array([0, .045 if carrier == 'left' else -.045, dz])
        if not rc.path(carrier, [T_hi, aside])['ok']:
            why.append(f'dz{dz}:aside')
            break
        o.move(f'{tag}_aside', {g: [aside]}, 2.)
        Pc = o.points()
        for k2 in k2s:
            nf = i+sf*k2
            if not 0 <= nf < o.n:              # the strand would run past the cord's end at the handle
                continue
            zc = max(Pc[nf][2], Pc[i][2], H['top']+.012)
            pf, pc_ = wps(free, Pc[nf], zc), wps(carrier, Pc[i], zc)
            # open only as far as the k2 nodes of cord between the grasps allow (80 %: slack keeps grips from slipping)
            d_max = .8*k2*float(np.mean(o._rest))
            dx = Pc[nf][0]-Pc[i][0]
            half = min(y, np.sqrt(max(0., d_max**2-dx**2))/2)
            pf[1] = [Pc[nf][0], half if free == 'left' else -half, zc]
            pc_[1] = [Pc[i][0], half if carrier == 'left' else -half, zc]
            # step 2 only (grasp + open sideways): carrier continuous from the carry, free arm fresh
            # (at most 4 complete tracks per arm; the carrier is re-tracked from the top of its carry
            # only -- the carry itself was checked already -- so a failing k2 costs seconds, not minutes)
            opts_f = opts(free, pf[:2])
            opts_c = opts(carrier, [prefix[-1], aside, pc_[1]]) if opts_f else []
            if not (opts_f and opts_c):
                why.append(f'dz{dz}/{k2}:ik_' + ('c' if opts_f else 'f'))
                continue
            n_c = 1
            pair = lambda c_, f_: (c_, f_) if carrier == 'left' else (f_, c_)
            if any(not rc.joint(*pair(c_, f_), off={carrier: n_c}) for c_ in opts_c for f_ in opts_f):
                found = (k2, nf, zc, pf, pc_)
                break
            why.append(f'dz{dz}/{k2}:arms')
        if found:
            break
    if not found:
        raise RuntimeError(f'{tag}: ik_skip hook open apex {i} ' + ' '.join(why[-6:]))
    k2, nf, zc, pf, pc_ = found
    gs = dict(guard_stretch=MAX_SEGMENT_STRETCH, guard_err=MAX_GRIP_ERROR_M)
    o.grasp(gf, nf)
    o.move(f'{tag}_open', {gf: pf[1], g: pc_[1]}, 1.5, **gs)
    # step 3: carrier swaps from the apex to the other strand
    o.release(g)
    o.settle(1.5, f'{tag}_swap')     # the free arm holds the cord; time for the carrier to reach its new grasp
    Pc = o.points()
    found = None
    for k3 in range(max(k_tot-k2, 6), max(k_tot-k2, 6)+12, 2):
        nc = i-sf*k3
        if not 0 <= nc < o.n:
            continue
        if np.linalg.norm(Pc[nc]-Pc[nf]) < .06:     # two grippers on the cord at once: keep them apart
            continue
        half = (k2+k3)*float(np.mean(o._rest))/2
        z_over = H['top']+np.sqrt(max(0., half**2-y**2))+.01
        pc2 = wps(carrier, Pc[nc], zc, z_over)
        pf_ = wps(free, Pc[nf], zc, z_over)
        pf2 = [pf[1]]+pf_[1:]                     # free arm rises from its open pose while the carrier regrasps
        opts_c = opts(carrier, pc2)
        opts_f = opts(free, pf2) if opts_c else []
        if not (opts_c and opts_f):
            why.append(f'k3 {k3}:ik_' + ('f' if opts_c else 'c'))
            continue
        pair = lambda c_, f_: (c_, f_) if carrier == 'left' else (f_, c_)
        if any(not rc.joint(*pair(c_, f_)) for c_ in opts_c for f_ in opts_f):
            found = (nc, pc2, pf2)
            break
        why.append(f'k3 {k3}:arms')
    if not found:
        raise RuntimeError(f'{tag}: ik_skip hook swap apex {i} ' + ' '.join(why[-6:]))
    nc, pc2, pf2 = found
    o.grasp(g, nc)
    o.move(f'{tag}_regrasp', {g: pc2[1], gf: pf2[1]}, 1.5, **gs)
    tgt = {gf: pf2, g: pc2}
    o.move(f'{tag}_over', {gg: w[2] for gg, w in tgt.items()}, 2.5, **gs)
    o.move(f'{tag}_lasso', {gg: w[3] for gg, w in tgt.items()}, 2.5, **gs)
    if H['pull'] is not None:
        o.move(f'{tag}_pull', {gg: w[4] for gg, w in tgt.items()}, 2., **gs)
    o.release('A'); o.release('B')
    o.settle(.8, f'{tag}_settle')

def execute_thread(o, rc, cand, orient, tag, k2s=None, H=None, dj=(4, -4, 6, -6, 8, -8)):
    """Plumb route with a hand-over at its last ring aperture: the side arm drags node i below that
    aperture's centre and lifts it as high as it can under the ring; the top arm reaches down through the
    aperture, takes a neighbouring node, rises vertically through it and on to the ball; then hook.
    Through two apertures the side arm first carries the node up through the lower ring itself (the
    gripper fits through a 21.6 cm aperture) into the gap under the upper ring, then hands over there."""
    lay = o.lay
    i = cand['node']
    for g_ in 'ABCD':
        o.release(g_)
    P = o.points()
    C = np.asarray(cand['C'])
    T_idx = len(C)-8
    H = H or hook_targets(lay)
    # C = node, pre-path (lift, optional pre-lift, lower-aperture traversal), W0 under the last aperture,
    # W1 above it, T over the ball, hook points
    pre = [np.asarray(c) for c in C[1:T_idx-2]]
    W0, W1 = C[T_idx-2], C[T_idx-1]
    rest = [np.asarray(C[T_idx])]
    if len(cand['plumb']) > 2:
        raise RuntimeError(f'{tag}: ik_skip thread through {len(cand["plumb"])} apertures')
    k = cand['plumb'][-1]
    z_top = lay.ring_z[k-1]-lay.ring_tube_radius_m-.012
    T_hi = np.array([C[T_idx][0], C[T_idx][1], H['top']+.045])
    # each arm in turn as the side arm (highest lift first); the top arm takes a neighbouring node and
    # rises through the aperture. The final point above the ball may shift in y on the right of P0's
    # axis (it never crosses P0's upward extension, so the word is unchanged).
    # the side arm may also carry node i across to the far side of the aperture at that height, so the
    # cord back to where it came from spans the aperture centre (where the top arm reaches deepest)
    far = -np.sign(P[i][1] if abs(P[i][1]) > 1e-3 else 1.)*.035*KS
    lifts = []
    for side in ('left', 'right'):
        # cheap pre-check: the drag itself at the node's height must be possible (dense orientation set;
        # nodes tucked under a ring tube are often reachable only with it)
        if not rc.path(side, [P[i], *pre, W0], rich=True)['ok']:
            continue
        # push-through: the gripper (15 cm finger rail) fits through the aperture, so with its beak up the side
        # arm may push the bight 6-10 cm above the ring; the top arm then takes a strand in the open above
        # the ring instead of reaching down into the aperture (out of reach under a high ring)
        for z_s in (lay.ring_z[k-1]+.10, lay.ring_z[k-1]+.08, lay.ring_z[k-1]+.06):
            Hp = np.array([W0[0], W0[1], z_s])
            r = rc.path(side, [P[i], *pre, W0, Hp], rich=True)
            if r['ok']:
                lifts.append((z_s, side, Hp, r))
                break
        for ys in (W0[1], 0., far/2, far):
            for z_s in np.arange(z_top, W0[2]-1e-9, -.01):
                Hp = np.array([W0[0], ys, z_s])
                r = rc.path(side, [P[i], *pre, W0, [W0[0], W0[1], z_s], Hp], rich=True)
                if r['ok']:
                    lifts.append((z_s, side, Hp, r))
                    break
    if not lifts:
        raise RuntimeError(f'{tag}: ik_skip thread side arm node {i}')
    K = rc.K
    W1 = np.asarray(W1, float)
    plans = []
    for z_s, side_s, Hs, rs in sorted(lifts, key=lambda x: (-round(x[0], 3), abs(x[2][1]-far))):
        push = z_s > lay.ring_z[k-1]
        if any(p_[0] == side_s and (p_[2][2] > lay.ring_z[k-1]) == push for p_ in plans):
            continue                    # per arm assignment: the push-through and the highest lift under the ring
        plan = None
        side_t = 'right' if side_s == 'left' else 'left'
        qq = K.home.copy()
        qq[K.qadr[side_s]] = rs['q'][-1]
        # top arm: grasp a neighbour of node i next to the side arm and rise vertically there. The cord
        # leaves the side grasp back towards where node i came from, so estimate neighbours along that way
        u = np.array([P[i][0]-Hs[0], P[i][1]-Hs[1], 0.])
        u /= max(np.linalg.norm(u), 1e-9)
        # the executed hand-over keeps the grippers >= 3.5 cm apart (prefer ~8 cm): the neighbour hangs below
        # and beside the side grasp along the cord, so probe those offsets here too
        offs = [u*d_+np.array([0, 0, dz_]) for d_ in (.06, .07, .05, .08, .04) for dz_ in (-.012, -.03, -.05)] + \
            [np.array([0, 0, -dz_]) for dz_ in (.035, .045)] + \
            [np.array([0, 0, -dz_]) for dz_ in (.06, .08)] + \
            [np.array([dx_, dy_, dz_]) for dx_, dy_ in ((0, .06), (0, -.06), (.06, 0), (-.06, 0), (0, .04), (0, -.04),
                                                       (.04, 0), (-.04, 0)) for dz_ in (-.015, -.04)]
        ok_t = False
        for off in offs:
            g0 = Hs+off
            for rt in rc.path_options(side_t, [g0, np.array([g0[0], g0[1], max(W1[2], g0[2]+.01)])], rich=True):
                qq[K.qadr[side_t]] = rt['q'][0]
                if not K.collisions(qq):
                    ok_t = True
                    break
            if ok_t:
                break
        if not ok_t:
            continue
        # rest of the route from W1 to above the ball: by the top arm, or after a hand-over in the open to
        # the (now free) side arm. The top point may shift in y right of P0's axis (same route class).
        for (yv, via), dz in product([(T_hi[1], rest), (0., rest[:-1]), (-T_hi[1], rest[:-1]), (0., rest)],
                                     (0., -.015, .025)):
            Th = np.array([T_hi[0], yv, T_hi[2]+dz])
            for carrier in (side_t, side_s):
                if rc.path(carrier, [W1]+via+[Th], rich=True)['ok']:
                    plan = (side_s, side_t, Hs, rs, Th, via, carrier)
                    break
            if plan:
                break
        if plan:
            plans.append(plan)
    if not plans:
        raise RuntimeError(f'{tag}: ik_skip thread top arm near node {i} (lifts ' +
                           ' '.join(f'{s_[1][0]}{s_[0]:.3f}' for s_ in lifts) + ')')
    # the hand-over depends on how the cord actually hangs from the side grasp: execute each arm
    # assignment in turn (state, frames and log rolled back between them) until the top arm reaches it
    import tempfile
    tmp_ = Path(tempfile.mkdtemp())
    o.save(tmp_/'pre')
    mark_ = (len(o.frames), len(o.log))
    try:
        for n_plan, plan in enumerate(plans):
            last_plan = n_plan == len(plans)-1
            if n_plan:
                o.restore(tmp_/'pre')
                del o.frames[mark_[0]:]; del o.log[mark_[1]:]
            try:
                r_ = _thread_handover(o, rc, cand, orient, tag, i, plan, pre, W0, W1, C, T_idx, k, H, k2s, last_plan)
            except RuntimeError:
                if last_plan:
                    raise
                continue                # a guard or IK dead end in this assignment: try the other one
            if r_ != 'next':
                return
    finally:
        shutil.rmtree(tmp_, ignore_errors=True)


def _thread_handover(o, rc, cand, orient, tag, i, plan, pre, W0, W1, C, T_idx, k, H, k2s, last_plan):
    """Execute one arm assignment of execute_thread from the drag on. Returns 'next' when the top arm
    cannot take the cord and another assignment remains to be tried."""
    lay = o.lay
    K = rc.K
    side_s, side_t, Hs, rs, T_hi, rest, carrier = plan
    gs, gt = GRIP[side_s], GRIP[side_t]
    o.grasp(gs, i)
    drag = [*pre, W0, [W0[0], W0[1], Hs[2]], Hs]
    drag = [d_ for n_, d_ in enumerate(drag) if n_ == 0 or np.linalg.norm(np.asarray(d_)-np.asarray(drag[n_-1])) > 1e-6]
    o.move(f'{tag}_drag', {gs: drag}, 4.+2.*(len(cand['plumb'])-1))
    Pc = o.points()
    qq = K.home.copy()
    qq[K.qadr[side_s]] = rs['q'][-1]
    # top arm: a neighbour inside the aperture footprint (it may hang below the side grasp), at least 3.5 cm
    # (preferably ~8 cm) from the side gripper so the two grippers never touch
    rim = lay.ring_radius_m-lay.ring_tube_radius_m-.012
    js = [i+d for d in range(-24, 25, 2) if d and 0 <= i+d < o.n]
    js = [j_ for j_ in js if np.hypot(Pc[j_][0]-lay.ring_x[k-1], Pc[j_][1]) < rim
          and np.linalg.norm(Pc[j_]-Pc[i]) >= .035]          # both grippers on the cord: keep them apart
    # (preferably ~8 cm; closer grasps are kept only when the top arm's whole track clears the side arm,
    # checked sample by sample below -- under a high ring the top arm cannot reach far down the strand)
    js.sort(key=lambda j_: abs(float(np.linalg.norm(Pc[j_]-Pc[i]))-.08))
    # the top arm reaches at most ~9 cm below the ring plane through the aperture; at most 10 tries
    js = [j_ for j_ in js if Pc[j_][2] > lay.ring_z[k-1]-lay.ring_tube_radius_m-.09][:10]
    # keep only neighbours from which this vertical bight still deletes a b in the actual cord shape
    if getattr(o, 'fixture', None) is not None:
        b0 = o.fixture.describe(Pc)[2]
        T_pt = C[T_idx]
        keep = []
        for j_ in js:
            Cp = np.array([Pc[j_], [Pc[j_][0], Pc[j_][1], max(W1[2], Pc[j_][2]+.01)]]+[np.asarray(v_) for v_ in rest]+direct.final_hook(lay, T_pt))
            bs = [o.fixture.describe(np.vstack([Pc[:j_], direct.excursion(lay, Cp, s_), Pc[j_+1:]]))[2] for s_ in (1, -1)]
            if min(bs) < b0:
                keep.append(j_)
        js = keep
    chosen = None
    ctr = np.array([lay.ring_x[k-1], 0.])
    why = {'ik': 0, 'clash': 0}
    for j_ in js:
        # rise vertically, or drifting up to 3 cm towards the aperture centre (still inside the aperture,
        # so the same route class)
        for f_ in (0., .5, 1.):
            xy = Pc[j_][:2]+min(1., .03*f_/max(np.linalg.norm(ctr-Pc[j_][:2]), 1e-9))*(ctr-Pc[j_][:2])
            Wj = np.array([xy[0], xy[1], max(W1[2], Pc[j_][2]+.01)])
            # the top arm must also get there: a vertical descent from above every ring over this spot
            # (the audit's approach path) joined to the rise, as one continuous track
            dz_free = min(.25, max(.10, max(lay.ring_z)+lay.ring_tube_radius_m+.06-Pc[j_][2]))
            above = Pc[j_]+np.array([0, 0, dz_free])
            opts = list(islice(rc.path_options(side_t, [above, Pc[j_], Wj], rich=True), 6))
            why['ik' if not opts else 'clash'] += 1
            for rt in opts:
                # the whole descent, grasp and rise next to the side arm, which holds the cord until the
                # hand-over and then stays put until the top arm has risen clear (its fingers stick up)
                clear = True
                for q_ in rt['q']:
                    qq[K.qadr[side_t]] = q_
                    if K.collisions(qq):
                        clear = False
                        break
                if clear:
                    chosen = (j_, Wj)
                    break
            if chosen is not None:
                break
        if chosen is not None:
            break
    if chosen is None and not last_plan:
        return 'next'
    if chosen is None:
        # no hand-over possible: the side arm lets the pushed-in cord go and takes it again from above
        o.release(gs)
        o.settle(.6, f'{tag}_let_go')
        Pc = o.points()
        b0 = o.fixture.describe(Pc)[2]
        T_pt = C[T_idx]
        regrasp = None
        js2 = [i+d for d in range(-24, 25, 2) if 0 <= i+d < o.n]
        js2 = [j_ for j_ in js2 if np.hypot(Pc[j_][0]-lay.ring_x[k-1], Pc[j_][1]) < rim]
        for j_ in js2:
            Wj = np.array([Pc[j_][0], Pc[j_][1], W1[2]])
            Cp = np.array([Pc[j_], Wj]+[np.asarray(v_) for v_ in rest]+direct.final_hook(lay, T_pt))
            if min(o.fixture.describe(np.vstack([Pc[:j_], direct.excursion(lay, Cp, s_), Pc[j_+1:]]))[2]
                   for s_ in (1, -1)) >= b0:
                continue
            above = Pc[j_]+np.array([0, 0, min(.25, max(.10, max(lay.ring_z)+lay.ring_tube_radius_m+.06-Pc[j_][2]))])
            for arm in (side_s, side_t):
                if rc.path(arm, [above, Pc[j_], Wj]+[np.asarray(v_) for v_ in rest]+[T_hi], rich=True)['ok']:
                    regrasp = (arm, j_, Wj)
                    break
            if regrasp:
                break
        if regrasp is None:
            raise RuntimeError(f'{tag}: ik_skip thread top arm at the actual cord near node {i} (side holds '
                               f'{np.round(Hs, 3).tolist()}, {len(js)} nodes inside {why}; regrasp from above failed)')
        arm, j, W1 = regrasp
        g = GRIP[arm]
        o.grasp(g, j)
        path_c = [W1]+[np.asarray(v_) for v_ in rest]+[T_hi]
        L = float(np.linalg.norm(np.diff(np.vstack([Pc[j]]+path_c), axis=0), axis=1).sum())
        o.move(f'{tag}_regrasp_rise', {g: path_c}, max(3., L/.04))
        hook_phase(o, rc, arm, j, orient, tag, [Pc[j]]+path_c, T_hi, H, k2s)
        return
    j, W1 = chosen
    if carrier == side_t and not rc.path(side_t, [Pc[j], W1]+[np.asarray(v_) for v_ in rest]+[T_hi], rich=True)['ok']:
        carrier = side_s
    o.grasp(gt, j)
    o.release(gs)
    o.settle(.5, f'{tag}_handover')
    o.move(f'{tag}_thread', {gt: [W1]}, max(2., float(np.linalg.norm(W1-Pc[j]))/.03))
    apex, prefix = j, [Pc[j], W1]
    if carrier == side_s:
        # second hand-over in the open above the aperture: the side arm takes a neighbour of the apex.
        # The top arm may first rise more on the spot, 3 cm at a time, so that the bight's strands above the
        # ring get long enough for a grasp >= 7 cm from it (same side of P0's axis; up to the carry height
        # over the ball, and below any higher ring whose aperture lies over this spot).
        z_cap = T_hi[2]+.03
        for kr in range(len(lay.ring_z)):
            if lay.ring_z[kr] > W1[2] and np.hypot(W1[0]-lay.ring_x[kr], W1[1]) < lay.ring_radius_m+lay.ring_tube_radius_m+.03:
                z_cap = min(z_cap, lay.ring_z[kr]-lay.ring_tube_radius_m-.03)
        got = None
        top_path = [Pc[j], W1]                  # the top arm's whole track since its grasp (one continuous IK)
        for dz in (0.,)+(.03,)*int(max(0., z_cap-W1[2])//.03):
            if dz:
                W_up = np.array([W1[0], W1[1], W1[2]+dz])
                if not rc.path(side_t, top_path+[W_up], rich=True)['ok']:
                    break
                o.move(f'{tag}_thread_up', {gt: [W_up]}, 1.)
                W1 = W_up
                top_path = top_path+[W_up]
            Pc = o.points()
            r_t = rc.path(side_t, top_path, rich=True)
            if not r_t['ok']:
                continue
            for d in (4, -4, 6, -6, 8, -8, 10, -10, 12, -12, 14, -14, 16, -16, 20, -20, 24, -24):
                k_ = j+d
                # both grippers on the cord at once: keep them >= 7 cm apart (an instantaneous no-contact
                # check alone left 3 cm gaps that no joint orientation choice could keep clear)
                if not 0 <= k_ < o.n or np.linalg.norm(Pc[k_]-W1) < .07:
                    continue
                pre = [Pc[k_]]+[np.asarray(v_) for v_ in rest]+[T_hi]
                for r1 in rc.path_options(side_s, pre, rich=True):
                    qq = K.home.copy()
                    qq[K.qadr[side_t]] = r_t['q'][-1]
                    qq[K.qadr[side_s]] = r1['q'][0]
                    if not K.collisions(qq):
                        got = (k_, pre)
                        break
                if got:
                    break
            if got:
                break
        if got is None:
            raise RuntimeError(f'{tag}: ik_skip thread open hand-over near node {j}')
        k_, pre = got
        o.grasp(gs, k_)
        o.release(gt)
        o.settle(.4, f'{tag}_handover2')
        apex, prefix = k_, pre
    g = GRIP[carrier]
    path_c = [np.asarray(v_) for v_ in rest]+[T_hi]
    L = float(np.linalg.norm(np.diff(np.vstack([prefix[-1] if carrier == side_t else prefix[0]]+path_c), axis=0), axis=1).sum())
    o.move(f'{tag}_route', {g: path_c}, max(3., L/.04))
    pref = prefix+path_c if carrier == side_t else prefix
    hook_phase(o, rc, carrier, apex, orient, tag, pref, T_hi, H, k2s)

def tidy_cord(o, rc, out, k, marks, F, round_):
    """When no candidate of pass k works: an isotopy move first. A reachable cord point (not under a ring)
    next to a stretch lying under the rings is dragged ~8 cm along the base, away from the fixture, so
    that stretch slides out to where a gripper can take it; the word must stay the same. The tidied state
    becomes the new start of pass k (its frames stay in the pass). True if a move was adopted."""
    lay = o.lay
    o.restore(out/'ckpt'/f'p{k-1:02d}')
    del o.frames[marks[k-1][0]:]
    del o.log[marks[k-1][1]:]
    P = o.points()
    w0 = F.describe(P)[0]

    def covered(p):
        return any(p[2] < zr and np.hypot(p[0]-cx, p[1]) < lay.ring_radius_m+lay.ring_tube_radius_m
                   for cx, zr in zip(lay.ring_x, lay.ring_z))

    idx = np.arange(4, o.n-4)
    under = [i for i in idx if covered(P[i])]
    if not under:
        return False
    free_ = [j for j in idx[::2] if not covered(P[j]) and P[j][2] < lay.base_height_m+.03]
    free_.sort(key=lambda j: min(abs(j-u) for u in under))
    ctr = np.array([np.mean(lay.post_x), 0.])
    tried = 0
    for j in free_[round_*4:]:
        if tried >= 8:
            break
        tried += 1
        d = P[j][:2]-ctr
        d = d/max(np.linalg.norm(d), 1e-9)
        tgt = np.array([P[j][0]+.08*d[0], P[j][1]+.08*d[1], P[j][2]])
        path = [P[j]+np.array([0, 0, .01]), tgt+np.array([0, 0, .01]), tgt]
        side = next((s_ for s_ in (('left', 'right') if P[j][1] >= 0 else ('right', 'left'))
                     if rc.path(s_, [P[j]]+path, rich=True)['ok']), None)
        if side is None:
            continue
        g = GRIP[side]
        try:
            o.grasp(g, int(j))
            o.move(f'p{k:02d}_tidy', {g: path}, 4.)
            o.release(g)
            o.settle(.6, f'p{k:02d}_tidy_rest')
        except RuntimeError:
            o.release(g)
            o.restore(out/'ckpt'/f'p{k-1:02d}')
            del o.frames[marks[k-1][0]:]
            del o.log[marks[k-1][1]:]
            continue
        if F.describe(o.points())[0] != w0 or sum(covered(p) for p in o.points()) >= len(under):
            o.restore(out/'ckpt'/f'p{k-1:02d}')
            del o.frames[marks[k-1][0]:]
            del o.log[marks[k-1][1]:]
            continue
        o.save(out/'ckpt'/f'p{k-1:02d}')
        marks[k-1] = (len(o.frames), len(o.log))
        return True
    return False


def next_pass_open(o, rc, F, node_step=8):
    """Optimistic lookahead before accepting a pass: the next pass needs at least one b-deleting candidate
    whose cord node a gripper can take (the dead ends seen were all of the kind "the needed stretch lies
    out of reach under the rings"; route details are left to the executor's own search). Cheap first:
    direct candidates on a coarse node subset, aperture routes only if those give nothing graspable."""
    P = o.points()
    if F.describe(P)[2] == 0:
        return True
    nodes = range(4, o.n-4, node_step)
    seen = set()

    def any_graspable(cands):
        for c in sorted(cands, key=lambda c: (c.get('tangle', 99), c['need'])):
            i = c['node']
            if i in seen:
                continue
            seen.add(i)
            if len(seen) > 60:
                return False
            for side in ('left', 'right'):
                if rc.path(side, [P[i], P[i]+np.array([0, 0, .01])], rich=True)['ok']:
                    return True
        return False

    return any_graspable(direct.candidates(F, o.lay, P, nodes)[1]) or \
        any_graspable(direct.plumb_candidates(F, o.lay, P, nodes)[1])


def audit_pass(o, out, k, mark):
    """Full IK audit (both arms, transits, collisions at 1 mm) of this pass alone; its summary."""
    from .ik_audit import main as audit_main
    d = out/'audit'/f'p{k:02d}_{len(list((out/"audit").glob(f"p{k:02d}_*"))) if (out/"audit").exists() else 0}'
    d.mkdir(parents=True)
    fr = o.frames[mark[0]:]
    np.savez_compressed(d/'frames.npz', t=[f[0] for f in fr], phase=[f[1] for f in fr],
                        pts=np.array([f[2] for f in fr]), handle=np.array([f[3] for f in fr]),
                        grips=np.array([f[4] for f in fr]), active=np.array([f[5] for f in fr]))
    (d/'events.json').write_text(json.dumps(o.log[mark[1]:], default=str))
    (d/'model.json').write_text(json.dumps(o.identity(), indent=2)+'\n')
    audit_main([o.variant, str(d), '--fixed-arms'])
    return json.loads((d/'ik_report.json').read_text())['summary']


def save_run(o, out):
    """Recorded frames and events of the accepted branch (the IK audit's input)."""
    np.savez_compressed(out/'frames.npz', t=[f[0] for f in o.frames], phase=[f[1] for f in o.frames],
                        pts=np.array([f[2] for f in o.frames]), handle=np.array([f[3] for f in o.frames]),
                        grips=np.array([f[4] for f in o.frames]), active=np.array([f[5] for f in o.frames]))
    (out/'events.json').write_text(json.dumps(o.log, default=str, indent=1))
    (out/'model.json').write_text(json.dumps(o.identity(), indent=2)+'\n')


def slack(o, x_handle, tag):
    for g in 'ABCD':
        o.release(g)
    o.grasp('B', 'handle')   # right arm; reach of the handle path is audited afterwards
    h = o.handle_pose()[0]
    o.move(f'{tag}_handle', {'B': [[h[0], h[1], .06], [x_handle, 0, .06], [x_handle, 0, .03]]}, 3.)
    o.release('B')
    o.settle(2., f'{tag}_handle_rest')   # time for the arm to retreat before the other arm starts


def goal_box(o):
    """Bounds of the local task's actual placement region in the oracle frame."""
    return dict(o.goal.box)


def in_goal(o):
    P = o.points(); h = o.handle_pose()[0]
    inside = o.goal.contains(o)
    import mujoco
    from topogym.evaluation.task_metrics import quiet_body, soft_speed
    velocities = np.empty_like(P)
    velocity = np.zeros(6)
    for i in range(o.n):
        mujoco.mj_objectVelocity(o.model, o.data, mujoco.mjtObj.mjOBJ_BODY, o.model.body(f'n{i}').id, velocity, 0)
        velocities[i] = velocity[3:]
    quiet_cord, speeds = soft_speed(dict(position_m=P, velocity_m_s=velocities))
    mujoco.mj_objectVelocity(o.model, o.data, mujoco.mjtObj.mjOBJ_BODY, o.model.body('handle').id, velocity, 0)
    quiet_handle = quiet_body(dict(linear_velocity_m_s=velocity[3:], angular_velocity_rad_s=velocity[:3]))
    fixture = getattr(o, 'fixture', None) or Fixture(o.lay)
    ok = all(inside.values()) and quiet_cord and quiet_handle and fixture.describe(P)[1] == 0
    return bool(ok), dict(cord_x=[round(float(P[:, 0].min()), 4), round(float(P[:, 0].max()), 4)],
                          cord_ymax=round(float(np.abs(P[:, 1]).max()), 4), cord_zmax=round(float(P[:, 2].max()), 4),
                          handle=np.round(h, 4).tolist(), target_inside=inside, quiet_handle=quiet_handle,
                          quiet_cord=quiet_cord, **speeds, formal_qualification=False)


def extract(o, tag='x', handle=True, max_moves=None, max_iter=40):
    for g in 'ABCD':
        o.release(g)
    GOAL = goal_box(o)
    gx, gy = GOAL['xmax'], GOAL['ycenter']
    o.grasp('B', 'handle')
    if handle:
        h = o.handle_pose()[0]
        xf = -o.lay.base_length_m/2                # far end of the fixture
        zt = o.lay.ball_z+o.lay.ball_radius_m+.11
        o.move(f'{tag}_handle_up', {'B': [[h[0], h[1], zt-.04]]}, 3.)
        o.move(f'{tag}_handle_over', {'B': [[.0, 0, zt], [xf, 0, zt], [gx-.12, 0, zt-.04]]}, 6.)
        o.move(f'{tag}_handle_down', {'B': [[gx-.14, gy, .12], [gx-.14, gy, .03]]}, 3.)
        # draw the handle slowly to the far side of the goal: the free cord slides back out of the rings
        o.move(f'{tag}_handle_draw', {'B': [[GOAL['xmin']+.04, gy, .03]]}, 12.)
    # slack: the handle held at the far side of the goal keeps the cord taut over the rims, so no loop can
    # slide back; set it down at the goal's near edge and let go while the loops are cleared
    hp = o.handle_pose()[0]
    o.move(f'{tag}_handle_slack', {'B': [[gx-.05, hp[1], .03]]}, 4.)
    o.release('B')
    o.settle(.5, f'{tag}_handle_set')
    z_clear = o.lay.ball_z+o.lay.ball_radius_m+.08          # above every ring and the ball
    import tempfile
    tmp = Path(tempfile.mkdtemp())

    def tangles():
        return len(signature(o.points(), o.lay))

    for it in range(max_iter):
        # the freed cord may still be threaded through rings / hooked round a post: try lifting cord points
        # clear of the fixture and carrying them over the goal; keep the first move that stays within the
        # guards and leaves fewer ring/post crossings (or brings more cord into the goal)
        P = o.points()
        out_ = np.nonzero(P[:, 0] > gx-.02)[0]
        if len(out_) == 0:
            break
        before = (tangles(), len(out_))
        o.save(tmp/'base')
        mark = (len(o.frames), len(o.log))
        order = list(out_[np.argsort(-P[out_, 2])][:6])+list(out_[::max(1, len(out_)//10)])
        done = False
        low = list(out_[np.argsort(P[out_, 2])][:6])        # cord on the base: pull loops back down
        # hand over hand: where the cord enters the goal, take it just inside and draw it deeper into the
        # goal (the cord behind slides back out through the rings, as a thread is pulled out of a needle)
        inside = P[:, 0] <= gx-.02
        edge = [j for j in range(o.n) if inside[j] and ((j > 0 and not inside[j-1]) or (j < o.n-1 and not inside[j+1]))]
        # loop tips: the cord points reaching furthest into the fixture (a loop hooked round a ring tube or
        # draped over a rim comes free when its tip is lifted out through the rings above, or drawn back)
        tips = [j for j in out_ if (j == 0 or P[j, 0] >= P[j-1, 0]) and (j == o.n-1 or P[j, 0] >= P[j+1, 0])]
        tips = sorted(tips, key=lambda j: -P[j, 0])[:4]
        # cancelling pairs: consecutive crossings of the same ring in opposite directions mean a loop of cord
        # poking through that ring; take the loop's apex and push it straight back through the ring
        ev = signature(P, o.lay, closing=False)
        unpoke = {}
        for (s1, n1), (s2, n2) in zip(ev[:-1], ev[1:]):
            if n1[0] == 'R' and n2[0] == 'R' and n1[:-1] == n2[:-1] and n1[-1] != n2[-1]:
                a_, b_ = int(s1)+1, int(s2)
                if b_ > a_:
                    seg = np.arange(a_, b_+1)
                    up = n1[-1] == '+'                 # up through the ring and back down: apex above it
                    apex = int(seg[np.argmax(P[seg, 2])] if up else seg[np.argmin(P[seg, 2])])
                    mid = (P[a_-1]+P[b_])/2            # where the loop crosses the ring plane
                    unpoke[apex] = (int(n1[1:-1])-1, up, mid)
        moves = [(int(j), 'unpoke') for j in unpoke]
        moves += [(int(j), 'under') for j in tips]
        moves += [(int(j), 'pull') for j in edge]
        moves += [(int(j), 'lift') for j in tips]+[(int(j), 'draw') for j in tips]
        moves += [(int(j), 'lift') for j in order]+[(int(j), 'drag') for j in low]
        for i, kind in list(dict.fromkeys(moves))[:max_moves]:
            o.restore(tmp/'base')
            del o.frames[mark[0]:]; del o.log[mark[1]:]
            p = o.points()[i]
            yv = float(np.clip(p[1], GOAL['ymin']+.02, GOAL['ymax']-.02))
            if kind == 'unpoke':
                # retract the loop the way a bight came in: over the open middle of the ring's aperture
                # (where it crossed the plane may be at the rim, on the tube), then straight back through
                kr, up, mid = unpoke[i]
                zr_ = o.lay.ring_z[kr]
                ac = direct.aperture_center(o.lay, kr+1)
                if up:
                    path = [[ac[0], ac[1], max(p[2], zr_+.03)], [ac[0], ac[1], zr_-.05]]
                else:
                    path = [[ac[0], ac[1], min(p[2], zr_-.03)], [ac[0], ac[1], zr_+.05]]
            elif kind == 'pull':
                path = [[p[0], p[1], max(p[2], .02)+.02], [max(GOAL['xmin']+.05, p[0]-.20), yv, .03]]
            elif kind == 'under':
                # a loop tip hooked up into a ring from below its tube: back down under the tube (3 cm below
                # the ring plane), outwards past the rim (beside the post on the x axis), then to the goal
                kr = int(np.argmin([abs(np.hypot(p[0]-cx_, p[1])-o.lay.ring_radius_m)+abs(p[2]-zr_)
                                    for cx_, zr_ in zip(o.lay.ring_x, o.lay.ring_z)]))
                cx_, zr_ = o.lay.ring_x[kr], o.lay.ring_z[kr]
                zu = max(.03, zr_-.03)
                dv = np.array([p[0]-cx_, p[1]])
                dv = dv/max(np.linalg.norm(dv), 1e-9)
                ys_ = .035 if p[1] >= 0 else -.035
                out_pt = np.array([cx_, 0.])+dv*(o.lay.ring_radius_m+.04)
                path = [[p[0], p[1], zu], [out_pt[0], out_pt[1]+ys_, zu], [gx-.10, ys_, zu], [gx-.10, ys_, .03]]
            elif kind == 'draw':
                # level, beside the posts (|y| >= 6 cm), back out towards the goal, then down
                ys_ = .06 if p[1] >= 0 else -.06
                path = [[p[0], ys_ if abs(p[1]) < .06 else p[1], p[2]+.01], [gx-.10, ys_, p[2]+.01], [gx-.10, ys_, .03]]
            elif kind == 'lift':
                path = [[p[0], p[1], z_clear], [gx-.08, yv, z_clear], [gx-.10, yv, .03]]
            else:
                # drag along the base towards the goal side: a loop poked up through an aperture slides back
                path = [[p[0], p[1], p[2]+.01], [max(gx-.10, p[0]-.18), yv, p[2]+.01]]
            try:
                o.grasp('A', i)
                # Extraction uses the same local limits as every other phase.
                o.move(f'{tag}_sweep{it}', {'A': path}, 15.)
                o.release('A')
                o.settle(.5, f'{tag}_sweep{it}_rest')
            except RuntimeError as e_:
                o.release('A')
                print(json.dumps(dict(event='extract_move', it=it, node=i, kind=kind, p=np.round(p, 3).tolist(),
                                      err=str(e_)[:120])), flush=True)
                continue
            after = (tangles(), int((o.points()[:, 0] > gx-.02).sum()))
            print(json.dumps(dict(event='extract_move', it=it, node=i, kind=kind, p=np.round(p, 3).tolist(),
                                  before=before, after=after)), flush=True)
            if after < before:
                done = True
                break
        if not done:
            o.restore(tmp/'base')
            del o.frames[mark[0]:]; del o.log[mark[1]:]
            raise RuntimeError(f'{tag}: extraction stuck with {before[0]} crossings, {before[1]} nodes outside the goal')
    o.grasp('B', 'handle')
    o.move(f'{tag}_handle_rest', {'B': [GOAL['xmin']+.04, gy, .012]}, 4.)
    o.release('B')
    o.settle(10., f'{tag}_rest')               # the Task needs the cord and handle at rest
    ok, info = in_goal(o)
    info['vmax'] = round(float(np.abs(o.data.qvel).max()), 5)
    return ok, info


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('variant', choices=('easy', 'medium', 'hard'))
    ap.add_argument('out')
    ap.add_argument('--start', default=None, help='checkpoint dir to start from')
    ap.add_argument('--max-passes', type=int, default=20)
    ap.add_argument('--handle-x', type=float, default=None)
    ap.add_argument('--max-candidates', type=int, default=6)
    ap.add_argument('--length', type=float, default=None, help='must match the local task cord length; defaults to its profile')
    ap.add_argument('--node-step', type=int, default=2)
    ap.add_argument('--cache-dir', default='runs/oracle_dev/orbits_cache', help='candidate-search cache')
    ap.add_argument('--hole-free', action='store_true', help='only bights whose rise crosses no ring aperture')
    ap.add_argument('--plumb', action='store_true', help='add vertical rises through aperture centres')
    ap.add_argument('--plumb-only', action='store_true', help='with --plumb: use only those routes')
    ap.add_argument('--plumb-first', action='store_true', help='with --plumb: try those routes first')
    ap.add_argument('--shard', type=int, default=0, help='this process searches cord nodes shard::nshard of each pass')
    ap.add_argument('--nshard', type=int, default=1)
    ap.add_argument('--round-seconds', type=float, default=1500.,
                    help='wall time per search round before the cord is tidied and the pass re-planned (0: off)')
    ap.add_argument('--round-attempts', type=int, default=0,
                    help='per pass and cord arrangement: after this many attempts, tidy the cord and re-plan')
    ap.add_argument('--object-level', action='store_true',
                    help='virtual point grippers: no robot IK checks or audits (object-level solution)')
    a = ap.parse_args(argv)
    if a.nshard < 1 or not 0 <= a.shard < a.nshard or a.node_step < 1:
        ap.error('require nshard >= 1, 0 <= shard < nshard and node-step >= 1')
    out = Path(a.out); out.mkdir(parents=True, exist_ok=False); (out/'snap').mkdir(); (out/'ckpt').mkdir()
    o = Oracle(a.variant, length=a.length)
    F = Fixture(o.lay)
    o.fixture = F
    rc = FreeCheck(o.lay) if a.object_level else RobotCheck(o.lay)
    log = open(out/'auto_log.jsonl', 'a')

    def rec(**kw):
        kw.update(t=round(o.data.time, 2), word=F.describe(o.points()), sig=sfmt(signature(o.points(), o.lay)),
                  stretch=round(o.stretch()[1], 4))
        print(json.dumps(kw, default=str), flush=True)
        log.write(json.dumps(kw, default=str)+'\n'); log.flush()

    if a.start:
        o.restore(a.start)
    else:
        # Settling has the same limits as manipulation; do not import relaxed initialization guards.
        o.move('settle', {}, 1.)
        hx = a.handle_x if a.handle_x is not None else o.lay.post_x[-1]+.035
        slack(o, hx, 'init')
    o.save(out/'ckpt'/'p00')
    marks = {0: (len(o.frames), len(o.log))}
    rec(event='start')
    k, tidies, pass_start = 1, 0, {}
    extracted = False
    while k <= a.max_passes:
        import hashlib
        pass_start.setdefault(k, marks[k-1])      # the audit covers tidy moves made in this pass too
        Pk = o.points()
        # each shard searches its own subset of cord nodes (the search is the slow part for long cords)
        nodes = range(4+a.node_step*a.shard, o.n-4, a.node_step*a.nshard)
        key = hashlib.sha1((a.variant+str(a.length)+'direct_v4'+str(a.node_step)+f'n{a.shard}of{a.nshard}'+('' if SCALE == .85 else f's{SCALE}v2')+(repr(o.lay) if FROM_TASK else '')).encode()+np.round(Pk, 6).tobytes()).hexdigest()[:16]
        cpath = Path(a.cache_dir)/f'{key}.json'
        if cpath.exists():
            cached = json.loads(cpath.read_text())
            bw, cands = tuple(cached['bw']), cached['cands']
        else:
            bw, cands = direct.candidates(F, o.lay, Pk, nodes)
            cpath.parent.mkdir(parents=True, exist_ok=True)
            cpath.write_text(json.dumps(dict(bw=list(bw), cands=cands), default=float))
        if a.plumb:
            ppath = cpath.with_name(cpath.stem+'_plumb11.json')
            if ppath.exists():
                pc = json.loads(ppath.read_text())['cands']
            else:
                pc = direct.plumb_candidates(F, o.lay, Pk, nodes)[1]
                ppath.write_text(json.dumps(dict(bw=list(bw), cands=pc), default=float))
            cands = pc if a.plumb_only else sorted(cands+pc, key=lambda c: c['need'])
        if a.hole_free:
            epath = cpath.with_name(cpath.stem+'_escape.json')
            if epath.exists():
                ecands = json.loads(epath.read_text())['cands']
            else:
                ecands = direct.escape_candidates(F, o.lay, Pk, nodes)[1]
                epath.write_text(json.dumps(dict(bw=list(bw), cands=ecands), default=float))
            cands = sorted(cands+ecands, key=lambda c: c['need'])
        n_all = len(cands)
        # one candidate per (node, route class): IK feasibility is decided mostly by where the bight
        # starts and which apertures it crosses, so near-duplicates would only repeat the same failure
        seen_cls, uniq = set(), []
        for c in cands:
            # for aperture-centre routes the entry point matters too (different arms reach different spots)
            # (with its heights: two-aperture routes differ only in how high they cross the gap)
            entry = tuple(np.round(np.asarray(c['Q']), 2).ravel()) if c.get('plumb') else ()
            cls = (c['node'], tuple(c.get('plumb') or route_holes(o.lay, c)), c['sign'], entry)
            if cls not in seen_cls:
                seen_cls.add(cls)
                uniq.append(c)
        cands = uniq
        if a.plumb_first:
            # vertical rises through aperture centres suit the gripper best; try them before the rest
            # cheapest primitives first: direct rises from where the node lies (one arm through the ring),
            # hole-free carries, then aperture hand-overs, then the rest
            in_place = [c for c in cands if c.get('plumb') and len(c['Q']) == 1]
            free = [c for c in cands if not c.get('plumb') and not route_holes(o.lay, c)]
            thread = [c for c in cands if c.get('plumb') and len(c['Q']) > 1]
            rest_ = [c for c in cands if not c.get('plumb') and route_holes(o.lay, c)]
            # within each primitive, the moves leaving the least entangled cord first (as the reference
            # solution keeps the cord tidy; the last pass then leaves it free to lift off), then by cord used
            tidy = lambda group: sorted(group, key=lambda c: (c.get('tangle', 99), c['need']))
            cands = tidy(in_place)+tidy(free)+tidy(thread)+tidy(rest_)
        if a.hole_free:
            cands = [c for c in cands if not route_holes(o.lay, c)]
        rec(event='search', k=k, b=bw[2], n=n_all, n_hole_free=len(cands), top=[(c['node'], c['sign'], round(c['need'], 3), c['Q'], c['y_s']) for c in cands[:6]])
        if bw[2] == 0:
            break
        ok = False
        n_att = 0
        round_t0 = time.time()
        for c0 in cands[:a.max_candidates]:
            if (a.round_attempts and n_att >= a.round_attempts) or \
                    (a.round_seconds and time.time()-round_t0 > a.round_seconds):
                break                                  # time to rearrange the cord (tidy) and re-plan
            # the nominal route first; if the robot cannot even start it (IK pre-checks only, nothing
            # executed), its corridor variants -- waypoints shifted, same topology, word re-checked
            queue, expanded = [c0], False
            while queue and not ok:
                c = queue.pop(0)
                prechecks_only = True
                for orient in (1, -1):
                    n_att += 1
                    o.restore(out/'ckpt'/f'p{k-1:02d}')
                    del o.frames[marks[k-1][0]:]; del o.log[marks[k-1][1]:]
                    t0 = time.time()
                    try:
                        try:
                            execute_robot(o, rc, c, orient, f'p{k:02d}')
                        except RuntimeError as e_:
                            # through an aperture the single arm may not fit: fall back to the hand-over
                            if not (c.get('plumb') and 'ik_skip carry' in str(e_)):
                                raise
                            if len(c['Q']) == 1:
                                # in place under the lowest ring: a helper arm props the cord up first
                                try:
                                    execute_assisted(o, rc, c, orient, f'p{k:02d}')
                                except RuntimeError as e2_:
                                    if 'ik_skip' not in str(e2_):
                                        raise
                                    o.restore(out/'ckpt'/f'p{k-1:02d}')
                                    del o.frames[marks[k-1][0]:]; del o.log[marks[k-1][1]:]
                                    execute_thread(o, rc, c, orient, f'p{k:02d}')
                            else:
                                execute_thread(o, rc, c, orient, f'p{k:02d}')
                    except RuntimeError as e:
                        rec(event='guard', k=k, node=c['node'], orient=orient, err=str(e)[:160],
                            variant=c.get('variant'))
                        if 'ik_skip' not in str(e) or 'actual cord' in str(e):
                            prechecks_only = False
                        continue
                    prechecks_only = False
                    nb = F.describe(o.points())[2]
                    rec(event='try', k=k, node=c['node'], orient=orient, Q=c['Q'], y_s=c['y_s'], need=round(c['need'], 3),
                        b_after=nb, pred_match=F.describe(o.points())[0] == c['word'], wall=round(time.time()-t0, 1),
                        variant=c.get('variant'))
                    # one ball pass changes exactly one b; a larger drop means the cord crossed a post or
                    # ring tube between guard samples (tunnelling) -- never accept it
                    if nb < bw[2]-1:
                        rec(event='topology_jump', k=k, node=c['node'], orient=orient, b_before=bw[2], b_after=nb)
                        continue
                    if nb == bw[2]-1 and F.describe(o.points())[0] != c['word']:
                        # one b fewer but not the predicted state: the cord took another route (or slipped
                        # through something); only the exact predicted word is accepted
                        rec(event='word_mismatch', k=k, node=c['node'], orient=orient)
                        continue
                    if nb == bw[2]-1:
                        # accept only what the robot can actually execute: the full IK audit of this pass
                        summ = dict(all_ok=True, failed=[], timeline_collision_samples=0, transit_failures=[]) \
                            if a.object_level else audit_pass(o, out, k, pass_start[k])
                        rec(event='audit', k=k, node=c['node'], orient=orient, all_ok=summ['all_ok'],
                            failed=summ['failed'], timeline_collisions=summ['timeline_collision_samples'],
                            transit_failures=len(summ['transit_failures']))
                        if not summ['all_ok']:
                            continue
                        if nb == 0:
                            # the last pass: accept it only if the freed cord can then be drawn into the goal
                            # (some final shapes leave a loop caught round a ring tube under tension)
                            try:
                                ok_x, info_x = extract(o, max_moves=8, max_iter=24)
                            except RuntimeError as e_x:
                                ok_x, info_x = False, dict(err=str(e_x)[:160])
                            rec(event='extract_try', k=k, node=c['node'], orient=orient, ok=ok_x, **info_x)
                            if not ok_x:
                                continue
                            if not a.object_level:
                                # Include extraction in the accepted robot branch, not only the ball pass.
                                extraction_audit = audit_pass(o, out, k, pass_start[k])
                                rec(event='extract_audit', k=k, all_ok=extraction_audit['all_ok'])
                                if not extraction_audit['all_ok']:
                                    continue
                            extracted = True
                        # one-pass lookahead: never accept a state whose next pass the robot cannot start
                        if not a.object_level and not next_pass_open(o, rc, F):
                            rec(event='dead_end', k=k, node=c['node'], orient=orient)
                            continue
                        ok = True
                        break
                if not ok and prechecks_only and not expanded:
                    expanded = True
                    o.restore(out/'ckpt'/f'p{k-1:02d}')
                    queue += direct.route_variants(F, o.lay, o.points(), c0)
            if ok:
                break
        if not ok:
            if tidies < 6 and tidy_cord(o, rc, out, k, marks, F, tidies):
                tidies += 1
                rec(event='tidy', k=k, round=tidies)
                continue
            rec(event='stuck', k=k)
            break
        tidies = 0
        o.save(out/'ckpt'/f'p{k:02d}')
        save_run(o, out)                     # accepted branch so far, for the IK audit of stopped runs
        marks[k] = (len(o.frames), len(o.log))
        snap_oracle(o, out/'snap'/f'p{k:02d}.png', f'pass {k}')
        rec(event='accepted', k=k, node=c['node'], orient=orient, Q=c['Q'], y_s=c['y_s'], need=round(c['need'], 3),
            max_stretch=round(getattr(o, 'max_stretch', 1.), 4))
        k += 1
    if F.describe(o.points())[2] == 0 and not extracted:
        try:
            ok, info = extract(o)
            rec(event='extract', ok=ok, **info)
        except RuntimeError as e:
            ok = False
            rec(event='extract_guard', err=str(e)[:200])
        o.save(out/'ckpt'/'final')
        snap_oracle(o, out/'snap'/'final.png', 'final placement')
    save_run(o, out)
    rec(event='done', max_stretch=round(getattr(o, 'max_stretch', 1.), 4), max_total=round(getattr(o, 'max_total', 1.), 4),
        max_pen=round(getattr(o, 'max_pen', 0.), 5))


if __name__ == '__main__':
    main()
