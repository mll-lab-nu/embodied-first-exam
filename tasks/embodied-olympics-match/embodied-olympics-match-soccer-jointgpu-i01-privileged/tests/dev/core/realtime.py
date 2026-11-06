"""Protocol eai-standard-realtime/1.0: a continuous world paced at slowdown S (one control step every dt x S wall
seconds), frozen at every unit end for the reviews of the seats the referee names (Phase.review).

Phases: prepare (until every seat sent start/ready; after the first, START_TIMEOUT_S: a side that has not started by
then loses, "no_show"; if none started, the match does not count; a single side has START_TIMEOUT_S from the service
start, else it loses) -> running -> review (each seat
in Phase.review sends ready WHY PLAN within READY_TIMEOUT_S, else its side loses, or with more than two sides retires
while the others go on) -> running ... -> over. The collect (every player session has ended) before the end: before
the start a side that has not started loses at once ("no_show", core 0.2.7; if no side started, "collected"); a single
side whose match has started loses ("abandoned", a valid loss, core 0.2.6); otherwise the match ends "collected"
(unfinished, not a valid trial).
Acts: one per (seat, entity) in flight (429); program play needs a live metered session, per-response play a fresh
completed model response (think_clock.py); the high action layer prepares off the world lock (in the seat's plan
worker) and is lowered at the next control-step boundary, where the whole batch of ready acts takes effect together,
or `delay_steps` later (the effect step is what the episode logs). Declared reaction delay (core 0.2.18): a sport
may declare D = sport.toml [timing] reaction_delay_steps; an act then takes effect (and is lowered) at step
max(the next control-step boundary, s + D), s = the step of the latest world state the service sent to the seat before
the act arrived (the `now` of any reply: observe, act, wait, status, ready), the same D for every seat, so that a
program that answers within D steps always gets exactly D, whatever the machine's load; a slower one gets its own
latency as before. Not declared: D = 0, the rule above unchanged. Observations may carry a query (observation
parameters, e.g. which camera) that the sport validates. Reply images (core 0.2.8): an act that takes effect at once
gets the images of its result (Match.reply_views), snapshotted at the effect step under the lock and drawn off the
lock after the act's timing is taken (`wall_s_after_request` excludes it; `render_wall_s` reports it), like an
observation; the world runs on meanwhile.
"""
from __future__ import annotations

import base64
import json
import math
import os
import time

import numpy as np

from . import spec as spec_mod
from .diaglog import jsonable, view_steps
from .episode import reaction_report
from .service import Service
from .sport import FINISHED, UNIT_OVER, Refused, parse_action


def query_of(body) -> dict | None:
    q = (body or {}).get("query")
    if q is None:
        return None
    if not isinstance(q, dict) or len(json.dumps(q)) > 4096:
        raise Refused("query must be a JSON object of at most 4 KiB")
    return q


class RealtimeService(Service):
    protocol = "realtime"
    protocol_id = "eai-standard-realtime/1.0"

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.slowdown = float(self.cfg.slowdown or 20)
        if not np.isfinite(self.slowdown) or self.slowdown <= 0:
            raise ValueError("invalid slowdown")
        self.period = self.m.dt * self.slowdown
        self.ready_deadline = self.resume_at = self.anchor = self.segment_start = None
        if len(self.cfg.side_list()) == 1:        # nobody to wait for: the start window opens now
            self.ready_deadline = time.monotonic() + self.start_window()
        self.pending: dict = {}                  # (seat, entity) -> act waiting for the next boundary
        self.scheduled: list = []                # [effect_k, seat, low] lowered acts with a delayed effect
        self.delay = int(getattr(self.layer, "delay_steps", 0) or 0)
        self.react = spec_mod.reaction_delay(self.decl)        # declared reaction delay D (core 0.2.18), 0 = none
        self.seen: dict = {}                                   # seat -> step of the latest world state sent to it
        self.lates, self.run_steps, self.run_wall = [], 0, 0.0
        for st in self.seats.values():
            st.stats.update(attempts=0, applied=0, refused=0, refused_invalid=0, dropped=0, observations=0, plan_s=[],
                            act_s=[], obs_age_s=[])

    def routes(self, post):
        if post:
            return {"start": self.ready, "ready": self.ready, "act": self.act, "wait": self.wait,
                    "observe": self.observe, "say": self.say, "team": self.team}
        return {"spec": self.spec, "status": self.status, "observe": self.observe, "team": self.team}

    def spec_core(self):
        return {"timing": {"slowdown": self.slowdown, "control_dt": self.m.dt, "period_s": self.period,
                           "policy": "report_only", "effect_delay_steps": self.delay,
                           "reaction_delay_steps": self.react,
                           # RCB patch: the review window, and what missing it costs (timeout() below)
                           "review_timeout_s": float(os.environ.get("READY_TIMEOUT_S", "60")),
                           "review_timeout_rule": "after every unit the world stays frozen until each due player sends "
                                                  "ready; a side that has not sent it within review_timeout_s seconds "
                                                  "of real time loses the match (ready_timeout)"},
                "start": self.start_rule(),
                "decision_rule": ("program play: your own program may observe and act without a new model response; "
                                  "one act per seat in flight" if os.environ.get("RCB_ACT_RULE") == "program" else
                                  "one fresh completed model response per act, after both players resume")}

    def start_window(self) -> float:
        return float(os.environ.get("START_TIMEOUT_S") or os.environ.get("READY_TIMEOUT_S", "60"))

    # ------------------------------------------------------------------ replies
    def state(self, seat, query=None, since=None):
        core = {"phase": self.phase, "done": self.phase == "over", "reason": self.reason,
                "ready": {s: st.ready for s, st in self.seats.items()},
                "world": "running" if self.phase == "running" else "frozen", "step": self.m.k,
                "t_sim": self.m.k * self.m.dt}
        self.seen[seat] = self.m.k              # every reply's `now` is a world state the seat has seen
        if self.retired:
            core["retired"] = list(self.retired)
        return {**core, **self.observation(seat, query, since)}

    def status(self, seat, body=None):
        since = self.team_since(body)
        with self.cond:
            return 200, self.state(seat, since=since)

    def ready(self, seat, body):
        st = self.seats[seat]
        st.meter.settle()                                   # never under the world lock (may wait for a stream)
        with self.cond:
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
                return 400, {"error": "why and plan must be strings of at most 2000 characters"}
            if self.phase == "review" and (not why.strip() or not plan.strip()):
                return 400, {"error": "both review fields required"}
            st.joined = st.ready = True
            if self.ready_deadline is None:
                self.ready_deadline = time.monotonic() + (self.start_window() if self.phase == "prepare" else
                                                          float(os.environ.get("READY_TIMEOUT_S", "60")))
            if self.phase == "review":
                self.reviews.append({"seat": seat, "after_unit": unit, "why": why, "plan": plan})
            self.ep.write("ready", seat=seat, unit=unit, why=why, plan=plan)
            self.barrier()
            self.cond.notify_all()
            while self.phase in ("prepare", "review") and self.m.unit() == unit:   # one start event releases all
                self.cond.wait(.5)
            return 200, {"accepted": "ready", "now": self.state(seat)}

    def barrier(self):
        if all(self.seats[s].ready for s in self.due()):
            self.resume_at = time.monotonic() + float(os.environ.get("BARRIER_LEAD_S", ".2"))

    def due(self):
        seats = self.cfg.seats if self.phase == "prepare" else self.m.phase().review
        return [s for s in seats if not self.seats[s].retired]

    def act(self, seat, body):
        st = self.seats[seat]
        try:
            cmd = parse_action(self.layer, seat, body, self.m, {})
        except Refused as exc:                  # a malformed action: the player's own error, never a failure
            with self.cond:
                self.refused_invalid(seat, exc)
            raise
        entity = str(cmd.get("entity", "")) if isinstance(cmd, dict) else ""
        arrived = time.monotonic()
        lock = st.act_lock(entity)
        if not lock.acquire(False):
            return 429, {"error": "one act request per seat" + (" and entity" if entity else "") + " may be in flight"}
        try:
            with self.cond:
                st.count("attempts")
                if self.phase != "running":
                    return 409, {"error": "the match is over" if self.phase == "over" else "world is not running",
                                 "now": self.state(seat)}
                if st.retired:
                    return 409, {"error": "your side has retired"}
                unit = self.m.unit()
                seen = self.seen.get(seat)              # the world state this act answers (reaction delay)
            if not st.meter.decided_by_model():
                with self.cond:
                    st.count("refused")
                    self.ep.write("refused_not_model", seat=seat, unit=unit)
                return 429, {"error": "act needs a fresh completed response started after resume, one act per response"}
            receipt = st.meter.last_call()
            with self.cond:
                if self.phase != "running" or self.m.unit() != unit:
                    return 409, {"error": "unit ended during response confirmation"}
                job = self.layer.snapshot(seat, cmd, self.m, st.stats["attempts"])
                act_id = self.acts.new(seat)            # diagnostics (core 0.2.25): act -> observation -> effect
                self.ep.write("act_received", seat=seat, unit=unit, decision=cmd, model_call=receipt, k=self.m.k,
                              act_id=act_id, obs_id_last=self.acts.last_obs.get(seat), seen=seen,
                              entity=entity or None)
            prepared = None
            if job is not None:
                prepared = (self.workers["plan", seat].call(job) if self.layer.worker else self.layer.prepare(job))
            with self.cond:
                if isinstance(prepared, dict) and "worker_s" in prepared:
                    st.sample("plan_s", prepared["worker_s"])
                if self.phase != "running" or self.m.unit() != unit:
                    st.count("dropped")
                    self.dropped({"act_id": act_id}, seat, "unit_over_planning" if self.phase != "over" else "match_over")
                    return 409, {"error": "unit ended during planning", "now": self.state(seat)}
                item = {"unit": unit, "cmd": cmd, "prepared": prepared, "arrived": arrived, "result": None,
                        "act_id": act_id, "entity": entity}
                if seen is not None:
                    item["seen"] = seen                 # the reaction report (core 0.2.23), any D
                    if self.react:
                        item["earliest"] = seen + self.react
                self.pending[seat, entity] = item
                while item["result"] is None and self.phase == "running" and self.m.unit() == unit:
                    self.cond.wait(.5)
                if item["result"] is None:
                    return 409, {"error": "unit ended before effect", "now": self.state(seat)}
                out = {"call": "act", "took_effect": item["result"], "now": self.state(seat)}
            if item.get("images") is not None:                  # drawn off the lock: the world runs on
                try:
                    out["observation"] = self.reply_images(seat, item["images"])
                except Exception as exc:  # noqa: BLE001
                    self.failure("act_images", exc)
                    return 500, {**out, "error": "technical failure"}
            return 200, out
        finally:
            lock.release()

    def apply_now(self, seat, low, act=None):
        """Log and apply one low-level command. An act's row (act = its pending item) also carries `seen`, the step of
        the world state the act answered (None if the seat had been sent none): the reaction report (core 0.2.23)."""
        self.ep.write("cmd", k=self.m.k, seat=seat, cmd=low, **({"seen": act.get("seen")} if act is not None else {}))
        info = self.m.apply(seat, low) or {}
        if act is not None and act.get("act_id") is not None:       # diagnostics (core 0.2.25): not in the cmd row
            self.diag("effect", seat=seat, act_id=act["act_id"], k=self.m.k, entity=act.get("entity") or None,
                      **({"rejected": True} if "rejected" in info else {}))
        return info

    def dropped(self, item, seat, why):
        """An accepted act that will never take effect (diagnostics, core 0.2.25)."""
        if item.get("act_id") is not None:
            self.diag("act_dropped", seat=seat, act_id=item["act_id"], k=self.m.k, why=why)

    def apply_pending(self):
        tick = getattr(self.layer, "tick", None)       # a layer's per-step command (the skill in the loop's step(),
        if tick is not None:                            # skilleval/inloop.py): applied and logged like any other
            for seat in self.cfg.seats:
                if self.seats[seat].retired:
                    continue
                low = tick(seat, self.m)
                if low is not None and "rejected" in self.apply_now(seat, low):
                    self.seats[seat].count("rejected")
        due = [x for x in self.scheduled if x[0] <= self.m.k]
        self.scheduled = [x for x in self.scheduled if x[0] > self.m.k]
        for _, seat, low, act in due:
            info = self.apply_now(seat, low, act)
            if "rejected" in info:
                self.seats[seat].count("rejected")
        batch, self.pending = self.pending, {}
        for (seat, _entity), item in batch.items():
            st = self.seats[seat]
            if item["unit"] != self.m.unit():
                st.count("dropped")
                self.dropped(item, seat, "unit_changed")
                continue
            if item.get("earliest", 0) > self.m.k:     # held until its reaction delay has passed (core 0.2.18)
                self.pending[seat, _entity] = item
                continue
            low, info = self.layer.lower(seat, item["cmd"], item["prepared"], self.m)
            if self.delay:
                self.scheduled.append([self.m.k + self.delay, seat, low, {"seen": item.get("seen"),
                                                                           "act_id": item["act_id"],
                                                                           "entity": item["entity"]}])
                info = {"effect_step": self.m.k + self.delay, **info}
            else:
                applied = self.apply_now(seat, low, item)
                item["images"] = self.reply_job(seat, low, applied)
                info = {**applied, **info}
            if "rejected" in info:
                st.count("rejected")
            elapsed = time.monotonic() - item["arrived"]
            item["result"] = {"step": self.m.k, "t_sim": self.m.k * self.m.dt, "wall_s_after_request": elapsed,
                              **({"seen_step": item["seen"], "reaction_delay_steps": self.react}
                                 if self.react and "seen" in item else {}),
                              **self.layer.reply(seat, item["cmd"], info, self.m)}
            st.count("applied")
            st.sample("act_s", elapsed)

    def observe(self, seat, body=None):
        st = self.seats[seat]
        query = query_of(body)
        since = self.team_since(body)
        if not st.view_lock.acquire(False):
            return 429, {"error": "one observation per seat may be in flight"}
        try:
            with self.cond:
                if self.phase == "over":           # core 0.2.26: no images after the end, the final state only
                    return 409, {"error": "the match is over", "now": self.state(seat, since=since)}
                now, (job, meta) = self.query_guard(seat, query, lambda: (self.state(seat, query, since),
                                                                          self.camera_job(seat, query)))
                st.count("observations")
                obs_id = st.stats["observations"]
                k_obs = self.m.k
            meta = dict(meta)
            steps = view_steps(meta, job, k_obs)
            out = self.draw(seat, job) or {}
            age = max(0.0, time.monotonic() - meta.pop("wall_mono", time.monotonic()))
            with self.cond:
                st.sample("obs_age_s", age)
                self.ep.write("observe", seat=seat, obs_id=obs_id, age_s=age, query=query, k=k_obs, view_steps=steps)
                self.acts.observed(seat, obs_id)        # what the seat's next act answers (act_received)
            obs = {"obs_id": obs_id, **meta, "obs_age_wall_s": age, "render_wall_s": out.get("worker_s", 0.0)}
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
            target, unit = self.m.k + int(np.ceil(d / self.m.dt)), self.m.unit()
            while self.phase == "running" and self.m.unit() == unit and self.m.k < target:
                self.cond.wait(.5)
            return 200, {"now": self.state(seat, since=since)}

    # ------------------------------------------------------------------ the world loop
    def on_end(self):
        if self.segment_start is not None:
            self.run_wall += time.monotonic() - self.segment_start
            self.segment_start = None
        self.drop_all("match_over")

    def drop_all(self, why):
        """The acts waiting for their effect step will never take effect: act_dropped rows, queues cleared."""
        for (s, _e), item in self.pending.items():
            self.dropped(item, s, why)
        for _k, s, _low, act in self.scheduled:
            self.dropped(act, s, why)
        self.pending.clear()
        self.scheduled.clear()

    def timeout(self):
        """The ready window ran out. In prepare (the start window): a side that never started loses ("no_show", see
        Service.close_start_window); in a review: a late side loses (or retires)."""
        if self.phase == "prepare":
            self.ready_deadline = None
            if self.close_start_window():
                self.barrier()                  # the present seats have all started: run after the lead time
            return
        missing = [s for s in self.due() if not self.seats[s].ready]
        sides = []
        for s in missing:
            if self.cfg.side_of(s) not in sides:
                sides.append(self.cfg.side_of(s))
        if len(sides) == 1 or (len(self.active_sides()) > 2 and len(sides) < len(self.active_sides())):
            for side in sides:
                seat = next(s for s in missing if self.cfg.side_of(s) == side)
                if not self.lose(seat, "ready_timeout"):
                    return
            self.ready_deadline = time.monotonic() + float(os.environ.get("READY_TIMEOUT_S", "60"))
            self.barrier()
            return
        self.end("incomplete")

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
                            now, epoch = time.monotonic(), time.time()      # the run starts when resume() returns
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
                    a, k = self.anchor
                    due = a + (self.m.k - k + 1) * self.period
                delay = due - time.monotonic()
                if delay > 0:
                    time.sleep(min(delay, .02))
                    continue
                with self.cond:
                    if self.phase != "running":
                        continue
                    try:                                # Embodied First Exam: the control step itself
                        self.apply_pending()
                        events = self.m.step()
                    except Exception as exc:  # noqa: BLE001
                        exc.rcb_where = "world_step"    # its own `where` in final.json errors (tests/grade.py)
                        raise
                    if events:                          # diagnostics (core 0.2.25): what the step returned
                        self.diag("event", k=self.m.k, events=jsonable(events))
                    self.bc.frame(force=self.m.phase().state != "playing")
                    self.run_steps += 1
                    self.lates.append(max(0.0, time.monotonic() - due))
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
                            if not self.due():                  # nobody reviews: go on after the lead time
                                self.barrier()
                    self.cond.notify_all()
                    if self.m.k % 50 == 0 or self.phase != "running":
                        self.write_final()
        except Exception as exc:  # noqa: BLE001
            self.failure(getattr(exc, "rcb_where", "world"), exc)   # world_step: the control step; else bookkeeping

    def header_extra(self) -> dict:
        """The episode header's timing (core 0.2.23): what the reaction report of a replay needs."""
        return {"timing": {"reaction_delay_steps": spec_mod.reaction_delay(self.decl),
                           "effect_delay_steps": int(getattr(self.layer, "delay_steps", 0) or 0)}}

    def reaction_final(self) -> dict:
        """final.json `reaction` (core 0.2.23, report only: no effect on validity or grading): per seat, how many acts
        took effect within the declared reaction delay D, and the distribution of the actual delay, from the episode's
        command rows (core/episode.reaction_report); `replayed`: the fresh-process replay's report is the same."""
        with self.ep.lock:
            rows = list(self.ep.commands)
        out = reaction_report(rows, self.cfg.seats, self.react, self.delay)
        rr = (self.replay or {}).get("reaction")
        out["replayed"] = None if not self.replay else bool(rr and rr.get("by_seat") == out["by_seat"])
        return out

    def extra_final(self):
        L = self.lates
        return {"reaction": self.reaction_final(), "slowdown": self.slowdown, "timing_policy": "report_only", "timing_invalid": False,
                "sim_lag": {"late_max_s": max(L, default=0), "late_p99_s": float(np.percentile(L, 99)) if L else 0,
                            "run_steps": self.run_steps, "run_sim_s": self.run_steps * self.m.dt,
                            "run_wall_s": self.run_wall, "period_s": self.period}}

    def collect(self):
        """Every player session has ended. Before the start every side that has not started loses ("no_show", a valid
        loss; Service.no_show_at_collect, core 0.2.7); a single side whose match has started loses ("abandoned", a
        valid loss; Service.abandon_single, core 0.2.6). Otherwise (two or more sides after the start, or no side
        started) the match ends "collected": unfinished, no winner, not a valid trial."""
        with self.cond:
            if self.no_show_at_collect():
                self.ready_deadline = None
            elif not self.abandon_single():
                self.end("collected")


__all__ = ["RealtimeService", "Refused"]
