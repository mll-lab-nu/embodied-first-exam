"""VESKEN post-contact retention joints (port of the source pressfit mechanics).

Source: a fixed joint host->part per connection, enabled with the CURRENT relative pose once the
source's acceptance gates hold.

Per operation (task.json['operations']), checked every PERIOD steps:
  geometry  : for every connector, the part's connector point vs the receiver's connector point
              (design centres from task.json); gap = component along the host's outward axis (max |.|),
              lateral = max off-axis error; axis = tilt of the part's outward axis.
  zone      : the operation is "approached" while lateral < 5 mm, -3 mm < gap < 50 mm, tilt < 15 deg.
              While in the zone the largest gap (travel start) and every jaw's peak deflection are
              recorded; leaving the zone clears them (source: per-operation approach->contact phase).
  good      : |gap| < axial_m, lateral < lateral_m, tilt < axis_deg, |v_part| < speed_m_s,
              (largest gap - gap) >= min_travel_m, contact force with the counterparts (receivers +
              this operation's jaws) > min_contact_N, every jaw peak > 0.25 mm and now < 0.7 mm,
              all dependency operations already connected.
  connect   : 'good' held continuously for dwell_s -> weld equality conn_<key> switched on at the
              current relative pose. Never switched off (no disassembly in the source); reset() clears.
The jaws themselves are ordinary MuJoCo slide joints with the source spring (scene.xml), not part of
this class. Not ported: the source's 0.15 N pull probe before connect() (a controller diagnostic).
"""
import math
import numpy as np
import mujoco
from ikea_runtime import Helpers, rotate, qinv, qmul

class VeskenMechanism:
    PERIOD = 4

    def __init__(self, model, data, task):
        self.m, self.d, self.task = model, data, task
        self.h = Helpers(model, data)
        self.ops = task['operations']
        self.c = {n: np.array(v, float) for n, v in task['centers'].items()}
        self.bid = {n: model.body(n).id for n in task['parts']}
        self.eq = {o['key']: model.equality(o['weld']).id for o in self.ops}
        jaws = {j['name']: j for j in task['jaws']}
        self.jaw = {o['key']: [(model.jnt_qposadr[model.joint(jaws[n]['joint']).id], float(jaws[n]['axis'][0])) for n in o['jaws']]
                    for o in self.ops}
        self.zone = task['approach_zone']; self.jg = task['jaw_gates']
        # cheap vectorised prefilter: distance of each part origin from its assembled pose on its host
        self.pid = np.array([self.bid[o['part']] for o in self.ops]); self.hid = np.array([self.bid[o['host']] for o in self.ops])
        self.rel = np.array([self.c[o['part']] - self.c[o['host']] for o in self.ops])
        self.near = 0.10
        self.reset()

    # -------------------------------------------------------------- bookkeeping
    def reset(self):
        self.counter = 0
        self.st = {o['key']: dict(max_gap=None, peak=[0.] * len(o['jaws']), dwell=0.) for o in self.ops}
        self.engaged_at = {}
        self.metrics = {}
        for i in self.eq.values():
            self.d.eq_active[i] = 0

    def connected(self, key):
        return bool(self.d.eq_active[self.eq[key]])

    def state(self):
        return dict(counter=self.counter, st={k: dict(v) for k, v in self.st.items()}, engaged_at=dict(self.engaged_at),
                    eq_data={k: self.m.eq_data[i].tolist() for k, i in self.eq.items()},
                    eq_active={k: bool(self.d.eq_active[i]) for k, i in self.eq.items()})

    def set_state(self, s):
        self.counter = s['counter']; self.st = {k: dict(v) for k, v in s['st'].items()}; self.engaged_at = dict(s['engaged_at'])
        for k, i in self.eq.items():
            self.m.eq_data[i] = s['eq_data'][k]; self.d.eq_active[i] = int(s['eq_active'][k])

    # -------------------------------------------------------------- geometry (source common.geometry)
    def geometry(self, o):
        d = self.d; P = o['part']
        pp = d.xpos[self.bid[P]]; qp = d.xquat[self.bid[P]]; qh = d.xquat[self.bid[o['host']]]
        out = rotate(qh, o['outward'])
        gaps, lats = [], []
        for c in o['connectors']:
            r = c['receiver']; pt = np.asarray(c['point'], float)
            actual = pp + rotate(qp, pt - self.c[P])
            desired = d.xpos[self.bid[r]] + rotate(d.xquat[self.bid[r]], pt - self.c[r])
            dl = actual - desired; g = float(dl @ out)
            gaps.append(g); lats.append(float(np.linalg.norm(dl - g * out)))
        gap = max(gaps, key=abs); lat = max(lats)
        ax = math.degrees(math.acos(float(np.clip(rotate(qp, o['outward']) @ out, -1, 1))))
        return gap, lat, ax

    def jaw_travel(self, key):
        return [float(self.d.qpos[a]) * s for a, s in self.jaw[key]]

    # -------------------------------------------------------------- update
    def update(self):
        self.counter += 1
        if self.counter % self.PERIOD:
            return
        dt = self.m.opt.timestep * self.PERIOD
        z = self.zone; d = self.d
        R = d.xmat[self.hid].reshape(-1, 3, 3)
        dist = np.linalg.norm(d.xpos[self.pid] - d.xpos[self.hid] - np.einsum('nij,nj->ni', R, self.rel), axis=1)
        for idx, o in enumerate(self.ops):
            k = o['key']
            if d.eq_active[self.eq[k]]:
                continue
            s = self.st[k]
            if dist[idx] > self.near:
                if s['max_gap'] is not None:
                    s.update(max_gap=None, peak=[0.] * len(o['jaws']), dwell=0.)
                continue
            gap, lat, ax = self.geometry(o)
            if not (lat < z['lateral_m'] and z['gap_min_m'] < gap < z['gap_max_m'] and ax < z['axis_deg']):
                if s['max_gap'] is not None:
                    s.update(max_gap=None, peak=[0.] * len(o['jaws']), dwell=0.)
                continue
            jaws = self.jaw_travel(k)
            s['max_gap'] = gap if s['max_gap'] is None else max(s['max_gap'], gap)
            s['peak'] = [max(a, b) for a, b in zip(s['peak'], jaws)]
            g = o['gates']
            v = self.h.state13(o['part'])[7:10]; speed = float(np.linalg.norm(v))
            contact = self.h.contact_force_between(o['part'], o['counterparts'])
            deps = all(self.connected(x) for x in o['dependencies'])
            good = (abs(gap) < g['axial_m'] and lat < g['lateral_m'] and ax < g['axis_deg'] and speed < g['speed_m_s']
                    and s['max_gap'] - gap >= g['min_travel_m'] and contact > g['min_contact_N']
                    and all(p > self.jg['peak_travel_min_m'] for p in s['peak'])
                    and all(j < self.jg['final_travel_max_m'] for j in jaws) and deps)
            s['dwell'] = s['dwell'] + dt if good else 0.
            self.metrics[k] = dict(gap_m=gap, lateral_m=lat, axis_deg=ax, speed_m_s=speed, travel_m=s['max_gap'] - gap,
                                   contact_N=contact, jaw_m=jaws, jaw_peak_m=list(s['peak']), dependencies_ok=deps, dwell_s=s['dwell'])
            if s['dwell'] >= g['dwell_s']:
                self.connect(o)

    def connect(self, o):
        i = self.eq[o['key']]
        r, q = self.h.rel_pose(o['host'], o['part'])        # part pose in the host frame (body1=host, body2=part)
        self.m.eq_data[i, 0:3] = 0; self.m.eq_data[i, 3:6] = r; self.m.eq_data[i, 6:10] = q; self.m.eq_data[i, 10] = 1
        self.d.eq_active[i] = 1
        self.engaged_at[o['key']] = float(self.d.time)
