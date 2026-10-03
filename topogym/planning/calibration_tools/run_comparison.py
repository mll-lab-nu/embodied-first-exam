"""Offline comparison of existing development evidence; never reruns a simulation."""
import json
from pathlib import Path
import statistics

from .contracts import digest


def _json(path, issues, *, required=False):
    if not path.exists():
        if required:
            issues.append("missing:"+path.name)
        return None
    try:
        return json.loads(path.read_text())
    except (ValueError, OSError) as exc:
        issues.append(f"unreadable:{path.name}:{type(exc).__name__}")
        return None


def summarize_run(directory):
    root = Path(directory).resolve()
    issues = []
    session = _json(root / "session.json", issues, required=True) or {}
    timing = _json(root / "timings.json", issues, required=True) or {}
    source = _json(root / "source_manifest.json", issues, required=True)
    assets = _json(root / "execution/asset_manifest.json", issues)
    report = _json(root / "report.json", issues) or {}
    actions, active_actions, ticks, active_ticks, cache = [], [], 0, 0, []
    episode, intervention = None, bool(report.get("exploration"))
    events_path = root / "events.jsonl"
    if events_path.exists():
        with events_path.open() as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                except ValueError:
                    issues.append("torn_events_tail")
                    break
                kind = row.get("kind")
                intervention |= bool(row.get("exploration"))
                if kind == "episode_started":
                    episode = row.get("metadata")
                elif kind == "control_committed":
                    count = row.get("physics_steps", 0)
                    actions.append(dict(action=row["action"], physics_steps=count))
                    active_actions.append(actions[-1])
                    ticks += count
                elif kind == "restore_committed":
                    active_actions = active_actions[:row["action_count"]]
                elif kind == "plan_prepared":
                    cache.append({k: row.get(k) for k in ("plan_id", "selection", "timings")})
    else:
        issues.append("missing:events.jsonl")
    active_ticks = sum(a["physics_steps"] for a in active_actions)
    config = dict(session.get("config", {}))
    for key in ("work_dir", "output_dir"):
        config.pop(key, None)
    costs = timing.get("costs", {})
    control = costs.get("control_step", {})
    identity = dict(config=digest(config) if config else None,
                    source=digest(source) if source else None,
                    assets=digest(assets) if assets else None,
                    actions=digest(actions) if actions else None,
                    candidate=digest(session.get("candidate", {})), exploration=intervention)
    return dict(directory=str(root), session_id=session.get("session_id"), identity=identity,
        task_id=config.get("task_id"), variation_id=config.get("variation_id"), seed=config.get("seed"),
        control_steps=len(actions), physics_ticks=ticks, active_branch_steps=len(active_actions),
        active_branch_ticks=active_ticks, simulation_time_s=ticks*config["physics_dt_s"] if "physics_dt_s" in config else None,
        control_wall_seconds=control.get("seconds"),
        wall_seconds_per_control=control.get("seconds", 0.)/len(actions) if actions and control else None,
        stages=costs, incomplete_spans=timing.get("incomplete_spans", []),
        task=report.get("task_summary"), plan_preparations=cache, episode=episode,
        timing_scope="host wall time; inclusive stages overlap, compare self_seconds separately", issues=issues)


def compare_runs(directories):
    """Return raw differences even when a speedup ratio would be misleading."""
    if not isinstance(directories, (list, tuple)) or len(directories) < 2:
        raise ValueError("Provide at least two run directories")
    if len(directories) > 128:
        raise ValueError("At most 128 runs per comparison")
    runs = [summarize_run(p) for p in directories]
    baseline, comparisons = runs[0], []
    for row in runs[1:]:
        mismatches = [name for name, expected in baseline["identity"].items()
                      if expected is None or row["identity"].get(name) is None or row["identity"].get(name) != expected]
        if row["control_steps"] != baseline["control_steps"] or row["physics_ticks"] != baseline["physics_ticks"]:
            mismatches.append("executed_work")
        if baseline["issues"] or row["issues"] or baseline["incomplete_spans"] or row["incomplete_spans"]:
            mismatches.append("incomplete_evidence")
        a, b = baseline["control_wall_seconds"], row["control_wall_seconds"]
        comparisons.append(dict(directory=row["directory"], comparable=not mismatches,
            differences=mismatches, control_speedup=a/b if not mismatches and a is not None and b and b > 0 else None,
            stage_deltas={name: dict(
                seconds=row["stages"][name].get("seconds", 0)-baseline["stages"][name].get("seconds", 0),
                self_seconds=row["stages"][name].get("self_seconds", 0)-baseline["stages"][name].get("self_seconds", 0))
                for name in baseline["stages"].keys() & row["stages"].keys()}))
    planning = {}
    for row in runs:
        for plan in row["plan_preparations"]:
            mode = plan["selection"]
            for name, value in (plan["timings"] or {}).items():
                planning.setdefault(mode, {}).setdefault(name, []).append(value)
    planning = {mode: {stage: dict(samples=len(values), median_s=statistics.median(values), total_s=sum(values))
                       for stage, values in stages.items()} for mode, stages in planning.items()}
    return dict(baseline=baseline["directory"], runs=runs, comparisons=comparisons, planning_by_selection=planning,
        scope="recorded workload and host wall time; no new physical or task qualification",
        planning_scope="descriptive totals by selected path; different planning requests are not a paired speedup test")
