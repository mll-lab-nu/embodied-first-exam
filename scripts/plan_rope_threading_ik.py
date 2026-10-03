#!/usr/bin/env python3
"""Convert a Rope Threading object witness into checked dual-arm ALOHA IK samples.

Candidate relay plans (which hand pushes/receives at each ring) and arm
assignments are tried in order. Each candidate is first re-certified at the
rope level (object_oracle.certify) and then converted to joint samples with
collision checks. Sampled IK evidence is not a physical execution.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


from topogym.planning.rope_threading.profiles import candidate_plans


def worker(args):
    import traceback
    from topogym.utils.io import write_json_atomic
    try:
        return _worker(args)
    except Exception:
        path = args.output/"relay_ik.json"
        report = json.loads(path.read_text()) if path.exists() else {}
        report.update(status="failed", robot_ik_verified=False, robot_execution_verified=False,
                      task_success=False, error=traceback.format_exc())
        write_json_atomic(path, report)
        raise


def _worker(args):
    from topogym.planning.rope_threading.geometry import frozen_problem
    from topogym.planning.rope_threading.object_oracle import (Track, build_tip_route, certify, relay_schedule,
                                                               material_budget)
    from topogym.planning.rope_threading.relay_ik import plan_relay_ik
    from topogym.planning.rope_threading.relay_kinematics import RopeThreadingKinematics
    from topogym.utils.io import write_json_atomic, to_jsonable
    started = time.monotonic()
    witness = json.loads(args.witness.read_text())
    problem = frozen_problem(args.output, variation=witness["variation_id"], seed=witness["seed"])
    for key in ("task_id", "variation_id", "model_revision", "terminal_revision", "instance_id",
                "asset_sha256", "required_crossings", "rings", "robot_scene"):
        if to_jsonable(witness[key]) != to_jsonable(problem.identity[key]):
            raise ValueError(f"Witness {key} differs from the rebuilt task")
    controls, dense, route = build_tip_route(problem, witness["route"]["parameters"])
    track = Track(problem.initial_m, dense)
    if witness.get("status") != "object_witness_verified":
        raise ValueError("An accepted object witness is required")
    plans = json.loads(args.plans_json.read_text()) if args.plans_json else candidate_plans(problem.variation)
    assignments = [dict(A=a.split("-")[0], B=a.split("-")[1]) for a in args.assignments.split(",")]
    report = dict(schema_version=1, scope="sampled dual-arm IK conversion of the object witness; no physics",
                  **{k: witness[k] for k in ("task_id", "variation_id", "instance_id", "seed", "model_revision")},
                  witness=str(args.witness), status="planning", accepted=None, attempts=[],
                  robot_ik_verified=False, robot_execution_verified=False, task_success=False)
    write_json_atomic(args.output/"relay_ik.json", to_jsonable(report))
    print("building kinematic scene", flush=True)
    kin = RopeThreadingKinematics(problem)
    hands = witness["relay"]["parameters"]
    certificate = witness["certificate"]
    sigma_final = float(witness["schedule"]["sigma_final"])
    accepted = None
    for name, plan in plans:
        try:
            holds, events = relay_schedule(problem, track, plan, hands, sigma_final)
            rope = certify(problem, track, holds, sigma_final=sigma_final,
                           margin_m=float(certificate["requested_margin_m"]),
                           hand_margin_m=float(certificate["requested_hand_margin_m"]),
                           hand_radius_m=float(hands["hand_radius_m"]), step_m=float(certificate["travel_step_m"]))
        except ValueError as error:
            report["attempts"].append(dict(plan=name, stage="schedule", passed=False, error=str(error)))
            write_json_atomic(args.output/"relay_ik.json", to_jsonable(report))
            continue
        if not rope["passed"]:
            report["attempts"].append(dict(plan=name, stage="object_certificate", passed=False, failures=rope["failures"]))
            write_json_atomic(args.output/"relay_ik.json", to_jsonable(report))
            continue
        for assignment in assignments:
            print(f"plan {name} assignment {assignment}", flush=True)
            def progress(index, total, accepted_phase):
                print(f"  hold {index+1}/{total}: {'ok '+str(accepted_phase['family'])+' '+str(accepted_phase['roll_deg']) if accepted_phase else 'FAILED'}", flush=True)
            result, samples = plan_relay_ik(problem, witness, assignment=assignment, kin=kin, holds=holds,
                                            track=track, progress=progress,
                                            options=dict(hold_step_m=args.hold_step_mm/1000))
            attempt = dict(plan=name, assignment=assignment, stage="ik", passed=result["passed"],
                           failed_hold=result.get("failed_hold"), phases=result["phases"],
                           wall_s=result["wall_time_s"], sample_count=result["sample_count"])
            report["attempts"].append(attempt)
            write_json_atomic(args.output/"relay_ik.json", to_jsonable(report))
            if result["passed"]:
                accepted = dict(plan=name, plan_entries=plan, assignment=assignment, holds=holds, events=events,
                                object_certificate=dict(rope, final_points_m=None, interval_lower_bounds=None),
                                material_budget=material_budget(problem, track, sigma_final), ik=result)
                from topogym.planning.rope_threading.relay_artifact import save_samples
                save_samples(args.output/"relay_samples.npz", samples, kin=kin, track=track, holds=holds,
                             identity=problem.identity, plan=name, assignment=assignment, options=result["options"])
                break
        if accepted:
            break
    report.update(accepted=accepted, status="robot_ik_verified" if accepted else "robot_ik_not_found",
                  robot_ik_verified=bool(accepted), wall_time_s=time.monotonic()-started,
                  limitations=["Sampled IK/collision evidence at discrete travel values; no continuous certificate",
                               "Follow-the-leader rope geometry; unheld regrasps assume the rope keeps its modelled shape",
                               "No physics, no contact, no Task success"])
    write_json_atomic(args.output/"relay_ik.json", to_jsonable(report))
    print(report["status"], flush=True)
    return 0 if accepted else 2



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--witness", type=Path, required=True, help="object_witness.json from plan_rope_threading_oracle.py")
    parser.add_argument("--plans-json", type=Path, help="JSON list of [name, plan] pairs replacing the built-in candidates")
    parser.add_argument("--assignments", default="right-left", help="A-B side assignments to try, comma separated")
    parser.add_argument("--hold-step-mm", type=float, default=10.)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    args.output = args.output.resolve()
    if not 0 < args.hold_step_mm <= 10:
        parser.error("--hold-step-mm must be between 0 and 10")
    if any(a not in ("right-left", "left-right") for a in args.assignments.split(",")):
        parser.error("--assignments must contain right-left or left-right")
    if args.worker:
        return worker(args)

    args.output.mkdir(parents=True, exist_ok=False)
    from scripts.test_policy_cube_transfer import snapshot
    from topogym.utils.process_limits import run_guarded
    source = snapshot(args.output)
    witness = args.output/"submitted_witness.json"
    witness.write_bytes(args.witness.read_bytes())
    command = [sys.executable, str(source/"scripts/plan_rope_threading_ik.py"), "--worker", "--output", str(args.output),
               "--witness", str(witness), "--assignments", args.assignments, "--hold-step-mm", str(args.hold_step_mm)]
    if args.plans_json:
        target = args.output/"submitted_plans.json"
        target.write_bytes(args.plans_json.read_bytes())
        command += ["--plans-json", str(target)]
    (args.output/"invocation.json").write_text(json.dumps(dict(command=command), indent=2)+"\n")
    environment = dict(os.environ, PYTHONPATH=str(source), OMP_NUM_THREADS="1", MKL_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")
    result = run_guarded(command, args.output, cwd=source, env=environment)
    print(f"exit={result}; {args.output}", flush=True)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
