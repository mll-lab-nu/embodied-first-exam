"""Protocol eai-standard-turn/1.0: turns decided by the plugin (Match.to_move), one chess clock per seat (CLOCK_S of
wall time, running only on its own turn, service time excluded; out of time = the match is lost), and after every
action that does not end the match its actor reviews (ready WHY PLAN) before play goes on.

Phases: prepare (until every seat sent start; after the first, START_TIMEOUT_S: a side that has not started by then
loses, "no_show"; if none started, incomplete; a single side has START_TIMEOUT_S from the service start, else it
loses; the collect before the start decides the same at once, core 0.2.7) -> play -> over.
An action or review out of turn: 409; one action in flight per seat: 429; a seat that stops playing on its turn
(collect hook) loses ("abandoned"); a single side whose match has started loses at the collect whoever is on turn
(core 0.2.6). With more than two sides a side that loses on the clock may retire while the
others play on (Match.retire); observations may carry a query (observation parameters) that the sport validates.
Images (core 0.2.8): the observation's cameras and an action's reply images (Match.reply_views) are snapshotted under
the lock and drawn after it is released, so drawing never blocks the other seats; the seat's clock stands still
while its images are drawn. The core tells the sport whose review is due (Match.awaiting_review).
"""
from __future__ import annotations

import base64
import os
import threading
import time
import traceback

from .diaglog import jsonable, view_steps
from .service import Service
from .realtime import query_of
from .sport import FINISHED, Refused, parse_action

WAIT_MAX_S = 60.0
REVIEW_MAX_CHARS = 2000


class TurnService(Service):
    protocol = "turn"
    protocol_id = "eai-standard-turn/1.0"

    def __init__(self, *a, **kw):
        self.clock_s = float(os.environ.get("CLOCK_S", "3600"))
        super().__init__(*a, clock_s=self.clock_s, **kw)
        self.start_deadline = self.on_turn = self.review_due = None
        if len(self.cfg.side_list()) == 1:        # nobody to wait for: the start window opens now
            self.start_deadline = time.time() + self.start_window()
        for st in self.seats.values():
            st.stats.update(n_act=0, n_observe=0, n_wait=0, refused_busy=0, refused_turn=0, refused_not_model=0,
                            refused_invalid=0, n_reviews=0)

    def routes(self, post):
        fns = ({"start": self.start, "observe": self.observe, "act": self.act, "ready": self.ready, "wait": self.wait}
               if post else {"spec": self.spec, "status": self.status})
        out = {ep: self.guarded(ep, fn) for ep, fn in fns.items()}
        if post:
            out["say"] = self.say
        out["team"] = self.team                    # read-only, never consumes (core 0.2.20)
        return out

    @property
    def review_due(self):
        return self._review_due

    @review_due.setter
    def review_due(self, seat):
        """The seat whose review is due; the sport sees it as Match.awaiting_review (core 0.2.8)."""
        self._review_due = seat
        self.m.awaiting_review = seat

    def guarded(self, ep, fn):
        """Every call runs under the lock, its service time is taken off the caller's clock, final.json follows. A
        handler may return (code, reply, job): the job (images) is drawn after the lock is released, with the
        caller's clock stopped, and attached to the reply as `observation`."""
        def run(seat, body):
            if ep == "spec":
                return fn(seat, body)
            st = self.seats[seat]
            if ep == "act" and not st.act_lock().acquire(blocking=False):
                with self.cond:
                    st.count("refused_busy")
                return 429, {"refused": True, "busy": True, "error": "busy: one action at a time"}
            try:
                with self.cond:
                    t = time.time()
                    try:
                        res = fn(seat, body)
                    except Exception as exc:  # noqa: BLE001
                        if exc.__class__.__name__ == "Refused":
                            raise
                        traceback.print_exc()
                        self.failure(ep, exc)
                        return 500, {"error": "technical failure"}      # details: the logs, never the player
                    finally:
                        if ep not in ("wait", "status"):
                            self.busy(seat, t)
                            self.write_final()
                    if len(res) == 2 or res[2] is None:
                        return res[:2]
                    st.freeze(time.time())
                return self.finish_images(ep, seat, *res)
            finally:
                if ep == "act":
                    st.act_lock().release()
        return run

    def finish_images(self, ep, seat, code, out, job):
        """Off the lock: draw `job` and attach it (observe: the camera images; act: the result of the action)."""
        st = self.seats[seat]
        try:
            obs = self.reply_images(seat, job) if ep == "act" else self.observe_images(seat, job, out["observation"])
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            with self.cond:
                st.thaw(time.time())
            self.failure(f"{ep}_images", exc)
            with self.cond:
                self.write_final()
            return 500, {**out, "error": "technical failure"}
        with self.cond:
            st.thaw(time.time())
            self.write_final()
        out["observation"] = obs
        return code, out

    def observe_images(self, seat, job, meta) -> dict:
        out = self.draw(seat, job)
        obs = dict(meta)
        if out is not None:
            obs = {"image_png_b64": base64.b64encode(out["png"]).decode(), **meta}
            if out.get("tiles"):
                obs["tiles"] = out["tiles"]
        return obs

    def spec_core(self):
        return {"clock": {"total_s": self.clock_s, "runs": "on your turn only (your actions and your reviews); the "
                          "time the service is busy does not count; out of time = you lose the match",
                          "start_window_s": self.start_window()},
                "start": self.start_rule(),
                "decision_rule": ("program play: your own program may act without a new model response; one action "
                                  "in flight" if os.environ.get("RCB_ACT_RULE") == "program" else
                                  "a new model response before every action")}

    # ------------------------------------------------------------------ clock and turns
    def set_turn(self, seat):
        now = time.time()
        if self.on_turn is not None:
            self.seats[self.on_turn].stop_turn(now)
        self.on_turn = seat
        if seat is not None:
            self.seats[seat].start_turn(now)
            self.ep.write("turn", seat=seat, clock_left_s=round(self.seats[seat].clock_left(), 1))
        self.cond.notify_all()

    def busy(self, seat, t):
        st = self.seats[seat]
        if self.on_turn == seat and st.turn_t0 is not None:
            st.turn_busy += time.time() - max(t, st.turn_t0)

    def on_end(self):
        self.set_turn(None)

    def lose(self, seat, why):
        if super().lose(seat, why):              # retired; the others play on
            self.review_due = None if self.review_due == seat else self.review_due
            if self.phase == "play" and (self.on_turn == seat or self.on_turn is None
                                         or self.seats[self.on_turn].retired):
                self.set_turn(self.m.to_move())
            return True
        return False

    # ------------------------------------------------------------------ replies
    def state(self, seat, query=None, since=None):
        others = [s for s in self.cfg.seats if s != seat]
        if self.phase == "prepare":
            turn = "start" if not self.seats[seat].joined else "waiting for the opponent to start"
        elif self.phase == "over":
            turn = "over"
        elif self.on_turn == seat:
            turn = "review" if self.review_due == seat else "you"
        else:
            turn = "opponent"
        out = {"seat": seat, "phase": self.phase, "turn": turn, "your_turn": turn in ("you", "review"),
               "awaiting_review": self.review_due == seat, "done": self.phase == "over",
               **self.observation(seat, query, since), "clock_left_s": round(self.seats[seat].clock_left(), 1)}
        if self.retired:
            out["retired"] = list(self.retired)
        if len(others) == 1:
            out["opponent_clock_left_s"] = round(self.seats[others[0]].clock_left(), 1)
        if self.phase == "over":
            o = self.outcome()
            w, side = o.winner, self.cfg.side_of(seat)
            out.update({"reason": self.reason, "won": w == side,
                        "winner": None if w is None else ("you" if w == side else "opponent")})
            if len(self.cfg.side_list()) > 2:
                out["place"] = o.ranking.index(side) + 1 if side in o.ranking else None
        return out

    def status(self, seat, body=None):
        return 200, {"state": self.state(seat, since=self.team_since(body))}

    def gate(self, seat):
        if self.phase == "over":                   # core 0.2.26: 409 and the final state, nothing drawn
            return 409, {"error": "the match is over", "state": self.state(seat)}
        if self.phase == "prepare":
            return 409, {"error": "the match has not started (both players must send start)", "state": self.state(seat)}
        return None

    def start(self, seat, body):
        st = self.seats[seat]
        if self.phase != "prepare" or st.joined:
            return 409, {"error": "already started", "state": self.state(seat)}
        st.meter.check_ready()
        st.joined = True
        self.ep.write("start", seat=seat)
        if all(s.joined for s in self.seats.values()):
            self.begin()
        else:
            self.start_deadline = time.time() + self.start_window()
        self.cond.notify_all()
        return 200, {"started": True, "state": self.state(seat)}

    def begin(self):
        self.phase, self.start_deadline = "play", None
        self.bc.event("run")
        self.bc.frame(force=True)
        self.set_turn(self.m.to_move())

    def observe(self, seat, body):
        g = self.gate(seat)
        if g:
            return g
        query = query_of(body)
        since = self.team_since(body)
        self.seats[seat].count("n_observe")
        (job, meta), now = self.query_guard(seat, query, lambda: (self.camera_job(seat, query),
                                                                   self.state(seat, query, since)))
        obs_id = self.seats[seat].stats["n_observe"]           # diagnostics (core 0.2.25): never replayed
        self.diag("observe", seat=seat, obs_id=obs_id, k=self.m.k, view_steps=view_steps(meta, job, self.m.k),
                  query=query)
        self.acts.observed(seat, obs_id)
        return 200, {"state": now, "observation": dict(meta)}, job     # drawn off the lock

    def act(self, seat, body):
        g = self.gate(seat)
        if g:
            return g
        st = self.seats[seat]
        if self.on_turn != seat or self.review_due == seat:
            st.count("refused_turn")
            why = "review your last action first" if self.review_due == seat else "it is not your turn"
            return 409, {"error": why, "state": self.state(seat)}
        try:
            cmd = parse_action(self.layer, seat, body, self.m, {"clock_left_s": {s: x.clock_left() for s, x in
                                                                                 self.seats.items()}})
        except Refused as exc:                  # a malformed action: the player's own error, never a failure
            self.refused_invalid(seat, exc)
            raise
        if not st.meter.decided_by_model():
            st.count("refused_not_model")
            return 429, {"refused": True, "error": "refused: no new model response since your previous action"}
        st.count("n_act")
        if st.clock_left() < 0:
            self.lose(seat, "clock")
            return 200, {"clock_forfeit": "your clock ran out: you lose the match", "state": self.state(seat)}
        low, info = self.layer.lower(seat, cmd, None, self.m)
        act_id = self.acts.new(seat)                           # diagnostics (core 0.2.25): act -> observation -> effect
        self.diag("act_received", seat=seat, k=self.m.k, act_id=act_id, obs_id_last=self.acts.last_obs.get(seat),
                  decision=cmd)
        self.ep.write("cmd", k=self.m.k, seat=seat, cmd=low, model_call=st.meter.last_call(),
                      clock_used_s=round(st.clock_used(), 1))
        k_cmd = self.m.k
        applied = self.m.apply(seat, low) or {}
        self.diag("effect", seat=seat, act_id=act_id, k=k_cmd, info=jsonable(applied),
                  **({"rejected": True} if "rejected" in applied else {}))
        job = self.reply_job(seat, low, applied)              # the result's images: snapshot now, drawn off the lock
        info = {**applied, **info}
        self.bc.frame(force=True)
        self.bc.event("action", seat=seat, scores=self.m.scores())
        if self.m.phase().state == FINISHED:
            self.end("match_over")
        else:
            self.review_due = seat
        return 200, {**self.layer.reply(seat, cmd, info, self.m), "state": self.state(seat)}, job

    def ready(self, seat, body):
        g = self.gate(seat)
        if g:
            return g
        st = self.seats[seat]
        if self.review_due != seat:
            st.count("refused_turn")
            return 409, {"error": "no review is due from you now (reviews follow each of your actions)",
                         "state": self.state(seat)}
        why, plan = body.get("why"), body.get("plan")
        if not (isinstance(why, str) and isinstance(plan, str) and why.strip() and plan.strip()):
            return 400, {"error": "ready needs two non-empty texts: WHY and PLAN"}
        if len(why) > REVIEW_MAX_CHARS or len(plan) > REVIEW_MAX_CHARS:
            return 400, {"error": f"WHY and PLAN are limited to {REVIEW_MAX_CHARS} characters each"}
        rv = {"seat": seat, "after_action": self.m.k, "why": why.strip(), "plan": plan.strip(),
              "clock_used_s": round(st.clock_used(), 1)}
        self.reviews.append(rv)
        st.count("n_reviews")
        self.ep.write("review", **rv)
        self.review_due = None
        if st.clock_left() < 0:
            self.lose(seat, "clock")
            return 200, {"accepted": "review recorded", "clock_forfeit": "your clock ran out: you lose the match",
                         "state": self.state(seat)}
        if self.m.to_move() != seat:
            self.set_turn(self.m.to_move())
        return 200, {"accepted": "review recorded", "state": self.state(seat)}

    def wait(self, seat, body):
        try:
            timeout = min(WAIT_MAX_S, max(0.0, float(body.get("timeout_s", WAIT_MAX_S))))
        except (TypeError, ValueError, OverflowError):
            return 400, {"error": "timeout_s must be a number"}
        since = self.team_since(body)
        self.seats[seat].count("n_wait")
        deadline = time.time() + timeout
        while self.phase != "over" and self.on_turn != seat and time.time() < deadline:
            self.cond.wait(min(1.0, max(0.01, deadline - time.time())))
        return 200, {"state": self.state(seat, since=since)}

    # ------------------------------------------------------------------ watchdog, collect
    def loop(self):
        while True:
            time.sleep(0.5)
            with self.cond:
                if self.finalizing:
                    return
                if self.phase == "prepare" and self.start_deadline and time.time() > self.start_deadline:
                    self.start_deadline = None
                    if self.close_start_window():
                        self.begin()
                elif self.phase == "play" and self.on_turn and self.seats[self.on_turn].clock_left() < 0:
                    self.lose(self.on_turn, "clock")

    def collect(self):
        def run():
            with self.cond:
                if self.phase == "play" and self.on_turn:
                    s = self.on_turn
                    self.lose(s, "clock" if self.seats[s].clock_left() < 0 else "abandoned")
                elif self.no_show_at_collect():           # before the start: a side not started loses (core 0.2.7)
                    self.start_deadline = None
                elif not self.abandon_single():           # a single side off its turn also loses (core 0.2.6)
                    self.end("incomplete" if self.phase == "prepare" else "collected")
        threading.Thread(target=run, daemon=True).start()

    def extra_final(self):
        return {"clock_s": self.clock_s, "clock_used_s": {s: round(st.clock_used(), 1) for s, st in self.seats.items()},
                "started": {s: st.joined for s, st in self.seats.items()}}
