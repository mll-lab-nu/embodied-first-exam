"""Authoring helpers (not shipped): wrist/finger IK and recorded motion primitives on a live Session."""

from __future__ import annotations

import mujoco
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

WRIST = list(range(6))
THUMB = list(range(6, 11))
INDEX = list(range(11, 15))
MIDDLE = list(range(15, 19))
RING = list(range(19, 23))
PINKY = list(range(23, 28))


def smooth(u):
    u = np.clip(u, 0.0, 1.0)
    return u * u * (3 - 2 * u)


class Ctl:
    def __init__(self, session, verbose=True):
        self.s = session
        self.m = session.model
        self.scratch = mujoco.MjData(self.m)
        self.rows = []
        self.log = []
        self.verbose = verbose
        self.lo, self.hi = self.m.actuator_ctrlrange.T.copy()
        self.base = np.asarray(session.config["wrist_base"], float)

    # ------------------------------------------------------------------ kinematics
    def fk(self, ctrl):
        d = self.scratch
        d.qpos[:] = self.s.data.qpos
        d.qpos[self.s.qadr] = ctrl
        mujoco.mj_kinematics(self.m, d)
        return d

    def tip(self, d, finger):
        names = getattr(self, "tipnames", None)
        return d.geom(names[finger] if names else f"right_{finger}_fingertip_collision").xpos

    def hand_R(self, d):
        return d.body("right_hand_C_MC").xmat.reshape(3, 3)

    def ik(self, seed, targets, variables, finger_dir=None, palm_dir=None, w_orient=0.3, reg=0.02, fixed=None,
           avoid=()):
        """Least squares on ``variables`` (actuator indices) so fingertips reach ``targets`` {finger: xyz}."""
        q = np.array(seed, float)
        if fixed:
            for k, v in fixed.items():
                q[k] = v
        variables = list(variables)
        lo, hi = self.lo[variables], self.hi[variables]
        x0 = np.clip(q[variables], lo + 1e-6, hi - 1e-6)

        def res(x):
            qq = q.copy()
            qq[variables] = x
            d = self.fk(qq)
            r = []
            for f, t in targets.items():
                r.extend((self.tip(d, f) - t) * 100)
            R = self.hand_R(d)
            if finger_dir is not None:
                r.extend((R[:, 2] - finger_dir) * w_orient)
            if palm_dir is not None:
                r.extend((R[:, 0] - palm_dir) * w_orient)
            for gid, other, margin in avoid:
                dist = mujoco.mj_geomDistance(self.m, d, gid, other, margin + 0.02, None)
                r.append(min(0.0, dist - margin) * 300)
            r.extend((x - x0) * reg)
            return np.asarray(r)

        sol = least_squares(res, x0, bounds=(lo, hi), max_nfev=300, xtol=1e-10, ftol=1e-10)
        q[variables] = sol.x
        d = self.fk(q)
        err = {f: float(np.linalg.norm(self.tip(d, f) - t)) for f, t in targets.items()}
        return q, err

    # ------------------------------------------------------------------ motion
    def step(self, ctrl):
        ctrl = np.clip(ctrl, self.lo, self.hi)
        self.rows.append(ctrl.copy())
        st = self.s.step(ctrl)
        return st

    def go(self, target, n, label=""):
        start = self.s.data.ctrl.copy()
        target = np.clip(np.asarray(target, float), self.lo, self.hi)
        st = None
        for k in range(1, n + 1):
            u = smooth(k / n)
            st = self.step(start + (target - start) * u)
            if self.s.done:
                break
        if self.verbose:
            self.report(label)
        if getattr(self, "snaps", None) is not None and label:
            self.snaps.append((label, self.s.render_frame(self.snap_cam, 480, 360, shadows=False)))
        return st

    def hold(self, n, label=""):
        return self.go(self.s.data.ctrl.copy(), n, label)

    def report(self, label):
        st = self.s.status()
        d = self.s.data
        msg = (f"[{st['steps']:5d}] {label:28s} stage={st['stage']} fail={st['failure']} tog={np.round(st['toggles_rad'],3)} "
               f"thr={st['open_threaded']} lnk={st['linked']} handpg={st['hand_on_pages']} rest={st['pages_resting']} "
               f"cov={st['pages_over_cover']} hb={int(st['hand_on_binder'])} fing={st['page_fingers']} bshift={st['binder_shift_m']:.4f}")
        self.log.append(msg)
        print(msg, flush=True)

    # ------------------------------------------------------------------ frames
    def wrist_pose(self):
        d = self.s.data
        return d.body("wrist_stage").xpos.copy(), d.body("wrist_stage").xmat.reshape(3, 3).copy()

    def wrist_ctrl_for(self, pos, R, ctrl):
        """Wrist targets that put the wrist stage frame at (pos, R); keeps the finger targets of ``ctrl``."""
        q = np.array(ctrl, float)
        q[:3] = pos - self.base
        eul = Rotation.from_matrix(R).as_euler("XYZ")
        # Choose the Euler branch closest to the current targets.
        alt = np.array([eul[0] + np.pi, np.pi - eul[1], eul[2] + np.pi])
        cands = []
        for e in (eul, alt):
            e = np.array(e)
            for k in range(3):
                e[k] = (e[k] - q[3 + k] + np.pi) % (2 * np.pi) - np.pi + q[3 + k]
            cands.append(e)
        e = min(cands, key=lambda e: np.abs(e - q[3:6]).sum())
        q[3:6] = e
        return q
