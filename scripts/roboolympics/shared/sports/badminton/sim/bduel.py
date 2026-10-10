"""Badminton duel: two robots, two players; rally scoring, first to 5 points, from 4-4 a two-point lead, at most 7.

Robot A (y < 0, facing +y) and robot B (y > 0, facing -y) are identical: the match task's robot (a Franka Panda on a
sliding base with a racket, bm.py). Each player sees and acts in its OWN frame, the frame of the single-player task
(its home at (0, -4.0), its half y < 0); B's frame is the world rotated 180 degrees about z: (x, y, z) -> (-x, -y, z).

Physics. MuJoCo contacts are off in the badminton scene and the shuttle is not a MuJoCo body, so the two robots never
interact physically: each robot runs in its OWN copy of the single-player model (scene/bm_scene.xml, `bm.Phys`), in its
own frame, stepped in lock-step at 1 ms; the shuttle (bm's point mass with quadratic drag) is integrated once, in the
world frame (A's frame). At every 1 ms step the racket of the player whose turn it is is tested against the shuttle
with the match task's contact model (bm.Phys._check_hit), and only while the shuttle is on that player's half. The
two-robot scene scene/bm_duel.xml only draws the game.

Stroke control. A player's act is the match task's racket-level command, planned by the match task's stroke controller
(`bm.Match.plan_racket`) on that player's own robot (`Side`). Because each robot's motion depends only on its own
joint targets, a planner process can advance an exact copy of the robot to the act's effect step and plan there; the
result is bit-identical to planning in the world thread (`apply_inline`, which the replay uses).

Points (the referee is a deterministic function of the 1 ms flight, evaluated inside every control step, so the
logged acts replay the match bit-exactly):
  * ready: both robots at rest in the ready pose at their spots in their service courts (bm.serve_spot: the right
    courts when the server's score is even, else the left ones; diagonally opposite, BWF 10.1, 9.1.3); FIRST_SERVER
    serves the first point, then the rally winner (Law 10.3; a let keeps the server). READY_STEPS (1 s) after play
    resumes the receiver is ready (state to_serve) and the server may toss the shuttle (`toss`: it appears at a point
    within bm.TOSS_REACH of its base, bm.TOSS_Z high, from rest or rising up to bm.TOSS_H_MAX) within
    SERVE_WINDOW_STEPS, else a service fault (undue delay; the MAX_DELAY_FAULTS-th disqualifies the player, Law
    16.7). Faults are recorded as "serve_fault:<reason>: ..." (docs/conventions/racket_serve_zh.md). The server must
    hit the tossed shuttle (a miss: fault, 9.1.8) below SERVE_MAX_Z (9.1.6) and upwards (9.1). Both bases stay within BASE_TOL of
    their spots until the serve is delivered (9.1.4; the mover's fault, both: a let);
  * the receiver must hit the serve; then the players hit in turn. A racket meets the shuttle only when it is that
    player's turn and the shuttle is on that player's half; after a hit the hitter's racket no longer touches it;
  * the shuttle lands (no bounce): in the court of the player whose turn it is (lines in) -> that player loses; out of
    that court -> the last hitter loses; on the last hitter's own half -> the hitter loses; into the net (below the
    top, between the posts) -> the hitter loses. An unreturned serve must land in the receiver's diagonal service
    court (else a service fault: the receiver's point).
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import pickle
from collections import deque
from pathlib import Path

import numpy as np

import mujoco as mj
import bm

# The robot, its base (6 m/s, 20 m/s^2), the scoring (first to 5, two-point lead from 4-4, at most 7), the hit cap and
# the shot timeout are the match task's (bm.py): the single-player task and the duel play by the same rules.
from bm import (BASE_VMAX, BASE_AMAX, WIN_POINTS, CAP_POINTS, MAX_HITS, MAX_POINTS, LEG_STEPS)  # noqa: E402,F401
from bm import (CONTROL_DT, SUBSTEPS, PHYS_DT, KP, KD, HOME, NET_TOP, POST_X, R_HEAD, RACKET_GAIN, E_SHUTTLE,
                OFFCENTRE_LOSS, SHOT_THETAS, SHOT_VMAX, sh_step, solve_shots, in_court)
from bm import SERVE_MAX_Z, SERVE_WINDOW_STEPS, BASE_TOL, MAX_DELAY_FAULTS, serve_spot, toss_problem, toss_vz  # noqa: E402

HERE = Path(__file__).resolve().parent
SCENE2 = HERE / "scene" / "bm_duel.xml"
REVISION = "bm-duel-wallclock-6"   # 2: base 6 m/s; 3: BWF serve courts, net 1.524 m, win by 2 (cap 7), receiver every point; 4: no draws (cap winner), rules in bm.py; 5: one scatter sequence for both robots; 6: the players serve (BWF Law 9)
SEED = int(os.environ.get("DUEL_SEED", "1"))      # the (shared) execution scatter
FIRST_SERVER = os.environ.get("FIRST_SERVER", "A")      # the side that serves the first point (Law 6: the toss)
if FIRST_SERVER not in ("A", "B"):
    raise ValueError("FIRST_SERVER must be A or B")
SIDES = ("A", "B")
OTHER = {"A": "B", "B": "A"}
MIR = np.array([-1.0, -1.0, 1.0])
READY_STEPS = 100              # 1.0 s from resume until the receiver is ready and the server may toss
CAM_EVERY = 2
Q_HOME = np.r_[HOME, bm.Q0_ARM]


def mir(v):
    return np.asarray(v, float) * MIR


def to_side(side, v):
    """World (A's frame) -> the side's own frame (and back: the map is its own inverse)."""
    return np.asarray(v, float) if side == "A" else mir(v)


# ---------------------------------------------------------------------------------------------- one player's robot
class Side(bm.Match):
    """One player's robot and stroke controller in its own frame: the match task's `Match` without the shuttle, the
    opponent and the referee (those live in `World`). Used live, in the planner process (an exact copy) and in the
    replay."""

    def __init__(self, side: str):              # noqa: D107 (bm.Match.__init__ is not called on purpose)
        self.side = side
        self.level = 0
        # the execution scatter: ONE seeded sequence shared by both robots (the n-th act of each robot gets the same
        # scatter draw, bm.Match.plan_racket), so neither seat nor role picks a luckier stream (as baseball's duel
        # gives both batters the same pitches); revision 4 drew a stream per role (seed x 10 + 0 for the first
        # receiver, + 1 for the other), which made the first receiver win 30 of 40 fairness matches
        self.lv = {"seed": SEED * 10}
        self.s = bm.Phys()
        self.s.reset(Q_HOME.copy())
        self.home = HOME.copy()                 # the ready target's base goal: the point's spot (go_home)
        self._twin = None
        self.plan, self.plan_j = [], 0
        self.leg = {"launch": 0}
        self.shots: list = []
        self._last_act = None
        self._q_hit_active = None
        self._ik_seed = None
        self.n_applied = 0                      # acts applied so far (the execution scatter's stream index)
        self.n_since_reset = 0                  # control steps since the robot was last put back at home

    @property
    def n_our_legs(self):                       # bm.Match.plan_racket's scatter index: this player's act ordinal
        return self.n_applied

    def _target_vel(self):
        a = self.s._actions
        return (a[-1] - a[-2]) / CONTROL_DT if self.n_since_reset >= 2 and len(a) >= 2 else np.zeros(9)

    def rt_act(self, T, pos, nrm, vel):
        self.leg = {"launch": self.k}           # T counts from now
        return super().rt_act(T, pos, nrm, vel)

    def go_home(self, spot):
        """Before a serve: the robot at its spot in its service court (its home for the point) in the ready pose, at
        rest, no command."""
        ph = self.s
        self.home = np.asarray(spot, float).copy()
        q = np.r_[self.home, bm.Q0_ARM]
        ph.d.qpos[ph.qa] = q; ph.d.qvel[ph.va] = 0.0
        mj.mj_forward(ph.m, ph.d)
        ph.target = q.copy()
        self.plan, self.plan_j = [], 0
        self._last_act = None; self._q_hit_active = None
        self.n_since_reset = 0

    def solo_step(self):
        """One control step of this robot alone (the planner's copy): the same targets and robot physics as World."""
        q = np.asarray(self._arm_target(), float)
        self.s.step(q)
        self.n_since_reset += 1

    def state_key(self) -> str:
        """Everything the stroke planner reads, hashed."""
        ph = self.s
        h = hashlib.sha256()
        for a in (ph.d.qpos, ph.d.qvel, ph.d.qacc_warmstart, ph.d.ctrl, np.array([ph.d.time]), ph.target):
            h.update(np.ascontiguousarray(a, dtype=np.float64).tobytes())
        h.update(repr((self.k, self.plan_j, len(self.plan), self.n_applied, self.n_since_reset)).encode())
        h.update(np.ascontiguousarray(self.home, dtype=np.float64).tobytes())
        if len(ph._actions) >= 2:
            h.update(np.ascontiguousarray(ph._actions[-2], dtype=np.float64).tobytes())
        if self._q_hit_active is not None:
            h.update(np.ascontiguousarray(self._q_hit_active, dtype=np.float64).tobytes())
        if self.plan_j < len(self.plan):
            h.update(np.ascontiguousarray(np.asarray(self.plan[self.plan_j:]), dtype=np.float64).tobytes())
        return h.hexdigest()


def plan_on(side: Side, dec: dict) -> dict:
    """What `apply_inline` would do at the copy's current step, as an installable result."""
    if dec["type"] == "none":
        return {"type": "none"}
    T = float(dec["t"])
    side.leg = {"launch": side.k}
    ik_seed = side._q_hit_active if side.plan_j < len(side.plan) else None
    side._ik_seed = ik_seed
    plan, info = side.plan_racket(T, dec["pos"], dec["normal"], dec["vel"])
    q_hit = info.pop("_q_hit", None)
    info["T_from_now"] = round(T, 4)
    return {"type": "act", "plan": plan, "q_hit": q_hit, "info": info, "ik_seed": ik_seed,
            "swing_last": getattr(side, "_swing_last", None)}


def install(side: Side, res: dict):
    """Apply a planned result with exactly the attribute changes of `apply_inline`."""
    side.n_applied += 1
    if res["type"] == "none":
        side.rt_clear()
        return None
    side.leg = {"launch": side.k}
    side._ik_seed = res["ik_seed"]
    if res["swing_last"] is not None:
        side._swing_last = res["swing_last"]
    info = res["info"]
    if res["plan"]:
        side.plan, side.plan_j = res["plan"], 0
        side._q_hit_active = res["q_hit"]
    side.shots.append({"k": side.k, "leg": side.n_applied - 1, **info})
    side._last_act = info
    return info


def apply_inline(side: Side, dec: dict):
    """The reference semantics (also the replay's): plan and apply at the current step."""
    if dec["type"] == "none":
        side.n_applied += 1
        side.rt_clear()
        return None
    info = side.rt_act(dec["t"], dec["pos"], dec["normal"], dec["vel"])
    side.n_applied += 1
    return info


# ---------------------------------------------------------------------------------------------- snapshots
class _Pickler(pickle.Pickler):
    def persistent_id(self, obj):
        return "MODEL" if isinstance(obj, mj.MjModel) else None


class _Unpickler(pickle.Unpickler):
    def __init__(self, f, model):
        super().__init__(f)
        self.model = model

    def persistent_load(self, pid):
        if pid != "MODEL":
            raise pickle.UnpicklingError(pid)
        return self.model


def snapshot(side: Side) -> bytes:
    """Exact copy of one robot for planning (not copied: the MjModel, the scratch twin, older joint targets)."""
    tw = side.__dict__.pop("_twin", None)
    acts = side.s._actions
    side.s._actions = acts[-2:]
    try:
        f = io.BytesIO()
        _Pickler(f, protocol=pickle.HIGHEST_PROTOCOL).dump(side)
        return f.getvalue()
    finally:
        side._twin = tw
        side.s._actions = acts


def restore(b: bytes, model) -> Side:
    side = _Unpickler(io.BytesIO(b), model).load()
    side._twin = None
    return side


# ---------------------------------------------------------------------------------------------- the world
class World:
    def __init__(self):
        self.sides = {s: Side(s) for s in SIDES}
        self.k = 0
        self.sh_p, self.sh_v, self.sh_live = (0.0, 3.0, 1.0), (0.0, 0.0, 0.0), False
        self.prev = {s: None for s in SIDES}
        self.events: list[dict] = []
        self.score = {"A": 0, "B": 0}
        self.points: list[dict] = []
        self.hits = 0
        self.plays = 0                          # tosses + hits in the match (a flight's id)
        self.done = False
        self.winner = None
        self.hist: deque = deque(maxlen=16)
        self.review_hist = None
        self._pending_point = None
        self.delay_faults = {"A": 0, "B": 0}    # serves not tossed in time (undue delay)
        self.disqualified = None                # the side with MAX_DELAY_FAULTS (Law 16.7): it loses the match
        self._start_point(0)

    # ------------------------------------------------------------------ points
    def next_server(self):
        """FIRST_SERVER serves the first point (Law 6); then the winner of the last rally serves (Law 10.3); after a
        let the same player serves again (Law 14.3)."""
        if not self.points:
            return FIRST_SERVER
        last = self.points[-1]
        return last["server"] if last["let"] else last["winner"]

    def receiver(self):
        return self.rs["receiver"]

    def match_over(self):
        """First to WIN_POINTS; from 4-4 a two-point lead is needed, capped: the first to CAP_POINTS wins."""
        hi, lo = max(self.score.values()), min(self.score.values())
        return (hi >= WIN_POINTS and hi - lo >= 2) or hi >= CAP_POINTS

    def _start_point(self, hold_from):
        n = len(self.points)
        srv = self.next_server()
        recv = OTHER[srv]
        right = self.score[srv] % 2 == 0        # the server's right court when its score is even (Law 10.1)
        spot = serve_spot(right)                # both robots in their right (left) service courts: diagonal (9.1.3)
        ready = hold_from + READY_STEPS
        self.rs = {"point": n, "server": srv, "receiver": recv, "service_court_right": right,
                   "hold_from": hold_from, "ready": ready, "deadline": ready + SERVE_WINDOW_STEPS, "launch": ready,
                   "expect": srv, "last_hitter": None, "played_k": ready, "state": "ready", "flight": self.plays,
                   "hits_in_point": 0, "serve_flight": False, "toss_k": None, "serve": None, "spot": spot.copy()}
        # the shuttle is held in the server's (missing) free hand, beside its ready pose, until the toss
        self.sh_p = tuple(float(x) for x in to_side(srv, np.r_[spot + np.array([-0.25, 0.35]), 1.0]))
        self.sh_v = (0.0, 0.0, 0.0)
        self.sh_live = False; self.hit_enabled = False
        self.events = []
        self.hist.clear()
        for s in SIDES:
            self.sides[s].go_home(spot)
            self.prev[s] = None

    def delivered(self):
        """The serve of the current point was delivered (hit or faulted)."""
        return self.rs["state"] not in ("ready", "to_serve", "tossed")

    def toss(self, side, p, h=0.0):
        """The server's toss: the shuttle appears at p (its own frame) now and rises h straight up (0: from rest).
        Raises ValueError if not allowed."""
        rs = self.rs
        if self.done or side != rs["server"]:
            raise ValueError("it is not your serve")
        if rs["state"] == "ready":
            raise ValueError(f"the receiver is not ready before step {rs['ready']}")
        if rs["state"] != "to_serve":
            raise ValueError("the shuttle was already tossed")
        ph = self.sides[side].s
        why = toss_problem(p, h, ph.d.qpos[ph.qa[:2]])
        if why:
            raise ValueError(why)
        self.sh_p = tuple(float(x) for x in to_side(side, p)); self.sh_v = (0.0, 0.0, toss_vz(h))
        self.sh_live = True; self.hit_enabled = True
        rs.update(state="tossed", toss_k=self.k, played_k=self.k, launch=self.k)
        rs["serve"] = {"toss": [round(float(x), 4) for x in p], "toss_height": float(h), "toss_k": self.k}
        self.plays += 1; rs["flight"] = self.plays
        self.events.append({"kind": "toss", "side": side, "k": self.k})

    def in_play(self):
        return self.rs["state"] in ("tossed", "live")

    def _end_point(self, loser, how):
        if self._pending_point is None:
            self._pending_point = (loser, how)

    def _commit_point(self):
        loser, how = self._pending_point
        self._pending_point = None
        winner = OTHER[loser] if loser is not None else None
        if winner is not None:
            self.score[winner] += 1
        self.review_hist = list(self.hist)
        self.points.append({"point": len(self.points) + 1, "winner": winner, "loser": loser, "how": how,
                            "score": dict(self.score), "hits": self.rs["hits_in_point"], "step": self.k,
                            "server": self.rs["server"], "receiver": self.rs["receiver"],
                            "court": "right" if self.rs["service_court_right"] else "left",
                            "serve": self.rs["serve"], "let": loser is None})
        self.rs["state"] = "over"
        if self.disqualified:
            self.points[-1]["disqualified"] = self.disqualified
            self.winner = OTHER[self.disqualified]
            self.done = True
            return
        if self.match_over():
            self.winner = max(SIDES, key=lambda s: self.score[s])
            self.done = True
            return
        if self.hits >= MAX_HITS or len(self.points) >= MAX_POINTS:
            # the cap: the leader wins; if level, the winner of the last point (no draws; as in the single task); the
            # last resort (no point won, not from the rulebook): the player who received first
            last = next((p["winner"] for p in reversed(self.points) if p["winner"]), OTHER[FIRST_SERVER])
            sa, sb = self.score["A"], self.score["B"]
            self.winner = "A" if sa > sb else "B" if sb > sa else last
            self.points[-1]["cap"] = True
            self.done = True
            return
        self._start_point(self.k)

    # ------------------------------------------------------------------ physics (shared by live and replay)
    def advance(self):
        """One control step: both robots follow their commands (the planned stroke, else back to the ready pose)."""
        if self.done:
            raise ValueError("the match is over")
        qs = {s: np.asarray(self.sides[s]._arm_target(), float) for s in SIDES}
        for s in SIDES:
            self.sides[s].s.check_target(qs[s])
        prev_t = {s: self.sides[s].s.target for s in SIDES}
        qd_des = {s: (qs[s] - prev_t[s]) / CONTROL_DT for s in SIDES}
        rk = {}
        for j in range(1, SUBSTEPS + 1):
            for s in SIDES:                     # the robot part of bm.Phys.step, per robot in its own model
                ph = self.sides[s].s
                m, d = ph.m, ph.d
                q_des = prev_t[s] + (qs[s] - prev_t[s]) * (j / SUBSTEPS)
                tau = KP * (q_des - d.qpos[ph.qa]) + KD * (qd_des[s] - d.qvel[ph.va]) + d.qfrc_bias[ph.va]
                d.ctrl[:] = np.clip(tau, m.actuator_ctrlrange[:, 0], m.actuator_ctrlrange[:, 1])
                mj.mj_step(m, d)
                c = d.site_xpos[ph.site].copy(); n = d.site_xmat[ph.site].reshape(3, 3)[:, 0].copy()
                rk[s] = (to_side(s, c), to_side(s, n))
            if self.sh_live:
                e = self.rs["expect"]
                own_half = self.sh_p[1] < 0 if e == "A" else self.sh_p[1] > 0
                if self.hit_enabled and own_half and self.prev[e] is not None:
                    self._check_hit(e, *rk[e])
                for s in SIDES:
                    self.prev[s] = (rk[s][0], rk[s][1], self.sh_p)
                self._advance_shuttle()
            else:
                for s in SIDES:
                    self.prev[s] = (rk[s][0], rk[s][1], self.sh_p)
        for s in SIDES:
            ph = self.sides[s].s
            ph.target = qs[s].copy()
            ph._actions.append(qs[s].copy())
            ph.k += 1
            ph.steps_total += SUBSTEPS
            self.sides[s].n_since_reset += 1
        self.k += 1
        rs = self.rs
        if rs["state"] == "ready" and self.k >= rs["ready"]:
            rs["state"] = "to_serve"            # the receiver is ready (Law 9.4): the server may toss
        if self._pending_point is None and rs["state"] != "over":
            self._referee()
        if self.k % CAM_EVERY == 0 or self._pending_point is not None:
            self.hist.append(self.snap())
        if self._pending_point is not None:
            self._commit_point()

    def snap(self):
        return {"k": self.k, "qA": self.sides["A"].s.d.qpos.copy(), "qB": self.sides["B"].s.d.qpos.copy(),
                "sh": self.sh_p, "shv": self.sh_v, "played_k": self.rs["played_k"], "point": self.rs["point"],
                "flight": self.rs["flight"], "wall_mono": __import__("time").monotonic()}

    def _check_hit(self, side, c, n):
        """bm.Phys._check_hit for one racket (world frame)."""
        cp, npv, sp = self.prev[side]
        sp = np.array(sp); sh = np.array(self.sh_p)
        s0 = float((sp - cp) @ npv); s1 = float((sh - c) @ n)
        if s0 * s1 > 0 or (s0 == 0 and s1 == 0):
            return
        f = s0 / (s0 - s1) if s0 != s1 else 0.0
        pc = cp + f * (c - cp); ps = sp + f * (sh - sp)
        r = ps - pc
        off = float(np.linalg.norm(r - (r @ n) * n))
        if off > R_HEAD:
            return
        vr = (c - cp) / PHYS_DT; vs = np.array(self.sh_v)
        n_out = n if float((vr - vs) @ n) >= 0 else -n
        u = float(vr @ n_out); vin = float(vs @ n_out)
        spd = RACKET_GAIN * max(u, 0.0) * (1 - OFFCENTRE_LOSS * (off / R_HEAD) ** 2) + E_SHUTTLE * max(0.0, -vin)
        v_out = n_out * spd
        p_new = ps + n_out * 0.002
        self.sh_p = tuple(float(x) for x in p_new); self.sh_v = tuple(float(x) for x in v_out)
        rs = self.rs
        serve = rs["state"] == "tossed"         # the server's hit of the tossed shuttle: the serve
        rs["last_hitter"] = side; rs["expect"] = OTHER[side]; rs["played_k"] = self.k
        rs["hits_in_point"] += 1; self.hits += 1; self.plays += 1; rs["flight"] = self.plays
        rs["serve_flight"] = serve
        self.events.append({"kind": "hit", "side": side, "k": self.k, "pos": [round(float(x), 4) for x in ps],
                            "offcentre": round(off, 4), "racket_speed": round(u, 3), "speed": round(spd, 3),
                            "v_out": [round(float(x), 3) for x in v_out]})
        if serve:
            rs["state"] = "live"
            z = float(ps[2])
            rs["serve"].update(hit_k=self.k, contact_z=round(z, 4), speed=round(spd, 3),
                               v_out=[round(float(x), 3) for x in to_side(side, v_out)])
            if z > SERVE_MAX_Z:                 # Law 9.1.6: the whole shuttle below 1.15 m when hit
                self._end_point(side, f"serve_fault:too_high: {side} hit the shuttle {z:.2f} m high, above {SERVE_MAX_Z} m "
                                      "(Law 9.1.6)")
            elif float(v_out[2]) <= 0.0:        # Law 9.1: the flight upwards from the server's racket
                self._end_point(side, f"serve_fault:not_upwards: {side}'s serve did not go upwards from the racket (Law 9.1)")

    def _advance_shuttle(self):
        """bm.Phys._advance_shuttle (world frame)."""
        p, v = self.sh_p, self.sh_v
        p1, v1 = sh_step(p, v)
        if (p[1] > 0) != (p1[1] > 0) and p[1] != p1[1]:
            f = p[1] / (p[1] - p1[1])
            z = p[2] + f * (p1[2] - p[2]); x = p[0] + f * (p1[0] - p[0])
            self.events.append({"kind": "cross", "k": self.k, "x": round(x, 4), "z": round(z, 4),
                                "to": "B" if p1[1] > 0 else "A"})
            if z < NET_TOP and abs(x) <= POST_X:
                self.sh_p = (x, 0.0, z); self.sh_v = (0.0, 0.0, 0.0); self.sh_live = False
                self.events.append({"kind": "net", "k": self.k, "x": round(x, 4), "z": round(z, 4)})
                return
        if p1[2] <= 0.0:
            f = p[2] / (p[2] - p1[2]) if p[2] != p1[2] else 1.0
            x = p[0] + f * (p1[0] - p[0]); y = p[1] + f * (p1[1] - p[1])
            self.sh_p = (x, y, 0.0); self.sh_v = (0.0, 0.0, 0.0); self.sh_live = False
            self.events.append({"kind": "land", "k": self.k, "x": round(x, 4), "y": round(y, 4)})
            return
        self.sh_p, self.sh_v = p1, v1

    def _referee(self):
        rs = self.rs
        if not self.delivered():                # Law 9.1.4: server and receiver stand still until the serve
            moved = {}
            for s in SIDES:
                ph = self.sides[s].s
                d = float(np.hypot(*(ph.d.qpos[ph.qa[:2]] - rs["spot"])))
                if d > BASE_TOL:
                    moved[s] = d
            if len(moved) == 2:
                return self._end_point(None, "let: both bases moved before the serve was delivered (Law 14.2.2)")
            if moved:
                s, d = next(iter(moved.items()))
                who = "serve_fault:moved" if s == rs["server"] else "receive_fault:moved"
                return self._end_point(s, f"{who}: {s}'s base moved {d:.2f} m from its spot before the serve was "
                                          "delivered (Law 9.1.4)")
        srv = rs["server"]
        if rs["state"] == "to_serve":
            if self.k >= rs["deadline"]:
                self.delay_faults[srv] += 1
                dq = self.delay_faults[srv] >= MAX_DELAY_FAULTS
                if dq:
                    self.disqualified = srv
                return self._end_point(srv, f"serve_fault:undue_delay: {srv} did not toss the shuttle within "
                                            f"{SERVE_WINDOW_STEPS * CONTROL_DT:.0f} s (undue delay, Law 9.1.1)"
                                       + (f"; {srv}'s {MAX_DELAY_FAULTS}rd undue-delay fault disqualifies it "
                                          "(Law 16.7)" if dq else ""))
            return
        if rs["state"] not in ("tossed", "live"):
            return
        exp, hitter = rs["expect"], rs["last_hitter"]
        ends = [e for e in self.events if e["kind"] in ("net", "land") and e["k"] == self.k - 1]
        if ends:
            e = ends[0]
            if rs["state"] == "tossed":         # the tossed shuttle reached the floor: the server missed it
                return self._end_point(srv, f"serve_fault:missed: {srv} missed the shuttle (Law 9.1.8)")
            if e["kind"] == "net":
                if rs["serve_flight"]:
                    return self._end_point(hitter, f"serve_fault:net: {hitter}'s serve hit the net (x={e['x']:.2f}, "
                                                   f"height {e['z']:.2f} m; Laws 9.1, 13.3.2)")
                return self._end_point(hitter, f"{hitter}'s shot hit the net (x={e['x']:.2f}, height {e['z']:.2f} m)")
            x, y = e["x"], e["y"]
            half = "A" if y < 0 else "B"
            sign = lambda s: -1 if s == "A" else 1          # in_court's side argument in the world frame
            if half == hitter:
                return self._end_point(hitter, f"{hitter}'s shot came down on its own side (x={x:.2f}, y={y:.2f})")
            if rs["serve_flight"]:              # the serve: it must land in the receiver's diagonal service court
                xr, yr = to_side(exp, [x, y, 0.0])[:2]
                if bm.in_service_court(xr, yr, rs["service_court_right"]):
                    return self._end_point(exp, f"{hitter}'s serve landed in {exp}'s service court (x={x:.2f}, "
                                                f"y={y:.2f}): {exp} did not return it")
                return self._end_point(hitter, f"serve_fault:out: {hitter}'s serve landed outside {exp}'s service court "
                                               f"(x={x:.2f}, y={y:.2f})")
            if in_court(x, y, sign(exp)):
                return self._end_point(exp, f"{hitter}'s shot landed in {exp}'s court (x={x:.2f}, y={y:.2f}): {exp} did not return it")
            return self._end_point(hitter, f"{hitter}'s shot landed out (x={x:.2f}, y={y:.2f})")
        if self.k - rs["played_k"] > LEG_STEPS:
            return self._end_point(exp, f"{exp} did not play the shuttle in time")

    # ------------------------------------------------------------------ replay and fingerprints
    def actions(self):
        return {s: [q.tolist() for q in self.sides[s].s._actions] for s in SIDES}

    def state_sha(self):
        h = hashlib.sha256()
        for s in SIDES:
            d = self.sides[s].s.d
            for a in (d.qpos, d.qvel, d.qacc_warmstart, d.ctrl, np.array([d.time])):
                h.update(np.ascontiguousarray(a, dtype=np.float64).tobytes())
        h.update(np.array(self.sh_p + self.sh_v, dtype=np.float64).tobytes())
        h.update(json.dumps(self.points, sort_keys=True).encode())
        return h.hexdigest()

    def targets_sha(self):
        return hashlib.sha256(json.dumps(self.actions(), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# ---------------------------------------------------------------------------------------------- rendering
CAMS = bm.Match.CAMS                       # behind and side, in the player's own frame (as in the match task)
VIEW_BACK = bm.Match.VIEW_BACK             # 0, 60, 120, 180 ms back
TILE = bm.Match.TILE


class Renderer:
    """Draws the two-robot scene: the player's two cameras (in its own frame) x 4 frames."""

    def __init__(self, side="A", width=TILE[0], height=TILE[1]):
        self.m = mj.MjModel.from_xml_path(str(SCENE2))
        self.d = mj.MjData(self.m)
        jid = lambda n: self.m.jnt_qposadr[mj.mj_name2id(self.m, mj.mjtObj.mjOBJ_JOINT, n)]
        self.qa = {"A": np.array([jid(j) for j in bm.JOINTS]), "B": np.array([jid(j + "_b") for j in bm.JOINTS])}
        self.r = mj.Renderer(self.m, height=height, width=width)
        self.cams = []
        for lookat, dist, az, el in CAMS:
            c = mj.MjvCamera()
            c.lookat[:] = to_side(side, lookat); c.distance = dist; c.azimuth = az + (0.0 if side == "A" else 180.0)
            c.elevation = el
            self.cams.append(c)

    def set_state(self, sn):
        d = self.d
        d.qpos[self.qa["A"]] = sn["qA"]; d.qpos[self.qa["B"]] = sn["qB"]
        d.mocap_pos[0] = sn["sh"]
        v = np.asarray(sn["shv"], float)
        if np.linalg.norm(v) < 1e-6:
            v = np.array([0.0, 0.0, -1.0])
        d.mocap_quat[0] = bm.quat_z_to(v)
        mj.mj_kinematics(self.m, d)

    def views(self, snaps) -> bytes:
        import imageio.v2 as imageio
        from PIL import Image, ImageDraw
        rows = []
        for c in self.cams:
            tiles = []
            for sn in snaps:
                self.set_state(sn)
                self.r.update_scene(self.d, camera=c)
                im = Image.fromarray(self.r.render())
                t = (sn["k"] - sn["played_k"]) * CONTROL_DT
                ImageDraw.Draw(im).text((6, 4), f"k={sn['k']} t={t:.2f}s", fill=(255, 255, 255))
                tiles.append(np.asarray(im))
            rows.append(np.concatenate(tiles, axis=1))
        buf = io.BytesIO()
        imageio.imwrite(buf, np.concatenate(rows, axis=0), format="png")
        return buf.getvalue()


def render_video(acts, k_end, out, fps=25, every=2):
    """Replay video from the logged acts: a high side view of the whole court, 2x slow motion, with the score."""
    import imageio.v2 as imageio
    from PIL import Image, ImageDraw
    w = World()
    rd = Renderer("A", 640, 360)
    cam = mj.MjvCamera(); cam.lookat[:] = [0.0, 0.0, 1.0]; cam.distance = 17.0; cam.azimuth = 0.0; cam.elevation = -22.0
    vw = imageio.get_writer(out, fps=fps, macro_block_size=8)
    i = 0
    while w.k < k_end and not w.done:
        while i < len(acts) and acts[i][0] == w.k:
            apply_inline(w.sides[acts[i][1]], acts[i][2]); i += 1
        w.advance()
        if w.k % every or (w.rs["state"] != "live" and w.k % (3 * every)):
            continue
        rd.set_state(w.snap())
        rd.r.update_scene(rd.d, camera=cam)
        im = Image.fromarray(rd.r.render())
        ImageDraw.Draw(im).text((10, 8), f"B (left) {w.score['B']} : {w.score['A']} A (right)   point {len(w.points) + 1}",
                                fill=(255, 255, 255))
        vw.append_data(np.asarray(im))
    vw.close()
