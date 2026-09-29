#!/usr/bin/env python3
"""Run staged qualification without RGB; final acceptance needs a Task audit.

--smoke exercises ordinary actions, per-tick checks and public local rewind in
the real Buzz easy scene. It does not attempt to solve Buzz.
Task adapters expose factory(env, context) -> iterable[Step].

Diagnostic runs rewind a failed step to its start and try the next candidate.
When none is left the live Env waits: write parameters to control/next.json
(write a temporary file, then rename it) or create control/stop. Creating
control/abort fails the running diagnostic stage at its next physics tick.
Proof runs use one --selection entry per step and never rewind.
"""
import argparse
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def worker(args):
    import torch
    from topogym.simulator import Env, SimulatorConfig, SegmentRunner
    from topogym.planning.base import ActionSequencePolicy
    from topogym.planning.solvability import QualificationWorkflow, Stage, PathCache, identity_for
    from topogym.utils.io import sha256_file, to_jsonable, write_json_atomic
    torch.set_num_threads(1)
    if args.smoke:
        from topogym.config.registry import task_definition
        # Same weld target as scripts/run_buzz_wire_policy.py; without an assist
        # model the world state has no "grasp" record for the entry check.
        layout = task_definition("buzz_wire_3d", "easy")().build_layout()
        grip = layout.loop_radius_m+layout.stem_length_m+layout.grip_length_m*.55
        values = dict(task_id="buzz_wire_3d", variation_id="easy", robot_id="panda_robotiq",
                      compute_backend="cpu", physics_dt_s=.025, solver_substeps=40,
                      control_decimation=1, control_mode="JOINT_ABS", max_physics_steps=40,
                      grasp_assist=dict(model="contact_weld_v1", targets=[
                          dict(entity="wand", link="wand", center_m=[grip, 0., 0.], radius_m=.025)]))
    else:
        values = json.loads(args.config.read_text())
    values.update(enable_rgb=False, enable_privileged=True, work_dir=str(args.output / "scene"))
    owner_sources = [Path(__file__)]
    factory = None
    if not args.smoke:
        module_name, function_name = args.stage_factory.split(":", 1)
        module = importlib.import_module(module_name)
        source = Path(module.__file__).resolve()
        if not source.is_relative_to(ROOT):
            raise ValueError("Stage factory must come from the frozen repository snapshot")
        owner_sources.append(source)
        factory = getattr(module, function_name)
    report = dict(status="running", scope="native workflow smoke" if args.smoke else "staged execution",
                  accepted_proof=False, rgb=False, video=False)
    write_json_atomic(args.output / "run_report.json", report)
    try:
        with Env(SimulatorConfig(**values)) as env:
            env.reset(seed=args.seed)
            with SegmentRunner(env, args.output, prepared_output=True) as runner:
                identity = identity_for(runner, owner_sources=owner_sources)
                flow = QualificationWorkflow(runner, args.output / "qualification", identity, mode=args.mode,
                                             abort_file=args.output / "control" / "abort")
                cache = PathCache(args.output / "path_cache", identity)
                if args.smoke:
                    def invariant(tick):
                        contacts = tick["world"]["contact_events"]
                        forbidden = ({"wire_metal", "wand_metal"}, {"wire_metal", "robot"})
                        return dict(contact_coverage=contacts["substeps_complete"],
                            no_forbidden_touch=not any(event["touching"] and
                                {event["role_a"], event["role_b"]} in forbidden
                                for event in contacts["events"]))

                    def window(name, actions, budget):
                        return Stage(name, "transit", dict(actions=actions, command="hold",
                            forbidden_roles=[sorted(pair) for pair in ({"wire_metal", "wand_metal"},
                                                                       {"wire_metal", "robot"})]),
                            lambda tick: ActionSequencePolicy([{} for _ in range(actions)]),
                            lambda tick: {"unbound": tick["world"]["grasp"]["hands"]["arm"]["binding"] is None},
                            invariant, lambda tick: {"task_not_failed": not tick["task"]["result"]["terminated"]},
                            budget)

                    flow.run(window("hold_at_home", 4, .2))
                    checkpoint = env.tick_record()["state"]
                    target = {key: checkpoint[key] for key in ("episode_id", "state_id")}
                    try:
                        flow.run(window("intentional_window_budget_probe", 2, .025))
                    except ValueError:
                        failure = flow.report["stages"][-1]
                        if not any("stage_time_budget" in row["checks"] for row in failure["violations"]):
                            raise
                    else:
                        raise AssertionError("Budget probe unexpectedly passed")
                    flow.rewind(target)
                    flow.run(window("retry_after_public_rewind", 2, .1))
                    report["smoke_checks"] = dict(real_ordinary_actions=True, per_tick_monitoring=True,
                        intentional_budget_rejection=True, public_same_episode_rewind=True,
                        local_retry=True, accepted_as_task_proof=False)
                else:
                    control = args.output / "control"
                    report["received_parameters"] = []

                    def wait(step, start, tried):
                        # Keep the live Env; only JSON parameters are accepted, never code.
                        control.mkdir(exist_ok=True)
                        write_json_atomic(control / "waiting.json", dict(step=step.name, start=start, tried=tried))
                        deadline = time.monotonic()+4*3600
                        try:
                            while time.monotonic() < deadline and not (control / "stop").exists():
                                request = control / "next.json"
                                if request.exists():
                                    kept = control / f"received_{len(report['received_parameters']):03d}.json"
                                    request.rename(kept)
                                    report["received_parameters"].append(dict(step=step.name, file=kept.name,
                                                                              sha256=sha256_file(kept)))
                                    write_json_atomic(args.output / "run_report.json", report)
                                    try:
                                        parameters = json.loads(kept.read_text())
                                    except ValueError:
                                        parameters = None
                                    if isinstance(parameters, dict):
                                        return parameters
                                    print(f"ignored non-object parameters {kept.name}", flush=True)
                                time.sleep(5)
                            return None
                        finally:
                            (control / "waiting.json").unlink(missing_ok=True)

                    selection = json.loads(args.selection.read_text()) if args.selection else None
                    context = SimpleNamespace(output=args.output, cache=cache, identity=identity)
                    for index, step in enumerate(factory(env, context)):
                        candidates = None
                        if selection is not None:
                            if index >= len(selection) or selection[index]["step"] != step.name:
                                raise ValueError(f"Selection does not match step {index}: {step.name}")
                            candidates = [selection[index]["parameters"]]
                            if args.mode == "diagnostic":
                                candidates += list(step.candidates)
                        flow.run_step(step, candidates, wait=wait)
                        if env.is_solved():
                            break
                finished = flow.finish()
                # Fields read by the task's independent audit (e.g. audit_buzz_wire_policy.py).
                report.update(status=finished["status"], native_task_success=finished["native_task_success"],
                              continuous_from_birth=finished["continuous_from_birth"],
                              identity=identity, workflow="qualification/workflow.json",
                              config=to_jsonable(env.config), seed=args.seed, variant=env.config.variation_id,
                              instance_id=env._task.instance_id, physics_steps=env._world.physics_step,
                              simulation_time_s=env._world.sim_time_s,
                              task_result=to_jsonable(env._task.result),
                              task_success=bool(env._task.result.task_success))
                if args.smoke:
                    assert report["status"] == "local_windows_passed"
    except BaseException:
        report.update(status="failed", error=traceback.format_exc())
        raise
    finally:
        write_json_atomic(args.output / "run_report.json", report)
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0 if report["status"] in {"local_windows_passed", "native_success_pending_independent_audit"} else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("diagnostic", "proof"), default="diagnostic")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--config", type=Path, help="SimulatorConfig JSON for a task adapter")
    parser.add_argument("--stage-factory", help="Frozen module:function yielding Step objects")
    parser.add_argument("--selection", type=Path, help="selection.json of an earlier run: one entry per step")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    args.output = args.output.resolve()
    if args.smoke:
        if args.mode != "diagnostic" or args.config or args.stage_factory:
            parser.error("--smoke requires diagnostic mode and no custom configuration/factory")
    elif not args.config or not args.stage_factory or ":" not in args.stage_factory:
        parser.error("Provide --smoke, or both --config and --stage-factory module:function")
    if args.selection and args.smoke:
        parser.error("--selection requires a task stage factory")
    if args.worker:
        raise SystemExit(worker(args))
    args.output.mkdir(parents=True, exist_ok=False)
    extra = list(sys.argv[1:])
    for flag, name in (("--config", "requested_config.json"), ("--selection", "requested_selection.json")):
        if flag in extra:
            target = args.output / name
            target.write_bytes(Path(extra[extra.index(flag)+1]).read_bytes())
            extra[extra.index(flag)+1] = str(target)
    from scripts.test_policy_cube_transfer import snapshot
    source = snapshot(args.output)
    (args.output / "source_manifest.json").rename(args.output / "run_source_manifest.json")
    command = [sys.executable, str(source / "scripts/run_solvability_workflow.py"), *extra, "--worker"]
    (args.output / "invocation.json").write_text(json.dumps(dict(command=command), indent=2))
    with (args.output / "runtime.log").open("x") as log:
        process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
            env=dict(os.environ, PYTHONPATH=str(source), OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
                     OPENBLAS_NUM_THREADS="1", TOPOGYM_VISUAL_ASSET_ROOT=str(ROOT / ".external/nyx-assets")))
        while process.poll() is None:
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                progress = args.output / "qualification/workflow.json"
                data = json.loads(progress.read_text()) if progress.exists() else {}
                print(data.get("status", "building"), len(data.get("stages", [])), flush=True)
    print(f"exit={process.returncode}; {args.output}")
    raise SystemExit(process.returncode)


if __name__ == "__main__":
    main()
