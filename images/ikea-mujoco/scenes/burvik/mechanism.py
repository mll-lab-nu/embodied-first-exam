"""BURVIK post-seat retention (the source's fixed connection joints), as MuJoCo welds.

Source: once an operation's gates hold for 36 steps
at 240 Hz (0.15 s), the part is joined to the root ('top') with a fixed joint at its CURRENT
relative pose:
  thread ops (legs):  -0.8 mm <= gap <= 0.8 mm along the top-frame op axis, lateral <= 1 mm,
                      thread-axis tilt <= 2 deg, relative speed < 0.025 m/s, travel >= 1 mm in the
                      operation, >= 0.25 turns relative to the top, counterpart contact window
                      (op.host: top for leg_0/1, handle for leg_2/3; >= 12 of the last 36 samples and
                      the mean above 0.01 N);
  handle (place):     same position gates with full orientation <= 2 deg, both rod ends within 1 mm
                      laterally of the two top holes, contact window with the top; joined to the top
                      only after s2-leg-handle-right is accepted (source: e.fixed('handle', True, True)
                      on that operation), here: after both handle legs are welded.
Every geometric quantity is measured in the top's frame, as in the source (targets are the
manifest centres relative to the top centre). Welds are never released except by reset().
The source's motor work gate (> 1e-5 J) has no robot counterpart and is not ported; the robot
turning the leg relative to the top is counted instead (turns gate).
The source's world fixtures (parking / held top) are not ported: the robot holds the parts.
"""
import math
from collections import deque
import numpy as np
import mujoco
from ikea_runtime import RetentionMechanism, Helpers

def _cross(a, b):
    return np.array([a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]])

def point_velocity(m, d, b, p):
    """world velocity of the material point of body b at world point p."""
    v = np.zeros(6)
    mujoco.mj_objectVelocity(m, d, mujoco.mjtObj.mjOBJ_BODY, b, v, 0)   # [ang, lin] at the body CoM, world axes
    return v[3:] + _cross(v[:3], p - d.xipos[b])

def rel_point_speed(m, d, part, host):
    """|velocity of the part's frame origin - velocity of the host material point at that location| (world)."""
    bp, bh = m.body(part).id, m.body(host).id; p = d.xpos[bp]
    return float(np.linalg.norm(point_velocity(m, d, bp, p) - point_velocity(m, d, bh, p)))

def _qrel(d, bh, bp):
    """orientation of body bp in the frame of body bh (wxyz)."""
    qi = np.zeros(4); q = np.zeros(4)
    mujoco.mju_negQuat(qi, d.xquat[bh]); mujoco.mju_mulQuat(q, qi, d.xquat[bp])
    return q

class BurvikRetention(RetentionMechanism):
    NEAR_LATERAL_M = 0.002      # bookkeeping zone around the seat (turns, travel, contact window)
    NEAR_GAP_M = (-0.002, 0.03)
    NEAR_DEG = 10.

    def __init__(self, model, data, task, period=4):
        self.m, self.d, self.task = model, data, task
        self.h = Helpers(model, data)
        self.period = period
        self.ops = list(task['mechanism_operations'])
        self.eq = {o['key']: model.equality(o['weld']['eq']).id for o in self.ops}
        self.bid = {n: model.body(n).id for n in task['parts']}
        geom_body = model.geom_bodyid
        self._cp = {o['key']: (self.bid[o['part']], set(self.bid[c] for c in o['counterparts'])) for o in self.ops}
        self.reset()

    def reset(self):
        super().reset()
        n = lambda o: max(1, int(round(o['gates']['contact_window_s'] / (self.m.opt.timestep * self.period))))
        self.window = {o['key']: deque(maxlen=n(o)) for o in self.ops}
        self.max_gap = {o['key']: None for o in self.ops}

    def state(self):
        s = super().state()
        s['window'] = {k: list(v) for k, v in self.window.items()}
        s['max_gap'] = dict(self.max_gap)
        return s

    def set_state(self, s):
        super().set_state(s)
        for k, v in s['window'].items():
            self.window[k].clear(); self.window[k].extend(v)
        self.max_gap = dict(s['max_gap'])

    def _contact(self, k):
        """sum of contact normal forces between the part and its counterpart(s)."""
        bp, cps = self._cp[k]; d = self.d; gb = self.m.geom_bodyid; f = 0.
        for i in range(d.ncon):
            c = d.contact[i]
            b1, b2 = gb[c.geom1], gb[c.geom2]
            if ((b1 == bp and b2 in cps) or (b2 == bp and b1 in cps)) and c.efc_address >= 0:
                f += abs(d.efc_force[c.efc_address])
        return f

    def _local(self, o):
        """part pose in the host (top) frame: position error to target, rotation matrix."""
        d = self.d; bp = self.bid[o['part']]; bh = self.bid[o['host']]
        Rh = d.xmat[bh].reshape(3, 3)
        rel = Rh.T @ (d.xpos[bp] - d.xpos[bh]) - np.asarray(o['target_pos'])
        Rrel = Rh.T @ d.xmat[bp].reshape(3, 3)
        return rel, Rrel

    def measure_lean(self, o):
        rel, Rrel = self._local(o)
        ax = np.asarray(o['axis'], float)
        gap = float(rel @ ax); lat = float(np.linalg.norm(rel - gap * ax))
        if o.get('tilt', 'full') == 'axis':
            pa = np.asarray(o['part_axis'], float)
            ang = math.degrees(math.acos(max(-1., min(1., float((Rrel @ pa) @ pa)))))
        else:
            ang = math.degrees(math.acos(max(-1., min(1., (np.trace(Rrel) - 1) / 2))))
        return gap, lat, ang, Rrel

    def _two_holes(self, o, Rrel, rel):
        """max lateral error (top-frame op axis) of the handle rod ends at the two top holes (top frame)."""
        c = np.array(self.task['centers'][o['part']]); ct = np.array(self.task['centers']['top'])
        ax = np.asarray(o['axis'], float); worst = 0.
        for p in o['two_hole_points']:
            dl = (rel + np.asarray(o['target_pos']) + Rrel @ (np.array(p) - c)) - (np.array(p) - ct)
            worst = max(worst, float(np.linalg.norm(dl - (dl @ ax) * ax)))
        return worst

    def _clear(self, k):
        self.window[k].clear(); self.max_gap[k] = None; self.prev_q.pop(k, None); self.dwell[k] = 0.

    def update(self):
        self.counter += 1
        if self.counter % self.period:
            return
        for o in self.ops:
            k = o['key']
            if self.active(k):
                continue
            g = o['gates']
            gap, lat, ang, Rrel = self.measure_lean(o)
            near = lat < self.NEAR_LATERAL_M and self.NEAR_GAP_M[0] < gap < self.NEAR_GAP_M[1] and ang < self.NEAR_DEG
            if not near:
                far = lat > 0.01 or not (-0.005 < gap < 0.04) or ang > 20.
                if far and (self.max_gap[k] is not None or self.window[k]):
                    self._clear(k)   # left the seat: a new approach starts (brief excursions keep the record)
                self.dwell[k] = 0.
                self.metrics[k] = dict(near=False, gap_m=gap, lateral_m=lat, angle_deg=ang, turns=self.turns[k])
                continue
            # travel within the current approach: largest gap since the part came near the seat
            self.max_gap[k] = gap if self.max_gap[k] is None else max(self.max_gap[k], gap)
            if o.get('count_turns'):
                q = _qrel(self.d, self.bid[o['host']], self.bid[o['part']])
                if k in self.prev_q:
                    dq = np.zeros(4); qi = np.zeros(4); mujoco.mju_negQuat(qi, self.prev_q[k]); mujoco.mju_mulQuat(dq, q, qi)
                    if dq[0] < 0: dq = -dq
                    self.turns[k] += 2 * math.atan2(float(dq[1:] @ np.asarray(o['axis'], float)), dq[0]) * o.get('turn_sign', 1) / (2 * math.pi)
                self.prev_q[k] = q
            speed = rel_point_speed(self.m, self.d, o['part'], o['host'])
            contact = self._contact(k)
            win = self.window[k]; win.append(contact)
            wv = np.array(win)
            window_ok = bool(len(win) == win.maxlen and np.count_nonzero(wv > g['contact_N']) >= g['contact_active_fraction'] * win.maxlen
                             and wv.mean() > g['contact_N'])
            travel = self.max_gap[k] - gap
            deps_ok = all(self.active(x) for x in o.get('dependencies', []))
            rel, _ = self._local(o)
            holes = self._two_holes(o, Rrel, rel) if o.get('two_hole_points') else 0.
            ok = (deps_ok and abs(gap) <= g['axial_m'] and lat <= g['lateral_m'] and ang <= g['axis_deg']
                  and speed < g['speed_m_s'] and travel >= g['min_travel_m'] and window_ok and holes <= g['lateral_m'])
            if o.get('min_turns') is not None:
                ok = ok and self.turns[k] >= o['min_turns']
            self.dwell[k] = self.dwell[k] + self.m.opt.timestep * self.period if ok else 0.
            self.metrics[k] = dict(near=True, gap_m=gap, lateral_m=lat, angle_deg=ang, speed_m_s=speed,
                                   travel_m=travel, contact_N=contact, contact_window_ok=window_ok, turns=self.turns[k],
                                   two_hole_error_m=holes, dependencies_ok=bool(deps_ok), dwell_s=self.dwell[k])
            if self.dwell[k] >= g['dwell_s']:
                self.engage(o)
