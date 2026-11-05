"""L-RL: the wheeled 5 v 5 team trained by reinforcement learning (an extra opponent tier above the scripted levels;
task RLSSL).

What it is. The scripted L3 team (opponents.Scripted, level 3: man marking, a blocker, passes, the reference's
shooting rule) is the low level; a small fixed-weight network chooses, every 0.2 s of game time while the ball is in
play, one OPTION per field robot and one for the robot with the ball (a residual over L3: option 0 is "what L3 would
do"). Off the ball (robots 1-4): L3's choice, go for the ball, go to one of 24 spots of a 6 x 4 grid over the field
(facing the ball), mark the k-th most advanced opponent (0.4 m on its ball side), or screen the shot (0.9 m from the
ball on the bisector of the goal's angle). With the ball: L3's decision, shoot at the best goal point, pass to
teammate k (its best receiving point), carry, or push the ball into space. The keeper and the set pieces stay L3's.
Every command is a skill (`move`, `kick`, `dribble`) checked and executed like any player's (World.execute), so the
robot's limits are the platform's; the kicks are the reference's (at most 6 m/s minus the robot's own speed).

Perception: the truth in the team frame, as the scripted L3 reads it (no reaction delay; `DELAY` = 0). The pilot of
10-16 first used the vision latency (0.04 s): that alone cost about 2 goals per match against L3 (20 matches), so the
RL tier reads exactly what the top scripted level reads and is compared with it on equal terms. In the duel seat
(builtin_players.RLPlayer) the service's own latency applies on top (observe, act, the declared effect delay).

Inference: numpy, float64, argmax (deterministic): the same seed replays the same match. The weights are
`sports/soccer_ssl/rl/<policy>/policy.npz` (obs mean / std, two tanh layers, the option heads); the training code is not part of the
repository (the Embodied Olympics handoff notes).
"""
from __future__ import annotations

import math
import os

import numpy as np

from . import BP, LEVELS, Scripted

HERE = os.path.dirname(os.path.abspath(__file__))
WEIGHTS_DIR = os.path.join(os.path.dirname(HERE), "rl")
DEFAULT_WEIGHTS = "lrl-v1"

DELAY = 0.0           # s: extra perception delay (L3's: none; the pilot's first runs used 0.04)
PERIOD = 0.2          # s of game time between decisions
FIELD = (1, 2, 3, 4)  # the field robots the network commands (0 is the keeper)

GRID_X = (-3.2, -2.0, -0.8, 0.4, 1.6, 2.8)
GRID_Y = (-2.0, -0.7, 0.7, 2.0)
GRID = [(x, y) for x in GRID_X for y in GRID_Y]
# off-ball options
O_DEFAULT, O_COLLECT = 0, 1
O_GRID = 2
O_MARK = O_GRID + len(GRID)          # 26..29: mark the k-th most advanced opponent field robot
O_SCREEN = O_MARK + 4                # 30
N_OFF = O_SCREEN + 1                 # 31
# ball options
C_DEFAULT, C_SHOT, C_PASS, C_CARRY, C_PUSH = 0, 1, 2, 6, 7   # C_PASS + k - 1 for teammate k = 1..4
N_BALL = 8
N_HEADS = len(FIELD) + 1
OBS_DIM = 4 + 5 * 8 + 5 + 4 * 5 + 1 + 5 + 4


def opp_field_sorted(v):
    """the opponent field robots on the field, the most advanced first (lowest x in our frame)."""
    return sorted((o for k, o in v.opp.items() if o.on and k != BP.KEEPER), key=lambda o: (o.p[0], o.p[1]))


def features(team) -> np.ndarray:
    """the network's input: the team's (delayed) view in its own frame, scaled to about [-1, 1]."""
    v = team.v
    f = [v.ball[0] / 4.5, v.ball[1] / 3.0, v.ball_v[0] / 3.0, v.ball_v[1] / 3.0]
    carrier = None
    for k in range(5):
        r = v.own.get(k)
        if r is None or not r.on:
            f += [0.0] * 8
            continue
        hb = bool(r.beam or r.engaged)
        if hb and k != BP.KEEPER and carrier is None:
            carrier = k
        f += [r.p[0] / 4.5, r.p[1] / 3.0, r.v[0] / 3.0, r.v[1] / 3.0, math.cos(r.yaw), math.sin(r.yaw), 1.0,
              1.0 if hb else 0.0]
    ok = v.opp.get(BP.KEEPER)
    if ok is not None and ok.on:
        f += [ok.p[0] / 4.5, ok.p[1] / 3.0, ok.v[0] / 3.0, ok.v[1] / 3.0, 1.0]
    else:
        f += [0.0] * 5
    of = opp_field_sorted(v)
    for i in range(4):
        if i < len(of):
            o = of[i]
            f += [o.p[0] / 4.5, o.p[1] / 3.0, o.v[0] / 3.0, o.v[1] / 3.0, 1.0]
        else:
            f += [0.0] * 5
    f.append(1.0 if team.opp_with_ball() is not None else 0.0)
    recv = team.pass_["recv"] if team.pass_ is not None else None
    f += [1.0 if recv == k else 0.0 for k in range(5)]
    R = v.ref
    f += [max(-3, min(3, R.score_us - R.score_them)) / 3.0, min(1.0, max(0.0, R.time_left / 300.0)),
          1.0 if R.half >= 2 else 0.0, 1.0 if carrier is not None else 0.0]
    return np.asarray(f, dtype=np.float64)


class Policy:
    """the fixed-weight network (numpy, float64): obs -> (N_OFF logits per field robot, N_BALL logits)."""

    def __init__(self, path):
        z = np.load(path)
        self.mu, self.sd = z["obs_mu"].astype(np.float64), z["obs_sd"].astype(np.float64)
        self.W = [z[f"W{i}"].astype(np.float64) for i in range(3)]
        self.b = [z[f"b{i}"].astype(np.float64) for i in range(3)]
        self.name = str(z["name"]) if "name" in z else os.path.basename(path)

    def logits(self, obs):
        h = np.clip((obs - self.mu) / self.sd, -5.0, 5.0)
        h = np.tanh(h @ self.W[0] + self.b[0])
        h = np.tanh(h @ self.W[1] + self.b[1])
        out = h @ self.W[2] + self.b[2]
        n = len(FIELD) * N_OFF
        return out[:n].reshape(len(FIELD), N_OFF), out[n:]

    def decide(self, obs, active):
        off, ball = self.logits(obs)
        return [int(np.argmax(r)) for r in off], int(np.argmax(ball))


def load_policy(name=None):
    name = name or os.environ.get("SSL_RL_WEIGHTS") or DEFAULT_WEIGHTS
    path = name if name.endswith(".npz") else os.path.join(WEIGHTS_DIR, name, "policy.npz")
    return Policy(path)


class RLTeamCore(Scripted):
    """L3 with the network's options on top (see the module docstring). `policy.decide(obs, active)` returns the
    options; `active` says which heads matter now (a robot with the ball or receiving a pass takes no off-ball
    option; the ball head only when a field robot has the ball)."""

    name = "rl"

    def __init__(self, policy, team="yellow", seed=0, rng=None, period=PERIOD, delay=DELAY):
        super().__init__(level=3, team=team, seed=seed, rng=rng, delay=delay)
        self.policy = policy
        self.period = float(period)
        self.next_t = -1.0
        self.opts = [O_DEFAULT] * len(FIELD)
        self.copt = C_DEFAULT
        self.stats.update(rl_decisions=0, rl_off_override=0, rl_ball_override=0)

    def play(self):
        v = self.v
        ids = [k for k in self.field_ids() if self.locked_until.get(k, -1) <= v.t]
        carrier = next((k for k in ids if self.has_ball(k)), None)
        recv = self.pass_["recv"] if self.pass_ is not None else None
        if v.t >= self.next_t - 1e-9:
            self.next_t = v.t + self.period
            active = [bool(k in ids and k != carrier and k != recv) for k in FIELD] + [carrier is not None]
            self.opts, self.copt = self.policy.decide(features(self), active)
            self.stats["rl_decisions"] += 1
            if carrier is not None and self.copt != C_DEFAULT:
                pl = self.ball_plan(carrier, self.copt)
                if pl is not None:
                    self.plan = pl
                    self.stats["rl_ball_override"] += 1
        over = [k for i, k in enumerate(FIELD) if self.opts[i] != O_DEFAULT and k in ids and k != carrier
                and k != recv]
        snap = {k: (self.sent_move.get(k), self.sent_drib.get(k)) for k in over}
        super().play()
        if not over:
            return
        self.cmds = [c for c in self.cmds if c[0] not in over]
        for k in over:
            m, d = snap[k]
            for cache, val in ((self.sent_move, m), (self.sent_drib, d)):
                if val is None:
                    cache.pop(k, None)
                else:
                    cache[k] = val
            self.off_ball(k, self.opts[FIELD.index(k)])
            self.stats["rl_off_override"] += 1

    # ------------------------------------------------------------------------------------------------ the options
    def off_ball(self, k, o):
        v = self.v
        b = v.ball
        if o == O_COLLECT:
            self.collect(k, aim=BP.OPP_GOAL)
            return
        p = None
        rpm = 3000
        if O_GRID <= o < O_MARK:
            p = GRID[o - O_GRID]
        elif O_MARK <= o < O_SCREEN:
            of = opp_field_sorted(v)
            j = o - O_MARK
            if j < len(of):
                r = of[j]
                mx, my = BP.unit(b[0] - r.p[0], b[1] - r.p[1])
                p = BP.push_out_of_own_da((r.p[0] + mx * 0.4, r.p[1] + my * 0.4))
                rpm = 0
            else:
                p = (max(-3.3, b[0] - 2.0), 0.0)
        elif o == O_SCREEN:
            p = self.screen_spot(0.9)
            rpm = 0
        if p is None:
            p = v.own[k].p
        if BP.dist(p, b) < 0.4:  # keep off the ball (two at it for 1 s: ball holding, §8.4.1.3)
            ux, uy = BP.unit(p[0] - b[0], p[1] - b[1])
            p = (b[0] + ux * 0.4, b[1] + uy * 0.4)
        self.move(k, p, math.atan2(b[1] - p[1], b[0] - p[0]))
        self.dribble(k, rpm)

    def ball_plan(self, n, o):
        """the carrier's plan for ball option o (Reference.attack executes it), or None (L3 decides)."""
        v = self.v
        b = v.ball
        if o == C_SHOT:
            s = self.best_shot(b, n)
            tgt = s["target"] if s is not None else (BP.HALF_L + 0.05, 0.0)
            return dict(num=n, kind="shot", target=tgt, speed=self.kick_speed, mode="flat", t=v.t,
                        margin=s["margin"] if s is not None else -1.0)
        if C_PASS <= o < C_CARRY:
            k = FIELD[o - C_PASS]
            r = v.own.get(k)
            if k == n or r is None or not r.on:
                return None
            best = None
            for q in self.pass_points(k):
                op = self._pass_option(n, k, q, check_receiver=False)
                if op is not None and (best is None or op["margin"] + 0.3 * op["value"] >
                                       best["margin"] + 0.3 * best["value"]):
                    best = op
            if best is None:
                return None
            return dict(num=n, kind="pass", target=best["target"], speed=best["speed"], mode=best["mode"], recv=k,
                        T=best["T"], t=v.t, margin=best["margin"], redirect=best.get("redirect"))
        if o == C_CARRY:
            if self.track_hold(n) > 0.4:
                return None
            return dict(num=n, kind="carry", target=self.carry_target(n), speed=0.0, mode="flat", t=v.t)
        if o == C_PUSH:
            tgt, sp = self.push_target(b)
            return dict(num=n, kind="push", target=tgt, speed=sp, mode="flat", t=v.t)
        return None


class RLTeam:
    """the plugin's interface, as opponents.ScriptedTeam: RLTeam(team, rng).act(truth) -> [command bodies], called
    every control step with World.truth_view(team); decides every second call (20 ms)."""

    level = "RL"

    def __init__(self, team="yellow", rng=None, every=2, policy=None, weights=None):
        self.policy = policy if policy is not None else load_policy(weights)
        self.team = RLTeamCore(self.policy, team=team, rng=rng)
        self.every = int(every)
        self.calls = 0

    def act(self, truth: dict) -> list:
        self.calls += 1
        if (self.calls - 1) % self.every:
            return []
        view = BP.view_from_truth(truth)
        return [BP.to_act(n, skill, args) for n, skill, args in self.team.update(view)]

    @property
    def stats(self):
        return self.team.stats


assert LEVELS[3]["delay"] == 0.0  # L3 itself is untouched: the RL team only passes its own delay
