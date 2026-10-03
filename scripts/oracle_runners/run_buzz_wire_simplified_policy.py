#!/usr/bin/env python3
"""Develop and audit robot execution of the two approved Buzz Wire scenes.

Scene integration does not imply a qualified oracle; consult the task page for
the actual validation scope of each variant and physics configuration.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def worker(args):
    import torch
    from topogym.simulator import Env, SimulatorConfig, SegmentRunner
    from topogym.tasks.buzz_wire_3d.common import recommended_grasp_assist
    from topogym.planning.buzz_wire_3d.simplified_policy import SimplifiedBuzzOracle, make_stage_policy
    from topogym.simulator.rollout_simulation.segment_contract import fingerprint
    from topogym.utils.io import to_jsonable, write_json_atomic

    torch.set_num_threads(1)
    output = args.output
    replay = None
    prefix_prepared = False
    prefix_released = False
    config = SimulatorConfig(task_id="buzz_wire_3d", variation_id=args.variant, seed=args.seed,
        control_mode="JOINT_ABS", observation_mode="EE", enable_privileged=True,
        enable_rgb=not args.no_rgb, compute_backend=args.compute_backend,
        physics_dt_s=args.physics_dt, control_decimation=args.control_decimation,
        solver_substeps=args.solver_substeps, max_physics_steps=round(args.episode_seconds/args.physics_dt),
        work_dir=output/"scene", grasp_assist=recommended_grasp_assist(args.variant, args.seed))
    source_run = args.replay_run or args.prefix_run
    if source_run:
        source_report = json.loads((source_run/"run_report.json").read_text())
        if source_report["variant"] != args.variant or source_report["seed"] != args.seed:
            raise ValueError("Replay source variant and seed must match")
        if args.replay_run and (source_report["status"] != "passed" or not source_report["task_success"]):
            raise ValueError("Full replay requires a successful source")
        if args.prefix_run:
            eligible = [segment for segment in source_report["segments"]
                        if segment["request_id"] in {"traverse", "prepare_finish_slide", "finish_recipe_0"}
                        and segment["reason"] == "policy_done" and not segment["feedback"]["task_terminated"]]
            if not eligible:
                raise ValueError("Finish development requires a completed, nonterminal traversal prefix")
            last = eligible[-1]
            prefix_released = last["request_id"] == "finish_recipe_0"
            prefix_prepared = last["request_id"] == "prepare_finish_slide" or prefix_released
            end_tick = last["feedback"]["physics_step"]
        else:
            end_tick = source_report["physics_steps"]
        manifest = json.loads((source_run/"run_source_manifest.json").read_text())
        for name, expected in manifest.items():
            if name.startswith("topogym/") and not name.startswith("topogym/planning/"):
                if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != expected:
                    raise ValueError(f"Replay runtime source changed: {name}")
        values = dict(source_report["config"])
        values.update(work_dir=str(output/"scene"), enable_rgb=not args.no_rgb)
        values["max_physics_steps"] = max(values["max_physics_steps"],
            round(args.episode_seconds/values["physics_dt_s"]))
        config = SimulatorConfig(**values)
        replay = []
        controls = source_run/"private/control_steps.jsonl"
        for line in controls.open():
            row = json.loads(line)
            if row["kind"] == "completed":
                if len(replay) == end_tick:
                    break
                if row["physics_steps"] != 1 or row["info"]["control_mode"] != "JOINT_ABS":
                    raise ValueError("Replay currently requires one ordinary joint action per tick")
                replay.append(row["info"]["executed_joint_targets"])
        if len(replay) != end_tick:
            raise ValueError("Source action ledger does not cover every tick")
    report = dict(status="running", started=time.time(), variant=args.variant, seed=args.seed,
        config=to_jsonable(config), task_success=False, from_default_home=True,
        scope="one instance; contact_weld_v1 assist; explicit timing; difficulty ranking not qualified",
        segments=[], grasp_events=[], planning=[])
    write_json_atomic(output/"run_report.json", report)
    try:
        with Env(config) as env:
            env.reset()
            report.update(instance_id=env._task.instance_id, terminal=env._task.terminal_metadata(),
                asset_sha256=to_jsonable(env._asset_build.sha256), initial_task=to_jsonable(env._task.result),
                initial_robot=to_jsonable(env._robot.observe()))
            policy = None
            with SegmentRunner(env, output, prepared_output=True) as runner:
                last = [None, -1.]
                def tick(row):
                    phase = getattr(policy, "phase", "initial")
                    report["grasp_events"].extend(to_jsonable(row["world"]["grasp"]["events"]))
                    t = float(row["state"]["sim_time_s"])
                    if phase != last[0] or t-last[1] >= 1.:
                        record = dict(state=row["state"], phase=phase,
                            wand=row["world"]["bodies"]["wand"], grasp=row["world"]["grasp"],
                            task_result=env._task.result, tracking=getattr(policy, "tracking", {}))
                        write_json_atomic(output/"progress.json", record)
                        print(phase, round(t, 3), record["tracking"], flush=True)
                        last[:] = [phase, t]
                env.add_state_sink(tick)
                if replay is not None:
                    class ReplayPolicy:
                        phase, tracking = "replay_joint_actions_from_home", {}
                        def initialize(self, context):
                            self.index = 0
                        def act(self, observation):
                            state = observation["state"]
                            if state["branch_id"] != 0 or state["physics_step"] != self.index:
                                raise ValueError("Replay must remain on consecutive ticks from home")
                            events = env.privileged.get("world")["contact_events"]["events"]
                            if any(e["touching"] and {e["role_a"], e["role_b"]} == {"robot", "wire_metal"} for e in events):
                                raise RuntimeError("Robot touched the wire during replay")
                            if self.index == len(replay):
                                return None
                            action = replay[self.index]
                            self.index += 1
                            return action
                    policy = ReplayPolicy()
                    result = runner.run_policy(request_id="replay-from-home", policy=policy,
                        submission_hash=fingerprint(replay), mode="unlimited")
                    report.update(segments=[to_jsonable(result)], task_result=to_jsonable(env._task.result),
                        simulation_time_s=env._world.sim_time_s, physics_steps=env._world.physics_step,
                        task_success=bool(env._task.result.task_success), statistics=runner._evidence.statistics(),
                        source_run=str(source_run), source_prefix_end_tick=end_tick,
                        source_actions_sha256=hashlib.sha256(controls.read_bytes()).hexdigest(),
                        replayed_actions_fingerprint=fingerprint(replay))
                    if not (result.get("evidence_complete") and result.get("physics_tick_complete")):
                        raise RuntimeError("Fresh replay has incomplete evidence")
                    if args.replay_run:
                        if not report["task_success"]:
                            raise RuntimeError("Fresh replay did not pass the native Task")
                        report["status"] = "passed"
                        return
                    if result["reason"] != "policy_done":
                        raise RuntimeError("Traversal prefix failed during fresh execution")
                def run(name, **parameters):
                    nonlocal policy
                    policy = make_stage_policy(env, parameters)
                    class OwnerObservationPolicy:
                        def initialize(self, context):
                            policy.initialize(context)
                        def act(self, observation):
                            # The trusted oracle reads the current privileged state.
                            # The complete per-tick world is already retained in the
                            # private journal; do not duplicate it in every observation.
                            observation = dict(observation, privileged=dict(
                                world=env.privileged.get("world")))
                            return policy.act(observation)
                    result = runner.run_policy(request_id=name, policy=OwnerObservationPolicy(),
                        submission_hash=fingerprint(dict(stage=name, parameters=parameters)),
                        mode="unlimited", state_fields=())
                    report["segments"].append(to_jsonable(result))
                    report.update(task_result=to_jsonable(env._task.result),
                        simulation_time_s=env._world.sim_time_s, physics_steps=env._world.physics_step,
                        last_phase=policy.phase, task_success=bool(env._task.result.task_success),
                        statistics=runner._evidence.statistics())
                    write_json_atomic(output/"run_report.json", report)
                    if not result.get("evidence_complete") or not result.get("physics_tick_complete"):
                        raise RuntimeError("Incomplete execution evidence")
                    if env._task.result.task_success:
                        return
                    if result["reason"] != "policy_done":
                        raise RuntimeError(f"Stage {name} failed: {result['reason']}")

                start = ("released" if prefix_released else "prepared" if prefix_prepared
                         else "traversed" if args.prefix_run else "home")
                oracle = SimplifiedBuzzOracle(env, output, variant=args.variant,
                    regrasp=args.regrasp, finish_mode=args.finish_mode,
                    terminal_contact_close=args.terminal_contact_close)
                for name, parameters in oracle.stages(start=start, part=args.part):
                    run(name, **parameters)
                    if env._task.result.task_success:
                        report["status"] = "passed"
                        return
                if args.part in {"pickup", "plan"}:
                    report["status"] = "pickup_passed" if args.part == "pickup" else "sampled_plan_passed"
                    return
                raise RuntimeError("Oracle stages ended without native Task success")

    except BaseException:
        report.update(status="failed", error=traceback.format_exc())
        raise
    finally:
        report["wall_time_s"] = time.time()-report["started"]
        write_json_atomic(output/"run_report.json", report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=("very_easy", "easier"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--part", choices=("pickup", "plan", "solve"), default="solve")
    parser.add_argument("--regrasp", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--finish-mode", choices=("direct", "release_regrasp", "slide_regrasp", "low_slide_regrasp"), default="low_slide_regrasp")
    parser.add_argument("--terminal-contact-close", action="store_true",
                        help="Experimental contact-limited first terminal regrasp; not a qualified solution")
    recorded = parser.add_mutually_exclusive_group()
    recorded.add_argument("--replay-run", type=lambda value: Path(value).resolve(),
                        help="Fresh execution of a successful source run's recorded joint actions; inherits its physics config")
    recorded.add_argument("--prefix-run", type=lambda value: Path(value).resolve(),
                         help="Fresh execution of a checked traversal prefix, followed by terminal planning")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--compute-backend", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--no-rgb", action="store_true")
    # Explicit development timing, like the existing Buzz oracle. This is not
    # the simulator / Harbor package's default 400 Hz Task and assist cadence.
    parser.add_argument("--physics-dt", type=float, default=.025)
    parser.add_argument("--control-decimation", type=int, default=1)
    parser.add_argument("--solver-substeps", type=int, default=40)
    parser.add_argument("--episode-seconds", type=float, default=450.)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    args.output = args.output.resolve()
    if args.worker:
        return worker(args)
    args.output.mkdir(parents=True, exist_ok=False)
    from scripts import test_policy_cube_transfer as snapshotting
    source_run = args.replay_run or args.prefix_run
    if source_run:
        # Other tasks may be under development in the shared workspace. A
        # replay inherits the original runtime, not unrelated concurrent edits.
        snapshotting.ROOT = source_run/"source_snapshot"
    source = snapshotting.snapshot(args.output)
    if source_run:
        manifest = json.loads((args.output/"source_manifest.json").read_text())
        for relative in (Path("scripts/oracle_runners/run_buzz_wire_simplified_policy.py"),
                         Path("topogym/planning/buzz_wire_3d/simplified_policy.py")):
            shutil.copy2(ROOT/relative, source/relative)
            manifest[str(relative)] = hashlib.sha256((source/relative).read_bytes()).hexdigest()
        (args.output/"source_manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    (args.output/"source_manifest.json").rename(args.output/"run_source_manifest.json")
    command = [sys.executable, str(source/"scripts/oracle_runners/run_buzz_wire_simplified_policy.py"),
               *sys.argv[1:], "--worker"]
    (args.output/"invocation.json").write_text(json.dumps(dict(command=command), indent=2)+"\n")
    import psutil
    with (args.output/"runtime.log").open("x") as log, (args.output/"resources.jsonl").open("x", buffering=1) as monitor:
        process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True, env=dict(os.environ, PYTHONPATH=str(source), OMP_NUM_THREADS="1",
                OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1", PYOPENGL_PLATFORM="egl",
                TOPOGYM_VISUAL_ASSET_ROOT=str(ROOT/".external/nyx-assets")))
        try:
            while process.poll() is None:
                row = dict(time=time.time(), cpu_percent=psutil.cpu_percent(), memory_percent=psutil.virtual_memory().percent)
                monitor.write(json.dumps(row)+"\n")
                if row["memory_percent"] >= 90:
                    raise RuntimeError("System memory reached 90%")
                time.sleep(1)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
    print("exit=", process.returncode, str(args.output), flush=True)
    raise SystemExit(process.returncode)


if __name__ == "__main__":
    main()
