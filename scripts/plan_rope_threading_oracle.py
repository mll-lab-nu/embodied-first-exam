#!/usr/bin/env python3
"""Freeze and verify a Rope Threading object-only witness; no robot success claim.

The witness uses a follow-the-leader rope model with a two-hand relay
schedule. Its assumptions and limits are written into object_witness.json.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--variation", choices=("easy", "medium", "hard"), default="medium")
    parser.add_argument("--clearance-mm", type=float, default=1.)
    parser.add_argument("--hand-clearance-mm", type=float, default=3.)
    parser.add_argument("--step-mm", type=float, default=2.)
    parser.add_argument("--route-json", type=Path, help="Route parameter overrides (JSON object)")
    parser.add_argument("--relay-json", type=Path, help="Per-ring relay plan (JSON list)")
    parser.add_argument("--audit", type=Path, help="Rebuild and verify an existing object_witness.json")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 0 < args.clearance_mm < 10 or not 0 < args.hand_clearance_mm < 20 or not 0 < args.step_mm <= 10:
        parser.error("Use clearances between 0 and 10/20 mm and a travel step of at most 10 mm")
    args.output = args.output.resolve()
    if args.worker:
        from topogym.planning.rope_threading.object_oracle import plan_object_path, audit_object_path
        from topogym.utils.io import write_json_atomic, to_jsonable
        start = time.monotonic()
        def progress(sigma, total, minimum):
            print(f"travel {sigma:.3f}/{total:.3f} m, rope lower bound {minimum*1000:.2f} mm", flush=True)
        if args.audit:
            witness = json.loads(args.audit.read_text())
            report = audit_object_path(witness, args.output, progress=progress)
            name = "object_audit.json"
        else:
            route = json.loads(args.route_json.read_text()) if args.route_json else None
            relay = json.loads(args.relay_json.read_text()) if args.relay_json else None
            report, problem, track = plan_object_path(args.output, variation=args.variation, seed=args.seed,
                route=route, relay=relay, margin_m=args.clearance_mm/1000, hand_margin_m=args.hand_clearance_mm/1000,
                step_m=args.step_mm/1000, progress=progress)
            import numpy as np
            np.savez_compressed(args.output/"witness_track.npz", track_points_m=track.points, track_tau_m=track.tau,
                                stations_m=problem.stations_m, tip_route_m=track.tip_route, initial_m=problem.initial_m)
            name = "object_witness.json"
        report["wall_time_s"] = time.monotonic()-start
        write_json_atomic(args.output/name, to_jsonable(report))
        print(report["status"], flush=True)
        return 0 if report["status"] == "object_witness_verified" else 2

    args.output.mkdir(parents=True, exist_ok=False)
    from scripts.test_policy_cube_transfer import snapshot
    from topogym.utils.process_limits import run_guarded
    source = snapshot(args.output)
    command = [sys.executable, str(source/"scripts/plan_rope_threading_oracle.py"), "--worker",
               "--output", str(args.output), "--seed", str(args.seed), "--variation", args.variation,
               "--clearance-mm", str(args.clearance_mm), "--hand-clearance-mm", str(args.hand_clearance_mm),
               "--step-mm", str(args.step_mm)]
    for flag, path in (("--route-json", args.route_json), ("--relay-json", args.relay_json), ("--audit", args.audit)):
        if path is not None:
            target = args.output/("submitted_"+path.name)
            target.write_bytes(path.read_bytes())
            command += [flag, str(target)]
    (args.output/"invocation.json").write_text(json.dumps(dict(command=command), indent=2)+"\n")
    environment = dict(os.environ, PYTHONPATH=str(source), OMP_NUM_THREADS="1",
                       MKL_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")
    result = run_guarded(command, args.output, cwd=source, env=environment)
    print(f"exit={result}; {args.output}", flush=True)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
