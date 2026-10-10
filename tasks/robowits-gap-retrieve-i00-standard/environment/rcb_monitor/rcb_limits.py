#!/usr/bin/env python3
"""Resource limits (docs/PROTOCOL.md §2.10): the sustained-violation rule, shared by the monitor sidecar (monitor.py) and
the verifier step, and the verifier step itself.

Copies of this file live in every task (environment/rcb_monitor/ for the monitor, tests/ for the verifier), byte-identical
to scripts/rcb_monitor/rcb_limits.py (ci_checks/check-monitor.py). Python 3.8+, standard library only: it runs inside
benchmark verifier images.

    python3 /tests/rcb_limits.py verify      # test.sh runs it on exit (trap), after the grader

The verifier step reads the monitor's sealed record (/var/rcb-monitor/, collected from the rcb_monitor sidecar, a
channel the agent cannot write), recomputes every violation from the raw samples with its own copy of the limits
(/tests/rcb_limits.json), and adds to /logs/verifier/reward.json:
  always:   resource_enforced, limits_violation_observed, resource_monitor_missing, peak_gpu_memory_gb, peak_memory_gb,
            peak_processes, peak_disk_gb, resource_emergency_kills; over_<metric>=1 for every violation
  enforced (the record's mode, RCB_LIMITS_ENFORCE=1) and violated: resource_limit_exceeded=1, success=0 (reward.txt 0),
            success_before_limits = the grader's success
  enforced and no usable record: infra_error=1 (not a result). Not enforced (the default): a missing or unusable
            record is only reported (resource_monitor_missing=1); the grader's verdict stands.
  RCB_LIMITS_ENFORCE neither 0/1/true/false: infra_error=1, resource_switch_error=1 (nobody knows what was asked for)
A violation is a limit exceeded for sustain_sec within window_sec (disk: two measurements in a row), or a kernel OOM kill
in the scope. The monitor's emergency kills (host protection) are counted, never violations by themselves.
The reasons, in words, go to /logs/verifier/resource_limits.json. If this step itself fails, it says so in reward.json
(resource_step_error=1, resource_monitor_missing=1; infra_error=1 when the switch asks for enforcement).
"""
import json
import os
import sys

FORMAT = "rcb-monitor/1"
RECORD = os.environ.get("RCB_MONITOR_RECORD", "/var/rcb-monitor")
METRICS = ("gpu_memory_gb", "memory_gb", "processes", "disk_gb")
LIMIT_KEY = {"gpu_memory_gb": "max_gpu_memory_gb", "memory_gb": "max_memory_gb", "processes": "max_processes",
             "disk_gb": "max_disk_gb"}
MAX_GAP_FRACTION = 0.10      # more of the agent phase than this unobserved: the record is not usable


def parse_switch(value):
    """RCB_LIMITS_ENFORCE -> (1 or 0, None), or (0, why) for a value that is neither on nor off (never a silent off)."""
    s = str("" if value is None else value).strip().lower()
    if s in ("", "0", "false"):
        return 0, None
    if s in ("1", "true"):
        return 1, None
    return 0, f"RCB_LIMITS_ENFORCE={value!r} is not one of 0, 1, true, false"


def sustained(series, limit, sustain_sec, window_sec, tick_sec):
    """First time a sustained violation is confirmed, or None.

    series: [(t, value)] in time order (value None = not measured: never over). Each sample stands for the time to the
    next one (the last for none), at most 3 ticks (a gap in the record never counts against the agent). A violation is confirmed at the
    first moment when the time over `limit` within the last `window_sec` reaches `sustain_sec` (so going under for a
    moment does not reset it)."""
    if limit is None or limit <= 0:
        return None
    iv = []                                         # (start, end) of the time over the limit
    for i, (t, v) in enumerate(series):
        if i + 1 == len(series):
            break                                   # the last sample has not lasted yet
        d = max(0.0, min(series[i + 1][0] - t, 3 * tick_sec))
        if v is not None and v > limit and d > 0:
            if iv and abs(iv[-1][1] - t) < 1e-9:
                iv[-1] = (iv[-1][0], t + d)
            else:
                iv.append((t, t + d))
    if not iv:
        return None
    # the over-time in a window (e - W, e] only grows while e moves through an interval: check each interval's end,
    # and inside the first one that reaches it, bisect for the exact moment
    def over_in(e):
        """Over-time inside (e - window, e]."""
        s = e - window_sec
        tot = 0.0
        for a, b in iv:
            if b <= s:
                continue
            if a >= e:
                break
            tot += min(b, e) - max(a, s)
        return tot

    for a, b in iv:
        if over_in(b) + 1e-9 >= sustain_sec:
            # bisect for the first moment in [a, b] at which it is reached
            x, y = a, b
            for _ in range(40):
                m = (x + y) / 2
                if over_in(m) + 1e-9 >= sustain_sec:
                    y = m
                else:
                    x = m
            return y
    return None


def consecutive(series, limit, n=2):
    """First time `n` consecutive measured samples are over `limit` (disk: measured once a minute), or None."""
    if limit is None or limit <= 0:
        return None
    run = 0
    for t, v in series:
        if v is None:
            continue
        run = run + 1 if v > limit else 0
        if run >= n:
            return t
    return None


def violations(samples, limits, events=()):
    """Every violation in a record: [{metric, limit, at, peak}] (empty: none). samples: the record's sample dicts.
    A limit exceeded for sustain_sec within window_sec (disk: two measurements in a row), or a kernel OOM kill in the
    scope. The monitor's own `emergency_kill` events protect the host and are not violations (PROTOCOL §2.10)."""
    tick = float(limits.get("tick_sec", 5))
    sustain = float(limits.get("sustain_sec", 60))
    window = float(limits.get("window_sec", 2 * sustain))
    out = []
    for m in METRICS:
        lim = limits.get(LIMIT_KEY[m])
        if lim is None:
            continue
        lim = float(lim)
        ser = [(s["t"], (s.get("scope") or {}).get(m)) for s in samples]
        at = consecutive(ser, lim) if m == "disk_gb" else sustained(ser, lim, sustain, window, tick)
        if at is not None:
            peak = max((v for _, v in ser if v is not None), default=None)
            out.append({"metric": m, "limit": lim, "at": round(at, 2), "peak": peak})
    for e in events:
        if e.get("event") == "oom" and e.get("scope"):
            out.append({"metric": "oom", "limit": None, "at": e.get("t"), "peak": e.get("count"),
                        "service": e.get("role")})
    return sorted(out, key=lambda v: v["at"] or 0)


def peaks(samples):
    p = {}
    for m in METRICS:
        vals = [(s.get("scope") or {}).get(m) for s in samples]
        vals = [v for v in vals if v is not None]
        p[m] = round(max(vals), 3) if vals else 0.0
    return p


def read_jsonl(path):
    out = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        pass             # a torn last line (the monitor was killed mid-write)
    except OSError:
        pass
    return out


def read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def load_record(record=RECORD):
    """(summary or None, samples, events)."""
    return (read_json(os.path.join(record, "summary.json")), read_jsonl(os.path.join(record, "samples.jsonl")),
            read_jsonl(os.path.join(record, "events.jsonl")))


def record_problems(summary, samples, events, limits):
    """Why a record cannot be used ([] = usable)."""
    why = []
    if not summary:
        why.append("no sealed record (/var/rcb-monitor/summary.json missing: the monitor did not run, crashed, or was not collected)")
    elif summary.get("format") != FORMAT:
        why.append(f"record format {summary.get('format')!r}, expected {FORMAT}")
    if not samples:
        why.append("no samples")
    fatal = [e for e in events if e.get("event") == "fatal"]
    if fatal:
        why.append("monitor fatal: " + "; ".join(str(e.get("why")) for e in fatal)[:300])
    if samples and summary and not summary.get("scope_seen"):
        why.append("the monitor never found the containers it watches (no beacon seen)")
    if float(limits.get("max_gpu_memory_gb") or 0) > 0 and samples:
        blind = sum(1 for s in samples if (s.get("scope") or {}).get("gpu_unmeasured"))
        if blind / len(samples) > MAX_GAP_FRACTION:
            why.append(f"NVML did not tell the GPU memory of processes in scope in {blind} of {len(samples)} samples "
                       "(MIG / vGPU?): the GPU-memory limit was not measured")
    if len(samples) >= 2:
        tick = float(limits.get("tick_sec", 5))
        span = samples[-1]["t"] - samples[0]["t"]
        gaps = sum(max(0.0, b["t"] - a["t"] - 3 * tick) for a, b in zip(samples, samples[1:]))
        if span > 0 and gaps / span > MAX_GAP_FRACTION:
            why.append(f"{gaps:.0f} s of {span:.0f} s unobserved")
    return why


def switch_of(summary):
    """(enforce, why the switch cannot be read or None): the record's mode when there is a record, else this step's
    own environment (the same run-time variable, task.toml [verifier.env])."""
    if summary and summary.get("switch_error"):
        return 0, str(summary["switch_error"])
    if summary and "enforce" in summary:
        return parse_switch(summary.get("enforce"))
    return parse_switch(os.environ.get("RCB_LIMITS_ENFORCE"))


def verify(argv=()):
    log = os.environ.get("RCB_VERIFIER_LOGS", "/logs/verifier")
    tests = os.path.dirname(os.path.abspath(__file__))
    limits = read_json(os.path.join(tests, "rcb_limits.json")) or {}
    summary, samples, events = load_record()
    enforce, switch_error = switch_of(summary)
    rj_path, rt_path = os.path.join(log, "reward.json"), os.path.join(log, "reward.txt")
    reward = read_json(rj_path)
    have_grade = isinstance(reward, dict)
    reward = reward if have_grade else {}
    problems = record_problems(summary, samples, events, limits)
    if switch_error and not any(switch_error in p for p in problems):
        problems.append(switch_error)
    viol = violations(samples, limits, events) if samples else []
    pk = peaks(samples)
    emergency = [e for e in events if e.get("event") == "emergency_kill"]
    detail = {"format": FORMAT, "enforced": enforce, "limits": {k: v for k, v in limits.items()},
              "peaks": pk, "violations": viol, "record_problems": problems, "emergency_kills": emergency,
              "monitor": {k: (summary or {}).get(k) for k in ("started", "ended", "n_samples", "capabilities", "killed",
                                                               "restarts", "disk_baseline_gb", "disk_partial_walks")}}
    add = {"resource_enforced": enforce, "limits_violation_observed": int(bool(viol)),
           "resource_monitor_missing": int(bool(problems)),
           "peak_gpu_memory_gb": pk["gpu_memory_gb"], "peak_memory_gb": pk["memory_gb"],
           "peak_processes": pk["processes"], "peak_disk_gb": pk["disk_gb"],
           "resource_emergency_kills": len(emergency)}
    for v in viol:
        add["over_" + v["metric"]] = 1
    if switch_error:
        # nobody knows whether enforcement was asked for: not a result in either mode
        add["resource_switch_error"] = 1
        add["infra_error"] = 1
        detail["verdict"] = "not a result: " + switch_error
    elif enforce and viol:
        # a confirmed violation fails the trial whatever the deliverable (and wins over a grader's infra flag: the
        # agent's processes were stopped for it)
        add["success_before_limits"] = int(reward.get("success", 0) or 0)
        add["resource_limit_exceeded"] = 1
        add["success"] = 0
        if "reward" in reward:
            add["reward"] = 0
        if reward.get("infra_error"):
            add["grader_infra_error"] = 1
            add["infra_error"] = 0
        detail["verdict"] = "failed: resource limit exceeded (" + ", ".join(v["metric"] for v in viol) + ")"
    elif enforce and problems:
        add["infra_error"] = 1
        detail["verdict"] = "not a result: the resource monitor's record is not usable"
    else:
        # not enforced: observe only. A missing or unusable record is reported (resource_monitor_missing), never infra.
        detail["verdict"] = ("observed only (RCB_LIMITS_ENFORCE=0): " + ", ".join(v["metric"] for v in viol)) if viol \
            else "within limits" if not problems else "observed only (RCB_LIMITS_ENFORCE=0): no usable record"
    os.makedirs(log, exist_ok=True)
    failed = enforce and viol and not switch_error
    if have_grade or failed:
        reward.update(add)
        reward.setdefault("success", 0)
        tmp = rj_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(reward, f, indent=1)
        os.replace(tmp, rj_path)
        if failed:
            with open(rt_path, "w") as f:
                f.write("0\n")
    with open(os.path.join(log, "resource_limits.json"), "w") as f:
        json.dump(detail, f, indent=1)
    print("resource limits: " + detail["verdict"], file=sys.stderr)
    return 0


def step_failed(err):
    """This step raised: say so in the grader's reward.json instead of leaving the trial without its resource fields
    (and, when the switch asks for enforcement or cannot be read, as an infrastructure error: nothing was judged)."""
    log = os.environ.get("RCB_VERIFIER_LOGS", "/logs/verifier")
    rj_path = os.path.join(log, "reward.json")
    reward = read_json(rj_path)
    enforce, switch_error = parse_switch(os.environ.get("RCB_LIMITS_ENFORCE"))
    add = {"resource_step_error": 1, "resource_monitor_missing": 1, "resource_enforced": enforce}
    if enforce or switch_error:
        add["infra_error"] = 1
    if isinstance(reward, dict):
        reward.update(add)
        tmp = rj_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(reward, f, indent=1)
        os.replace(tmp, rj_path)
    with open(os.path.join(log, "resource_limits.json"), "w") as f:
        json.dump({"format": FORMAT, "enforced": enforce, "verdict": "the verifier's resource step failed: " + err,
                   "record_problems": [err]}, f, indent=1)


if __name__ == "__main__":
    if sys.argv[1:2] == ["verify"]:
        try:
            sys.exit(verify(sys.argv[2:]))
        except Exception as e:                      # never break the grader's own verdict
            msg = f"{type(e).__name__}: {e}"
            print(f"resource limits: verifier step failed: {msg}", file=sys.stderr)
            try:
                step_failed(msg)
            except Exception:
                pass
            sys.exit(0)
    print(__doc__)
