"""Baseball duel engine: pitcher against batter, two seats, one 100 Hz clock (shared by the service and its replay).

Format (symmetric): plate appearances alternate between the seats; in each, one seat bats and the other pitches.
FIRST_BATTER bats in plate appearances 1, 3, 5, ..., the other seat in 2, 4, 6, ...; each seat bats PA_PER_SEAT times.
Score = bases, as in the single-player game (walk or single 1, double 2, home run 4; bb.judge_batted's fielders). If the
bases are level after the regulation plate appearances, the seats bat one more each until the bases differ after a
pair, at most EXTRA_PAIRS times; still level after that, the winner of the last pitch wins (the common last-resort rule
of the real-time sports: the player who won the last point). A pitch is won by the batter if it ends the plate
appearance with bases (walk or hit), else by the pitcher; the last pitch always ends a plate appearance. There are no
draws. A plate appearance that reaches PA_MAX_PITCHES pitches without ending ends as an out (no bases): two-
strike fouls never end a plate appearance, and without this limit a batter could stall the game indefinitely. Every
game therefore ends after at most 2 * (PA_PER_SEAT + EXTRA_PAIRS) * PA_MAX_PITCHES pitches, always after a completed
pair of plate appearances.

A pitch: the pitcher winds up (WINDUP, seeded by the batter's pitch number: both seats see the same sequence) with the
ball in its hand at the release point bb.REL. During the windup the pitcher commands the pitch (type, speed, target at
the plate; a later command replaces an earlier one); at the release the last command is thrown, with a seeded
execution scatter (PITCH_SCATTER) on the target and the speed: bb.Pitch aims the ball's centre at the scattered target
(y = 0) with the type's spin. No command by the release = an automatic ball. After the release the batter swings as
in the single-player game (bbrt: the bat square T s after the command takes effect; seeded swing scatter bb.SCATTER,
keyed by the batter's pitch number). The pitch is over END_AFTER s after the contact or the plate; it is judged while
the world is frozen (bb.judge_batted and the count, as bb.Game.decide_finish).

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
REVISION = "baseball-duel-1"
PA_PER_SEAT = 5
EXTRA_PAIRS = 5                  # extra pairs until decided, at most this many; then the last pitch decides
PA_MAX_PITCHES = bb.PA_MAX_PITCHES   # a plate appearance reaching 15 pitches is an out (as in the single game)
WINDUP = bbrt.WINDUP             # the single-player game's windup (0.6-1.2 s)
ARSENAL = {"fastball": (34.0, 42.0), "slider": (33.0, 37.5), "changeup": (29.0, 35.5), "curveball": (28.0, 33.5)}
TARGET_X = (-0.60, 0.60)
TARGET_Z = (0.20, 1.60)
PITCH_SCATTER = dict(target_m=0.03, speed_mps=0.3)


def windup_s(seed: int, j: int) -> float:
    r = bb._rng(seed, 11, j)
    n0, n1 = int(round(WINDUP[0] / DT)), int(round(WINDUP[1] / DT))
    return int(r.integers(n0, n1 + 1)) * DT


def swing_scatter(seed: int, j: int) -> dict:
    z = bb._rng(seed, 7, j).standard_normal(5)
    S = bb.SCATTER
    return dict(t=z[0] * S["t_ms"] / 1000.0, plane=z[1] * S["plane_deg"], height=z[2] * S["height_m"],
                speed=1.0 + z[3] * S["speed_frac"], reach=z[4] * S["reach_m"])


def validate_pitch(body: dict) -> dict:
    """A pitch command {'type': 'pitch', 'pitch': TYPE, 'speed': m/s, 'x': m, 'z': m}; raises ValueError."""
    name = body.get("pitch")
    if name not in ARSENAL:
        raise ValueError(f"pitch must be one of {sorted(ARSENAL)}")
    sp, x, z = float(body["speed"]), float(body["x"]), float(body["z"])
    if not np.all(np.isfinite([sp, x, z])):
        raise ValueError("speed, x and z must be finite numbers")
    lo, hi = ARSENAL[name]
    if not lo <= sp <= hi:
        raise ValueError(f"a {name} is thrown at {lo:g}-{hi:g} m/s")
    if not (TARGET_X[0] <= x <= TARGET_X[1] and TARGET_Z[0] <= z <= TARGET_Z[1]):
        raise ValueError(f"target x must be in {list(TARGET_X)} m and z in {list(TARGET_Z)} m")
    return {"type": "pitch", "pitch": name, "speed": sp, "x": x, "z": z}


def make_pitch(seed: int, j: int, cmd: dict) -> bb.Pitch:
    """The thrown pitch for the batter's pitch number j: the command with its seeded execution scatter (pure)."""
    z = bb._rng(seed, 13, j).standard_normal(3)
    S = PITCH_SCATTER
    p = bb.Pitch(cmd["pitch"], cmd["speed"] + z[2] * S["speed_mps"], cmd["x"] + z[0] * S["target_m"],
                 cmd["z"] + z[1] * S["target_m"])
    if p.cross is None or not all(np.isfinite(p.cross)) or abs(p.cross[1] - p.target[0]) > 0.01 \
            or abs(p.cross[2] - p.target[1]) > 0.01:
        raise ValueError("the pitcher cannot throw this pitch to that target")
    return p


class Duel:
    def __init__(self, seed: int, first: str):
        assert first in SIDES
        self.seed, self.first = int(seed), first
        self.level, self.lv = "duel", {"n_pa": 2 * PA_PER_SEAT}      # for bb.render_video
        self.k = 0
        self.pa = 0                                   # index of the current plate appearance (both seats)
        self.balls = self.strikes = 0
        self.score = {s: 0 for s in SIDES}
        self.pa_results = []                          # every finished plate appearance, in order
        self.history = []                             # one record per pitch
        self.faced = {s: 0 for s in SIDES}            # pitches thrown to each batter so far
        self.done = False
        self._begin()

    # --- who does what
    @property
    def batter(self) -> str:
        return self.first if self.pa % 2 == 0 else OTHER[self.first]

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
               "count": [self.balls, self.strikes], "pitch_command": cmd, "decision": dict(dec)}
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
        """Phase 2, once the pitch is over (the world is frozen): the batted ball, the count, the score."""
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
            b = self.batter
            self.score[b] += pa_end[1]
            self.pa_results.append({"pa": self.pa + 1, "batter": b, "pa_of_batter": self.pa_of(b),
                                    "result": pa_end[0], "bases": pa_end[1],
                                    "pitches": sum(1 for h in self.history if h["pa"] == self.pa)})
            rec["pa_result"] = pa_end[0]
            self.pa += 1
            self.balls = self.strikes = 0
            if self.pa % 2 == 0 and self.pa >= 2 * PA_PER_SEAT and (
                    self.score["A"] != self.score["B"] or self.pa >= 2 * (PA_PER_SEAT + EXTRA_PAIRS)):
                self.done = True
        self.judged = True
        return rec

    def next_pitch(self):
        assert self.over and self.judged and not self.done
        self._begin()

    # --- results
    def winner(self):
        """More bases; level after the last extra pair: the winner of the last pitch (None while undecided)."""
        a, b = self.score["A"], self.score["B"]
        if a != b:
            return "A" if a > b else "B"
        if not self.done or not self.history:
            return None
        last = self.history[-1]
        won_by_batter = last.get("pa_result") in ("walk", "single", "double", "home run")
        return last["batter"] if won_by_batter else last["pitcher"]

    def decided_by(self):
        if not self.done:
            return None
        return "bases" if self.score["A"] != self.score["B"] else "last pitch"

    def public_rec(self, rec: dict) -> dict:
        out = {"pitch": rec["pitch"] + 1, "plate_appearance": rec["pa"] + 1, "batter": rec["batter"],
               "pitcher": rec["pitcher"], "pitch_type": rec["type"], "radar_mps": rec["radar"],
               "plate_crossing": None if rec["crossing"] is None else {"x": rec["crossing"][1], "z": rec["crossing"][2]},
               "in_zone": rec["zone"], "outcome": rec["outcome"], "count_after": rec["count_after"]}
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
        out = []
        for i in range(4):
            n = max(0, self.n - bbrt.FRAME_GAP_STEPS * (3 - i))
            t = round(n * DT - self.windup, 4)
            out.append({"pitch": self.idx, "n": n, "k": self.k_begin + n, "t": t,
                        "ball": [float(x) for x in self.ball_at(t)], "swing": swp})
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
