"""Protocol eai-standard-realtime/1.0: a continuous world paced at slowdown S (one control step every dt x S wall
seconds), frozen at every unit end for the reviews of the seats the referee names (Phase.review).

Phases (core 0.4.0, fw_pattern §7 decision 3; core/phases.py): prepare (until every seat sent start/ready; the
preparation window from t0: a side that has not started by then loses, "no_show"; if none started, the match does not
count) -> running -> review (each seat in Phase.review sends ready WHY PLAN, written by the agent itself: the lead's
decision 10-21, core/reviews.py; the world runs again when every seat due is ready, and at the window's end in any
case: a missing review is recorded, never a loss) -> running ... -> over. POST /<seat>/resign: the side leaves (two sides: it loses). A harness session's end
(SIGUSR1, the collect) is only an event: the seat's programs play on. The wall-clock cap (timing.wall_cap_s from t0,
or the legacy timing.match_s from the match start) is a platform safety cut-off: reason wall_cap, void.
Ready barriers (core 0.2.38): the preparation deadline counts from the service start (the common moment), the review
deadline from the freeze at the unit end; no seat's start or ready moves either; every seat due ready -> the world runs
(again) at once; a seat that misses a deadline gets the rules below. One action interface: see ARBITRATION (/spec).
Two-phase timing and ready (D2, pilot 2026-10-18): start and ready return at once once recorded (they used to block
until the next run); the world runs again as soon as every seat due has sent it (barrier + BARRIER_LEAD_S), which the
seat learns from status or wait (a wait while the world is frozen returns when it runs again, when the match is over,
or at once if a ready is due from the seat; at most WAIT_FROZEN_MAX_S). With PREPARE_TIMEOUT_S set, the start window
opens for every seat at the service start (the same moment for all; a side with a seat that has not started by then
loses, "no_show"; nobody is ever made ready); without it, the START_TIMEOUT_S rule above. MATCH_TIMEOUT_S (optional)
counts from the match start (the first run); when it runs out the match ends as at the collect (Service.time_up).
Deployment record (D3, core/deploys.py): every act's program identity (request headers) on its act_received row and
final.json `deploys`; record only.
Acts (core 0.3.0: one pipeline, core/acts.py): a request id makes a resent act take effect at most once; a batch
({"acts": [...]}, one act per entity) takes effect at one boundary; one act per (seat, entity) in flight (429); program
play needs a live metered session, per-response play a fresh completed model response (think_clock.py); the high
action layer prepares off the world lock (in the seat's plan worker) and is lowered at the next control-step boundary
(acts.ActionQueue: the layer's tick, the delayed commands due, then the acts in arrival order), where the whole batch of
ready acts takes effect together, or `delay_steps` later (the effect step is what the episode logs). Effect step
(core 0.5.0, decided 10-28): an act received at step r (the step the world is at when the service admits it) takes
effect at e = r + L, L the action layer's planning budget (0 on the joint layer), the same for every seat. The
declared reaction delay D of core 0.2.18 - 0.4.9 (e = r + D + L) is gone: a program's own compute and transport time
is the program's business, the world does not wait for it; the reaction report (final.json `reaction`) shows each
seat's program latency, the effect step minus the step of the latest world state the seat had been sent (`seen`), as
a diagnostic. An act whose layer plans nothing (no snapshot job) is queued under the admission's lock, so at L = 0 it
always takes effect at the next boundary. Observations may carry a query (observation
parameters, e.g. which camera) that the sport validates. Reply images (core 0.2.8): an act that takes effect at once
gets the images of its result (Match.reply_views), snapshotted at the effect step under the lock and drawn off the
lock after the act's timing is taken (`wall_s_after_request` excludes it; `render_wall_s` reports it), like an
observation; the world runs on meanwhile.
The world thread (core 0.4.0, fwspec integrity): it only applies the boundary and steps the world; final.json is
written by a reporter thread (REPORT_EVERY_S, and at once at a freeze or the end) from a snapshot taken under the lock,
drawing happens in the seats' render workers (lower CPU priority, core/workers.py), and every step's lag behind its
schedule and costs (lock wait, boundary, Match.step, Host work) go to final.json `integrity` (with the late acts:
plan_miss, the late drawings: render_miss, the observations' age in steps) and slow_step rows. Observations (core
0.4.0, eo-seat/1 ObserveReply): the image's newest frame, taken at step c, is delivered at step c + L, L the task's
declared camera latency (sensors.cameras[].latency_steps; a gen-1 task: sport.toml [observation] latency_steps;
RO_CAMERA_LATENCY_STEPS, an override), never earlier and the same for every seat; a drawing that ends after c + L is
late (counted) and delivered at once; the reply's state (`now`) is the world's at delivery; `frames` stamp each frame's
step and available step. Without a declared latency the image is delivered when drawn (no render_miss).
"""
from __future__ import annotations

import base64
import gc
import json
import os
import math
import threading
import time

import numpy as np

from . import deploys as deploys_mod
from . import sources
from . import spec as spec_mod
from .acts import ActionQueue, ActPipeline, batch_of, current_request, derive_limits
from .diaglog import jsonable, view_steps
from .episode import reaction_report
from .service import CAMERA_KIND, Later, Service, camera_ids, camera_latency, camera_model, frame_stamps
from .sport import FINISHED, UNIT_OVER, PluginFault, Refused, parse_action, referee_events


def query_of(body) -> dict | None:
    q = (body or {}).get("query")
    if q is None:
        return None
    if not isinstance(q, dict) or len(json.dumps(q)) > 4096:
        raise Refused("query must be a JSON object of at most 4 KiB")
    return q


WAIT_FROZEN_MAX_S = 30.0       # D2: a wait while the world is frozen returns after at most this (wall seconds)
REPORT_EVERY_S = 1.0           # core 0.4.0: the mid-match final.json, from the reporter thread (wall seconds)
GC_FREEZE_EVERY_S = 10.0       # the reporter freezes the heap's long-lived objects this often (gc.freeze)
HEAVY_EVERY_S = 30.0           # the mid-match final.json's percentiles (integrity, sim_lag, the seats' summaries) are
                               # recomputed at most this often; maxima and counts are current at every write


STALL_PROBE_S = 0.25           # a step's lag or one of its parts longer than this: the slow_step row carries the host's
                               # pressure stall information (host_pressure), to tell a host stall from the world's own cost


def host_pressure() -> dict | None:
    """The host's pressure stall information (Linux PSI, /proc/pressure/{io,cpu,memory}): per resource the share of
    time some (or all) tasks waited, over the last 10 / 60 / 300 s (avg10, avg60, avg300, %) and the total (us). None
    where the kernel has none. Read only for a slow step (a few small /proc reads, no disk IO)."""
    out = {}
    for res in ("io", "cpu", "memory"):
        try:
            with open(f"/proc/pressure/{res}") as f:
                rows = f.read().split("\n")
        except OSError:
            continue
        r = {}
        for line in rows:
            parts = line.split()
            if not parts:
                continue
            kv = dict(x.split("=", 1) for x in parts[1:] if "=" in x)
            try:
                r[parts[0]] = {k: (float(v) if k != "total" else int(v)) for k, v in kv.items()}
            except ValueError:
                continue
        out[res] = r
    return out or None


class StepCosts:
    """The world thread's timing (core 0.4.0, the integrity report: fw_pattern 原则 4): per control step the world's
    lag behind its schedule at the step's start, the wait for the world lock, and the cost of the boundary (the acts'
    lowering: an action layer planning at the boundary), of Match.step (physics, an in-world opponent, the referee)
    and of the Host's own work; percentiles in final.json `integrity`. A step whose boundary, Match.step or Host
    work took longer than SLOW_S is counted in `slow` by what took the time (and gets a diagnostic slow_step row)."""
    KEYS = ("lag", "lock", "apply", "step", "host")
    SLOW_S = 0.05

    def __init__(self):
        from array import array
        self.v = {k: array("f") for k in self.KEYS}
        self.mx = {k: 0.0 for k in self.KEYS}          # running maxima (the mid-match final.json, O(1))
        self.slow = {"apply": 0, "step": 0, "host": 0, "lock": 0}

    def add(self, **kw) -> list:
        """Record one step; returns what took longer than SLOW_S (empty for a normal step)."""
        for k, x in kw.items():
            x = max(0.0, float(x))
            self.v[k].append(x)
            if x > self.mx[k]:
                self.mx[k] = x
        slow = [k for k in self.slow if kw.get(k, 0.0) > self.SLOW_S]
        for k in slow:
            self.slow[k] += 1
        return slow

    def copy(self) -> "StepCosts":
        out = StepCosts.__new__(StepCosts)
        out.v = {k: a[:] for k, a in self.v.items()}
        out.mx = dict(self.mx)
        out.slow = dict(self.slow)
        return out

    @staticmethod
    def stats(a) -> dict | None:
        if not len(a):
            return None
        x = np.asarray(a, dtype=float)
        return {"p50": round(float(np.percentile(x, 50)), 4), "p99": round(float(np.percentile(x, 99)), 4),
                "max": round(float(x.max()), 4), "n": int(x.size)}

    def report(self) -> dict:
        return {k: self.stats(self.v[k]) for k in self.KEYS}
# One action interface (core 0.2.38): the public arbitration rule, /spec `arbitration` (RealtimeService.arbitration).
ARBITRATION = ("every action of a seat, sent by you from your shell (game act) or by a program you run, goes through"
               " the same act endpoint under the same rules: no other or faster channel. A batch {\"acts\": [act, "
               "...]} carries one act per robot (each names its robot as `entity`; a robot twice: 400; any robot "
               "whose act would conflict or exceed its in-flight limit: the whole batch is refused) and takes effect"
               " at one control-step boundary. An act may carry a request_id (1-64 characters of A-Z a-z 0-9 _ -): "
               "the same id again (a resend after a lost reply) waits for the first request or gets its reply, "
               "marked duplicate; it never takes effect twice (game and ro_client do this for you). An act received "
               "at step r (the step the world is at when the service admits it: received_step) takes effect at the "
               "control-step boundary e = r + L (effect_step; L the action layer's planning budget, "
               "layer_delay_steps in `action`, 0 on the joint layer), the same for every seat and whatever you had "
               "observed: the world never waits for your program, so the time your program takes to answer what it "
               "observed is your own latency; the reply comes once it took effect, after up to L + 1 control steps "
               "((L + 1) x period_s wall seconds), so a program that waits for each reply before its next act acts "
               "at most once every L + 1 steps; to act at every step, send acts without waiting for their replies "
               "(ro_client: Seat.act(cmd, wait=False); or several connections): the effect step stays the same. Up "
               "to in_flight_per_robot acts per robot may be received and not yet in effect (more: 429 in_flight); a"
               " second act for the same robot with the same effect step, i.e. received at the same step, is refused"
               " (409 effect_step_conflict). At a boundary the platform's own per-step command comes first, then the"
               " delayed commands due, then the acts due in arrival order; a command stays in force until a later "
               "applied command replaces it (the action layer's rule), so the latest applied command wins. The "
               "record (final.json deploys / control_sources) names the source of every applied act: agent (your own"
               " shell), program (a program process, via game act or the ro_client module), program_raw (no identity"
               " headers: a program speaking HTTP itself; it works the same, recorded as a program of unknown "
               "version)")


def platform_latency(parity: dict | None) -> dict:
    """Core 0.5.0 (Chi 10-29): {side: {"commands", "program_latency_steps": {min, p50, p90, max, n}}} of every
    measured platform side (core/parity.py: effect step - decision step, the queue's or the world's own report): its
    planner's own time, a diagnostic like a seat's program latency (final.json reaction.platform)."""
    out = {}
    for side, rep in (parity or {}).items():
        if not isinstance(rep, dict):
            continue
        world = rep.get("world") if isinstance(rep.get("world"), dict) else {}
        lat = rep.get("action_delay_steps") or world.get("action_delay_steps")
        out[str(side)] = {"commands": int(rep.get("commands") or world.get("commands") or 0),
                          "program_latency_steps": lat}
    return out


STREAM_START_S = 120.0                           # core 0.5.4: the longest the start waits for the camera workers


class _Inline:
    """core 0.5.4: a FrameStream worker that draws in the service's own process (Views.draw: no render worker)."""

    def __init__(self, svc, seat):
        self.svc, self.seat = svc, seat

    def call(self, job, wait=True):
        return self.svc.draw(self.seat, job) or {}

    def close(self):
        pass


def plan_workers_report(raw: dict) -> dict:
    """core 0.5.6 (Chi 10-31): per seat with plan workers: their number, their CPUs (as each reported them), the plans'
    time (seconds: p50 / p99 / max) and the acts that took effect late (after r + L: a plan back after its budget)."""
    out = {}
    for s, r in raw.items():
        ps = sorted(r.pop("plan_s"))
        n = len(ps)
        out[s] = dict(r, plans=n, plan_s=({"p50": round(ps[n // 2], 5), "p99": round(ps[min(n - 1, int(.99 * (n - 1)))],
                                                                                   5), "max": round(ps[-1], 5)}
                                         if n else None))
    return out


class RealtimeService(Service):
    protocol = "realtime"
    protocol_id = "eai-standard-realtime/1.0"
    draw_images = True                           # core 0.5.4: False (a practice world without cameras): no images

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.slowdown = float(self.cfg.slowdown or 20)
        if not np.isfinite(self.slowdown) or self.slowdown <= 0:
            raise ValueError("invalid slowdown")
        self.period = self.m.dt * self.slowdown
        self.ready_deadline = self.resume_at = self.anchor = self.segment_start = None
        # ready barrier (core 0.2.38): ONE preparation deadline for every seat, from the common moment (core 0.3.0:
        # t0, the start barrier, or the service start); no seat's start moves it. Before t0: none (on_t0 sets it)
        self.ready_deadline = self.t0_mono + self.prep_window() if self.t0_open() else None
        self.match_deadline = None               # D2: MATCH_TIMEOUT_S after the match start
        self.cap_deadline = self.wall_cap_deadline()             # core 0.4.0: timing.wall_cap_s after t0
        self.delay = int(getattr(self.layer, "delay_steps", 0) or 0)
        spec_mod.check_removed(self.decl)                      # core 0.5.0: no reaction delay D (e = r + L)
        self.plan = self.layer_delay()                         # L: the action layer's planning budget
        self.k_cap = self.ts.in_flight_per_robot(self.plan)    # K: acts per robot received, not yet in effect
        self.seen: dict = {}                                   # seat -> step of the latest world state sent to it
        self.flight = {s: {} for s in self.cfg.seats}          # seat -> robot -> [effect steps of its open acts]
        # core 0.3.0: one action pipeline (core/acts.py): the boundary step, the request entry, the derived limits
        self.sched = ActionQueue(self.layer, delay=self.delay, apply=self.sched_apply, seats=self.tick_seats,
                                 reply_job=self.reply_job, on_effect=self.sched_effect, on_drop=self.sched_drop,
                                 plan=self.plan, platform_wait=False, on_platform=self.sched_platform)
        self.platform_stats: dict = {}           # core 0.4.1: side -> {commands} (core 0.5.0: never a plan miss)
        self.pipeline = ActPipeline(self)
        self.limits = derive_limits(self.m.dt, self.slowdown, {s: len(self.m.entities(s)) for s in self.cfg.seats},
                                    self.ts, in_flight=self.k_cap)
        self.lates, self.run_steps, self.run_wall = [], 0, 0.0
        self.late_max = 0.0                      # running max of lates (the mid-match final.json)
        self.heavy = {"t": None, "integrity": None, "sim_lag": None}   # the mid-match percentiles (HEAVY_EVERY_S)
        self.costs = StepCosts()                 # core 0.4.0: the world thread's timing (final.json integrity)
        self.report_now = threading.Event()      # core 0.4.0: the world loop asks the reporter for final.json
        # core 0.4.0 (fwspec sensors.cameras[].latency_steps): the observation's newest frame, taken at step c, is
        # delivered at c + L (the task's declaration; a gen-1 task: sport.toml [observation] latency_steps); None: not
        # declared (delivered when drawn, no render_miss)
        self.obs_latency = camera_latency(self.ts, self.decl)
        self.camera_ids = camera_ids(self.ts)
        for st in self.seats.values():
            st.stats.update(attempts=0, applied=0, refused=0, refused_invalid=0, dropped=0, observations=0, plan_s=[],
                            act_s=[], obs_age_s=[], obs_age_steps=[])
        self.t_built = time.monotonic()
        self.streams = self.init_streams()      # core 0.5.4: the every-step camera (core/stream.py), {} = on request
        # core 0.5.6 (core/platform_seat.py, Chi 10-31): a platform side that plays as a player seat: its program in its
        # own process on its own CPUs, its observation after every step, its replies received like a seat's acts
        from .platform_seat import PlatformSeats
        self.pseats = PlatformSeats(self.sport, self.plugin, self.cfg, self.m, receive=self.sched.platform_receive,
                                    live=True, lock=self.cond, now=lambda: self.m.k,
                                    accept=lambda unit: self.phase == "running" and self.m.unit() == unit,
                                    on_error=lambda side, exc: self.failure(f"platform_seat {side}", exc))
        self.obs_wall = []                       # core 0.5.4: the observe handler's wall time (s), every observation

    def init_streams(self) -> dict:
        """core 0.5.4 (core/stream.py): with the task's camera model "stream" (TaskSpec sensors.delivery =
        every_step; a gen-1 task: sport.toml [observation] camera_model; RO_CAMERA_MODEL) and a declared latency L, one
        FrameStream per seat: K camera workers (RO_CAMERA_WORKERS), the seat's render worker the first of them."""
        if (camera_model(self.ts, self.decl, self.environ) != "stream" or self.obs_latency is None
                or not self.draw_images):
            return {}
        from .stream import FrameStream
        from .workers import ProcessWorker
        # core 0.5.5: a sport that draws its own images (Match.camera_job) streams too: its Match learns the camera model
        # before its first camera job (Match.camera_model = "stream": a job of the current step's frame only), and the
        # extra workers are the sport's own render kind (the core's camera kind cannot draw a sport's job)
        if not self.cameras:
            try:
                self.m.camera_model = "stream"
            except AttributeError:
                pass
        kind = CAMERA_KIND if self.cameras else "render"
        k = max(1, int(self.setting("RO_CAMERA_WORKERS") or 1))
        out = {}
        for s in self.cfg.seats:
            if ("render", s) in self.workers:          # the sport's render workers: K camera worker processes, started
                make = (lambda i, s=s: ProcessWorker(self.plugin, kind, s, self.cfg.to_json()))   # and warmed
                try:                                   # up now (the preparation), never at the first frame
                    warm = self.camera_job(s)[0]
                except Exception:  # noqa: BLE001
                    warm = None
                out[s] = FrameStream(make, k, self.obs_latency, lambda: self.m.k,
                                     first_worker=self.workers[("render", s)], warm_job=warm)
            else:                                      # drawn in this process (one at a time): one drawing thread
                out[s] = FrameStream((lambda i, s=s: _Inline(self, s)), 1, self.obs_latency, lambda: self.m.k)
        return out

    def streams_up(self) -> bool:
        """core 0.5.4: the world starts running only once every seat's camera workers are up and warmed (at most
        STREAM_START_S after the service start): a frame of the match never waits for a worker's start."""
        if not self.streams or self.match_t0 is not None:
            return True
        if all(fs.started.is_set() for fs in self.streams.values()):
            return True
        return time.monotonic() - self.t_built > STREAM_START_S

    def take_frames(self):
        """With the lock held, after a step (and when the world starts running): every seat's frame of this step
        (a job snapshot; drawn off the lock by its FrameStream)."""
        if not self.streams:
            return
        k, unit = self.m.k, self.m.unit()
        for s, fs in self.streams.items():
            try:
                job, meta = self.camera_job(s)
            except Exception as exc:  # noqa: BLE001  (a sport's camera hook: never stop the world for a picture)
                self.diag("frame_failed", seat=s, k=k, error=repr(exc)[:200])
                continue
            fs.submit(k, unit, job, meta)

    def platform_observe(self):
        """With the lock held, after a step (and when the world starts running): each platform seat's observation of
        this step to its program (core/platform_seat.py), while the unit is in play."""
        if not self.pseats:
            return
        try:
            if self.m.phase().state != "playing":
                return
            self.pseats.observe(self.m, self.m.k, self.m.unit())
        except Exception as exc:  # noqa: BLE001  (the plugin's observation hook: a technical failure, as a seat's)
            self.failure("platform_observe", exc)

    def routes(self, post):
        if post:
            return {"start": self.ready, "ready": self.ready, "act": self.pipeline.handle, "wait": self.wait,
                    "observe": self.observe, "say": self.say, "team": self.team, "session": self.open_session,
                    "resign": self.resign}
        return {"spec": self.spec, "status": self.status, "observe": self.observe, "team": self.team}

    def spec_core(self):
        return {"timing": {"slowdown": self.slowdown, "control_dt": self.m.dt, "period_s": self.period,
                           "policy": "report_only", "effect_delay_steps": self.delay},
                "action": {"layer_delay_steps": self.plan,
                           "in_flight_per_robot": self.k_cap, "batch": True,
                           "rule": "an act received at step r (the step the world is at when the service admits it) "
                                   f"takes effect at step r + L (L = {self.plan}); the world does not wait for your "
                                   f"program; at most {self.k_cap} per robot in flight; "
                                   "the same effect step twice for a robot: 409 effect_step_conflict"},
                "start": self.start_rule(),
                "ready": {"returns": "at once, once recorded (start and review alike)",
                          "resume": "the world runs again as soon as every seat due has sent ready (start in the "
                                    "preparation, ready WHY PLAN in a review); learn it from status (phase, world) or "
                                    "wait, which while the world is frozen returns when it runs again, when the match "
                                    "is over, or at once if a ready is due from you",
                          "review_timeout_s": self.review_window(),
                          **({"review_timeout_by_reason_s": {str(k): float(v) for k, v in
                                                             (self.ts.review.get("windows_s") or {}).items()}}
                             if self.ts.review.get("windows_s") else {}),
                          "review_rule": "in a review every seat named by the referee sends ready WHY PLAN within "
                                         "review_timeout_s (review_timeout_by_reason_s[the unit's end reason] where "
                                         "given) of the freeze (the end of the unit, the same moment for "
                                         "every seat; no seat's ready moves it); " + self.review_authorship() +
                                         "; the world runs again as soon as every seat due is ready, and at the "
                                         "window's end in any case: a missing review never loses the match, it is "
                                         "recorded (review_missing)"},
                "resign": {"endpoint": "POST /<seat>/resign {\"confirm\": true}",
                           "rule": "your side leaves the match: with two sides it loses and the match ends; with more "
                                   "it retires (its robots perform the safe exit action) and the others go on"},
                "arbitration": ARBITRATION,
                "phases": self.phase_rules(),
                "failure_rule": self.failure_rule(),
                "decision_rule": ("program play: your own program may observe and act without a new model response; "
                                  "one act per seat in flight" if self.ts.runtime.get("act_rule") == "program" else
                                  "one fresh completed model response per act, after both players resume")}

    def start_window(self) -> float:
        """The preparation window when the task sets none: the review window (as before core 0.3.0)."""
        return self.review_window()

    def review_window(self, reason: str | None = None) -> float:
        """TaskSpec timing.review_s (READY_TIMEOUT_S, default 60 s): a review's window from the freeze; core 0.5.2: a
        unit that ends for `reason` (Phase.reason, e.g. half_time) takes the TaskSpec's review.windows_s[reason] when
        the Task declares one (eo-taskspec/1 review.windows_s; the sport's [timing] review_windows_s)."""
        own = (self.ts.review.get("windows_s") or {}).get(reason) if reason else None
        return float(own) if own is not None else float(self.ts.timing["review_s"])

    # ------------------------------------------------------------------ replies
    def state(self, seat, query=None, since=None):
        core = {"phase": self.phase, "done": self.phase == "over", "reason": self.reason,
                "ready": {s: st.ready for s, st in self.seats.items()},
                "world": "running" if self.phase == "running" else "frozen", "step": self.m.k,
                "t_sim": self.m.k * self.m.dt}
        self.seen[seat] = self.m.k              # every reply's `now` is a world state the seat has seen
        if self.retired:
            core["retired"] = list(self.retired)
        pm = getattr(self, "post_match_view", lambda: None)()   # core 0.4.9: after the whistle (practice: none)
        if pm:
            core["post_match"] = pm
        return {**core, **self.observation(seat, query, since)}

    def status(self, seat, body=None):
        since = self.team_since(body)
        with self.cond:
            out = self.state(seat, since=since)
        disk = self.disk_view(seat)                  # persistent: the soft cap (`game status` adds the use)
        if disk:
            out = {**out, "disk": disk}
        return 200, out

    def ready(self, seat, body):
        st = self.seats[seat]
        st.meter.settle()                                   # never under the world lock (may wait for a stream)
        with self.cond:
            early = self.before_t0(seat)                    # core 0.3.0: the start barrier
            if early:
                return early
            if self.phase not in ("prepare", "review"):
                return 409, {"error": "not awaiting ready", "now": self.state(seat)}
            if st.retired:
                return 409, {"error": "your side has retired"}
            if self.phase == "review" and seat not in self.due():
                return 409, {"error": "no review is due from you now"}
            unit = self.m.unit()
            if st.ready:
                return 409, {"error": "ready already submitted"}
            why, plan = body.get("why", ""), body.get("plan", "")
            if not isinstance(why, str) or not isinstance(plan, str) or len(why) > 2000 or len(plan) > 2000:
                return 400, {"error": "why and plan must be strings of at most 2000 characters", "code": "bad_request"}
            if self.phase == "review":                    # the lead 10-21: from the agent itself
                refused = self.review_gate(seat, why, plan, {"unit": unit, "k": int(self.m.k)})
                if refused:
                    return refused[0], {**refused[1], "now": self.state(seat), "deadlines": self.deadlines_now()}
            st.joined = st.ready = True
            # ready barrier (core 0.2.38): the deadlines were set when the phase opened (prepare: the service start;
            # review: the freeze at the unit end); a ready never sets or moves them
            ident = deploys_mod.current()
            src = sources.tag(ident)                          # core 0.3.0: the source is recorded (any policy)
            proc = (ident or {}).get("proc")                  # core 0.4.0: and the process path (seat-authorised)
            if self.phase == "review":
                empty = not why.strip() or not plan.strip()   # core 0.4.0: accepted, recorded for the diagnostics
                st.count("reviews_submitted")
                st.count("reviews_written")
                if empty:
                    st.count("reviews_empty")
                self.reviews.append({"seat": seat, "after_unit": unit, "why": why, "plan": plan, "source": src,
                                     **({"proc": proc} if proc else {}), **({"empty": True} if empty else {})})
            self.ep.write("ready", seat=seat, unit=unit, why=why, plan=plan, source=src,
                          **({"proc": proc} if proc else {}))
            self.barrier()
            self.cond.notify_all()
            # D2: ready returns at once (it used to block until the next run); the world resumes when every seat
            # due is ready (barrier + BARRIER_LEAD_S): status / wait tell the seat
            return 200, {"accepted": "ready", "now": self.state(seat),
                         "resume": "when every required seat is ready",
                         "waiting_for": [s for s in self.due() if not self.seats[s].ready],
                         "deadlines": self.deadlines_now()}

    def barrier(self):
        if all(self.seats[s].ready for s in self.due()):
            self.resume_at = time.monotonic() + float(self.ts.timing["barrier_lead_s"])

    def due(self):
        seats = self.cfg.seats if self.phase == "prepare" else self.m.phase().review
        return [s for s in seats if not self.seats[s].retired]

    def act(self, seat, body):
        """POST /<seat>/act: the action pipeline (core/acts.py ActPipeline -> act_step)."""
        return self.pipeline.handle(seat, body)

    def act_step(self, seat, body):
        """The protocol step of the action pipeline: parse every act, admit it per (seat, entity), queue it for the
        boundary (acts.ActionQueue) and wait for its effect -> (code, reply, admitted)."""
        st = self.seats[seat]
        many = batch_of(body)
        if many is not None and not all(isinstance(b.get("entity"), str) and b["entity"] for b in many):
            raise Refused("every act of a batch names its entity (one act per entity)")
        cmds = []
        for b in (many if many is not None else [body]):
            try:
                cmd = parse_action(self.layer, seat, b, self.m, {})
            except Refused as exc:              # a malformed action: the player's own error, never a failure
                with self.cond:
                    if isinstance(exc, PluginFault):      # core 0.4.0: the plugin's fault (recorded), not the player's
                        self.plugin_fault(seat, exc)
                    else:
                        self.refused_invalid(seat, exc)
                raise
            cmds.append((cmd, str(cmd.get("entity", "")) if isinstance(cmd, dict) else ""))
        if many is not None:
            ents = [e for _, e in cmds]
            if not all(ents):
                raise Refused("every act of a batch names its entity (one act per entity)")
            if len(set(ents)) != len(ents):
                raise Refused("an entity appears twice in the batch: one act per entity")
        return self.act_admit(seat, st, cmds, many is not None, time.monotonic())

    def act_admit(self, seat, st, cmds, batch, arrived):
        """Admission (eo-seat/1 9.5): the phase -> the metering -> under the lock the receive step r and the effect
        step e = r + L; per robot a second act with the same e is refused (409 effect_step_conflict), more than
        K open acts too (429 in_flight); then the records, the planning off the lock, the queue, the effect. An act
        batch whose layer plans nothing (every snapshot job None) is queued here, under the admission's lock (core
        0.5.0): no world step can pass between its receipt and its queueing, so at L = 0 it takes effect at the next
        boundary, never late."""
        n = len(cmds)
        ents = [entity for _, entity in cmds]
        with self.cond:
            st.count("attempts", n)
            first = st.stats["attempts"] - n
            early = self.before_t0(seat)                    # core 0.3.0: the start barrier
            if early:
                return (*early, False)
            if self.phase != "running":
                return 409, {"error": "the match is over" if self.phase == "over" else "world is not running",
                             "code": "match_over" if self.phase == "over" else "not_running",
                             "now": self.state(seat)}, False
            if st.retired:
                return 409, {"error": "your side has retired", "code": "side_retired"}, False
            unit = self.m.unit()
        if not st.meter.decided_by_model():
            with self.cond:
                st.count("refused")
                self.ep.write("refused_not_model", seat=seat, unit=unit)
            return 429, {"error": "act needs a fresh completed response started after resume, one act per response"}, \
                False
        receipt = st.meter.last_call()
        rid = current_request()
        items, jobs = [], []
        with self.cond:
            if self.phase != "running" or self.m.unit() != unit:
                return 409, {"error": "unit ended during response confirmation", "code": "unit_ended"}, False
            r = self.m.k                                # the receive step (core 0.4.0, fw_pattern §7 decision 4)
            e = r + self.sched.lead()                   # its effect step: r + L, whatever the seat had seen
            seen = self.seen.get(seat)                  # diagnostics only (the reaction report)
            fl = self.flight[seat]
            for entity in ents:
                if e in fl.get(entity, ()):
                    st.count("refused_conflict")
                    return 409, {"error": f"an act for {'robot ' + entity if entity else 'your robot'} already takes "
                                          f"effect at step {e} (received at step {r}): one act per robot per step" +
                                          ("; the whole batch is refused" if batch else ""),
                                 "code": "effect_step_conflict", "now": self.state(seat)}, False
            for entity in ents:
                if len(fl.get(entity, ())) >= self.k_cap:
                    st.count("act_busy")            # FWTEST 10-19: an act refused for the in-flight limit, counted
                    return 429, {"error": f"{'robot ' + entity if entity else 'your robot'} has {self.k_cap} act(s) "
                                          "received and not yet in effect (in_flight_per_robot)" +
                                          (": the whole batch is refused" if batch else ""),
                                 "code": "in_flight"}, False
            for entity in ents:
                fl.setdefault(entity, []).append(e)
            for i, (cmd, entity) in enumerate(cmds):
                jobs.append(self.layer.snapshot(seat, cmd, self.m, first + i + 1))
                act_id = self.acts.new(seat)            # diagnostics (core 0.2.25): act -> observation -> effect
                dep = self.deploy_client(seat, self.m.k)        # D3: the program version that sent it
                self.ep.write("act_received", seat=seat, unit=unit, decision=cmd, model_call=receipt, k=self.m.k,
                              act_id=act_id, obs_id_last=self.acts.last_obs.get(seat), seen=seen,
                              received_step=r, effect_step=e,
                              entity=entity or None, client=deploys_mod.current(),
                              deploy=dep["n"] if dep else None, actor=dep["actor"] if dep else None,
                              **({"request_id": rid} if rid else {}), **({"batch": [i, n]} if batch else {}))
                item = {"seat": seat, "unit": unit, "cmd": cmd, "prepared": None, "arrived": arrived, "result": None,
                        "act_id": act_id, "entity": entity, "deploy": dep, "received": r}
                if seen is not None:
                    item["seen"] = seen                 # the reaction report (core 0.2.23): the program latency
                items.append(item)
            queued = all(job is None for job in jobs)   # core 0.5.0: nothing to plan, queued under this lock
            if queued:
                self.sched.submit(items)
        try:
            return self.act_effect(seat, st, items, jobs, unit, batch, r, e, queued)
        finally:
            with self.cond:
                for entity in ents:
                    open_ = self.flight[seat].get(entity)
                    if open_ and e in open_:
                        open_.remove(e)

    def act_effect(self, seat, st, items, jobs, unit, batch, r, e, queued=False):
        """The planning off the lock, the queue (unless `queued` already: nothing to plan), the wait for the effect
        and the receipt (after the effect)."""
        for item, job in zip(items, jobs):              # admitted: from here on the request id keeps its reply
            if job is not None:
                item["prepared"] = (self.plan_call(seat, job) if self.layer.worker
                                    else self.layer.prepare(job))
        with self.cond:
            for item in items:
                if isinstance(item["prepared"], dict) and "worker_s" in item["prepared"]:
                    st.sample("plan_s", item["prepared"]["worker_s"])
            if not queued and (self.phase != "running" or self.m.unit() != unit):
                for item in items:
                    st.count("dropped")
                    self.dropped(item, seat, "unit_over_planning" if self.phase != "over" else "match_over")
                return 409, {"error": "unit ended during planning", "code": "unit_ended",
                             "now": self.state(seat)}, True
            if not queued:
                self.sched.submit(items)
            while (any(x["result"] is None and "dropped" not in x for x in items) and self.phase == "running"
                   and self.m.unit() == unit):
                self.cond.wait(.5)
            now = self.state(seat)
        if not batch:
            item = items[0]
            if item["result"] is None:
                return 409, {"error": "unit ended before effect", "code": "unit_ended", "now": now}, True
            out = {"call": "act", "act_id": item["act_id"], "received_step": r, "effect_step": e,
                   "took_effect": item["result"], "now": now}
        else:
            out = {"call": "act", "received_step": r,
                   "results": [{"entity": x["entity"], "robot": x["entity"], "act_id": x["act_id"],
                                "effect_step": e, "took_effect": x["result"]}
                               if x["result"] is not None else
                               {"entity": x["entity"], "robot": x["entity"], "act_id": x["act_id"],
                                "error": "unit ended before effect", "code": "unit_ended"}
                               for x in items], "now": now}
        for item, res in zip(items, out.get("results") or [out]):
            if item.get("images") is not None:          # drawn off the lock: the world runs on
                try:
                    res["observation"] = self.reply_images(seat, item["images"])
                except Exception as exc:  # noqa: BLE001
                    self.failure("act_images", exc)
                    return 500, {**out, "error": "technical failure"}, True
        if batch and not any(x["result"] is not None for x in items):
            return 409, {**out, "error": "unit ended before effect", "code": "unit_ended"}, True
        return 200, out, True

    def apply_now(self, seat, low, act=None):
        """Log and apply one low-level command. An act's row (act = its pending item) also carries `seen`, the step of
        the world state the act answered (None if the seat had been sent none): the reaction report (core 0.2.23)."""
        self.ep.write("cmd", k=self.m.k, seat=seat, cmd=low,
                      **({"seen": act.get("seen")} if act is not None else {}),
                      **({"received_step": act["received"]} if act is not None and act.get("received") is not None
                         else {}))
        info = self.m.apply(seat, low) or {}
        if act is not None and act.get("deploy") is not None:       # D3: its version's first effect step
            self.deploys.effect(act["deploy"], self.m.k)
        if act is not None and act.get("act_id") is not None:       # diagnostics (core 0.2.25): not in the cmd row
            self.diag("effect", seat=seat, act_id=act["act_id"], k=self.m.k, entity=act.get("entity") or None,
                      **({"actor": act["deploy"]["actor"]} if act.get("deploy") else {}),
                      **({"rejected": True} if "rejected" in info else {}))
        return info

    def dropped(self, item, seat, why):
        """An accepted act that will never take effect (diagnostics, core 0.2.25)."""
        if item.get("act_id") is not None:
            self.diag("act_dropped", seat=seat, act_id=item["act_id"], k=self.m.k, why=why)

    # ------------------------------------------------------------------ the boundary (acts.ActionQueue hooks)
    def tick_seats(self):
        return [s for s in self.cfg.seats if not self.seats[s].retired]

    def sched_apply(self, seat, low, item, when):
        """Apply and record one low-level command: a layer's per-step command (when = "tick", a platform resource
        such as a flight controller's velocity loop), a platform side's command ("platform", core 0.4.1: `seat` is the
        side, Match.platform_commands), a delayed effect ("delayed") or an act ("now")."""
        info = self.apply_now(seat, low, item)
        if when not in ("now", "platform") and "rejected" in info:
            self.seats[seat].count("rejected")
        return info

    def sched_platform(self, side, low, info):
        """Core 0.4.1: a platform side's command took effect (counted). Core 0.5.0 (Chi 10-29): its planner's time is
        its program latency, as a seat program's is, never a plan miss: final.json reaction.platform reports it
        (effect step - decision step, core/parity.py)."""
        st = self.platform_stats.setdefault(str(side), {"commands": 0})
        st["commands"] += 1

    def release_flight(self, item):
        """With the lock held (core 0.4.5): the act no longer counts against in_flight_per_robot from the boundary
        where it took effect (or was dropped), not from the moment its request thread wakes after it; so a program
        that sends one act per robot per control step with K = L + 1 in flight never meets 429 in_flight."""
        open_ = self.flight.get(item["seat"], {}).get(item.get("entity") or "")
        if open_ and item.get("earliest") in open_:
            open_.remove(item["earliest"])

    def sched_effect(self, item, info):
        self.release_flight(item)
        st = self.seats[item["seat"]]
        if "rejected" in info:
            st.count("rejected")
        st.count("applied")
        st.sample("act_s", item["result"]["wall_s_after_request"])
        if item["result"].get("late_steps"):                  # core 0.4.0: after its effect step (plan_miss)
            st.count("late_acts")

    def sched_drop(self, item, why):
        self.release_flight(item)
        if why in ("unit_changed", "unit_over") and item.get("result") is None:
            self.seats[item["seat"]].count("dropped")
        self.dropped(item, item["seat"], why)

    def apply_pending(self):
        """At the boundary before step k: acts.ActionQueue (the layer's tick, the delayed commands due, then the acts
        in arrival order)."""
        return self.sched.apply_due(self.m)

    def observe(self, seat, body=None):
        t_in = time.monotonic()
        try:
            if not self.draw_images:                   # a practice world without cameras: the state only
                with self.cond:
                    return 200, {"call": "observe", "now": self.state(seat, query_of(body), self.team_since(body)),
                                 "observation": {"frames": [], "note": "this practice world draws no images "
                                                                       "(cameras: false)"}}
            if self.streams and self.phase == "running":
                return self.observe_stream(seat, body)
            return self.observe_request(seat, body)
        finally:
            self.obs_wall.append(time.monotonic() - t_in)

    def observe_stream(self, seat, body=None):
        """core 0.5.4, the every-step camera (core/stream.py): at once, the frame taken L steps before the step the
        world is at (k - L), drawn in the background; if it is still being drawn the reply waits for it (a render
        miss); in a unit's first L steps there is no frame of the unit yet: no image. The state (`now`) is the
        world's at delivery. A frozen world (preparation, a review) answers as on request (observe_request)."""
        st = self.seats[seat]
        query = query_of(body)
        since = self.team_since(body)
        if not st.view_lock.acquire(False):
            with self.cond:
                st.count("observe_busy")
            return 429, {"error": "one observation per seat may be in flight"}
        try:
            with self.cond:
                if self.phase == "over":
                    return 409, {"error": "the match is over", "now": self.state(seat, since=since)}
                st.count("observations")
                obs_id = st.stats["observations"]
                k_obs, unit = self.m.k, self.m.unit()
            L = int(self.obs_latency)
            fs = self.streams[seat]
            k_f, out, waited = fs.get(k_obs - L, unit, timeout=max(1.0, 8 * L * self.period))
            with self.cond:
                k_out, wall_out = self.m.k, time.time()
                now = self.query_guard(seat, query, lambda: self.state(seat, query, since))
                late = None if k_f is None else (k_f < k_obs - L or k_out > k_obs)
                if k_f is not None:
                    st.count("frames_delivered")
                    st.sample("obs_age_steps", k_out - k_f)
                    if late:
                        st.count("frames_late")
                else:
                    st.count("frames_unavailable")
                self.ep.write("observe", seat=seat, obs_id=obs_id, query=query, k=k_obs,
                              view_steps=[] if k_f is None else [k_f], delivered_step=k_out,
                              **({"late": True} if late else {}))
                self.acts.observed(seat, obs_id)
            meta = fs.meta_of(k_f) if k_f is not None else {}      # a sport's own frame metadata (core 0.5.5:
            meta.pop("wall_mono", None)                             # e.g. its cameras' poses at that frame)
            obs = {**meta, "obs_id": obs_id, "step": k_out, "latency_steps": L, "delivered_step": k_out,
                   "delivered_wall_s": round(wall_out, 3), "camera_model": "stream"}
            if k_f is None:
                obs.update(frames=[], note=f"no frame yet: the first frame of this unit is delivered {L} control "
                                           "steps after the unit starts")
                return 200, {"call": "observe", "now": now, "observation": obs}
            obs.update(frames=frame_stamps(self.camera_ids, [k_f], L, bool(late)), render_wall_s=out.get("worker_s", 0.0),
                       wait_wall_s=round(waited, 4))
            if out.get("png"):
                obs["image_png_b64"] = base64.b64encode(out["png"]).decode()
            if out.get("tiles"):
                obs["tiles"] = out["tiles"]
            if out.get("renderer"):
                obs["renderer"] = out["renderer"]
            return 200, {"call": "observe", "now": now, "observation": obs}
        finally:
            st.view_lock.release()

    def observe_request(self, seat, body=None):
        st = self.seats[seat]
        query = query_of(body)
        since = self.team_since(body)
        if not st.view_lock.acquire(False):
            with self.cond:
                st.count("observe_busy")            # FWTEST 10-19: counted
            return 429, {"error": "one observation per seat may be in flight"}
        try:
            with self.cond:
                if self.phase == "over":           # core 0.2.26: no images after the end, the final state only
                    return 409, {"error": "the match is over", "now": self.state(seat, since=since)}
                now, (job, meta) = self.query_guard(seat, query, lambda: (self.state(seat, query, since),
                                                                          self.camera_job(seat, query)))
                st.count("observations")
                obs_id = st.stats["observations"]
                k_obs, unit = self.m.k, self.m.unit()
            meta = dict(meta)
            steps = view_steps(meta, job, k_obs)
            out = self.draw(seat, job) or {}
            with self.cond:
                # core 0.4.0 (eo-seat/1 ObserveReply; fwspec sensors.cameras[].latency_steps): the newest frame, taken
                # at step c, is delivered at its available step c + L and never earlier, the same for every seat
                # whatever the drawing cost; a drawing that ends after it is late (render_miss) and delivered at once.
                # The state (`now`) is the world's at delivery (state latency 0)
                newest = max(steps) if steps else k_obs
                L = self.obs_latency
                drawn = bool(out.get("png") or out.get("tiles")) and bool(steps)
                avail = None if L is None or not drawn else newest + L      # no image: nothing to hold
                late = None if avail is None else self.m.k > avail
                if avail is not None and not late:
                    end = time.monotonic() + max(1.0, 4 * (avail - self.m.k + 1) * self.period)
                    while (self.phase == "running" and self.m.k < avail and self.m.unit() == unit
                           and time.monotonic() < end):
                        self.cond.wait(min(self.period, 0.05))
                k_out, wall_out = self.m.k, time.time()
                if self.phase != "over":                # (a query the sport cannot read now: the player's 400)
                    now = self.query_guard(seat, query, lambda: self.state(seat, query, since))
                age = max(0.0, time.monotonic() - meta.pop("wall_mono", time.monotonic()))
                st.sample("obs_age_s", age)
                if drawn:
                    st.sample("obs_age_steps", k_out - newest)
                if late is not None:
                    st.count("frames_delivered")
                    if late:
                        st.count("frames_late")
                self.ep.write("observe", seat=seat, obs_id=obs_id, age_s=age, query=query, k=k_obs, view_steps=steps,
                              delivered_step=k_out, **({"late": True} if late else {}))
                self.acts.observed(seat, obs_id)        # what the seat's next act answers (act_received)
            frames = frame_stamps(self.camera_ids, steps, L, late) if drawn else []      # eo-seat/1 frames
            obs = {"obs_id": obs_id, **meta, "obs_age_wall_s": age, "render_wall_s": out.get("worker_s", 0.0),
                   "step": k_out, "frames": frames, "latency_steps": L, "delivered_step": k_out,
                   "delivered_wall_s": round(wall_out, 3)}
            if out.get("png"):
                obs["image_png_b64"] = base64.b64encode(out["png"]).decode()
            if out.get("tiles"):
                obs["tiles"] = out["tiles"]
            return 200, {"call": "observe", "now": now, "observation": obs}
        finally:
            st.view_lock.release()

    def wait(self, seat, body):
        try:
            d = float(body.get("dt", 0))
        except (TypeError, ValueError, OverflowError):
            d = math.nan
        if not np.isfinite(d) or not 0 < d <= 1:
            return 400, {"error": "dt must be 0..1 game seconds"}
        since = self.team_since(body)
        with self.cond:
            if self.phase in ("prepare", "review"):          # D2: frozen: until the world runs again
                end = time.monotonic() + WAIT_FROZEN_MAX_S
                while (self.phase in ("prepare", "review") and not self.owes_ready(seat)
                       and time.monotonic() < end):
                    self.cond.wait(min(.5, max(.01, end - time.monotonic())))
                return 200, {"now": self.state(seat, since=since), "deadlines": self.deadlines_now()}
            target, unit = self.m.k + int(np.ceil(d / self.m.dt)), self.m.unit()
            while self.phase == "running" and self.m.unit() == unit and self.m.k < target:
                self.cond.wait(.5)
            return 200, {"now": self.state(seat, since=since)}

    def deadlines_now(self) -> dict:
        """With the lock held: Service.deadlines_now + `review_left_s` in a review (from the freeze; core 0.2.38)."""
        out = super().deadlines_now()
        out["review_left_s"] = (max(0.0, round(self.ready_deadline - time.monotonic(), 1))
                                if self.phase == "review" and self.ready_deadline is not None else None)
        return out

    def owes_ready(self, seat) -> bool:
        """With the lock held: the world waits for this seat (prepare: its start, from t0 on; review: its ready)."""
        st = self.seats[seat]
        return self.t0_open() and not st.retired and not st.ready and seat in self.due()

    def on_t0(self):
        """The start barrier opened (core/phases.py): the preparation deadline and the wall-clock cap count from t0."""
        if self.phase == "prepare":
            self.ready_deadline = self.t0_mono + self.prep_window()
        self.cap_deadline = self.wall_cap_deadline()

    # ------------------------------------------------------------------ the world loop
    def on_end(self):
        if self.segment_start is not None:
            self.run_wall += time.monotonic() - self.segment_start
            self.segment_start = None
        self.drop_all("match_over")
        for fs in self.streams.values():        # core 0.5.4: no more frames (the render workers close at finalize)
            fs.close()

    def drop_all(self, why):
        """The acts waiting for their effect step will never take effect: act_dropped rows, queues cleared."""
        return self.sched.drop_all(why)

    def timeout(self):
        """The ready window ran out. In prepare (the start window): a side that never started loses ("no_show", see
        Service.close_start_window). In a review (core 0.4.0, fw_pattern §7 decision 3 b): the world runs again after
        the lead time, nobody loses; each missing review is recorded (a review_missing row, final.json
        review_missing; the Judge's diagnostics)."""
        if self.phase == "prepare":
            self.ready_deadline = None
            if self.close_start_window():
                self.barrier()                  # the present seats have all started: run after the lead time
            return
        unit = self.m.unit()
        for s in [x for x in self.due() if not self.seats[x].ready]:
            self.seats[s].count("reviews_missing")
            self.review_missing.append({"seat": s, "after_unit": unit, "k": int(self.m.k)})
            self.diag("review_missing", seat=s, unit=unit, k=self.m.k)
        self.ready_deadline = None
        self.resume_at = time.monotonic() + float(self.ts.timing["barrier_lead_s"])

    def loop(self):
        threading.Thread(target=self.reporter, daemon=True).start()     # core 0.4.0: final.json off the world thread
        try:
            while True:
                with self.cond:
                    if self.phase == "over":
                        return
                    now = time.monotonic()
                    if self.match_deadline is not None and now > self.match_deadline:
                        self.match_deadline = None
                        self.time_up("match_s")                     # the legacy cap from the match start ran out
                        continue
                    if self.cap_deadline is not None and now > self.cap_deadline:
                        self.cap_deadline = None
                        self.time_up("wall_cap_s")                  # core 0.4.0: the safety cut-off from t0
                        continue
                    if self.phase in ("prepare", "review"):
                        if self.phase == "prepare" and not self.t0_open():
                            self.check_t0_wait()                    # core 0.3.0: the start barrier's own deadline
                        if self.resume_at is not None and now >= self.resume_at and self.streams_up():
                            if self.m.phase().state == UNIT_OVER:
                                self.ep.write("resume", k=self.m.k)
                                self.m.resume()
                            now, epoch = time.monotonic(), time.time()      # the run starts when resume() returns
                            for st in self.seats.values():
                                st.meter.begin_segment(epoch)
                                st.ready = False
                            # the development-world gate says "running" BEFORE the world runs (FWTEST 10-19: it was
                            # written after the phase switch, so practice calls in that window still went through)
                            starting = self.match_t0 is None
                            if starting:
                                self.mark_match_start()     # snapshot point (a); devworld gate (core 0.2.38)
                            else:
                                self.devgate("running")     # a resume
                            self.phase, self.anchor, self.segment_start = "running", (now, self.m.k), now
                            if starting:                                # D2: the match starts
                                self.match_t0 = now
                                if self.match_window() is not None:
                                    self.match_deadline = now + self.match_window()
                            self.resume_at = self.ready_deadline = None
                            self.ep.write("run", k=self.m.k, started_epoch=epoch)
                            self.take_frames()              # core 0.5.4: the unit's first frame (the placement)
                            self.platform_observe()         # core 0.5.6: the platform seats' first observation
                            self.bc.event("run")
                            self.cond.notify_all()
                        elif self.ready_deadline and now > self.ready_deadline:
                            self.timeout()
                            continue
                        else:
                            self.cond.wait(.01)
                            continue
                    a, k = self.anchor
                    due = a + (self.m.k - k + 1) * self.period
                t_in = time.monotonic()
                delay = due - t_in
                if delay > 0:
                    time.sleep(min(delay, .02))
                    continue
                with self.cond:
                    t_lock = time.monotonic()
                    if self.phase != "running":
                        continue
                    self.apply_pending()
                    t_apply = time.monotonic()
                    events = self.m.step()
                    t_step = time.monotonic()
                    self.take_frames()                  # core 0.5.4: every seat's frame of this step (a snapshot)
                    self.platform_observe()             # core 0.5.6: the platform seats' observation of this step
                    if events:                          # diagnostics (core 0.2.25): what the step returned
                        self.diag("event", k=self.m.k, events=jsonable(events))
                        for ev in referee_events(events):   # core 0.4.0 (eo-world/1): side_retired acts; unit_over and
                            if ev["kind"] == "side_retired":   # match_over follow Match.phase(), the compat path
                                self.referee_retired(str(ev.get("side")), str(ev.get("why") or "referee"))
                    self.bc.frame(force=self.m.phase().state != "playing")
                    self.run_steps += 1
                    t_end = time.monotonic()
                    late = max(0.0, t_end - due)
                    self.lates.append(late)
                    if late > self.late_max:
                        self.late_max = late
                    slow = self.costs.add(lag=t_in - due, lock=t_lock - t_in, apply=t_apply - t_lock,
                                          step=t_step - t_apply, host=t_end - t_step)
                    if slow or t_in - due > STALL_PROBE_S:   # diagnostics (core 0.4.0): where the world thread's
                        worst = max(t_in - due, t_lock - t_in, t_apply - t_lock, t_step - t_apply, t_end - t_step)
                        self.diag("slow_step", k=self.m.k - 1, what=slow or ["lag"], lag_s=round(t_in - due, 4),
                                  lock_s=round(t_lock - t_in, 4), apply_s=round(t_apply - t_lock, 4),
                                  step_s=round(t_step - t_apply, 4), host_s=round(t_end - t_step, 4),
                                  **({"pressure": host_pressure()} if worst > STALL_PROBE_S else {}))
                    ph = self.m.phase()
                    if ph.state != "playing":
                        self.drop_all("unit_over")             # pending acts count as dropped (sched_drop)
                        self.ep.write("unit_over", k=self.m.k, unit=self.m.unit(), reason=ph.reason)
                        self.bc.event("unit_over", unit=self.m.unit(), reason=ph.reason, scores=self.m.scores())
                        if ph.state == FINISHED:
                            self.end("match_over")
                        else:
                            self.phase = "review"
                            for s in self.due():                   # core 0.4.0: the review diagnostics' base
                                self.seats[s].count("reviews_due")
                            self.devgate("review")                 # devworld_access = preparation_review: it reopens
                            self.run_wall += time.monotonic() - self.segment_start
                            self.segment_start = None
                            self.ready_deadline = time.monotonic() + self.review_window(ph.reason)
                            if not self.due():                  # nobody reviews: go on after the lead time
                                self.barrier()
                    self.cond.notify_all()
                    if self.phase != "running":
                        self.report_now.set()           # core 0.4.0: final.json from the reporter thread
        except Exception as exc:  # noqa: BLE001
            self.failure("world", exc)

    def reporter(self):
        """The mid-match final.json (core 0.4.0): written by this thread every REPORT_EVERY_S and at once when the
        world loop asks (a review, the end), never by the world thread (it hashed and serialized the whole record
        under the lock every 50 steps); the finalizer writes the graded one."""
        last_freeze = time.monotonic()
        while not self.finalized:
            self.report_now.wait(REPORT_EVERY_S)
            self.report_now.clear()
            if self.finalized:
                return
            if time.monotonic() - last_freeze >= GC_FREEZE_EVERY_S:
                # the match's long-lived records (the episode's command rows, the step costs) grow all match long:
                # Python's full collections walked them all and stopped every thread, the world's too (an 11 v 11
                # match: world_lag_max up 0.13 -> 0.47 s from step 13k to 40k). Freezing moves what exists now out of
                # the collector's reach (cyclic garbage made before it is no longer collected: bounded per match)
                gc.freeze()
                last_freeze = time.monotonic()
            try:
                self.write_final()
            except Exception as exc:  # noqa: BLE001  (a sport's final_fields: a technical failure, as before)
                self.failure("world", exc)
                return

    def header_extra(self) -> dict:
        """The episode header's timing (core 0.2.23): what the reaction report of a replay needs (L, the planning
        budget, and the layer's effect delay; core 0.5.0: no reaction delay)."""
        return {"timing": {"effect_delay_steps": int(getattr(self.layer, "delay_steps", 0) or 0),
                           "layer_delay_steps": self.layer_delay()}}

    def layer_delay(self) -> int:
        """L, the action layer's planning budget: the task's (TaskSpec action.layer_delay_steps), else the sport's for
        this action layer (core 0.4.1: sport.toml [timing] layer_delay_steps, core/spec.layer_delay), else 0."""
        return self.ts.layer_delay(spec_mod.layer_delay(self.decl, self.cfg.action_level))

    def reaction_final(self, platform: dict | None = None) -> Later:
        """final.json `reaction` (core 0.2.23, report only: no effect on validity or grading): per seat, how many acts
        took effect on time (at r + L) and the distribution of the program latency (effect step - the step of the
        state the seat had seen), from the episode's command rows (core/episode.reaction_report); `replayed`: the
        fresh-process replay's report is the same. Core 0.4.0: computed after the lock is released
        (Service.write_final), on a copy of the rows. Only in the graded final.json: mid-match (the reporter's rewrite
        every second) it is None, since copying and walking every command row each second grew with the match and
        held the GIL off the world thread (56 000 rows: 42 ms)."""
        if not (self.finalized or self.grading):
            return None
        with self.ep.lock:
            rows = list(self.ep.commands)
        seats, delay, plan, replay = self.cfg.seats, self.delay, self.plan, self.replay

        def report():
            out = reaction_report(rows, seats, delay, plan)
            if platform:                         # core 0.5.0: the platform sides' program latency, as the seats'
                out["platform"] = platform
            rr = (replay or {}).get("reaction")
            out["replayed"] = None if not replay else bool(rr and rr.get("by_seat") == out["by_seat"])
            return out
        return Later(report)

    def extra_final(self):
        """With the lock held: realtime's final.json fields; the percentiles are computed after (Later), on copies.
        Mid-match (the reporter's rewrite every second, not graded) the percentiles are recomputed at most every
        HEAVY_EVERY_S and reused in between, with the counts and maxima current (light_final): their cost grows with
        the match and held the GIL off the world thread. The graded final.json computes everything."""
        now = time.monotonic()
        if not (self.finalized or self.grading) and self.heavy["t"] is not None and \
                now - self.heavy["t"] < HEAVY_EVERY_S and self.heavy["integrity"] is not None:
            return self.light_final()
        if not (self.finalized or self.grading):
            self.heavy["t"] = now
        return self.full_final()

    def plan_workers_raw(self) -> dict | None:
        """core 0.5.6, with the lock held: copies of what plan_workers_report needs (computed after, off the lock)."""
        pools = getattr(self, "plan_pools", None) or {}
        if not pools:
            return None
        seen = getattr(self, "plan_cpus_seen", {})
        return {s: {"workers": len(pool), "cpus": list(seen.get(s, [])), "budget_steps": self.plan,
                    "late_acts": self.seats[s].stats.get("late_acts", 0),
                    "plan_s": list(self.seats[s].stats.get("plan_s") or [])} for s, pool in pools.items()}

    def counts_final(self) -> dict:
        """With the lock held: the integrity fields that are counts (cheap, current at every write)."""
        acts = sum(st.stats.get("applied", 0) for st in self.seats.values())
        late_acts = sum(st.stats.get("late_acts", 0) for st in self.seats.values())
        platform = {k: dict(v) for k, v in self.platform_stats.items()}
        p_acts = sum(v["commands"] for v in platform.values())
        frames = sum(st.stats.get("frames_delivered", 0) for st in self.seats.values())
        frames_late = sum(st.stats.get("frames_late", 0) for st in self.seats.values())
        return {"plan_miss_fraction": round(late_acts / acts, 6) if acts else 0.0,
                "render_miss_fraction": (round(frames_late / frames, 6) if frames else 0.0)
                if self.obs_latency is not None else None,
                "acts": acts, "late_acts": late_acts, "observations": frames, "late_observations": frames_late,
                "platform_commands": p_acts, "platform": platform}

    def light_final(self) -> dict:
        """With the lock held, mid-match: the last full percentiles (at most HEAVY_EVERY_S old, marked `as_of_step`)
        with the counts, the maxima and the run's lag fields of now."""
        integ = dict(self.heavy["integrity"], **self.counts_final(),
                     world_lag_max_s=round(float(self.costs.mx["lag"]), 4), late_step_max_s=float(self.late_max),
                     slow_steps=dict(self.costs.slow))
        sim = dict(self.heavy["sim_lag"], late_max_s=float(self.late_max), run_steps=self.run_steps,
                   run_sim_s=self.run_steps * self.m.dt, run_wall_s=self.run_wall)
        return {"reaction": None, "slowdown": self.slowdown, "timing_policy": "report_only",
                "timing_invalid": False, "sim_lag": sim, "integrity": integ}

    def full_final(self):
        """With the lock held: every realtime field (percentiles over the whole match, computed after, as Later)."""
        lates = np.asarray(self.lates, dtype=float)
        costs = self.costs.copy()
        acts = sum(st.stats.get("applied", 0) for st in self.seats.values())
        late_acts = sum(st.stats.get("late_acts", 0) for st in self.seats.values())
        platform = {k: dict(v) for k, v in self.platform_stats.items()}       # core 0.4.1: platform sides' commands
        p_acts = sum(v["commands"] for v in platform.values())
        frames = sum(st.stats.get("frames_delivered", 0) for st in self.seats.values())
        frames_late = sum(st.stats.get("frames_late", 0) for st in self.seats.values())
        ages = [x for st in self.seats.values() for x in st.stats.get("obs_age_steps", [])]
        parity = self.parity_final()             # core 0.4.7: the platform sides' timing against the seat's
        lag = {"run_steps": self.run_steps, "run_sim_s": self.run_steps * self.m.dt, "run_wall_s": self.run_wall,
               "period_s": self.period}
        declared = self.obs_latency
        streams, obs_wall = dict(self.streams), list(self.obs_wall)
        pseat = self.pseats.report() if self.pseats else None         # core 0.5.6 (histograms: cheap)
        planw_raw = self.plan_workers_raw()

        heavy, as_of, mid = self.heavy, self.run_steps, not (self.finalized or self.grading)

        def sim_lag():
            out = {"late_max_s": float(lates.max()) if lates.size else 0,
                   "late_p99_s": float(np.percentile(lates, 99)) if lates.size else 0, **lag}
            if mid:
                out = heavy["sim_lag"] = dict(out, as_of_step=as_of)
            return out

        def integrity():
            """core 0.4.0: the integrity report (fwspec world-report integrity; the Judge compares the TaskSpec's
            tolerance): the world's lag behind its schedule (at a step's start), the late steps (at a step's end),
            the acts that took effect after their effect step (plan_miss; core 0.4.1: with a platform side's commands,
            Match.platform_commands: platform_commands and platform by side, counted only: core 0.5.0, a platform
            side's own planning time is its program latency, final.json reaction.platform, never a plan miss),
            the observations whose newest frame came
            after its available step (render_miss; None when the task declares no camera latency), the
            observations' age when delivered (control steps) and where the world thread's time went (seconds)."""
            rep = costs.report()
            out = {"world_lag_max_s": (rep["lag"] or {}).get("max", 0.0),
                    "world_lag_p99_s": (rep["lag"] or {}).get("p99", 0.0),
                    "late_step_p99_s": float(np.percentile(lates, 99)) if lates.size else 0.0,
                    "late_step_max_s": float(lates.max()) if lates.size else 0.0,
                    "plan_miss_fraction": round(late_acts / acts, 6) if acts else 0.0,
                    "render_miss_fraction": (round(frames_late / frames, 6) if frames else 0.0)
                    if declared is not None else None,
                    "observation_latency_steps": declared, "observation_age_steps": StepCosts.stats(ages),
                    "acts": acts, "late_acts": late_acts, "observations": frames, "late_observations": frames_late,
                    "platform_commands": p_acts, "platform": platform,
                    **({"platform_parity": parity} if parity else {}),
                    "costs": rep, "slow_steps": costs.slow,
                    "observe_wall_s": StepCosts.stats(obs_wall),         # core 0.5.4: the observe handler's time
                    **({"platform_seat": pseat} if pseat else {}),       # core 0.5.6: the platform seats
                    **({"plan_workers": plan_workers_report(planw_raw)} if planw_raw else {}),   # core 0.5.6
                    **({"camera_stream": {s: fs.report() for s, fs in streams.items()}} if streams else {})}
            if mid:
                out = heavy["integrity"] = dict(out, as_of_step=as_of)
            return out
        return {"reaction": self.reaction_final(platform_latency(parity)), "slowdown": self.slowdown,
                "timing_policy": "report_only",
                "timing_invalid": False, "sim_lag": Later(sim_lag), "integrity": Later(integrity)}

    def collect(self, events: list | None = None):
        """Harness sessions ended (SIGUSR1: the Backend's per-seat events, else every session; core 0.4.0, fw_pattern
        §7 decision 3): only an event (core/phases.py session_end). The seats stay in the match: their programs play
        on, and the match ends by its rules, by the preparation deadline (no_show) or at the wall-clock cap.
        Embodied First Exam (RO_COLLECT_ENDS_MATCH=1, the task's compose): Harbor collects once the agent's session has
        ended, so the session end decides at once: before the start a no-show, a match in play is lost (abandoned),
        both valid losses (the core-0.2 rule, Service.no_show_at_collect / abandon)."""
        with self.cond:
            self.session_end(events)
            if events is None and os.environ.get("RO_COLLECT_ENDS_MATCH") == "1" and self.phase != "over":
                if not self.no_show_at_collect() and self.in_play():
                    for seat in self.cfg.seats:
                        self.lose(seat, "abandoned")
                self.cond.notify_all()


__all__ = ["RealtimeService", "Refused"]
