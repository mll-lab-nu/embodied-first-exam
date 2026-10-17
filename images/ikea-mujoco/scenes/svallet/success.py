"""SVALLET success criteria (self-contained; used through scene.load().success()).

Port of the source endpoint grader:
  * every operation's retention joint is connected (weld on), and at its connector points
    |gap| < axial_m, lateral < lateral_m, axis tilt < axis_deg (s1: shade key in the stand socket,
    s2: E12 bulb thread top at the shade socket);
  * no fixture joints (this scene has none) and the spring jaw joint exists;
  * the stand is supported by the bench: contact normal force (z) on the stand > 0.1 N;
  * the stand orientation is within 3 deg of its upright, initial orientation (quat [1,0,0,0]);
  * cable gate: skipped (cable.enabled = false), never counted as passed.
Added because the source grades with a NullRobot: no robot contact with any lamp part (released).
"""
import numpy as np
import mujoco
from ikea_runtime import Helpers, rotate, axis_angle_deg, quat_angle_deg


class Monitor:
    def __init__(self, model, data, task, scene=None):
        self.m, self.d, self.t, self.scene = model, data, task, scene
        self.h = Helpers(model, data)
        self.robot_bodies = set(i for i in range(model.nbody) if model.body(i).name.startswith(('left_', 'right_')))
        self.part_bodies = set(i for i in range(model.nbody) if model.body(i).name in task['parts'] or model.body(i).name == task['jaw']['name'])
        self.stand = model.body(task['endpoint']['floor_body']).id
        self.bench = model.geom(task['endpoint']['floor_geom']).id
        self.reset()

    def reset(self):
        pass

    def state(self):
        return {}

    def set_state(self, s):
        pass

    def update(self):
        pass

    def _connected(self, key):
        mech = getattr(self.scene, 'mech', None)
        return bool(mech is not None and mech.active(key))

    def evaluate(self):
        rep = dict(operations=[], failures=[])
        for o in self.t['operations']:
            p, qp = self.h.pose(o['part']); h, qh = self.h.pose(o['host'])
            out = rotate(qh, o['axis'])
            gaps, lats = [], []
            for pl, hl in zip(o['points'], o['host_points']):
                delta = (p + rotate(qp, pl)) - (h + rotate(qh, hl))
                g = float(delta @ out); gaps.append(abs(g)); lats.append(float(np.linalg.norm(delta - g * out)))
            ax = axis_angle_deg(rotate(qp, o['axis']), out)
            gt = o['gates']; con = self._connected(o['key'])
            ok = con and max(gaps) < gt['axial_m'] and max(lats) < gt['lateral_m'] and ax < gt['axis_deg']
            rep['operations'].append(dict(key=o['key'], connected=con, gap_m=max(gaps), lateral_m=max(lats), axis_deg=ax, passed=bool(ok)))
            if not ok: rep['failures'].append(o['key'])
        # floor (bench) support of the stand: z force on the stand from the bench
        fz = 0.; f6 = np.zeros(6); gb = self.h.geom_body
        for i in range(self.d.ncon):
            c = self.d.contact[i]
            if c.efc_address < 0: continue
            if (c.geom1 == self.bench and gb[c.geom2] == self.stand) or (c.geom2 == self.bench and gb[c.geom1] == self.stand):
                mujoco.mj_contactForce(self.m, self.d, i, f6)
                fw = c.frame.reshape(3, 3).T @ f6[:3]          # force on geom2 from geom1
                fz += fw[2] if gb[c.geom2] == self.stand else -fw[2]
        e = self.t['endpoint']
        floor_ok = fz > e['min_floor_normal_N']
        orient = quat_angle_deg(self.h.pose('stand')[1], e['root_quat'])
        b1, b2, _ = self.h.contact_normal_forces()
        robot_touch = any(((x in self.robot_bodies) and (y in self.part_bodies)) or ((y in self.robot_bodies) and (x in self.part_bodies))
                          for x, y in zip(b1, b2))
        ops_ok = all(r['passed'] for r in rep['operations'])
        rep.update(operations_ok=bool(ops_ok), fixtures_enabled=0, springs_enabled=True,
                   floor_normal_N=float(fz), floor_contact_present=bool(floor_ok), orientation_deg=float(orient),
                   released=not robot_touch, cable_gate='skipped', cable_connected=None,
                   mechanism=getattr(getattr(self.scene, 'mech', None), 'metrics', None))
        rep['success'] = bool(ops_ok and floor_ok and orient < e['root_upright_deg'] and not robot_touch)
        return rep

    def report(self):
        return self.evaluate()
