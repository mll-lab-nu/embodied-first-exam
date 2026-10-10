"""Table-tennis duel: two robots, two models. One game: first to 5 points; from 4:4 a player must lead by 2, capped at
7 (at 6:6 the next point wins), i.e. ITTF 2.11.1 scaled down.

Robot A (y < 0, facing +y) and robot B (y > 0, facing -y) are identical Franka + paddle arms in one MuJoCo scene
(scene/tt_duel.xml, made by mk_scene2.py). Every point starts with a serve machine: a recorded DeepMind serve
(the match task's pool) towards the receiver, who changes every point (FIRST_RECEIVER receives the first; lets do not
count); then the two players rally.

Each player sees and acts in its OWN frame, the frame of the single-player tasks (its robot at (0, -1.75, 0) facing
+y, its half y < 0): for B every position is mirrored, (x, y, z) -> (-x, -y, z). So both players get the same
instruction, the same cameras (behind and beside their robot) and the same shot interface; the shot of either side is
planned by the match task's stroke controller on a single-robot planning copy in that player's frame (the joint
spaces of the two robots coincide).

Rules (the referee is a deterministic function of the contact events, evaluated inside every control step, so the
recorded joint targets of both robots replay the match bit-exactly):
  - the serve bounces on the server's (machine's) half, then on the receiver's half; the receiver must hit it;
  - after a hit by P the ball must first touch the table on the other half; the other player must hit it after
    exactly one bounce on its half;
  - the player to hit loses the point if it lets the ball bounce twice, hits it before it bounced (volley), misses it
    (the ball reaches the floor after its bounce), or the ball hits its arm while over or travelling towards its half
    (obstruction, ITTF 2.10.1.6); the hitter loses the point if its ball touches its own half, the floor, the other
    robot beyond the end line or beside the table (ITTF 2.10.1.4) or anything else before the other half; a return
    that touches the net and then the other half is good and play continues (ITTF 2.7.1); a robot whose arm or paddle
    touches the table, net or floor loses the point; touching the ball twice loses the point;
  - a machine serve that touches the net, an irregular machine serve, or faults by both players at once are lets;
  - expedite rule (ITTF 2.15.4, applied from the first point): if the receiver makes 13 good returns in a rally, the
    receiver wins the point. This bounds every rally (at most 26 hits) and so the match (at most 13 points + lets).
"""
from __future__ import annotations

import io
import json
import os
from collections import deque
from pathlib import Path

import numpy as np

import mujoco as mj
import match
import rally
import rcb_tt
from rally import BallModel, world_spin  # noqa: F401
from rcb_tt import CONTROL_DT, VEL_LIMIT, KP, KD, SUBSTEPS, MERGE_GAP_S, JOINTS

HERE = Path(__file__).resolve().parent
SCENE2 = HERE / "scene" / "tt_duel.xml"
SERVES = match.SERVES
Q0 = rcb_tt.load_instance(str(rally.INSTANCE))["q0"]
WIN_POINTS = 5                  # first to 5 ...
WIN_BY = 2                      # ... but from 4:4 a player must lead by 2 ...
CAP_POINTS = 7                  # ... up to 7 (at 6:6 the next point wins)
EXPEDITE_RETURNS = 13           # ITTF 2.15.4: the receiver's 13th good return in a rally wins it the point
MAX_POINTS_WITH_LETS = 40       # guard: 13 scoring points at most, so this needs 27+ lets; then the player ahead wins,
                                # at a level score the player who won the last point (no draws)
READY_STEPS = 80
CAM_EVERY = 2
DECISION_AFTER_SERVE_BOUNCE = 5
DECISION_AFTER_HIT = 6
ADJUST_FRAMES = 3
DEAD_STEPS = 250                # 2.5 s after the last hit without a decisive event: the player to hit loses
SEED = int(os.environ.get("DUEL_SEED", "1"))   # the serve-machine sequence and both seats' execution scatter
REVISION = "duel-wallclock-3"
FIRST_RECEIVER = os.environ.get("FIRST_RECEIVER", "A")
if FIRST_RECEIVER not in ("A", "B"):
    raise ValueError("FIRST_RECEIVER must be A or B")
SIDES = ("A", "B")
OTHER = {"A": "B", "B": "A"}
MIR = np.array([-1.0, -1.0, 1.0])


def mir(v):
    return np.asarray(v, float) * MIR


def match_winner(score):
    """The winner ('A' / 'B') of a game with this score, else None: first to WIN_POINTS with a lead of WIN_BY, or the
    first to CAP_POINTS."""
    for s in SIDES:
        a, b = score[s], score[OTHER[s]]
        if a >= CAP_POINTS or (a >= WIN_POINTS and a - b >= WIN_BY):
            return s
    return None


class Planner(match.Match):
    """The match task's stroke controller on a single-robot copy, synced to one side's state in that side's frame."""

    def __init__(self, side: str):
        self.side = side
        self.level = 0
        self.lv = {"seed": SEED + (0 if side == "A" else 1)}
        self.s = rcb_tt.Session(instance=str(rally.INSTANCE), scene=str(rally.SCENE))
        self.bm = BallModel()
        self._twin = None
        self._ik_seed = None
        self._planned_hit = None
        self.n_our_legs = 0
        self.leg = {"launch": 0}



class Duel:
    def __init__(self):
        m = self.m = mj.MjModel.from_xml_path(str(SCENE2))
        d = self.d = mj.MjData(m)
        jid = lambda n: mj.mj_name2id(m, mj.mjtObj.mjOBJ_JOINT, n)
        self.qadr = {s: np.array([m.jnt_qposadr[jid(j + sfx)] for j in JOINTS]) for s, sfx in (("A", ""), ("B", "_b"))}
        self.vadr = {s: np.array([m.jnt_dofadr[jid(j + sfx)] for j in JOINTS]) for s, sfx in (("A", ""), ("B", "_b"))}
        aid = lambda n: mj.mj_name2id(m, mj.mjtObj.mjOBJ_ACTUATOR, n)
        self.aadr = {s: np.array([aid(f"motor{i}{sfx}") for i in range(1, 8)]) for s, sfx in (("A", ""), ("B", "_b"))}
        self.lo = m.actuator_ctrlrange[:, 0].copy(); self.hi = m.actuator_ctrlrange[:, 1].copy()
        self.JLOW = m.jnt_range[[jid(j) for j in JOINTS], 0].copy(); self.JHIGH = m.jnt_range[[jid(j) for j in JOINTS], 1].copy()
        gid = lambda n: mj.mj_name2id(m, mj.mjtObj.mjOBJ_GEOM, n)
        self.g_ball, self.g_table, self.g_net, self.g_floor = gid("geom_ball"), gid("geom_table"), gid("geom_net"), gid("floor")
        self.g_blade = {"A": gid("paddle_blade"), "B": gid("paddle_blade_b")}
        self.robot_geoms = {s: self._subtree_geoms("link0" + sfx) for s, sfx in (("A", ""), ("B", "_b"))}
        # Serve fix (2026-09-29): the recorded serves were made for a table with nobody at the serving end. In a duel the
        # server-side robot stands there, so during the serve (until the ball's bounce on the receiver's half) its geoms
        # are "ghosts" for the ball: collision bit 2 only, which the table, net and floor also carry (the arm still
        # collides with them, so the arm-on-table rule holds) but the ball (bit 1) does not.
        self._ghost_geoms = {s: sorted(set(self.robot_geoms[s]) | {self.g_blade[s]}) for s in SIDES}   # the blade is its own body
        self._mask0 = {g: (int(m.geom_contype[g]), int(m.geom_conaffinity[g])) for s in SIDES for g in self._ghost_geoms[s]}
        for g in (self.g_table, self.g_net, self.g_floor):
            m.geom_contype[g] |= 2; m.geom_conaffinity[g] |= 2
        self.ghost = {s: False for s in SIDES}
        # the ball-blade contacts are explicit <pair>s (own restitution), which ignore the masks: switch them off by margin
        self._blade_pairs = {s: [i for i in range(m.npair) if {int(m.pair_geom1[i]), int(m.pair_geom2[i])} == {self.g_ball, self.g_blade[s]}]
                             for s in SIDES}
        self._pair_margin0 = {i: float(m.pair_margin[i]) for s in SIDES for i in self._blade_pairs[s]}
        self.site_paddle = {s: mj.mj_name2id(m, mj.mjtObj.mjOBJ_SITE, "paddle_center" + sfx) for s, sfx in (("A", ""), ("B", "_b"))}
        mj.mj_resetData(m, d)
        for s in SIDES:
            d.qpos[self.qadr[s]] = Q0
        mj.mj_forward(m, d)
        self.target = {s: Q0.copy() for s in SIDES}
        self.actions = {s: [] for s in SIDES}
        self.k = 0
        self.events: list[dict] = []
        self._last_touch: dict = {}
        self.env_touch = {s: 0 for s in SIDES}
        rng = np.random.default_rng(SEED)
        self.serve_ids = [int(x) for x in rng.choice(sorted(SERVES), size=2 * CAP_POINTS - 1, replace=False)]
        self.score = {"A": 0, "B": 0}
        self.points: list[dict] = []
        self.hits = 0
        self.done = False
        self.winner = None
        self.hist: deque = deque(maxlen=12)
        # live control
        # the arm command layer (docs/benchmarks/roboolympics-modes.md; the duel's form of shared/.../core.py): per side a
        # row list from the step it was installed (plan / plan_j), else a slew, else the rest command: the high-level
        # plugin rests by returning to the ready pose (rest_ready, the original behaviour), the low level holds
        self.plan = {s: [] for s in SIDES}; self.plan_j = {s: 0 for s in SIDES}
        self.slew = {s: None for s in SIDES}
        self.rest_ready = True
        self.rejected = {s: 0 for s in SIDES}
        self.planners = {}  # expensive planners live in separate processes
        self.decided: dict = {}              # (ball id, phase) -> True for decisions already served
        self.review_due = False              # a point just ended: the world waits (static) for both seats' reviews
        self._start_point(0)
        self._reset_arms = False
        mj.mj_forward(m, d)

    def _subtree_geoms(self, root_name):
        m = self.m
        root = mj.mj_name2id(m, mj.mjtObj.mjOBJ_BODY, root_name)
        out = set()
        for g in range(m.ngeom):
            b = m.geom_bodyid[g]
            while b not in (0, root):
                b = m.body_parentid[b]
            if b == root:
                out.add(g)
        return out

    # ------------------------------------------------------------------ points
    def _start_point(self, hold_from):
        n = len(self.points)
        recv = FIRST_RECEIVER if sum(self.score.values()) % 2 == 0 else OTHER[FIRST_RECEIVER]   # every point; lets keep it
        sid = self.serve_ids[n % len(self.serve_ids)]
        self.rs = {"point": n, "receiver": recv, "serve": sid, "hold_from": hold_from, "launch": hold_from + READY_STEPS,
                   "expect": recv, "last_hitter": None, "bounces": {"A": 0, "B": 0}, "serve_phase": True,
                   "played_k": hold_from + READY_STEPS, "ball_id": 0, "last_event_k": hold_from + READY_STEPS,
                   "hits_in_point": 0, "receiver_returns": 0, "net_touches": 0, "state": "ready"}
        self.events = []; self._last_touch = {}; self.frames = []
        self.hist.clear()
        self._pending_point = None
        self._set_ghost(OTHER[recv], True); self._set_ghost(recv, False)   # serve fix: server-side robot is a ghost for the ball
        self._reset_arms = True           # serve fix: both players back to the ready pose (applied at the end of step())
        self._park()

    def _set_ghost(self, side, on):
        if self.ghost[side] == on:
            return
        m = self.m
        for g in self._ghost_geoms[side]:
            ct, ca = self._mask0[g]
            if ct or ca:                                  # visual-only geoms (0/0) stay out of collisions
                m.geom_contype[g] = 2 if on else ct
                m.geom_conaffinity[g] = 2 if on else ca
        for i in self._blade_pairs[side]:
            m.pair_margin[i] = -10.0 if on else self._pair_margin0[i]   # a contact would need 10 m of penetration: never
        self.ghost[side] = on

    def _serve_state(self):
        b = SERVES[self.rs["serve"]]
        p, v, w = np.array(b["pos"]), np.array(b["vel"]), np.array(b["spin"])
        if self.rs["receiver"] == "B":
            p, v, w = mir(p), mir(v), mir(w)
        return p, v, w

    def _park(self):
        p, v, w = self._serve_state()
        d = self.d
        d.qpos[0:3] = p; d.qpos[3:7] = [1, 0, 0, 0]; d.qvel[0:3] = v; d.qvel[3:6] = w

    def in_play(self):
        return self.k > self.rs["launch"]

    def _end_point(self, loser, how):
        # Defer resets until the control boundary: never reset a scene mid-substep.
        if self._pending_point is None:
            self._pending_point = (loser, how)

    def _commit_point(self):
        loser, how = self._pending_point
        winner = OTHER[loser] if loser is not None else None
        if winner is not None:
            self.score[winner] += 1
        self.review_hist = list(self.hist) or [{"k": self.k, "qpos": self.d.qpos.copy(), "played_k": self.rs["played_k"], "point": self.rs["point"]}]
        self.points.append({"point": len(self.points) + 1, "winner": winner, "loser": loser, "how": how,
                            "score": dict(self.score), "hits": self.rs["hits_in_point"], "step": self.k,
                            "receiver": self.rs["receiver"], "let": loser is None,
                            "net_touches": self.rs["net_touches"]})
        self.rs["state"] = "over"
        w = match_winner(self.score)
        if w is None and len(self.points) >= MAX_POINTS_WITH_LETS:      # guard (never reached in practice)
            a, b = self.score["A"], self.score["B"]
            w = "A" if a > b else "B" if b > a else next(p["winner"] for p in reversed(self.points) if p["winner"])
        if w is not None:
            self.winner = w
            self.done = True
            return
        self._start_point(self.k)
        self.review_due = True

    # ------------------------------------------------------------------ physics + referee (shared by live and replay)
    def _check(self, side, q):
        if q.shape != (7,) or not np.all(np.isfinite(q)):
            raise ValueError("bad target")
        if (q < self.JLOW - 1e-9).any() or (q > self.JHIGH + 1e-9).any():
            raise ValueError(f"{side}: joint target outside range")
        if (np.abs(q - self.target[side]) > VEL_LIMIT * CONTROL_DT * (1 + 1e-6) + 1e-12).any():
            raise ValueError(f"{side}: joint speed limit")

    def step(self, qA, qB):
        qs = {"A": np.asarray(qA, float), "B": np.asarray(qB, float)}
        for s in SIDES:
            self._check(s, qs[s])
        m, d = self.m, self.d
        if self.rs["state"] == "ready" and self.k >= self.rs["launch"]:
            self.rs["state"] = "live"
        prev = {s: self.target[s] for s in SIDES}
        for j in range(1, SUBSTEPS + 1):
            for s in SIDES:
                qd_des = (qs[s] - prev[s]) / CONTROL_DT
                q_des = prev[s] + (qs[s] - prev[s]) * (j / SUBSTEPS)
                va = self.vadr[s]
                tau = KP * (q_des - d.qpos[self.qadr[s]]) + KD * (qd_des - d.qvel[va]) + d.qfrc_bias[va]
                d.ctrl[self.aadr[s]] = np.clip(tau, self.lo[self.aadr[s]], self.hi[self.aadr[s]])
            self._v_pre = d.qvel[0:3].copy()          # the ball's velocity before this substep (for _towards_half)
            mj.mj_step(m, d)
            self._scan()
        for s in SIDES:
            self.target[s] = qs[s].copy()
            self.actions[s].append(qs[s].copy())
        self.k += 1
        if self.rs["state"] == "ready" and self.k <= self.rs["launch"]:
            self._park()
        elif not self.done and self._pending_point is None:
            self._referee_time()
        if self.k % CAM_EVERY == 0 or self._pending_point is not None:
            self.hist.append({"k": self.k, "qpos": d.qpos.copy(), "played_k": self.rs["played_k"],
                              "point": self.rs["point"], "wall_mono": __import__('time').monotonic()})
            if self.in_play():
                self.frames.append(self.k)
        if self._pending_point is not None:
            self._commit_point()
        if getattr(self, "_reset_arms", False):
            for side in SIDES:
                d.qpos[self.qadr[side]] = Q0; d.qvel[self.vadr[side]] = 0.0
                self.target[side] = Q0.copy(); self.plan[side] = []; self.plan_j[side] = 0; self.slew[side] = None
            mj.mj_forward(m, d)
            self._reset_arms = False

    def _scan(self):
        if self.rs["state"] != "live" or self.done or self._pending_point is not None:
            return
        d, t = self.d, self.d.time
        kinds, env_faults = set(), set()
        for c in d.contact[:d.ncon]:
            g1, g2 = int(c.geom1), int(c.geom2)
            if self.g_ball in (g1, g2):
                other = g2 if g1 == self.g_ball else g1
                if other == self.g_table:
                    normal_z = float(c.frame[2]) * (1 if g1 == self.g_table else -1)
                    top = normal_z > 1e-6 and abs(c.pos[0]) <= .7635 and abs(c.pos[1]) <= 1.371
                    kind = ("table_A" if c.pos[1] < 0 else "table_B") if top else "table_side"
                elif other in self.g_blade.values():
                    kind = "paddle_" + next(s for s in SIDES if self.g_blade[s] == other)
                elif other == self.g_net: kind = "net"
                elif other == self.g_floor: kind = "floor"
                else:
                    owners = [s for s in SIDES if other in self.robot_geoms[s]]
                    kind = "robot_" + owners[0] if owners else "other"
                kinds.add(kind)
            else:
                for side in SIDES:
                    own = self.robot_geoms[side] | {self.g_blade[side]}
                    if ((g1 in own and g2 in (self.g_table, self.g_net, self.g_floor)) or
                            (g2 in own and g1 in (self.g_table, self.g_net, self.g_floor))):
                        env_faults.add(side)
        if env_faults:
            if len(env_faults) == 2:
                self._end_point(None, "let: simultaneous arm/table faults")
            else:
                side = next(iter(env_faults)); self._end_point(side, f"{side}'s arm or paddle touched table/net/floor")
            return
        # Same-substep contacts are processed by category, never by seat priority.
        new = [kind for kind in kinds if kind not in self._last_touch or t-self._last_touch[kind] > MERGE_GAP_S+1e-9]
        for kind in kinds: self._last_touch[kind] = t
        for prefix in ("robot_", "paddle_"):
            if prefix+"A" in new and prefix+"B" in new:
                self._end_point(None, "let: simultaneous two-seat ball contact")
                return
        priority = lambda k: (0 if k.startswith("robot_") else 1 if k in ("table_A", "table_B") else
                              2 if k.startswith("paddle_") else 3, k)
        for kind in sorted(new, key=priority):
            ev = {"t": round(float(t), 6), "k": self.k, "kind": kind, "pos": d.qpos[:3].tolist()}
            self.events.append(ev)
            self._on_event(ev)
            if self._pending_point is not None: break

    def _on_event(self, ev):
        rs = self.rs
        if self.done or rs["state"] != "live":
            return
        kind = ev["kind"]
        rs["last_event_k"] = self.k
        exp, hitter = rs["expect"], rs["last_hitter"]
        server_half = OTHER[rs["receiver"]]
        if kind in ("table_A", "table_B"):
            half = kind[-1]
            if rs["serve_phase"] and hitter is None:
                if half == server_half and rs["bounces"][server_half] == 0 and rs["bounces"][exp] == 0:
                    rs["bounces"][server_half] = 1
                    return
                if half == exp and rs["bounces"][exp] == 0 and rs["bounces"][server_half] == 1:
                    rs["bounces"][exp] = 1; rs["serve_phase"] = False
                    self._set_ghost(server_half, False)     # the serve reached the receiver's half: normal collisions again
                    return
                # an odd serve (never happens with the pool); replay the point as a let is not needed: receiver's point
                return self._end_point(None, "let: irregular machine serve")
            if half == exp:
                rs["bounces"][exp] += 1
                if rs["bounces"][exp] >= 2:
                    return self._end_point(exp, f"{exp} let the ball bounce twice")
                if hitter == rs["receiver"]:                 # a good return by the receiver
                    rs["receiver_returns"] += 1
                    if rs["receiver_returns"] >= EXPEDITE_RETURNS:
                        return self._end_point(OTHER[hitter], f"{hitter} made {EXPEDITE_RETURNS} good returns as the "
                                               "receiver (expedite rule)")
                return
            return self._end_point(hitter, f"{hitter}'s shot hit its own half")
        if kind.startswith("paddle_"):
            p = kind[-1]
            if p == exp:
                if rs["bounces"][exp] != 1:
                    return self._end_point(p, f"{p} hit the ball before it bounced (volley)")
                rs["last_hitter"] = p; rs["expect"] = OTHER[p]; rs["bounces"] = {"A": 0, "B": 0}
                rs["played_k"] = self.k; rs["ball_id"] += 1; rs["hits_in_point"] += 1; self.hits += 1
                self.frames = []
                return
            return self._end_point(p, f"{p} touched the ball twice")
        if kind == "net":
            if hitter is None:
                return self._end_point(None, "let: machine serve touched net")
            rs["net_touches"] += 1                 # a return may touch the net (ITTF 2.7.1): play on
            return
        if kind.startswith("robot_"):
            r = kind[-1]
            if hitter is not None and r == exp and rs["bounces"][r] == 0 and not self._towards_half(r):
                return self._end_point(hitter, f"{hitter}'s shot went out (it passed {r}'s half and hit {r}'s robot)")
            return self._end_point(r, f"the ball hit {r}'s non-blade robot part (arm or handle)")
        # floor / other
        if hitter is None:
            return self._end_point(exp, "the serve was not returned")
        if rs["bounces"][exp] >= 1:
            return self._end_point(exp, f"{exp} missed the ball")
        return self._end_point(hitter, f"{hitter}'s shot went out")

    def _towards_half(self, side, horizon_s=0.5):
        """Whether the ball is over `side`'s half or its straight-line path in the next horizon_s reaches it (in that
        side's own frame). Ball contact with a robot outside this is not obstruction: the shot was going out."""
        p, v = self.d.qpos[0:3].copy(), np.array(self._v_pre)
        if side == "B":
            p, v = mir(p), mir(v)
        for t in np.linspace(0.0, horizon_s, 26):
            x, y = p[0] + v[0] * t, p[1] + v[1] * t
            if abs(x) <= 0.7625 and -1.37 <= y <= 0.0:
                return True
        return False

    def _referee_time(self):
        rs = self.rs
        if rs["state"] != "live":
            return
        p = self.d.qpos[0:3]
        out = abs(p[1]) > 3.0 or abs(p[0]) > 2.5 or p[2] < -0.5
        if out or self.k - rs["last_event_k"] > DEAD_STEPS:
            exp, hitter = rs["expect"], rs["last_hitter"]
            if hitter is None or rs["bounces"][exp] >= 1:
                return self._end_point(exp, f"{exp} missed the ball")
            return self._end_point(hitter, f"{hitter}'s shot went out")

    def replay(self, qA_list, qB_list):
        if len(qA_list) != len(qB_list):
            raise ValueError("seat trajectory lengths differ")
        for a, b in zip(qA_list, qB_list):
            if self.done: raise ValueError("trajectory continues after match end")
            self.step(a, b)

    def state_sha(self):
        import hashlib
        h = hashlib.sha256()
        for a in (self.d.qpos, self.d.qvel, self.d.qacc_warmstart, self.d.ctrl, np.array([self.d.time])):
            h.update(np.ascontiguousarray(a, dtype=np.float64).tobytes())
        h.update(json.dumps(self.points, sort_keys=True).encode())
        return h.hexdigest()

    # ------------------------------------------------------------------ live control
    def _ready(self, s):
        tgt = self.target[s]
        lim = VEL_LIMIT * CONTROL_DT * 0.6
        return tgt + np.clip(Q0 - tgt, -lim, lim)

    def _arm(self, s):
        if self.plan_j[s] < len(self.plan[s]):
            q = self.plan[s][self.plan_j[s]]; self.plan_j[s] += 1
            return q
        if self.slew[s] is not None:
            goal, speed = self.slew[s]
            lim = VEL_LIMIT * CONTROL_DT * speed
            return self.target[s] + np.clip(goal - self.target[s], -lim, lim)
        return self._ready(s) if self.rest_ready else self.target[s].copy()

    def install(self, s, dec):
        """A validated low-level command (action_low.validate) at the start of the coming control step of side s."""
        lim = VEL_LIMIT * CONTROL_DT
        if dec["type"] == "hold":
            self.plan[s] = []; self.plan_j[s] = 0; self.slew[s] = None
            return {"command": "hold"}
        if dec["type"] == "slew":
            self.plan[s] = []; self.plan_j[s] = 0; self.slew[s] = (np.asarray(dec["q"], float), float(dec["speed"]))
            return {"command": "slew"}
        Q = np.asarray(dec["q"], float); k0 = int(dec["k0"]); j0 = max(0, self.k - k0)
        if j0 >= len(Q):
            self.rejected[s] += 1
            return {"rejected": f"stale: the trajectory's last row was for step {k0 + len(Q) - 1}; this is step {self.k}"}
        jump = np.abs(Q[j0] - self.target[s])
        if (jump > lim).any():
            j = int(np.argmax(jump / lim)); self.rejected[s] += 1
            return {"rejected": f"discontinuous: row {j0} (step {self.k}) moves joint {j + 1} by {jump[j]:.5f} rad from "
                                f"the target in force (limit {lim[j]:.5f} per step); the previous command goes on",
                    "first_row_used": j0}
        hold = [self.target[s].copy()] * max(0, k0 - self.k)       # before K0 the target is held
        self.plan[s] = hold + [q for q in Q[j0:]]; self.plan_j[s] = 0; self.slew[s] = None
        return {"command": "traj", "first_row_used": j0, "rows_left": int(len(Q) - j0)}

    def command_state(self, s):
        if self.plan_j[s] < len(self.plan[s]):
            return {"type": "traj", "rows_left": len(self.plan[s]) - self.plan_j[s]}
        if self.slew[s] is not None:
            return {"type": "slew", "q": [round(float(x), 5) for x in self.slew[s][0]], "speed": self.slew[s][1]}
        return "hold"

    def advance(self):
        self.step(self._arm("A"), self._arm("B"))

    def review_done(self):
        self.review_due = False

    # ------------------------------------------------------------------ observations (in the side's own frame)
    CAMS = match.Match.CAMS
    VIEW_BACK = match.Match.VIEW_BACK

    def _extra_geoms(self, scn):
        def add(size, pos, rgba):
            if scn.ngeom >= scn.maxgeom:
                return
            mj.mjv_initGeom(scn.geoms[scn.ngeom], mj.mjtGeom.mjGEOM_BOX, np.asarray(size, float), np.asarray(pos, float),
                            np.eye(3).ravel(), np.asarray(rgba, np.float32))
            scn.ngeom += 1
        for y in np.arange(-1.25, 1.26, 0.25):
            for x in (-0.7625, 0.7625):
                add([0.03, 0.006, 0.002], [x, y, 0.002], [1, 0.9, 0.1, 1])
        for x in np.arange(-0.75, 0.76, 0.25):
            for y in (-1.37, 1.37):
                add([0.006, 0.03, 0.002], [x, y, 0.002], [1, 0.9, 0.1, 1])

    def render_views(self, side, width=480, height=360) -> bytes:
        import imageio.v2 as imageio
        from PIL import Image, ImageDraw
        if not hasattr(self, "_renderer"):
            self._renderer = mj.Renderer(self.m, height=height, width=width)
            self._rd = mj.MjData(self.m)
        cams = []
        for lookat, dist, az, el in self.CAMS:
            c = mj.MjvCamera()
            c.lookat[:] = lookat if side == "A" else mir(lookat)
            c.distance = dist; c.azimuth = az if side == "A" else az + 180.0; c.elevation = el
            cams.append(c)
        r, rd = self._renderer, self._rd
        hist = list(self.hist) or [{"k": self.k, "qpos": self.d.qpos.copy(), "played_k": self.rs["played_k"], "point": self.rs["point"]}]
        snaps = [hist[max(0, len(hist) - 1 - b)] for b in reversed(self.VIEW_BACK)]
        rows = []
        for c in cams:
            tiles = []
            for sn in snaps:
                rd.qpos[:] = sn["qpos"]
                if sn["k"] <= sn.get("played_k", self.rs["played_k"]): rd.qpos[:3] = [0, 0, -10]
                mj.mj_forward(self.m, rd)
                r.update_scene(rd, camera=c)
                self._extra_geoms(r.scene)
                im = Image.fromarray(r.render())
                ImageDraw.Draw(im).text((6, 4), f"k={sn['k']} t={(sn['k'] - sn.get('played_k', self.rs['played_k'])) * CONTROL_DT:.2f}s", fill=(255, 255, 255))
                tiles.append(np.asarray(im))
            rows.append(np.concatenate(tiles, axis=1))
        buf = io.BytesIO()
        imageio.imwrite(buf, np.concatenate(rows, axis=0), format="png")
        return buf.getvalue()


def render_video(qA, qB, out, names=("A", "B"), fps=25):
    """Replay video: a side view and a high view of the whole table, 4x slow motion, with the score."""
    import imageio.v2 as imageio
    from PIL import Image, ImageDraw
    du = Duel()
    r = mj.Renderer(du.m, height=360, width=560)
    cams = []
    for lookat, dist, az, el in (([0.0, 0.0, 0.2], 4.6, 0.0, -10.0), ([0.0, 0.0, 0.0], 4.4, 0.0, -55.0)):
        c = mj.MjvCamera(); c.lookat[:] = lookat; c.distance = dist; c.azimuth = az; c.elevation = el
        cams.append(c)
    w = imageio.get_writer(out, fps=fps, macro_block_size=8)
    for k, (a, b) in enumerate(zip(qA, qB)):
        du.step(a, b)
        if du.rs["state"] != "live" and k % 3:
            continue
        imgs = []
        for c in cams:
            r.update_scene(du.d, camera=c)
            du._extra_geoms(r.scene)
            imgs.append(r.render())
        im = Image.fromarray(np.concatenate(imgs, axis=1))
        ImageDraw.Draw(im).text((8, 6), f"{names[1]} (left)  {du.score['B']} : {du.score['A']}  {names[0]} (right)",
                                fill=(255, 255, 255))
        w.append_data(np.asarray(im))
    w.close(); r.close()
