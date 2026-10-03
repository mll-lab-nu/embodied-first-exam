#!/usr/bin/env python3
"""Independently audit a recorded Blanket oracle run from its tick evidence; no physics is advanced."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-native-success", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    from topogym.planning.blanket_flatten.audit import audit_execution
    from topogym.utils.io import to_jsonable, write_json_atomic
    report = audit_execution(args.run, args.output, require_native_success=args.require_native_success)
    report["run"] = str(args.run.resolve())
    write_json_atomic(args.output/"execution_audit.json", to_jsonable(report))
    print(report["status"], "accepted_proof" if report["accepted_proof"] else "", flush=True)
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
