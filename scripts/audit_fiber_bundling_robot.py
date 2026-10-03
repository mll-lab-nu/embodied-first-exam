#!/usr/bin/env python3
"""Audit saved Fiber states against their frozen Task, without a simulator."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=lambda p: Path(p).resolve(), required=True)
    parser.add_argument("--output", type=lambda p: Path(p).resolve(), required=True)
    args = parser.parse_args()
    frozen = args.run / "source_snapshot"
    if not (frozen / "topogym/tasks/fiber_bundling/common.py").is_file():
        parser.error("Run has no frozen Fiber Task source")
    sys.path.insert(0, str(frozen))
    source = Path(__file__).resolve().parents[1] / "topogym/planning/fiber_bundling/audit.py"
    spec = importlib.util.spec_from_file_location("fiber_saved_state_audit", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.audit_run(args.run, args.output)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
