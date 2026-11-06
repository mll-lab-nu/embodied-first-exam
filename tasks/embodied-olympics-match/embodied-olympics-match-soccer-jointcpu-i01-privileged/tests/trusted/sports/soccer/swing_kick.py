"""The Booster T1's swing-leg kick: the platform `kick` skill of robot soccer (soccer.World, kick style "swing").

The released T1 walking policy cannot kick (it only walks), so for the kick the legs leave the policy: every 10 ms
this model-based controller computes both legs' joint targets and a support feed-forward, and the legs run PD at the
kick gains plus that feed-forward, through the same motor limits as walking (bodies/booster_t1: torque and the
torque-speed envelope). When the kick is over (the stability check passed or timed out), the walking policy takes the
legs again with its memory reset to the standing state.

Origin: the Unitree G1 two-mode pilot's kick (pilot-g1-modes bodies/unitree_g1/kick.py, 003aa97e), ported to the T1
in the B9 study (b9-dynamic prototypes/b9_soccer/kick_proto.py + g1kick.py: 28/30 shots past a goalkeeper with a
0.30 s reaction and 0.74 m/s sideways speed under the real limits). The logic of the stance, shift, swing and landing
is the G1 kick's; the body constants are the T1's (computed from the model, World._kick_geometry), the swing's
wind-up, follow-through and reach are the B9 study's values. New for the platform skill (soccer-2v2-4; the checks in
b9-dynamic prototypes/soccer_t1_check/): the shift starts from where the CoM is, the kicking foot lands at ground
level until it is down, the kicking foot turns to the kick direction (aim), and the end: instead of the prototype's
one-step return between the feet and an immediate hand-back (42 % falls in the 2 s after the kick), a joint-space
return to the walking policy's own standing targets and a stability check; World then lets the policy step in place.

Phases (10 ms ticks; PARAMS n_*; some wait for a condition, at most `+extra`):
  stand    0.40 s (+0.60)  the leg targets go from where the policy left them to the standing pose, until both feet
                            are down and still
  shift    1.10 s          the pelvis (and the centre of mass) moves over the support (left) foot, 4 cm lower
  hold     0.30 s (+0.60)  until the capture point is within 1 cm of the support foot's centre
  lift     0.30 s          the kicking (right) foot rises to the strike height, winds back 10 cm and turns to the aim
  wait     (timed kick only) the foot stays wound up until the swing must start for the strike point to pass the
                            given target at the given time (t_strike); none when it is already late (`late`)
  swing    ~0.1-0.4 s       the foot travels along the kick direction through the strike point (minimum jerk; the
                            nominal peak foot speed from the power)
  follow   0.10 s, retract 0.40 s, lower 0.30 s (+0.40, until the foot is down)
  restore  0.40 s          joint space: from the last targets to the walking policy's standing targets (end_q)
  steady   0.10 s (+0.30)  the stability check: both feet down, the CoM slow and over the feet, the trunk's rotation
                            slow; then done (also when the limit is reached)
A balance loop runs from the shift to the landing: the capture point (CoM + v / omega) onto its target, the pelvis
moved by the error. Each tick the leg targets come from inverse kinematics of the two feet (position and orientation;
the support foot fixed in the world, the kicking foot on its path) relative to the desired pelvis.
Timed kick (t_strike, soccer-2v2-7): the target and the time come from the command (the player's prediction of where
the ball's centre will be and when); the motion reads only the robot's own state, never the ball. retime() moves the
target and the time while the swing has not started (the player refines its prediction).
Deterministic: it reads only the simulator state (and its own MjData for the kinematics)."""
from __future__ import annotations

import math

import numpy as np

import mujoco

DT = 0.01                                   # the kick's tick: every 5 physics steps of 2 ms
GAINS_KP = [700.0, 700.0, 500.0, 900.0, 300.0, 300.0]   # per leg joint (hip pitch, roll, yaw, knee, ankle pitch, roll)
GAINS_KD = [12.0, 12.0, 8.0, 15.0, 6.0, 6.0]            # the G1 kick's gains (the Booster SDK takes any PD gains)
PARAMS = dict(
    back=0.10,              # wind-up: the foot this far behind where it stood
    follow=0.20,            # with a target: the swing ends this far beyond it
    xmax=0.32,              # the swing's end at most this far beyond the support foot's toe line (min 0.05)
    side_max=0.08,          # the path shifted sideways onto the target by at most this
    h_min=0.03, h_max=0.12,  # the strike height (foot site) within these
    height=0.07, reach=0.22,  # without a target
    crouch=0.04,            # the pelvis goes down this much for the kick
    outside=0.012,          # the balance target this much outside the support foot's centre line
    # phase lengths (10 ms ticks) and the waits' limits
    n_stand=40, n_shift=110, n_hold=30, n_lift=30, n_follow=10, n_retract=40, n_lower=30, n_unshift=0,
    n_restore=40, n_steady=10,
    stand_max=60, hold_max=60, lower_max=40, steady_max=30,
    stand_v=9.0,            # the stance also waits for the CoM to move slower than this (m/s; 9: no wait)
    steady_v=0.12, steady_off=0.05, steady_w=0.8,   # the stability check: CoM speed, CoM offset, trunk rotation
    decay_back=True,        # (unshift) the balance loop's slow term fades back between the feet
    turn_foot=True,         # the kicking foot turns to the kick's direction for the swing (with an aim)
    follow_support=False,   # targets follow the support foot's planar slip
    keep_crouch=True,       # (unshift, steady with IK) the pelvis stays down to the end
    com_from_actual=True,   # the shift's CoM path starts at the CoM (G1: at the feet's centre)
    land_depth=0.0,         # the kicking foot lands this far below where it stood (G1: 0.01)
    land_tol=0.005,         # the lowering goes on until the foot is this close to where it stood
    unshift_ground=True,    # (unshift) back between the feet with the kicking foot held at ground level
)


def minjerk(s):
    s = min(max(s, 0.0), 1.0)
    return 10 * s ** 3 - 15 * s ** 4 + 6 * s ** 5


def yaw_of_mat(R):
    return math.atan2(R[1, 0], R[0, 0])


def rot_z(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


class SwingKick:
    """One kick of one robot. rob: soccer.Robot (prefix, joint and DOF addresses); geom: World._kick_geometry() (omega,
    foot_strike_forward, strike_in_site); kin: an MjData of the same model for the kinematics (shared, overwritten);
    stand_q: the policy's standing joint targets; speed: the swing's nominal peak foot speed (m/s); target: where the
    foot's strike point should meet the ball (world); direction: the swing's horizontal direction (world)."""

    def __init__(self, m, d, kin, rob, geom, stand_q, speed, target=None, direction=None, params=None,
                 foot="right", end_q=None, t_strike=None):
        self.m, self.kin, self.rob = m, kin, rob
        self.P = dict(PARAMS, **(params or {}))
        self.omega = float(geom["omega"])
        self.fsf = float(geom["foot_strike_forward"])
        self.sis = np.asarray(geom["strike_in_site"], float)
        self.kp = np.array(GAINS_KP * 2, float)
        self.kd = np.array(GAINS_KD * 2, float)
        self.stand_q = np.asarray(stand_q, float)
        self.end_q = None if end_q is None else np.asarray(end_q, float)   # the walking policy's standing targets
        self.foot = foot
        self.sup = "left" if foot == "right" else "right"
        p = rob.name + ":"
        self.site = {"left": m.site(p + "left_foot").id, "right": m.site(p + "right_foot").id}
        self.base = m.body(p + "Trunk").id
        self.legcols = {"left": np.arange(0, 6), "right": np.arange(6, 12)}
        R_pel = d.xmat[self.base].reshape(3, 3)
        self.yaw0 = yaw_of_mat(R_pel)
        self.Rlevel = rot_z(self.yaw0)
        self.fw = self.Rlevel[:, 0].copy()
        self.left_ax = self.Rlevel[:, 1].copy()
        self.p0 = d.xpos[self.base].copy()
        self.feet0 = {s: d.site_xpos[self.site[s]].copy() for s in ("left", "right")}
        self.q_start = d.qpos[rob.jq].astype(float).copy()
        self.q = self.q_start.copy()
        self.com_off = np.zeros(2)
        self.com_fast = np.zeros(2)
        self.extra = dict(stand=0, hold=0, lower=0, steady=0)
        self.speed = float(speed)
        self.target = None if target is None else np.asarray(target, float).copy()
        if direction is not None:
            a = np.array([direction[0], direction[1], 0.0], float)
            self.aim = a / max(float(np.linalg.norm(a)), 1e-9)
        else:
            self.aim = self.fw.copy()
        # the kick's direction relative to the heading; the kicking foot turns to it for the swing (its instep faces
        # the direction of the kick) when PARAMS turn_foot
        self.aim_rel = math.atan2(float(np.cross(self.fw, self.aim)[2]), float(self.fw @ self.aim))
        self.Raim = rot_z(self.yaw0 + self.aim_rel) if self.P["turn_foot"] else self.Rlevel
        self.foot_turn = 0.0                         # 0..1: how far the kicking foot is turned to the kick direction
        P = self.P
        dist = 0.15 + P["reach"] + 0.10                        # the swing's nominal length (the G1 kick's)
        n_sw = max(6, int(round(1.875 * dist / max(self.speed, 0.5) / DT)))
        # the timed kick (t_strike: seconds after the start at which the strike point passes the target): the foot
        # waits wound up between the lift and the swing ("wait", re-entered every tick until the swing must start)
        self.t_strike = None if t_strike is None else float(t_strike)
        self.t = 0.0                                 # seconds since the start (one tick = DT)
        self.late = None                             # timed: how much later than t_strike the strike point passes
        self.phases = [("stand", P["n_stand"]), ("shift", P["n_shift"]), ("hold", P["n_hold"]),
                       ("lift", P["n_lift"])] + ([("wait", 1)] if self.t_strike is not None else []) + [
                       ("swing", n_sw), ("follow", P["n_follow"]),
                       ("retract", P["n_retract"]), ("lower", P["n_lower"])]
        if P["n_unshift"] > 0:
            self.phases.append(("unshift", P["n_unshift"]))
        if P["n_restore"] > 0 and self.end_q is not None:
            self.phases.append(("restore", P["n_restore"]))
        self.phases.append(("steady", P["n_steady"]))
        self.delta = np.zeros(3)
        self.i, self.pi, self.done = 0, 0, False
        self.ff = np.zeros(12)
        self.ik_err = {"left": 0.0, "right": 0.0}
        idx = [list(m.jnt_qposadr).index(a) for a in rob.jq]
        self.qlo, self.qhi = m.jnt_range[idx, 0].copy(), m.jnt_range[idx, 1].copy()
        self.qlo[[3, 9]] = 0.15                     # the knees stay bent (no straight-leg singularity)
        self.qpel0 = np.array([math.cos(self.yaw0 / 2), 0.0, 0.0, math.sin(self.yaw0 / 2)])
        self.mid_end = None
        self.stance_com_f = None
        self._com_prev = None
        self.steady_ok = False
        self.steady_info = None
        self.restored = False
        self.stance_info = None

    # ------------------------------------------------------------------ queries
    def phase(self) -> str:
        return self.phases[min(self.pi, len(self.phases) - 1)][0]

    def remaining_s(self) -> float:
        """nominal time left (s), without the waits"""
        if self.done:
            return 0.0
        n = self.phases[self.pi][1] - self.i + sum(n for _, n in self.phases[self.pi + 1:])
        return n * DT

    def swing_to_strike_s(self) -> float:
        """timed kick: seconds from the start of the swing until the strike point passes the target"""
        if not hasattr(self, "x_end"):
            self._path()
        n_sw = next(n for nm, n in self.phases if nm == "swing")
        y = (self.x_strike - self.x_back) / max(self.x_end - self.x_back, 1e-6)
        lo, hi = 0.0, 1.0
        for _ in range(40):                          # minjerk is monotonic on [0, 1]
            mid = 0.5 * (lo + hi)
            lo, hi = (mid, hi) if minjerk(mid) < y else (lo, mid)
        return 0.5 * (lo + hi) * n_sw * DT

    def strike_in_s(self):
        """timed kick: seconds until the strike point passes the target as planned now (None once the swing began)"""
        if self.t_strike is None or self.phase() not in ("stand", "shift", "hold", "lift", "wait"):
            return None
        return max(self.t_strike - self.t, 0.0)

    def retime(self, t_strike, target):
        """timed kick, before the swing: a new time (seconds from now) and target point (world) for the strike"""
        if self.t_strike is None or self.phase() not in ("stand", "shift", "hold", "lift", "wait"):
            return False
        self.t_strike = self.t + float(t_strike)
        self.target = np.asarray(target, float).copy()
        if hasattr(self, "x_end"):
            del self.x_end                           # the path is planned again from the new target
        return True

    def strike_t(self) -> float:
        """nominal time from the start of the kick to the middle of the swing (s), without the waits"""
        n = 0
        for name, k in self.phases:
            if name == "swing":
                return (n + k / 2) * DT
            n += k
        return n * DT

    # ------------------------------------------------------------------ targets
    def _pelvis_target(self, name, s):
        if name == "stand":
            k = 0.0
        elif name == "shift":
            k = minjerk(s)
        elif name == "unshift":
            k = 1.0 - minjerk(s)
        elif name == "steady":
            k = 0.0
        else:
            k = 1.0
        off = self.com_off + self.com_fast
        corr = self.fw * off[0] + self.left_ax * off[1]
        kz = k if name in ("stand", "shift") or not self.P["keep_crouch"] else 1.0
        return self.p0 + self.delta * np.array([k, k, kz]) + corr

    def _path(self):
        P = self.P
        f0, sup = self.feet0[self.foot], self.feet0[self.sup]
        aim = self.aim
        lat = np.array([-aim[1], aim[0], 0.0])
        toe = float((sup - f0) @ aim)
        if self.target is None:
            x_end, side, h = toe + P["reach"], 0.0, P["height"]
        else:
            rel = self.target - self.Raim @ self.sis - f0
            x_end, side, h = float(rel @ aim) + P["follow"], float(rel @ lat), float(rel[2])
        x_end = float(np.clip(x_end, toe + 0.05, toe + P["xmax"]))
        side = float(np.clip(side, -P["side_max"], P["side_max"]))
        h = float(np.clip(h, P["h_min"], P["h_max"]))
        self.x_back, self.x_end, self.side, self.h = -P["back"], x_end, side, h
        # where along the path the strike point meets the target (timed kick)
        self.x_strike = float(np.clip(x_end - (P["follow"] if self.target is not None else 0.0), -P["back"], x_end))

    def _at(self, x, z, side_k=1.0):
        f0 = self.feet0[self.foot]
        lat = np.array([-self.aim[1], self.aim[0], 0.0])
        return f0 + self.aim * x + lat * (self.side * side_k) + np.array([0.0, 0.0, z])

    def _kick_foot_target(self, name, s):
        f0 = self.feet0[self.foot]
        if name in ("stand", "shift", "unshift", "steady"):
            return f0.copy()
        if not hasattr(self, "x_end"):
            self._path()
        k = minjerk(s)
        if self.P["turn_foot"]:
            self.foot_turn = k if name == "lift" else 1.0 if name in ("swing", "follow") else \
                1.0 - k if name == "retract" else 0.0
        if name == "lift":
            return self._at(self.x_back * k, self.h * k, k)
        if name == "wait":
            if self.P["turn_foot"]:
                self.foot_turn = 1.0
            return self._at(self.x_back, self.h)
        if name == "swing":
            return self._at(self.x_back + (self.x_end - self.x_back) * k, self.h)
        if name == "follow":
            return self._at(self.x_end + 0.02, self.h)
        if name == "retract":
            return self._at((self.x_end + 0.02) * (1 - k), self.h + 0.02 * math.sin(math.pi * k), 1 - k)
        if name == "lower":
            return f0 + np.array([0, 0, self.h - (self.h + self.P["land_depth"]) * k])
        return f0.copy()

    # ------------------------------------------------------------------ inverse kinematics of the feet
    def _ik(self, d, p_pel, foot_targets, iters=10):
        m, kd, rob = self.m, self.kin, self.rob
        kd.qpos[:] = d.qpos
        j = rob.rq
        kd.qpos[j:j + 3] = p_pel
        kd.qpos[j + 3:j + 7] = self.qpel0
        q = self.q.copy()
        jp = np.zeros((3, m.nv))
        jr = np.zeros((3, m.nv))
        for _ in range(iters):
            kd.qpos[rob.jq] = q
            mujoco.mj_kinematics(m, kd)
            mujoco.mj_comPos(m, kd)
            for side in ("left", "right"):
                sid = self.site[side]
                p = kd.site_xpos[sid]
                R = kd.site_xmat[sid].reshape(3, 3)
                Rt = self.Rlevel if side != self.foot or self.foot_turn == 0.0 else \
                    rot_z(self.yaw0 + self.aim_rel * self.foot_turn)
                e = np.r_[foot_targets[side] - p, 0.5 * (np.cross(R[:, 0], Rt[:, 0]) + np.cross(R[:, 1], Rt[:, 1]) +
                                                         np.cross(R[:, 2], Rt[:, 2]))]
                mujoco.mj_jacSite(m, kd, jp, jr, sid)
                cols = rob.jv[self.legcols[side]]
                J = np.vstack([jp[:, cols], jr[:, cols]])
                dq = J.T @ np.linalg.solve(J @ J.T + 1e-3 * np.eye(6), e)
                n = float(np.abs(dq).max())
                if n > 0.15:                          # small steps: stay on the bent-knee branch
                    dq *= 0.15 / n
                c = self.legcols[side]
                q[c] = np.clip(q[c] + dq, self.qlo[c], self.qhi[c])
                self.ik_err[side] = float(np.linalg.norm(e[:3]))
        return q

    def _balance_target(self, d=None):
        P = self.P
        out = self.left_ax * (P["outside"] if self.sup == "left" else -P["outside"])
        p = self.feet0[self.sup] if d is None else d.site_xpos[self.site[self.sup]]
        return p + self.fw * self.fsf + out

    def _site_vel(self, d, side):
        v = np.zeros(6)
        mujoco.mj_objectVelocity(self.m, d, mujoco.mjtObj.mjOBJ_SITE, self.site[side], v, 0)
        return v[3:]

    def _com_vel(self, com):
        prev = self._com_prev
        self._com_prev = com.copy()
        return np.zeros(3) if prev is None else (com - prev) / DT

    def _support_ff(self, d, name):
        """Leg torques that carry the robot's weight (static equilibrium with the feet's contact forces): tau = bias -
        J_c^T F, the weight split between the feet by where the centre of mass is (all on the support foot while the
        other is off the ground)."""
        m, rob = self.m, self.rob
        com = d.subtree_com[self.base].copy()
        W = float(m.body_subtreemass[self.base]) * 9.81
        if name in ("lift", "swing", "follow", "retract"):
            share = {self.sup: 1.0, self.foot: 0.0}
        else:
            pl, pr = d.site_xpos[self.site["left"]], d.site_xpos[self.site["right"]]
            ax = pl[:2] - pr[:2]
            t = float(np.clip((com[:2] - pr[:2]) @ ax / max(float(ax @ ax), 1e-9), 0.0, 1.0))
            share = {"left": t, "right": 1.0 - t}
        gen = np.zeros(m.nv)
        jp = np.zeros((3, m.nv))
        jr = np.zeros((3, m.nv))
        for side, w in share.items():
            if w <= 0:
                continue
            p = d.site_xpos[self.site[side]]
            F = np.array([0.0, 0.0, w * W])
            r = np.array([com[0] - p[0], com[1] - p[1], 0.0])
            mujoco.mj_jacSite(m, d, jp, jr, self.site[side])
            gen += jp.T @ F + jr.T @ np.cross(r, F)
        return d.qfrc_bias[rob.jv] - gen[rob.jv]

    def _steady(self, d, com, v):
        """the stability check before the walking policy takes the legs again"""
        P = self.P
        z = [float(d.site_xpos[self.site[s]][2]) for s in ("left", "right")]
        feet_down = abs(z[0] - z[1]) < 0.008 and max(float(np.linalg.norm(self._site_vel(d, s)))
                                                     for s in ("left", "right")) < 0.05
        mid = 0.5 * (d.site_xpos[self.site["left"]] + d.site_xpos[self.site["right"]]) + self.fw * self.fsf
        if self.restored and self.stance_com_f is not None:   # the policy's own stance: its CoM is ahead of the feet
            mid = mid + self.fw * self.stance_com_f
        off = float(np.linalg.norm(com[:2] - mid[:2]))
        w = float(np.linalg.norm(d.cvel[self.base][:3]))
        self.steady_info = dict(feet_down=bool(feet_down), v=round(float(np.linalg.norm(v[:2])), 3),
                                off=round(off, 3), w=round(w, 3))
        return feet_down and float(np.linalg.norm(v[:2])) < P["steady_v"] and off < P["steady_off"] and w < P["steady_w"]

    # ------------------------------------------------------------------ one tick
    def step(self, d):
        """The leg targets of this tick (12); self.ff is the support feed-forward. self.done once it is over."""
        name, n = self.phases[self.pi]
        s = self.i / n
        P = self.P
        if name == "stand":
            k = minjerk(s)
            self.q = self.q_start + (self.stand_q - self.q_start) * k
            q = self.q
            vc = self._com_vel(d.subtree_com[self.base])
            if self.i == n - 1 and self.extra["stand"] < P["stand_max"]:
                z = [d.site_xpos[self.site[sd]][2] for sd in ("left", "right")]
                vz = [np.linalg.norm(self._site_vel(d, sd)) for sd in ("left", "right")]
                if abs(z[0] - z[1]) > 0.006 or max(vz) > 0.05 or float(np.linalg.norm(vc[:2])) > P["stand_v"]:
                    # a foot still in the air or moving, or the body still moving: wait
                    self.extra["stand"] += 1
                    self.ff = self._support_ff(d, name)
                    self.t += DT
                    return q.copy()
            if self.i == n - 1:                       # the stance reached: the feet and the pelvis as they are now
                self.feet0 = {sd: d.site_xpos[self.site[sd]].copy() for sd in ("left", "right")}
                self.p0 = d.xpos[self.base].copy()
                self.qpel0 = np.zeros(4)
                mujoco.mju_mat2Quat(self.qpel0, d.xmat[self.base].reshape(-1).copy())
                mid = 0.5 * (self.feet0["left"] + self.feet0["right"]) + self.fw * self.fsf
                com0 = d.subtree_com[self.base].copy()
                # the shift starts from where the CoM is (the T1 stands with it ~8 cm ahead of the feet's centre), so
                # the balance loop sees no jump when it starts (G1: from the feet's centre)
                self.com_start = np.r_[com0[:2], 0.0] if P["com_from_actual"] else np.r_[mid[:2], 0.0]
                self.stance_com_f = float((com0[:2] - mid[:2]) @ self.fw[:2])
                c = self._balance_target()
                dl = c - com0
                self.delta = np.array([dl[0], dl[1], -P["crouch"]])
                dlr = self.feet0["left"] - self.feet0["right"]
                self.stance_info = dict(fore=round(float(dlr @ self.fw), 3), lat=round(float(dlr @ self.left_ax), 3),
                                        delta=[round(float(x), 3) for x in self.delta])
        elif name == "restore" or (name == "steady" and self.restored):
            # joint space, both feet down: from the kick's last targets to the walking policy's own standing targets
            # (the policy takes over exactly where it would stand)
            com = d.subtree_com[self.base]
            v = self._com_vel(com)
            if name == "restore":
                if self.i == 0:
                    self.q_from = self.q.copy()
                self.q = self.q_from + (self.end_q - self.q_from) * minjerk(s)
                if self.i == n - 1:
                    self.restored = True
            elif self.i == n - 1:
                self.steady_ok = self._steady(d, com, v)
                if not self.steady_ok and self.extra["steady"] < P["steady_max"]:
                    self.extra["steady"] += 1
                    self.i -= 1
            q = self.q
        else:
            if name == "unshift" and self.i == 0:     # both feet down again: where the kicking foot landed
                self.feet0[self.foot] = d.site_xpos[self.site[self.foot]].copy()
                if P["unshift_ground"]:               # on the ground (as high as the support foot), not pressed in
                    self.feet0[self.foot][2] = self.feet0[self.sup][2]
                self.mid_end = 0.5 * (self.feet0["left"] + self.feet0["right"]) + self.fw * self.fsf
            com = d.subtree_com[self.base]
            v = self._com_vel(com)
            bt = self._balance_target(d)
            if name == "shift":
                c = self.com_start + (bt - self.com_start) * minjerk(s)
            elif name == "unshift":
                c = bt + (self.mid_end - bt) * minjerk(s)
            elif name == "steady":
                c = self.mid_end
            else:
                c = bt
            xi = com[:2] + v[:2] / self.omega
            err = c[:2] - xi
            e_loc = np.array([err @ self.fw[:2], err @ self.left_ax[:2]])
            if name in ("unshift", "steady") and P["decay_back"]:   # back between the feet: the slow term fades
                self.com_off = self.com_off * 0.97 + 0.03 * np.clip(e_loc, -0.02, 0.02)
            else:
                self.com_off = np.clip(self.com_off + 0.05 * e_loc, -0.08, 0.08)
            self.com_fast = np.clip(1.3 * e_loc, -0.06, 0.06)
            if name == "lower" and self.i == n - 1 and self.extra["lower"] < P["lower_max"] and \
                    d.site_xpos[self.site[self.foot]][2] > self.feet0[self.foot][2] + P["land_tol"]:
                self.extra["lower"] += 1
                self.i -= 1
            if name == "hold" and self.i == n - 1 and np.linalg.norm(e_loc) > 0.01 and \
                    self.extra["hold"] < P["hold_max"]:
                self.extra["hold"] += 1
                self.i -= 1
            if name == "wait":                       # timed kick: wound up until the swing must start
                start_at = self.t_strike - self.swing_to_strike_s()
                if self.t + DT < start_at - 1e-9:
                    self.i -= 1
                else:
                    self.late = round(max(0.0, self.t + DT - start_at), 3)
            if name == "steady" and self.i == n - 1:
                self.steady_ok = self._steady(d, com, v)
                if not self.steady_ok and self.extra["steady"] < P["steady_max"]:
                    self.extra["steady"] += 1
                    self.i -= 1
            p_pel = self._pelvis_target(name, s)
            feet = {self.sup: self.feet0[self.sup], self.foot: self._kick_foot_target(name, s)}
            if P["follow_support"]:                   # the support foot slid: everything moves with it (planar)
                slip = d.site_xpos[self.site[self.sup]] - self.feet0[self.sup]
                slip[2] = 0.0
                p_pel = p_pel + slip
                feet = {k: v + slip for k, v in feet.items()}
            self.q = self._ik(d, p_pel, feet)
            q = self.q
        self.ff = self._support_ff(d, name)
        self.t += DT
        self.i += 1
        if self.i >= n:
            self.i = 0
            self.pi += 1
            if self.pi >= len(self.phases):
                self.done = True
        return q.copy()
