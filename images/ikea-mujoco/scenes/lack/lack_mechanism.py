"""LACK source mechanism: auto-weld on seat (the only non-contact mechanism of the scene).

Port of the source seat mechanism. Every `period_steps` physics steps, in the tabletop frame:
  eligible(leg, stud) = 0 <= leg origin z <= seat_z  and  |leg xy - stud xy| <= align_xy
                        and  angle(leg +z, tabletop +z) <= align_axis_deg
  candidates: unassigned legs with |world vertical speed| < seat_speed, sorted by distance;
  each takes the nearest vacant stud (one leg per stud) and its pre-authored weld equality
  weld_leg_k (tabletop -> leg_k) is switched on with the CURRENT relative pose.
Welds stay latched until reset (the source never unwelds outside reset / set_state).
The weld only locks an already-seated leg; it never moves a part to a target pose.
"""
import math
import numpy as np
import mujoco
from ikea_runtime import Helpers, rotate, qmul, qinv


def assign_connections(offsets, axis_cos, vz, slots, previous, th):
    """Verbatim logic of the source criteria.assign_connections."""
    offsets = np.asarray(offsets); slots = np.asarray(slots)
    dist = np.linalg.norm(offsets[:, None, :2] - slots[None, :, :2], axis=-1)
    valid = ((offsets[:, 2] <= th['seat_z_m']) & (offsets[:, 2] >= 0.0)
             & (np.asarray(axis_cos) >= math.cos(math.radians(th['align_axis_deg']))))
    eligible = valid[:, None] & (dist <= th['align_xy_m'])
    result = np.asarray(previous, dtype=int).copy()
    occupied = set(result[result >= 0].tolist())
    cands = sorted((float(dist[i, j]), i, j) for i, j in zip(*np.where(eligible))
                   if result[i] < 0 and abs(vz[i]) < th['seat_speed_m_s'])
    for _, leg, stud in cands:
        if result[leg] < 0 and stud not in occupied:
            result[leg] = stud; occupied.add(stud)
    return result, dist


class SeatWeldMechanism:
    def __init__(self, model, data, task):
        self.m, self.d, self.t = model, data, task
        self.h = Helpers(model, data)
        self.legs = task['legs']; self.slots = np.asarray(task['slots_in_tabletop_frame'], float)
        self.th = task['thresholds']; self.period = task['mechanism']['period_steps']
        self.eq = [model.equality(n).id for n in task['mechanism']['welds']]
        self.reset()

    def reset(self):
        self.counter = 0
        self.assignment = np.full(len(self.legs), -1, dtype=int)
        self.engaged_at = [None] * len(self.legs)
        for i in self.eq:
            self.d.eq_active[i] = 0

    def welded(self):
        return np.array([bool(self.d.eq_active[i]) for i in self.eq])

    def measure(self):
        """offsets (n,3) of leg origins in the tabletop frame, axis cosines (n,), world vz (n,)."""
        pt, qt = self.h.pose('tabletop'); qi = qinv(qt); up = rotate(qt, [0, 0, 1])
        off, cos, vz = [], [], []
        for n in self.legs:
            st = self.h.state13(n)
            off.append(rotate(qi, st[:3] - pt)); cos.append(float(rotate(st[3:7], [0, 0, 1]) @ up)); vz.append(float(st[9]))
        return np.array(off), np.array(cos), np.array(vz)

    def update(self):
        self.counter += 1
        if self.counter % self.period:
            return
        off, cos, vz = self.measure()
        new, _ = assign_connections(off, cos, vz, self.slots, self.assignment, self.th)
        for k in np.where((new >= 0) & (self.assignment < 0))[0]:
            self.engage(int(k))
        self.assignment = new

    def engage(self, k):
        i = self.eq[k]
        r, q = self.h.rel_pose('tabletop', self.legs[k])     # leg pose in the tabletop frame
        self.m.eq_data[i, 0:3] = 0; self.m.eq_data[i, 3:6] = r; self.m.eq_data[i, 6:10] = q; self.m.eq_data[i, 10] = 1
        self.d.eq_active[i] = 1
        self.engaged_at[k] = float(self.d.time)

    def state(self):
        return dict(counter=self.counter, assignment=self.assignment.tolist(), engaged_at=list(self.engaged_at),
                    eq_data=[self.m.eq_data[i].tolist() for i in self.eq], eq_active=[bool(self.d.eq_active[i]) for i in self.eq])

    def set_state(self, s):
        self.counter = s['counter']; self.assignment = np.array(s['assignment'], dtype=int); self.engaged_at = list(s['engaged_at'])
        for i, ed, ea in zip(self.eq, s['eq_data'], s['eq_active']):
            self.m.eq_data[i] = ed; self.d.eq_active[i] = int(ea)
