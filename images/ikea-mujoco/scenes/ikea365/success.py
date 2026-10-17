"""IKEA365 success criteria (used through scene.load().success()).

Port of the source grader: the endpoint report and the strict support report must both pass,
plus the source's chronological requirement (all seven operations accepted in order, mechanism.py).

endpoint (gates f27_math.GATES: axial 0.1 mm, lateral 0.6 mm, axis 1.5 deg, speed 0.02 m/s):
  * screw: retention joint member_a<->same_screw engaged AND screw aligned (threaded: axis tilt)
    with its seated pose relative to member_a AND relative to member_b ('through')
  * structure: retention joint member_a<->member_b engaged AND member_b aligned with member_a
    (full orientation; member_b is 180-deg yaw symmetric, both yaw solutions accepted)
  * released: no robot contact with any part (source: no world fixture enabled)
  * settled: every part speed < 0.025 m/s
  * bench reaction on the parts (z) > 0
  * bowl: contact force with member_a + member_b > 0.1 N AND member_a turned (its z axis . world z < -0.95)
strict support (source strict_support_report on a 480-sample/2 s support test): the bench must carry
  the whole weight in a gravity window (0.75-1.0 s) and weight + a 2 N downward test load applied
  to member_a in a loaded window (1.75-2.0 s), signed reaction and momentum balance within
  max(0.05 N, 2 %). The grader runs this probe itself on a copy of the current state (state is
  restored afterwards), with the arms holding their current commands. The 2 N test load is a
  grader-applied force (xfrc_applied), as in the source; it never acts during an episode.
"""
import numpy as np
import mujoco
from ikea_runtime import rotate, qmul, qinv, quat_angle_deg, axis_angle_deg

Z_YAW180 = np.array([0., 0., 0., 1.])


class Monitor:
    def __init__(self, model, data, task, scene=None):
        self.m, self.d, self.t, self.scene = model, data, task, scene
        self.g = task['gates']
        self.parts = list(task['parts'])
        self.bid = {n: model.body(n).id for n in self.parts}
        self.robot = np.array([i for i in range(model.nbody) if model.body(i).name.startswith(('left_', 'right_'))])
        self.bench = model.geom('bench').id
        self.mass = {n: float(model.body_subtreemass[self.bid[n]]) for n in self.parts}
        a = task['assembled_in_member_a_frame']
        self.screw_rel = np.array(a['same_screw']); self.b_rel = np.array(a['member_b'])

    def reset(self): pass
    def update(self): pass
    def state(self): return {}
    def set_state(self, s): pass

    # ------------------------------------------------------------------ helpers
    def _pose(self, n):
        b = self.bid[n]; return self.d.xpos[b].copy(), self.d.xquat[b].copy()

    def _vel(self, n):
        v = np.zeros(6); mujoco.mj_objectVelocity(self.m, self.d, mujoco.mjtObj.mjOBJ_BODY, self.bid[n], v, 0)
        return v[3:]

    def _aligned(self, key, host, rel, threaded):
        ph, qh = self._pose(host); pk, qk = self._pose(key)
        axis = rotate(qh, [0, 0, 1]); target = ph + rotate(qh, rel)
        delta = pk - target; gap = float(delta @ axis); lat = float(np.linalg.norm(delta - gap * axis))
        if threaded:
            tilt = axis_angle_deg(rotate(qk, [0, 0, 1]), axis)
        else:
            qr = qmul(qinv(qh), qk); tilt = min(quat_angle_deg(qr, [1, 0, 0, 0]), quat_angle_deg(qr, Z_YAW180))
        speed = float(np.linalg.norm(self._vel(key)))
        ok = abs(gap) < self.g['axial_m'] and lat < self.g['lateral_m'] and tilt < self.g['axis_deg'] and speed < self.g['speed_m_s']
        return dict(gap_m=gap, lateral_m=lat, angle_deg=tilt, speed_m_s=speed, passed=bool(ok))

    def _contacts(self):
        n = self.d.ncon; c = self.d.contact
        return c.geom1[:n], c.geom2[:n], self.m.geom_bodyid[c.geom1[:n]], self.m.geom_bodyid[c.geom2[:n]]

    def bench_force(self):
        """Net contact force (world) exerted by the bench on all task parts."""
        g1, g2, b1, b2 = self._contacts(); total = np.zeros(3); f6 = np.zeros(6)
        ids = set(self.bid.values())
        for i in range(len(g1)):
            if g1[i] == self.bench and b2[i] in ids: s = 1.        # force on geom2 (part) from geom1 (bench)
            elif g2[i] == self.bench and b1[i] in ids: s = -1.
            else: continue
            mujoco.mj_contactForce(self.m, self.d, i, f6)
            total += s * (self.d.contact[i].frame.reshape(3, 3).T @ f6[:3])
        return total

    def pair_force(self, a, others):
        g1, g2, b1, b2 = self._contacts(); ia = self.bid[a]; ib = [self.bid[o] for o in others]
        sel = ((b1 == ia) & np.isin(b2, ib)) | ((b2 == ia) & np.isin(b1, ib))
        adr = self.d.contact.efc_address[:len(g1)][sel]
        return float(np.abs(self.d.efc_force[adr[adr >= 0]]).sum())

    def robot_touch(self):
        g1, g2, b1, b2 = self._contacts(); ids = list(self.bid.values())
        return bool(np.any((np.isin(b1, self.robot) & np.isin(b2, ids)) | (np.isin(b2, self.robot) & np.isin(b1, ids))))

    # ------------------------------------------------------------------ endpoint
    def endpoint(self):
        mech = self.scene.mech if self.scene is not None else None
        ret = mech.retained() if mech is not None else [False, False]
        rep = dict(failures=[])
        sa = self._aligned('same_screw', 'member_a', self.screw_rel, True)
        sb = self._aligned('same_screw', 'member_b', self.screw_rel, True)
        hw = bool(ret[0] and sa['passed'] and sb['passed'])
        if not hw: rep['failures'].append('unseated_screw:same_screw')
        st = self._aligned('member_b', 'member_a', self.b_rel, False)
        structure = bool(ret[1] and st['passed'])
        if not structure: rep['failures'].append('structure_not_connected:member_a-member_b')
        released = not self.robot_touch()
        if not released: rep['failures'].append('robot_still_touching_parts')
        settled = all(float(np.linalg.norm(self._vel(n))) < self.g['settled_speed_m_s'] for n in self.parts)
        bench = float(self.bench_force()[2])
        up = float(rotate(self._pose('member_a')[1], [0, 0, 1])[2])
        bowl_f = self.pair_force('bowl', ['member_a', 'member_b'])
        bowl_ok = bowl_f > self.g['bowl_contact_N'] and up < self.g['bowl_up_z']
        rep.update(screw_vs_member_a=sa, screw_vs_member_b=sb, member_b_vs_member_a=st,
                   retention_screw=bool(ret[0]), retention_members=bool(ret[1]),
                   hardware_fraction=float(hw), structure_fraction=float(structure), released=released, settled=bool(settled),
                   bench_signed_N=bench, member_a_up_z=up, bowl_contact_N=bowl_f, bowl_supported=bool(bowl_ok))
        rep['success'] = bool(hw and structure and released and settled and bench > 0 and bowl_ok)
        if not rep['success'] and not rep['failures']: rep['failures'].append('endpoint_not_supported_or_aligned')
        return rep

    # ------------------------------------------------------------------ strict support probe
    def support_probe(self, seconds=2.0):
        """Source strict_support_report on a fresh 2 s test from the current state; state restored afterwards."""
        S = self.scene; m, d = self.m, self.d
        saved = S.get_state(); ctrl = d.ctrl.copy(); xfrc = d.xfrc_applied.copy()
        dt = m.opt.timestep; n = int(round(seconds / dt)); half = n // 2; win = int(round(0.25 / dt))
        root = self.bid[self.t['root']]; load = self.g['support_test_load_N']
        masses = np.array([self.mass[k] for k in self.parts])
        rows = []
        try:
            for i in range(n):
                d.ctrl[:] = ctrl
                d.xfrc_applied[:] = xfrc
                if i >= half: d.xfrc_applied[root, 2] -= load
                S.step()
                if (half - win) <= i < half or (n - win) <= i < n:
                    mom = sum(masses[j] * self._vel(k) for j, k in enumerate(self.parts))
                    rows.append((i, self.bench_force(), mom, self.robot_touch()))
        finally:
            d.xfrc_applied[:] = xfrc
            S.set_state(saved); d.ctrl[:] = ctrl
            mujoco.mj_forward(m, d)
        windows = []
        for phase, lo, hi, extra in (('gravity', half - win, half, 0.), ('loaded', n - win, n, load)):
            sel = [r for r in rows if lo <= r[0] < hi]
            reaction = np.mean([r[1] for r in sel], axis=0)
            dpdt = (sel[-1][2] - sel[0][2]) / ((len(sel) - 1) * dt)
            expected = float(masses.sum() * 9.81 + extra)
            residual = reaction + np.array([0, 0, -expected]) - dpdt
            tol = max(self.g['support_tol_abs_N'], self.g['support_tol_rel'] * expected)
            touched = any(r[3] for r in sel)
            windows.append(dict(phase=phase, measured_N=float(reaction[2]), expected_N=expected, momentum_derivative_N=dpdt.tolist(),
                                residual_N=residual.tolist(), tolerance_N=tol, robot_touch=touched,
                                verified=bool(abs(reaction[2] - expected) < tol and np.linalg.norm(residual) < tol and not touched)))
        return dict(verified=all(w['verified'] for w in windows), windows=windows, test_load_N=load)

    def report(self, run_support_probe=True):
        rep = self.endpoint()
        mech = self.scene.mech if self.scene is not None else None
        rep['operations_accepted'] = mech.accepted() if mech is not None else []
        rep['operation_events'] = [dict(key=k, t=t, metrics=me) for k, t, me in (mech.events if mech is not None else [])]
        rep['all_operations_accepted'] = bool(mech is not None and mech.complete)
        rep['next_operation'] = None if mech is None or mech.complete else mech.ops[mech.next]
        if rep['success'] and rep['all_operations_accepted'] and run_support_probe:
            rep['strict_support'] = self.support_probe()
        else:
            rep['strict_support'] = dict(verified=False, reason='not run: endpoint or chronology not satisfied')
        rep['success'] = bool(rep['success'] and rep['all_operations_accepted'] and rep['strict_support']['verified'])
        return rep
