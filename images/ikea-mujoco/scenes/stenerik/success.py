"""STENERIK success criteria (used through scene.load().success()).

Port of the source grader (check_success = endpoint_report AND strict_support):

endpoint_report
  * hardware: every one of the 6 crossbar inserts holds a screw that is retained (screw->crossbar weld
    on) and aligned both to the crossbar insert and to the hole of the support it passes through:
    |axial gap| < 0.1 mm, lateral < 0.6 mm, thread-axis tilt < 1.5 deg, speed < 0.02 m/s;
  * structure: both supports joined to the crossbar (join weld on) and aligned to their side pose:
    gap < 0.1 mm, lateral < 0.6 mm, orientation < 1.5 deg, speed < 0.02 m/s;
  * pads: each of the 4 pad sites (flat front rail + sloped rail of each support) holds a pad that is
    bonded to that support, no longer bonded to the backing, and aligned (same gates, box frame);
  * released: no fixture holds a part -> here: no robot contact with any included part
    (all parts except the backing strip);
  * settled: every included part slower than 0.025 m/s;  * bench force on the included parts > 0.
strict_support (only evaluated when the endpoint holds): the source's 480-frame support test is run on
a COPY of the simulation state (the live simulation is untouched): 2 s with the arms holding their
current targets; gravity window 0.75-1.0 s, then a 2 N downward test load on the crossbar (root) and
loaded window 1.75-2.0 s. In each window the mean bench reaction on the included parts must equal
their weight (+ load) within max(0.05 N, 2 %), also after the momentum-derivative correction.
Screws/pads/supports are identical parts, so any screw may fill any insert, any pad any site and either
support either side. Source operation chronology (17 operations) is reported by 'chronology' (it is an
offline audit item in the source, not part of check_success).
"""
import numpy as np
import mujoco
from ikea_runtime import qmul, qinv, rotate, quat_angle_deg, axis_angle_deg

class Monitor:
    def __init__(self, model, data, task, scene=None):
        self.m, self.d, self.t = model, data, task
        self.mech = scene.mech
        self.g = task['gates']
        self.inc = task['included']
        self.inc_ids = np.array([model.body(k).id for k in self.inc])
        self.robot = np.array([model.body(i).name.startswith(('left_', 'right_')) for i in range(model.nbody)])
        self.inc_mask = np.zeros(model.nbody, bool); self.inc_mask[self.inc_ids] = True
        self.bench = model.geom('bench').id
        self.root = model.body(task['root']).id

    def reset(self): pass
    def update(self): pass
    def state(self): return {}
    def set_state(self, s): pass

    # ------------------------------------------------------------- endpoint
    def _aligned(self, key, tp, tq, host_q, threaded):
        mc = self.mech; p, q = mc.pose(key); ax = rotate(host_q, [0, 0, 1])
        dl = p - tp; gap = float(dl @ ax); lat = float(np.linalg.norm(dl - gap * ax))
        ang = axis_angle_deg(rotate(q, [0, 0, 1]), ax) if threaded else quat_angle_deg(q, tq)
        sp = mc.speed(key); g = self.g
        ok = abs(gap) < g['axial_m'] and lat < g['lateral_m'] and ang < g['axis_deg'] and sp < g['speed_m_s']
        return dict(gap_m=gap, lateral_m=lat, angle_deg=ang, speed_m_s=sp, aligned=bool(ok))

    def _box_aligned(self, pad, tp, tq, host_q):
        mc = self.mech; p, q = mc.pose(pad); qb = qmul(q, mc.pad_box[pad]); ax = rotate(host_q, [0, 0, 1])
        dl = p - tp; gap = float(dl @ ax); lat = float(np.linalg.norm(dl - gap * ax)); ang = quat_angle_deg(qb, tq)
        sp = mc.speed(pad); g = self.g
        ok = abs(gap) < g['axial_m'] and lat < g['lateral_m'] and ang < g['axis_deg'] and sp < g['speed_m_s']
        return dict(gap_m=gap, lateral_m=lat, angle_deg=ang, speed_m_s=sp, aligned=bool(ok))

    def endpoint(self):
        mc = self.mech; rep = dict(failures=[])
        pc, qc = mc.pose('crossbar')
        side_sup = {s: mc.side_support(s) for s in ('L', 'R')}
        # hardware
        hw = {}; used = set()
        for k in range(6):
            side = self.t['insert_side'][k]; sup = side_sup[side]
            tp, tq = mc.insert_target(k)
            ps, qs = mc.pose(sup); rel_s = np.array(self.t['inserts'][k]) - np.array(self.t['side_support_rel_crossbar'][side])
            tps = ps + rotate(qs, rel_s)
            best = None
            for s in mc.screws:
                if s in used or not mc.active('ret_crossbar_screw_%s' % s[-1]):
                    continue
                a = self._aligned(s, tp, tq, qc, True); b = self._aligned(s, tps, qs, qs, True)
                r = dict(screw=s, crossbar=a, through=dict(b, support=sup), ok=bool(a['aligned'] and b['aligned']))
                if best is None or r['ok'] > best['ok'] or (r['ok'] == best['ok'] and a['lateral_m'] < best['crossbar']['lateral_m']):
                    best = r
            if best is None:
                best = dict(screw=None, ok=False)
            if best['ok']: used.add(best['screw'])
            else: rep['failures'].append('unseated_screw:insert_%d' % k)
            hw['insert_%d' % k] = best
        # structure
        st = {}
        for side, sup in side_sup.items():
            tp = pc + rotate(qc, self.t['side_support_rel_crossbar'][side])
            a = self._aligned(sup, tp, qc, qc, False); on = mc.active('join_crossbar_%s' % sup)
            st[side] = dict(support=sup, joined=on, **a, ok=bool(on and a['aligned']))
            if not st[side]['ok']: rep['failures'].append('structure_not_connected:%s' % side)
        if side_sup['L'] == side_sup['R']:
            st['L']['ok'] = st['R']['ok'] = False; rep['failures'].append('both sides resolve to one support')
        # pads
        pads = {}; pused = set()
        for sup in mc.supports:
            for typ in ('flat', 'slope'):
                tp, tq, qs = mc.site_target(sup, typ); best = None
                for p in mc.pads:
                    if p in pused or not mc.active('adhesive_%s_%s' % (sup, p)):
                        continue
                    a = self._box_aligned(p, tp, tq, qs); backed = mc.active('backing_%s' % p)
                    r = dict(pad=p, backed=backed, **a, ok=bool(a['aligned'] and not backed))
                    if best is None or r['ok'] > best['ok']: best = r
                if best is None: best = dict(pad=None, ok=False)
                if best['ok']: pused.add(best['pad'])
                else: rep['failures'].append('pad_not_on_correct_face_or_still_backed:%s|%s' % (sup, typ))
                pads['%s|%s' % (sup, typ)] = best
        # released / settled / bench
        d = self.d; n = d.ncon
        b1 = mc.geom_body[d.contact.geom1[:n]]; b2 = mc.geom_body[d.contact.geom2[:n]]
        touch = bool(np.any((self.robot[b1] & self.inc_mask[b2]) | (self.robot[b2] & self.inc_mask[b1]))) if n else False
        speeds = {k: mc.speed(k) for k in self.inc}
        settled = all(v < self.g['settled_speed_m_s'] for v in speeds.values())
        bench = float(sum(mc.bench_force(k)[2] for k in self.inc))
        if touch: rep['failures'].append('robot_still_touching_parts')
        if not settled: rep['failures'].append('not_settled')
        hf = sum(v['ok'] for v in hw.values()) / 6.; sf = sum(v['ok'] for v in st.values()) / 2.; pf = sum(v['ok'] for v in pads.values()) / 4.
        ok = hf == 1 and sf == 1 and pf == 1 and not touch and settled and bench > 0
        rep.update(hardware_fraction=hf, structure_fraction=sf, pad_fraction=pf, released=not touch, settled=bool(settled),
                   bench_signed_N=bench, hardware=hw, structure=st, pads=pads, endpoint_ok=bool(ok))
        return rep

    # ------------------------------------------------------------- strict support (on a copy)
    def strict_support(self):
        m = self.m; d = mujoco.MjData(m); mujoco.mj_copyData(d, m, self.d)
        dt = m.opt.timestep; n_total = int(round(2.0 / dt)); n_load = int(round(1.0 / dt))
        masses = m.body_mass[self.inc_ids]; win = {'gravity': (0.75, 1.0), 'loaded': (1.75, 2.0)}
        rec = {k: [] for k in win}; mom = {k: [] for k in win}; v6 = np.zeros(6); f6 = np.zeros(6)
        load = self.g['support_load_N']
        for i in range(n_total):
            d.xfrc_applied[self.root] = [0, 0, -load, 0, 0, 0] if i >= n_load else 0
            mujoco.mj_step(m, d)
            t = (i + 1) * dt
            for k, (a, b) in win.items():
                if a <= t < b + 1e-9:
                    r = np.zeros(3)
                    for c in range(d.ncon):
                        con = d.contact[c]
                        if con.geom1 == self.bench and self.inc_mask[m.geom_bodyid[con.geom2]]: s = 1.
                        elif con.geom2 == self.bench and self.inc_mask[m.geom_bodyid[con.geom1]]: s = -1.
                        else: continue
                        mujoco.mj_contactForce(m, d, c, f6); r += s * (con.frame.reshape(3, 3).T @ f6[:3])
                    p = np.zeros(3)
                    for bi, mi in zip(self.inc_ids, masses):
                        mujoco.mj_objectVelocity(m, d, mujoco.mjtObj.mjOBJ_BODY, int(bi), v6, 0); p += mi * v6[3:]
                    rec[k].append(r); mom[k].append(p)
        out = dict(windows=[], verified=False)
        for k, L in (('gravity', 0.), ('loaded', load)):
            R = np.mean(rec[k], axis=0); P = np.array(mom[k]); dur = (len(P) - 1) * dt
            dpdt = (P[-1] - P[0]) / dur
            exp = float(masses.sum() * 9.81 + L); res = R + np.array([0, 0, -exp]) - dpdt
            tol = max(self.g['support_tol_abs_N'], self.g['support_tol_rel'] * exp)
            out['windows'].append(dict(phase=k, measured_N=float(R[2]), expected_N=exp, momentum_derivative_N=dpdt.tolist(),
                                       residual_N=res.tolist(), tolerance_N=tol,
                                       verified=bool(abs(R[2] - exp) < tol and np.linalg.norm(res) < tol)))
        out['verified'] = all(w['verified'] for w in out['windows'])
        return out

    def report(self, probe=True):
        rep = self.endpoint()
        rep['strict_support'] = self.strict_support() if (probe and rep['endpoint_ok']) else None
        rep['success'] = bool(rep['endpoint_ok'] and rep['strict_support'] is not None and rep['strict_support']['verified'])
        rep['chronology'] = self.mech.chronology()
        rep['mechanism_metrics'] = dict(self.mech.metrics)
        return rep
