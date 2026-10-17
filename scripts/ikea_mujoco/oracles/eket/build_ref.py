#!/usr/bin/env python3
"""Build the eket closed-loop reference, phase by phase (see README.md).

The original demo is the phase guide: its rows are executed through the joint-speed clamp, plus a per-arm offset that
the closed-loop corrections leave behind. At each slide's servo point, if the operation's gate has not accepted yet,
the demo pauses and the panel-holding arm runs a Jacobian servo on the true relative pose of the panel to the top until
the gate accepts; the correction stays as the arm's offset and is ramped out once the arm has released the panel.
Every stage ends with a checkpoint (the executed rows so far + the full state), so later stages are searched cheaply.

  build_ref.py --out DIR [--from STAGE] [--to STAGE] [--set key=value ...]   (DIR/ref.npz: the executed rows)
"""
from __future__ import annotations
import argparse, json, math, os, pickle, sys, time
import numpy as np
from eket_lib import Rig, ARM, GRIP, demo_rows, qmul, qconj

CFG = dict(
    sa_row=10000, sa_kp=0.05, sa_kr=0.05,
    sb_row=26000, sb_kp=0.05, sb_kr=0.05,
    bk_row=52200, bk_kp=0.03, bk_kr=0.03,
    bo_row=64000, bo_kp=0.03, bo_kr=0.03,
    ramp=400, max_servo=4000, post_hold=0,
    tk_kp=0.02, tk_kr=0.02, tk_cap=0.5,         # 0.05 jams the back (run b2); 0.02 = the reference (b2k)
)
# guide tracks (demo rows [r0, r1), arm, panel): the held panel follows the guide's pose relative to the top
TRACKS = [(5800, 10000, 'left', 'side_a'), (18250, 26000, 'left', 'side_b'), (35650, 46300, 'left', 'back'),
          (49900, 52200, 'left', 'back'), (56400, 64000, 'left', 'bottom')]
GUIDE = os.environ.get('EKET_GUIDE', 'runs/guide.npz')
STAGES = [('side_a', 11400), ('side_b', 27300), ('back', 52260), ('bottom', 65300), ('end', None)]


class Builder:
    def __init__(self, out, cfg):
        self.out = out; self.cfg = cfg; os.makedirs(out, exist_ok=True)
        self.g = Rig(); self.demo = demo_rows(); self.i = 0
        z = np.load(GUIDE); self.guide = z['rel']; self.groles = list(z['roles'])
        self.track_at = {}
        for r0, r1, arm, role in TRACKS:
            for i in range(r0, r1):
                self.track_at[i] = (arm, role)
        self.off = {a: np.zeros(7) for a in ARM}; self.ramps = []      # [(arm, start_tick, n, offset0)]
        self.log = []; self.pending = {}
        c = cfg
        self.servos = {c['sa_row']: ('side_a_slide', 'left', 'side_a', c['sa_kp'], c['sa_kr']),
                       c['sb_row']: ('side_b_slide', 'left', 'side_b', c['sb_kp'], c['sb_kr']),
                       c['bk_row']: ('back_slide', 'left', 'back', c['bk_kp'], c['bk_kr']),
                       c['bo_row']: ('bottom_slide', 'left', 'bottom', c['bo_kp'], c['bo_kr'])}

    # ---- state
    def save(self, name):
        st = dict(g=self.g.get(), i=self.i, off={a: v.copy() for a, v in self.off.items()}, ramps=list(self.ramps), pending=dict(self.pending),
                  log=list(self.log), cfg=self.cfg)
        pickle.dump(st, open(os.path.join(self.out, f'ck_{name}.pkl'), 'wb'))

    def load(self, name):
        st = pickle.load(open(os.path.join(self.out, f'ck_{name}.pkl'), 'rb'))
        self.g.set(st['g']); self.i = st['i']; self.off = st['off']; self.ramps = st['ramps']; self.log = st['log']; self.pending = st['pending']

    def note(self, **kw):
        kw.update(row=self.i, tick=len(self.g.ex), done=self.g.tr.status()['completed'][-1:] or None)
        self.log.append(kw); print(json.dumps(kw, default=str), flush=True)

    # ---- acting
    def target(self, i):
        row = self.demo[i].copy()
        for arm in ARM:
            row[ARM[arm]] += self.off[arm]
        return row

    def tick_ramps(self):
        t = len(self.g.ex); keep = []
        for arm, t0, n, o0 in self.ramps:
            k = min(1., (t - t0) / n)
            self.off[arm] = o0 * (1 - k)
            if k < 1: keep.append((arm, t0, n, o0))
        self.ramps = keep

    def track_dq(self, arm, role, ref):
        g = self.g
        p, q, v, w = g.rel(role)
        qe = qmul(ref[3:], qconj(q / np.linalg.norm(q)))
        if qe[0] < 0: qe = -qe
        ang = 2 * math.atan2(np.linalg.norm(qe[1:]), qe[0])
        rv = qe[1:] / (np.linalg.norm(qe[1:]) + 1e-300) * ang       # rotation (top frame) from the panel to the guide
        cap = g.s.step_limit[ARM[arm]] * self.cfg['tk_cap']
        # servo_dq turns ep (goal - p) and r (the panel's rotation, corrected by -r) into the arm increment
        return g.servo_dq(arm, role, self.cfg['tk_kp'], self.cfg['tk_kr'], cap=cap, ep=ref[:3] - p, r=-rv)

    def servo(self, op, arm, role, kp, kr):
        g = self.g
        row = self.target(self.i)
        cap = g.s.step_limit[ARM[arm]] * 0.5
        n0 = len(g.tr.records); k = 0
        while len(g.tr.records) == n0 and k < self.cfg['max_servo']:
            row[ARM[arm]] += g.servo_dq(arm, role, kp, kr, cap=cap)
            g.step(row); k += 1
        ok = len(g.tr.records) > n0
        for _ in range(self.cfg['post_hold']):
            g.step(row)
        self.off[arm] = g.ctrl[ARM[arm]] - self.demo[self.i][ARM[arm]]
        self.note(ev='servo', op=op, ok=ok, ticks=k, off=np.round(self.off[arm], 5).tolist(),
                  rec=g.tr.records[-1]['name'] if ok else None)
        return ok

    def run_to(self, end):
        g = self.g; demo = self.demo; end = len(demo) if end is None else end
        pending_ramp = self.pending
        while self.i < end:
            i = self.i
            if i in self.servos:
                op, arm, role, kp, kr = self.servos[i]
                if g.cur() == op and g.tr.gate is not None:
                    self.servo(op, arm, role, kp, kr)
                    pending_ramp[arm] = True
                else:
                    self.note(ev='servo_skip', op=op, cur=g.cur())
            # ramp out an arm's offset once its gripper is fully open again (the panel released)
            for arm in list(pending_ramp):
                if demo[i][GRIP[arm]] == 255 and demo[i - 1][GRIP[arm]] == 255 and demo[i - 40][GRIP[arm]] < 255:
                    self.ramps.append((arm, len(g.ex), self.cfg['ramp'], self.off[arm].copy())); del pending_ramp[arm]
                    self.note(ev='ramp', arm=arm)
            self.tick_ramps()
            if i in self.track_at:
                arm, role = self.track_at[i]
                ref = self.guide[i, self.groles.index(role)]
                self.off[arm] += self.track_dq(arm, role, ref)
            n0 = len(g.tr.records)
            g.step(self.target(i))
            if len(g.tr.records) > n0:
                self.note(ev='accept', op=g.tr.records[-1]['name'])
            self.i += 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True); ap.add_argument('--from', dest='frm', default=None)
    ap.add_argument('--to', default=None); ap.add_argument('--set', nargs='*', default=[])
    a = ap.parse_args()
    cfg = dict(CFG)
    for kv in a.set:
        k, v = kv.split('='); cfg[k] = type(CFG[k])(float(v)) if isinstance(CFG[k], (int, float)) else v
    b = Builder(a.out, cfg)
    names = [s for s, _ in STAGES]
    k0 = 0
    if a.frm:
        b.load(a.frm); k0 = names.index(a.frm) + 1
    t0 = time.time()
    for name, end in STAGES[k0:]:
        b.run_to(end)
        b.save(name)
        st = b.g.tr.status()
        b.note(ev='stage', stage=name, completed=st['completed'], cur=st['current'], wall=round(time.time() - t0, 1))
        if a.to == name:
            break
    if not a.to or a.to == 'end':
        fc = b.g.s.final_check()
        b.note(ev='final', success=fc['success'], checks=fc['end']['report']['checks'], term=fc['end']['terminal'],
               settled=fc['settled']['report']['checks'], sha=fc['state_sha'], settled_sha=fc['settled_sha'])
        ex = np.array(b.g.ex)
        b.g.s.save_trajectory(ex, os.path.join(a.out, 'ref.npz'))


if __name__ == '__main__':
    main()
