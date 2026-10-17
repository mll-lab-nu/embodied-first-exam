"""VARIERA success criteria (self-contained; used through scene.load().success()).

Ported from the source VARIERA grader (screw seated relative to the receiver AND the shelf hole, frames aligned under the shelf,
speed < 0.02 m/s, released and bench-supported) with the latest export's evaluator rules
(no welds: four DISTINCT receivers each hold a screw that was turned relative to that receiver
with pitch-consistent descent, heads seated at the shelf holes, all held for 0.5 s).
Robot contact with any furniture part during the hold window fails the hold (assembly must stand
on its own, like the source's released-fixture requirement).
Gates (task.json['gates']) are the source grader's except the screw seat gap: axial 0.2 mm (user decision
2026-10-15; source 0.1 mm), lateral 0.6 mm, axis 1.5 deg,
speed 0.02 m/s, >= 0.4 measured turns. The frame axial gate is 0.5 mm because without a weld the
frame/shelf gap is set by resting contact rather than a locked joint. Screw seating is measured at the
head bearing point against the hole centre on the shelf top; coaxiality with the receiver at its mouth.
Thread turns and descent are accumulated only over the engaged travel: tip more than 4 pitches (2 mm) past
the receiver mouth (beyond the male and female half-turn lead-ins and the free entry) and the head more than
0.25 mm above its seat, and
the descent must match turns x pitch within 20 % (+ a quarter pitch).
"""
import math
import numpy as np
from ikea_runtime import Helpers, rotate, qmul, qinv, axis_angle_deg, quat_angle_deg

class Monitor:
    PERIOD = 4

    def __init__(self, model, data, task, scene=None):
        self.m, self.d, self.t = model, data, task
        self.h = Helpers(model, data)
        a = task['assembled_in_shelf_frame']
        self.holes = [np.array([x, y, a['screw_seated_origin_z']]) for x, y in a['shelf_holes_xy']]
        self.receivers = [(f, np.array(r)) for f in ('frame_1', 'frame_2') for r in task['receivers_in_frame_frame']]
        self.screws = ['screw_%d' % i for i in range(1, 5)]
        self.g = task['gates']; self.pitch = task['screw']['pitch_m']
        self.robot_bodies = set(i for i in range(model.nbody) if model.body(i).name.startswith(('left_', 'right_')))
        self.part_bodies = set(model.body(n).id for n in task['parts'])
        self.reset()

    def reset(self):
        self.counter = 0
        self.acc = {}       # (screw, receiver index) -> dict(turns, descent, prev_q, prev_z)
        self.hold = 0.
        self.last = None

    def state(self):
        return dict(counter=self.counter, hold=self.hold,
                    acc={'%s|%d' % k: dict(turns=v['turns'], descent=v['descent'], prev_q=None if v['prev_q'] is None else v['prev_q'].tolist(), prev_z=v['prev_z'])
                         for k, v in self.acc.items()})

    def set_state(self, s):
        self.counter = s['counter']; self.hold = s['hold']
        self.acc = {(k.split('|')[0], int(k.split('|')[1])): dict(turns=v['turns'], descent=v['descent'], prev_q=None if v['prev_q'] is None else np.array(v['prev_q']), prev_z=v['prev_z'])
                    for k, v in s['acc'].items()}

    def _receiver_world(self, ri):
        f, r = self.receivers[ri]
        p, q = self.h.pose(f)
        return p + rotate(q, r), rotate(q, [0, 0, 1]), q

    def _track(self):
        # thread engagement bookkeeping: screw tip below a receiver mouth and coaxial within 1 mm
        for s in self.screws:
            ps, qs = self.h.pose(s)
            for ri in range(len(self.receivers)):
                mouth, ax, qf = self._receiver_world(ri)
                rel = ps - mouth; depth = -float(rel @ ax); lat = float(np.linalg.norm(rel + depth * ax))
                key = (s, ri)
                engaged = (depth > 0.0 and depth < 0.012 and lat < 0.001 and axis_angle_deg(rotate(qs, [0, 0, 1]), ax) < 10)
                if not engaged:
                    if key in self.acc: self.acc[key]['prev_q'] = None
                    continue
                qrel = qmul(qinv(qf), qs)
                a = self.acc.setdefault(key, dict(turns=0., descent=0., prev_q=None, prev_z=depth))
                ps_, qsh = self.h.pose('shelf'); zs = rotate(qsh, [0, 0, 1])
                head_gap = float((ps + rotate(qs, [0, 0, self.t['screw']['head_bearing_z_m']]) - (ps_ + rotate(qsh, [0, 0, 0.0015]))) @ zs)
                if a['prev_q'] is not None and head_gap > 0.00025 and depth > 4 * self.pitch:   # engaged travel only: past the lead-ins, before the seat
                    dq = qmul(qrel, qinv(a['prev_q']))
                    if dq[0] < 0: dq = -dq
                    a['turns'] += -2 * math.atan2(dq[3], dq[0]) / (2 * math.pi)   # right-hand: clockwise from head = tightening
                    a['descent'] += depth - a['prev_z']
                a['prev_q'] = qrel; a['prev_z'] = depth

    def evaluate(self):
        g = self.g; rep = dict(screws={}, frames={}, failures=[])
        ps, qs_ = self.h.pose('shelf'); vs = self.h.state13('shelf')
        z = rotate(qs_, [0, 0, 1])
        # frames under shelf
        a = self.t['assembled_in_shelf_frame']
        frames_ok = True
        for f in ('frame_1', 'frame_2'):
            st = self.h.state13(f); best = None
            for tgt_name in ('frame_1', 'frame_2'):
                tgt = ps + rotate(qs_, a[tgt_name]); dl = st[:3] - tgt; gap = float(dl @ z); lat = float(np.linalg.norm(dl - gap * z))
                ang = min(quat_angle_deg(st[3:7], qs_), quat_angle_deg(st[3:7], qmul(qs_, [0, 0, 0, 1])))
                r = dict(target=tgt_name, gap_m=gap, lateral_m=lat, angle_deg=ang, speed_m_s=float(np.linalg.norm(st[7:10])))
                if best is None or lat < best['lateral_m']: best = r
            best['passed'] = bool(abs(best['gap_m']) < g['frame_axial_m'] and best['lateral_m'] < g['lateral_m'] and best['angle_deg'] < g['axis_deg'] and best['speed_m_s'] < g['speed_m_s'])
            rep['frames'][f] = best; frames_ok &= best['passed']
        if rep['frames']['frame_1']['target'] == rep['frames']['frame_2']['target']:
            frames_ok = False; rep['failures'].append('both frames at the same side')
        # screws: seated at a hole, coaxial with a distinct receiver, threaded
        used = set(); screws_ok = True
        for s in self.screws:
            st = self.h.state13(s); sax = rotate(st[3:7], [0, 0, 1]); best = None
            hb = st[:3] + rotate(st[3:7], [0, 0, self.t['screw']['head_bearing_z_m']])     # head bearing point
            for hi, hole in enumerate(self.holes):
                tgt = ps + rotate(qs_, hole + np.array([0, 0, self.t['screw']['head_bearing_z_m']]))   # hole centre on the shelf top
                dl = hb - tgt; gap = float(dl @ z); lat = float(np.linalg.norm(dl - gap * z))
                if best is None or lat < best['lateral_m']:
                    best = dict(hole=hi, gap_m=gap, lateral_m=lat, axis_deg=axis_angle_deg(sax, z), speed_m_s=float(np.linalg.norm(st[7:10])))
            rbest = None
            for ri in range(len(self.receivers)):
                mouth, ax, _ = self._receiver_world(ri); rel = st[:3] - mouth; dd = float(rel @ ax); lat = float(np.linalg.norm(rel - dd * ax))
                if rbest is None or lat < rbest['lateral_m']:
                    rbest = dict(receiver=ri, lateral_m=lat, axis_deg=axis_angle_deg(sax, ax))
            acc = self.acc.get((s, rbest['receiver']), dict(turns=0., descent=0.))
            n = acc['turns']; dsc = acc['descent']
            pitch_ok = n >= g['min_turns'] and abs(dsc - n * self.pitch) <= g['pitch_tolerance_rel'] * n * self.pitch + 0.25 * self.pitch
            ok = (abs(best['gap_m']) < g['axial_m'] and best['lateral_m'] < g['lateral_m'] and best['axis_deg'] < g['axis_deg']
                  and best['speed_m_s'] < g['speed_m_s'] and rbest['lateral_m'] < g['lateral_m'] and rbest['axis_deg'] < g['axis_deg']
                  and pitch_ok and rbest['receiver'] not in used)
            if ok: used.add(rbest['receiver'])
            rep['screws'][s] = dict(**best, receiver=rbest['receiver'], receiver_lateral_m=rbest['lateral_m'],
                                   receiver_axis_deg=rbest['axis_deg'], turns=n, descent_m=dsc, pitch_consistent=bool(pitch_ok), passed=bool(ok))
            screws_ok &= ok
        # released (no robot contact with parts) and supported by the bench
        b1, b2, f = self.h.contact_normal_forces()
        robot_touch = any(((x in self.robot_bodies) and (y in self.part_bodies)) or ((y in self.robot_bodies) and (x in self.part_bodies))
                          for x, y in zip(b1, b2))
        bench = self.m.geom('bench').id
        cg1 = self.d.contact.geom1[:self.d.ncon]; cg2 = self.d.contact.geom2[:self.d.ncon]
        fb = self.h.geom_body
        frame_ids = {self.m.body('frame_1').id, self.m.body('frame_2').id}
        supported = all(any(((cg1[i] == bench and fb[cg2[i]] == fid) or (cg2[i] == bench and fb[cg1[i]] == fid)) for i in range(self.d.ncon)) for fid in frame_ids)
        rep.update(frames_ok=bool(frames_ok), screws_ok=bool(screws_ok), released=not robot_touch, bench_supported=bool(supported),
                   distinct_receivers=len(used))
        rep['instant_ok'] = bool(frames_ok and screws_ok and not robot_touch and supported)
        return rep

    def update(self):
        self.counter += 1
        if self.counter % self.PERIOD:
            return
        self._track()
        if self.counter % (self.PERIOD * 5) == 0:
            rep = self.evaluate(); self.last = rep
            self.hold = self.hold + self.PERIOD * 5 * self.m.opt.timestep if rep['instant_ok'] else 0.

    def report(self):
        rep = self.evaluate()
        rep['hold_s'] = self.hold
        rep['success'] = bool(rep['instant_ok'] and self.hold >= self.g['hold_s'])
        return rep
