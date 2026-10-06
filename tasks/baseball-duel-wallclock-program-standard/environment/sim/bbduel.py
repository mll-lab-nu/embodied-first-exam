"""Baseball duel engine: pitcher against batter, two seats, one 100 Hz clock (shared by the service and its replay).

Format: innings with outs, base runners and runs (MLB Official Baseball Rules). FIRST_BATTER (the visitors) bats in the
top of each inning, the other seat (home) in the bottom; in each half-inning one seat bats and the other pitches until
the batting seat has 3 outs (5.09(e)). The plate appearance's result comes from the single-player game (strikeout,
walk, bb.judge_batted's outs and hits); an out leaves the runners where they are, a walk moves only forced runners
(5.05(b)(1), 5.06(b)(3)(B)), a hit moves every runner as many bases as the batter (advance_runners()). A run scores
for each runner reaching home (5.08(a)); score = runs. The game is INNINGS innings (7.01(a)); it ends after the top
half of the last inning if home leads (7.01(e)(1)) and in the bottom half as soon as home leads (7.01(e)(3): runs past
the winning run count only on a home run). Level after the regulation innings: extra innings, at most EXTRA_INNINGS,
each half-inning starting with runners on first and second base (the WBSC tie-break rule; MLB 7.01(b)(2) puts one
on second); still level after that, the winner of the last pitch wins (the common last-resort rule of the real-time
sports: the player who won the last point): the batter if it put the batter on base (the last half-inning ended at the
run limit), else the pitcher (it ended at 3 outs). There are no draws.
No tiebreak counts how the runs came: once a half-inning will reach the run limit anyway, the pitcher could steer that
too (e.g. bases: 7 walks give 7, 4 home runs 16).

Why outs: with a fixed number of plate appearances a walk was a sure, bounded result that the pitcher could always
force (no pitch = an automatic ball; or a pitch out of the bat's reach), so a leading pitcher conceded walks. A walk
makes no out, so a pitcher who walks every batter never ends the half-inning and concedes RUN_LIMIT runs, the most a
half-inning can give (in a bottom half that can end the game, it loses as soon as home leads).

Bounds (MLB has none): a half-inning also ends when the batting seat has RUN_LIMIT runs in it (runs past the limit on
that play do not count); a plate appearance that reaches PA_MAX_PITCHES pitches without ending is an out (two-strike
fouls never end a plate appearance). Every half-inning therefore ends after finitely many pitches, and so does the
game.

A pitch: the pitcher winds up (WINDUP, seeded by the batter's pitch number: both seats see the same sequence) with the
ball in its hand at the release point bb.REL. During the windup the pitcher commands the pitch (type, speed, target at
the plate, and the spin: its rate and break direction within SPIN_RATE and BREAK_SPAN of the type's default; a later
command replaces an earlier one); at the release the last command is thrown, with a seeded execution scatter
(PITCH_SCATTER) on the target, the speed and the spin (rate and break direction): bb.Pitch aims the ball's centre at
the scattered target (y = 0) with the scattered spin. No command by the release = an automatic ball. After the
release the batter swings as in the single-player game (bbrt: the bat square T s after the command takes effect;
seeded swing scatter bb.SCATTER, keyed by the batter's pitch number). The pitch is over END_AFTER s after the contact
or the plate; it is judged while the world is frozen (bb.judge_batted and the count, as bb.Game.decide_finish).

Time stamps: k = control steps of running world since the start (frozen time does not count), n = steps since this
pitch's windup began, t = n * DT - windup = time since release.
"""
from __future__ import annotations

import hashlib
import json
import math

import numpy as np

import bb
import bbrt

DT = bbrt.DT
SIDES = ("A", "B")
OTHER = {"A": "B", "B": "A"}
REVISION = "baseball-duel-2"
INNINGS = 1                      # regulation innings (MLB: 9)
EXTRA_INNINGS = 1                # extra innings until decided, at most this many; then the last pitch decides
RUN_LIMIT = 4                    # runs per half-inning (MLB: no limit)
PA_MAX_PITCHES = bb.PA_MAX_PITCHES   # a plate appearance reaching 15 pitches is an out (as in the single game)
ON_BASE = ("walk", "single", "double", "home run")   # the plate appearance results that put the batter on base
WINDUP = bbrt.WINDUP             # the single-player game's windup (0.6-1.2 s)
ARSENAL = {"fastball": (34.0, 42.0), "sinker": (34.0, 41.0), "cutter": (33.0, 39.0), "slider": (33.0, 37.5),
           "changeup": (29.0, 35.5), "splitter": (30.0, 37.0), "curveball": (28.0, 33.5)}
TARGET_X = (-0.60, 0.60)
TARGET_Z = (0.20, 1.60)
PITCH_SCATTER = {"target_m": 0.03, "speed_mps": 0.3, "spin_frac": 0.03, "break_deg": 8.0}
SPIN_RATE = (0.8, 1.2)           # the pitcher's spin rate: this share of the type's default
BREAK_SPAN = 25.0                # the break direction: at most this many degrees from the type's default


def windup_s(seed: int, j: int) -> float:
    r = bb._rng(seed, 11, j)
    n0, n1 = int(round(WINDUP[0] / DT)), int(round(WINDUP[1] / DT))
    return int(r.integers(n0, n1 + 1)) * DT


def swing_scatter(seed: int, j: int) -> dict:
    z = bb._rng(seed, 7, j).standard_normal(5)
    S = bb.SCATTER
    return dict(t=z[0] * S["t_ms"] / 1000.0, plane=z[1] * S["plane_deg"], height=z[2] * S["height_m"],
                speed=1.0 + z[3] * S["speed_frac"], reach=z[4] * S["reach_m"])


def default_spin(name: str) -> dict:
    """A type's single-player spin (bb.PITCH_TYPES) as the duel's spin parameters, rounded to 1 rpm and 0.1 degree:
    the rate and the break direction (where the Magnus force pushes a ball moving along -y, in degrees from straight
    up towards first base, +x)."""
    pt = bb.PITCH_TYPES[name]
    ax = pt["axis"]
    return dict(spin_rpm=round(pt["spin"] * 60 / (2 * math.pi)),
                break_deg=round(math.degrees(math.atan2(ax[2], -ax[0])), 1))


def spin_vector(name: str, spin_rpm: float, break_deg: float) -> tuple:
    """(rate in rad/s, unit axis) of a `name` pitch with this rate and break direction; the axis keeps the type's
    gyro component (spin along the flight, which does not break the ball)."""
    g = bb.PITCH_TYPES[name]["axis"][1]
    b, t = math.radians(break_deg), math.sqrt(1 - g * g)
    return spin_rpm * 2 * math.pi / 60, (-math.cos(b) * t, g, math.sin(b) * t)


def spin_limits(name: str) -> dict:
    """The pitcher's choices for a `name` pitch's spin, [low, high] rounded to 0.1: rate (rpm) and break direction."""
    d = default_spin(name)
    return dict(spin_rpm=[round(f * d["spin_rpm"], 1) for f in SPIN_RATE],
                break_deg=[round(d["break_deg"] + s * BREAK_SPAN, 1) for s in (-1, 1)])


def validate_pitch(body: dict) -> dict:
    """A pitch command {'type': 'pitch', 'pitch': TYPE, 'speed': m/s, 'x': m, 'z': m, 'spin_rpm': rpm, 'break_deg':
    degrees} (the spin defaults to the type's); returns it complete; raises ValueError."""
    name = body.get("pitch")
    if name not in ARSENAL:
        raise ValueError(f"pitch must be one of {sorted(ARSENAL)}")
    d = default_spin(name)
    sp, x, z = float(body["speed"]), float(body["x"]), float(body["z"])
    rpm, brk = float(body.get("spin_rpm", d["spin_rpm"])), float(body.get("break_deg", d["break_deg"]))
    if not np.all(np.isfinite([sp, x, z, rpm, brk])):
        raise ValueError("speed, x, z, spin_rpm and break_deg must be finite numbers")
    lo, hi = ARSENAL[name]
    if not lo <= sp <= hi:
        raise ValueError(f"a {name} is thrown at {lo:g}-{hi:g} m/s")
    if not (TARGET_X[0] <= x <= TARGET_X[1] and TARGET_Z[0] <= z <= TARGET_Z[1]):
        raise ValueError(f"target x must be in {list(TARGET_X)} m and z in {list(TARGET_Z)} m")
    lim = spin_limits(name)                          # rounded: a limit computed from the default may differ by 1e-14
    lo, hi = lim["spin_rpm"]
    if not lo - 1e-6 <= rpm <= hi + 1e-6:
        raise ValueError(f"a {name} spins at {lo:g}-{hi:g} rpm")
    lo, hi = lim["break_deg"]
    if not lo - 1e-6 <= brk <= hi + 1e-6:
        raise ValueError(f"a {name} breaks towards {lo:g} to {hi:g} degrees")
    return {"type": "pitch", "pitch": name, "speed": sp, "x": x, "z": z, "spin_rpm": rpm, "break_deg": brk}


def make_pitch(seed: int, j: int, cmd: dict) -> bb.Pitch:
    """The thrown pitch for the batter's pitch number j: the command with its seeded execution scatter (pure)."""
    z = bb._rng(seed, 13, j).standard_normal(5)
    S = PITCH_SCATTER
    spin, axis = spin_vector(cmd["pitch"], cmd["spin_rpm"] * (1 + z[3] * S["spin_frac"]),
                             cmd["break_deg"] + z[4] * S["break_deg"])
    p = bb.Pitch(cmd["pitch"], cmd["speed"] + z[2] * S["speed_mps"], cmd["x"] + z[0] * S["target_m"],
                 cmd["z"] + z[1] * S["target_m"], spin, axis)
    if p.cross is None or not all(np.isfinite(p.cross)) or abs(p.cross[1] - p.target[0]) > 0.01 \
            or abs(p.cross[2] - p.target[1]) > 0.01:
        raise ValueError("the pitcher cannot throw this pitch to that target")
    return p


def advance_runners(runners: tuple, result: str, bases: int) -> tuple:
    """The runners (first, second, third occupied) after the batter reaches base, and the runs scored: a walk moves
    only the runners it forces (5.06(b)(3)(B)); a hit moves the batter and every runner `bases` bases (pure)."""
    if result == "walk":
        if all(runners):
            return runners, 1
        i = runners.index(False)                      # the batter forces each runner up to the first empty base
        return runners[:i] + (True,) + runners[i + 1:], 0
    after = [b + bases for b in (1, 2, 3) if runners[b - 1]] + [bases]
    return tuple(b in after for b in (1, 2, 3)), sum(b >= 4 for b in after)


class Duel:
    def __init__(self, seed: int, first: str):
        assert first in SIDES
        self.seed, self.first = int(seed), first
        self.k = 0
        self.pa = 0                                   # index of the current plate appearance (both seats)
        self.balls = self.strikes = 0
        self.inning, self.top = 1, True               # the current half-inning
        self.outs, self.half_runs = 0, 0
        self.runners = (False, False, False)          # first, second, third base occupied
        self.score = {s: 0 for s in SIDES}
        self.pa_results = []                          # every finished plate appearance, in order
        self.history = []                             # one record per pitch
        self.faced = {s: 0 for s in SIDES}            # pitches thrown to each batter so far
        self.done = False
        self._begin()

    # --- who does what
    @property
    def batter(self) -> str:
        return self.first if self.top else OTHER[self.first]

    @property
    def half(self) -> str:
        return "top" if self.top else "bottom"

    def on_base(self) -> list:
        """The occupied bases (1 = first, 2 = second, 3 = third)."""
        return [b for b in (1, 2, 3) if self.runners[b - 1]]

    def walkoff_half(self) -> bool:
        """The bottom of the last or an extra inning: the game ends as soon as home leads (7.01(e)(3))."""
        return not self.top and self.inning >= INNINGS

    @property
    def pitcher(self) -> str:
        return OTHER[self.batter]

    def role(self, side: str) -> str:
        return "batting" if side == self.batter else "pitching"

    def pa_of(self, side: str) -> int:
        """1-based number of the current plate appearance of `side` as a batter (or of its next one)."""
        return sum(1 for r in self.pa_results if r["batter"] == side) + 1

    # --- a pitch
    def _begin(self):
        self.idx = len(self.history)
        self.j = self.faced[self.batter]
        self.windup = windup_s(self.seed, self.j)
        self.n = 0
        self.k_begin = self.k
        self.pitch_cmd = None                         # (command, prepared bb.Pitch) until the release
        self.pitch = None                             # the thrown pitch (after the release)
        self.plan = None                              # the batter's planned swing (not started)
        self.rec = None                               # the record once the pitch is resolved
        self.t_end = self.t_plate = None
        self.over = self.judged = False

    @property
    def t(self) -> float:
        return round(self.n * DT - self.windup, 6)

    def released(self) -> bool:
        return self.t >= 0.0

    # --- commands (applied at a control step; see apply())
    def set_pitch(self, cmd: dict, prepared: bb.Pitch) -> dict:
        if self.released() or self.over:
            return {"accepted": False, "why": "the ball has already been released"}
        self.pitch_cmd = (dict(cmd), prepared)
        return {"accepted": True, "release_in_s": round(-self.t, 4)}

    def cancel_pitch(self) -> dict:
        if self.released() or self.over:
            return {"accepted": False, "why": "the ball has already been released"}
        self.pitch_cmd = None
        return {"accepted": True, "note": "no pitch commanded: at the release this is an automatic ball"}

    def swing(self, T, plane, height, speed, reach) -> dict:
        if not self.released():
            return {"accepted": False, "why": "the ball has not been released yet"}
        if self.rec is not None or self.over:
            return {"accepted": False, "why": "the swing is under way (or the pitch was taken): it cannot be changed"}
        tsq = bbrt.T_SQUARE / speed
        start = self.t + T - tsq
        late = 0.0
        if start < self.t:
            late, start = self.t - start, self.t
        self.plan = {"start": round(start, 6), "plane": plane, "height": height, "speed": speed, "reach": reach}
        info = {"accepted": True, "swing_start_in_s": round(start - self.t, 4),
                "square_in_s": round(start - self.t + tsq, 4), "square_later_than_asked_s": round(late, 4),
                "swing_start_t_since_release": round(start, 4)}
        if start <= self.t:
            self._commit_swing()
            info["swing_started"] = True
        return info

    def cancel_swing(self) -> dict:
        if not self.released():
            return {"accepted": True, "note": "no swing planned"}
        if self.rec is not None or self.over:
            return {"accepted": False, "why": "the swing is under way (or the pitch was taken): it cannot be changed"}
        self.plan = None
        return {"accepted": True}

    def apply(self, side: str, dec: dict, prepared=None) -> dict:
        """A command of `side` at the current control step (live: at the step boundary after it arrived)."""
        if side == self.pitcher:
            if dec["type"] == "none":
                return self.cancel_pitch()
            if prepared is None:
                prepared = make_pitch(self.seed, self.j, dec)
            return self.set_pitch(dec, prepared)
        if dec["type"] == "none":
            return self.cancel_swing()
        return self.swing(dec["t"], dec["plane"], dec["height"], dec["speed"], dec["reach"])

    def _commit_swing(self):
        pl = self.plan
        self._resolve({"type": "swing", "t": pl["start"], "plane": pl["plane"], "height": pl["height"],
                       "speed": pl["speed"], "reach": pl["reach"]})

    def _resolve(self, dec):
        """Phase 1 (cheap): the executed swing and the bat-ball contact, or a take."""
        p = self.pitch
        cmd = self.pitch_cmd[0] if self.pitch_cmd else None
        rec = {"pitch": self.idx, "pa": self.pa, "batter": self.batter, "pitcher": self.pitcher, "j": self.j,
               "inning": self.inning, "half": self.half, "count": [self.balls, self.strikes], "outs": self.outs,
               "on_base": self.on_base(), "pitch_command": cmd, "decision": dict(dec)}
        if p is None:
            rec.update(type=None, radar=None, outcome="ball (no pitch)")
        else:
            rec.update(type=p.ptype, radar=p.radar(), target=[round(p.target[0], 4), round(p.target[1], 4)])
            if dec["type"] == "take":
                rec["outcome"] = "strike (called)" if p.zone else "ball"
            else:
                sc = swing_scatter(self.seed, self.j)
                t0 = float(dec["t"]) + sc["t"]
                sw = bb.Swing(t0, float(dec["plane"]) + sc["plane"], float(dec["height"]) + sc["height"],
                              float(dec["speed"]) * sc["speed"], float(dec["reach"]) + sc["reach"])
                rec["swing_executed"] = {"t_start": round(t0, 4), "plane_deg": round(sw.plane_deg, 3),
                                         "height": round(sw.H, 4), "speed": round(sw.speed, 3),
                                         "reach": round(sw.reach, 4)}
                rec["swing_obj"] = sw
                info, st = bb.swing_result(p, sw)
                if info is None:
                    rec["outcome"] = "strike (swinging)"
                else:
                    rec["contact"] = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in info.items()
                                      if k != "pos"}
                    rec["contact"]["pos"] = [round(x, 4) for x in info["pos"]]
                    rec["post_state"] = st
        self.rec = rec
        self.plan = None
        if p is None:
            self.t_end = self.t
        else:
            t_evt = rec["contact"]["t"] if "contact" in rec else self.t_plate
            self.t_end = max(t_evt + bbrt.END_AFTER, self.t)

    # --- the clock
    def advance(self, steps: int = 1) -> int:
        run = 0
        while run < steps and not self.over:
            self.n += 1; self.k += 1; run += 1
            t = self.t
            if self.pitch is None and self.rec is None and t >= -1e-9:          # the release
                if self.pitch_cmd is None:
                    self._resolve({"type": "take"})
                else:
                    self.pitch = self.pitch_cmd[1]
                    p = self.pitch
                    self.t_plate = p.cross[0] if p.cross is not None else p.path[-1][0]
            if self.rec is None and self.pitch is not None:
                if self.plan is not None and t >= self.plan["start"] - 1e-9:
                    self._commit_swing()
                elif t >= self.t_plate + bbrt.TAKE_AFTER - 1e-9:
                    self._resolve({"type": "take"})
            if self.rec is not None and t >= self.t_end - 1e-9:
                self.over = True
        return run

    def finish(self) -> dict:
        """Phase 2, once the pitch is over (the world is frozen): the batted ball, the count, the runners, the score."""
        assert self.over and not self.judged
        rec, p = self.rec, self.pitch
        if "post_state" in rec:
            b = bb.judge_batted(rec["post_state"])
            rec["batted_samples"] = b.pop("samples")
            rec["batted"] = b
            rec["outcome"] = "foul" if b["kind"] == "foul" else b["kind"]
        rec["crossing"] = None if (p is None or p.cross is None) else [round(x, 4) for x in p.cross]
        rec["zone"] = bool(p is not None and p.zone)
        rec["pitch_obj"] = p
        o = rec["outcome"]
        pa_end = None
        if o in ("strike (called)", "strike (swinging)"):
            self.strikes += 1
            if self.strikes >= 3:
                pa_end = ("strikeout", 0)
        elif o in ("ball", "ball (no pitch)"):
            self.balls += 1
            if self.balls >= 4:
                pa_end = ("walk", 1)
        elif o == "foul":
            if self.strikes < 2:
                self.strikes += 1
        else:
            pa_end = (o, rec["batted"]["bases"])
        n_pa = 1 + sum(1 for h in self.history if h["pa"] == self.pa)
        if pa_end is None and n_pa >= PA_MAX_PITCHES:
            pa_end = ("out (pitch limit)", 0)
        rec["count_after"] = [self.balls, self.strikes]
        self.history.append(rec)
        self.faced[self.batter] += 1
        if pa_end:
            rec["pa_result"] = pa_end[0]
            self._end_pa(rec, *pa_end)
        else:
            rec.update(runs=0, outs_after=self.outs, on_base_after=self.on_base())
        self.judged = True
        return rec

    def _end_pa(self, rec: dict, result: str, bases: int):
        """The plate appearance's out or runners and runs (within the half-inning's limit), then the next batter."""
        b = self.batter
        if result in ON_BASE:
            self.runners, runs = advance_runners(self.runners, result, bases)
        else:
            self.outs, runs = self.outs + 1, 0
        runs = min(runs, RUN_LIMIT - self.half_runs)
        if self.walkoff_half() and result != "home run":     # the game ends when the winning run scores (7.01(e)(3))
            runs = min(runs, self.score[self.pitcher] - self.score[b] + 1)
        self.score[b] += runs
        self.half_runs += runs
        self.pa_results.append({"pa": self.pa + 1, "batter": b, "pa_of_batter": self.pa_of(b),
                                "inning": self.inning, "half": self.half, "result": result, "bases": bases,
                                "runs": runs, "pitches": sum(1 for h in self.history if h["pa"] == self.pa)})
        rec.update(runs=runs, outs_after=self.outs, on_base_after=self.on_base())
        self._next_batter()

    def _next_batter(self):
        """After a plate appearance: the next batter, the next half-inning or the end of the game."""
        self.pa += 1
        self.balls = self.strikes = 0
        home, visitors = self.score[OTHER[self.first]], self.score[self.first]
        if self.walkoff_half() and home > visitors:
            self.done = True
        elif self.outs >= 3 or self.half_runs >= RUN_LIMIT:
            last = self.inning >= INNINGS
            if self.top and last and home > visitors:                  # 7.01(e)(1)
                self.done = True
            elif not self.top and last and (home != visitors or self.inning >= INNINGS + EXTRA_INNINGS):
                self.done = True
            else:
                if not self.top:
                    self.inning += 1
                self.top = not self.top
                self.outs, self.half_runs = 0, 0
                extra = self.inning > INNINGS                           # extra innings: runners on first and second
                self.runners = (extra, extra, False)

    def next_pitch(self):
        assert self.over and self.judged and not self.done
        self._begin()

    # --- results
    def winner(self):
        """More runs; level after the last extra inning: the winner of the last pitch (None while undecided)."""
        a, b = self.score["A"], self.score["B"]
        if a != b:
            return "A" if a > b else "B"
        if not self.done or not self.history:
            return None
        last = self.history[-1]
        won_by_batter = last.get("pa_result") in ON_BASE
        return last["batter"] if won_by_batter else last["pitcher"]

    def decided_by(self):
        if not self.done:
            return None
        return "runs" if self.score["A"] != self.score["B"] else "last pitch"

    def public_rec(self, rec: dict) -> dict:
        out = {"pitch": rec["pitch"] + 1, "inning": rec["inning"], "half": rec["half"],
               "plate_appearance": rec["pa"] + 1, "batter": rec["batter"],
               "pitcher": rec["pitcher"], "pitch_type": rec["type"], "radar_mps": rec["radar"],
               "plate_crossing": None if rec["crossing"] is None else {"x": rec["crossing"][1], "z": rec["crossing"][2]},
               "in_zone": rec["zone"], "outcome": rec["outcome"], "count_after": rec["count_after"],
               "outs_after": rec["outs_after"], "on_base_after": rec["on_base_after"], "runs": rec["runs"]}
        if "contact" in rec:
            b = rec["batted"]
            out["batted_ball"] = {k: b[k] for k in ("exit_speed", "launch_deg", "spray_deg", "distance", "hang_time",
                                                    "fielder") if k in b}
        if "swing_executed" in rec:
            out["swing_executed"] = rec["swing_executed"]
        if rec.get("pa_result"):
            out["plate_appearance_result"] = rec["pa_result"]
        return out

    def state_sha(self) -> str:
        h = hashlib.sha256()
        for rec in self.history:
            p = rec["pitch_obj"]
            h.update(repr((rec["pitch"], rec["batter"], rec["outcome"], rec["count_after"], rec["pitch_command"],
                           None if p is None else (p.s0, p.path[-1], p.cross), rec.get("swing_executed"),
                           rec.get("post_state"), rec.get("contact"), rec.get("batted"),
                           rec.get("batted_samples", [])[-1:] if rec.get("batted_samples") else None)).encode())
        h.update(repr((self.score, self.pa_results, self.done, self.k)).encode())
        return h.hexdigest()

    # --- what the cameras see
    def ball_at(self, t):
        rec = self.rec
        if rec is not None and "contact" in rec and t > rec["contact"]["t"]:
            pc = rec["post_state"]; d = t - rec["contact"]["t"]
            return (pc[0] + pc[3] * d, pc[1] + pc[4] * d, pc[2] + pc[5] * d)
        if self.pitch is None or t < 0:
            return tuple(bb.REL)
        return tuple(self.pitch.state_at(t)[:3])

    def snapshots(self) -> list:
        sw = self.rec.get("swing_obj") if self.rec is not None else None
        swp = None if sw is None else (sw.t0, sw.plane_deg, sw.H, sw.speed, sw.reach)
        runners = self.rec["on_base"] if self.rec is not None else self.on_base()      # the runners before this pitch
        out = []
        for i in range(4):
            n = max(0, self.n - bbrt.FRAME_GAP_STEPS * (3 - i))
            t = round(n * DT - self.windup, 4)
            out.append({"pitch": self.idx, "n": n, "k": self.k_begin + n, "t": t,
                        "ball": [float(x) for x in self.ball_at(t)], "swing": swp, "runners": runners})
        return out

    def heard(self):
        h = []
        if self.released():
            h.append({"event": "release", "t": 0.0})
        if self.rec is not None and "contact" in self.rec and self.t >= self.rec["contact"]["t"]:
            h.append({"event": "bat", "t": round(self.rec["contact"]["t"], 3)})
        elif self.pitch is not None and self.t >= self.t_plate and self.pitch.cross is not None:
            h.append({"event": "mitt", "t": round(self.t_plate, 3)})
        return h

    def command(self, side):
        if side == self.pitcher:
            if self.pitch_cmd is None:
                return "none (no pitch commanded)" if not self.released() else "none"
            return dict(self.pitch_cmd[0])
        if self.rec is not None:
            if "swing_executed" in self.rec:
                return {"swing": "under way (started at t = %.3f s)" % self.rec["swing_executed"]["t_start"]}
            return "none (the pitch is being taken)"
        if self.plan is not None:
            pl = self.plan
            return {"swing_start_in_s": round(pl["start"] - self.t, 4),
                    "square_in_s": round(pl["start"] - self.t + bbrt.T_SQUARE / pl["speed"], 4),
                    "plane_deg": pl["plane"], "height": pl["height"], "speed": pl["speed"], "reach": pl["reach"]}
        return "none (the bat at rest)"


def replay(seed: int, first: str, cmds: list, k_end: int) -> Duel:
    """Re-run a duel from its (pitch, step, seat, command) list only: the commands that took effect at step k of
    pitch p are applied, in order, before the step k -> k + 1; a judged pitch is followed by the next one at once."""
    g = Duel(seed, first)
    i = 0
    while True:
        if g.over and not g.judged:
            g.finish()
        if g.done or g.k >= k_end:
            break
        if g.over:
            g.next_pitch()
        while i < len(cmds) and cmds[i][0] == g.idx and cmds[i][1] == g.k:
            g.apply(cmds[i][2], cmds[i][3])
            i += 1
        if i < len(cmds) and (cmds[i][0], cmds[i][1]) < (g.idx, g.k):
            raise ValueError(f"command {i} at pitch {cmds[i][0]} step {cmds[i][1]} was never reached")
        g.advance(1)
    if i != len(cmds):
        raise ValueError(f"replay consumed {i} of {len(cmds)} commands")
    return g


def decisions_sha(cmds: list) -> str:
    return hashlib.sha256(json.dumps(cmds, sort_keys=True, default=float).encode()).hexdigest()
