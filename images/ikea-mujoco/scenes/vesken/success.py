"""VESKEN body steps 1-8 success criteria (self-contained; used through scene.load().success()).

Port of the source endpoint grader:
  * every one of the 23 operations is connected (its retention weld is on) AND, at the current
    state, its connector error is within the operation gates: max |gap| < axial_m (0.6 mm),
    max lateral < lateral_m (0.8 mm), outward-axis tilt < axis_deg (2 deg);
  * no fixtures (none exist in this scene) and all 32 spring jaws present (always true here);
  * floor support: summed vertical contact force between the four feet and the bench top > 0.1 N
    (source: feet against the ground plane);
  * base orientation: tray_0 within 3 deg of its upright, unrotated assembly orientation (full
    rotation angle, as the source).
Robot analogue of the source's NullRobot endpoint: no arm link touches any furniture part or jaw
('released'). The source endpoint is instantaneous (no hold time); so is this one.
"""
import math
import numpy as np
import mujoco
from ikea_runtime import Helpers, rotate, quat_angle_deg

class Monitor:
    def __init__(self, model, data, task, scene=None):
        self.m, self.d, self.t, self.scene = model, data, task, scene
        self.h = Helpers(model, data)
        self.c = {n: np.array(v, float) for n, v in task['centers'].items()}
        self.eq = {o['key']: model.equality(o['weld']).id for o in task['operations']}
        self.feet = [model.body(n).id for n in task['floor_parts']]
        self.floor = set(model.geom(g).id for g in task['floor_geoms'])
        self.robot = set(i for i in range(model.nbody) if model.body(i).name.startswith(('left_', 'right_')))
        jaw_names = [j['name'] for j in task['jaws']]
        self.furniture = set(model.body(n).id for n in task['parts'] + jaw_names)

    def reset(self): pass
    def update(self): pass
    def state(self): return {}
    def set_state(self, s): pass

    def _op(self, o):
        d = self.d; P = o['part']
        pp, qp = self.h.pose(P); _, qh = self.h.pose(o['host'])
        out = rotate(qh, o['outward']); gaps, lats = [], []
        for c in o['connectors']:
            r = c['receiver']; pt = np.asarray(c['point'], float); pr, qr = self.h.pose(r)
            dl = (pp + rotate(qp, pt - self.c[P])) - (pr + rotate(qr, pt - self.c[r]))
            g = float(dl @ out); gaps.append(abs(g)); lats.append(float(np.linalg.norm(dl - g * out)))
        ax = math.degrees(math.acos(float(np.clip(rotate(qp, o['outward']) @ out, -1, 1))))
        g = o['gates']; conn = bool(d.eq_active[self.eq[o['key']]])
        return dict(key=o['key'], connected=conn, gap_m=max(gaps), lateral_m=max(lats), axis_deg=ax,
                    passed=bool(conn and max(gaps) < g['axial_m'] and max(lats) < g['lateral_m'] and ax < g['axis_deg']))

    def report(self):
        d, m = self.d, self.m
        ops = [self._op(o) for o in self.t['operations']]
        fz = 0.; robot_touch = False; f6 = np.zeros(6); gb = m.geom_bodyid
        for i in range(d.ncon):
            c = d.contact[i]; b1, b2 = gb[c.geom1], gb[c.geom2]
            if (b1 in self.robot and b2 in self.furniture) or (b2 in self.robot and b1 in self.furniture):
                robot_touch = True
            if (c.geom1 in self.floor and b2 in self.feet) or (c.geom2 in self.floor and b1 in self.feet):
                mujoco.mj_contactForce(m, d, i, f6)
                fw = c.frame.reshape(3, 3).T @ f6[:3]          # force on geom2 from geom1 (world)
                fz += abs(float(fw[2]))
        _, qb = self.h.pose(self.t['base'])
        orient = quat_angle_deg(qb, self.t['base_orientation_quat'])
        floor_ok = fz > 0.1
        rep = dict(operations=ops, connected=sum(o['connected'] for o in ops), operations_passed=sum(o['passed'] for o in ops),
                   floor_contact_N=fz, floor_contact_present=bool(floor_ok), orientation_deg=orient,
                   fixtures_off=True, springs_enabled=True, released=not robot_touch)
        rep['success'] = bool(all(o['passed'] for o in ops) and floor_ok and orient < self.t['base_orientation_deg'] and not robot_touch)
        return rep
