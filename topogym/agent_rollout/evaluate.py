"""Run the shared variant bank across agents, conditions and independent repeats."""
import json
from pathlib import Path
import subprocess
import sys

from topogym.agent_bridge.session import write_json
from .suite import ROOT, identifier, load_suite
from .profiles import profile


def summarize(results):
    groups = {}
    for result in results:
        key = (result["agent_id"], result["input_mode"], result["task_id"],
               result.get("interaction", "segments"), result.get("reset_policy", "disabled"))
        groups.setdefault(key, []).append(result)
    summary = []
    for (agent, mode, task, interaction, reset_policy), trials in groups.items():
        variants = {}
        for trial in trials:
            variants.setdefault(trial["variant_id"], []).append(trial)
        variant_rates = [sum(t["success"] for t in group)/len(group) for group in variants.values()]
        summary.append(dict(agent_id=agent, input_mode=mode, task_id=task, interaction=interaction,
            reset_policy=reset_policy, trials=len(trials),
            first_episode_success_rate=sum(t.get("first_episode_success", t["success"]) for t in trials)/len(trials),
            total_resets=sum(t.get("resets", 0) for t in trials),
            total_ticks=sum(t.get("ticks", 0) for t in trials),
            total_wall_seconds=sum(t.get("wall_seconds", 0) for t in trials),
            variants=len(variants), successes=sum(t["success"] for t in trials),
            success_rate=sum(t["success"] for t in trials)/len(trials),
            mean_variant_success_rate=sum(variant_rates)/len(variant_rates),
            any_repeat_success_rate=sum(any(t["success"] for t in g) for g in variants.values())/len(variants),
            pipeline_errors=sum(t["status"] == "pipeline_error" for t in trials),
            token_budget_exhaustions=sum(t["status"] == "token_budget_exhausted" for t in trials),
            known_metered_tokens=sum((t.get("token_budget") or {}).get("used", 0) for t in trials),
            successes_within_token_budget=sum(t.get("success_within_token_budget", False) for t in trials),
            physics_qualified=all(t.get("physics_qualified", False) for t in trials),
            observation_isolation=sorted({t.get("observation_isolation", "unknown") for t in trials}),
            usage_complete=all(t.get("usage_complete", False) for t in trials)))
    return summary


def evaluate(suite_path, output, agents, *, repeats=3, max_steps=1000, max_total_steps=10000,
             max_segments=50, max_calls=100, samples_per_camera=4, worker_timeout_s=3600,
             token_limit=3_000_000, max_output_tokens=8192, max_resets=2, max_api_calls=1000):
    if type(token_limit) is not int or token_limit < 0:
        raise ValueError("token_limit must be a nonnegative integer")
    if type(max_resets) is not int or max_resets < 0:
        raise ValueError("max_resets must be a nonnegative integer")
    if not isinstance(worker_timeout_s, (int, float)) or not 0 < worker_timeout_s < float("inf"):
        raise ValueError("worker_timeout_s must be finite and positive")
    for name, value in dict(repeats=repeats, max_steps=max_steps, max_total_steps=max_total_steps,
                            max_segments=max_segments, max_calls=max_calls, samples_per_camera=samples_per_camera,
                            max_output_tokens=max_output_tokens, max_api_calls=max_api_calls).items():
        if type(value) is not int or value < 1:
            raise ValueError(f"{name} must be positive")
    if max_steps > 10000 or not 2 <= samples_per_camera <= 16:
        raise ValueError("max_steps <=10000; samples_per_camera must be 2..16 to include both endpoints")
    if not agents:
        raise ValueError("At least one agent is required")
    agents = [dict(agent, mode=profile(agent)["access_mode"], **profile(agent)) for agent in agents]
    seen = set()
    for agent in agents:
        key = (identifier(agent["id"]), agent["mode"])
        if key in seen:
            raise ValueError("Unknown or duplicate agent/input condition")
        seen.add(key)
        if agent["provider"] not in ("codex", "command", "replay"):
            raise ValueError("Unknown agent provider")
        if agent["provider"] == "command" and token_limit:
            raise ValueError("command cannot enforce per-request token limits; use Codex or explicitly set --token-limit 0")
    suite_path = Path(suite_path).resolve()
    suite = load_suite(suite_path)  # Validate the WHOLE bank before the first rollout.
    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "evaluation.json", dict(suite=str(suite_path), suite_sha256=suite["sha256"],
        agents=agents, repeats=repeats, max_steps=max_steps, max_total_steps=max_total_steps,
        max_segments=max_segments, max_calls=max_calls, samples_per_camera=samples_per_camera,
        token_limit=token_limit, max_output_tokens=max_output_tokens,
        max_resets=max_resets, max_api_calls=max_api_calls, worker_timeout_s=worker_timeout_s,
        reset_scope="per-agent reset_policy; always same frozen preset", scene_randomization="preparation only"))
    results, references = [], {}
    for agent in agents:
        for variant in suite["variants"]:
            for repeat in range(1, repeats+1):
                parts = (f"agent_{agent['id']}_{agent['mode']}_rollouts", variant["task_id"],
                         variant["variant_id"], f"repeat_{repeat}")
                public, private = root.joinpath(*parts), root.joinpath("_private", *parts)
                key = (variant["task_id"], variant["variant_id"])
                job = dict(public=str(public), private=str(private), agent=agent, repeat=repeat,
                    preset=str(suite_path.parent / variant["path"]), expected_initial=references.get(key),
                    max_steps=max_steps, max_total_steps=max_total_steps, max_segments=max_segments,
                    max_calls=max_calls, samples_per_camera=samples_per_camera,
                    token_limit=token_limit, max_output_tokens=max_output_tokens, max_resets=max_resets,
                    max_api_calls=max_api_calls, worker_timeout_s=worker_timeout_s)
                jobs = root / "_jobs"
                jobs.mkdir(exist_ok=True)
                job_path = jobs / f"job_{len(results)+1}.json"
                write_json(job_path, job)
                print("Running " + "/".join(parts), flush=True)
                failure = None
                with job_path.with_suffix(".log").open("w") as log:
                    try:
                        process = subprocess.run([sys.executable, "-m", "topogym.agent_rollout", "worker", str(job_path)],
                            cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                            timeout=worker_timeout_s + (15 if agent["interaction"] == "tools" else 0))
                        if process.returncode:
                            failure = f"Worker exited {process.returncode}"
                    except subprocess.TimeoutExpired:
                        failure = "Worker wall-time limit exceeded"
                if not (private / "result.json").exists():
                    result = dict(agent_id=agent["id"], input_mode=agent["mode"], task_id=variant["task_id"],
                                  variant_id=variant["variant_id"], repeat=repeat, status="pipeline_error",
                                  success=False, reason=failure or "Missing worker result", usage_complete=False)
                else:
                    result = json.loads((private / "result.json").read_text())
                    if failure and result["status"] != "pipeline_error":
                        result.update(status="pipeline_error", success=False, reason=failure)
                if result.get("initial_audit"):
                    references.setdefault(key, result["initial_audit"])
                result["directory"] = public.relative_to(root).as_posix()
                results.append(result)
                # Persist after every attempt, including infrastructure errors.
                write_json(root / "results.json", results)
                write_json(root / "summary.json", summarize(results))
    return root / "summary.json"
