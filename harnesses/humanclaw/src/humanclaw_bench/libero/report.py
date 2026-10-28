"""Run and batch summaries, with source span IDs and explicit missing usage."""
from __future__ import annotations
from collections import defaultdict
import json
from pathlib import Path
import sqlite3
import statistics

from humanclaw_bench.experiments.report import normalize_model_usage, _price_usage


def events(directory):
    """Read the original ordered event stream for a run."""
    with (Path(directory) / "events.jsonl").open() as handle:
        for line in handle:
            yield json.loads(line)


def summarize(directory):
    """Derive metrics and evidence links without inventing missing usage."""
    directory = Path(directory)
    manifest = json.loads((directory / "run.json").read_text())
    starts, ends, counters = {}, {}, defaultdict(lambda: defaultdict(int))
    delivered_ns = settled_ns = None
    for e in events(directory):
        if e["event"] == "native.command":
            command = e.get("data") or {}
            if command.get("method") == "turn/start" or command.get("type") == "prompt":
                delivered_ns = delivered_ns or e["monotonic_ns"]
        if e["event"] == "native.event":
            notification = e.get("data") or {}
            if notification.get("method") == "turn/completed" or notification.get("type") == "agent_settled":
                settled_ns = e["monotonic_ns"]
        if e["event"] == "span.start":
            starts[e["span_id"]] = e
        elif e["event"] == "span.end":
            ends[e["span_id"]] = e
        elif e["event"] in {"capability.exposed", "tool.requested", "tool.rejected", "tool.deduplicated"}:
            counters[e["name"]][e["event"].split(".")[-1]] += 1
    calls, operations = [], {}
    for ident, start in starts.items():
        end = ends.get(ident)
        if start["kind"] == "model":
            raw = (end or {}).get("data", {}).get("usage")
            usage = normalize_model_usage(raw)
            model = start["data"].get("attributes", {}).get("model")
            pricing = manifest.get("pricing") or {}
            rate = pricing.get("models", {}).get(model) if "models" in pricing else pricing
            calls.append({"span_id": ident, "parent_span_id": start["parent_span_id"],
                          "model": model, "raw_usage": raw, "usage": usage,
                          "cost": _price_usage(usage, rate),
                          "status": (end or {}).get("data", {}).get("status", "unfinished")})
        if start["kind"] in {"tool", "module", "environment"}:
            key = start["name"]
            row = operations.setdefault(key, {"kind": start["kind"], "executions": 0, "failures": 0,
                "unfinished": 0, "duration_ms": [], "span_ids": [], **counters.get(key, {})})
            row["executions"] += 1
            row["span_ids"].append(ident)
            if end is None:
                row["unfinished"] += 1
            else:
                row["failures"] += end["data"]["status"] == "failed"
                row["duration_ms"].append(end["data"]["duration_ms"])
    for key, counts in counters.items():
        operations.setdefault(key, {"executions": 0, "failures": 0, "unfinished": 0, "duration_ms": [], "span_ids": []}).update(counts)
    for row in operations.values():
        resolved = row["executions"] - row["unfinished"]
        row["failure_rate"] = row["failures"] / resolved if resolved else None
        row["duration_total_ms_inclusive"] = sum(row["duration_ms"])
    token_keys = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens", "total_tokens")
    known = {key: sum(c["usage"][key] or 0 for c in calls) for key in token_keys}
    totals = {key: known[key] if all(c["usage"][key] is not None for c in calls) else None for key in token_keys}
    metered = sum(c["usage"]["input_tokens"] is not None and c["usage"]["output_tokens"] is not None for c in calls)
    priced = sum(c["cost"]["total_usd"] is not None for c in calls)
    cost = sum(c["cost"]["known_subtotal_usd"] for c in calls)
    timing = {start["name"]: ends[ident]["data"]["duration_ms"] for ident, start in starts.items()
              if ident in ends and start["name"] in {"episode.decision", "episode.startup"}}
    if delivered_ns is not None:
        phase = next((s for s in starts.values() if s["name"] == "episode.decision"), None)
        if phase:
            timing["native.startup"] = (delivered_ns-phase["monotonic_ns"])/1e6
            timing["episode.harness_including_startup"] = timing.get("episode.decision")
            end_ns = settled_ns or ends.get(phase["span_id"], {}).get("monotonic_ns")
            if end_ns:
                timing["episode.decision"] = (end_ns-delivered_ns)/1e6
    motion = {"recorded_steps": 0, "unfinished_steps": 0}
    if (directory / "motion.sqlite").exists():
        with sqlite3.connect(f"file:{directory / 'motion.sqlite'}?mode=ro", uri=True) as db:
            motion = {"recorded_steps": db.execute("SELECT count(*) FROM steps WHERE phase='episode'").fetchone()[0],
                      "unfinished_steps": db.execute("SELECT count(*) FROM steps WHERE status!='completed'").fetchone()[0],
                      "environment_step_ms": (db.execute("SELECT sum(elapsed_ns) FROM steps WHERE phase='episode'").fetchone()[0] or 0)/1e6}
    result = {"schema": "libero_report_v1", "run_id": manifest["run_id"],
        "metadata": manifest["metadata"], "status": manifest["status"], "outcome": manifest["outcome"],
        "model_requests": len(calls), "metered_requests": metered,
        "usage_coverage": metered / len(calls) if calls else None,
        "tokens": totals, "known_token_subtotals": known,
        "cost_usd": cost if priced == len(calls) else None, "known_cost_subtotal_usd": cost,
        "pricing_coverage": priced / len(calls) if calls else None,
        "timing_ms": timing, "operations": operations, "model_calls": calls,
        "motion": motion, "unfinished_span_ids": sorted((set(starts)-set(ends)) | {k for k,v in ends.items() if v["data"].get("status") == "interrupted"}),
        "latency_note": "Inclusive nested operation times overlap; only episode.decision is end-to-end decision latency."}
    (directory / "report.json").write_text(json.dumps(result, indent=2))
    return result


def aggregate(directories):
    """Group attempts with explicit scoring, failure and coverage denominators."""
    grouped = defaultdict(list)
    for directory in directories:
        report = summarize(directory)
        grouped[report["metadata"]["harness"]].append(report)
    out = {}
    def distribution(values):
        """Summarize observed values using mean, median and nearest-rank P95."""
        if not values:
            return {"n": 0, "mean": None, "median": None, "p95": None}
        ordered = sorted(values)
        import math
        return {"n": len(values), "mean": statistics.mean(values), "median": statistics.median(values),
                "p95": ordered[max(0, math.ceil(.95*len(ordered))-1)]}
    for name, reports in grouped.items():
        scored = [r for r in reports if r["outcome"].get("benchmark_success") is not None and not r["outcome"].get("infrastructure_error")]
        success = sum(r["outcome"]["benchmark_success"] is True for r in scored)
        out[name] = {"attempts": len(reports), "scored_attempts": len(scored), "successes": success,
                     "unscored_attempts": len(reports)-len(scored),
                     "incomplete_attempts": sum(r["status"] in {"running", "interrupted"} or bool(r["unfinished_span_ids"]) for r in reports),
                     "infrastructure_errors": sum(bool(r["outcome"].get("infrastructure_error")) for r in reports),
                     "success_rate": success/len(scored) if scored else None,
                     "decision_ms_all_outcomes": distribution([r["timing_ms"]["episode.decision"] for r in reports if "episode.decision" in r["timing_ms"]]),
                     "missing_decision_latency_attempts": sum("episode.decision" not in r["timing_ms"] for r in reports),
                     "tokens_known_runs": distribution([r["tokens"]["total_tokens"] for r in reports if r["tokens"]["total_tokens"] is not None]),
                     "usd_known_runs": distribution([r["cost_usd"] for r in reports if r["cost_usd"] is not None]),
                     "unknown_cost_attempts": sum(r["cost_usd"] is None for r in reports),
                     "run_ids": [r["run_id"] for r in reports]}
    return {"schema": "libero_batch_v1", "groups": out,
            "denominator": "Scored attempts; infrastructure errors are separate. No best-of-attempt selection. All outcomes enter latency/cost."}
