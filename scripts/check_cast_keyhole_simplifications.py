#!/usr/bin/env python3
"""Freeze source, hold home for a few control steps, save real Nyx frames/video.

This is a short stability diagnostic, not a solving or Harbor qualification.
Only the child process owned by this invocation is stopped at 90% host memory.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def worker(args):
    import numpy as np
    import torch
    from scipy.spatial.transform import Rotation
    from topogym.simulator import Env, SimulatorConfig
    from topogym.tasks.cast_keyhole.common import recommended_grasp_assist
    from topogym.recording import RecordingSession
    from topogym.recording.segment import save_rgb
    from topogym.recording.encoding import probe
    from topogym.utils.io import to_jsonable, write_json_atomic
    torch.set_num_threads(1)
    config = SimulatorConfig(task_id="cast_keyhole", variation_id=args.variation,
        robot_id="aloha", compute_backend=args.backend, enable_rgb=not args.no_rgb,
        control_mode="JOINT_ABS", enable_privileged=True, max_physics_steps=None,
        work_dir=args.output/"scene", grasp_assist=recommended_grasp_assist(args.variation, args.seed))
    report = dict(status="running", scope="short home-hold diagnostic; no solution qualification",
        config=to_jsonable(config), requested_control_steps=args.steps, seed=args.seed,
        full_robot_solve_verified=False, long_term_stability_verified=False,
        thresholds=dict(translation_drift_m=.005, rotation_drift_rad=.05,
                        final_linear_speed_m_s=.05, final_angular_speed_rad_s=.5),
        started=time.time())
    write_json_atomic(args.output/"report.json", report)
    try:
        if args.backend == "cuda":
            report["gpu"] = torch.cuda.get_device_name()
        from contextlib import nullcontext
        with Env(config) as env:
            _, info = env.reset(seed=args.seed)
            report.update(instance_id=env._task.instance_id,
                          asset_sha256=dict(env._asset_build.sha256),
                          terminal=env._task.terminal_metadata(), initial_info=to_jsonable(info))
            report["task_entities"] = sorted(env._task.local_vertices)
            report["remainder_entities"] = list(env._task.placement_remainder)
            names = ("keyhole_gold", "keyhole_silver")

            def sample():
                state = env._world.read_state()
                return dict(physics_step=env._world.physics_step, sim_time_s=env._world.sim_time_s,
                            bodies={n: to_jsonable(state["bodies"][n]) for n in names},
                            task_result=to_jsonable(env._task.result))

            states = [sample()]
            if not args.no_rgb:
                frame = env.sensor_frame()
                report["initial_frames"] = save_rgb(args.output, "initial", frame)
            write_json_atomic(args.output/"report.json", report)
            recorder = (RecordingSession(args.output/"recording", metadata=dict(
                scope=report["scope"], instance_id=report["instance_id"])) if not args.no_rgb else nullcontext())
            with recorder as recording:
                if recording:
                    recording.append(frame)
                for _ in range(args.steps):
                    # Omitted groups retain the accepted native home targets.
                    result = env.step({})
                    states.append(sample())
                    if recording:
                        frame = env.sensor_frame()
                        recording.append(frame)
                    if len(states) == 4 and recording:
                        report["three_step_frames"] = save_rgb(args.output, "after_3_steps", frame)
                    if (len(states)-1) % 10 == 0:
                        print(f"Completed {len(states)-1}/{args.steps} control steps", flush=True)
                    if result[2] or result[3]:
                        break
                report["states"] = states
                report["executed_control_steps"] = len(states)-1
                report["executed_physics_ticks"] = states[-1]["physics_step"]-states[0]["physics_step"]
                report["simulated_duration_s"] = states[-1]["sim_time_s"]-states[0]["sim_time_s"]
                motion = {}
                for name in names:
                    first = states[0]["bodies"][name]
                    r0 = Rotation.from_quat(np.asarray(first["quaternion_wxyz"])[[1, 2, 3, 0]])
                    rows = [s["bodies"][name] for s in states]
                    motion[name] = dict(
                        maximum_translation_drift_m=max(float(np.linalg.norm(
                            np.asarray(b["position_m"])-first["position_m"])) for b in rows),
                        maximum_rotation_drift_rad=max(float((Rotation.from_quat(
                            np.asarray(b["quaternion_wxyz"])[[1, 2, 3, 0]])*r0.inv()).magnitude()) for b in rows),
                        final_linear_speed_m_s=float(np.linalg.norm(rows[-1]["linear_velocity_m_s"])),
                        final_angular_speed_rad_s=float(np.linalg.norm(rows[-1]["angular_velocity_rad_s"])),
                        finite=all(np.isfinite(np.r_[b["position_m"], b["quaternion_wxyz"],
                            b["linear_velocity_m_s"], b["angular_velocity_rad_s"]]).all() for b in rows))
                report["motion"] = motion
                quiet = all(m["finite"] and m["maximum_translation_drift_m"] <= .005
                    and m["maximum_rotation_drift_rad"] <= .05 and m["final_linear_speed_m_s"] <= .05
                    and m["final_angular_speed_rad_s"] <= .5 for m in motion.values())
                report["short_stability_passed"] = bool(quiet and len(states)-1 == args.steps
                    and report["executed_physics_ticks"] == args.steps*config.control_decimation
                    and all(not s["task_result"]["terminated"] and not s["task_result"]["task_success"] for s in states))
                report["status"] = "passed" if report["short_stability_passed"] else "failed"
                report["stability_scope_s"] = report["simulated_duration_s"]
                write_json_atomic(args.output/"report.json", report)
                if recording:
                    report["final_frames"] = save_rgb(args.output, "after_steps", frame)
                    recording.append_final(frame)
                    recording.finish(dict(short_stability_passed=report["short_stability_passed"],
                                          task_success=bool(env.is_solved())))
            if not args.no_rgb:
                report["videos"] = {p.stem: probe(p, decode=True)
                    for p in sorted((args.output/"recording/videos").glob("*.mp4"))}
            if args.check_grasp:
                from topogym.assets.variation_resources import read_json
                from topogym.planning.cast_keyhole.simplified_policy import SimplifiedKeyholePolicy
                from topogym.planning.cast_keyhole.kinematics import preflight_simplified_pickup
                geometry = read_json(env._task.geometry_resource)
                _, built = env._task.build_assets(args.output/"planning_assets")
                origins = {b["name"]: np.asarray(b["origin_m"]) for b in built["bodies"]}
                policy = SimplifiedKeyholePolicy(geometry=geometry, variation=args.variation,
                    body_origins=origins, goal_region=report["terminal"]["goal_region"],
                    mount_position=[0., 0., 0.], canonical_vertices={}, part="pickup")
                # The hold diagnostic uses JOINT observations; this owner-side
                # preflight needs TCP poses and authored body states as well.
                policy.obs = dict(robot=env._robot.observe(), privileged=dict(world=env._world.read_state()))
                print("Starting read-only pickup IK/mesh preflight", flush=True)
                before_tick = env._world.physics_step
                preflight = preflight_simplified_pickup(env._robot, env._world.entities, origins,
                    geometry, policy, env._task.table_height_m)
                assert before_tick == env._world.physics_step
                write_json_atomic(args.output/"grasp_preflight.json", preflight)
                report["grasp_preflight_passed"] = preflight["passed"]
                if not preflight["passed"]:
                    report["status"] = "grasp_preflight_failed"
    except BaseException:
        report.update(status="error", error=traceback.format_exc())
        raise
    finally:
        report["wall_time_s"] = time.time()-report["started"]
        write_json_atomic(args.output/"report.json", report)
    return 0 if report["status"] == "passed" else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variation", choices=("very_easy", "easier", "easy", "medium", "hard"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--steps", type=int, default=3)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--backend", choices=("cuda", "cpu"), default="cuda")
    parser.add_argument("--no-rgb", action="store_true")
    parser.add_argument("--check-grasp", action="store_true", help="Read-only native IK and full mesh pickup preflight")
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.steps <= 100:
        parser.error("steps must be in 1..100")
    if args.backend == "cpu" and not args.no_rgb:
        parser.error("CPU physics requires explicit --no-rgb; screenshots use CUDA/Nyx")
    if args.check_grasp and args.variation not in {"very_easy", "easier"}:
        parser.error("--check-grasp is for the two simplified policies")
    args.output = args.output.resolve()
    if args.worker:
        return worker(args)
    import psutil
    args.output.mkdir(parents=True, exist_ok=False)
    from scripts.test_policy_cube_transfer import snapshot
    source = snapshot(args.output)
    command = [sys.executable, str(source/"scripts/check_cast_keyhole_simplifications.py"),
        "--worker", "--variation", args.variation, "--output", str(args.output),
        "--steps", str(args.steps), "--seed", str(args.seed), "--backend", args.backend]
    if args.no_rgb:
        command.append("--no-rgb")
    if args.check_grasp:
        command.append("--check-grasp")
    (args.output/"invocation.json").write_text(json.dumps(command, indent=2)+"\n")
    with (args.output/"runtime.log").open("x") as log, (args.output/"resources.jsonl").open("x") as resources:
        child = subprocess.Popen(command, cwd=source, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True, env=dict(os.environ, PYTHONPATH=str(source), OMP_NUM_THREADS="1",
                OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1",
                TOPOGYM_VISUAL_ASSET_ROOT=str(ROOT/".external/nyx-assets")))
        while child.poll() is None:
            row = dict(time=time.time(), cpu_percent=psutil.cpu_percent(),
                       memory_percent=psutil.virtual_memory().percent)
            resources.write(json.dumps(row)+"\n"); resources.flush()
            if row["memory_percent"] >= 90.:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                break
            time.sleep(1)
        code = child.wait()
    print(f"exit={code}; {args.output}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
