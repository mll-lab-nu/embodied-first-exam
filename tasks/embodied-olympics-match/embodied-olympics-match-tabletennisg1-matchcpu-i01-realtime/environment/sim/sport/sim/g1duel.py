"""The game of tabletennis_g1: two Unitree G1s (g1world.World), the ITTF referee and service judge, one game to 5.

Robot A (y < 0, facing +y) and robot B (y > 0, facing -y) stand at the two ends of the table. Format duel: both are
players' robots; format match: B is the platform's opponent (opponent.Opponent, a peer: the same robot driven
through the same joint interface, at its level). The rules and the referee are sports/tabletennis revision
duel-wallclock-12's (sim/duel.py there: the service by the players (serve.py, ITTF 2.6), 2 serves each and one each
from 4:4, lets, the expedite rule's 13 returns and 30 s limit, the 16-point guard; the referee a deterministic function of the ball's
contact events inside every physics step), with the G1 in place of the Franka on its rail:

  each point (rule G3)   both robots are put back standing still in the ready pose at home (a humanoid may have fallen;
                         the body holds them in the ready pose until their players command them); the serve opens READY_STEPS
                         after the point
  commands               a robot's joint command (joints, g1world.Robot.command: the open-control arbiter; no walk) and the
                         server's toss; a command to a robot that is stopped by a reflex or has fallen is refused
  the hidden ball        before its toss the ball waits out of every camera's view (HIDE, in the server's frame)
  the toss's reach       measured from the server's pelvis (rule G4)
  robot and net          a robot (links or racket) touching the net assembly loses the point (ITTF 2.10.1.10); touching
                         the table is allowed (the collision reflex protects the robot)

Each side sees and acts in its OWN frame (the frame of A; B's is the world turned by 180 degrees about z).
"""
from __future__ import annotations

import hashlib
import json
import time
from collections import deque

import numpy as np

import g1world as GW
import serve as SV
from g1world import CONTROL_DT, OTHER, SIDES, own

WIN_POINTS = 5                  # first to 5 ...
WIN_BY = 2                      # ... but from 4:4 a player must lead by 2 ...
CAP_POINTS = 7                  # ... up to 7 (at 6:6 the next point wins)
EXPEDITE_RETURNS = 13           # ITTF 2.15.4: the receiver's 13th good return in a rally wins it the point
MAX_POINTS_WITH_LETS = 16       # guard: then the player ahead wins, at a level score the player who won the last point
                                # (g1tt-8, was 40: a game has at most 13 scored points; 16 leaves 3 lets and bounds the
                                # session, sport.toml [termination])
POINT_LIMIT_S = 30.0            # g1tt-8 (D15): a point not decided this long after its serve opened is the receiver's
                                # (the expedite rule in time; the longest point of 615 screening matches: 24 s)
READY_STEPS = 80                # the serve opens 0.8 s after a point
CAM_EVERY = 2
DEAD_STEPS = 250                # 2.5 s after the last event without a decisive one: the player to hit loses
HIDE = np.array([0.0, -9.0, 4.0])   # the ball before its toss (server's frame): far behind and above, out of view
REVISION = "g1tt-10"            # bump on any change that alters play (the world, the rules, the observation)
CAMS = (([0.0, 0.30, 0.05], 3.6, 72.0, -33.0),      # behind and above the robot, looking down the table
        ([0.0, 0.05, 0.25], 4.0, 0.0, -8.0))        # from the side
CAM_INFO = [{"name": "behind", "position": [-0.933, -2.5714, 2.0107], "forward": [0.2592, 0.7976, -0.5446],
             "up": [0.1683, 0.518, 0.8387]},
            {"name": "side", "position": [-3.9611, 0.05, 0.8067], "forward": [0.9903, 0.0, -0.1392],
             "up": [0.1392, 0.0, 0.9903]}]
VIEW_BACK = (0, 2, 4, 6)        # camera frames back from the latest: 0, 40, 80, 120 ms


def match_winner(score):
    for s in SIDES:
        a, b = score[s], score[OTHER[s]]
        if a >= CAP_POINTS or (a >= WIN_POINTS and a - b >= WIN_BY):
            return s
    return None


class Game:
    """One game between side A and side B (module docstring). opponent: None (both sides are players) or a level
    (B is the platform's opponent at that level: its program, opponent.Program, plays as a player seat (g1tt-10,
    core 0.5.6): the Host feeds it opp_view() after every step and applies its commands through opp_command();
    opponent_inline=True (a Game used directly: the screens) runs the program in this thread at every step, with the
    same views and commands). sides: the robots built (default both; ("A",) is a practice world with opponent none:
    the other side is off the field, robot B is not in the model)."""

    def __init__(self, seed: int = 1, first: str = "A", opponent_level: int | None = None, opponent_lv=None,
                 opponent_timing=None, opponent_inline: bool = True, sides=SIDES):
        if first not in SIDES:
            raise ValueError("first must be A or B")
        self.seed, self.first = int(seed), first
        self.W = GW.World(sides, sensing_seed=self.seed)
        self.m, self.d = self.W.m, self.W.d
        self.k = 0
        self.events: list[dict] = []
        self._last_touch: dict = {}
        self.serve_log: list[dict] = []
        self.delay_faults = {"A": 0, "B": 0}
        self.disqualified = None
        self.serve_lets = 0
        self.score = {"A": 0, "B": 0}
        self.points: list[dict] = []
        self.hits = 0
        self.done = False
        self.winner = None
        self.hist: deque = deque(maxlen=12)
        self.review_due = False
        self.rejected = {s: 0 for s in SIDES}
        self.commands = {s: None for s in SIDES}       # the latest command taken per side (shown in the observation)
        self.opp = None                                 # the opponent's program run in line (opponent_inline)
        self.opp_level = None if opponent_level is None else int(opponent_level)
        self.ball_hist: dict = {}                       # step -> (in play, p, v, w): the ball as the world had it
        self.machine = None                             # a practice world's ball machine (devworld.Machine)
        self.listeners: list = []
        if opponent_level is not None:
            import opponent
            tm = opponent_timing or opponent.default_timing()
            self.opp_cam = int(tm.latency("camera") or 0)
            self.opp_lead = int(tm.lead())
            self.opp_tlag = opponent.truth_lag(self.opp_level, self.opp_cam)
            if opponent_inline:
                self.opp = opponent.Program("B", self.opp_level, self.seed, self.opp_cam, self.opp_lead,
                                            lv=opponent_lv, threaded=False)
            # Embodied First Exam: the toss speeds of the opponent's serves solved here, before play. vz_for_height is
            # ~0.15 s for a height not solved yet; a seat's toss is solved when its act is parsed (plugin.parse, off the
            # world thread), the opponent's toss reached it on the world thread (opp_command): one ~0.15 s step at its
            # first toss, which voided short real-time matches on late_step_p99. The same values, cached earlier.
            lv = dict(opponent.LEVELS[self.opp_level], **(opponent_lv or {}))
            for name in lv["serves"]:
                SV.vz_for_height((lv.get("recipes") or opponent.TP.G1_SERVES)[name].get("height", opponent.TP.TOSS_H))
        self._start_point(0)
        self._apply_reset()
        self._keep_ball()

    # ------------------------------------------------------------------ points
    def server(self) -> str:
        f, o = self.first, OTHER[self.first]
        return f if SV.server_of((self.score[f], self.score[o]), 0, WIN_POINTS) == 0 else o

    def _start_point(self, hold_from):
        srv = self.server()
        recv = OTHER[srv]
        op = hold_from + READY_STEPS
        self.rs = {"point": len(self.points), "server": srv, "receiver": recv, "hold_from": hold_from, "launch": op,
                   "serve": {"phase": "ready", "open_k": op, "deadline_k": op + int(round(SV.SERVE_CLOCK_S / CONTROL_DT)),
                             "toss": None, "judge": None},
                   "expect": recv, "last_hitter": None, "bounces": {"A": 0, "B": 0}, "serve_phase": True,
                   "played_k": op, "ball_id": 0, "last_event_k": op,
                   "hits_in_point": 0, "receiver_returns": 0, "net_touches": 0, "state": "ready"}
        self.events = []
        self._last_touch = {}
        self.hist.clear()
        self._pending_point = None
        self._reset_robots = True          # both robots back standing at home (applied at the end of step())

    def _apply_reset(self):
        for r in self.W.robots.values():
            r.place(self.d)
        self.commands = {s: None for s in SIDES}
        self._park()
        self.W.d.qacc_warmstart[:] = 0.0
        import mujoco as mj
        mj.mj_forward(self.m, self.d)
        self._reset_robots = False

    def _park(self):
        """The ball before it is free: out of view until its toss, then at rest on the toss device."""
        d, sv = self.d, self.rs["serve"]
        d.qpos[3:7] = [1, 0, 0, 0]
        d.qvel[0:6] = 0.0
        d.qpos[0:3] = own(self.rs["server"], HIDE) if sv["toss"] is None else sv["toss"]["world"]

    def in_play(self):
        return self.rs["state"] in ("rest", "live")

    def pelvis_own(self, side):
        r = self.W.robots[side]
        return own(side, self.d.qpos[r.root_q:r.root_q + 3])[:2]

    # ------------------------------------------------------------------ the service (serve.py)
    def toss_check(self, side, pos_own, height):
        rs, sv = self.rs, self.rs["serve"]
        if self.done or rs["server"] != side or sv["toss"] is not None:
            return "no toss now: it is not your service, or the ball is already in play", 409
        if self.k < sv["open_k"]:
            return (f"no toss yet: your opponent is getting ready (the serve opens in "
                    f"{(sv['open_k'] - self.k) * CONTROL_DT:.2f} s)", 409)
        why = SV.toss_problem(pos_own, height, self.pelvis_own(side))
        return None if why is None else (why, 400)

    def toss(self, side, pos_own, height):
        bad = self.toss_check(side, pos_own, height)
        if bad:
            return {"rejected": bad[0]}
        sv = self.rs["serve"]
        sv["toss"] = {"pos": [float(x) for x in pos_own], "height": float(height), "vz": SV.vz_for_height(height),
                      "k": int(self.k), "world": [float(x) for x in own(side, pos_own)]}
        sv["phase"] = "rest"
        sv["judge"] = SV.ServeJudge(self.k)
        self.rs["state"] = "rest"
        self.rs["played_k"] = self.k
        self.rs["last_event_k"] = self.k
        self.serve_log.append({"point": self.rs["point"], "server": side,
                               "toss": {k: sv["toss"][k] for k in ("pos", "height", "vz", "k")}})
        self._park()
        return {"toss": {k: sv["toss"][k] for k in ("pos", "height", "k")},
                "projected_at_step": int(self.k + SV.TOSS_REST_STEPS)}

    def _serve_kind(self, kind):
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
        p = own(rs["server"], ev["pos"])
        v = own(rs["server"], self.W.v_pre)
        j.contact(self._serve_kind(ev["kind"]), p, v, ev["k"])
        if j.struck and not was_struck:
            srv = rs["server"]
            sv["phase"] = "struck"
            rs["last_hitter"] = srv
            rs["expect"] = rs["receiver"]
            rs["bounces"] = {"A": 0, "B": 0}
            rs["played_k"] = self.k
            rs["ball_id"] += 1
            rs["hits_in_point"] += 1
            self.hits += 1
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
            rs["bounces"] = {srv: 0, recv: 1}
            if j.net:
                rs["net_touches"] += 1
            return
        if j.verdict == "let":
            self.serve_lets += 1
            if self.serve_lets < SV.LET_LIMIT:
                return self._end_point(None, "let: " + j.why)
            log.update(verdict="fault", code="repeated_let", why=SV.repeated_let_why(self.serve_lets))
            return self._end_point(srv, f"serve_fault:repeated_let: {SV.repeated_let_why(self.serve_lets)} "
                                        f"({srv} served)")
        if j.verdict == "obstruction":
            return self._end_point(recv, f"{recv} obstructed the service: " + j.why)
        return self._end_point(srv, f"serve_fault:{j.code or 'other'}: {j.why} ({srv} served)")

    def _end_point(self, loser, how):
        if self._pending_point is None:
            self._pending_point = (loser, how)

    def _commit_point(self):
        loser, how = self._pending_point
        winner = OTHER[loser] if loser is not None else None
        if winner is not None:
            self.score[winner] += 1
            self.serve_lets = 0
        self.review_hist = list(self.hist) or [self._snap()]
        self.points.append({"point": len(self.points) + 1, "winner": winner, "loser": loser, "how": how,
                            "score": dict(self.score), "hits": self.rs["hits_in_point"], "step": self.k,
                            "server": self.rs["server"], "receiver": self.rs["receiver"], "let": loser is None,
                            "net_touches": self.rs["net_touches"],
                            "robots": {s: self.W.robots[s].status() for s in self.W.sides}})
        self.rs["state"] = "over"
        w = match_winner(self.score) if self.machine is None else None   # the ball machine's world never ends
        if self.disqualified is not None:
            w = OTHER[self.disqualified]
        if w is None and len(self.points) >= MAX_POINTS_WITH_LETS and self.machine is None:
            a, b = self.score["A"], self.score["B"]
            w = "A" if a > b else "B" if b > a else next(p["winner"] for p in reversed(self.points) if p["winner"])
        if w is not None:
            self.winner = w
            self.done = True
            return
        self._start_point(self.k)
        self.review_due = True

    # ------------------------------------------------------------------ commands
    def install(self, side, cmd) -> dict:
        """A validated joint command (plugin.JointLayer: joints / walk) of `side`, taking effect from this step."""
        r = self.W.robots[side]
        if cmd["type"] == "walk":
            why = r.command(self.d, walk=cmd["v"])
        else:
            why = r.command(self.d, q=cmd["q"], kp=cmd.get("kp"), kd=cmd.get("kd"), qd=cmd.get("qd"),
                            walk=cmd.get("walk"))
        if why:
            self.rejected[side] += 1
            return {"rejected": why}
        self.commands[side] = {"type": cmd["type"], "step": int(self.k),
                               **({"rows": int(np.asarray(cmd["q"]).reshape(-1, np.shape(cmd["q"])[-1]).shape[0])}
                                  if cmd["type"] == "joints" else {"v": [float(x) for x in cmd["v"]]})}
        return {"command": cmd["type"], "step": int(self.k)}

    # ------------------------------------------------------------------ the platform's opponent (side B, format match)
    def opp_view(self) -> dict:
        """The opponent's view of this step (opponent.view: its seat's channels and latencies)."""
        import opponent
        return opponent.view(self, "B", self.opp_cam, self.opp_tlag)

    def opp_command(self, cmd: dict) -> dict:
        """One command of the opponent's program (joints or toss), as a seat's act takes effect."""
        if cmd.get("type") == "toss":
            return self.toss("B", cmd["pos"], cmd["height"])
        return self.install("B", cmd)

    def _keep_ball(self):
        """The ball of this step as the world has it (the opponent's camera and truth channels read it later)."""
        p, v, w = self.W.ball()
        self.ball_hist[self.k] = (self.rs["state"] == "live", np.asarray(p, float).copy(),
                                  np.asarray(v, float).copy(), np.asarray(w, float).copy())
        self.ball_hist.pop(self.k - 64, None)

    # ------------------------------------------------------------------ one control step
    def step(self):
        if self.done:
            return
        d, sv = self.d, self.rs["serve"]
        if self.opp is not None:                         # the program in line (a Game used directly): its view of
            res = self.opp.decide({"k": self.k, "unit": len(self.points), "obs": self.opp_view()})   # this step,
            for c in res.get("commands") or ():                                                     # its commands
                self.opp_command(c)
        if self.rs["state"] == "rest" and self.k - sv["toss"]["k"] >= SV.TOSS_REST_STEPS:
            d.qpos[0:3] = sv["toss"]["world"]
            d.qvel[0:3] = [0.0, 0.0, sv["toss"]["vz"]]
            d.qvel[3:6] = 0.0
            self.rs["state"] = "live"
            sv["phase"] = "toss"
            sv["judge"].projected = True

        def scan(contacts):
            self._scan(contacts)
            j = sv["judge"]
            if (j is not None and self.rs["state"] == "live" and not j.struck and j.verdict is None
                    and self._pending_point is None):
                j.position(own(self.rs["server"], d.qpos[0:3]))      # Law 2.6.4 at every physics step
                self._serve_decided()
        self.W.step(scan)
        self.k += 1
        if self.rs["state"] in ("ready", "rest"):
            self._park()
            if self.rs["state"] == "ready" and self._pending_point is None:
                self._serve_clock()
        elif self._pending_point is None:
            self._referee_time()
        if self.k % CAM_EVERY == 0 or self._pending_point is not None:
            self.hist.append(self._snap())
        if self._pending_point is not None:
            self._commit_point()
        if self._reset_robots and not self.done:
            self._apply_reset()
        self._keep_ball()

    def _snap(self):
        return {"k": self.k, "qpos": self.d.qpos.copy(), "played_k": self.rs["played_k"], "point": self.rs["point"],
                "wall_mono": time.monotonic()}

    def _scan(self, contacts):
        if self.rs["state"] not in ("rest", "live") or self.done or self._pending_point is not None:
            return
        t = self.d.time
        env = self.W.net_touch
        if env:
            if len(env) == 2:
                self._end_point(None, "let: both robots touched the net at once")
            else:
                s = next(iter(env))
                self._end_point(s, f"{s}'s robot touched the net assembly (Law 2.10.1.10)")
            return
        kinds = {k for k, _c in contacts}
        new = [kind for kind in kinds if kind not in self._last_touch or
               t - self._last_touch[kind] > GW.MERGE_GAP_S + 1e-9]
        for kind in kinds:
            self._last_touch[kind] = t
        for prefix in ("robot_", "paddle_"):
            if prefix + "A" in new and prefix + "B" in new:
                self._end_point(None, "let: simultaneous two-seat ball contact")
                return
        priority = lambda k: (0 if k.startswith("robot_") else 1 if k in ("table_A", "table_B") else
                              2 if k.startswith("paddle_") else 3, k)
        for kind in sorted(new, key=priority):
            ev = {"t": round(float(t), 6), "k": self.k, "kind": kind, "pos": self.d.qpos[:3].tolist()}
            self.events.append(ev)
            for lis in self.listeners:                  # what the in-world robots hear (the opponent's planner)
                lis.heard(ev)
            self._on_event(ev)
            if self._pending_point is not None:
                break

    def _on_event(self, ev):
        rs = self.rs
        if self.done or rs["state"] not in ("rest", "live"):
            return
        kind = ev["kind"]
        rs["last_event_k"] = self.k
        if rs["serve_phase"]:
            return self._serve_event(ev)
        exp, hitter = rs["expect"], rs["last_hitter"]
        if kind in ("table_A", "table_B"):
            half = kind[-1]
            if half == exp:
                rs["bounces"][exp] += 1
                if rs["bounces"][exp] >= 2:
                    return self._end_point(exp, f"{exp} let the ball bounce twice")
                if hitter == rs["receiver"]:
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
                rs["last_hitter"] = p
                rs["expect"] = OTHER[p]
                rs["bounces"] = {"A": 0, "B": 0}
                rs["played_k"] = self.k
                rs["ball_id"] += 1
                rs["hits_in_point"] += 1
                self.hits += 1
                return
            return self._end_point(p, f"{p} touched the ball twice")
        if kind == "net":
            rs["net_touches"] += 1
            return
        if kind.startswith("robot_"):
            r = kind[-1]
            if hitter is not None and r == exp and rs["bounces"][r] == 0 and not self._towards_half(r):
                return self._end_point(hitter, f"{hitter}'s shot went out (it passed {r}'s half and hit {r}'s robot)")
            return self._end_point(r, f"the ball hit {r}'s robot (not the blade)")
        if rs["bounces"][exp] >= 1:
            return self._end_point(exp, f"{exp} missed the ball")
        return self._end_point(hitter, f"{hitter}'s shot went out")

    def _towards_half(self, side, horizon_s=0.5):
        p, v = own(side, self.d.qpos[0:3]), own(side, self.W.v_pre)
        for t in np.linspace(0.0, horizon_s, 26):
            x, y = p[0] + v[0] * t, p[1] + v[1] * t
            if abs(x) <= GW.TABLE_X and -GW.TABLE_Y <= y <= 0.0:
                return True
        return False

    def _serve_clock(self):
        rs, sv = self.rs, self.rs["serve"]
        if self.machine is not None or sv["toss"] is not None or self.k < sv["deadline_k"]:
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
        if self.k - sv["open_k"] >= int(round(POINT_LIMIT_S / CONTROL_DT)):
            return self._end_point(rs["server"], f"the point was not decided {POINT_LIMIT_S:.0f} s after the serve "
                                                 f"opened: the receiver wins it (expedite rule, D15)")
        if rs["serve_phase"] and sv["judge"] is not None and sv["judge"].struck and \
                self.k - sv["judge"].strike["k"] >= SV.SERVE_STEPS:
            sv["judge"]._end("fault", "the service was not decided within 3 s of the strike", "undecided")
            return self._serve_decided()
        p = self.d.qpos[0:3]
        out = abs(p[1]) > 3.0 or abs(p[0]) > 2.5 or p[2] < -0.5
        if rs["serve_phase"] and not (sv["judge"] and sv["judge"].struck):
            out = False                                  # the toss: the judge decides (2.6.4)
        if out or self.k - rs["last_event_k"] > DEAD_STEPS:
            exp, hitter = rs["expect"], rs["last_hitter"]
            if hitter is None or rs["bounces"][exp] >= 1:
                return self._end_point(exp, f"{exp} missed the ball")
            return self._end_point(hitter, f"{hitter}'s shot went out")

    def review_done(self):
        self.review_due = False

    def state_sha(self):
        h = hashlib.sha256(self.W.state_sha().encode())
        h.update(json.dumps(self.points, sort_keys=True, default=str).encode())
        if self.opp is not None:
            h.update(self.opp.digest().encode())
        return h.hexdigest()

    # ------------------------------------------------------------------ what a side sees (own frame)
    def heard(self, side) -> list:
        o = OTHER[side]
        names = {f"table_{side}": "bounce on your half", f"table_{o}": "bounce on the opponent's half",
                 f"paddle_{side}": "paddle", f"paddle_{o}": "opponent hit", f"robot_{side}": "robot",
                 f"robot_{o}": "opponent robot", "table_side": "table side", "net": "net", "floor": "floor"}
        t0 = self.rs["played_k"] * CONTROL_DT
        return [{"event": names.get(x["kind"], x["kind"]), "t": round(x["t"] - t0, 3)}
                for x in self.events[-12:] if x["t"] >= t0 - .011]
