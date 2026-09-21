"""python -m topogym.agent_rollout {prepare,evaluate,worker}."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("prepare", help="Sample/freeze the complete variant bank before any rollout")
    p.add_argument("--task", action="append", choices=("counter", "cast_coil"), default=[])
    p.add_argument("--preparer", action="append", default=[], metavar="TASK=MODULE:FUNCTION")
    p.add_argument("--variants", type=int, default=1)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--backend", choices=("cpu", "cuda"), default="cpu")
    p.add_argument("--renderer", choices=("rasterizer", "nyx"), default="rasterizer")
    p.add_argument("--objective", choices=("assemble", "disassemble"), default="assemble")
    p.add_argument("--resolution", type=int, nargs=2, default=[320, 180])
    p = commands.add_parser("evaluate", help="Run shared frozen variants; default three repeats per condition")
    p.add_argument("--suite", type=Path, required=True)
    p.add_argument("--agents", type=Path, required=True, help="JSON list of agent configurations")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--max-steps", type=int, default=1000)
    p.add_argument("--max-total-steps", type=int, default=10000)
    p.add_argument("--max-segments", type=int, default=50)
    p.add_argument("--max-calls", type=int, default=100)
    p.add_argument("--samples-per-camera", type=int, default=4)
    p.add_argument("--worker-timeout-s", type=float, default=3600)
    p.add_argument("--max-resets", type=int, default=2, help="Per-trial resets when reset_policy=same_preset")
    p.add_argument("--max-api-calls", type=int, default=1000, help="Cumulative environment API calls across resets")
    p.add_argument("--token-limit", type=int, default=3_000_000,
                   help="Per-repeat input+output token limit for Codex; 0 explicitly disables enforcement")
    p.add_argument("--max-output-tokens", type=int, default=8192,
                   help="Per underlying model request output cap, including reasoning")
    p = commands.add_parser("worker", help=argparse.SUPPRESS)
    p.add_argument("job", type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        from .suite import prepare
        tasks = {name: f"topogym.agent_rollout.suite:prepare_{name}" for name in args.task}
        tasks.update(dict(item.split("=", 1) for item in args.preparer))
        print(prepare(args.output, tasks, variants=args.variants, seed=args.seed,
            options=dict(backend=args.backend, renderer=args.renderer, objective=args.objective,
                         resolution=args.resolution)))
    elif args.command == "evaluate":
        from .evaluate import evaluate
        print(evaluate(args.suite, args.output, json.loads(args.agents.read_text()),
            **{name: getattr(args, name) for name in ("repeats", "max_steps", "max_total_steps", "max_segments",
                                                   "max_calls", "samples_per_camera", "worker_timeout_s",
                                                   "token_limit", "max_output_tokens", "max_resets", "max_api_calls")}))
    else:
        from .runtime import run_repeat
        result = run_repeat(json.loads(args.job.read_text()))
        print(json.dumps(result, ensure_ascii=False))
        if result["status"] == "pipeline_error":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
