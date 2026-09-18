"""Native-state, substep CCD audit of the threading scene and contact fixtures."""
import argparse
from dataclasses import asdict
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import time

import numpy as np
from omegaconf import OmegaConf, open_dict

from topogym.tasks.knot_untying.diagnostics import FemDiagnostics, LIMITS
from topogym.tasks.knot_untying.physics_probe import SolverLog
from .geometry import route_crossings

ROOT = Path(__file__).resolve().parents[3]


def make_config(args):
    from hydra import compose, initialize_config_dir
    with initialize_config_dir(version_base="1.3", config_dir=str(ROOT/"configs")):
        cfg = compose(config_name="rope_threading_preview")
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
    if args.refined:
        cfg.task.geometry.rope_subdivisions = 6
        cfg.task.geometry.radial_segments = 16
        cfg.task.rope.mesh.maxvolume = 1.e-8
    if args.tighter:
        cfg.task.rope.fem.newton_max_iterations = 200
        cfg.task.rope.fem.newton_tolerance = .005
    return cfg


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mode", choices=("free_settle", "ring_contact", "reference_prefix", "full_threading"), default="free_settle")
    parser.add_argument("--seconds", type=float)
    parser.add_argument("--dt", type=float, default=.005)
    parser.add_argument("--friction-eps", type=float)
    parser.add_argument("--robot-coupling", choices=("two_way_soft_constraint", "external_articulation"),
                        default="external_articulation")
    parser.add_argument("--without-robot", action="store_true")
    parser.add_argument("--refined", action="store_true")
    parser.add_argument("--tighter", action="store_true")
    parser.add_argument("--full-ccd", action="store_true", help="Disable conservative clearance certificates")
    parser.add_argument("--reference", type=Path, default=Path("runs/environment-solvability/rope_threading/reference_motion_v1"))
    parser.add_argument("--reference-speed", type=float, default=1.)
    parser.add_argument("--qualification", type=Path, help="Passed physics suite summary required before full execution")
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--fps", type=int, default=20)
    parser.add_argument("--resolution", type=int, nargs=2, default=(960, 540))
    args = parser.parse_args()
    reference_mode = args.mode in ("reference_prefix", "full_threading")
    if args.reference_speed <= 0:
        parser.error("Reference speed must be positive")
    if args.seconds is None:
        args.seconds = ({"free_settle": 5., "ring_contact": 20.}.get(args.mode)
                        if not reference_mode else (25. if args.mode == "reference_prefix" else 373.9955)/args.reference_speed+42.)
    if args.mode == "full_threading":
        if not args.qualification:
            parser.error("Full execution requires a passed --qualification summary")
        qualification = json.loads(args.qualification.read_text())
        if not qualification.get("passed"):
            parser.error("The supplied physics qualification did not pass")
    if args.dt <= 0 or args.seconds <= 0:
        parser.error("Time step and duration must be positive")
    output = args.output.resolve()
    if any((output/name).exists() for name in ("report.json", "progress.json", "validation_spec.json")):
        raise FileExistsError("Use a new evidence directory")
    output.mkdir(parents=True, exist_ok=True)
    cfg = make_config(args)
    qualification_evidence = None
    if args.mode == "full_threading":
        from .qualification import verify_for_execution
        qualification_evidence = verify_for_execution(args.qualification, cfg, args.reference_speed, args.reference)
    actions = None
    if args.mode == "ring_contact":
        from .contact_probe import RingContactActions
        actions = RingContactActions()
        args.without_robot = True
    if reference_mode:
        from .reference_actions import ReferenceThreadingActions
        actions = ReferenceThreadingActions(args.reference, speed=args.reference_speed,
                                            prefix=args.mode == "reference_prefix")
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
    spec = dict(mode=args.mode, duration_s=args.seconds, dt=args.dt, substeps=int(cfg.env.sim.substeps),
        limits=asdict(LIMITS), include_robot=not args.without_robot, robot_coupling=args.robot_coupling,
        solver=OmegaConf.to_container(cfg.task.rope, resolve=True),
        source_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        versions={name: version(name) for name in ("genesis-world", "pyuipc", "ipctk", "numpy")},
        actuation=actions.specification() if actions else dict(kind="none"),
        runtime_fem_position_overwrites=False, runtime_velocity_resets=False, full_demo=False,
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
        monitor = FemDiagnostics(task, loaded=actions is not None, audit_rigid=True)
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
        (output/"validation_spec.json").write_text(json.dumps(spec, indent=2)+"\n")
        np.savez_compressed(output/"mesh.npz", initial_nodes=monitor.initial, rest_volumes=monitor.rest_volumes,
                            elements=monitor.elements, surface_faces=monitor.faces, material_rings=monitor.rings)
    except Exception as exc:
        if recorder:
            recorder.stack.close()
        if monitor:
            monitor.close()
        (output/"report.json").write_text(json.dumps(dict(passed=False, setup_succeeded=False,
            mode=args.mode, error=f"{type(exc).__name__}: {exc}", full_demo=False), indent=2)+"\n")
        raise
    start = time.perf_counter()
    log, failure = SolverLog(output), None
    try:
        monitor.install()
        with log:
            for step in range(round(args.seconds/args.dt)):
                if (output/"STOP").exists():
                    raise RuntimeError("Explicitly stopped; this rollout is incomplete")
                if actions:
                    actions.update(step*args.dt)
                task.scene.step()
                if hasattr(actions, "observe"):
                    actions.observe((step+1)*args.dt, monitor)
                if recorder:
                    recorder.capture(step+1, (step+1)*args.dt, actions)
                log.update()
                if step % max(1, round(.25/args.dt)) == 0:
                    progress = dict(time_s=(step+1)*args.dt, wall_seconds=time.perf_counter()-start,
                        rms_speed_m_s=monitor.window[-1][2]["rms_speed_m_s"], min_J=monitor.min_J,
                        length_change=monitor.maxima["max_total_length_relative_change"],
                        diagnostics_wall_seconds=monitor.elapsed_diagnostics_s,
                        crossings=route_crossings(monitor.last_centers, task.layout.rings(), task.layout.radius))
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
        initial_collision_audit=spec["initial_collision_audit"],
        solver=log.report(monitor.count), scope="native_substep_physics_audit", full_demo=False,
        robot_grasp_qualified=False, complete_physics_suite_passed=bool(qualification_evidence),
        final_crossings=route_crossings(getattr(monitor, "last_centers", task.centerline),
                                        task.layout.rings(), task.layout.radius),
        actuation=actions.report() if actions else dict(kind="none", final_active_constraints=0))
    report["passed"] = bool(failure is None and monitor.count > 0 and report["mechanical_checks_passed"]
        and report["solver"]["convergence_verified"] and report["actuation"].get("passed", True)
        and (not report["final_crossings"] if args.mode == "free_settle" else True))
    report["full_threading_verified"] = bool(report["passed"] and args.mode == "full_threading")
    report["full_demo"] = report["full_threading_verified"]
    report["robot_grasp_qualified"] = bool(report["passed"] and reference_mode)
    report["reference_speed"] = args.reference_speed if reference_mode else None
    (output/"report.json").write_text(json.dumps(report, indent=2)+"\n")
    (output/"trace.json").write_text(json.dumps(monitor.samples, indent=2)+"\n")
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
