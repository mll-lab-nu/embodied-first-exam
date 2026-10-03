"""Source-only CLI: inspect capabilities, run a smoke check or a JSON command file."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("capabilities", "smoke", "script"))
    parser.add_argument("--config", type=Path, help="SimulatorConfig JSON; overrides CLI scene defaults")
    parser.add_argument("--kind", choices=("geometry", "physics"), default="geometry")
    parser.add_argument("--task", default="cast_keyhole")
    parser.add_argument("--variation", default="very_easy")
    parser.add_argument("--backend", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--rgb", action="store_true", help="Build Nyx cameras, capture only on request")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--steps", type=int, default=3)
    parser.add_argument("--commands", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text()) if args.config else dict(
        task_id=args.task, variation_id=args.variation, compute_backend=args.backend,
        enable_rgb=args.rgb, seed=args.seed)
    from .api import open_session
    from topogym.utils.io import write_json_atomic
    results = []
    with open_session(config, args.output, kind=args.kind) as dev:
        results.append(dev.capabilities())
        if args.command == "smoke":
            results.append(dev.inspect())
            mark = dev.checkpoint("initial")
            if args.kind == "physics":
                if type(args.steps) is not int or not 1 <= args.steps <= 100:
                    raise ValueError("Smoke steps must be in [1, 100]")
                dev.watch(["contact_changed"], before_steps=1, after_steps=1)
                if config.get("enable_rgb"):
                    results.append(dev.capture_frame("cam_high"))
                for i in range(args.steps):
                    results.append(dev.step({}, request_id=f"smoke-step-{i}"))
                results.append(dev.contacts())
            else:
                probe = dev.inspect()
                entity = "keyhole_silver"
                body = probe["bodies"][entity]
                pose = {key: body[key] for key in ("position_m", "quaternion_wxyz")}
                results.append(dev.sweep_object(entity, [pose], obstacles=["keyhole_gold"]))
            results.append(dev.restore(mark))
        if args.command == "script":
            if args.commands is None:
                parser.error("script requires --commands")
            for row in json.loads(args.commands.read_text()):
                token = dev.submit(row["method"], **row.get("params", {}))
                results.append(dev.wait(token))
        report = dev.export_report()
        write_json_atomic(args.output / "cli_results.json", results)
        print(json.dumps(dict(report=report["report"], output=str(args.output),
                              formal_qualification=False), ensure_ascii=False))


if __name__ == "__main__":
    main()
