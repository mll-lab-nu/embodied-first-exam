"""The RL opponent (level 4, "L-RL"; not an official level): a trained high-level policy that plays the scripted team B
of the `match` / `team_match` formats in place of soccer.Coach, opened by a parameter (RCB_LEVEL=4). Levels 1-3 and
the frozen configurations are unchanged.

What it is: every DECIDE_EVERY control steps (0.2 s) a small fixed-weight network (weights in rl/<version>/actor.npz, NumPy
inference on the CPU, greedy: the same match replays bit-exactly) chooses one of SKILLS for each of its two robots;
between decisions every skill is executed at every control step by the scripted player's own planner
(soccer.plan_robot, the level-3 / reference parameters: walk at most 0.8 m/s, the in-walk kick). So the RL opponent
moves its robots only through the commands any player has (walk / stand / kick), within the same limits (the walking
command range, the command rate limit, the motors of bodies/booster_t1), and it reads the same true state as the
scripted levels (soccer.World.truth: ball and robot positions; plus the robots' velocities). What it learned is
which skill each robot plays when: who goes for the ball, where the shot goes, who defends, blocks or marks.

Restarts it does not decide (the scripted team's rules apply): the opponents' kick-off before the ball is in play
(wait outside the circle), its own kick-off touch, and the penalty shoot-out (soccer.Coach's shoot-out striker and
keeper).

Observation (team frame, OBS_DIM floats): the ball (position, velocity), each own robot (position, heading, velocity,
fallen, benched, kicking, the ball relative to it, the skill it plays), each opponent (the same without the skill),
the score difference, the clock and the restart flags. Training: PPO against the scripted levels and earlier versions
of itself (league); the training scripts are not part of this repository (README "RL opponent").
"""
from __future__ import annotations

import math
import os

import numpy as np

import soccer as S

HERE = os.path.dirname(os.path.abspath(__file__))
RL_DIR = os.path.join(HERE, "rl")                # rl/<version>/actor.npz
DECIDE_EVERY = 10                      # control steps between decisions (0.2 s)
LV = dict(S.COACH_LEVELS["reference"])  # the skills' planner parameters: the strongest scripted player's
LV_FAST = dict(LV, vmax=1.0, vlat=0.5)  # the walking command's full forward range
SKILLS = ("strike", "strike_left", "strike_right", "strike_fast", "dribble", "support", "defend", "block", "mark",
          "press", "rush", "cover")
K = len(SKILLS)
OBS_DIM = 4 + 2 * (13 + K) + 2 * 13 + 7


def _team_robots(team):
    return S.TEAM_ROBOTS[team], S.TEAM_ROBOTS[S.OTHER[team]]


def observe(w, team, tr, skills, order=None):
    """The policy's input (team frame), from World.truth(team) `tr` and the robots' velocities. order: the own robots,
    the lead (the one that plays the ball) first."""
    mine, theirs = _team_robots(team)
    mine = tuple(order or mine)
    ball, bv = np.asarray(tr["ball"], float), np.asarray(tr["ball_v"], float)
    o = [ball[0] / 5, ball[1] / 3.5, bv[0] / 3, bv[1] / 3]

    def robot(r):
        st = tr["robots"][r]
        xy = np.asarray(st["xy"], float)
        v = st["v"] if "v" in st else S.to_team(team, w.rob[r].vel(w.d))
        rel = ball - xy
        return [xy[0] / 5, xy[1] / 3.5, math.cos(st["yaw"]), math.sin(st["yaw"]), float(v[0]), float(v[1]),
                float(st["fallen"]), float(st["bench"]), float(st["kicking"]), rel[0] / 5, rel[1] / 5,
                math.hypot(*rel) / 5, math.atan2(rel[1], rel[0]) - st["yaw"]]

    for j, r in enumerate(mine):
        f = robot(r)
        f[-1] = math.sin(f[-1])                                 # the ball's bearing from the heading
        o += f
        o += [1.0 if skills is not None and skills[j] == s else 0.0 for s in range(K)]
    for r in theirs:
        f = robot(r)
        f[-1] = math.sin(f[-1])
        o += f
    ref = w.referee(team)
    ko, fk = ref["kickoff"], ref["free_kick"]
    clock = float(ref["clock_s"]) / S.HALF_S
    o += [float(np.clip(ref["score"]["us"] - ref["score"]["them"], -3, 3)) / 3, clock, 1.0 if ref["period"] == 2 else 0.0,
          1.0 if ko and ko["ours"] and not ko["ball_in_play"] else 0.0,
          1.0 if ko and not ko["ours"] and not ko["ball_in_play"] else 0.0,
          1.0 if fk and fk["ours"] and not fk["ball_in_play"] else 0.0,
          1.0 if fk and not fk["ours"] and not fk["ball_in_play"] else 0.0]
    return np.asarray(o, np.float32)


def _wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def _unit(a):
    return np.array([math.cos(a), math.sin(a)])


def _go(pos, yaw, target, face, opps, speed):
    """walk toward target at up to `speed` m/s, facing `face`, yielding to opponents within 1.05 m (no pushing)."""
    err = target - pos
    v = err * 1.5
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
                v = v + tangent * .22
    mag = float(np.hypot(*v))
    if mag > speed:
        v *= speed / mag
    wz = float(np.clip(_wrap(face - yaw) * 2., -1, 1))
    vx = float(v @ _unit(yaw)) / .75
    vy = float(v @ _unit(yaw + math.pi / 2)) / .75
    if float(np.hypot(*err)) < .035 and abs(wz) < .06:
        return dict(type="stand")
    return dict(type="walk", v=[round(float(np.clip(vx, -1, 1)), 3), round(float(np.clip(vy, -.85, .85)), 3),
                                round(wz, 3)])


def _rush(pos, yaw, b, opps):
    """go behind the ball on the line to the goal centre at up to 0.95 m/s and kick with the full-power in-walk kick
    as soon as the ball is 0.24-0.68 m ahead and 0.055-0.25 m to a side"""
    delta = b - pos
    dist = float(np.hypot(*delta))
    shot = math.atan2(-b[1], max(.4, S.HALF_L - b[0]))
    f, l = _unit(shot), _unit(shot + math.pi / 2)
    bl = np.array([delta @ _unit(yaw), delta @ _unit(yaw + math.pi / 2)])
    align = _wrap(shot - yaw)
    if .24 < bl[0] < .68 and .055 < abs(bl[1]) < .25 and abs(align) < .24:
        return dict(type="kick", style="step", foot="left" if bl[1] > 0 else "right", power=1.0,
                    aim=round(float(np.clip(align, -.2, .2)), 4), v=[.48, 0.0, 0.0])
    side = 1 if delta @ l > 0 else -1
    target = b - .45 * f - side * .14 * l
    approach, lateral = (pos - b) @ f, (pos - b) @ l
    if approach > -.22 and dist > .48:
        target = b - .6 * f + (1 if lateral >= 0 else -1) * .7 * l
    target = np.array([np.clip(target[0], -4.55, 4.65), np.clip(target[1], -3.1, 3.1)])
    face = shot if dist < 1.25 else math.atan2(delta[1], delta[0])
    if dist < .55 and bl[0] < .12:
        target = b - .58 * f - side * .18 * l
    return _go(pos, yaw, target, face, opps, .95 if dist > 1 else .48)


def rush_cover(skill, me, mine, ball, rob, avoid=None):
    """the skills "rush" (the fast striker) and "cover" (on the line ball -> own goal near the goal line, clearing a
    ball that comes within 0.55 m); after the controller GPT-6 Astra wrote in the 10-16 precheck (team frame)."""
    st = rob[me]
    if st["bench"] or st["fallen"] or st["kicking"]:
        return None
    pos, yaw = np.asarray(st["xy"], float), float(st["yaw"])
    b = np.asarray(ball, float)
    opps = [np.asarray(rob[o]["xy"], float) for o in rob if o[0] != me[0] and not rob[o]["bench"]]
    if avoid is not None:                               # an opponents' free kick: wait outside its circle
        c, rad, _ = avoid
        u = pos - c
        if float(np.hypot(*u)) < rad + 0.5:
            return _go(pos, yaw, c + (rad + 0.6) * u / max(float(np.hypot(*u)), 1e-6), yaw, opps, .6)
    if skill == "rush":
        return _rush(pos, yaw, b, opps)
    delta = b - pos
    dist = float(np.hypot(*delta))
    face = math.atan2(delta[1], delta[0])
    gx = -4.15 if b[0] < .3 else -2.5
    mates = [np.asarray(rob[o]["xy"], float) for o in mine if o != me and not rob[o]["bench"]]
    if mates and mates[0][0] < -2.95 and abs(mates[0][1]) < 2.1:
        gx = -2.7
    gy = float(np.clip(b[1] * (gx + S.HALF_L) / max(.5, b[0] + S.HALF_L), -1.1, 1.1))
    if dist < .55 and pos[0] < b[0] and gx < -3:
        return _rush(pos, yaw, b, opps)
    return _go(pos, yaw, np.array([gx, gy]), face, opps, .35 if dist < 1.5 else .8)


class MLP:
    """The fixed-weight actor: obs -> (tanh layers) -> 2 x K logits; float64 NumPy, greedy."""

    def __init__(self, path):
        z = np.load(path)
        self.mu, self.sd = z["obs_mu"].astype(np.float64), z["obs_sd"].astype(np.float64)
        self.W = [z[f"W{i}"].astype(np.float64) for i in range(int(z["n_layers"]))]
        self.b = [z[f"b{i}"].astype(np.float64) for i in range(int(z["n_layers"]))]
        self.version = str(z["version"]) if "version" in z else os.path.basename(path)

    def logits(self, obs):
        x = np.clip((np.asarray(obs, np.float64) - self.mu) / self.sd, -10, 10)
        for i, (W, b) in enumerate(zip(self.W, self.b)):
            x = x @ W + b
            if i < len(self.W) - 1:
                x = np.tanh(x)
        return x.reshape(2, K)

    def __call__(self, obs):
        return [int(i) for i in np.argmax(self.logits(obs), axis=1)]


def load(version="v2"):
    return MLP(os.path.join(RL_DIR, version, "actor.npz"))


class RLCoach(S.Coach):
    """soccer.Coach's interface (decide(w) -> {robot: command}) with the skills chosen by a policy. policy: obs ->
    [skill of robot 1, skill of robot 2] (None: the skills are set from outside, the training loop's case)."""

    def __init__(self, team, policy=None, version="v2"):
        super().__init__(team, "reference")
        self.policy = load(version) if policy is None and version else policy
        self.skills = None
        self.obs = None
        self.order = list(S.TEAM_ROBOTS[team])
        self.k_switch = -10 ** 9

    def reset(self):
        super().reset()
        self.skills = None
        self.order = list(S.TEAM_ROBOTS[self.team])
        self.k_switch = -10 ** 9

    def update_order(self, tr, k):
        """the lead robot (first in the observation; the policy's first skill): the one with the lower cost (distance
        to the ball, + 0.7 m if it is ahead of the ball); switched when the other's cost is 1 m lower and the lead has
        held 5 s, or at once when the lead is down or benched"""
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

    def observe(self, w):
        return observe(w, self.team, w.truth(self.team), self.skills, self.order)

    def decide(self, w, robots=None):
        tr = w.truth(self.team)
        team = self.team
        mine = S.TEAM_ROBOTS[team]
        self.update_order(tr, w.k)
        if self.policy is not None and (self.skills is None or w.k % DECIDE_EVERY == 0):
            self.obs = observe(w, team, tr, self.skills, self.order)
            self.skills = list(self.policy(self.obs))
        skills = self.skills or [SKILLS.index("rush"), SKILLS.index("cover")]
        roles = self.roles(w, tr)                       # the scripted roles: restarts and the shoot-out
        rob = tr["robots"]
        ball, bv = np.asarray(tr["ball"], float), np.asarray(tr["ball_v"], float)
        avoid = None
        if w.fk and not w.fk["in_play"] and w.fk["team"] != team:
            avoid = (S.to_team(team, w.fk["spot"]), S.CENTER_R, w.fk["kind"] == "goal_kick")
        base = dict(defend_half=True, aim_left=(w.pso["cur"]["n"] // 2 + w.seed) % 2 == 0 if w.pso else True,
                    kickoff_touch=bool(w.ko and w.ko["team"] == team and not w.ko["touched_outside"]
                                       and float(np.hypot(*ball)) < S.CENTER_R), avoid=avoid)
        scripted = w.state == "pso_kick" or bool(w.ko and not w.ko["in_play"])
        out = {}
        for j, r in enumerate(robots or mine):
            if scripted:
                role = roles[r]
                if w.ko and not w.ko["in_play"] and (w.ko["team"] != team or role != "striker"):
                    role = "idle"
                cmd = S.plan_robot(LV, r, mine, ball, bv, rob, role, base, team)
            else:
                sk = SKILLS[skills[self.order.index(r)]]
                if sk in ("rush", "cover"):
                    cmd = rush_cover(sk, r, mine, ball, rob, avoid)
                else:
                    lv, role, ref = self.skill(skills[self.order.index(r)], r, mine, ball, bv, rob, base)
                    cmd = S.plan_robot(lv, r, mine, ball, bv, rob, role, ref, team)
            if cmd is not None and (cmd["type"] == "kick" or cmd != w.prog[r]):
                out[r] = cmd
        return out

    def skill(self, s, me, mine, ball, bv, rob, base):
        """(planner parameters, role, ref) of skill s for robot `me` (team frame)."""
        name = SKILLS[s]
        own = np.array([-S.HALF_L, 0.0])
        p = np.asarray(rob[me]["xy"], float)
        face_ball = math.atan2(ball[1] - p[1], ball[0] - p[0])
        if name == "strike":
            return LV, "striker", base
        if name == "strike_left":
            return LV, "striker", dict(base, aim_point=(S.HALF_L, 0.7))
        if name == "strike_right":
            return LV, "striker", dict(base, aim_point=(S.HALF_L, -0.7))
        if name == "strike_fast":
            return LV_FAST, "striker", base
        if name == "dribble":
            return LV, "striker", dict(base, aim_point=(S.HALF_L, 0.0), pass_power=0.0)
        if name == "support":
            return LV, "support", base
        if name == "defend":                            # on the line from the ball to the own goal, near the goal
            spot = own + 0.25 * (ball - own)
            spot[0] = max(spot[0], -S.HALF_L + 0.6)
            return LV, "receive", dict(base, spot=spot, face=face_ball)
        if name == "block":                             # goal side of the ball, in the shot's lane
            u = own - ball
            spot = ball + 0.8 * u / max(float(np.hypot(*u)), 1e-6)
            return LV, "receive", dict(base, spot=spot, face=face_ball)
        if name == "mark":                              # goal side of the opponent nearest the own goal
            opps = [o for o in rob if o[0] != me[0] and not rob[o]["bench"]]
            if not opps:
                return LV, "support", base
            o = min(opps, key=lambda o: (float(np.hypot(*(np.asarray(rob[o]["xy"]) - own))), o))
            q = np.asarray(rob[o]["xy"], float)
            u = own - q
            spot = q + 0.6 * u / max(float(np.hypot(*u)), 1e-6)
            return LV, "receive", dict(base, spot=spot, face=face_ball)
        # press: straight at the ball
        return LV, "receive", dict(base, spot=ball.copy(), face=face_ball)


# ------------------------------------------------------------------ the built-in seat (duel world, seat B)
def snapshot(w, team):
    """What the RL opponent reads, as a JSON-able dict (SoccerMatch.builtin_truth): the true state of World.truth with
    the robots' velocities (team frame), the referee's information and the restart state the skills need."""
    tr = w.truth(team)
    rob = {}
    for r, st in tr["robots"].items():
        v = S.to_team(team, w.rob[r].vel(w.d))
        rob[r] = dict(xy=[float(x) for x in st["xy"]], yaw=float(st["yaw"]), fallen=bool(st["fallen"]),
                      bench=bool(st["bench"]), kicking=bool(st["kicking"]), v=[float(v[0]), float(v[1])])
    fk = None if not w.fk else dict(team=w.fk["team"], in_play=bool(w.fk["in_play"]), kind=w.fk["kind"],
                                    spot=[float(x) for x in w.fk["spot"]])
    pso = None
    if w.pso:
        cur = w.pso.get("cur") or {}
        pso = dict(cur=dict(n=cur.get("n", 0), striker=cur.get("striker"), keeper=cur.get("keeper")))
    ko = None if not w.ko else dict(team=w.ko["team"], in_play=bool(w.ko["in_play"]),
                                    touched_outside=bool(w.ko["touched_outside"]))
    return dict(team=team, k=int(w.k), seed=int(w.seed), state=w.state, ko=ko, fk=fk, pso=pso,
                truth=dict(ball=[float(x) for x in tr["ball"]], ball_v=[float(x) for x in tr["ball_v"]], k=int(w.k),
                           robots=rob),
                referee=w.referee(team))


class SnapWorld:
    """The attributes of soccer.World that RLCoach reads, from a snapshot() dict (the built-in seat's view)."""

    def __init__(self, snap, prog):
        self.k, self.seed, self.state = snap["k"], snap["seed"], snap["state"]
        self.ko, self.fk, self.pso = snap["ko"], snap["fk"], snap["pso"]
        tr = snap["truth"]
        self._tr = dict(ball=np.asarray(tr["ball"], float), ball_v=np.asarray(tr["ball_v"], float), k=tr["k"],
                        robots={r: dict(st, xy=np.asarray(st["xy"], float)) for r, st in tr["robots"].items()})
        self._ref = snap["referee"]
        self.prog = prog

    def truth(self, team):
        return self._tr

    def referee(self, team):
        return self._ref


class BuiltinRL:
    """The RL opponent as a seat's player (core/client.py contract, built_in seat: view["truth"] = snapshot()). One
    command per call (the core's player loop takes one body per call): a kick first, else the lead robot's, the other
    robot's when it has waited STARVE calls with a changed command; a robot's kick is not re-sent while it may not have started yet (KICK_HOLD control steps)."""
    KICK_HOLD = 5
    STARVE = 3

    def __init__(self, team, robots, version="v2"):
        self.coach = RLCoach(team, version=version)
        self.robots = [team + str(r) for r in robots]
        self.last = {r: dict(type="stand") for r in self.robots}
        self.kick_k = {r: -10 ** 9 for r in self.robots}
        self.rr = 0
        self.calls = 0
        self.sent_call = {}
        self.dk = None

    def act(self, snap):
        w = SnapWorld(snap, self.last)
        c = self.coach
        kd = w.k // DECIDE_EVERY
        c.update_order(w.truth(c.team), w.k)
        if c.skills is None or kd != self.dk:            # a decision at the first view of each 0.2 s period
            self.dk = kd
            c.obs = observe(w, c.team, w.truth(c.team), c.skills, c.order)
            c.skills = list(c.policy(c.obs))
        pol, c.policy = c.policy, None                   # decide() without a new decision
        try:
            want = c.decide(w)
        finally:
            c.policy = pol
        todo = [r for r in self.robots if r in want and not (want[r]["type"] == "kick" and
                                                             w.k - self.kick_k[r] < self.KICK_HOLD)]
        if not todo:
            return None
        # one command per call: a kick first, then the lead robot (the one playing the ball), unless the other one has
        # waited STARVE calls with a changed command
        self.calls += 1
        lead = c.order[0]
        kicks = [x for x in todo if want[x]["type"] == "kick"]
        starved = [x for x in todo if x != lead and self.calls - self.sent_call.get(x, 0) >= self.STARVE]
        r = kicks[0] if kicks else starved[0] if starved else (lead if lead in todo else todo[0])
        self.sent_call[r] = self.calls
        self.last[r] = want[r]
        if want[r]["type"] == "kick":
            self.kick_k[r] = w.k
        return dict(want[r], entity=r[1:])
