"""STENERIK source mechanisms (f27 fasteners): post-contact retention welds and the pad backing release.

Ported from the source's fastener operations (contact operation, pad release) and its connect step. The source replaces
a fastened / pressed contact by an ideal fixed joint once measured geometric, contact and dwell
gates hold; here a MuJoCo weld (inactive until then) is switched on with the CURRENT relative pose.
Nothing is moved by the mechanism: parts only move through contact and the robots.

Non-contact mechanisms (all MuJoCo weld equalities, task.json['welds']):
  * ret_crossbar_screw_i   screw_i -> crossbar, when a screw is seated in an insert: |gap| < 0.1 mm,
                           lateral < 0.6 mm, tilt < 1.5 deg, speed < 0.02 m/s, axial travel > 1 mm,
                           mean (48 ms) contact > 0.01 N with BOTH the crossbar and the support it
                           passes through, >= 0.4 turns and > 1e-5 J of tightening work (torque about the
                           axis from robot contacts -- fingers or the robot-held screwdriver -- or an applied
                           wrench x rotation) while engaged, all
                           held for 0.15 s.  Threads themselves are geometric SDF contact.
  * join_crossbar_support_k  support -> crossbar, switched on together with the third screw of
                           that side (source: on screw_3 / screw_6, the last screw of each side).
  * adhesive_<support>_pad_i  pad -> support, when a pad (already released from the backing) sits on a
                           pad site: |gap| < 0.1 mm (and >= -0.5 mm), lateral < 0.6 mm, angle < 1.5 deg,
                           speed < 0.02 m/s, travel > 1 mm, mean pad-support contact > 1 N, for 0.30 s.
  * backing_pad_i          pad -> backing, ACTIVE at start (packaged adhesive); switched off once the
                           weld has to pull the pad back towards the backing with >= 1.5 N along the
                           backing normal for 0.25 s (source: declared 1.5 N / 0.25 s release surrogate).
Screws and pads are identical parts: any screw may fill any insert and any pad any site; any of the
two (identical) supports may be the left or right one. Supports, crossbar and backing have no welds
to the world (the source's diagnostic world fixtures are replaced by the robots).
"""
import math, collections
import numpy as np
import mujoco
from ikea_runtime import qmul, qinv, rotate, quat_angle_deg, axis_angle_deg

def _ang_axis_deg(qa, qb_axis_world):
    return axis_angle_deg(rotate(qa, [0, 0, 1]), qb_axis_world)

class StenerikMechanism:
    PERIOD = 4                      # update every 4 physics steps (4 ms; source ran at 240 Hz)

    def __init__(self, model, data, task):
        self.m, self.d, self.t = model, data, task
        m = model
        self.g = task['gates']
        self.bid = {k: m.body(k).id for k in task['parts']}
        self.geom_body = m.geom_bodyid.copy()
        self.robot = np.array([m.body(i).name.startswith(('left_', 'right_')) for i in range(m.nbody)])
        # hand tools held by the robot (cross screwdriver): their contact torque on a screw is robot torque
        for i in range(m.nbody):
            if m.body(i).name in ('screwdriver',): self.robot[i] = True
        self.part_mask = np.zeros(m.nbody, bool); self.part_mask[list(self.bid.values())] = True
        self.bench_geom = m.geom('bench').id
        self.dof = {k: m.jnt_dofadr[m.body_jntadr[b]] for k, b in self.bid.items()}
        self.qadr = {k: m.jnt_qposadr[m.body_jntadr[b]] for k, b in self.bid.items()}
        self.eq = {w['eq']: m.equality(w['eq']).id for w in task['welds']}
        self.eq_init = {w['eq']: bool(w['initially_active']) for w in task['welds']}
        self.eq_data0 = m.eq_data.copy()
        self.screws = ['screw_%d' % i for i in range(1, 7)]
        self.pads = ['pad_%d' % i for i in range(1, 5)]
        self.supports = ['support_1', 'support_2']
        self.inserts = np.array(task['inserts'])
        self.side_rel = {s: np.array(v) for s, v in task['side_support_rel_crossbar'].items()}
        self.pad_box = {k: np.array(v) for k, v in task['pad_box_quat'].items()}
        # one flat (front) and one sloped (rear) site per support, identical in each support frame
        self.site_types = {'flat': task['pad_sites'][0], 'slope': task['pad_sites'][1]}
        self.nwin = int(round(self.g['contact_window_s'] / (self.PERIOD * m.opt.timestep)))
        self.dt = self.PERIOD * m.opt.timestep
        self._cf = None
        self.reset()

    # ------------------------------------------------------------- bookkeeping
    def reset(self):
        self.m.eq_data[:] = self.eq_data0
        for n, i in self.eq.items():
            self.d.eq_active[i] = int(self.eq_init[n])
        self.counter = 0
        self._cf = None
        self.trk = {}            # tracker key -> dict
        self.release_dwell = {p: 0. for p in self.pads}
        self.filled = {}         # insert index -> screw
        self.pad_at = {}         # 'support|type' -> pad
        self.ops = {}            # chronology: op key -> sim time accepted
        self.place_dwell = {}
        self.metrics = {}
        self.initial = {k: self.d.xpos[b].copy() for k, b in self.bid.items()}

    def active(self, name):
        return bool(self.d.eq_active[self.eq[name]])

    def state(self):
        def enc(v):
            if isinstance(v, np.ndarray): return v.tolist()
            if isinstance(v, collections.deque): return [dict(x) for x in v]
            return v
        return dict(counter=self.counter, release_dwell=dict(self.release_dwell), filled=dict(self.filled),
                    pad_at=dict(self.pad_at), ops=dict(self.ops), place_dwell=dict(self.place_dwell),
                    initial={k: v.tolist() for k, v in self.initial.items()},
                    trk={k: {a: enc(b) for a, b in v.items()} for k, v in self.trk.items()},
                    eq_data={n: self.m.eq_data[i].tolist() for n, i in self.eq.items()},
                    eq_active={n: bool(self.d.eq_active[i]) for n, i in self.eq.items()})

    def set_state(self, s):
        self.counter = s['counter']; self.release_dwell = dict(s['release_dwell'])
        self.filled = {int(k): v for k, v in s['filled'].items()}; self.pad_at = dict(s['pad_at'])
        self.ops = dict(s['ops']); self.place_dwell = dict(s['place_dwell'])
        self.initial = {k: np.array(v) for k, v in s['initial'].items()}
        self.trk = {}
        for k, v in s['trk'].items():
            v = dict(v)
            if 'prev_q' in v and v['prev_q'] is not None: v['prev_q'] = np.array(v['prev_q'])
            if 'win' in v: v['win'] = collections.deque(v['win'], maxlen=self.nwin)
            self.trk[k] = v
        for n, i in self.eq.items():
            self.m.eq_data[i] = s['eq_data'][n]; self.d.eq_active[i] = int(s['eq_active'][n])

    # ------------------------------------------------------------- measurements
    def pose(self, k):
        b = self.bid[k]
        return self.d.xpos[b].copy(), self.d.xquat[b].copy()

    def speed(self, k):
        a = self.dof[k]
        return float(np.linalg.norm(self.d.qvel[a:a + 3]))

    def _contacts(self):
        """Net contact force vectors between body pairs (on first from second) and robot torque on screws."""
        if self._cf is not None:
            return self._cf
        m, d = self.m, self.d; n = d.ncon
        pair = collections.defaultdict(lambda: np.zeros(3)); rtorque = collections.defaultdict(lambda: np.zeros(3))
        if n:
            g1 = d.contact.geom1[:n]; g2 = d.contact.geom2[:n]
            b1 = self.geom_body[g1]; b2 = self.geom_body[g2]
            sel = np.nonzero(self.part_mask[b1] | self.part_mask[b2])[0]
            frames = d.contact.frame[:n]; pos = d.contact.pos[:n]
            f6 = np.zeros(6)
            for i in sel:
                mujoco.mj_contactForce(m, d, int(i), f6)
                fw = frames[i].reshape(3, 3).T @ f6[:3]            # force on body2 from body1 (world)
                x1, x2 = int(b1[i]), int(b2[i])
                pair[(x2, x1)] += fw; pair[(x1, x2)] -= fw
                for rb, sb, f in ((x1, x2, fw), (x2, x1, -fw)):
                    if self.robot[rb] and self.part_mask[sb]:
                        rtorque[sb] += np.cross(pos[i] - d.xpos[sb], f)
        self._cf = (pair, rtorque)
        return self._cf

    def force(self, a, b):
        pair, _ = self._contacts()
        v = pair.get((self.bid[a], self.bid[b]))
        return 0. if v is None else float(np.linalg.norm(v))

    def bench_force(self, a):
        """Net contact force on body a from the bench geom (vector)."""
        m, d = self.m, self.d; n = d.ncon; tot = np.zeros(3); f6 = np.zeros(6); ia = self.bid[a]
        for i in range(n):
            c = d.contact[i]
            if c.geom1 == self.bench_geom and self.geom_body[c.geom2] == ia:
                s = 1.
            elif c.geom2 == self.bench_geom and self.geom_body[c.geom1] == ia:
                s = -1.
            else:
                continue
            mujoco.mj_contactForce(m, d, i, f6)
            tot += s * (c.frame.reshape(3, 3).T @ f6[:3])
        return tot

    def weld_force_on_body2(self, name):
        """World force the weld applies on its body2 (from the constraint rows of this weld)."""
        m, d = self.m, self.d; i = self.eq[name]
        rows = np.nonzero((d.efc_type[:d.nefc] == mujoco.mjtConstraint.mjCNSTR_EQUALITY) & (d.efc_id[:d.nefc] == i))[0]
        if not len(rows):
            return np.zeros(3)
        dof = self.dof[m.body(m.eq_obj2id[i]).name]
        f = np.zeros(3)
        if mujoco.mj_isSparse(m):
            for r in rows:
                a, nnz = d.efc_J_rowadr[r], d.efc_J_rownnz[r]
                cols = d.efc_J_colind[a:a + nnz]; vals = d.efc_J[a:a + nnz]
                for c, v in zip(cols, vals):
                    if dof <= c < dof + 3: f[c - dof] += v * d.efc_force[r]
        else:
            J = d.efc_J[:d.nefc * m.nv].reshape(d.nefc, m.nv)
            f = J[rows, dof:dof + 3].T @ d.efc_force[rows]
        return f

    def side_support(self, side):
        """The support standing at the crossbar's left (L) / right (R) side (nearest to that pose)."""
        pc, qc = self.pose('crossbar')
        want = pc + rotate(qc, self.side_rel[side])
        return min(self.supports, key=lambda s: float(np.linalg.norm(self.pose(s)[0] - want)))

    def support_side(self, s):
        pc, qc = self.pose('crossbar')
        return 'L' if rotate(qinv(qc), self.pose(s)[0] - pc)[0] < 0 else 'R'

    def insert_target(self, k):
        pc, qc = self.pose('crossbar')
        return pc + rotate(qc, self.inserts[k]), qc

    def site_target(self, s, typ):
        ps, qs = self.pose(s); st = self.site_types[typ]
        return ps + rotate(qs, st['pos']), qmul(qs, st['box_quat']), qs

    # ------------------------------------------------------------- welds
    def engage(self, name):
        i = self.eq[name]; m, d = self.m, self.d
        b1, b2 = m.eq_obj1id[i], m.eq_obj2id[i]
        p1, q1 = d.xpos[b1], d.xquat[b1]; p2, q2 = d.xpos[b2], d.xquat[b2]
        m.eq_data[i, 0:3] = 0; m.eq_data[i, 3:6] = rotate(qinv(q1), p2 - p1); m.eq_data[i, 6:10] = qmul(qinv(q1), q2)
        m.eq_data[i, 10] = 1; d.eq_active[i] = 1

    def accept(self, op):
        if op not in self.ops:
            self.ops[op] = float(self.d.time)

    # ------------------------------------------------------------- per-update gates
    def _window(self, tr, vals):
        w = tr.setdefault('win', collections.deque(maxlen=self.nwin)); w.append(vals)
        return {k: float(np.mean([x[k] for x in w])) for k in vals}

    def _screws(self):
        g = self.g; free = [s for s in self.screws if not self.active('ret_crossbar_screw_%s' % s[-1])]
        open_ins = [k for k in range(6) if k not in self.filled]
        if not free or not open_ins:
            return
        pc, qc = self.pose('crossbar'); ax = rotate(qc, [0, 0, 1])
        tg = pc + np.array([rotate(qc, self.inserts[k]) for k in open_ins])
        sp = np.array([self.d.xpos[self.bid[s]] for s in free])
        dist = np.linalg.norm(sp[:, None, :] - tg[None, :, :], axis=-1)
        live = set()
        for a, s in enumerate(free):
            for b, k in enumerate(open_ins):
                if dist[a, b] > 0.022:
                    continue
                ps, qs = self.pose(s); dl = ps - tg[b]; gap = float(dl @ ax); lat = float(np.linalg.norm(dl - gap * ax))
                tilt = _ang_axis_deg(qs, ax)
                if not (-0.001 < gap < 0.020 and lat < 0.002 and tilt < 15):
                    continue
                key = 'screw|%s|%d' % (s, k); live.add(key)
                tr = self.trk.setdefault(key, dict(turns=0., work=0., max_gap=gap, prev_q=None, dwell=0.))
                qrel = qmul(qinv(qc), qs)
                if tr['prev_q'] is not None:
                    dq = qmul(qrel, qinv(tr['prev_q']))
                    if dq[0] < 0: dq = -dq
                    step = 2 * math.atan2(float(dq[3]), float(dq[0]))
                    tr['turns'] += step / (2 * math.pi)
                    # driving torque about the axis: robot finger contacts (+ any applied wrench, test rigs)
                    tau = float((self._contacts()[1].get(self.bid[s], np.zeros(3)) + self.d.xfrc_applied[self.bid[s], 3:6]) @ ax)
                    tr['work'] += max(0., tau * step)
                tr['prev_q'] = qrel; tr['max_gap'] = max(tr['max_gap'], gap)
                side = self.t['insert_side'][k]; through = self.side_support(side)
                c = self._window(tr, dict(crossbar=self.force(s, 'crossbar'), through=self.force(s, through)))
                contact = min(c.values())
                ok = (abs(gap) < g['axial_m'] and lat < g['lateral_m'] and tilt < g['axis_deg'] and self.speed(s) < g['speed_m_s']
                      and tr['max_gap'] - gap > g['travel_m'] and contact > g['contact_N'] and abs(tr['turns']) > g['turns']
                      and tr['work'] > g['work_J'])
                tr['dwell'] = tr['dwell'] + self.dt if ok else 0.
                self.metrics[key] = dict(gap_m=gap, lateral_m=lat, tilt_deg=tilt, speed_m_s=self.speed(s), travel_m=tr['max_gap'] - gap,
                                         contact_N=c, turns=tr['turns'], work_J=tr['work'], dwell_s=tr['dwell'], through=through)
                if tr['dwell'] >= g['dwell_s']:
                    self.engage('ret_crossbar_screw_%s' % s[-1]); self.filled[k] = s; self.accept('screw_%d' % (k + 1))
                    side_ins = [j for j in range(6) if self.t['insert_side'][j] == side]
                    if all(j in self.filled for j in side_ins):
                        self.engage('join_crossbar_%s' % through)
                    return
        for key in [x for x in self.trk if x.startswith('screw|') and x not in live]:
            del self.trk[key]; self.metrics.pop(key, None)

    def _pads(self):
        g = self.g; live = set()
        for p in self.pads:
            if self.active('backing_%s' % p) or any(self.active('adhesive_%s_%s' % (s, p)) for s in self.supports):
                continue
            pp, qp = self.pose(p); qbox = qmul(qp, self.pad_box[p])
            for s in self.supports:
                for typ in ('flat', 'slope'):
                    sk = '%s|%s' % (s, typ)
                    if sk in self.pad_at:
                        continue
                    tp, tq, qs = self.site_target(s, typ)
                    if np.linalg.norm(pp - tp) > 0.045:
                        continue
                    ax = rotate(qs, [0, 0, 1]); dl = pp - tp; gap = float(dl @ ax); lat = float(np.linalg.norm(dl - gap * ax))
                    ang = quat_angle_deg(qbox, tq)
                    if not (-0.001 < gap < 0.040 and lat < 0.010 and ang < 20):
                        continue
                    key = 'pad|%s|%s' % (p, sk); live.add(key)
                    tr = self.trk.setdefault(key, dict(max_gap=gap, dwell=0.))
                    tr['max_gap'] = max(tr['max_gap'], gap)
                    c = self._window(tr, dict(support=self.force(p, s)))['support']
                    ok = (abs(gap) < g['axial_m'] and gap >= g['pad_min_gap_m'] and lat < g['lateral_m'] and ang < g['axis_deg']
                          and self.speed(p) < g['speed_m_s'] and tr['max_gap'] - gap > g['travel_m']
                          and c > g['contact_N'] and c > g['pad_contact_N'])
                    tr['dwell'] = tr['dwell'] + self.dt if ok else 0.
                    self.metrics[key] = dict(gap_m=gap, lateral_m=lat, angle_deg=ang, speed_m_s=self.speed(p),
                                             travel_m=tr['max_gap'] - gap, contact_N=c, dwell_s=tr['dwell'])
                    if tr['dwell'] >= g['pad_dwell_s']:
                        self.engage('adhesive_%s_%s' % (s, p)); self.pad_at[sk] = p
                        src = {('L', 'flat'): 1, ('L', 'slope'): 2, ('R', 'flat'): 3, ('R', 'slope'): 4}[(self.support_side(s), typ)]
                        self.accept('press_pad_%d' % src)
                        return
        for key in [x for x in self.trk if x.startswith('pad|') and x not in live]:
            del self.trk[key]; self.metrics.pop(key, None)

    def _release(self):
        g = self.g
        for p in self.pads:
            w = 'backing_%s' % p
            if not self.active(w):
                continue
            _, qb = self.pose('backing'); n = rotate(qb, [0, 0, 1])
            pull = -float(self.weld_force_on_body2(w) @ n)
            self.release_dwell[p] = self.release_dwell[p] + self.dt if pull >= g['release_force_N'] else 0.
            if pull > 0.05:
                self.metrics['release|' + p] = dict(pull_N=pull, dwell_s=self.release_dwell[p])
            if self.release_dwell[p] >= g['release_s']:
                self.d.eq_active[self.eq[w]] = 0
                self.accept('release_%s' % p)
                self.metrics.pop('release|' + p, None)

    def _places(self):
        """Chronology only (source place / mate operations; their world fixtures are not ported)."""
        g = self.g; wt = self.t['world_targets']
        cands = [('place_left_support', wt['support_1'], self.supports, 'bench'),
                 ('place_right_support', wt['support_2'], self.supports, 'bench'),
                 ('mate_crossbar', wt['crossbar'], ['crossbar'], 'supports')]
        for op, tgt, bodies, cp in cands:
            if op in self.ops:
                continue
            ok_any = False
            for k in bodies:
                p, q = self.pose(k); dl = p - np.array(tgt)
                if np.linalg.norm(dl) > 0.005:
                    continue
                gap = float(dl[2]); lat = float(np.linalg.norm(dl[:2])); ang = quat_angle_deg(q, [1, 0, 0, 0])
                if cp == 'bench':
                    c = float(np.linalg.norm(self.bench_force(k)))
                else:
                    c = min(self.force(k, s) for s in self.supports)
                ok_any |= (abs(gap) < g['axial_m'] and lat < g['lateral_m'] and ang < g['axis_deg'] and self.speed(k) < g['speed_m_s']
                           and np.linalg.norm(p - self.initial[k]) > g['travel_m'] and c > g['contact_N'])
            self.place_dwell[op] = self.place_dwell.get(op, 0.) + self.dt if ok_any else 0.
            if self.place_dwell[op] >= g['dwell_s']:
                self.accept(op)

    def update(self):
        self.counter += 1
        if self.counter % self.PERIOD:
            return
        self._cf = None
        self._release()
        self._screws()
        self._pads()
        self._places()

    def chronology(self):
        order = [o['key'] for o in self.t['operations']]
        times = [self.ops.get(k) for k in order]
        done = [t for t in times if t is not None]
        in_order = all(t is not None for t in times) and all(a <= b for a, b in zip(times, times[1:]))
        return dict(accepted={k: self.ops.get(k) for k in order}, n_accepted=len(done), all_in_source_order=bool(in_order))
