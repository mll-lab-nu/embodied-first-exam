#!/usr/bin/env python3
"""Independently audit a Slotted Post Ring oracle execution from its recorded per-tick states."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path, help="run_slotted_post_ring_oracle.py output directory")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--require-native-success", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    args.run, args.output = args.run.resolve(), args.output.resolve()
    if args.worker:
        from topogym.planning.slotted_post_ring.audit import audit_execution
        from topogym.utils.io import write_json_atomic
        report = audit_execution(args.run, args.output, require_native_success=args.require_native_success)
        write_json_atomic(args.output/"execution_audit.json", report)
        print(json.dumps(report, indent=2), flush=True)
        return 0 if report["passed"] else 2
    args.output.mkdir(parents=True, exist_ok=False)
    from scripts.test_policy_cube_transfer import snapshot
    from topogym.utils.process_limits import run_guarded
    source = snapshot(args.output)
    relative = Path("harbor_templates/topogym/common/rcb_topogym.py")
    target = source / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / relative, target)
    manifest_path = args.output / "source_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest[str(relative)] = hashlib.sha256(target.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    command = [sys.executable, str(source/"scripts/audit_slotted_post_ring_oracle.py"), "--worker",
               "--run", str(args.run), "--output", str(args.output)]
    if args.require_native_success:
        command.append("--require-native-success")
    (args.output/"invocation.json").write_text(json.dumps(dict(command=command), indent=2)+"\n")
    environment = dict(os.environ, PYTHONPATH=str(source), OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
                       OPENBLAS_NUM_THREADS="1", PYTHONUNBUFFERED="1")
    result = run_guarded(command, args.output, cwd=source, env=environment)
    print(f"exit={result}; {args.output}", flush=True)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
