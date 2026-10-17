"""The joint-level RL opponent (level 5; the opponent team of the joint-level match): our own walking policy trained with
rsl_rl PPO on the GPU world of the joint level (pilots/soccer_joint/train_mjlab: the row limiter, PD, the real T1 motor
model, soccer-2v2-11 contact, hidden dynamics and pushes), driven by a team plan. Its robots are under joint control
like the agent's: 12 joint targets per robot every control step through the world's row limiter and motors; nothing
of the walking policy or the kick skills of the high level.

  gait   rl/joint/<version>/gait.npz: an MLP (ELU; obs normalizer mean/std/eps) from 47 inputs (projected gravity, body
         angular velocity x0.25, the velocity command vx, vy, wz (m/s, rad/s), joint positions - Booster's stance,
         joint velocities x0.05, the last action, the gait clock sin / cos) to 12 actions: row = stance + scale clip(a).
         NumPy float64 on the CPU, deterministic.
  plan   the robot that plays the ball (the lead: the lower distance to the ball, + 0.7 m when ahead of it, hysteresis)
         rushes: behind the ball on the line to the goal, then walks through it (dribbles) toward the goal; the other
         covers the line ball -> own goal near the goal line and clears a ball that comes close; both yield to
         opponents (no pushing). Kick-off: the kicking team's lead dribbles, the other team waits outside the circle;
         the shoot-out: the striker dribbles at the goal, the keeper covers.
It reads the true state (World.truth and the robots' own joint states), like the scripted levels.
"""
from __future__ import annotations

import math
import os

import numpy as np

import soccer as S

HERE = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.join(HERE, "rl", "joint")
STANCE = np.array([-0.2, 0.0, 0.0, 0.4, -0.25, 0.0] * 2)        # Booster's default stance (the GPU world's DEFAULT_Q)
VMAX = dict(vx=(-0.8, 1.6), vy=(-0.7, 0.7), wz=(-1.6, 1.6))      # the gait's command ranges (its training ranges)
BALL_RANGE = 1.5                                                 # the lead plays the ball skill within this of the ball
_V = os.environ.get("RLJ_VARIANT", "")                           # tuning experiments only (empty: the defaults)
KNOB = dict(gait="", yield_dribble=1, plan="mid", mid_d=1.0, mid_v=1.2, rush_v=1.5, drib_v=1.4, drib_lat=0.25, drib_face=0.8)
for _kv in filter(None, _V.replace(",", "+").split("+")):
    _k, _, _v = _kv.partition("=")
    KNOB[_k] = type(KNOB[_k])(_v) if not isinstance(KNOB[_k], str) else _v


class Gait:
    def __init__(self, path):
        z = np.load(path)
        self.mean, self.std, self.eps = (np.asarray(z[k], np.float64) for k in ("mean", "std", "eps"))
        n = sum(1 for k in z.files if k.startswith("w"))
        self.W = [np.asarray(z[f"w{i}"], np.float64) for i in range(n)]
        self.b = [np.asarray(z[f"b{i}"], np.float64) for i in range(n)]
        self.scale = float(z["action_scale"]) if "action_scale" in z.files else 0.6
        self.hz = float(z["gait_hz"]) if "gait_hz" in z.files else 1.6

    def __call__(self, x):
        x = (np.asarray(x, np.float64) - self.mean) / (self.std + self.eps)
        for i, (W, b) in enumerate(zip(self.W, self.b)):
            x = x @ W + b
            if i < len(self.W) - 1:
                x = np.where(x > 0, x, np.expm1(np.minimum(x, 0)))
        return x


def _rot_inv(q, v):
    """world vector v into the body frame of quaternion q (w, x, y, z)"""
    w, x = q[0], np.asarray(q[1:], float)
    t = 2.0 * np.cross(x, v)
    return v - w * t + np.cross(x, t)


def _wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def _unit(a):
    return np.array([math.cos(a), math.sin(a)])


SKILLS = ("rush", "rush_left", "rush_right", "mid", "mid_far", "cover", "press", "forward")
K = len(SKILLS)
DEFAULT_SKILLS = (SKILLS.index("rush"), SKILLS.index("mid"))   # the tuned plan: lead rushes, the other mid
DECIDE_EVERY = 10                                               # control steps between the plan's decisions (0.2 s)
OBS_DIM = 4 + 2 * (12 + K) + 2 * 11 + 4


class Plan:
    """the strategy layer: obs -> one skill per robot (lead, other); tanh MLP (obs_mu/obs_sd, W*/b*), greedy"""

    def __init__(self, path):
        z = np.load(path)
        self.mu, self.sd = z["obs_mu"].astype(np.float64), z["obs_sd"].astype(np.float64)
        n = int(z["n_layers"])
        self.W = [z[f"W{i}"].astype(np.float64) for i in range(n)]
        self.b = [z[f"b{i}"].astype(np.float64) for i in range(n)]

    def logits(self, obs):
        x = np.clip((np.asarray(obs, np.float64) - self.mu) / self.sd, -10, 10)
        for i, (W, b) in enumerate(zip(self.W, self.b)):
            x = x @ W + b
            if i < len(self.W) - 1:
                x = np.tanh(x)
        return x.reshape(2, K)

    def __call__(self, obs):
        return [int(i) for i in np.argmax(self.logits(obs), axis=1)]


def plan_obs(w, team, tr, order, skills):
    """the strategy layer's input (team frame): the ball, own robots in role order (+ their skills), opponents, game"""
    ball, bv = np.asarray(tr["ball"], float), np.asarray(tr["ball_v"], float)
    o = [ball[0] / 5, ball[1] / 3.5, bv[0] / 3, bv[1] / 3]

    def robot(r):
        st = tr["robots"][r]
        xy = np.asarray(st["xy"], float)
        v = S.to_team(team, w.rob[r].vel(w.d))
        rel = ball - xy
        return [xy[0] / 5, xy[1] / 3.5, math.cos(st["yaw"]), math.sin(st["yaw"]), float(v[0]), float(v[1]),
                float(st["fallen"]), float(st["bench"]), rel[0] / 5, rel[1] / 5, math.hypot(*rel) / 5]
    for j, r in enumerate(order):
        o += robot(r) + [0.0]
        o += [1.0 if skills is not None and skills[j] == s else 0.0 for s in range(K)]
    for r in S.TEAM_ROBOTS[S.OTHER[team]]:
        o += robot(r)
    sc = w.score[team] - w.score[S.OTHER[team]]
    o += [float(np.clip(sc, -3, 3)) / 3, w.clock() / S.HALF_S, 1.0 if w.period == 2 else 0.0,
          1.0 if (w.ko and not w.ko["in_play"]) else 0.0]
    return np.asarray(o, np.float32)


class JointTeam:
    """soccer.Coach's interface for a team under joint control (World puts the coach's team under joint control)."""
    joint = True

    def __init__(self, team, version="v1", policy=None):
        self.team = team
        self.gait = Gait(os.path.join(DIR, KNOB["gait"] or version, "gait.npz"))
        bp = os.path.join(DIR, version, "ball.npz")
        self.ball = Gait(bp) if os.path.exists(bp) else None      # the ball skill (same network format), optional
        self.ball_r = BALL_RANGE
        pp = os.path.join(DIR, version, "plan.npz") if version else ""
        self.policy = policy if policy is not None else (Plan(pp) if pp and os.path.exists(pp) else None)
        self.reset()

    def reset(self):
        self.order = list(S.TEAM_ROBOTS[self.team])
        self.k_switch = -10 ** 9
        self.phase = {r: 0.0 for r in S.TEAM_ROBOTS[self.team]}
        self.act = {r: np.zeros(12) for r in S.TEAM_ROBOTS[self.team]}
        self.was_down = {r: True for r in S.TEAM_ROBOTS[self.team]}
        self.skills = None                            # set by the strategy layer (or from outside: training)
        self.obs = None

    # ------------------------------------------------------------------ the plan (team frame)
    def _update_order(self, tr, k):
        rob, ball = tr["robots"], np.asarray(tr["ball"], float)

        def cost(r):
            st = rob[r]
            if st["fallen"] or st["bench"]:
                return 1e9
            xy = np.asarray(st["xy"], float)
            return float(np.hypot(*(xy - ball))) + (0.7 if xy[0] > ball[0] + 0.3 else 0.0)
        lead, other = self.order
        cl, co = cost(lead), cost(other)
        if (cl >= 1e9 and co < 1e9) or (co + 1.0 < cl and (k - self.k_switch) * S.CONTROL_DT > 5.0):
            self.order = [other, lead]
            self.k_switch = k

    @staticmethod
    def _go(pos, yaw, target, face, opps, speed):
        """the velocity command (body frame, m/s, rad/s) toward target, facing face, yielding to opponents"""
        tx = float(np.clip(target[0], -S.HALF_L + 0.35, S.HALF_L - (0.1 if abs(target[1]) < S.GOAL_W / 2 - 0.2
                                                                   else 0.35)))
        target = np.array([tx, float(np.clip(target[1], -S.HALF_W + 0.35, S.HALF_W - 0.35))])
        err = target - pos
        v = err * 2.0
        for ax, lim in ((0, S.HALF_L), (1, S.HALF_W)):   # keep off the boards (a trunk over a board leaves the field)
            gap = lim - abs(pos[ax])
            if gap < 0.45 and not (ax == 0 and abs(pos[1]) < S.GOAL_W / 2 - 0.2):
                v[ax] -= math.copysign(2.0 * (0.45 - gap), pos[ax])
        mag = float(np.hypot(*v))
        if mag > speed:
            v *= speed / mag
        for ob in sorted(opps, key=lambda q: float(np.hypot(*(q - pos))))[:4]:
            od = ob - pos
            dd = float(np.hypot(*od))
            if .08 < dd < 1.05:
                toward = od / dd
                closing = float(v @ toward)
                allowed = .06 if dd < .7 else .06 + (dd - .7) * 1.3
                if closing > allowed:
                    v = v - (closing - allowed) * toward
                    tangent = np.array([-toward[1], toward[0]])
                    if tangent @ err < 0:
                        tangent = -tangent
                    v = v + tangent * .25
        wz = float(np.clip(_wrap(face - yaw) * 2.5, *VMAX["wz"]))
        vx, vy = float(v @ _unit(yaw)), float(v @ _unit(yaw + math.pi / 2))
        if float(np.hypot(*err)) < .04 and abs(wz) < .08:
            return np.zeros(3)
        return np.array([np.clip(vx, *VMAX["vx"]), np.clip(vy, *VMAX["vy"]), wz])

    def _rush(self, pos, yaw, b, opps, aim=None):
        """behind the ball on the line ball -> aim, then walk through it toward the aim (the dribble)"""
        aim = np.array([S.HALF_L, 0.0]) if aim is None else np.asarray(aim, float)
        delta = b - pos
        dist = float(np.hypot(*delta))
        u = aim - b
        shot = math.atan2(u[1], u[0])
        f, l = _unit(shot), _unit(shot + math.pi / 2)
        rel = pos - b
        behind, lat = float(rel @ f), float(rel @ l)
        if behind < -0.05 and abs(lat) < KNOB["drib_lat"] and abs(_wrap(shot - yaw)) < KNOB["drib_face"]:
            near = [o for o in opps if float(np.hypot(*(o - pos))) < 0.6] if KNOB["yield_dribble"] else []
            return self._go(pos, yaw, b + 0.8 * f, shot, near, KNOB["drib_v"])   # through the ball (the dribble)
        if behind > -0.25 and dist < 1.2:                                  # wrong side: around it
            side = 1 if lat >= 0 else -1
            return self._go(pos, yaw, b - 0.55 * f + side * 0.55 * l, shot, opps, 1.2)
        target = b - 0.35 * f
        face = shot if dist < 1.0 else math.atan2(delta[1], delta[0])
        return self._go(pos, yaw, target, face, opps, KNOB["rush_v"] if dist > 1.0 else 0.8)

    def _cover(self, pos, yaw, b, mate, opps):
        delta = b - pos
        dist = float(np.hypot(*delta))
        gx = -4.15 if b[0] < .3 else -2.5
        if mate is not None and mate[0] < -2.95 and abs(mate[1]) < 2.1:
            gx = -2.7
        gy = float(np.clip(b[1] * (gx + S.HALF_L) / max(.5, b[0] + S.HALF_L), -1.1, 1.1))
        if dist < .6 and pos[0] < b[0] and gx < -3:
            return self._rush(pos, yaw, b, opps)
        return self._go(pos, yaw, np.array([gx, gy]), math.atan2(delta[1], delta[0]), opps, .5 if dist < 1.5 else 1.1)

    def commands(self, w, tr):
        """the velocity command of each robot (team frame plan; robot frame command)"""
        team = self.team
        mine = S.TEAM_ROBOTS[team]
        rob = tr["robots"]
        b = np.asarray(tr["ball"], float)
        opps = [np.asarray(rob[o]["xy"], float) for o in rob if o[0] != team and not rob[o]["bench"]]
        self._update_order(tr, w.k)
        lead = self.order[0]
        out = {}
        ko = w.ko if (w.ko and not w.ko["in_play"]) else None
        for r in mine:
            st = rob[r]
            pos, yaw = np.asarray(st["xy"], float), float(st["yaw"])
            mate = [np.asarray(rob[o]["xy"], float) for o in mine if o != r and not rob[o]["bench"]]
            mate = mate[0] if mate else None
            if w.state == "pso_kick" and w.pso:
                cur = w.pso["cur"]
                if r == cur.get("striker"):
                    out[r] = self._rush(pos, yaw, b, opps, aim=(S.HALF_L, 0.6))
                elif r == cur.get("keeper"):
                    out[r] = self._go(pos, yaw, np.array([-S.HALF_L + 0.3, float(np.clip(b[1], -0.9, 0.9))]),
                                      math.atan2(b[1] - pos[1], b[0] - pos[0]), [], 0.8)
                else:
                    out[r] = np.zeros(3)
                continue
            if ko is not None and (ko["team"] != team or r != lead):
                spot = np.array([-1.4, 0.3]) if r == lead else np.array([-3.6, 0.0])
                out[r] = self._go(pos, yaw, spot, 0.0, opps, 0.8)
                continue
            if r == lead and self.ball is not None and float(np.hypot(*(b - pos))) < self.ball_r:
                out[r] = self._ball_input(w, r, tr)
                continue
            if self.skills is not None:
                out[r] = self._skill(SKILLS[self.skills[self.order.index(r)]], pos, yaw, b, mate, opps, rob)
                continue
            if r == lead or KNOB["plan"] == "chase":
                out[r] = self._rush(pos, yaw, b, opps)
            elif KNOB["plan"] == "mid":                    # the second robot between the ball and the own goal, 1.5 m off
                u = np.array([-S.HALF_L, 0.0]) - b
                spot = b + KNOB["mid_d"] * u / max(float(np.hypot(*u)), 1e-6)
                out[r] = self._go(pos, yaw, spot, math.atan2(b[1] - pos[1], b[0] - pos[0]), opps, KNOB["mid_v"])
            else:
                out[r] = self._cover(pos, yaw, b, mate, opps)
        return out

    def _skill(self, name, pos, yaw, b, mate, opps, rob):
        face = math.atan2(b[1] - pos[1], b[0] - pos[0])
        own = np.array([-S.HALF_L, 0.0])
        if name == "rush":
            return self._rush(pos, yaw, b, opps)
        if name == "rush_left":
            return self._rush(pos, yaw, b, opps, aim=(S.HALF_L, 0.7))
        if name == "rush_right":
            return self._rush(pos, yaw, b, opps, aim=(S.HALF_L, -0.7))
        if name in ("mid", "mid_far"):
            u = own - b
            dd = KNOB["mid_d"] if name == "mid" else 2.2
            return self._go(pos, yaw, b + dd * u / max(float(np.hypot(*u)), 1e-6), face, opps, KNOB["mid_v"])
        if name == "cover":
            return self._cover(pos, yaw, b, mate, opps)
        if name == "press":                           # straight at the ball
            return self._go(pos, yaw, b, face, [], 1.5)
        # forward: ahead of the ball toward the opponents' goal, for a rebound
        u = np.array([S.HALF_L, 0.0]) - b
        return self._go(pos, yaw, b + 1.5 * u / max(float(np.hypot(*u)), 1e-6), face, opps, 1.2)

    def _ball_input(self, w, r, tr):
        """the ball skill's inputs (body frame xy, world-frame physics): the ball, its velocity, the goal centre"""
        d, rb = w.d, w.rob[r]
        q = d.qpos[rb.rq + 3:rb.rq + 7]
        base = d.qpos[rb.rq:rb.rq + 3]
        ball, bv = w.ball_pos(), w.ball_v()
        goal = S.from_team(self.team, np.array([S.HALF_L, 0.0]))
        f = lambda v: _rot_inv(q, np.array([v[0], v[1], 0.0]))[:2]  # noqa: E731
        return ("ball", f(ball[:2] - base[:2]), f(bv[:2]), f(goal - base[:2]))

    # ------------------------------------------------------------------ the joint level
    def decide(self, w, robots=None):
        tr = w.truth(self.team)
        if self.policy is not None and (self.skills is None or w.k % DECIDE_EVERY == 0):
            self._update_order(tr, w.k)
            self.obs = plan_obs(w, self.team, tr, self.order, self.skills)
            self.skills = list(self.policy(self.obs))
        cmds = self.commands(w, tr)
        d = w.d
        out = {}
        for r, c in cmds.items():
            down = w.fallen[r] is not None or w.penalty[r] is not None or w.on_bench(r) or w.held.get(r, -1) > w.k
            if down:
                self.was_down[r] = True
                continue
            if self.was_down[r]:                      # stood up or placed: the gait starts afresh
                self.phase[r], self.act[r], self.was_down[r] = 0.0, np.zeros(12), False
            rb = w.rob[r]
            q = d.qpos[rb.rq + 3:rb.rq + 7]
            g = _rot_inv(q, np.array([0.0, 0.0, -1.0]))
            wb = d.qvel[rb.rv + 3:rb.rv + 6]
            ph = 2 * math.pi * self.phase[r]
            if isinstance(c, tuple):                  # ("ball", ball rel, ball vel, goal rel): the ball skill
                _, brel, bvel, grel = c
                obs = np.concatenate([g, 0.25 * wb, d.qpos[rb.jq] - STANCE, 0.05 * d.qvel[rb.jv], self.act[r],
                                      brel, bvel, 0.2 * grel, [math.sin(ph), math.cos(ph)]])
                a = np.clip(self.ball(obs), -1.0, 1.0)
            else:
                obs = np.concatenate([g, 0.25 * wb, c, d.qpos[rb.jq] - STANCE, 0.05 * d.qvel[rb.jv], self.act[r],
                                      [math.sin(ph), math.cos(ph)]])
                a = np.clip(self.gait(obs), -1.0, 1.0)
            self.act[r] = a
            self.phase[r] = math.fmod(self.phase[r] + self.gait.hz * S.CONTROL_DT, 1.0)
            out[r] = dict(type="joints", q=[float(x) for x in STANCE + self.gait.scale * a])
        return out
