"""LACK success criteria (self-contained; used through scene.load().success()).

Port of the source endpoint grader: success iff every leg is welded by the seat mechanism (lack_mechanism.py) to a
DISTINCT stud and, measured live in the tabletop frame,
  0 <= leg origin height above the slab top <= 0.012 m,
  lateral offset of the leg origin to its assigned stud <= 0.020 m,
  leg axis within 10 deg of the tabletop axis.
Like the source, this is the assembled endpoint only (no contact history, strength or hold window).
"""
import math
import numpy as np


class Monitor:
    def __init__(self, model, data, task, scene=None):
        self.m, self.d, self.t, self.scene = model, data, task, scene
        self.slots = np.asarray(task['slots_in_tabletop_frame'], float)
        self.th = task['thresholds']

    def reset(self):
        pass

    def update(self):
        pass

    def state(self):
        return {}

    def set_state(self, s):
        pass

    def report(self):
        mech = self.scene.mech
        off, cos, vz = mech.measure()
        welded = mech.welded(); assigned = mech.assignment.copy()
        n = len(self.t['legs'])
        rep = dict(legs=n, welded=welded.tolist(), assignment=assigned.tolist(), depth_m=off[:, 2].tolist(),
                   axis_deg=[math.degrees(math.acos(max(-1., min(1., c)))) for c in cos],
                   scope='Current assembled endpoint only; not contact history, tightening strength or robot validation')
        if not welded.all() or (assigned < 0).any() or len(set(assigned.tolist())) != n:
            rep.update(success=False, reason='missing_or_duplicate_weld'); return rep
        lateral = np.linalg.norm(off[:, :2] - self.slots[assigned], axis=-1)
        ok = bool((off[:, 2] >= 0).all() and (off[:, 2] <= self.th['seat_z_m']).all()
                  and (lateral <= self.th['align_xy_m']).all()
                  and (cos >= math.cos(math.radians(self.th['align_axis_deg']))).all())
        rep.update(success=ok, lateral_m=lateral.tolist())
        return rep
