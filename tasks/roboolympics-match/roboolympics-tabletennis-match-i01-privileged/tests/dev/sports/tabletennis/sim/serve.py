"""The service by the players' robots (revision wallclock-8 / duel-wallclock-6): ITTF Laws of Table Tennis 2.6 (the
service), 2.9.1.1 (let), 2.10.1.1 (a failed service), 2.13.3 (order of serving), scaled to our game (first to 5).
Shared by match.py (format match: the player against the scripted opponent) and duel.py (two players).

The robot holds its paddle and has no free hand, so the toss is made by a toss device on the robot (deviation, Law
2.6.1-2.6.2). The racket sports' common interface (tennis, badminton, table tennis): the server sends
`toss {pos, height}`; when it takes effect the ball rests at `pos` (stationary, as on the open palm, Law 2.6.1) for
TOSS_REST_STEPS and is then projected straight up, with no spin, at the speed that makes it rise `height` metres above
`pos` (Law 2.6.2: near vertically upwards, without spin, rising at least 16 cm: height >= H_MIN; vz_for_height solves
the speed on the simulator's own ball model). Until the toss the ball is held out of sight inside the server's column.
Everything else is judged as in the rulebook:

  2.6.2  the toss falls without touching anything before being struck     -> any other contact first is a fault
  2.6.3  struck as it falls, touching first the server's court, then directly the receiver's court
                                                                          -> a strike while it rises (or rests) is a
                                                                             fault; any other bounce sequence is a fault
  2.6.4  from the start of service until struck, the ball is above the level of the playing surface and behind the
         server's end line                                                -> checked at every physics step on the whole
                                                                             ball (centre z >= r, y <= -(1.37 + r) in
                                                                             the server's frame); a dropped toss is a
                                                                             fault (2.10.1.1)
  2.9.1.1  a service touching the net assembly, otherwise correct (or obstructed by the receiver), is a let; at most
           LET_LIMIT - 1 in a row: the server's LET_LIMIT-th service let since the last point scored is a failed
           service (deviation D12, in place of chapter 3's sanctions for delaying play; see below)
  2.10.1.6 the receiver obstructing a service that did not touch the net loses the point
  2.13.3   service changes after every 2 points; from 4:4 (the scaled 10:10) after every point
  D13      (not in the Laws) the service's bounce on the receiver's court must be at least SERVE_MIN_DEPTH from the net
           (the ball's centre, in the server's frame y >= SERVE_MIN_DEPTH), else a failed service (serve_fault:short);
           a short service that touched the net is a fault too (a let needs a service that is otherwise correct)

Not judged (deviations): the ball hidden from the receiver (2.6.4; the toss is in plain view of both cameras, the
receiver also hears when it is made), the free arm (2.6.5; there is none). The toss point is limited to what the
device can reach: within TOSS_REACH horizontally of the server's base and at most TOSS_Z_MAX above the table. A server
must toss within SERVE_CLOCK_S of the serve opening (undue delay: a failed service; the DELAY_LIMIT-th time it loses the
match) - not in the Laws (chapter 3 regulates delay with warnings and penalty points). Lets are not limited by the
Laws either, and a let does not change the server (2.13.3), so a server who can make the ball clip the net at will
(at the low level a program replays the same joint trajectory from the same reset state, and the physics is
deterministic) could replay its service indefinitely and, when ahead, run the game into the 40-point guard (D8); a
deliberately repeated let is the kind of conduct chapter 3 sanctions (continuity of play 3.4.4.1; behaviour that
unfairly affects an opponent 3.5.2.1, a warning and then penalty points 3.5.2.2-3.5.2.3), here a fixed rule: the
LET_LIMIT-th service let in a row is the receiver's point (serve_fault:repeated_let).
"""
from __future__ import annotations

import numpy as np

BALL_R = 0.02
END_Y = 1.37                      # the end lines are y = -1.37 (the server at y < 0, its own frame)
HALF_X = 0.7625
TOSS_REST_STEPS = 10              # 0.1 s at rest on the device before the projection (Law 2.6.1: stationary)
H_MIN = 0.16                      # m: the toss rises at least 16 cm (Law 2.6.2)
H_MAX = 1.0                       # m: the toss device's limit (projected at 4.8 m/s; 0.9 s back down)
TOSS_REACH = 0.9                  # m, horizontal distance of the toss point from the server's base (the device's reach)
TOSS_Z_MAX = 0.9                  # m above the table top
SERVE_CLOCK_S = 5.0               # s of game time from the serve opening to the toss
DELAY_LIMIT = 3                   # the 3rd undue-delay fault of a player loses it the match
LET_LIMIT = 3                     # the server's 3rd service let since the last point scored is a failed service (D12)
SERVE_MIN_DEPTH = 0.2             # m: the service's bounce on the receiver's court must be at least this far from the net
                                  # (the ball's centre at the contact; deviation D13, revision wallclock-14 / duel-wallclock-11):
                                  # under the real restitution no robot body returns >= 90 % of the legal services that bounce
                                  # closer (B9, olympiad_review/screening/tt_realism_zh.md section 2.6); the value is set by the
                                  # re-screen (0.2 or 0.3 m); the scripted opponent's serve library obeys it too


def repeated_let_why(n: int) -> str:
    """The text of a let service turned into a failed service (D12), after `serve_fault:repeated_let: `."""
    return (f"the service touched the net and was otherwise good, the server's let {n} of {LET_LIMIT} in a row: a "
            "failed service (D12: lets limited in place of ITTF 3.4.4.1 / 3.5.2 sanctions; Law 2.9.1.1)")
OPP_TOSS_VZ = 2.0                 # the scripted opponent's toss (format match): rises 19.8 cm
SERVE_STEPS = 300                 # a service is decided within 3 s of the strike (else: fault)


def server_of(scores: tuple[int, int], first: int, win_points: int = 5) -> int:
    """Index (0 / 1) of the server of the next point, Law 2.13.3 scaled to a game to `win_points`: the service changes
    after every 2 points scored (lets do not count); once both have win_points - 1 (4:4, the scaled 10:10) it changes
    after every point, the sequence unchanged. scores: points of (player 0, player 1); first: who served first."""
    a, b = scores
    n = a + b
    deuce = win_points - 1
    turn = n - deuce if min(a, b) >= deuce else n // 2   # 4:4 comes after exactly 8 points (turn 4): then 1 each
    return first if turn % 2 == 0 else 1 - first


_VZ_CACHE: dict = {}


def vz_for_height(h: float) -> float:
    """The upward speed (m/s) at which a ball projected straight up with no spin rises h metres, on the simulator's
    own ball model (gravity and air drag; bisection, cached; deterministic)."""
    h = float(h)
    if h not in _VZ_CACHE:
        import rally
        bm = rally.BallModel()
        p0 = np.array([0.0, -2.6, 1.5])          # away from the table and the floor

        def rise(vz):
            P, _, _, _ = bm.rollout(p0, np.array([0.0, 0.0, vz]), np.zeros(3), 1200)
            return float(P[:, 2].max() - p0[2])
        lo, hi = 0.5, 8.0
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            lo, hi = (mid, hi) if rise(mid) < h else (lo, mid)
        _VZ_CACHE[h] = round(hi, 6)               # the smallest speed found that rises at least h
    return _VZ_CACHE[h]


def toss_problem(pos, height, base) -> str | None:
    """Why a toss is refused (its parameters break Law 2.6.1-2.6.4 or the device's reach), else None. pos and base in
    the server's own frame."""
    p = np.asarray(pos, float)
    if p.shape != (3,) or not np.all(np.isfinite(p)) or not np.isfinite(height):
        return "toss needs pos [x, y, z] and height (finite numbers)"
    if p[1] > -(END_Y + BALL_R):
        return f"the toss point must be behind your end line: y <= {-(END_Y + BALL_R):.2f} (the whole ball, Law 2.6.4)"
    if p[2] < BALL_R:
        return f"the toss point must be above the playing surface: z >= {BALL_R} (the whole ball, Law 2.6.4)"
    if p[2] > TOSS_Z_MAX:
        return f"the toss point is out of the toss device's reach: z <= {TOSS_Z_MAX}"
    if float(np.hypot(*(p[:2] - np.asarray(base, float)[:2]))) > TOSS_REACH:
        return f"the toss point is out of the toss device's reach: within {TOSS_REACH} m of your base horizontally"
    if not (H_MIN <= height <= H_MAX):
        return f"height must be in [{H_MIN}, {H_MAX}] m (Law 2.6.2: the toss rises at least 16 cm)"
    return None


def legal_before_strike(p) -> bool:
    """Law 2.6.4 on the whole ball, server's frame: above the level of the playing surface, behind the end line."""
    return bool(p[2] >= BALL_R and p[1] <= -(END_Y + BALL_R))


def towards_court(p, v, horizon_s=0.5) -> bool:
    """Whether a ball at p moving with v is over the receiver's court (y > 0, server's frame) or its straight-line path
    reaches it within horizon_s (obstruction, Law 2.5.8)."""
    for t in np.linspace(0.0, horizon_s, 26):
        x, y = p[0] + v[0] * t, p[1] + v[1] * t
        if abs(x) <= HALF_X and 0.0 <= y <= END_Y:
            return True
    return False


class ServeJudge:
    """The service from the toss to its verdict, fed with the ball's contacts in the server's frame:
    paddle_server, robot_server, paddle_receiver, robot_receiver, table_server, table_receiver (top surface only),
    table_side, net, floor, other; plus the 2.6.4 position check. verdict: None (pending), "good", "let" or
    "fault" / "obstruction" (with `why`)."""

    def __init__(self, toss_k: int):
        self.toss_k = toss_k
        self.projected = False
        self.struck = False
        self.stage = 0                 # after the strike: 0 expects the server's court, 1 the receiver's
        self.net = False
        self.verdict, self.why = None, ""
        self.code = ""                 # the fault's reason code (serve_fault:<code>; sport.toml [spec] serve)
        self.strike = None

    def _end(self, verdict, why, code=""):
        if self.verdict is None:
            self.verdict, self.why, self.code = verdict, why, code

    def position(self, p_server_frame):
        """At every physics step until the strike (Law 2.6.4)."""
        if self.verdict is None and not self.struck and not legal_before_strike(p_server_frame):
            y, z = p_server_frame[1], p_server_frame[2]
            self._end("fault", "the toss fell below the playing surface without being struck (Laws 2.6.4, 2.10.1.1)"
                      if z < BALL_R else "the ball went in front of the end line before it was struck (Law 2.6.4)"
                      if y > -(END_Y + BALL_R) else "the toss broke Law 2.6.4",
                      "dropped" if z < BALL_R else "in_front" if y > -(END_Y + BALL_R) else "position")

    def contact(self, kind, p, v_pre, k):
        if self.verdict is not None:
            return
        if not self.struck:
            if kind != "paddle_server":
                self._end("fault", f"the toss touched {kind.replace('_', ' ')} before it was struck (Law 2.6.2)", "toss_touched")
            elif not self.projected:
                self._end("fault", "the ball was struck before it was projected (Law 2.6.2)", "not_projected")
            elif v_pre[2] >= 0.0:
                self._end("fault", "the ball was struck while it was rising, not falling (Law 2.6.3)", "rising")
            else:
                self.struck = True
                self.strike = {"k": int(k), "pos": [round(float(x), 4) for x in p]}
            return
        if kind == "net":
            self.net = True
            return
        if kind == "paddle_server":
            self._end("fault", "the server struck the ball twice (Laws 2.6.3, 2.10.1.7)", "double_hit")
            return
        if kind in ("paddle_receiver", "robot_receiver"):
            if self.stage == 1 and towards_court(p, v_pre):
                self._end("let" if self.net else "obstruction",
                          "the service touched the net and the receiver obstructed it (Law 2.9.1.1)" if self.net else
                          "the receiver obstructed the service (Laws 2.5.8, 2.10.1.6)")
            else:
                self._end("fault", "the service touched the receiver's robot without bouncing on its court first "
                                   "(it was going out; Law 2.6.3)", "out")
            return
        if self.stage == 0:
            if kind == "table_server":
                self.stage = 1
                return
            self._end("fault", f"the service did not touch the server's court first ({kind.replace('_', ' ')}; Law 2.6.3)", "not_own_court")
            return
        if kind == "table_receiver":
            if float(p[1]) < SERVE_MIN_DEPTH:
                self._end("fault", f"the service bounced on the receiver's court {float(p[1]):.2f} m from the net, closer than "
                          f"{SERVE_MIN_DEPTH:.2f} m (deviation D13)", "short")
                return
            self._end("let" if self.net else "good", "the service touched the net assembly, otherwise correct: a let "
                      "(Law 2.9.1.1)" if self.net else "good service")
            return
        self._end("fault", f"after the server's court the service touched {kind.replace('_', ' ')} instead of the "
                           "receiver's court (Law 2.6.3)", "out")
