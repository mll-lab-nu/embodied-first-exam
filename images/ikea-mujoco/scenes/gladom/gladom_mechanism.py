"""GLADOM retention mechanism (the source's fixed connection joints).

The source enables a fixed joint part->frame_a ("Joints/<part>") once an operation's acceptance
gates hold for 36 steps at 240 Hz (0.15 s):
  |gap| <= 0.8 mm along frame_a z, lateral <= 1 mm, tilt <= 2 deg (threads: screw axis tilt),
  relative speed < 0.025 m/s, travel (initial gap - gap) >= 1 mm, counterpart contact > 0.01 N,
  threads: >= a quarter turn.
Joints: the four screws on their own acceptance; frame_b after s2-122202 (bottom screw);
ring after s3-122202-right (both ring screws). The tray is never jointed.
Here each joint is an initially inactive MuJoCo weld 'retain_<part>' switched on at the current
relative pose (shared ikea_runtime.RetentionMechanism.engage). Additions for a robot instead of the
source's scripted wrench driver:
  * turns are counted only while the screw is inside its thread corridor (coaxial within 1 mm,
    tip between 2 mm below the target and 7 mm above it = above the nut top);
  * travel = peak gap since the part entered a 5 mm lateral corridor minus the current gap;
  * chronology: s1/s2 screws need frame_b aligned (s1-cross-align gates), ring screws need the
    ring placed (s3-ring-place gates) at acceptance time;
  * symmetric parts: frame_b / ring may sit at 0 or 180 deg; ring screws may use either ring
    receiver, but not the same one.
"""
import math
import numpy as np
import mujoco
from ikea_runtime import RetentionMechanism, Helpers, qmul, qinv, quat_angle_deg


# fast local math (numpy.cross is ~25 us per call; these run at the 250 Hz bookkeeping rate)
def rotate(q, v):
    out = np.zeros(3); mujoco.mju_rotVecQuat(out, np.asarray(v, float), np.asarray(q, float)); return out

def cross(a, b):
    return np.array([a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]])

def axis_angle_deg(u, v):
    u = np.asarray(u, float); v = np.asarray(v, float)
    return math.degrees(math.atan2(float(np.linalg.norm(cross(u, v))), float(u @ v)))


def state13(m, d, b):
    """[pos, quat, lin vel, ang vel] (world) of body id b (fast; no np.r_)."""
    v = np.zeros(6); mujoco.mj_objectVelocity(m, d, mujoco.mjtObj.mjOBJ_BODY, b, v, 0)
    out = np.empty(13); out[:3] = d.xpos[b]; out[3:7] = d.xquat[b]; out[7:10] = v[3:]; out[10:] = v[:3]
    return out


def pose_error(h, part, host, target_pos, target_quats, axis=(0, 0, 1), tilt='full', part_axis=(0, 0, 1)):
    """Best (gap, lateral, angle, speed, index) over the symmetric target orientations."""
    sp = state13(h.m, h.d, h.bid(part)); sh = state13(h.m, h.d, h.bid(host)); qh = sh[3:7]
    tp = sh[:3] + rotate(qh, target_pos); ax = rotate(qh, axis)
    dl = sp[:3] - tp; gap = float(dl @ ax); lat = float(np.linalg.norm(dl - gap * ax))
    best = None
    for i, tq in enumerate(target_quats):
        q = qmul(qh, tq)
        ang = axis_angle_deg(rotate(sp[3:7], part_axis), rotate(q, part_axis)) if tilt == 'axis' else quat_angle_deg(sp[3:7], q)
        if best is None or ang < best[1]:
            best = (i, ang)
    vh = sh[7:10] + cross(sh[10:13], sp[:3] - sh[:3])
    return dict(gap=gap, lateral=lat, angle=best[1], quat_index=best[0], speed=float(np.linalg.norm(sp[7:10] - vh)))


def gates_ok(me, g):
    return abs(me['gap']) <= g['axial_m'] and me['lateral'] <= g['lateral_m'] and me['angle'] <= g['axis_deg'] and me['speed'] < g['speed_m_s']


class GladomRetention(RetentionMechanism):
    CORRIDOR_M = 0.005

    def reset(self):
        super().reset()
        self.peak = {}          # op key -> peak gap inside the lateral corridor
        self.claimed = {}       # op key -> engaged target position (host frame)

    def state(self):
        s = super().state(); s.update(peak=dict(self.peak), claimed={k: list(v) for k, v in self.claimed.items()}); return s

    def set_state(self, s):
        super().set_state(s); self.peak = dict(s.get('peak', {})); self.claimed = {k: list(v) for k, v in s.get('claimed', {}).items()}

    def _pair_force(self, a, others):
        n = self.d.ncon
        if n == 0:
            return 0.
        gb = self.h.geom_body; c = self.d.contact
        b1 = gb[c.geom1[:n]]; b2 = gb[c.geom2[:n]]; ia = self.h.bid(a)
        ob = np.zeros(self.m.nbody, bool); ob[[self.h.bid(x) for x in others]] = True
        sel = ((b1 == ia) & ob[b2]) | ((b2 == ia) & ob[b1])
        if not sel.any():
            return 0.
        adr = c.efc_address[:n][sel]
        return float(np.abs(self.d.efc_force[adr[adr >= 0]]).sum())

    def _far(self, o, r=0.02):
        hb = self.h.bid(o['host']); p = self.d.xpos[self.h.bid(o['part'])]
        R = self.d.xmat[hb].reshape(3, 3); ph = self.d.xpos[hb]
        return all(np.linalg.norm(ph + R @ np.asarray(tp) - p) > r for tp in self._candidates(o))

    def _gap_lat(self, o):
        hb = self.h.bid(o['host']); R = self.d.xmat[hb].reshape(3, 3)
        dl = self.d.xpos[self.h.bid(o['part'])] - (self.d.xpos[hb] + R @ np.asarray(o['target_pos']))
        ax = R @ np.asarray(o['axis'], float); gap = float(dl @ ax)
        return gap, float(np.linalg.norm(dl - gap * ax))

    def _candidates(self, o):
        taken = [tuple(self.claimed[k]) for k in o.get('exclusive_with', []) if k in self.claimed]
        c = [o['target_pos']] + o.get('alt_target_pos', [])
        return [p for p in c if tuple(p) not in taken]

    def measure(self, o):
        quats = [o['target_quat']] + o.get('alt_target_quat', [])
        best = None
        for tp in self._candidates(o):
            me = pose_error(self.h, o['part'], o['host'], tp, quats, o['axis'], o.get('tilt', 'full'), o.get('part_axis', [0, 0, 1]))
            if best is None or me['lateral'] < best['lateral']:
                best = me; best['target_pos'] = tp
        best['qrel'] = qmul(qinv(self.d.xquat[self.h.bid(o['host'])]), self.d.xquat[self.h.bid(o['part'])]); best['axis_host'] = np.asarray(o['axis'], float)
        return best

    def update(self):
        self.counter += 1
        if self.counter % self.period:
            return
        dt = self.m.opt.timestep * self.period
        for o in self.ops:
            k = o['key']
            if self.active(k):
                continue
            g = o['gates']
            if self._far(o):     # cheap early-out: part origin > 2 cm from every candidate target
                self.dwell[k] = 0.; self.prev_q.pop(k, None); self.peak.pop(k, None)
                continue
            deps_ok = all(self.active(x) for x in o.get('dependencies', []) if x in self.eq)
            if not deps_ok and not o.get('count_turns'):   # cheap path: only keep the travel peak up to date
                gap, lat = self._gap_lat(o)
                self.peak[k] = max(self.peak.get(k, gap), gap) if lat < self.CORRIDOR_M else gap
                self.dwell[k] = 0.
                continue
            me = self.measure(o)
            if me is None:
                continue
            # travel inside the lateral corridor
            if me['lateral'] < self.CORRIDOR_M:
                self.peak[k] = max(self.peak.get(k, me['gap']), me['gap'])
            else:
                self.peak[k] = me['gap']
            travel = self.peak[k] - me['gap']
            # thread turns, only while engaged in the thread corridor
            if o.get('count_turns'):
                c = o['thread_corridor']
                inside = (me['lateral'] < c['lateral_m'] and me['angle'] < c['axis_deg'] and c['gap_min_m'] < me['gap'] < c['gap_max_m'])
                q = me['qrel']
                if inside and k in self.prev_q:
                    dq = qmul(q, qinv(self.prev_q[k]))
                    if dq[0] < 0: dq = -dq
                    self.turns[k] += 2 * math.atan2(float(dq[1:] @ me['axis_host']), dq[0]) * o.get('turn_sign', 1) / (2 * math.pi)
                if inside: self.prev_q[k] = q
                else: self.prev_q.pop(k, None)
            contact = self._pair_force(o['part'], o['counterparts']) if o.get('counterparts') else 1e9
            ok = deps_ok and gates_ok(me, g) and contact > g.get('min_contact_N', -1)
            if o.get('min_turns') is not None:
                ok = ok and self.turns[k] >= o['min_turns']
            if o.get('min_travel_m') is not None:
                ok = ok and travel >= o['min_travel_m']
            pre_ok = True
            for pr in o.get('prerequisite_poses', []):
                pm = pose_error(self.h, pr['part'], o['host'], pr['target_pos'], pr['target_quats'], tilt=pr.get('tilt', 'full'))
                pre_ok &= gates_ok(pm, pr['gates'])
            ok = ok and pre_ok
            self.dwell[k] = self.dwell[k] + dt if ok else 0.
            self.metrics[k] = dict(gap_m=me['gap'], lateral_m=me['lateral'], angle_deg=me['angle'], speed_m_s=me['speed'],
                                   contact_N=contact if contact < 1e8 else None, turns=self.turns[k], travel_m=travel,
                                   prerequisites_ok=bool(pre_ok), dependencies_ok=bool(deps_ok), dwell_s=self.dwell[k])
            if self.dwell[k] >= g['dwell_s']:
                self.claimed[k] = list(me['target_pos'])
                self.engage(o)
