"""Core of the table-tennis match service (interactive mode): one game against a scripted opponent, with the duel's
rules: first to 5 points, from 4:4 a lead of 2, at 6:6 the next point wins (7 at most); the expedite rule (the
receiver's 13th good return in a rally wins it the point, ITTF 2.15.4) bounds every rally. The opponent serves every
point, so the agent is always the receiver (the duel's receiver rotation cannot apply: the robot cannot serve).

The robot (Franka + paddle, y < 0) plays a scripted opponent on the far side (y > 0). The opponent is part of the
world, like the physics: a deterministic function of the simulator state, evaluated inside every control step, so a
recorded sequence of the robot's joint targets replays the whole match bit-exactly (no schedule is needed).

Point flow (all inside step()):
  ready   READY_STEPS control steps; the next serve is held at its launch state, out of play.
  serve   the opponent serves: a recorded DeepMind serve (bounces on its half, crosses the net, bounces on ours).
  our leg the ball comes to us (a serve, or the opponent's return). The model decides the shot (live code:
          swing / adjust decision points); the robot hits or not. The leg is judged like the rally task: exactly one
          own bounce before the hit, one paddle contact, first contact after the hit other than the net = the
          opponent's half (a return may touch the net, ITTF 2.7.1). A failed leg = the opponent's point. A serve
          that touches the net is a let (ITTF 2.9.1.1: no point, the next serve; the recorded serves clear the net
          by >= 3.9 cm, so this does not happen with the pool).
  opp leg our return bounced on the opponent's half. The opponent (below) either returns it (a new "our leg"
          starts at its hit) or misses it (our point once the ball is dead).

The opponent (LEVELS): a kinematic paddle on its end line, at the centre when it serves. `reaction_s` after our hit it
moves towards the (perfectly predicted) ball at `chase`; after each of its shots it walks back towards the centre at
`recover`. When the ball reaches the top of its bounce on its half (or y = HIT_Y) it evaluates our shot's pressure
    pressure = max(|ball x - its paddle x| / reach, (our speed off the paddle - SPEED_FREE) / (max_speed - SPEED_FREE))
and, deterministically: pressure > 1 -> it misses (our point); > PRESSURE_WEAK -> a weak return (slow, central, no
spin); < PRESSURE_PASSIVE -> it attacks (its widest, fastest ball, full spin); else a normal return (a seeded target
within the level's width, its pace, top- or backspin plus a sidespin share). It sets the ball's velocity and spin (an
impulse; it never touches the ball physically) so that the ball lands on our half and its apex after our bounce is in
the box the reference stroke returns reliably; an unreachable target moves towards the centre and the pace down.
It never misses except by the rule above.
Our strokes scatter: the aim is perturbed by a seeded N(0, EXEC_SIGMA[power]) per shot before the stroke is planned.
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
from rally import BallModel, world_spin, hermite  # noqa: F401
from rcb_tt import CONTROL_DT, VEL_LIMIT

HERE = Path(__file__).resolve().parent
SCENE, INSTANCE = rally.SCENE, rally.INSTANCE
SERVES = {b["id"]: b for b in json.load(open(HERE / "serves_pool.json"))["serves"]}
REVISION = "wallclock-5"
WIN_POINTS = 5                 # the duel's format (duel.py): first to 5 ...
WIN_BY = 2                     # ... from 4:4 a lead of 2 ...
CAP_POINTS = 7                 # ... at 6:6 the next point wins
EXPEDITE_RETURNS = 13          # ITTF 2.15.4: the receiver's (our) 13th good return in a rally wins us the point
MAX_POINTS_WITH_LETS = 40      # guard: 13 scoring points at most, so this needs 27+ lets; then the player ahead wins,
                               # at a level score the player who won the last point
READY_STEPS = 80               # 0.8 s between points
LEG_STEPS = 250                # our leg is lost if nothing decisive happens 2.5 s after it started
CAM_EVERY = 2                  # 50 Hz camera frames
DECISION_AFTER_OPP_BOUNCE = 5  # serve legs: 5th frame (0.1 s) after the serve bounced on the opponent's half
DECISION_AFTER_OPP_HIT = 6     # return legs: 6th frame (0.12 s) after the opponent's hit
ADJUST_FRAMES = 3              # second decision point: 3rd frame (0.06 s) after the ball bounced on our half
HIT_Y = 1.55
OPP_Y, OPP_Z = 1.75, 0.22      # where the opponent's paddle is drawn
SHOULDER = np.array([0.0, -1.75, 0.33])
APEX_X_MAX = 0.30              # the opponent only plays balls whose apex after our bounce is in the box the reference
                               # stroke returns reliably (|x| <= 0.30, -1.38 <= y <= -1.10, 0.25 <= z <= 0.45)
rcb_tt.HORIZON = 10 ** 7
OPP_HALF = rally.OPP_HALF

LEVELS = {   # defence: reaction, chase / recovery speed, reach, too-fast threshold; attack: width, pace, spin, sidespin share
    1: dict(reaction_s=0.27, chase=0.47, recover=0.33, reach=0.27, max_speed=5.4,
            width=0.15, pace=4.0, spin=10.0, side=0.0, seed=101),
    2: dict(reaction_s=0.25, chase=0.50, recover=0.35, reach=0.29, max_speed=5.6,
            width=0.22, pace=4.4, spin=20.0, side=0.3, seed=202),
    3: dict(reaction_s=0.24, chase=0.53, recover=0.37, reach=0.31, max_speed=5.8,
            width=0.28, pace=4.9, spin=30.0, side=0.6, seed=303),
    4: dict(reaction_s=0.22, chase=0.55, recover=0.40, reach=0.33, max_speed=6.0,
            width=0.30, pace=5.4, spin=40.0, side=1.0, seed=404),
}
SPEED_FREE = 3.8              # our shot's speed off the paddle below this puts no pressure on the opponent
PRESSURE_WEAK = 0.75          # our shot's pressure above this (but <= 1) -> the opponent only manages a weak return
PRESSURE_PASSIVE = 0.35       # below this the opponent attacks: its widest, fastest ball with its most spin
EXEC_SIGMA = {"soft": 0.04, "normal": 0.06, "hard": 0.09}   # our stroke's landing scatter (m, per axis)
POWER = ("soft", "normal", "hard")


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


def ball_state(d):
    return d.qpos[0:3].copy(), d.qvel[0:3].copy(), world_spin(d)


class Match(rally.Rally):
    """The match. Live: run_to_decision() / shot() / adjust(). Replay: replay(actions)."""

    def __init__(self, level: int = 1, lv_override: dict | None = None):
        self.level = int(level)
        self.lv = dict(LEVELS.get(self.level, LEVELS[1]))
        if lv_override:
            self.lv.update(lv_override)
        if os.environ.get("MATCH_SEED"):           # other instances of the same level: serves + opponent + scatter
            self.lv["seed"] = int(os.environ["MATCH_SEED"])
        self.s = rcb_tt.Session(instance=str(INSTANCE), scene=str(SCENE))
        self.bm = BallModel()
        self._twin = None
        self._ik_seed = None
        self._planned_hit = None
        rng = np.random.default_rng(self.lv["seed"])
        ids = sorted(SERVES)
        self.serve_ids = [int(x) for x in rng.choice(ids, size=2 * CAP_POINTS - 1, replace=False)]
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
        sid = self.serve_ids[n % len(self.serve_ids)]
        self.point_returns = 0             # our good returns in this rally (expedite rule)
        self.leg = {"kind": "serve", "serve": sid, "point": n, "hold_from": hold_from,
                    "launch": hold_from + READY_STEPS, "state": "incoming"}
        self.legs.append(self.leg)
        b = SERVES[sid]
        self.opp = {"x0": 0.0, "k0": self.leg["launch"], "tx": 0.0, "plan_k": None,      # ready at the centre
                    "speed": self.lv["recover"]}
        self._new_leg_bookkeeping()
        self._park()

    def _new_leg_bookkeeping(self):
        self.frames = []
        s = self.s
        s._events.clear(); s._last_touch.clear(); s._robot_table = 0; s._v_out = None
        self.i = self.n_our_legs

    def _park(self):
        b = SERVES[self.leg["serve"]]
        d = self.s.d
        d.qpos[0:3] = b["pos"]; d.qpos[3:7] = [1, 0, 0, 0]; d.qvel[0:3] = b["vel"]; d.qvel[3:6] = b["spin"]

    def _cur(self) -> dict:
        return self.leg

    def in_play(self) -> bool:
        return self.k > self.leg["launch"]

    def t_since_launch(self) -> float:
        return round((self.k - self.leg["launch"]) * CONTROL_DT, 6)

    # ------------------------------------------------------------------ the opponent
    def opp_x(self, k=None) -> float:
        k = self.k if k is None else k
        o = self.opp
        dt = max(0.0, (k - o["k0"]) * CONTROL_DT)
        dx = o["tx"] - o["x0"]
        step = min(abs(dx), o.get("speed", self.lv["recover"]) * dt)
        return float(o["x0"] + np.sign(dx) * step)

    def _opp_move(self, tx: float):
        self.opp = {"x0": self.opp_x(), "k0": self.k, "tx": float(tx), "plan_k": self.opp.get("plan_k"),
                    "speed": self.lv["chase"]}

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
            mag = lv["spin"] * (1.0 if mode == "attack" else 0.5 + 0.5 * abs(u[2]))
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
                    if v is not None and self._reachable(p_hit, v, spin):
                        self._return_search = {"candidates": candidates, "relax": relax,
                                               "nominal_pace": pace, "nominal_target_x": tx}
                        return v, spin, target.tolist(), speed
        raise RuntimeError("opponent solver could not construct a legal reachable return")

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
        leg = self.leg
        if leg["kind"] == "serve" and self.k <= leg["launch"]:
            self._park()
        else:
            self._referee()
        if self.k % CAM_EVERY == 0:
            d = self.s.d
            self.hist.append({"k": self.k, "t": self.t_since_launch(), "qpos": d.qpos.copy(), "opp_x": self.opp_x(),
                              "leg_id": len(self.legs)-1, "wall_mono": time.monotonic()})
            if self.in_play() and leg["state"] == "incoming":
                p = d.qpos[0:3]
                self.frames.append({"t": self.t_since_launch(), "pos": [float(x) for x in p]})

    def _leg_verdict(self):
        return rcb_tt.judge(self.s._events, OPP_HALF, robot_env_contact=self.s._robot_table)

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
                self._end_point(winner=None, how="let: the serve touched the net")
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
                if ok:
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
        rec["pressure"] = round(pressure, 3)
        if pressure > 1.0:
            why = (f"too wide: the ball passed {gap:.2f} m from the opponent's paddle (its reach {self.lv['reach']:.2f} m)"
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
        R = np.zeros(9); mj.mju_quat2Mat(R, d.qpos[3:7])
        d.qvel[0:3] = vo
        d.qvel[3:6] = R.reshape(3, 3).T @ wo
        self.leg["state"] = "done"
        self.opp = {"x0": ox, "k0": self.k, "tx": 0.0, "plan_k": None, "speed": self.lv["recover"]}
        self.leg = {"kind": "return", "point": len(self.points), "launch": self.k, "state": "incoming",
                    "opp_hit_x": round(float(p[0]), 3)}
        self.legs.append(self.leg)
        self._new_leg_bookkeeping()

    def _close_our_leg(self, v, ok):
        kinds = [e["kind"] for e in self.s._events]
        vo = self.s._v_out
        self.leg["v_out"] = None if vo is None else [float(x) for x in vo]
        res = {"leg": self.n_our_legs, "point": len(self.points), "kind": self.leg["kind"], "returned": ok,
               "speed_out": None if vo is None else round(float(np.linalg.norm(vo)), 2),
               "hit": int(v["hit"]), "landing_x": round(float(v["landing_x"]), 3),
               "landing_y": round(float(v["landing_y"]), 3), "events": kinds, "step": self.k}
        if ok:
            res["summary"] = f"returned: landed on the opponent's half at x={v['landing_x']:.2f}, y={v['landing_y']:.2f}"
        elif not v["hit"]:
            res["summary"] = "missed: no paddle contact"
        elif v["robot_env_contact"]:
            res["summary"] = "fault: the arm or paddle touched the table/net/floor"
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

    def _end_point(self, winner: int | None, how: str):
        if winner is not None:                 # None: a let (no point scored, the next serve)
            self.score[winner] += 1
        self.points.append({"point": len(self.points), "how": how,
                            "winner": "you" if winner == 0 else "opponent" if winner == 1 else "let",
                            "score": list(self.score), "step": self.k, "serve": self.legs[-1].get("serve")
                            if self.legs[-1]["kind"] == "serve" else None})
        self.review_hist = list(self.hist)
        self.review_hist.append({"k": self.k, "t": self.t_since_launch(), "qpos": self.s.d.qpos.copy(),
                                 "opp_x": self.opp_x(), "leg_id": len(self.legs)-1, "wall_mono": time.monotonic()})
        self.leg["state"] = "done"
        w = match_winner(self.score)
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

    # ------------------------------------------------------------------ live control
    def _arm_target(self):
        if self.plan_j < len(self.plan):
            q = self.plan[self.plan_j]; self.plan_j += 1
            return q
        return self._ready_target()

    def decision_due(self) -> bool:
        leg = self.leg
        if self.done or leg["state"] != "incoming" or not self.in_play():
            return False
        ev = self.s._events
        if any(e["kind"] == "paddle" for e in ev):
            return False
        n_frames = len(self.frames)
        if self.phase == "swing":
            if leg["kind"] == "serve":
                b = [e for e in ev if e["kind"] == "table_opp"]
                if not b:
                    return False
                t_b = b[0]["t"] - leg["launch"] * CONTROL_DT
                return sum(1 for f in self.frames if f["t"] > t_b) >= DECISION_AFTER_OPP_BOUNCE
            return n_frames >= DECISION_AFTER_OPP_HIT
        b = [e for e in ev if e["kind"] == "table_own"]
        if not b:
            return False
        t_b = b[0]["t"] - leg["launch"] * CONTROL_DT
        return sum(1 for f in self.frames if f["t"] > t_b) >= ADJUST_FRAMES

    def run_to_decision(self) -> None:
        """Advance (arm: rest of the plan, then back to ready) until the next decision point or the match end."""
        self.phase = "swing"
        while not self.done:
            if self.decision_due():
                return
            self.step(self._arm_target())

    def shot(self, decision: dict, delay_steps: int) -> dict:
        leg_i = self.n_our_legs
        rec = {"leg": leg_i, "decision": decision, "delay_steps": int(delay_steps), "k_decision": self.k}
        for _ in range(delay_steps):
            if self.leg["state"] != "incoming" or self.done:
                break
            self.step(self._arm_target())
        rec["k_exec"] = self.k
        self._ik_seed = None
        if decision.get("type") == "swing" and self.leg["state"] == "incoming" and not self.done:
            if "normal" in decision:
                self.plan, info = self.plan_paddle(float(decision["t"]), decision["pos"], decision["normal"], decision["vel"])
            else:
                self.plan, info = self.plan_stroke(float(decision["t"]), np.asarray(decision["pos"], float),
                                                   np.asarray(decision.get("aim", rally.AIM_DEFAULT), float),
                                                   decision.get("power", "normal"))
            self.plan_j = 0
            rec.update(info)
        self._rec = rec
        if decision.get("type") == "swing":
            self.phase = "adjust"
            while not self.done and self.n_our_legs == leg_i:
                if self.decision_due():
                    return {"phase": "adjust", **{k: rec[k] for k in rec if k != "decision"}}
                self.step(self._arm_target())
        return self._after_leg(rec, leg_i)

    def adjust(self, decision: dict, delay_steps: int) -> dict:
        rec, leg_i = self._rec, self.n_our_legs
        rec["adjust"] = decision
        rec["adjust_delay_steps"] = int(delay_steps)
        for _ in range(delay_steps):
            if self.n_our_legs != leg_i or self.done:
                break
            self.step(self._arm_target())
        self._ik_seed = self._planned_hit
        if decision.get("type") == "adjust" and self.n_our_legs == leg_i and not self.done and "normal" in decision:
            plan, info = self.plan_paddle(float(decision["t"]), decision["pos"], decision["normal"], decision["vel"])
            rec["adjust_info"] = info
            if plan:
                self.plan, self.plan_j = plan, 0
        elif decision.get("type") == "adjust" and self.n_our_legs == leg_i and not self.done:
            plan, info = self.plan_stroke(float(decision["t"]), np.asarray(decision["pos"], float),
                                          np.asarray(decision.get("aim", rec.get("aim", rally.AIM_DEFAULT)), float),
                                          decision.get("power", rec.get("power", "normal")))
            rec["adjust_info"] = info
            if plan:
                self.plan, self.plan_j = plan, 0
        return self._after_leg(rec, leg_i)

    def _after_leg(self, rec, leg_i) -> dict:
        n0 = len(self.points)
        while not self.done and self.n_our_legs == leg_i:
            self.step(self._arm_target())
        self.shots.append(rec)
        res = dict(self.results[leg_i]) if leg_i < len(self.results) else {"summary": "match over"}
        self.run_to_decision()
        res["points_finished"] = self.points[n0:]
        return res

    # ------------------------------------------------------------------ stroke controller (rally's, + power)
    def plan_stroke(self, t_hit, p_hit, aim, power="normal"):
        """The rally's stroke controller, plus (a) a pace choice and (b) up to 3 full rehearsals of the stroke on a
        twin simulator from the current state (arm + the real ball): the aim point is corrected by the rehearsed
        landing error. The rehearsal uses the player's contact time/point as given: a wrong contact misses in the
        rehearsal too and is not corrected."""
        self._power = power if power in POWER else "normal"
        aim = np.asarray(aim, float)
        rng = np.random.default_rng([self.lv["seed"], 7, self.n_our_legs])       # one draw per shot (adjust reuses it)
        aim = aim + rng.normal(0.0, EXEC_SIGMA[self._power], 2)
        aim_eff = aim.copy()
        seed = self._ik_seed
        best = None
        for it in range(4):
            self._ik_seed = seed
            tg, info = rally.Rally.plan_stroke(self, t_hit, p_hit, aim_eff)
            if not tg:
                return tg, info
            L, speed = self._rehearse(tg)
            err = None if L is None else float(np.linalg.norm(np.asarray(L) - aim))
            if best is None or (err is not None and (best[2] is None or err < best[2])):
                best = (tg, info, err, L, speed)
            if L is None or err < 0.04:
                break
            aim_eff = aim_eff + (aim - np.asarray(L))
        tg, info, err, L, speed = best
        info["power"] = self._power
        info["rehearsal_landing"] = None if L is None else [round(float(x), 3) for x in L]
        info["rehearsal_speed"] = None if speed is None else round(float(speed), 2)
        return tg, info

    def _rehearse(self, targets):
        """Run `targets` on the twin from the full current state (arm and ball); (landing xy of the first contact
        after the paddle, outgoing speed) or (None, None) if the paddle never touches the ball."""
        tw = self._twin_session()
        m, d = tw.m, tw.d
        mj.mj_resetData(m, d)
        d.qpos[:] = self.s.d.qpos; d.qvel[:] = self.s.d.qvel; d.qacc_warmstart[:] = self.s.d.qacc_warmstart
        d.time = self.s.d.time
        mj.mj_forward(m, d)
        tw._target = self.s._target.copy(); tw._k = 0; tw._events = []; tw._last_touch = {}
        tw._robot_table = 0; tw._v_out = None; tw._actions = []
        for j in range(len(targets) + 150):
            tw.step(targets[j] if j < len(targets) else targets[-1])
            kinds = [e["kind"] for e in tw._events]
            if "paddle" in kinds:
                post = [e for e in tw._events[kinds.index("paddle") + 1:] if e["kind"] not in ("paddle", "net")]
                if post:
                    sp = None if tw._v_out is None else float(np.linalg.norm(tw._v_out))
                    return post[0]["pos"][:2], sp
            if d.qpos[2] < -0.3:
                break
        return None, None

    def _pick_stroke(self, cands):
        good = ([c for c in cands if c["ik"] < 1e-3 and c["ratio"] <= 1.0] or [c for c in cands if c["ik"] < 1e-3]
                or cands)
        power = getattr(self, "_power", "normal")
        if power == "normal":
            return min(good, key=lambda c: c["ratio"])
        sp = sorted(good, key=lambda c: float(np.linalg.norm(c["v_out"])))
        return sp[-1] if power == "hard" else sp[0]

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

    def render_views(self, width=480, height=360) -> bytes:
        """PNG: 2 rows (behind-the-robot camera, side camera) x 4 columns (oldest -> latest camera frame, 40 ms
        apart), each tile stamped with its time since the current ball was played."""
        import imageio.v2 as imageio
        from PIL import Image, ImageDraw
        if not hasattr(self, "_renderer"):
            self._renderer = mj.Renderer(self.s.m, height=height, width=width)
            self._rd = mj.MjData(self.s.m)
            self._cams = []
            for lookat, dist, az, el in self.CAMS:
                c = mj.MjvCamera(); c.lookat[:] = lookat; c.distance = dist; c.azimuth = az; c.elevation = el
                self._cams.append(c)
        r, rd = self._renderer, self._rd
        hist = list(self.hist)
        snaps = [hist[max(0, len(hist) - 1 - b)] for b in reversed(self.VIEW_BACK)]
        rows = []
        for c in self._cams:
            tiles = []
            for sn in snaps:
                rd.qpos[:] = sn["qpos"]; mj.mj_forward(self.s.m, rd)
                r.update_scene(rd, camera=c)
                self._extra_geoms(r.scene, sn["opp_x"])
                im = Image.fromarray(r.render())
                ImageDraw.Draw(im).text((6, 4), f"t={sn['t']:.2f}s", fill=(255, 255, 255))
                tiles.append(np.asarray(im))
            rows.append(np.concatenate(tiles, axis=1))
        buf = io.BytesIO()
        imageio.imwrite(buf, np.concatenate(rows, axis=0), format="png")
        return buf.getvalue()

    def view_times(self):
        hist = list(self.hist)
        return [hist[max(0, len(hist) - 1 - b)]["t"] for b in reversed(self.VIEW_BACK)]

    def decision_observation(self) -> dict:
        st = self.s.state()
        leg = self.leg
        heard = [{"event": {"table_opp": "bounce on the opponent's half", "table_own": "bounce on your half",
                            "net": "net"}.get(e["kind"], e["kind"]),
                  "t": round(e["t"] - leg["launch"] * CONTROL_DT, 3)} for e in self.s._events]
        return {"score": {"you": self.score[0], "opponent": self.score[1]}, "point": len(self.points) + 1,
                "ball": "serve" if leg["kind"] == "serve" else "opponent's return",
                "t_since_played": self.t_since_launch(),
                "heard": heard, "view_times": self.view_times(),
                "q": st["q"].round(4).tolist(), "paddle_pos": st["paddle_pos"].round(3).tolist(),
                "paddle_normal": st["paddle_normal"].round(3).tolist()}

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

    def rt_act(self, T: float, pos, nrm, vel) -> dict:
        """Replace the arm's command: the paddle state at contact T s from now (scheme B, no ball state). The swing is
        planned from the arm's current state, so a new `act` corrects the one under way."""
        t_hit = (self.k - self.leg["launch"]) * CONTROL_DT + float(T)
        self._ik_seed = self._planned_hit if self.plan_j < len(self.plan) else None
        plan, info = self.plan_paddle(t_hit, pos, nrm, vel)
        info["T_from_now"] = round(float(T), 4)
        if plan:
            self.plan, self.plan_j = plan, 0
        self.shots.append({"k": self.k, "leg": self.n_our_legs, **{k: info[k] for k in info if k != "paddle_vel_delivered"}})
        if plan:
            self.contact_k = self.k + info["n_swing_steps_available"]
            self._last_act = info
        return info

    def rt_clear(self) -> None:
        self.plan, self.plan_j = [], 0
        self._last_act = None
        self.contact_k = self.k

    # ------------------------------------------------------------------ paddle-level stroke (scheme B)
    PADDLE_SCATTER = dict(pos=0.004, ang_deg=0.6, speed=0.02)   # execution scatter of the paddle state at contact

    def _ik_best(self, pos, normal, preferred=None):
        """Choose an accurate branch the arm can reach with little joint travel.

        A precise pose on the far side of a joint's range can take longer than the
        entire incoming flight. Preserve cheap local solves for nearby commands;
        otherwise compare deterministic starts using joint-speed-normalized travel.
        """
        s = self.s
        first = preferred if preferred is not None else s.d.qpos[s._qadr]
        best = self._ik(pos, normal, first)
        def travel(candidate):
            return float(np.max(np.abs(candidate[0] - s._target) / VEL_LIMIT))
        def rank(candidate):
            return (0, travel(candidate)) if candidate[1] < 1e-4 else (1, candidate[1])
        if best[1] < 1e-4 and travel(best) <= .35:
            return best
        if not hasattr(self, "_ik_starts"):
            rng = np.random.default_rng(0)
            q0 = s.inst["q0"]
            self._ik_starts = [q0] + [np.clip(q0+rng.normal(0, .8, 7), s.JOINT_LOW+.05, s.JOINT_HIGH-.05)
                                       for _ in range(12)]
        for seed in self._ik_starts:
            if np.array_equal(seed, first):
                continue
            candidate = self._ik(pos, normal, seed)
            if rank(candidate) < rank(best):
                best = candidate
            if best[1] < 1e-4 and travel(best) <= .35:
                break
        return best

    def plan_paddle(self, t_hit, p_c, nrm, v_p):
        """Scheme B: the player gives the paddle state at contact (time t_hit s after the ball was played, blade-centre
        position p_c, blade face normal nrm, blade velocity v_p). The controller only makes the arm deliver it: IK,
        a speed-weighted Jacobian inverse, a joint-speed-limited cubic swing and robot-only rehearsals (no ball) that
        correct the PD controller's lag. It uses no ball state and does not aim."""
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
        q_h, res = self._ik_best(p_c, nrm, self._ik_seed)
        info["ik_residual"] = round(float(res), 5)
        Jp = s.jacobian(q_h)[:3]
        Winv = np.diag(VEL_LIMIT ** 2)
        qd_h = Winv @ Jp.T @ np.linalg.solve(Jp @ Winv @ Jp.T, v_p)
        ratio = float(np.max(np.abs(qd_h) / VEL_LIMIT))
        scale = max(1.0, ratio / 0.9)
        qd_h = qd_h / scale
        info["speed_scale"] = round(scale, 3)
        q_s = s._target.copy(); v_s = self._target_vel()
        n_sw = int(n_avail)
        for n in (range(25, int(n_avail) + 1) if np.max(np.abs(v_s)) < 1e-6 else []):
            sw = hermite(q_s, np.zeros(7), q_h, qd_h, n * CONTROL_DT, n)
            if np.max(np.abs(np.diff(np.vstack([q_s, sw]), axis=0)) / (VEL_LIMIT * CONTROL_DT)) <= 0.97:
                n_sw = n
                break
        n_sw = int(min(n_sw, n_avail))
        info["n_swing_steps"] = n_sw
        q_goal, qd_goal = q_h.copy(), qd_h.copy()
        self._planned_hit = q_h.copy()
        best = None
        for it in range(5):
            tg = self._swing_targets(q_goal, qd_goal, n_avail, n_sw)
            p, n_act, v_act = self._simulate_arm(tg, n_avail)
            angle = float(np.arccos(np.clip(n_act @ nrm, -1, 1)))
            loss = np.linalg.norm(p-p_c) + .1*angle + .01*np.linalg.norm(v_act-v_p/scale)
            if best is None or loss < best[0]:
                best = (loss, tg, p.copy(), n_act.copy(), v_act.copy())
            # Further rehearsal is unnecessary once delivery is already well
            # below the declared scatter; avoid holding up the wallclock loop.
            if (it == 4 or (np.linalg.norm(p-p_c) < .0005 and angle < np.radians(.1)
                            and np.linalg.norm(v_act-v_p/scale) < .005)):
                break
            J = s.jacobian(q_goal)
            e = np.r_[p_c - p, np.cross(n_act, nrm)]
            q_goal = np.clip(q_goal + J.T @ np.linalg.solve(J @ J.T + 1e-4 * np.eye(6), e),
                             s.JOINT_LOW + 1e-4, s.JOINT_HIGH - 1e-4)
            qd_goal = qd_goal + Winv @ Jp.T @ np.linalg.solve(Jp @ Winv @ Jp.T, (v_p / scale) - v_act) * 0.7
            qd_goal = qd_goal / max(1.0, float(np.max(np.abs(qd_goal) / VEL_LIMIT)))
        _, tg, p, n_act, v_act = best
        info["normal_error_deg"] = round(float(np.degrees(np.arccos(np.clip(n_act @ nrm, -1, 1)))), 3)
        info["blade_error_m"] = round(float(np.linalg.norm(p - p_c)), 4)
        info["paddle_vel_delivered"] = [round(float(x), 3) for x in v_act]
        notes = []
        if info["blade_error_m"] > .03 or info["normal_error_deg"] > 5:
            notes.append("command not achievable accurately: see blade_error_m / normal_error_deg")
        if res > 1e-3: notes.append(f"pose not reachable exactly (IK residual {res:.3f})")
        if scale > 1.0: notes.append(f"paddle speed limited by the joint speed limits (x{1 / scale:.2f})")
        if n_sw < 20: notes.append("short swing (little time left)")
        info["stroke"] = "; ".join(notes) or "ok"
        return tg, info


def render_video(actions, level, out, fps=25):
    """Replay video, the two decision cameras side by side, 4x slow motion (every 3rd frame while no ball is live)."""
    import imageio.v2 as imageio
    mt = Match(level)
    r = mj.Renderer(mt.s.m, height=360, width=560)
    cams = []
    for lookat, dist, az, el in Match.CAMS:
        c = mj.MjvCamera(); c.lookat[:] = lookat; c.distance = dist; c.azimuth = az; c.elevation = el
        cams.append(c)
    w = imageio.get_writer(out, fps=fps, macro_block_size=8)
    from PIL import Image, ImageDraw
    for k, q in enumerate(actions):
        mt.step(q)
        if (not mt.in_play() or mt.leg["state"] == "done") and k % 3:
            continue
        imgs = []
        for c in cams:
            r.update_scene(mt.s.d, camera=c)
            mt._extra_geoms(r.scene, mt.opp_x())
            imgs.append(r.render())
        im = Image.fromarray(np.concatenate(imgs, axis=1))
        ImageDraw.Draw(im).text((8, 6), f"you {mt.score[0]} : {mt.score[1]} opponent   (level {level})",
                                fill=(255, 255, 255))
        w.append_data(np.asarray(im))
    w.close(); r.close()
