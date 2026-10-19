"""The Booster T1's in-walk kick ("step" style of the platform `kick`, soccer-2v2-8 / soccer-5v5-3).

The real T1 kicks out of its walk: the learned kick of the RoboCup 2025 AdultSize champion "integrated the kicking
motion into the final step of the approach gait" (about 1.5 s from 1.5 m away, the walk included), B-Human's T1 in-walk
kicks hit the ball about 0.2 s into a 0.25 s kick step, and Booster's own demo kick walks through the ball. The swing
kick (swing_kick.py) instead stops, shifts the weight onto one foot and balances there (contact 2.4-2.9 s after the
command). This kick keeps the released walking policy in charge of balance and replaces one swing of the kicking foot:

  approach  the walking policy walks on with the commanded velocity until the kicking foot lifts off (its gait phase)
            with the ball where that foot's swing can reach it (ahead of the support foot by reach_min..reach_max along
            the kick direction, within side_max of the foot's line); at most approach_max_s, else the kick is called
            off (World: kick_cancelled)
  wind      the kicking foot goes back and up to the strike height (n_wind ticks)
  swing     minimum jerk through the strike point (the ball as it lies when the swing is planned; nominal peak foot
            speed from the power, as the swing kick)
  retract   the foot comes back to a short step ahead of the support foot, just above the ground (n_retract)
  then the policy takes the leg again (its gait clock resumes in the kicking foot's late swing, so it puts it down)

While the foot is overridden the policy's gait clock is held in the middle of the kicking foot's swing: the policy keeps
the support leg in stance and balances the body (its own targets for the support leg); the kicking leg runs PD at the
swing kick's gains toward inverse-kinematics targets (foot level, turned to the kick direction). All torques go through
the same motor limits (bodies/servo.py). Reads only the simulator state; deterministic."""
from __future__ import annotations

import math

import numpy as np

import mujoco

import swing_kick as SK

DT = 0.01
GAIT_LIFT = {"right": (0.50, 0.68), "left": (0.00, 0.18)}   # gait phases at which the foot is lifting off
GAIT_HOLD = {"right": 0.72, "left": 0.22}                    # held while the foot is overridden (mid swing)
GAIT_RELEASE = {"right": 0.86, "left": 0.36}                 # resumed here (late swing: the policy lowers the foot)
PARAMS = dict(
    reach_min=0.16, reach_max=0.40,   # the ball's centre ahead of the support foot's site along the kick direction
    side_max=0.08,                    # the swing's line shifted sideways onto the ball by at most this
    back=0.08,                        # wind-up: the foot this far behind the support foot's site
    height=0.07,                      # strike height of the foot site (the swing kick's nominal)
    follow=0.12,                      # the swing ends this far beyond the strike point
    xmax=0.42,                        # ... at most this far ahead of the support foot's site
    land=0.10,                        # the retracted foot: this far ahead of the support foot's site
    land_h=0.035,                     # ... this high (the policy puts it down)
    n_wind=8, n_retract=8,
    release=0.80,                     # the gait phase (right foot; left: - 0.5) at which the policy takes the leg back
    land_out=0.0,
    gain_scale=1.0,                   # the kicking leg's PD gains: the swing kick's, scaled                     # the retracted foot this much farther out than its own line
    approach_max_s=2.0,
    speed_min=2.4, speed_max=4.0,     # nominal peak foot speed of the swing from the power (a slower swing keeps the
                                      # robot on one foot too long: at 1.6 m/s 13/29 fell, at >= 2.8 m/s 0/58)
)


class StepKick:
    """One in-walk kick of one robot. rob: soccer.Robot; geom: World._kick_geometry(); kin: a scratch MjData;
    speed: nominal peak foot speed (m/s); aim_rel: the kick direction relative to the heading (rad); foot."""

    def __init__(self, m, kin, rob, geom, power, aim_rel=0.0, foot="right", params=None):
        self.m, self.kin, self.rob = m, kin, rob
        self.P = dict(PARAMS, **(params or {}))
        self.power = float(power)
        self.speed = self.P["speed_min"] + (self.P["speed_max"] - self.P["speed_min"]) * self.power
        self.aim_rel = float(aim_rel)
        self.foot = foot
        self.sup = "left" if foot == "right" else "right"
        p = rob.name + ":"
        self.site = {"left": m.site(p + "left_foot").id, "right": m.site(p + "right_foot").id}
        self.base = m.body(p + "Trunk").id
        self.legcols = {"left": np.arange(0, 6), "right": np.arange(6, 12)}
        self.sis = np.asarray(geom["strike_in_site"], float)
        self.kp = np.array(SK.GAINS_KP * 2, float) * self.P["gain_scale"]
        self.kd = np.array(SK.GAINS_KD * 2, float) * self.P["gain_scale"]
        idx = [list(m.jnt_qposadr).index(a) for a in rob.jq]
        self.qlo, self.qhi = m.jnt_range[idx, 0].copy(), m.jnt_range[idx, 1].copy()
        self.qlo[[3, 9]] = 0.15
        self.phase_name = "approach"
        self.i = 0
        self.t = 0.0
        self.done = False
        self.cancelled = False
        self.q = None
        self.plan = None
        self.why = None

    # ------------------------------------------------------------------ queries
    def phase(self):
        return self.phase_name

    def overriding(self):
        return self.phase_name in ("wind", "swing", "retract")

    def gait_release(self):
        return self.P["release"] - (0.5 if self.foot == "left" else 0.0)

    def gait_hold(self):
        return GAIT_HOLD[self.foot] if self.overriding() else None

    # ------------------------------------------------------------------ planning
    def _frames(self, d):
        R = d.xmat[self.base].reshape(3, 3)
        yaw = SK.yaw_of_mat(R)
        a = yaw + self.aim_rel
        u = np.array([math.cos(a), math.sin(a), 0.0])
        lat = np.array([-u[1], u[0], 0.0])
        return yaw, u, lat

    def reachable(self, d, ball):
        """the ball (world centre) relative to the support foot: (ahead, side offset from the kicking foot's line, ok)"""
        yaw, u, lat = self._frames(d)
        sup = d.site_xpos[self.site[self.sup]]
        kf = d.site_xpos[self.site[self.foot]]
        Ra = SK.rot_z(yaw + self.aim_rel)
        sp = Ra @ self.sis                                 # the strike point relative to the foot site
        rel = np.asarray(ball, float) - sup
        ahead = float(rel @ u)
        line = float((kf - sup) @ lat) + float(sp @ lat)    # the kicking foot's strike line, sideways from the support
        side = float(rel @ lat) - line
        ok = self.P["reach_min"] <= ahead <= self.P["reach_max"] and abs(side) <= self.P["side_max"]
        return ahead, side, ok

    def _plan(self, d, ball):
        P = self.P
        yaw, u, lat = self._frames(d)
        Ra = SK.rot_z(yaw + self.aim_rel)
        sp = Ra @ self.sis
        sup = d.site_xpos[self.site[self.sup]].copy()
        f0 = d.site_xpos[self.site[self.foot]].copy()
        ground = float(sup[2])
        _, side, _ = self.reachable(d, ball)
        side = float(np.clip(side, -P["side_max"], P["side_max"]))
        line_off = float((f0 - sup) @ lat)                 # the foot's line, sideways from the support foot
        lat_t = line_off + side
        strike = np.asarray(ball, float) - u * (0.11 + 0.03)   # ball radius + the swing kick's gap
        x_strike = float((strike - sp - sup) @ u)
        x_end = min(x_strike + P["follow"], P["xmax"])
        z = ground + P["height"]
        def pt(x, l, zz):
            return sup + u * x + lat * l + np.array([0.0, 0.0, zz - sup[2]])
        self.plan = dict(f0=f0, back=pt(-P["back"], lat_t, z), end=pt(x_end, lat_t, z),
                         land=pt(P["land"], line_off + (-1 if self.foot == "right" else 1) * P["land_out"], ground + P["land_h"]), u=u, Rfoot=Ra,
                         x_strike=x_strike, x_end=x_end)
        dist = x_end + P["back"]
        self.n_sw = max(6, int(round(1.875 * dist / max(self.speed, 0.5) / DT)))

    # ------------------------------------------------------------------ inverse kinematics (the kicking leg only)
    def _ik(self, d, target, Rt, iters=10):
        m, kd, rob = self.m, self.kin, self.rob
        kd.qpos[:] = d.qpos
        q = d.qpos[rob.jq].copy() if self.q is None else self.q.copy()
        c = self.legcols[self.foot]
        sid = self.site[self.foot]
        jp = np.zeros((3, m.nv))
        jr = np.zeros((3, m.nv))
        for _ in range(iters):
            kd.qpos[rob.jq] = q
            mujoco.mj_kinematics(m, kd)
            mujoco.mj_comPos(m, kd)
            p = kd.site_xpos[sid]
            R = kd.site_xmat[sid].reshape(3, 3)
            e = np.r_[target - p, 0.5 * (np.cross(R[:, 0], Rt[:, 0]) + np.cross(R[:, 1], Rt[:, 1]) +
                                         np.cross(R[:, 2], Rt[:, 2]))]
            mujoco.mj_jacSite(m, kd, jp, jr, sid)
            cols = rob.jv[c]
            J = np.vstack([jp[:, cols], jr[:, cols]])
            dq = J.T @ np.linalg.solve(J @ J.T + 1e-3 * np.eye(6), e)
            n = float(np.abs(dq).max())
            if n > 0.15:
                dq *= 0.15 / n
            q[c] = np.clip(q[c] + dq, self.qlo[c], self.qhi[c])
        return q

    # ------------------------------------------------------------------ one tick
    def step(self, d, gait, ball, pol_targets):
        """this tick's leg targets (12) given the policy's targets; None: the policy's own (no override)"""
        P = self.P
        self.t += DT
        if self.phase_name == "approach":
            lo, hi = GAIT_LIFT[self.foot]
            if lo <= gait <= hi or (self.foot == "left" and gait >= 0.98):
                _, _, ok = self.reachable(d, ball)
                if ok:
                    self._plan(d, ball)
                    self.phase_name, self.i = "wind", 0
                    self.q = d.qpos[self.rob.jq].copy()
            if self.phase_name == "approach":
                if self.t >= P["approach_max_s"]:
                    self.done, self.cancelled = True, True
                    self.why = "the ball was not in reach of a step"
                return None
        pl = self.plan
        name = self.phase_name
        n = {"wind": P["n_wind"], "swing": self.n_sw, "retract": P["n_retract"]}[name]
        s = (self.i + 1) / n
        k = SK.minjerk(s)
        if name == "wind":
            tgt = pl["f0"] + (pl["back"] - pl["f0"]) * k
        elif name == "swing":
            tgt = pl["back"] + (pl["end"] - pl["back"]) * k
        else:
            tgt = pl["end"] + (pl["land"] - pl["end"]) * k
        q = self._ik(d, tgt, pl["Rfoot"])
        self.q = q
        out = np.asarray(pol_targets, float).copy()
        c = self.legcols[self.foot]
        out[c] = q[c]
        self.i += 1
        if self.i >= n:
            self.i = 0
            nxt = {"wind": "swing", "swing": "retract", "retract": None}[name]
            if nxt is None:
                self.done = True
                self.phase_name = "over"
            else:
                self.phase_name = nxt
        return out
