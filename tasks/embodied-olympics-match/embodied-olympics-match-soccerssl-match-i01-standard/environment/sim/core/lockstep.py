"""Embodied First Exam: protocol eai-standard-lockstep/1.0, the standard mode of Embodied Olympics' real-time matches.

The match, the world, the referee, the opponent, the observation, the reviews, the record and the grading are those of
eai-standard-realtime/1.0 (core/realtime.py, unchanged); only the clock differs. The world does not run on the wall
clock: it advances one control step at a time, and only while every seat that plays (a built-in seat too) lets it:

  - a seat lets it advance while one of its `wait {dt}` calls is open (up to that call's target step) or while one of
    its accepted acts waits for the step at which it takes effect (the act's own step: the next one, or s + D with a
    declared reaction delay D);
  - nothing advances while any act is still being prepared (the high level's plan, a skill call), so preparing an
    act never costs game time: it takes effect at the step after the state it answers, whatever its wall time;
  - between calls the world stands still (no step is ever taken for a seat that is thinking).

Everything else is eai-standard-realtime/1.0's: one act per (seat, entity) in flight (429), acts lowered at a step
boundary, the frozen review after every unit with its time limit (READY_TIMEOUT_S of real time; a side that misses it
loses, ready_timeout), the start window, the collect rules (a single side whose match has started loses when its
session ends, abandoned), live grading. The reply fields are the same (`now.world` is "running" while the match is in
play, whether or not a step is being taken). /spec timing says `clock = "lockstep"`; `period_s` is null (no wall time per
step). The episode is a realtime episode (header protocol "realtime"): its replay, video and grading are unchanged.

Run (the sim service's command): python3 -m core.lockstep   (cwd = the directory holding core/; the environment of
core/serve.py). Every seat must be unmetered (PLAYER_MODE_<seat> = unmetered) or built-in (RO_BUILTIN_SEATS): this entry starts
no metering proxy.
"""
from __future__ import annotations

import math
import os
import time
from pathlib import Path

import numpy as np

from . import serve
from .realtime import RealtimeService
from .sport import FINISHED, UNIT_OVER

PROTOCOL_ID = "eai-standard-lockstep/1.0"
RULE = ("the world advances only while you let it: during an open `wait {dt}` (up to dt game seconds) and, for an "
        "accepted act, up to the step at which it takes effect (the step after the state it answers); between your "
        "calls it stands still, and preparing an act (planning, a skill call) takes no game time. With two seats the "
        "world advances only while both let it. After every unit the world freezes for the reviews as before")


class LockstepService(RealtimeService):
    protocol_id = PROTOCOL_ID

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.waits = {s: [] for s in self.cfg.seats}      # seat -> target steps of its open wait calls
        self.inflight = {s: 0 for s in self.cfg.seats}    # seat -> act calls not yet returned

    # ------------------------------------------------------------------ the seat's calls
    def spec_core(self):
        out = super().spec_core()
        t = dict(out.get("timing") or {})
        t.update(clock="lockstep", period_s=None, slowdown=None, policy="lockstep", rule=RULE)
        out["timing"] = t
        out["decision_rule"] = ("program play: your own program may observe and act without a new model response; "
                                "one act per seat in flight; the world waits for you between calls")
        return out

    def act(self, seat, body):
        with self.cond:
            self.inflight[seat] += 1
        try:
            return super().act(seat, body)
        finally:
            with self.cond:
                self.inflight[seat] -= 1
                self.cond.notify_all()

    def wait(self, seat, body):
        try:
            d = float(body.get("dt", 0))
        except (TypeError, ValueError, OverflowError):
            d = math.nan
        if not np.isfinite(d) or not 0 < d <= 1:
            return 400, {"error": "dt must be 0..1 game seconds"}
        since = self.team_since(body)
        with self.cond:
            target, unit = self.m.k + int(np.ceil(d / self.m.dt)), self.m.unit()
            self.waits[seat].append(target)
            self.cond.notify_all()
            try:
                while self.phase == "running" and self.m.unit() == unit and self.m.k < target:
                    self.cond.wait(.5)
            finally:
                self.waits[seat].remove(target)
            return 200, {"now": self.state(seat, since=since)}

    # ------------------------------------------------------------------ the world loop
    def may_step(self) -> bool:
        """With the lock held: every seat that plays lets the world take the next step, and no act is being prepared."""
        k = self.m.k
        playing = [s for s in self.cfg.seats if not self.seats[s].retired]
        for s in playing:
            if self.inflight[s] > sum(1 for (ss, _e) in self.pending if ss == s):
                return False                    # an act of this seat is still being prepared (or answered)
        for s in playing:
            need = max(self.waits[s], default=k)
            for (ss, _e), item in self.pending.items():
                if ss == s:
                    need = max(need, max(k, int(item.get("earliest", 0))) + 1)
            if need <= k:
                return False
        return True

    def loop(self):
        try:
            while True:
                with self.cond:
                    if self.phase == "over":
                        return
                    now = time.monotonic()
                    if self.phase in ("prepare", "review"):
                        if self.resume_at is not None and now >= self.resume_at:
                            if self.m.phase().state == UNIT_OVER:
                                self.ep.write("resume", k=self.m.k)
                                self.m.resume()
                            now, epoch = time.monotonic(), time.time()
                            for st in self.seats.values():
                                st.meter.begin_segment(epoch)
                                st.ready = False
                            self.phase, self.anchor, self.segment_start = "running", (now, self.m.k), now
                            self.resume_at = self.ready_deadline = None
                            self.ep.write("run", k=self.m.k, started_epoch=epoch)
                            self.bc.event("run")
                            self.cond.notify_all()
                        elif self.ready_deadline and now > self.ready_deadline:
                            self.timeout()
                            continue
                        else:
                            self.cond.wait(.01)
                            continue
                    if not self.may_step():
                        self.cond.wait(.05)
                        continue
                    try:                                # Embodied First Exam: the control step itself
                        self.apply_pending()
                        events = self.m.step()
                    except Exception as exc:  # noqa: BLE001
                        exc.rcb_where = "world_step"    # its own `where` in final.json errors (tests/grade.py)
                        raise
                    if events:
                        self.diag("event", k=self.m.k, events=_jsonable(events))
                    self.bc.frame(force=self.m.phase().state != "playing")
                    self.run_steps += 1
                    ph = self.m.phase()
                    if ph.state != "playing":
                        for s, _e in self.pending:
                            self.seats[s].count("dropped")
                        self.drop_all("unit_over")
                        self.ep.write("unit_over", k=self.m.k, unit=self.m.unit(), reason=ph.reason)
                        self.bc.event("unit_over", unit=self.m.unit(), reason=ph.reason, scores=self.m.scores())
                        if ph.state == FINISHED:
                            self.end("match_over")
                        else:
                            self.phase = "review"
                            self.run_wall += time.monotonic() - self.segment_start
                            self.segment_start = None
                            self.ready_deadline = time.monotonic() + float(os.environ.get("READY_TIMEOUT_S", "60"))
                            if not self.due():
                                self.barrier()
                    self.cond.notify_all()
                    if self.m.k % 50 == 0 or self.phase != "running":
                        self.write_final()
        except Exception as exc:  # noqa: BLE001
            self.failure(getattr(exc, "rcb_where", "world"), exc)

    def extra_final(self):
        out = super().extra_final()
        out.update(clock="lockstep", timing_policy="lockstep")
        out["sim_lag"] = {"run_steps": self.run_steps, "run_sim_s": self.run_steps * self.m.dt,
                          "run_wall_s": self.run_wall, "period_s": None}
        return out


def _jsonable(x):
    from .diaglog import jsonable
    return jsonable(x)


def main():
    """core/launch.py for unmetered seats, then core/serve.py with the lockstep service."""
    seats = os.environ.get("RO_SEATS", "A,B").split(",")
    builtin = {x.split("=", 1)[0].strip() for x in os.environ.get("RO_BUILTIN_SEATS", "").split(",") if "=" in x}
    metered = [s for s in seats if s not in builtin       # a built-in seat (core/builtin_seat.py): no model plays it
               and os.environ.get(f"PLAYER_MODE_{s}", os.environ.get("RCB_PLAYER_MODE", "model")) != "unmetered"]
    if metered:
        raise SystemExit(f"core.lockstep: seats {metered} are metered; this entry starts no metering proxy")
    data = Path(os.environ.get("RCB_DATA", "/data"))
    data.mkdir(exist_ok=True)
    for s in seats:
        open(data / f"think_calls_{s}.jsonl", "a").close()
    serve.RealtimeService = LockstepService          # core/serve.py picks the service class by sport.protocol
    serve.main()


if __name__ == "__main__":
    main()
