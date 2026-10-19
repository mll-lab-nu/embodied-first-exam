"""Model-API errors of one seat, classified for the trial's validity (docs/EAI_STANDARD_REALTIME_1_0.md, "Validity").

The metering proxy (think_proxy.py) logs every request of a seat to its think_calls file (think_calls.jsonl, or
think_calls_<seat>.jsonl in a duel) and counts failed model calls and in-proxy 429 retries in the usage file. A model-API
error is a model call that did not complete successfully (an HTTP error such as 429 or 5xx, a stream error, a broken
connection) or one 429 retry inside the proxy. Each error is
  * transient   when a later model call of the same seat completed successfully (the harness retried and got past it);
  * unrecovered when no model call of that seat completed successfully after it (the agent stopped, or the session
                ended, because of the model API, e.g. an account rate limit it could not get past).
A seat's model API failed the trial (`api_failure`, the trial's proxy_error) only if it had an unrecovered error or more
than MAX_TRANSIENT_API_ERRORS transient errors in the match. Transient errors below the limit are only counted and
reported. Azure deployment switches (azure_failovers) are not errors: the request completed on another replica.

The same file is copied into every Olympiad task's sim (scripts/olympiad/generate.py) and used by
scripts/olympiad/regrade_transient.py. Standard library only.
"""
from __future__ import annotations

import json
import os
import threading

MAX_TRANSIENT_API_ERRORS = 5


def calls_file_for(usage_file: str) -> str:
    """The think_calls file the proxy writes next to `usage_file` (think_proxy.py's own rule)."""
    base = os.path.basename(usage_file)
    if "think_usage" in base:
        return usage_file.replace("think_usage", "think_calls").rsplit(".json", 1)[0] + ".jsonl"
    return os.path.join(os.path.dirname(usage_file) or ".", "think_calls.jsonl")


class SeatApiErrors:
    """Incremental classifier of one seat's think_calls records (reads only the lines added since the last call)."""

    def __init__(self, calls_file: str | None = None):
        self.calls_file = calls_file
        self.lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        self.offset = 0
        self.error_times: list[float] = []      # when each error happened (a failed call's end, a retry's time)
        self.last_ok = None                      # end time of the latest successfully completed model call
        self.logged_failed = 0                   # failed model calls in the log
        self.logged_retries = 0                  # in-proxy 429 retries in the log
        self.model_calls = 0

    def add(self, rec) -> None:
        if not isinstance(rec, dict) or not rec.get("model_call"):
            return
        self.model_calls += 1
        end = _num(rec.get("t1"), _num(rec.get("t0"), 0.0))
        retries = rec.get("retries") if isinstance(rec.get("retries"), list) else []
        for r in retries:
            self.error_times.append(_num(r.get("at") if isinstance(r, dict) else None, end))
        self.logged_retries += len(retries)
        if rec.get("status") == 200 and rec.get("completed") is True:
            self.last_ok = end if self.last_ok is None else max(self.last_ok, end)
        else:
            self.logged_failed += 1
            self.error_times.append(end)

    def read(self) -> None:
        if not self.calls_file:
            return
        try:
            with open(self.calls_file, "rb") as f:
                f.seek(0, os.SEEK_END)
                if f.tell() < self.offset:              # the file was replaced: start again
                    self.reset()
                f.seek(self.offset)
                data = f.read()
        except OSError:
            return
        end = data.rfind(b"\n")
        if end < 0:
            return
        self.offset += end + 1                          # only complete lines; a line being written waits
        for line in data[:end].splitlines():
            if line.strip():
                try:
                    self.add(json.loads(line))
                except ValueError:
                    pass                                # not a record (think_proxy.py writes whole lines)

    def summary(self, usage: dict | None = None) -> dict:
        transient = sum(1 for t in self.error_times if self.last_ok is not None and self.last_ok > t)
        unrecovered = len(self.error_times) - transient
        missing = 0
        if isinstance(usage, dict):                     # counted by the proxy but not (yet) in the log: not recovered
            missing = (max(0, int(usage.get("failed_model_calls", 0) or 0) - self.logged_failed)
                       + max(0, int(usage.get("rate_limit_retries", 0) or 0) - self.logged_retries))
        unrecovered += missing
        return {"transient_api_errors": transient, "unrecovered_api_errors": unrecovered,
                "api_failure": bool(unrecovered > 0 or transient > MAX_TRANSIENT_API_ERRORS),
                "model_calls_logged": self.model_calls, "unlogged_api_errors": missing}


def _num(v, default):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else default


def classify_calls(records, usage: dict | None = None) -> dict:
    """Classify a list of think_calls records (dicts). Returns transient_api_errors, unrecovered_api_errors and
    api_failure (unrecovered > 0 or transient > MAX_TRANSIENT_API_ERRORS)."""
    s = SeatApiErrors()
    for rec in records:
        s.add(rec)
    return s.summary(usage)


def classify_file(calls_file: str, usage: dict | None = None) -> dict:
    s = SeatApiErrors(calls_file)
    s.read()
    return s.summary(usage)


_SEATS: dict[str, SeatApiErrors] = {}
_SEATS_LOCK = threading.Lock()


def seat_api_errors(usage_file: str, usage: dict | None = None) -> dict:
    """The classification of the seat metered in `usage_file` (its think_calls file read incrementally), for a server's
    final record. `usage`: that seat's usage counters, already read."""
    path = calls_file_for(usage_file)
    with _SEATS_LOCK:
        s = _SEATS.setdefault(path, SeatApiErrors(path))
    with s.lock:
        s.read()
        return s.summary(usage)
