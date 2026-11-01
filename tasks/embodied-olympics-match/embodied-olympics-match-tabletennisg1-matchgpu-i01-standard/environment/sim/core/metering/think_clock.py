"""Wallclock model-turn gate. Oracle exemption must be explicitly enabled by the runner.

Core 0.4.0: no environment reads here (core/taskspec.py is the core's one reader): the seat's player mode, the act rule
(per_response | program) and the per-response wait come as arguments (core/seats.py passes the TaskSpec's)."""
from __future__ import annotations
import json
import threading
import time

USAGE_FILE = "/data/think_usage.json"
RULE_WAIT_S = 1.0               # per_response: how long an act waits for its model response to complete


class MeterError(RuntimeError):
    pass


READ_RETRY_S = 1.0              # a meter file that cannot be read or is invalid is read again for up to this long
READ_RETRY_STEP_S = 0.01        # before it counts (core 0.4.6): one failed read is no lost meter


def _read_once(path):
    """(usage, why): the meter file's object, or {} and why it could not be read."""
    try:
        with open(path) as f:
            value = json.load(f)
    except OSError as e:
        return {}, type(e).__name__
    except ValueError:
        return {}, "unparsable"
    return (value, None) if isinstance(value, dict) else ({}, "not an object")


def read_usage(path=USAGE_FILE, retry_s=0.0):
    """The meter file's object ({} when it cannot be read). With `retry_s` a failed read is retried for that long:
    the proxy replaces the file atomically, but a shared or network file system may still fail one read of a file
    that is being replaced (2026-10-24: one failed read in 62 532 voided a match on a parallel file system)."""
    deadline = time.monotonic() + retry_s
    while True:
        u, why = _read_once(path)
        if why is None or time.monotonic() >= deadline:
            return u
        time.sleep(READ_RETRY_STEP_S)


def _invalid(u: dict) -> str | None:
    """Why the meter's counters cannot be a live session's (None: they can)."""
    counters = ("model_calls_completed", "act_calls_completed", "requests", "in_flight")
    if not isinstance(u.get("epoch"), str) or not u["epoch"]:
        return "no epoch"
    if any(type(u.get(k)) is not int or u[k] < 0 for k in counters):
        return "bad counters"
    if u["requests"] < 1:
        return "no model request yet"
    if u["act_calls_completed"] > u["model_calls_completed"] or u["model_calls_completed"] > u["requests"]:
        return "inconsistent counters"
    return None


class ThinkClock:
    def __init__(self, seconds_per_ktok=0.0, usage_file=USAGE_FILE, mode=None, act_rule=None,
                 rule_wait_s=RULE_WAIT_S, read_retry_s=READ_RETRY_S, **kwargs):
        self.usage_file = usage_file
        self.read_retry_s = float(read_retry_s)
        self.mode = mode or "model"
        self.min_started_at = 0.0
        self.rule_wait_s = float(rule_wait_s)
        if self.mode not in ("model", "oracle", "unmetered"):
            raise ValueError("RCB_PLAYER_MODE must be model, oracle or unmetered")
        # Embodied First Exam: "unmetered" = a model seat whose model calls the harness's own runner records (the
        # sim holds no metering proxy and no credential): no meter here, as for "oracle", under its own name.
        act_rule = act_rule or "per_response"
        if act_rule not in ("per_response", "program"):
            raise ValueError("RCB_ACT_RULE must be per_response or program")
        self.rule = "explicit_oracle" if self.mode == "oracle" else "unmetered" if self.mode == "unmetered" else (
            "program" if act_rule == "program" else "completed_act_calls")
        self._calls_at_decision = 0
        self._epoch = None
        self._last = {}
        self.last_good = {}             # the last reading check_ready accepted (core/seats.validity_fields' fallback)
        self.lock = threading.Lock()

    def check_ready(self):
        if self.mode in ("oracle", "unmetered"):
            return {}
        deadline = time.monotonic() + self.read_retry_s
        while True:                     # a failed or invalid read counts only if it persists for read_retry_s
            u, why = _read_once(self.usage_file)
            why = why or _invalid(u)
            if why is None:
                break
            if time.monotonic() >= deadline:
                raise MeterError(f"model meter is missing, invalid, or has not received a model request ({why})")
            time.sleep(READ_RETRY_STEP_S)
        if self._epoch is not None and u["epoch"] != self._epoch:
            raise MeterError("model meter restarted during this match")
        self._epoch = u["epoch"]
        if u["act_calls_completed"] < self._calls_at_decision:
            raise MeterError("model meter counters moved backwards during this match")
        self.last_good = u
        return u

    def settle(self, max_wait_s=2.0):
        """Drain the response carrying start/ready before discarding its act credits."""
        if self.mode in ("oracle", "unmetered") or self.rule == "program":
            return                                     # program play: no per-response act credits to discard
        deadline = time.monotonic() + max_wait_s
        while self.check_ready()["in_flight"]:
            if time.monotonic() >= deadline:
                raise MeterError("model response did not settle before the match resumed")
            time.sleep(.01)

    def rebase(self):
        """Discard all pre-start/review act credits. Caller first settles model traffic."""
        with self.lock:
            if self.mode in ("oracle", "unmetered"):
                return
            u = self.check_ready()
            if u["in_flight"]:
                raise MeterError("cannot rebase the model meter while responses are in flight")
            self._calls_at_decision = u["act_calls_completed"]
            self._last = {}

    def last_call(self):
        return dict(self._last)

    def decided_by_model(self):
        with self.lock:
            if self.mode in ("oracle", "unmetered"):
                self._last = {self.mode: True}
                return True
            if self.rule == "program":
                # Program play: the agent's own program may act; a live, metered model session is still required.
                u = self.check_ready()
                self._last = {"program": True, "act_calls_completed": u["act_calls_completed"],
                              "model_calls_completed": u["model_calls_completed"], "epoch": u["epoch"]}
                return True
            deadline = time.monotonic() + self.rule_wait_s
            while True:
                u = self.check_ready()
                done = u["act_calls_completed"]
                if done > self._calls_at_decision and u.get("last_act_started_at", 0) >= self.min_started_at:
                    self._calls_at_decision = done
                    self._last = {"act_calls_completed": done, "model_calls_completed": u["model_calls_completed"],
                                  "response_seq": u.get("last_act_response_seq"),
                                  "epoch": u["epoch"], "last_completed_at": u.get("last_act_call_at"),
                                  "request_started_at": u.get("last_act_started_at")}
                    return True
                if not u["in_flight"] or time.monotonic() >= deadline:
                    return False
                time.sleep(.01)

    def begin_segment(self, started_at):
        """Discard frozen requests, including responses still in flight at the barrier."""
        with self.lock:
            self.min_started_at = started_at
            if self.mode not in ("oracle", "unmetered"):
                self._calls_at_decision = self.check_ready()["act_calls_completed"]
            self._last = {}
