#!/usr/bin/env python3
"""Record real default scenes with the existing Env and shared RecordingSession.

Each task runs in a fresh process. No alternate scene loop, API modification,
private video writer, or reset-to-demo-pose is used for default scene clips.
"""
from pathlib import Path
import argparse
import json
import os
import shutil
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/"tests")]


def run_case(args):
    import math
    import numpy as np
    from topogym.simulator import SimulatorConfig, Env
    from scene_preset_evidence import SceneEvidence, PhysicsSceneEvidence, source_identity
    before = source_identity(ROOT)
    parameters = json.loads(Path(args.task_parameters).read_text()) if args.task_parameters else {}
    cfg = SimulatorConfig(task_id=args.case, variation_id=args.variation,
                          enable_rgb=not args.no_rgb, enable_privileged=True,
                          task_parameters=parameters,
                          physics_dt_s=args.physics_dt,
                          control_decimation=round(.025/args.physics_dt),
                          work_dir=Path(args.output)/args.case/"episodes")
    evidence_class = PhysicsSceneEvidence if args.no_rgb else SceneEvidence
    evidence = evidence_class(Path(args.output)/args.case, args.case, cfg)
    if parameters:
        evidence.report["diagnostic_parameters_override"] = parameters
    env = Env(cfg)
    stability = None
    if args.probe == "slotted_stability":
        if args.case != "slotted_post_ring" or args.seconds <= 2.:
            raise ValueError("Slotted stability requires slotted_post_ring and seconds > 2")
        from slotted_scene_stability import SlottedStabilityAudit
        stability = SlottedStabilityAudit(env, evidence.folder, args.seconds)
        env.add_state_sink(stability.sample)
        evidence.report["scope"] = "unassisted initial scene stability; not task solved"
        evidence.save()
    if args.probe == "gravity":
        if args.case != "horseshoe_ring" or not 0 < args.seconds <= .15:
            raise ValueError("Gravity probe requires horseshoe_ring and 0 < seconds <= .15")
        from scene_preset_diagnostics import lifted_ring_class, ring_sample, check_gravity
        env._task_class = lifted_ring_class(env._task_class)
        evidence.report["diagnostic"] = "ring lifted 0.35 m in initial declaration; not default scene"
    gravity_samples = []
    if args.probe.startswith("terminal_"):
        if args.case != "buzz_wire_3d":
            raise ValueError("Terminal support diagnostics require buzz_wire_3d")
        from scene_preset_diagnostics import terminal_wand_class
        env._task_class = terminal_wand_class(env._task_class)
        evidence.report["diagnostic"] = "wand starts on terminal support; no mid-route traversal claim"
    error = None
    try:
        with evidence.stage("default_reset_home"):
            observation, info = env.reset(seed=0)
            evidence.scene_inventory(env)
            evidence.sample(env, observation, info, label="initial")
            if args.probe == "gravity":
                gravity_samples.append(ring_sample(env, info["sim_time_s"]))
        with evidence.stage("continuous_default_physics"):
            steps = math.ceil(args.seconds/(cfg.physics_dt_s*cfg.control_decimation))
            for i in range(steps):
                observation, reward, terminated, truncated, info = env.step({})
                evidence.sample(env, observation, info, action={}, label="hold_home")
                if args.probe == "gravity":
                    gravity_samples.append(ring_sample(env, info["sim_time_s"]))
                if terminated or truncated:
                    raise AssertionError(f"Early termination at {info['sim_time_s']}: {info}")
                if i % 20 == 0:
                    print(f"{args.case}: {info['sim_time_s']:.3f}s", flush=True)
        if args.probe in {"reach", "pickup", "terminal_reach", "terminal_pickup"}:
            from scene_preset_pickup import plan_pickup, execute_pickup
            with evidence.stage("loaded_robot_fixture_ik_path"):
                plan = plan_pickup(env)
                evidence.report["pickup_plan"] = plan
                evidence.save()
            if args.probe in {"pickup", "terminal_pickup"}:
                execute_pickup(env, evidence, plan, release=args.probe == "terminal_pickup")
        if args.probe == "layout_reach":
            from scene_preset_pickup import plan_layout_reach
            with evidence.stage("representative_layout_approaches"):
                evidence.report["layout_reach"] = plan_layout_reach(env)
                evidence.save()
                assert evidence.report["layout_reach"]["passed"], "Some layout approaches did not qualify"
        if args.probe == "layout_search":
            from scene_preset_pickup import search_threading_layout
            with evidence.stage("whole_assembly_candidate_search"):
                evidence.report["layout_search"] = search_threading_layout(env)
                evidence.save()
                assert evidence.report["layout_search"]["passed"], "No layout candidate met all filters"
        if args.probe == "home_clearance":
            from scene_preset_pickup import plan_home_clearance
            with evidence.stage("home_and_opening_collision_clearance"):
                evidence.report["home_clearance"] = plan_home_clearance(env)
                evidence.save()
                assert evidence.report["home_clearance"]["passed"], "Home/opening gap below 10 mm"
        evidence.report["source_unchanged_during_case"] = source_identity(ROOT) == before
        assert evidence.report["source_unchanged_during_case"]
        evidence.report["physical_time_s"] = evidence.report["last_info"]["sim_time_s"]
        if gravity_samples:
            evidence.report["gravity_test"] = check_gravity(gravity_samples)
    except BaseException:
        error = traceback.format_exc()
        print(error, flush=True)
    finally:
        try:
            if stability is not None:
                evidence.report["stability"] = stability.finish()
                if not evidence.report["stability"]["passed"] and not error:
                    error = "Initial scene settling thresholds failed; see stability report"
            evidence.close(error)
        finally:
            env.close()
    return 1 if error else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--tasks", nargs="+")
    parser.add_argument("--variation", default="base",
                        help="Explicit registered variation ID or difficulty alias")
    parser.add_argument("--seconds", type=float, default=3.)
    parser.add_argument("--no-rgb", action="store_true",
                        help="Explicit physics-only slotted stability run; no renderer fallback")
    parser.add_argument("--physics-dt", type=float, choices=(.0025, .00125), default=.0025,
                        help="Default or half physical step; control interval remains 0.025 s")
    parser.add_argument("--task-parameters", help="JSON file for explicitly labelled candidate parameters")
    parser.add_argument("--unchanged-seconds", type=float,
                        help="Optional shorter observation of tasks outside the nine restored scenes")
    parser.add_argument("--probe", choices=("scene", "gravity", "reach", "pickup",
        "terminal_reach", "terminal_pickup", "terminal_support", "layout_reach", "layout_search", "home_clearance", "slotted_stability"), default="scene")
    parser.add_argument("--visual-asset-root", default=os.environ.get(
        "TOPOGYM_VISUAL_ASSET_ROOT", str(ROOT/".external/nyx-assets")))
    parser.add_argument("--case", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.no_rgb and args.probe != 'slotted_stability':
        parser.error('--no-rgb requires --probe slotted_stability (per-tick physical audit)')
    os.environ["TOPOGYM_VISUAL_ASSET_ROOT"] = str(Path(args.visual_asset_root).expanduser().resolve())
    if args.seconds < 0:
        parser.error("seconds cannot be negative")
    if args.unchanged_seconds is not None and args.unchanged_seconds < 0:
        parser.error("unchanged-seconds cannot be negative")
    if args.case:
        return run_case(args)
    from topogym.config.registry import task_catalog
    tasks = args.tasks or [r["task_id"] for r in task_catalog()]
    from topogym.tasks.scene_presets import PRESETS
    seconds_by_task = {task: (args.unchanged_seconds if args.unchanged_seconds is not None
                             and task not in PRESETS else args.seconds) for task in tasks}
    if not set(tasks) <= {r["task_id"] for r in task_catalog()}:
        parser.error("unknown task")
    from scene_preset_evidence import source_identity
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    parameters = json.loads(Path(args.task_parameters).read_text()) if args.task_parameters else {}
    if parameters:
        (output/"candidate_parameters.json").write_text(json.dumps(parameters,indent=2)+"\n")
        args.task_parameters = str(output/"candidate_parameters.json")
    identity = source_identity(ROOT)
    (output/"source_identity.json").write_text(json.dumps(identity, indent=2)+"\n")
    snapshot = output/"source_snapshot"
    for relative in identity:
        target = snapshot/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT/relative, target)
    (output/"validation_spec.json").write_text(json.dumps(dict(
        tasks=tasks, variation_id=args.variation, seconds_by_task=seconds_by_task, probe=args.probe,
        physics_dt_s=args.physics_dt, control_interval_s=.025,
        candidate_parameters=parameters,
        scope=("actual continuous home-hold scene validation" if args.probe == "scene"
               else f"explicit {args.probe} diagnostic; not task solved"),
        assertions=["Nyx + compact_lab", "robot home initial state", "finite physical state",
                    "rigid penetration <= 1mm", "valid FEM volume and endpoint constraints",
                    "shared SensorFrame recording", "source identity unchanged",
                    "complete video decode"],
        exclusions=["full task solved", "robot grasp qualification", "long-time stability"],
        visual_review="required separately; nonempty RGB is not sufficient"), indent=2)+"\n")
    results = []
    for task in tasks:
        if source_identity(ROOT) != identity:
            raise RuntimeError("Source changed between cases; start a new evidence batch")
        command = [sys.executable, str(Path(__file__).resolve()), "--case", task,
                   "--variation", args.variation,
                   "--seconds", str(seconds_by_task[task]), "--probe", args.probe,
                   "--physics-dt", str(args.physics_dt), "--output", str(output)]
        if args.task_parameters:
            command += ["--task-parameters", args.task_parameters]
        if args.no_rgb:
            command += ['--no-rgb']
        with (output/f"{task}.log").open("w") as log:
            completed = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        results.append(dict(task=task, returncode=completed.returncode))
        (output/"summary.json").write_text(json.dumps(results, indent=2)+"\n")
        print(f"{task}: exit {completed.returncode}", flush=True)
    return int(any(r["returncode"] for r in results))


if __name__ == "__main__":
    raise SystemExit(main())
