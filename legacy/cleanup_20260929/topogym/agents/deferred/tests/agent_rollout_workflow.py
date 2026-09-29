"""Operator helpers behind tests/run_agent_rollout.sh; never an agent tool."""
import argparse
from collections import Counter
import getpass
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "topogym.rollout_workflow.v1"
# Short tutorial defaults, intentionally separate from full evaluation defaults.
LIMITS = dict(repeats=1, max_calls=4, max_segments=6, max_steps=100,
              max_total_steps=300, max_resets=1, max_api_calls=100,
              token_limit=3_000_000, max_output_tokens=8192,
              samples_per_camera=2, worker_timeout_s=3600)


def integer(value):
    result = int(value)
    if result < 0:
        raise argparse.ArgumentTypeError("must be nonnegative")
    return result


def positive(value):
    result = integer(value)
    if result == 0:
        raise argparse.ArgumentTypeError("must be positive")
    return result


def seconds(value):
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise argparse.ArgumentTypeError("must be finite and positive")
    return result


def parser():
    p = argparse.ArgumentParser(description=(
        "Linux rollout workflow: prepare configuration and frozen presets, then evaluate, report or watch. "
        "Paths are relative to the repository. Only evaluate can incur model API charges."))
    commands = p.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="Create a NEW run directory; no model requests")
    prepare.add_argument("--task", choices=("cast_coil", "counter"), default="cast_coil")
    prepare.add_argument("--model", help="Model ID for the current Codex/OpenAI adapter")
    prepare.add_argument("--agent-id", default="model")
    prepare.add_argument("--access-mode", choices=("rgb", "simulator", "both"), default="simulator")
    prepare.add_argument("--reset-policy", choices=("disabled", "same_preset"),
                         help="Override the default (simulator: same_preset; RGB: disabled)")
    prepare.add_argument("--agents", type=Path, help="Copy an existing agent JSON instead of generating it")
    prepare.add_argument("--suite", type=Path, help="Reuse an existing frozen suite, without resampling")
    prepare.add_argument("--variants", type=positive, default=1)
    prepare.add_argument("--seed", type=int, default=20260921)
    prepare.add_argument("--backend", choices=("cpu", "cuda"), default="cpu")
    prepare.add_argument("--renderer", choices=("rasterizer", "nyx"), default="rasterizer")
    prepare.add_argument("--objective", choices=("assemble", "disassemble"), default="assemble")
    prepare.add_argument("--resolution", type=positive, nargs=2, default=[320, 180])
    prepare.add_argument("--timeout-s", type=seconds, default=600, help="Per agent turn")
    for name, default in LIMITS.items():
        kind = seconds if name == "worker_timeout_s" else integer if name in ("max_resets", "token_limit") else positive
        prepare.add_argument("--" + name.replace("_", "-"), type=kind, default=default)
    evaluate = commands.add_parser("evaluate", help="Run saved settings; may incur model API charges")
    report = commands.add_parser("report", help="Show results, log locations and camera video directories")
    report.add_argument("--json", action="store_true", help="Print full summary and results JSON")
    watch = commands.add_parser("watch", help="Monitor public token ledgers; Ctrl-C to stop")
    watch.add_argument("--interval", type=seconds, default=2)
    watch.add_argument("--once", action="store_true", help="Print one snapshot and exit")
    for command in (prepare, evaluate, report, watch):
        command.add_argument("--output", type=Path, required=True, help="Run root (not its evaluation subdirectory)")
    return p


def read_json(path):
    return json.loads(path.read_text())


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def validate_agents(agents, token_limit):
    from topogym.agent_rollout.profiles import profile
    from topogym.agent_rollout.suite import identifier
    if not isinstance(agents, list) or not agents:
        raise ValueError("agents JSON must be a nonempty list")
    seen = set()
    for agent in agents:
        key = (identifier(agent["id"]), profile(agent)["access_mode"])
        if key in seen:
            raise ValueError("Duplicate agent ID / access mode")
        seen.add(key)
        if agent["provider"] not in ("codex", "command", "replay"):
            raise ValueError("Unsupported provider; add an adapter before using this service")
        if agent["provider"] == "codex" and not agent.get("model"):
            raise ValueError("Codex requires a model ID")
        if agent["provider"] == "command" and token_limit:
            raise ValueError("command cannot enforce token budgets; explicitly use --token-limit 0")


def prepare_run(args):
    from topogym.agent_rollout.suite import load_suite
    limits = {name: getattr(args, name) for name in LIMITS}
    if args.max_steps > 10000 or not 2 <= args.samples_per_camera <= 16:
        raise ValueError("max_steps must be <=10000; samples_per_camera must be 2..16")
    if args.agents:
        if args.model or args.agent_id != "model" or args.access_mode != "simulator" or args.reset_policy:
            raise ValueError("Use either --agents or generated-agent options, not both")
        agents = read_json(args.agents)
    else:
        if not args.model:
            raise ValueError("Specify --model MODEL_ID or --agents PATH")
        modes = ["rgb", "simulator"] if args.access_mode == "both" else [args.access_mode]
        agents = [dict(id=args.agent_id, provider="codex", model=args.model, access_mode=mode,
                       interaction="tools", reset_policy=args.reset_policy or
                       ("same_preset" if mode == "simulator" else "disabled"), timeout_s=args.timeout_s)
                  for mode in modes]
    validate_agents(agents, args.token_limit)
    # Validate reused scenes before creating anything. The suite path stays external.
    suite = args.suite.resolve() if args.suite else args.output / "presets/suite.json"
    if args.suite:
        load_suite(suite)
    args.output.mkdir(parents=True, exist_ok=False)
    write_json(args.output / "agents.json", agents)
    if not args.suite:
        subprocess.run([sys.executable, "-m", "topogym.agent_rollout", "prepare",
                        "--task", args.task, "--variants", str(args.variants), "--seed", str(args.seed),
                        "--backend", args.backend, "--renderer", args.renderer, "--objective", args.objective,
                        "--resolution", *map(str, args.resolution), "--output", str(suite.parent)],
                       cwd=ROOT, check=True)
    bank = load_suite(suite)
    trials = len(agents) * len(bank["variants"]) * args.repeats
    write_json(args.output / "run.json", dict(schema=SCHEMA, suite=str(suite), limits=limits,
                                              expected_trials=trials))
    print(f"Prepared {trials} trials; no model API was called.", flush=True)
    print(f"Agents: {args.output / 'agents.json'}\nSettings: {args.output / 'run.json'}\nSuite: {suite}")
    print("Review the saved settings, then use the evaluate subcommand.")


def load_run(root):
    settings = read_json(root / "run.json")
    if settings.get("schema") != SCHEMA or set(settings["limits"]) != set(LIMITS):
        raise ValueError("Unknown or incomplete workflow settings")
    return settings


def evaluate_run(args):
    from topogym.agent_rollout.suite import load_suite
    settings = load_run(args.output)
    agents = read_json(args.output / "agents.json")
    validate_agents(agents, settings["limits"]["token_limit"])
    if (args.output / "evaluation").exists():
        raise ValueError("evaluation already exists; prepare a new run (use --suite to reuse frozen variants)")
    load_suite(settings["suite"])
    env = dict(os.environ)
    if any(agent["provider"] == "codex" for agent in agents):
        key = env.get("TOPOGYM_MODEL_API_KEY")
        if not key:
            if not sys.stdin.isatty():
                raise ValueError("Set TOPOGYM_MODEL_API_KEY in the process environment, or run evaluate in a terminal")
            key = getpass.getpass("Model service API key (current adapter: OpenAI): ")
        if not key.strip():
            raise ValueError("An API key is required for the current Codex/OpenAI adapter")
        env["CODEX_API_KEY"] = key
        print("Starting evaluation with the Codex/OpenAI adapter; model API charges may apply.", flush=True)
    # Keep the generic variable out of downstream agent processes; the trusted
    # Codex budget proxy consumes CODEX_API_KEY and issues temporary credentials.
    env.pop("TOPOGYM_MODEL_API_KEY", None)
    env.setdefault("PYOPENGL_PLATFORM", "egl")
    env.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
    command = [sys.executable, "-m", "topogym.agent_rollout", "evaluate",
               "--suite", settings["suite"], "--agents", str(args.output / "agents.json"),
               "--output", str(args.output / "evaluation")]
    for name, value in settings["limits"].items():
        command.extend(["--" + name.replace("_", "-"), str(value)])
    subprocess.run(command, cwd=ROOT, env=env, check=True)
    return report_run(argparse.Namespace(output=args.output, json=False))


def report_run(args):
    root = args.output / "evaluation"
    if not (root / "results.json").exists():
        print(f"No results yet. Worker logs, if started: {root / '_jobs'}")
        return 1
    results = read_json(root / "results.json")
    summary = read_json(root / "summary.json")
    if args.json:
        print(json.dumps(dict(summary=summary, results=results), ensure_ascii=False, indent=2))
    else:
        expected = None
        if (args.output / "run.json").exists():
            # Recompute from the evaluation snapshot when possible, since the
            # operator may have reviewed/edited agents.json after preparation.
            settings = read_json(root / "evaluation.json")
            bank = read_json(Path(settings["suite"]))
            expected = len(settings["agents"]) * len(bank["variants"]) * settings["repeats"]
        print(f"Recorded trials: {len(results)}" + (f" / {expected}" if expected is not None else ""))
        print("Statuses: " + json.dumps(dict(Counter(row["status"] for row in results))))
        for row in summary:
            print(f"{row['agent_id']} / {row['input_mode']} / {row['task_id']}: "
                  f"success={row['successes']}/{row['trials']}, pipeline_errors={row['pipeline_errors']}, "
                  f"known_tokens={row.get('known_metered_tokens', 0)}, usage_complete={row['usage_complete']}")
        for row in results:
            public = root / row["directory"]
            print(f"Trial: {public} [{row['status']}]")
            if row.get("reason"):
                print(f"  Reason: {row['reason']}")
            for episode in sorted((public / "episodes").glob("episode_*")):
                for camera in sorted(episode.iterdir()):
                    if camera.is_dir() and next(camera.glob("segment_*.mp4"), None):
                        print(f"  Camera videos: {camera}")
            print(f"  Private logs: {root / '_private' / row['directory']}")
        print(f"Summary: {root / 'summary.json'}\nResults: {root / 'results.json'}\nWorker logs: {root / '_jobs'}")
    return int(any(row["status"] == "pipeline_error" for row in results))


def watch_run(args):
    root = args.output / "evaluation"
    while True:
        print(time.strftime("%Y-%m-%d %H:%M:%S"), flush=True)
        paths = sorted(root.glob("agent_*_rollouts/*/rollout_*/repeat_*/token_budget.json"))
        if not paths:
            print("Waiting for public token ledgers (unmetered replay runs may have none).", flush=True)
        for path in paths:
            try:
                data = read_json(path)
            except (OSError, ValueError):
                print(f"{path.parent.relative_to(root)}: ledger being updated", flush=True)
                continue
            print(f"{path.parent.relative_to(root)}: " + json.dumps(data, ensure_ascii=False), flush=True)
        if args.once:
            return 0
        time.sleep(args.interval)


def main():
    args = parser().parse_args()
    args.output = args.output.resolve()
    try:
        return {"prepare": prepare_run, "evaluate": evaluate_run,
                "report": report_run, "watch": watch_run}[args.command](args) or 0
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
