"""SVALLET retention mechanism: the source's post-contact retention FixedJoints as MuJoCo welds.

Source: a fixed joint host->part is enabled at the CURRENT relative
pose once, continuously for gates.dwell_s, the part is seated:
  |gap| < axial_m, lateral < lateral_m, axis tilt < axis_deg (at the connector points),
  part speed < speed_m_s, travel along the insertion axis >= min_travel_m,
  contact with the expected counterparts (host + its jaws) > min_contact_N,
  press: spring jaw peak travel > 0.25 mm (it was cammed open) and current travel < 0.7 mm (it snapped back),
  screw: > 0.25 turn of tightening rotation about the insertion axis, and the mount weld already on.
Travel, turns and jaw peak are accumulated while the part is in the source's operation corridor
(lateral < 15 mm, tilt < 15 deg, gap > -3 mm = the source's escape limits) and reset when it leaves.
Not ported: the source's 0.15 N / 0.25 s pull probe before connecting (an applied test force, not a
scene mechanism; the snap barb geometry under the jaw is what resists pull-out here).
"""
import math
import numpy as np
from ikea_runtime import RetentionMechanism, qmul, qinv


class SvalletRetention(RetentionMechanism):
    def __init__(self, model, data, task, period=None):
        super().__init__(model, data, task, period=period or task['mechanism']['period_steps'])
        self.jaw_adr = {o['key']: [int(model.jnt_qposadr[model.joint(j['joint']).id]) for j in o.get('jaw', [])] for o in self.ops}

    def reset(self):
        super().reset()
        self.track = {o['key']: None for o in self.ops}

    def state(self):
        s = super().state()
        s['track'] = {k: (None if t is None else dict(t, prev_q=t['prev_q'].tolist())) for k, t in self.track.items()}
        return s

    def set_state(self, s):
        super().set_state(s)
        self.track = {k: (None if t is None else dict(t, prev_q=np.array(t['prev_q']))) for k, t in s['track'].items()}

    def update(self):
        self.counter += 1
        if self.counter % self.period:
            return
        dt = self.m.opt.timestep * self.period
        cor = self.task['mechanism']
        for o in self.ops:
            k = o['key']
            if self.active(k):
                continue
            g = o['gates']; me = self.measure(o)
            inside = me['lateral'] < cor['corridor_lateral_m'] and me['angle'] < cor['corridor_axis_deg'] and me['gap'] > cor['corridor_gap_min_m']
            if not inside:
                self.track[k] = None; self.dwell[k] = 0.
                self.metrics[k] = dict(gap_m=me['gap'], lateral_m=me['lateral'], angle_deg=me['angle'], in_corridor=False)
                continue
            jaw = [float(self.d.qpos[a]) for a in self.jaw_adr[k]]
            t = self.track[k]
            if t is None:
                t = self.track[k] = dict(peak_gap=me['gap'], turns=0., prev_q=me['qrel'], jaw_peak=[0.] * len(jaw))
            # tightening rotation about the insertion direction (-outward) in the host frame
            dq = qmul(me['qrel'], qinv(t['prev_q']))
            if dq[0] < 0: dq = -dq
            t['turns'] += 2 * math.atan2(float(dq[1:] @ -me['axis_host']), dq[0]) / (2 * math.pi)
            t['prev_q'] = me['qrel']
            t['peak_gap'] = max(t['peak_gap'], me['gap'])
            t['jaw_peak'] = [max(a, b) for a, b in zip(t['jaw_peak'], jaw)]
            contact = self.h.contact_force_between(o['part'], o['counterparts'])
            deps_ok = all(self.active(x) for x in o.get('dependencies', []) if x in self.eq)
            travel = t['peak_gap'] - me['gap']
            ok = (deps_ok and abs(me['gap']) < g['axial_m'] and me['lateral'] < g['lateral_m'] and me['angle'] < g['axis_deg']
                  and me['speed'] < g['speed_m_s'] and travel >= g['min_travel_m'] and contact > g['min_contact_N'])
            if o.get('min_turns') is not None:
                ok = ok and t['turns'] > o['min_turns']
            for j, pk, now in zip(o.get('jaw', []), t['jaw_peak'], jaw):
                ok = ok and pk > j['min_peak_m'] and now < j['max_final_m']
            self.dwell[k] = self.dwell[k] + dt if ok else 0.
            self.turns[k] = t['turns']
            self.metrics[k] = dict(gap_m=me['gap'], lateral_m=me['lateral'], angle_deg=me['angle'], speed_m_s=me['speed'],
                                   contact_N=contact, travel_m=travel, turns=t['turns'], jaw_m=jaw, jaw_peak_m=list(t['jaw_peak']),
                                   dependencies_ok=deps_ok, in_corridor=True, dwell_s=self.dwell[k])
            if self.dwell[k] >= g['dwell_s']:
                self.engage(o)
