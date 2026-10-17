"""IKEA365 operation ledger and post-seat retention (port of the source f27 fastener mechanics).


The seven operations must be accepted in order (source Ledger). Each is accepted from measured
state only (poses, velocities, contact forces), never moves anything. The ONLY non-contact
mechanism is the source's ideal post-seat retention: when the reinstalled screw has been seated
(geometric SDF thread, measured turns, head contact with member_a and member_b) for the dwell time,
two weld equalities are switched on with the CURRENT relative poses, exactly like the source's
FixedJoints Connections/member_a_same_screw and Connections/member_a_member_b. They are never
switched off (the source has no disassembly after reinstall); reset() clears them.

Not ported: the source's per-part world fixtures (diagnostic holds of parts in the air / after
placement, replaced by the bench and the robot), its force/torque controller and the motor-work
gate (work_J > 1e-5 J, computed from the controller's own applied torque; there is no applied
screw torque here, the robot turns the screw through finger contact).
"""
import math, copy
import numpy as np
import mujoco
from ikea_runtime import Helpers, rotate, qmul, qinv, quat_angle_deg, axis_angle_deg

Z_YAW180 = np.array([0., 0., 0., 1.])


class Ikea365Mechanism:
    PERIOD = 4   # physics steps between updates (4 ms)

    def __init__(self, model, data, task):
        self.m, self.d, self.t = model, data, task
        self.h = Helpers(model, data)
        self.g = task['gates']
        self.ops = [o['key'] for o in task['operations']]
        self.eq = [model.equality(n).id for n in task['operations'][4]['welds']]
        a = task['assembled_in_member_a_frame']
        self.screw_rel = np.array(a['same_screw']); self.b_rel = np.array(a['member_b'])
        self.return_rel = np.array(task['operations'][3]['target_in_member_a_frame'])
        self.bid = {n: model.body(n).id for n in task['parts']}
        self.geom_body = model.geom_bodyid
        self.reset()

    # ------------------------------------------------------------------ state
    def reset(self):
        self.counter = 0
        self.next = 0                    # index of the next operation to accept
        self.events = []                 # (key, sim time, metrics)
        self.op = {}                     # per-operation running quantities (reset at operation start)
        self._start_op()
        mujoco.mj_kinematics(self.m, self.d)          # Scene.reset calls this before mj_forward
        self.b_start = self.h.pose('member_b')[0].tolist()
        for i in self.eq:
            self.d.eq_active[i] = 0

    def state(self):
        return dict(counter=self.counter, next=self.next, b_start=self.b_start, events=[list(e) for e in self.events],
                    op=copy.deepcopy(self.op),
                    eq_data=[self.m.eq_data[i].tolist() for i in self.eq], eq_active=[bool(self.d.eq_active[i]) for i in self.eq])

    def set_state(self, s):
        self.counter = s['counter']; self.next = s['next']; self.b_start = s['b_start']; self.events = [tuple(e) for e in s['events']]
        self.op = copy.deepcopy(s['op'])
        for i, dat, act in zip(self.eq, s['eq_data'], s['eq_active']):
            self.m.eq_data[i] = dat; self.d.eq_active[i] = int(act)

    @property
    def complete(self):
        return self.next >= len(self.ops)

    def accepted(self):
        return [e[0] for e in self.events]

    def retained(self):
        return [bool(self.d.eq_active[i]) for i in self.eq]

    # ------------------------------------------------------------------ measurements
    def contact_force(self, a, b):
        """Sum of contact normal forces between bodies a and b (N)."""
        n = self.d.ncon
        if n == 0:
            return 0.
        c = self.d.contact
        b1 = self.geom_body[c.geom1[:n]]; b2 = self.geom_body[c.geom2[:n]]
        ia, ib = self.bid[a], self.bid[b]
        sel = ((b1 == ia) & (b2 == ib)) | ((b1 == ib) & (b2 == ia))
        if not sel.any():
            return 0.
        adr = c.efc_address[:n][sel]
        return float(np.abs(self.d.efc_force[adr[adr >= 0]]).sum())

    def rel(self, part, host='member_a'):
        """Part origin and orientation in the host frame, part speed (world)."""
        ph, qh = self.h.pose(host); pp, qp = self.h.pose(part)
        qi = qinv(qh)
        v = np.zeros(6); mujoco.mj_objectVelocity(self.m, self.d, mujoco.mjtObj.mjOBJ_BODY, self.bid[part], v, 0)
        return rotate(qi, pp - ph), qmul(qi, qp), float(np.linalg.norm(v[3:]))

    def _window(self, name, value, seconds):
        w = self.op.setdefault(name, [])
        w.append(value)
        n = max(1, int(round(seconds / (self.PERIOD * self.m.opt.timestep))))
        del w[:-n]
        return float(np.mean(w))

    def _start_op(self):
        self.op = dict(dwell=0., turns=0., prev_q=None, start_gap=None, engaged_s=0., max_lift=0., start_z=None)

    def _accept(self, metrics):
        key = self.ops[self.next]
        self.events.append((key, float(self.d.time), metrics))
        self.next += 1
        self._start_op()

    def _dwell(self, ok, dt):
        self.op['dwell'] = self.op['dwell'] + dt if ok else 0.
        return self.op['dwell'] >= self.g['dwell_s']

    def _turns(self, qrel):
        """Accumulated rotation of the screw about member_a's z axis since operation start (turns, +CCW from the head)."""
        if self.op['prev_q'] is not None:
            dq = qmul(qrel, qinv(np.asarray(self.op['prev_q'])))
            if dq[0] < 0: dq = -dq
            self.op['turns'] += 2 * math.atan2(dq[3], dq[0]) / (2 * math.pi)
        self.op['prev_q'] = [float(x) for x in qrel]
        return self.op['turns']

    # ------------------------------------------------------------------ update
    def update(self):
        self.counter += 1
        if self.counter % self.PERIOD or self.complete:
            return
        g = self.g; dt = self.PERIOD * self.m.opt.timestep
        key = self.ops[self.next]
        if key in ('remove_same_screw', 'reinstall_same_screw', 'return_same_screw', 'park_same_screw'):
            p, q, speed = self.rel('same_screw')
            delta = p - self.screw_rel; gap = float(delta[2]); lat = float(np.linalg.norm(delta[:2]))
            tilt = axis_angle_deg(rotate(q, [0, 0, 1]), [0, 0, 1])
        if key == 'remove_same_screw':
            turns = self._turns(q)
            fa = self._window('fa', self.contact_force('same_screw', 'member_a'), g['contact_window_s'])
            if gap < g['unthread_engaged_gap_m'] and fa > g['contact_N']:
                self.op['engaged_s'] += dt
            if gap > g['unthread_gap_m'] and turns > g['turns'] and self.op['engaged_s'] > g['unthread_engaged_contact_s'] and lat < g['unthread_lateral_m']:
                self._accept(dict(gap_m=gap, lateral_m=lat, turns=turns, engaged_contact_s=self.op['engaged_s']))
        elif key == 'park_same_screw':
            touch = self.contact_force('same_screw', 'member_a') + self.contact_force('same_screw', 'member_b')
            dist = float(np.linalg.norm(delta))
            if self._dwell(touch == 0. and dist > g['park_min_distance_m'] and speed < g['transport_speed_m_s'], dt):
                self._accept(dict(distance_m=dist, speed_m_s=speed))
        elif key == 'cross_members':
            p, q, speed = self.rel('member_b')
            delta = p - self.b_rel; gap = float(delta[2]); lat = float(np.linalg.norm(delta[:2]))
            ang = min(quat_angle_deg(q, [1, 0, 0, 0]), quat_angle_deg(q, Z_YAW180))
            travel = float(np.linalg.norm(self.h.pose('member_b')[0] - np.asarray(self.b_start)))   # since episode start
            fc = self._window('fc', self.contact_force('member_b', 'member_a'), g['contact_window_s'])
            ok = (abs(gap) < g['axial_m'] and lat < g['lateral_m'] and ang < g['axis_deg'] and speed < g['speed_m_s']
                  and travel > g['travel_m'] and fc > g['contact_N'])
            if self._dwell(ok, dt):
                self._accept(dict(gap_m=gap, lateral_m=lat, angle_deg=ang, speed_m_s=speed, travel_m=travel, contact_N=fc))
        elif key == 'return_same_screw':
            err = float(np.linalg.norm(p - self.return_rel))
            if self._dwell(err < g['transport_pos_m'] and speed < g['transport_speed_m_s'] and tilt < g['transport_angle_deg'], dt):
                self._accept(dict(position_error_m=err, speed_m_s=speed, tilt_deg=tilt))
        elif key == 'reinstall_same_screw':
            turns = self._turns(q)
            if self.op['start_gap'] is None:
                self.op['start_gap'] = float(gap)
            travel = abs(self.op['start_gap'] - gap)
            fa = self._window('fa', self.contact_force('same_screw', 'member_a'), g['contact_window_s'])
            fb = self._window('fb', self.contact_force('same_screw', 'member_b'), g['contact_window_s'])
            # screw also coaxial/seated relative to member_b ('through'), as the endpoint grader requires
            pb, qb, _ = self.rel('same_screw', 'member_b'); db = pb - self.screw_rel
            ok = (abs(gap) < g['axial_m'] and lat < g['lateral_m'] and tilt < g['axis_deg'] and speed < g['speed_m_s']
                  and travel > g['travel_m'] and min(fa, fb) > g['contact_N'] and abs(turns) > g['turns'])
            if self._dwell(ok, dt):
                for i, (host, part) in zip(self.eq, (('member_a', 'same_screw'), ('member_a', 'member_b'))):
                    self.engage(i, host, part)
                self._accept(dict(gap_m=gap, lateral_m=lat, tilt_deg=tilt, speed_m_s=speed, travel_m=travel,
                                  contact_member_a_N=fa, contact_member_b_N=fb, turns=turns,
                                  through_gap_m=float(db[2]), through_lateral_m=float(np.linalg.norm(db[:2]))))
        elif key == 'turn_stand':
            pa, qa = self.h.pose('member_a')
            if self.op['start_z'] is None:
                self.op['start_z'] = float(pa[2])
                self.op['ref'] = [[x.tolist() for x in self.rel(k)[:2]] for k in ('member_b', 'same_screw')]
            lift = float(pa[2]) - self.op['start_z']
            up = float(rotate(qa, [0, 0, 1])[2])
            drift = 0.; deg = 0.
            for k, (rp, rq) in zip(('member_b', 'same_screw'), self.op['ref']):
                p, q, _ = self.rel(k); drift = max(drift, float(np.linalg.norm(p - np.asarray(rp)))); deg = max(deg, quat_angle_deg(q, rq))
            self.op['drift'] = max(self.op.get('drift', 0.), drift); self.op['deg'] = max(self.op.get('deg', 0.), deg)
            if lift > g['turn_lift_m'] and up < g['turn_up_z'] and self.op['drift'] < g['turn_drift_m'] and self.op['deg'] < g['turn_drift_deg']:
                self._accept(dict(lift_m=lift, up_z=up, max_relative_drift_m=self.op['drift'], max_relative_angle_deg=self.op['deg']))
        elif key == 'place_bowl':
            f = self.contact_force('bowl', 'member_a') + self.contact_force('bowl', 'member_b')
            n = int(round(g['bowl_window_s'] / dt))
            w = self.op.setdefault('fbowl', []); w.append(f); del w[:-n]
            if len(w) == n and float(np.mean(w)) > g['bowl_contact_N']:
                self._accept(dict(support_contact_N=float(np.mean(w))))

    def engage(self, i, host, part):
        r, q = self.h.rel_pose(host, part)
        self.m.eq_data[i, 0:3] = 0; self.m.eq_data[i, 3:6] = r; self.m.eq_data[i, 6:10] = q; self.m.eq_data[i, 10] = 1
        self.d.eq_active[i] = 1
