#!/usr/bin/env python3
"""Snapshot and run local Genesis/Nyx segment acceptance; no model/API calls."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]


def run_case(output, *, case="cube", seed=0, split=False, robot="panda_robotiq", mode="EE_ABS",
             speed_scale=1., physics_dt=.0025, control_decimation=10, solver_substeps=4,
             tracking_hold_seconds=2.5):
    from topogym.simulator import Env, SimulatorConfig, SegmentRunner
    from topogym.utils.io import write_json_atomic, to_jsonable
    from fixtures.cube_transfer import register_cube_transfer
    from fixtures.cube_policy import cube_policy
    from contextlib import nullcontext
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    report = dict(status="running", case=case, seed=seed, split=split, robot=robot, control_mode=mode,
                  scope="actual Genesis/Nyx low-level policy segment acceptance", started=time.time())
    config = SimulatorConfig(task_id="cube_transfer" if case in {"cube", "empty_grasp"} else
                             "cast_coil" if robot == "aloha" else "hedgehog_in_cage",
                             robot_id=robot, control_mode=mode, observation_mode="EE",
                             enable_privileged=True, max_physics_steps=round(25./physics_dt),
                             physics_dt_s=physics_dt, control_decimation=control_decimation,
                             solver_substeps=solver_substeps)
    report["config"] = to_jsonable(config)
    from importlib.metadata import version, PackageNotFoundError
    report["packages"] = {}
    for package in ("genesis-world", "gs-nyx", "gs-nyx-plugin", "torch", "numpy"):
        try:
            report["packages"][package] = version(package)
        except PackageNotFoundError:
            report["packages"][package] = None
    report["thresholds"] = dict(lift_m=.05, airborne_translation_m=.15, placement_error_m=.02,
        table_clearance_m=.003, settled_linear_speed_m_s=.01, settled_angular_speed_rad_s=.1,
        stable_duration_s=.5, gripper_withdrawal_m=.05, held_duration_s=.2,
        held_relative_displacement_m=.01, held_tcp_distance_m=.07)
    if case == "interfaces":
        report["thresholds"] = dict(tcp_position_m=.003, tcp_orientation_rad=.01,
                                    joint_tracking_rad=.005,
                                    gripper_native=.003 if robot == "aloha" else .03)
        report["additional_policy_hold_limit_s"] = tracking_hold_seconds
    write_json_atomic(output / "report.json", report)
    try:
        import torch
        torch.set_num_threads(1)
        report["torch_num_threads"] = torch.get_num_threads()
        report["cuda_available"] = torch.cuda.is_available()
        if not report["cuda_available"]:
            report["status"] = "blocked"
            raise RuntimeError("CUDA unavailable; Nyx acceptance requires CUDA")
        report["gpu"] = torch.cuda.get_device_name()
        write_json_atomic(output / "report.json", report)
        with register_cube_transfer() if case in {"cube", "empty_grasp"} else nullcontext():
            with Env(config) as env:
                env.reset(seed=seed)
                costs = {}
                def timed(obj, name):
                    original = getattr(obj, name)
                    key = type(obj).__name__ + "." + name
                    costs[key] = dict(calls=0, seconds=0.)
                    def call(*args, **kwargs):
                        start = time.perf_counter()
                        try:
                            return original(*args, **kwargs)
                        finally:
                            costs[key]["calls"] += 1
                            costs[key]["seconds"] += time.perf_counter()-start
                    setattr(obj, name, call)
                for name in ("advance", "read_state", "capture_state"):
                    timed(env._world, name)
                timed(env._sensors, "sample")
                env.add_transition_sink(lambda transition: write_json_atomic(output / "timing.json", costs))
                report["initial_observation"] = to_jsonable({k: v for k, v in env.observe().items() if k != "rgb"})
                report["asset_sha256"] = to_jsonable(env._asset_build.sha256)
                write_json_atomic(output / "report.json", report)
                with SegmentRunner(env, output / "trail") as runner:
                    actor = runner.interaction()
                    initial_physics = {key: runner._last_tick[key] for key in ("world", "robot")}
                    report["initial_physics_sha256"] = hashlib.sha256(json.dumps(
                        to_jsonable(initial_physics), sort_keys=True, allow_nan=False).encode()).hexdigest()
                    frames = env.sensor_frame()
                    from topogym.sensors.renderers.nyx import NyxCamera
                    assert env._world.tabletop.presentation["background"] == "compact_lab"
                    assert all(isinstance(c, NyxCamera) for c in env._world.cameras.values())
                    expected = ({"cam_high", "cam_low", "cam_left_wrist", "cam_right_wrist"}
                                if robot == "aloha" else {"agentview", "front_oblique", "wrist"})
                    assert set(frames.rgb) == expected
                    assert all(image.shape == (480, 848, 3) for image in frames.rgb.values())
                    if case in {"cube", "empty_grasp"}:
                        segments = cube_policy(actor, split=split, empty_grasp=case == "empty_grasp",
                                               speed_scale=speed_scale)
                        report["task_result"] = to_jsonable(env._task.result)
                        report["segments"] = to_jsonable(segments)
                        report["task_expectation_passed"] = env._task.result.task_success == (case == "cube")
                    else:
                        from fixtures.control_targets import targets_and_action, rotation
                        import numpy as np
                        goals, action = targets_and_action(env, mode)
                        first = actor.run_segment(request_id="one", actions=[action]+[{}]*9)
                        second = actor.run_segment(request_id="two", actions=[{}]*10)
                        assert first["end_state_ref"] == second["start_state_ref"]
                        assert first["physics_steps"] == second["physics_steps"] == 10*config.control_decimation
                        targets = env.last_transition.info["executed_joint_targets"]
                        def tracking():
                            measured = env.privileged.get("robot")
                            errors = {}
                            for arm, goal in goals.items():
                                field = actor.action_spec["groups"][arm]["gripper_field"]
                                finger = "finger_position_" + ("m" if field.endswith("_m") else "rad")
                                errors[arm] = dict(
                                    position=float(np.linalg.norm(measured[arm]["tcp_position_world_m"]-goal["position_world_m"])),
                                    orientation=float((rotation(measured[arm]["tcp_orientation_wxyz"]).inv()*rotation(goal["orientation_wxyz"])).magnitude()),
                                    joints=float(np.max(np.abs(measured[arm]["joint_position_rad"]-targets[arm]["joint_position_rad"]))),
                                    gripper=float(np.max(np.abs(measured[arm][finger]-goal[field]))))
                            return errors
                        def within_threshold(errors):
                            return all(error["position"] < .003 and error["orientation"] < .01
                                and error["joints"] < .005 and error["gripper"] < (.003 if robot == "aloha" else .03)
                                for error in errors.values())
                        segments = [first, second]
                        errors = tracking()
                        report["tracking_errors_after_20_control_steps"] = errors
                        report["original_short_tracking_passed"] = within_threshold(errors)
                        # A separate policy-owned hold segment checks eventual tracking.
                        # The original short-duration qualification remains explicit.
                        if not within_threshold(errors) and tracking_hold_seconds > 0:
                            actor.begin_segment(request_id="settle")
                            for _ in range(round(tracking_hold_seconds / actor.timing_spec["control_dt_s"])):
                                feedback = actor.step({})
                                errors = tracking()
                                if within_threshold(errors) or feedback[2] or feedback[3]:
                                    break
                            segments.append(actor.end_segment())
                        report["tracking_errors"] = errors
                        report["tracking_passed"] = within_threshold(errors)
                        report["tracking_duration_s"] = env._world.sim_time_s
                        report["segments"] = to_jsonable(segments)
                    assert all(s["evidence_complete"] for s in segments)
                    assert sum(s["physics_steps"] for s in segments) == env._world.physics_step
                    assert all(a["end_state_ref"] == b["start_state_ref"] for a, b in zip(segments, segments[1:]))
                    with (runner.root / "private/physics_states.jsonl").open() as stream:
                        ticks = [json.loads(line)["state"]["physics_step"] for line in stream]
                    assert ticks == list(range(env._world.physics_step+1))
                    report["physics_steps"] = env._world.physics_step
                    report["task_instance_id"] = env._task.instance_id
                    report["initial_public"] = to_jsonable(actor.initial)
                    report["segment_checks_passed"] = True
                    if case in {"cube", "empty_grasp"}:
                        assert report["task_expectation_passed"], "Cube transfer success predicate failed"
                    else:
                        assert report["tracking_passed"], "Robot tracking threshold failed after policy hold"
        report["status"] = "passed"
    except BaseException:
        if report["status"] != "blocked":
            report["status"] = "failed"
        report["error"] = traceback.format_exc()
        raise
    finally:
        report["wall_time_s"] = time.time()-report["started"]
        write_json_atomic(output / "report.json", report)


def snapshot(output):
    destination = output / "source_snapshot"
    hashes = {}
    for subtree in ("topogym", "tests", "scripts", "assets/robots"):
        for path in sorted((ROOT / subtree).rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts or "deferred" in path.parts:
                continue
            relative = path.relative_to(ROOT)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            hashes[str(relative)] = hashlib.sha256(target.read_bytes()).hexdigest()
    (output / "source_manifest.json").write_text(json.dumps(hashes, indent=2))
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--case", choices=["cube", "empty_grasp", "interfaces"], default="cube")
    parser.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2, 3, 4])
    parser.add_argument("--split", action="store_true")
    parser.add_argument("--speed-scale", type=float, default=1.)
    parser.add_argument("--physics-dt", type=float, default=.0025)
    parser.add_argument("--control-decimation", type=int, default=10)
    parser.add_argument("--solver-substeps", type=int, default=4)
    parser.add_argument("--robot", choices=["aloha", "panda_robotiq"], default="panda_robotiq")
    parser.add_argument("--mode", choices=["JOINT_ABS", "JOINT_DELTA", "EE_ABS", "EE_DELTA"], default="EE_ABS")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--suite", action="store_true", help="Run seeds, split, empty grasp and both-robot control matrix")
    parser.add_argument("--matrix", action="store_true", help="Run only the both-robot control matrix")
    parser.add_argument("--tracking-hold-seconds", type=float, default=2.5,
                        help="Extra policy hold after the original 20-step tracking measurement; 0 keeps original duration")
    parser.add_argument("--jobs", type=int, choices=[1, 2, 3, 4], default=1,
                        help="Independent simulator processes; provision GPU/RAM for every job")
    args = parser.parse_args()
    if args.worker:
        run_case(args.output, case=args.case, seed=args.seeds[0], split=args.split,
                 robot=args.robot, mode=args.mode, speed_scale=args.speed_scale,
                 physics_dt=args.physics_dt, control_decimation=args.control_decimation,
                 solver_substeps=args.solver_substeps, tracking_hold_seconds=args.tracking_hold_seconds)
        return
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = snapshot(output)
    summary = dict(status="running", cases=[], source_snapshot=str(source))
    cases = [dict(name=f"case_{index}_seed_{seed}", case=args.case, seed=seed,
                  robot=args.robot, mode=args.mode, split=args.split) for index, seed in enumerate(args.seeds)]
    if args.suite:
        cases = [dict(name=f"cube_seed_{seed}", case="cube", seed=seed,
                      robot="panda_robotiq", mode="EE_ABS", split=False) for seed in args.seeds]
        cases += [dict(name=name, case=case, seed=0, robot="panda_robotiq", mode="EE_ABS", split=split)
                  for name, case, split in (("cube_split", "cube", True), ("empty_grasp", "empty_grasp", False))]
    if args.matrix:
        cases = []
    if args.suite or args.matrix:
        cases += [dict(name=f"interfaces_{robot}_{mode}", case="interfaces", seed=0,
                       robot=robot, mode=mode, split=False)
                  for robot in ("panda_robotiq", "aloha")
                  for mode in ("JOINT_ABS", "JOINT_DELTA", "EE_ABS", "EE_DELTA")]
    summary["planned_cases"] = cases
    (output / "summary.json").write_text(json.dumps(summary, indent=2))
    def execute(case):
        folder = output / case["name"]
        cmd = [sys.executable, str(source / "scripts/test_policy_cube_transfer.py"), "--worker",
               "--output", str(folder), "--case", case["case"], "--seeds", str(case["seed"]),
               "--robot", case["robot"], "--mode", case["mode"], "--speed-scale", str(args.speed_scale),
               "--physics-dt", str(args.physics_dt), "--control-decimation", str(args.control_decimation),
               "--solver-substeps", str(args.solver_substeps),
               "--tracking-hold-seconds", str(args.tracking_hold_seconds)]
        if case["split"]:
            cmd.append("--split")
        with (output / (case["name"]+".log")).open("w") as log:
            result = subprocess.run(cmd, cwd=source, stdout=log, stderr=subprocess.STDOUT,
                env=dict(os.environ, PYTHONPATH=str(source)+os.pathsep+str(source/"tests"),
                         OMP_NUM_THREADS="1", MKL_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1"))
        return dict(**case, exit_code=result.returncode, report=str(folder / "report.json"))
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for result in pool.map(execute, cases):
            summary["cases"].append(result)
            (output / "summary.json").write_text(json.dumps(summary, indent=2))
    if args.suite and not args.matrix and 0 in args.seeds:
        regular = json.loads((output / "cube_seed_0/report.json").read_text())
        split = json.loads((output / "cube_split/report.json").read_text())
        summary["same_seed_initial_physics_identical"] = (regular.get("initial_physics_sha256") is not None
            and regular.get("initial_physics_sha256") == split.get("initial_physics_sha256"))
    summary["status"] = "passed" if all(c["exit_code"] == 0 for c in summary["cases"]) else "failed"
    if summary.get("same_seed_initial_physics_identical") is False:
        summary["status"] = "failed"
    (output / "summary.json").write_text(json.dumps(summary, indent=2))
    if summary["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
