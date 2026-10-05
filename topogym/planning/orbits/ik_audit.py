"""Convert an accepted rope-oracle run into ALOHA joint trajectories and audit them.

Input: <run>/frames.npz (accepted branch only) and <run>/events.json. Grasp episodes (a gripper
holding one node, a two-strand pinch, or the handle) are assigned to arms with overlapping
episodes on different arms; each episode's TCP path is solved by damped least-squares IK with the
previous sample as seed. Reports residuals, joint-limit margins, robot/fixture and arm/arm contacts.
"""
import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np

from .rope_sim import layout_for  # noqa: E402
from .aloha_ik import AlohaIK, approach_rotation, LIMITS, from_mj  # noqa: E402
from .local_contract import (MAX_GRIP_ERROR_M, MAX_PENETRATION_M, MAX_SEGMENT_STRETCH, MAX_TOTAL_STRETCH,
                             MAX_IK_STEP_RAD, STANDARD_JOINT_SPEED_RAD_S, task_for)

APPROACH = {                 # each arm first tries a tilt from its own side, which keeps the forearms apart
    'left': [[0, -.6, -.8], [0, 0, -1], [.6, 0, -.8], [-.6, 0, -.8], [0, -1, 0], [0, -.9, -.44], [.5, -.86, 0],
             [-.5, -.86, 0], [0, -.6, .8]],
    'right': [[0, .6, -.8], [0, 0, -1], [.6, 0, -.8], [-.6, 0, -.8], [0, 1, 0], [0, .9, -.44], [.5, .86, 0],
              [-.5, .86, 0], [0, .6, .8]],
}


def episodes(events, t_end):
    """[(gripper, target, t0, t1)] from grasp/release events."""
    open_ = {}
    out = []
    for e in events:
        if e.get('event') == 'grasp':
            g = e['gripper']
            if g in open_:
                out.append((g, open_[g][0], open_[g][1], e['t']))
            open_[g] = (e['node'], e['t'])
        elif e.get('event') == 'release':
            g = e['gripper']
            if g in open_:
                out.append((g, open_[g][0], open_[g][1], e['t']))
                del open_[g]
    for g, (node, t0) in open_.items():
        out.append((g, node, t0, t_end))
    return sorted([o for o in out if o[3] > o[2]+1e-6], key=lambda o: o[2])


def resting(lay, p):
    """A cord point lying on a support: the base, or on top of a ring tube (its upper half may be pinched)."""
    if p[2] < lay.base_height_m+.006:
        return True
    for cx, zr in zip(lay.ring_x, lay.ring_z):
        d = np.hypot(np.hypot(p[0]-cx, p[1])-lay.ring_radius_m, p[2]-zr)
        if p[2] > zr and d < lay.ring_tube_radius_m+lay.cord_radius_m+.004:
            return True
    return False


def rich_approaches(side):
    """Denser approach set (tilt 0-80 deg in 8 azimuths) for tight spots such as ring apertures."""
    out = [[0, 0, -1]]
    for th in (20, 40, 60, 80, 100, 120):         # >90: beak pointing upward (reach up under a ring)
        for ph in range(0, 360, 45):
            t, f = np.radians(th), np.radians(ph)
            out.append([float(np.sin(t)*np.cos(f)), float(np.sin(t)*np.sin(f)), float(-np.cos(t))])
    return out


def track(K, side, P, seed, max_step=MAX_IK_STEP_RAD, approaches=None):
    """Per-sample orientation choice with continuity: keep the previous approach when feasible,
    otherwise switch to another candidate whose joint step stays below max_step (rad per sample).
    Each starting orientation is tried in turn; the first complete track (else the longest) is returned."""
    rots = [(app, roll, approach_rotation(side, app, roll)) for app in (approaches or APPROACH[side]) for roll in (0, 90)]
    best = None
    for start in range(len(rots)):
        r = _track(K, side, P, seed, max_step, rots, start)
        if r['ok']:
            return r
        if best is None or len(r['q']) > len(best['q']):
            best = r
    return best


def rrt_connect(K, side, qa, qb, others=(), iters=4000, step=.2, seed=0):
    """Collision-free joint path qa -> qb for one arm (RRT-Connect + shortcutting), checked against the
    fixture and against every pose in others (the other arm over the transit's time span, so any timing
    is safe). None when no path is found."""
    rng = np.random.default_rng(seed)
    idx = K.qadr[side]
    o_ = 'right' if side == 'left' else 'left'
    lo = np.maximum(LIMITS[:, 0], np.minimum(qa, qb)-1.2)
    hi = np.minimum(LIMITS[:, 1], np.maximum(qa, qb)+1.2)
    others = list(others) or [None]

    def free(q):
        for oq in others:
            qq = K.home.copy()
            qq[idx] = q
            if oq is not None:
                qq[K.qadr[o_]] = oq
            if K.collisions(qq):
                return False
        return True

    def edge(q1, q2):
        n = max(1, int(np.ceil(np.abs(q2-q1).max()/.05)))
        return all(free(q1+(q2-q1)*u) for u in np.linspace(0, 1, n+1)[1:])

    if not free(qa) or not free(qb):
        return None
    if edge(qa, qb):
        return [qa, qb]
    trees = [([np.asarray(qa, float)], [-1]), ([np.asarray(qb, float)], [-1])]

    def extend(tree, target):
        nodes, par = tree
        d = [np.abs(n_-target).max() for n_ in nodes]
        j = int(np.argmin(d))
        q = nodes[j]+(target-nodes[j])*min(1., step/max(d[j], 1e-9))
        if edge(nodes[j], q):
            nodes.append(q)
            par.append(j)
            return len(nodes)-1
        return None

    def chain(tree, j):
        nodes, par = tree
        out = []
        while j != -1:
            out.append(nodes[j])
            j = par[j]
        return out

    for it in range(iters):
        a_, b_ = trees if it % 2 == 0 else trees[::-1]
        target = rng.uniform(lo, hi)
        ja = extend(a_, target)
        if ja is None:
            continue
        # connect the other tree towards the new node greedily
        while True:
            jb = extend(b_, a_[0][ja])
            if jb is None:
                break
            if np.abs(b_[0][jb]-a_[0][ja]).max() < 1e-6:
                pa, pb = chain(a_, ja), chain(b_, jb)
                path = (pa[::-1]+pb[1:]) if a_ is trees[0] else (pb[::-1]+pa[1:])
                for _ in range(60):                       # shortcutting
                    if len(path) < 3:
                        break
                    i1, i2 = sorted(rng.choice(len(path), 2, replace=False))
                    if i2-i1 > 1 and edge(path[i1], path[i2]):
                        path = path[:i1+1]+path[i2:]
                return path
    return None


def _reorient_clear(K, side, q0, q1, p, n=12, tol=MAX_GRIP_ERROR_M):
    """In-place reorientation while holding the cord point p: the joint-linear move q0 -> q1 keeps the
    finger pads within tol of p and touches nothing."""
    from .aloha_ik import to_mj
    target = to_mj(p)
    idx = K.qadr[side]
    for u in np.linspace(0, 1, n)[1:-1]:
        qi = q0.copy()
        qi[idx] = (1-u)*q0[idx]+u*q1[idx]
        K.fk(qi)
        tcp, R = K.tcp(side)
        if np.linalg.norm(tcp+K.PAD*R[:, 0]-target) > tol or K.collisions(qi, sides=(side,)):
            return False
    return True


def _track(K, side, P, seed, max_step, rots, start, max_reorients=2):
    """Per-sample orientation choice with joint continuity; where no orientation continues, at most
    max_reorients in-place reorientations (the gripper turns about the held cord point; the executor pauses
    the cord for them)."""
    q = seed.copy()
    cur = start
    qs, used, fails, reorients = [], [], [], []
    pe = re = 0.
    for k, p in enumerate(P):
        order = [cur]+[j for j in range(len(rots)) if j != cur] if k else [start]
        ok = False
        for j in order:
            qn, e1, e2 = K.solve(side, p, rots[j][2], q)
            if e1 > 2e-3 or e2 > 3e-2:
                continue
            if qs and np.abs(qn[K.qadr[side]]-qs[-1]).max() > max_step:
                continue
            c = K.collisions(qn, sides=(side,))
            if c:
                if j == order[0]:
                    fails.append(dict(k=k, p=np.round(p, 3).tolist(), c=c[:1]))
                continue
            q, cur, ok = qn, j, True
            pe, re = max(pe, e1), max(re, e2)
            break
        if not ok and qs and len(reorients) < max_reorients:
            for j in order:
                qn, e1, e2 = K.solve(side, p, rots[j][2], q)
                if e1 > 2e-3 or e2 > 3e-2 or K.collisions(qn, sides=(side,)):
                    continue
                if _reorient_clear(K, side, q, qn, p):
                    q, cur, ok = qn, j, True
                    pe, re = max(pe, e1), max(re, e2)
                    reorients.append(k)
                    break
        if not ok:
            return dict(ok=False, q=np.array(qs), approach=None if cur is None else rots[cur][0],
                        roll=None if cur is None else rots[cur][1], pos_err=pe, rot_err=re,
                        collisions=fails[-1:] or [dict(k=k, p=np.round(p, 3).tolist(), c='no feasible orientation')],
                        switches=len(set(used)), fail_at=k)
        qs.append(q[K.qadr[side]].copy())
        used.append(cur)
    return dict(ok=True, q=np.array(qs), approach=rots[cur][0], roll=rots[cur][1], pos_err=pe, rot_err=re,
                collisions=[], switches=int(np.sum(np.diff(used) != 0)) if len(used) > 1 else 0, fail_at=None,
                reorients=reorients)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('variant')
    ap.add_argument('run')
    ap.add_argument('--hz', type=float, default=10.)
    ap.add_argument('--fixed-arms', action='store_true', help='gripper A is the left arm, B the right arm')
    a = ap.parse_args(argv)
    run = Path(a.run)
    identity_path = run/'model.json'
    if not identity_path.is_file():
        raise ValueError('Recorded run has no model identity; cannot audit it against local v15 geometry')
    identity = json.loads(identity_path.read_text())
    lay = layout_for(a.variant)
    limits = dict(penetration_m=MAX_PENETRATION_M, grip_error_m=MAX_GRIP_ERROR_M,
                  segment_stretch=MAX_SEGMENT_STRETCH, total_stretch=MAX_TOTAL_STRETCH)
    task = task_for(a.variant)
    if (identity.get('variant') != a.variant or identity.get('layout') != asdict(lay)
            or identity.get('model_revision') != task.model_revision or identity.get('limits') != limits
            or identity.get('task_parameters') != task.identity_config()):
        raise ValueError('Recorded run model/limits differ from the local task')
    fr = np.load(run/'frames.npz', allow_pickle=True)
    ev = json.loads((run/'events.json').read_text())
    t = fr['t']; grips = fr['grips']
    K = AlohaIK(lay)
    eps = episodes(ev, float(t[-1]))
    # arm assignment: interval 2-colouring; prefer the arm on the side of the mean y
    assign = {}
    for i, (g, node, t0, t1) in enumerate(eps):
        m = (t >= t0) & (t <= t1)
        yv = grips[m, 'ABCD'.index(g), 1].mean() if m.any() else 0.
        busy = {assign[j] for j, e in enumerate(eps[:i]) if j in assign and e[3] > t0+1e-6}
        pref = ['left', 'right'] if yv >= 0 else ['right', 'left']
        assign[i] = {'A': 'left', 'B': 'right'}[g] if a.fixed_arms else next(s for s in pref if s not in busy)
    report = []
    grid = np.arange(t[0], t[-1]+1e-9, 1/a.hz)
    chosen = {}                                   # episode -> (arm, first grid index, joint samples)
    options = {}                                  # episode -> (arm, first grid index, complete tracks)
    # the executor uses the dense set (incl. upward-pointing beaks) for aperture hand-overs: audit with both
    rots_all = {s_: [(app, roll, approach_rotation(s_, app, roll))
                     for app in APPROACH[s_]+[a for a in rich_approaches(s_) if a not in APPROACH[s_]] for roll in (0, 90)]
                for s_ in ('left', 'right')}
    for i, (g, node, t0, t1) in enumerate(eps):
        side = assign[i]
        m = (t > t0+1e-6) & (t <= t1)          # the frame at t0 still has the mocap where it was before the grasp
        ts = t[m]
        if len(ts) == 0:
            continue
        sel = np.unique(np.searchsorted(ts, np.arange(ts[0], ts[-1]+1e-9, 1/a.hz)).clip(0, len(ts)-1))
        P = grips[m][sel, 'ABCD'.index(g)]
        keep = P[:, 2] > -.5                     # drop samples taken before the mocap left its parking spot
        P = P[keep]
        i0 = int(np.searchsorted(grid, ts[sel][keep][0]-1e-9)) if keep.any() else 0
        res = None
        if a.fixed_arms:
            opts = [r_ for r_ in (_track(K, side, P, K.home, MAX_IK_STEP_RAD, rots_all[side], st)
                                  for st in range(len(rots_all[side]))) if r_['ok']]
            low = np.array([resting(lay, p_) for p_ in P])
            for dz in ((min(.0015, lay.cord_radius_m/2), min(.003, lay.cord_radius_m)) if not opts and low.any() else ()):
                # a cord lying on the base or table: pinch its upper half, as the planner does
                Pr = P.copy()
                Pr[low, 2] += dz
                opts = [r_ for r_ in (_track(K, side, Pr, K.home, MAX_IK_STEP_RAD, rots_all[side], st)
                                      for st in range(len(rots_all[side]))) if r_['ok']]
                if opts:
                    break
            if opts:
                options[i] = (side, i0, opts)
                res = opts[0]
        if res is None:
            res = track(K, side, P, K.home)
        chosen[i] = (side, i0, res['q'])
        if not res['ok'] and not a.fixed_arms:
            other = 'left' if side == 'right' else 'right'
            busy = {assign[j] for j, e in enumerate(eps) if j != i and e[2] < t1-1e-6 and e[3] > t0+1e-6}
            if other not in busy:
                r2 = track(K, other, P, K.home)
                if r2['ok'] or len(r2['q']) > len(res['q']):
                    res, side = r2, other
                    assign[i] = other
        q = res['q']
        margin = float(np.min(np.minimum(q-LIMITS[:, 0], LIMITS[:, 1]-q))) if len(q) else None
        dq = float(np.abs(np.diff(q, axis=0)).max()*a.hz) if len(q) > 1 else 0.
        rec = dict(episode=i, gripper=g, target=node, t0=round(t0, 2), t1=round(t1, 2), arm=side, samples=len(P),
                   solved=len(q), ok=res['ok'], approach=res['approach'], roll=res['roll'],
                   max_pos_err_m=res['pos_err'], max_rot_err_rad=res['rot_err'], joint_margin_rad=margin,
                   max_joint_speed_rad_s=dq, collisions=res['collisions'], fail_at=res.get('fail_at'),
                   orientation_switches=res.get('switches'), joint_clash=res.get('joint_clash'),
                   path_local_min=np.round(P.min(0), 3).tolist(), path_local_max=np.round(P.max(0), 3).tolist())
        print(json.dumps(rec, default=str), flush=True)
        report.append(rec)
        np.save(run/f'ik_ep{i:02d}_{side}.npy', q)
    if a.fixed_arms and options:
        # backtracking choice of one track per episode so that time-overlapping episodes of the two arms
        # never collide sample by sample
        ids = sorted(options)

        def clash(i_, r_, pick):
            s1, a0, _ = options[i_]
            for j_, rj in pick.items():
                s2, b0, _ = options[j_]
                if s2 == s1:
                    continue
                for k_ in range(len(r_['q'])):
                    kk = a0+k_-b0
                    if 0 <= kk < len(rj['q']):
                        qq = K.home.copy()
                        qq[K.qadr[s1]] = r_['q'][k_]; qq[K.qadr[s2]] = rj['q'][kk]
                        if K.collisions(qq):
                            return True
            return False

        def search(n, pick):
            if n == len(ids):
                return dict(pick)
            for r_ in options[ids[n]][2]:
                if not clash(ids[n], r_, pick):
                    pick[ids[n]] = r_
                    out = search(n+1, pick)
                    if out is not None:
                        return out
                    del pick[ids[n]]
            return None
        best = search(0, {})
        for rec in report:
            e_ = rec['episode']
            if e_ in options:
                r_ = best[e_] if best is not None else options[e_][2][0]
                np.save(run/f"ik_ep{e_:02d}_{rec['arm']}.npy", r_['q'])
                rec.update(approach=r_['approach'], roll=r_['roll'], joint_choice_found=best is not None)
        print(json.dumps(dict(joint_orientation_choice=best is not None, options={k_: len(v_[2]) for k_, v_ in options.items()})))
    # joint timeline for both arms. Episodes use their tracked samples; between episodes an arm retreats
    # 6 cm along its approach, moves to a pre-grasp pose 6 cm before the next grasp and approaches, going
    # via the ready (home) pose and/or lifted copies of the two poses when the direct joint-linear move
    # would hit the fixture (home first when the gap is >= 3 s). Both arms are then checked together.
    home = {s_: np.array(K.home[K.qadr[s_]]) for s_ in ('left', 'right')}

    def backoff(s_, qa):
        qq = K.home.copy()
        qq[K.qadr[s_]] = qa
        K.fk(qq)
        p, R = K.tcp(s_)
        away = -R[:, 0].copy()           # back off along the approach axis, but never downwards
        if away[2] < 0:                  # (an upward-pointing beak under a ring retreats horizontally)
            away[2] = 0.
        away /= max(np.linalg.norm(away), 1e-9)
        up = p+.06*away
        up_local = from_mj(up)+K.PAD*np.array([R[1, 0], -R[0, 0], R[2, 0]])
        qu, e1, _ = K.solve(s_, up_local, R, qq.copy())
        return qu[K.qadr[s_]] if e1 < 2e-3 else qa

    def shifted(s_, qa, d):
        """The same grasp orientation with the TCP moved by the world vector d (None if IK fails)."""
        qq = K.home.copy()
        qq[K.qadr[s_]] = qa
        K.fk(qq)
        p, R = K.tcp(s_)
        up = p+np.asarray(d, float)
        up_local = from_mj(up)+K.PAD*np.array([R[1, 0], -R[0, 0], R[2, 0]])
        qu, e1, _ = K.solve(s_, up_local, R, qq.copy())
        return qu[K.qadr[s_]] if e1 < 2e-3 else None

    def line(s_, qa, d, dist, step=.025):
        """Joint samples of a straight Cartesian move of the TCP by dist along the MJCF-frame direction d
        (same orientation, IK seeded sample to sample), or None where IK fails."""
        d = np.asarray(d, float)/np.linalg.norm(d)
        path, q = [], qa
        for k in range(1, int(np.ceil(dist/step))+1):
            q = shifted(s_, q, d*min(step, dist-(k-1)*step))
            if q is None:
                return None
            path.append(q)
        return path

    def exits(s_, qa):
        """Retreat paths from a grasp: the default back-off first, then straight up (out of a ring aperture),
        longer back-offs along the approach (a gripper slid in under a ring), then down / sideways moves far
        enough to leave a ring's footprint."""
        out = [[backoff(s_, qa)]]
        qq = K.home.copy()
        qq[K.qadr[s_]] = qa
        K.fk(qq)
        p_mj, R = K.tcp(s_)
        p_loc = from_mj(p_mj)+K.PAD*np.array([R[1, 0], -R[0, 0], R[2, 0]])     # the grasp point (task frame)
        # straight up first: a gripper that reached down into a ring aperture can only leave it vertically
        moves = [([0, 0, 1], dist) for dist in (.10, .15, .20, .25)]
        moves += [(-R[:, 0], dist) for dist in (.10, .15)]
        moves += [(v, dist) for v in ([0, 0, -1], [1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0])
                  for dist in ((.06, .10) if v[2] else (.06, .10, .15, .20))]
        for v, dist in moves:
            path = line(s_, qa, v, dist)
            if path is not None:
                out.append(path)
        # straight up out of an aperture with the orientation re-chosen sample by sample (in-place
        # reorientations allowed, as in the episode tracks): a tilted grasp may not rise fixed through a ring
        rots = rots_all[s_]
        start = int(np.argmin([np.linalg.norm(R-r_[2]) for r_ in rots]))
        P_up = np.array([p_loc+np.array([0, 0, dz]) for dz in np.arange(0., .2501, .025)])
        r_up = _track(K, s_, P_up, qq, MAX_IK_STEP_RAD, rots, start)
        if len(r_up['q']) and np.abs(r_up['q'][0]-qa).max() < .05:
            for n_ in (5, 7, 9, 11):          # 10, 15, 20, 25 cm
                if len(r_up['q']) >= n_:
                    out.append(list(r_up['q'][1:n_]))
        return out

    def segment_hits(s_, qs, n):
        """Robot-fixture contacts of this arm along joint-linear legs through qs (n samples per leg)."""
        for qa, qb in zip(qs[:-1], qs[1:]):
            for u in np.linspace(0, 1, n)[1:]:
                qq = K.home.copy()
                qq[K.qadr[s_]] = (1-u)*qa+u*qb
                if K.collisions(qq, sides=(s_,)):
                    return True
        return False

    def timed_keys(ta, tb, ra, pb, via, w=0., q0=None):
        """Retreat path ra (joint samples), optionally hold at its end for a fraction w of the remaining gap
        (letting the other arm pass), then the via poses evenly spaced, the pre-grasp path pb and approach."""
        G = tb-ta
        ea = (min(1.5, .3*G) if len(ra) > 1 else min(.5, .25*G)) if ra else 0.
        eb = (min(1.5, .3*G) if len(pb) > 1 else min(.5, .25*G)) if pb else 0.
        keys = [(ta+ea*(k_+1)/len(ra), q_) for k_, q_ in enumerate(ra or [])]
        keys += [(tb-eb+eb*k_/len(pb), q_) for k_, q_ in enumerate(pb or [])]
        lo, hi = ta+ea, tb-eb
        if w > 0:
            lo += w*(hi-lo)
            keys.append((lo, ra[-1] if ra else (q0 if q0 is not None else keys[0][1])))
        return keys+[(lo+(hi-lo)*(k_+1)/(len(via)+1), qv) for k_, qv in enumerate(via)]

    clash_kinds = {}

    def clashes_other(s_, qa, qb, ta, tb, keys, other):
        """Arm/arm or fixture contact at the grid times of this transit, the other arm on its timeline."""
        if other is None:
            return False
        o_ = 'right' if s_ == 'left' else 'left'
        pts = sorted([(ta, qa), *keys, (tb, qb)], key=lambda k_: k_[0])
        kt = np.array([k_[0] for k_ in pts]); kq = np.array([k_[1] for k_ in pts])
        for j in np.nonzero((grid > ta) & (grid < tb))[0]:
            qq = K.home.copy()
            qq[K.qadr[s_]] = [np.interp(grid[j], kt, kq[:, d]) for d in range(6)]
            qq[K.qadr[o_]] = other[j]
            c = K.collisions(qq)
            if c:
                k_ = (c[0].get('kind'), c[0].get('robot') or c[0].get('a'), c[0].get('fixture') or c[0].get('b'))
                clash_kinds[str(k_)] = clash_kinds.get(str(k_), 0)+1
                return True
        return False

    def transit(s_, qa, qb, ta, tb, ret_a=True, pre_b=True, other=None):
        """Collision-free waypoints (time, q) strictly between ta and tb: a retreat path and a pre-grasp path
        (back-off first, then other directions) joined directly, via home, or via lifted copies."""
        G = tb-ta
        found = None
        why_t = {'fixture': 0, 'other_arm': 0}
        for ra in (exits(s_, qa) if ret_a else [None]):
            for pb in ([p_[::-1] for p_ in exits(s_, qb)] if pre_b else [None]):
                ea, eb = (ra[-1] if ra else qa), (pb[0] if pb else qb)
                options = [[], [home[s_]]]
                for dz in (.06, .12, .18):
                    la, lb = shifted(s_, ea, [0, 0, dz]), shifted(s_, eb, [0, 0, dz])
                    if la is not None and lb is not None:
                        options += [[la, lb], [la, home[s_], lb]]
                if G >= 3.:
                    options.insert(0, [home[s_]])
                for via in options:
                    qs = [qa]+(ra or [])+via+(pb or [])+[qb]
                    if segment_hits(s_, qs, 6):
                        why_t['fixture'] += 1
                        continue
                    # hold (after the retreat, or at the start pose) while the other arm passes, then go; or
                    # stay at the release pose first (an arm that just handed the cord over waits until the
                    # taker has risen away from its fingers), then retreat
                    for w, wp in (((0., 0.), (.4, 0.), (.7, 0.), (.85, 0.), (0., .3), (0., .5), (.3, .4))
                                  if other is not None else ((0., 0.),)):
                        ts_ = ta+wp*G
                        keys_ = timed_keys(ts_, tb, ra, pb, via, w, qa)+([(ts_, qa)] if wp else [])
                        if not clashes_other(s_, qa, qb, ta, tb, keys_, other):
                            found = ra, pb, via, w, wp
                            break
                        why_t['other_arm'] += 1
                    if found:
                        break
                if found:
                    break
            if found:
                break
        if found is None:
            # no menu option: hold still while the other arm finishes its part, then plan a joint path among
            # the fixture and the other arm's poses over the remaining window [ts, tb]
            o_ = 'right' if s_ == 'left' else 'left'
            for w in (0., .5, .8):
                ts = ta+w*(tb-ta)
                if other is not None and w > 0:
                    held = np.nonzero((grid >= ta-1e-9) & (grid <= ts+1e-9))[0]
                    clash = False
                    for j in held:
                        qq = K.home.copy()
                        qq[K.qadr[s_]] = qa
                        qq[K.qadr[o_]] = other[j]
                        if K.collisions(qq):
                            clash = True
                            break
                    if clash:
                        continue
                others = []
                if other is not None:
                    js = np.nonzero((grid >= ts-1e-9) & (grid <= tb+1e-9))[0]
                    others = [other[j] for j in js[::2]]
                path = rrt_connect(K, s_, qa, qb, others)
                if path is not None:
                    inner = path[1:-1]
                    keys = [(ts, qa)] if w > 0 else []
                    return keys+[(ts+(tb-ts)*(k_+1)/(len(inner)+1), q_) for k_, q_ in enumerate(inner)]
            transit_bad.append(dict(arm=s_, t0=round(ta, 2), t1=round(tb, 2), rejected=why_t,
                                    contacts=dict(sorted(clash_kinds.items(), key=lambda kv: -kv[1])[:4])))
            clash_kinds.clear()
            found = ([backoff(s_, qa)] if ret_a else None, [backoff(s_, qb)] if pre_b else None,
                     [home[s_]] if G >= 3. else [], 0., 0.)
        ra, pb, via, w, wp = found
        ts_ = ta+wp*G
        return timed_keys(ts_, tb, ra, pb, via, w, qa)+([(ts_, qa)] if wp else [])

    def timeline(s_, other):
        keys = [(float(grid[0]), home[s_])]          # (time, q) keyframes outside episodes
        fixed = {}                                    # grid index -> q inside episodes
        mine = [r for r in report if r['arm'] == s_ and r['solved']]
        prev_end, prev_q = float(grid[0]), None
        for r in mine:
            q = np.load(run/f"ik_ep{r['episode']:02d}_{s_}.npy")
            ts = r['t0']
            if prev_q is None:
                keys += transit(s_, home[s_], q[0], prev_end, ts, ret_a=False, other=other)
            else:
                keys += transit(s_, prev_q, q[0], prev_end, ts, other=other)
            keys.append((ts, q[0]))
            i0 = int(np.searchsorted(grid, ts-1e-9))
            for j_, qj in enumerate(q):
                if i0+j_ < len(grid):
                    fixed[i0+j_] = qj
            prev_end = float(grid[min(i0+len(q)-1, len(grid)-1)])
            prev_q = q[-1]
            keys.append((prev_end, q[-1]))
        if prev_q is not None:
            n_bad = len(transit_bad)
            tail = transit(s_, prev_q, home[s_], prev_end, prev_end+1.5, pre_b=False, other=other)
            if len(transit_bad) > n_bad:
                # returning home after the run's last grasp is optional: the arm holds its last pose
                # (the next pass starts from there)
                del transit_bad[n_bad:]
                tail = [(prev_end+1.5, prev_q)]
            keys += tail
        kt = np.array([k_[0] for k_ in keys]); kq = np.array([k_[1] for k_ in keys])
        order = np.argsort(kt, kind='stable'); kt, kq = kt[order], kq[order]
        arr = np.array([[np.interp(tt, kt, kq[:, d]) for d in range(6)] for tt in grid])
        for j_, qj in fixed.items():
            arr[j_] = qj
        return arr

    # left alone first, then right around it, then left again around the final right timeline
    transit_bad = []
    left0 = timeline('left', None)
    del transit_bad[:]                                  # left is planned again below
    traj = {'right': timeline('right', left0)}
    traj['left'] = timeline('left', traj['right'])
    joint_bad = []
    for j in range(len(grid)):
        qq = K.home.copy()
        for s_ in ('left', 'right'):
            qq[K.qadr[s_]] = traj[s_][j]
        c = K.collisions(qq)
        if c:
            joint_bad.append(dict(t=round(float(grid[j]), 2), contacts=c[:3]))
    dq_max = max(float(np.abs(np.diff(traj[s_], axis=0)).max()*a.hz) for s_ in ('left', 'right'))
    np.savez_compressed(run/'joint_timeline.npz', t=grid, left=traj['left'], right=traj['right'])
    ok = all(r['ok'] for r in report) and not joint_bad and not transit_bad
    summary = dict(variant=a.variant, run=str(run), episodes=len(report), all_ok=ok,
                   failed=[r['episode'] for r in report if not r['ok']],
                   timeline_collision_samples=len(joint_bad), first_timeline_collisions=joint_bad[:5],
                   transit_failures=transit_bad, timeline_max_joint_speed_rad_s=round(dq_max, 3),
                   # Standard control accepts <= 0.04 rad joint-target change per 25 ms step (1.6 rad/s):
                   # the whole pass (cord motions included, quasi-static) is replayed this much slower
                   standard_time_scale=float(np.ceil(max(1., dq_max/STANDARD_JOINT_SPEED_RAD_S)*100)/100),
                   formal_qualification=False, scope='kinematic audit of a detached MuJoCo planning model')
    (run/'ik_report.json').write_text(json.dumps(dict(summary=summary, episodes=report), default=str, indent=1))
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
