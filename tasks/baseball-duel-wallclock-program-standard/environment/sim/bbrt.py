"""The 100 Hz pitch clock for baseball batting (wall-clock version; shared by the service, its fresh-process replay
and the reference player). The event engine bb.py is the lock-step tasks' engine; its decide() is split into the
same three phases run at different times (bb.Game.decide_begin / decide_finish / next_pitch; identical results).

Per pitch: the pitcher winds up for a seeded time (0.60-1.20 s, the ball in its hand at the release point), releases
(t = 0), the ball flies (bb.Pitch, unchanged). The rig holds its command: none (bat at rest), or a planned swing =
the bat's state when it is square (theta = 0), T s from the control step at which the command took effect. The swing
starts 3.9741 / SPEED s before that (at once if that is already past) and, once started, cannot be changed or stopped.

The pitch is resolved (phase 1, ~1 ms: the executed swing with its seeded scatter and the bat-ball contact):
  - the clock reaches the planned swing start      -> a swing with t = start, delay_s = SWING_DELAY (t_eff < 0, so
    the swing starts exactly at `start`, + the seeded scatter);
  - the ball is TAKE_AFTER s past the plate first   -> a take.
The pitch is over when the clock reaches the contact (or the ball's arrival at the plate) + END_AFTER. Only then is
its outcome judged (phase 2: the batted ball's flight and the fielders, the count; `finish`) and only after the
review is the next pitch generated (phase 3, `next_pitch`): the world is frozen during both, and the count the
batter sees stays the pre-pitch count until the pitch is over.

Time stamps: k = control steps of running world since the game started (frozen time does not count), n = steps since
this pitch's windup began, t = n * DT - windup = time since release.
"""
from __future__ import annotations

import math

import bb

DT = 0.01                       # control clock, s
WINDUP = (0.60, 1.20)           # seeded windup before release, s (multiples of DT)
TAKE_AFTER = 0.03               # no swing started this long after the ball reached the plate: a take
END_AFTER = 0.05                # the pitch is over this long after contact / the plate
SWING_DELAY = -(bb.T_DECISION + 10.0)   # decide()'s t_eff = -10 s: the swing starts at its own start time
FRAME_GAP = 0.03                # observe: 4 frames, 30 ms apart, the last one now
FRAME_GAP_STEPS = 3
T_SQUARE = (5 * math.pi / 3 + math.pi / 6) * bb.S_SS   # time to square = T_SQUARE / SPEED (3.9741 / SPEED)


def windup_s(seed: int, k: int) -> float:
    r = bb._rng(seed, 11, k)                  # its own stream: pitches and scatter are unchanged
    n0, n1 = int(round(WINDUP[0] / DT)), int(round(WINDUP[1] / DT))
    return int(r.integers(n0, n1 + 1)) * DT


class RT:
    def __init__(self, level: int, seed: int | None = None):
        self.G = bb.Game(level, {"seed": seed} if seed is not None else None)
        self.k = 0                             # control steps since the game started
        self.over_recs = []                    # records of pitches that are over (and judged)
        self._begin()

    # --- a pitch
    def _begin(self):
        self.idx = len(self.G.history)
        self.pitch = self.G.pitch
        self.windup = windup_s(self.G.seed, self.idx)
        self.n = 0                             # steps since this pitch's windup began
        self.k_begin = self.k                  # global step of this pitch's first state
        self.plan = None                       # planned swing (not started yet)
        self.rec = None                        # the bb record once the pitch is resolved (swing started / taken)
        self.t_end = None
        self.over = False                      # the pitch is over (the clock reached t_end)
        self.judged = False                    # its outcome has been judged (finish)
        p = self.pitch
        self.t_plate = p.cross[0] if p.cross is not None else p.path[-1][0]

    @property
    def t(self) -> float:
        """Time since release (negative: the windup)."""
        return round(self.n * DT - self.windup, 6)

    def released(self) -> bool:
        return self.t >= 0.0

    def finish(self) -> dict:
        """Phase 2, once the pitch is over (the world is frozen): judge the outcome, update the count."""
        assert self.over and not self.judged
        self.G.decide_finish(self.rec)
        self.judged = True
        self.over_recs.append(self.rec)
        return self.rec

    def next_pitch(self):
        """Phase 3, after the review: the next pitch's flight; its windup starts."""
        assert self.over and self.judged and not self.G.done
        self.G.next_pitch()
        self._begin()

    # --- commands
    def act(self, T, plane, height, speed, reach) -> dict:
        """The bat square T s from now (now = the current control step); returns what the rig will do (or why not).
        As in the duel, a swing command is refused before the release."""
        if not self.released():
            return {"accepted": False, "why": "the ball has not been released yet"}
        if self.rec is not None or self.over:
            return {"accepted": False, "why": "the swing is under way (or the pitch was taken): it cannot be changed"}
        tsq = T_SQUARE / speed
        start = self.t + T - tsq
        late = 0.0
        if start < self.t:
            late = self.t - start
            start = self.t
        self.plan = {"start": round(start, 6), "plane": plane, "height": height, "speed": speed, "reach": reach}
        info = {"accepted": True, "swing_start_in_s": round(start - self.t, 4),
                "square_in_s": round(start - self.t + tsq, 4), "square_later_than_asked_s": round(late, 4),
                "swing_start_t_since_release": round(start, 4)}
        if start <= self.t:
            self._commit_swing()
            info["swing_started"] = True
        return info

    def cancel(self) -> dict:
        if not self.released():
            return {"accepted": True, "note": "no swing planned"}
        if self.rec is not None or self.over:
            return {"accepted": False, "why": "the swing is under way (or the pitch was taken): it cannot be changed"}
        self.plan = None
        return {"accepted": True}

    def _commit_swing(self):
        pl = self.plan
        dec = {"type": "swing", "t": pl["start"], "plane": pl["plane"], "height": pl["height"], "speed": pl["speed"],
               "reach": pl["reach"]}
        self._resolve(dec)

    def _resolve(self, dec):
        rec = self.G.decide_begin(dec, SWING_DELAY)    # phase 1 only (cheap)
        self.rec = rec
        self.plan = None
        t_evt = rec["contact"]["t"] if "contact" in rec else self.t_plate
        self.t_end = max(t_evt + END_AFTER, self.t)

    # --- the clock
    def advance(self, steps: int) -> int:
        """Run up to `steps` control steps; stops early when the pitch is over. Returns the steps run."""
        run = 0
        while run < steps and not self.over:
            self.n += 1; self.k += 1; run += 1
            t = self.t
            if self.rec is None:
                if self.plan is not None and t >= self.plan["start"] - 1e-9:
                    self._commit_swing()
                elif t >= self.t_plate + TAKE_AFTER - 1e-9:
                    self._resolve({"type": "take"})
            if self.rec is not None and t >= self.t_end - 1e-9:
                self.over = True
        return run

    # --- what the batter knows / sees
    def swing_obj(self):
        return self.rec.get("swing_obj") if self.rec is not None else None

    def ball_at(self, t):
        """Ball centre at time t of this pitch (after contact: straight on from the post-contact state)."""
        rec = self.rec
        if rec is not None and "contact" in rec and t > rec["contact"]["t"]:
            pc = rec["post_state"]; d = t - rec["contact"]["t"]
            return (pc[0] + pc[3] * d, pc[1] + pc[4] * d, pc[2] + pc[5] * d)
        return tuple(self.pitch.state_at(max(0.0, t))[:3])

    def view_frames(self):
        """The 4 camera frames 30 ms apart ending now: (n, t since release) each; repeated at the windup start."""
        out = []
        for i in range(4):
            n = max(0, self.n - FRAME_GAP_STEPS * (3 - i))
            out.append((n, round(n * DT - self.windup, 4)))
        return out

    def snapshots(self) -> list[dict]:
        """Display data for the 4 frames (plain floats: sent to the render process)."""
        sw = self.swing_obj()
        swp = None if sw is None else (sw.t0, sw.plane_deg, sw.H, sw.speed, sw.reach)
        return [{"pitch": self.idx, "n": n, "k": self.k_begin + n, "t": t, "ball": [float(x) for x in self.ball_at(t)],
                 "swing": swp} for n, t in self.view_frames()]

    def heard(self):
        h = []
        if self.released():
            h.append({"event": "release", "t": 0.0})
        if self.rec is not None and "contact" in self.rec and self.t >= self.rec["contact"]["t"]:
            h.append({"event": "bat", "t": round(self.rec["contact"]["t"], 3)})
        elif self.t >= self.t_plate and self.pitch.cross is not None and not (self.rec and "contact" in self.rec):
            h.append({"event": "mitt", "t": round(self.t_plate, 3)})
        return h

    def command(self):
        if self.rec is not None:
            if "swing_executed" in self.rec:
                return {"swing": "under way (started at t = %.3f s)" % self.rec["swing_executed"]["t_start"]}
            return "none (the pitch is being taken)"
        if self.plan is not None:
            pl = self.plan
            return {"swing_start_in_s": round(pl["start"] - self.t, 4),
                    "square_in_s": round(pl["start"] - self.t + T_SQUARE / pl["speed"], 4),
                    "plane_deg": pl["plane"], "height": pl["height"], "speed": pl["speed"], "reach": pl["reach"]}
        return "none (the bat at rest)"


def render_snaps(snaps: list[dict], rd) -> bytes:
    """PNG: 2 rows (catcher camera, side camera) x 4 columns (the given frames, oldest left)."""
    import io
    import imageio.v2 as imageio
    import numpy as np
    from PIL import Image, ImageDraw
    rows = []
    for cam in ("catcher", "side"):
        tiles = []
        for sn in snaps:
            sw = None if sn["swing"] is None else bb.Swing(*sn["swing"])
            rd.set(tuple(sn["ball"]), sw, sn["t"])
            im = Image.fromarray(rd.render(cam))
            lab = f"{cam}  t={sn['t']:+.2f}s" + ("  (windup)" if sn["t"] < 0 else "")
            ImageDraw.Draw(im).text((6, 4), lab, fill=(255, 255, 0))
            tiles.append(np.asarray(im))
        rows.append(np.concatenate(tiles, axis=1))
    buf = io.BytesIO()
    imageio.imwrite(buf, np.concatenate(rows, axis=0), format="png")
    return buf.getvalue()


def replay(level: int, seed: int, acts: list[tuple[int, int, dict]], k_end: int) -> "RT":
    """Re-run a game from its (pitch, step, command) list only (no wall time): the commands that took effect at
    control step k of pitch p are applied, in order, before the step k -> k + 1; a judged pitch is followed by the
    next one at once (the review does not change the state). Stops at step k_end or at the end of the game."""
    rt = RT(level, seed)
    i = 0
    while True:
        if rt.over and not rt.judged:
            rt.finish()
        if rt.G.done or rt.k >= k_end:
            break
        if rt.over:
            rt.next_pitch()
        while i < len(acts) and acts[i][0] == rt.idx and acts[i][1] == rt.k:
            apply(rt, acts[i][2])
            i += 1
        if i < len(acts) and (acts[i][0], acts[i][1]) < (rt.idx, rt.k):
            raise ValueError(f"command {i} at pitch {acts[i][0]} step {acts[i][1]} was never reached")
        rt.advance(1)
    if i != len(acts):
        raise ValueError(f"replay consumed {i} of {len(acts)} commands")
    return rt


def apply(rt: RT, dec: dict) -> dict:
    if dec["type"] == "none":
        return rt.cancel()
    return rt.act(dec["t"], dec["plane"], dec["height"], dec["speed"], dec["reach"])
