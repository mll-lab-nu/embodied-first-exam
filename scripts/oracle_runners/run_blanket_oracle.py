#!/usr/bin/env python3
"""Frozen-source Blanket robot oracle: default home -> assisted route -> native Task success."""
import argparse
from contextlib import contextmanager, nullcontext
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


@contextmanager
def record_episode(env, output):
    """Subscribe the shared recorder to the same continuous physical execution."""
    from topogym.recording import RecordingSession
    from topogym.recording.segment import save_rgb
    recording = RecordingSession(output/"recording", metadata=dict(
        scope="continuous robot oracle from default home", assistance="pbd_local_patch_v1"))
    recording.__enter__()
    initial = env.sensor_frame()
    save_rgb(output, "initial", initial)
    recording.append(initial)
    remove = env.add_frame_sink(recording.append)
    try:
        yield
    finally:
        remove()
        try:
            # An interrupted physics tick faults Env; keep the already recorded
            # prefix without asking that environment for another observation.
            faulted = bool(env._faulted)
            if not faulted:
                final = env.sensor_frame()
                recording.append_final(final)
                save_rgb(output, "final", final)
            recording.finish(dict(task_success=bool(env._task.result.task_success) and not faulted,
                terminated=bool(env._task.result.terminated), environment_faulted=faulted,
                final_frame_available=not faulted, scope="executed prefix; see oracle_report.json"))
        finally:
            recording.close(commit=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--variation", choices=("very_easy", "easier", "easy", "medium", "hard"), default="easy")
    parser.add_argument("--max-physics-steps", type=int,
                        help="Defaults: very_easy 20000, easier 48000, easy / medium 28000, hard 40000")
    parser.add_argument("--record", action="store_true", help="Save continuous four-camera shared recording")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.max_physics_steps is None:
        args.max_physics_steps = {"very_easy": 20000, "easier": 48000,
                                 "easy": 28000, "medium": 28000, "hard": 40000}[args.variation]
    args.output = args.output.resolve()
    if args.worker:
        from topogym.simulator import Env, SimulatorConfig, SegmentRunner
        from topogym.planning.blanket_flatten import assist_support
        from topogym.planning.blanket_flatten.routes import PATCH, ROUTES
        from topogym.planning.blanket_flatten.robot_oracle import run_route_oracle
        # Frozen Blanket scenes are bound to CUDA float64, 2.5 ms / 4 substeps and
        # the prepared camera rig; RGB therefore stays enabled (Nyx).
        config = SimulatorConfig(task_id="blanket_flatten", variation_id=args.variation, compute_backend="cuda",
            enable_rgb=True, enable_privileged=True, control_mode="JOINT_ABS",
            max_physics_steps=args.max_physics_steps, work_dir=args.output/"scene",
            grasp_assist=dict(model="pbd_local_patch_v1", stable_time_s=.03,
                              targets=[dict(entity="blanket", **PATCH,
                                            max_strain_ratio=ROUTES[args.variation]["max_strain_ratio"])]))
        assist_support.enable()   # compatibility call; material support is now public runtime
        with Env(config) as env:
            # Observations skip RGB; --record takes frames through the shared sink.
            env.defer_rgb = True
            env.reset(seed=args.seed)
            with (record_episode(env, args.output) if args.record else nullcontext()), \
                    SegmentRunner(env, args.output/"trail") as runner:
                report = run_route_oracle(env, runner, args.output, variation=args.variation)
        return 0 if report["task_success"] else 2

    args.output.mkdir(parents=True, exist_ok=False)
    from scripts.test_policy_cube_transfer import snapshot
    from topogym.utils.process_limits import run_guarded
    source = snapshot(args.output)
    command = [sys.executable, str(source/"scripts/oracle_runners/run_blanket_oracle.py"), "--worker",
               "--output", str(args.output), "--seed", str(args.seed), "--variation", args.variation,
               "--max-physics-steps", str(args.max_physics_steps)]
    if args.record:
        command.append("--record")
    (args.output/"invocation.json").write_text(json.dumps(dict(command=command), indent=2)+"\n")
    environment = dict(os.environ, PYTHONPATH=str(source), OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
                       OPENBLAS_NUM_THREADS="1", QD_NUM_THREADS="1", PYTHONUNBUFFERED="1")
    result = run_guarded(command, args.output, cwd=source, env=environment)
    print(f"exit={result}; {args.output}", flush=True)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
