"""badminton: robot singles badminton in real time (docs/framework_zh.md §4.2). Migrated from the Season-1 tasks
badminton-match-wallclock-program-standard and badminton-duel-wallclock-program-standard (docs §10 stage 3). The four
groups of contract ②, on the unchanged legacy simulator (sim/bm.py, sim/bduel.py, sim/wc.py, sim/scene/):
  world + referee  format match-wallclock = bm.Match (seat A against the scripted opponent, levels 1-2, which plays
                   inside the world), format duel-wallclock = bduel.World (seats A and B, mirrored robots); the players
                   serve (BWF Law 9: the rally winner serves; the server tosses the shuttle with `toss`, then hits
                   it below 1.15 m, upwards, into the diagonal service court); step = one 10 ms control step (the
                   legacy services' rt_advance(1) / advance()); a point end freezes the world for the reviews
  actions          low = joint targets: `traj` (a list of 9 joint targets [base_x, base_y, q1..q7], one per control
                   step, followed exactly, then the robot returns to its ready pose and the base to its spot), `none`
                   and `toss` (the shuttle appears at a point, from rest or rising: the server's missing hand);
                   high = the legacy racket command `act` (the racket state at contact T s after the act takes
                   effect), planned in the seat's plan worker by the legacy stroke controller (bm.Match.plan_racket,
                   through the legacy wc.plan_on / bduel.plan_on) on an exact copy of the match (or of the seat's
                   robot) advanced to the act's effect step k0 = request step + lead (the legacy services' lead:
                   ceil(0.4 s / wall time per step)), and lowered to the SAME `traj` command with k0, the planner's
                   state key at k0 and the stroke's hit configuration; `toss` takes effect at k0 too (nothing to
                   plan); the episode holds only `traj`, `none` and `toss`
  referee          phase / scores / tiebreaks (disqualification, then the legacy winner chain in three rules)
  observation      observe = the legacy state (score, what was heard, the robot's own body, its command); camera_job =
                   the legacy 2 cameras x 4 frames (60 ms apart), drawn by the sport itself (the legacy scenes and
                   extra geometry) in the seat's render worker
"""
from __future__ import annotations

import copy
import hashlib
import itertools
import json
import math
import os
import struct
import sys
import time
import zlib

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SIM = os.path.join(HERE, "sim")
if SIM not in sys.path:
    sys.path.insert(0, SIM)
os.environ.pop("MATCH_SEED", None)          # bm.Match reads it at construction; the seed comes from the config only

import bduel as BD  # noqa: E402
import bm as BM  # noqa: E402
import wc as WC  # noqa: E402

from core.sport import FINISHED, PLAYING, UNIT_OVER, MatchBase, Phase, Refused  # noqa: E402

REVISION = "badminton-wallclock-5+duel-7+core-0.2"
SEATS2 = ("A", "B")
OPPONENT = "opponent"                       # the scripted opponent's side in format match-wallclock (no seat)
DT = BM.CONTROL_DT
PLAN_LEAD_S = 0.4                           # wall-time budget of an act's stroke planning (legacy WALLCLOCK_PLAN_LEAD_S)
T_MAX_S = 5.0
TRAJ_MAX = 600                              # joint targets in one low-level traj command
STROKE_KEYS = ("stroke", "base", "base_goal", "k_hit", "n_swing_steps_available", "n_swing_steps", "ik_residual",
               "blade_error_m", "normal_error_deg", "speed_scale", "racket_vel_delivered", "T_from_now")
VEL_LIM = BM.VEL_LIMIT * DT * (1 + 1e-6) + 1e-12
FOCAL_PX = 434.6                            # 45 degree vertical field of view on a 360 px tile
IMAGE_LAYOUT = ("2 rows x 4 columns of 480 x 360 tiles. Row 1: camera behind and above your base line looking down the "
                "court; row 2: camera at the side of the court (x < 0 in your frame) looking along +x: your half (y < 0) "
                "is on the right. Columns: four camera frames 60 ms apart, oldest left; each tile is stamped with its "
                "control step k and its time t since the shuttle shown was played (view_steps, view_times). The "
                "shuttle is drawn enlarged: an orange cork (12 cm ball centred on the shuttle's position) with a white "
                "skirt behind it, cork first along its flight. Yellow marks every 1 m along the outside of the singles "
                "side lines and behind the base lines.")
_TOKENS = itertools.count(1)


def lead_steps(slowdown) -> int:
    """Control steps from an act's request to its effect (the legacy services' LEAD_STEPS)."""
    period = DT * float(slowdown or 20)
    return max(1, int(math.ceil(PLAN_LEAD_S / period - 1e-9)))


def _clean(x):
    """JSON-exact python values (what the episode log holds and the replay reads back)."""
    return json.loads(json.dumps(x, default=lambda o: o.tolist() if hasattr(o, "tolist") else float(o)))


class Badminton(MatchBase):
    def __init__(self, cfg):
        self.cfg = cfg
        self.single = len(cfg.seats) == 1
        self.dt = DT
        self.token = next(_TOKENS)
        self.review_due = False
        self.review_hist = None                 # single: the finished point's last camera frames (display only)
        self.deferred = {s: None for s in cfg.seats}     # a lowered command waiting for its effect step k0
        self.rejected = {s: 0 for s in cfg.seats}
        self.mismatch = {s: 0 for s in cfg.seats}       # acts re-planned late or planned for another state
        self.level_ = None
        if self.single:
            self.level_ = 1 if cfg.level is None else int(cfg.level)
            if self.level_ not in BM.LEVELS:
                raise ValueError(f"opponent level must be one of {sorted(BM.LEVELS)}")
            self.g = BM.Match(self.level_, lv_override={"seed": int(cfg.seed)})
        else:
            self.first = cfg.first if cfg.first in SEATS2 else "A"
            self._ctx()
            self.g = BD.World()

    def _ctx(self):
        """bduel.py keeps the seed and the first server in module globals: set them for this match."""
        if not self.single:
            BD.SEED, BD.FIRST_SERVER = int(self.cfg.seed), self.first

    @property
    def k(self):
        return self.g.k

    # ------------------------------------------------------------------ robot access
    def robot(self, seat):
        """The object that owns the seat's robot and stroke state (bm.Match or bduel.Side)."""
        return self.g if self.single else self.g.sides[seat]

    def key(self, seat) -> str:
        """Everything the stroke planner reads, hashed (the legacy services' state key)."""
        return WC.state_key(self.g) if self.single else self.g.sides[seat].state_key()

    # ------------------------------------------------------------------ world + referee
    def step(self):
        self._ctx()
        for s in self.cfg.seats:               # A, then B (the legacy apply_due order)
            item = self.deferred[s]
            if item is not None and item["k0"] == self.g.k:
                self.deferred[s] = None
                if "rejected" in self._take_effect(s, item):
                    self.rejected[s] += 1
        g = self.g
        n0 = len(g.points)
        if self.single:
            pre = list(g.hist)
            g.rt_advance(1)
            if g.hist and g.hist[-1]["k"] == g.k and "leg_id" not in g.hist[-1]:
                g.hist[-1]["leg_id"] = len(g.legs) - 1          # display only (the legacy _frame_extras)
                g.hist[-1]["wall_mono"] = time.monotonic()
        else:
            g.advance()
        if len(g.points) > n0:
            self.deferred = {s: None for s in self.cfg.seats}   # no command carries over to the next point
            if self.single:
                self.review_hist = pre or None
            if not g.done:
                self.review_due = True
            return [{"kind": "point", **_clean(g.points[-1])}]
        return []

    def state_digest(self):
        if not self.single:
            return self.g.state_sha()
        g = self.g                              # the robot and shuttle state + the referee's record
        rec = json.dumps({"score": list(g.score), "points": g.points}, sort_keys=True, default=float)
        return hashlib.sha256((g.s.state_sha() + rec).encode()).hexdigest()

    def capped(self):
        return bool(self.g.points and self.g.points[-1].get("cap"))

    def phase(self):
        if self.g.done:
            return Phase(FINISHED, reason="disqualified" if self.g.disqualified else
                         "match_limit" if self.capped() else "match_over")
        if self.review_due:
            return Phase(UNIT_OVER, review=tuple(self.cfg.seats), reason=self.g.points[-1]["how"])
        return Phase(PLAYING)

    def resume(self):
        self.review_due = False

    def unit(self):
        return len(self.g.points)

    def sides(self):
        return [self.cfg.seats[0], OPPONENT] if self.single else list(SEATS2)

    def scores(self):
        if self.single:
            return {self.cfg.seats[0]: int(self.g.score[0]), OPPONENT: int(self.g.score[1])}
        return {s: int(self.g.score[s]) for s in SEATS2}

    def tiebreaks(self):
        """The winner chain as three rules: the score (first to 5, from 4-4 by 2, at most 7; at the match limit the
        player ahead), else the winner of the last point that was not a let, else (last resort, not from the
        rulebook) the player who received first (format match-wallclock: the opponent, since you serve first)."""
        def score(m):
            sc = m.scores()
            a, b = m.sides()
            return None if sc[a] == sc[b] else (a if sc[a] > sc[b] else b)

        def last_point(m):
            names = {"you": m.sides()[0], "opponent": OPPONENT} if m.single else {s: s for s in SEATS2}
            won = [names[p["winner"]] for p in m.g.points if p.get("winner") in names]
            return won[-1] if won else None

        def first_receiver(m):
            return OPPONENT if m.single else BD.OTHER[m.first]

        def disqualification(m):                # Law 16.7: the third undue-delay fault disqualifies a player
            if m.single:
                return OPPONENT if m.g.disqualified else None
            return BD.OTHER[m.g.disqualified] if m.g.disqualified else None
        return [("disqualification", disqualification), ("score", score), ("last_point", last_point),
                ("first_receiver", first_receiver)]

    def forfeit(self, seat, why):
        return False                            # the core decides a forfeit; the world is left as it was

    # ------------------------------------------------------------------ actions (low level)
    def schema(self, seat):
        return LOW_SCHEMA

    def apply(self, seat, cmd):
        self._ctx()
        typ = cmd.get("type")
        if typ not in ("traj", "none", "toss"):
            return {"rejected": f"unknown command {typ!r}"}
        k0 = cmd.get("k0")
        if k0 is None or k0 == self.g.k:
            return self._take_effect(seat, cmd)
        if k0 < self.g.k:
            return {"rejected": f"late: planned to take effect at step {k0}, now {self.g.k}"}
        self.deferred[seat] = dict(cmd)
        return {"effect_step": int(k0)}

    def _take_effect(self, seat, cmd):
        """A command takes effect: `toss` puts the shuttle at the given point, from rest or rising (height) (the server only, in its
        serve window; refused with no change otherwise); `none` cancels the stroke (the legacy rt_clear); a `traj`
        replaces the stroke under way with exactly the attribute changes of the legacy install (wc.install /
        bduel.install). A traj is refused (no change) if it breaks a joint range or speed limit, or if the state it was
        planned for (its key) is not the live one at its effect step."""
        if cmd["type"] == "toss":
            try:
                if self.single:
                    self.g.toss(cmd["pos"], cmd.get("height", 0.0))
                else:
                    self.g.toss(seat, cmd["pos"], cmd.get("height", 0.0))
            except ValueError as e:
                return {"rejected": f"serve: {e}"}
            return {"tossed_step": int(self.g.k)}
        if cmd["type"] == "none":
            if self.single:
                WC.install(self.g, {"type": "none"})
            else:
                BD.install(self.g.sides[seat], {"type": "none"})
            return {"command": "cleared: the robot returns to the ready pose, the base home"}
        key = cmd.get("key")
        if key is not None and key != self.key(seat):
            self.mismatch[seat] += 1
            return {"rejected": "the robot's state at the effect step differs from the planned one"}
        rob = self.robot(seat)
        cur = np.asarray(rob.s.target, np.float64)
        q = np.asarray(cmd.get("q") or np.zeros((0, 9)), np.float64).reshape(-1, 9)
        lo, hi = rob.s.lo, rob.s.hi
        prev = cur
        for i, qi in enumerate(q):
            if not np.all(np.isfinite(qi)) or (qi < lo - 1e-9).any() or (qi > hi + 1e-9).any():
                return {"rejected": f"joint target {i} outside the joint ranges"}
            if (np.abs(qi - prev) > VEL_LIM).any():
                return {"rejected": f"joint target {i} breaks a joint speed limit"}
            prev = qi
        if (cmd.get("info") or {}).get("replanned_late_steps"):
            self.mismatch[seat] += 1
        q_hit = cmd.get("q_hit")
        res = {"type": "act", "plan": [x.copy() for x in q], "info": copy.deepcopy(cmd.get("info") or {}),
               "q_hit": None if q_hit is None else np.asarray(q_hit, np.float64), "ik_seed": None,
               "swing_last": None}
        if self.single:
            WC.install(self.g, res)
        else:
            BD.install(self.g.sides[seat], res)
        return {"took_effect_step": int(self.g.k), "n_targets": int(len(q))}

    # ------------------------------------------------------------------ the serve
    def serve_state(self, seat) -> dict:
        """The current point's serve as the seat sees it: whether it serves, the phase (ready: the receiver is getting
        waiting: the receiver is getting ready; open: the server may toss; tossed; done: the serve was delivered), the
        steps that bound it, its base (docs/conventions/racket_serve_zh.md)."""
        g = self.g
        if self.single:
            leg = g.leg
            first = next(x for x in reversed(g.legs) if x["kind"] in ("serve", "our_serve") and x["point"] == leg["point"])
            server = first["kind"] == "our_serve"
            right = first["service_court_right"]
            if server:
                ready, deadline, rel = first["ready"], first["deadline"], first.get("toss_k")
                phase = ("waiting" if first["state"] == "held" and g.k < ready else "open" if first["state"] == "held"
                         else "tossed" if first["state"] == "falling" else "done")
            else:
                ready = deadline = rel = first["launch"]
                phase = "waiting" if g.k < ready else "done"
            base = g.s.d.qpos[g.s.qa[:2]]
        else:
            rs = g.rs
            server = rs["server"] == seat
            right, ready, deadline, rel = rs["service_court_right"], rs["ready"], rs["deadline"], rs["toss_k"]
            phase = {"ready": "waiting", "to_serve": "open", "tossed": "tossed"}.get(rs["state"], "done")
            ph = g.sides[seat].s
            base = ph.d.qpos[ph.qa[:2]]
        return {"server": server, "right": right, "phase": phase, "ready_k": ready, "deadline_k": deadline,
                "toss_k": rel, "base": np.asarray(base, float).copy()}

    def serve_refusal(self, seat, k_eff, pos, height):
        """Why a toss (at `pos`, rising `height`, effective at step k_eff) is refused now: (message, HTTP code) or None."""
        sv = self.serve_state(seat)
        if self.g.done or not sv["server"]:
            return "it is not your serve", 409
        if sv["phase"] not in ("waiting", "open"):
            return "the shuttle was already tossed (one toss per serve)", 409
        why = BM.toss_problem(pos, height, sv["base"])
        if why:
            return why, 400
        if k_eff < sv["ready_k"]:
            return (f"the receiver is ready at step {sv['ready_k']}: the toss would take effect at step {k_eff}; "
                    "send it so that it takes effect then or later (state.serve_in_s)"), 409
        return None

    def _serve_obs(self, seat):
        g, sv = self.g, self.serve_state(seat)
        o = {"court": "right" if sv["right"] else "left", "phase": sv["phase"]}
        if sv["phase"] in ("waiting", "open") and sv["server"]:
            o["opens_in_s"] = round(max(0.0, (sv["ready_k"] - g.k) * DT), 3)
            o["deadline_in_s"] = round(max(0.0, (sv["deadline_k"] - g.k) * DT), 3)
        if sv["toss_k"] is not None and sv["phase"] in ("tossed", "done"):
            o["tossed_at_step"] = int(sv["toss_k"])
        return {"you_serve": sv["server"], "you_receive_serve": not sv["server"], "serve": o,
                "serve_in_s": round(max(0.0, (sv["ready_k"] - g.k) * DT), 3) if sv["phase"] in ("waiting", "open")
                else None}

    # ------------------------------------------------------------------ observation
    def observe(self, seat, query=None):
        g = self.g
        if self.single:
            o = self._single_state()
            leg = g.leg
            o.update(self._serve_obs(seat))
            if leg["kind"] == "our_serve" and leg["state"] in ("held", "falling"):
                o["ball_in_play"] = leg["state"] == "falling"
                o["ball_state"] = "not yet served" if leg["state"] == "held" else "tossed: yours to hit (your serve)"
                o["t_since_played"] = None if leg["state"] == "held" else g.t_since_launch()
                o["heard"] = [] if leg["state"] == "held" else [{"event": "you tossed the shuttle", "t": 0.0}]
            elif not g.in_play():
                o["ball_in_play"] = False
                o["ball_state"] = "not yet served"
                o["heard"] = []
                o["t_since_played"] = None
            else:
                o["ball_in_play"] = leg["state"] in ("incoming", "to_opp")
                o["ball_state"] = {"incoming": "coming to you", "to_opp": "going to the opponent",
                                   "done": "dead"}.get(leg["state"], leg["state"])
                if leg["state"] == "to_opp":
                    o["heard"] = o["heard"] + [{"event": "you served" if leg["kind"] == "our_serve" else
                                                "you hit the shuttle",
                                                "t": round((leg["hit"]["k"] - leg["launch"]) * DT, 3)
                                                if "k" in leg.get("hit", {}) else None}]
            o["last_points"] = [{k: p[k] for k in ("point", "winner", "how", "score")} for p in g.points[-3:]]
            o["last_shots"] = [{k: r.get(k) for k in ("returned", "summary", "speed_out")} for r in g.results[-3:]]
            o["opponent_level"] = self.level_
        else:
            o = self._duel_state(seat)
        rob = self.robot(seat)
        la, active = rob._last_act, rob.plan_j < len(rob.plan)
        k_hit = la.get("k_hit") if la else None
        o["command"] = ({"contact_in_s": round((k_hit - g.k) * DT, 3) if k_hit is not None and k_hit >= g.k
                         else "passed",
                         "phase": "approach" if k_hit is not None and g.k < k_hit else "follow_through",
                         "pos": la.get("racket_pos"), "normal": la.get("racket_normal"), "vel": la.get("racket_vel"),
                         "stroke": la.get("stroke")}
                        if active and la else
                        {"traj_steps_left": len(rob.plan) - rob.plan_j} if active else
                        "none (the robot returns to / holds the ready pose, the base to its spot)")
        it = self.deferred[seat]
        if it is not None:
            o["pending_commands"] = [{"type": {"traj": "act"}.get(it["type"], it["type"]),
                                      "takes_effect_at_step": int(it["k0"])}]
        if self.cfg.action_level == "low":
            o["q_target"] = [float(x) for x in rob.s.target]
        return o

    def _single_state(self):
        """bm.Match.decision_observation() without view_times (the frames' times come with the images)."""
        g = self.g
        ph, leg = g.s, g.leg
        heard = [{"event": "the opponent served" if leg["kind"] == "serve" else "the opponent hit the shuttle",
                  "t": 0.0}] if leg["kind"] in ("serve", "return") else []
        c, n, _ = ph.racket_state()
        return {"score": {"you": g.score[0], "opponent": g.score[1]}, "point": len(g.points) + 1,
                "ball": {"serve": "serve", "our_serve": "your serve"}.get(leg["kind"], "opponent's return"),
                "t_since_played": g.t_since_launch(), "heard": heard,
                "robot_base_xy": [round(float(x), 3) for x in ph.d.qpos[ph.qa[:2]]],
                "q_arm": [round(float(x), 4) for x in ph.d.qpos[ph.qa[2:]]],
                "racket_pos": [round(float(x), 3) for x in c], "racket_normal": [round(float(x), 3) for x in n]}

    def _duel_state(self, side):
        """The duel's state(side), without the core's fields (phase, world, step, ready ...)."""
        w = self.g
        rs, other, me = w.rs, BD.OTHER[side], w.sides[side]
        ph = me.s
        c, n, _ = ph.racket_state()
        st = rs["state"]
        server = rs["server"] == side
        if st in ("ready", "to_serve"):
            ball = "not yet served"
        elif st == "tossed":
            ball = "tossed: yours to hit (your serve)" if server else "the opponent tossed the shuttle (serving)"
        elif st == "live":
            ball = "coming to you" if rs["expect"] == side else "going to the opponent"
        else:
            ball = "dead"
        heard = []
        for e in w.events:
            if e["kind"] == "toss":
                heard.append({"event": "you tossed the shuttle" if e["side"] == side else
                              "the opponent tossed the shuttle", "t": round((e["k"] - rs["ready"]) * DT, 3)})
            elif e["kind"] == "hit":
                first = e["k"] == (rs["serve"] or {}).get("hit_k")
                what = ("served" if first else "hit the shuttle")
                heard.append({"event": f"you {what}" if e["side"] == side else f"the opponent {what}",
                              "t": round((e["k"] - rs["ready"]) * DT, 3)})
        o = {"point": rs["point"] + 1, "score": {"you": w.score[side], "opponent": w.score[other]},
             "ball_state": ball, "ball_in_play": st in ("tossed", "live"),
             "t_since_played": round((w.k - rs["played_k"]) * DT, 3) if st in ("tossed", "live", "over") else None,
             "heard": heard, "robot_base_xy": [round(float(x), 3) for x in ph.d.qpos[ph.qa[:2]]],
             "q_arm": [round(float(x), 4) for x in ph.d.qpos[ph.qa[2:]]],
             "racket_pos": [round(float(x), 3) for x in c], "racket_normal": [round(float(x), 3) for x in n],
             "last_points": [{"point": p["point"], "how": p["how"], "let": p["let"],
                              "winner": "let" if p["winner"] is None else ("you" if p["winner"] == side else
                                                                           "opponent"),
                              "server": "you" if p["server"] == side else "opponent",
                              "score": {"you": p["score"][side], "opponent": p["score"][other]}}
                             for p in w.points[-3:]]}
        o.update(self._serve_obs(side))
        return o

    def _snaps(self):
        """The 4 camera frames 60 ms apart ending at the newest one; during a review the finished point's last frames.
        Before the first frame of a point: the current state (not stored: observing changes nothing)."""
        g = self.g
        if self.single:
            hist = list(self.review_hist if (self.review_due and self.review_hist) else g.hist)
            if not hist:
                hist = [{"k": g.k, "t": g.t_since_launch(), "qpos": g.s.d.qpos.copy(), "sh": g.s.sh_p,
                         "shv": g.s.sh_v, "opp": g.opp_xy().copy(), "leg_id": len(g.legs) - 1}]
        else:
            hist = list(g.review_hist or []) if (self.review_due and g.review_hist) else list(g.hist)
            if not hist:
                hist = [g.snap()]
        return [hist[max(0, len(hist) - 1 - b)] for b in reversed(BM.Match.VIEW_BACK)]

    def camera_job(self, seat):
        snaps = self._snaps()
        if self.single:
            frames = [{"qpos": np.asarray(s["qpos"], np.float64).copy(), "sh": tuple(float(x) for x in s["sh"]),
                       "shv": tuple(float(x) for x in s["shv"]), "opp": [float(x) for x in s["opp"]],
                       "k": int(s["k"]), "t": float(s["t"])} for s in snaps]
            times = [round(float(s["t"]), 3) for s in snaps]
            legs = [s.get("leg_id") for s in snaps]
        else:
            frames = [{"qA": np.asarray(s["qA"], np.float64).copy(), "qB": np.asarray(s["qB"], np.float64).copy(),
                       "sh": tuple(float(x) for x in s["sh"]), "shv": tuple(float(x) for x in s["shv"]),
                       "k": int(s["k"]), "played_k": int(s["played_k"])} for s in snaps]
            times = [round((s["k"] - s["played_k"]) * DT, 3) for s in snaps]
            legs = [s.get("flight") for s in snaps]
        job = {"single": self.single, "side": "A" if self.single else seat, "snaps": frames}
        meta = {"view_times": times, "view_steps": [int(s["k"]) for s in snaps], "view_leg_ids": legs,
                "view_sim_times": [round(s["k"] * DT, 4) for s in snaps], "image_layout": IMAGE_LAYOUT,
                "wall_mono": snaps[-1].get("wall_mono", time.monotonic())}
        return job, meta

    def final_fields(self):
        g = self.g
        lead = lead_steps(self.cfg.slowdown)
        if self.single:
            a = self.cfg.seats[0]
            return {"level": self.level_, "points_for": int(g.score[0]), "points_against": int(g.score[1]),
                    "win_points": BM.WIN_POINTS, "won": bool(g.done and g.winner == 0),
                    "returns": int(sum(r["returned"] for r in g.results)), "our_legs": int(g.n_our_legs),
                    "match_limit": self.capped(), "hits": int(g.hits),
                    "lets": sum(1 for p in g.points if p.get("let")), "points": _clean(g.points),
                    "results": _clean(g.results), "shots": _clean(g.shots), "physics_steps": int(g.s.steps_total),
                    "opponent": _clean([x.get("opp") for x in g.legs if x.get("opp")]),
                    "serves": [{"server": "opponent", "type": x.get("serve")} if x["kind"] == "serve" else
                               {"server": "you", "toss": x.get("toss"), "toss_k": x.get("toss_k"),
                                "contact_z": (x.get("hit") or {}).get("pos", [None] * 3)[2],
                                "speed": (x.get("hit") or {}).get("speed")}
                               for x in g.legs if x.get("kind") in ("serve", "our_serve")],
                    "plan_lead_steps": lead, "rejected_acts": dict(self.rejected), "plan_mismatch": dict(self.mismatch),
                    "seats": {a: {"rejected_acts": self.rejected[a]}}}
        return {"score": dict(g.score), "points": _clean(g.points), "hits": int(g.hits), "match_limit": self.capped(),
                "first_server": self.first, "lead_steps": lead, "rejected_acts": dict(self.rejected),
                "plan_mismatch": dict(self.mismatch),
                "seats": {s: {"rejected_acts": self.rejected[s]} for s in SEATS2}}


# ---------------------------------------------------------------------------------------------- action layers
NUM = {"type": "number"}
VEC3 = {"type": "vector", "len": 3}
NONE = {"none": {}}
SERVE = {"toss": {"pos": {**VEC3, "unit": "m",
                          "doc": f"your serve's toss (docs/conventions/racket_serve_zh.md): the shuttle appears at this "
                                 f"point (your frame) when the command takes effect; {BM.TOSS_Z[0]} <= z <= "
                                 f"{BM.TOSS_Z[1]}, within {BM.TOSS_REACH} m (horizontally) of your base, y <= -0.5; "
                                 "only the server, once per serve, from the step the receiver is ready (state.serve)"},
                  "height": {**NUM, "min": 0.0, "max": BM.TOSS_H_MAX, "unit": "m", "optional": True,
                             "doc": f"how far it rises straight up from pos (0 <= height <= {BM.TOSS_H_MAX}; default "
                                    "0: released from rest)"}}}
HIGH_SCHEMA = {
    "act": {"t": {**NUM, "min": 0.0, "max": T_MAX_S, "unit": "s",
                  "doc": "contact T s after the act takes effect (0 < T <= 5)"},
            "pos": {**VEC3, "unit": "m", "doc": "racket-head centre at contact: |x| <= 3.4, -7.5 <= y <= -0.3, "
                                                "0.2 <= z <= 3.0"},
            "normal": {**VEC3, "doc": "string-face normal at contact (non-zero)"},
            "vel": {**VEC3, "unit": "m/s", "doc": "racket-head velocity at contact, |vel| <= 8"}},
    **SERVE, **NONE}
LOW_SCHEMA = {
    "traj": {"q": {"type": "list", "doc": f"1-{TRAJ_MAX} joint-target vectors [base_x, base_y, q1..q7], one per 10 ms "
                                          "control step from the next step on, followed exactly (then the robot returns "
                                          "to its ready pose, the base home); each within the joint ranges and the "
                                          "joint speed limits"}},
    **SERVE, **NONE}


def _vec(body, key, n):
    v = body.get(key)
    if not isinstance(v, (list, tuple)) or len(v) != n:
        raise Refused(f"{key} must be a list of {n} numbers")
    out = []
    for x in v:
        if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
            raise Refused(f"{key} must hold {n} finite numbers")
        out.append(float(x))
    return out


def _common(seat, body, match, allowed, lead=0):
    if not isinstance(body, dict):
        raise Refused("the action must be a JSON object")
    typ = body.get("type")
    if typ not in allowed:
        raise Refused(f"unknown action type {typ!r}; one of {sorted(allowed)}")
    extra = sorted(set(body) - set(allowed[typ]) - {"type"})
    if extra:
        raise Refused(f"unknown field(s) {extra} for {typ}")
    item = match.deferred.get(seat)
    if item is not None and item["k0"] > match.k:
        raise Refused(f"your previous act takes effect at step {item['k0']}; send the next command after that", 409)
    if typ == "none":
        return {"type": "none"}
    if typ == "toss":
        rel = _vec(body, "pos", 3)
        h = body.get("height", 0.0)
        if isinstance(h, bool) or not isinstance(h, (int, float)) or not math.isfinite(h):
            raise Refused("height must be a finite number (0: released from rest)")
        bad = match.serve_refusal(seat, match.k + lead, rel, float(h))
        if bad:
            raise Refused(f"toss refused: {bad[0]}", bad[1])
        return {"type": "toss", "pos": rel, "height": float(h)}
    return None


class LowLayer:
    """Low level: joint targets (traj), none and toss, effective at the next control step."""
    level = "low"
    worker = None
    delay_steps = 0

    def schema(self, match, seat):
        return LOW_SCHEMA

    def parse(self, seat, body, match, ctx):
        out = _common(seat, body, match, LOW_SCHEMA)
        if out is not None:
            return out
        q = body.get("q")
        if not isinstance(q, list) or not 1 <= len(q) <= TRAJ_MAX:
            raise Refused(f"q must be a list of 1 to {TRAJ_MAX} joint-target vectors")
        return {"type": "traj", "k0": None, "q": [_vec({"q": r}, "q", 9) for r in q]}

    def snapshot(self, seat, cmd, match, ordinal):
        return None

    def prepare(self, job):
        return None

    def lower(self, seat, cmd, prepared, match):
        return cmd, {}

    def reply(self, seat, cmd, info, match):
        return info


def plan_job(job, model) -> dict:
    """The legacy planner (wc._worker / the duel's workers.plan): restore the exact copy taken at the request step,
    advance it to the effect step k0 = request step + lead with the command in force, and plan the act there
    (wc.plan_on / bduel.plan_on: what Match.rt_act at k0 would do). Single: if the point ends on the way, the act
    is dropped (as in the legacy planner)."""
    k0 = int(job["k_req"]) + int(job["lead"])
    out = {"k_effect": k0, "status": "ok"}
    if job.get("none"):
        return out
    t0 = time.monotonic()
    if job["single"]:
        m = WC.restore(job["snap"], model)
        while m.k < k0:
            n0 = len(m.points)
            m.rt_advance(1)
            if len(m.points) > n0 or m.done:
                out["status"] = "dropped"
                return out
        out["key"] = WC.state_key(m)
        res = WC.plan_on(m, job["dec"])
    else:
        side = BD.restore(job["snap"], model)
        while side.k < k0:
            side.solo_step()
        out["key"] = side.state_key()
        res = BD.plan_on(side, job["dec"])
    out.update(plan=[np.asarray(q, np.float64) for q in res["plan"]],
               q_hit=None if res["q_hit"] is None else np.asarray(res["q_hit"], np.float64), info=res["info"],
               plan_s=time.monotonic() - t0)
    return out


class PlanCtx:
    """The seat's plan worker: the MjModel the snapshots are restored with."""

    def __init__(self):
        self.model = BM.Phys().m

    def plan(self, job):
        return plan_job(job, self.model)


class RacketLayer(LowLayer):
    """High level: the legacy racket command. `act` (and `none`) take effect `lead` control steps after the step at
    which the request arrives (the legacy act lead); an act is planned in the seat's plan worker from a snapshot of
    that step and lowered to a low-level traj with its effect step."""
    level = "high"
    worker = "plan"

    def __init__(self, lead):
        self.lead = lead
        self.ctx = None                         # an in-process planner for a late act (see lower)

    def schema(self, match, seat):
        return HIGH_SCHEMA

    def parse(self, seat, body, match, ctx):
        out = _common(seat, body, match, HIGH_SCHEMA, self.lead)
        if out is not None:
            return out
        T = body.get("t")
        if isinstance(T, bool) or not isinstance(T, (int, float)) or not math.isfinite(T):
            raise Refused("t must be a finite number")
        pos, nrm, vel = _vec(body, "pos", 3), _vec(body, "normal", 3), _vec(body, "vel", 3)
        if np.linalg.norm(nrm) < 1e-6:
            raise Refused("normal must be a non-zero vector")
        if not 0.0 < T <= T_MAX_S:
            raise Refused(f"t must be in (0, {T_MAX_S}] s from when the act takes effect")
        if not (abs(pos[0]) <= 3.4 and -7.5 <= pos[1] <= -0.3 and 0.2 <= pos[2] <= 3.0):
            raise Refused("pos out of range: |x| <= 3.4, -7.5 <= y <= -0.3, 0.2 <= z <= 3.0")
        if np.linalg.norm(vel) > 8.0:
            raise Refused("vel too large: |vel| <= 8 m/s")
        return {"type": "act", "t": float(T), "pos": pos, "normal": nrm, "vel": vel}

    def snapshot(self, seat, cmd, match, ordinal):
        job = {"single": match.single, "k_req": int(match.k), "lead": self.lead}
        if cmd["type"] in ("none", "toss"):     # nothing to plan: takes effect `lead` steps after the request
            return dict(job, none=True)
        match._ctx()
        snap = WC.snapshot(match.g) if match.single else BD.snapshot(match.g.sides[seat])
        return dict(job, snap=snap, dec=cmd)

    def prepare(self, job):
        if job.get("none"):
            return plan_job(job, None)
        if self.ctx is None:
            self.ctx = PlanCtx()
        return self.ctx.plan(job)

    def lower(self, seat, cmd, prepared, match):
        k0 = int(prepared["k_effect"])
        if cmd["type"] == "none":
            return {"type": "none", "k0": k0}, {"effect_step": k0}
        if cmd["type"] == "toss":
            return {"type": "toss", "k0": max(k0, int(match.k)), "pos": cmd["pos"], "height": cmd["height"]}, \
                {"effect_step": k0}
        late = match.k - k0
        if late > 0 and prepared.get("status") == "ok" and cmd["t"] - late * DT > 0:
            # the plan worker missed the effect step (the legacy service stalled the world until the plan came): plan
            # again here, from the state now, for an effect now and the same contact time (the world waits)
            d = dict(cmd, t=round(cmd["t"] - late * DT, 6))
            job = dict(self.snapshot(seat, d, match, 0), lead=0)
            prepared = self.prepare(job)
            prepared["info"]["replanned_late_steps"] = late
            k0 = int(prepared["k_effect"])
        if prepared.get("status") != "ok":     # the point ends before the effect step: nothing to install
            return {"type": "traj", "k0": k0, "q": [], "key": "dropped: the point ends before the effect step"}, \
                {"effect_step": k0, "stroke": {"stroke": "dropped: the point ends before the act takes effect"}}
        info = _clean({k: v for k, v in prepared["info"].items() if k in STROKE_KEYS + ("replanned_late_steps",)})
        low = _clean({"type": "traj", "k0": k0, "q": prepared["plan"], "q_hit": prepared["q_hit"],
                      "key": prepared["key"], "info": prepared["info"]})
        return low, {"stroke": info, "effect_step": k0}

    def reply(self, seat, cmd, info, match):
        return info


# ---------------------------------------------------------------------------------------------- render
def _players_model(live, scene_file):
    """The model the cameras draw: the players' presentation scene (presentation/presentation.toml `players`: the
    Franka Panda's visual meshes on the same bodies, renderer rule 6; same kinematics, checked) with the live model's
    marker settings, else the live model itself."""
    from renderers import Scene, players_model
    fine = players_model(HERE, Scene.from_file(scene_file))
    if fine is None:
        return live
    if fine.nsite == live.nsite:
        fine.site_pos[:], fine.site_size[:], fine.site_rgba[:] = live.site_pos, live.site_size, live.site_rgba
    return fine


class Views:
    """The legacy observation images: 2 cameras x 4 frames, each tile stamped `k=.. t=..`, one PNG. Tiles are cached by
    their content, so a frame shown in several observations is drawn once (same pixels). Since revision wallclock-5 /
    duel-7 the arms are drawn with the players' presentation scene (the Franka Panda's 25k visual meshes)."""

    def __init__(self, single, side):
        import mujoco as mj
        self.mj, self.single = mj, single
        if single:
            self.m = _players_model(mj.MjModel.from_xml_path(str(BM.SCENE)), BM.SCENE)
            w, h = BM.Match.TILE
            self.r = mj.Renderer(self.m, height=h, width=w)
            self.rd = mj.MjData(self.m)
            self.cams = []
            for lookat, dist, az, el in BM.Match.CAMS:
                c = mj.MjvCamera()
                c.lookat[:] = lookat
                c.distance, c.azimuth, c.elevation = dist, az, el
                self.cams.append(c)
        else:
            self.dr = dr = BD.Renderer(side)   # the legacy duel renderer: both robots, the side's own cameras
            fine = _players_model(dr.m, BD.SCENE2)
            if fine is not dr.m:               # the same joints and qpos addresses (kinematics checked identical)
                h, w = dr.r.height, dr.r.width
                dr.r.close()
                dr.m, dr.d = fine, mj.MjData(fine)
                dr.r = mj.Renderer(fine, height=h, width=w)
            self.cams = self.dr.cams
        self.cache: dict = {}

    def tile(self, ci, sn):
        from PIL import Image, ImageDraw
        mj = self.mj
        if self.single:
            rd = self.rd
            rd.qpos[:] = sn["qpos"]
            rd.mocap_pos[0] = sn["sh"]
            v = np.asarray(sn["shv"], float)
            if np.linalg.norm(v) < 1e-6:
                v = np.array([0.0, 0.0, -1.0])
            rd.mocap_quat[0] = BM.quat_z_to(v)
            mj.mj_kinematics(self.m, rd)
            self.r.update_scene(rd, camera=self.cams[ci])
            BM.Match._extra_geoms(self.r.scene, np.asarray(sn["opp"], float), sn["sh"])
            im = Image.fromarray(self.r.render())
            ImageDraw.Draw(im).text((6, 4), f"k={sn['k']} t={sn['t']:.2f}s", fill=(255, 255, 255))
        else:
            dr = self.dr
            dr.set_state(sn)
            dr.r.update_scene(dr.d, camera=self.cams[ci])
            im = Image.fromarray(dr.r.render())
            t = (sn["k"] - sn["played_k"]) * DT
            ImageDraw.Draw(im).text((6, 4), f"k={sn['k']} t={t:.2f}s", fill=(255, 255, 255))
        return np.asarray(im)

    @staticmethod
    def content_key(ci, sn):
        h = hashlib.sha1()
        for name in sorted(sn):
            v = sn[name]
            h.update(name.encode())
            h.update(np.ascontiguousarray(v, np.float64).tobytes() if isinstance(v, (np.ndarray, list, tuple))
                     else repr(v).encode())
        return ci, h.hexdigest()

    def draw(self, job):
        rows = []
        for ci in range(len(self.cams)):
            tiles = []
            for sn in job["snaps"]:
                key = self.content_key(ci, sn)
                if key not in self.cache:
                    self.cache[key] = self.tile(ci, sn)
                tiles.append(self.cache[key])
            rows.append(np.concatenate(tiles, axis=1))
        if len(self.cache) > 64:
            for key in list(self.cache)[:len(self.cache) - 48]:
                del self.cache[key]
        return png(np.concatenate(rows, axis=0))


def png(img: np.ndarray) -> bytes:
    """RGB8 PNG without row filters, zlib level 1 (the same pixels as the legacy imageio PNG, about 3x faster)."""
    h, w = img.shape[:2]
    raw = np.zeros((h, w * 3 + 1), np.uint8)
    raw[:, 1:] = np.ascontiguousarray(img[..., :3], np.uint8).reshape(h, -1)

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw.tobytes(), 1)) + chunk(b"IEND", b""))


_LOCAL_VIEWS: dict = {}


class BadmintonSport:
    name = "badminton"
    protocol = "realtime"
    revision = REVISION
    source_dirs = [HERE]
    workers = ("plan", "render")

    def __init__(self):
        self._lead = lead_steps(None)

    def build(self, cfg):
        self._lead = lead_steps(cfg.slowdown)   # the core asks for the action layer right after build()
        return Badminton(cfg)

    def action_layer(self, level):
        return RacketLayer(self._lead) if level == "high" else LowLayer()

    def worker_init(self, kind, seat, cfg):
        if kind == "plan":
            return PlanCtx()
        return Views(len(cfg.seats) == 1, seat if len(cfg.seats) > 1 else "A")

    def worker_call(self, obj, kind, job):
        if kind == "plan":
            if obj is None:
                obj = PlanCtx()
            return obj.plan(job)
        if obj is None:                         # in-process (core/local.py): one renderer per (format, side)
            key = (job["single"], job["side"])
            if key not in _LOCAL_VIEWS:
                _LOCAL_VIEWS[key] = Views(*key)
            obj = _LOCAL_VIEWS[key]
        return {"png": obj.draw(job)}

    def spec(self, cfg, seat, m):
        lead = lead_steps(cfg.slowdown)
        single = len(cfg.seats) == 1
        out = {
            "robot": ("franka-panda on a 1.0 m pedestal, base on x-y rails (<= 6 m/s, <= 20 m/s^2) + badminton racket "
                      f"(head centre 0.56 m beyond the flange, string bed radius {BM.R_HEAD} m)"),
            "base": {"max_speed_mps": BM.BASE_VMAX, "max_accel_mps2": BM.BASE_AMAX, "home_xy": [float(x) for x in BM.HOME],
                     "range": {"x": [float(BM.BASE_LO[0]), float(BM.BASE_HI[0])],
                               "y": [float(BM.BASE_LO[1]), float(BM.BASE_HI[1])]}},
            "frame": ("your own: x to your right, y towards the opponent, z up; your half y < 0, your base's home "
                      f"{[float(x) for x in BM.HOME]}" + ("" if single else "; the opponent's robot plays from y > 0 (in "
                                                                          "its own frame it sees the game as you do)")),
            "match": {"win_points": BM.WIN_POINTS, "two_point_lead_from": BM.WIN_POINTS - 1,
                      "cap_points": BM.CAP_POINTS, "max_hits": BM.MAX_HITS, "max_points_played": BM.MAX_POINTS,
                      "scoring": "rally point",
                      **({"opponent_level": m.level_, "first_player": seat, "first_server": seat,
                          "serves": "you serve the first point; then the winner of each rally serves the next point "
                                    "(a let: the same server); the opponent serves like you, by the rules"} if single else
                         {"first_player": m.first, "first_server": m.first, "first_server_is_you": m.first == seat,
                          "serves": "match.first_server serves the first point; then the winner of each rally serves "
                                    "the next point (a let: the same server)"})},
            "serve": {"spot_right_court_xy": [float(x) for x in BM.serve_spot(True)],
                      "spot_left_court_xy": [float(x) for x in BM.serve_spot(False)],
                      "courts": "both robots stand in their right service courts when the server's score is even, else "
                                "in their left ones (diagonally opposite); the spot is your base's home for the point",
                      "base_tolerance_m": BM.BASE_TOL, "ready_s": round(BD.READY_STEPS * DT, 3),
                      "window_s": round(BM.SERVE_WINDOW_STEPS * DT, 3), "toss_z_m": list(BM.TOSS_Z),
                      "toss_reach_m": BM.TOSS_REACH, "toss_height_m": [0.0, BM.TOSS_H_MAX], "max_contact_z_m": BM.SERVE_MAX_Z,
                      "command": "{'type': 'toss', 'pos': [x, y, z], 'height': H}: the shuttle appears at the point "
                                 "when the command takes effect (the same lead as an act) and rises H straight up "
                                 "(0 <= H <= 0.5; 0 or omitted: released from rest); then hit it with an act (it may "
                                 "be sent before the toss)",
                      "phases": "serve.phase: waiting (the receiver is getting ready), open (toss now), tossed, done",
                      "faults": "serve faults are recorded as 'serve_fault:<reason>: ...' (reasons: undue_delay, "
                                "missed, too_high, not_upwards, net, out, moved); the receiver's base moving early: "
                                "'receive_fault:moved: ...'"},
            "act": {"lead_steps": lead, "lead_game_s": round(lead * DT, 4), "T_max_s": T_MAX_S,
                    "rule": (f"an act (and none) takes effect {lead} control steps after the step at which it arrives "
                             "(the stroke is planned meanwhile; the reply gives effect_step, the state shows "
                             "pending_commands, and a command sent before then is refused with HTTP 409); T counts "
                             "from the effect step" if cfg.action_level == "high" else
                             "traj and none take effect at the next control step")},
            "cameras": [dict(c, fovy_deg=45.0, tile_px=list(BM.Match.TILE), focal_px=FOCAL_PX,
                             principal_point_px=[240, 180], image_right="forward x up") for c in BM.Match.cam_info()],
            "image": "2 rows (behind, side) x 4 columns (camera frames 60 ms apart, oldest left); tile 480 x 360",
            "shuttle": {"model": "point mass, gravity 9.81 + quadratic drag: dv/dt = g - K |v| v",
                        "K_per_m": round(BM.K_DRAG, 4), "terminal_speed_mps": BM.V_TERM,
                        "bounce": "none: the rally ends when it reaches the floor"},
        }
        if cfg.action_level == "low":
            rob = m.robot(seat)
            out["joints"] = {"names": BM.JOINTS, "low": [float(x) for x in rob.s.lo],
                             "high": [float(x) for x in rob.s.hi],
                             "max_step": [float(x) for x in BM.VEL_LIMIT * DT],
                             "ready_pose_arm": [float(x) for x in BM.Q0_ARM],
                             "rule": "each target within [low, high] and within max_step of the previous target "
                                     "(the first one: of q_target in the state)"}
        return out

    def players(self):
        import builtin_players as bp
        return {"reference": bp.Reference, "random": bp.Random}


SPORT = BadmintonSport()
