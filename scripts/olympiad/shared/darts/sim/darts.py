"""Darts, 501 double-out: board geometry and scoring, deterministic dart flight, execution scatter, the scripted
opponent (optimal-aim policy tables), the match state machines (single player: Match; two players: Duel) and the
fresh-process replay.

World frame (metres): origin on the floor at the centre of the throw line (the oche's front edge); +x towards the
board, +y to the thrower's LEFT, z up. The board face is the plane x = X_BOARD (2.37 m), the bullseye centre is at
(X_BOARD, 0, Z_BULL = 1.73). Board coordinates as the thrower sees them: u = to the right (= -y), v = up (= z - Z_BULL).

Flight (pure Python floats, fixed-step RK4, so a recorded list of commands replays bit-exactly in any process): the
dart leaves RELEASE with velocity SPEED * (cos p cos y, cos p sin y, sin p) (y = yaw, + = left; p = pitch, + = up)
and flies under gravity with quadratic air drag a = -K_DRAG |v| v (K_DRAG is fixed per match from the seed, in
[K_MIN, K_MAX], and not told to the player). It sticks where its tip reaches the board plane. Darts do not deflect
off wires or other darts (simplification); a dart outside the double ring scores 0; outside the board (r > 225 mm)
it misses the board.

Execution scatter (seeded): the executed command is (yaw + N(0, s_yaw), pitch + N(0, s_pitch), speed * (1 + N(0, s_v)))
with numpy.random.default_rng([SEED, thrower, dart_index_of_that_thrower]).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sys

import numpy as np

G = 9.81
X_BOARD = 2.37
Z_BULL = 1.73
RELEASE = (0.40, 0.0, 1.68)          # the release mechanism's release point (fixed)
DT = 0.0005
K_MIN, K_MAX = 0.02, 0.05            # drag constant range (1/m); the match's value is drawn from the seed
V_MIN, V_MAX = 4.0, 9.0              # release speed limits (m/s)
YAW_MAX, PITCH_MIN, PITCH_MAX = 20.0, -10.0, 40.0

R_BULL, R_OBULL = 0.00635, 0.0159
R_TRI_IN, R_TRI_OUT = 0.099, 0.107
R_DBL_IN, R_DBL_OUT = 0.162, 0.170
R_BOARD = 0.225
SEGMENTS = [20, 1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5]   # clockwise from the top

START = 501
LEGS_TO_WIN = 2                      # best of 3 legs (single player and duel)
MAX_VISITS = 30                      # per thrower and leg; if nobody has checked out by then, the lower remaining score wins
BASE_SEED = 5010
SEED = int(os.environ.get("MATCH_SEED", BASE_SEED))

# execution scatter (1 sigma): yaw deg, pitch deg, relative speed
PLAYER_SCATTER = {"yaw_deg": 0.35, "pitch_deg": 0.30, "speed_rel": 0.008}
LEVELS = {
    1: {"name": "L1 (pub player)", "scatter": {"yaw_deg": 1.05, "pitch_deg": 0.95, "speed_rel": 0.025}, "speed": 6.5},
    2: {"name": "L2 (county player)", "scatter": {"yaw_deg": 0.55, "pitch_deg": 0.48, "speed_rel": 0.013}, "speed": 6.5},
    3: {"name": "L3 (strong amateur)", "scatter": {"yaw_deg": 0.43, "pitch_deg": 0.37, "speed_rel": 0.010}, "speed": 6.5},
    4: {"name": "L4 (near your level)", "scatter": {"yaw_deg": 0.38, "pitch_deg": 0.33, "speed_rel": 0.009}, "speed": 6.5},
}
HERE = os.path.dirname(os.path.abspath(__file__))


def k_drag(seed: int = None) -> float:
    rng = np.random.default_rng([SEED if seed is None else seed, 777])
    return round(float(K_MIN + (K_MAX - K_MIN) * rng.uniform()), 4)


# ---------------------------------------------------------------------------------------------------- scoring
def score_uv(u: float, v: float) -> dict:
    """The bed a dart tip at board coordinates (u right, v up; metres) lands in."""
    r = math.hypot(u, v)
    if r > R_BOARD:
        return {"value": 0, "double": False, "ring": "off", "number": 0, "call": "no score (missed the board)"}
    if r <= R_BULL:
        return {"value": 50, "double": True, "ring": "bull", "number": 25, "call": "bull (50)"}
    if r <= R_OBULL:
        return {"value": 25, "double": False, "ring": "outer_bull", "number": 25, "call": "25 (outer bull)"}
    if r > R_DBL_OUT:
        return {"value": 0, "double": False, "ring": "outside", "number": 0, "call": "no score (outside the doubles)"}
    th = math.degrees(math.atan2(u, v)) % 360.0
    n = SEGMENTS[int(((th + 9.0) % 360.0) // 18.0) % 20]
    if R_TRI_IN <= r <= R_TRI_OUT:
        return {"value": 3 * n, "double": False, "ring": "treble", "number": n, "call": f"treble {n}"}
    if R_DBL_IN <= r:
        return {"value": 2 * n, "double": True, "ring": "double", "number": n, "call": f"double {n}"}
    return {"value": n, "double": False, "ring": "single", "number": n, "call": f"single {n}"}


# outcome classes for the aim planner: 0 miss, 1..20 singles, 21..40 doubles, 41..60 trebles, 61 outer bull, 62 bull
OUT_VAL = np.array([0] + list(range(1, 21)) + [2 * n for n in range(1, 21)] + [3 * n for n in range(1, 21)] + [25, 50])
OUT_DBL = np.array([False] * 21 + [True] * 20 + [False] * 21 + [True])
SEG_ARR = np.array(SEGMENTS)


def outcome_np(u: np.ndarray, v: np.ndarray) -> np.ndarray:
    r = np.hypot(u, v)
    th = np.degrees(np.arctan2(u, v)) % 360.0
    n = SEG_ARR[(((th + 9.0) % 360.0) // 18.0).astype(int) % 20]
    o = n.copy()                                           # single
    o = np.where((r >= R_TRI_IN) & (r <= R_TRI_OUT), 40 + n, o)
    o = np.where((r >= R_DBL_IN) & (r <= R_DBL_OUT), 20 + n, o)
    o = np.where(r > R_DBL_OUT, 0, o)
    o = np.where(r <= R_OBULL, 61, o)
    o = np.where(r <= R_BULL, 62, o)
    return o


# ---------------------------------------------------------------------------------------------------- flight
def _acc(vx, vy, vz, k):
    s = math.sqrt(vx * vx + vy * vy + vz * vz)
    return -k * s * vx, -k * s * vy, -G - k * s * vz


def fly(yaw_deg: float, pitch_deg: float, speed: float, k: float, trail: bool = False) -> dict:
    """Integrate the flight from RELEASE until the tip reaches the board plane (or the floor)."""
    y, p = math.radians(yaw_deg), math.radians(pitch_deg)
    x, yy, z = RELEASE
    vx, vy, vz = speed * math.cos(p) * math.cos(y), speed * math.cos(p) * math.sin(y), speed * math.sin(p)
    t = 0.0
    pts = [(0.0, x, yy, z)] if trail else None
    for _ in range(40000):
        a1 = _acc(vx, vy, vz, k)
        v2 = (vx + 0.5 * DT * a1[0], vy + 0.5 * DT * a1[1], vz + 0.5 * DT * a1[2])
        a2 = _acc(*v2, k)
        v3 = (vx + 0.5 * DT * a2[0], vy + 0.5 * DT * a2[1], vz + 0.5 * DT * a2[2])
        a3 = _acc(*v3, k)
        v4 = (vx + DT * a3[0], vy + DT * a3[1], vz + DT * a3[2])
        a4 = _acc(*v4, k)
        nx = x + DT / 6.0 * (vx + 2 * v2[0] + 2 * v3[0] + v4[0])
        ny = yy + DT / 6.0 * (vy + 2 * v2[1] + 2 * v3[1] + v4[1])
        nz = z + DT / 6.0 * (vz + 2 * v2[2] + 2 * v3[2] + v4[2])
        nvx = vx + DT / 6.0 * (a1[0] + 2 * a2[0] + 2 * a3[0] + a4[0])
        nvy = vy + DT / 6.0 * (a1[1] + 2 * a2[1] + 2 * a3[1] + a4[1])
        nvz = vz + DT / 6.0 * (a1[2] + 2 * a2[2] + 2 * a3[2] + a4[2])
        if nx >= X_BOARD:
            f = (X_BOARD - x) / (nx - x)
            hy, hz = yy + f * (ny - yy), z + f * (nz - z)
            hv = (vx + f * (nvx - vx), vy + f * (nvy - vy), vz + f * (nvz - vz))
            t += f * DT
            if trail:
                pts.append((t, X_BOARD, hy, hz))
            return {"hit": "board", "y": hy, "z": hz, "u": -hy, "v": hz - Z_BULL, "t": t, "vel": hv, "trail": pts}
        if nz <= 0.0 or nvx <= 0.0:
            return {"hit": "floor", "y": ny, "z": 0.0, "u": 99.0, "v": -99.0, "t": t + DT, "vel": (nvx, nvy, nvz),
                    "trail": pts, "x": nx}
        x, yy, z, vx, vy, vz = nx, ny, nz, nvx, nvy, nvz
        t += DT
        if trail and (len(pts) == 0 or t - pts[-1][0] >= 0.01 - 1e-12):
            pts.append((t, x, yy, z))
    raise RuntimeError("flight did not end")


def aim_command(u: float, v: float, speed: float, k: float) -> tuple[float, float]:
    """(yaw, pitch) in degrees that land a dart released at `speed` on board point (u, v) (noise-free, Newton)."""
    y = math.degrees(math.atan2(-u, X_BOARD - RELEASE[0]))
    p = 10.0
    for _ in range(30):
        f = fly(y, p, speed, k)
        eu, ev = u - f["u"], v - f["v"]
        if abs(eu) < 1e-7 and abs(ev) < 1e-7:
            break
        h = 1e-4
        fy, fp = fly(y + h, p, speed, k), fly(y, p + h, speed, k)
        j11, j12 = (fy["u"] - f["u"]) / h, (fp["u"] - f["u"]) / h
        j21, j22 = (fy["v"] - f["v"]) / h, (fp["v"] - f["v"]) / h
        det = j11 * j22 - j12 * j21
        y += (j22 * eu - j12 * ev) / det
        p += (-j21 * eu + j11 * ev) / det
    return y, p


def jitter(cmd: tuple[float, float, float], scatter: dict, seed: int, who: int, idx: int) -> tuple[float, float, float]:
    z = np.random.default_rng([seed, who, idx]).standard_normal(3)
    return (cmd[0] + scatter["yaw_deg"] * float(z[0]), cmd[1] + scatter["pitch_deg"] * float(z[1]),
            cmd[2] * (1.0 + scatter["speed_rel"] * float(z[2])))


def board_cov(scatter: dict, speed: float, k: float) -> np.ndarray:
    """Linearised 2x2 covariance of the landing point (u, v) for a thrower's scatter at `speed` (aim at the bull)."""
    y0, p0 = aim_command(0.0, 0.0, speed, k)
    f0 = fly(y0, p0, speed, k)
    J = np.zeros((2, 3))
    for i, (dy, dp, dv) in enumerate(((1e-3, 0, 0), (0, 1e-3, 0), (0, 0, 1e-4 * speed))):
        f = fly(y0 + dy, p0 + dp, speed + dv, k)
        h = dy or dp or dv
        J[0, i], J[1, i] = (f["u"] - f0["u"]) / h, (f["v"] - f0["v"]) / h
    S = np.diag([scatter["yaw_deg"] ** 2, scatter["pitch_deg"] ** 2, (scatter["speed_rel"] * speed) ** 2])
    return J @ S @ J.T


# ---------------------------------------------------------------------------------------------------- aim policy
def build_policy(cov: np.ndarray, grid_mm: float = 4.0, n_samples: int = 3000) -> dict:
    """Optimal aim for every (remaining, darts left in the visit) state, for a thrower whose landing scatter is
    Gaussian with covariance `cov` (the optimal-aim idea of Tibshirani, Price & Taylor 2011, "A statistician plays
    darts", extended from max expected score to min expected visits to check out, double-out and bust rules
    included; a bust is treated as returning to the current score). Deterministic (fixed quasi-sample set)."""
    L = np.linalg.cholesky(cov)
    z = np.random.default_rng(12345).standard_normal((n_samples, 2))
    off = z @ L.T
    g = np.arange(-0.180, 0.180 + 1e-9, grid_mm / 1000.0)
    A = np.array([(a, b) for a in g for b in g if math.hypot(a, b) <= 0.180])
    P = np.zeros((len(A), 63))
    for i0 in range(0, len(A), 256):
        a = A[i0:i0 + 256]
        o = outcome_np(a[:, None, 0] + off[None, :, 0], a[:, None, 1] + off[None, :, 1])
        for j in range(len(a)):
            P[i0 + j] = np.bincount(o[j], minlength=63) / n_samples
    W = np.zeros(START + 1)
    Gd = np.zeros((START + 1, 4))
    pol = {}
    for r in range(2, START + 1):
        nr = r - OUT_VAL
        fin = (nr == 0) & OUT_DBL
        bust = (nr < 2) & ~fin
        ok = ~fin & ~bust
        nrc = np.where(ok, nr, 0)
        w = W[r - 1] + 1.0 if r > 2 else 5.0
        for _ in range(200):
            W[r] = w
            best = {}
            for d in (1, 2, 3):
                nxt = W[nrc] if d == 1 else Gd[nrc, d - 1]
                c = np.where(fin, 0.0, np.where(bust, w, nxt))
                if d > 1:
                    c = np.where(ok & (nr == r), Gd[r, d - 1], c)
                ev = P @ c
                i = int(np.argmin(ev))
                Gd[r, d] = ev[i]
                best[d] = i
            w_new = 1.0 + Gd[r, 3]
            if abs(w_new - w) < 1e-10:
                w = w_new
                break
            w = w_new
        W[r] = w
        for d in (1, 2, 3):
            a = A[best[d]]
            pol[f"{r},{d}"] = [round(float(a[0]), 4), round(float(a[1]), 4)]
    return {"policy": pol, "expected_visits": {str(r): round(float(W[r]), 4) for r in range(2, START + 1)},
            "cov": cov.tolist(), "grid_mm": grid_mm, "n_samples": n_samples}


_POL = {}


def policy(level: int) -> dict:
    if level not in _POL:
        _POL[level] = json.load(open(os.path.join(HERE, f"policy_l{level}.json")))["policy"]
    return _POL[level]


# ---------------------------------------------------------------------------------------------------- match
WHO = {0: "you", 1: "opponent"}


class Match:
    """Best of 3 legs of 501 double-out against the scripted opponent, 3 darts per visit, players alternate visits.
    The opponent throws first in legs 1 and 3, the player in leg 2 (as in Duel). A leg nobody has checked out after
    MAX_VISITS visits each goes to the lower remaining score; if level, the opponent wins it (the last-resort rule: more
    chess-clock time left; the scripted opponent uses no clock time)."""

    def __init__(self, level: int = 1, seed: int = None):
        self.level = level
        self.seed = SEED if seed is None else seed
        self.k = k_drag(self.seed)
        self.L = LEVELS[level]
        self.legs = [0, 0]
        self.leg = 0
        self.leg_results = []
        self.ndarts = [0, 0]                  # over the match (the scatter draws continue across legs)
        self.visits = []                      # finished visits
        self.done = False
        self.winner = None
        self.reason = None
        self.forfeit = False
        self.decisions = []                   # the player's commands (the replayable record)
        self.log = []                         # every dart
        self._new_leg()

    def _new_leg(self):
        self.leg += 1
        self.starter = 1 if self.leg % 2 == 1 else 0       # the opponent throws first in legs 1 and 3
        self.turn = self.starter
        self.rem = [START, START]
        self.nvisits = [0, 0]                 # in this leg
        self._new_visit()

    # --- visits
    def _new_visit(self):
        self.visit = {"who": self.turn, "leg": self.leg, "start": self.rem[self.turn], "darts": [], "bust": False,
                      "checkout": False, "n": self.nvisits[self.turn] + 1}

    def darts_left(self) -> int:
        return 3 - len(self.visit["darts"])

    def _end_leg(self, winner: int, how: str):
        self.legs[winner] += 1
        self.leg_results.append({"leg": self.leg, "starter": WHO[self.starter], "winner": WHO[winner], "how": how,
                                 "remaining": {"you": self.rem[0], "opponent": self.rem[1]}})
        if self.legs[winner] >= LEGS_TO_WIN:
            self.done, self.winner, self.reason = True, winner, "match_over"
        else:
            self._new_leg()

    def _end_visit(self):
        v = self.visit
        who = v["who"]
        v["scored"] = 0 if v["bust"] else v["start"] - self.rem[who]
        v["remaining"] = self.rem[who]
        self.visits.append(v)
        self.nvisits[who] += 1
        self.turn = 1 - who
        if v["checkout"]:
            self._end_leg(who, "checkout")
        elif self.nvisits[0] >= MAX_VISITS and self.nvisits[1] >= MAX_VISITS:
            a, b = self.rem
            # level at the cap: the last-resort rule (more chess-clock time left) gives the leg to the opponent, which
            # uses no clock time
            self._end_leg(0 if a < b else 1, "visit_cap" if a != b else "visit_cap_clock")
        else:
            self._new_visit()
        return v

    def _throw(self, who: int, cmd: tuple[float, float, float], aim=None) -> dict:
        """With `who` on the oche: execute cmd (with scatter), score it, update the visit. Returns the dart record."""
        ex = jitter(cmd, PLAYER_SCATTER if who == 0 else self.L["scatter"], self.seed, who, self.ndarts[who])
        self.ndarts[who] += 1
        f = fly(ex[0], ex[1], ex[2], self.k)
        s = score_uv(f["u"], f["v"]) if f["hit"] == "board" else {"value": 0, "double": False, "ring": "floor",
                                                                 "number": 0, "call": "no score (missed the board)"}
        before = self.rem[who]
        after = before - s["value"]
        rec = {"who": who, "leg": self.leg, "visit": self.visit["n"], "dart": len(self.visit["darts"]) + 1, "cmd": list(cmd),
               "executed": list(ex), "hit": f["hit"], "u": f["u"], "v": f["v"], "vel": list(f["vel"]),
               "t_flight": f["t"], "value": s["value"], "double": s["double"], "ring": s["ring"], "call": s["call"],
               "before": before, "aim": aim}
        if after == 0 and s["double"]:
            self.rem[who] = 0
            rec["event"] = "game shot"
            self.visit["checkout"] = True
        elif after < 2:
            rec["event"] = "bust"
            self.rem[who] = self.visit["start"]
            self.visit["bust"] = True
        else:
            self.rem[who] = after
        rec["after"] = self.rem[who]
        self.visit["darts"].append(rec)
        self.log.append(rec)
        if self.visit["bust"] or self.visit["checkout"] or len(self.visit["darts"]) == 3:
            rec["visit_over"] = True
            leg = self.leg
            self._end_visit()
            rec["leg_over"] = self.leg != leg or self.done
        return rec

    def player_throw(self, yaw: float, pitch: float, speed: float) -> dict:
        assert not self.done and self.turn == 0
        self.decisions.append({"yaw": yaw, "pitch": pitch, "speed": speed})
        return self._throw(0, (yaw, pitch, speed))

    def opponent_command(self):
        aim = policy(self.level)[f"{self.rem[1]},{self.darts_left()}"]
        y, p = aim_command(aim[0], aim[1], self.L["speed"], self.k)
        return (y, p, self.L["speed"]), aim

    def run_to_decision(self) -> list[dict]:
        """Let the opponent throw until it is the player's turn (or the match is over)."""
        recs = []
        while not self.done and self.turn == 1:
            cmd, aim = self.opponent_command()
            recs.append(self._throw(1, cmd, aim))
        return recs

    def player_forfeit(self):
        """The player's clock ran out (or it stopped playing): the match is lost."""
        self.forfeit = True
        self.done, self.winner, self.reason = True, 1, "clock"

    def replay(self, decisions: list[dict], forfeit: bool = False) -> None:
        self.run_to_decision()
        for d in decisions:
            if self.done:
                break
            self.player_throw(d["yaw"], d["pitch"], d["speed"])
            self.run_to_decision()
        if forfeit and not self.done:
            self.player_forfeit()

    def state_sha(self) -> str:
        s = repr([(r["who"], r["leg"], r["u"], r["v"], r["value"], r["after"]) for r in self.log]) + repr(
            (self.legs, self.rem, self.winner, self.reason))
        return hashlib.sha256(s.encode()).hexdigest()

    def stats(self, who: int) -> dict:
        darts = [r for r in self.log if r["who"] == who]
        vis = [v for v in self.visits if v["who"] == who]
        pts = sum(v["scored"] for v in vis)
        opp = [r for r in darts if (r["before"] <= 40 and r["before"] % 2 == 0) or r["before"] == 50]
        return {"legs": self.legs[who], "darts": len(darts), "visits": len(vis), "points": pts,
                "three_dart_avg": round(3.0 * pts / len(darts), 2) if darts else 0.0,
                "points_per_dart": round(pts / len(darts), 3) if darts else 0.0,
                "first9_avg": round(sum(v["scored"] for v in vis[:3]) / max(1, min(3, len(vis))), 2),
                "busts": sum(1 for v in vis if v["bust"]), "trebles": sum(1 for r in darts if r["ring"] == "treble"),
                "doubles_hit": sum(1 for r in darts if r["ring"] in ("double", "bull")),
                "no_score_darts": sum(1 for r in darts if r["value"] == 0),
                "checkout_opportunities": len(opp), "checkouts": sum(1 for v in vis if v["checkout"]),
                "tons": sum(1 for v in vis if v["scored"] >= 100),
                "max_visit": max([v["scored"] for v in vis] or [0])}


# ---------------------------------------------------------------------------------------------------- duel
SEATS = ("A", "B")
OTHER = {"A": "B", "B": "A"}


class Duel:
    """Two players (seats A and B), 501 double-out, best of 3 legs, alternate visits of 3 darts. FIRST throws first
    in legs 1 and 3, the other seat in leg 2. Both players have the same release mechanism and scatter, the same drag
    constant and the same scatter draws (common random numbers: the n-th dart of either player in a leg scatters
    alike, numpy.random.default_rng([SEED, 100 + leg, n])). A leg not checked out after MAX_VISITS visits each goes
    to the lower remaining score; if level, to the player with more chess-clock time left (the last-resort rule)."""

    def __init__(self, seed: int, first: str):
        assert first in SEATS
        self.seed, self.first = int(seed), first
        self.k = k_drag(self.seed)
        self.legs = {s: 0 for s in SEATS}
        self.leg = 0
        self.leg_results = []
        self.done = False
        self.winner = None
        self.reason = None
        self.forfeit = None                  # (seat, why) when a player lost by clock / abandonment
        self.clock_left = None
        self.decisions = []                  # replayable record: {"seat", "yaw", "pitch", "speed"}
        self.log = []                        # every dart
        self.visits = []
        self._new_leg()

    def _new_leg(self):
        self.leg += 1
        self.starter = self.first if self.leg % 2 == 1 else OTHER[self.first]
        self.turn = self.starter
        self.rem = {s: START for s in SEATS}
        self.ndarts = {s: 0 for s in SEATS}
        self.nvisits = {s: 0 for s in SEATS}
        self._new_visit()

    def _new_visit(self):
        self.visit = {"seat": self.turn, "leg": self.leg, "start": self.rem[self.turn], "darts": [], "bust": False,
                      "checkout": False, "n": self.nvisits[self.turn] + 1}

    def darts_left(self) -> int:
        return 3 - len(self.visit["darts"])

    def _end_leg(self, winner: str, why: str):
        self.legs[winner] += 1
        self.leg_results.append({"leg": self.leg, "starter": self.starter, "winner": winner, "how": why,
                                 "remaining": dict(self.rem)})
        if self.legs[winner] >= LEGS_TO_WIN:
            self.done, self.winner, self.reason = True, winner, "match_over"
        else:
            self._new_leg()

    def _end_visit(self):
        v = self.visit
        seat = v["seat"]
        v["scored"] = 0 if v["bust"] else v["start"] - self.rem[seat]
        v["remaining"] = self.rem[seat]
        self.visits.append(v)
        self.nvisits[seat] += 1
        self.turn = OTHER[seat]
        if v["checkout"]:
            self._end_leg(seat, "checkout")
        elif self.nvisits["A"] >= MAX_VISITS and self.nvisits["B"] >= MAX_VISITS:
            a, b = self.rem["A"], self.rem["B"]
            if a != b:
                self._end_leg("A" if a < b else "B", "visit_cap")
            else:                                        # level at the cap: more chess-clock time left wins
                c = self.clock_left or {}
                ca, cb = c.get("A", 0.0), c.get("B", 0.0)       # recorded with the throw (exact on replay)
                self._end_leg("A" if ca > cb else "B" if cb > ca else OTHER[self.starter], "visit_cap_clock")
        else:
            self._new_visit()

    def throw(self, seat: str, yaw: float, pitch: float, speed: float, clock_left: dict | None = None) -> dict:
        """clock_left: both players' chess-clock time left (s) when the dart is thrown, recorded with it; it decides
        a leg level at the visit cap (the last-resort rule)."""
        assert not self.done and seat == self.turn, (seat, self.turn)
        d = {"seat": seat, "yaw": yaw, "pitch": pitch, "speed": speed}
        if clock_left is not None:
            d["clock_left_s"] = {k: round(float(v), 3) for k, v in clock_left.items()}
        self.decisions.append(d)
        self.clock_left = d.get("clock_left_s")
        z = np.random.default_rng([self.seed, 100 + self.leg, self.ndarts[seat]]).standard_normal(3)
        sc = PLAYER_SCATTER
        ex = (yaw + sc["yaw_deg"] * float(z[0]), pitch + sc["pitch_deg"] * float(z[1]),
              speed * (1.0 + sc["speed_rel"] * float(z[2])))
        self.ndarts[seat] += 1
        f = fly(ex[0], ex[1], ex[2], self.k)
        s = score_uv(f["u"], f["v"]) if f["hit"] == "board" else {"value": 0, "double": False, "ring": "floor",
                                                                 "number": 0, "call": "no score (missed the board)"}
        before = self.rem[seat]
        after = before - s["value"]
        rec = {"seat": seat, "leg": self.leg, "visit": self.visit["n"], "dart": len(self.visit["darts"]) + 1,
               "cmd": [yaw, pitch, speed], "executed": list(ex), "hit": f["hit"], "u": f["u"], "v": f["v"],
               "vel": list(f["vel"]), "t_flight": f["t"], "value": s["value"], "double": s["double"],
               "ring": s["ring"], "call": s["call"], "before": before}
        if after == 0 and s["double"]:
            self.rem[seat] = 0
            rec["event"] = "game shot"
            self.visit["checkout"] = True
        elif after < 2:
            rec["event"] = "bust"
            self.rem[seat] = self.visit["start"]
            self.visit["bust"] = True
        else:
            self.rem[seat] = after
        rec["after"] = self.rem[seat]
        self.visit["darts"].append(rec)
        self.log.append(rec)
        if self.visit["bust"] or self.visit["checkout"] or len(self.visit["darts"]) == 3:
            rec["visit_over"] = True
            leg = self.leg
            self._end_visit()
            rec["leg_over"] = self.leg != leg or self.done
        return rec

    def lose(self, seat: str, why: str):
        """`seat` loses the match (its clock ran out, or it stopped playing on its turn)."""
        if not self.done:
            self.forfeit = {"seat": seat, "why": why}
            self.decisions.append({"seat": seat, "forfeit": why})
            self.done, self.winner, self.reason = True, OTHER[seat], why

    def replay(self, decisions: list) -> None:
        for d in decisions:
            if "forfeit" in d:
                self.lose(d["seat"], d["forfeit"])
            else:
                self.throw(d["seat"], d["yaw"], d["pitch"], d["speed"], d.get("clock_left_s"))

    def state_sha(self) -> str:
        s = repr([(r["seat"], r["leg"], r["u"], r["v"], r["value"], r["after"]) for r in self.log]) + repr(
            (self.legs, self.rem, self.winner, self.reason, self.forfeit))
        return hashlib.sha256(s.encode()).hexdigest()

    def stats(self, seat: str) -> dict:
        darts = [r for r in self.log if r["seat"] == seat]
        vis = [v for v in self.visits if v["seat"] == seat]
        pts = sum(v["scored"] for v in vis)
        return {"legs": self.legs[seat], "darts": len(darts), "visits": len(vis),
                "three_dart_avg": round(3.0 * pts / len(darts), 2) if darts else 0.0,
                "busts": sum(1 for v in vis if v["bust"]), "trebles": sum(1 for r in darts if r["ring"] == "treble"),
                "checkouts": sum(1 for v in vis if v["checkout"])}


def main():
    if sys.argv[1] == "replay_duel":
        tr = json.load(open(sys.argv[2]))
        m = Duel(tr["seed"], tr["first_player"])
        m.replay(tr["decisions"])
        print(json.dumps({"sha": m.state_sha(), "legs": m.legs, "rem": m.rem, "winner": m.winner, "reason": m.reason,
                          "done": m.done, "n_darts": len(m.log)}))
    elif sys.argv[1] == "replay":
        tr = json.load(open(sys.argv[2]))
        m = Match(tr["level"], tr["seed"])
        m.replay(tr["decisions"], tr.get("forfeit", False))
        print(json.dumps({"sha": m.state_sha(), "legs": m.legs, "rem": m.rem, "winner": m.winner, "reason": m.reason,
                          "done": m.done, "n_darts": len(m.log)}))
    elif sys.argv[1] == "policy":          # python3 darts.py policy LEVEL|player OUT.json
        who = sys.argv[2]
        sc, sp = (PLAYER_SCATTER, 7.0) if who == "player" else (LEVELS[int(who)]["scatter"], LEVELS[int(who)]["speed"])
        cov = board_cov(sc, sp, 0.5 * (K_MIN + K_MAX))
        out = build_policy(cov)
        out["scatter"], out["speed"] = sc, sp
        json.dump(out, open(sys.argv[3], "w"))
        print(who, "sigma_u,v mm", np.sqrt(np.diag(cov)) * 1000, "E[visits from 501]", out["expected_visits"]["501"])


if __name__ == "__main__":
    main()
