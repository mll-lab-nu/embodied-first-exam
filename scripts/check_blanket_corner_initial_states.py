#!/usr/bin/env python3
"""Frozen-source reset, rewind and short home-hold checks for Blanket corner folds.

Use --compare <previous-output>/particle_checks.npz in a second invocation to
check reconstruction in an independent process. This is not a robot solution.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def worker(args):
    import numpy as np
    import torch
    from topogym.recording import RecordingSession
    from topogym.recording.encoding import probe
    from topogym.recording.segment import save_rgb
    from topogym.simulator import Env, SimulatorConfig
    from topogym.utils.io import sha256_file, to_jsonable, write_json_atomic
    torch.set_num_threads(1)
    parameters = {}
    if args.candidate:
        manifest = args.candidate/"state/manifest.json"
        parameters.update(initial_state_path=str(manifest), initial_state_sha256=sha256_file(manifest))
    config = SimulatorConfig(task_id="blanket_flatten", variation_id=args.variation,
        task_parameters=parameters, enable_rgb=True, enable_privileged=True,
        work_dir=args.output/"scene", max_physics_steps=None)
    report = dict(status="running", scope="reset/rewind/short home hold; not a robot solution",
        config=to_jsonable(config), full_robot_solve_verified=False, seed=args.seed)
    write_json_atomic(args.output/"report.json", report)
    try:
        with Env(config) as env:
            env.defer_rgb = True
            _, info = env.reset(seed=args.seed)
            report.update(initial_state=to_jsonable(env._initial_state_report),
                instance_id=env._task.instance_id, asset_sha256=dict(env._asset_build.sha256))
            assert env._world.physics_step == 0
            assert env._initial_state_report["initialization_advance_calls"] == 0

            def particles():
                value = env._world.read_state()["particles"]["blanket"]
                return np.stack([np.asarray(value["position_m"]), np.asarray(value["velocity_m_s"])])

            initial = particles()
            if args.candidate:
                with np.load(args.candidate/"reference.npz") as reference:
                    assert np.array_equal(initial[0], reference["positions"])
                    assert np.array_equal(initial[1], reference["velocities"])
                report["preparation_nodes_exact"] = True
            handle = env.interaction(privileged=True)
            prefix = [initial]
            for _ in range(5):
                env.step({})
                prefix.append(particles())
            handle.rewind_to(info["state_ref"])
            assert np.array_equal(initial, particles())
            rewind_checks = []
            for expected in prefix[1:]:
                env.step({})
                actual = particles()
                rewind_checks.append(dict(exact=bool(np.array_equal(expected, actual)),
                    maximum_position_error_m=float(np.abs(expected[0]-actual[0]).max()),
                    maximum_velocity_error_m_s=float(np.abs(expected[1]-actual[1]).max())))
            report["rewind_checks"] = rewind_checks
            report["rewind_and_five_step_replay_exact"] = all(r["exact"] for r in rewind_checks)
            write_json_atomic(args.output/"report.json", report)
            handle.rewind_to(info["state_ref"])
            frame = env.sensor_frame()
            report["initial_frames"] = save_rgb(args.output, "initial", frame)
            samples = []
            with RecordingSession(args.output/"recording", fps=30,
                    metadata=dict(scope=report["scope"], instance_id=env._task.instance_id)) as recording:
                recording.append(frame)
                for i in range(args.steps):
                    _, _, terminated, truncated, _ = env.step({})
                    state = env._world.read_state()
                    goal, failure, metrics = env._task.evaluate_state(state)
                    assert not goal and failure is None and not terminated and not truncated
                    assert metrics["gates"]["material_intact"] and metrics["gates"]["above_table"]
                    samples.append(dict(physics_step=env._world.physics_step, **metrics))
                    frame = env.sensor_frame()
                    recording.append(frame)
                recording.append_final(frame)
                recording.finish(dict(task_success=False, short_home_hold_completed=True))
            report["final_frames"] = save_rgb(args.output, "after_hold", frame)
            final = particles()
            checks = dict(prefix=np.stack(prefix), final=final)
            np.savez_compressed(args.output/"particle_checks.npz", **checks)
            if args.compare:
                with np.load(args.compare) as comparison:
                    report["independent_process_checks"] = {key: dict(
                        exact=bool(np.array_equal(actual, comparison[key])),
                        maximum_absolute_error=float(np.abs(actual-comparison[key]).max()))
                        for key, actual in checks.items()}
                report["independent_process_nodes_exact"] = all(
                    r["exact"] for r in report["independent_process_checks"].values())
            report.update(status="passed", control_steps=args.steps,
                simulated_duration_s=env._world.sim_time_s, samples=samples,
                maximum_displacement_m=float(np.linalg.norm(final[0]-initial[0], axis=1).max()),
                maximum_final_speed_m_s=float(np.linalg.norm(final[1], axis=1).max()))
            env.reset(seed=args.seed)
            assert env._world.physics_step == 0 and np.array_equal(initial, particles())
            report["repeat_reset_nodes_exact"] = True
        report["videos"] = {p.stem: probe(p, decode=True)
            for p in sorted((args.output/"recording/videos").glob("*.mp4"))}
        assert len(report["videos"]) == 4
        if not report["rewind_and_five_step_replay_exact"] or not report.get("independent_process_nodes_exact", True):
            report["status"] = "replay_mismatch"
    except BaseException as error:
        report.update(status="failed", error=f"{type(error).__name__}: {error}", traceback=traceback.format_exc())
        raise
    finally:
        write_json_atomic(args.output/"report.json", report)
    return 0 if report["status"] == "passed" else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variation", choices=("very_easy", "easier"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--compare", type=Path)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--steps", type=int, default=100)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.steps < 1:
        parser.error("--steps must be positive")
    for name in ("output", "candidate", "compare"):
        if getattr(args, name) is not None:
            setattr(args, name, getattr(args, name).resolve())
    if args.worker:
        return worker(args)
    args.output.mkdir(parents=True, exist_ok=False)
    from scripts.test_policy_cube_transfer import snapshot
    from topogym.utils.process_limits import run_guarded
    source = snapshot(args.output)
    command = [sys.executable, str(source/"scripts/check_blanket_corner_initial_states.py"),
        "--worker", "--variation", args.variation, "--output", str(args.output),
        "--seed", str(args.seed), "--steps", str(args.steps)]
    for name in ("candidate", "compare"):
        if getattr(args, name) is not None:
            command.extend(["--"+name, str(getattr(args, name))])
    (args.output/"invocation.json").write_text(json.dumps(dict(command=command), indent=2)+"\n")
    environment = dict(os.environ, PYTHONPATH=str(source), PYOPENGL_PLATFORM="egl",
        OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1", QD_NUM_THREADS="1",
        PYTHONUNBUFFERED="1")
    return run_guarded(command, args.output, cwd=source, env=environment)


if __name__ == "__main__":
    raise SystemExit(main())
