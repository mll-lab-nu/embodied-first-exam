#!/usr/bin/env python3
"""Build the ikea365 closed-loop reference, phase by phase (see README.md).

The original demo is the phase guide; its rows are executed through the joint-speed clamp, plus a per-arm offset that
the closed-loop phases leave behind:
  A  demo rows up to the screw return (gates 1-4: remove, park, cross, return).
  B  the right hand, still holding the returned screw on its thread entry, threads it K turns (right joint 7 spun at w,
     the TCP lowered by the pitch per turn by Jacobian IK), so that it stands upright and engaged instead of tipping
     over on release (the standard agent's finding: released at the entry it tips to ~9 deg under the prism rule).
  C  demo rows to the demo's screwdriver spin; the right arm's joints 1-6 offset is ramped out after its release, its
     joint 7 keeps the K turns.
  D  closed-loop screwing with the left hand's screwdriver: lift clear, centre the tip on the TRUE screw axis (3 IK
     passes), then advance joint 7's target at w (w_slow once the screw is within slow_gap of its seat; the target's
     lead over the joint is bounded by the damping lead + tau / kp) while the axial push on the head is held in the
     f_lo..f_hi band by Jacobian IK and the tip is re-centred every 40 ticks. Once the screw is within seat_gap of its
     seat, joint 7's target follows the joint (zero actuator torque), so the retention welds engage on an unloaded
     screw (the spin's stall torque, left on, twists the welded screw 4 deg and turn_stand is never accepted). After
     the mechanism accepts reinstall_same_screw: hold at zero torque, lift the screwdriver straight up.
  E  demo rows from the end of the demo's turning (e_row) to the end: turn the stand, place the bowl. The left arm is
     blended back onto the demo (joint 7 by whole turns). Guide tracks: in each grasp's approach the arm's TCP follows
     the guide's TCP pose relative to the object (member_b, member_a, bowl; the guide = the demo replayed unclamped on
     the pre-prism physics, where it passes), through damped-least-squares Jacobian IK; the correction stays in the
     arm's offset while it holds and is ramped out after the gripper opens again.
Every stage ends with a checkpoint (the executed rows + the full state), so later stages are searched cheaply.

  build_ref.py --out DIR [--from STAGE] [--to STAGE] [--set key=value ...]   (DIR/ref.npz: the executed rows)
"""
from __future__ import annotations
import argparse, json, math, os, pickle, sys, time
import numpy as np
from i365_lib import Rig, ARM, GRIP, demo_rows, qmul, qconj, rotvec

CFG = dict(
    b_row=41200, k=7.0, w=2.5,                    # B: start row, turns, joint-7 speed (rad/s)
    blend=1.0,                                    # C/E: offset blend times (s)
    spin_row=53635,                               # C ends here (the demo's screwdriver spin starts)
    d_lift=0.003, f_lo=5.0, f_hi=15.0, dz=2e-6,   # D: lift before centring (m), axial force band (N), descent per tick
    tau=99., tau_slow=99., slow_gap=0.0006, seat_gap=0.00004, w_slow=2.0,   # D: lead caps (N m), gaps (m), slow speed
    d_max=60.0, hold=0.2, lift=0.004,             # D: give up (s), hold after acceptance (s), lift (m)
    e_row=63500,                                  # E starts at this demo row (the demo's screwdriver 2 cm up)
    tk_kp=0.02, tk_kr=0.02, tk_cap=0.5, ramp=400, tracks=1,   # tracks=0: E without the guide tracks (ablation)
)
# guide tracks (demo rows [r0, r1), arm, object): the TCP follows the guide's TCP pose relative to the object
TRACKS = [(66000, 69060, 'right', 'member_b'),     # right grasps member_b (closes 68894-69054)
          (71000, 73460, 'left', 'member_a'),       # left grasps the lifted stand (closes 73294-73454)
          (77500, 79420, 'right', 'bowl'),          # right grasps the bowl (closes 79254-79414)
          (79420, 83254, 'right', 'member_a')]      # right places the bowl on the turned stand
GUIDE = os.environ.get('I365_GUIDE', 'runs/scan_old_noclamp.npz')
GUIDE_OBJ = {'member_a': 0, 'member_b': 1, 'same_screw': 2, 'bowl': 3}
STAGES = ['A', 'B', 'C', 'D', 'E']
KP7 = 2000.; KD7 = 200.                           # Panda actuator 7 gains (scene.xml)


def quat_to_mat(q):
    w, x, y, z = q
    return np.array([[1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)], [2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x)],
                     [2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)]])


class Builder:
    def __init__(self, out, cfg):
        self.out = out; self.cfg = cfg; os.makedirs(out, exist_ok=True)
        self.g = Rig(); self.demo = demo_rows(); self.i = 0
        z = np.load(GUIDE); self.gpose = z['pose']; self.gtcp = z['tcp']
        self.track_at = {}
        for r0, r1, arm, obj in TRACKS:
            for i in range(r0, r1):
                self.track_at.setdefault(i, []).append((arm, obj))
        self.off = {a: np.zeros(7) for a in ARM}; self.ramps = []      # [(arm, start_tick, n, offset0, offset1)]
        self.base = {a: np.zeros(7) for a in ARM}    # what an offset ramps out to (joint 7: whole turns)
        self.pending = {}; self.log = []; self.t0 = time.time()

    # ---- state
    def save(self, name):
        st = dict(g=self.g.get(), i=self.i, off={a: v.copy() for a, v in self.off.items()}, ramps=list(self.ramps),
                  base={a: v.copy() for a, v in self.base.items()},
                  pending=dict(self.pending), log=list(self.log), cfg=self.cfg)
        pickle.dump(st, open(os.path.join(self.out, f'ck_{name}.pkl'), 'wb'))

    def load(self, name, src=None):
        st = pickle.load(open(os.path.join(src or self.out, f'ck_{name}.pkl'), 'rb'))
        self.g.set(st['g']); self.i = st['i']; self.off = st['off']; self.ramps = st['ramps']; self.log = st['log']
        self.pending = st['pending']; self.base = st['base']

    def note(self, **kw):
        g = self.g; gap, lat, tilt, sp = g.screw()
        kw.update(row=self.i, tick=len(g.ex), t=round(float(g.d.time), 3), acc=g.M.accepted()[-1:] or None,
                  gap_mm=round(1000 * gap, 3), lat_mm=round(1000 * lat, 3), tilt=round(tilt, 3),
                  wall=round(time.time() - self.t0, 1))
        self.log.append(kw); print(json.dumps(kw, default=str), flush=True)

    # ---- acting
    def target(self, i):
        row = self.demo[i].copy()
        for arm in ARM:
            row[ARM[arm]] += self.off[arm]
        return row

    def ramp(self, arm, n, to=None):
        to = self.base[arm] if to is None else to
        self.ramps = [r for r in self.ramps if r[0] != arm]
        self.ramps.append((arm, len(self.g.ex), n, self.off[arm].copy(), to.copy()))

    def tick_ramps(self):
        t = len(self.g.ex); keep = []
        for arm, t0, n, o0, o1 in self.ramps:
            k = min(1., max(0., (t - t0) / n))
            self.off[arm] = o0 + (o1 - o0) * k
            if k < 1: keep.append((arm, t0, n, o0, o1))
        self.ramps = keep

    def track_dq(self, arm, obj, i):
        """Joint increment moving the arm's TCP toward the guide's TCP pose relative to `obj` at demo row i."""
        g = self.g; d = g.d
        k = GUIDE_OBJ[obj]
        pg, qg = self.gpose[i, k, :3], self.gpose[i, k, 3:]
        Rg = quat_to_mat(qg); tg = self.gtcp[i, 0 if arm == 'left' else 1]
        rel_p = Rg.T @ (tg[:3] - pg); rel_R = Rg.T @ tg[3:].reshape(3, 3)
        po, qo = g.pose(obj); Ro = quat_to_mat(qo)
        p_des = po + Ro @ rel_p; R_des = Ro @ rel_R
        sid = g.site[arm]; p = d.site_xpos[sid]; Rt = d.site_xmat[sid].reshape(3, 3)
        Re = R_des @ Rt.T
        ang = math.acos(max(-1., min(1., (np.trace(Re) - 1) / 2)))
        ax = np.array([Re[2, 1] - Re[1, 2], Re[0, 2] - Re[2, 0], Re[1, 0] - Re[0, 1]])
        w = ax / (np.linalg.norm(ax) + 1e-300) * ang
        cap = g.s.step_limit[ARM[arm]] * self.cfg['tk_cap']
        dq = g.ik(arm, self.cfg['tk_kp'] * (p_des - p), self.cfg['tk_kr'] * w)
        return np.clip(dq, -cap, cap), float(np.linalg.norm(p_des - p)), math.degrees(ang)

    def run_demo(self, end, with_tracks=True):
        g = self.g; demo = self.demo; c = self.cfg
        while self.i < end:
            i = self.i
            for arm in list(self.pending):       # ramp an arm's offset out once its gripper is fully open again
                if demo[i][GRIP[arm]] > 200 and demo[i - 1][GRIP[arm]] == demo[i][GRIP[arm]] and demo[i - 40][GRIP[arm]] < demo[i][GRIP[arm]] \
                        and i not in self.track_at:
                    self.ramp(arm, c['ramp'])
                    del self.pending[arm]; self.note(ev='ramp', arm=arm)
            self.tick_ramps()
            if with_tracks and i in self.track_at:
                for arm, obj in self.track_at[i]:
                    dq, ep, ea = self.track_dq(arm, obj, i)
                    self.off[arm] += dq; self.pending[arm] = True
                    if i % 400 == 0:
                        self.note(ev='track', arm=arm, obj=obj, err_mm=round(1000 * ep, 3), err_deg=round(ea, 3))
            n0 = len(g.M.events)
            g.step(self.target(i))
            if len(g.M.events) > n0:
                self.note(ev='accept', op=g.M.events[-1][0], metrics=g.M.events[-1][2])
            self.i += 1

    # ---- stages
    def stage_A(self):
        self.run_demo(self.cfg['b_row'], with_tracks=False)

    def stage_B(self):
        """The right hand threads the returned screw K turns (joint 7 at w), the TCP lowered by the pitch per turn."""
        g = self.g; c = self.cfg; d = g.d; dt = g.s.control_dt
        cmd = g.ctrl
        n = int(round(c['k'] * 2 * math.pi / (c['w'] * dt)))
        for k in range(n):
            dz = -0.0005 * c['w'] * dt / (2 * math.pi)
            cmd[ARM['right']] += g.ik_move('right', np.array([0, 0, dz]))
            cmd[14] += c['w'] * dt
            g.step(cmd)
            if k % 400 == 0:
                self.note(ev='B', k=k, of=n)
        for _ in range(int(round(0.3 / dt))):
            g.step(cmd)
        off = cmd[ARM['right']] - self.demo[self.i - 1][ARM['right']]
        self.off['right'] = off.copy()
        self.base['right'][6] = 2 * math.pi * round(off[6] / (2 * math.pi))
        self.note(ev='B_done', off=np.round(off, 4).tolist())

    def stage_C(self):
        g = self.g; c = self.cfg; demo = self.demo; dt = g.s.control_dt
        # the demo's release of the screw: the right hand opens; its joints 1-6 offset is ramped out from 0.3 s later
        i_rel = self.i + int(np.flatnonzero(demo[self.i:, 15] > 100)[0])
        i_ramp = i_rel + int(round(0.3 / dt))
        self.run_demo(i_ramp, with_tracks=False)
        self.ramp('right', int(round(c['blend'] / dt)))
        self.run_demo(c['spin_row'], with_tracks=False)

    def stage_D(self):
        g = self.g; c = self.cfg; d = g.d; dt = g.s.control_dt
        cmd = g.ctrl; L = ARM['left']; q7 = int(g.qadr['left'][6]); v7 = int(g.dof['left'][6])
        lat, h = g.tip_offset()
        self.note(ev='D_start', tip_lat_mm=np.round(1000 * lat, 3).tolist(), tip_h_mm=round(1000 * h, 3))
        if h < c['d_lift']:
            nl = int(round(0.3 / dt))
            for _ in range(nl):
                cmd[L] += g.ik_move('left', np.array([0, 0, (c['d_lift'] - h) / nl])); g.step(cmd)
        for _ in range(3):
            lat, h = g.tip_offset(); nl = int(round(0.3 / dt))
            for _ in range(nl):
                cmd[L] += g.ik_move('left', -lat / nl); g.step(cmd)
            for _ in range(int(round(0.2 / dt))):
                g.step(cmd)
        lat, h = g.tip_offset()
        self.note(ev='D_centred', tip_lat_mm=np.round(1000 * lat, 3).tolist(), tip_h_mm=round(1000 * h, 3))
        n0 = len(g.M.events); k = 0; nmax = int(round(c['d_max'] / dt)); mode = 'spin'
        while len(g.M.events) == n0 and k < nmax:
            gap, latm, tilt, sp = g.screw()
            f = g.fbody('screwdriver', 'same_screw')
            if f < c['f_lo']:
                cmd[L] += g.ik_move('left', np.array([0, 0, -c['dz']]))
            elif f > c['f_hi']:
                cmd[L] += g.ik_move('left', np.array([0, 0, c['dz']]))
            if k % 40 == 0:
                lat, h = g.tip_offset(); cmd[L] += g.ik_move('left', -0.2 * lat)
            qv = float(d.qvel[v7]); qq = float(d.qpos[q7])
            if gap > c['seat_gap']:
                tau, w = (c['tau'], c['w']) if gap > c['slow_gap'] else (c['tau_slow'], c['w_slow'])
                mode = 'spin' if gap > c['slow_gap'] else 'slow'
                # joint-7 target: advance at w, but never lead the joint by more than the damping lead + tau / kp
                cmd[6] = min(cmd[6] + w * dt, qq + (KD7 * max(qv, 0.) + tau) / KP7)
            else:
                mode = 'seated'; cmd[6] = qq + KD7 * qv / KP7          # zero actuator torque
            g.step(cmd); k += 1
            if k % 800 == 0:
                self.note(ev='D', k=k, mode=mode, F=round(f, 2), tau7=round(float(d.actuator_force[6]), 3),
                          turns=round(g.M.op.get('turns', 0.), 3))
        ok = len(g.M.events) > n0
        self.note(ev='D_accept' if ok else 'D_FAILED', ticks=k, metrics=g.M.events[-1][2] if ok else None,
                  tau7=round(float(d.actuator_force[6]), 3))
        if not ok:
            raise SystemExit(2)
        # hold (torque zero), then lift the screwdriver straight up
        for _ in range(int(round(c['hold'] / dt))):
            cmd[6] = float(d.qpos[q7]) + KD7 * float(d.qvel[v7]) / KP7
            g.step(cmd)
        q7_hold = cmd[6]
        nl = int(round(0.5 / dt))
        for _ in range(nl):
            cmd[L] += g.ik_move('left', np.array([0, 0, c['lift'] / nl])); cmd[6] = q7_hold; g.step(cmd)
        self.note(ev='D_lifted', op=dict((k, (round(v, 5) if isinstance(v, float) else None)) for k, v in g.M.op.items()
                                       if k in ('drift', 'deg')))
        self.d_cmd = cmd

    def stage_E(self):
        g = self.g; c = self.cfg; dt = g.s.control_dt
        self.i = c['e_row']
        self.off['left'] = g.ctrl[ARM['left']] - self.demo[self.i][ARM['left']]
        self.base['left'][6] = 2 * math.pi * round(self.off['left'][6] / (2 * math.pi))
        self.ramp('left', int(round(c['blend'] / dt)))        # the left arm blended onto the demo (joint 7: whole turns)
        self.run_demo(len(self.demo), with_tracks=bool(c['tracks']))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True); ap.add_argument('--from', dest='frm', default=None)
    ap.add_argument('--src', default=None, help='checkpoint dir to load --from (default --out)')
    ap.add_argument('--to', default=None); ap.add_argument('--set', nargs='*', default=[])
    a = ap.parse_args()
    cfg = dict(CFG)
    for kv in a.set:
        k, v = kv.split('='); cfg[k] = type(CFG[k])(float(v))
    b = Builder(a.out, cfg)
    k0 = 0
    if a.frm:
        b.load(a.frm, a.src); k0 = STAGES.index(a.frm) + 1
    for name in STAGES[k0:]:
        getattr(b, 'stage_' + name)()
        b.save(name)
        b.note(ev='stage', stage=name, accepted=b.g.M.accepted())
        if a.to == name:
            break
    if not a.to or a.to == 'E':
        fc = b.g.s.final_check()
        rep = fc['end']['report']
        b.note(ev='final', success=fc['success'], failures=rep.get('failures'), next=rep.get('next_operation'),
               support=rep.get('strict_support', {}).get('verified'), term=fc['end']['terminal'],
               settled_ok=fc['settled']['success'], sha=fc['state_sha'], settled_sha=fc['settled_sha'],
               events=[(e[0], round(e[1], 3)) for e in b.g.M.events])
        b.g.s.save_trajectory(np.array(b.g.ex), os.path.join(a.out, 'ref.npz'))


if __name__ == '__main__':
    main()
