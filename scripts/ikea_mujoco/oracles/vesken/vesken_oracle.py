#!/usr/bin/env python3
"""VESKEN closed-loop reference (privileged mode, rcb_ikea.Session, the final physics with the arm joint-speed clamp).

Phase guide: the original demo (ctrl rows) and its unclamped run (ref_free: every part's pose every 20 rows, each
operation's connector error). The demo's gripper events give each arm's grasp intervals and the part each one carries
(sched.json); the operations' release rows H_k come from the mechanism's own weld events (plan.json).

Operation k = demo rows [H_{k-1}, H_k), executed with feedback from the TRUE state, per arm and row:
  approach (<= APPROACH rows before a grasp): the TCP is offset by where the part really is versus where it was in
      the reference run (translation, plus the part's rotation when it is small), so the hand closes on the part the
      same way;
  carry (grasp interval of a carried part): an integral loop moves the TCP offset (position and orientation) so that
      the part follows its reference pose; near its host the error is the connector error relative to the host
      (the mechanism's own geometry) versus the reference run's;
  idle: the offset decays to zero (and is then exactly zero: the demo row is used as it is).
  press: optional extra depth along the insertion axis before H_k;
  weld: before the release row H_k the controller keeps tracking on the last row until the weld is on (<= wait_s).
Every Cartesian offset becomes joint targets by damped least squares IK on left_tcp / right_tcp. Every emitted row is
speed-limited (a row farther than the limit from the previous applied target is reached over the ticks it needs), so
Session.applied() never changes a recorded row.
A failed gate is corrected locally: run_op() is retried from op k-1's checkpoint with other parameters (search.py).
"""
from __future__ import annotations
import json, math, os, sys
import numpy as np
import mujoco
import rcb_ikea as R

ARM_CTRL = {'left': list(range(0, 7)), 'right': list(range(8, 15))}
# The demo's left arm folds its elbow to j4 = -3.03 rad with the wrist bent (j6 0.68) on its way from home to cap_3
# (rows 324600-325600): the hand hits left_link2 (4.9 kN in the unclamped demo, 6.9 kN in the original reference). The
# motion is replaced by a smooth straight joint-space path between the same end configurations.
DEMO_PATCHES = [('left', 324600, 325600)]
SPEED_MARGIN = 0.999
APPROACH = 1500


def smooth(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def qmul(a, b):
    w, x, y, z = a; W, X, Y, Z = b
    return np.array([w*W-x*X-y*Y-z*Z, w*X+x*W+y*Z-z*Y, w*Y-x*Z+y*W+z*X, w*Z+x*Y-y*X+z*W])


def qconj(q):
    return np.array([q[0], -q[1], -q[2], -q[3]])


def rotvec(q):
    q = q / np.linalg.norm(q)
    if q[0] < 0: q = -q
    s = np.linalg.norm(q[1:])
    if s < 1e-12: return np.zeros(3)
    return q[1:] / s * 2 * math.atan2(s, q[0])


def rotmat(v):
    th = np.linalg.norm(v)
    if th < 1e-12: return np.eye(3)
    k = v / th; K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + math.sin(th) * K + (1 - math.cos(th)) * K @ K


class IK:
    def __init__(self, model):
        self.m = model; self.d = mujoco.MjData(model)
        self.site = {a: model.site(f'{a}_tcp').id for a in ('left', 'right')}
        j = lambda a, i: model.joint(f'{a}_joint{i}').id
        self.qadr = {a: [model.jnt_qposadr[j(a, i)] for i in range(1, 8)] for a in ('left', 'right')}
        self.dadr = {a: [model.jnt_dofadr[j(a, i)] for i in range(1, 8)] for a in ('left', 'right')}
        self.lo = {a: np.array([model.jnt_range[j(a, i)][0] if model.jnt_limited[j(a, i)] else -1e9 for i in range(1, 8)]) for a in ('left', 'right')}
        self.hi = {a: np.array([model.jnt_range[j(a, i)][1] if model.jnt_limited[j(a, i)] else 1e9 for i in range(1, 8)]) for a in ('left', 'right')}
        self.jp = np.zeros((3, model.nv)); self.jr = np.zeros((3, model.nv))

    def fk(self, arm, q):
        self.d.qpos[self.qadr[arm]] = q
        mujoco.mj_kinematics(self.m, self.d)
        s = self.site[arm]
        return self.d.site_xpos[s].copy(), self.d.site_xmat[s].reshape(3, 3).copy()

    def solve(self, arm, q0, p_goal, R_goal, iters=20):
        q = np.array(q0, float); s = self.site[arm]
        for _ in range(iters):
            self.d.qpos[self.qadr[arm]] = q
            mujoco.mj_kinematics(self.m, self.d); mujoco.mj_comPos(self.m, self.d)
            p = self.d.site_xpos[s]; Rm = self.d.site_xmat[s].reshape(3, 3)
            ep = p_goal - p; Re = R_goal @ Rm.T
            er = 0.5 * np.array([Re[2, 1] - Re[1, 2], Re[0, 2] - Re[2, 0], Re[1, 0] - Re[0, 1]])
            if np.linalg.norm(ep) < 1e-7 and np.linalg.norm(er) < 1e-6:
                break
            mujoco.mj_jacSite(self.m, self.d, self.jp, self.jr, s)
            J = np.vstack([self.jp[:, self.dadr[arm]], self.jr[:, self.dadr[arm]]])
            dq = J.T @ np.linalg.solve(J @ J.T + 1e-4 * np.eye(6), np.r_[ep, er])
            q = np.clip(q + dq, self.lo[arm], self.hi[arm])
        return q


class Runner:
    def __init__(self, demo_path, ref_dir):
        self.demo = np.ascontiguousarray(np.load(demo_path)['ctrl'], dtype=np.float64)
        for arm, a, b in DEMO_PATCHES:                  # joint-space re-paths of demo arm motions (see DEMO_PATCHES)
            cols = ARM_CTRL[arm]; q0, q1 = self.demo[a - 1, cols].copy(), self.demo[b, cols].copy()
            for i in range(a, b):
                w = smooth((i - a + 1) / (b - a + 1))
                self.demo[i, cols] = q0 + w * (q1 - q0)
        self.plan = json.load(open(os.path.join(ref_dir, 'plan.json')))
        self.sched = json.load(open(os.path.join(ref_dir, 'sched.json')))
        z = np.load(os.path.join(ref_dir, 'pos_free.npz'))
        self.pf = z['pose']; self.pf_parts = list(z['parts'])
        ez = np.load(os.path.join(ref_dir, 'eref_free.npz'))
        self.ef = {k: ez[k] for k in ez.files}
        self.ef_idx = {k: {int(r[0]): n for n, r in enumerate(v)} for k, v in self.ef.items()}
        self.s = R.Session('vesken')
        self.m, self.d = self.s.model, self.s.data
        self.mech = self.s.S.mech
        self.ops = self.s.S.task['operations']
        self.op_of_part = {o['part']: n for n, o in enumerate(self.ops)}
        self.ik = IK(self.m)
        self.lim = self.s.step_limit * SPEED_MARGIN
        self.fin = np.isfinite(self.lim)
        self.parts = self.s.S.task['parts']
        self.bid = {n: self.m.body(n).id for n in self.parts}
        self.home = {n: self.d.xpos[self.bid[n]].copy() for n in self.parts}
        self.off = {a: dict(p=np.zeros(3), r=np.zeros(3)) for a in ('left', 'right')}
        self.gb = self.m.geom_bodyid
        self.robot = np.zeros(self.m.nbody, bool); self.robot[R.robot_bodies(self.m)] = True
        self.rr_max = (0., None, 0)
        self.p = {}
        # per arm: row -> interval lookup
        self.ivs = {a: [(it['cs'], it['oe'], it['part'], it['carried']) for it in self.sched[a]] for a in ('left', 'right')}

    # ------------------------------------------------------------ state
    def checkpoint(self):
        st = self.s.get_state(); rows = np.array(st.pop('rows')); st['rows'] = []
        return dict(st=st, rows=rows, off={a: {k: v.copy() for k, v in o.items()} for a, o in self.off.items()}, rr_max=self.rr_max)

    def restore(self, ck):
        st = dict(ck['st']); st['rows'] = list(ck['rows'])
        self.s.set_state(st)
        self.off = {a: {k: v.copy() for k, v in o.items()} for a, o in ck['off'].items()}; self.rr_max = ck['rr_max']

    # ------------------------------------------------------------ reference lookups
    def pref(self, name, i):
        """reference (free-run) pose of a part at demo row i (linear in position, nearest in rotation)."""
        j = self.pf_parts.index(name); k = i / 20.; k0 = min(int(k), len(self.pf) - 1); k1 = min(k0 + 1, len(self.pf) - 1)
        w = k - k0
        p = (1 - w) * self.pf[k0, j, :3] + w * self.pf[k1, j, :3]
        q = self.pf[k0 if w < 0.5 else k1, j, 3:]
        return p, q

    def eref(self, key, i):
        idx = self.ef_idx[key]; k = (i // 20) * 20
        n = idx.get(k)
        return None if n is None else self.ef[key][n, 1:4]

    def conn_error(self, o):
        from ikea_runtime import rotate
        mech = self.mech; d = self.d
        P = o['part']; pp = d.xpos[mech.bid[P]]; qp = d.xquat[mech.bid[P]]; qh = d.xquat[mech.bid[o['host']]]
        out = rotate(qh, o['outward']); errs = []
        for c in o['connectors']:
            r = c['receiver']; pt = np.asarray(c['point'], float)
            errs.append(pp + rotate(qp, pt - mech.c[P]) - (d.xpos[mech.bid[r]] + rotate(d.xquat[mech.bid[r]], pt - mech.c[r])))
        return np.mean(errs, axis=0), out

    def mode(self, arm, i):
        for cs, oe, part, carried in self.ivs[arm]:
            if cs <= i < oe:
                return ('carry' if carried else 'frozen'), part, cs
            if i < cs:
                if cs - i <= self.p.get('approach', APPROACH):
                    return 'approach', part, cs
                return 'idle', None, None
        return 'idle', None, None

    # ------------------------------------------------------------ control
    def control(self, i, tcp_ref):
        p = self.p
        for arm in ('left', 'right'):
            o = self.off[arm]
            md, part, cs = self.mode(arm, i)
            if md == 'approach' and p.get('ff', True):
                b = self.bid[part]
                pa, qa = self.d.xpos[b], self.d.xquat[b]
                pr, qr = self.pref(part, i)
                dr = rotvec(qmul(qa, qconj(qr)))
                if np.linalg.norm(dr) > p.get('ff_rot_max', 0.25) or not p.get('ff_rot', True):
                    dr = np.zeros(3)
                tp, tR = tcp_ref[arm]
                tgt_p = pa + rotmat(dr) @ (tp - pr) - tp
                a = p.get('ff_rate', 1 / 150.)
                o['p'] += a * (tgt_p - o['p']); o['r'] += a * (dr - o['r'])
            elif md == 'carry':
                k = self.op_of_part.get(part)
                e = None
                if k is not None and not self.mech.connected(self.ops[k]['key']):
                    er = self.eref(self.ops[k]['key'], i)
                    if er is not None and np.linalg.norm(er) < p.get('rel_zone', 0.06):
                        ea, _ = self.conn_error(self.ops[k]); e = ea - er
                b = self.bid[part]
                pr, qr = self.pref(part, i)
                if e is None:
                    e = self.d.xpos[b] - pr
                erot = rotvec(qmul(self.d.xquat[b], qconj(qr)))
                n_hold = 2 if any(self.mode(x, i)[1] == part and self.mode(x, i)[0] == 'carry' for x in ('left', 'right') if x != arm) else 1
                g = p.get('g', 0.01) / n_hold; gr = p.get('gr', 0.005) / n_hold
                if self.mech.connected(self.ops[k]['key']) if k is not None else False:
                    g = gr = 0.                                  # welded: hold the offset until the release
                o['p'] -= g * e
                if p.get('rot', True):
                    o['r'] -= gr * erot
                npn = np.linalg.norm(o['p']); lim = p.get('max_off', 0.03)
                if npn > lim: o['p'] *= lim / npn
                nr = np.linalg.norm(o['r'])
                if nr > 0.3: o['r'] *= 0.3 / nr
            elif md == 'frozen':
                pass
            else:
                o['p'] *= (1 - 1 / 300.); o['r'] *= (1 - 1 / 300.)
                if np.linalg.norm(o['p']) < 2e-6 and np.linalg.norm(o['r']) < 1e-5:
                    o['p'][:] = 0; o['r'][:] = 0

    def emit(self, row):
        row = np.clip(np.asarray(row, float), self.s._clo, self.s._chi)
        prev = self.d.ctrl.copy(); dlt = row - prev
        r = float(np.max(np.abs(dlt[self.fin]) / self.lim[self.fin]))
        n = max(1, int(math.ceil(r - 1e-12)))
        for k in range(1, n + 1):
            self.s.step(row if k == n else prev + dlt * (k / n))
            self._rr()

    def _rr(self):
        d = self.d; n = d.ncon
        if not n: return
        b1 = self.gb[d.contact.geom1[:n]]; b2 = self.gb[d.contact.geom2[:n]]
        sel = np.flatnonzero(self.robot[b1] & self.robot[b2])
        if len(sel):
            adr = d.contact.efc_address[sel]
            f = np.where(adr >= 0, d.efc_force[np.maximum(adr, 0)], 0.)
            j = int(np.argmax(f))
            if f[j] > self.rr_max[0]:
                self.rr_max = (float(f[j]), (self.m.body(int(b1[sel[j]])).name, self.m.body(int(b2[sel[j]])).name), len(self.s.rows))

    def step_row(self, i, extra=None):
        row = self.demo[i].copy()
        tcp_ref = {a: self.ik.fk(a, row[ARM_CTRL[a]]) for a in ('left', 'right')}
        self.control(i, tcp_ref)
        for a in ('left', 'right'):
            dp = self.off[a]['p'] + (extra.get(a, 0) if extra else 0); dr = self.off[a]['r']
            if np.linalg.norm(dp) > 0 or np.linalg.norm(dr) > 0:
                tp, tR = tcp_ref[a]
                row[ARM_CTRL[a]] = self.ik.solve(a, row[ARM_CTRL[a]], tp + dp, rotmat(dr) @ tR)
        self.emit(row)

    # ------------------------------------------------------------ one operation
    def run_op(self, k, p, log=None):
        self.p = p
        o = self.ops[k]; key = o['key']; pl = self.plan['ops'][k]
        start = self.plan['ops'][k - 1]['H'] if k > 0 else 0
        Z, H = pl['Z'], pl['H']
        depth = p.get('depth', 0.0)
        _, out_w = self.conn_error(o)
        for i in range(start, H):
            extra = None
            if depth and H - 200 > Z:
                w = smooth((i - Z) / max(200., (H - 200 - Z)))
                extra = {a: -out_w * depth * w for a in pl['arms']}
            self.step_row(i, extra)
        waited = 0; wmax = int(p.get('wait_s', 1.5) / self.s.control_dt)
        seek = 0.; base = depth if (depth and H - 200 > Z) else 0.
        while not self.mech.connected(key) and waited < wmax:
            mt = self.mech.metrics.get(key)
            # press until the snap is seated against the host: seated but no contact force -> push a little deeper
            if p.get('seek', True) and mt and abs(mt['gap_m']) < 0.0006 and mt['contact_N'] < p.get('seek_N', 0.1):
                seek = min(seek + p.get('seek_step', 0.0001), p.get('seek_max', 0.003))
            extra = {a: -out_w * (base + seek) for a in pl['arms']}
            for _ in range(20):
                self.step_row(H - 1, extra)
            waited += 20
        if log is not None: log.append(('seek', seek))
        ok = self.mech.connected(key)
        later = {x['part'] for x in self.ops[k + 1:]}
        dist = 0.; worst = None
        for n in later:
            if n.startswith(('foot', 'cap')):
                continue
            dd = float(np.linalg.norm(self.d.xpos[self.bid[n]] - self.home[n]))
            if dd > dist: dist, worst = dd, n
        # reference tracking quality of every part at H (vs the free run)
        dev = {n: round(1000 * float(np.linalg.norm(self.d.xpos[self.bid[n]] - self.pref(n, H)[0])), 1) for n in self.parts}
        g, l, a = self.mech.geometry(o)
        return dict(key=key, ok=ok, waited=waited, rows=len(self.s.rows), disturb_mm=round(1000 * dist, 2), disturb_part=worst,
                    gap_mm=round(1000 * g, 3), lat_mm=round(1000 * l, 3), ax=round(a, 3), metrics=self.mech.metrics.get(key),
                    rr=self.rr_max, params=p, engaged=sorted(self.mech.engaged_at), dev=dev)

    def tail(self, p):
        self.p = p
        for i in range(self.plan['ops'][-1]['H'], len(self.demo)):
            self.step_row(i)
        self.hold_rest(p.get('rest_s', 0.5))

    def hold_rest(self, sec):
        row = self.d.ctrl.copy()
        for _ in range(int(sec / self.s.control_dt)):
            self.s.step(row); self._rr()


CANDIDATES = [
    dict(),
    dict(g=0.02, gr=0.01),
    dict(g=0.005, gr=0.0025),
    dict(rot=False, ff_rot=False),
    dict(approach=800),
    dict(g=0.02, gr=0.01, depth=0.002),
    dict(depth=0.002, wait_s=2.5),
    dict(ff=False),
]
