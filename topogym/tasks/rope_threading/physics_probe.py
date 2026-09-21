"""Native-state, substep CCD audit of the threading scene and contact fixtures."""
import argparse
from dataclasses import asdict
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import time

import numpy as np
from omegaconf import OmegaConf, open_dict

from topogym.tasks.knot_untying.diagnostics import FemDiagnostics, LIMITS
from topogym.tasks.knot_untying.physics_probe import SolverLog
from .geometry import route_crossings

ROOT = Path(__file__).resolve().parents[3]


def validate_execution_mode(mode, qualification, exploratory_reason):
    """An explicitly requested trial leaves formal qualification pending."""
    if exploratory_reason is not None:
        if mode != "full_threading" or not exploratory_reason.strip():
            raise ValueError("Exploration requires full_threading and a nonempty reason")
        if qualification is not None:
            raise ValueError("Exploration cannot also claim a passed qualification")
    elif mode == "full_threading":
        if qualification is None:
            raise ValueError("Full execution requires a passed --qualification summary")
        if not json.loads(Path(qualification).read_text()).get("passed"):
            raise ValueError("The supplied physics qualification did not pass")


def classify_execution(report, mode, exploratory_reason):
    """Separate observed task completion from physical qualification."""
    actions = report.get("actuation", {})
    checks = actions.get("checks", {})
    full = mode == "full_threading"
    report["exploratory"] = exploratory_reason is not None
    report["exploratory_reason"] = exploratory_reason
    report["full_sequence_completed"] = bool(full and checks.get("source_sequence_complete")
                                             and checks.get("post_release_observed"))
    report["full_task_observed"] = bool(report["full_sequence_completed"] and actions.get("passed"))
    report["full_threading_verified"] = bool(full and report["passed"]
        and report.get("complete_physics_suite_passed") and not report["exploratory"])
    report["full_demo"] = report["full_threading_verified"]


def make_config(args):
    from hydra import compose, initialize_config_dir
    with initialize_config_dir(version_base="1.3", config_dir=str(ROOT/"configs")):
        cfg = compose(config_name=args.config_name)
    cfg.env.cameras = {}
    cfg.env.renderer.type = "rasterizer"
    cfg.env.presentation.background = "checker"
    cfg.env.sim.dt = args.dt
    with open_dict(cfg.task):
        cfg.task.robot_coupling = args.robot_coupling
        cfg.task.robot_rigid_collision = dict(enable_collision=True, enable_self_collision=True,
                                              enable_neutral_collision=True, enable_adjacent_collision=False)
    if args.friction_eps is not None:
        with open_dict(cfg.task.rope.fem):
            cfg.task.rope.fem.contact_eps_velocity = args.friction_eps
    if args.young_modulus is not None:
        cfg.task.rope.fem.E = args.young_modulus
    if args.contact_distance is not None:
        cfg.task.rope.fem.contact_d_hat = args.contact_distance
    if args.initial_rope_lift:
        with open_dict(cfg.task.geometry):
            cfg.task.geometry.rope_height_offset_m = args.initial_rope_lift
    if args.refined:
        from .mesh_resolution import refinement_settings
        finer = refinement_settings(cfg.task.geometry, cfg.task.rope.mesh)
        cfg.task.geometry.rope_subdivisions = finer['rope_subdivisions']
        cfg.task.geometry.radial_segments = finer['radial_segments']
        cfg.task.rope.mesh.maxvolume = finer['maxvolume']
    if args.tighter:
        cfg.task.rope.fem.newton_max_iterations = 200
        cfg.task.rope.fem.newton_tolerance = .005
    return cfg


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--config-name", default="rope_threading_preview")
    parser.add_argument("--mode", choices=("free_settle", "ring_contact", "reference_prefix", "full_threading"), default="free_settle")
    parser.add_argument("--seconds", type=float)
    parser.add_argument("--dt", type=float, default=.005)
    parser.add_argument("--friction-eps", type=float)
    parser.add_argument("--young-modulus", type=float, help="Rope Young's modulus in Pa")
    parser.add_argument("--contact-distance", type=float, help="IPC contact activation distance in metres")
    parser.add_argument("--initial-rope-lift", type=float, default=0., help="Translate only the initial rope upward in metres")
    parser.add_argument("--sample-interval", type=float, default=.02)
    parser.add_argument("--startup-diagnostics", action="store_true", help="Save startup motion at every native substep")
    parser.add_argument("--robot-coupling", choices=("two_way_soft_constraint", "external_articulation"),
                        default="external_articulation")
    parser.add_argument("--without-robot", action="store_true")
    parser.add_argument("--refined", action="store_true")
    parser.add_argument("--tighter", action="store_true")
    parser.add_argument("--full-ccd", action="store_true", help="Disable conservative clearance certificates")
    parser.add_argument("--reference", type=Path, default=Path("runs/environment-solvability/rope_threading/reference_motion_v1"))
    parser.add_argument("--reference-speed", type=float, default=1.)
    parser.add_argument("--feedback-handoff", action="store_true",
                        help="Replace the R2 handoff with measured-state replanning and contact gates")
    parser.add_argument("--qualification", type=Path, help="Passed physics suite summary required before full execution")
    parser.add_argument("--exploratory-reason", help="Explicitly run the full sequence with qualification pending; retain all native checks")
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--fps", type=int, default=20)
    parser.add_argument("--resolution", type=int, nargs=2, default=(960, 540))
    args = parser.parse_args()
    for name in ("young_modulus", "contact_distance", "sample_interval"):
        value = getattr(args, name)
        if value is not None and (not np.isfinite(value) or value <= 0):
            parser.error(f"{name} must be finite and positive")
    if not np.isfinite(args.initial_rope_lift) or args.initial_rope_lift < 0:
        parser.error("initial_rope_lift must be finite and nonnegative")
    reference_mode = args.mode in ("reference_prefix", "full_threading")
    if args.feedback_handoff and args.mode != "full_threading":
        parser.error("Feedback handoff is available only for full_threading")
    if args.reference_speed <= 0:
        parser.error("Reference speed must be positive")
    default_duration = args.seconds is None
    if default_duration:
        args.seconds = ({"free_settle": 5., "ring_contact": 20.}.get(args.mode)
                        if not reference_mode else (25. if args.mode == "reference_prefix" else 373.9955)/args.reference_speed+42.)
    try:
        validate_execution_mode(args.mode, args.qualification, args.exploratory_reason)
    except ValueError as exc:
        parser.error(str(exc))
    if args.dt <= 0 or args.seconds <= 0:
        parser.error("Time step and duration must be positive")
    output = args.output.resolve()
    if any((output/name).exists() for name in ("report.json", "progress.json", "validation_spec.json")):
        raise FileExistsError("Use a new evidence directory")
    output.mkdir(parents=True, exist_ok=True)
    process_id = os.getpid()
    (output/"process_info.json").write_text(json.dumps(dict(pid=process_id,
        start_ticks=Path(f"/proc/{process_id}/stat").read_text().split()[21]), indent=2)+"\n")
    cfg = make_config(args)
    qualification_evidence = None
    if args.mode == "full_threading" and args.exploratory_reason is None:
        from .qualification import verify_for_execution
        qualification_evidence = verify_for_execution(args.qualification, cfg, args.reference_speed, args.reference)
    actions = None
    validation_cfg = cfg.task.get("validation", {})
    if args.mode == "ring_contact":
        from .contact_probe import RingContactActions
        actions = RingContactActions(release_height_m=validation_cfg.get("fixture_release_height_m"),
            contact_distance_m=float(cfg.task.rope.fem.contact_d_hat),
            release_horizontal_offset_m=validation_cfg.get("fixture_release_horizontal_offset_m", .12),
            post_release_s=validation_cfg.get("fixture_post_release_s", 8.))
        if default_duration:
            args.seconds = actions.duration_s
        args.without_robot = True
    if reference_mode:
        from .reference_actions import ReferenceThreadingActions
        actions = ReferenceThreadingActions(args.reference, speed=args.reference_speed,
            contact_distance_m=float(cfg.task.rope.fem.contact_d_hat),
            settle_s=validation_cfg.get("final_post_sequence_settle_s", 5.),
            prefix=args.mode == "reference_prefix", release_limits=(
                dict(max_unsupported_height_m=float(validation_cfg.max_unsupported_release_height_m),
                     max_supported_material_span_m=float(validation_cfg.max_supported_release_material_span_m))
                if "max_unsupported_release_height_m" in validation_cfg else None))
        if args.feedback_handoff:
            from .feedback_actions import FeedbackThreadingActions
            actions = FeedbackThreadingActions(args.reference, speed=args.reference_speed,
                contact_distance_m=float(cfg.task.rope.fem.contact_d_hat), settle_s=actions.settle_s,
                release_limits=actions.release_limits, cfg=cfg, output=output)
        if default_duration:
            args.seconds = actions.cutoff/args.reference_speed+36.+actions.settle_s+(90. if args.feedback_handoff else 0.)
        args.without_robot = False
    camera_metadata = None
    if args.record:
        if not reference_mode:
            parser.error("Physical video recording is available for robot runs")
        from topogym.world.aloha_cameras import configure_aloha_rig
        camera_metadata = configure_aloha_rig(cfg, keep=(), resolution=args.resolution)
        with open_dict(cfg.env.cameras):
            cfg.env.cameras["detail"] = dict(res=list(args.resolution), pos=[.92, .98, 1.75],
                lookat=[-.11, .05, 1.10], up=[0, 0, 1], fov=39, near=.005, far=12.)
        cfg.env.renderer.type = "nyx"
        cfg.env.presentation.background = "compact_lab"
    OmegaConf.save(cfg, output/"config.yaml", resolve=True)
    files = sorted(Path(__file__).parent.glob("*.py"))
    files += [ROOT/"topogym/tasks/knot_untying"/f for f in
              ("diagnostics.py", "rigid_diagnostics.py", "physics_probe.py", "ipc_compat.py", "robot_probe.py", "control.py")]
    files += [ROOT/path for path in ("topogym/robot/assets.py", "topogym/robot/aloha.py",
        "topogym/world/genesis_ipc_vertex_constraints.py", "topogym/world/rope_backends/fem_ipc.py",
        "topogym/primitives/fem_attachment.py")]
    # The forward-only cache adapter calls this audited original method.
    import importlib.util
    genesis_package = Path(importlib.util.find_spec("genesis").origin).parent
    files.append(genesis_package/"engine/solvers/fem_solver.py")
    spec = dict(mode=args.mode, duration_s=args.seconds, dt=args.dt, substeps=int(cfg.env.sim.substeps),
        limits=asdict(LIMITS), include_robot=not args.without_robot, robot_coupling=args.robot_coupling,
        solver=OmegaConf.to_container(cfg.task.rope, resolve=True),
        source_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        versions={name: version(name) for name in ("genesis-world", "pyuipc", "ipctk", "numpy")},
        actuation=actions.specification() if actions else dict(kind="none"),
        runtime_fem_position_overwrites=False, runtime_velocity_resets=False, full_demo=False,
        exploratory=args.exploratory_reason is not None, exploratory_reason=args.exploratory_reason,
        qualification=qualification_evidence)
    (output/"validation_spec.json").write_text(json.dumps(spec, indent=2)+"\n")
    for p in files:
        destination = output/"implementation"/p.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(p.read_bytes())
    import genesis as gs
    from topogym.robot import initialize_robot_controller
    from .scene import ThreadingSceneBuilder
    gs.init(backend=gs.cuda, seed=7, logging_level="warning")
    monitor = recorder = None
    controller = None
    try:
        task = ThreadingSceneBuilder(cfg.env, cfg.task, cfg.robot_control).build(
            asset_dir=output/"assets", include_robot=not args.without_robot,
            pre_build=actions.declare if actions else None)
        if not args.without_robot:
            external = args.robot_coupling == "external_articulation"
            controller = initialize_robot_controller(scene=task.scene, manifest=task.manifest,
                robot_cfg=cfg.robot_control, settle_steps=0, reset_home=not external)
            if external:
                for side, arm in controller.arms.items():
                    arm.set_arm_qpos(cfg.robot_control.home[side][:6])
                    arm.set_gripper(cfg.robot_control.home[side][6])
        diagnostic_type = FemDiagnostics
        if args.startup_diagnostics:
            from .startup_diagnostics import StartupDiagnostics
            diagnostic_type = StartupDiagnostics
        monitor = diagnostic_type(task, loaded=actions is not None, audit_rigid=True,
                                  sample_interval_s=args.sample_interval)
        if task.table_contact:
            task.table_contact.observe(monitor.initial, initial=True)
            original_observe = monitor.observe

            def observe_with_table_bounds():
                original_observe()
                task.table_contact.observe(monitor.last_positions)

            monitor.observe = observe_with_table_bounds
        if not args.full_ccd:
            from .diagnostics import CertifiedRigidSurfaceCCD
            monitor.ccd.close()
            monitor.ccd = CertifiedRigidSurfaceCCD(task, monitor.initial, monitor.faces)
        spec["initial_collision_audit"] = dict(
            fem_self_intersection=monitor.ccd.checker.initial_intersections,
            rigid_intersections=[p["name"] for p in monitor.ccd.parts
                                 if p["checker"] is not None and p["checker"].initial_intersections])
        if hasattr(actions, "configure"):
            actions.configure(task, controller, monitor)
        if args.record:
            from .recording import ThreadingRecorder
            recorder = ThreadingRecorder(task, output, fps=args.fps, dt=args.dt, metadata=camera_metadata)
        spec["native_ipc_config"] = task.scene.sim.coupler._ipc_scene.config().to_json()
        spec["deformation_damping"] = task.damping.specification() if task.damping else None
        spec["table_contact"] = task.table_contact.specification() if task.table_contact else None
        (output/"validation_spec.json").write_text(json.dumps(spec, indent=2)+"\n")
        np.savez_compressed(output/"mesh.npz", initial_nodes=monitor.initial, rest_volumes=monitor.rest_volumes,
                            elements=monitor.elements, surface_faces=monitor.faces, material_rings=monitor.rings)
    except Exception as exc:
        if recorder:
            recorder.stack.close()
        if monitor:
            monitor.close()
        (output/"report.json").write_text(json.dumps(dict(passed=False, setup_succeeded=False,
            mode=args.mode, error=f"{type(exc).__name__}: {exc}", full_demo=False,
            exploratory=args.exploratory_reason is not None,
            exploratory_reason=args.exploratory_reason), indent=2)+"\n")
        raise
    start = time.perf_counter()
    log, failure = SolverLog(output), None
    timings = dict(control_s=0., physics_step_s=0., robot_audit_s=0., rendering_s=0.)
    try:
        monitor.install()
        with log:
            for step in range(round(args.seconds/args.dt)):
                if (output/"STOP").exists():
                    raise RuntimeError("Explicitly stopped; this rollout is incomplete")
                if actions:
                    mark = time.perf_counter()
                    actions.update(step*args.dt)
                    timings["control_s"] += time.perf_counter()-mark
                mark = time.perf_counter()
                task.scene.step()
                timings["physics_step_s"] += time.perf_counter()-mark
                if hasattr(actions, "observe"):
                    mark = time.perf_counter()
                    actions.observe((step+1)*args.dt, monitor)
                    timings["robot_audit_s"] += time.perf_counter()-mark
                if recorder:
                    mark = time.perf_counter()
                    recorder.capture(step+1, (step+1)*args.dt, actions)
                    timings["rendering_s"] += time.perf_counter()-mark
                log.update()
                if step % max(1, round(.25/args.dt)) == 0:
                    import torch
                    progress = dict(time_s=(step+1)*args.dt, wall_seconds=time.perf_counter()-start,
                        rms_speed_m_s=monitor.window[-1][2]["rms_speed_m_s"], min_J=monitor.min_J,
                        length_change=monitor.maxima["max_total_length_relative_change"],
                        max_local_axial_strain=monitor.maxima["max_local_axial_strain"],
                        solver_frames=log.frames, solver_converged_frames=log.converged,
                        max_newton_iterations=log.max_iterations, solver_warning_count=len(log.warnings),
                        diagnostics_wall_seconds=monitor.elapsed_diagnostics_s,
                        timing_seconds=dict(timings),
                        gpu_tensor_allocated_bytes=torch.cuda.memory_allocated(),
                        retained_fem_checkpoints=len(task.scene.sim.fem_solver._ckpt),
                        crossings=route_crossings(monitor.last_centers, task.layout.rings(), task.layout.radius))
                    if reference_mode:
                        progress.update(stage=actions.stage, source_time_s=actions.source_time,
                            active_grasps=dict(actions.owners),
                            max_grasp_follow_error_m=actions.max_follow_error,
                            max_native_robot_surface_error_m=actions.max_native_pose_error,
                            last_native_finger_gaps_m=dict(actions.finger_gaps))
                    (output/"progress.json").write_text(json.dumps(progress, indent=2)+"\n")
                    print(json.dumps(progress), file=log.progress, flush=True)
                if step % max(1, round(1./args.dt)) == 0:
                    (output/"partial_trace.json").write_text(json.dumps(monitor.samples)+"\n")
                    np.savez_compressed(output/"partial_trajectory.npz", times=[m["time_s"] for m in monitor.samples],
                        centerlines=np.asarray(monitor.centers), final_nodes=monitor.last_positions,
                        final_velocity=monitor.last_velocity)
                    if hasattr(actions, "samples"):
                        (output/"partial_contact_trace.json").write_text(json.dumps(actions.samples)+"\n")
                if hasattr(actions, "finished") and actions.finished((step+1)*args.dt):
                    break
    except Exception as exc:
        failure = f"{type(exc).__name__}: {exc}"
    finally:
        if hasattr(actions, "close_contact_monitors"):
            actions.close_contact_monitors()
        monitor.close()
    report = monitor.report()
    report["ccd_statistics"] = monitor.ccd.statistics() if hasattr(monitor.ccd, "statistics") else None
    report.update(mode=args.mode, error=failure, wall_seconds=time.perf_counter()-start,
        centerline_interpolation=task.layout.centerline_interpolation,
        timing_seconds=timings,
        initial_collision_audit=spec["initial_collision_audit"],
        solver=log.report(monitor.count), scope="native_substep_physics_audit", full_demo=False,
        robot_grasp_qualified=False, complete_physics_suite_passed=bool(qualification_evidence),
        final_crossings=route_crossings(getattr(monitor, "last_centers", task.centerline),
                                        task.layout.rings(), task.layout.radius),
        actuation=actions.report() if actions else dict(kind="none", final_active_constraints=0))
    report["passed"] = bool(failure is None and monitor.count > 0 and report["mechanical_checks_passed"]
        and report["solver"]["convergence_verified"] and report["actuation"].get("passed", True)
        and (not report["final_crossings"] if args.mode == "free_settle" else True))
    report["deformation_damping"] = task.damping.report(monitor.count) if task.damping else None
    if task.damping:
        report["passed"] = bool(report["passed"] and report["deformation_damping"]["passed"])
    report["runtime_memory"] = task.memory_policy.report()
    report["passed"] = bool(report["passed"] and report["runtime_memory"]["passed"])
    report["table_contact"] = task.table_contact.report(monitor.count) if task.table_contact else None
    if task.table_contact:
        report["passed"] = bool(report["passed"] and report["table_contact"]["passed"])
    classify_execution(report, args.mode, args.exploratory_reason)
    report["robot_grasp_qualified"] = bool(report["passed"] and reference_mode)
    report["reference_speed"] = args.reference_speed if reference_mode else None
    (output/"report.json").write_text(json.dumps(report, indent=2)+"\n")
    (output/"trace.json").write_text(json.dumps(monitor.samples, indent=2)+"\n")
    if hasattr(monitor, "startup_samples"):
        (output/"startup_trace.json").write_text(json.dumps(monitor.startup_samples, indent=2)+"\n")
    if hasattr(actions, "samples"):
        (output/"contact_trace.json").write_text(json.dumps(actions.samples, indent=2)+"\n")
    np.savez_compressed(output/"trajectory.npz", times=[m["time_s"] for m in monitor.samples],
        centerlines=np.asarray(monitor.centers), initial_centerline=task.centerline,
        final_nodes=getattr(monitor, "last_positions", monitor.initial),
        final_velocity=getattr(monitor, "last_velocity", np.zeros_like(monitor.initial)))
    if recorder:
        recorder.close(report)
    print(json.dumps(report, indent=2), flush=True)
    if not report["passed"]:
        raise SystemExit("Physics gate did not pass; see report.json")


if __name__ == "__main__":
    main()
