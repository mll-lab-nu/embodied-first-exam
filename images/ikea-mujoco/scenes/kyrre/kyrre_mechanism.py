"""KYRRE retention mechanism: the source's post-contact retention joints, one weld per operation.

Source: the source's KYRRE press-fit operation gates and its connect step. A weld (MuJoCo weld equality, initially off) is switched on
with the CURRENT host->part relative pose once all of these hold continuously for dwell_s (0.15 s):
  * previous operation's weld on (source 'dependencies'; the source runs operations strictly in order)
  * |gap| < axial_m (0.6 mm) along the host outward axis, lateral < lateral_m (0.8 mm), tilt < axis_deg (2 deg),
    gap/lateral the worst over the operation's connector points (source geometry())
  * travel: the part came down >= min_travel_m (4 mm) along the axis (source: initial gap - gap)
  * expected counterpart contact > min_contact_N (0.03 N): sum over counterparts of |net contact force|
    (screws: seat; legs: seat; press-ins: leg + its jaw)
  * dwell speed (user decision 2026-09-27, fd_speed_rule): world-frame finite-difference speed of the
    part centre < speed_m_s (0.02 m/s); here the difference is taken over the 4-step mechanism period
  * screws: > 1/4 turn (pi/2) of tightening rotation about the axis (right-hand: clockwise seen from above)
  * press-ins: the jaw opened > 0.25 mm during insertion and is now back below 0.7 mm (snap captured)
History (travel, turns, jaw peak) accumulates while the part is near its seat: lateral < 15 mm,
tilt < 15 deg, gap > -3 mm (the source's escape limits); it restarts when the part leaves that region.
Welds are never switched off (the source has no disassembly); reset() clears everything.
Not ported: the source's 0.15 N / 0.25 s pull test before a press-in joint (a controller-applied test).
Seated screws (speed, user decision 2026-10-16): when a screw's weld latches, every geom of that screw and the
internal-thread insert geoms of its hole (<host>_ins<i>_tooth*/wall*, the insert at the screw's target) get
contype = conaffinity = 0, so a seated screw has no contacts; the clamped leg keeps its own weld. The switch is
tied to the weld state (engage, set_state, reset), so every replay and every restored state reproduces it.
Cut-over (coordinator 2026-10-16): the switch-off is active only from the start of op SW_FROM_OP (sw_cutover.json
or env var, default off; with it off nothing changes). Start of that op = all earlier ops latched and, if SW_FROM_T is
given, sim time >= SW_FROM_T (the recorded step boundary). At that moment every screw already welded switches off,
afterwards each new screw at its latch.
"""
import math
import numpy as np
import mujoco
from ikea_runtime import RetentionMechanism, rotate, qmul, qinv, axis_angle_deg

REGION_LAT = 0.015
REGION_DEG = 15.0
REGION_GAP_MIN = -0.003


def sw_cutover(ops):
    """Cut-over of the seated-screw contact switch-off: (0-based op index or None, sim time or None).
    Env vars SW_FROM_OP (1-based op number or op key) / SW_FROM_T (s) override sw_cutover.json next to this file
    ({"from_op": null, "from_t": null}); unset/null = off, the mechanism then behaves exactly as the original."""
    import json, os
    cfg = {}
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sw_cutover.json')
    if os.path.exists(p):
        cfg = json.load(open(p))
    op = os.environ.get('SW_FROM_OP', cfg.get('from_op')); t = os.environ.get('SW_FROM_T', cfg.get('from_t'))
    if op in (None, '', 'none', 'off'):
        return None, None
    keys = [o['key'] for o in ops]
    i = keys.index(op) if op in keys else int(op) - 1
    assert 0 <= i < len(ops), op
    return i, (None if t in (None, '') else float(t))

class KyrreMechanism(RetentionMechanism):
    def __init__(self, model, data, task, period=4):
        super().__init__(model, data, task, period)
        self._prepare()

    def _prepare(self):
        m = self.m; ops = self.ops; n = len(ops)
        self.key = [o['key'] for o in ops]
        self.part_id = np.array([m.body(o['part']).id for o in ops]); self.host_id = np.array([m.body(o['host']).id for o in ops])
        self.tpos = np.array([o['target_pos'] for o in ops], float)
        assert all(np.allclose(o['target_quat'], [1, 0, 0, 0]) for o in ops)
        self.axis = np.array([o['axis'] for o in ops], float); self.pax = np.array([o['part_axis'] for o in ops], float)
        k = max(len(o['points']) for o in ops)
        self.pts = np.array([o['points'] + [o['points'][-1]] * (k - len(o['points'])) for o in ops], float)
        self.cp = [[m.body(c).id for c in o['counterparts']] for o in ops]
        self.jaw = [[m.jnt_qposadr[m.joint(j).id] for j in o.get('jaws', [])] for o in ops]
        self.mode = [o['mode'] for o in ops]
        self.deps = [[self.key.index(x) for x in o.get('dependencies', []) if x in self.key] for o in ops]
        self.eq_ids = np.array([self.eq[kk] for kk in self.key])
        self._prepare_screw_contacts()

    def _prepare_screw_contacts(self):
        """Per screw operation: its geoms + its hole's insert geoms (switched off once its weld latches)."""
        import re
        m = self.m; names = [m.geom(g).name for g in range(m.ngeom)]
        self.sw_orig = (m.geom_contype.copy(), m.geom_conaffinity.copy())
        self.sw_geoms = {}; self.sw_from, self.sw_from_t = sw_cutover(self.ops); self.sw_active = False
        for i, o in enumerate(self.ops):
            if o['mode'] != 'screw':
                continue
            hb = self.host_id[i]; ins = {}
            for g, n in enumerate(names):
                r = re.match(re.escape(o['host']) + r'_ins(\d+)_(tooth|wall)', n)
                if r and m.geom_bodyid[g] == hb:
                    ins.setdefault(r.group(1), []).append(g)
            dist = {k: float(np.linalg.norm(m.geom_pos[v].mean(0)[:2] - self.tpos[i][:2])) for k, v in ins.items()}
            k = min(dist, key=dist.get)
            assert dist[k] < 0.002, (o['key'], dist)
            own = [g for g in range(m.ngeom) if m.geom_bodyid[g] == self.part_id[i]]
            self.sw_geoms[i] = np.array(own + ins[k])
        self.sync_screw_contacts()

    def sw_check(self):
        """Cut-over reached: all ops before SW_FROM_OP latched and sim time >= SW_FROM_T (if given)."""
        if self.sw_from is None:
            return False
        if self.sw_from_t is not None and self.d.time < self.sw_from_t - 1e-7:
            return False
        return bool(all(self.d.eq_active[self.eq_ids[j]] for j in range(self.sw_from)))

    def sw_poll(self):
        if self.sw_from is not None and not self.sw_active and self.sw_check():
            self.sw_active = True; self.sync_screw_contacts()

    def sync_screw_contacts(self):
        """Screw geoms + hole insert geoms collide unless the cut-over is reached and the screw's weld is on."""
        if not hasattr(self, 'sw_geoms'):
            return
        if self.sw_from is None:
            return
        self.sw_active = self.sw_check()
        ct, ca = self.sw_orig
        for i, g in self.sw_geoms.items():
            on = not (self.sw_active and self.d.eq_active[self.eq_ids[i]])
            self.m.geom_contype[g] = ct[g] if on else 0
            self.m.geom_conaffinity[g] = ca[g] if on else 0

    def engage(self, o):
        super().engage(o)
        self.sync_screw_contacts()

    def reset(self):
        super().reset()
        n = len(self.ops)
        self.maxgap = np.full(n, np.nan); self.turn = np.zeros(n); self.jaw_peak = np.zeros(n)
        self.prev_p = None; self.prev_R = None
        self.sync_screw_contacts()

    def state(self):
        s = super().state()
        s['hist'] = dict(maxgap=self.maxgap.tolist(), turn=self.turn.tolist(), jaw_peak=self.jaw_peak.tolist(),
                         prev_p=None if self.prev_p is None else self.prev_p.tolist(), prev_R=None if self.prev_R is None else self.prev_R.tolist())
        return s

    def set_state(self, s):
        super().set_state(s)
        h = s['hist']
        self.maxgap = np.array(h['maxgap'], float); self.turn = np.array(h['turn']); self.jaw_peak = np.array(h['jaw_peak'])
        self.prev_p = None if h['prev_p'] is None else np.array(h['prev_p']); self.prev_R = None if h['prev_R'] is None else np.array(h['prev_R'])
        self.sync_screw_contacts()

    def geometry_all(self):
        """Source geometry() for every operation: worst connector gap / lateral, part-axis tilt (deg)."""
        d = self.d; X = d.xmat.reshape(-1, 3, 3)
        Rh = X[self.host_id]; Rp = X[self.part_id]; ph = d.xpos[self.host_id]; pp = d.xpos[self.part_id]
        tp = ph + np.einsum('nij,nj->ni', Rh, self.tpos)
        out = np.einsum('nij,nj->ni', Rh, self.axis)
        dl = (pp[:, None] + np.einsum('nij,nkj->nki', Rp, self.pts)) - (tp[:, None] + np.einsum('nij,nkj->nki', Rh, self.pts))
        g = np.einsum('nki,ni->nk', dl, out)
        lat = np.linalg.norm(dl - g[..., None] * out[:, None], axis=2).max(1)
        gap = g[np.arange(len(g)), np.abs(g).argmax(1)]
        ang = np.degrees(np.arccos(np.clip(np.einsum('ni,ni->n', np.einsum('nij,nj->ni', Rp, self.pax), out), -1, 1)))
        return gap, lat, ang, out, pp.copy(), Rp.copy()

    def geometry(self, o):
        gap, lat, ang, out, pp, Rp = self.geometry_all(); i = self.key.index(o['key'])
        return float(gap[i]), float(lat[i]), float(ang[i])

    def counterpart_force(self, i):
        """Source: sum over counterparts of the norm of the net contact force from that counterpart."""
        m, d = self.m, self.d
        ia = self.part_id[i]; tot = {b: np.zeros(3) for b in self.cp[i]}
        f6 = np.zeros(6); gb = self.h.geom_body
        for c_i in range(d.ncon):
            c = d.contact[c_i]; b1, b2 = gb[c.geom1], gb[c.geom2]
            if b1 == ia and b2 in tot: other, sgn = b2, -1.
            elif b2 == ia and b1 in tot: other, sgn = b1, 1.
            else: continue
            mujoco.mj_contactForce(m, d, c_i, f6)
            tot[other] += sgn * (c.frame.reshape(3, 3).T @ f6[:3])
        return float(sum(np.linalg.norm(v) for v in tot.values()))

    def update(self):
        self.sw_poll()
        self._update()
        self.sw_poll()

    def _update(self):
        self.counter += 1
        if self.counter % self.period:
            return
        dt = self.m.opt.timestep * self.period
        active = self.d.eq_active[self.eq_ids].astype(bool)
        if active.all():
            return
        gap, lat, ang, out, pp, Rp = self.geometry_all()
        inside = (lat < REGION_LAT) & (ang < REGION_DEG) & (gap > REGION_GAP_MIN)
        self.maxgap = np.where(inside, np.fmax(self.maxgap, gap), np.nan)
        if self.prev_R is not None:
            Rd = np.einsum('nij,nkj->nik', Rp, self.prev_R)          # R_now R_prev^T
            s = 0.5 * np.stack([Rd[:, 2, 1] - Rd[:, 1, 2], Rd[:, 0, 2] - Rd[:, 2, 0], Rd[:, 1, 0] - Rd[:, 0, 1]], 1)
            c = 0.5 * (np.trace(Rd, axis1=1, axis2=2) - 1)
            dturn = np.arctan2(np.einsum('ni,ni->n', s, -out), c)    # rotation about -axis (tightening, right-hand)
            speed = np.linalg.norm(pp - self.prev_p, axis=1) / dt     # source fd_speed_rule: world-frame position difference
        else:
            dturn = np.zeros(len(gap)); speed = np.full(len(gap), np.inf)
        self.turn = np.where(inside, self.turn + dturn, 0.)
        jaw_now = np.array([max((self.d.qpos[a] for a in j), default=0.) for j in self.jaw])
        self.jaw_peak = np.where(inside, np.maximum(self.jaw_peak, jaw_now), 0.)
        self.prev_p = pp; self.prev_R = Rp
        travel = np.nan_to_num(self.maxgap - gap, nan=0.)
        for i, o in enumerate(self.ops):
            if active[i]:
                continue
            k = self.key[i]; g = o['gates']
            deps_ok = all(active[j] for j in self.deps[i])
            ok = bool(deps_ok and inside[i] and abs(gap[i]) < g['axial_m'] and lat[i] < g['lateral_m'] and ang[i] < g['axis_deg']
                      and travel[i] >= g['min_travel_m'] and speed[i] < g['speed_m_s'])
            if ok and self.mode[i] == 'screw':
                ok = self.turn[i] > math.pi / 2
            if ok and self.mode[i] == 'press':
                ok = self.jaw_peak[i] > 0.00025 and jaw_now[i] < 0.0007
            contact = None
            if ok:
                contact = self.counterpart_force(i); ok = contact > g['min_contact_N']
            self.dwell[k] = self.dwell[k] + dt if ok else 0.
            if inside[i] or self.dwell[k] > 0:
                self.metrics[k] = dict(gap_m=float(gap[i]), lateral_m=float(lat[i]), axis_deg=float(ang[i]), fd_speed_m_s=float(speed[i]),
                                       travel_m=float(travel[i]), turns=float(self.turn[i] / (2 * math.pi)), jaw_peak_m=float(self.jaw_peak[i]),
                                       jaw_m=float(jaw_now[i]), counterpart_contact_N=contact, dependencies_ok=deps_ok, dwell_s=self.dwell[k])
            if self.dwell[k] >= g['dwell_s'] - 1e-9:
                self.engage(o)
