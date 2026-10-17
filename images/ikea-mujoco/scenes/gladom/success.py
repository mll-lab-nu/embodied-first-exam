"""GLADOM success criteria (self-contained; used through scene.load().success()).

Port of the source endpoint grader for the robot scene:
  * required model joints: retention welds of frame_b, ring and the four screws are all active
    (source: Joints/<part> enabled for every part except frame_a and the tray);
  * assembled geometry of every non-root part relative to frame_a: |gap| <= 0.8 mm along frame_a z,
    lateral <= 1 mm, tilt <= 2 deg (screws: axis tilt; others: full orientation modulo the part's
    own symmetry: frame_b / ring 180 deg, tray 7.5 deg), relative speed < 0.025 m/s;
    ring screws may occupy either ring receiver (identical parts), but distinct ones;
  * the tray is unjointed and unforced and supported by the ring: tray-ring contact > 0.01 N in
    >= 12 of 36 samples (and mean > 0.01 N) over the last 0.15 s (source: 36 steps at 240 Hz);
  * released: no robot contact with any furniture part (source: every diagnostic fixture released,
    no wrench on the tray);
  * all of the above hold continuously for 0.15 s.
"""
import math
from collections import deque
import numpy as np
import mujoco
from ikea_runtime import Helpers, qmul, qinv, quat_angle_deg


# fast local math (numpy.cross is ~25 us per call; these run at the 250 Hz bookkeeping rate)
def rotate(q, v):
    out = np.zeros(3); mujoco.mju_rotVecQuat(out, np.asarray(v, float), np.asarray(q, float)); return out

def cross(a, b):
    return np.array([a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]])

def axis_angle_deg(u, v):
    u = np.asarray(u, float); v = np.asarray(v, float)
    return math.degrees(math.atan2(float(np.linalg.norm(cross(u, v))), float(u @ v)))

ROOT = 'frame_a'


def state13(m, d, b):
    """[pos, quat, lin vel, ang vel] (world) of body id b (fast; no np.r_)."""
    v = np.zeros(6); mujoco.mj_objectVelocity(m, d, mujoco.mjtObj.mjOBJ_BODY, b, v, 0)
    out = np.empty(13); out[:3] = d.xpos[b]; out[3:7] = d.xquat[b]; out[7:10] = v[3:]; out[10:] = v[:3]
    return out


class Monitor:
    PERIOD = 4

    def __init__(self, model, data, task, scene=None):
        self.m, self.d, self.t, self.scene = model, data, task, scene
        self.h = Helpers(model, data)
        self.g = task['gates']
        self.ops = {o['key']: o for o in task['operations']}
        self.robot_mask = np.array([model.body(i).name.startswith(('left_', 'right_')) for i in range(model.nbody)])
        self.part_mask = np.zeros(model.nbody, bool); self.part_mask[[model.body(n).id for n in task['parts']]] = True
        self.weld_ids = {p: model.equality(e).id for p, e in task['retention_joints'].items()}
        tr = task['tray']
        self.win = max(1, int(round(tr['contact_window_s'] / (self.PERIOD * model.opt.timestep))))
        self.reset()

    def reset(self):
        self.counter = 0; self.hold = 0.; self.last = None
        self.tray_hist = deque(maxlen=self.win); self.touch_hist = deque(maxlen=self.win)

    def state(self):
        return dict(counter=self.counter, hold=self.hold, tray_hist=list(self.tray_hist), touch_hist=list(self.touch_hist))

    def set_state(self, s):
        self.counter = s['counter']; self.hold = s['hold']
        self.tray_hist = deque(s['tray_hist'], maxlen=self.win); self.touch_hist = deque(s['touch_hist'], maxlen=self.win)

    # ------------------------------------------------------------ geometry
    def _pose(self, part, target, quats=None, tilt='full', yaw_period=None):
        a = state13(self.m, self.d, self.h.bid(ROOT)); s = state13(self.m, self.d, self.h.bid(part)); qa = a[3:7]
        z = rotate(qa, [0, 0, 1]); tp = a[:3] + rotate(qa, target)
        dl = s[:3] - tp; gap = float(dl @ z); lat = float(np.linalg.norm(dl - gap * z))
        if tilt == 'axis':
            ang = axis_angle_deg(rotate(s[3:7], [0, 0, 1]), z)
        else:
            if yaw_period is not None:   # nearest symmetric yaw from the twist of the relative rotation about frame_a z
                qr = qmul(qinv(qa), s[3:7]); psi = 2 * math.atan2(qr[3], qr[0]); per = math.radians(yaw_period)
                k = round(psi / per); quats = [[math.cos(k * per / 2), 0, 0, math.sin(k * per / 2)]]
            ang = min(quat_angle_deg(s[3:7], qmul(qa, q)) for q in quats)
        v = a[7:10] + cross(a[10:13], s[:3] - a[:3])
        return dict(gap_m=gap, lateral_m=lat, angle_deg=ang, speed_m_s=float(np.linalg.norm(s[7:10] - v)))

    def _ok(self, r):
        g = self.g
        return bool(abs(r['gap_m']) <= g['axial_m'] and r['lateral_m'] <= g['lateral_m'] and r['angle_deg'] <= g['axis_deg'] and r['speed_m_s'] < g['speed_m_s'])

    def _contacts(self):
        n = self.d.ncon
        if n == 0:
            return 0., False
        c = self.d.contact; gb = self.h.geom_body
        b1 = gb[c.geom1[:n]]; b2 = gb[c.geom2[:n]]
        tray, ring = self.h.bid('tray'), self.h.bid('ring')
        sel = ((b1 == tray) & (b2 == ring)) | ((b2 == tray) & (b1 == ring))
        tray_ring = 0.
        if sel.any():
            adr = c.efc_address[:n][sel]; tray_ring = float(np.abs(self.d.efc_force[adr[adr >= 0]]).sum())
        touch = bool(np.any((self.robot_mask[b1] & self.part_mask[b2]) | (self.robot_mask[b2] & self.part_mask[b1])))
        return tray_ring, touch

    def evaluate(self):
        rep = dict(geometry={}, joints={}, failures=[])
        o = self.ops
        rep['geometry']['frame_b'] = self._pose('frame_b', o['s1-cross-align']['target_pos'], [o['s1-cross-align']['target_quat']] + o['s1-cross-align']['alt_target_quat'])
        rep['geometry']['ring'] = self._pose('ring', o['s3-ring-place']['target_pos'], [o['s3-ring-place']['target_quat']] + o['s3-ring-place']['alt_target_quat'])
        rep['geometry']['tray'] = self._pose('tray', o['s4-tray-place']['target_pos'], yaw_period=self.t['tray']['yaw_period_deg'])
        for k in ('s1-123451', 's2-122202'):
            rep['geometry'][o[k]['part']] = self._pose(o[k]['part'], o[k]['target_pos'], tilt='axis')
        # ring screws: best distinct assignment to the two ring receivers
        L, R = o['s3-122202-left'], o['s3-122202-right']
        tl, tr = L['target_pos'], R['target_pos']
        a = (self._pose(L['part'], tl, tilt='axis'), self._pose(R['part'], tr, tilt='axis'))
        b = (self._pose(L['part'], tr, tilt='axis'), self._pose(R['part'], tl, tilt='axis'))
        use = a if a[0]['lateral_m'] + a[1]['lateral_m'] <= b[0]['lateral_m'] + b[1]['lateral_m'] else b
        rep['geometry'][L['part']], rep['geometry'][R['part']] = use
        rep['ring_screws_swapped'] = use is b
        for n, r in rep['geometry'].items():
            r['passed'] = self._ok(r)
            if not r['passed']: rep['failures'].append('geometry:' + n)
        for p, i in self.weld_ids.items():
            rep['joints'][p] = bool(self.d.eq_active[i])
            if not rep['joints'][p]: rep['failures'].append('missing_required_model_joint:' + p)
        tray_ring, touch = self._contacts()
        hist = np.array(self.tray_hist if len(self.tray_hist) else [tray_ring])
        thr = self.t['tray']['min_contact_N']
        support = bool(len(hist) >= self.win and np.count_nonzero(hist > thr) >= math.ceil(self.t['tray']['min_active_fraction'] * self.win) and hist.mean() > thr)
        if not support: rep['failures'].append('unforced_gravity_support:tray')
        released = not touch and not any(self.touch_hist)
        if not released: rep['failures'].append('robot_contact_with_furniture')
        rep.update(tray_ring_contact_N=tray_ring, support=support, released=released,
                   geometry_fraction=float(np.mean([r['passed'] for r in rep['geometry'].values()])),
                   joint_fraction=float(np.mean(list(rep['joints'].values()))))
        if self.scene is not None and getattr(self.scene, 'mech', None) is not None:
            rep['operations'] = {k: dict(v, engaged=self.scene.mech.active(k)) for k, v in self.scene.mech.metrics.items()}
            for k in self.scene.mech.eq:
                rep.setdefault('operations', {}).setdefault(k, {})['engaged'] = self.scene.mech.active(k)
        rep['instant_ok'] = not rep['failures']
        return rep

    def update(self):
        self.counter += 1
        if self.counter % self.PERIOD:
            return
        tray_ring, touch = self._contacts()
        self.tray_hist.append(tray_ring); self.touch_hist.append(touch)
        if self.counter % (self.PERIOD * 5) == 0:
            if not all(self.d.eq_active[i] for i in self.weld_ids.values()):   # fast path: a required joint is missing
                self.hold = 0.; return
            rep = self.evaluate(); self.last = rep
            self.hold = self.hold + self.PERIOD * 5 * self.m.opt.timestep if rep['instant_ok'] else 0.

    def report(self):
        rep = self.evaluate()
        rep['hold_s'] = self.hold
        rep['success'] = bool(rep['instant_ok'] and self.hold >= self.g['hold_s'])
        return rep
