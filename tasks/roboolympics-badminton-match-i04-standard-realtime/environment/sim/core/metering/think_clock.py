"""Wallclock model-turn gate. Oracle exemption must be explicitly enabled by the runner."""
from __future__ import annotations
import json
import os
import threading
import time

USAGE_FILE = os.environ.get("THINK_USAGE_FILE", "/data/think_usage.json")


class MeterError(RuntimeError):
    pass


def read_usage(path=USAGE_FILE):
    try:
        with open(path) as f:
            value = json.load(f)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


class ThinkClock:
    def __init__(self, seconds_per_ktok=0.0, usage_file=USAGE_FILE, **kwargs):
        self.usage_file = usage_file
        self.mode = kwargs.get("mode") or os.environ.get("RCB_PLAYER_MODE", "model")
        self.min_started_at = 0.0
        if self.mode not in ("model", "oracle"):
            raise ValueError("RCB_PLAYER_MODE must be model or oracle")
        act_rule = os.environ.get("RCB_ACT_RULE", "per_response")
        if act_rule not in ("per_response", "program"):
            raise ValueError("RCB_ACT_RULE must be per_response or program")
        self.rule = "explicit_oracle" if self.mode == "oracle" else (
            "program" if act_rule == "program" else "completed_act_calls")
        self._calls_at_decision = 0
        self._epoch = None
        self._last = {}
        self.lock = threading.Lock()

    def check_ready(self):
        if self.mode == "oracle":
            return {}
        u = read_usage(self.usage_file)
        counters = ("model_calls_completed", "act_calls_completed", "requests", "in_flight")
        if (not isinstance(u.get("epoch"), str) or not u["epoch"]
                or any(type(u.get(k)) is not int or u[k] < 0 for k in counters)
                or u["requests"] < 1 or u["act_calls_completed"] > u["model_calls_completed"]
                or u["model_calls_completed"] > u["requests"]):
            raise MeterError("model meter is missing, invalid, or has not received a model request")
        if self._epoch is not None and u["epoch"] != self._epoch:
            raise MeterError("model meter restarted during this match")
        self._epoch = u["epoch"]
        if u["act_calls_completed"] < self._calls_at_decision:
            raise MeterError("model meter counters moved backwards during this match")
        return u

    def settle(self, max_wait_s=2.0):
        """Drain the response carrying start/ready before discarding its act credits."""
        if self.mode == "oracle" or self.rule == "program":
            return                                     # program play: no per-response act credits to discard
        deadline = time.monotonic() + max_wait_s
        while self.check_ready()["in_flight"]:
            if time.monotonic() >= deadline:
                raise MeterError("model response did not settle before the match resumed")
            time.sleep(.01)

    def rebase(self):
        """Discard all pre-start/review act credits. Caller first settles model traffic."""
        with self.lock:
            if self.mode == "oracle":
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
            if self.mode == "oracle":
                self._last = {"oracle": True}
                return True
            if self.rule == "program":
                # Program play: the agent's own program may act; a live, metered model session is still required.
                u = self.check_ready()
                self._last = {"program": True, "act_calls_completed": u["act_calls_completed"],
                              "model_calls_completed": u["model_calls_completed"], "epoch": u["epoch"]}
                return True
            deadline = time.monotonic() + float(os.environ.get("WALLCLOCK_RULE_WAIT_S", "1"))
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
            if self.mode != "oracle":
                self._calls_at_decision = self.check_ready()["act_calls_completed"]
            self._last = {}
