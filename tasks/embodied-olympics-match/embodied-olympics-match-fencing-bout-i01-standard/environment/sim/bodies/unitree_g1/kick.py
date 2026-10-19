"""The G1's kick: a model-based whole-leg motion (the walking policy cannot kick), run on the legs' PD at the kick
gains (body.toml [kick]) with the motors' torque limits.

  stand    the leg targets go from where the policy left them to the stance (0.25 s), feet down
  shift    the pelvis moves over the support foot (0.55 s); a centre-of-mass loop keeps the CoM over the support
           foot's centre during the whole kick (the support foot stays where it is in the world)
  lift     the kicking foot rises by `height` and winds back 0.15 m (0.25 s)
  swing    the foot travels `reach` beyond the support foot's toe line along the robot's forward axis at `speed`
           (a minimum-jerk profile: its peak speed is about 1.9 x the mean), the instep at ball height
  recover  follow-through, the foot back under the hip and down, the pelvis back between the feet, stand; then the
           walking policy takes the legs again (its memory reset)
Each control step the leg targets come from inverse kinematics of the two feet (position and a level orientation,
the support foot fixed in the world, the kicking foot on its path) relative to the desired pelvis pose. The kick
does not aim: the robot aims by walking and turning before it (the foot moves along its forward axis)."""
from __future__ import annotations

import math

import numpy as np

FOOT_STRIKE_FORWARD = 0.035          # the strike box's centre ahead of the ankle (model.xml)
BACK = -0.10                         # the wind-up: the foot 10 cm behind where it stood
FOLLOW = 0.10                        # with a target: the swing ends this far beyond it
STRIKE_IN_SITE = np.array([0.035, 0.0, -0.02])   # the strike box's centre in the foot site's frame (model.xml)
OUTSIDE = 0.012                      # the balance target this much outside the support foot's centre line (the
                                     # swinging leg pulls the body toward the kicking side)
STAND_MAX = 60                       # the stand waits until both feet are down and still (or this)
LOWER_MAX = 40                       # the lowering goes on until the kicking foot is down (or this)
HOLD_MAX = 60                        # the hold lasts until the capture point is within 1 cm of the target (or this)
CROUCH = 0.05                        # the pelvis goes down this much for the kick (the support knee bent more)
OMEGA = math.sqrt(9.81 / 0.68)       # the linear inverted pendulum's natural frequency at the G1's CoM height


def minjerk(s):
    s = min(max(s, 0.0), 1.0)
    return 10 * s ** 3 - 15 * s ** 4 + 6 * s ** 5


def yaw_of(R):
    return math.atan2(R[1, 0], R[0, 0])


def rot_z(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


class Kick:
    def __init__(self, rig, d, foot="right", speed=3.0, height=0.07, reach=0.22, target=None, direction=None):
        import mujoco as mj
        self.mj, self.rig, self.m = mj, rig, rig.m
        K = rig.B.decl["kick"]
        self.kp, self.kd = np.array(K["gains_kp"] * 2, float), np.array(K["gains_kd"] * 2, float)
        self.kin = mj.MjData(self.m)
        self.foot = foot
        self.sup = "left" if foot == "right" else "right"
        site = lambda n: mj.mj_name2id(self.m, mj.mjtObj.mjOBJ_SITE, rig.prefix + n)
        self.site = {"left": site("left_foot"), "right": site("right_foot")}
        self.legcols = {"left": np.arange(0, 6), "right": np.arange(6, 12)}
        p_pel, R_pel = rig.pelvis(d)
        self.yaw0 = yaw_of(R_pel)
        self.Rlevel = rot_z(self.yaw0)
        self.fw = self.Rlevel[:, 0]
        self.left_ax = self.Rlevel[:, 1]
        self.p0 = p_pel.copy()
        self.feet0 = {s: d.site_xpos[self.site[s]].copy() for s in ("left", "right")}
        self.q_start = d.qpos[rig.lqadr].copy()
        self.q = self.q_start.copy()
        self.com_off = np.zeros(2)
        self.com_fast = np.zeros(2)
        self.hold_extra = 0
        self.stand_extra = 0
        self.lower_extra = 0
        self.speed, self.height, self.reach = float(speed), float(height), float(reach)
        self.target = None if target is None else np.asarray(target, float).copy()
        if direction is not None:                   # the swing's direction (world, horizontal); default: forward
            a = np.array([direction[0], direction[1], 0.0], float)
            self.aim = a / max(np.linalg.norm(a), 1e-9)
        else:
            self.aim = self.fw.copy()
        dist = 0.15 + reach + 0.10                  # the swing's nominal length: its duration (`speed` is the nominal
        n_sw = max(6, int(round(1.875 * dist / max(speed, 0.5) / rig.dt)))      # peak; the real one is about 0.7 x)
        self.phases = [("stand", 40), ("shift", 140), ("hold", 30), ("lift", 30), ("swing", n_sw), ("follow", 10),
                       ("retract", 50), ("lower", 40), ("unshift", 1), ("settle", 1)]
        self.delta = np.zeros(3)
        self.i, self.pi, self.done = 0, 0, False
        self.log = []
        self.ff = np.zeros(12)
        self.ik_err = {"left": 0.0, "right": 0.0}
        idx = [self.m.jnt_qposadr.tolist().index(a) for a in rig.lqadr]
        self.qlo, self.qhi = self.m.jnt_range[idx, 0].copy(), self.m.jnt_range[idx, 1].copy()
        self.qlo[[3, 9]] = 0.15                       # the knees stay bent (no straight-leg singularity)
        self.qpel0 = np.array([math.cos(self.yaw0 / 2), 0.0, 0.0, math.sin(self.yaw0 / 2)])

    # ------------------------------------------------------------------ targets
    def _phase(self):
        name, n = self.phases[self.pi]
        return name, n, self.i / n

    def _pelvis_target(self, name, s):
        """The pelvis moves by `delta` (the vector that puts the centre of mass over the support foot's centre,
        measured when the shift starts), plus the balance correction while on one foot."""
        if name in ("stand", "settle"):
            k = 0.0
        elif name == "shift":
            k = minjerk(s)
        elif name == "unshift":
            k = 1.0 - minjerk(s)
        else:
            k = 1.0
        off = self.com_off + self.com_fast
        corr = self.fw * off[0] + self.left_ax * off[1]
        return self.p0 + self.delta * k + corr

    def _path(self):
        """The kicking foot's path (foot site, world), set when the stance is reached, along `aim` from where the foot
        stood: wound back 10 cm and lifted to the strike height, then swung forward to its end point, back above
        where it stood and down. Without a target the end point is `reach` beyond the support foot's toe line at
        `height`; with one (where the strike box's centre should meet the ball) the end is 10 cm beyond it, the
        height is the target's and the path is shifted sideways onto it (each within the leg's reach: at most 8 cm
        sideways, 3-12 cm up, 5-32 cm beyond the toe line)."""
        f0, sup = self.feet0[self.foot], self.feet0[self.sup]
        aim = self.aim
        lat = np.array([-aim[1], aim[0], 0.0])
        toe = float((sup - f0) @ aim)
        if self.target is None:
            x_end, side, h = toe + self.reach, 0.0, self.height
        else:
            rel = self.target - self.Rlevel @ STRIKE_IN_SITE - f0
            x_end, side, h = float(rel @ aim) + FOLLOW, float(rel @ lat), float(rel[2])
        x_end = float(np.clip(x_end, toe + 0.05, toe + 0.32))
        side = float(np.clip(side, -0.08, 0.08))
        h = float(np.clip(h, 0.03, 0.12))
        self.x_back, self.x_end, self.side, self.h = BACK, x_end, side, h

    def _at(self, x, z, side_k=1.0):
        f0 = self.feet0[self.foot]
        lat = np.array([-self.aim[1], self.aim[0], 0.0])
        return f0 + self.aim * x + lat * (self.side * side_k) + np.array([0.0, 0.0, z])

    def _kick_foot_target(self, name, s):
        f0 = self.feet0[self.foot]
        if name in ("stand", "shift", "settle", "unshift"):
            return f0.copy()
        if not hasattr(self, "x_end"):
            self._path()
        k = minjerk(s)
        if name == "lift":                          # wound back and up (and over onto the strike line)
            return self._at(self.x_back * k, self.h * k, k)
        if name == "swing":                         # forward through the strike point
            return self._at(self.x_back + (self.x_end - self.x_back) * k, self.h)
        if name == "follow":
            return self._at(self.x_end + 0.02, self.h)
        if name == "retract":                       # back above where it stood, at the strike height (clear of a ball)
            return self._at((self.x_end + 0.02) * (1 - k), self.h + 0.02 * math.sin(math.pi * k), 1 - k)
        if name == "lower":                         # down to 1 cm below where it stood (a firm landing)
            return f0 + np.array([0, 0, self.h - (self.h + 0.01) * k])
        return f0.copy()

    # ------------------------------------------------------------------ inverse kinematics of the feet
    def _ik(self, d, p_pel, foot_targets, iters=10):
        mj, m, kd, rig = self.mj, self.m, self.kin, self.rig
        kd.qpos[:] = d.qpos
        j = rig.fqadr
        kd.qpos[j:j + 3] = p_pel
        kd.qpos[j + 3:j + 7] = self.qpel0
        q = self.q.copy()
        jp = np.zeros((3, m.nv)); jr = np.zeros((3, m.nv))
        for _ in range(iters):
            kd.qpos[rig.lqadr] = q
            mj.mj_kinematics(m, kd)
            mj.mj_comPos(m, kd)
            for side in ("left", "right"):
                sid = self.site[side]
                p = kd.site_xpos[sid]
                R = kd.site_xmat[sid].reshape(3, 3)
                e = np.r_[foot_targets[side] - p, 0.5 * (np.cross(R[:, 0], self.Rlevel[:, 0]) +
                                                         np.cross(R[:, 1], self.Rlevel[:, 1]) +
                                                         np.cross(R[:, 2], self.Rlevel[:, 2]))]
                mj.mj_jacSite(m, kd, jp, jr, sid)
                cols = rig.lvadr[self.legcols[side]]
                J = np.vstack([jp[:, cols], jr[:, cols]])
                dq = J.T @ np.linalg.solve(J @ J.T + 1e-3 * np.eye(6), e)
                n = np.abs(dq).max()
                if n > 0.15:                          # small steps: stay on the bent-knee branch
                    dq *= 0.15 / n
                c = self.legcols[side]
                q[c] = np.clip(q[c] + dq, self.qlo[c], self.qhi[c])
                self.ik_err[side] = float(np.linalg.norm(e[:3]))
        return q

    def _nominal_pelvis(self, d, q_legs):
        """The level pelvis position that the leg angles q_legs put above the feet where they stand."""
        mj, m, kd, rig = self.mj, self.m, self.kin, self.rig
        kd.qpos[:] = d.qpos
        j = rig.fqadr
        kd.qpos[j:j + 3] = 0.0
        kd.qpos[j + 3:j + 7] = (math.cos(self.yaw0 / 2), 0.0, 0.0, math.sin(self.yaw0 / 2))
        kd.qpos[rig.lqadr] = q_legs
        mj.mj_kinematics(m, kd)
        off = [self.feet0[sd] - kd.site_xpos[self.site[sd]] for sd in ("left", "right")]
        return 0.5 * (off[0] + off[1])

    def _balance_target(self, d=None):
        """The support foot's centre (where it is now: it may slip or turn under a hard swing), a little outside."""
        out = self.left_ax * (OUTSIDE if self.sup == "left" else -OUTSIDE)
        p = self.feet0[self.sup] if d is None else d.site_xpos[self.site[self.sup]]
        return p + self.fw * FOOT_STRIKE_FORWARD + out

    def _site_vel(self, d, side):
        v = np.zeros(6)
        self.mj.mj_objectVelocity(self.m, d, self.mj.mjtObj.mjOBJ_SITE, self.site[side], v, 0)
        return v[3:]

    def _com_vel(self, d, com):
        prev = getattr(self, "_com_prev", None)
        self._com_prev = com.copy()
        return np.zeros(3) if prev is None else (com - prev) / self.rig.dt

    def _support_ff(self, d, name):
        """Leg torques that carry the robot's weight (static equilibrium with the feet's contact forces): tau =
        bias - J_c^T F, the weight split between the feet by where the centre of mass is (all of it on the support
        foot while the other is off the ground). Without it the stance legs sag under the PD and the kick drifts."""
        mj, m, rig = self.mj, self.m, self.rig
        com = d.subtree_com[rig.base_body].copy()
        W = float(m.body_subtreemass[rig.base_body]) * 9.81
        one_foot = name in ("lift", "swing", "follow", "retract")
        if one_foot:
            share = {self.sup: 1.0, self.foot: 0.0}
        else:
            pl, pr = d.site_xpos[self.site["left"]], d.site_xpos[self.site["right"]]
            ax = pl[:2] - pr[:2]
            t = float(np.clip((com[:2] - pr[:2]) @ ax / max(ax @ ax, 1e-9), 0.0, 1.0))
            share = {"left": t, "right": 1.0 - t}
        gen = np.zeros(m.nv)
        jp = np.zeros((3, m.nv)); jr = np.zeros((3, m.nv))
        for side, w in share.items():
            if w <= 0:
                continue
            p = d.site_xpos[self.site[side]]
            F = np.array([0.0, 0.0, w * W])
            r = np.array([com[0] - p[0], com[1] - p[1], 0.0])
            mj.mj_jacSite(m, d, jp, jr, self.site[side])
            gen += jp.T @ F + jr.T @ np.cross(r, F)
        return d.qfrc_bias[rig.lvadr] - gen[rig.lvadr]

    # ------------------------------------------------------------------ one control step
    def step(self, d):
        name, n, s = self._phase()
        rig = self.rig
        if name == "stand":
            k = minjerk(s)
            stand = rig.policy.default
            self.q = self.q_start + (stand - self.q_start) * k
            q = self.q
            if self.i == n - 1 and self.stand_extra < STAND_MAX:
                z = [d.site_xpos[self.site[sd]][2] for sd in ("left", "right")]
                vz = [np.linalg.norm(self._site_vel(d, sd)) for sd in ("left", "right")]
                if abs(z[0] - z[1]) > 0.006 or max(vz) > 0.05:  # a foot still in the air or moving: wait
                    self.stand_extra += 1
                    self.ff = self._support_ff(d, name)
                    return q.copy()                   # (the step counter stays)
            if self.i == n - 1:                       # the stance reached: the feet as they are now, the pelvis
                self.feet0 = {sd: d.site_xpos[self.site[sd]].copy() for sd in ("left", "right")}
                p_now, R_now = rig.pelvis(d)              # the pelvis as it stands (the support torques hold it
                self.p0 = p_now.copy()                    # there: no sag, no creeping); its tilt is kept
                self.qpel0 = np.zeros(4)
                self.mj.mju_mat2Quat(self.qpel0, R_now.reshape(-1))
                c = self._balance_target()
                dl = c - d.subtree_com[rig.base_body]
                self.delta = np.array([dl[0], dl[1], -CROUCH])     # and a little lower: room for the support leg
                mid = 0.5 * (self.feet0["left"] + self.feet0["right"]) + self.fw * FOOT_STRIKE_FORWARD
                self.com_start = np.r_[mid[:2], 0.0]       # the shift starts from the middle of the feet
        else:
            if name == "unshift" and self.i == 0:     # both feet down again: where the kicking foot landed
                self.feet0[self.foot] = d.site_xpos[self.site[self.foot]].copy()
                self.mid_end = 0.5 * (self.feet0["left"] + self.feet0["right"]) + self.fw * FOOT_STRIKE_FORWARD
            if True:                                  # balance: the capture point (CoM + v / omega) onto its
                com = d.subtree_com[rig.base_body]        # target (the support foot's centre; on the way there during
                v = self._com_vel(d, com)                 # the shifts), the pelvis moved by the error
                bt = self._balance_target(d)
                if name == "shift":
                    c = self.com_start + (bt - self.com_start) * minjerk(s)
                elif name == "unshift":
                    c = bt + (self.mid_end - bt) * minjerk(s)
                elif name == "settle":
                    c = self.mid_end
                else:
                    c = bt
                xi = com[:2] + v[:2] / OMEGA
                err = c[:2] - xi
                e_loc = np.array([err @ self.fw[:2], err @ self.left_ax[:2]])
                self.com_off = np.clip(self.com_off + 0.05 * e_loc, -0.08, 0.08)   # slow integral of the error
                self.com_fast = np.clip(1.3 * e_loc, -0.06, 0.06)                     # plus a direct term
                if name == "lower" and self.i == n - 1 and self.lower_extra < LOWER_MAX and \
                        d.site_xpos[self.site[self.foot]][2] > self.feet0[self.foot][2] + 0.01:
                    self.lower_extra += 1                 # the foot not down yet: keep lowering
                    self.i -= 1
                if name == "hold" and self.i == n - 1 and np.linalg.norm(e_loc) > 0.01 and self.hold_extra < HOLD_MAX:
                    self.hold_extra += 1                  # not settled yet: hold on
                    self.i -= 1
            p_pel = self._pelvis_target(name, s)
            feet = {self.sup: self.feet0[self.sup], self.foot: self._kick_foot_target(name, s)}
            self.q = self._ik(d, p_pel, feet)
            q = self.q
        self.ff = self._support_ff(d, name)
        self.i += 1
        if self.i >= n:
            self.i = 0
            self.pi += 1
            if self.pi >= len(self.phases):
                self.done = True
        return q.copy()
