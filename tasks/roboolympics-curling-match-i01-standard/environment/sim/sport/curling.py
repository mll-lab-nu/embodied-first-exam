"""Curling physics, rules, scripted opponent and match state (pure Python, deterministic).

Ice model: a faithful port of DigitalCurling's "FCV1" simulator (digitalcurling/DigitalCurling,
src/simulator/src/fcv1/simulator_fcv1.cpp, MIT; Uehara & Ito, "Improving the Digital Curling simulator towards
real data", IPSJ GI-46(18), 2021), step 1 ms:
  longitudinal deceleration  a(v) = (0.00200985 / (v + 0.06385782) + 0.00626286) * 9.80665          [m/s^2]
  curl (the velocity direction turns at)  yaw rate = sign(omega) * 0.00820 * v^-0.8                  [rad/s]
  spin decay  d|omega|/dt = -0.025 / max(v, 0.001)                                                  [rad/s^2]
Stone-stone collisions: FCV1 hands them to Box2D (circles, restitution 1, friction 0.2). Box2D is not used here;
collisions are an equivalent impulse model written out below (equal masses, solid-disc inertia, restitution 1,
Coulomb friction 0.2 on the contact's tangential slip, which also transfers spin).

Coordinates (DigitalCurling's): metres; the release point (the hack) is the origin, +y runs down the sheet towards
the house, +x is to the right as seen from the hack. Far hog line y = 32.004, tee line 38.405 (tee (0, 38.405)),
back line 40.234, house radius 1.829, sheet |x| <= 2.375, stone radius 0.145.

Hidden ice (revision curling-3, 2026-10-11): the deceleration is a(v) times the ice's deceleration scale kd, the same
for both teams and fixed for a match, drawn per match seed from KD_RANGE (plugin.ice_kd: core.rng stream "ice"); the
players are told the law and the range, not kd. kd = 1 is the FCV1 ice above. The scripted team plays on the true ice
(sport.toml deviation D8).

Everything is plain Python floats with a fixed operation order, so a match replays bit-exactly in a fresh process.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os

import numpy as np

DT = 0.001
G = 9.80665
R = 0.145                 # stone radius
MASS = 19.96
INERTIA = 0.5 * MASS * R * R
RESTITUTION = 1.0
FRICTION = 0.2
HOG_Y = 32.004
TEE_Y = 38.405
BACK_Y = 40.234
HOUSE_R = 1.829
HALF_W = 2.375
TEE = (0.0, TEE_Y)
SPIN_W = math.pi / 2      # |omega| at release (as DigitalCurling)
V_MIN, V_MAX = 0.5, 4.0
ANGLE_MAX_DEG = 5.0

N_STONES = 5              # per team per end
N_ENDS = 4
MAX_EXTRA_ENDS = 3        # a tie after the regulation ends: extra ends until a team scores, at most 3; then the
                          # chess clocks decide (the service calls resolve_tiebreak())
FGZ_STONES = 5            # WCF R6(b) five-rock rule: before the 6th stone of an end

KD_RANGE = (0.97, 1.03)   # the ice's deceleration scale kd, uniform in this range per match (hidden; curling-3)

# execution noise (seeded per throw): release speed [m/s] and direction [deg]
PLAYER_NOISE = {"speed": 0.004, "angle_deg": 0.03}
LEVELS = {   # seed: the level's default instance; MATCH_SEED (env) selects another instance of the same level
    1: {"seed": 7101, "speed": 0.020, "angle_deg": 0.08, "guards": False},
    # curling-4 (2026-10-12): level 2 is level 3's planner with a larger execution error (until curling-3 it was
    # level 1's one-step greedy plan with more candidates, which a takeout-only program beat 16 times in 20)
    2: {"seed": 7202, "speed": 0.010, "angle_deg": 0.05, "guards": True, "lookahead": True,
        "plies": 2, "top": 3, "reply": "greedy", "phi0": 0.3, "w_close": 0.2, "w_guard": 0.3, "w_house": 0.1},
    3: {"seed": 7303, "speed": 0.006, "angle_deg": 0.035, "guards": True, "lookahead": True,    # curling-3
        "plies": 2, "top": 3, "reply": "greedy", "phi0": 0.3, "w_close": 0.2, "w_guard": 0.3, "w_house": 0.1},
}


def accel(v: float) -> float:
    return -(0.00200985 / (v + 0.06385782) + 0.00626286) * G


# ----------------------------------------------------------------------------------------------------- physics
class Sheet:
    """Stones in play: a list of dicts {id, team, x, y, vx, vy, w, a}; team 0 = the player (yellow), 1 = opponent (red).
    kd: the ice's deceleration scale (1.0 = the FCV1 ice)."""

    def __init__(self, kd: float = 1.0):
        self.stones: list[dict] = []
        self.kd = float(kd)

    def copy(self) -> "Sheet":
        s = Sheet(self.kd)
        s.stones = [dict(st) for st in self.stones]
        return s

    def positions(self) -> list[tuple[int, int, float, float]]:
        return [(st["id"], st["team"], st["x"], st["y"]) for st in self.stones]

    def throw(self, sid: int, team: int, v0: float, angle_deg: float, spin: str, frame_every: float | None = None,
              max_t: float = 120.0, fast: bool = False) -> dict:
        """Release stone `sid` from the hack and simulate until everything stops. Returns events and (optional)
        frames: [(t, [(id, team, x, y, a), ...])] every `frame_every` s of simulated time. `fast` (planning copies
        of the scripted team only, never a real throw): the stone's free flight is read off the master path of its
        spin (see _fly) up to the first possible contact, and only the rest is stepped; "t" then counts the stepped
        part only."""
        th = math.radians(angle_deg)
        w0 = SPIN_W if spin == "ccw" else -SPIN_W
        st = {"id": sid, "team": team, "x": 0.0, "y": 0.0, "vx": v0 * math.sin(th), "vy": v0 * math.cos(th),
              "w": w0, "a": 0.0}
        self.stones.append(st)
        ev = {"collisions": 0, "removed": [], "t": 0.0}
        frames = []
        touched = set()
        if fast and frame_every is None:
            self._fly(st, v0, th, spin)
        k = self._run(ev, touched, frame_every, frames, max_t)
        ev["t"] = round(k * DT, 3)
        # at rest (WCF R2(f)): the delivered stone is removed if it has not come to rest completely beyond the far hog
        # line, unless it struck another stone (then it stays in play); stones it moved are never removed for that
        struck = any(sid in key for key in touched)
        if st in self.stones and st["y"] < HOG_Y + R and not struck:
            self.stones.remove(st)
            ev["removed"].append((st["id"], "hog line"))
        ev["struck"] = struck
        if frame_every is not None:
            frames.append((ev["t"], [(s["id"], s["team"], s["x"], s["y"], s["a"]) for s in self.stones]))
        ev["frames"] = frames
        return ev

    def in_fgz(self, s: dict) -> bool:
        """WCF R6(a): between the hog line and the tee line, excluding the house (stones still in play short of the hog
        line after striking stones are in the zone too)."""
        return s["y"] < TEE_Y and not in_house(s["x"], s["y"])

    def throw_rules(self, sid: int, team: int, v0: float, angle_deg: float, spin: str, fgz: bool,
                    frame_every: float | None = None, fast: bool = False) -> dict:
        """throw() with the free guard zone rule (WCF R6(b)) when `fgz`: if the delivered stone moves an opposition
        stone from the zone out of play (directly or indirectly), the delivered stone is removed and every moved stone
        is put back where it was."""
        before = [dict(st) for st in self.stones]
        guards = {st["id"] for st in self.stones if st["team"] != team and self.in_fgz(st)} if fgz else set()
        ev = self.throw(sid, team, v0, angle_deg, spin, frame_every=frame_every, fast=fast)
        left = {st["id"] for st in self.stones}
        if guards - left:
            self.stones = before
            ev["removed"] = [(sid, "free guard zone violation: an opposition guard was moved out of play")]
            ev["fgz_violation"] = True
            if frame_every is not None:
                ev["frames"].append((ev["t"], [(st["id"], st["team"], st["x"], st["y"], st["a"]) for st in self.stones]))
        return ev

    def _run(self, ev: dict, touched: set, frame_every: float | None = None, frames: list | None = None,
             max_t: float = 120.0) -> int:
        """Step until every stone is at rest (or max_t); returns the number of steps."""
        every = None if frame_every is None else int(round(frame_every / DT))
        k = 0
        while True:
            if every is not None and k % every == 0:
                frames.append((round(k * DT, 3), [(s["id"], s["team"], s["x"], s["y"], s["a"]) for s in self.stones]))
            moving = [s for s in self.stones if s["vx"] != 0.0 or s["vy"] != 0.0]
            if not moving or k * DT > max_t:
                break
            self._step(moving, ev, touched)
            k += 1
        return k

    def _fly(self, st: dict, v0: float, th: float, spin: str) -> None:
        """Planning shortcut: a lone stone on the ice follows the master path of its spin from the moment its speed
        is v0, rotated to its heading (Master). Move `st` along that path (sampled every 10 steps, at most 4 cm apart)
        up to the last sample before it comes within 0.1 m of touching a stone, the side line or the back line (from
        there it is stepped), or to its rest point if nothing is in the way. Approximate (the path's speed grid, the
        spin's decay since release; a few mm at rest): planning only."""
        m = master(spin, self.kd)
        k = min(int(np.searchsorted(m.S, v0)), len(m.S) - 1)
        if k < 2:
            return
        idx = np.arange(k, -1, -10)
        if idx[-1] != 0:
            idx = np.append(idx, 0)
        dx, dy = m.X[idx] - m.X[k], m.Y[idx] - m.Y[k]
        c, s_ = math.cos(m.H[k]), math.sin(m.H[k])
        lx, ly = dx * c - dy * s_, dx * s_ + dy * c
        ct, sn = math.cos(th), math.sin(th)
        px, py = lx * ct + ly * sn, -lx * sn + ly * ct
        reach = 2 * R + 0.1
        bad = (np.abs(px) + R >= HALF_W - 0.1) | (py - R > BACK_Y - 0.1)
        for o in self.stones:
            if o is not st:
                bad |= (px - o["x"]) ** 2 + (py - o["y"]) ** 2 < reach * reach
        hit = np.flatnonzero(bad)
        j = int(hit[0]) - 1 if hit.size else len(idx) - 1
        if j <= 0:
            return
        i = int(idx[j])
        st["x"], st["y"] = float(px[j]), float(py[j])
        if i == 0:                                  # at rest
            st["vx"] = st["vy"] = st["w"] = 0.0
            return
        h = th + float(m.H[i] - m.H[k])
        v = float(m.S[i])
        st["vx"], st["vy"] = v * math.sin(h), v * math.cos(h)
        decay = float(np.sum(0.025 / np.maximum(m.S[i + 1:k + 1], 0.001))) * DT
        st["w"] = max(SPIN_W - decay, 0.0) * (1.0 if spin == "ccw" else -1.0)

    def _step(self, moving: list[dict], ev: dict, touched: set) -> None:
        kd = self.kd
        for s in moving:
            vx, vy, w = s["vx"], s["vy"], s["w"]
            v = math.sqrt(vx * vx + vy * vy)
            if v > 1e-12:
                nv = v + accel(v) * kd * DT
                if nv <= 0.0:
                    s["vx"] = s["vy"] = 0.0
                    s["w"] = 0.0        # a stopped stone's spin dies within ~0.1 s in FCV1; zeroed at once here
                else:
                    ex, ey = vx / v, vy / v
                    yaw = (0.0 if abs(w) <= 1e-12 else (1.0 if w > 0 else -1.0) * 0.00820 * v ** -0.8) * DT
                    lon, tr = nv * math.cos(yaw), nv * math.sin(yaw)
                    s["vx"] = lon * ex - tr * ey      # e_transverse = skew(e) = (-ey, ex)
                    s["vy"] = lon * ey + tr * ex
            if abs(w) > 1e-12:
                dw = 0.025 / max(v, 0.001) * DT
                s["w"] = 0.0 if abs(w) <= dw else w - dw * (1.0 if w > 0 else -1.0)
        for s in moving:
            s["x"] += s["vx"] * DT
            s["y"] += s["vy"] * DT
            s["a"] += s["w"] * DT
        self._collide(moving, ev, touched)
        for s in list(self.stones):
            if abs(s["x"]) + R >= HALF_W or s["y"] - R > BACK_Y:
                self.stones.remove(s)
                ev["removed"].append((s["id"], "side line" if abs(s["x"]) + R >= HALF_W else "back line"))

    def _collide(self, moving: list[dict], ev: dict, touched: set) -> None:
        for _ in range(2):
            hit = False
            done = set()
            for a in list(moving):
                done.add(a["id"])
                for b in self.stones:
                    if b["id"] in done:
                        continue
                    dx, dy = b["x"] - a["x"], b["y"] - a["y"]
                    if abs(dx) >= 2 * R or abs(dy) >= 2 * R:
                        continue
                    d2 = dx * dx + dy * dy
                    if d2 >= 4 * R * R or d2 == 0.0:
                        continue
                    d = math.sqrt(d2)
                    nx, ny = dx / d, dy / d
                    tx, ty = -ny, nx
                    # contact-point velocities (w x r, r_a = R n, r_b = -R n)
                    vax = a["vx"] - a["w"] * R * ny
                    vay = a["vy"] + a["w"] * R * nx
                    vbx = b["vx"] + b["w"] * R * ny
                    vby = b["vy"] - b["w"] * R * nx
                    rvx, rvy = vbx - vax, vby - vay
                    vn = rvx * nx + rvy * ny
                    if vn < 0.0:
                        jn = -(1.0 + RESTITUTION) * vn / (2.0 / MASS)
                        vt = rvx * tx + rvy * ty
                        jt = -vt / (2.0 / MASS + 2.0 * R * R / INERTIA)
                        lim = FRICTION * jn
                        jt = max(-lim, min(lim, jt))
                        jx, jy = jn * nx + jt * tx, jn * ny + jt * ty
                        a["vx"] -= jx / MASS; a["vy"] -= jy / MASS
                        b["vx"] += jx / MASS; b["vy"] += jy / MASS
                        # torque: r x J; r_a = R n with impulse -J, r_b = -R n with impulse +J
                        a["w"] += (-(R * nx * jy - R * ny * jx)) / INERTIA
                        b["w"] += (-(R * nx * jy - R * ny * jx)) / INERTIA
                        key = (min(a["id"], b["id"]), max(a["id"], b["id"]))
                        if key not in touched:
                            ev["collisions"] += 1
                        touched.add(key)
                        hit = True
                        if a not in moving:
                            moving.append(a)
                        if b not in moving:
                            moving.append(b)
                    # separate overlapping stones (positional correction, like Box2D's)
                    pen = 2 * R - d
                    if pen > 1e-9:
                        c = 0.5 * pen
                        a["x"] -= c * nx; a["y"] -= c * ny
                        b["x"] += c * nx; b["y"] += c * ny
            if not hit:
                break


def dist_tee(x: float, y: float) -> float:
    return math.hypot(x, y - TEE_Y)


def in_house(x: float, y: float) -> bool:
    return dist_tee(x, y) < HOUSE_R + R


def score_end(sheet: Sheet) -> tuple[int, int]:
    """(team, points): the team with the stone closest to the tee scores one point per stone in the house closer
    than the other team's closest stone. (-1, 0) for a blank end."""
    h = sorted((dist_tee(s["x"], s["y"]), s["team"]) for s in sheet.stones if in_house(s["x"], s["y"]))
    if not h:
        return -1, 0
    team = h[0][1]
    other = [d for d, t in h if t != team]
    lim = other[0] if other else 1e9
    return team, sum(1 for d, t in h if t == team and d < lim)


# --------------------------------------------------------------------------- shot inversion (the opponent's aim)
class Master:
    """A single stone released at V_MAX along +y with each spin, recorded every step, on the ice of deceleration scale
    kd. The ice has no memory except the spin's sign, so a stone released at v0 < V_MAX follows the master's tail from
    the moment its speed is v0 (up to the spin decay, which never changes the sign here), rotated to its own heading.
    Used to aim shots (the opponent's, and a planning aid); the throws themselves are always simulated in full."""

    def __init__(self, spin: str, kd: float = 1.0):
        th = 0.0
        kd = float(kd)
        w = SPIN_W if spin == "ccw" else -SPIN_W
        x = y = 0.0
        vx, vy = 0.0, V_MAX
        S, X, Y, H = [], [], [], []
        while True:
            v = math.sqrt(vx * vx + vy * vy)
            S.append(v); X.append(x); Y.append(y); H.append(math.atan2(vx, vy))
            if v <= 0.0:
                break
            nv = v + accel(v) * kd * DT
            if nv <= 0.0:
                vx = vy = 0.0
            else:
                ex, ey = vx / v, vy / v
                yaw = (1.0 if w > 0 else -1.0) * 0.00820 * v ** -0.8 * DT
                lon, tr = nv * math.cos(yaw), nv * math.sin(yaw)
                vx, vy = lon * ex - tr * ey, lon * ey + tr * ex
            dw = 0.025 / max(v, 0.001) * DT
            w = w - dw * (1.0 if w > 0 else -1.0) if abs(w) > dw else w
            x += vx * DT; y += vy * DT
        self.S = np.array(S[::-1]); self.X = np.array(X[::-1]); self.Y = np.array(Y[::-1]); self.H = np.array(H[::-1])
        # reversed: ascending speed. index k: state when speed = S[k]; the end (rest) is index 0
        self.xe, self.ye = self.X[0], self.Y[0]

    def _local(self, k: int, j: int) -> tuple[float, float]:
        """Displacement from state k to state j (j <= k), in the frame where the heading at k is +y."""
        dx, dy = self.X[j] - self.X[k], self.Y[j] - self.Y[k]
        h = self.H[k]
        c, s = math.cos(h), math.sin(h)
        return dx * c - dy * s, dx * s + dy * c

    def aim(self, tx: float, ty: float, v_at: float = 0.0) -> tuple[float, float] | None:
        """Release speed and angle (deg) so the stone passes (tx, ty) at speed v_at (0 = comes to rest there)."""
        j = int(np.searchsorted(self.S, v_at)) if v_at > 0 else 0
        r = math.hypot(tx, ty)
        lo, hi = j + 1, len(self.S) - 1
        if math.hypot(*self._local(hi, j)) < r:
            return None
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if math.hypot(*self._local(mid, j)) < r:
                lo = mid
            else:
                hi = mid
        dx, dy = self._local(hi, j)
        ang = math.atan2(tx, ty) - math.atan2(dx, dy)
        return float(self.S[hi]), math.degrees(ang)


_MASTERS: dict[tuple[str, float], Master] = {}


def master(spin: str, kd: float = 1.0) -> Master:
    """The master path of `spin` on the ice of deceleration scale kd (cached per (spin, kd))."""
    key = (spin, float(kd))
    if key not in _MASTERS:
        if len(_MASTERS) >= 8:                    # a few ices at a time (one per match in a long-running process)
            _MASTERS.pop(next(iter(_MASTERS)))
        _MASTERS[key] = Master(spin, kd)
    return _MASTERS[key]


# ------------------------------------------------------------------------------------------- scripted opponent
def _blocked(sheet: Sheet, tx: float, ty: float, skip_id: int | None = None) -> bool:
    """Is any stone within ~one stone width of the straight line from the hack to (tx, ty), in front of it?"""
    L = math.hypot(tx, ty)
    ux, uy = tx / L, ty / L
    for s in sheet.stones:
        if s["id"] == skip_id:
            continue
        along = s["x"] * ux + s["y"] * uy
        if along < 20.0 or along > L - 0.05:
            continue
        if abs(-s["x"] * uy + s["y"] * ux) < 2 * R + 0.06:
            return True
    return False


def _value(sheet: Sheet, team: int) -> float:
    """The end's score from `team`'s side if it ended now, plus a small bonus for its closest stone."""
    t, p = score_end(sheet)
    v = float(p if t == team else -p if t >= 0 else 0)
    own = [dist_tee(s["x"], s["y"]) for s in sheet.stones if s["team"] == team and in_house(s["x"], s["y"])]
    return v + (0.2 * (1.0 - min(own) / (HOUSE_R + R)) if own else 0.0)


def opponent_candidates(sheet: Sheet, level: int, is_last: bool) -> list[dict]:
    c = []
    for (x, dy) in ((0.0, 0.0), (-0.45, 0.0), (0.45, 0.0), (0.0, -0.5), (0.0, 0.45), (-0.9, 0.3), (0.9, 0.3)):
        for sp in ("ccw", "cw"):
            c.append({"kind": "draw", "target": (x, TEE_Y + dy), "v_at": 0.0, "spin": sp})
    for s in sheet.stones:
        if s["team"] == 0 and dist_tee(s["x"], s["y"]) < HOUSE_R + R + 0.6:
            for sp in ("ccw", "cw"):
                if LEVELS[level]["guards"]:      # level 2: also hit-and-roll / double-takeout lines (off-centre hits)
                    for off in (-0.08, 0.0, 0.08):
                        for va in (1.6, 2.6):
                            c.append({"kind": "takeout", "target": (s["x"] + off, s["y"]), "v_at": va, "spin": sp})
                else:
                    c.append({"kind": "takeout", "target": (s["x"], s["y"]), "v_at": 1.6, "spin": sp})
    if LEVELS[level]["guards"] and not is_last:
        house = sorted((dist_tee(s["x"], s["y"]), s["team"], s) for s in sheet.stones if in_house(s["x"], s["y"]))
        if house and house[0][1] == 1:
            sh = house[0][2]
            for sp in ("ccw", "cw"):
                c.append({"kind": "guard", "target": (sh["x"] * 0.9, TEE_Y - HOUSE_R - 2.2), "v_at": 0.0, "spin": sp})
    return c


def opponent_plan(sheet: Sheet, level: int, is_last: bool, sid: int = 2 * N_STONES - 1, fgz: bool = False,
                  ctx: dict | None = None) -> dict:
    """The opponent's shot (deterministic). Level 1: it tries each candidate (draws around the button, takeouts of
    the player's stones near the house) on a copy of the sheet with its nominal release, and picks the one that
    leaves it the best end score if the end ended now (ties: the first candidate). It does not know its own execution
    noise, and it does not look ahead. It aims and simulates on the true ice (sheet.kd; deviation D8). Levels 2 and 3
    (LEVELS[level]["lookahead"], with the match context `ctx`, Match.context()): plan_l3; they differ only in the
    execution noise (curling-4; until curling-3 level 2 was level 1's greedy choice among more candidates, the
    `guards` branch of opponent_candidates, kept for a level without lookahead)."""
    if LEVELS[level].get("lookahead") and ctx is not None:
        return plan_l3(sheet, ctx, sid, fgz, LEVELS[level])
    best, bv = None, -1e9
    for cand in opponent_candidates(sheet, level, is_last):
        v, ang, sp = plan_to_throw(cand, sheet.kd)
        t = sheet.copy()
        t.throw_rules(sid, 1, v, ang, sp, fgz)
        val = _value(t, 1) + (0.05 if cand["kind"] == "guard" else 0.0)
        if val > bv + 1e-9:
            best, bv = cand, val
    return best


# ------------------------------------------------------------------- level 3: two plies, the hammer, guards
# The points of the end for the team with the hammer (>= 3 pooled; 5 stones a team), a rough model from the validity
# pilot's games (the reference against level 2, both hammer sides pooled): the level-3 team's match value.
HAMMER_END = {3: 0.20, 2: 0.17, 1: 0.43, 0: 0.05, -1: 0.12, -2: 0.02, -3: 0.01}
_WP: dict = {}


def wp_scripted(d: int, end_next: int, hammer: int) -> float:
    """The scripted team's chance to win the match from the start of end `end_next` (0-based) with lead d and the
    hammer (1) or not (0), under the match format's rules: 4 ends, extra ends while tied (at most 3), a tie after them
    goes to the scripted team; the team that scores gives the hammer away, a blank end keeps it."""
    d = max(-12, min(12, int(d)))
    key = (d, end_next, hammer)
    if key not in _WP:
        if end_next >= N_ENDS and d != 0:
            r = 1.0 if d > 0 else 0.0
        elif end_next >= N_ENDS + MAX_EXTRA_ENDS:
            r = 1.0
        else:
            r = 0.0
            for j, p in HAMMER_END.items():
                pts = j if hammer else -j                     # the scripted team's points
                h2 = (1 - hammer) if j > 0 else hammer          # the team that scores gives the hammer away
                r += p * wp_scripted(d + pts, end_next + 1, h2)
        _WP[key] = r
    return _WP[key]


def _centre_guard(s: dict) -> bool:
    return HOG_Y + 0.5 < s["y"] < TEE_Y - HOUSE_R - R and abs(s["x"]) < 0.75


def value_l3(stones: list[dict], ctx: dict, k_last: int, cfg: dict | None = None) -> float:
    """The level-3 team's value of the stones after the throw k_last (0-based) of the end. The end is over: its
    chance to win the match (wp_scripted). Mid-end, in points: the end's score if it ended now and the closest stones
    (weighted by phi, from phi0 after the first stone to 1 at the last: early stones in the house get hit), and the
    hammer's tactics: without the hammer centre guards of its own are worth something (they protect stones it
    will draw behind); with the hammer it wants the centre and the house clear of the player's stones (it plays for
    two or a blank)."""
    sh = Sheet()
    sh.stones = stones
    t, p = score_end(sh)
    j = p if t == 1 else -p if t == 0 else 0
    if k_last >= 2 * N_STONES - 1:
        h2 = 0 if j > 0 else 1 if j < 0 else ctx["hammer"]
        return wp_scripted(ctx["d"] + j, ctx["end"] + 1, h2)
    cfg = cfg or {}
    wc, wg, wh = cfg.get("w_close", 0.2), cfg.get("w_guard", 0.3), cfg.get("w_house", 0.1)
    phi0 = cfg.get("phi0", 1.0)                 # early in the end a stone in the house is worth less (it will be hit)
    # tuned against the reference (research/rerun/curling_v3, 2026-10-11): w_guard >= 0.5 makes it guard about twice
    # a match and the reference then wins ~12%; top 5 with the minimax reply ~26%; this setting ~51% (both hammer
    # orders, 80 matches), 27.5% with the official hammer order (level 2: 45%, 37.5%)
    phi = phi0 + (1.0 - phi0) * (k_last + 1) / (2 * N_STONES)
    own = [dist_tee(s["x"], s["y"]) for s in stones if s["team"] == 1 and in_house(s["x"], s["y"])]
    opp = [dist_tee(s["x"], s["y"]) for s in stones if s["team"] == 0 and in_house(s["x"], s["y"])]
    v = phi * (float(j) + wc * ((1.0 - min(own) / (HOUSE_R + R)) if own else 0.0)
               - wc * ((1.0 - min(opp) / (HOUSE_R + R)) if opp else 0.0))
    if ctx["hammer"]:
        v -= wg * sum(1 for s in stones if s["team"] == 0 and _centre_guard(s))
        v -= wh * len(opp)
    else:
        v += wg * min(2, sum(1 for s in stones if s["team"] == 1 and _centre_guard(s)))
        v += wh * len(own)
    return v


def l3_candidates(sheet: Sheet, ctx: dict, is_last: bool, fgz: bool) -> list[dict]:
    c = []
    for (x, dy) in ((0.0, 0.0), (-0.45, 0.0), (0.45, 0.0), (0.0, -0.5), (0.0, 0.45), (-0.9, 0.3), (0.9, 0.3),
                    (-0.3, -0.9), (0.3, -0.9)):
        for sp in ("ccw", "cw"):
            c.append({"kind": "draw", "target": (x, TEE_Y + dy), "v_at": 0.0, "spin": sp})
    if not is_last:
        house = sorted(((dist_tee(s["x"], s["y"]), s["team"], s) for s in sheet.stones if in_house(s["x"], s["y"])),
                       key=lambda t: t[0])
        spots = [(0.0, TEE_Y - HOUSE_R - 1.0), (0.0, TEE_Y - HOUSE_R - 2.2), (-0.6, TEE_Y - HOUSE_R - 0.6),
                 (0.6, TEE_Y - HOUSE_R - 0.6)]
        if house and house[0][1] == 1:
            spots.append((house[0][2]["x"] * 0.9, TEE_Y - HOUSE_R - 1.2))
        for gx, gy in spots:
            for sp in ("ccw", "cw"):
                c.append({"kind": "guard", "target": (gx, gy), "v_at": 0.0, "spin": sp})
    for s in sheet.stones:
        if s["team"] != 0:
            continue
        near = dist_tee(s["x"], s["y"]) < HOUSE_R + R + 0.6
        if near or (s["y"] > HOG_Y and not (fgz and sheet.in_fgz(s))):       # guards too, once the FGZ allows
            for sp in ("ccw", "cw"):
                for off in ((-0.08, 0.0, 0.08) if near else (-0.06, 0.0, 0.06)):
                    for va in (1.6, 2.6):
                        c.append({"kind": "takeout" if near else "peel", "target": (s["x"] + off, s["y"]),
                                  "v_at": va, "spin": sp})
    if is_last and ctx["hammer"]:                      # a throw-away: blank the end and keep the hammer
        for tx in (-1.6, 0.0, 1.6):
            for sp in ("ccw", "cw"):
                c.append({"kind": "through", "target": (tx, BACK_Y + 0.6), "v_at": 0.0, "spin": sp})
    return c


def l3_replies(sheet: Sheet) -> list[dict]:
    """The player's replies as the level-3 team models them: draws around the button, takeouts of its stones in or
    near the house, peels of its centre guards."""
    c = []
    for (x, dy) in ((0.0, 0.0), (-0.45, 0.0), (0.45, 0.0), (0.0, -0.5), (0.0, 0.45)):
        for sp in ("ccw", "cw"):
            c.append({"target": (x, TEE_Y + dy), "v_at": 0.0, "spin": sp})
    mine = sorted(((dist_tee(s["x"], s["y"]), s) for s in sheet.stones if s["team"] == 1), key=lambda t: t[0])
    for d, s in mine[:3]:
        if d < HOUSE_R + R + 0.6 or _centre_guard(s):
            for sp in ("ccw", "cw"):
                for va in (1.6, 2.6):
                    c.append({"target": (s["x"], s["y"]), "v_at": va, "spin": sp})
    return c


def plan_l3(sheet: Sheet, ctx: dict, sid: int, fgz: bool, cfg: dict) -> dict:
    """Level 3: every candidate (l3_candidates) on a planning copy of the sheet (the fast free flight of Sheet.throw,
    true ice, no noise) valued by value_l3; with cfg["plies"] = 2, unless its stone ends the end, the best cfg["top"]
    distinct ones are looked at one ply deeper, against the player's reply among l3_replies: the one worst for the
    level-3 team (cfg["reply"] = "min", minimax) or the player's greedy one (the best end score for the player if the
    end ended then, "greedy"). Ties: the first candidate."""
    k = ctx["k"]
    is_last = k == 2 * N_STONES - 1
    kd = sheet.kd
    ones = []
    for cand in l3_candidates(sheet, ctx, is_last, fgz):
        v, ang, sp = plan_to_throw(cand, kd)
        t = sheet.copy()
        t.throw_rules(sid, 1, v, ang, sp, fgz, fast=True)
        ones.append((value_l3(t.stones, ctx, k, cfg), cand, t))
    if is_last or ctx["left_opp"] <= 0 or cfg.get("plies", 2) < 2 or k < cfg.get("from_k", 0):
        best = max(ones, key=lambda o: o[0])           # max() keeps the first of equal values
        return best[1]
    order = sorted(range(len(ones)), key=lambda i: -ones[i][0])
    top, seen = [], set()
    for i in order:
        key = (round(ones[i][0], 6), ones[i][1]["kind"])
        if key in seen:
            continue
        seen.add(key)
        top.append(ones[i])
        if len(top) >= cfg.get("top", 5):
            break
    rsid = N_STONES - ctx["left_opp"]                  # the player's next stone id (team 0: 0..4)
    rfgz = k + 1 < FGZ_STONES
    best, bv = top[0][1], -1e9
    greedy = cfg.get("reply", "min") == "greedy"
    for _v1, cand, t in top:
        worst, pbest = 1e9, -1e9
        for r in l3_replies(t):
            v, ang, sp = plan_to_throw(r, kd)
            t2 = t.copy()
            t2.throw_rules(rsid, 0, v, ang, sp, rfgz, fast=True)
            if greedy:
                pv = _value(t2, 0)
                if pv > pbest + 1e-9:
                    pbest, worst = pv, value_l3(t2.stones, ctx, k + 1, cfg)
            else:
                worst = min(worst, value_l3(t2.stones, ctx, k + 1, cfg))
        if worst > bv + 1e-9:
            best, bv = cand, worst
    return best


def plan_to_throw(plan: dict, kd: float = 1.0) -> tuple[float, float, str]:
    """Aim the plan's shot on the ice of deceleration scale kd, correcting the aim point for the curl."""
    sp = plan["spin"]
    tx, ty = plan["target"]
    a = master(sp, kd).aim(tx, ty, plan["v_at"])
    if a is None:
        a = (V_MAX, 0.0)
    return a[0], a[1], sp


# ----------------------------------------------------------------------------------------------------- match
class Match:
    """A match of N_ENDS ends (+ up to MAX_EXTRA_ENDS extra ends while tied), N_STONES stones per team per end, against the
    scripted opponent. The opponent has the hammer (last stone) in end 1 unless `hammer` is set before the first stone
    (the plugin draws it, deviation D6); afterwards the team that scored in the previous end throws first (a blank
    end keeps the hammer). Lock-step: `run_to_decision()` plays the opponent's
    throws until it is the player's turn (or the match is over)."""

    def __init__(self, level: int = 1, kd: float = 1.0):
        self.level = level
        self.L = dict(LEVELS[level])
        if os.environ.get("MATCH_SEED"):
            self.L["seed"] = int(os.environ["MATCH_SEED"])
        self.kd = float(kd)         # the ice's deceleration scale (hidden from the players; plugin.ice_kd)
        self.score = [0, 0]
        self.end = 0
        self.hammer = 1
        self.sheet = Sheet(self.kd)
        self.k = 0                  # throw index within the end (0..2*N_STONES-1)
        self.n_throws = 0           # total throws so far (both teams)
        self.done = False
        self.forfeit = False        # the player's match clock ran out: its remaining stones are forfeited, the
                                    # current end is finished by the opponent and no further end is played
        self.decisions: list[dict] = []
        self.log: list[dict] = []   # one entry per throw (both teams)
        self.ends: list[dict] = []
        self.last_throw: dict | None = None
        self.last_opp: list[dict] = []
        self.frames_cb = None       # optional callback(frames, meta) for rendering replays

    # --- whose turn
    def n_ends_total(self) -> int:
        tied_after = self.end >= N_ENDS and self.score[0] == self.score[1]
        return N_ENDS + (min(MAX_EXTRA_ENDS, self.end - N_ENDS + 1) if tied_after else 0)

    def thrower(self) -> int:
        first = 1 - self.hammer
        return first if self.k % 2 == 0 else 1 - first

    def stones_left(self, team: int) -> int:
        first = 1 - self.hammer
        thrown = (self.k + 1) // 2 if team == first else self.k // 2
        return N_STONES - thrown

    def stone_id(self, team: int) -> int:
        return team * N_STONES + (N_STONES - self.stones_left(team))

    # --- execution
    def noise_stream(self, team: int) -> int:
        """The team's execution-noise stream: the player's (team 0) 1, the scripted team's 2."""
        return 1 if team == 0 else 2

    def _noise(self, team: int) -> tuple[float, float]:
        if getattr(self, "noiseless", False):       # planning copies only (calibration players)
            return 0.0, 0.0
        # each team's own stream (curling-2, 2026-10-08): the n-th stone of a team in an end draws
        # default_rng([seed, end, stream, n]); until curling-1 the n-th stone of each team drew the same numbers, so a
        # team that threw later could read its coming error off the other team's stone and aim against it
        rng = np.random.default_rng([self.L["seed"], self.end, self.noise_stream(team), N_STONES - self.stones_left(team)])
        z = rng.standard_normal(2)
        nz = PLAYER_NOISE if team == 0 else self.L
        return float(z[0] * nz["speed"]), float(z[1] * nz["angle_deg"])

    def _throw(self, team: int, v: float, ang: float, spin: str, meta: dict) -> dict:
        dv, da = self._noise(team)
        v_act = min(V_MAX + 0.05, max(0.1, v + dv))
        a_act = ang + da
        fe = 1.0 if self.frames_cb is not None else None
        sid = self.stone_id(team)
        ev = self.sheet.throw_rules(sid, team, v_act, a_act, spin, self.k < FGZ_STONES, frame_every=fe)
        rec = {"end": self.end, "k": self.k, "team": team, "sid": sid, "v": v, "angle": ang, "spin": spin,
               "v_actual": v_act, "angle_actual": a_act, "collisions": ev["collisions"],
               "removed": [list(r) for r in ev["removed"]], "fgz_violation": bool(ev.get("fgz_violation")),
               "t": ev["t"], **meta}
        if self.frames_cb is not None:
            self.frames_cb(ev["frames"], rec, self)
        self.log.append(rec)
        self._advance()
        return rec

    def _pass(self, team: int, why: str) -> dict:
        rec = {"end": self.end, "k": self.k, "team": team, "pass": why}
        self.log.append(rec)
        self._advance()
        return rec

    def _advance(self) -> None:
        self.k += 1
        self.n_throws += 1
        if self.k >= 2 * N_STONES:
            team, pts = score_end(self.sheet)
            if team >= 0:
                self.score[team] += pts
                self.hammer = 1 - team
            self.ends.append({"end": self.end, "team": team, "points": pts, "score": list(self.score),
                              "stones": [[s["team"], round(s["x"], 4), round(s["y"], 4)] for s in self.sheet.stones]})
            if self.frames_cb is not None:
                self.frames_cb(None, {"end_over": self.end, "team": team, "points": pts}, self)
            self.end += 1
            self.k = 0
            self.end_sheet = self.sheet        # the finished end's stones at rest (the plugin's reply image)
            self.sheet = Sheet(self.kd)
            if self.forfeit or (self.end >= N_ENDS and (self.score[0] != self.score[1]
                                                        or self.end >= N_ENDS + MAX_EXTRA_ENDS)):
                self.done = True

    def context(self) -> dict:
        """The scripted team's view of the coming throw: its lead d, the end, whether it has the hammer, the throw's
        index k in the end, its stones left (left_me) and the player's (left_opp; 0 once the player forfeited)."""
        return {"d": self.score[1] - self.score[0], "end": self.end, "hammer": int(self.hammer == 1), "k": self.k,
                "left_me": self.stones_left(1), "left_opp": 0 if self.forfeit else self.stones_left(0)}

    def opponent_throw(self) -> dict:
        is_last = self.stones_left(1) == 1 and self.hammer == 1
        plan = opponent_plan(self.sheet, self.level, is_last, self.stone_id(1), fgz=self.k < FGZ_STONES,
                             ctx=self.context())
        v, ang, spin = plan_to_throw(plan, self.kd)
        return self._throw(1, v, ang, spin, {"plan": plan["kind"]})

    def run_to_decision(self, stop_at_end: bool = False) -> list[dict]:
        """Play the opponent's throws (and the player's forfeited stones) until the player must decide. With
        `stop_at_end`, also stop when an end has just finished (the between-ends review; call again to go on)."""
        out = []
        n_ends = len(self.ends)
        while not self.done and (self.thrower() == 1 or self.forfeit):
            if stop_at_end and len(self.ends) > n_ends:
                break
            if self.thrower() == 1:
                out.append(self.opponent_throw())
            else:
                out.append(self._pass(0, "match clock exhausted"))
        return out

    def player_throw(self, v: float, ang: float, spin: str) -> dict:
        assert not self.done and self.thrower() == 0
        self.decisions.append({"type": "throw", "v": v, "angle": ang, "spin": spin})
        return self._throw(0, v, ang, spin, {})

    def player_forfeit(self, at_boundary: bool = False) -> None:
        """The match clock ran out: this and all the player's later stones are not thrown; the opponent finishes the
        current end and no further end is played (the score stands). `at_boundary`: it ran out between ends (before
        the next end's first stone), so the match ends at once."""
        self.decisions.append({"type": "forfeit", "at_boundary": bool(at_boundary)})
        self.forfeit = True
        if at_boundary:
            self.done = True

    def replay(self, decisions: list[dict]) -> None:
        """Re-run the match from the player's decisions, in the live order: after each decision the world runs up to
        the next decision or the end of an end (the between-ends review), and on to the player's turn when the next
        throw comes."""
        self.run_to_decision(stop_at_end=True)
        for d in decisions:
            if self.done:
                break
            if d["type"] == "throw":
                self.run_to_decision()
                self.player_throw(d["v"], d["angle"], d["spin"])
            else:
                if not d.get("at_boundary"):
                    self.run_to_decision()
                self.player_forfeit(bool(d.get("at_boundary")))
            self.run_to_decision(stop_at_end=True)

    # --- evidence
    @property
    def winner_team(self):
        """0 / 1 once the match is over (the tie-break included), else None."""
        if not self.done:
            return None
        if self.score[0] != self.score[1]:
            return 0 if self.score[0] > self.score[1] else 1
        tb = getattr(self, "tiebreak", None)
        return None if tb is None else tb["winner"]

    def resolve_tiebreak(self, winner: int, clock_left_s) -> None:
        """The last-resort rule for a tie after the last extra end: the team with more chess-clock time left wins (the
        service supplies the clocks; they are recorded in the trajectory and applied again on replay)."""
        assert self.done and self.score[0] == self.score[1]
        self.tiebreak = {"winner": int(winner), "clock_left_s": [float(c) for c in clock_left_s]}

    def state_sha(self) -> str:
        blob = json.dumps({"score": self.score, "log": self.log, "ends": self.ends, "done": self.done,
                           "tiebreak": getattr(self, "tiebreak", None), "kd": self.kd,
                           "stones": [[s["id"], s["x"], s["y"]] for s in self.sheet.stones]}, sort_keys=True,
                          default=float)
        return hashlib.sha256(blob.encode()).hexdigest()

    def clone(self) -> "Match":
        cb = self.frames_cb
        self.frames_cb = None
        m = copy.deepcopy(self)
        self.frames_cb = cb
        return m
