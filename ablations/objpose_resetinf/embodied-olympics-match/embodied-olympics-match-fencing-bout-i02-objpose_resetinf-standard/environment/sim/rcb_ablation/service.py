"""The ablations' match service: a subclass of the core's RealtimeService / TurnService (core/realtime.py,
core/turn.py, unchanged) that adds the switches' routes. With every switch off the module is never imported
(rcb_ablation/serve.py), so the core's service is the one that runs.

/finish (RCB_HIDE_SUCCESS). POST /<seat>/finish {} ends the agent's session at once: the match is decided exactly as
the core decides it when the session ends (Service.collect: before the start a no-show, during play an abandoned
match, both valid losses; after the end the result stands). After it every call but /spec and /status is a 409.

State queries (RCB_STATE_QUERY). GET /<seat>/state/entities and POST /<seat>/state/query {"names", "fields"}: the
sport's table (rcb_ablation/sports/<sport>.py), read under the world's lock, no step and no clock effect; 409 once the
match is over; counted (final.json state_queries) and logged (episode.jsonl rows "state_query", never replayed).

Reset, save and load (RCB_STATE_OPS, RCB_RESET_BUDGET). POST /<seat>/reset starts the match again from its frozen
start (the same build of the same seed: the world, the opponent and its random draws, the score, the clocks).
POST /<seat>/save_state {} keeps a deep copy of the whole match (the world with the opponent inside it, its random
generators, the score and the game clock; a built-in opponent seat's player; a turn match's chess clocks; the graded
command rows from the start) under a handle; POST /<seat>/load_state {"handle"} restores a copy of it. After a reset
or a load the world is frozen until the agent sends start (or ready), at most the review window, then it runs on. A
match the agent lost (or forfeited by the rules: a missed review, the chess clock) is held at its end instead of being
finalized, so the agent may reset or load; a win ends the run as before. The graded record (episode.jsonl) is the last
episode's: from the frozen start, or for a loaded one the rows up to the save followed by the rows after the load, so
the spectator replay draws the graded match. Earlier episodes' logs are kept as episode.<n>.jsonl.

A core from 0.5 on (table tennis G1): the platform opponent's program runs in a process of its own
(core/platform_seat.py); a save also keeps its whole state, read there after every observation already sent, its
replies received first (rcb_ablation/platform_ops.py, rcb_ablation/worker.py), and the commands it sent that are not
yet in effect; a load restores both and checks them (the reply's `verified`: the match's state digest and the program's
canonical state hash equal to the save's); a reset builds a new program. The seats' frame streams start empty, and the frozen world
after a reset or load runs on when its window (the review window) is over. GET /over stays false while a loss is held.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import threading
import time
from collections import OrderedDict

import core

from . import BUDGET, HIDE, MAX_HANDLES, OPS, QUERY
from . import platform_ops
from . import snapcopy
from . import sports

RULE_ENDS = ("match_over", "ready_timeout", "clock")        # a match decided by its rules: held when lost (OPS)
NEW = not str(getattr(core, "VERSION", "")).startswith("0.2.")   # a core from 0.5 on (platform seats, frame streams)
STREAM_DRAIN_S = 30.0                                      # a frame being drawn at a reset or load: waited for


class _Abl:
    def __init__(self):
        self.finished = False
        self.finish_t = None
        self.collected = False
        self.queries = 0
        self.gen = 0
        self.resets = self.saves = self.loads = 0
        self.handles: OrderedDict = OrderedDict()
        self.next_handle = 0
        self.held = False                    # OPS: the match ended in a loss and is held (not finalized)
        self.episode = 1
        self.episodes_log: list = []
        self.ep_began = "start"
        self.ep_t0 = 0.0
        self.ep_k0 = 0
        self.header = None
        self.players: dict = {}             # built-in seat -> its locked player
        self.restore_players: dict = {}     # built-in seat -> the player to restore at its next start
        self.loop_alive = False
        self.reporter = False
        self.verified: dict = {}            # the last load's checks (a core from 0.5 on)
        self.table = None


def _now(svc) -> float:
    return round(time.monotonic() - svc.t0, 3)


def make(Base):
    turn = Base.protocol == "turn"

    class Ablation(Base):
        def __init__(self, *a, **kw):
            self.abl = _Abl()
            super().__init__(*a, **kw)
            self.abl_sport = sports.module(self.sport.name)

        # ------------------------------------------------------------------ routes
        def routes(self, post):
            r = dict(super().routes(post))
            if post:
                if HIDE:
                    r["finish"] = self.abl_finish
                if QUERY:
                    r["state_query"] = self.abl_query
                if OPS:
                    r.update(reset=self.abl_reset, save_state=self.abl_save, load_state=self.abl_load)
            elif QUERY:
                r["state_entities"] = self.abl_entities
            if HIDE and self.abl.finished:
                r = {ep: (fn if ep in ("spec", "status") else self.abl_after_finish) for ep, fn in r.items()}
            return r

        def abl_after_finish(self, seat, body=None):
            return 409, {"error": "your session has finished (POST /finish): no more calls"}

        def spec(self, seat, body=None):
            code, out = super().spec(seat, body)
            if code != 200:
                return code, out
            out = dict(out)
            if HIDE:
                out["success_signal"] = "hidden"
                out["finish"] = ("POST /finish {}: ends your session now; the match is decided as at the end of your "
                                 "session (before the start: no-show; during play: abandoned; after the end: the "
                                 "result stands); afterwards every call but /spec and /status is refused (409)")
            if QUERY:
                out["state_query"] = {"entities": "GET /state/entities", "query": "POST /state/query",
                                      "frame": (self.abl_table() or {}).get("frame")}
            if OPS:
                b = dict(out.get("budget") or {})
                b["reset"] = BUDGET
                out["budget"] = b
                out["state_ops"] = {
                    "reset": "POST /reset {}: the match from its start again (world, opponent, score, clocks)",
                    "save_state": "POST /save_state {}: answers {handle, step}; the handle only, never the state",
                    "load_state": "POST /load_state {handle}: the saved match (world, opponent, score, game clock) "
                                  "as a new episode",
                    "after": ("after a reset or a load the match resumes at once, on the turn it had (your clock "
                              "as it was)" if turn else
                              "after a reset or a load the world is frozen until you send start (or ready), at most "
                              f"{self.abl_window():g} s of real time; then it runs on"),
                    "max_handles": MAX_HANDLES, "resets": BUDGET,
                    "end": "a match you lose (or forfeit by the rules) is held at its end: you may reset or load; "
                           "a match you win ends the run"}
            return 200, out

        # ------------------------------------------------------------------ /finish
        def abl_finish(self, seat, body=None):
            with self.cond:
                if self.abl.finished:
                    return 409, {"error": "your session has already finished"}
                self.abl.finished, self.abl.finish_t = True, _now(self)
                (getattr(self, "diag", None) or self.ep.write)("finish", seat=seat, k=self.m.k, phase=self.phase)
            self.collect()
            return 200, {"ok": True, "done": True, "reason": "finished"}

        def collect(self, *a, **kw):
            with self.cond:
                self.abl.collected = True
                if OPS and self.abl.held and not self.finalizing:      # a held loss: finalize it now
                    self.finalizing = True
                    if NEW:
                        self.session_end(a[0] if a else kw.get("events"))
                        self.on_end()
                        self.settle_seats(self.reason, self.forfeiting)
                        self.ended_at = time.monotonic()
                        self.devgate("over")
                    self.abl_close_episode(self.reason or "over")
                    threading.Thread(target=self.finalize, daemon=True).start()
                    return
            return super().collect(*a, **kw)

        # ------------------------------------------------------------------ the end of a match (OPS: held losses)
        def end(self, reason, forfeiting=None):
            if not OPS or reason not in RULE_ENDS or self.abl.collected or self.abl.finished:
                if OPS and not self.finalizing:
                    with self.cond:
                        if not self.finalizing and not self.abl.held:
                            self.abl_close_episode(reason)
                return super().end(reason, forfeiting)
            with self.cond:
                if self.finalizing or self.phase == "over":
                    return
                if forfeiting is not None:
                    self.forfeit(forfeiting, reason)
                prev = self.reason
                self.reason = reason
                won = self.abl_agent_won()
                self.reason = prev
                if won:
                    self.abl_close_episode(reason)
                    return super().end(reason, None)          # the forfeit (if any) is already recorded
                self.abl_stop_world()
                self.phase, self.reason, self.abl.held = "over", reason, True
                if NEW:
                    self.devgate("review")              # frozen, as in a review: a reset or load may follow
                self.ep.write("end", k=self.m.k, reason=reason)
                self.bc.frame(force=True)
                self.bc.event("end", reason=reason)
                self.abl_close_episode(reason)
                self.write_final()
                self.cond.notify_all()

        def abl_stop_world(self):
            """A held loss: the world stops as at the end (its pending acts dropped), but stays usable for a reset or
            a load (a core from 0.5 on: its frame streams stay open)."""
            if not NEW:
                return self.on_end()
            if self.segment_start is not None:
                self.run_wall += time.monotonic() - self.segment_start
                self.segment_start = None
            self.drop_all("match_over")

        def abl_agent_won(self) -> bool:
            seat = self.abl_seat()
            try:
                return self.outcome().winner == self.cfg.side_of(seat)
            except Exception:  # noqa: BLE001
                return False

        def abl_seat(self) -> str:
            builtin = set(self.abl_builtin())
            return next((s for s in self.cfg.seats if s not in builtin), self.cfg.seats[0])

        def abl_builtin(self) -> dict:
            out = {}
            for item in (os.environ.get("RO_BUILTIN_SEATS") or "").split(","):
                if "=" in item:
                    s, _, ref = item.partition("=")
                    if s.strip() and ref.strip():
                        out[s.strip()] = ref.strip()
            return out

        def loop(self):
            while True:
                with self.cond:
                    self.abl.loop_alive = True
                again = False
                try:
                    super().loop()
                finally:
                    with self.cond:
                        # a reset or load while this loop was returning (it saw "over"): it runs the new episode
                        again = OPS and self.phase != "over" and not self.finalizing
                        self.abl.loop_alive = again
                if not again:
                    return

        def reporter(self):
            """The mid-match final.json writer (a core from 0.4 on): one per service, though the world loop that
            starts it runs again after a held loss."""
            with self.cond:
                if self.abl.reporter:
                    return
                self.abl.reporter = True
            return super().reporter()

        def timeout(self):
            """After a reset or a load (a core from 0.5 on: the match has started, the phase is prepare): the window
            ran out, the world runs on after the lead time (nobody loses). Otherwise the core's rule."""
            if NEW and OPS and self.phase == "prepare" and self.match_t0 is not None:
                self.ready_deadline = None
                self.resume_at = time.monotonic() + float(self.ts.timing["barrier_lead_s"])
                self.diag("restart_window_over", k=self.m.k)
                return
            return super().timeout()

        # ------------------------------------------------------------------ state queries
        def abl_table(self):
            if self.abl.table is None and self.abl_sport is not None and hasattr(self.abl_sport, "entities"):
                with self.cond:
                    self.abl.table = self.abl_sport.entities(self.m, self.abl_seat())
            return self.abl.table

        def abl_entities(self, seat, body=None):
            if self.abl_sport is None or not hasattr(self.abl_sport, "entities"):
                return 501, {"error": "no state table for this sport"}
            with self.cond:
                if self.phase == "over":
                    return 409, {"error": "the match is over"}
            return 200, self.abl_table()

        def abl_query(self, seat, body):
            table = self.abl_table() if self.abl_sport is not None else None
            if not table:
                return 501, {"error": "no state table for this sport"}
            ents = table["entities"]
            names = body.get("names")
            fields = body.get("fields")
            if not isinstance(names, list) or not names or not all(isinstance(n, str) for n in names):
                return 400, {"error": "names: a non-empty list of entity names", "names": sorted(ents)}
            bad = [n for n in names if n not in ents]
            if bad:
                return 400, {"error": f"unknown names {bad[:10]}", "names": sorted(ents)}
            if fields is not None:
                if not isinstance(fields, list) or not all(isinstance(f, str) for f in fields):
                    return 400, {"error": "fields: a list of field names (optional)"}
                valid = sorted({f for n in names for f in ents[n]["fields"]})
                badf = [f for f in fields if f not in valid]
                if badf:
                    return 400, {"error": f"unknown fields {badf[:10]}", "fields": valid}
            with self.cond:
                if self.phase == "over" or self.finalizing:
                    return 409, {"error": "the match is over"}
                vals = self.abl_sport.read(self.m, self.abl_seat(), names)
                self.abl.queries += 1
                k, n = self.m.k, self.abl.queries
                (getattr(self, "diag", None) or self.ep.write)("state_query", seat=seat, k=k, names=names[:50])
            if fields is not None:
                vals = {name: {f: v for f, v in vals.get(name, {}).items() if f in fields} for name in names}
            else:
                vals = {name: vals.get(name, {}) for name in names}
            dt = float(getattr(self.m, "dt", 0.0) or 0.0)
            return 200, {"state": vals, "control_steps": k, "sim_time_s": round(k * dt, 6) if dt else None,
                         "state_queries": n}

        # ------------------------------------------------------------------ reset, save, load
        def abl_window(self) -> float:
            if NEW:
                return float(self.review_window())
            return float(os.environ.get("READY_TIMEOUT_S", "60"))

        def abl_can_restart(self):
            if self.finalizing or self.abl.collected or self.abl.finished:
                return 409, {"error": "the run has ended: no reset, save or load"}
            return None

        def abl_reply(self, seat):
            st = self.state(seat)
            out = {"episode": self.abl.episode, "resets_left": BUDGET - self.abl.resets, "saves": self.abl.saves,
                   "loads": self.abl.loads}
            out["state" if turn else "now"] = st
            return out

        def abl_reset(self, seat, body=None):
            with self.cond:
                bad = self.abl_can_restart()
                if bad:
                    return bad
                if self.abl.resets >= BUDGET:
                    return 409, {"error": "no resets left", "resets_left": 0}
                m = self.sport.build(self.cfg)
                if hasattr(self.m, "camera_model"):          # the service tells its match the camera model
                    try:
                        m.camera_model = self.m.camera_model
                    except AttributeError:
                        pass
                self.abl.resets += 1
                self.abl_restart(m, None, "reset")
                return 200, self.abl_reply(seat)

        def abl_save(self, seat, body=None):
            with self.cond:
                bad = self.abl_can_restart()
                if bad:
                    return bad
                if self.phase == "over":
                    return 409, {"error": "the match is over: nothing to save"}
                t = time.monotonic()
                ps = getattr(self, "pseats", None)
                programs = platform_ops.save(ps) if ps else {}     # the platform opponent's program, in its process
                m, shared = snapcopy.snap(self.m)
                sched = getattr(self, "sched", None) if NEW else None
                snap = {"m": m, "k": self.m.k, "digest": self.m.state_digest(), "rows": copy.deepcopy(self.ep.commands),
                        "scheduled": copy.deepcopy(getattr(self, "scheduled", [])), "players": self.abl_save_players(),
                        "programs": programs,
                        "sched": {"platform_pending": copy.deepcopy(sched.platform_pending),
                                  "platform_seq": sched.platform_seq,
                                  "scheduled": copy.deepcopy(sched.scheduled)} if sched is not None else None,
                        "clocks": {s: (st.used, st.clock_s) for s, st in self.seats.items()} if turn else None,
                        "on_turn": getattr(self, "on_turn", None), "review_due": getattr(self, "review_due", None)}
                self.abl.next_handle += 1
                h = f"s{self.abl.next_handle}"
                self.abl.handles[h] = snap
                while len(self.abl.handles) > MAX_HANDLES:
                    self.abl.handles.popitem(last=False)
                self.abl.saves += 1
                self.ep.write("save_state", handle=h, k=self.m.k, digest=snap["digest"],
                              copy_s=round(time.monotonic() - t, 3), shared=shared,
                              **({"program_state_sha": {s: p["state_sha"] for s, p in programs.items()}} if programs else {}))
                return 200, {"handle": h, "step": self.m.k, "saves": self.abl.saves,
                             "handles_kept": len(self.abl.handles)}

        def abl_load(self, seat, body):
            h = body.get("handle")
            with self.cond:
                bad = self.abl_can_restart()
                if bad:
                    return bad
                if not isinstance(h, str) or h not in self.abl.handles:
                    return 404, {"error": "unknown handle (saved in this run and among the last "
                                          f"{MAX_HANDLES} kept)", "handles": list(self.abl.handles)}
                snap = self.abl.handles.pop(h)
                self.abl.handles[h] = snap                   # most recently used
                m, _ = snapcopy.snap(snap["m"])
                self.abl.loads += 1
                self.abl_restart(m, snap, "load", handle=h)
                out = self.abl_reply(seat)
                if NEW:
                    out["verified"] = self.abl.verified
                return 200, out

        def abl_save_players(self) -> dict:
            out = {}
            for seat, p in self.abl.players.items():
                got = p.lock.acquire(timeout=10)
                try:
                    out[seat], _ = snapcopy.snap(p.player)
                finally:
                    if got:
                        p.lock.release()
            return out

        def abl_close_episode(self, ended):
            a = self.abl
            if a.episodes_log and a.episodes_log[-1]["episode"] == a.episode:
                return
            a.episodes_log.append({"episode": a.episode, "began": a.ep_began, "t_start_s": a.ep_t0,
                                   "t_end_s": _now(self), "control_steps": int(self.m.k) - int(a.ep_k0),
                                   "ended": ended})

        def abl_restart(self, m, snap, why, handle=None):
            """Under the lock: a new episode on match `m` (a fresh build or a copy of a saved one)."""
            a = self.abl
            self.abl_close_episode(self.reason if self.phase == "over" else why)
            # the old episode's acts and built-in players stop here
            a.gen += 1
            if not turn and NEW:
                # the acts not yet in effect are dropped; the platform opponent's commands received and not yet in
                # effect are the saved ones (none after a reset)
                self.drop_all(why)
                self.flight = {s: {} for s in self.cfg.seats}
                sc = (snap or {}).get("sched")
                self.sched.platform_pending = copy.deepcopy(sc["platform_pending"]) if sc else []
                self.sched.platform_seq = sc["platform_seq"] if sc else 0
                self.sched.scheduled = copy.deepcopy(sc["scheduled"]) if sc else []
            elif not turn:
                for (s, _e), item in list(self.pending.items()):
                    if hasattr(self, "dropped"):
                        self.dropped(item, s, why)
                self.pending.clear()
                self.scheduled = copy.deepcopy(snap["scheduled"]) if snap else []
            if not turn:
                if self.segment_start is not None:
                    self.run_wall += time.monotonic() - self.segment_start
                self.segment_start = self.anchor = self.resume_at = None
                self.seen = {}
            self.m = m
            self.bc.m = m
            if NEW:
                self.abl_restart_new(m, snap)
            if hasattr(self.layer, "_units"):                # the skill in the loop: reload at the next contact
                self.layer._units.clear()
            self.phase, self.reason, self.forfeiting, a.held = "prepare", None, None, False
            self.retired = []
            if hasattr(self, "exits"):
                self.exits = []
            for st in self.seats.values():
                st.ready = False
                st.retired = False
            self.abl_rotate_log(snap, why, handle)
            a.episode += 1
            a.ep_began, a.ep_t0, a.ep_k0 = why, _now(self), int(m.k)
            if turn:
                now = time.time()
                for s, st in self.seats.items():
                    st.used = snap["clocks"][s][0] if snap else 0.0
                    st.turn_t0, st.turn_busy = None, 0.0
                self.on_turn = None
                self.review_due = snap["review_due"] if snap else None
                self.start_deadline = None
                self.begin()                    # a turn match plays on at once (the chess clock runs on your turn)
            else:
                if not NEW or self.match_t0 is not None:     # (before the match start: the start window stands)
                    self.ready_deadline = time.monotonic() + self.abl_window()
                if NEW and self.match_t0 is not None:
                    self.devgate("review")
                if not a.loop_alive:
                    a.loop_alive = True
                    threading.Thread(target=self.loop, daemon=True).start()
            self.abl_restart_players(snap)
            self.write_final()
            self.cond.notify_all()

        def abl_restart_new(self, m, snap):
            """A core from 0.5 on, under the lock: the platform opponent's program is the saved one (a load: checked
            to pickle to the saved bytes) or a new one (a reset); every seat's frame stream starts empty."""
            ps = getattr(self, "pseats", None)
            got = platform_ops.restore(ps, snap.get("programs") if snap else None) if ps else {}
            v = {"state_digest_equal": m.state_digest() == snap["digest"]} if snap else {}
            if snap and got:
                v["opponent_program_equal"] = {s: r.get("state_sha") == snap["programs"][s]["state_sha"]
                                               and r.get("program_digest") == snap["programs"][s].get("program_digest")
                                               for s, r in got.items()}
                diff = {s: sorted(k for k, h in (r.get("parts") or {}).items()
                                  if (snap["programs"][s].get("parts") or {}).get(k) != h)
                        for s, r in got.items() if not v["opponent_program_equal"][s]}
                if diff:
                    v["opponent_program_diff"] = diff
            self.abl.verified = v
            for fs in (getattr(self, "streams", None) or {}).values():
                end = time.monotonic() + STREAM_DRAIN_S
                with fs.cond:
                    for item in fs.pending:
                        fs.queued.discard(item[0])
                    fs.pending.clear()
                    while fs.queued and time.monotonic() < end:      # a frame being drawn: its drawing ends
                        fs.cond.wait(0.05)
                    fs.ready.clear()
                    fs.metas.clear()
                    fs.dropped.clear()
                    fs.queued.clear()
                    fs.unit_first.clear()

        def abl_rotate_log(self, snap, why, handle):
            ep = self.ep
            if hasattr(ep, "flush"):
                ep.flush(timeout=60)                         # a background writer: every row in the file first
            with ep.lock:
                cv = getattr(ep, "_cv", None)
                if cv is not None:
                    with cv:
                        while ep._done < ep._queued:
                            cv.wait(1.0)
                        if ep._f is not None and not ep._f.closed:
                            ep._f.close()
                        ep._f = None
                if self.abl.header is None:
                    with ep.path.open() as f:
                        self.abl.header = f.readline()
                keep = ep.path.with_name(f"episode.{self.abl.episode}.jsonl")
                try:
                    os.replace(ep.path, keep)
                except OSError:
                    pass
                rows = copy.deepcopy(snap["rows"]) if snap else []
                with ep.path.open("w") as f:
                    f.write(self.abl.header)
                    for r in rows:
                        f.write(json.dumps(r, default=float) + "\n")
                ep.commands = rows
                if hasattr(ep, "_sha"):                       # the running digest of the command rows
                    h = hashlib.sha256(b"[")
                    for i, r in enumerate(rows):
                        if i:
                            h.update(b",")
                        h.update(json.dumps(r, sort_keys=True, separators=(",", ":"), default=float).encode())
                    ep._sha = h
            self.ep.write(why if why != "load" else "load_state", episode=self.abl.episode + 1, k=self.m.k,
                          **({"handle": handle, "digest": snap["digest"]} if snap else {}),
                          **({"verified": self.abl.verified} if NEW else {}),
                          resets=self.abl.resets, saves=self.abl.saves, loads=self.abl.loads,
                          previous_log=f"episode.{self.abl.episode}.jsonl")

        def abl_restart_players(self, snap):
            builtin = self.abl_builtin()
            if not builtin or not hasattr(self, "abl_builtin_mod"):
                return
            self.abl.players = {}
            self.abl.restore_players = {}
            if snap:
                for seat, p in (snap.get("players") or {}).items():
                    self.abl.restore_players[seat], _ = snapcopy.snap(p)
            for st_name in builtin:
                self.seats[st_name].joined = False
            self.abl_builtin_mod.start(self, self.plugin, builtin)

        # ------------------------------------------------------------------ final.json
        def extra_final(self):
            out = dict(super().extra_final())
            a = self.abl
            if HIDE:
                out["success_signal"] = "hidden"
                out["finished"] = a.finished
                out["finish_time_s"] = a.finish_t
                out["ended_by"] = ("finish" if a.finished else "timeout" if a.collected else
                                   "match" if self.phase == "over" else None)
            if QUERY:
                out["state_queries"] = a.queries
            if OPS:
                log = list(a.episodes_log)
                if not log or log[-1]["episode"] != a.episode:
                    log.append({"episode": a.episode, "began": a.ep_began, "t_start_s": a.ep_t0, "t_end_s": None,
                                "control_steps": int(self.m.k) - int(a.ep_k0), "ended": None})
                out.update(resets=a.resets, saves=a.saves, loads=a.loads, episodes=a.episode, reset_budget=BUDGET,
                           episodes_log=log)
                if self.finalized:
                    try:
                        won = self.outcome().winner == self.cfg.side_of(self.abl_seat())
                    except Exception:  # noqa: BLE001
                        won = False
                    if won:
                        out.update(resets_at_success=a.resets, loads_at_success=a.loads)
            return out

    Ablation.__name__ = Ablation.__qualname__ = "Ablation" + Base.__name__
    return Ablation


# ---------------------------------------------------------------------- built-in seats (core/builtin_seat.py)
class _LockedPlayer:
    """A built-in seat's player: act / review under a lock, so save_state copies it between two decisions."""

    def __init__(self, player):
        self.player, self.lock = player, threading.Lock()

    def act(self, view):
        with self.lock:
            return self.player.act(view)

    def __getattr__(self, name):
        attr = getattr(self.player, name)
        if callable(attr) and name in ("review", "message"):
            def locked(*a, **kw):
                with self.lock:
                    return attr(*a, **kw)
            return locked
        return attr


def patch_builtin(bs):
    """core/builtin_seat.py: each player is wrapped (and restored from a save on a load); a seat's thread of an older
    episode ends at its next call (its LocalSeat answers `done`)."""
    if not OPS or getattr(bs, "abl_patched", False):
        return
    bs.abl_patched = True
    orig_init, orig_call, orig_load, orig_start = bs.LocalSeat.__init__, bs.LocalSeat.call, bs.load, bs.start

    def init(self, service, seat):
        orig_init(self, service, seat)
        self.abl_gen = service.abl.gen if hasattr(service, "abl") else 0

    def call(self, ep, body=None, tries=20):
        svc = self.service
        if hasattr(svc, "abl") and svc.abl.gen != self.abl_gen:
            return {"now": {"done": True, "phase": "over", "reason": "superseded by a reset or load"},
                    "state": {"done": True}, "http_status": 409}
        return orig_call(self, ep, body, tries)

    def start(service, plugin, seats):
        service.abl_builtin_mod = bs

        def wrap(ref):
            factory = orig_load(ref, plugin)

            def make_player(spec, seat, seed):
                restore = service.abl.restore_players.pop(seat, None)
                p = _LockedPlayer(restore if restore is not None else factory(spec, seat, seed))
                service.abl.players[seat] = p
                return p
            return make_player
        saved = bs.load
        bs.load = lambda ref, plugin_: wrap(ref)
        try:
            return orig_start(service, plugin, seats)
        finally:
            bs.load = saved

    bs.LocalSeat.__init__, bs.LocalSeat.call, bs.start = init, call, start
