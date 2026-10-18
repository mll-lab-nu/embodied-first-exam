"""Model-API errors of one seat, classified for the trial's validity (docs/EAI_STANDARD_REALTIME_1_0.md, "Validity").

The metering proxy (think_proxy.py) logs every request of a seat to its think_calls file (think_calls.jsonl, or
think_calls_<seat>.jsonl in a duel) and counts failed model calls and in-proxy 429 retries in the usage file. A model-API
error is a model call that did not complete successfully (an HTTP error such as 429 or 5xx, a stream error, a broken
connection) or one 429 retry inside the proxy. Each error is
  * transient   when a later model call of the same seat completed successfully (the harness retried and got past it);
  * unrecovered when no model call of that seat completed successfully after it (the agent got no answer after all
                retries: it stopped, or the session ended, because of the model API, e.g. an account rate limit it
                could not get past). A failure the proxy counted but did not log is unrecovered too.
A seat's model API failed the trial (`api_failure`, the trial's proxy_error) if it had an unrecovered error (rule of
2026-10-17; before, also more than 5 transient errors did). Transient errors are only recorded: their count, the
in-proxy 429 retries (`api_retries`) and the time they cost (`api_wait_s`). Only a pathological amount of them is a
technical failure too (the sanity cap, `api_failure_reason` "transient_cap" / "wait_cap"):
  * more than MAX_TRANSIENT_API_ERRORS transient errors, or
  * more than MAX_API_WAIT_FRACTION of the seat's model session (first call start .. last call end) lost to errors,
    once that loss is at least MIN_API_WAIT_S.
The time lost (`api_wait_s`) is the union of the failed calls (start to the next model call's start: the call itself and
the harness's back-off before its retry) and the proxy's own 429 waits. Azure deployment switches (azure_failovers) are
not errors: the request completed on another replica.

The same file is copied into every Olympiad task's sim (scripts/olympiad/generate.py) and used by
scripts/olympiad/regrade_transient.py. Standard library only.
"""
from __future__ import annotations

import bisect
import json
import os
import threading

# Sanity cap on recovered errors (2026-10-17). Our harnesses retry a model request or a broken stream up to 40
# times, so one call that got through on its last reconnect already makes 40 transient errors; the cap sits above
# that, so a single hard-won call never voids a trial. Our healthy long Azure sessions see a few drops in 60-150 calls (STUNTCAR Big Air
# L3, 2026-10-17: 6 stream drops in 66 calls, 15 s lost in 937 s); 50 recovered errors in one seat means the provider
# failed on the order of every second call or worse, and the match measures the API rather than the model.
MAX_TRANSIENT_API_ERRORS = 50
# Time cap: wall-clock play keeps running while the harness reconnects, so time lost to the API is time the agent did
# not have. One fifth of the session is far above what recovered drops cost in practice (about 1-2%, see above) and
# below the point where the agent's play is no longer comparable with a clean trial. The floor keeps one slow reconnect
# in a short session (e.g. a 40 s timeout in a 3-minute game) from tripping the fraction on its own.
MAX_API_WAIT_FRACTION = 0.20
MIN_API_WAIT_S = 60.0


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
        self.starts: list[float] = []            # start of every model call (sorted)
        self.first_t0 = self.last_t1 = None      # the seat's model session
        self.failed_spans: list[tuple[float, float]] = []   # (start, end) of each failed model call
        self.wait_spans: list[tuple[float, float]] = []     # the proxy's own 429 waits

    def add(self, rec) -> None:
        if not isinstance(rec, dict) or not rec.get("model_call"):
            return
        self.model_calls += 1
        end = _num(rec.get("t1"), _num(rec.get("t0"), 0.0))
        start = min(_num(rec.get("t0"), end), end)
        bisect.insort(self.starts, start)
        self.first_t0 = start if self.first_t0 is None else min(self.first_t0, start)
        self.last_t1 = end if self.last_t1 is None else max(self.last_t1, end)
        retries = rec.get("retries") if isinstance(rec.get("retries"), list) else []
        for r in retries:
            at = _num(r.get("at") if isinstance(r, dict) else None, end)
            self.error_times.append(at)
            wait = _num(r.get("wait_s") if isinstance(r, dict) else None, 0.0)
            if wait > 0:
                self.wait_spans.append((at, at + wait))
        self.logged_retries += len(retries)
        if rec.get("status") == 200 and rec.get("completed") is True:
            self.last_ok = end if self.last_ok is None else max(self.last_ok, end)
        else:
            self.logged_failed += 1
            self.error_times.append(end)
            self.failed_spans.append((start, end))

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

    def wait_s(self) -> float:
        """Wall time lost to model-API errors: each failed call from its start to the next model call's start (the
        harness's back-off and reconnect included; to its own end if none followed) and the proxy's 429 waits, with
        overlaps counted once."""
        spans = list(self.wait_spans)
        for start, end in self.failed_spans:
            i = bisect.bisect_left(self.starts, end)
            spans.append((start, self.starts[i] if i < len(self.starts) else end))
        lost, cur = 0.0, None
        for a, b in sorted(spans):
            if cur is None or a > cur[1]:
                if cur is not None:
                    lost += cur[1] - cur[0]
                cur = [a, b]
            else:
                cur[1] = max(cur[1], b)
        if cur is not None:
            lost += cur[1] - cur[0]
        return lost

    def summary(self, usage: dict | None = None) -> dict:
        transient = sum(1 for t in self.error_times if self.last_ok is not None and self.last_ok > t)
        unrecovered = len(self.error_times) - transient
        missing = 0
        if isinstance(usage, dict):                     # counted by the proxy but not (yet) in the log: not recovered
            missing = (max(0, int(usage.get("failed_model_calls", 0) or 0) - self.logged_failed)
                       + max(0, int(usage.get("rate_limit_retries", 0) or 0) - self.logged_retries))
        unrecovered += missing
        session = (self.last_t1 - self.first_t0) if self.model_calls else 0.0
        lost = self.wait_s()
        reason = None
        if unrecovered > 0:
            reason = "unrecovered"
        elif transient > MAX_TRANSIENT_API_ERRORS:
            reason = "transient_cap"
        elif lost >= MIN_API_WAIT_S and lost > MAX_API_WAIT_FRACTION * session:
            reason = "wait_cap"
        return {"transient_api_errors": transient, "unrecovered_api_errors": unrecovered,
                "api_failure": reason is not None, "api_failure_reason": reason,
                "api_retries": self.logged_retries, "api_wait_s": round(lost, 1), "api_session_s": round(session, 1),
                "model_calls_logged": self.model_calls, "unlogged_api_errors": missing}


def _num(v, default):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else default


def classify_calls(records, usage: dict | None = None) -> dict:
    """Classify a list of think_calls records (dicts). Returns transient_api_errors, unrecovered_api_errors,
    api_retries, api_wait_s and api_failure (an unrecovered error, or above the sanity cap; api_failure_reason says
    which)."""
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
