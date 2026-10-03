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
                                                               material_budget, support_regrasps)
    from topogym.planning.rope_threading.relay_ik import plan_relay_ik
    from topogym.planning.rope_threading.relay_kinematics import RopeThreadingKinematics
    from topogym.utils.io import write_json_atomic, to_jsonable
    started = time.monotonic()
    witness = json.loads(args.witness.read_text())
    problem = frozen_problem(args.output, variation=witness["variation_id"], seed=witness["seed"],
                             task_parameters=witness.get("task_parameters"))
    for key in ("task_id", "variation_id", "model_revision", "terminal_revision", "instance_id",
                "asset_sha256", "required_crossings", "rings", "robot_scene"):
        if to_jsonable(witness[key]) != to_jsonable(problem.identity[key]):
            raise ValueError(f"Witness {key} differs from the rebuilt task")
    controls, dense, route = build_tip_route(problem, witness["route"]["parameters"])
    track = Track(problem.initial_m, dense)
    if witness.get("status") != "object_witness_verified":
        raise ValueError("An accepted object witness is required")
    plans = json.loads(args.plans_json.read_text()) if args.plans_json else candidate_plans(problem.variation)
    reused = None
    if args.reuse_samples:
        from topogym.planning.rope_threading.relay_artifact import load_plan
        reused = load_plan(args.reuse_samples)
        if not args.reuse_leading_holds:
            plans = [(name, plan) for name, plan in plans if name == reused[1]["plan"]]
        if not plans:
            raise ValueError("Cached recipe is not in the target candidate plans")
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
            if args.support_regrasps:
                holds = support_regrasps(holds, track.rope_length, separation_m=args.support_separation)
                # Preserve the constant-travel ordering in the report as well
                # as the robot samples: keeper acquire, old release, new
                # acquire, keeper release.
                keepers = {h["sigma_start"]: h for h in holds if h["role"] == "keeper"}
                supported_events = []
                for event in events:
                    keeper = keepers.get(event.get("sigma"))
                    if keeper and event["kind"] == "release" and event.get("reason") == "regrasp":
                        supported_events.append(dict(kind="grasp", hand=keeper["hand"], role="keeper",
                            ring=keeper["ring"], sigma=keeper["sigma_start"],
                            station_behind_tip_m=keeper["station_behind_tip_m"],
                            position_m=track.rope([keeper["station_m"]], keeper["sigma_start"])[0].tolist()))
                        event = dict(event, reason="supported_regrasp")
                    supported_events.append(event)
                    if keeper and event["kind"] == "grasp" and event["hand"] != keeper["hand"]:
                        supported_events.append(dict(kind="release", hand=keeper["hand"], sigma=keeper["sigma_start"],
                                                     reason="regrasp_completed"))
                events = supported_events
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
            def attempt_progress(index, phase):
                write_json_atomic(args.output/"ik_progress.json", to_jsonable(dict(
                    plan=name, assignment=assignment, hold_index=index, phase=phase,
                    wall_time_s=time.monotonic()-started)))
            if reused is not None:
                from topogym.planning.calibration_tools.adapters.rope_threading import recheck_relay
                from topogym.planning.rope_threading.relay_artifact import validate_hold_timeline
                selected = reused[0]
                if args.reuse_leading_holds:
                    from topogym.planning.rope_threading.relay_artifact import leading_holds
                    selected = leading_holds(*reused, holds, assignment)
                validate_hold_timeline(selected, holds, assignment)
                if not abs(float(selected[-1]["sigma"])-sigma_final) < 1e-8:
                    raise ValueError("Cached relay ends at a different material travel")
                result, samples = recheck_relay(selected, reused[1], problem=problem, kin=kin, track=track, assignment=assignment,
                    check_options=dict(fixture_margin_m=args.fixture_margin_mm/1000,
                                       rope_margin_m=args.rope_margin_mm/1000, inter_arm_m=args.inter_arm_mm/1000,
                                       max_penetration_m=args.max_penetration_mm/1000))
                from topogym.utils.io import sha256_file
                result["reused_samples_sha256"] = sha256_file(args.reuse_samples)
                result["reused_leading_holds"] = args.reuse_leading_holds
            else:
                result, samples = plan_relay_ik(problem, witness, assignment=assignment, kin=kin, holds=holds,
                                                track=track, progress=progress,
                                                attempt_progress=attempt_progress,
                                                options=dict(hold_step_m=args.hold_step_mm/1000,
                                                             fixture_margin_m=args.fixture_margin_mm/1000,
                                                             max_penetration_m=args.max_penetration_mm/1000,
                                                             rope_margin_m=args.rope_margin_mm/1000,
                                                             inter_arm_m=args.inter_arm_mm/1000,
                                                             material_tangent=args.material_tangent,
                                                             material_tangent_delay_m=args.material_tangent_delay,
                                                             material_tangent_min_lead_m=args.material_tangent_min_lead,
                                                             material_axis_tolerance_deg=args.material_axis_tolerance_deg,
                                                             recover_wrist_branch=args.recover_wrist_branch,
                                                             max_holds=args.max_holds))
            attempt = dict(plan=name, assignment=assignment, stage="ik", passed=result["passed"],
                           failed_hold=result.get("failed_hold"), phases=result["phases"],
                           wall_s=result["wall_time_s"], sample_count=result["sample_count"])
            if result.get("failures"):
                attempt["failures"] = result["failures"]
            report["attempts"].append(attempt)
            if not result["passed"] and samples:
                from topogym.planning.rope_threading.relay_artifact import save_samples
                partial = args.output/f"prefix_{len(report['attempts']):02d}.npz"
                save_samples(partial, samples, kin=kin, track=track, holds=holds,
                             identity=problem.identity, plan=name, assignment=assignment, options=result["options"],
                             complete_relay=False)
                attempt["verified_prefix"] = str(partial)
            write_json_atomic(args.output/"relay_ik.json", to_jsonable(report))
            if result["passed"]:
                accepted = dict(plan=name, plan_entries=plan, assignment=assignment, holds=holds, events=events,
                                object_certificate=dict(rope, final_points_m=None, interval_lower_bounds=None),
                                material_budget=material_budget(problem, track, sigma_final), ik=result)
                from topogym.planning.rope_threading.relay_artifact import save_samples
                save_samples(args.output/"relay_samples.npz", samples, kin=kin, track=track, holds=holds,
                             identity=problem.identity, plan=name, assignment=assignment, options=result["options"],
                             complete_relay=result.get("complete_relay", True))
                break
        if accepted:
            break
    report.update(accepted=accepted, status="robot_ik_verified" if accepted else "robot_ik_not_found",
                  robot_ik_verified=bool(accepted), wall_time_s=time.monotonic()-started,
                  limitations=["Sampled IK/collision evidence at discrete travel values; no continuous certificate",
                               "Follow-the-leader geometry is a model; physical shape and grasp retention require execution",
                               "No physics, no contact, no Task success"])
    if accepted and not accepted["ik"].get("complete_relay", True):
        report["status"] = "robot_ik_prefix_verified"
    write_json_atomic(args.output/"relay_ik.json", to_jsonable(report))
    print(report["status"], flush=True)
    return 0 if accepted else 2



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--witness", type=Path, required=True, help="object_witness.json from plan_rope_threading_oracle.py")
    parser.add_argument("--plans-json", type=Path, help="JSON list of [name, plan] pairs replacing the built-in candidates")
    parser.add_argument("--reuse-samples", type=Path,
                        help="Recheck a cached relay against target fixtures and rope; requires a matching recipe/path")
    parser.add_argument("--reuse-leading-holds", action="store_true", help="Recertify exact leading holds of a complete cached relay against a shorter full target")
    parser.add_argument("--assignments", default="right-left", help="A-B side assignments to try, comma separated")
    parser.add_argument("--hold-step-mm", type=float, default=10.)
    parser.add_argument("--fixture-margin-mm", type=float, default=5.)
    parser.add_argument("--rope-margin-mm", type=float, default=3.)
    parser.add_argument("--inter-arm-mm", type=float, default=10.)
    parser.add_argument("--max-penetration-mm", type=float, default=0., help="Explicit allowed FCL contact depth estimate; native contact still governs execution")
    parser.add_argument("--material-tangent", action="store_true",
                        help="Keep the grasped material axis aligned with the modelled rope tangent")
    parser.add_argument("--support-regrasps", action="store_true",
                        help="Keep the other hand attached while changing material stations")
    parser.add_argument("--recover-wrist-branch", action="store_true",
                        help="Try a checked near-stationary wrist branch change when local IK fails")
    parser.add_argument("--support-separation", type=float, default=.10,
                        help="Material separation from the new grasp to its temporary keeper (m)")
    parser.add_argument("--material-tangent-delay", type=float, default=0.,
                        help="Delay first-hold tangent alignment until this travel in metres, then turn gradually")
    parser.add_argument("--max-holds", type=int, choices=range(1, 5), help="Export an explicitly partial calibration probe")
    parser.add_argument("--material-axis-tolerance-deg", type=float, default=0.,
                        help="Permit bounded material-axis tilt while avoiding IK singularities")
    parser.add_argument("--material-tangent-min-lead", type=float, default=0.,
                        help="Only constrain material direction when the free leading end is at least this long (m)")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    args.output = args.output.resolve()
    if not 0 < args.hold_step_mm <= 10:
        parser.error("--hold-step-mm must be between 0 and 10")
    if not 0 <= args.max_penetration_mm <= 10:
        parser.error("--max-penetration-mm must be in [0, 10]")
    margins = (args.fixture_margin_mm, args.rope_margin_mm, args.inter_arm_mm)
    if not all(0 <= v <= 20 for v in margins):
        parser.error("Collision margins must be in [0, 20] mm")
    if args.reuse_leading_holds and not args.reuse_samples:
        parser.error("--reuse-leading-holds requires --reuse-samples")
    if not 0 <= args.material_tangent_delay <= .5 or (args.material_tangent_delay and not args.material_tangent):
        parser.error("--material-tangent-delay requires --material-tangent and must be in [0, .5]")
    if args.material_tangent and args.reuse_samples:
        parser.error("--material-tangent replans poses and cannot be combined with --reuse-samples")
    if args.recover_wrist_branch and args.reuse_samples:
        parser.error("--recover-wrist-branch replans joints and cannot reuse samples")
    if not 0.05 <= args.support_separation <= .3:
        parser.error("--support-separation must be in [.05, .3]")
    if args.max_holds and args.reuse_samples:
        parser.error("--max-holds cannot be combined with --reuse-samples")
    if not 0 <= args.material_axis_tolerance_deg <= 30 or (args.material_axis_tolerance_deg and not args.material_tangent):
        parser.error("--material-axis-tolerance-deg requires --material-tangent and must be in [0, 30]")
    if not 0 <= args.material_tangent_min_lead <= .3 or (args.material_tangent_min_lead and not args.material_tangent):
        parser.error("--material-tangent-min-lead requires --material-tangent and must be in [0, .3]")
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
               "--witness", str(witness), "--assignments", args.assignments, "--hold-step-mm", str(args.hold_step_mm),
               "--fixture-margin-mm", str(args.fixture_margin_mm), "--rope-margin-mm", str(args.rope_margin_mm),
               "--inter-arm-mm", str(args.inter_arm_mm), "--max-penetration-mm", str(args.max_penetration_mm)]
    if args.plans_json:
        target = args.output/"submitted_plans.json"
        target.write_bytes(args.plans_json.read_bytes())
        command += ["--plans-json", str(target)]
    if args.reuse_samples:
        target = args.output/"submitted_samples.npz"
        target.write_bytes(args.reuse_samples.read_bytes())
        command += ["--reuse-samples", str(target)]
    if args.reuse_leading_holds:
        command += ["--reuse-leading-holds"]
    if args.material_tangent:
        command += ["--material-tangent", "--material-tangent-delay", str(args.material_tangent_delay),
                    "--material-axis-tolerance-deg", str(args.material_axis_tolerance_deg),
                    "--material-tangent-min-lead", str(args.material_tangent_min_lead)]
    if args.max_holds:
        command += ["--max-holds", str(args.max_holds)]
    if args.support_regrasps:
        command += ["--support-regrasps", "--support-separation", str(args.support_separation)]
    if args.recover_wrist_branch:
        command += ["--recover-wrist-branch"]
    (args.output/"invocation.json").write_text(json.dumps(dict(command=command), indent=2)+"\n")
    environment = dict(os.environ, PYTHONPATH=str(source), OMP_NUM_THREADS="1", MKL_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")
    result = run_guarded(command, args.output, cwd=source, env=environment)
    print(f"exit={result}; {args.output}", flush=True)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
