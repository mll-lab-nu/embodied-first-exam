#!/usr/bin/env python3
"""Independently audit a frozen Claws execution and its imported geometry."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--require-native-success", action="store_true")
    parser.add_argument("--tolerate-piece-contact", action="store_true", help="Allow bounded piece/piece sliding contact with independent triangle-depth checks")
    parser.add_argument("--piece-force-n", type=float, default=8.)
    parser.add_argument("--contact-depth-mm", type=float, default=.5)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    args.run, args.output = args.run.resolve(), args.output.resolve()
    if args.worker:
        from topogym.planning.interlocked_claws.audit import audit_execution
        from topogym.utils.io import write_json_atomic
        report = audit_execution(args.run, args.output, require_native_success=args.require_native_success,
                                 tolerate_piece_contact=args.tolerate_piece_contact, piece_force_n=args.piece_force_n,
                                 contact_depth_limit_m=args.contact_depth_mm/1000)
        write_json_atomic(args.output/"execution_audit.json", report)
        print(json.dumps(report, indent=2), flush=True)
        return 0 if report["passed"] else 2
    args.output.mkdir(parents=True, exist_ok=False)
    from scripts.test_policy_cube_transfer import snapshot
    from topogym.utils.process_limits import run_guarded
    source = snapshot(args.output)
    command = [sys.executable, str(source/"scripts/audit_claws_oracle.py"), "--worker",
               "--run", str(args.run), "--output", str(args.output)]
    if args.require_native_success:
        command.append("--require-native-success")
    if args.tolerate_piece_contact:
        command.append("--tolerate-piece-contact")
    command += ["--piece-force-n", str(args.piece_force_n), "--contact-depth-mm", str(args.contact_depth_mm)]
    (args.output/"invocation.json").write_text(json.dumps(dict(command=command), indent=2)+"\n")
    environment = dict(os.environ, PYTHONPATH=str(source), OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
                       OPENBLAS_NUM_THREADS="1", PYTHONUNBUFFERED="1")
    result = run_guarded(command, args.output, cwd=source, env=environment)
    print(f"exit={result}; {args.output}", flush=True)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
