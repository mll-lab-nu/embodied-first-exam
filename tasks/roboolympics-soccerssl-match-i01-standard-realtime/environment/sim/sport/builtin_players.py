"""soccer_ssl's built-in players (wheeled 5 v 5 soccer, RoboCup SSL Division B): the reference team, the simple
baselines of step 4, and the shared behaviour the scripted opponents (opponents/) are built from. One file with
numpy and the standard library only: task generation copies it into a task's solution/ as the oracle, and the
camera reference must work from the observation alone.

Everything is in the team's frame (skill_api.py): the team attacks +x, its goal is at x = -4.5. A team is called with
a TeamView every decision tick and returns commands [(number, skill, args)]; `TeamPlayer` wraps a team as an
act(observation) player (a `batch` act per call).

  Reference   passes, receives (dribbler on, standing on the ball's path), runs into open space, shoots, defends
              with distinct roles, keeps goal (class Reference; the decision procedure is in its docstring).
              Perception: the overhead camera tiles of the observation through the colour detector below
              (detect_tiles), or the truth (screen/ world-level batches, the scripted opponents).
  AllChase, Fixed, ShootOnly, Random, Idle   simple baselines (class docstrings).

Physical numbers are the published ones the world uses (rulebook §2.1; bodies/ssl_robot/body.toml) as any team would
know them; the ball's two-phase model was measured in the world (olympiad_review/screening/soccer_ssl_players_zh.md).
"""
from __future__ import annotations

import itertools
import math
from collections import deque
from dataclasses import dataclass, field, replace

import numpy as np

# ==============================================================================================================
# geom.py
# ==============================================================================================================


# ------------------------------------------------------------------------------------------------ the field (§2.1)
HALF_L, HALF_W = 4.5, 3.0
WALL_X, WALL_Y = 4.8, 3.3
GOAL_HALF_W = 0.5
DA_DEPTH, DA_HALF_W = 1.0, 1.0
CENTER_R = 0.5
ROBOT_R = 0.09
BALL_R = 0.0215
KICK_REACH = 0.09          # robot centre -> ball centre when the ball rests at the dribbler (body.py x_ball_rest)
STOP_DIST = 0.5 + ROBOT_R  # §5.1.1 / §8.4.3.1: robots keep 0.5 m (nearest side) from the ball in stop / free kicks
DA_KEEPOUT = 0.2 + ROBOT_R  # §8.4.1.1
OWN_GOAL = (-HALF_L, 0.0)
OPP_GOAL = (HALF_L, 0.0)

# ------------------------------------------------------------------------------------------------ the robot (body.toml)
V_MAX, A_MAX = 3.0, 3.0
STOP_SPEED = 1.5            # §5.1.1 (agent's own duty, interfaces §0)
KICK_MAX_LEGAL = 6.5        # §8.4.2.2; the kicker's speed error is 3 % (sigma), so aim below
KICK_SAFE = 6.0
RECEIVE_MAX = 4.0           # the dribbler holds a ball arriving up to ~4.5 m/s (A's lab: 10/10 at 4 m/s)

# ------------------------------------------------------------------------------------------------ the ball (measured)
SLIDE_DEC = 3.4             # m/s^2 while sliding (sliding friction 0.35 g)
ROLL_DEC = 0.45             # m/s^2 rolling
ROLL_RATIO = 5.0 / 7.0      # a kicked ball slides until its speed falls to 5/7 of the launch speed


def wrap(a: float) -> float:
    return (a + math.pi) % (2.0 * math.pi) - math.pi


def dist(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def unit(dx, dy):
    n = math.hypot(dx, dy)
    return (dx / n, dy / n) if n > 1e-9 else (1.0, 0.0)


def in_field(p, margin=0.0) -> bool:
    return abs(p[0]) <= HALF_L - margin and abs(p[1]) <= HALF_W - margin


def own_da_dist(p) -> float:
    """distance from p to the own defense area (0 inside)."""
    dx = max(-HALF_L - p[0], 0.0, p[0] - (-HALF_L + DA_DEPTH))
    dy = max(abs(p[1]) - DA_HALF_W, 0.0)
    return math.hypot(dx, dy)


def opp_da_dist(p) -> float:
    return own_da_dist((-p[0], p[1]))


def push_out_of_own_da(p, margin=0.12):
    """a field robot's target kept outside its own defense area (a defender touching the ball fully inside it gives a
    penalty, §8.4.1.5): pushed out along the shorter way."""
    x, y = p
    if own_da_dist(p) >= ROBOT_R + margin:
        return p
    xr = -HALF_L + DA_DEPTH + ROBOT_R + margin
    yr = DA_HALF_W + ROBOT_R + margin
    if (xr - x) < (yr - abs(y)) or abs(y) < DA_HALF_W * 0.6:
        return (xr, y)
    return (x, math.copysign(yr, y if y != 0 else 1.0))


def push_out_of_opp_da(p, margin=0.12):
    q = push_out_of_own_da((-p[0], p[1]), margin)
    return (-q[0], q[1])


def clamp_field(p, margin=0.12):
    return (max(-HALF_L - 0.2, min(HALF_L + 0.2, p[0])), max(-HALF_W - 0.2, min(HALF_W + 0.2, p[1])))


def clamp_play(p, margin=0.1):
    return (max(-HALF_L + margin, min(HALF_L - margin, p[0])), max(-HALF_W + margin, min(HALF_W - margin, p[1])))


# ------------------------------------------------------------------------------------------------ ball model
class BallPath:
    """the ball's predicted ground path from (p, v) with the two-phase model: sliding at SLIDE_DEC down to v_switch,
    then rolling at ROLL_DEC (sim/ball.py, measured). `sliding` says whether the ball still slides and v_switch
    where it stops sliding. dec_scale / slide=False are the capability impairments (A2)."""

    def __init__(self, p, v, sliding=False, v_switch=0.0, roll_dec=ROLL_DEC, slide_dec=SLIDE_DEC):
        self.p = (float(p[0]), float(p[1]))
        sp = math.hypot(v[0], v[1])
        self.speed = sp
        self.d = (v[0] / sp, v[1] / sp) if sp > 1e-6 else (1.0, 0.0)
        self.rd, self.sd = roll_dec, slide_dec
        if sliding and sp > v_switch > 0:
            self.t1 = (sp - v_switch) / slide_dec
            self.s1 = sp * self.t1 - 0.5 * slide_dec * self.t1 ** 2
            self.v1 = v_switch
        else:
            self.t1, self.s1, self.v1 = 0.0, 0.0, sp
        self.t_stop = self.t1 + self.v1 / roll_dec
        self.s_stop = self.s1 + self.v1 ** 2 / (2 * roll_dec)

    def s_at(self, t):
        if t <= 0:
            return 0.0
        if t < self.t1:
            return self.speed * t - 0.5 * self.sd * t * t
        t2 = min(t - self.t1, self.v1 / self.rd)
        return self.s1 + self.v1 * t2 - 0.5 * self.rd * t2 * t2

    def v_at(self, t):
        if t < self.t1:
            return self.speed - self.sd * t
        return max(0.0, self.v1 - self.rd * (t - self.t1))

    def at(self, t):
        s = self.s_at(t)
        return (self.p[0] + self.d[0] * s, self.p[1] + self.d[1] * s)

    def t_of_s(self, s):
        """time when the ball has travelled s (inf if it stops before)."""
        if s <= 0:
            return 0.0
        if s > self.s_stop:
            return math.inf
        if s <= self.s1 and self.t1 > 0:
            a = self.sd
            disc = self.speed ** 2 - 2 * a * s
            return (self.speed - math.sqrt(max(disc, 0.0))) / a
        s2 = s - self.s1
        disc = self.v1 ** 2 - 2 * self.rd * s2
        return self.t1 + (self.v1 - math.sqrt(max(disc, 0.0))) / self.rd


def kick_path(p, direction, v0, roll_dec=ROLL_DEC, slide_dec=SLIDE_DEC, model_slide=True):
    """the path of a ball kicked flat at v0 along direction from p."""
    return BallPath(p, (direction[0] * v0, direction[1] * v0), sliding=model_slide, v_switch=ROLL_RATIO * v0,
                    roll_dec=roll_dec, slide_dec=slide_dec)


def pass_speed(distance, arrive=2.6, vmin=1.6, vmax=KICK_SAFE, roll_dec=ROLL_DEC, model_slide=True):
    """the kick speed whose ball arrives at `distance` with about `arrive` m/s (bisection on the model)."""
    lo, hi = vmin, vmax
    def arr(v0):
        P = kick_path((0, 0), (1, 0), v0, roll_dec=roll_dec, model_slide=model_slide)
        t = P.t_of_s(distance)
        return -1.0 if math.isinf(t) else P.v_at(t)
    if arr(hi) < arrive:
        return hi
    if arr(lo) >= arrive:
        return lo
    for _ in range(25):
        mid = 0.5 * (lo + hi)
        if arr(mid) < arrive:
            lo = mid
        else:
            hi = mid
    return hi


# ------------------------------------------------------------------------------------------------ robot motion
def reach_time(p, v, q, vmax=V_MAX, amax=A_MAX, slack=0.0):
    """time for a robot at p moving at v to reach q (within `slack` metres), no need to stop there: a bang-bang
    estimate along the line with the initial velocity's component, plus braking the sideways component."""
    dx, dy = q[0] - p[0], q[1] - p[1]
    d = math.hypot(dx, dy) - slack
    if d <= 0:
        return 0.0
    ux, uy = dx / (d + slack), dy / (d + slack)
    u = v[0] * ux + v[1] * uy
    w = abs(-v[0] * uy + v[1] * ux)
    t0 = 0.0
    if u < 0:
        t0 = -u / amax
        d += u * u / (2 * amax)
        u = 0.0
    u = min(u, vmax)
    da = (vmax * vmax - u * u) / (2 * amax)
    if d <= da:
        t = (-u + math.sqrt(u * u + 2 * amax * d)) / amax
    else:
        t = (vmax - u) / amax + (d - da) / vmax
    return t0 + t + 0.5 * w / amax


def intercept(p, v, path: BallPath, react=0.0, vmax=V_MAX, horizon=4.0, dt=0.04, slack=0.08, field_only=True):
    """the earliest (t, point) at which a robot (p, v) can be at the ball on `path`; None if not within the horizon
    or the ball leaves the field first; for a stopping ball the rest point."""
    t = 0.0
    while t <= horizon:
        b = path.at(t)
        if field_only and not in_field(b, -0.03):
            return None
        if reach_time(p, v, b, vmax=vmax, slack=slack) + react <= t:
            return t, b
        if t > path.t_stop:
            break
        t += dt
    b = path.at(path.t_stop)
    if field_only and not in_field(b, -0.03):
        return None
    tr = reach_time(p, v, b, vmax=vmax, slack=slack) + react
    if tr <= horizon + 2.0:
        return max(tr, path.t_stop), b
    return None


def lane_margin(path: BallPath, length, robots, react=0.0, vmax=V_MAX, start=0.25, step=0.2, tail=0.15,
                radius=ROBOT_R + BALL_R + 0.02):
    """the smallest time margin (s) by which any of `robots` [(p, v)] would be late to block the ball on `path` over
    its first `length` metres (from `start`, up to length - tail): positive = the lane is open."""
    best = math.inf
    s = start
    while s <= length - tail + 1e-9:
        tb = path.t_of_s(s)
        if math.isinf(tb):
            return -1.0
        b = path.at(tb)
        for (p, v) in robots:
            m = reach_time(p, v, b, vmax=vmax, slack=radius) + react - tb
            if m < best:
                best = m
        s += step
    return best


def point_to_segment(p, a, b):
    """distance from p to the segment a-b and the parameter along it."""
    ax, ay = b[0] - a[0], b[1] - a[1]
    L2 = ax * ax + ay * ay
    if L2 < 1e-12:
        return dist(p, a), 0.0
    u = max(0.0, min(1.0, ((p[0] - a[0]) * ax + (p[1] - a[1]) * ay) / L2))
    return math.hypot(a[0] + u * ax - p[0], a[1] + u * ay - p[1]), u

# ==============================================================================================================
# view.py
# ==============================================================================================================



TEAMS = ("blue", "yellow")


def other(team):
    return "yellow" if team == "blue" else "blue"


@dataclass
class Bot:
    p: tuple
    yaw: float
    v: tuple = (0.0, 0.0)
    w: float = 0.0
    on: bool = True
    beam: bool = False          # own robots only: the break beam (own sensor)
    engaged: bool = False       # own robots only: the dribbler holds a ball (own sensor)
    charge: float = 1.0         # own robots only: the kicker's stored-energy fraction


@dataclass
class Ref:
    state: str = "RUNNING"      # STOP, PREPARE_KICKOFF, KICKOFF, FREE_KICK, PREPARE_PENALTY, PENALTY, RUNNING
    ours: bool | None = None    # the command is for us (True), them (False), nobody (None)
    next_cmd: str | None = None
    next_ours: bool | None = None
    placement: tuple = (0.0, 0.0)
    stage: str = "FIRST_HALF"
    half: int = 1
    score_us: int = 0
    score_them: int = 0
    time_left: float = 300.0
    allowed: int = 5


@dataclass
class TeamView:
    t: float
    team: str
    sign: int
    ball: tuple                 # (x, y)
    ball_v: tuple               # (vx, vy)
    ball_z: float = 0.0215
    ball_seen: bool = True
    own: dict = field(default_factory=dict)
    opp: dict = field(default_factory=dict)
    ref: Ref = field(default_factory=Ref)

    def own_on(self):
        return {k: r for k, r in self.own.items() if r.on}

    def opp_on(self):
        return {k: r for k, r in self.opp.items() if r.on}


def geometric_beam(r: "Bot", ball) -> bool:
    """whether the ball sits at robot r's dribbler, judged from positions (for a robot whose own break beam is not in
    the view: the scripted opponents read the truth, which has no robot sensors)."""
    dx, dy = ball[0] - r.p[0], ball[1] - r.p[1]
    d = math.hypot(dx, dy)
    return d < 0.102 and abs(wrap(math.atan2(dy, dx) - r.yaw)) < 0.3


def ref_from_view(R: dict) -> Ref:
    """the referee's information as World.referee_view / the observation give it (team frame, us / them)."""
    ft = R.get("for_team")
    nc = R.get("next_command")
    pl = R.get("placement") or (0.0, 0.0)
    sc = R.get("score") or {}
    al = R.get("allowed_robots") or {}
    return Ref(state=R.get("command", "RUNNING"), ours=None if ft is None else ft == "us",
               next_cmd=nc[0] if nc else None, next_ours=None if not nc or nc[1] is None else nc[1] == "us",
               placement=(float(pl[0]), float(pl[1])), stage=R.get("stage", ""), half=int(R.get("half", 1)),
               score_us=int(sc.get("us", 0)), score_them=int(sc.get("them", 0)),
               time_left=float(R.get("time_left", 0.0)), allowed=int(al.get("us", 5)))


def view_from_truth(truth: dict, own_states: dict | None = None) -> TeamView:
    """World.truth_view(team) (team frame) as a TeamView. own_states {number: World.own_state} adds the own robots'
    sensors (break beam, capacitor); without them the beam is judged from positions."""
    b = truth["ball"]
    ball = (float(b["pos"][0]), float(b["pos"][1]))
    own, opp = {}, {}
    for src, dst in ((truth["us"], own), (truth["them"], opp)):
        for n, r in src.items():
            if not r.get("on_field", True) or "pose" not in r:
                dst[int(n)] = Bot((9.0, 9.0), 0.0, on=False)
                continue
            x, y, yaw = r["pose"]
            vx, vy, w = r["vel"]
            dst[int(n)] = Bot((float(x), float(y)), float(yaw), (float(vx), float(vy)), float(w), True)
    for n, r in own.items():
        st = (own_states or {}).get(n) or (own_states or {}).get(str(n))
        if st is not None and st.get("on_field", True):
            r.beam = bool(st.get("ball_in_beam", False))
            r.charge = float(st.get("kicker_charge", 1.0))
        elif r.on:
            r.beam = geometric_beam(r, ball)
    R = truth.get("referee") or {}
    return TeamView(t=float(truth["t"]), team=str(truth.get("team", "")), sign=int(R.get("attack_sign", 1)),
                    ball=ball, ball_v=(float(b["vel"][0]), float(b["vel"][1])), ball_z=float(b["pos"][2]),
                    own=own, opp=opp, ref=ref_from_view(R))

# ==============================================================================================================
# base.py
# ==============================================================================================================




KEEPER = 0


class BallTracker:
    """the ball's state for prediction: whether it still slides after a kick (the speed fell faster than rolling
    friction explains, or it jumped) and the speed at which it starts rolling."""

    def __init__(self):
        self.prev = None
        self.sliding = False
        self.v_switch = 0.0

    def update(self, t, p, v):
        sp = math.hypot(*v)
        if self.prev is not None:
            t0, p0, v0 = self.prev
            sp0 = math.hypot(*v0)
            dt = max(t - t0, 1e-3)
            turned = sp > 0.3 and sp0 > 0.3 and (v[0] * v0[0] + v[1] * v0[1]) / (sp * sp0) < 0.94
            if sp > sp0 + 0.4 or (turned and sp > 1.0):
                self.sliding, self.v_switch = True, ROLL_RATIO * sp
            elif self.sliding and sp <= self.v_switch + 0.02:
                self.sliding = False
            if dt > 0.5:
                self.sliding = False
        self.prev = (t, p, v)

    def path(self, p, v, roll_dec=ROLL_DEC, model_slide=True):
        return BallPath(p, v, sliding=self.sliding and model_slide, v_switch=self.v_switch, roll_dec=roll_dec)


class TeamBase:
    """See the module docstring. Parameters common to all teams:
      vmax          the robots' speed cap in play (m/s; the robot's own limit is 3)
      react         seconds added to the robots' reach times when comparing who gets the ball first
      kick_speed    shot speed (m/s)
    """

    name = "base"

    def __init__(self, team: str = "blue", seed: int = 0, vmax: float = V_MAX, react: float = 0.0,
                 kick_speed: float = KICK_SAFE, roll_dec: float = ROLL_DEC, model_slide: bool = True, rng=None,
                 target_eps: float = 0.0):
        self.team = team
        self.rng = rng if rng is not None else np.random.default_rng(seed)
        self.vmax, self.react, self.kick_speed = vmax, react, kick_speed
        self.roll_dec, self.model_slide = roll_dec, model_slide
        self.ball = BallTracker()
        self.cmds: list = []
        self.sent_move: dict = {}
        self.sent_drib: dict = {}
        self.locked_until: dict = {}     # number -> time: the set-piece kicker keeps off the ball (§8.2 double touch)
        self.hold_start: dict = {}       # number -> ball position when this robot got the ball (§8.4.1.8: 1 m)
        self.sp = None                   # the set piece being taken: dict(num, aim, speed, mode, phase)
        self.last_kick: dict = {}
        self.target_eps = float(target_eps)
        self.kick_lead = 0.08            # s from an observation to the kick taking effect (vision + command delay)
        self.kick_window = 0.15          # s a kick stays armed (it fires when the ball blocks the beam)
        self.stats = dict(kicks=0, passes=0, shots=0, chips=0, clears=0, pass_ok=0, pass_lost=0)
        self.v: TeamView | None = None

    # ------------------------------------------------------------------------------------------------ entry
    def update(self, view: TeamView) -> list:
        self.v = view
        self.cmds = []
        self.ball.update(view.t, view.ball, view.ball_v)
        for k, r in view.own.items():
            if r.on:
                self.track_hold(k)
        st = view.ref.state
        if st == "RUNNING":
            self.sp = None
            self.play()
        elif st == "STOP":
            self.sp = None
            self.stop_play()
        elif st == "PREPARE_KICKOFF":
            self.prepare_kickoff()
        elif st in ("KICKOFF", "FREE_KICK"):
            if view.ref.ours:
                self.take_set_piece()
            else:
                self.defend_set_piece()
        elif st in ("PREPARE_PENALTY", "PENALTY"):
            self.penalty()
        return self.cmds

    # ------------------------------------------------------------------------------------------------ skills
    STOP_V = 1.2           # m/s: under the 1.5 m/s of a stop (§5.1.1) with the tracking's overshoot
    NEAR_V = 1.2           # m/s: approaching another robot (a crash is > 1.5 m/s difference, §8.4.2.3)

    def move(self, n, p, theta, vmax=None, avoid=True, ball_obstacle=False, da=True, t=None, ball_clear=None):
        """move robot n to p facing theta (team frame), detouring around the robots (and the ball when asked) in the
        way; field robots stay out of both defense areas. A speed cap below the robot's own (`vmax`, a stop, a robot
        close ahead) is a carrot: the target at most v^2 / 2a ahead, re-sent every tick, so the robot never plans to
        go faster than the cap."""
        r = self.v.own[n]
        st = self.v.ref.state
        if da and n != KEEPER:
            p = push_out_of_own_da(p)
        if da:
            p = push_out_of_opp_da(p, margin=0.05 if st == "RUNNING" else 0.45)
        p = clamp_field(p)
        if self.target_eps:  # replicas: a decision-irrelevant 0.1 mm nudge that only makes the chaos diverge
            p = (p[0] + self.target_eps, p[1])
        if ball_clear is None and (st in ("STOP", "PREPARE_KICKOFF", "PREPARE_PENALTY") or
                                   (st in ("KICKOFF", "FREE_KICK") and self.v.ref.ours is False)):
            ball_clear = STOP_DIST + 0.25
        if avoid:
            p = self._detour(n, r.p, p, ball_obstacle, ball_clear)
            if da and n != KEEPER:
                p = push_out_of_own_da(p)
            if da:
                p = push_out_of_opp_da(p, margin=0.05 if st == "RUNNING" else 0.45)
        if da and st != "RUNNING":
            if opp_da_dist(r.p) < 0.42:
                # caught near the opponent area when the game stops: straight out, the shortest way (0.2 m within
                # 2 s, §8.4.1.1)
                p = self._da_exit(r.p)
                avoid = False
            else:
                p = self._around_opp_da(r.p, p)
        vmax = self.vmax if vmax is None else vmax
        if st == "STOP":
            vmax = min(vmax, self.STOP_V)
        d = dist(r.p, p)
        if d > 0.05 and n != KEEPER:
            # crash guard (§8.4.2.3: > 1.5 m/s closing speed at contact): near another robot, moving towards it,
            # keep the closing speed under ~1.1 m/s, whatever the other robot does
            ux, uy = unit(p[0] - r.p[0], p[1] - r.p[1])
            for k, o in list(self.v.own.items()) + [(-1 - k, o) for k, o in self.v.opp.items()]:
                if k == n or not o.on:
                    continue
                rx, ry = o.p[0] - r.p[0], o.p[1] - r.p[1]
                dd = math.hypot(rx, ry)
                if dd < 0.6 and dd > 1e-6 and (rx * ux + ry * uy) / dd > 0.3:
                    towards = max(0.0, -(o.v[0] * rx + o.v[1] * ry) / dd)
                    vmax = min(vmax if vmax is not None else self.vmax, max(0.3, 1.1 - towards))
        if avoid and d > 0.1:
            ux, uy = unit(p[0] - r.p[0], p[1] - r.p[1])
            for k, o in list(self.v.own.items()) + [(-1 - k, o) for k, o in self.v.opp.items()]:
                if k == n or not o.on:
                    continue
                rx, ry = o.p[0] - r.p[0], o.p[1] - r.p[1]
                along = rx * ux + ry * uy
                if 0.0 < along < 0.75 and abs(-rx * uy + ry * ux) < 0.24 and dist(o.p, p) > 0.05:
                    vmax = min(vmax, self.NEAR_V)
                    break
        last = self.sent_move.get(n)
        if vmax < V_MAX - 1e-6:
            L = max(0.08, 0.9 * vmax * vmax / (2 * A_MAX))
            if d > L:
                # the same destination and the robot still well short of the last carrot: nothing new to send
                if last is not None and len(last) > 5 and dist(last[5], p) < 0.05 and abs(wrap(last[2] - theta)) < 0.05 \
                        and dist(r.p, last[:2]) > 0.5 * L and self.v.t - last[4] < 0.5:
                    return
                dest = p
                p = (r.p[0] + (p[0] - r.p[0]) * L / d, r.p[1] + (p[1] - r.p[1]) * L / d)
                if da and opp_da_dist(r.p) >= 0.2:
                    p = push_out_of_opp_da(p, margin=0.05)
                self.sent_move[n] = (p[0], p[1], theta, None, self.v.t, dest)
                self.cmds.append((n, "move", dict(x=round(p[0], 4), y=round(p[1], 4), theta=round(wrap(theta), 4))))
                return
        tt = t
        key = (p[0], p[1], theta, tt, self.v.t)
        if last is not None and abs(last[0] - p[0]) < 0.015 and abs(last[1] - p[1]) < 0.015 \
                and abs(wrap(last[2] - theta)) < 0.02 and ((tt is None) == (last[3] is None)) \
                and (tt is None or abs(tt - last[3]) < 0.1) and self.v.t - last[4] < 0.5:
            return
        self.sent_move[n] = key
        a = dict(x=round(p[0], 4), y=round(p[1], 4), theta=round(wrap(theta), 4))
        if tt is not None:
            a["t"] = round(tt, 3)
        self.cmds.append((n, "move", a))

    @staticmethod
    def _da_exit(p, keep=0.6):
        """the nearest point `keep` metres outside the opponent defense area (team frame)."""
        x0, y0 = HALF_L - DA_DEPTH, DA_HALF_W
        if p[0] > HALF_L - 0.12 and abs(p[1]) < GOAL_HALF_W + 0.1:
            return (HALF_L - 0.45, max(-0.3, min(0.3, p[1])))   # in the goal mouth: out through the front first
        cx = min(max(p[0], x0), HALF_L)
        cy = min(max(p[1], -y0), y0)
        if p[0] < x0 or abs(p[1]) > y0:      # outside: away from the nearest point of the area
            ux, uy = unit(p[0] - cx, p[1] - cy)
            return (cx + ux * keep, cy + uy * keep)
        # inside: out through the nearer side (front or flank)
        if (p[0] - x0) < (y0 - abs(p[1])):
            return (x0 - keep, p[1])
        return (p[0], math.copysign(y0 + keep, p[1] if p[1] else 1.0))

    @staticmethod
    def _around_opp_da(a, b, keep=0.42):
        """a stop or a set piece: robots keep 0.2 m from the opponent defense area (§8.4.1.1); a straight path that
        passes closer goes by the area's near corner first."""
        L = dist(a, b)
        k = max(1, int(L / 0.1))
        for i in range(1, k):
            q = (a[0] + (b[0] - a[0]) * i / k, a[1] + (b[1] - a[1]) * i / k)
            if opp_da_dist(q) < keep:
                side = 1.0 if (b[1] if abs(b[1]) > 0.3 else a[1]) >= 0 else -1.0
                c = (HALF_L - DA_DEPTH - keep - 0.05, side * (DA_HALF_W + keep + 0.05))
                if dist(a, c) > 0.15:
                    return c
                return b
        return b

    def dribble(self, n, rpm):
        if self.sent_drib.get(n) == rpm:
            return
        self.sent_drib[n] = rpm
        self.cmds.append((n, "dribble", dict(rpm=rpm)))

    def kick(self, n, speed, mode="flat", armed_for=None):
        if armed_for is None:
            armed_for = self.kick_window
        self.last_kick[n] = self.v.t
        self.cmds.append((n, "kick", dict(speed=round(float(speed), 3), mode=mode, armed_for=armed_for)))
        self.stats["kicks"] += 1

    def _detour(self, n, a, b, ball_obstacle, ball_clear=None):
        if dist(a, b) < 0.2:
            return b
        obst = [(r.p, 0.24) for k, r in self.v.own.items() if k != n and r.on] + \
               [(r.p, 0.24) for r in self.v.opp.values() if r.on]
        if ball_clear:
            obst.append((self.v.ball, ball_clear))
            pl = self.v.ref.placement
            if pl is not None and self.v.ref.state == "STOP" and dist(pl, self.v.ball) > 0.05:
                obst.append((tuple(pl), ball_clear))
        elif ball_obstacle:
            obst.append((self.v.ball, 0.2))
        best = None
        for o, rad in obst:
            d, u = point_to_segment(o, a, b)
            if d < rad and 0.0 < u < 1.0 and dist(o, b) > rad - 0.02 and dist(o, a) > min(0.12, rad - 0.05):
                if best is None or u < best[1]:
                    best = (o, u, rad)
        if best is None:
            return b
        o, _, rad = best
        dx, dy = unit(b[0] - a[0], b[1] - a[1])
        px, py = -dy, dx
        side = (o[0] - a[0]) * px + (o[1] - a[1]) * py
        s = -1.0 if side > 0 else 1.0
        off = rad + 0.14
        q = (o[0] + s * px * off - dx * 0.05, o[1] + s * py * off - dy * 0.05)
        if not in_field(q, -0.2):
            q = (o[0] - s * px * off, o[1] - s * py * off)
        return q

    # ------------------------------------------------------------------------------------------------ helpers
    def has_ball(self, n):
        r = self.v.own[n]
        return r.engaged or r.beam

    def path(self):
        return self.ball.path(self.v.ball, self.v.ball_v, roll_dec=self.roll_dec, model_slide=self.model_slide)

    def opp_list(self, exclude=()):
        return [(r.p, r.v) for k, r in self.v.opp.items() if r.on and k not in exclude]

    def opp_with_ball(self):
        """the opponent controlling the ball (close in front of it), else None."""
        b = self.v.ball
        for k, r in self.v.opp.items():
            if not r.on:
                continue
            dx, dy = b[0] - r.p[0], b[1] - r.p[1]
            d = math.hypot(dx, dy)
            if d < 0.14 and abs(wrap(math.atan2(dy, dx) - r.yaw)) < 0.7 and \
                    math.hypot(self.v.ball_v[0] - r.v[0], self.v.ball_v[1] - r.v[1]) < 1.0:
                return k
        return None

    def kick_ready(self, n, speed):
        need = (speed / 8.5) ** 2
        return self.v.own[n].charge >= need + 0.01

    def collect(self, n, aim=None, rpm=3000, vmax=None):
        """go and get the ball: on a moving ball, stand on its path facing it; on a slow ball, drive into it facing
        it (turning towards `aim` on the way when the ball is not between)."""
        r = self.v.own[n]
        b, bv = self.v.ball, self.v.ball_v
        sp = math.hypot(*bv)
        if n != KEEPER and (opp_da_dist(b) < 0.25 or own_da_dist(b) < 0.05):
            # the ball at the opponent defense area: touching it there is a foul (§8.4.2.1); in the own area it is
            # the keeper's. Wait outside, between the ball and the own goal.
            ux, uy = unit(-HALF_L - b[0], -b[1])
            self.move(n, (b[0] + ux * 0.6, b[1] + uy * 0.6), math.atan2(-uy, -ux), vmax=vmax)
            self.dribble(n, 0)
            return
        self.dribble(n, rpm)
        if sp > 0.6:
            P = self.path()
            d = P.d
            rel = (r.p[0] - b[0]) * d[0] + (r.p[1] - b[1]) * d[1]   # how far along the path the robot is
            lat = abs(-(r.p[0] - b[0]) * d[1] + (r.p[1] - b[1]) * d[0])
            if 0.0 < rel < 1.2 and lat < 0.5:
                # the ball is about to arrive: only correct sideways onto its line (the kick point on the path),
                # facing it; moving along the line now only makes the robot late
                c = (b[0] + d[0] * (rel + 0.0), b[1] + d[1] * (rel + 0.0))
                self.move(n, c, math.atan2(-d[1], -d[0]), vmax=vmax, avoid=False)
                return
            # aim to be there with ~0.2 s to spare (a robot still moving when the ball arrives misses it)
            it = intercept(r.p, r.v, P, react=0.2, vmax=vmax or self.vmax, field_only=False) or \
                intercept(r.p, r.v, P, react=0.03, vmax=vmax or self.vmax, field_only=False)
            if it is not None:
                t, q = it
                d = P.d
                c = (q[0] + d[0] * KICK_REACH * 0.9, q[1] + d[1] * KICK_REACH * 0.9)
                if dist(r.p, b) < 0.5 and (b[0] - r.p[0]) * d[0] + (b[1] - r.p[1]) * d[1] > 0:
                    c = (b[0] + d[0] * 0.3, b[1] + d[1] * 0.3)  # chasing a ball rolling away: catch up
                    self.move(n, c, math.atan2(b[1] - r.p[1], b[0] - r.p[0]), vmax=vmax, avoid=True)
                    return
                self.move(n, c, math.atan2(-d[1], -d[0]), vmax=vmax, avoid=dist(r.p, c) > 0.5)
                return
        dx, dy = b[0] - r.p[0], b[1] - r.p[1]
        d = math.hypot(dx, dy)
        th = math.atan2(dy, dx)
        if aim is not None and d > 0.35:
            ad = math.atan2(aim[1] - b[1], aim[0] - b[0])
            if abs(wrap(ad - th)) > 1.2:  # come around: line up behind the ball
                pre = (b[0] - math.cos(ad) * 0.32, b[1] - math.sin(ad) * 0.32)
                self.move(n, pre, ad, vmax=vmax, ball_obstacle=True)
                return
        # an opponent holding the ball: tackle, i.e. come to the ball's free side and stop at touching distance
        # (driving on would push the robot: pushing, §8.4.1.2; arriving fast is crashing, §8.4.2.3)
        holder = None
        for o in self.v.opp.values():
            if o.on and dist(o.p, b) < 0.13:
                holder = o
                break
        if holder is not None:
            ox, oy = unit(b[0] - holder.p[0], b[1] - holder.p[1])
            tgt = (holder.p[0] + ox * 0.19, holder.p[1] + oy * 0.19)
            if dist(r.p, tgt) > 0.45:
                tgt = (holder.p[0] + ox * 0.4, holder.p[1] + oy * 0.4)
                self.move(n, tgt, math.atan2(-oy, -ox), vmax=vmax)
            else:
                self.move(n, tgt, math.atan2(-oy, -ox), vmax=min(vmax or self.vmax, 0.6), avoid=False)
            return
        tgt = (b[0] - math.cos(th) * 0.075, b[1] - math.sin(th) * 0.075)
        self.move(n, tgt, th, vmax=min(vmax or self.vmax, 2.0) if d < 0.6 else vmax, avoid=d > 0.4)

    def turn_and_kick(self, n, target, speed, mode="flat", tol=None):
        """with the ball at the dribbler: turn to `target` (at most ~1 rad per tick so the dribbler keeps the ball)
        and kick when the heading is good. Returns True when the kick was issued."""
        r = self.v.own[n]
        b = self.v.ball
        ang = math.atan2(target[1] - r.p[1], target[0] - r.p[0])
        err = wrap(ang - r.yaw)
        D = max(dist(r.p, target), 0.5)
        if tol is None:
            tol = max(0.02, min(0.07, math.atan2(0.12, D)))
        # the kick fires when the command takes effect (the observation's age plus the command's delay, ~0.05-0.1 s
        # later): the heading then, not now, must be right, and a robot still turning fast is not ready
        err_then = wrap(ang - (r.yaw + r.w * self.kick_lead))
        if abs(err) < tol and abs(err_then) < tol and abs(r.w) < 1.5 and self.kick_ready(n, speed) \
                and (r.beam or r.engaged) and self.v.t - self.last_kick.get(n, -9.0) > 0.3:
            if mode == "flat":  # the kick adds the robot's own velocity: stay under 6.5 m/s (§8.4.2.2)
                fwd = r.v[0] * math.cos(r.yaw) + r.v[1] * math.sin(r.yaw)
                speed = min(speed, KICK_SAFE - max(0.0, fwd))
            self.kick(n, speed, mode)
            self.hold_start.pop(n, None)
            return True
        step = max(-0.9, min(0.9, err))
        self.move(n, r.p, r.yaw + step, avoid=False, da=False)
        self.dribble(n, 3000)
        return False

    def track_hold(self, n):
        """metres the ball has moved since robot n got it (the 1 m dribbling limit, §8.4.1.8)."""
        h = self.hold_start.get(n)
        if not self.has_ball(n):
            if h is not None and (self.v.t - h[1] > 0.25 or dist(self.v.ball, self.v.own[n].p) > 0.16):
                self.hold_start.pop(n, None)
                self.stats["losses"] = self.stats.get("losses", 0) + 1
            return 0.0
        if h is None:
            h = self.hold_start[n] = [self.v.ball, self.v.t, self.v.t]
            self.stats["gains"] = self.stats.get("gains", 0) + 1
        h[1] = self.v.t
        return dist(h[0], self.v.ball)

    # ------------------------------------------------------------------------------------------------ keeper
    def keeper(self, n=KEEPER, react=0.0, clear_fn=None):
        r = self.v.own.get(n)
        if r is None or not r.on:
            return
        b, bv = self.v.ball, self.v.ball_v
        gx = -HALF_L
        # a shot: the ball heading for the goal mouth
        if bv[0] < -0.5:
            tcross = (gx - b[0]) / bv[0]
            ycross = b[1] + bv[1] * tcross
            if 0 < tcross < 2.5 and abs(ycross) < GOAL_HALF_W + 0.15:
                x = gx + 0.12
                y = b[1] + bv[1] * (x - b[0]) / bv[0]
                y = max(-GOAL_HALF_W, min(GOAL_HALF_W, y))
                self.move(n, (x, y), 0.0, da=False, avoid=False, vmax=V_MAX)
                self.dribble(n, 3000)
                return
        # the ball resting in the own defense area: the keeper clears it
        if own_da_dist(b) == 0.0 and math.hypot(*bv) < 0.8 and self.opp_with_ball() is None:
            if self.has_ball(n):
                if clear_fn is not None:
                    clear_fn(n)
                else:
                    self.turn_and_kick(n, (0.0, math.copysign(2.0, -b[1] if abs(b[1]) > 0.1 else 1)), 4.0, "chip")
                return
            self.collect(n, aim=(0.0, 0.0))
            return
        x, y = self.keeper_spot(b)
        self.move(n, (x, y), math.atan2(b[1] - y, b[0] - x), da=False, avoid=False, vmax=V_MAX)
        self.dribble(n, 0)

    def keeper_spot(self, b):
        """where the keeper waits: on the line ball -> goal centre, 0.15-0.45 m out, inside the area."""
        gx = -HALF_L
        d = dist(b, (gx, 0.0))
        ax, ay = unit(b[0] - gx, b[1])
        rad = 0.15 + min(0.3, max(0.0, (d - 1.5) * 0.1))
        x, y = gx + ax * rad, ay * rad * 1.0
        x = max(gx + 0.1, x)
        y = max(-GOAL_HALF_W + 0.05, min(GOAL_HALF_W - 0.05, y + (b[1] * 0.1)))
        return x, y

    # ------------------------------------------------------------------------------------------------ referee states
    def field_ids(self):
        return [k for k, r in sorted(self.v.own.items()) if r.on and k != KEEPER]

    def formation(self) -> dict:
        """number -> target position for the stop / set pieces (subclasses refine it). Default: a compact defence."""
        b = self.v.ball
        ids = self.field_ids()
        gx = -HALF_L
        spots = []
        ux, uy = unit(gx - b[0], -b[1])
        spots.append((b[0] + ux * 0.85, b[1] + uy * 0.85))
        spots.append((max(gx + 1.35, b[0] - 1.6), b[1] * 0.4 + 0.9))
        spots.append((max(gx + 1.35, b[0] - 1.6), b[1] * 0.4 - 0.9))
        spots.append((min(b[0] + 1.0, 2.5), -math.copysign(1.8, b[1] if b[1] else 1)))
        spots.append((max(gx + 1.35, b[0] - 2.5), 0.0))
        return assign(ids, spots, self.v)

    def _keep_clear(self, p, d=0.9, keeper=False):
        """a spot at least d from the ball and from where the referee will place it (§5.1.1, §8.4.3.1), inside the
        field and out of both defense areas: around the ball from the spot's own direction until one fits."""
        pts = [self.v.ball]
        pl = self.v.ref.placement
        if pl is not None and self.v.ref.state == "STOP" and dist(pl, self.v.ball) > 0.05:
            pts.append(tuple(pl))  # the ball goes there 1 s into the stop

        def ok(q):
            return all(dist(q, c) >= d - 1e-6 for c in pts) and in_field(q, 0.12) and opp_da_dist(q) > 0.55 \
                and (own_da_dist(q) == 0.0 if keeper else own_da_dist(q) > 0.25)  # the keeper stays in its area

        if ok(p):
            return p
        b = min(pts, key=lambda c: dist(p, c))
        a0 = math.atan2(p[1] - b[1], p[0] - b[0]) if dist(p, b) > 1e-6 else math.atan2(-b[1], -HALF_L - b[0])
        for rad in (d, d + 0.3, d + 0.6):
            for k in range(0, 13):
                for sgn in ((1,) if k == 0 else (1, -1)):
                    a = a0 + sgn * k * math.pi / 12
                    q = (b[0] + rad * math.cos(a), b[1] + rad * math.sin(a))
                    if ok(q):
                        return q
        if len(pts) > 1:  # nothing keeps clear of both: keep clear of the ball itself
            self_b = self.v.ball
            ux, uy = unit(p[0] - self_b[0], p[1] - self_b[1])
            return clamp_play((self_b[0] + ux * d, self_b[1] + uy * d), 0.12)
        return p

    def stop_play(self):
        """STOP: keep 0.5 m from the ball (and the opponent defense area by 0.2 m) at under 1.5 m/s (§5.1.1)."""
        pos = self.formation()
        nxt = self.v.ref.next_cmd
        if nxt == "FREE_KICK" and self.v.ref.next_ours:
            taker = self.set_piece_taker()
            if taker is not None:
                aim, _, _ = self.set_piece_aim(taker)
                b = self.v.ball
                ux, uy = unit(aim[0] - b[0], aim[1] - b[1])
                pos[taker] = (b[0] - ux * 0.8, b[1] - uy * 0.8)
        for n, p in pos.items():
            p = self._keep_clear(p)
            self.move(n, p, math.atan2(self.v.ball[1] - p[1], self.v.ball[0] - p[0]), vmax=1.1)
            self.dribble(n, 0)
        if KEEPER in self.v.own and self.v.own[KEEPER].on:
            k = self.v.own[KEEPER]
            p = self._keep_clear((-HALF_L + 0.2, max(-0.4, min(0.4, self.v.ball[1] * 0.1))), keeper=True)
            self.move(KEEPER, p, 0.0, vmax=1.1, da=False)
            self.dribble(KEEPER, 0)

    def prepare_kickoff(self):
        """own half, outside the centre circle; the kicking team's kicker behind the ball (§5.3.2)."""
        ours = bool(self.v.ref.ours)
        spots = [(-0.9, 1.6), (-0.9, -1.6), (-1.6, 0.0), (-2.6, 0.8)] if ours else \
                [(-0.85, 0.0), (-1.2, 1.4), (-1.2, -1.4), (-2.4, 0.0)]
        ids = self.field_ids()
        if ours and ids:
            kicker = 1 if 1 in ids else ids[0]
            aim, _, _ = self.set_piece_aim(kicker, kickoff=True)
            ux, uy = unit(aim[0], aim[1])
            self.move(kicker, (-ux * 0.25, -uy * 0.25), math.atan2(uy, ux), avoid=False, da=False)
            self.dribble(kicker, 0)
            ids = [k for k in ids if k != kicker]
        pos = assign(ids, spots, self.v)
        for n, p in pos.items():
            self.move(n, p, 0.0, da=False)
            self.dribble(n, 0)
        if KEEPER in self.v.own and self.v.own[KEEPER].on:
            self.move(KEEPER, (-HALF_L + 0.2, 0.0), 0.0, da=False)

    def set_piece_taker(self):
        ids = self.field_ids()
        if not ids:
            return None
        if self.sp is not None and self.sp["num"] in ids:
            return self.sp["num"]
        b = self.v.ball
        return min(ids, key=lambda k: dist(self.v.own[k].p, b))

    def set_piece_aim(self, n, kickoff=False):
        """(aim point, speed, mode) of a set piece; subclasses choose passes. Default: towards the goal."""
        if kickoff:
            return (-1.0, 1.6), 2.5, "flat"
        return OPP_GOAL, self.kick_speed, "flat"

    def take_set_piece(self):
        """our kick-off / free kick: the taker lines up behind the ball with the dribbler off and drives in with an
        armed kick (one touch; then it keeps off the ball, §8.2)."""
        n = self.set_piece_taker()
        b = self.v.ball
        if n is not None:
            if self.sp is None or self.sp["num"] != n or "aim" not in self.sp:  # (a penalty's record has no aim)
                aim, speed, mode = self.set_piece_aim(n, kickoff=self.v.ref.state == "KICKOFF")
                self.sp = dict(num=n, aim=aim, speed=speed, mode=mode, phase="line", t0=self.v.t)
            sp = self.sp
            r = self.v.own[n]
            ux, uy = unit(sp["aim"][0] - b[0], sp["aim"][1] - b[1])
            th = math.atan2(uy, ux)
            self.dribble(n, 0)
            if sp["phase"] == "line":
                pre = (b[0] - ux * 0.22, b[1] - uy * 0.22)
                self.move(n, pre, th, ball_obstacle=True, da=False)
                if dist(r.p, pre) < 0.04 and abs(wrap(r.yaw - th)) < 0.03 and math.hypot(*r.v) < 0.2 \
                        and self.kick_ready(n, sp["speed"]):
                    sp["phase"] = "go"
                    sp["ball0"] = b
                    self.kick(n, sp["speed"], sp["mode"], armed_for=3.0)
                    if sp["mode"] == "chip":
                        self.stats["chips"] += 1
                    self.locked_until[n] = self.v.t + 3.0
            if sp["phase"] == "go":
                if dist(b, sp["ball0"]) > 0.03 or math.hypot(*self.v.ball_v) > 0.3:
                    sp["phase"] = "done"  # kicked: keep off the ball (§8.2 double touch)
                else:
                    self.move(n, (b[0] - ux * 0.02, b[1] - uy * 0.02), th, vmax=0.8, avoid=False, da=False)
            if sp["phase"] == "done":
                self.move(n, (r.p[0] - ux * 0.3, r.p[1] - uy * 0.3), th, avoid=False, da=False)
        if self.v.ref.state == "KICKOFF":  # the others stay where they stood for the kick-off (own half)
            self.keeper()
            return
        pos = self.formation()
        pos.pop(n, None)
        for k, p in pos.items():
            p = self._keep_clear(p, 0.3)
            self.move(k, p, math.atan2(b[1] - p[1], b[0] - p[0]))
            self.dribble(k, 3000)
        self.keeper()

    def defend_set_piece(self):
        """their kick-off / free kick: everyone keeps 0.5 m from the ball (§8.4.3.1) until it is in play."""
        pos = self.formation()
        for n, p in pos.items():
            p = self._keep_clear(p, 0.9)
            self.move(n, p, math.atan2(self.v.ball[1] - p[1], self.v.ball[0] - p[0]))
            self.dribble(n, 0)
        self.keeper()

    def penalty(self):
        """§5.3.5: the kicker 0.35 m behind the ball, everybody else 1 m behind it, the defending keeper on its goal
        line; the kicker shoots into the corner away from the keeper."""
        v = self.v
        b = v.ball
        ours = bool(v.ref.ours)
        ids = self.field_ids()
        if ours:
            kicker = 1 if 1 in ids else (ids[0] if ids else None)
            ky = min((r.p[1] for k, r in v.opp.items() if r.on and r.p[0] > 4.0), default=0.0, key=abs)
            aim = (HALF_L, -0.36 if ky > 0 else 0.36)
            ux, uy = unit(aim[0] - b[0], aim[1] - b[1])
            th = math.atan2(uy, ux)
            rest = [k for k in ids if k != kicker]
            for i, k in enumerate(rest):
                self.move(k, (b[0] - 1.35, -1.8 + 1.2 * i), 0.0, da=False)
            if kicker is not None:
                r = v.own[kicker]
                self.dribble(kicker, 0)
                if v.ref.state == "PREPARE_PENALTY":
                    self.move(kicker, (b[0] - 0.35, b[1]), 0.0, avoid=False, da=False)
                    self.sp = None
                else:
                    self.penalty_kicker(kicker, aim)
            if KEEPER in v.own and v.own[KEEPER].on:
                self.move(KEEPER, (-4.2, 0.0), 0.0, da=False)
        else:
            for i, k in enumerate(ids):
                self.move(k, (b[0] + 1.35, -1.8 + 1.2 * i), math.pi, da=False)
            if KEEPER in v.own and v.own[KEEPER].on:
                y = 0.0
                if math.hypot(*v.ball_v) > 0.5 and v.ball_v[0] < 0:
                    y = b[1] + v.ball_v[1] * (-HALF_L + 0.05 - b[0]) / v.ball_v[0]
                    y = max(-0.45, min(0.45, y))
                self.move(KEEPER, (-HALF_L + 0.05, y), 0.0, da=False, avoid=False)
                self.dribble(KEEPER, 3000)

    def penalty_kicker(self, n, corner):
        """§5.3.5 (Division B: the kicker may touch the ball again; it may only move towards the goal): from 6 m a
        keeper saves any shot, so knock the ball towards the goal (1.8 m/s pushes, never letting it roll back),
        follow it, and shoot into the corner away from the keeper from within 2.3 m."""
        v = self.v
        r = v.own[n]
        b = v.ball
        sp = self.sp
        if sp is None or sp.get("num") != n or "pen" not in sp:
            sp = self.sp = dict(num=n, pen="line", t=v.t)
        dg = dist(b, OPP_GOAL)
        shoot = dg < 2.3
        tgt = corner if shoot else (HALF_L, 0.0)
        ux, uy = unit(tgt[0] - b[0], tgt[1] - b[1])
        th = math.atan2(uy, ux)
        if sp["pen"] == "go":
            moved = dist(b, sp["ball0"]) > 0.04 or math.hypot(*v.ball_v) > 0.3
            if moved:
                sp["pen"] = "follow"
            else:
                self.move(n, (b[0] - ux * 0.02, b[1] - uy * 0.02), th, vmax=0.6, avoid=False, da=False)
                return
        if sp["pen"] == "follow":
            if math.hypot(*v.ball_v) > 0.25:  # stay behind the rolling ball, facing the goal
                self.move(n, (b[0] - ux * 0.35, b[1] - uy * 0.35), th, vmax=2.0, avoid=False, da=False)
                return
            sp["pen"] = "line"
        # line up behind the ball (it never comes back towards the robot: approach from behind only)
        pre = (b[0] - ux * 0.22, b[1] - uy * 0.22)
        self.move(n, pre, th, avoid=False, da=False, vmax=1.5)
        if dist(r.p, pre) < 0.05 and abs(wrap(r.yaw - th)) < 0.04 and math.hypot(*r.v) < 0.2:
            speed = 5.6 if shoot else 1.8  # the robot still creeps forward at the kick: stay under 6.5 m/s
            if self.kick_ready(n, speed):
                sp["pen"], sp["ball0"] = "go", b
                self.kick(n, speed, "flat", armed_for=2.0)

    def play(self):  # pragma: no cover - subclasses
        raise NotImplementedError


def assign(ids, spots, view, cost=None):
    """robots -> spots minimising the summed squared distance (brute force over permutations, at most 5 robots)."""
    ids = list(ids)
    if not ids:
        return {}
    spots = list(spots)
    while len(spots) < len(ids):
        spots.append(spots[-1] if spots else (-2.0, 0.0))
    best, best_c = None, math.inf
    for perm in itertools.permutations(range(len(spots)), len(ids)):
        c = 0.0
        for i, j in zip(ids, perm):
            c += dist(view.own[i].p, spots[j]) ** 2 if cost is None else cost(i, spots[j])
            if c >= best_c:
                break
        if c < best_c:
            best, best_c = perm, c
    return {i: spots[j] for i, j in zip(ids, best)}

# ==============================================================================================================
# reference.py
# ==============================================================================================================





class Reference(TeamBase):
    name = "reference"

    def __init__(self, team="blue", seed=0, passing=True, read_opp=True, roles="planned", role_period=2.0,
                 ball_noise=0.0, roll_dec=ROLL_DEC, model_slide=True, chip=True, redirects=True, lag=0.0, lookahead=0.08, shoot_range=6.5, shoot_margin=-0.4,
                 **kw):
        super().__init__(team, seed, roll_dec=roll_dec, model_slide=model_slide, **kw)
        self.passing, self.read_opp, self.roles = passing, read_opp, roles
        self.role_period = role_period
        self.ball_noise = ball_noise
        self.chip = chip
        self.redirects = redirects
        # chip PASSES: off by default (a bouncing ball reaches the receiver in the air and is rarely controlled:
        # 2/2 lost in the traced matches); chips stay as clearances
        self.chip_passes = False
        self.lag, self.lag_buf = float(lag), deque()
        self.lookahead = float(lookahead)
        # an extra shooting rule: shoot from within shoot_range m whenever the best goal point's margin exceeds
        # shoot_margin (s; negative = the keeper could just reach it). 0 = off. Default 6.5 m / -0.4 s: shooting
        # often pays here (rebounds, a keeper that moved); 200 seeds on L3: +2.12 goals/match vs +0.55 without it
        # (olympiad_review/screening/soccer_ssl_players_zh.md 2.4)
        self.shoot_range, self.shoot_margin = float(shoot_range), float(shoot_margin)
        self.getter = None
        self.pass_ = None
        self.plan = None              # the carrier's committed action: dict(num, kind, target, speed, mode, t)
        self.support_spots = []
        self.spots_t = -1.0
        self.random_roles = None
        self.random_t = -1e9
        self.kick_cool = {}
        self.noisy = None
        self.log = deque(maxlen=3000)
        self.debug = False

    # ------------------------------------------------------------------------------------------------ perception
    def update(self, view):
        if self.lag > 0:
            # A4 impairment: act on the world as it was `lag` seconds before this observation (all of it, own
            # robots included), with no compensation
            self.lag_buf.append(view)
            while len(self.lag_buf) > 1 and view.t - self.lag_buf[1].t >= self.lag - 1e-6:
                self.lag_buf.popleft()
            old = self.lag_buf[0]
            view = replace(old, ref=view.ref)
        if self.ball_noise > 0:
            view = self._noisy(view)
        if self.lookahead > 0 and math.hypot(*view.ball_v) > 0.3 and \
                not any(r.on and dist(r.p, view.ball) < 0.2 for r in view.own.values()):
            # A4: the command acts ~`lookahead` s after the picture was taken: carry a rolling ball forward
            P = BallPath(view.ball, view.ball_v)
            sp = P.v_at(self.lookahead)
            view = replace(view, ball=P.at(self.lookahead), ball_v=(P.d[0] * sp, P.d[1] * sp))
        return super().update(view)

    def _noisy(self, view):
        """A1 impairment: the ball position with Gaussian noise; its velocity from differences of noisy positions
        over 0.1 s (what a player without filtering would compute)."""
        nx, ny = self.rng.normal(0, self.ball_noise, 2)
        p = (view.ball[0] + nx, view.ball[1] + ny)
        if self.noisy is None:
            self.noisy = []
        self.noisy.append((view.t, p))
        self.noisy = [e for e in self.noisy if view.t - e[0] <= 0.1 + 1e-6]
        t0, p0 = self.noisy[0]
        dt = view.t - t0
        v = ((p[0] - p0[0]) / dt, (p[1] - p0[1]) / dt) if dt > 0.03 else view.ball_v
        view.ball, view.ball_v = p, v
        return view

    # ------------------------------------------------------------------------------------------------ in play
    def play(self):
        v = self.v
        ids = [k for k in self.field_ids() if self.locked_until.get(k, -1) <= v.t]
        locked = [k for k in self.field_ids() if k not in ids]
        P = self.path()
        opp_ctrl = self.opp_with_ball()
        carrier = next((k for k in ids if self.has_ball(k)), None)
        # pass bookkeeping
        if self.pass_ is not None:
            pr = self.pass_
            if carrier == pr["recv"]:
                self.stats["pass_ok"] += 1
                self.log.append((round(v.t, 2), "pass_ok", pr["recv"]))
                self.pass_ = None
            elif carrier is not None and carrier != pr["recv"] and (carrier != pr["from"] or v.t - pr["t"] > 0.4):
                self.stats["pass_other"] = self.stats.get("pass_other", 0) + 1
                self.log.append((round(v.t, 2), "pass_other", carrier))
                self.pass_ = None
            elif (opp_ctrl is not None and v.t - pr["t"] > 0.3) or v.t > pr["deadline"]:
                self.stats["pass_lost"] += 1
                why = "opp" if opp_ctrl is not None else ("other" if carrier is not None else "timeout")
                self.log.append((round(v.t, 2), "pass_lost", pr["recv"], why, [round(c, 2) for c in v.ball]))
                self.pass_ = None
        # interception times
        mine = {}
        for k in ids:
            r = v.own[k]
            it = intercept(r.p, r.v, P, react=0.0)
            mine[k] = it[0] if it is not None else 9.0
        theirs = 9.0
        for k, r in v.opp.items():
            if r.on:
                it = intercept(r.p, r.v, P, react=0.1)
                if it is not None:
                    theirs = min(theirs, it[0])
        # the ball-getter
        getter = self._choose_getter(ids, mine, carrier)
        self.getter = getter
        best_mine = mine.get(getter, 9.0) if getter is not None else 9.0
        defending = opp_ctrl is not None or (carrier is None and self.pass_ is None and theirs + 0.25 < best_mine)
        others = [k for k in ids if k != getter] + locked
        # the getter
        if self.roles == "swarm":
            for k in ids:
                if k == carrier:
                    self.attack(k)
                else:
                    self.collect(k, aim=OPP_GOAL)
            self.keeper(clear_fn=self.keeper_clear)
            return
        if getter is not None:
            if getter == carrier:
                self.attack(getter)
            elif self.pass_ is not None and self.pass_.get("redirect") and getter == self.pass_["recv"] \
                    and self.redirect_receive(getter):
                pass
            else:
                if self.plan is not None and self.plan["num"] == getter:
                    self.plan = None
                aim = OPP_GOAL
                self.collect(getter, aim=aim)
        # the others
        if defending:
            spots = self.defend_spots(len(others))
        else:
            spots = self.attack_spots(len(others), carrier if carrier is not None else getter)
        if self.roles == "random":
            pos = self._random_assign(others, spots)
        else:
            pos = assign(others, spots, v)
        b = v.ball
        pl = self.plan
        for k, p in pos.items():
            if self.pass_ is not None and k == self.pass_["recv"]:
                continue
            if pl is not None and pl["kind"] == "pass" and pl["recv"] == k and pl["num"] == carrier:
                # the pass is being lined up: wait on the spot, facing the ball
                q = pl["target"]
                rd = pl.get("redirect")
                if rd:
                    h = rd["heading"]
                    self.move(k, (q[0] - math.cos(h) * KICK_REACH, q[1] - math.sin(h) * KICK_REACH), h, avoid=False)
                else:
                    self.move(k, q, math.atan2(b[1] - q[1], b[0] - q[0]), avoid=False)
                self.dribble(k, 3000)
                continue
            if dist(p, b) < 0.4:  # off-ball robots keep off the ball (two at it for 1 s: ball holding, §8.4.1.3)
                ux, uy = unit(p[0] - b[0], p[1] - b[1])
                p = (b[0] + ux * 0.4, b[1] + uy * 0.4)
            th = math.atan2(b[1] - p[1], b[0] - p[0])
            self.move(k, p, th)
            self.dribble(k, 3000 if not defending else 0)
        self.keeper(clear_fn=self.keeper_clear)

    def _choose_getter(self, ids, mine, carrier):
        v = self.v
        if carrier is not None:
            return carrier
        if self.pass_ is not None and self.pass_["recv"] in ids:
            return self.pass_["recv"]
        if not ids:
            return None
        if self.roles == "random":
            if self.random_roles is None or v.t - self.random_t >= self.role_period or self.random_roles[0] not in ids:
                perm = list(self.rng.permutation(ids))
                self.random_roles, self.random_t = perm, v.t
            return self.random_roles[0]
        best = min(ids, key=lambda k: mine[k])
        g = self.getter
        if g in ids and mine[g] <= mine[best] + (0.6 if not self.passing else 0.25):
            return g
        return best

    def _random_assign(self, others, spots):
        order = [k for k in (self.random_roles or []) if k in others] + [k for k in others if k not in (self.random_roles or [])]
        return {k: spots[i % len(spots)] for i, k in enumerate(order)} if spots else {}

    def redirect_receive(self, n):
        """the receiver of a one-touch pass: its kick point on the ball's path, facing the goal point, kick armed.
        False when the ball's path no longer allows it (then it receives normally)."""
        v = self.v
        rd = self.pass_["redirect"]
        r = v.own[n]
        b, bv = v.ball, v.ball_v
        sp = math.hypot(*bv)
        h = rd["heading"]
        if sp < 0.8:
            return False
        dx, dy = bv[0] / sp, bv[1] / sp
        # the point of the path nearest the planned kick point
        kp = (r.p[0] + math.cos(h) * KICK_REACH, r.p[1] + math.sin(h) * KICK_REACH)
        u = (kp[0] - b[0]) * dx + (kp[1] - b[1]) * dy
        if u < 0.05:
            return False
        q = (b[0] + dx * u, b[1] + dy * u)
        ang = math.degrees(math.acos(max(-1.0, min(1.0, -(dx * math.cos(h) + dy * math.sin(h))))))
        if ang > 80.0 or dist(q, kp) > 0.6:
            return False
        self.move(n, (q[0] - math.cos(h) * KICK_REACH, q[1] - math.sin(h) * KICK_REACH), h, avoid=False)
        self.dribble(n, 0)
        if not self.pass_.get("armed"):
            self.kick(n, self.kick_speed - 0.6, "flat", armed_for=3.0)  # its own motion adds to the ball
            self.pass_["armed"] = True
        return True

    # ------------------------------------------------------------------------------------------------ the carrier
    def attack(self, n):
        v = self.v
        r = v.own[n]
        b = v.ball
        dd = self.track_hold(n)
        if self.kick_cool.get(n, -1) > v.t:
            self.move(n, r.p, r.yaw, avoid=False)
            return
        pl = self.plan
        if pl is not None and (pl["num"] != n or v.t - pl["t"] > 1.2):
            pl = self.plan = None
        if pl is not None and pl["kind"] == "pass":
            k = pl["recv"]
            # re-check the lane while turning (the opponents move)
            ok = self._pass_option(n, k, pl["target"], check_receiver=False) if self.passing else None
            # committed: only a lane that has clearly closed (or worse than when it was chosen) cancels it
            if ok is None or (self.read_opp and ok["margin"] < min(-0.1, pl.get("margin", 0.0) - 0.15)):
                pl = self.plan = None
            else:
                pl.update(speed=ok["speed"], T=ok["T"], margin=ok["margin"], redirect=ok.get("redirect"))
        if pl is None:
            pl = self.decide(n, dd)
            self.plan = pl
            if self.debug:
                self.log.append((round(v.t, 2), "decide", n, pl["kind"], [round(c, 2) for c in b], round(dd, 2),
                                 round(pl.get("margin", 0.0), 2)))
        if dd > 0.5 and (r.beam or r.engaged):
            # about to break the 1 m dribbling limit (§8.4.1.8): release now along the heading unless it points at
            # the own goal (then just let the ball go: dribbler off)
            fx = math.cos(r.yaw)
            if fx > -0.3:
                self.kick(n, 3.5 if fx > 0.5 else 2.5, "flat")
                self.kick_cool[n] = v.t + 0.4
                self.locked_until[n] = v.t + 0.25
                self.log.append((round(v.t, 2), "forced", n))
            else:
                self.dribble(n, 0)
                self.locked_until[n] = v.t + 0.3
            self.plan = None
            return
        if pl["kind"] == "shield":
            err = wrap(pl["yaw"] - r.yaw)
            self.move(n, r.p, r.yaw + max(-0.9, min(0.9, err)), avoid=False, da=False)
            self.dribble(n, 3000)
            if v.t - pl["t"] > 0.15:
                self.plan = None
            return
        if pl["kind"] == "carry":
            tgt = pl["target"]
            ang = math.atan2(tgt[1] - r.p[1], tgt[0] - r.p[0])
            if dd > 0.4 or dist(r.p, tgt) < 0.05:
                self.plan = None
                self.move(n, r.p, ang, avoid=False)
            else:
                self.move(n, tgt, ang, vmax=1.2, avoid=False)
            self.dribble(n, 3000)
            if v.t - pl["t"] > 0.3:
                self.plan = None
            return
        tol = None
        if pl["kind"] == "pass":  # a receiver adjusts to a pass up to ~0.25 m off; a shot needs the goal
            tol = max(0.04, min(0.12, math.atan2(0.25, max(dist(r.p, pl["target"]), 0.5))))
        elif pl["kind"] in ("push", "solo"):
            tol = 0.15
        if self.turn_and_kick(n, pl["target"], pl["speed"], pl["mode"], tol=tol):
            self.kick_cool[n] = v.t + 0.4
            self.locked_until[n] = v.t + 0.25
            kind = pl["kind"]
            key = {"pass": "passes", "shot": "shots", "solo": "solos"}.get(kind, "clears")
            self.stats[key] = self.stats.get(key, 0) + 1
            if pl["mode"] == "chip":
                self.stats["chips"] += 1
            self.log.append((round(v.t, 2), kind, n, pl.get("recv"), [round(c, 2) for c in b],
                             [round(c, 2) for c in pl["target"]], round(pl["speed"], 2), pl["mode"],
                             round(pl.get("margin", 0.0), 2)))
            if kind == "pass":
                self.pass_ = dict(recv=pl["recv"], q=pl["target"], t=v.t, deadline=v.t + pl["T"] + 1.2,
                                  redirect=pl.get("redirect"), **{"from": n})
                if pl.get("redirect"):
                    self.stats["redirects"] = self.stats.get("redirects", 0) + 1
            self.plan = None

    def decide(self, n, dd):
        """the carrier's choice: shot, pass, carry, or push / clear."""
        v = self.v
        b = v.ball
        shot = self.best_shot(b, n)
        here = self.spot_value(b, exclude_carrier=True)
        press = min((dist(o.p, b) for o in v.opp.values() if o.on), default=9.0)
        dg = dist(b, OPP_GOAL)
        if shot is not None and ((shot["margin"] > 0.04 and dg < 5.0) or (dg < 2.4 and shot["margin"] > -0.15)
                                 or (dg < self.shoot_range and shot["margin"] > self.shoot_margin)):
            return dict(num=n, kind="shot", target=shot["target"], speed=self.kick_speed, mode="flat", t=v.t,
                        margin=shot["margin"])
        best = risky = None
        if self.passing:
            for k in self.field_ids():
                if k == n:
                    continue
                for q in self.pass_points(k):
                    o = self._pass_option(n, k, q)
                    if o is None:
                        continue
                    if self.read_opp and o["margin"] < 0.05:
                        if o["margin"] > -0.2 and (risky is None or o["margin"] > risky["margin"]):
                            risky = dict(o, val=o["value"], recv=k)
                        continue
                    val = o["value"] + (0.4 if self.read_opp else 0.0) * min(o["margin"], 0.5) \
                        - 0.05 * dist(q, v.own[k].p)
                    if best is None or val > best["val"]:
                        best = dict(o, val=val, recv=k)
        pressed = press < 0.7
        if best is not None and (best["val"] > here + 0.1 or pressed or dd > 0.4):
            return dict(num=n, kind="pass", target=best["target"], speed=best["speed"], mode=best["mode"],
                        recv=best["recv"], T=best["T"], t=v.t, margin=best["margin"], redirect=best.get("redirect"))
        if shot is not None and ((dg < 2.2 and shot["margin"] > -0.15) or (dg < 3.0 and shot["margin"] > -0.08)
                                 or (dg < 4.2 and shot["margin"] > -0.02)):
            return dict(num=n, kind="shot", target=shot["target"], speed=self.kick_speed, mode="flat", t=v.t,
                        margin=shot["margin"])
        # a solo run: nobody but the keeper between the ball and the goal and nobody close: knock the ball 1.2 m
        # ahead and follow it (the 1 m limit counts only while the robot touches the ball, §8.4.1.8)
        if 2.6 < dg < 6.0 and press > 1.2 and not any(
                o.on and opp_da_dist(o.p) > 0.05 and o.p[0] > b[0] - 0.3 and dist(o.p, b) < 2.2
                for o in v.opp.values()):
            ux, uy = unit(OPP_GOAL[0] - 1.6 - b[0], -b[1] * 0.7)
            return dict(num=n, kind="solo", target=(b[0] + ux * 1.5, b[1] + uy * 1.5), speed=1.9, mode="flat", t=v.t)
        if dd < 0.25 and not pressed:
            return dict(num=n, kind="carry", target=self.carry_target(n), speed=0.0, mode="flat", t=v.t)
        h = self.hold_start.get(n)
        held = v.t - h[2] if h is not None else 0.0
        if pressed and risky is not None and (held > 0.3 or press < 0.35):
            # under pressure a risky pass beats losing the ball where it is
            return dict(num=n, kind="pass", target=risky["target"], speed=risky["speed"], mode=risky["mode"],
                        recv=risky["recv"], T=risky["T"], t=v.t, margin=risky["margin"], redirect=risky.get("redirect"))
        if pressed and dd < 0.45 and held < 0.6:
            # shield: turn the robot between the presser and the ball and wait for a lane to open
            o = min((o for o in v.opp.values() if o.on), key=lambda o: dist(o.p, b))
            r = v.own[n]
            away = math.atan2(r.p[1] - o.p[1], r.p[0] - o.p[0])
            return dict(num=n, kind="shield", target=(r.p[0], r.p[1]), yaw=away, speed=0.0, mode="flat", t=v.t)
        # release: push the ball into space ahead (no pass on) or a chip clear when pressed deep in our half
        tgt, sp = self.push_target(b)
        mode = "flat"
        if self.chip and b[0] < -1.0 and pressed:
            tgt, sp, mode = (min(b[0] + 3.0, 2.0), math.copysign(1.5, b[1] if b[1] else 1)), 4.5, "chip"
        return dict(num=n, kind="push", target=tgt, speed=sp, mode=mode, t=v.t)

    def carry_target(self, n):
        r = self.v.own[n]
        b = self.v.ball
        best, bv = None, -1e9
        for ang in np.linspace(-1.2, 1.2, 9):
            q = (b[0] + 0.45 * math.cos(ang), b[1] + 0.45 * math.sin(ang))
            if not in_field(q, 0.25) or opp_da_dist(q) < 0.25:
                continue
            clear = min((dist(o.p, q) for o in self.v.opp.values() if o.on), default=3.0) if self.read_opp else 1.0
            val = q[0] * 0.3 + min(clear, 1.2)
            if val > bv:
                best, bv = q, val
        if best is None:
            best = b
        rx, ry = unit(best[0] - b[0], best[1] - b[1])
        return (best[0] - rx * KICK_REACH, best[1] - ry * KICK_REACH)

    def push_target(self, b):
        """a release: the ball into the most open space ahead (or the goal when near)."""
        if dist(b, OPP_GOAL) < 3.5:
            return (HALF_L, 0.0), self.kick_speed
        best, bv = None, -1e9
        for ang in np.linspace(-1.0, 1.0, 11):
            q = (b[0] + 2.0 * math.cos(ang), b[1] + 2.0 * math.sin(ang))
            if not in_field(q, 0.3):
                continue
            clear = min((point_to_segment(o.p, b, q)[0] for o in self.v.opp.values() if o.on), default=3.0) \
                if self.read_opp else 1.0
            val = min(clear, 1.0) + 0.15 * q[0]
            if val > bv:
                best, bv = q, val
        return (best or (b[0] + 2.0, b[1])), 3.0

    def keeper_clear(self, n):
        """the keeper with the ball in its area: a pass to the open teammate, else a chip up the field."""
        b = self.v.ball
        best = None
        if self.passing:
            for k in self.field_ids():
                o = self._pass_option(n, k, self.v.own[k].p)
                if o is not None and o["margin"] > 0.2 and (best is None or o["value"] > best[0]["value"]):
                    best = (o, k)
        if best is not None:
            o, k = best
            if self.turn_and_kick(n, o["target"], o["speed"], o["mode"]):
                self.pass_ = dict(recv=k, q=o["target"], t=self.v.t, deadline=self.v.t + o["T"] + 1.2, **{"from": n})
                self.stats["passes"] += 1
            return
        self.turn_and_kick(n, (0.0, math.copysign(2.0, b[1] if b[1] else 1.0)), 5.0, "chip")

    # ------------------------------------------------------------------------------------------------ evaluation
    def pass_points(self, k):
        """where teammate k can take a pass: where it stands, or a lead pass into the space around it (up to 1 m
        away, the receiver starts running when the pass is lined up)."""
        r = self.v.own[k]
        pts = [r.p]
        for i in range(8):
            a = i * math.pi / 4
            q = (r.p[0] + 0.9 * math.cos(a), r.p[1] + 0.9 * math.sin(a))
            if in_field(q, 0.25) and opp_da_dist(q) > 0.3 and own_da_dist(q) > 0.3:
                pts.append(q)
        return pts

    def turn_time(self, n, q):
        """seconds robot n needs to turn (with the ball) to face q: about 5 rad/s plus the kick's latency."""
        r = self.v.own[n]
        return abs(wrap(math.atan2(q[1] - r.p[1], q[0] - r.p[0]) - r.yaw)) / 5.0 + 0.05

    def _pass_option(self, n, k, q, check_receiver=True):
        """a flat (or chip) pass from the ball to teammate k at q: the kick speed, flight time, the lane's time
        margin against the opponents (their reaction ~0.1 s, less the time the passer needs to turn) and the value
        of receiving there."""
        v = self.v
        b = v.ball
        tt = self.turn_time(n, q)
        D = dist(b, q)
        if D < 1.2 or D > 6.5:
            return None
        if own_da_dist(q) < 0.15 or opp_da_dist(q) < 0.15:
            return None
        ux, uy = unit(q[0] - b[0], q[1] - b[1])
        arrive = 2.6 if D > 3.0 else (2.2 if D > 2.0 else 1.6)  # a short pass arrives soft: the receiver has
        speed = pass_speed(D - KICK_REACH, arrive=arrive, vmin=1.2, roll_dec=self.roll_dec,  # little time to adjust
                           model_slide=self.model_slide)
        P = kick_path(b, (ux, uy), speed, roll_dec=self.roll_dec, model_slide=self.model_slide)
        T = P.t_of_s(D - KICK_REACH)
        if math.isinf(T):
            return None
        rk = v.own[k]
        # the receiver must be there (and settled) before the ball: its own reaction (~0.1 s) and 0.15 s to spare
        if check_receiver and reach_time(rk.p, rk.v, q, slack=0.03) + 0.25 > T + tt:
            return None
        mode = "flat"
        margin = lane_margin(P, D - KICK_REACH, self.opp_list(), react=0.1 - tt) if self.read_opp else 1.0
        if self.read_opp and margin < 0.1 and self.chip and self.chip_passes and 2.6 < D < 4.2:
            # a chip over the defender near the passer: the ball flies ~v^2/g (45 deg), then rolls
            near = [(o.p, o.v) for o in v.opp.values() if o.on and dist(o.p, b) < 1.4]
            far = [(o.p, o.v) for o in v.opp.values() if o.on and dist(o.p, b) >= 1.4]
            cs = min(5.5, math.sqrt(9.81 * (D - 0.6)))
            flight = (D - 0.6) / (cs * math.cos(math.pi / 4))
            m2 = min((reach_time(p, vv, q, slack=0.3) + 0.1 - tt - (flight + 0.4) for p, vv in far), default=1.0)
            if m2 > 0.15 and near:
                return dict(target=q, speed=cs, mode="chip", T=flight + 0.6, margin=m2, value=self.spot_value(q) - 0.1)
        o = dict(target=q, speed=speed, mode=mode, T=T, margin=margin, value=self.spot_value(q))
        rd = self.redirect_option(b, q, T + tt) if self.redirects else None
        if rd is not None:
            o.update(redirect=rd, value=o["value"] + 0.8)
        return o

    def redirect_option(self, b, q, t_arrive):
        """a one-touch shot (the receiver faces the goal with an armed kick; the passed ball, arriving from the side,
        is kicked on at once): the goal point and the receiver's heading, or None. Needs the ball to come in at most
        75 degrees off the robot's heading (the kicker's beam catches it there; screen/ drill) and the goal point open
        against the opponents' reach by the time the shot gets there."""
        if dist(q, OPP_GOAL) > 3.8 or q[0] < 1.0:
            return None
        ix, iy = unit(q[0] - b[0], q[1] - b[1])
        best = None
        for y in (-0.32, 0.32, 0.0):
            tgt = (HALF_L + 0.05, y)
            sx, sy = unit(tgt[0] - q[0], tgt[1] - q[1])
            # the ball comes in `ang` degrees off the robot's heading (0: head-on into the kicker)
            ang = math.degrees(math.acos(max(-1.0, min(1.0, -(ix * sx + iy * sy)))))
            if ang > 75.0:
                continue
            P = kick_path(q, (sx, sy), self.kick_speed, roll_dec=self.roll_dec, model_slide=self.model_slide)
            L = dist(q, tgt)
            m = lane_margin(P, L, self.opp_list(), react=0.1 + t_arrive, start=0.3, tail=0.0) if self.read_opp \
                else 0.3
            if best is None or m > best["margin"]:
                best = dict(target=tgt, heading=math.atan2(sy, sx), margin=m)
        if best is None or best["margin"] < 0.05:
            return None
        return best

    def best_shot(self, b, n=None):
        best = None
        if dist(b, OPP_GOAL) > 6.0:
            return None
        opps = self.opp_list()
        for y in np.linspace(-0.33, 0.33, 7):
            tgt = (HALF_L + 0.05, float(y))
            ux, uy = unit(tgt[0] - b[0], tgt[1] - b[1])
            P = kick_path(b, (ux, uy), self.kick_speed, roll_dec=self.roll_dec, model_slide=self.model_slide)
            L = dist(b, tgt)
            if math.isinf(P.t_of_s(L)):
                continue
            tt = self.turn_time(n, tgt) if n is not None else 0.0
            m = lane_margin(P, L, opps, react=0.1 - 0.5 * tt, start=0.3, tail=0.0) if self.read_opp else \
                0.3 - 0.05 * L
            m -= 0.04 * L  # the kick's 1 deg direction error matters more from afar
            if best is None or m > best["margin"]:
                best = dict(target=tgt, margin=m)
        return best

    def spot_value(self, q, exclude_carrier=False, use_opp=None):
        """how good it is to have the ball at q: the view of the goal (the open angle), progress, room."""
        use_opp = bool(self.read_opp) if use_opp is None else use_opp
        gx = HALF_L
        a1 = math.atan2(-0.5 - q[1], gx - q[0])
        a2 = math.atan2(0.5 - q[1], gx - q[0])
        ang = abs(a2 - a1)
        dg = dist(q, OPP_GOAL)
        val = 0.35 * q[0] / HALF_L + 1.2 * ang * (1.0 if dg < 5.0 else 0.4)
        if use_opp:
            room = min((dist(o.p, q) for o in self.v.opp.values() if o.on), default=3.0)
            val += 0.5 * min(room, 1.2)
            # how many opponents stand in the shooting triangle
            blk = 0
            for o in self.v.opp.values():
                if o.on and o.p[0] > q[0]:
                    d, u = point_to_segment(o.p, q, OPP_GOAL)
                    if d < 0.25 + 0.1 * u * dg:
                        blk += 1
            val -= 0.15 * max(0, blk - 1)
        return val

    # ------------------------------------------------------------------------------------------------ positions
    def attack_spots(self, n, carrier):
        """n spots for the off-ball robots: the best open receiving spots (recomputed every 0.25 s) and a safety."""
        v = self.v
        if n <= 0:
            return []
        b = v.ball
        if v.t - self.spots_t >= 0.25 or len(self.support_spots) != n:
            self.spots_t = v.t
            cand = []
            for x in np.arange(-1.2, 3.9, 0.4):
                for y in np.arange(-2.6, 2.61, 0.4):
                    q = (float(x), float(y))
                    if opp_da_dist(q) < 0.35:
                        continue
                    D = dist(q, b)
                    if D < 1.3 or D > 4.2:
                        continue
                    rs = self.read_opp is True  # b2_weak ("passes"): the spots ignore the opponents
                    s = self.spot_value(q, use_opp=rs)
                    if rs:
                        lane = min((point_to_segment(o.p, b, q)[0] for o in v.opp.values() if o.on), default=2.0)
                        s += 0.8 * min(lane, 0.7)
                    s -= 0.12 * abs(D - 2.4)
                    cand.append((s, q))
            cand.sort(key=lambda e: -e[0])
            chosen = []
            safety_x = max(-3.0, min(b[0] - 2.0, 0.5))
            nn = n - 1 if n >= 3 else n
            for s, q in cand:
                if all(dist(q, c) > 1.6 for c in chosen):
                    chosen.append(q)
                if len(chosen) >= nn:
                    break
            if n >= 3:
                chosen.append((safety_x, b[1] * 0.3))
            while len(chosen) < n:
                chosen.append((safety_x, -b[1] * 0.3))
            # stick to the previous spots unless clearly better (avoid running back and forth)
            if len(self.support_spots) == n:
                keep = []
                for q in chosen:
                    near = min(self.support_spots, key=lambda c: dist(c, q))
                    keep.append(near if dist(near, q) < 0.5 else q)
                chosen = keep
            self.support_spots = chosen
        return list(self.support_spots)

    def defend_spots(self, n):
        """n spots with the ball theirs: a blocker on the ball-goal line, markers between the ball and the most
        dangerous opponents, a safety."""
        v = self.v
        b = v.ball
        gx = -HALF_L
        spots = []
        ux, uy = unit(gx - b[0], -b[1])
        dball = dist(b, (gx, 0.0))
        rb = min(1.1, max(0.5, dball - 1.6))
        spots.append(push_out_of_own_da((b[0] + ux * rb, b[1] + uy * rb)))
        if self.read_opp:
            danger = sorted((o for k, o in v.opp.items() if o.on and dist(o.p, b) > 0.5 and opp_da_dist(o.p) > 0.4
                             and o.p[0] < max(1.0, b[0] + 1.0)),
                            key=lambda o: dist(o.p, (gx, 0.0)))
            for o in danger[: max(0, n - 1)]:
                mx, my = unit(b[0] - o.p[0], b[1] - o.p[1])
                gx2, gy2 = unit(gx - o.p[0], -o.p[1])
                dx, dy = unit(mx + gx2, my + gy2)
                spots.append(push_out_of_own_da((o.p[0] + dx * 0.4, o.p[1] + dy * 0.4)))
        while len(spots) < n:
            spots.append(push_out_of_own_da((max(gx + 1.3, b[0] - 2.0), 0.6 * (1 if len(spots) % 2 else -1))))
        return spots[:n]

    # ------------------------------------------------------------------------------------------------ set pieces
    def formation(self):
        v = self.v
        ids = self.field_ids()
        nxt_ours = v.ref.next_ours if v.ref.state == "STOP" else v.ref.ours
        if nxt_ours:
            spots = self.attack_spots(len(ids), None)
        else:
            spots = self.defend_spots(len(ids))
        spots = [push_out_of_opp_da(push_out_of_own_da(q), 0.45) for q in spots]
        return assign(ids, spots, v)

    def set_piece_aim(self, n, kickoff=False):
        v = self.v
        b = v.ball
        if kickoff:
            # a pass to a teammate standing wide in the own half
            return (-0.9, 1.6 if (self.rng.random() < 0.5) else -1.6), 2.4, "flat"
        shot = self.best_shot(b)
        if shot is not None and shot["margin"] > 0.1 and dist(b, OPP_GOAL) < 4.5:
            return shot["target"], self.kick_speed, "flat"
        best = None
        if self.passing:
            for k in self.field_ids():
                if k == n:
                    continue
                o = self._pass_option(n, k, v.own[k].p)
                if o is not None and o["margin"] > 0.1 and (best is None or o["value"] > best["value"]):
                    best = o
        if best is not None:
            return best["target"], best["speed"], best["mode"]
        tgt, sp = self.push_target(b)
        return tgt, sp, "flat"

# ==============================================================================================================
# baselines.py
# ==============================================================================================================




class AllChase(Reference):
    name = "allchase"

    def play(self):
        v = self.v
        for k in self.field_ids():
            if self.locked_until.get(k, -1) > v.t and not self.has_ball(k):
                continue
            if self.has_ball(k):
                self.shoot_now(k)
            else:
                self.collect(k, aim=OPP_GOAL)
        self.keeper()

    def shoot_now(self, k):
        if self.kick_cool.get(k, -1) > self.v.t:
            return
        shot = self.best_shot(self.v.ball)
        tgt = shot["target"] if shot is not None else OPP_GOAL
        if self.turn_and_kick(k, tgt, self.kick_speed, "flat", tol=0.06):
            self.kick_cool[k] = self.v.t + 0.4
            self.stats["shots"] += 1
            self.log.append((round(self.v.t, 2), "shot", k, None, [round(c, 2) for c in self.v.ball]))
        elif self.track_hold(k) > 0.75 and (self.v.own[k].beam or self.v.own[k].engaged):
            self.kick(k, self.kick_speed - 0.8)
            self.kick_cool[k] = self.v.t + 0.4

    def set_piece_aim(self, n, kickoff=False):
        return OPP_GOAL, self.kick_speed, "flat"


class Fixed(AllChase):
    name = "fixed"
    SPOTS = [(-2.5, 1.2), (-2.5, -1.2), (0.5, 1.5), (0.5, -1.5)]

    def play(self):
        v = self.v
        ids = [k for k in self.field_ids() if self.locked_until.get(k, -1) <= v.t or self.has_ball(k)]
        carrier = next((k for k in ids if self.has_ball(k)), None)
        g = carrier if carrier is not None else (min(ids, key=lambda k: dist(v.own[k].p, v.ball)) if ids else None)
        for i, k in enumerate(self.field_ids()):
            if k == g:
                if k == carrier:
                    self.shoot_now(k)
                else:
                    self.collect(k, aim=OPP_GOAL)
            else:
                p = self.SPOTS[(k - 1) % len(self.SPOTS)]
                self.move(k, p, 0.0)
        self.keeper()


class ShootOnly(Reference):
    """the reference without passes or carries: wins the ball the same way, shoots at once."""
    name = "shootonly"

    def decide(self, n, dd):
        shot = self.best_shot(self.v.ball)
        tgt = shot["target"] if shot is not None else OPP_GOAL
        return dict(num=n, kind="shot", target=tgt, speed=self.kick_speed, mode="flat", t=self.v.t)


class Random(TeamBase):
    name = "random"

    def update(self, view):
        self.v = view
        self.cmds = []
        if not hasattr(self, "next_t"):
            self.next_t = {}
        for k, r in view.own.items():
            if not r.on or view.t < self.next_t.get(k, 0.0):
                continue
            self.next_t[k] = view.t + 0.5
            x, y = self.rng.uniform(-4.3, 4.3), self.rng.uniform(-2.8, 2.8)
            self.cmds.append((k, "move", dict(x=float(x), y=float(y), theta=float(self.rng.uniform(-math.pi, math.pi)))))
            self.cmds.append((k, "dribble", dict(rpm=float(self.rng.choice([0.0, 3000.0])))))
            if self.rng.random() < 0.5:
                self.cmds.append((k, "kick", dict(speed=float(self.rng.uniform(1.0, 6.0)), mode="flat",
                                                  armed_for=0.5)))
        return self.cmds


class Idle(TeamBase):
    name = "idle"

    def update(self, view):
        return []


# ==============================================================================================================
# commands -> acts
# ==============================================================================================================
def to_act(n, skill, args) -> dict:
    """one team command as an act body of skill_api.py (entity = the robot's number as a string)."""
    a = {"type": skill, "entity": str(int(n))}
    a.update({k: v for k, v in args.items() if v is not None})
    return a


class Outbox:
    """the commands a team wants sent, latest per (robot, skill), released at most `per_act` at a time (a `batch` act
    holds at most 5): kicks first, then moves of robots near the ball, the keeper, dribbler changes, other moves; a
    command that waits gains priority."""

    def __init__(self, per_act=5):
        self.per_act = per_act
        self.pending = {}
        self.seq = 0

    def put(self, cmds, view=None):
        for n, skill, args in cmds:
            self.seq += 1
            if skill == "kick":
                pr = 0.0
            elif skill == "move":
                near = view is not None and n in view.own and dist(view.own[n].p, view.ball) < 1.2
                pr = 1.0 if near else (2.0 if n == KEEPER else 4.0)
            else:
                pr = 3.0
            old = self.pending.get((n, skill))
            self.pending[(n, skill)] = (pr, old[1] if old else self.seq, args)

    def take(self):
        if not self.pending:
            return []
        order = sorted(self.pending.items(), key=lambda kv: kv[1][0] + 0.02 * (kv[1][1] - self.seq))
        out = []
        for (n, skill), (pr, sq, args) in order[: self.per_act]:
            del self.pending[(n, skill)]
            out.append((n, skill, args))
        return out


def make(name: str, team: str = "blue", seed: int = 0, **opts):
    """a built-in team by name: reference, allchase, fixed, shootonly, random, idle."""
    table = {"reference": Reference, "allchase": AllChase, "fixed": Fixed, "shootonly": ShootOnly,
             "random": Random, "idle": Idle}
    return table[name](team=team, seed=seed, **opts)


# ==============================================================================================================
# the overhead camera: a colour detector (after docs/screening/soccer_ssl/render/detect.py, line C)
# ==============================================================================================================
# The tiles are straight-down pictures in the WORLD frame (image right = world +x, up = world +y; skill_api.py). Each
# robot top carries the SSL pattern (rules §3.2.5): a blue / yellow centre dot and four pink / green dots whose
# angular order gives the heading and whose colours give the id. The ball is orange. Detections are back-projected
# with the published pinhole calibration of /spec (CameraDef: pos, lookat, up, fovy_deg, width, height).
ROBOT_TOP_Z = 0.148
PAT_FRONT = math.atan2(0.054772, 0.035)
PAT_BACK = math.atan2(0.035, -0.054772)
PAT_TEMPLATE = {"FL": PAT_FRONT, "BL": PAT_BACK, "BR": -PAT_BACK, "FR": -PAT_FRONT}
PAT_IDS = ["PPGP", "GPGP", "GGGP", "PGGP", "PPPG", "GPPG", "GGPG", "PGPG",
           "GGGG", "PPPP", "PPGG", "GGPP", "GPGG", "GPPP", "PGGG", "PGPP"]
PAT_CODE = {c: i for i, c in enumerate(PAT_IDS)}


def _hsv(img):
    x = img[..., :3].astype(np.float32) / 255.0
    r, g, b = x[..., 0], x[..., 1], x[..., 2]
    v = x.max(-1)
    c = v - x.min(-1)
    s = np.where(v > 0, c / np.maximum(v, 1e-6), 0)
    cc = np.maximum(c, 1e-6)
    h = np.where(v == r, ((g - b) / cc) % 6, np.where(v == g, (b - r) / cc + 2, (r - g) / cc + 4)) * 60.0
    return h, s, v


def _masks(img):
    h, s, v = _hsv(img)
    return {
        "ball": (h > 12) & (h < 42) & (s > 0.6) & (v > 0.5),
        "yellow": (h > 48) & (h < 72) & (s > 0.5) & (v > 0.55),
        "G": (h > 95) & (h < 145) & (s > 0.6) & (v > 0.7),
        "blue": (h > 215) & (h < 265) & (s > 0.6) & (v > 0.45),
        "P": (h > 280) & (h < 320) & (s > 0.5) & (v > 0.5),
    }


def _blobs(mask, min_px=3):
    """4-connected components -> [(cy, cx, area)] in pixel-centre coordinates."""
    ys, xs = np.nonzero(mask)
    n = ys.size
    if n == 0:
        return []
    H, W = mask.shape
    idx = np.full((H + 2, W + 2), -1, np.int64)
    idx[ys + 1, xs + 1] = np.arange(n)
    nbs = [idx[ys + 1 + dy, xs + 1 + dx] for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1))]
    lab = np.arange(n)
    while True:
        new = lab.copy()
        for nb in nbs:
            ok = nb >= 0
            new[ok] = np.minimum(new[ok], lab[nb[ok]])
        new = new[new]
        if np.array_equal(new, lab):
            break
        lab = new
    ids, inv, cnt = np.unique(lab, return_inverse=True, return_counts=True)
    sy = np.bincount(inv, ys + 0.5)
    sx = np.bincount(inv, xs + 0.5)
    return [(sy[k] / cnt[k], sx[k] / cnt[k], int(cnt[k])) for k in range(len(ids)) if cnt[k] >= min_px]


def _cam_basis(cam):
    fwd = np.subtract(cam["lookat"], cam["pos"]).astype(float)
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, cam["up"])
    right /= np.linalg.norm(right)
    return right, np.cross(right, fwd), fwd


def ground_point(cam, u, v, z=0.0):
    """the world point at height z seen at pixel (u, v) of a CameraDef (u right, v down from the top-left)."""
    right, up, fwd = _cam_basis(cam)
    f = (cam["height"] / 2) / math.tan(math.radians(cam["fovy_deg"]) / 2)
    ray = fwd + right * (u - cam["width"] / 2) / f - up * (v - cam["height"] / 2) / f
    t = (z - cam["pos"][2]) / ray[2]
    return np.asarray(cam["pos"], float) + t * ray


def detect_tile(img, cam, top_z=ROBOT_TOP_Z, ball_z=BALL_R):
    """robots (team, world x, y, yaw, id) and balls (world x, y) in one camera tile."""
    mk = _masks(img)
    bl = {k: _blobs(v) for k, v in mk.items()}
    ax = np.array(cam["pos"][:2], float)

    def world(b, z):
        return ground_point(cam, b[1], b[0], z)[:2]

    dots = [(world(b, top_z), col) for col in ("P", "G") for b in bl["P" if col == "P" else "G"]]
    robots = []
    for team in ("blue", "yellow"):
        for b in bl[team]:
            if b[2] < 6:
                continue
            c = world(b, top_z)
            near = [(p, col) for p, col in dots if 0.035 < np.linalg.norm(p - c) < 0.095]
            rob = {"team": team, "x": float(c[0]), "y": float(c[1]), "axis_d": float(np.linalg.norm(c - ax)),
                   "yaw": None, "id": None}
            if len(near) == 4:
                ang = sorted((math.atan2(p[1] - c[1], p[0] - c[0]), col) for p, col in near)
                order = ["FL", "BL", "BR", "FR"]
                best = None
                for k in range(4):
                    labels = order[k:] + order[:k]
                    diffs = [wrap(a - PAT_TEMPLATE[lab]) for (a, _), lab in zip(ang, labels)]
                    th = math.atan2(sum(math.sin(d) for d in diffs), sum(math.cos(d) for d in diffs))
                    res = sum(wrap(d - th) ** 2 for d in diffs)
                    if best is None or res < best[0]:
                        best = (res, th, {lab: col for (_, col), lab in zip(ang, labels)})
                _, th, cols = best
                rob["yaw"] = th
                rob["id"] = PAT_CODE.get("".join(cols[k] for k in ("FL", "FR", "BL", "BR")))
            robots.append(rob)
    balls = []
    for b in bl["ball"]:
        if b[2] < 3:
            continue
        p = world(b, ball_z)
        balls.append({"x": float(p[0]), "y": float(p[1]), "axis_d": float(np.linalg.norm(p - ax)), "area": b[2]})
    return {"robots": robots, "balls": balls}


def detect_tiles(img, tiles, cams):
    """all tiles of one observation image -> (robots, balls) merged over the cameras' seams (world frame).
    tiles: [{camera, x, y, w, h}] (the tile's place in the image); cams: {name: CameraDef}."""
    robots, balls = [], []
    for t in tiles:
        cam = cams.get(t.get("camera") or t.get("name"))
        if cam is None:
            continue
        x0, y0 = int(t.get("x", 0)), int(t.get("y", 0))
        w = int(t.get("w", t.get("width", cam["width"])))
        h = int(t.get("h", t.get("height", cam["height"])))
        det = detect_tile(img[y0:y0 + h, x0:x0 + w], cam)
        for r in det["robots"]:
            same = [o for o in robots if o["team"] == r["team"] and math.hypot(o["x"] - r["x"], o["y"] - r["y"]) < 0.1]
            if not same:
                robots.append(r)
            elif (r["id"] is not None, -r["axis_d"]) > (same[0]["id"] is not None, -same[0]["axis_d"]):
                robots[robots.index(same[0])] = r
        for b in det["balls"]:
            same = [o for o in balls if math.hypot(o["x"] - b["x"], o["y"] - b["y"]) < 0.1]
            if not same:
                balls.append(b)
            elif b["axis_d"] < same[0]["axis_d"]:
                balls[balls.index(same[0])] = b
    return robots, balls


class CameraTracker:
    """the ball and the opponents from successive camera frames (team frame): positions from the detector, the
    ball's velocity from a least-squares line over the last ~0.12 s of detections (reset when the ball jumps: a
    kick), the opponents' velocities from differences; the ball is kept up to 0.5 s when unseen (hidden under a
    robot's dribbler: then it is put at that robot's dribbler)."""

    def __init__(self):
        self.hist = deque(maxlen=12)
        self.opp_prev = {}
        self.ball_last = None

    def update(self, t, sign, robots, balls, own, my_color):
        def tp(x, y):
            return (x, y) if sign > 0 else (-x, -y)

        opp = {}
        for r in robots:
            if r["team"] == my_color or r["id"] is None or r["id"] > 15:
                continue
            p = tp(r["x"], r["y"])
            yaw = 0.0 if r["yaw"] is None else wrap(r["yaw"] if sign > 0 else r["yaw"] + math.pi)
            prev = self.opp_prev.get(r["id"])
            v = (0.0, 0.0)
            if prev is not None and 0.0 < t - prev[0] < 0.3:
                dt = t - prev[0]
                v = ((p[0] - prev[1][0]) / dt, (p[1] - prev[1][1]) / dt)
            self.opp_prev[r["id"]] = (t, p)
            opp[int(r["id"])] = Bot(p, yaw, v, 0.0, True)
        ball = None
        if balls:
            cand = [tp(b["x"], b["y"]) for b in balls]
            if self.ball_last is not None:
                cand.sort(key=lambda q: dist(q, self.ball_last[1]))
            ball = cand[0]
        if ball is not None:
            if self.hist and dist(ball, self.hist[-1][1]) > 0.35:
                self.hist.clear()
            self.hist.append((t, ball))
            self.ball_last = (t, ball)
        elif self.ball_last is not None and t - self.ball_last[0] < 0.5:
            # hidden: under one of the robots (at its dribbler) or where it was last seen
            bl = self.ball_last[1]
            near = min(list(own.values()) + list(opp.values()), key=lambda r: dist(r.p, bl), default=None)
            ball = bl
            if near is not None and dist(near.p, bl) < 0.25:
                ball = (near.p[0] + KICK_REACH * math.cos(near.yaw), near.p[1] + KICK_REACH * math.sin(near.yaw))
        v = (0.0, 0.0)
        pts = [e for e in self.hist if t - e[0] <= 0.121]
        if len(pts) >= 2:
            ts = np.array([e[0] for e in pts])
            xs = np.array([e[1][0] for e in pts])
            ys = np.array([e[1][1] for e in pts])
            tm = ts - ts.mean()
            den = float((tm * tm).sum())
            if den > 1e-9:
                v = (float((tm * (xs - xs.mean())).sum() / den), float((tm * (ys - ys.mean())).sum() / den))
        return (ball, v, opp)


# ==============================================================================================================
# act(view) players (core's built-in player interface: Sport.players())
# ==============================================================================================================
def _own_from_state(st_robots):
    """the observation's own robots (World.own_state per robot, keyed by number) as Bots."""
    own = {}
    items = st_robots.items() if isinstance(st_robots, dict) else ((r.get("number"), r) for r in st_robots)
    for k, r in items:
        n = int(k)
        if not r.get("on_field", True) or "pose" not in r:
            own[n] = Bot((9.0, 9.0), 0.0, on=False)
            continue
        pose = r["pose"]
        if isinstance(pose, dict):
            pose = (pose["x"], pose["y"], pose.get("theta", pose.get("yaw", 0.0)))
        vel = r.get("vel") or (0.0, 0.0, 0.0)
        own[n] = Bot((float(pose[0]), float(pose[1])), float(pose[2]), (float(vel[0]), float(vel[1])),
                     float(vel[2]) if len(vel) > 2 else 0.0, True, bool(r.get("ball_in_beam", False)), False,
                     float(r.get("kicker_charge", 1.0)))
    return own


def _image(obs):
    import base64
    import io

    from PIL import Image

    b = obs.get("image_png_b64")
    if not b:
        return None
    return np.asarray(Image.open(io.BytesIO(base64.b64decode(b))).convert("RGB"))


class TeamPlayer:
    """a built-in team as an act(view) player of one team seat: it reads its own robots' state and the referee from
    the observation, the ball and the opponents from the overhead camera tiles (or from `truth` when the observation
    carries one: the screening's truth variants), runs the team every call and returns one `batch` act of at most
    five commands (the most urgent first; the rest wait for the next call)."""

    def __init__(self, team="reference", spec=None, seat="A", seed=0, perception="camera", **opts):
        self.spec = spec or {}
        self.team = make(team, seed=seed, **opts)
        self.perception = perception
        self.box = Outbox(5)
        self.track = CameraTracker()
        cams = self.spec.get("cameras") or (self.spec.get("camera") or {}).get("cameras") or []
        self.cams = {c["name"]: c for c in cams if isinstance(c, dict) and "name" in c}
        self.color = self.spec.get("team_color") or self.spec.get("color")
        self.last_view = None

    def view_from(self, view, img=None) -> TeamView | None:
        st = view.get("state") or view
        obs = view.get("observation") or {}
        ref = st.get("referee") or {}
        sign = int((st.get("frame") or {}).get("attack_sign") or ref.get("attack_sign") or 1)
        t = float(st.get("t_sim", st.get("t", 0.0)))
        own = _own_from_state(st.get("robots") or st.get("us") or {})
        if "truth" in st:
            tv = view_from_truth(st["truth"], own_states=st.get("robots"))
            ball, bv, opp = tv.ball, tv.ball_v, tv.opp
            # the onboard formats give no own pose (only drifting odometry): the truth's own robots then, with the
            # robots' own sensors (break beam, capacitor) from the state
            if not any(r.on for r in own.values()):
                own = tv.own
                # and its move targets are read in each robot's odometry frame: remember both poses per robot
                self.odom = {}
                for k, r in (st.get("robots") or {}).items():
                    o = r.get("odom")
                    if o is not None and int(k) in own and own[int(k)].on:
                        self.odom[int(k)] = (own[int(k)].p, own[int(k)].yaw, (o[0], o[1]), o[2])
        else:
            img = _image(obs) if img is None else img
            if img is None or not self.cams:
                return None
            color = self.color or st.get("color") or st.get("team_color")
            robots, balls = detect_tiles(img, obs.get("tiles") or [], self.cams)
            if color is None:  # our colour: the team whose detected robots sit where our own robots are
                color = self._guess_color(robots, own, sign)
            t_frame = t - float((st.get("frame") or {}).get("age_s", 0.0))
            ball, bv, opp = self.track.update(t_frame, sign, robots, balls, own, color)
            if ball is None:
                ball = self.last_view.ball if self.last_view is not None else (0.0, 0.0)
            age = t - t_frame
            if age > 0 and math.hypot(*bv) > 0.3:  # the picture is `age` old: carry a rolling ball to now
                P = BallPath(ball, bv)
                sp = P.v_at(age)
                ball, bv = P.at(age), (P.d[0] * sp, P.d[1] * sp)
                opp = {k: replace(o, p=(o.p[0] + o.v[0] * age, o.p[1] + o.v[1] * age)) for k, o in opp.items()}
        return TeamView(t=t, team=str(self.color or ""), sign=sign, ball=(float(ball[0]), float(ball[1])),
                        ball_v=(float(bv[0]), float(bv[1])), own=own, opp=opp, ref=ref_from_view(ref))

    def _guess_color(self, robots, own, sign):
        best, bd = "blue", math.inf
        for col in ("blue", "yellow"):
            d = 0.0
            for r in own.values():
                if r.on:
                    xs = [math.hypot(o["x"] * sign - r.p[0], o["y"] * sign - r.p[1]) for o in robots if o["team"] == col]
                    d += min(xs, default=1.0)
            if d < bd:
                best, bd = col, d
        self.color = best
        return best

    def act(self, view):
        tv = self.view_from(view)
        if tv is None:
            return None
        self.last_view = tv
        self.box.put(self.team.update(tv), tv)
        cmds = self.box.take()
        if not cmds:
            return None
        if getattr(self, "odom", None):
            cmds = [(n, sk, self._to_odom(n, a) if sk == "move" else a) for n, sk, a in cmds]
        acts = [to_act(n, s, a) for n, s, a in cmds]
        return acts[0] if len(acts) == 1 else {"type": "batch", "commands": acts}

    def _to_odom(self, n, a):
        """a team-frame move target in robot n's odometry frame (onboard formats): the same offset from the robot."""
        if n not in self.odom:
            return a
        (px, py), th, (ox, oy), oth = self.odom[n]
        dx, dy = a["x"] - px, a["y"] - py
        c, s_ = math.cos(oth - th), math.sin(oth - th)
        b = dict(a)
        b["x"] = round(ox + c * dx - s_ * dy, 4)
        b["y"] = round(oy + s_ * dx + c * dy, 4)
        b["theta"] = round(wrap(a.get("theta", 0.0) - th + oth), 4)
        b.pop("t", None)
        return b

    def review(self, reply):
        self.track = CameraTracker()
        self.box = Outbox(5)
        return "review", "built-in player: same plan"


def _factory(team, **opts):
    def f(spec, seat, seed=0):
        return TeamPlayer(team, spec=spec, seat=seat, seed=seed, **opts)
    return f


PLAYERS = {"reference": _factory("reference"), "allchase": _factory("allchase"), "fixed": _factory("fixed"),
           "random": _factory("random"), "stand": _factory("idle")}

class RLPlayer(TeamPlayer):
    """the RL tier (L-RL, opponents/rl.py: L3 with a trained network choosing each robot's option every 0.2 s) as a
    built-in seat's player (core RO_BUILTIN_SEATS): it reads the truth the core hands an in-process seat
    (`uses_truth`; view["truth"] = SSLMatch.builtin_truth(seat)), as L3 reads it, and sends at most five commands per
    `batch` act like any player (the service's latency applies as to any seat). Weights: rl/<policy>/policy.npz (numpy, argmax: deterministic)."""

    uses_truth = True

    def __init__(self, spec=None, seat="B", seed=0, weights=None):
        from opponents.rl import RLTeamCore, load_policy  # noqa: PLC0415  (the sport directory is on the path)

        self.spec = spec or {}
        self.team = RLTeamCore(load_policy(weights), team="yellow" if str(seat)[:1] == "B" else "blue", seed=seed)
        self.perception = "truth"
        self.box = Outbox(5)
        self.track = CameraTracker()
        self.cams = {}
        self.color = None
        self.last_view = None

    def act(self, view):
        if "truth" in view:  # the core's truth for an in-process seat: read through the truth path of view_from
            st = dict(view.get("state") or {})
            st["truth"] = view["truth"]
            view = dict(view, state=st)
        return super().act(view)

    def review(self, reply):
        self.box = Outbox(5)
        return "review", "built-in RL player: same policy"


def rl_factory(spec, seat, seed=0):
    return RLPlayer(spec=spec, seat=seat, seed=seed)


PLAYERS["rl"] = rl_factory

# The tasks' oracle (sport.toml [players] reference_class; solution/oracle_play.py through core/client.py, which calls
# factory(spec, seat, seed)): the reference team as a seat's player. `Reference` is the team class (team, seed, ...).
ReferencePlayer = PLAYERS["reference"]
