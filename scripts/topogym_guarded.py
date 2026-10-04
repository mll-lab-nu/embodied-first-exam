#!/usr/bin/env python3
"""Run one owned command with the project's memory limit; never kill unrelated jobs."""
import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from topogym.utils.process_limits import run_guarded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cwd", type=Path, default=ROOT)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("command required")
    args.output.mkdir(parents=True, exist_ok=False)
    return run_guarded(command, args.output, cwd=args.cwd, env=dict(os.environ))


if __name__ == "__main__":
    raise SystemExit(main())
