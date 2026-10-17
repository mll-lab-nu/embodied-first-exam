"""Core of the table-tennis match service (interactive mode): one game against a scripted opponent, with the duel's
rules: first to 5 points, from 4:4 a lead of 2, at 6:6 the next point wins (7 at most); the expedite rule (the
receiver's 13th good return in a rally wins it the point, ITTF 2.15.4) bounds every rally. The players serve
(serve.py, ITTF 2.6): the robot serves the first 2 points, the opponent the next 2, ...; from 4:4 one each (2.13.3).

The robot (Franka + paddle on an x-y rail base, y < 0) plays a scripted opponent on the far side (y > 0). The opponent
is part of the world, like the physics: a deterministic function of the simulator state, evaluated inside every control
step, so a recorded sequence of the robot's joint targets and tosses replays the whole match bit-exactly.

Point flow (all inside step()):
  ready     READY_STEPS control steps (the receiver gets ready).
  our serve the ball waits hidden in our column until our `toss` (within serve.SERVE_CLOCK_S, else a failed service;
            the DELAY_LIMIT-th loses the match); it rests on the toss device, is projected straight up, and our strike
            and the bounces are judged by serve.ServeJudge (Laws 2.6.2-2.6.4, 2.9.1.1). A good service goes to the
            opponent like any of our returns.
  opp serve the opponent tosses from its end (serve.OPP_TOSS_VZ) and, as the toss falls back, plays a serve of the
            official serve library from that point (serve_library.json: the legal services a Franka on a rail made
            under the real limits; the level draws from the easiest OPP_POOL_SHARE of them): it bounces on its half,
            crosses the net, bounces on ours.
  our leg   the ball comes to us (a serve, or the opponent's return); the robot hits or not. The leg is judged like the
            rally task: exactly one own bounce before the hit, one paddle contact, first contact after the hit other
            than the net = the opponent's half (a return may touch the net, ITTF 2.7.1). A failed leg = the
            opponent's point. A serve that touches the net is a let (ITTF 2.9.1.1; the recorded serves clear the net).
  opp leg   our ball bounced on the opponent's half. The opponent (below) either returns it (a new "our leg" starts at
            its hit) or misses it (our point once the ball is dead).

The opponent (LEVELS): a kinematic paddle on its end line, at the centre when a point starts. `reaction_s` after our
hit it moves towards the (perfectly predicted) ball at up to `chase`; after each of its shots it walks back towards the
centre at up to `recover` (revision wallclock-10: within the rail's real limits, 8 m/s^2 and 200 m/s^3, rcb_tt.OPP_LIM). When the ball reaches the top of its bounce on its half (or y = HIT_Y) it evaluates our shot's pressure
    pressure = max(|ball x - its paddle x| / reach, (our speed off the paddle - SPEED_FREE) / (max_speed - SPEED_FREE))
and, deterministically: pressure > 1 -> it misses (our point); > PRESSURE_WEAK -> a weak return (slow, central, no
spin); < PRESSURE_PASSIVE -> it attacks (its widest, fastest ball, full spin); else a normal return (a seeded target
within the level's width, its pace, top- or backspin plus a sidespin share). Our services are received the same way.
It sets the ball's velocity and spin (an impulse; it never touches the ball physically) so that the ball lands on our
half and its apex after our bounce is in the box the reference stroke returns reliably; an unreachable target moves
towards the centre and the pace down. Every shot stays within the real-limited arm's envelope (OPP_SPEED_MAX,
OPP_SPIN_MAX, OPP_BLADE_MAX). It never misses except by the rule above.
Our strokes scatter: the commanded paddle state is perturbed by a seeded PADDLE_SCATTER per shot (plan_paddle).
"""
from __future__ import annotations

import io
import json
import os
import time
from collections import deque
from pathlib import Path

import numpy as np

import mujoco as mj
import rally
import rcb_tt
import serve as SV
from rally import BallModel, world_spin, hermite  # noqa: F401
from rcb_tt import ARM_VEL, BASE_HI, BASE_LO, CONTROL_DT, HOME

HERE = Path(__file__).resolve().parent
SCENE, INSTANCE = rally.SCENE, rally.INSTANCE
SERVE_LIBRARY = json.load(open(HERE / "serve_library.json"))      # the official serve library (wallclock-10)
SERVES = {b["id"]: b for b in SERVE_LIBRARY["serves"]}
REVISION = "wallclock-15"    # 15: the setpoint generator and the planner at 0.9 of the velocity limits, the joint-velocity reflex; 14: realistic restitution, scatter 1 cm / 1.5 deg / 5 %, the JerkLimiter brakes relative to the reference, serve depth rule D13, serve library rebuilt; 13: the opponent recalibrated; 12: the setpoint generator brakes within the jerk in force (no ringing); 6: the players' images (fine arm meshes); 7: the robot stands on an x-y rail base (rcb_tt.BASE_*); 8: the players serve (serve.py)
                             # 9: table contact allowed (D4), table avoidance, serve receive recalibrated
                             # 10: the real robot's limits (rcb_tt.TTServo, the arm and the rail), the limits-aware stroke
                             #     planner (bodies/trajopt), the opponent held to the same limits and recalibrated
                             # 11: at most 2 service lets in a row (serve.LET_LIMIT, D12)


# The scripted opponent's serves (format match): the official serve library (serve_library.json, made by
# prototypes/tabletennis_serve/build_library.py): the legal services a Franka-on-a-rail server made under the real Panda
# limits (the robot's own serve code, the sport's referee), stored as the ball's state at the strike, in order of
# difficulty for the receiver (a low apex after the bounce on its court, then spin). Each is preceded by a legal toss
# (serve.OPP_TOSS_VZ from the strike point, struck as it falls back through it). Levels draw from the easiest share.
# Until revision wallclock-9 the opponent played recorded human serves (DeepMind; 3.9-6.4 m/s, up to 97 rad/s) that the
# real arm cannot make.
OPP_POOL = [b["id"] for b in SERVE_LIBRARY["serves"]]
OPP_POOL_SHARE = {1: 0.25, 2: 0.4, 3: 0.55, 4: 1.0}   # the easiest share of the serve library per level
WIN_POINTS = 5                 # the duel's format (duel.py): first to 5 ...
WIN_BY = 2                     # ... from 4:4 a lead of 2 ...
CAP_POINTS = 7                 # ... at 6:6 the next point wins
EXPEDITE_RETURNS = 13          # ITTF 2.15.4: the receiver's (our) 13th good return in a rally wins us the point
MAX_POINTS_WITH_LETS = 40      # guard: 13 scoring points at most, so this needs 27+ lets; then the player ahead wins,
                               # at a level score the player who won the last point
READY_STEPS = 80               # 0.8 s between points
LEG_STEPS = 250                # our leg is lost if nothing decisive happens 2.5 s after it started
CAM_EVERY = 2                  # 50 Hz camera frames
HIT_Y = 1.55
OPP_X_MAX = 1.0                # the opponent's paddle travel along its end line (as our rail, |x| <= 1.0)
OPP_Y, OPP_Z = 1.75, 0.22      # where the opponent's paddle is drawn
SHOULDER = np.array([0.0, -1.75, 0.33])
APEX_X_MAX = 0.30              # the opponent only plays balls whose apex after our bounce is in the box the reference
                               # stroke returns reliably (|x| <= 0.30, -1.38 <= y <= -1.10, 0.25 <= z <= 0.45)
rcb_tt.HORIZON = 10 ** 7
OPP_HALF = rally.OPP_HALF

LEVELS = {   # defence: reaction, chase / recovery speed, reach, too-fast threshold; attack: width, pace, spin, sidespin share
    # recalibrated under the real limits (revision wallclock-10; README "The real limits in the sport"): every value
    # monotone in the level; the opponent's paddle and shots obey the real limits (OPP_* below, rcb_tt.OPP_LIM)
    # revision wallclock-13 (screening 2026-10-11): short services are no longer near-automatic points (short_y1 from
    # 0.85 / 0.80 / 0.76 / 0.62 to 0.62 / 0.58 / 0.54 / 0.50: a program that only served short and never returned a
    # ball won 4/10 at L1 and SOL took all its 6 points at L2 that way), and L1 / L2 are easier in the rally
    # (reaction 0.30 -> 0.34 / 0.28 -> 0.31 s, chase 0.42 -> 0.36 / 0.45 -> 0.40 m/s, reach 0.24 -> 0.20 / 0.26 -> 0.23 m)
    # so that the reference still wins L1 (docs/screening/tabletennis.md)
    # revision wallclock-14 (re-screen 2026-10-12, realistic restitution): the softer table shortens the ball's travel
    # after its bounce, so the same services met the opponent nearer the net (the reference's L1 points from short
    # services 6/52 -> 34/82 at the old values): short_y1 0.62 / 0.58 / 0.54 / 0.50 -> 0.57 / 0.53 / 0.49 / 0.45; and
    # L1 / L2 attack more gently (pace 3.9 -> 3.6 / 4.0 -> 3.75 m/s, spin 8 -> 4 / 10 -> 6 rad/s, width 0.12 -> 0.06 /
    # 0.15 -> 0.10 m) so that the reference still wins L1 (reach / chase / reaction barely mattered: 237 of 240 matches
    # unchanged). Truth reference 15/11/5/2 of 20, camera 13/10/5/0 (screening/tabletennis_rescreen_zh.md)
    # revision wallclock-15 (the reflexes cost the reference strokes): L1 / L2 short_y1 back to 0.62 / 0.57 (truth
    # reference L1 10/20 -> 11/20, 20 seeds; screening/tabletennis_rescreen_zh.md)
    1: dict(reaction_s=0.34, chase=0.36, recover=0.30, reach=0.20, max_speed=5.2,
            width=0.06, pace=3.6, spin=4.0, side=0.0, seed=101, chase_serve=0.65, short_y1=0.62),
    2: dict(reaction_s=0.31, chase=0.40, recover=0.32, reach=0.23, max_speed=5.3,
            width=0.10, pace=3.75, spin=6.0, side=0.0, seed=202, chase_serve=0.72, short_y1=0.57),
    3: dict(reaction_s=0.27, chase=0.46, recover=0.33, reach=0.27, max_speed=5.4,
            width=0.18, pace=4.1, spin=12.0, side=0.1, seed=303, chase_serve=0.78, short_y1=0.49),
    4: dict(reaction_s=0.24, chase=0.52, recover=0.36, reach=0.31, max_speed=5.6,
            width=0.26, pace=4.6, spin=25.0, side=0.5, seed=404, chase_serve=1.00, short_y1=0.45),
}
# Export-only opponent tiers (tools/fexam.toml `tier`, MatchConfig.params {"opponent_tier": NAME}; never an official
# level: the official levels are LEVELS 1-4 and nothing here changes them). A tier is a set of LEVELS values on top of
# its base level (`level`, which keeps that level's serve pool), played only on development seeds (< 100000). Like every
# level the opponent reads the simulator's true ball state with no perception noise (_predict_opp_hit) and obeys the
# real limits (OPP_*, rcb_tt.OPP_LIM); a tier only moves the level's values within them.
#   top   (First Exam top tier, 2026-10-16; olympiad_review/handoff/fexam_top_tiers.md): level 4's full serve library
#         and the strongest shots the real-limited arm makes - width 0.30 m (the edge of the returnable apex box,
#         APEX_X_MAX), pace 5.0 m/s (its attack 5.5 = OPP_SPEED_MAX), spin 34 rad/s (OPP_SPIN_MAX), level 4's sidespin
#         share - with level 2's defence (reaction, chase / recovery, reach, too-fast threshold, short-service limit,
#         service chase). A stronger defence leaves the truth-state reference no points to win (it scores only from the
#         opponent's misses): level 4's defence with level 1's shots 1 of 14 seeds, level 4 itself 0 of 14; this tier
#         5 of 20 (seeds 1-20, D = 5), level 2's defence with level 4's shots 1 of 10.
TIERS = {
    "top": dict(level=4, lv=dict(reaction_s=0.31, chase=0.40, recover=0.32, reach=0.23, max_speed=5.3, short_y1=0.57,
                                 chase_serve=0.72, width=0.30, pace=5.0, spin=34.0, side=0.5)),
}


# Receiving our service (recalibrated 2026-10-07): the opponent is ready for a service, so it moves at chase_serve
# (it anticipates width), and a short service is harder: a further pressure term grows from 0 at a hit point
# SHORT_Y0 m from the net to 1 at short_y1 m (the ball's top over the table); better levels reach shorter balls.
SHORT_Y0 = 1.25
SPEED_FREE = 3.8              # our shot's speed off the paddle below this puts no pressure on the opponent
PRESSURE_WEAK = 0.75          # our shot's pressure above this (but <= 1) -> the opponent only manages a weak return
PRESSURE_PASSIVE = 0.35       # below this the opponent attacks: its widest, fastest ball with its most spin
# The opponent obeys the real limits too (revision wallclock-10). Its paddle moves along its end line like our rail
# base: speed <= min(the level's speed, 2 m/s), acceleration <= 8 m/s^2, jerk <= 200 m/s^3 (rcb_tt.BASE_LIM, a jerk-
# limited setpoint at 1 kHz). Its shots stay within what the real-limited Franka produces in this sport: the ball's
# speed off the paddle <= OPP_SPEED_MAX, spin <= OPP_SPIN_MAX, and the blade speed the contact law needs for the shot
# (instructions: normal restitution 0.80 since revision 14, tangential relative velocity kept) <= OPP_BLADE_MAX.
OPP_SPEED_MAX = 5.5           # m/s: the limited reference's shots off the paddle (tt-planner, 102 shots): p95 5.3, max 5.7
OPP_SPIN_MAX = 34.0           # rad/s: the most spin of a legal service in the serve library (the arm's strongest brush)
OPP_BLADE_MAX = 2.0           # m/s: the blade speed the limited arm delivers at a contact (README "Real limits")
E_BLADE = 0.80                # the contact law's normal restitution (sport.toml [spec] blade)


def match_winner(score):
    """0 (us) / 1 (opponent) if the game is won at this score [us, opponent], else None (same rule as the duel)."""
    for i in (0, 1):
        a, b = score[i], score[1 - i]
        if a >= CAP_POINTS or (a >= WIN_POINTS and a - b >= WIN_BY):
            return i
    return None


def towards_own_half(p, v, horizon_s=0.5):
    """Whether a ball at p moving with v is over our half (y < 0) or its straight-line path reaches it within horizon_s:
    a ball touching a robot outside this is not obstruction, the shot was going out (the duel's rule)."""
    for t in np.linspace(0.0, horizon_s, 26):
        x, y = p[0] + v[0] * t, p[1] + v[1] * t
        if abs(x) <= 0.7625 and -1.37 <= y <= 0.0:
            return True
    return False


def _top(e) -> bool:
    """A table contact on the top surface (the playing surface; the vertical sides are not, Law 2.1.2)."""
    cp, cn = e.get("contact_pos"), e.get("contact_normal")
    return bool(cp is not None and cn is not None and cn[2] > 1e-6 and abs(cp[0]) <= .7625 + .001
                and abs(cp[1]) <= 1.37 + .001)


def ball_state(d):
    return d.qpos[0:3].copy(), d.qvel[0:3].copy(), world_spin(d)


WRIST_POW = float(os.environ.get("RCB_TT_WRIST_POW", "0"))     # returns: joint weights x (jerk cap)^WRIST_POW


class Match(rally.Rally):
    """The match: step(q) advances one control step (the arm command layer, arm_commands.Core, supplies q)."""

    def __init__(self, level: int = 1, lv_override: dict | None = None):
        self.level = int(level)
        self.lv = dict(LEVELS.get(self.level, LEVELS[1]))
        if lv_override:
            self.lv.update(lv_override)
        if os.environ.get("MATCH_SEED"):           # other instances of the same level: serves + opponent + scatter
            self.lv["seed"] = int(os.environ["MATCH_SEED"])
        self.s = rcb_tt.Session(instance=str(INSTANCE), scene=str(SCENE))
        self.base_rest = HOME.copy()       # where the base goes when no stroke is under way (`move`; home at each point)
        self.bm = BallModel()
        self._twin = None
        self._ik_seed = None
        self._planned_hit = None
        rng = np.random.default_rng(self.lv["seed"])
        pool = OPP_POOL[:int(np.ceil(OPP_POOL_SHARE.get(self.level, 1.0) * len(OPP_POOL)))]
        self.serve_ids = [str(x) for x in rng.choice(sorted(pool), size=2 * CAP_POINTS - 1, replace=False)]
        self.n_opp_serves = 0              # the opponent's serves so far (the next one is serve_ids[n_opp_serves])
        self.first_server = 0              # format match: you serve first (no toss of a coin: deviation D2)
        self.delay_faults = [0, 0]         # undue-delay faults (serve.SERVE_CLOCK_S); the DELAY_LIMIT-th loses the match
        self.disqualified = None
        self.serve_lets = 0                # service lets since the last point scored (serve.LET_LIMIT, D12)
        self.our_serves: list[dict] = []   # our services: toss, strike, verdict
        self.score = [0, 0]                # [robot, opponent]
        self.points: list[dict] = []       # per point: winner, how, legs
        self.legs: list[dict] = []         # every leg of the match (ours and the opponent's shots)
        self.results: list[dict] = []      # our legs' results (rally-style)
        self.shots: list[dict] = []
        self.hist: deque = deque(maxlen=12)  # recent camera snapshots for the views
        self.frames: list[dict] = []       # (internal) ball camera frames of the current leg, for timing only
        self.done = False
        self.winner = None                 # 0 us, 1 the opponent (set when the game ends)
        self.phase = "swing"
        self.plan, self.plan_j, self._rec = [], 0, {}
        self.contact_k = 0
        self.n_our_legs = 0                # every ball that came to us (also the per-leg RNG streams)
        self.n_our_shots = 0               # our shots: legs in which our paddle touched the ball
        self.i = 0
        self._start_point(hold_from=0)

    # ------------------------------------------------------------------ point / leg bookkeeping
    def _start_point(self, hold_from: int):
        n = len(self.points)
        self.point_returns = 0             # the receiver's good returns in this rally (expedite rule)
        self.base_rest = HOME.copy()       # the base's rest position is home again at every point
        self.point_server = SV.server_of((self.score[0], self.score[1]), self.first_server, WIN_POINTS)
        self.judge = None
        self.s.substep_hook = None
        if self.point_server == 1:         # the opponent serves: a toss, then a recorded serve from where it falls
            sid = self.serve_ids[self.n_opp_serves % len(self.serve_ids)]
            self.n_opp_serves += 1
            toss_k = hold_from + READY_STEPS
            P0 = np.array(SERVES[sid]["pos"], float)
            Pt, Vt, _, _ = self.bm.rollout(P0, np.array([0.0, 0.0, SV.OPP_TOSS_VZ]), np.zeros(3), 1500)
            fall = np.flatnonzero((Vt[:, 2] < 0) & (Pt[:, 2] <= P0[2]))
            n_toss = int(np.ceil((int(fall[0]) + 1) / 10.0))            # control steps until it is back at P0
            self._opp_toss = (P0, Pt, Vt)
            self.leg = {"kind": "serve", "serve": sid, "point": n, "hold_from": hold_from, "toss_k": toss_k,
                        "launch": toss_k + SV.TOSS_REST_STEPS + n_toss, "state": "incoming"}
        else:                              # we serve: the ball waits in our toss device until our toss
            self.leg = {"kind": "our_serve", "point": n, "hold_from": hold_from, "open": hold_from + READY_STEPS,
                        "deadline": hold_from + READY_STEPS + int(round(SV.SERVE_CLOCK_S / CONTROL_DT)),
                        "launch": hold_from + READY_STEPS, "state": "waiting", "toss": None}
        self.legs.append(self.leg)
        self.opp = {"tx": 0.0, "plan_k": None, "speed": self.lv["recover"]}    # ready at the centre, at rest
        self._opp_jl = rcb_tt.RailLimiter(rcb_tt.OPP_LIM, rcb_tt.PHYS_DT, q0=np.zeros(1))
        self._new_leg_bookkeeping()
        self._park()

    def _new_leg_bookkeeping(self):
        self.frames = []
        s = self.s
        s._events.clear(); s._last_touch.clear(); s._robot_table = 0; s._robot_net = 0; s._v_out = None
        self._judged = 0
        self.i = self.n_our_legs

    def _park(self):
        """The ball before it is free: the opponent's serve - on its toss device at the toss point, then tossed
        (played back from the ball model), at the strike the recorded serve; our serve - hidden in our column until our
        toss, then at rest at the toss point for serve.TOSS_REST_STEPS."""
        d, leg = self.s.d, self.leg
        d.qpos[3:7] = [1, 0, 0, 0]
        if leg["kind"] == "serve":
            P0, Pt, Vt = self._opp_toss
            i = (self.k - leg["toss_k"] - SV.TOSS_REST_STEPS) * 10 - 1
            if self.k >= leg["launch"]:
                b = SERVES[leg["serve"]]
                d.qpos[0:3] = b["pos"]; d.qvel[0:3] = b["vel"]; d.qvel[3:6] = b["spin"]
            elif i >= 0:
                d.qpos[0:3] = Pt[min(i, len(Pt) - 1)]; d.qvel[0:3] = Vt[min(i, len(Vt) - 1)]; d.qvel[3:6] = 0.0
            else:
                d.qpos[0:3] = P0; d.qvel[0:6] = 0.0
            return
        if leg["state"] == "waiting":
            b = self.s.d.qpos[self.s._qadr[:2]]
            d.qpos[0:3] = [b[0], b[1], -0.3]; d.qvel[0:6] = 0.0          # inside the column: no contact, not drawn
        else:                                                             # at rest on the toss device
            d.qpos[0:3] = leg["toss"]["pos"]; d.qvel[0:6] = 0.0

    def _cur(self) -> dict:
        return self.leg

    def in_play(self) -> bool:
        if self.leg["kind"] == "our_serve" and self.leg["state"] == "waiting":
            return False
        return self.k > self.leg["launch"]

    def t_since_launch(self) -> float:
        return round((self.k - self.leg["launch"]) * CONTROL_DT, 6)

    # ------------------------------------------------------------------ the opponent
    def opp_x(self) -> float:
        return float(self._opp_jl.q[0])

    def _opp_step(self):
        """One control step of the opponent's paddle towards its goal tx (the rail's real limits, the level's speed)."""
        o, jl = self.opp, self._opp_jl
        jl.V = np.array([min(float(o["speed"]), rcb_tt.BASE_VMAX) - rcb_tt.BASE_JMAX * rcb_tt.PHYS_DT ** 2])
        r = np.array([float(o["tx"])])
        for _ in range(rcb_tt.SUBSTEPS):
            jl.step(r)

    def _opp_move(self, tx: float):
        sp = self.lv["chase_serve"] if self.leg.get("kind") == "our_serve" else self.lv["chase"]
        self.opp = {"tx": float(np.clip(tx, -OPP_X_MAX, OPP_X_MAX)), "plan_k": self.opp.get("plan_k"), "speed": sp}

    def _predict_opp_hit(self):
        """Where the ball will be when the opponent hits it (ball-only model, true state)."""
        p, v, w = ball_state(self.s.d)
        P, V, _, _ = self.bm.rollout(p, v, w, 1500)
        bounced = False
        for i in range(1, len(P)):
            if not bounced and P[i, 1] > 0 and P[i, 2] < 0.03 and V[i, 2] > 0:
                bounced = True
            if bounced and (V[i, 2] <= 0 or P[i, 1] >= HIT_Y):
                return P[i]
        return P[-1]

    def _opp_return(self, p_hit, mode="normal"):
        """Opponent's shot from p_hit: (v, w, target, pace). normal: a seeded target within the level's width, its pace
        and spin (top- or backspin, plus a sidespin share); attack: its widest and fastest ball with full spin; weak:
        a slow, central, spinless ball (a chance for us). Only balls whose apex after our bounce is in the reliably
        returnable box are played; otherwise the target moves towards the centre and the pace down."""
        lv = self.lv
        v_in = self.s.d.qvel[0:3].copy()                      # the ball as the opponent meets it
        rng = np.random.default_rng([lv["seed"], len(self.points), len(self.legs)])
        u = rng.uniform(-1, 1, 5)
        if mode == "weak":
            tx, ty, pace = 0.08 * u[0], -0.6 + 0.1 * u[1], 3.7
            w = np.zeros(3)
        else:
            width = lv["width"] * (1.0 if mode == "attack" else abs(u[0]) ** 0.5)
            tx = float(np.sign(u[0]) or 1.0) * width
            ty = -0.6 + 0.15 * u[1]
            pace = lv["pace"] + (0.5 if mode == "attack" else 0.0)
            mag = min(OPP_SPIN_MAX, lv["spin"] * (1.0 if mode == "attack" else 0.5 + 0.5 * abs(u[2])))
            sgn = 1.0 if u[3] > -0.4 else -1.0                   # 70 % topspin, 30 % backspin
            w = np.array([sgn * mag, 0.0, lv["side"] * mag * u[4]])
        if "explore" in lv:                                  # calibration only: random pace / spin
            pace = float(rng.uniform(3.6, lv.get("pace_max", 5.0)))
            sm = lv.get("spin_max", 15.0)
            w = np.array([float(rng.uniform(-sm, sm)), 0.0, float(rng.uniform(-sm, sm)) * lv.get("side", 0.0)])
            tx = float(u[0]) * lv["width"]
        # Search depth as well as width before weakening a nominal shot. Every return is checked.
        candidates = 0
        nominal_w = w.copy()
        for relax in (1.0, .75, .5, 0.0):
            for dp in (0.0, -.4, .4):
                for depth in (ty, -.45, -.75, -.3, -.9):
                    candidates += 1
                    target = np.array([tx*relax, depth])
                    speed = max(3.6, pace+dp)
                    spin = nominal_w*relax
                    v = self._solve_shot(p_hit, target, speed, spin)
                    if v is not None and self._within_limits(v_in, v) and self._reachable(p_hit, v, spin):
                        self._return_search = {"candidates": candidates, "relax": relax,
                                               "nominal_pace": pace, "nominal_target_x": tx}
                        return v, spin, target.tolist(), speed
        raise RuntimeError("opponent solver could not construct a legal reachable return")

    @staticmethod
    def _within_limits(v_in, v_out) -> bool:
        """The opponent's shot is one the real-limited arm can make: the ball's speed off the paddle <= OPP_SPEED_MAX
        and the blade speed the contact law needs (normal along v_out - v_in: v_p.n = (v_out.n + E v_in.n) / (1 + E))
        <= OPP_BLADE_MAX."""
        if float(np.linalg.norm(v_out)) > OPP_SPEED_MAX:
            return False
        dv = np.asarray(v_out, float) - np.asarray(v_in, float)
        n = dv / max(float(np.linalg.norm(dv)), 1e-9)
        return abs((float(v_out @ n) + E_BLADE * float(v_in @ n)) / (1 + E_BLADE)) <= OPP_BLADE_MAX

    def _solve_shot(self, p0, target, pace, w):
        """Newton on (vx, vz) with vy = -pace so that the ball-only flight lands at `target` and clears the net."""
        flight = max(.15, abs(target[1]-p0[1])/pace*1.12)
        v = np.array([(target[0]-p0[0])/flight, -pace,
                      (rally.BALL_R-p0[2]+.5*9.81*flight**2)/flight])
        for _ in range(12):
            L, ok = self._landing(p0, v, w)
            if L is None:
                v[2] += 0.4
                continue
            err = L - target
            if np.linalg.norm(err) < 0.01:
                return v if ok else None
            J = np.zeros((2, 2))
            for c, idx in enumerate((0, 2)):
                dv = np.zeros(3); dv[idx] = 2e-2
                L2, _ = self._landing(p0, v + dv, w)
                if L2 is None:
                    return None
                J[:, c] = (L2 - L) / 2e-2
            try:
                dx = np.linalg.lstsq(J, err, rcond=None)[0]
            except np.linalg.LinAlgError:
                return None
            dx = np.clip(dx, -0.8, 0.8)
            v[0] -= dx[0]; v[2] -= dx[1]
        return None

    def _landing(self, p0, v, w):
        """First table contact on our half (interpolated to the ball-radius height) and whether the flight clears
        the net by >= 3 cm; None if the first contact is anything else."""
        P, _, _, first = self.bm.rollout(p0, v, w, 1500, stop_at_contact=True)
        if not first or first[1] != "table_own" or len(P) < 3:
            return None, False
        a, b = P[-3], P[-2]
        z0 = rally.BALL_R
        f = 0.0 if abs(a[2] - b[2]) < 1e-9 else float(np.clip((a[2] - z0) / (a[2] - b[2]), 0.0, 2.0))
        L = a[:2] + f * (b[:2] - a[:2])
        i0 = int(np.argmin(np.abs(P[:, 1])))
        clear = P[i0, 2] > 0.1525 + 0.02 + 0.03
        return L, bool(clear)

    def _reachable(self, p0, v, w) -> bool:
        P, V, _, _ = self.bm.rollout(p0, v, w, 1500)
        bounced = False
        for i in range(1, len(P)):
            if not bounced:
                if P[i, 2] < 0.03 and V[i, 2] > 0 and P[i, 1] < 0:
                    bounced = True
                continue
            if V[i, 2] <= 0:
                a = P[i]
                return bool(.17 <= a[2] <= .65 and -1.55 <= a[1] <= -.90 and abs(a[0]) <= .45
                            and np.linalg.norm(a-SHOULDER) <= .82)
        return False

    # ------------------------------------------------------------------ stepping (shared by live and replay)
    def step(self, q):
        self.s.step(q)
        self._opp_step()
        leg = self.leg
        if leg["kind"] == "serve" and self.k <= leg["launch"]:
            self._park()
        elif leg["kind"] == "our_serve" and leg["state"] in ("waiting", "rest"):
            self._our_serve_wait()
        elif leg["kind"] == "our_serve" and leg["state"] in ("toss", "struck"):
            self._our_serve_judge()
        else:
            self._referee()
        if self.k % CAM_EVERY == 0:
            d = self.s.d
            self.hist.append({"k": self.k, "t": self.t_since_launch(), "qpos": d.qpos.copy(), "opp_x": self.opp_x(),
                              "leg_id": len(self.legs)-1, "wall_mono": time.monotonic()})
            if self.in_play() and leg["state"] == "incoming":
                p = d.qpos[0:3]
                self.frames.append({"t": self.t_since_launch(), "pos": [float(x) for x in p]})

    # ------------------------------------------------------------------ our service (serve.py, ITTF 2.6)
    def toss_check(self, pos, height) -> tuple[str, int] | None:
        """Why our toss is refused now ((reason, HTTP code)), else None."""
        leg = self.leg
        if self.done or leg["kind"] != "our_serve" or leg["state"] != "waiting":
            return "no toss now: it is not your service, or the ball is already in play", 409
        if self.k < leg["open"]:
            return f"no toss yet: your opponent is getting ready (the serve opens in {(leg['open'] - self.k) * CONTROL_DT:.2f} s)", 409
        why = SV.toss_problem(pos, height, self.s._target[:2])
        return None if why is None else (why, 400)

    def toss(self, pos, height) -> dict:
        """`toss` at the start of control step self.k: the ball is put at rest at pos on the toss device, projected
        straight up serve.TOSS_REST_STEPS later to rise `height` metres."""
        bad = self.toss_check(pos, height)
        if bad:
            return {"rejected": bad[0]}
        leg = self.leg
        leg["toss"] = {"pos": [float(x) for x in pos], "height": float(height), "vz": SV.vz_for_height(height),
                       "k": int(self.k)}
        leg["state"], leg["launch"] = "rest", self.k
        self.judge = SV.ServeJudge(self.k)
        self._new_leg_bookkeeping()
        self.our_serves.append({"point": leg["point"], "toss": dict(leg["toss"])})
        self._park()
        return {"toss": dict(leg["toss"]), "projected_at_step": int(self.k + SV.TOSS_REST_STEPS)}

    def _our_serve_wait(self):
        """Before our toss is projected: the ball waits (hidden, or at rest on the device); the serve clock."""
        leg = self.leg
        if self.done:
            return
        if leg["state"] == "waiting":
            self._park()
            if self.k >= leg["deadline"]:
                self.delay_faults[0] += 1
                if self.delay_faults[0] >= SV.DELAY_LIMIT:
                    self.disqualified = 0
                self._end_point(winner=1, how=f"serve_fault:undue_delay: you did not toss within "
                                              f"{SV.SERVE_CLOCK_S:.0f} s (fault {self.delay_faults[0]} of {SV.DELAY_LIMIT})")
            return
        self._feed_judge()                                    # a strike or a touch while it rests is a fault
        if self.judge.verdict is None and self.k - leg["toss"]["k"] >= SV.TOSS_REST_STEPS:
            d = self.s.d
            d.qpos[0:3] = leg["toss"]["pos"]; d.qvel[0:3] = [0.0, 0.0, leg["toss"]["vz"]]; d.qvel[3:6] = 0.0
            leg["state"] = "toss"
            self.judge.projected = True
            judge, dd, ev = self.judge, self.s.d, self.s._events

            def hook():                                       # Law 2.6.4 at every physics step until the strike
                if not any(e["kind"] == "paddle" for e in ev):
                    judge.position(dd.qpos[0:3])
            self.s.substep_hook = hook
        elif self.judge.verdict is None:
            self._park()
        self._serve_verdict()

    def _feed_judge(self):
        """Our service's contacts (the server's frame is ours) since the last call, into the judge."""
        ev = self.s._events
        for e in ev[self._judged:]:
            k = e["kind"]
            top = _top(e)
            kind = {"table_own": "table_server" if top else "table_side",
                    "table_opp": "table_receiver" if top else "table_side", "paddle": "paddle_server",
                    "robot": "robot_server"}.get(k, k)
            self.judge.contact(kind, e["pos"], e["vel_pre"], int(round(e["t"] / CONTROL_DT)))
        self._judged = len(ev)

    def _our_serve_judge(self):
        leg = self.leg
        if self.done:
            return
        self._feed_judge()
        if self.judge.struck and leg["state"] == "toss":
            leg["state"] = "struck"
            self.s.substep_hook = None
            ip = next(e for e in self.s._events if e["kind"] == "paddle")
            leg["paddle_t"] = ip["t"]
            self.opp["plan_k"] = int(round(ip["t"] / CONTROL_DT)) + int(round(self.lv["reaction_s"] / CONTROL_DT))
        if (self.opp.get("plan_k") is not None and self.k >= self.opp["plan_k"]):
            leg["opp_x_react"] = round(self.opp_x(), 3)
            self._opp_move(self._predict_opp_hit()[0])
            self.opp["plan_k"] = None
        if self.judge.verdict is None and self.judge.struck and self.k - self.judge.strike["k"] >= SV.SERVE_STEPS:
            self.judge._end("fault", "the service was not decided within 3 s of the strike", "undecided")
        if self.judge.verdict is None and self.s._robot_net:
            self.judge._end("fault", "your robot touched the net assembly during the service (Law 2.10.1.10)",
                            "robot_net")
        self._serve_verdict()

    def _serve_verdict(self):
        j, leg = self.judge, self.leg
        if j is None or j.verdict is None or self.done:
            return
        self.s.substep_hook = None
        vo = self.s._v_out
        leg["v_out"] = None if vo is None else [float(x) for x in vo]
        rec = self.our_serves[-1]
        rec.update(verdict=j.verdict, why=j.why, code=j.code, strike=j.strike, net=j.net,
                   speed_out=None if vo is None else round(float(np.linalg.norm(vo)), 2),
                   events=[e["kind"] for e in self.s._events], **self._shot_facts())
        if j.verdict == "good":
            leg["state"] = "to_opp"                           # the opponent receives it like a return
        elif j.verdict == "let":
            if self._service_let(server=0, how="let: " + j.why):
                rec.update(verdict="fault", code="repeated_let", why=SV.repeated_let_why(self.serve_lets))
        else:
            self._end_point(winner=1, how=f"serve_fault:{j.code or 'other'}: {j.why}")

    def _leg_verdict(self):
        return rcb_tt.judge(self.s._events, OPP_HALF, robot_env_contact=self.s._robot_net)

    def _referee(self):
        if self.done:
            return
        leg, d = self.leg, self.s.d
        kinds = [e["kind"] for e in self.s._events]
        p = d.qpos[0:3]
        dead = any(x in ("floor", "robot", "other") for x in kinds) or p[2] < -0.3 or abs(p[1]) > 2.8 or abs(p[0]) > 2.5
        if (leg["state"] in ("incoming", "to_opp") and self.opp.get("plan_k") is not None
                and self.k >= self.opp["plan_k"]):
            leg["opp_x_react"] = round(self.opp_x(), 3)       # the opponent reacts `reaction_s` after our hit
            self._opp_move(self._predict_opp_hit()[0])
            self.opp["plan_k"] = None
        if leg["state"] == "incoming":
            if leg["kind"] == "serve" and "net" in (kinds[:kinds.index("paddle")] if "paddle" in kinds else kinds):
                self._service_let(server=1, how="let: the serve touched the net")
                return
            if leg["kind"] == "return" and "robot" in kinds and "paddle" not in kinds and "table_own" not in kinds:
                e = next(x for x in self.s._events if x["kind"] == "robot")
                if not towards_own_half(e["pos"], e["vel_pre"]):        # as in the duel (ITTF 2.10.1.4 vs 2.10.1.6)
                    self._end_point(winner=0, how="the opponent's shot went out (it passed your half and hit your robot)")
                    return
            post = kinds[kinds.index("paddle") + 1:] if "paddle" in kinds else []
            post = [x for x in post if x not in ("paddle", "net")]      # a return may touch the net (ITTF 2.7.1)
            if "paddle" in kinds and self.opp.get("plan_k") is None and "paddle_t" not in leg:
                ip = next(e for e in self.s._events if e["kind"] == "paddle")
                leg["paddle_t"] = ip["t"]
                self.opp["plan_k"] = int(round(ip["t"] / CONTROL_DT)) + int(round(self.lv["reaction_s"] / CONTROL_DT))
            if post or dead or self.k - leg["launch"] >= LEG_STEPS:
                v = self._leg_verdict()
                ok = bool(v["success"]) and not dead
                self._close_our_leg(v, ok)
                if ok and self.point_server == 1:           # we receive: our good returns count (expedite)
                    self.point_returns += 1
                if ok and self.point_returns >= EXPEDITE_RETURNS:
                    self._end_point(winner=0, how=f"you made {EXPEDITE_RETURNS} good returns as the receiver "
                                                  "(expedite rule)")
                elif ok:
                    leg["state"] = "to_opp"
                else:
                    self._end_point(winner=1, how=self.results[-1]["summary"])
            return
        if leg["state"] == "to_opp":
            v = d.qvel[0:3]
            bounced = kinds.count("table_opp") >= 1
            if bounced and p[1] > 0 and (v[2] <= 0 or p[1] >= HIT_Y) and p[2] > 0.05:
                self._opp_hit()
            elif dead or self.k - leg["launch"] >= 2 * LEG_STEPS:
                self._end_point(winner=0, how=leg.get("opp_miss", "the opponent could not reach the ball"))
            return
        if leg["state"] == "opp_missed":
            if dead or self.k - leg["opp_k"] >= 60:
                self._end_point(winner=0, how=leg["opp_miss"])

    def _opp_hit(self):
        d = self.s.d
        p, v, w = ball_state(d)
        ox = self.opp_x()
        vo = self.leg.get("v_out")
        speed = float(np.linalg.norm(vo)) if vo is not None else float(np.linalg.norm(v))   # our shot's pace off the paddle
        gap = abs(float(p[0]) - ox)
        rec = {"k": self.k, "ball_x": round(float(p[0]), 3), "opp_x": round(ox, 3), "gap": round(gap, 3),
               "speed": round(speed, 3)}
        self.leg["opp"] = rec
        rec["t_flight"] = round((self.k - int(round(self.leg.get("paddle_t", 0) / CONTROL_DT))) * CONTROL_DT, 3) if self.leg.get("paddle_t") else None
        rec["opp_x_at_react"] = self.leg.get("opp_x_react")
        pressure = max(gap / self.lv["reach"], (speed - SPEED_FREE) / (self.lv["max_speed"] - SPEED_FREE))
        short = 0.0
        if self.leg.get("kind") == "our_serve":
            short = max(0.0, (SHORT_Y0 - float(p[1])) / (SHORT_Y0 - self.lv["short_y1"]))
            rec["short"] = round(short, 3)
        pressure = max(pressure, short)
        rec["pressure"] = round(pressure, 3)
        if pressure > 1.0:
            why = (f"too short: the opponent met your service only {float(p[1]):.2f} m from the net (its limit "
                   f"{self.lv['short_y1']:.2f} m)" if short >= pressure else
                   f"too wide: the ball passed {gap:.2f} m from the opponent's paddle (its reach {self.lv['reach']:.2f} m)"
                   if gap > self.lv["reach"] else
                   f"too fast: {speed:.1f} m/s off your paddle (it handles up to {self.lv['max_speed']:.1f} m/s)")
            self.leg["state"] = "opp_missed"; self.leg["opp_miss"] = why; self.leg["opp_k"] = self.k
            rec["missed"] = why
            return
        mode = "weak" if pressure > PRESSURE_WEAK else ("attack" if pressure < PRESSURE_PASSIVE else "normal")
        rec["mode"] = mode
        try:
            vo, wo, target, pace = self._opp_return(p, mode)
        except RuntimeError:          # no legal return from where it met the ball: the opponent misses it
            why = "the opponent could not play a legal return from where it met the ball"
            self.leg["state"] = "opp_missed"; self.leg["opp_miss"] = why; self.leg["opp_k"] = self.k
            rec["missed"] = why
            return
        rec.update(target=[round(x, 3) for x in target], pace=pace, spin=[float(x) for x in wo],
                   search=dict(self._return_search))
        if self.point_server == 0:                            # the opponent receives: its good returns count (expedite)
            self.point_returns += 1
            if self.point_returns >= EXPEDITE_RETURNS:
                self.leg["state"] = "done"
                self._end_point(winner=1, how=f"the opponent made {EXPEDITE_RETURNS} good returns as the receiver "
                                              "(expedite rule)")
                return
        R = np.zeros(9); mj.mju_quat2Mat(R, d.qpos[3:7])
        d.qvel[0:3] = vo
        d.qvel[3:6] = R.reshape(3, 3).T @ wo
        self.leg["state"] = "done"
        self.opp = {"tx": 0.0, "plan_k": None, "speed": self.lv["recover"]}
        self.leg = {"kind": "return", "point": len(self.points), "launch": self.k, "state": "incoming",
                    "opp_hit_x": round(float(p[0]), 3)}
        self.legs.append(self.leg)
        self._new_leg_bookkeeping()

    def _shot_facts(self) -> dict:
        """Our shot's spin 5 ms after the contact and the blade speed the arm delivered at it (the real limits)."""
        w = self.s._w_out
        bl = next((e.get("blade_vel") for e in self.s._events if e["kind"] == "paddle"), None)
        return {"spin_out": None if w is None else round(float(np.linalg.norm(w)), 2),
                "blade_speed": None if bl is None else round(float(np.linalg.norm(bl)), 3)}

    def _close_our_leg(self, v, ok):
        kinds = [e["kind"] for e in self.s._events]
        vo = self.s._v_out
        self.leg["v_out"] = None if vo is None else [float(x) for x in vo]
        res = {"leg": self.n_our_legs, "point": len(self.points), "kind": self.leg["kind"], "returned": ok,
               "speed_out": None if vo is None else round(float(np.linalg.norm(vo)), 2),
               "hit": int(v["hit"]), "landing_x": round(float(v["landing_x"]), 3),
               "landing_y": round(float(v["landing_y"]), 3), "events": kinds, "step": self.k, **self._shot_facts()}
        if ok:
            res["summary"] = f"returned: landed on the opponent's half at x={v['landing_x']:.2f}, y={v['landing_y']:.2f}"
        elif not v["hit"]:
            res["summary"] = "missed: no paddle contact"
        elif v["robot_env_contact"]:
            res["summary"] = "fault: your robot touched the net assembly (Law 2.10.1.10)"
        elif v["n_paddle_contacts"] != 1:
            res["summary"] = "fault: more than one paddle contact"
        elif v["own_bounces_before_hit"] != 1:
            res["summary"] = "fault: hit before the ball bounced on your half (volley)"
        elif v["landed"]:
            nxt = kinds[kinds.index("paddle") + 1:]
            nxt = [x for x in nxt if x not in ("paddle", "net")]
            where = {"table_own": "your own half", "floor": "the floor (out)"}.get(nxt[0], nxt[0]) if nxt else "?"
            via = " (after touching the net)" if v["net_touch"] else ""
            res["summary"] = f"fault: after your hit the ball hit {where}{via} (x={v['landing_x']:.2f}, y={v['landing_y']:.2f})"
        else:
            res["summary"] = "fault: after your hit the ball flew out without touching the table"
        if ok and v["net_touch"]:
            res["summary"] += " after touching the net"
        res["net_touch"] = int(v["net_touch"])
        self.results.append(res)
        self.n_our_legs += 1
        self.n_our_shots += int(bool(v["hit"]))
        res["shot"] = self.n_our_shots if v["hit"] else None

    def _service_let(self, server: int, how: str) -> bool:
        """A service let (ITTF 2.9.1.1) replays the service by the same server (2.13.3), at most SV.LET_LIMIT - 1 in a
        row (D12): the server's LET_LIMIT-th service let since the last point scored is a failed service, the
        receiver's point. True if it was turned into a fault."""
        self.serve_lets += 1
        if self.serve_lets < SV.LET_LIMIT:
            self._end_point(winner=None, how=how)
            return False
        who = "you" if server == 0 else "the opponent"
        self._end_point(winner=1 - server, how=f"serve_fault:repeated_let: {SV.repeated_let_why(self.serve_lets)} "
                                                f"({who} served)")
        return True

    def _end_point(self, winner: int | None, how: str):
        if winner is not None:                 # None: a let (no point scored, the next serve)
            self.score[winner] += 1
            self.serve_lets = 0
        self.s.substep_hook = None
        first = next(lg for lg in reversed(self.legs) if lg["kind"] in ("serve", "our_serve"))
        self.points.append({"point": len(self.points), "how": how,
                            "winner": "you" if winner == 0 else "opponent" if winner == 1 else "let",
                            "score": list(self.score), "step": self.k,
                            "server": "you" if self.point_server == 0 else "opponent",
                            "serve": first.get("serve") if first["kind"] == "serve" else None})
        self.review_hist = list(self.hist)
        self.review_hist.append({"k": self.k, "t": self.t_since_launch(), "qpos": self.s.d.qpos.copy(),
                                 "opp_x": self.opp_x(), "leg_id": len(self.legs)-1, "wall_mono": time.monotonic()})
        self.leg["state"] = "done"
        w = match_winner(self.score)
        if self.disqualified is not None:      # the DELAY_LIMIT-th undue-delay fault loses the match
            w = 1 - self.disqualified
        if w is None and len(self.points) >= MAX_POINTS_WITH_LETS:      # guard (never reached in practice)
            w = (0 if self.score[0] > self.score[1] else 1 if self.score[1] > self.score[0] else
                 next((0 if p["winner"] == "you" else 1) for p in reversed(self.points) if p["winner"] != "let"))
        if w is not None:
            self.winner = w
            self.done = True
            return
        self.hist.clear()
        self._start_point(hold_from=self.k)

    def replay(self, actions) -> None:
        for q in actions:
            self.step(q)

    # ------------------------------------------------------------------ the arm's command (arm_commands.Core overrides it)
    def _arm_target(self):
        if self.plan_j < len(self.plan):
            q = self.plan[self.plan_j]; self.plan_j += 1
            return q
        return self._rest_target(self.base_rest)

    # ------------------------------------------------------------------ views
    CAMS = (([0.0, 0.30, 0.05], 3.6, 72.0, -33.0),      # behind and above the robot, looking down the table
            ([0.0, 0.05, 0.25], 4.0, 0.0, -8.0))        # from the side
    # world poses of the two cameras as rendered (OpenGL: forward = view direction, image right = forward x up);
    # pinhole, vertical field of view 45 deg, tiles 480 x 360 px -> focal length 434.6 px, principal point at the centre
    # (wall-clock tasks: the positions are the centre of MuJoCo's two stereo eye cameras, which is what the mono render
    # uses; the lock-step tasks' spec gave scene.camera[0], the left eye, 3.4 cm (ipd / 2) to the left: ~4-7 px off)
    CAM_INFO = [{"name": "behind", "position": [-0.933, -2.5714, 2.0107], "forward": [0.2592, 0.7976, -0.5446],
                 "up": [0.1683, 0.518, 0.8387]},
                {"name": "side", "position": [-3.9611, 0.05, 0.8067], "forward": [0.9903, 0.0, -0.1392],
                 "up": [0.1392, 0.0, 0.9903]}]
    VIEW_BACK = (0, 2, 4, 6)                            # camera frames back from the latest: 0, 40, 80, 120 ms

    def _extra_geoms(self, scn, opp_x):
        def add(typ, size, pos, rgba, mat=np.eye(3)):
            if scn.ngeom >= scn.maxgeom:
                return
            mj.mjv_initGeom(scn.geoms[scn.ngeom], typ, np.asarray(size, float), np.asarray(pos, float),
                            np.asarray(mat, float).ravel(), np.asarray(rgba, np.float32))
            scn.ngeom += 1
        # opponent: red paddle + a grey body behind it
        add(mj.mjtGeom.mjGEOM_BOX, [0.075, 0.008, 0.075], [opp_x, OPP_Y, OPP_Z], [0.85, 0.1, 0.1, 1])
        add(mj.mjtGeom.mjGEOM_CAPSULE, [0.14, 0.30, 0], [opp_x, OPP_Y + 0.35, 0.30], [0.35, 0.35, 0.4, 1])
        # scale marks every 0.25 m along both side edges of the table and along both end lines
        for y in np.arange(-1.25, 1.26, 0.25):
            for x in (-0.7625, 0.7625):
                add(mj.mjtGeom.mjGEOM_BOX, [0.03, 0.006, 0.002], [x, y, 0.002], [1, 0.9, 0.1, 1])
        for x in np.arange(-0.75, 0.76, 0.25):
            for y in (-1.37, 1.37):
                add(mj.mjtGeom.mjGEOM_BOX, [0.006, 0.03, 0.002], [x, y, 0.002], [1, 0.9, 0.1, 1])

    # ------------------------------------------------------------------ real-time control (observe / act / wait)
    # The real-time protocol has no decision points: the world advances only through the agent's calls, each of which
    # first costs its latency (the service decides how many control steps; see server.py). Between calls the arm keeps
    # executing its current command: the rest of its planned stroke, then the speed-limited return to the ready pose.
    def rt_advance(self, n_steps: int):
        """Run up to n_steps control steps with the arm's current command. Stops early when a point ends (the world is
        then static until the review) or the match is over. Returns (steps run, points finished, our shot results)."""
        n0, r0, n = len(self.points), len(self.results), 0
        while n < n_steps and not self.done and len(self.points) == n0:
            self.step(self._arm_target()); n += 1
        if len(self.points) > n0:
            self.plan, self.plan_j = [], 0          # a new point: no stroke carries over; the arm returns to ready
        return n, self.points[n0:], self.results[r0:]

    # ------------------------------------------------------------------ paddle-level stroke (scheme B)
    PADDLE_SCATTER = dict(pos=0.01, ang_deg=1.5, speed=0.05)   # execution scatter of the paddle state at contact
    # (revision 14: 1 cm / 1.5 deg / 5 %, was 4 mm / 0.6 deg / 2 %: the nominal-model absolute error of a Panda is 3-10 mm
    # (Franzese 2026), high-speed tracking <= 5 mm (TiPToP); olympiad_review/screening/tt_realism_zh.md section 2.3)

    def _contact_state(self, pos, normal, v_p, base, n_avail, prev=None, M=None, serve=False):
        """The limits-aware planner's contact configuration: (q, qd, residual). A re-plan of the same ball (prev = the
        last contact's (q, qd)) corrects it with reachability weights (rally.reach_weights: the joints that can still
        change by the contact do), so the arm keeps its course; else the accurate branch nearest in time (_ik_best)
        and the velocity-limit-weighted Jacobian inverse."""
        s = self.s
        Jfn = lambda q: s.jacobian(np.r_[base, q])[:3, 2:]
        if prev is not None and os.environ.get("RCB_TT_REACH_WEIGHTS") == "1":     # tried: worse (README)
            wq, wv = rally.reach_weights(n_avail, M)
            q, res = self._ik(pos, normal, prev[0], base, w=np.maximum(wq, 1e-3))
            if res < 1e-4:
                Jp = Jfn(q)
                W = np.diag(ARM_VEL ** 2 * np.maximum(wv, 1e-3))
                qd = prev[1] + W @ Jp.T @ np.linalg.solve(Jp @ W @ Jp.T + 1e-9 * np.eye(3), v_p - Jp @ prev[1])
                return q, qd, res
        q, res = self._ik_best(pos, normal, None if prev is None else prev[0], base)
        Jp = Jfn(q)
        W = np.diag(ARM_VEL ** 2)
        if not serve and WRIST_POW > 0:              # a return: more of the paddle speed from the wrist, whose
            cap = rally.AL.jerk_caps(self._arm_inertia(q, base), rally.ARM_LIM)   # torque-rate jerk is far higher
            W = np.diag(ARM_VEL ** 2 * (cap / float(np.max(cap))) ** WRIST_POW)
        qd = W @ Jp.T @ np.linalg.solve(Jp @ W @ Jp.T + 1e-9 * np.eye(3), v_p)
        return q, qd, res

    def _ik_best(self, pos, normal, preferred=None, base=None):
        """Choose an accurate arm branch (7 joints, the base at `base`) the arm can reach with little joint travel.

        A precise pose on the far side of a joint's range can take longer than the
        entire incoming flight. Preserve cheap local solves for nearby commands;
        otherwise compare deterministic starts using joint-speed-normalized travel.
        """
        s = self.s
        base = s._target[:2].copy() if base is None else np.asarray(base, float)
        first = preferred if preferred is not None else s.d.qpos[s._qadr[2:]]
        best = self._ik(pos, normal, first, base)
        arm_now = s._target[2:]

        def travel(candidate):
            dq = np.abs(candidate[0] - arm_now)
            if rally.PLANNER == "hermite":
                return float(np.max(dq / ARM_VEL))
            # rest to rest under the real velocity and acceleration limits (the limits-aware planner)
            A = rally.ARM_LIM.acc
            return float(np.max(np.maximum(dq / ARM_VEL + ARM_VEL / A, 2.0 * np.sqrt(dq / A))))

        def rank(candidate):
            return (0, travel(candidate)) if candidate[1] < 1e-4 else (1, candidate[1])
        if best[1] < 1e-4 and travel(best) <= .35:
            return best
        if (preferred is not None and rally.PLANNER != "hermite" and best[1] < 1e-4
                and float(np.max(np.abs(best[0] - np.asarray(preferred, float)))) < 0.3):
            return best                              # a re-plan: the branch of the previous contact pose (continuity)
        if preferred is not None and rally.PLANNER != "hermite":   # also from the current arm (a re-plan's seed is
            cand = self._ik(pos, normal, s.d.qpos[s._qadr[2:]], base)  # the previous contact pose)
            if rank(cand) < rank(best):
                best = cand
            if best[1] < 1e-4 and travel(best) <= .35:
                return best
        if not hasattr(self, "_ik_starts"):
            rng = np.random.default_rng(0)
            q0 = s.inst["q0"]
            self._ik_starts = [q0] + [np.clip(q0+rng.normal(0, .8, 7), s.JOINT_LOW[2:]+.05, s.JOINT_HIGH[2:]-.05)
                                       for _ in range(12)]
        for seed in self._ik_starts:
            if np.array_equal(seed, first):
                continue
            candidate = self._ik(pos, normal, seed, base)
            if rank(candidate) < rank(best):
                best = candidate
            if best[1] < 1e-4 and travel(best) <= .35:
                break
        return best

    def base_plan(self, p_c, base, n_avail):
        """The base's part of a stroke: the wanted base position at contact (`base`, else the default stance for the
        contact p_c), the goal it can reach and stop at 5 steps before the contact (else the farthest point towards
        it), and its go-to trajectory (n_avail + 25 rows, then it waits at the goal)."""
        s = self.s
        b_now, v_now, a_now = s._target[:2].copy(), self._target_vel()[:2], self._target_acc()[:2]
        want = rcb_tt.stance(p_c, b_now) if base is None else np.clip(np.asarray(base, float), BASE_LO, BASE_HI)
        goal, short = rcb_tt.base_reach(b_now, v_now, want, n_avail, a=a_now)
        rows, _ = rcb_tt.base_plan(b_now, v_now, goal, n_avail + 25, a=a_now)
        return goal, short, rows

    def plan_paddle(self, t_hit, p_c, nrm, v_p, base=None):
        """Scheme B: the player gives the paddle state at contact (time t_hit s after the ball was played, blade-centre
        position p_c, blade face normal nrm, blade velocity v_p) and optionally the base position at contact. The
        controller only makes the robot deliver it: the base to `base` (default: the stance rule, rcb_tt.stance) with
        the bounded go-to generator, arriving at rest 5 steps before the contact (or as far as it gets), the arm's IK
        at that base position, a speed-weighted Jacobian inverse, a joint-speed-limited cubic swing and robot-only
        rehearsals of the whole 9-joint motion (no ball) that correct the PD controller's lag. It uses no ball state
        and does not aim."""
        s = self.s
        p_c = np.asarray(p_c, float); nrm = np.asarray(nrm, float); nrm = nrm / np.linalg.norm(nrm)
        v_p = np.asarray(v_p, float)
        info = {"t_hit": t_hit, "paddle_pos": p_c.round(4).tolist(), "paddle_normal": nrm.round(4).tolist(),
                "paddle_vel": v_p.round(3).tolist()}
        k_hit = self._cur()["launch"] + int(round(t_hit / CONTROL_DT))
        n_avail = k_hit - self.k
        info["n_swing_steps_available"] = int(n_avail)
        if n_avail < 1:
            info["stroke"] = "too late: the contact time has already passed"
            return [], info
        rng = np.random.default_rng([self.lv["seed"], 11, self.n_our_legs])
        sc = self.PADDLE_SCATTER
        p_c = p_c + rng.normal(0.0, sc["pos"], 3)
        axis = np.cross(nrm, rng.normal(0.0, 1.0, 3)); axis /= np.linalg.norm(axis)
        ang = np.radians(rng.normal(0.0, sc["ang_deg"]))
        nrm = nrm * np.cos(ang) + np.cross(axis, nrm) * np.sin(ang); nrm /= np.linalg.norm(nrm)
        v_p = v_p * (1.0 + rng.normal(0.0, sc["speed"]))
        goal, short, base_rows = self.base_plan(p_c, base, int(n_avail))
        info["base_goal"] = [round(float(x), 4) for x in goal]
        info["base"] = "ok" if short < 1e-6 else f"the base cannot reach the wanted position in time: {short:.2f} m short"
        Jp = None
        if rally.PLANNER != "hermite":
            prev = getattr(self, "_planned_state", None) if self._ik_seed is not None else None
            q_h, qd_h, res = self._contact_state(p_c, nrm, v_p, goal, n_avail, prev,
                                                 self._arm_inertia(s._target[2:], goal),
                                                 serve=(getattr(self, "leg", None) or {}).get("kind") == "our_serve")
            Winv = np.diag(ARM_VEL ** 2)
            Jp = s.jacobian(np.r_[goal, q_h])[:3, 2:]
        else:
            q_h, res = self._ik_best(p_c, nrm, self._ik_seed, goal)
            Jp = s.jacobian(np.r_[goal, q_h])[:3, 2:]
            Winv = np.diag(ARM_VEL ** 2)
            qd_h = Winv @ Jp.T @ np.linalg.solve(Jp @ Winv @ Jp.T, v_p)
        info["ik_residual"] = round(float(res), 5)
        ratio = float(np.max(np.abs(qd_h) / ARM_VEL))
        scale = rally.contact_prescale(ratio)         # 1 with the limits-aware planner (revision 14/11)
        qd_h = qd_h / scale
        info["speed_scale"] = round(scale, 3)
        q_s = s._target[2:].copy(); v_s = self._target_vel()[2:]
        n_sw = int(n_avail)
        for n in (range(25, int(n_avail) + 1) if np.max(np.abs(v_s)) < 1e-6 and rally.PLANNER == "hermite" else []):
            sw = hermite(q_s, np.zeros(7), q_h, qd_h, n * CONTROL_DT, n)
            if np.max(np.abs(np.diff(np.vstack([q_s, sw]), axis=0)) / (ARM_VEL * CONTROL_DT)) <= 0.97:
                n_sw = n
                break
        n_sw = int(min(n_sw, n_avail))
        info["n_swing_steps"] = n_sw
        q_goal, qd_goal = q_h.copy(), qd_h.copy()
        self._planned_hit = q_h.copy()
        via = None                                   # table avoidance: a pre-contact pose when the direct path dips
        info["approach"] = "direct"
        if rally.touches_table(s, self._swing_targets(q_goal, qd_goal, n_avail, n_sw, base_rows)[:n_avail]):
            info["approach"] = "direct (touches the table)"
            for dz in rally.VIA_DZ:
                q_pre, r_pre = self._ik(rally.via_pose(p_c, v_p, nrm, dz), nrm, q_h, goal)
                if r_pre > 1e-3:
                    continue
                cand = self._swing_targets(q_goal, qd_goal, n_avail, n_sw, base_rows, q_pre)
                if not rally.touches_table(s, cand[:n_avail]):
                    via, info["approach"] = q_pre, f"from above (+{dz:.2f} m) to clear the table"
                    break
        best = None
        for it in range(5):
            tg = self._swing_targets(q_goal, qd_goal, n_avail, n_sw, base_rows, via)
            p, n_act, v_act = self._simulate_arm(tg, n_avail)
            angle = float(np.arccos(np.clip(n_act @ nrm, -1, 1)))
            loss = np.linalg.norm(p-p_c) + .1*angle + .01*np.linalg.norm(v_act-v_p/scale)
            loss += 1.0 if self._rehearsal_table else 0.0      # prefer a swing that clears the table
            if best is None or loss < best[0]:
                best = (loss, tg, p.copy(), n_act.copy(), v_act.copy(), self._rehearsal_table)
            # Further rehearsal is unnecessary once delivery is already well
            # below the declared scatter; avoid holding up the wallclock loop.
            if (it == 4 or (np.linalg.norm(p-p_c) < .0005 and angle < np.radians(.1)
                            and np.linalg.norm(v_act-v_p/scale) < .005 and not self._rehearsal_table)):
                break
            J = s.jacobian(np.r_[goal, q_goal])[:, 2:]
            e = np.r_[p_c - p, np.cross(n_act, nrm)]
            q_goal = np.clip(q_goal + J.T @ np.linalg.solve(J @ J.T + 1e-4 * np.eye(6), e),
                             s.JOINT_LOW[2:] + 1e-4, s.JOINT_HIGH[2:] - 1e-4)
            qd_goal = qd_goal + Winv @ Jp.T @ np.linalg.solve(Jp @ Winv @ Jp.T, (v_p / scale) - v_act) * 0.7
            qd_goal = qd_goal / max(1.0, float(np.max(np.abs(qd_goal) / ARM_VEL)))
        _, tg, p, n_act, v_act, table = best
        self._planned_state = (q_h.copy(), qd_h.copy())
        si = getattr(self, "_stroke_info", None) if rally.PLANNER != "hermite" else None
        if si:                                       # the limits-aware planner: its stroke and what it delivers
            info.update(si)
            info["n_swing_steps"] = si["n_stroke"] or int(n_avail)
            if si["plan_scale"] < 0.97:              # the limits cost paddle speed: tell the player (act reply)
                scale = scale / max(0.05, si["plan_scale"])
                info["speed_scale"] = round(scale, 3)
            n_sw = info["n_swing_steps"]
        info["table_contact_in_rehearsal"] = bool(table)
        info["normal_error_deg"] = round(float(np.degrees(np.arccos(np.clip(n_act @ nrm, -1, 1)))), 3)
        info["blade_error_m"] = round(float(np.linalg.norm(p - p_c)), 4)
        info["paddle_vel_delivered"] = [round(float(x), 3) for x in v_act]
        notes = []
        if info["blade_error_m"] > .03 or info["normal_error_deg"] > 5:
            notes.append("command not achievable accurately: see blade_error_m / normal_error_deg")
        if res > 1e-3: notes.append(f"pose not reachable exactly (IK residual {res:.3f})")
        if scale > 1.0: notes.append(f"paddle speed limited by the joint limits (x{1 / scale:.2f})")
        if n_sw < 20: notes.append("short swing (little time left)")
        if short >= 1e-6: notes.append(info["base"])
        if table: notes.append("the rehearsed swing still touches the table (allowed, but the table stops the paddle)")
        info["stroke"] = "; ".join(notes) or "ok"
        return tg, info
