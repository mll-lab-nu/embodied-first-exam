"""KYRRE success criteria (self-contained; used through scene.load().success()).

User decision 2026-10-16: the task stops after the six screws (operation 9). The three press-in pins were removed
from the scene, and with them the press-in operations and the final turn-over / standing checks (old criteria 3-4, turned over and standing on its legs).
The stool stays upside-down on the table.

Ported from the source endpoint (endpoint_report + the bearing check)
and the final turn-over/gravity-support probe (support_probe):
  1. all 9 retention welds engaged (3 legs, 6 screws) (each by its source acceptance gates, in source order; see
     kyrre_mechanism.py);
  2. every operation still within its gates: worst connector |gap| < 0.6 mm, lateral < 0.8 mm,
     axis < 2 deg;
  3. screw heads seated on connected bearing pads (source kyrre_bearing.evaluate, verbatim geometry);
  4. assembly stays rigid after the last weld: every part within 1 mm / 1 deg of its pose relative
     to the seat when the last weld engaged (source support probe relative drift);
  5. released: no robot contact with any part, and all of the above held for 1.5 s with seat drift
     < 1 cm and tilt change < 3 deg over the hold (source gravity_support: 360 steps at 240 Hz).
"""
import math
import numpy as np
import mujoco
from ikea_runtime import Helpers, rotate, qmul, qinv, axis_angle_deg, quat_angle_deg

EPS = 1e-8
# User decision 2026-10-15: screw seat-gap gate 0.7 mm (source 0.6 mm) for the endpoint and head-bearing checks;
# the weld acceptance gates in kyrre_mechanism.py keep the source 0.6 mm.
SCREW_SEAT_GAP_M = 0.0007

def _connected_bearing(leg, part):
    """Verbatim port of kyrre_bearing.connected_bearing (static leg geometry)."""
    boxes = [s for s in leg["shapes"] if s["kind"] == "box"]
    supports = [i for i, s in enumerate(boxes) if not s.get("bearing_for") and s["size"][2] > .05 and s["size"][2] > 2 * max(s["size"][:2])]
    roots = [max(supports, key=lambda i: boxes[i]["size"][2])] if supports else []
    wanted = [i for i, s in enumerate(boxes) if s.get("bearing_for") == part]
    if not roots or not wanted: return False
    angle = boxes[roots[0]].get("rotation_z_rad", 0.)
    if any(abs(math.sin(s.get("rotation_z_rad", 0.) - angle)) > EPS or math.cos(s.get("rotation_z_rad", 0.) - angle) < 0 for s in boxes): return False
    c, t = math.cos(angle), math.sin(angle); R = np.array([[c, t, 0], [-t, c, 0], [0, 0, 1]])
    centers = [R @ np.array(s["center"]) for s in boxes]; sizes = [np.array(s["size"]) for s in boxes]
    seen = set(roots); todo = list(roots)
    while todo:
        i = todo.pop()
        for j in range(len(boxes)):
            if j in seen: continue
            overlap = (sizes[i] + sizes[j]) / 2 - np.abs(centers[i] - centers[j])
            if (overlap >= -EPS).all() and (overlap > EPS).sum() >= 2: seen.add(j); todo.append(j)
    for i in wanted:
        lo = centers[i] - sizes[i] / 2; hi = centers[i] + sizes[i] / 2
        if lo[2] < -EPS or hi[2] > .020 + EPS or max(abs(lo[0]), abs(hi[0])) > .060 + EPS or max(abs(lo[1]), abs(hi[1])) > .025 + EPS: return False
    return all(i in seen for i in wanted)


class Monitor:
    PERIOD = 20

    def __init__(self, model, data, task, scene=None):
        self.m, self.d, self.t, self.scene = model, data, task, scene
        self.h = Helpers(model, data)
        self.f = task['final']
        self.parts = task['parts']
        self.pid = {n: model.body(n).id for n in self.parts}
        self.seat = self.pid['seat']
        self.legs = [self.pid[n] for n in ('leg_1', 'leg_2', 'leg_3')]
        self.robot = set(i for i in range(model.nbody) if model.body(i).name.startswith(('left_', 'right_')))
        jaws = [model.body(j).id for j in range(model.nbody) if model.body(j).name.startswith('jaw_')]
        self.furniture = set(self.pid.values()) | set(jaws)
        self.sb = task['spec_bodies']
        self.screw_ops = [o for o in task['spec_operations'] if o['mode'] == 'screw']
        self.connected = {o['part']: _connected_bearing(self.sb['leg_' + o['part'].split('_')[1]], o['part']) for o in self.screw_ops}
        self.reset()

    def reset(self):
        self.counter = 0; self.hold = 0.; self.hold_ref = None
        self.rigid_ref = None; self.max_rel = [0., 0.]; self.last = None

    def state(self):
        return dict(counter=self.counter, hold=self.hold, hold_ref=None if self.hold_ref is None else [x.tolist() for x in self.hold_ref],
                    rigid_ref=None if self.rigid_ref is None else {k: [a.tolist(), b.tolist()] for k, (a, b) in self.rigid_ref.items()},
                    max_rel=list(self.max_rel))

    def set_state(self, s):
        self.counter = s['counter']; self.hold = s['hold']
        self.hold_ref = None if s['hold_ref'] is None else [np.array(x) for x in s['hold_ref']]
        self.rigid_ref = None if s['rigid_ref'] is None else {k: (np.array(a), np.array(b)) for k, (a, b) in s['rigid_ref'].items()}
        self.max_rel = list(s['max_rel'])

    def _mech(self):
        return self.scene.mech if self.scene is not None else None

    def _rel(self):
        return {n: self.h.rel_pose('seat', n) for n in self.parts if n != 'seat'}

    def _bearing(self):
        """kyrre_bearing.evaluate with MuJoCo poses (part frames = source part centres)."""
        heads = []
        for op in self.screw_ops:
            part = op['part']; leg_name = 'leg_' + part.split('_')[1]; leg = self.sb[leg_name]
            head = max((s for s in self.sb[part]['shapes'] if s['kind'] == 'cylinder'), key=lambda s: s['radius'])
            pp, pq = self.h.pose(part); lp, lq = self.h.pose(leg_name); lqi = qinv(lq)
            center = rotate(lqi, pp + rotate(pq, head['center']) - lp)
            normal = rotate(lqi, rotate(pq, [0, 0, 1])); normal /= np.linalg.norm(normal)
            axis = float(np.degrees(np.arccos(np.clip(normal[2], -1, 1))))
            target = np.array(op['connectors'][0]['point']) - np.array(leg['center'])
            lateral = float(np.linalg.norm(center[:2] - target[:2]))
            samples = np.array([rotate(lqi, pp + rotate(pq, np.array(head['center']) + [.9666666666666667 * head['radius'] * np.cos(a),
                                .9666666666666667 * head['radius'] * np.sin(a), -head['height'] / 2]) - lp) for a in np.linspace(0, 2 * np.pi, 16, endpoint=False)])
            covered = np.zeros(len(samples), bool); collisions = []
            zext = head['height'] / 2 * abs(normal[2]) + head['radius'] * np.linalg.norm(normal[:2])
            for si, shape in enumerate(leg['shapes']):
                if shape['kind'] != 'box': continue
                a = shape.get('rotation_z_rad', 0.); c, t = math.cos(a), math.sin(a); R = np.array([[c, t], [-t, c]])
                xy = (samples[:, :2] - shape['center'][:2]) @ R.T
                inside = (np.abs(xy) <= np.array(shape['size'][:2]) / 2 + EPS).all(1)
                top = shape['center'][2] + shape['size'][2] / 2; gap = samples[:, 2] - top
                covered |= inside & (np.abs(gap) <= SCREW_SEAT_GAP_M)
                xyc = R @ (center[:2] - shape['center'][:2])
                dist = np.linalg.norm(np.maximum(np.abs(xyc) - np.array(shape['size'][:2]) / 2, 0))
                overlap = min(center[2] + zext, top) - max(center[2] - zext, shape['center'][2] - shape['size'][2] / 2)
                if dist < head['radius'] and overlap > SCREW_SEAT_GAP_M: collisions.append(si)
            ok = bool(covered.all() and self.connected[part] and not collisions and axis < op['gates']['axis_deg'] and lateral < op['gates']['lateral_m'])
            heads.append(dict(screw=part, passed=ok, rim_samples_supported=int(covered.sum()), head_axis_deg=axis, lateral_m=lateral, collisions=collisions))
        return heads

    def evaluate(self):
        mech = self._mech(); rep = dict(failures=[])
        welds = {o['key']: bool(mech is not None and mech.active(o['key'])) for o in self.t['operations']}
        rep['welds'] = welds; rep['welds_engaged'] = sum(welds.values())
        ops = {}
        if mech is not None:
            G, L, A = mech.geometry_all()[:3]
            for i, o in enumerate(mech.ops):
                gap, lat, ang = float(G[i]), float(L[i]), float(A[i]); g = o['gates']
                ops[o['key']] = dict(gap_m=gap, lateral_m=lat, axis_deg=ang, passed=bool(welds[o['key']] and abs(gap) < (SCREW_SEAT_GAP_M if o['mode'] == 'screw' else g['axial_m']) and lat < g['lateral_m'] and ang < g['axis_deg']))
        rep['operations'] = ops
        n_ops = len(self.t['operations'])
        ops_ok = len(ops) == n_ops and all(v['passed'] for v in ops.values())
        b1, b2, _ = self.h.contact_normal_forces()
        robot_touch = any((x in self.robot and y in self.furniture) or (y in self.robot and x in self.furniture) for x, y in zip(b1, b2))
        heads = self._bearing() if rep['welds_engaged'] == n_ops else []
        rep['heads'] = heads; heads_ok = len(heads) == 6 and all(x['passed'] for x in heads)
        rep['max_relative_drift_m'], rep['max_relative_angle_deg'] = self.max_rel
        rigid_ok = self.rigid_ref is not None and self.max_rel[0] < self.f['relative_drift_m'] and self.max_rel[1] < self.f['relative_angle_deg']
        rep.update(all_welds=rep['welds_engaged'] == n_ops, operations_ok=bool(ops_ok), heads_ok=bool(heads_ok), rigid=bool(rigid_ok),
                   released=not robot_touch)
        rep['instant_ok'] = bool(rep['all_welds'] and ops_ok and heads_ok and rigid_ok and not robot_touch)
        return rep

    def update(self):
        self.counter += 1
        if self.counter % self.PERIOD:
            return
        mech = self._mech()
        if mech is None or not all(mech.active(o['key']) for o in self.t['operations']):
            self.hold = 0.; self.hold_ref = None; self.last = None
            return
        if self.rigid_ref is None:
            self.rigid_ref = self._rel()
        for n, (p, q) in self._rel().items():
            p0, q0 = self.rigid_ref[n]
            self.max_rel[0] = max(self.max_rel[0], float(np.linalg.norm(p - p0))); self.max_rel[1] = max(self.max_rel[1], quat_angle_deg(q, q0))
        rep = self.evaluate(); self.last = rep
        sp, sq = self.h.pose('seat')
        if rep['instant_ok']:
            if self.hold_ref is None: self.hold_ref = [sp, sq]
            drift = float(np.linalg.norm(sp - self.hold_ref[0])); turn = quat_angle_deg(sq, self.hold_ref[1])
            if drift < self.f['hold_drift_m'] and turn < self.f['hold_tilt_deg']:
                self.hold += self.PERIOD * self.m.opt.timestep
            else:
                self.hold = 0.; self.hold_ref = [sp, sq]
        else:
            self.hold = 0.; self.hold_ref = None

    def report(self):
        rep = self.evaluate()
        rep['hold_s'] = self.hold
        rep['success'] = bool(rep['instant_ok'] and self.hold >= self.f['hold_s'])
        mech = self._mech()
        if mech is not None:
            rep['mechanism'] = dict(metrics=mech.metrics, engaged_at=mech.engaged_at)
        return rep
