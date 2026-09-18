"""Execute reproducible, independently monitored FEM stability experiments."""
import argparse
from dataclasses import asdict
import gzip
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import re
import sys
import time

import numpy as np
from omegaconf import OmegaConf, open_dict

from .diagnostics import FemDiagnostics, LIMITS
from .geometry import projected_crossings


ROOT = Path(__file__).resolve().parents[3]


class SolverLog:
    """Preserve native IPC convergence evidence without flooding the console."""
    def __init__(self, folder):
        self.path = Path(folder)/'solver.log'
        self.frames, self.converged, self.max_iterations = 0, 0, 0
        self.warnings = []
        self.pending_line = ''

    def __enter__(self):
        import uipc
        sys.stdout.flush()
        sys.stderr.flush()
        self.saved = [os.dup(1), os.dup(2)]
        self.progress = os.fdopen(os.dup(1), 'w', buffering=1)
        self.file = self.path.open('wb', buffering=0)
        self.reader = self.path.open()
        for fd in (1, 2):
            os.dup2(self.file.fileno(), fd)
        uipc.Logger.set_pattern('%v')
        uipc.Logger.set_level(uipc.Logger.Level.Info)
        return self

    def update(self):
        chunk = self.pending_line+self.reader.read()
        complete, _, self.pending_line = chunk.rpartition('\n')
        chunk = complete
        self.frames += len(re.findall(r'<<< End Frame:', chunk))
        iterations = [int(x) for x in re.findall(r'Newton Iteration Converged with Iteration Count: (\d+)', chunk)]
        self.converged += len(iterations)
        exhausted = [int(x) for x in re.findall(r'Newton Iteration Exits with Max Iteration: (\d+)', chunk)]
        self.max_iterations = max([self.max_iterations, *iterations, *exhausted])
        self.warnings += [line for line in chunk.splitlines()
                          if any(s in line.lower() for s in ('not converge', 'failed', 'exceed', 'nan',
                                                            'reach max', 'exits with max iteration'))]

    def __exit__(self, *args):
        import uipc
        uipc.Logger.set_level(uipc.Logger.Level.Error)
        self.update()
        for fd, saved in zip((1, 2), self.saved):
            os.dup2(saved, fd)
            os.close(saved)
        self.progress.close()
        self.reader.close()
        self.file.close()
        with self.path.open('rb') as source, gzip.open(str(self.path)+'.gz', 'wb') as target:
            for chunk in iter(lambda: source.read(1024*1024), b''):
                target.write(chunk)
        self.path.unlink()

    def report(self, expected):
        return dict(frames=self.frames, converged_frames=self.converged,
                    max_newton_iterations=self.max_iterations, warnings=self.warnings,
                    convergence_verified=self.frames == self.converged == expected and not self.warnings)


def make_config(args):
    from hydra import compose, initialize_config_dir
    with initialize_config_dir(version_base='1.3', config_dir=str(ROOT/'configs')):
        overrides = (['env_configs@env=world_tabletop_aloha_v1',
                      'robot_control_configs@robot_control=aloha_position_ik']
                     if getattr(args, 'robot', 'panda') == 'aloha' else [])
        cfg = compose(config_name='knot_untying_preview', overrides=overrides)
    cfg.env.cameras = {}
    cfg.env.renderer.type = 'rasterizer'
    cfg.env.presentation.background = 'checker'
    cfg.env.sim.dt = args.dt
    if getattr(args, 'robot', 'panda') == 'aloha':
        with open_dict(cfg.task):
            # The default 500-face simplification leaves holes in both finger
            # hulls. Preserve the imported hulls for IPC's volume computation.
            cfg.task.robot_collision = dict(decimate=False)
            cfg.task.robot_rigid_collision = dict(enable_collision=True, enable_self_collision=True,
                                                  enable_neutral_collision=True, enable_adjacent_collision=False)
            if getattr(args, 'robot_coupling', None):
                cfg.task.robot_coupling = args.robot_coupling
    cfg.task.origin_xy_m[0] += args.x_offset
    cfg.task.origin_xy_m[1] += getattr(args, 'y_offset', 0.)
    with open_dict(cfg.task):
        cfg.task.yaw_deg = args.yaw
    if args.refined:
        cfg.task.geometry.segment_length_m = .00175
        cfg.task.geometry.radial_segments = 16
        cfg.task.rope.mesh.maxvolume = 1e-8
    if args.tighter:
        cfg.task.rope.fem.newton_max_iterations = 200
        cfg.task.rope.fem.newton_tolerance = .005
    if getattr(args, 'newton_tol', None) is not None:
        cfg.task.rope.fem.newton_tolerance = args.newton_tol
    if getattr(args, 'friction_eps', None) is not None:
        with open_dict(cfg.task.rope.fem):
            cfg.task.rope.fem.contact_eps_velocity = args.friction_eps
    return cfg


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seconds', type=float, default=10.)
    parser.add_argument('--extend-to', type=float, help='Continue this same rollout if only settling limits fail')
    parser.add_argument('--mode', choices=('free_settle', 'contact_slide', 'lift_release', 'feed_release',
                                          'robot_grasp', 'robot_contact', 'untie_fixture', 'robot_untying'), default='free_settle')
    parser.add_argument('--dt', type=float, default=.005)
    parser.add_argument('--seed', type=int, default=7)
    parser.add_argument('--x-offset', type=float, default=0.)
    parser.add_argument('--y-offset', type=float, default=0.)
    parser.add_argument('--yaw', type=float, default=0.)
    parser.add_argument('--untying-route', choices=('remote_left', 'remote_extended', 'remote_adaptive',
                                                  'remote_adaptive_spread', 'understrand'), default='remote_left')
    parser.add_argument('--spread-span', type=float, default=.78,
                        help='Final gripper span in metres for remote_adaptive_spread')
    parser.add_argument('--spread-duration', type=float, default=20.,
                        help='Smooth right-hand spreading duration in seconds')
    parser.add_argument('--refined', action='store_true')
    parser.add_argument('--tighter', action='store_true')
    parser.add_argument('--without-robot', action='store_true')
    parser.add_argument('--robot', choices=('panda', 'aloha'), default='panda')
    parser.add_argument('--robot-coupling', choices=('two_way_soft_constraint', 'external_articulation'))
    parser.add_argument('--pregrasp-start', action='store_true',
                        help='Declare open initial hover poses for the untying candidate before physics build')
    parser.add_argument('--audit-rigid', action='store_true', help='Include actual IPC rigid surfaces in independent FEM CCD')
    parser.add_argument('--friction-eps', type=float, help='Explicit IPC friction smoothing velocity (m/s)')
    parser.add_argument('--newton-tol', type=float, help='Explicit IPC Newton convergence tolerance')
    parser.add_argument('--record', action='store_true', help='Record synchronized actual robot interaction views')
    parser.add_argument('--fps', type=int, default=20)
    parser.add_argument('--resolution', type=int, nargs=2, default=(960, 540))
    args = parser.parse_args()
    if args.mode in ('robot_grasp', 'robot_untying', 'robot_contact'):
        args.robot, args.audit_rigid, args.without_robot = 'aloha', True, False
    if args.seconds <= 0 or args.dt <= 0:
        raise ValueError('Duration and time step must be positive')
    if (args.spread_span != .78 or args.spread_duration != 20.) and (
            args.mode != 'robot_untying' or args.untying_route != 'remote_adaptive_spread'):
        parser.error('Custom spread parameters require robot_untying with remote_adaptive_spread')
    if args.extend_to is not None and (args.mode != 'free_settle' or args.extend_to < args.seconds):
        raise ValueError('Extension must be longer than the free-settle experiment')
    output = args.output.resolve()
    if any((output/name).exists() for name in ('report.json', 'validation_spec.json', 'progress.json')):
        raise FileExistsError(f'Use a new output directory; completed or unfinished evidence exists in {output}')
    output.mkdir(parents=True, exist_ok=True)
    cfg = make_config(args)
    initial_robot_pose = None
    if args.pregrasp_start:
        if args.mode not in ('robot_untying', 'robot_contact') or args.robot_coupling != 'external_articulation':
            raise ValueError('Pregrasp start requires external articulation and robot_contact or robot_untying')
        from .untying import configure_untying_start
        from .robot_probe import configure_contact_start
        initial_robot_pose = (configure_untying_start(cfg) if args.mode == 'robot_untying' else configure_contact_start(cfg))
    camera_metadata = None
    if args.record:
        if args.robot != 'aloha' or args.without_robot:
            raise ValueError('Physical recording currently requires the ALOHA scene')
        from .recording import configure_cameras
        camera_metadata = configure_cameras(cfg, tuple(args.resolution))
        camera_metadata['initial_robot_pose'] = initial_robot_pose
    from .probe_actions import ProbeActions
    from .contact_probe import CrossedStrandActions, build_contact_scene
    from .robot_probe import RobotContactActions, RobotGraspActions
    from .untying import RobotUntyingActions, UntyingFixtureActions
    actions = (RobotUntyingActions(route=args.untying_route, yaw_deg=args.yaw,
                                  spread_span_m=args.spread_span, spread_duration_s=args.spread_duration)
               if args.mode == 'robot_untying' else
               RobotContactActions() if args.mode == 'robot_contact' else
               UntyingFixtureActions() if args.mode == 'untie_fixture' else
               RobotGraspActions() if args.mode == 'robot_grasp' else
               CrossedStrandActions() if args.mode == 'contact_slide' else
               ProbeActions(args.mode) if args.mode != 'free_settle' else None)
    include_robot = not args.without_robot and args.mode != 'contact_slide'
    OmegaConf.save(cfg, output/'config.yaml', resolve=True)
    source_snapshot = {str(path.relative_to(ROOT)): path.read_bytes()
                       for path in sorted(Path(__file__).parent.glob('*.py'))}
    spec = dict(experiment=args.mode, duration_s=args.seconds, limits=asdict(LIMITS),
                extend_to_s=args.extend_to,
                seed=args.seed, include_robot=include_robot,
                initial_robot_pose=initial_robot_pose,
                robot_coupling=str(cfg.task.get('robot_coupling', 'two_way_soft_constraint')) if include_robot else None,
                robot_axis_adapter='Genesis 1.2.1 / pyuipc 0.0.25 revolute edge correction'
                    if cfg.task.get('robot_coupling') == 'external_articulation' else None,
                audit_rigid=args.audit_rigid,
                dt=args.dt, substeps=int(cfg.env.sim.substeps),
                solver=OmegaConf.to_container(cfg.task.rope, resolve=True),
                geometry=OmegaConf.to_container(cfg.task.geometry, resolve=True),
                runtime_node_position_overwrites=False, runtime_velocity_resets=False,
                actuation=actions.specification() if actions else dict(kind='none'),
                versions={name: version(name) for name in ('genesis-world', 'pyuipc', 'ipctk', 'numpy')},
                source_sha256={path: hashlib.sha256(content).hexdigest() for path, content in source_snapshot.items()})
    for path, content in source_snapshot.items():
        destination = output/'implementation'/path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    (output/'validation_spec.json').write_text(json.dumps(spec, indent=2)+'\n')
    import genesis as gs
    from topogym.robot import initialize_robot_controller
    from .scene import KnotSceneBuilder
    gs.init(backend=gs.cuda, logging_level='warning', seed=args.seed)
    try:
        task = (build_contact_scene(cfg, output/'assets', actions) if args.mode == 'contact_slide' else
                KnotSceneBuilder(cfg.env, cfg.task, cfg.robot_control).build(
                    asset_dir=output/'assets', include_robot=include_robot,
                    pre_build=actions.declare if actions else None))
    except Exception as exc:
        (output/'report.json').write_text(json.dumps(dict(
            experiment=args.mode, passed=False, build_succeeded=False, error=f'{type(exc).__name__}: {exc}',
            simulated_seconds=0., complete_physics_suite_passed=False,
            robot_grasp_qualified=False), indent=2)+'\n')
        raise
    monitor = None
    recorder = None
    try:
        if include_robot:
            external = cfg.task.get('robot_coupling') == 'external_articulation'
            controller = initialize_robot_controller(scene=task.scene, manifest=task.manifest,
                                                    robot_cfg=cfg.robot_control, settle_steps=0, reset_home=not external)
            if external:
                for side, arm in controller.arms.items():
                    arm.set_arm_qpos(cfg.robot_control.home[side][:6])
                    arm.set_gripper(cfg.robot_control.home[side][6])
        monitor = FemDiagnostics(task, loaded=actions is not None, audit_rigid=args.audit_rigid)
        if hasattr(actions, 'configure'):
            actions.configure(task, controller, monitor)
        spec['native_ipc_config'] = task.scene.sim.coupler._ipc_scene.config().to_json()
        np.savez_compressed(output/'mesh.npz', initial_nodes=monitor.initial, rest_volumes=monitor.rest_volumes,
                            elements=monitor.elements, surface_faces=monitor.faces, material_rings=monitor.rings,
                            material_edges=monitor.material_edges, material_slices=monitor.material_slices)
        spec['mesh_sha256'] = hashlib.sha256((output/'mesh.npz').read_bytes()).hexdigest()
        (output/'validation_spec.json').write_text(json.dumps(spec, indent=2)+'\n')
        if args.record:
            from .recording import PhysicalRecorder
            recorder = PhysicalRecorder(task, output, fps=args.fps, dt=args.dt, metadata=camera_metadata)
    except Exception as exc:
        if monitor is not None:
            monitor.close()
        (output/'report.json').write_text(json.dumps(dict(
            experiment=args.mode, passed=False, build_succeeded=True, setup_succeeded=False,
            error=f'{type(exc).__name__}: {exc}', simulated_seconds=0.,
            complete_physics_suite_passed=False, robot_grasp_qualified=False,
            untying_verified=False), indent=2)+'\n')
        raise
    failure = None
    start = time.perf_counter()
    log = SolverLog(output)
    try:
        monitor.install()
        with log:
            max_steps = round((args.extend_to or args.seconds)/args.dt)
            for step in range(max_steps):
                if (output/'STOP').exists():
                    raise RuntimeError('Stopped by task coordinator; rollout is incomplete')
                if step == round(args.seconds/args.dt) and args.extend_to:
                    interim = monitor.report()
                    failed = [key for key, value in interim['checks'].items() if not value]
                    extend = bool(failed) and all(key.startswith('settled_') for key in failed)
                    (output/'extension_decision.json').write_text(json.dumps(
                        dict(continue_same_rollout=extend, at_time_s=step*args.dt,
                             initial_duration_report=interim), indent=2)+'\n')
                    if not extend:
                        break
                if actions:
                    actions.update(step*args.dt)
                task.scene.step()
                if hasattr(actions, 'observe'):
                    actions.observe((step+1)*args.dt, monitor)
                if recorder:
                    recorder.capture(step+1, (step+1)*args.dt, actions)
                log.update()
                if step % max(1, round(.25/args.dt)) == 0:
                    progress = dict(time_s=(step+1)*args.dt,
                        rms_speed=monitor.window[-1][2]['rms_speed_m_s'], min_J=monitor.min_J,
                        crossings=len(projected_crossings(monitor.last_centers)) if args.mode != 'contact_slide' else None,
                        wall_seconds=time.perf_counter()-start)
                    print(json.dumps(progress), file=log.progress, flush=True)
                    (output/'progress.json').write_text(json.dumps(progress)+'\n')
                if step % max(1, round(1./args.dt)) == 0:
                    # Read-only evidence checkpoint; this cannot restart or
                    # overwrite the physical state of a rollout.
                    (output/'partial_trace.json').write_text(json.dumps(monitor.samples)+'\n')
                    np.savez_compressed(output/'partial_trajectory.npz',
                        times=np.array([m['time_s'] for m in monitor.samples]),
                        centerlines=np.array(monitor.centers),
                        final_nodes=monitor.last_positions, final_velocity=monitor.last_velocity)
                    if hasattr(actions, 'samples'):
                        (output/'partial_contact_trace.json').write_text(json.dumps(actions.samples)+'\n')
                if hasattr(actions, 'finished') and actions.finished((step+1)*args.dt):
                    break
    except Exception as exc:
        failure = f'{type(exc).__name__}: {exc}'
    finally:
        if hasattr(actions, 'close_contact_monitors'):
            actions.close_contact_monitors()
        monitor.close()
    report = monitor.report()
    solver = log.report(monitor.count)
    centers = getattr(monitor, 'last_centers', task.centerline)
    crossings = projected_crossings(centers) if args.mode != 'contact_slide' else []
    report.update(scope='local_fem_physics_only', experiment=args.mode, error=failure,
        initial_robot_pose=initial_robot_pose,
        solver=solver, wall_seconds=time.perf_counter()-start,
        real_time_ratio=monitor.count*monitor.dt/max(1e-9, time.perf_counter()-start),
        final_crossings=crossings, task_preserved=len(crossings) == 3 and abs(sum(h['sign'] for h in crossings)) == 3,
        robot_grasp_qualified=False, complete_physics_suite_passed=False)
    report['actuation'] = actions.report() if actions else dict(kind='none', final_active_constraints=0)
    report['passed'] = bool(failure is None and report['mechanical_checks_passed']
                            and solver['convergence_verified']
                            and (report['task_preserved'] or args.mode != 'free_settle')
                            and report['actuation'].get('passed', True)
                            and report['actuation']['final_active_constraints'] == 0)
    report['robot_grasp_qualified'] = bool(args.mode == 'robot_grasp' and report['passed'])
    report['untying_verified'] = bool(args.mode == 'robot_untying' and report['passed'] and not crossings)
    (output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    if recorder:
        recorder.close(report)
    (output/'trace.json').write_text(json.dumps(monitor.samples, indent=2)+'\n')
    if hasattr(actions, 'samples'):
        (output/'contact_trace.json').write_text(json.dumps(actions.samples, indent=2)+'\n')
    np.savez_compressed(output/'trajectory.npz', times=np.array([m['time_s'] for m in monitor.samples]),
        centerlines=np.array(monitor.centers), initial_centerline=task.centerline,
        final_nodes=getattr(monitor, 'last_positions', monitor.initial),
        final_velocity=getattr(monitor, 'last_velocity', np.zeros_like(monitor.initial)))
    print(json.dumps(report, indent=2), flush=True)
    if failure:
        raise SystemExit(failure)
    if not report['passed']:
        raise SystemExit('Physical or actuation checks did not pass; see report.json')


if __name__ == '__main__':
    main()
