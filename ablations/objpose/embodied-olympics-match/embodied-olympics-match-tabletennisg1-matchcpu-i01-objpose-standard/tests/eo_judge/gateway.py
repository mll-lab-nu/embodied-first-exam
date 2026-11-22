"""Model-call errors of one seat, attributed by cause, and the time they cost it (fw_pattern_1020.md principle 6, D2;
the brief of IMPL-JUDGE 10-20; the lead's decision 10-21, FWSPEC-4 ③).

Model access rule (integrity/model_access_lost@1, decided 10-21): a model-service failure is judged only by the time a
seat lost to it, never by how many errors there were. A seat's lost time is the union of the spans of its failed model
calls (each from its start to the start of the seat's next call; the gateway's own 429 waits too: model_access) over
the service-side causes, split by cause: the gateway's (platform: gateway_s), the provider's (external: provider_s),
undetermined (unknown_s). Both the lost time and the threshold count the whole session, preparation and match (Chi
10-21): the match is void when a seat lost more than max(min_s, match_fraction x the session's duration) (the TaskSpec's
integrity.tolerance.model_access_lost; default max(120 s, 5 %); the duration: the actual one from the start of the
preparation (t0) to the match end for the verdict, the Task's worst case (preparation + match: termination.wall_bound_s,
else the safety cap wall_cap_s) for the Runner's abort at a certain breach). E.g. FWTEST2 r6: preparation 6808 s,
match ~2400 s, lost 279 s: threshold ~461 s, valid.
The fault is of the class whose own lost time is over the threshold (gateway: platform, provider: external, else
undetermined); when only the causes together are over it, undetermined (mixed causes). An error that recovers at once
costs only its own call; errors counted without time lost never void. The old separate gateway (30 s) and provider
(120 s) thresholds and the interim error-count rule below are gone as verdict rules.

Cause of a failed model call (one record of the gateway log, think_calls_<seat>.jsonl):

  agent     the request itself was wrong (HTTP 400 / 413 / 422), the seat's own budget refused it, the gateway
            refused it by policy, or the seat's own client went away while the answer streamed (BrokenPipe /
            ConnectionAborted on the downstream side); never voids a match, recorded only
  platform  the platform's account or routing failed: 401 / 403 (credentials), 402 (billing), 404 (no such route or
            deployment), 429 (the platform account's rate limit, also the gateway's own 429 retries, and a call the
            gateway moved between deployments because they were at their rate limit), credentials missing in the
            gateway, a 400 / 404 after the gateway moved the call to another deployment (the move caused it)
  external  the model service failed: 5xx, a stream that ended without completing, an upstream connection error
  undetermined  anything the record cannot place (e.g. a connection reset mid-stream: either side)

The lost-time arithmetic is the one of core/metering/api_errors.py (2026-10-17; same definitions: an error is
recovered when a later model call of the seat completed; the time lost is the union of each failed call from its start
to the next call's start and the gateway's own 429 waits: outage_summary), applied by the judge to the sealed gateway
log, not to the match service's snapshot of it, and by the Runner to the live log (framework/run/monitor.py). Only
service-side errors (platform, external, undetermined) count, those of the preparation included, and only those of
calls that started before the match ended: a call that starts after the end cannot change the result (reported in the
diagnostics). The interim
error-count rule of 2026-10-17 (an unrecovered error, more than 50 recovered errors, or more than 20 % of the session)
stays readable here (INTERIM_RULE, outage_summary's `reason`) for comparisons with old verdicts only.

The judge keeps its own copy of the arithmetic (a judge rule is frozen with the Task, it must not change when the
metering proxy's file does); framework/judge/tests/test_judge.py checks that both agree on the same calls.
"""
from __future__ import annotations

import bisect

AGENT_STATUS = {400: "bad_request", 413: "request_too_large", 422: "unprocessable_request"}
PLATFORM_STATUS = {401: "auth", 403: "auth", 402: "account_billing", 404: "route_not_found",
                   429: "account_rate_limit"}
DOWNSTREAM_ERRORS = {"BrokenPipeError", "ConnectionAbortedError"}       # writing to the seat's own client failed
AMBIGUOUS_ERRORS = {"ConnectionResetError"}                             # mid-stream: either side may have reset
UPSTREAM_ERRORS = {"ConnectionResetError", "TimeoutError", "timeout", "IncompleteRead", "RemoteDisconnected",
                   "URLError", "ProtocolError", "ChunkedEncodingError", "ReadTimeout", "SSLError", "OSError",
                   "HTTPException", "ConnectionRefusedError"}
SERVICE_CLASSES = ("platform", "external", "undetermined")

# the thresholds of core/metering/api_errors.py (2026-10-17)
MAX_TRANSIENT_API_ERRORS = 50
MAX_API_WAIT_FRACTION = 0.20
MIN_API_WAIT_S = 60.0
INTERIM_RULE = "api_errors/unrecovered_or_cap@2026-10-17"

MODEL_ACCESS_RULE = "integrity/model_access_lost@1"           # decided 10-21 (FWSPEC-4 ③)
MODEL_ACCESS_DEFAULT = {"min_s": 120.0, "match_fraction": 0.05}   # a TaskSpec without the tolerance gets these
CAUSE_KEYS = {"platform": "gateway_s", "external": "provider_s", "undetermined": "unknown_s"}


def cause(rec: dict) -> tuple[str, str] | None:
    """(class, code) of a failed call; None for a successful call or a record that is not a model call."""
    if rec.get("blocked"):                   # the gateway refused the request before it reached a model
        why = str(rec.get("blocked"))
        return ("agent", "budget") if "budget" in why else ("agent", "gateway_refused")
    if not rec.get("model_call"):
        return None
    status, err = rec.get("status"), rec.get("error")
    if status == 200 and rec.get("completed") is True:
        return None
    if rec.get("budget_refused"):
        return "agent", "budget"
    name = err.split("(")[0].split(":")[0].strip() if isinstance(err, str) else None
    if name in DOWNSTREAM_ERRORS and status in (None, 200):
        return "agent", "client_disconnect"         # the answer was streaming to the seat when its client left
    if name in AMBIGUOUS_ERRORS and status in (None, 200):
        return "undetermined", "connection_reset"    # mid-stream: the upstream or the seat's client reset it
    if err == "missing_upstream_credentials":
        return "platform", "credentials"
    moves = (rec.get("azure_failovers") or rec.get("failovers") or [])
    if moves:                                        # the gateway moved this call between deployments
        why = " ".join(str(m.get("reason", "")) for m in moves if isinstance(m, dict)).lower()
        if "rate_limit" in why or "429" in why:
            return "platform", "account_rate_limit"  # the platform's deployments were at their rate limit
        if isinstance(status, int) and (status in AGENT_STATUS or status == 404):
            return "platform", "failover_error"      # the new deployment refused what the old one held
    if isinstance(status, int) and not isinstance(status, bool):
        if status in AGENT_STATUS:
            return "agent", AGENT_STATUS[status]
        if status in PLATFORM_STATUS:
            return "platform", PLATFORM_STATUS[status]
        if 500 <= status < 600:
            return "external", f"upstream_{status}"
        if status == 200:
            return "external", "stream_error"
    if name in UPSTREAM_ERRORS:
        return "external", "upstream_connection"
    return "undetermined", "unknown_failure"


def _num(v, default):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else default


def _span(rec: dict) -> tuple[float, float]:
    end = _num(rec.get("t1"), _num(rec.get("t0"), 0.0))
    return min(_num(rec.get("t0"), end), end), end


def _retries(rec: dict) -> list:
    return [r for r in (rec.get("retries") or []) if isinstance(r, dict)] if isinstance(rec.get("retries"), list) \
        else []


def outage_summary(records: list, keep: set, end: float | None = None) -> dict:
    """The interim rule over one seat's records: the errors of the cause classes in `keep` (the gateway's own 429
    retries count as platform errors) of calls that started at or before `end` (None: all), recovered by any later
    successful call. Same numbers as api_errors.SeatApiErrors.summary when keep has every class and end is None."""
    calls = [r for r in records if isinstance(r, dict) and r.get("model_call")]
    starts, last_ok, first_t0, last_t1 = [], None, None, None
    errors, failed_spans, wait_spans = [], [], []
    for rec in calls:
        start, stop = _span(rec)
        inside = end is None or start <= end
        if inside:
            bisect.insort(starts, start)
            first_t0 = start if first_t0 is None else min(first_t0, start)
            last_t1 = stop if last_t1 is None else max(last_t1, stop)
        c = cause(rec)
        if c is None:
            last_ok = stop if last_ok is None else max(last_ok, stop)
        elif c[0] in keep and inside:
            errors.append(stop)
            failed_spans.append((start, stop))
        if "platform" in keep:
            for r in _retries(rec):
                at = _num(r.get("at"), stop)
                if end is None or at <= end:
                    errors.append(at)
                    wait = _num(r.get("wait_s"), 0.0)
                    if wait > 0:
                        wait_spans.append((at, at + wait))
    transient = sum(1 for t in errors if last_ok is not None and last_ok > t)
    unrecovered = len(errors) - transient
    spans = list(wait_spans)
    for start, stop in failed_spans:
        i = bisect.bisect_left(starts, stop)
        spans.append((start, starts[i] if i < len(starts) else stop))
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
    session = (last_t1 - first_t0) if first_t0 is not None else 0.0
    reason = None
    if unrecovered > 0:
        reason = "unrecovered"
    elif transient > MAX_TRANSIENT_API_ERRORS:
        reason = "transient_cap"
    elif lost >= MIN_API_WAIT_S and lost > MAX_API_WAIT_FRACTION * session:
        reason = "wait_cap"
    return {"errors": len(errors), "transient": transient, "unrecovered": unrecovered, "wait_s": round(lost, 1),
            "session_s": round(session, 1), "failure": reason is not None, "reason": reason}


def seat_report(records: list, usage: dict | None, match_end: float | None) -> dict:
    """Everything the judge needs about one seat's model calls: counts by cause, the errors after the match end, the
    time lost to failures (model_access: in all and by cause), the failures the gateway counted but never logged."""
    calls = [r for r in records if isinstance(r, dict) and r.get("model_call")]
    ok = sum(1 for r in calls if cause(r) is None)
    by_cause: dict = {}
    after_end: dict = {}
    retries_logged = 0
    for r in records:
        if not isinstance(r, dict):
            continue
        rt = _retries(r) if r.get("model_call") else []
        retries_logged += len(rt)
        start = _span(r)[0]
        late = match_end is not None and start > match_end
        for _ in rt:
            key = "platform/account_rate_limit_retry"
            tgt = after_end if late else by_cause
            tgt[key] = tgt.get(key, 0) + 1
        c = cause(r)
        if c is None:
            continue
        key = f"{c[0]}/{c[1]}"
        tgt = after_end if late else by_cause
        tgt[key] = tgt.get(key, 0) + 1
    failed_logged = sum(1 for r in calls if cause(r) is not None)
    unlogged = 0
    if isinstance(usage, dict):
        unlogged = (max(0, int(usage.get("failed_model_calls", 0) or 0) - failed_logged)
                    + max(0, int(usage.get("rate_limit_retries", 0) or 0) - retries_logged))
    union = outage_summary(records, set(SERVICE_CLASSES), match_end)
    return {"calls": len(calls), "completed": ok, "errors_by_cause": dict(sorted(by_cause.items())),
            "after_match_end": dict(sorted(after_end.items())), "unlogged_failures": unlogged,
            "rule": MODEL_ACCESS_RULE, "access": model_access(records, match_end),
            "errors": {k: union[k] for k in ("errors", "transient", "unrecovered")},
            "routes": sorted({str(r.get("route")) for r in calls if r.get("route")}),
            "deployments": sorted({str(r.get("azure_deployment")) for r in calls if r.get("azure_deployment")})}


def model_access(records: list, end: float | None = None) -> dict:
    """The time one seat lost to model-service failures (run.schema delivered.model_access): {lost_s: the union over
    every service-side cause, gateway_s: the gateway's own (platform), provider_s: the provider's (external),
    unknown_s: undetermined}, of the calls that started at or before `end` (None: every call so far)."""
    out = {"lost_s": outage_summary(records, set(SERVICE_CLASSES), end)["wait_s"]}
    for cls, key in CAUSE_KEYS.items():
        out[key] = outage_summary(records, {cls}, end)["wait_s"]
    return out


def access_threshold(tolerance: dict | None, session_s: float | None) -> float:
    """max(min_s, match_fraction x session_s): the most model-access time a seat may lose (TaskSpec
    integrity.tolerance.model_access_lost, else MODEL_ACCESS_DEFAULT). session_s: the session's duration, preparation
    and match (Chi 10-21; the actual one for the verdict, the Task's worst case for an abort at a certain breach);
    None or 0: min_s alone. The key keeps its name match_fraction (TaskSpec schema)."""
    t = tolerance if isinstance(tolerance, dict) else MODEL_ACCESS_DEFAULT
    min_s = float(t.get("min_s", MODEL_ACCESS_DEFAULT["min_s"]))
    frac = float(t.get("match_fraction", MODEL_ACCESS_DEFAULT["match_fraction"]))
    return round(max(min_s, frac * max(0.0, float(session_s or 0.0))), 1)


def access_faults(access: dict, threshold: float) -> list:
    """[class]: the fault classes of a seat's lost model access over `threshold`: each cause whose own lost time is
    over it (the gateway: platform, the provider: external, undetermined), else, when only the causes together are,
    undetermined (mixed causes); [] when the seat lost no more than the threshold."""
    if not access or access.get("lost_s", 0) <= threshold:
        return []
    own = [cls for cls, key in CAUSE_KEYS.items() if access.get(key, 0) > threshold]
    return own or ["undetermined"]
