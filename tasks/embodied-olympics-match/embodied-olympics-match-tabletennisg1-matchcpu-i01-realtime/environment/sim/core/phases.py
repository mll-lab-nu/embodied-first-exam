"""Phase rules (core 0.3.0, fw-v1): the start barrier t0, the preparation and match deadlines, no-show, abandonment,
the wall-clock match cap, and what final.json says about every seat and side. A mixin of the match service
(core/service.py Service); both protocols (core/realtime.py, core/turn.py) use it.

Start barrier (TaskSpec timing.t0, core/taskspec.py):
    barrier         (generated tasks) the match opens when every seat has arrived: a seat arrives with its first
                    request of any kind (the harness adapter sends POST /<seat>/session before it starts the harness:
                    `python3 -m ro_client --session`; the built-in client loop does the same). t0 = the last arrival,
                    or T0_WAIT_S (timing.t0_wait_s, default 600 s) after the first one ("barrier_timeout"). Until
                    then start / act / ready answer 409 ("the match opens when every seat's session has started"),
                    the other endpoints answer as usual. The preparation deadline counts from t0.
    service_start   (tools that start no Harbor trial; unit tests) t0 = the service start, the rule before 0.3.0.
POST /<seat>/session {} blocks at most SESSION_WAIT_S (30 s): before t0 {"phase": "init", "waiting_for": [seats]}
(the client calls again), from t0 on at once {"t0", "source", "phase", "deadlines"}. Episode rows: `session` (a
seat's first arrival), `t0` (epoch, source, arrivals); final.json `t0` = {"epoch", "source": "barrier" |
"barrier_timeout" | "service_start", "arrivals": {seat: epoch}}.

Seat status (final.json seat_status; an episode row `seat_status` at every change):
    {seat: {"state": "playing" | "finished" | "timed_out" | "session_ended" | "retired" | "infra_failure",
            "why", "k"}}
    timed_out: no_show, ready_timeout or clock; session_ended: decided at the collect only (the official world never
    sees one session end: abandoned, collected); retired: the side retired (more than two sides); infra_failure: a
    technical failure, or no session ever arrived from the seat.
Side outcome (final.json side_outcome, derived from core/outcome.py's decision once the match is over):
    {side: {"result": "won" | "lost" | "drew" | "ranked" | "forfeit" | "dnf" | "void" | "solo", "place", "why"}}
    (drew, core 0.5.2: a draw the fixture allows; place 1 for every side)
failure_hint (final.json): the core's own reading {"class": "none" | "agent" | "infrastructure" |
"external_provider", "reason"}; the verifier (core/grading.py, verdict.json) decides.

Lifecycle (core 0.4.0, fw_pattern §7 decision 3; eo-seat/1 9.7). A seat's harness session ending is only an event
(`harness_exit` rows, final.json harness_exits): the seat stays in the match, its programs play on. The real exits:
    resigned   POST /<seat>/resign: the seat's side leaves (taskspec.UNDECIDED resign: any seat of a side)
    no_show    a side with a seat that has not started when the preparation window closes (agent); a seat that never
               arrived at all is a platform failure (no_session)
    rules      a sport's own exit (an event side_retired), and the turn protocol's chess clock
One rule for every exit (exit_side): if fewer than two sides remain in play (platform sides count) the match ends,
the leaving side forfeits; else the side retires (Match.retire: its robots perform the safe exit action) and the
others go on; the retired sides are ranked after those still in play, the later retirement first. A review never
forfeits: its window runs out -> the world resumes (realtime) or the turn passes (turn), the missing review is a
`review_missing` row. The wall-clock cap is a platform safety cut-off (reason wall_cap, a platform fault: void),
never settled by the score; SIGUSR2 ends a match as a platform fault the platform requested (reason aborted).
final.json `termination` (the world report's vocabulary): completed | resigned | no_show | wall_cap |
platform_fault | not_started; `exits` [{side, kind, step, seat}]; `faults` [{class, code, where, at_step}].
"""
from __future__ import annotations

import json
import os
import time

SESSION_WAIT_S = 30.0            # POST /session blocks at most this long per call
FORFEIT_REASONS = ("ready_timeout", "clock", "abandoned", "no_show", "resigned")   # ready_timeout / abandoned: before 0.4.0
TERMINATION = {"match_over": "completed", "clock": "completed", "ready_timeout": "completed", "abandoned": "completed",
               "resigned": "resigned", "no_show": "no_show", "wall_cap": "wall_cap", "technical_error": "platform_fault",
               "aborted": "platform_fault", "incomplete": "not_started", "collected": "not_started"}
EXIT_KINDS = ("resigned", "no_show")
T0_SOURCES = ("barrier", "barrier_timeout", "service_start")
SEAT_STATES = ("playing", "finished", "timed_out", "session_ended", "retired", "infra_failure")
SIDE_RESULTS = ("won", "lost", "drew", "ranked", "forfeit", "dnf", "void", "solo")
FAILURE_CLASSES = ("none", "agent", "infrastructure", "external_provider")
BEFORE_T0 = "the match opens when every seat's session has started"


class PhaseRules:
    """Mixin of Service. Needs self.cfg, self.seats, self.cond, self.ep, self.ts (core/taskspec.py), self.phase,
    self.reason, self.forfeiting, self.retired, self.t0 (monotonic service start). The preparation window, the
    deadlines, no-show, abandonment and the match cap (Service.start_window ... abandon_single before core 0.3.0) moved
    here unchanged in a commit of their own; the preparation then counts from t0. A protocol sets its preparation
    deadline in on_t0()."""

    # ------------------------------------------------------------------ moved from core/service.py (core 0.3.0)
    def start_window(self) -> float:
        """The preparation window when the task sets none (TaskSpec timing.prepare_s None): 1800 s (realtime: the
        review window, RealtimeService.start_window)."""
        return 1800.0

    # ------------------------------------------------------------------ D2: two-phase timing (pilot 2026-10-18)
    def prepare_window(self) -> float | None:
        """TaskSpec timing.prepare_s (D2; PREPARE_TIMEOUT_S, else START_TIMEOUT_S, else taskspec.json; core 0.3.0):
        the preparation phase, counted from the match service start, the same moment for every seat (they all got
        the task then); a side with a seat that has not sent start by then loses (no_show). Not set: the protocol's
        fallback (Service.start_window), from the same moment (core 0.2.38: it used to open with the first start, so
        that an early start moved the other seats' deadline)."""
        v = self.ts.timing.get("prepare_s")
        return float(v) if v is not None else None

    def prep_window(self) -> float:
        """The preparation window in seconds (core 0.2.38, ready barrier): PREPARE_TIMEOUT_S, else the start window
        START_TIMEOUT_S. Always counted from the service start (self.t0), the common moment of every seat; no seat's
        start or ready ever moves it."""
        p = self.prepare_window()
        return p if p is not None else self.start_window()

    def match_window(self) -> float | None:
        """TaskSpec timing.match_s (D2; MATCH_TIMEOUT_S): the match phase, counted from the match start (the first
        run); when it runs out the match ends as at the collect (Service.time_up). Not set: no limit but the
        session's."""
        v = self.ts.timing.get("match_s")
        return float(v) if v is not None else None

    def wall_cap_deadline(self) -> float | None:
        """The monotonic time of the platform safety cut-off (TaskSpec timing.wall_cap_s, counted from t0; core
        0.4.0), None before t0 or without one. A gen-1 task's cap is timing.match_s, from the match start
        (match_window). taskspec.UNDECIDED wall_cap_from names the two."""
        v = self.ts.timing.get("wall_cap_s")
        if v is None or self.t0_mono is None:
            return None
        return self.t0_mono + float(v)

    def deadlines_now(self) -> dict:
        """With the lock held: what is left of the two phases (wall seconds; None: not running / no limit)."""
        now = time.monotonic()
        p, m = self.prep_window(), self.match_window()
        prep = (max(0.0, round(self.t0_mono + p - now, 1)) if self.t0_mono is not None and self.match_t0 is None
                and self.phase == "prepare" else None)
        match = (max(0.0, round(self.match_t0 + m - now, 1)) if m is not None and self.match_t0 is not None
                 and self.phase != "over" else None)
        cap = getattr(self, "cap_deadline", None)
        return {"prepare_left_s": prep, "match_left_s": match,
                "wall_cap_left_s": (max(0.0, round(cap - now, 1)) if cap is not None and self.phase != "over" else None)}

    def failure_rule(self) -> str:
        """N18: what happens to a seat whose program crashes, goes silent or answers late (sport.toml [timing]
        failure_rule, else the protocol's generic rule)."""
        own = (self.decl.get("timing") or {}).get("failure_rule")
        if own:
            return str(own)
        if self.protocol == "turn":
            return ("nothing is played for you: if your program crashes or stops, the game waits for your action "
                    "while your chess clock runs; when it runs out you lose the match (clock)")
        return ("nothing is sent for you: if your program crashes, stops sending acts or answers late, the world goes "
                "on with the commands already in force (the action layer's own rule: a target or setpoint holds "
                "until a new act replaces it); a late act takes effect when it arrives, at the next control step")

    def phase_rules(self) -> dict:
        """/spec `phases` (D2): the two phases and how play resumes after ready."""
        p, m = self.prep_window(), self.match_window()
        out = {"prepare": {"timeout_s": p, "from": self.start_rule()["opens"], "rule": self.start_rule()["rule"]},
               "match": {"timeout_s": m, "from": "match_start",
                         "rule": ("no limit of its own: the match ends by the rules (your seat stays in the match "
                                  "when your own session ends: the programs you started play on)" if m is None else
                                  f"a platform safety cut-off {m:g} s of wall time after the match start: a match "
                                  "still running then does not count (a platform fault, replayed later); it is never "
                                  "settled by the score. Your seat stays in the match when your own session ends")},
               "wall_cap": {"timeout_s": self.ts.timing.get("wall_cap_s"), "from": "t0",
                            "rule": "a platform safety cut-off: a match still running then does not count"},
               "left": self.deadlines_now(), "failure_rule": self.failure_rule()}
        return out

    def time_up(self, which: str = "match_s"):
        """With the lock held: the wall-clock cap ran out (core 0.4.0: a platform safety cut-off, fw_pattern §7
        decision 5): the match ends "wall_cap", a platform fault (void, rerun), never settled by the score. `which`:
        timing.wall_cap_s (from t0) or the legacy timing.match_s (from the match start)."""
        self.diag("match_timeout", k=self.m.k, phase=self.phase, cap=which)
        self.fault("platform", "wall_cap", where="host", note=f"the wall-clock cap ({which}) ran out")
        self.end("wall_cap")

    def fault(self, cls: str, code: str, where: str | None = None, note: str | None = None, seat=None):
        """With the lock held: a fault the Host observed (final.json `faults`; the Judge classifies): class platform
        | plugin | external | agent | undetermined."""
        f = {"class": cls, "code": code, "at_step": int(self.m.k)}
        if where:
            f["where"] = where
        if seat:
            f["seat"] = seat
        if note:
            f["note"] = note[:300]
        if f not in self.faults:
            self.faults.append(f)
            self.diag("fault", **f)

    def exit_side(self, seat: str, why: str) -> bool:
        """With the lock held: the one exit rule (eo-seat/1 9.7): `seat`'s side leaves (resigned, no_show, clock, a
        rule). If fewer than two sides would remain in play (platform sides count: MatchConfig.platform) the match
        ends and the side forfeits; else the side retires (Match.retire: its robots perform the safe exit action;
        whatever the sport answers, the Host takes no act of it any more) and the others go on. True: the match goes
        on."""
        side = self.cfg.side_of(seat)
        if side in self.retired:
            return True
        if why in EXIT_KINDS:
            self.exits.append({"side": side, "kind": why, "step": int(self.m.k), "seat": seat})
        platform = len(getattr(self.cfg, "platform", None) or {})
        remaining = [x for x in self.active_sides() if x != side]
        if len(remaining) + platform >= 2:
            self.m.retire(side, why)
            self.retired.append(side)
            for s in self.cfg.seats_of(side):
                self.seats[s].retired = True
            self.ep.write("retire", k=self.m.k, seat=seat, side=side, why=why)
            self.retire_seats(side, why)
            self.failsafe(side)                  # core 0.4.0: its robots' safe exit (Match.failsafe; default none)
            self.cond.notify_all()
            return True
        self.end(why, seat)
        return False

    def referee_retired(self, side: str, why: str):
        """With the lock held (core 0.4.0, eo-world/1 Event side_retired): the sport's referee took `side` out under
        its rules (no Host exit: the result says it, status retired). The Host takes no act of its seats any more and
        applies the safe exit; whether the match goes on is the sport's (Match.phase)."""
        if side in self.retired or side not in self.cfg.side_list():
            return
        self.retired.append(side)
        for s in self.cfg.seats_of(side):
            self.seats[s].retired = True
        self.diag("referee_retired", k=self.m.k, side=side, why=why)
        self.retire_seats(side, why)
        self.failsafe(side)
        self.cond.notify_all()

    def session_end(self, events: list | None = None):
        """With the lock held: harness sessions ended (core 0.4.0: an event only, never an exit). `events`: the
        Backend's per-seat events [{"seat", "code"?, "at"?}]; None: every session has ended (Harbor's collect) and
        each seat without an exit yet gets one. Rows `harness_exit` (seat, code, k), final.json harness_exits."""
        if events is None:
            events = [{"seat": s} for s in self.cfg.seats if not self.harness_exits.get(s)]
        for e in events:
            seat = e.get("seat")
            if seat not in self.seats:
                continue
            self.harness_exits.setdefault(seat, []).append(int(self.m.k))
            self.diag("harness_exit", seat=seat, k=self.m.k, code=e.get("code"), at=e.get("at"),
                      phase=self.phase)

    def mark_match_start(self):
        """With the lock held, once: the match starts (every required seat is ready: the first run / begin). A
        diagnostic `match_start` row (never replayed; tools/snapshot_watch.py freezes the seats' programs on it: the
        match-start snapshot), and the development-world gate says "running" (Service.devgate)."""
        self.diag("match_start", k=self.m.k, wall_s=round(time.monotonic() - self.t0, 3))
        self.devgate("running")

    def devgate(self, state, **extra):
        """With the lock held: the development-world gate (core 0.2.38, devworld_access; core/practice.py). When
        RO_DEVWORLD_GATE names a file (the generator's compose, devworld_access != throughout: a volume shared with the
        seats' practice services only, never the seats), write the world's state there: "running" (the match runs:
        at its start and at every resume), "review" (frozen for a review), "over". No file yet = the preparation. The
        practice service closes ("preparation": from the match start on) or pauses ("preparation_review": while the
        state is running or over) the development world. A write failure is a technical failure (the trial's access
        window would not hold)."""
        path = self.gate_path
        if not path:
            return
        self.gate_seq = getattr(self, "gate_seq", 0) + 1
        try:
            tmp = path + ".tmp"
            with open(tmp, "w") as f:
                json.dump({"state": state, "match_started": True, "seq": self.gate_seq, "k": self.m.k,
                           "ts": round(time.time(), 3), **self.gate_extra(), **extra}, f)
            os.replace(tmp, path)
        except OSError as exc:
            self.errors.append({"where": "devworld_gate", "error": str(exc)[:300]})

    def gate_extra(self) -> dict:
        """Protocol fields of the gate (turn: the seat on turn)."""
        return {}

    def start_rule(self) -> dict:
        """The start window as /spec states it (both protocols). Core 0.2.38: it always opens at the service start
        (the common moment), whether PREPARE_TIMEOUT_S or only START_TIMEOUT_S is set; core 0.3.0: at the start
        barrier t0 when the task has one (TaskSpec timing.t0 = barrier)."""
        barrier = self.t0_mode == "barrier"
        opens = "t0" if barrier else "service_start"
        when = ("at the start barrier t0 (when every seat's session has started: POST /<seat>/session)" if barrier
                else "when the match service starts")
        if len(self.cfg.side_list()) == 1:
            return {"window_s": self.prep_window(), "opens": opens,
                    "rule": f"the window opens {when}; send start (you are ready) before it "
                            "closes, else you lose the match (no_show); start returns at once and the match begins "
                            "right after it"}
        return {"window_s": self.prep_window(), "opens": opens,
                "rule": f"preparation: the window opens {when}, the same moment for every "
                        "seat, and no seat's start moves it; send start (you are ready) before it closes; the match "
                        "begins as soon as every seat has started (start returns at once: learn when play begins "
                        "from status or wait; you may go on developing meanwhile); a side with a seat that has not "
                        "started when it closes loses the match (no_show); if no side starts, the match does not "
                        "count"}

    def absent_sides(self) -> list:
        """With the lock held: the sides (not retired) of which some seat has not started, in seat order."""
        absent = []
        for s in self.cfg.seats:
            side = self.cfg.side_of(s)
            if not self.seats[s].joined and side not in self.retired and side not in absent:
                absent.append(side)
        return absent

    def close_start_window(self, at="start_timeout") -> bool:
        """With the lock held, when the start window ran out in prepare (core rule 5, docs/framework_zh.md §9; core
        0.2.2), or at the collect before the start (Service.no_show_at_collect, core 0.2.7; `at` names the logged
        row). A side is absent if any of its seats has not started. With two or more sides and at least one side
        present, every absent side loses ("no_show", a valid forfeit): with two sides the present side wins; with more,
        an absent side retires if the sport lets the others play on (Match.retire), else the match ends there. If no
        side is present the match is incomplete (a technical failure, no winner). A single-side format (whose window
        opens when the service starts) is a valid loss ("no_show", success 0). True = the match goes on with the
        present sides, who have all started."""
        absent = self.absent_sides()
        present = [x for x in self.active_sides() if x not in absent]
        self.ep.write(at, started={s: st.joined for s, st in self.seats.items()}, absent=absent)
        if not absent:
            return True
        if len(self.cfg.side_list()) == 1:          # a single player (or team) who never started: a valid loss
            self.lose(next(s for s in self.cfg.seats if not self.seats[s].joined), "no_show")
            return False
        if not present:
            self.end("incomplete")
            return False
        for side in absent:
            seat = next(s for s in self.cfg.seats_of(side) if not self.seats[s].joined)
            if not self.lose(seat, "no_show"):
                return False
        return True

    def no_show_at_collect(self) -> bool:
        """With the lock held, at the collect (every player session has ended) before the match has started: the
        session end is a no-show, decided at once instead of when the start window closes (core rule 5,
        docs/framework_zh.md §9; core 0.2.7). Every side that has not started loses ("no_show", a valid forfeit;
        Service.close_start_window): a single side (alone or against a scripted opponent) has a valid loss (success 0);
        with two sides the present side wins; with more, the absent sides retire or the match ends as at the window.
        If no side has started (with two or more sides) nothing is decided here: the match does not count, as before
        (the caller ends it unfinished). True = the match ended; False = not before the start, no side present, or
        present sides would play on (more than two sides; the caller ends the match unfinished)."""
        if self.phase != "prepare" or self.in_play():
            return False
        if len(self.cfg.side_list()) > 1 and not [x for x in self.active_sides() if x not in self.absent_sides()]:
            return False
        return not self.close_start_window("collect_before_start")

    def in_play(self) -> bool:
        """With the lock held: the match has started (play has begun, or every seat has started and play is about to
        begin) and is not over."""
        if self.phase == "prepare":
            return all(st.joined for st in self.seats.values())
        return self.phase != "over"

    def abandon_single(self) -> bool:
        """With the lock held, at the collect (the verifier collects once every player session has ended): a single
        side (alone or against a scripted opponent) whose match has started and is not over loses, "abandoned", a
        valid loss (success 0), in both protocols (core rule 6, docs/framework_zh.md §9; core 0.2.6). Ending the
        session early (the player thinks it is done, gives up, hits the agent time limit or runs out of context) is the
        player's own problem; API and infrastructure failures are Harbor agent errors, rerun, not handled here. Before
        the start the session end is a no-show (Service.no_show_at_collect, core rule 5, core 0.2.7). True = the side
        lost."""
        if len(self.cfg.side_list()) != 1 or not self.in_play():
            return False
        self.lose(self.cfg.seats[0], "abandoned")
        return True

    # ------------------------------------------------------------------ the start barrier
    def init_phases(self):
        """At the service start (Service.__init__, after the header row): the barrier state (t0 now when timing.t0 =
        service_start) and every seat "playing"."""
        self.t0_mode = self.ts.options.get("timing.t0", "service_start")
        self.t0_wait_s = float(self.ts.timing.get("t0_wait_s") or 600.0)
        self.t0_arrivals: dict = {}              # seat -> epoch of its first request
        self.t0_first = None                     # monotonic time of the first arrival
        self.t0_epoch = self.t0_mono = self.t0_source = None
        self.seat_states = {s: {"state": "playing", "why": None, "k": 0} for s in self.cfg.seats}
        self.retire_why: dict = {}               # side -> why it retired
        self.exits: list = []                    # core 0.4.0: [{side, kind: resigned | no_show, step, seat}]
        self.faults: list = []                   # core 0.4.0: the faults the Host observed (final.json faults)
        self.harness_exits: dict = {}            # core 0.4.0: seat -> [steps of its harness exits] (events only)
        self.review_missing: list = []           # core 0.4.0: reviews due and not sent in their window
        self.final_facts: dict = {}              # write_final's validity facts (failure_hint, side_outcome)
        if self.t0_mode != "barrier":
            self.t0_mono = self.t0
            self.t0_epoch = round(time.time() - (time.monotonic() - self.t0), 3)
            self.t0_source = "service_start"
            self.ep.write("t0", epoch=self.t0_epoch, source="service_start", arrivals={})

    def t0_open(self) -> bool:
        """Has the match opened (t0 set)?"""
        return self.t0_mono is not None

    def arrive(self, seat: str) -> None:
        """Any request of `seat` (the HTTP layer calls it before the endpoint; open_session too): the seat's first
        arrival is recorded (a `session` row) and t0 opens when every seat has arrived."""
        if seat in self.t0_arrivals or seat not in self.seats:
            return
        with self.cond:
            if seat in self.t0_arrivals:
                return
            now = round(time.time(), 3)
            self.t0_arrivals[seat] = now
            if self.t0_first is None:
                self.t0_first = time.monotonic()
            self.ep.write("session", seat=seat, epoch=now, k=self.m.k)
            if not self.t0_open() and self.phase != "over" and all(s in self.t0_arrivals for s in self.cfg.seats):
                self.open_t0("barrier", now)         # t0 = the last arrival
            self.cond.notify_all()

    def check_t0_wait(self) -> None:
        """With the lock held, from the service's loop: open t0 with source barrier_timeout once T0_WAIT_S has
        passed since the first arrival."""
        if (not self.t0_open() and self.t0_first is not None and self.phase != "over"
                and time.monotonic() - self.t0_first >= self.t0_wait_s):
            self.open_t0("barrier_timeout")

    def open_t0(self, source: str, epoch: float | None = None):
        """With the lock held: the match opens (t0): a `t0` row, the protocol's preparation deadline (on_t0)."""
        self.t0_mono, self.t0_source = time.monotonic(), source
        self.t0_epoch = epoch if epoch is not None else round(time.time(), 3)
        self.ep.write("t0", epoch=self.t0_epoch, source=source, arrivals=dict(self.t0_arrivals), k=self.m.k)
        self.on_t0()
        self.cond.notify_all()

    def on_t0(self):
        """With the lock held, when the barrier opens: the protocol's preparation deadline (realtime, turn)."""

    def t0_info(self) -> dict:
        """final.json `t0`: {"epoch", "source", "arrivals": {seat: epoch}} (epoch and source None before t0)."""
        return {"epoch": self.t0_epoch, "source": self.t0_source, "arrivals": dict(self.t0_arrivals)}

    def before_t0(self, seat) -> tuple[int, dict] | None:
        """With the lock held: the 409 of start / act / ready before t0, else None."""
        if self.t0_open():
            return None
        return 409, {"error": BEFORE_T0, "phase": "init",
                     "waiting_for": [s for s in self.cfg.seats if s not in self.t0_arrivals]}

    def open_session(self, seat: str, body: dict | None = None) -> tuple[int, dict]:
        """POST /<seat>/session: blocks until t0 (at most SESSION_WAIT_S); see the module text."""
        self.arrive(seat)
        end = time.monotonic() + SESSION_WAIT_S
        with self.cond:
            while not self.t0_open() and self.phase != "over" and time.monotonic() < end:
                self.check_t0_wait()
                self.cond.wait(min(0.5, max(0.01, end - time.monotonic())))
            if not self.t0_open():
                if self.phase == "over":
                    return 409, {"error": "the match is over", "phase": "over", "reason": self.reason, "t0": None}
                return 200, {"phase": "init", "waiting_for": [s for s in self.cfg.seats if s not in self.t0_arrivals],
                             "t0": None, "barrier_wait_s": self.t0_wait_s}
            return 200, {"t0": self.t0_epoch, "source": self.t0_source, "phase": self.phase,
                         "deadlines": self.deadlines_now()}

    def session_rule(self) -> dict:
        """/spec `session` (core 0.3.0)."""
        return {"endpoint": "POST /<seat>/session {}", "t0": self.t0_mode,
                "rule": ("the match opens (t0) when every seat's session has started (your first request of any kind "
                         f"counts), or {self.t0_wait_s:g} s after the first seat's: before t0 start, act and ready "
                         "answer 409; session blocks at most 30 s and answers {phase: init, waiting_for} until t0, "
                         "then {t0, source, phase, deadlines}; the preparation deadline counts from t0"
                         if self.t0_mode == "barrier" else
                         "t0 is the match service start (no start barrier); session answers {t0, source, phase, "
                         "deadlines} at once")}

    # ------------------------------------------------------------------ what final.json says
    def no_session_seats(self) -> list:
        """With the lock held: the seats of a no_show that never opened their session while the start barrier was on
        (FWTEAM 10-20; the coordinator's decision of 10-19, the verifier's no_session): the harness or its container
        never came up, a platform failure. The trial is void (write_final), the seat infra_failure, no side forfeits."""
        if self.reason != "no_show" or self.t0_source not in ("barrier", "barrier_timeout"):
            return []
        if os.environ.get("RO_COLLECT_ENDS_MATCH") == "1":   # Embodied First Exam: Harbor started the agent's container
            return []                                       # with the sim; a seat that never called is a no-show
        return [s for s in self.cfg.seats if s not in self.t0_arrivals and not self.seats[s].joined]

    def set_seat_state(self, seat, state, why=None):
        """With the lock held: a seat's status changed (a `seat_status` row)."""
        cur = self.seat_states.get(seat) or {}
        if cur.get("state") == state and cur.get("why") == why:
            return
        self.seat_states[seat] = {"state": state, "why": why, "k": int(self.m.k)}
        self.diag("seat_status", seat=seat, **self.seat_states[seat])

    def retire_seats(self, side, why):
        """With the lock held: `side` retired (more than two sides)."""
        self.retire_why[side] = why
        for s in self.cfg.seats_of(side):
            self.set_seat_state(s, "retired", why)

    def settle_seats(self, reason, forfeiting=None):
        """With the lock held, at the end of the match (reason set): the final state of every seat still playing."""
        never = set(self.no_session_seats()) if reason == "no_show" else set()
        for s in self.cfg.seats:
            if self.seat_states[s]["state"] != "playing":
                continue
            joined = self.seats[s].joined
            if s in never:                       # never opened its session (barrier on): not the agent's no_show
                self.set_seat_state(s, "infra_failure", "no_session")
            elif reason in ("technical_error", "wall_cap", "aborted"):
                self.set_seat_state(s, "infra_failure", reason)
            elif reason == "resigned" and forfeiting is not None and self.cfg.side_of(s) == self.cfg.side_of(
                    forfeiting):
                self.set_seat_state(s, "retired", "resigned")
            elif reason in ("collected", "incomplete") and s not in self.t0_arrivals and self.match_t0 is None:
                self.set_seat_state(s, "infra_failure", "no_session")
            elif reason in ("collected", "incomplete", "no_show") and not joined:
                self.set_seat_state(s, "timed_out", "no_show")
            elif reason in ("ready_timeout", "clock") and s == forfeiting:
                self.set_seat_state(s, "timed_out", reason)
            elif reason in ("abandoned", "collected"):
                self.set_seat_state(s, "session_ended", reason)
            else:
                self.set_seat_state(s, "finished", reason)

    def seat_status(self) -> dict:
        """final.json seat_status (see the module text)."""
        return {s: dict(v) for s, v in self.seat_states.items()}

    def side_outcome(self, valid: bool | None = None) -> dict:
        """final.json side_outcome ({} before the match is over); `valid`: the trial's validity (write_final's)."""
        if self.phase != "over":
            return {}
        if valid is None:
            valid = bool(self.final_facts.get("valid"))
        sides = self.cfg.side_list()
        if not valid:
            return {d: {"result": "void", "place": None, "why": self.reason} for d in sides}
        o = self.outcome()
        lost = (self.cfg.side_of(self.forfeiting) if self.forfeiting is not None and self.reason in FORFEIT_REASONS
                else None)
        if o.solo:
            return {d: {"result": "solo", "place": None, "why": o.decided_by} for d in sides}
        out, ranking = {}, list(o.ranking or [])
        for d in sides:
            place = ranking.index(d) + 1 if d in ranking else None
            if d in self.retired:
                res, why = "dnf", self.retire_why.get(d)
            elif d == lost:
                res, why = "forfeit", self.reason
            elif o.draw:                         # core 0.5.2: a draw (the fixture allows one)
                res, why, place = "drew", o.decided_by, 1
            elif len(sides) <= 2:
                res, why = ("won" if o.winner == d else "lost"), o.decided_by
            else:
                res, why = "ranked", o.decided_by
            out[d] = {"result": res, "place": place if len(sides) > 1 else None, "why": why}
        return out

    def failure_hint(self, facts: dict | None = None) -> dict | None:
        """final.json failure_hint: the core's own reading {"class", "reason"} (the verifier decides; None while the
        match runs). `facts`: write_final's {"valid", "replay_ok", "meter_error", "proxy_error"}."""
        if self.phase != "over":
            return None
        f = self.final_facts if facts is None else facts
        if self.errors:
            return {"class": "infrastructure", "reason": str(self.errors[0].get("where") or "error")}
        if f.get("proxy_error"):
            return {"class": "external_provider", "reason": "proxy_error"}
        if f.get("meter_error"):
            return {"class": "infrastructure", "reason": "metering"}
        if self.finalized and not f.get("replay_ok"):
            return {"class": "infrastructure", "reason": "replay"}
        if self.reason in ("wall_cap", "aborted"):          # core 0.4.0: platform faults (void, rerun)
            return {"class": "infrastructure", "reason": self.reason}
        if self.no_session_seats():
            return {"class": "infrastructure", "reason": "no_session"}   # never opened a session (decision 10-19)
        if self.reason in FORFEIT_REASONS:
            return {"class": "agent", "reason": self.reason}
        if self.reason in ("collected", "incomplete") and self.match_t0 is None:
            if any(s not in self.t0_arrivals for s in self.cfg.seats):
                return {"class": "infrastructure", "reason": "no_session"}
            return {"class": "agent", "reason": "nobody_started"}
        if self.reason == "collected":
            return {"class": "none", "reason": "unfinished"}
        if self.reason == "technical_error":
            return {"class": "infrastructure", "reason": "technical_error"}
        return {"class": "none", "reason": None}


__all__ = ["PhaseRules", "SESSION_WAIT_S", "T0_SOURCES", "SEAT_STATES", "SIDE_RESULTS", "FAILURE_CLASSES",
           "BEFORE_T0", "FORFEIT_REASONS", "TERMINATION", "EXIT_KINDS"]
