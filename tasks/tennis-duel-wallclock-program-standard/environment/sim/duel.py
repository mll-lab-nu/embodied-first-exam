"""Tennis duel: two robots, two agents, first to 5 points.

Robot A (rails at y < 0, facing +y) and robot B (rails at y > 0, facing -y) are identical Franka arms on x-y rail
bases with tennis rackets, in one MuJoCo scene (scene/tn_duel.xml, made by scripts/olympiad/tennis/mk_duel_scene.py).
Each player sees and acts in its OWN frame, the frame of the single-player task (its half y < 0, its base's home
(0, -11.4)): for B every position, velocity and spin is mirrored, (x, y, z) -> (-x, -y, z) (a turn of 180 degrees about
z). B's joint values mean the same in B's frame as A's in the world, so both players get the same instruction, cameras
and stroke interface, and each act is planned by the single-player stroke controller (tn.PlanCtx) on a robot-only copy
in that player's frame.

Physics: tn.py's (the ball is a point mass with drag, Magnus lift, the court bounce and racket impact laws, integrated at
1 ms; MuJoCo moves the robots only, contacts disabled).

Serve: a neutral serving machine. Every point it serves from behind the base line of the side that does not receive
into the receiver's service box diagonally opposite, with the single-player serve generator (speed, spin, placement;
level-1 serves) seeded by DUEL_SEED and the points played. The receiver changes every point (FIRST_RECEIVER receives
points 1, 3, 5, ...); the box changes every two points (deuce, deuce, ad, ad, ...), so both players receive in both
boxes. The robot on the serving side cannot touch the serve.

Scoring: first to 5 points; from 4:4 a player must lead by 2, and at 6:6 the next point wins (at most 7). The match
also ends after MAX_HITS racket hits or MAX_POINTS points played (lets included): the player ahead wins; at equal points
the winner of the last point wins (no draws). The same format as the single-player game (tn.py).

Rules (a deterministic function of the ball events, evaluated inside every control step, so the recorded joint targets
of both robots replay the match bit-exactly):
  - the serve must first bounce in the receiver's service box, else it is a let (the point is replayed from the same
    half with a fresh machine serve); a serve into the net is a let; the receiver may not hit the serve before it
    bounces (ITF 24 e);
  - any other ball may be volleyed or hit after one bounce on the hitter's half; a second bounce (miss) loses the point;
  - after a hit by P the ball must cross the net above it and first land in the other player's singles court (lines
    in), directly or after touching the net's top edge (net cord, ITF Rule 25 a): a ball into the net, out, or a
    bounce on P's own half lose P the point; a racket touches the ball at most once in a row.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import os
from collections import deque
from pathlib import Path

import numpy as np

import mujoco as mj
import tn
from tn import (ALPHA, BALL_R, CONTROL_DT, HEAD_A, HEAD_B, E_RACKET, KD, KP, MU_RACKET, OFFCENTRE_LOSS, PHYS_DT,  # noqa: F401
                RACKET_GAIN, SUBSTEPS, VEL_LIMIT, JOINTS, HOME, ARM_VEL, base_goto, ball_advance, impact, in_court,
                in_service_box)

HERE = Path(__file__).resolve().parent
SCENE2 = HERE / "scene" / "tn_duel.xml"
# the match format of the single-player game (tn.py): first to 5, from 4:4 by 2, at most 7; the match limit
from tn import WIN_POINTS, WIN_BY, CAP_POINTS, MAX_HITS, MAX_POINTS, match_won, match_winner, serve_index  # noqa: E402
READY_STEPS = 100               # 1.0 s between the resume and the serve
LEG_STEPS = 500                 # a ball not decided 5 s after it was played: the player to hit loses
CAM_EVERY = 2
SERVE_LEVEL = 1                 # the machine's serves: the single-player level-1 serve generator
SEED = int(os.environ.get("DUEL_SEED", "1"))
REVISION = "tennis-duel-wallclock-4"     # 2: volleys, receiver every point, win by 2 (cap 7), match limit; 3: net cord; 4: no draws (the match limit ends with a winner)
FIRST_RECEIVER = os.environ.get("FIRST_RECEIVER", "A")
if FIRST_RECEIVER not in ("A", "B"):
    raise ValueError("FIRST_RECEIVER must be A or B")
SIDES = ("A", "B")
OTHER = {"A": "B", "B": "A"}
MIR = np.array([-1.0, -1.0, 1.0])
Q_HOME = np.r_[HOME, tn.Q0_ARM]


def mir(v):
    return np.asarray(v, float) * MIR


def own(side, v):
    """A world vector in `side`'s own frame (and back: the mirror is its own inverse)."""
    return np.asarray(v, float).copy() if side == "A" else mir(v)


def half_of(y):
    return "A" if y < 0 else "B"


def _serve_generator():
    """tn.Match's serve generator without a match (a pure function of the level parameters, the seed and the point)."""
    g = tn.Match.__new__(tn.Match)
    g.lv = dict(tn.LEVELS[SERVE_LEVEL], seed=SEED)
    g._serve_cache = {}
    return g


class Side:
    """One robot's live control state (its own frame)."""

    def __init__(self, name):
        self.name = name
        self.plan, self.plan_j = [], 0
        self.base_goal = None
        self.q_hit_active = None
        self.last_act = None
        self.n_snapshots = 0           # acts planned so far (the execution scatter's ordinal)
        self.hit_enabled = False
        self.prev = None


class Duel:
    CAMS = tn.Match.CAMS
    VIEW_BACK = tn.Match.VIEW_BACK
    TILE = tn.Match.TILE

    def __init__(self):
        m = self.m = mj.MjModel.from_xml_path(str(SCENE2))
        d = self.d = mj.MjData(m)
        jid = lambda n: mj.mj_name2id(m, mj.mjtObj.mjOBJ_JOINT, n)
        sfx = {"A": "", "B": "_b"}
        self.qa = {s: np.array([m.jnt_qposadr[jid(j + sfx[s])] for j in JOINTS]) for s in SIDES}
        self.va = {s: np.array([m.jnt_dofadr[jid(j + sfx[s])] for j in JOINTS]) for s in SIDES}
        aid = lambda n: mj.mj_name2id(m, mj.mjtObj.mjOBJ_ACTUATOR, n)
        anames = ["motor_bx", "motor_by"] + [f"motor{i}" for i in range(1, 8)]
        self.aa = {s: np.array([aid(a + sfx[s]) for a in anames]) for s in SIDES}
        self.lo = m.jnt_range[[jid(j) for j in JOINTS], 0].copy()
        self.hi = m.jnt_range[[jid(j) for j in JOINTS], 1].copy()
        self.site = {s: mj.mj_name2id(m, mj.mjtObj.mjOBJ_SITE, "racket_center" + sfx[s]) for s in SIDES}
        self.clo, self.chi = m.actuator_ctrlrange[:, 0].copy(), m.actuator_ctrlrange[:, 1].copy()
        mj.mj_resetData(m, d)
        for s in SIDES:
            d.qpos[self.qa[s]] = Q_HOME
        mj.mj_forward(m, d)
        self.target = {s: Q_HOME.copy() for s in SIDES}
        self.actions = {s: [] for s in SIDES}
        self.sides = {s: Side(s) for s in SIDES}
        self.k = 0
        self.b_p, self.b_v, self.b_w, self.b_live = (0.0, 0.0, -5.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), False
        self.events: list[dict] = []
        self.score = {"A": 0, "B": 0}
        self.points: list[dict] = []
        self.hits = 0
        self.done = False
        self.limit_reached = False
        self.leg_id = -1
        self.hist: deque = deque(maxlen=16)
        self.review_hist: list = []
        self.serves = _serve_generator()
        self._start_point(0)

    # ------------------------------------------------------------------ points
    def receiver(self):
        """The receiver changes every point (lets do not count): FIRST_RECEIVER receives points 1, 3, 5, ..."""
        return FIRST_RECEIVER if sum(self.score.values()) % 2 == 0 else OTHER[FIRST_RECEIVER]

    def won(self):
        return match_won(self.score["A"], self.score["B"])

    def winner(self):
        """'A' or 'B' once the match is over (no draws): by the score, else the winner of the last point that was not
        a let, else the player who did not receive first."""
        if not self.done:
            return None
        w = match_winner(self.score["A"], self.score["B"],
                         [{"A": 0, "B": 1}.get(p["winner"]) for p in self.points], 0 if FIRST_RECEIVER == "B" else 1)
        return SIDES[w]

    def _start_point(self, hold_from):
        self.review_hist = list(self.hist)
        self.hist.clear()
        n = len(self.points)
        recv = self.receiver()
        # Serving half: deuce for scored points 0, 1, ad for 2, 3, ... (so both receivers get both boxes; ITF 17). A let
        # (no score change) is replayed from the same half; the machine's serve index also counts the points played,
        # so a replayed point gets a fresh serve of the same half (a fixed serve could repeat a fault forever).
        half = (sum(self.score.values()) // 2) % 2
        c = self.serves._serve_solution(serve_index(n, half))
        p0, v, w = (np.asarray(c[k], float) for k in ("p0", "v", "w"))
        if recv == "B":
            p0, v, w = mir(p0), mir(v), mir(w)
        self.leg_id += 1
        self.rs = {"point": n, "receiver": recv, "server_x": float(c["sx"]), "launch": hold_from + READY_STEPS,
                   "played_k": hold_from + READY_STEPS, "expect": recv, "hitter": None, "bounces": 0,
                   "state": "ready", "hits_in_point": 0, "serve": {"type": c["styp"], "speed": round(float(c["spd"]), 2),
                                                                     "target_kind": c["kind"]}}
        self.b_p, self.b_v, self.b_w = tuple(float(x) for x in p0), tuple(float(x) for x in v), tuple(float(x) for x in w)
        self.b_live = False
        self.events = []
        for s in SIDES:
            sd = self.sides[s]
            sd.hit_enabled = False
            sd.base_goal = None
        self._pending_point = None

    def in_play(self):
        return self.k >= self.rs["launch"]

    def t_since_played(self):
        return round((self.k - self.rs["played_k"]) * CONTROL_DT, 6)

    def _end_point(self, loser, how):
        if self._pending_point is None:
            self._pending_point = (loser, how)

    def _commit_point(self):
        loser, how = self._pending_point
        winner = OTHER[loser] if loser is not None else None
        if winner is not None:
            self.score[winner] += 1
        self.points.append({"point": len(self.points) + 1, "winner": winner, "loser": loser, "how": how,
                            "score": dict(self.score), "hits": self.rs["hits_in_point"], "step": self.k,
                            "receiver": self.rs["receiver"], "let": loser is None})
        self.rs["state"] = "over"
        self.b_live = False
        for s in SIDES:                     # no command carries over to the next point
            sd = self.sides[s]
            sd.plan, sd.plan_j, sd.last_act, sd.q_hit_active = [], 0, None, None
        if self.won():
            self.done = True
            return
        if self.hits >= MAX_HITS or len(self.points) >= MAX_POINTS:
            self.done = True
            self.limit_reached = True
            return
        self._start_point(self.k)

    # ------------------------------------------------------------------ physics + referee (shared by live and replay)
    def _check(self, s, q):
        if q.shape != (9,) or not np.all(np.isfinite(q)):
            raise ValueError(f"{s}: action must be 9 finite joint targets")
        if (q < self.lo - 1e-9).any() or (q > self.hi + 1e-9).any():
            raise ValueError(f"{s}: step {self.k}: joint target outside range")
        if (np.abs(q - self.target[s]) > VEL_LIMIT * CONTROL_DT * (1 + 1e-6) + 1e-12).any():
            raise ValueError(f"{s}: step {self.k}: joint speed limit")

    def step(self, qA, qB):
        qs = {"A": np.asarray(qA, np.float64).reshape(-1), "B": np.asarray(qB, np.float64).reshape(-1)}
        for s in SIDES:
            self._check(s, qs[s])
        m, d = self.m, self.d
        prev = {s: self.target[s] for s in SIDES}
        for j in range(1, SUBSTEPS + 1):
            for s in SIDES:
                qd_des = (qs[s] - prev[s]) / CONTROL_DT
                q_des = prev[s] + (qs[s] - prev[s]) * (j / SUBSTEPS)
                tau = KP * (q_des - d.qpos[self.qa[s]]) + KD * (qd_des - d.qvel[self.va[s]]) + d.qfrc_bias[self.va[s]]
                d.ctrl[self.aa[s]] = np.clip(tau, self.clo[self.aa[s]], self.chi[self.aa[s]])
            mj.mj_step(m, d)
            poses = {s: (d.site_xpos[self.site[s]].copy(), d.site_xmat[self.site[s]].reshape(3, 3).copy()) for s in SIDES}
            if self.b_live and self._pending_point is None:
                for s in SIDES:
                    sd = self.sides[s]
                    if sd.hit_enabled and sd.prev is not None:
                        self._check_hit(s, *poses[s])
                for s in SIDES:
                    self.sides[s].prev = (poses[s][0], poses[s][1], self.b_p)
                self._advance_ball()
            else:
                for s in SIDES:
                    self.sides[s].prev = (poses[s][0], poses[s][1], self.b_p)
        for s in SIDES:
            self.target[s] = qs[s].copy()
            self.actions[s].append(qs[s].copy())
        self.k += 1
        if self.rs["state"] == "ready" and self.k == self.rs["launch"]:
            self.rs["state"] = "live"
            self.b_live = True
            self.sides[self.rs["receiver"]].hit_enabled = True
        if not self.done and self._pending_point is None:
            self._referee()
        if self.k % CAM_EVERY == 0 or self._pending_point is not None:
            self.hist.append({"k": self.k, "t": self.t_since_played(), "qpos": d.qpos.copy(), "b": self.b_p,
                              "leg_id": self.leg_id})
        if self._pending_point is not None:
            self._commit_point()

    def _advance_ball(self):
        p, v, w, e = ball_advance(self.b_p, self.b_v, self.b_w)
        self.b_p, self.b_v, self.b_w = p, v, w
        if e is None:
            return
        if e[0] == "net":
            self.b_live = False
            self.events.append({"kind": "net", "k": self.k, "x": round(e[1], 4), "z": round(e[2], 4)})
        elif e[0] == "cord":
            self.events.append({"kind": "cord", "k": self.k, "x": round(e[1], 4), "z": round(e[2], 4)})
        else:
            self.events.append({"kind": "bounce", "k": self.k, "x": round(e[1], 4), "y": round(e[2], 4),
                                "half": half_of(e[2])})
        self._on_event(self.events[-1])

    def _check_hit(self, s, c1, R1):
        """tn.Phys._check_hit for robot s."""
        sd = self.sides[s]
        c0, R0, p0 = sd.prev
        n0, n1 = R0[:, 0], R1[:, 0]
        p0a = np.array(p0); p1a = np.array(self.b_p)
        s0 = float((p0a - c0) @ n0); s1 = float((p1a - c1) @ n1)
        side = 1.0 if s0 >= 0 else -1.0
        a0, a1 = side * s0, side * s1
        if not (a0 >= BALL_R > a1):
            return
        f = (a0 - BALL_R) / (a0 - a1)
        pc = c0 + f * (c1 - c0); ps = p0a + f * (p1a - p0a)
        nn = n0 + f * (n1 - n0); nn = nn / np.linalg.norm(nn)
        r = ps - pc
        la, lb = float(r @ R1[:, 1]), float(r @ R1[:, 2])
        rho2 = (la / HEAD_A) ** 2 + (lb / HEAD_B) ** 2
        if rho2 > 1.0:
            return
        vr = (c1 - c0) / PHYS_DT * RACKET_GAIN
        n_out = side * nn
        vb = np.array(self.b_v)
        e = E_RACKET * (1.0 - OFFCENTRE_LOSS * rho2)
        u = tuple(float(x) for x in vb - vr)
        u2, w2 = impact(u, self.b_w, tuple(float(x) for x in n_out), e, MU_RACKET)
        v_out = np.array(u2) + vr
        p_new = pc + (r - (r @ nn) * nn) + n_out * (BALL_R + 0.0005)
        self.b_p = tuple(float(x) for x in p_new); self.b_v = tuple(float(x) for x in v_out)
        self.b_w = tuple(float(x) for x in w2)
        sd.hit_enabled = False
        ev = {"kind": "hit", "side": s, "k": self.k, "pos": [round(float(x), 4) for x in ps],
              "offcentre": round(math.sqrt(rho2), 3), "speed": round(float(np.linalg.norm(v_out)), 3)}
        self.events.append(ev)
        self._on_event(ev)

    def _on_event(self, ev):
        rs = self.rs
        if self.done or rs["state"] != "live" or self._pending_point is not None:
            return
        exp, hitter = rs["expect"], rs["hitter"]
        kind = ev["kind"]
        if kind == "bounce":
            x, y, half = ev["x"], ev["y"], ev["half"]
            ox, oy = own(exp, [x, y, 0.0])[:2]          # in the frame of the player to hit
            if rs["bounces"] == 0:
                if hitter is None:                       # the machine's serve
                    if half == exp and in_service_box(ox, oy, rs["server_x"]):
                        rs["bounces"] = 1
                        return
                    return self._end_point(None, "let: the serve missed the service box")
                if half != exp:
                    return self._end_point(hitter, f"{hitter}'s shot came down on its own half")
                if not in_court(ox, oy, -1):
                    return self._end_point(hitter, f"{hitter}'s shot landed out")
                rs["bounces"] = 1
                return
            return self._end_point(exp, f"{exp} let the ball bounce twice")
        if kind == "cord":                               # the ball touched the net's top edge
            if hitter is None:
                return self._end_point(None, "let: the serve touched the net")   # ITF Rule 22 a
            return                                       # in a rally play goes on (ITF Rule 25 a)
        if kind == "net":
            if hitter is None:
                return self._end_point(None, "let: the serve hit the net")
            return self._end_point(hitter, f"{hitter}'s shot hit the net")
        if kind == "hit":
            p = ev["side"]
            if rs["bounces"] == 0 and hitter is None:      # ITF 24 e: the serve must bounce; other volleys are legal
                return self._end_point(p, f"{p} returned the serve before it bounced")
            rs["hitter"], rs["expect"], rs["bounces"] = p, OTHER[p], 0
            rs["played_k"] = self.k; rs["hits_in_point"] += 1; self.hits += 1
            self.leg_id += 1
            self.sides[OTHER[p]].hit_enabled = True
            return

    def _referee(self):
        rs = self.rs
        if rs["state"] != "live":
            return
        if not self.b_live or self.k - rs["played_k"] >= LEG_STEPS:
            exp, hitter = rs["expect"], rs["hitter"]
            if hitter is None and rs["bounces"] == 0:
                return self._end_point(None, "let: the serve was not completed")
            if rs["bounces"] >= 1 or hitter is None:
                return self._end_point(exp, f"{exp} missed the ball")
            return self._end_point(hitter, f"{hitter}'s shot was not completed")

    def replay(self, qA_list, qB_list):
        """Re-run the match from both robots' recorded joint targets (they determine everything else)."""
        if len(qA_list) != len(qB_list):
            raise ValueError("seat trajectory lengths differ")
        for a, b in zip(qA_list, qB_list):
            if self.done:
                raise ValueError("trajectory continues after the match end")
            self.step(a, b)

    def state_sha(self):
        h = hashlib.sha256()
        d = self.d
        for a in (d.qpos, d.qvel, d.qacc_warmstart, d.ctrl, np.array([d.time]), np.array(self.b_p + self.b_v + self.b_w)):
            h.update(np.ascontiguousarray(a, dtype=np.float64).tobytes())
        h.update(json.dumps(self.points, sort_keys=True).encode())
        return h.hexdigest()

    # ------------------------------------------------------------------ live control (each side in its own frame)
    def _target_vel(self, s):
        a = self.actions[s]
        return (a[-1] - a[-2]) / CONTROL_DT if len(a) >= 2 else np.zeros(9)

    def _ready_target(self, s):
        tgt = self.target[s]
        lim = ARM_VEL * CONTROL_DT * 0.6
        arm = tgt[2:] + np.clip(tn.Q0_ARM - tgt[2:], -lim, lim)
        sd = self.sides[s]
        goal = HOME if sd.base_goal is None else sd.base_goal
        b, _ = base_goto(tgt[:2], self._target_vel(s)[:2], goal)
        return np.r_[b, arm]

    def _arm_target(self, s):
        sd = self.sides[s]
        if sd.plan_j < len(sd.plan):
            q = sd.plan[sd.plan_j]; sd.plan_j += 1
            return q
        return self._ready_target(s)

    def rt_advance(self, n_steps=1):
        """Up to n_steps control steps with both robots' current commands; stops at the end of a point."""
        n0, n = len(self.points), 0
        while n < n_steps and not self.done and len(self.points) == n0:
            self.step(self._arm_target("A"), self._arm_target("B")); n += 1
        return n, self.points[n0:]

    def plan_snapshot(self, s) -> dict:
        """What the stroke planner needs from robot s at the step an act is accepted (its own frame; no ball)."""
        d, sd = self.d, self.sides[s]
        snap = {"k": self.k, "qpos": d.qpos[self.qa[s]].copy(), "qvel": d.qvel[self.va[s]].copy(),
                "qacc_warmstart": d.qacc_warmstart[self.va[s]].copy(), "ctrl": d.ctrl[self.aa[s]].copy(),
                "time": float(d.time), "target": self.target[s].copy(), "tail": [a.copy() for a in self.actions[s][-2:]],
                "plan": [q.copy() for q in sd.plan[sd.plan_j:]],
                "base_goal": None if sd.base_goal is None else sd.base_goal.copy(), "q_hit_active": sd.q_hit_active,
                "launch": int(self.rs["played_k"]),
                "seed": int(SEED * 1000 + (0 if s == FIRST_RECEIVER else 1)), "n_our_legs": int(sd.n_snapshots)}
        sd.n_snapshots += 1
        return snap

    def rt_install(self, s, res):
        if res["k_effect"] != self.k or not np.array_equal(res["target_at_effect"], self.target[s]):
            raise RuntimeError(f"{s}: plan for step {res['k_effect']} installed at step {self.k} (or its predicted joint "
                               "targets differ from the live ones)")
        sd = self.sides[s]
        if res["plan"]:
            sd.plan, sd.plan_j = list(res["plan"]), 0
            sd.q_hit_active = res["q_hit"]
            sd.last_act = res["info"]
        return res["info"]

    def rt_move(self, s, bx, by):
        sd = self.sides[s]
        sd.base_goal = np.clip(np.array([bx, by], float), tn.BASE_LO, tn.BASE_HI)
        return [round(float(x), 3) for x in sd.base_goal]

    def rt_clear(self, s):
        sd = self.sides[s]
        sd.plan, sd.plan_j, sd.last_act, sd.q_hit_active = [], 0, None, None

    # ------------------------------------------------------------------ observations
    def ensure_frame(self):
        if not self.hist:
            self.hist.append({"k": self.k, "t": self.t_since_played(), "qpos": self.d.qpos.copy(), "b": self.b_p,
                              "leg_id": self.leg_id})

    def side_state(self, s):
        """What player s knows without looking, in its own frame."""
        d, rs = self.d, self.rs
        other = OTHER[s]
        c = own(s, d.site_xpos[self.site[s]])
        n = own(s, d.site_xmat[self.site[s]].reshape(3, 3)[:, 0])
        heard = [{"event": "the machine served" if rs["hitter"] is None else
                  ("you hit the ball" if rs["hitter"] == s else "the opponent hit the ball"), "t": 0.0}]
        for e in self.events:
            if e["kind"] == "bounce" and e["k"] >= rs["played_k"]:
                heard.append({"event": "bounce on your side" if e["half"] == s else "bounce on the opponent's side",
                              "t": round((e["k"] - rs["played_k"]) * CONTROL_DT, 2)})
        live = self.in_play() and rs["state"] == "live"
        return {"score": {"you": self.score[s], "opponent": self.score[other]}, "point": len(self.points) + 1,
                "you_receive_serve": rs["receiver"] == s,
                "ball": "serve" if rs["hitter"] is None else ("your shot" if rs["hitter"] == s else "opponent's shot"),
                "ball_in_play": live,
                "ball_state": ("not yet served" if not self.in_play() else
                               ("coming to you" if live and rs["expect"] == s else
                                ("going to the opponent" if live else "dead"))),
                "t_since_played": self.t_since_played(), "heard": heard,
                "robot_base_xy": [round(float(x), 3) for x in d.qpos[self.qa[s][:2]]],
                "q_arm": [round(float(x), 4) for x in d.qpos[self.qa[s][2:]]],
                "racket_pos": [round(float(x), 3) for x in c], "racket_normal": [round(float(x), 3) for x in n]}

    def cameras(self, s):
        cams = []
        for lookat, dist, az, el in self.CAMS:
            c = mj.MjvCamera()
            c.lookat[:] = lookat if s == "A" else mir(lookat)
            c.distance = dist; c.azimuth = az if s == "A" else az + 180.0; c.elevation = el
            cams.append(c)
        return cams


def render_video(qA, qB, out, fps=25, every=2):
    """Replay video: a high side view of the whole court, 2x slow motion, with the score."""
    import imageio.v2 as imageio
    from PIL import Image, ImageDraw
    du = Duel()
    r = mj.Renderer(du.m, height=360, width=640)
    rd = mj.MjData(du.m)
    c = mj.MjvCamera(); c.lookat[:] = [0.0, 0.0, 0.5]; c.distance = 30.0; c.azimuth = 0.0; c.elevation = -30.0
    w = imageio.get_writer(out, fps=fps, macro_block_size=8)
    for k, (a, b) in enumerate(zip(qA, qB)):
        du.step(a, b)
        if k % (every if du.b_live else 3 * every):
            continue
        rd.qpos[:] = du.d.qpos; rd.mocap_pos[0] = du.b_p
        mj.mj_kinematics(du.m, rd)
        r.update_scene(rd, camera=c)
        im = Image.fromarray(r.render())
        ImageDraw.Draw(im).text((8, 6), f"B (left) {du.score['B']} : {du.score['A']} A (right)", fill=(255, 255, 255))
        w.append_data(np.asarray(im))
        if du.done:
            break
    w.close(); r.close()
