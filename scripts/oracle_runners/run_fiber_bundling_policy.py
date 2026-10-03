#!/usr/bin/env python3
"""Run the approved two/three-strand scenes from home with shared evidence.

Diagnostic stages may rewind; a proof or fresh action replay must be continuous.
RGB uses SegmentRunner's shared recording path. No object poses are written.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import traceback
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def worker(args):
    import torch
    from topogym.simulator import Env, SimulatorConfig, SegmentRunner
    from topogym.planning.fiber_bundling.stages import stages
    from topogym.planning.solvability import QualificationWorkflow, identity_for
    from topogym.simulator.rollout_simulation.segment_contract import fingerprint
    from topogym.utils.io import to_jsonable, write_json_atomic

    torch.set_num_threads(1)
    output = args.output
    replay = None
    if args.replay_run:
        source = args.replay_run
        previous = json.loads((source / "run_report.json").read_text())
        values = json.loads((source / "config.json").read_text())
        if args.config:
            replacement = json.loads(args.config.read_text())
            if (replacement["task_id"] != "fiber_bundling"
                    or replacement["variation_id"] not in {args.variant, f"fiber_bundling_{args.variant}"}
                    or abs(replacement["physics_dt_s"] * replacement["control_decimation"]
                           - values["physics_dt_s"] * values["control_decimation"]) > 1e-12):
                raise ValueError("Replay configuration must preserve the task and action period")
            values = replacement
        metadata = json.loads((source / "private/static_model.json").read_text())["episode"]
        if not previous.get("task_success") or not previous.get("continuous_from_birth", False):
            raise ValueError("Replay requires a successful continuous source run")
        if metadata["canonical_variation_id"] != f"fiber_bundling_{args.variant}" or metadata["seed"] != args.seed:
            raise ValueError("Replay variant and seed differ from the source")
        replay = []
        for line in (source / "private/control_steps.jsonl").open():
            row = json.loads(line)
            if row["kind"] == "completed":
                if row["info"]["control_mode"] != "JOINT_ABS":
                    raise ValueError("Replay requires executed joint targets")
                replay.append(row["info"]["executed_joint_targets"])
        if not replay:
            raise ValueError("Source contains no completed actions")
        # A changed integrator can reach the stable window a few ticks later.
        # Hold the final executed command for at most two more simulated seconds.
        replay += [replay[-1]] * round(2. / (values["physics_dt_s"] * values["control_decimation"]))
    elif args.config:
        values = json.loads(args.config.read_text())
        if values["task_id"] != "fiber_bundling" or values["variation_id"] not in {args.variant, f"fiber_bundling_{args.variant}"}:
            raise ValueError("Requested configuration does not match the variation")
    else:
        from topogym.tasks.fiber_bundling.common import recommended_grasp_assist
        values = dict(task_id="fiber_bundling", variation_id=f"fiber_bundling_{args.variant}",
            robot_id="panda_robotiq", control_mode="JOINT_ABS", compute_backend="cpu", precision="64",
            physics_dt_s=.0025, control_decimation=10, solver_substeps=4,
            rigid_options={"use_contact_island": False},
            grasp_assist=to_jsonable(recommended_grasp_assist(args.variant, args.seed)))
    values.update(seed=args.seed, enable_rgb=not args.no_rgb, enable_privileged=True,
        work_dir=str(output / "scene"), history_storage="memory" if args.mode == "diagnostic" else "segment",
        max_physics_steps=round(args.episode_seconds / values["physics_dt_s"]))
    config = SimulatorConfig(**values)
    report = dict(status="running", started=time.time(), variant=args.variant, seed=args.seed,
        config=to_jsonable(config), task_success=False, accepted_proof=False,
        scope="one seeded instance; contact_weld_v1 sheath grasp; difficulty ranking not qualified",
        continuous_from_birth=False, source_run=str(args.replay_run) if args.replay_run else None)
    write_json_atomic(output / "run_report.json", report)
    env = None
    try:
        with Env(config) as env:
            env.reset(seed=args.seed)
            report.update(instance_id=env._task.instance_id, terminal=env._task.terminal_metadata(),
                asset_sha256=dict(env._asset_build.sha256), initial_task=to_jsonable(env._task.result))
            write_json_atomic(output / "run_report.json", report)
            with SegmentRunner(env, output, prepared_output=True) as runner:
                last_progress = [-1.]

                def monitor(tick):
                    seconds = tick["state"]["sim_time_s"]
                    if seconds - last_progress[0] >= 1.:
                        last_progress[0] = seconds
                        write_json_atomic(output / "progress.json", dict(state=tick["state"],
                            task=tick["task"]["result"], grasp=tick["world"]["grasp"]["hands"]["arm"]))

                unsubscribe = env.add_state_sink(monitor)
                try:
                    if replay is not None:
                        class RecordedActions:
                            index = 0

                            def act(self, observation):
                                if observation["state"]["branch_id"] != 0:
                                    raise RuntimeError("A fresh replay must not rewind")
                                if self.index == len(replay):
                                    return None
                                action = replay[self.index]
                                self.index += 1
                                return action

                        result = runner.run_policy(request_id="continuous-replay", policy=RecordedActions(),
                            submission_hash=fingerprint(replay), mode="unlimited",
                            state_fields=(), observation_profile={"rgb_camera_ids": []})
                        report.update(continuous_from_birth=True, replay_result=to_jsonable(result))
                    else:
                        identity = identity_for(runner, owner_sources=[Path(__file__)])
                        flow = QualificationWorkflow(runner, output / "qualification", identity, mode=args.mode)
                        context = SimpleNamespace(output=output, identity=identity)
                        selected = json.loads(args.selection.read_text()) if args.selection else None
                        for index, step in enumerate(stages(env, context)):
                            candidates = None
                            if selected is not None:
                                if index >= len(selected) or selected[index]["step"] != step.name:
                                    raise ValueError(f"Selection mismatch at {step.name}")
                                candidates = [selected[index]["parameters"]]
                            print("stage", step.name, "start_s", env._world.sim_time_s, flush=True)
                            flow.run_step(step, candidates)
                            if env.is_solved():
                                break
                        report.update(flow.finish())
                    report.update(task_success=bool(env.is_solved()), task_result=to_jsonable(env._task.result),
                        physics_steps=env._world.physics_step, simulation_time_s=env._world.sim_time_s)
                    if not report["task_success"]:
                        raise RuntimeError("Reference ended without native Task success")
                    report["status"] = "native_success_pending_independent_audit"
                finally:
                    unsubscribe()
    except BaseException:
        report.update(status="failed", error=traceback.format_exc())
        raise
    finally:
        report["wall_time_s"] = time.time() - report["started"]
        write_json_atomic(output / "run_report.json", report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=("very_easy", "easier"), required=True)
    parser.add_argument("--output", type=lambda p: Path(p).resolve(), required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--mode", choices=("diagnostic", "proof"), default="proof")
    parser.add_argument("--config", type=lambda p: Path(p).resolve())
    parser.add_argument("--selection", type=lambda p: Path(p).resolve())
    parser.add_argument("--replay-run", type=lambda p: Path(p).resolve())
    parser.add_argument("--episode-seconds", type=float, default=600.)
    parser.add_argument("--no-rgb", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.episode_seconds <= 0 or args.replay_run and (args.selection or args.mode == "diagnostic"):
        parser.error("Replay requires proof mode and no selection override; duration must be positive")
    if args.worker:
        return worker(args)
    args.output.mkdir(parents=True, exist_ok=False)
    from scripts import test_policy_cube_transfer as snapshotting
    if args.replay_run:
        snapshotting.ROOT = args.replay_run / "source_snapshot"
    source = snapshotting.snapshot(args.output)
    manifest = json.loads((args.output / "source_manifest.json").read_text())
    if args.replay_run:
        # Keep the original runtime; only add this execution entry and auditor.
        for relative in ("scripts/oracle_runners/run_fiber_bundling_policy.py", "scripts/audit_fiber_bundling_robot.py",
                         "topogym/planning/fiber_bundling/audit.py"):
            shutil.copy2(ROOT / relative, source / relative)
            manifest[relative] = hashlib.sha256((source / relative).read_bytes()).hexdigest()
    (args.output / "source_manifest.json").unlink()
    (args.output / "run_source_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    options = list(sys.argv[1:])
    for flag, path in (("--config", args.config), ("--selection", args.selection)):
        if path is not None:
            destination = args.output / f"requested_{flag[2:]}.json"
            shutil.copy2(path, destination)
            options[options.index(flag) + 1] = str(destination)
    command = [sys.executable, str(source / "scripts/oracle_runners/run_fiber_bundling_policy.py"), *options, "--worker"]
    (args.output / "invocation.json").write_text(json.dumps(dict(command=command), indent=2) + "\n")
    import psutil
    with (args.output / "runtime.log").open("x") as log, (args.output / "resources.jsonl").open("x", buffering=1) as monitor:
        process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
            env=dict(os.environ, PYTHONPATH=str(source), OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1",
                     TOPOGYM_VISUAL_ASSET_ROOT=str(ROOT / ".external/nyx-assets")))
        try:
            while process.poll() is None:
                sample = dict(time=time.time(), cpu_percent=psutil.cpu_percent(),
                    memory_percent=psutil.virtual_memory().percent,
                    disk_free_bytes=shutil.disk_usage(args.output).free)
                monitor.write(json.dumps(sample) + "\n")
                if sample["memory_percent"] >= 90:
                    raise RuntimeError("System memory reached 90%; stopping only this invocation")
                if sample["disk_free_bytes"] < 1024 ** 3:
                    raise RuntimeError("Less than 1 GiB remains; stopping this invocation before evidence writes fail")
                time.sleep(2)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
    print("exit=", process.returncode, args.output, flush=True)
    raise SystemExit(process.returncode)


if __name__ == "__main__":
    main()
