"""EKET steps 1-4: ported source operation gates (frozen c140392 MotionGate) and the source frame-joint latch.

Every quantity is the part's pose / velocity relative to
the TOP panel frame (all panels are identity-oriented in the assembled cabinet), exactly as the source's
StateOps.relative().  Contacts are the net normal contact force between the operated panel and each
counterpart panel (source: filtered contact sensor force_matrix_w).

Adaptations (no scripted driver here; a robot moves the parts):
  * the gates run every PERIOD = 4 physics steps (4 ms, source 1/240 s); step-count dwells are converted
    to time (12 source steps = 0.05 s -> 13 updates, 24 -> 25); the 1 s pose window = 251 samples;
  * an operation's measurement starts when the previous one is accepted (first one at reset), at the
    part's then-current relative pose; if that pose is within the operation's minimum travel of its goal
    the start is deferred until the part is at least that far away (source: "a gate must start outside
    its measured minimum travel");
  * the source driver's per-operation step budgets (1200/3600/2880 steps) are not ported: they bound the
    scripted force driver, not the assembly;
  * the back's three 0.35 s source fit-probe pulses are a driver action; the source grader's consequence
    is kept: back_slide cannot be accepted until 1.05 s after the back first came within 2 mm of its goal.
"""
import math
import numpy as np
import mujoco
from ikea_runtime import _cross

ROLES = ('top', 'bottom', 'side_a', 'back', 'side_b')
OPERATIONS = ('side_a_entry', 'side_a_slide', 'side_b_entry', 'side_b_slide', 'back_slide', 'bottom_entry', 'bottom_slide')
MANUAL_STEP = (1, 1, 2, 2, 3, 4, 4)
SLIDES = {'side_a_slide', 'side_b_slide', 'bottom_slide'}
LATCH = {'side_a_slide': ('side_a',), 'side_b_slide': ('side_b',), 'bottom_slide': ('bottom_a', 'bottom_b')}
JOINT_PAIRS = {'side_a': ('top', 'side_a'), 'side_b': ('top', 'side_b'), 'bottom_a': ('side_a', 'bottom'), 'bottom_b': ('side_b', 'bottom')}
PERIOD = 4
SRC_DT = 1 / 240

def qmul(a, b):
    w, x, y, z = a; W, X, Y, Z = b
    return np.array([w*W-x*X-y*Y-z*Z, w*X+x*W+y*Z-z*Y, w*Y-x*Z+y*W+z*X, w*Z+x*Y-y*X+z*W])

def qconj(q):
    return np.array([q[0], -q[1], -q[2], -q[3]])

def quat_angle_deg(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    n = np.linalg.norm(a) * np.linalg.norm(b)
    if n < 1e-12 or not math.isfinite(n):
        return float('inf')
    return math.degrees(2 * math.acos(float(np.clip(abs(np.dot(a, b)) / n, 0., 1.))))

# ------------------------------------------------------------------ frozen source gate (spec.py)
class SeatTolerance:
    def __init__(self, position_m=.0008, angle_deg=1., linear_speed_m_s=.012, angular_speed_rad_s=.10,
                 contact_force_N=.015, contact_window_m=.004, dwell_steps=12, contact_samples=3):
        self.position_m, self.angle_deg = position_m, angle_deg
        self.linear_speed_m_s, self.angular_speed_rad_s = linear_speed_m_s, angular_speed_rad_s
        self.contact_force_N, self.contact_window_m = contact_force_N, contact_window_m
        self.dwell_steps, self.contact_samples = dwell_steps, contact_samples
        # source dwell is counted in 1/240 s physics steps -> same time at the gate period
        self.dwell_updates = int(math.ceil(dwell_steps * SRC_DT / (PERIOD * 1e-3) - 1e-9))

    def as_dict(self):
        return dict(position_m=self.position_m, angle_deg=self.angle_deg, linear_speed_m_s=self.linear_speed_m_s,
                    angular_speed_rad_s=self.angular_speed_rad_s, contact_force_N=self.contact_force_N,
                    contact_window_m=self.contact_window_m, dwell_steps=self.dwell_steps,
                    dwell_updates=self.dwell_updates, contact_samples=self.contact_samples)

class MotionGate:
    """Port of the frozen c140392 MotionGate (positions/velocities relative to the counterpart frame)."""
    def __init__(self, start, goal, minimum_travel, required_targets, tolerance, dt, pose_window_seconds=0.):
        self.start = np.asarray(start, float).copy(); self.goal = np.asarray(goal, float).copy()
        axis = self.goal - self.start; length = float(np.linalg.norm(axis))
        if length < minimum_travel or minimum_travel <= 0:
            raise ValueError('A gate must start outside its measured minimum travel')
        self.axis = axis / length
        self.minimum_travel = minimum_travel; self.required_targets = tuple(required_targets)
        self.tolerance = tolerance; self.dt = dt; self.pose_window_seconds = pose_window_seconds
        self.pose_range_m = .0002; self.pose_net_drift_m = .00005
        self.contact_hits = dict.fromkeys(self.required_targets, 0)
        self.dwell = 0; self.max_progress = 0.; self.last = {}; self.position_history = []
        # source dwell counted in 1/240 s steps -> same duration at this gate period
        self.dwell_needed = int(math.ceil(tolerance.dwell_steps * SRC_DT / dt - 1e-9))

    def update(self, position, angle_deg, relative_velocity, angular_speed, contacts):
        p, v = np.asarray(position, float), np.asarray(relative_velocity, float)
        finite = bool(np.isfinite(np.r_[p, v, angle_deg, angular_speed, list(contacts.values())]).all())
        previous = self.position_history[-1] if self.position_history else None
        fd_speed = float(np.linalg.norm(p - previous) / self.dt) if previous is not None and finite else None
        count = max(2, round(self.pose_window_seconds / self.dt) + 1)
        if finite:
            self.position_history.append(p.copy()); self.position_history = self.position_history[-count:]
        else:
            self.position_history = []
        pose_window = None
        speed_ok = np.linalg.norm(v) < self.tolerance.linear_speed_m_s
        if self.pose_window_seconds:
            speed_ok = False
            if len(self.position_history) == count:
                poses = np.asarray(self.position_history)
                speed = np.linalg.norm(np.diff(poses, axis=0), axis=1) / self.dt
                pose_window = dict(seconds=self.pose_window_seconds, samples=count,
                                   range_m=float(np.linalg.norm(np.ptp(poses, axis=0))),
                                   net_drift_m=float(np.linalg.norm(poses[-1] - poses[0])),
                                   max_goal_error_m=float(np.linalg.norm(poses - self.goal, axis=1).max()),
                                   max_finite_difference_speed_m_s=float(speed.max()))
                speed_ok = (pose_window['range_m'] <= self.pose_range_m and pose_window['net_drift_m'] <= self.pose_net_drift_m
                            and pose_window['max_goal_error_m'] <= self.tolerance.position_m
                            and pose_window['max_finite_difference_speed_m_s'] < self.tolerance.linear_speed_m_s)
        error = float(np.linalg.norm(p - self.goal))
        progress = float(np.dot(p - self.start, self.axis))
        self.max_progress = max(self.max_progress, progress) if finite else self.max_progress
        if finite and error <= self.tolerance.contact_window_m:
            for t in self.required_targets:
                if contacts.get(t, 0.) >= self.tolerance.contact_force_N:
                    self.contact_hits[t] += 1
        near = (finite and error <= self.tolerance.position_m and abs(angle_deg) <= self.tolerance.angle_deg
                and speed_ok and abs(angular_speed) < self.tolerance.angular_speed_rad_s and progress >= self.minimum_travel)
        witnessed = all(n >= self.tolerance.contact_samples for n in self.contact_hits.values())
        self.dwell = self.dwell + 1 if near and witnessed else 0
        self.last = dict(finite=finite, position_error_m=error, angle_error_deg=float(angle_deg), progress_m=progress,
                         relative_speed_m_s=float(np.linalg.norm(v)), finite_difference_relative_speed_m_s=fd_speed,
                         pose_window=pose_window, relative_angular_speed_rad_s=float(angular_speed),
                         contact_hits=dict(self.contact_hits), dwell_updates=self.dwell)
        return self.dwell >= self.dwell_needed

    def state(self):
        return dict(start=self.start.tolist(), contact_hits=dict(self.contact_hits), dwell=self.dwell,
                    max_progress=self.max_progress, history=[p.tolist() for p in self.position_history], last=self.last)

    def set_state(self, s):
        self.contact_hits = dict(s['contact_hits']); self.dwell = s['dwell']; self.max_progress = s['max_progress']
        self.position_history = [np.array(p) for p in s['history']]; self.last = s['last']

# ------------------------------------------------------------------ operation specs (observation.operation_spec)
def operation_spec(name, canonical):
    role = 'back' if name == 'back_slide' else name.rsplit('_', 1)[0]
    goal = np.asarray(canonical[role]) - np.asarray(canonical['top'])
    if name.endswith('_entry'):
        goal = goal + [-.011 if role == 'bottom' else .011, 0., -.0055 if role == 'bottom' else 0.]
    targets = ['side_a', 'side_b', 'top'] if role == 'back' else ['side_a', 'side_b'] if role == 'bottom' else ['top']
    tol = (SeatTolerance(position_m=.0005 if name == 'bottom_slide' else .00025, angle_deg=.10, dwell_steps=24)
           if name in SLIDES else SeatTolerance())
    return dict(name=name, role=role, goal=goal, targets=targets, manual_step=MANUAL_STEP[OPERATIONS.index(name)],
                minimum_travel=.30 if role == 'back' else .014 if name.endswith('_entry') else .008,
                tolerance=tol, pose_window_seconds=1. if name == 'bottom_slide' else 0.)

# ------------------------------------------------------------------ measurements (StateOps)
class Measure:
    def __init__(self, m, d):
        self.m, self.d = m, d
        self.bid = {r: m.body(r).id for r in ROLES}
        self.geom_body = m.geom_bodyid

    def relative(self, role, parent='top'):
        m, d = self.m, self.d
        a, b = self.bid[parent], self.bid[role]
        qa = d.xquat[a]; Ra = d.xmat[a].reshape(3, 3)
        delta = d.xpos[b] - d.xpos[a]
        va = np.zeros(6); vb = np.zeros(6)
        mujoco.mj_objectVelocity(m, d, mujoco.mjtObj.mjOBJ_BODY, a, va, 0)
        mujoco.mj_objectVelocity(m, d, mujoco.mjtObj.mjOBJ_BODY, b, vb, 0)
        omega = vb[:3] - va[:3]
        vel = vb[3:] - va[3:] - _cross(va[:3], delta)
        return Ra.T @ delta, qmul(qconj(qa), d.xquat[b]), Ra.T @ vel, float(np.linalg.norm(omega))

    def contacts(self, role):
        """{other panel: |net normal contact force on role from other|}."""
        d = self.d; n = d.ncon; ib = self.bid[role]
        tot = {r: np.zeros(3) for r in ROLES if r != role}
        rev = {v: k for k, v in self.bid.items()}
        if n:
            c = d.contact
            b1 = self.geom_body[c.geom1[:n]]; b2 = self.geom_body[c.geom2[:n]]
            sel = np.nonzero(((b1 == ib) & np.isin(b2, list(rev))) | ((b2 == ib) & np.isin(b1, list(rev))))[0]
            f6 = np.zeros(6)
            for i in sel:
                if c.efc_address[i] < 0:
                    continue
                mujoco.mj_contactForce(self.m, d, int(i), f6)
                fn = f6[0] * c.frame[i, :3]          # normal force on geom2 from geom1 (world)
                other = rev[int(b1[i])] if b2[i] == ib else rev[int(b2[i])]
                if other == role:
                    continue
                tot[other] += fn if b2[i] == ib else -fn
        return {k: float(np.linalg.norm(v)) for k, v in tot.items()}

    def finite(self):
        d = self.d
        return bool(all(np.isfinite(d.xpos[b]).all() and np.isfinite(d.xquat[b]).all() for b in self.bid.values())
                    and np.isfinite(d.qvel).all())

# ------------------------------------------------------------------ ordered operation tracker (journal + gates)
class OpTracker:
    """Runs the seven source gates in the source order on live measurements. Used independently by the
    latch mechanism and by the success monitor."""
    def __init__(self, m, d, canonical):
        self.m, self.d = m, d
        self.canon = {k: np.asarray(v, float) for k, v in canonical.items()}
        self.meas = Measure(m, d)
        self.dt = PERIOD * m.opt.timestep
        self.reset()

    def reset(self):
        self.idx = 0; self.gate = None; self.records = []; self.counter = 0
        self.probe_start = None; self.prev = None; self.start_time = None

    def current(self):
        return OPERATIONS[self.idx] if self.idx < len(OPERATIONS) else None

    def _begin(self, spec, p):
        if np.linalg.norm(spec['goal'] - p) < spec['minimum_travel']:
            return False
        self.gate = MotionGate(p, spec['goal'], spec['minimum_travel'], spec['targets'], spec['tolerance'], self.dt,
                               spec['pose_window_seconds'])
        self.start_time = float(self.d.time); self.probe_start = None; self.prev = p.copy()
        return True

    def update(self):
        """Call after every physics step. Returns the name of an operation accepted at this step, or None."""
        self.counter += 1
        if self.counter % PERIOD or self.idx >= len(OPERATIONS):
            return None
        name = OPERATIONS[self.idx]; spec = operation_spec(name, self.canon)
        p, q, v, w = self.meas.relative(spec['role'])
        if self.gate is None and not self._begin(spec, p):
            return None
        g = self.gate
        if name == 'back_slide' and self.probe_start is None and np.linalg.norm(self.prev - spec['goal']) < .002:
            self.probe_start = float(self.d.time)
        ang = quat_angle_deg(q, [1., 0, 0, 0])
        passed = g.update(p, ang, v, w, self.meas.contacts(spec['role']))
        if name in SLIDES:
            precise = np.linalg.norm(p - spec['goal']) < .00005 and ang < .02
            passed = passed and precise; g.last['driver_precision_target_met'] = bool(precise)
        if self.probe_start is not None and float(self.d.time) - self.probe_start < 3 * .35:
            passed = False; g.last['fit_probe_exclusion'] = True
        self.prev = p.copy()
        if passed:
            self.records.append(dict(name=name, role=spec['role'], manual_step=spec['manual_step'], passed=True,
                                     start_time_s=self.start_time, end_time_s=float(self.d.time),
                                     start_in_top_frame=g.start.tolist(), goal_in_top_frame=spec['goal'].tolist(),
                                     thresholds=spec['tolerance'].as_dict(), minimum_travel_m=spec['minimum_travel'], **g.last))
            self.idx += 1; self.gate = None
            return name
        return None

    def status(self):
        cur = self.current()
        out = dict(completed=[r['name'] for r in self.records], current=cur)
        if cur is not None:
            spec = operation_spec(cur, self.canon)
            out['current_goal_in_top_frame'] = spec['goal'].tolist()
            out['current_started'] = self.gate is not None
            if self.gate is not None:
                out['current_metrics'] = self.gate.last
        return out

    def state(self):
        return dict(idx=self.idx, records=self.records, counter=self.counter, probe_start=self.probe_start,
                    prev=None if self.prev is None else self.prev.tolist(), start_time=self.start_time,
                    gate=None if self.gate is None else self.gate.state())

    def set_state(self, s):
        self.idx = s['idx']; self.records = list(s['records']); self.counter = s['counter']
        self.probe_start = s['probe_start']; self.prev = None if s['prev'] is None else np.array(s['prev'])
        self.start_time = s['start_time']; self.gate = None
        if s['gate'] is not None:
            spec = operation_spec(OPERATIONS[self.idx], self.canon)
            self.gate = MotionGate(s['gate']['start'], spec['goal'], spec['minimum_travel'], spec['targets'],
                                   spec['tolerance'], self.dt, spec['pose_window_seconds'])
            self.gate.set_state(s['gate'])

# ------------------------------------------------------------------ source frame-joint latch (StateOps.latch)
class EketMechanism:
    """Four source fixed joints (MuJoCo weld equalities joint_<name>, inactive at reset).  When a slide
    operation passes its source gate, its joints are enabled with the CURRENT measured relative pose of
    body1 -> body2 (no snapping to the goal).  Joints are never disabled (the source has no disassembly)."""
    def __init__(self, model, data, task):
        self.m, self.d = model, data
        self.tracker = OpTracker(model, data, task['canonical_in_cabinet_frame'])
        self.eq = {j: model.equality('joint_' + j).id for j in JOINT_PAIRS}
        self.reset()

    def reset(self):
        self.tracker.reset(); self.events = []
        for i in self.eq.values():
            self.d.eq_active[i] = 0

    def active_joints(self):
        return sorted(j for j, i in self.eq.items() if self.d.eq_active[i])

    def latch(self, j):
        a, b = JOINT_PAIRS[j]; m, d = self.m, self.d
        ia, ib = m.body(a).id, m.body(b).id
        Ra = d.xmat[ia].reshape(3, 3)
        r = Ra.T @ (d.xpos[ib] - d.xpos[ia]); q = qmul(qconj(d.xquat[ia]), d.xquat[ib])
        i = self.eq[j]
        m.eq_data[i, 0:3] = 0; m.eq_data[i, 3:6] = r; m.eq_data[i, 6:10] = q / np.linalg.norm(q); m.eq_data[i, 10] = 1
        d.eq_active[i] = 1
        self.events.append(dict(time_s=float(d.time), joint=j, body1=a, body2=b, local_pos=r.tolist(), local_quat_wxyz=q.tolist()))

    def update(self):
        done = self.tracker.update()
        if done in LATCH:
            for j in LATCH[done]:
                if not self.d.eq_active[self.eq[j]]:
                    self.latch(j)

    def state(self):
        return dict(tracker=self.tracker.state(), events=self.events,
                    eq_data={j: self.m.eq_data[i].tolist() for j, i in self.eq.items()},
                    eq_active={j: bool(self.d.eq_active[i]) for j, i in self.eq.items()})

    def set_state(self, s):
        self.tracker.set_state(s['tracker']); self.events = list(s['events'])
        for j, i in self.eq.items():
            self.m.eq_data[i] = s['eq_data'][j]; self.d.eq_active[i] = int(s['eq_active'][j])
