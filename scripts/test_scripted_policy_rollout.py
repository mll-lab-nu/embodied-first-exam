#!/usr/bin/env python3
"""Freeze and execute real scripted-policy rollouts under task_rollouts.

Long-example defaults explicitly use 25 ms ticks / decimation 1 / 40 solver
substeps (40 Hz control). SimulatorConfig defaults are unchanged. Use
--physics-dt .0025 --control-decimation 10 --solver-substeps 4 for default ticks.
"""
from pathlib import Path
import argparse
from datetime import date
import json
import os
import re
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]


class LimitedReachPolicy:
    """Short sensor-feedback check; sees no object coordinates or Task state."""

    def initialize(self, context):
        self.target = None
        self.calls = 0

    def act(self, obs):
        import numpy as np
        assert set(obs) == {"rgb", "robot", "task", "state", "execution_state", "camera_calibration"}
        assert set(obs["rgb"]) == {"agentview", "front_oblique", "wrist"}
        assert set(obs["camera_calibration"]) == {"agentview", "front_oblique"}
        arm = obs["robot"]["arm"]
        assert set(arm) == {"joint_position_rad", "tcp_position_world_m",
                            "tcp_orientation_wxyz", "finger_position_rad"}
        measured = np.asarray(arm["tcp_position_world_m"])
        if self.target is None:
            self.target = measured + [0.005, 0., 0.]
        self.error_m = float(np.linalg.norm(measured - self.target))
        self.calls += 1
        if obs["execution_state"]["control_steps"] >= 8 and self.error_m < .002:
            return None
        if self.calls > 60:
            raise RuntimeError("Limited proprioception feedback target not reached")
        return {"arm": dict(position_world_m=self.target.tolist(),
                            orientation_wxyz=arm["tcp_orientation_wxyz"].tolist())}


def allocate_rollout(root, experiment, task):
    for component in (experiment, task):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", component):
            raise ValueError("Experiment/task names must be single path components")
    parent = Path(root).resolve() / experiment / task
    parent.mkdir(parents=True, exist_ok=True)
    for number in range(1, 1000000):
        destination = parent / f"rollout_{number:04d}"
        try:
            destination.mkdir(mode=0o700)
            return destination
        except FileExistsError:
            continue
    raise RuntimeError("Rollout namespace exhausted")


def run_case(output, *, case="pick_place", seed=0, split=False,
             physics_dt=.025, control_decimation=1, solver_substeps=40):
    from importlib.metadata import version, PackageNotFoundError
    from topogym.simulator import Env, SimulatorConfig, SegmentRunner
    from topogym.planning.examples.cube_pick_place import CubePickPlacePolicy
    from topogym.utils.io import write_json_atomic, to_jsonable
    from topogym.simulator.rollout_simulation.segment_contract import fingerprint
    from fixtures.cube_pick_place import register_cube_pick_place
    from fixtures.cube_transfer import register_cube_transfer

    output = Path(output)
    identity = "cube_pick_place" if case == "pick_place" else "cube_transfer"
    config = SimulatorConfig(task_id=identity, robot_id="panda_robotiq", control_mode="EE_ABS",
        observation_mode="JOINT", enable_privileged=case != "limited", physics_dt_s=physics_dt,
        control_decimation=control_decimation, solver_substeps=solver_substeps,
        max_physics_steps=round(25./physics_dt))
    report = dict(status="running", case=case, seed=seed, split=split, config=to_jsonable(config),
        started=time.time(), scope=("actual Genesis/Nyx limited proprioception feedback" if case == "limited" else
                                   "actual Genesis/Nyx passive scripted policy; unlimited world observations"),
        timing_scope="default ticks" if (physics_dt, control_decimation, solver_substeps) == (.0025, 10, 4)
                     else "explicit test configuration; does not qualify default physical tick cadence",
        source_manifest="run_source_manifest.json", segments=[])
    report["packages"] = {}
    for package in ("genesis-world", "gs-nyx", "gs-nyx-plugin", "torch", "numpy", "scipy"):
        try:
            report["packages"][package] = version(package)
        except PackageNotFoundError:
            report["packages"][package] = None
    report["thresholds"] = dict(lift_m=.05, held_duration_s=.2, held_relative_displacement_m=.01,
        held_tcp_distance_m=.07, placement_error_m=.02, table_clearance_m=.003,
        stable_duration_s=.5, settled_linear_speed_m_s=.01, settled_angular_speed_rad_s=.1,
        gripper_withdrawal_m=.05, required_airborne_translation_m=0. if case == "pick_place" else .15)
    write_json_atomic(output / "run_report.json", report)
    try:
        import torch
        torch.set_num_threads(1)
        if not torch.cuda.is_available():
            report["status"] = "blocked"
            raise RuntimeError("CUDA unavailable; actual Nyx recording requires CUDA")
        report["gpu"] = torch.cuda.get_device_name()
        write_json_atomic(output / "run_report.json", report)
        registration = register_cube_pick_place if case == "pick_place" else register_cube_transfer
        with registration(), Env(config) as env:
            env.reset(seed=seed)
            report["asset_sha256"] = to_jsonable(env._asset_build.sha256)
            report["initial_robot"] = to_jsonable(env._robot.observe())
            report["from_default_home"] = True
            write_json_atomic(output / "run_report.json", report)
            with SegmentRunner(env, output, prepared_output=True) as runner:
                report["initial_physics_sha256"] = fingerprint({k: runner._last_tick[k] for k in ("world", "robot")})
                from topogym.sensors.renderers.nyx import NyxCamera
                frame = env.sensor_frame()
                assert env._world.tabletop.presentation["background"] == "compact_lab"
                assert all(isinstance(c, NyxCamera) for c in env._world.cameras.values())
                assert set(frame.rgb) == {"agentview", "front_oblique", "wrist"}
                assert all(p.shape == (480, 848, 3) for p in frame.rgb.values())
                initial_position = (None if case == "limited" else
                    env.privileged.get("world")["bodies"]["cube"]["position_m"])
                active = [None]
                def progress(transition):
                    write_json_atomic(output / "progress.json", dict(
                        phase=getattr(active[0], "phase", "limited_reach" if case == "limited" else None),
                        physics_step=env._world.physics_step, sim_time_s=env._world.sim_time_s,
                        task_result=env._task.result))
                env.add_transition_sink(progress)
                source = json.loads((output / "run_source_manifest.json").read_text())
                common = dict(place_entity_id=None if case == "pick_place" else "target_marker",
                              grasp_offset_m=(0., -.10, 0.) if case == "empty_grasp" else (0., 0., 0.))
                report["submissions"] = []
                for index, part in enumerate(("pickup", "transfer") if split else ("all",), 1):
                    parameters = dict(common, part=part)
                    if part == "transfer":
                        parameters["pickup_position_world_m"] = to_jsonable(initial_position)
                    policy_name = ("scripts.test_scripted_policy_rollout:LimitedReachPolicy" if case == "limited"
                                   else "topogym.planning.examples.cube_pick_place:CubePickPlacePolicy")
                    if case == "limited":
                        parameters = {}
                    submission = dict(policy=policy_name,
                        source_hashes=source, parameters=parameters)
                    digest = fingerprint(submission)
                    report["submissions"].append(dict(submission_hash=digest, parameters=parameters))
                    write_json_atomic(output / "run_report.json", report)
                    policy = active[0] = (LimitedReachPolicy() if case == "limited" else CubePickPlacePolicy(**parameters))
                    result = runner.run_policy(request_id=f"cube-{index}", policy=policy, submission_hash=digest,
                        mode="limited" if case == "limited" else "unlimited",
                        state_fields=() if case == "limited" else ("world",), observation_profile=dict(
                            calibration_camera_ids=["agentview", "front_oblique"]))
                    report["segments"].append(to_jsonable(result))
                    if result["reason"] != "policy_done":
                        break
                report["task_result"] = to_jsonable(env._task.result)
                report["statistics"] = runner._evidence.statistics()
                report["physics_steps"] = env._world.physics_step
                expected_success = case not in {"empty_grasp", "limited"}
                report["task_expectation_passed"] = env._task.result.task_success == expected_success
                segments = report["segments"]
                assert segments and all(s["evidence_complete"] for s in segments), "Incomplete execution evidence"
                assert sum(s["physics_steps"] for s in segments) == env._world.physics_step
                assert all(b["start_state_ref"] == a["end_state_ref"] for a, b in zip(segments, segments[1:]))
                assert all(set(s["media"]["videos"]) == {"agentview", "front_oblique", "wrist", "combined"}
                           for s in segments)
                rows = [json.loads(line) for line in (output / "private/physics_states.jsonl").read_text().splitlines()]
                assert [row["state"]["physics_step"] for row in rows] == list(range(env._world.physics_step+1))
                assert report["task_expectation_passed"], "Independent task predicate failed"
                if expected_success:
                    assert segments[-1]["reason"] == "env_terminal"
                    assert len(segments) == (2 if split else 1)
                elif case == "empty_grasp":
                    assert segments[-1]["reason"] == "policy_error"
                    assert not env._task.lifted and not env._task.held_once
                    assert policy.phase == "hold", "Negative case did not finish the lift attempt"
                    policy_report = json.loads((output / f"private/policies/segment_{segments[-1]['segment_id']}.json").read_text())
                    assert any(error["stage"] == "policy_act" and
                               error["message"] == "Reference policy failed to lift the cube"
                               for error in policy_report["errors"]), "Unrelated policy failure is not an empty-grasp pass"
                else:
                    assert segments[-1]["reason"] == "policy_done"
                    assert policy.error_m < .002
                    report["limited_feedback"] = dict(target_error_m=policy.error_m,
                        decision_calls=policy.calls, privileged_enabled=False)
                report["segment_checks_passed"] = True
        report["status"] = "passed"
    except BaseException:
        if report["status"] != "blocked":
            report["status"] = "failed"
        report["error"] = traceback.format_exc()
        raise
    finally:
        report["wall_time_s"] = time.time() - report["started"]
        write_json_atomic(output / "run_report.json", report)


def run_snapshot(output, **options):
    from scripts.test_policy_cube_transfer import snapshot
    output = Path(output)
    source = snapshot(output)
    (output / "source_manifest.json").rename(output / "run_source_manifest.json")
    from topogym.utils.io import write_json_atomic
    write_json_atomic(output / "run_report.json", dict(status="starting", options=options,
                      source_snapshot="source_snapshot", source_manifest="run_source_manifest.json"))
    cmd = [sys.executable, str(source / "scripts/test_scripted_policy_rollout.py"), "--worker", "--output", str(output)]
    for key, value in options.items():
        flag = "--" + key.replace("_", "-")
        if isinstance(value, bool):
            if value:
                cmd.append(flag)
        else:
            cmd.extend([flag, str(value)])
    with (output / "runtime.log").open("x") as log:
        result = subprocess.run(cmd, cwd=source, stdout=log, stderr=subprocess.STDOUT,
            env=dict(os.environ, PYTHONPATH=str(source)+os.pathsep+str(source / "tests"),
                     OMP_NUM_THREADS="1", MKL_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1"))
    report = json.loads((output / "run_report.json").read_text())
    if result.returncode or report["status"] != "passed":
        raise RuntimeError(f"Rollout failed; see {output / 'run_report.json'}")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT / "task_rollouts"))
    parser.add_argument("--experiment", default="scripted_policy_pick_place_"+date.today().strftime("%Y%m%d"))
    parser.add_argument("--case", choices=["pick_place", "cube", "empty_grasp", "limited"], default="pick_place")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--seeds", type=int, nargs="+", help="Run the chosen case sequentially for these seeds")
    parser.add_argument("--split", action="store_true")
    parser.add_argument("--physics-dt", type=float, default=.025)
    parser.add_argument("--control-decimation", type=int, default=1)
    parser.add_argument("--solver-substeps", type=int, default=40)
    parser.add_argument("--suite", action="store_true", help="Sequential pick/place, five transfer seeds, split and empty grasp")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--output", help=argparse.SUPPRESS)
    args = parser.parse_args()
    timing = dict(physics_dt=args.physics_dt, control_decimation=args.control_decimation, solver_substeps=args.solver_substeps)
    if args.worker:
        run_case(args.output, case=args.case, seed=args.seed, split=args.split, **timing)
        return
    cases = [(args.case, seed, args.split) for seed in (args.seeds or [args.seed])]
    if args.suite:
        cases = [("pick_place", 0, False)] + [("cube", seed, False) for seed in range(5)]
        cases += [("cube", 0, True), ("empty_grasp", 0, False)]
    failed = False
    for case, seed, split in cases:
        task = "cube_pick_place" if case == "pick_place" else "cube_transfer"
        output = allocate_rollout(args.root, args.experiment, task)
        print(str(output), flush=True)
        try:
            run_snapshot(output, case=case, seed=seed, split=split, **timing)
            print("passed", flush=True)
        except Exception as error:
            failed = True
            print(str(error), flush=True)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
