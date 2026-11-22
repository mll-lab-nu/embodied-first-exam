"""Embodied First Exam: protocol eai-standard-lockstep/1.0, the standard mode of Embodied Olympics' real-time matches,
on core 0.5 (the table tennis of two Unitree G1s, tabletennis_g1).

The match, the world, the referee, the opponent, the observation, the reviews, the record and the grading are those of
eai-standard-realtime/1.0 (core/realtime.py, unchanged); only the clock differs. The world does not run on the wall
clock: it advances one control step at a time, and only while the seat lets it:

  - the seat lets it advance while one of its `wait {dt}` calls is open (up to that call's target step) or while one of
    its accepted acts waits for the step at which it takes effect;
  - nothing advances while one of the seat's act or observe calls is being handled, so preparing an act never costs
    game time: it takes effect at the step after the state it answers, whatever its wall time;
  - between calls the world stands still (no step is ever taken for a seat that is thinking);
  - every camera frame is drawn before the step at which an observation may ask for it, so an observation always gets
    the frame taken L steps before (L = the declared camera latency), never a later one;
  - the platform's opponent plays without a clock too (core/platform_seat.py with live = False, the rule of core/local.py
    and the in-process screens): after each step the world waits for its program's reply to that step's observation and
    receives it at that step, so its own computing time costs no game time either.

Everything else is eai-standard-realtime/1.0's: acts lowered at a step boundary, the frozen review after every unit
with its time limit (READY_TIMEOUT_S of real time; a missed review is recorded, the world resumes), the start window,
the collect rules of the task (RO_COLLECT_ENDS_MATCH), live grading. /spec timing says `clock = "lockstep"`;
`period_s` is null (no wall time per step). The episode is a realtime episode (header protocol "realtime"): its
replay, video and grading are unchanged. final.json `clock` = "lockstep"; the integrity readings of the wall clock
(world lag, late steps) are 0 by construction.

Run (the sim service's command): python3 -m core.lockstep (cwd = the directory holding core/; the environment of
core/serve.py). The seat must be unmetered (PLAYER_MODE_<seat> = unmetered).
"""
from __future__ import annotations

import math
import os
import signal
import threading
import time
from pathlib import Path

import numpy as np

from . import serve, taskspec
from .realtime import RealtimeService, referee_events, jsonable
from .sport import FINISHED, UNIT_OVER

PROTOCOL_ID = "eai-standard-lockstep/1.0"
RULE = ("the world advances only while you let it: during an open `wait {dt}` (up to dt game seconds) and, for an "
        "accepted act, up to the step at which it takes effect; between your calls it stands still, and computing an "
        "act or an observation takes no game time. The platform's opponent is held to the same rule (the world waits "
        "for its reply after every step). After every point the world freezes for the review as before")
WAIT_FROZEN_MAX_S = 30.0


class LockstepService(RealtimeService):
    protocol_id = PROTOCOL_ID

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.waits = {s: [] for s in self.cfg.seats}       # seat -> target steps of its open wait calls
        self.busy = {s: 0 for s in self.cfg.seats}         # seat -> act / observe calls being handled
        if self.pseats:                                    # the opponent without a clock (core/local.py's rule)
            from .platform_seat import PlatformSeats
            self.pseats.close()
            self.pseats = PlatformSeats(self.sport, self.plugin, self.cfg, self.m, receive=self.sched.platform_receive,
                                        live=False, lock=self.cond, now=lambda: self.m.k,
                                        accept=lambda unit: self.phase == "running" and self.m.unit() == unit,
                                        on_error=lambda side, exc: self.failure(f"platform_seat {side}", exc))

    # ------------------------------------------------------------------ the seat's calls
    def spec_core(self):
        out = super().spec_core()
        t = dict(out.get("timing") or {})
        t.update(clock="lockstep", period_s=None, slowdown=None, policy="lockstep", rule=RULE)
        out["timing"] = t
        out["decision_rule"] = ("program play: your own program may observe and act without a new model response; "
                                "the world waits for you between calls")
        return out

    def routes(self, post):
        r = dict(super().routes(post))
        if post and "act" in r:
            r["act"] = self._held(r["act"])
        if "observe" in r:
            r["observe"] = self._held(r["observe"])
        return r

    def _held(self, fn):
        def call(seat, *a, **kw):
            with self.cond:
                if seat in self.busy:
                    self.busy[seat] += 1
            try:
                return fn(seat, *a, **kw)
            finally:
                with self.cond:
                    if seat in self.busy:
                        self.busy[seat] -= 1
                    self.cond.notify_all()
        return call

    def wait(self, seat, body):
        try:
            d = float(body.get("dt", 0))
        except (TypeError, ValueError, OverflowError, AttributeError):
            d = math.nan
        if not np.isfinite(d) or not 0 < d <= 1:
            return 400, {"error": "dt must be 0..1 game seconds"}
        since = self.team_since(body)
        with self.cond:
            if self.phase in ("prepare", "review"):          # frozen: until the world runs again (as in real time)
                end = time.monotonic() + WAIT_FROZEN_MAX_S
                while (self.phase in ("prepare", "review") and not self.owes_ready(seat)
                       and time.monotonic() < end):
                    self.cond.wait(min(.5, max(.01, end - time.monotonic())))
                return 200, {"now": self.state(seat, since=since), "deadlines": self.deadlines_now()}
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
    def frames_ready(self) -> bool:
        """With the lock held: the frame an observation at the next step may ask for (step k + 1 - L) is drawn (or
        will never be: dropped, failed, a closed stream)."""
        if not self.streams or self.obs_latency is None:
            return True
        target = self.m.k + 1 - int(self.obs_latency)
        for fs in self.streams.values():
            with fs.cond:
                if fs.closed or target in fs.ready or target not in fs.queued:
                    continue
                return False
        return True

    def may_step(self) -> bool:
        """With the lock held: the seat lets the world take the next step, none of its calls is being handled, and the
        frames are drawn."""
        k = self.m.k
        playing = [s for s in self.cfg.seats if not self.seats[s].retired]
        if not playing:
            return True
        for s in playing:
            if self.busy[s] > self.sched.waiting(s):
                return False                    # a call of this seat is being handled (an act not yet queued)
            need = max(self.waits[s], default=k)
            if self.sched.waiting(s):
                need = max(need, k + 1)
            if need <= k:
                return False
        return self.frames_ready()

    def loop(self):
        threading.Thread(target=self.reporter, daemon=True).start()
        try:
            while True:
                with self.cond:
                    if self.phase == "over":
                        return
                    now = time.monotonic()
                    if self.match_deadline is not None and now > self.match_deadline:
                        self.match_deadline = None
                        self.time_up("match_s")
                        continue
                    if self.cap_deadline is not None and now > self.cap_deadline:
                        self.cap_deadline = None
                        self.time_up("wall_cap_s")
                        continue
                    if self.phase in ("prepare", "review"):
                        if self.phase == "prepare" and not self.t0_open():
                            self.check_t0_wait()
                        if self.resume_at is not None and now >= self.resume_at and self.streams_up():
                            if self.m.phase().state == UNIT_OVER:
                                self.ep.write("resume", k=self.m.k)
                                self.m.resume()
                            now, epoch = time.monotonic(), time.time()
                            for st in self.seats.values():
                                st.meter.begin_segment(epoch)
                                st.ready = False
                            starting = self.match_t0 is None
                            if starting:
                                self.mark_match_start()
                            else:
                                self.devgate("running")
                            self.phase, self.anchor, self.segment_start = "running", (now, self.m.k), now
                            if starting:
                                self.match_t0 = now
                                if self.match_window() is not None:
                                    self.match_deadline = now + self.match_window()
                            self.resume_at = self.ready_deadline = None
                            self.ep.write("run", k=self.m.k, started_epoch=epoch)
                            self.take_frames()
                            self.platform_observe()
                            self.bc.event("run")
                            self.cond.notify_all()
                        elif self.ready_deadline and now > self.ready_deadline:
                            self.timeout()
                            continue
                        else:
                            self.cond.wait(.01)
                            continue
                    if self.phase != "running":
                        continue
                    if not self.may_step():
                        self.cond.wait(.05)
                        continue
                    t_lock = time.monotonic()
                    self.apply_pending()
                    t_apply = time.monotonic()
                    events = self.m.step()
                    t_step = time.monotonic()
                    self.take_frames()
                    self.platform_observe()
                    if events:
                        self.diag("event", k=self.m.k, events=jsonable(events))
                        for ev in referee_events(events):
                            if ev["kind"] == "side_retired":
                                self.referee_retired(str(ev.get("side")), str(ev.get("why") or "referee"))
                    self.bc.frame(force=self.m.phase().state != "playing")
                    self.run_steps += 1
                    t_end = time.monotonic()
                    self.lates.append(0.0)               # no wall schedule: never late
                    self.costs.add(lag=0.0, lock=0.0, apply=t_apply - t_lock, step=t_step - t_apply,
                                   host=t_end - t_step)
                    ph = self.m.phase()
                    if ph.state != "playing":
                        self.drop_all("unit_over")
                        self.ep.write("unit_over", k=self.m.k, unit=self.m.unit(), reason=ph.reason)
                        self.bc.event("unit_over", unit=self.m.unit(), reason=ph.reason, scores=self.m.scores())
                        if ph.state == FINISHED:
                            self.end("match_over")
                        else:
                            self.phase = "review"
                            for s in self.due():
                                self.seats[s].count("reviews_due")
                            self.devgate("review")
                            self.run_wall += time.monotonic() - self.segment_start
                            self.segment_start = None
                            self.ready_deadline = time.monotonic() + self.review_window(ph.reason)
                            if not self.due():
                                self.barrier()
                    self.cond.notify_all()
                    if self.phase != "running":
                        self.report_now.set()
        except Exception as exc:  # noqa: BLE001
            self.failure("world", exc)

    def extra_final(self):
        out = dict(super().extra_final())
        out["clock"] = "lockstep"
        return out


def main():
    """core/serve.py main with the lockstep service."""
    import os as _os
    plugin = _os.path.abspath(taskspec.setting("RO_PLUGIN"))
    from .workers import leave_platform_cpus
    world_cpus = leave_platform_cpus()
    sport = serve.load_plugin(plugin)
    ts = taskspec.load()
    cfg = serve.config_from_env(ts, sport.protocol)
    if sport.protocol != "realtime":
        raise ValueError("core.lockstep serves real-time sports only")
    data = Path(taskspec.setting("RCB_DATA"))
    svc = LockstepService(sport, plugin, cfg, data, ts=ts)
    svc.world_cpus = world_cpus
    hosts = taskspec.pairs(taskspec.setting("SEAT_HOSTS"))
    signal.signal(signal.SIGUSR1, lambda *a: threading.Thread(target=lambda: svc.collect(serve.session_events(data)),
                                                              daemon=True).start())
    signal.signal(signal.SIGUSR2, lambda *a: threading.Thread(target=lambda: svc.abort(**serve.abort_request(data)),
                                                              daemon=True).start())
    svc.write_final()
    (data / "server.pid").write_text(str(_os.getpid()))
    threading.Thread(target=svc.loop, daemon=True).start()
    print(f"{sport.name} {cfg.format} service ready ({svc.protocol_id})", flush=True)
    serve.make_server(svc, cfg.seats, hosts, int(taskspec.setting("RCB_PORT"))).serve_forever()


if __name__ == "__main__":
    main()
