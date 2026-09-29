"""Summarize rollout outcomes, token budgets and episode artifacts."""
import argparse
import json
from pathlib import Path

from .collect import atomic_json


def _optional_json(path):
    """Old or incomplete trials may lack supplementary episode artifacts."""
    try:
        value = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _stop_delay_ms(stop, timings, key):
    decision = stop.get("decision_monotonic_ns")
    stopped = timings.get(key + "_monotonic_ns")
    if decision is None or stopped is None or stopped < decision:
        return None
    return round((stopped - decision) / 1_000_000, 3)


def episode_summary(run, trial_name, item):
    """Project collected evidence without inferring missing observations as zero."""
    archive = Path(item["archive"]) if item.get("archive") else None
    session = _optional_json(archive / "session_final.json") if archive else {}
    report = _optional_json(archive / "report.json") if archive else {}
    instance = _optional_json(archive / "instance.json") if archive else {}
    simulator = instance.get("simulator", {})
    verdict = item.get("verification") or {}
    usage = item.get("usage") or {}
    stop, timings = usage.get("stop") or {}, item.get("stop_timings") or {}
    records = report.get("segments")
    segments = [record.get("result") for record in records] if isinstance(records, list) else None
    complete_records = segments is not None and all(isinstance(s, dict) for s in segments)
    initial = [s for s in segments if s.get("segment_id") == 0] if complete_records else None
    policies = [s for s in segments if s.get("segment_id") != 0] if complete_records else None

    def total(items, field):
        if items is None or any(s.get(field) is None for s in items):
            return None
        return sum(s[field] for s in items)

    return dict(trial=trial_name, episode_id=session.get("episode_id") or report.get("episode_id"),
        task_id=simulator.get("task_id"), seed=simulator.get("seed"), mode=instance.get("mode"),
        control_mode=simulator.get("control_mode"), evaluation=verdict.get("evaluation"),
        task_success=verdict.get("task_success"), reward=verdict.get("reward"),
        pipeline_passed=item.get("pipeline_passed"), archive_status=item.get("status"),
        evidence_complete=verdict.get("evidence_complete"),
        stop_reason=stop.get("reason") or item.get("failure_reason") or verdict.get("stop_reason")
            or session.get("stop_reason") or item.get("harbor_exception") or item.get("error"),
        stop_dimensions=stop.get("dimensions", []), token_mode=usage.get("mode"),
        usage=usage.get("usage") or {k: usage.get(k) for k in ("input_tokens", "output_tokens")},
        limits=usage.get("limits", {}), overshoot=usage.get("overshoot", {}),
        budget_qualified=item.get("budget_qualified"), usage_complete=usage.get("usage_complete"),
        model_requests=usage.get("request_count"), in_flight_requests=usage.get("in_flight_requests"),
        policy_segments=len(policies) if policies is not None else verdict.get("segments"),
        control_steps=total(segments if complete_records else None, "control_steps"),
        initial_control_steps=total(initial, "control_steps"), policy_control_steps=total(policies, "control_steps"),
        simulated_duration_s=total(segments if complete_records else None, "simulated_duration_s"),
        agent_stop_delay_ms=_stop_delay_ms(stop, timings, "agent_stopped"),
        execution_stop_delay_ms=_stop_delay_ms(stop, timings, "worker_stopped"),
        forced_environment_stop=timings.get("forced_environment_stop", False),
        archive=str(archive) if archive else None,
        usage_path=str(Path(run) / "jobs/job" / trial_name / "usage") if usage else None)


def summarize(run):
    run = Path(run)
    index = json.loads((run / "rollout_index.json").read_text())
    trials = list(index["trials"].values())
    config = json.loads((run / "experiment.resolved.json").read_text())
    task = [item for item in trials if item.get("verification", {}).get("evaluation") == "task_success"]
    eligible = [item for item in task if item.get("pipeline_passed")
                and item["verification"].get("scoring_eligible", False)]
    solved = sum(item["verification"].get("task_success") is True for item in eligible)
    budgeted = config["usage"]["mode"] != "off"
    planned_tasks = sum(i["evaluation"] == "task_success" for i in config["instances"]) * config["attempts"]
    budget_solved = sum(item.get("pipeline_passed", False) and item.get("budget_qualified", False)
                        and item["verification"].get("reward") == 1 for item in task)
    summary = dict(schema_version=2, expected_trials=index["expected_trials"], collected_trials=index["collected_trials"],
        pipeline_passed=index["pipeline_passed"],
        pipeline_smoke_trials=sum(item.get("verification", {}).get("evaluation") == "pipeline_smoke" for item in trials),
        task_trials=len(task), scored_task_trials=len(eligible), solved_task_trials=solved,
        success_rate=solved / len(eligible) if eligible else None,
        unscored_task_trials=len(task)-len(eligible),
        incomplete_archives=sum(item.get("status") != "complete" for item in trials),
        token_mode=config["usage"]["mode"], token_budget_enforced=budgeted,
        budget_qualified=(len(trials) == index["expected_trials"] and all(
            t.get("budget_qualified", False) for t in trials)) if budgeted else None,
        planned_task_trials=planned_tasks, budget_solved_trials=budget_solved if budgeted else None,
        budget_success_rate=budget_solved / planned_tasks if budgeted and planned_tasks else None,
        budget_failed_trials=sum(t.get("failure_reason") in {"budget_exceeded", "budget_exhausted",
            "reservation_violation"} for t in trials),
        usage_failed_trials=sum(t.get("failure_reason") not in {None, "budget_exceeded", "budget_exhausted",
            "reservation_violation"} for t in trials),
        missing_trials=max(0, index["expected_trials"] - len(trials)),
        confirmed_usage={key: sum((t.get("usage") or {}).get(key, 0) or 0 for t in trials)
                         for key in ("input_tokens", "output_tokens")} if budgeted else None,
        rollout_index=str(run / "rollout_index.json"))
    if connection := config.get("model_connection"):
        summary["model"] = connection["full_model_name"]
        summary["provider"] = connection["provider_id"]
        summary["opencode_version"] = connection["opencode_version"]
    if budgeted:
        summary["confirmed_usage_by_route"] = {}
        for trial in trials:
            for route, counts in (trial.get("usage") or {}).get("by_route", {}).items():
                row = summary["confirmed_usage_by_route"].setdefault(route, dict(input_tokens=0, output_tokens=0))
                for key in row:
                    row[key] += counts[key]
        summary["usage_adapter_ids"] = sorted({trial["usage_binding"]["adapter_id"]
            for trial in trials if trial.get("usage_binding")})
    summary["run_dir"] = str(run.resolve())
    summary["episodes"] = [episode_summary(run, key, item) for key, item in sorted(index["trials"].items())]
    atomic_json(run / "summary.json", summary)
    return summary


def format_summary(summary):
    """Concise terminal view; JSON remains available for tools and old callers."""
    def value(item):
        if item is None:
            return "unknown"
        if isinstance(item, bool):
            return "yes" if item else "no"
        # Do not let artifact text inject extra terminal lines/control sequences.
        return "".join(c if c.isprintable() else "?" for c in str(item))

    def count(item):
        return f"{item:,}" if isinstance(item, (int, float)) else value(item)

    def status(item):
        return "PASS" if item is True else "FAIL" if item is False else "unknown"

    lines = ["", "TopoGym episode summary", f"Run: {value(summary.get('run_dir'))}",
        f"Model: {value(summary.get('model'))}",
        f"Trials collected: {count(summary.get('collected_trials'))} / {count(summary.get('expected_trials'))}"
        f" | Pipeline: {status(summary.get('pipeline_passed'))}"]
    for item in summary.get("episodes", []):
        mode = item.get("token_mode") or summary.get("token_mode")
        reason = value(item.get("stop_reason")) if item.get("stop_reason") else "none recorded"
        if item.get("stop_dimensions"):
            reason += " [" + ", ".join(value(d) for d in item["stop_dimensions"]) + "]"
        lines += ["", f"Trial: {value(item.get('trial'))}",
            f"  Episode: {value(item.get('episode_id'))}",
            f"  Task: {value(item.get('task_id'))} | seed={value(item.get('seed'))}"
            f" | mode={value(item.get('mode'))} | control={value(item.get('control_mode'))}",
            f"  Task success: {value(item.get('task_success'))} | Reward: {value(item.get('reward'))}"
            f" | Pipeline: {status(item.get('pipeline_passed'))}", f"  Stop reason: {reason}"]
        if mode == "off":
            lines.append("  Token budget: off (usage not measured)")
        else:
            lines.append(f"  Token budget: {status(item.get('budget_qualified'))} ({value(mode)}; per trial)")
            for dimension in ("input", "output"):
                key = dimension + "_tokens"
                used, limit = item.get("usage", {}).get(key), item.get("limits", {}).get(key)
                extra = item.get("overshoot", {}).get(key)
                line = f"    {dimension.capitalize()}: {count(used)} / {count(limit)}"
                if extra is not None and extra > 0:
                    line += f" (over by {count(extra)})"
                lines.append(line)
            lines.append(f"  Usage complete: {value(item.get('usage_complete'))}"
                f" | Model requests: {count(item.get('model_requests'))}"
                f" | In flight: {count(item.get('in_flight_requests'))}")
        duration = item.get("simulated_duration_s")
        duration = f"{duration:.3f}s" if duration is not None else "unknown"
        lines += [f"  Policy segments: {count(item.get('policy_segments'))}"
            f" | Control steps: {count(item.get('control_steps'))}"
            f" (initial={count(item.get('initial_control_steps'))}, policy={count(item.get('policy_control_steps'))})"
            f" | Simulated: {duration}"]
        delays = [(label, item.get(key)) for label, key in (
            ("agent", "agent_stop_delay_ms"), ("execution", "execution_stop_delay_ms"))]
        if any(delay is not None for _, delay in delays):
            lines.append("  Stop confirmed after decision: " + " | ".join(
                label + (f" +{delay:.1f}ms" if delay is not None else " unknown") for label, delay in delays))
        if item.get("forced_environment_stop"):
            lines.append("  Forced container stop: yes")
        lines += [f"  Archive: {value(item.get('archive'))}",
            f"  Archive status: {value(item.get('archive_status'))}"
            f" | Evidence complete: {value(item.get('evidence_complete'))}"]
        if item.get("usage_path"):
            lines.append(f"  Usage ledger: {value(item['usage_path'])}/ledger.sqlite")
    if summary.get("token_mode") == "observed":
        lines.append("\nObserved usage is settled from provider receipts; in-flight input can exceed the limit.")
    lines.append(f"Summary JSON: {value(summary.get('run_dir'))}/summary.json")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--format", choices=("json", "text"), default="json")
    args = parser.parse_args(argv)
    summary = summarize(args.run)
    print(format_summary(summary) if args.format == "text" else json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
