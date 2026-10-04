"""Shared CLI, source snapshots and resource supervision for knot oracle runners."""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from .artifacts import ROOT, default_instance, task_dir, validate_instance
from .robot_oracle import TIERS
from topogym.utils.io import sha256_file, write_json_atomic


def parser(*, branching=False):
    p = argparse.ArgumentParser(description="Frozen-instance knot oracle; records JOINT_ABS and actual physics ticks.")
    p.add_argument("--variation", choices=sorted(TIERS), required=True)
    p.add_argument("--instance", type=Path, help="frozen instance.json; default: current task directory (historical inputs must be explicit)")
    p.add_argument("--output", type=Path, required=True, help="new evidence directory")
    p.add_argument("--close", type=float, default=.005, help="pinch opening width in metres; native robot limits apply")
    p.add_argument("--end-offset", type=float, default=.035, help="end-spread grasp distance from each tip, m")
    p.add_argument("--full-pull", action=argparse.BooleanOptionalAction, default=None,
                   help="continue after the first removed crossing; default on for hard")
    p.add_argument("--max-pull", type=float, help="withdraw distance, m; default .55 for hard, .6 otherwise")
    p.add_argument("--speed", type=float, default=.04, help="Cartesian pull speed parameter, m/s")
    p.add_argument("--max-decisions", type=int, default=16)
    p.add_argument("--settle", type=float, default=10., help="final settling budget, simulated seconds")
    p.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    if branching:
        p.add_argument("--tight-curl-m", type=float, default=.12, help="diagnostic curl span; does not reject a branch")
        p.add_argument("--max-nonprogress-decisions", type=int, default=None,
                       help="optional crossing-progress budget; disabled by default")
        p.add_argument("--resume", type=Path, help="trusted local checkpoints/d<k>_*.pkl; verified before replay")
        p.add_argument("--wait-hours", type=float, default=0.,
                       help="optional root-level wait for control/next.json after automatic candidates are exhausted")
        p.add_argument("--max-attempts", type=int, default=128, help="whole-search candidate budget")
    return p


def normalize(args):
    args.instance = (args.instance or default_instance(args.variation)).resolve()
    args.output = args.output.resolve()
    hard = args.variation == "knot_untying_hard"
    if args.full_pull is None:
        args.full_pull = hard
    if args.max_pull is None:
        args.max_pull = .55 if hard else .6
    validate_parameters(vars(args))
    if getattr(args, "resume", None):
        args.resume = args.resume.resolve()
    return args


from .parameters import validate_parameters


def freeze_sources(output):
    from scripts.test_policy_cube_transfer import snapshot
    source = snapshot(output)
    manifest = json.loads((output/"source_manifest.json").read_text())
    for tier in TIERS:
        path = task_dir(tier)/"environment/rcb_topogym.py"
        relative = path.relative_to(ROOT)
        destination = source/relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        manifest[str(relative)] = sha256_file(destination)
    write_json_atomic(output/"source_manifest.json", manifest)
    return source


def supervise(command, output, source):
    import psutil
    env = dict(os.environ, PYTHONPATH=str(source), PYTHONDONTWRITEBYTECODE="1")
    env.setdefault("RCB_SESSION_LOG", str(output/"session_events.jsonl"))
    # Nyx stores a cache in cwd. Keep frozen source bytes separate from runtime cache.
    with (output/"run.log").open("w") as log, (output/"resources.jsonl").open("w") as resources:
        p = subprocess.Popen(command, cwd=output, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            while p.poll() is None:
                row = dict(time=time.time(), cpu_percent=psutil.cpu_percent(), memory_percent=psutil.virtual_memory().percent)
                resources.write(json.dumps(row)+"\n")
                resources.flush()
                if row["memory_percent"] >= 90:
                    import signal
                    os.killpg(p.pid, signal.SIGTERM)
                    try:
                        p.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        os.killpg(p.pid, signal.SIGKILL)
                    write_json_atomic(output/"supervisor.json", dict(status="memory_limit", **row))
                    return 1
                time.sleep(5)
        finally:
            if p.poll() is None:
                import signal
                os.killpg(p.pid, signal.SIGTERM)
                try:
                    p.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(p.pid, signal.SIGKILL)
            p.wait()
    return p.returncode


def main(argv=None, *, branching=False):
    p = parser(branching=branching)
    raw = list(sys.argv[1:] if argv is None else argv)
    try:
        args = normalize(p.parse_args(raw))
        validate_instance(args.instance, args.variation)
    except (ValueError, KeyError, FileNotFoundError) as error:
        p.error(str(error))
    if not args.worker:
        args.output.mkdir(parents=True, exist_ok=False)
        write_json_atomic(args.output/"arguments.json", vars(args))
        source = freeze_sources(args.output)
        script = "run_knot_branching.py" if branching else "run_knot_oracle.py"
        command = [sys.executable, str(source/"scripts/oracle_runners"/script), *raw,
                   "--instance", str(args.instance), "--output", str(args.output), "--worker"]
        if getattr(args, "resume", None):
            command += ["--resume", str(args.resume)]
        write_json_atomic(args.output/"command.json", command)
        return supervise(command, args.output, source)
    engine = None
    try:
        if branching:
            from .branching import Branching
            engine = Branching(args)
        else:
            from .robot_oracle import Runner
            engine = Runner(args)
        return 0 if engine.run() else 1
    finally:
        if engine is not None:
            (engine.r if branching else engine).session.close()
