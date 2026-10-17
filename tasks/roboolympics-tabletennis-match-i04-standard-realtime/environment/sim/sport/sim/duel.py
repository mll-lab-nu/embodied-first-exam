"""Table-tennis duel: two robots, two models. One game: first to 5 points; from 4:4 a player must lead by 2, capped at
7 (at 6:6 the next point wins), i.e. ITTF 2.11.1 scaled down.

Robot A (y < 0, facing +y) and robot B (y > 0, facing -y) are identical Franka + paddle arms on x-y rail bases in one
MuJoCo scene (scene/tt_duel.xml). The players serve (serve.py, ITTF 2.6): FIRST_SERVER serves the first two points,
then the other two, and so on; from 4:4 the service changes after every point (ITTF 2.13.3 scaled; lets do not count).
Before every point both robots are put back at rest in the ready pose with their bases at home; the server tosses
(`toss`) within serve.SERVE_CLOCK_S of the serve opening and strikes the falling ball; then the two players rally.

Each player sees and acts in its OWN frame, the frame of the single-player tasks (its robot's base at home (0, -1.75,
0) facing +y, its half y < 0): for B every position is mirrored, (x, y, z) -> (-x, -y, z). So both players get the
same instruction, the same cameras (behind and beside their robot) and the same shot interface; the shot of either side
is planned by the match task's stroke controller on a single-robot planning copy in that player's frame (the joint
spaces of the two robots coincide).

Rules (the referee is a deterministic function of the contact events, evaluated inside every control step, so the
recorded joint targets and tosses of both robots replay the match bit-exactly):
  - the service (serve.ServeJudge): struck as the toss falls, behind the end line and above the playing surface, it
    bounces on the server's court, then on the receiver's court; a net touch on an otherwise good service is a let; any
    other service fault is the receiver's point; the receiver must hit the served ball after its bounce;
  - after a hit by P the ball must first touch the table on the other half; the other player must hit it after
    exactly one bounce on its half;
  - the player to hit loses the point if it lets the ball bounce twice, hits it before it bounced (volley), misses it
    (the ball reaches the floor after its bounce), or the ball hits its arm while over or travelling towards its half
    (obstruction, ITTF 2.10.1.6); the hitter loses the point if its ball touches its own half, the floor, the other
    robot beyond the end line or beside the table (ITTF 2.10.1.4) or anything else before the other half; a return
    that touches the net and then the other half is good and play continues (ITTF 2.7.1); a robot whose arm or paddle
    touches the net assembly loses the point (touching the table is allowed, ITTF 2.10.1.9-11); touching the ball
    twice loses the point;
  - faults by both players at once are lets;
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
import serve as SV
from rally import BallModel, world_spin  # noqa: F401
from rcb_tt import ARM_VEL, BASE_VMAX, CONTROL_DT, HOME, VEL_LIMIT, KP, KD, SUBSTEPS, MERGE_GAP_S, JOINTS

HERE = Path(__file__).resolve().parent
SCENE2 = HERE / "scene" / "tt_duel.xml"
Q0 = np.r_[HOME, rcb_tt.load_instance(str(rally.INSTANCE))["q0"]]     # the ready configuration (9: base at home)
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
REVISION = "duel-wallclock-12"   # 12: the setpoint generator and the planner at 0.9 of the velocity limits, the joint-velocity reflex; 11: realistic restitution, scatter 1 cm / 1.5 deg / 5 %, the JerkLimiter brakes relative to the reference, serve depth rule D13; 10: the setpoint generator brakes within the jerk in force (no ringing); 4: the players' images (fine arm meshes); 5: the robots stand on x-y rail bases; 6: the players serve (serve.py)
                             # 7: table contact allowed (D4), table avoidance; 8: the real robot's limits (rcb_tt.TTServo)
                             # 9: at most 2 service lets in a row (serve.LET_LIMIT, D12)
FIRST_SERVER = os.environ.get("FIRST_SERVER", "A")
if FIRST_SERVER not in ("A", "B"):
    raise ValueError("FIRST_SERVER must be A or B")
SIDES = ("A", "B")
OTHER = {"A": "B", "B": "A"}
MIR = np.array([-1.0, -1.0, 1.0])


def mir(v):
    return np.asarray(v, float) * MIR


def own(side, v):
    """World <-> side's own frame (B's frame is the world turned by 180 degrees about z; the map is its own inverse)."""
    return mir(v) if side == "B" else np.asarray(v, float)


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
        self.base_rest = HOME.copy()
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
        self.aadr = {s: np.array([aid(f"motor_bx{sfx}"), aid(f"motor_by{sfx}")] + [aid(f"motor{i}{sfx}") for i in range(1, 8)])
                     for s, sfx in (("A", ""), ("B", "_b"))}
        self.lo = m.actuator_ctrlrange[:, 0].copy(); self.hi = m.actuator_ctrlrange[:, 1].copy()
        self.JLOW = m.jnt_range[[jid(j) for j in JOINTS], 0].copy(); self.JHIGH = m.jnt_range[[jid(j) for j in JOINTS], 1].copy()
        gid = lambda n: mj.mj_name2id(m, mj.mjtObj.mjOBJ_GEOM, n)
        self.g_ball, self.g_table, self.g_net, self.g_floor = gid("geom_ball"), gid("geom_table"), gid("geom_net"), gid("floor")
        self.g_blade = {"A": gid("paddle_blade"), "B": gid("paddle_blade_b")}
        self.robot_geoms = {s: self._subtree_geoms("link0" + sfx) for s, sfx in (("A", ""), ("B", "_b"))}
        self.site_paddle = {s: mj.mj_name2id(m, mj.mjtObj.mjOBJ_SITE, "paddle_center" + sfx) for s, sfx in (("A", ""), ("B", "_b"))}
        mj.mj_resetData(m, d)
        for s in SIDES:
            d.qpos[self.qadr[s]] = Q0
        mj.mj_forward(m, d)
        self._M = np.zeros((m.nv, m.nv))
        self.servo = {s: rcb_tt.TTServo(self.qadr[s], self.vadr[s], self.aadr[s]) for s in SIDES}
        for s in SIDES:
            self.servo[s].sync(d)
        self.target = {s: Q0.copy() for s in SIDES}
        self.prev = {s: Q0.copy() for s in SIDES}          # the targets of the previous step (target velocity)
        self.prev2 = {s: Q0.copy() for s in SIDES}         # ... and of the step before (target acceleration)
        self.actions = {s: [] for s in SIDES}
        self.k = 0
        self.events: list[dict] = []
        self._last_touch: dict = {}
        self.env_touch = {s: 0 for s in SIDES}
        self.serve_log: list[dict] = []      # every service: server, toss, strike, verdict
        self.delay_faults = {"A": 0, "B": 0}
        self.disqualified = None
        self.serve_lets = 0                  # service lets since the last point scored (serve.LET_LIMIT, D12)
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
        self.base_rest = {s: HOME.copy() for s in SIDES}   # where each base goes when no stroke is under way (`move`)
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
    def server(self) -> str:
        """Law 2.13.3 (scaled): FIRST_SERVER serves 2, then the other 2, ...; from 4:4 one each in turn."""
        f, o = FIRST_SERVER, OTHER[FIRST_SERVER]
        return f if SV.server_of((self.score[f], self.score[o]), 0, WIN_POINTS) == 0 else o

    def _start_point(self, hold_from):
        n = len(self.points)
        srv = self.server()
        recv = OTHER[srv]
        op = hold_from + READY_STEPS
        self.rs = {"point": n, "server": srv, "receiver": recv, "hold_from": hold_from, "launch": op,
                   "serve": {"phase": "ready", "open_k": op, "deadline_k": op + int(round(SV.SERVE_CLOCK_S / CONTROL_DT)),
                             "toss": None, "judge": None},
                   "expect": recv, "last_hitter": None, "bounces": {"A": 0, "B": 0}, "serve_phase": True,
                   "played_k": op, "ball_id": 0, "last_event_k": op,
                   "hits_in_point": 0, "receiver_returns": 0, "net_touches": 0, "state": "ready"}
        self.events = []; self._last_touch = {}; self.frames = []
        self.hist.clear()
        self._pending_point = None
        self._toss_pending = None
        self._reset_arms = True           # both players back to the ready pose and home (applied at the end of step())
        self._park()

    def _park(self):
        """The ball before it is free: hidden in the server's column until its toss, then at rest on the toss device."""
        d, sv = self.d, self.rs["serve"]
        d.qpos[3:7] = [1, 0, 0, 0]; d.qvel[0:6] = 0.0
        if sv["toss"] is None:
            srv = self.rs["server"]
            b = d.qpos[self.qadr[srv][:2]]
            d.qpos[0:3] = own(srv, [b[0], b[1], -0.3])               # inside the column: no contact, not drawn
        else:
            d.qpos[0:3] = sv["toss"]["world"]

    def in_play(self):
        return self.rs["state"] in ("rest", "live")

    # ------------------------------------------------------------------ the service (serve.py)
    def toss_check(self, side, pos_own, height):
        """Why side's toss is refused now ((reason, HTTP code)), else None. pos in side's own frame."""
        rs, sv = self.rs, self.rs["serve"]
        if self.done or rs["server"] != side or sv["toss"] is not None or self._toss_pending is not None:
            return "no toss now: it is not your service, or the ball is already in play", 409
        if self.k < sv["open_k"]:
            return (f"no toss yet: your opponent is getting ready (the serve opens in "
                    f"{(sv['open_k'] - self.k) * CONTROL_DT:.2f} s)", 409)
        why = SV.toss_problem(pos_own, height, self.target[side][:2])
        return None if why is None else (why, 400)

    def toss(self, side, pos_own, height):
        """`toss` at the start of the coming control step: the ball at rest at the toss point (own frame) on the toss
        device, projected straight up serve.TOSS_REST_STEPS later to rise `height` metres."""
        bad = self.toss_check(side, pos_own, height)
        if bad:
            return {"rejected": bad[0]}
        sv = self.rs["serve"]
        sv["toss"] = {"pos": [float(x) for x in pos_own], "height": float(height), "vz": SV.vz_for_height(height),
                      "k": int(self.k),
                      "world": [float(x) for x in own(side, pos_own)]}
        sv["phase"] = "rest"
        sv["judge"] = SV.ServeJudge(self.k)
        self.rs["state"] = "rest"; self.rs["played_k"] = self.k; self.rs["last_event_k"] = self.k
        self.serve_log.append({"point": self.rs["point"], "server": side,
                               "toss": {k: sv["toss"][k] for k in ("pos", "height", "vz", "k")}})
        self._park()
        return {"toss": {k: sv["toss"][k] for k in ("pos", "height", "k")},
                "projected_at_step": int(self.k + SV.TOSS_REST_STEPS)}

    def _serve_kind(self, kind):
        """A contact kind in the server's terms (serve.ServeJudge)."""
        srv = self.rs["server"]
        if kind in ("table_A", "table_B"):
            return "table_server" if kind[-1] == srv else "table_receiver"
        for pre in ("paddle_", "robot_"):
            if kind.startswith(pre):
                return pre + ("server" if kind[-1] == srv else "receiver")
        return kind

    def _serve_event(self, ev):
        rs, sv = self.rs, self.rs["serve"]
        j = sv["judge"]
        was_struck = j.struck
        p = own(rs["server"], ev["pos"]); v = own(rs["server"], self._v_pre)
        j.contact(self._serve_kind(ev["kind"]), p, v, ev["k"])
        if j.struck and not was_struck:                 # the strike: the ball is played to the receiver
            srv = rs["server"]
            sv["phase"] = "struck"
            rs["last_hitter"] = srv; rs["expect"] = rs["receiver"]; rs["bounces"] = {"A": 0, "B": 0}
            rs["played_k"] = self.k; rs["ball_id"] += 1; rs["hits_in_point"] += 1; self.hits += 1
            self.frames = []
        self._serve_decided()

    def _serve_decided(self):
        rs, sv = self.rs, self.rs["serve"]
        j = sv["judge"]
        if j.verdict is None:
            return
        log = self.serve_log[-1]
        log.update(verdict=j.verdict, why=j.why, code=j.code, strike=j.strike, net=j.net)
        srv, recv = rs["server"], rs["receiver"]
        if j.verdict == "good":
            rs["serve_phase"] = False
            sv["phase"] = "in play"
            rs["bounces"] = {srv: 0, recv: 1}           # it bounced on the receiver's court: the receiver must hit it
            if j.net:
                rs["net_touches"] += 1
            return
        if j.verdict == "let":
            self.serve_lets += 1                        # a let does not change the server (2.13.3): at most
            if self.serve_lets < SV.LET_LIMIT:          # LET_LIMIT - 1 in a row (D12)
                return self._end_point(None, "let: " + j.why)
            log.update(verdict="fault", code="repeated_let", why=SV.repeated_let_why(self.serve_lets))
            return self._end_point(srv, f"serve_fault:repeated_let: {SV.repeated_let_why(self.serve_lets)} "
                                        f"({srv} served)")
        if j.verdict == "obstruction":
            return self._end_point(recv, f"{recv} obstructed the service: " + j.why)
        return self._end_point(srv, f"serve_fault:{j.code or 'other'}: {j.why} ({srv} served)")

    def _end_point(self, loser, how):
        # Defer resets until the control boundary: never reset a scene mid-substep.
        if self._pending_point is None:
            self._pending_point = (loser, how)

    def _commit_point(self):
        loser, how = self._pending_point
        winner = OTHER[loser] if loser is not None else None
        if winner is not None:
            self.score[winner] += 1
            self.serve_lets = 0
        self.review_hist = list(self.hist) or [{"k": self.k, "qpos": self.d.qpos.copy(), "played_k": self.rs["played_k"], "point": self.rs["point"]}]
        self.points.append({"point": len(self.points) + 1, "winner": winner, "loser": loser, "how": how,
                            "score": dict(self.score), "hits": self.rs["hits_in_point"], "step": self.k,
                            "server": self.rs["server"], "receiver": self.rs["receiver"], "let": loser is None,
                            "net_touches": self.rs["net_touches"]})
        self.rs["state"] = "over"
        w = match_winner(self.score)
        if self.disqualified is not None:              # the DELAY_LIMIT-th undue-delay fault loses the match
            w = OTHER[self.disqualified]
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
        if q.shape != (rcb_tt.NQ,) or not np.all(np.isfinite(q)):
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
        sv = self.rs["serve"]
        if self.rs["state"] == "rest" and self.k - sv["toss"]["k"] >= SV.TOSS_REST_STEPS and not self.done:
            d.qpos[0:3] = sv["toss"]["world"]; d.qvel[0:3] = [0.0, 0.0, sv["toss"]["vz"]]; d.qvel[3:6] = 0.0
            self.rs["state"] = "live"; sv["phase"] = "toss"; sv["judge"].projected = True
        prev = {s: self.target[s] for s in SIDES}
        for j in range(1, SUBSTEPS + 1):
            mj.mj_fullM(m, self._M, d.qM)             # the joint-space inertia of the last forward pass (servo FF)
            for s in SIDES:                           # each robot's real-limits servo (rcb_tt.TTServo)
                aa = self.aadr[s]
                d.ctrl[aa] = self.servo[s].ctrl(m, d, self._M, j, prev[s], qs[s], self.lo[aa], self.hi[aa])
            self._v_pre = d.qvel[0:3].copy()          # the ball's velocity before this substep (for _towards_half)
            mj.mj_step(m, d)
            self._scan()
            j = sv["judge"]
            if (j is not None and self.rs["state"] == "live" and not j.struck and j.verdict is None
                    and self._pending_point is None):
                j.position(own(self.rs["server"], d.qpos[0:3]))      # Law 2.6.4 at every physics step until the strike
                self._serve_decided()
        for s in SIDES:
            self.servo[s].after_step(d)
            self.prev2[s] = self.prev[s]
            self.prev[s] = self.target[s]
            self.target[s] = qs[s].copy()
            self.actions[s].append(qs[s].copy())
        self.k += 1
        if self.rs["state"] in ("ready", "rest") and not self.done:
            self._park()
            if self.rs["state"] == "ready" and self._pending_point is None:
                self._serve_clock()
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
                self.prev[side] = Q0.copy()                # at rest: the target velocity restarts at zero
                self.prev2[side] = Q0.copy()
                self.base_rest[side] = HOME.copy()
            mj.mj_forward(m, d)
            for side in SIDES:
                self.servo[side].sync(d)                   # the servo restarts at rest in the ready pose
            self._reset_arms = False

    def _scan(self):
        if self.rs["state"] not in ("rest", "live") or self.done or self._pending_point is not None:
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
                    if (g1 in own and g2 == self.g_net) or (g2 in own and g1 == self.g_net):
                        env_faults.add(side)      # ITTF 2.10.1.10; touching the table or floor is allowed (D4)
        if env_faults:
            if len(env_faults) == 2:
                self._end_point(None, "let: both robots touched the net at once")
            else:
                side = next(iter(env_faults)); self._end_point(side, f"{side}'s robot touched the net assembly (Law 2.10.1.10)")
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
        if self.done or rs["state"] not in ("rest", "live"):
            return
        kind = ev["kind"]
        rs["last_event_k"] = self.k
        if rs["serve_phase"]:                           # the service: serve.ServeJudge until its verdict
            return self._serve_event(ev)
        exp, hitter = rs["expect"], rs["last_hitter"]
        if kind in ("table_A", "table_B"):
            half = kind[-1]
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
            rs["net_touches"] += 1                 # a return may touch the net (ITTF 2.7.1): play on
            return
        if kind.startswith("robot_"):
            r = kind[-1]
            if hitter is not None and r == exp and rs["bounces"][r] == 0 and not self._towards_half(r):
                return self._end_point(hitter, f"{hitter}'s shot went out (it passed {r}'s half and hit {r}'s robot)")
            return self._end_point(r, f"the ball hit {r}'s non-blade robot part (arm or handle)")
        # floor / other
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

    def _serve_clock(self):
        """Undue delay: no toss within serve.SERVE_CLOCK_S of the serve opening is a failed service; the
        serve.DELAY_LIMIT-th time the server loses the match."""
        rs, sv = self.rs, self.rs["serve"]
        if sv["toss"] is not None or self._toss_pending is not None or self.k < sv["deadline_k"]:
            return
        srv = rs["server"]
        self.delay_faults[srv] += 1
        if self.delay_faults[srv] >= SV.DELAY_LIMIT:
            self.disqualified = srv
        self.serve_log.append({"point": rs["point"], "server": srv, "verdict": "fault", "why": "undue delay",
                               "code": "undue_delay"})
        self._end_point(srv, f"serve_fault:undue_delay: {srv} did not toss within {SV.SERVE_CLOCK_S:.0f} s "
                             f"(fault {self.delay_faults[srv]} of {SV.DELAY_LIMIT})")

    def _referee_time(self):
        rs = self.rs
        if rs["state"] != "live":
            return
        sv = rs["serve"]
        if rs["serve_phase"] and sv["judge"] is not None and sv["judge"].struck and \
                self.k - sv["judge"].strike["k"] >= SV.SERVE_STEPS:
            sv["judge"]._end("fault", "the service was not decided within 3 s of the strike", "undecided")
            return self._serve_decided()
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
        for a in (self.d.qpos, self.d.qvel, self.d.qacc_warmstart, self.d.ctrl, np.array([self.d.time]),
                  self.servo["A"].state(), self.servo["B"].state()):
            h.update(np.ascontiguousarray(a, dtype=np.float64).tobytes())
        h.update(json.dumps(self.points, sort_keys=True).encode())
        return h.hexdigest()

    # ------------------------------------------------------------------ live control
    def _target_vel(self, s):
        return (self.target[s] - self.prev[s]) / CONTROL_DT

    def _target_acc(self, s):
        return (self.target[s] - 2 * self.prev[s] + self.prev2[s]) / CONTROL_DT ** 2

    def _slew_step(self, s, goal, speed, base_speed=None):
        """A slew step: the arm joint by joint at speed x its velocity limits within its acceleration limits
        (rcb_tt.seek), the base by the bounded go-to generator."""
        tgt = self.target[s]
        vel = self._target_vel(s)
        arm, _ = rcb_tt.seek(tgt[2:], vel[2:], goal[2:], ARM_VEL * speed, rcb_tt.ARM_ACC, self.JLOW[2:], self.JHIGH[2:])
        b, _, _ = rcb_tt.base_goto(tgt[:2], vel[:2], goal[:2],
                                   vmax=BASE_VMAX * (speed if base_speed is None else base_speed),
                                   a=self._target_acc(s)[:2])
        return np.r_[b, arm]

    def _ready(self, s):
        return self._slew_step(s, np.r_[self.base_rest[s], Q0[2:]], 0.6, 1.0)

    def _arm(self, s):
        if self.plan_j[s] < len(self.plan[s]):
            q = self.plan[s][self.plan_j[s]]; self.plan_j[s] += 1
            return q
        if self.slew[s] is not None:
            goal, speed = self.slew[s]
            return self._slew_step(s, goal, speed)
        return self._ready(s) if self.rest_ready else self.target[s].copy()

    def move(self, s, b):
        """`move`: side s's base rest position (own frame = joint values); home again at each point."""
        self.base_rest[s] = np.clip(np.asarray(b, float), rcb_tt.BASE_LO, rcb_tt.BASE_HI)
        return {"base_rest": [round(float(x), 4) for x in self.base_rest[s]]}

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
        held = k0 > self.k                                         # before K0 the target in force is held (at rest)
        why = rcb_tt.rows_problem(Q[j0:j0 + 1], self.target[s], np.zeros(rcb_tt.NQ) if held else self._target_vel(s))
        if why:
            self.rejected[s] += 1
            return {"rejected": f"beyond the limits where it joins the target in force (row {j0}, step "
                                f"{max(self.k, k0)}): {why}; the previous command goes on", "first_row_used": j0}
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
