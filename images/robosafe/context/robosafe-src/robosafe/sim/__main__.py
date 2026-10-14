"""python -m robosafe.sim replay | demo | scenarios | eval | eval2 | report | report2

    replay RECORD            apply the rows of a world record (`World.save_record`) and print the state hash
    demo --scenario NAME     run one randomised skill scenario, write its record (and frames) to --out
    scenarios NAME [-n N]    success count of a skill scenario on N placements
    eval                     the actions on the generated assets: see `robosafe/sim/evaluate.py` and docs/MOTION.md
    eval2                    the same on two arms: see `robosafe/sim/evaluate_two_arms.py` and docs/MOTION.md 11
    report FILE [FILE ...]   Markdown tables over eval result files, side by side
    report2 FILE [FILE ...]  Markdown tables over the result files of eval2
    eval_room                a robot that drives, in a room: see `robosafe/sim/evaluate_room.py` and docs/MOTION.md 12
    report_room FILE [...] [--before FILE ...]   Markdown tables over the result files of eval_room
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m robosafe.sim")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("replay", help="re-apply the rows of a world record and print the state hash")
    p.add_argument("record")
    p = sub.add_parser("demo", help="run one skill scenario and write its record")
    p.add_argument("--scenario", required=True)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--index", type=int, default=0)
    p.add_argument("--out", default="build/sim_demo")
    p.add_argument("--no-frames", action="store_true")
    p = sub.add_parser("scenarios", help="success count of a skill scenario")
    p.add_argument("name")
    p.add_argument("-n", type=int, default=10)
    p.add_argument("--seed", type=int, default=2026)
    p = sub.add_parser("eval", help="success rates of the actions on the generated assets")
    from . import evaluate
    evaluate.add_arguments(p)
    p = sub.add_parser("eval2", help="the same on a robot with two arms, by arm, place and what the other arm does")
    from . import evaluate_two_arms
    evaluate_two_arms.add_arguments(p)
    p = sub.add_parser("eval_room", help="a robot that drives: the way to spots of a room, and the arm from the base")
    from . import evaluate_room
    evaluate_room.add_arguments(p)
    p = sub.add_parser("report_room", help="Markdown tables over the result files of eval_room, taken together")
    p.add_argument("files", nargs="+")
    p.add_argument("--before", nargs="*", default=None, help="result files of an earlier measurement, shown beside (before → now)")
    p = sub.add_parser("report", help="Markdown tables over eval result files, side by side")
    p.add_argument("files", nargs="+")
    p.add_argument("--labels", nargs="*", default=None)
    p = sub.add_parser("report2", help="Markdown tables over the result files of eval2, taken together")
    p.add_argument("files", nargs="+")
    args = ap.parse_args(argv)

    if args.cmd == "eval_room":
        return evaluate_room.main(args)
    if args.cmd == "report_room":
        print(evaluate_room.report(args.files, args.before))
        return 0
    if args.cmd == "replay":
        from .world import World
        world = World.replay(args.record)
        print(json.dumps({"rows": int(world.record.shape[0]), "state_hash": world.state_hash(), "time": world.time}))
        world.close()
        return 0
    if args.cmd == "demo":
        from . import scenarios, skills
        from .png import write_png
        if args.scenario not in scenarios.RUNNERS:
            print(f"unknown scenario {args.scenario!r}; scenarios: {sorted(scenarios.RUNNERS)}", file=sys.stderr)
            return 2
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        frames = []

        def grab(world) -> None:
            if world.tick % 25 == 0:
                frames.append(world.render("front"))

        r = scenarios.RUNNERS[args.scenario](args.seed, args.index, on_step=None if args.no_frames else grab)
        world = r["world"]
        rec = world.save_record(out / "record.json")
        for i, frame in enumerate(frames):
            write_png(out / f"frame_{i:03d}.png", frame)
        statuses = {k: [v.ok, v.reason] for k, v in r.items() if isinstance(v, skills.Status)}
        summary = {"scenario": args.scenario, "seed": args.seed, "index": args.index, "success": bool(r["success"]),
                   "rows": rec["n_rows"], "state_hash": rec["state_hash"], "statuses": statuses, "frames": len(frames)}
        (out / "summary.json").write_text(json.dumps(summary, indent=1))
        print(json.dumps(summary))
        world.close()
        return 0
    if args.cmd == "scenarios":
        from . import scenarios
        r = scenarios.evaluate(args.name, args.seed, args.n)
        for t in r["trials"]:
            print(scenarios.summary_line(t))
        print(f"{args.name}: {r['successes']} of {r['n']}")
        return 0
    if args.cmd == "eval":
        return evaluate.main(args)
    if args.cmd == "eval2":
        return evaluate_two_arms.main(args)
    if args.cmd == "report":
        print(evaluate.report(args.files, args.labels))
        return 0
    if args.cmd == "report2":
        print(evaluate_two_arms.report(args.files))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
