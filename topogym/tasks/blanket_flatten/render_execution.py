"""Render exact recorded particle and full robot states from one physical run."""
import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import re

import numpy as np
from omegaconf import OmegaConf

CAMERAS = ('agentview', 'front_oblique', 'wrist')
INITIAL_CAMERAS = ('overview', 'detail', 'topdown')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--preview', action='store_true')
    parser.add_argument('--initialization', action='store_true',
                        help='Render gravity initialization and passive stability, without claiming robot completion')
    parser.add_argument('--external', action='store_true', help='Render an explicitly labelled no-robot external manipulation')
    parser.add_argument('--camera-overrides', type=Path, help='Camera mapping only; preserves the physical source configuration')
    parser.add_argument('--allow-failed', action='store_true', help='Render a clearly labelled diagnostic attempt')
    parser.add_argument('--output', type=Path, help='Separate output directory for render verification')
    parser.add_argument('--frame-indices', type=int, nargs='+', help='Selected frames; requires --preview')
    parser.add_argument('--shared-raster-updates', action='store_true', help='Upload robot/cloth state once per frame')
    parser.add_argument('--include-preparation', action='store_true', help='Include the procedural initial-state construction in a robot video')
    parser.add_argument('--fps', type=int, help='Video frame rate; must divide the recorded frame rate')
    args = parser.parse_args()
    if args.external and args.initialization:
        parser.error('--external and --initialization are distinct recording scopes')
    if args.frame_indices and not args.preview:
        parser.error('--frame-indices requires --preview')
    source = args.source.resolve()
    report = json.loads((source/'report.json').read_text())
    review = json.loads((source/'review.json').read_text()) if (source/'review.json').exists() else {}
    approved = bool(report['full_robot_task_verified'] and report.get('initial_robot_clearance_checks', 0) > 0
                    and report.get('minimum_initial_robot_clearance_m', 0) >= .008
                    and review.get('approved_for_archive', True))
    initial_approved = bool(report.get('mode') == 'stability' and report.get('success')
        and report.get('initialization_accepted') and report.get('binding', {}).get('passed')
        and report.get('final_evidence', {}).get('passive_seconds', 0) >= 10
        and report.get('initial_robot_clearance_checks', 0) > 0
        and report.get('minimum_initial_robot_clearance_m', 0) >= .008)
    if args.external and report.get('mode') != 'external':
        raise ValueError('External rendering requires a no-robot external source run')
    external_review = json.loads((source/'external_review.json').read_text()) if (source/'external_review.json').exists() else {}
    external_approved = bool(args.external and report.get('success') and external_review.get('external_manipulation_verified'))
    source_approved = external_approved if args.external else (initial_approved if args.initialization else approved)
    if not source_approved and not args.allow_failed:
        scope = 'accepted initialization with 10 s passive stability' if args.initialization else 'completed robot task'
        raise ValueError(f'Cannot render this attempt as {scope}')
    cameras = INITIAL_CAMERAS if args.initialization or args.external else CAMERAS
    cfg = OmegaConf.load(source/'config.yaml')
    source_fps = int(cfg.run.fps)
    video_fps = source_fps if args.fps is None else args.fps
    if video_fps <= 0 or source_fps % video_fps:
        raise ValueError('Video fps must be a positive divisor of the source fps')
    stride = source_fps//video_fps
    if args.camera_overrides:
        overrides = OmegaConf.load(args.camera_overrides)
        if set(overrides) == {'cameras'}:
            overrides = overrides.cameras
        if not set(overrides).issubset(cameras):
            raise ValueError('Camera overrides may only name the three recording cameras')
        cfg.env.cameras = OmegaConf.merge(cfg.env.cameras, overrides)
    cfg.env.cameras = OmegaConf.create({name: OmegaConf.to_container(cfg.env.cameras[name], resolve=True) for name in cameras})
    # NpzFile does not cache decompressed arrays. Re-reading positions in the
    # frame loop would decompress the entire recording several times per frame.
    with np.load(source/'physical_trace.npz') as archive:
        trace = {name: archive[name] for name in archive.files}
    output = args.output.resolve() if args.output else source/('preview' if args.preview else 'render')
    if (output/'render_report.json').exists():
        raise FileExistsError(f'Preserving existing render: {output}')
    output.mkdir(parents=True, exist_ok=True)
    render_source = Path(__file__).read_bytes()
    (output/'render_execution_source.py').write_bytes(render_source)
    OmegaConf.save(cfg, output/'render_config.yaml', resolve=True)
    import genesis as gs
    import imageio.v2 as imageio
    from PIL import Image
    from topogym.supervision.pbd_probe import probe_particles
    from .scene import BlanketSceneBuilder
    gs.init(backend=gs.cuda, precision=str(cfg.env.genesis.precision), seed=int(cfg.task.geometry.seed), logging_level='warning')
    task = BlanketSceneBuilder(cfg.env, cfg.task, cfg.robot_control).build(asset_dir=output/'assets', include_robot=not args.external)
    robot = None if args.external else task.tabletop.manifest.get('robot')
    arm_geoms = [] if robot is None else [geom for geom in robot.geoms if re.search(r'(?:^|_)link[0-7]$', geom.link.name) and len(geom.mesh.faces)]
    arm_samples = []
    if not np.array_equal(trace['faces'], task.faces) or not np.allclose(trace['material_uv'], task.material_uv, atol=1e-7):
        raise ValueError('Rebuilt cloth topology differs from physical recording')
    if not np.array_equal(trace['supports'], task.supports) or not np.allclose(trace['weights'], task.weights, atol=1e-6):
        raise ValueError('Rebuilt visual binding differs from physical recording')
    phases = trace['phases']
    keyframes = sorted(set([0, len(phases)-1, *np.flatnonzero(phases[1:] != phases[:-1])+1]))
    if args.initialization:
        keyframes = sorted(set(keyframes+[min(len(phases)-1, round(t*int(cfg.run.fps))) for t in (.2, .5, 1.)]))
    if report.get('preparation'):
        keyframes = sorted(set(keyframes+[min(len(phases)-1, int(np.searchsorted(trace['steps'], e['step'])))
                                          for e in report['events']]))
    if args.frame_indices:
        if min(args.frame_indices) < 0 or max(args.frame_indices) >= len(phases):
            raise ValueError('Requested frame index outside the trace')
        keyframes = sorted(set(args.frame_indices))
    start_frame = 0
    actions = [e for e in report['events'] if e['phase'].startswith('pull_')]
    if (report.get('preparation') or report.get('initial_state_restoration')) and actions and not args.initialization and not args.preview and not args.include_preparation:
        # A complete robot demonstration starts at the settled selected state.
        # Keep one second before the first action; the full source trace retains
        # all procedural construction and the independent passive recheck.
        start_step = max(0, actions[0]['step']-round(1/float(trace['dt'])))
        start_frame = int(np.searchsorted(trace['steps'], start_step))
        keyframes = sorted(set([start_frame]+[i for i in keyframes if i >= start_frame]))
    selected = keyframes if args.preview else sorted(set([*range(start_frame, len(phases), stride), len(phases)-1]))
    if not args.preview:
        keyframes = sorted(set(selected[min(len(selected)-1, int(np.searchsorted(selected, i)))] for i in keyframes))
    max_particle_error, max_joint_error = 0., 0.
    with ExitStack() as stack:
        writers = {} if args.preview else {name: stack.enter_context(imageio.get_writer(output/f'{name}.mp4',
            fps=video_fps, codec='libx264', quality=8, macro_block_size=1,
            ffmpeg_log_level='error', ffmpeg_params=['-movflags', '+faststart'])) for name in cameras}
        for frame_number, index in enumerate(selected):
            task.cloth.set_particles_pos(trace['positions'][index])
            if robot is not None:
                robot.set_qpos(trace['robot_qpos'][index], zero_velocity=True)
            max_particle_error = max(max_particle_error, float(np.max(np.abs(probe_particles(task.cloth)-trace['positions'][index]))))
            if robot is not None:
                max_joint_error = max(max_joint_error, float(np.max(np.abs(robot.get_qpos().cpu().numpy()-trace['robot_qpos'][index]))))
            if args.external:
                task.scene.clear_debug_objects()
                for center, color in zip(trace['hand_centers'][index], [(1., .25, .1, 1.), (.15, 1., .3, 1.)]):
                    if np.isfinite(center).all():
                        task.scene.draw_debug_sphere(center, radius=.009, color=color)
                        task.scene.draw_debug_arrow(center+[0, 0, .10], vec=[0, 0, -.08], radius=.003, color=color)
            if robot is not None and not args.initialization:
                task.scene.visualizer.update_visual_states(force_render=True)
            if 'wrist' in task.tabletop.cameras:
                task.tabletop.cameras['wrist'].move_to_attach()
            for camera_index, (name, camera) in enumerate(task.tabletop.cameras.items()):
                # The initialization cameras share one rasterizer context.
                # Its first render uploads the recorded state for this frame;
                # the next cameras only change the viewpoint. Re-uploading the
                # entire scene for every camera is unnecessary. Keep the prior
                # path for attached robot cameras and other renderer backends.
                shared_raster = (args.initialization or args.external) and str(cfg.env.renderer.type) == 'rasterizer'
                shared_robot = args.shared_raster_updates and not args.initialization and str(cfg.env.renderer.type) == 'rasterizer'
                # The rasterizer owns a scene cache separate from visual states.
                # Refresh that cache on the first camera even if FK was updated.
                force = camera_index == 0 if shared_robot else (not shared_raster or camera_index == 0)
                rgb = camera.render(force_render=force)[0]
                if name in writers:
                    writers[name].append_data(rgb)
                if index in keyframes:
                    Image.fromarray(rgb).save(output/f'{index:05d}_{phases[index]}_{name}.jpg', quality=92)
            if robot is not None and not args.initialization and not args.preview and (frame_number % video_fps == 0 or index in keyframes):
                from .robot_clearance import surface_clearance
                if not arm_geoms:
                    raise ValueError('No arm collision geometry found for motion review')
                meshes = [(str(geom.idx), geom.get_verts().detach().cpu().numpy(), np.asarray(geom.mesh.faces)) for geom in arm_geoms]
                clearance = surface_clearance(trace['positions'][index], task.faces, meshes)
                arm_samples.append(dict(source_frame=int(index), source_seconds=float(trace['steps'][index]*trace['dt']),
                                        phase=str(phases[index]), minimum_distance_m=clearance))
            if frame_number % 100 == 0 or args.preview:
                print(f'render {frame_number}/{len(selected)} source_frame={index} phase={phases[index]}', flush=True)
    if max_particle_error > 1e-6 or max_joint_error > 1e-6:
        raise ValueError('Rendered pose differs from measured physical state')
    result = dict(source=str(source), source_success=source_approved,
        scope='external_manipulation' if args.external else ('gravity_initialization_and_passive_stability' if args.initialization else 'robot_task'),
        full_robot_task_verified=approved, initialization_verified=initial_approved,
        external_manipulation_verified=external_approved,
        grip_markers_enabled=bool(args.external and all(camera.debug for camera in task.tabletop.cameras.values())),
        classification='exact_physical_state_replay', render_simulation_steps=0,
        render_source_sha256=hashlib.sha256(render_source).hexdigest(),
        source_physics_steps=report['physics_steps'], preview_only=args.preview,
        shared_robot_raster_updates=bool(args.shared_raster_updates),
        frames=len(selected), source_frames=len(phases), fps=video_fps, source_fps=source_fps,
        source_frame_indices=list(selected),
        source_start_frame=start_frame, recording_start_s=float(trace['steps'][start_frame]*trace['dt']),
        recording_end_s=float(trace['steps'][-1]*trace['dt']),
        cameras=list(cameras), maximum_particle_reconstruction_error_m=max_particle_error,
        maximum_joint_reconstruction_error=max_joint_error,
        render_config_sha256=hashlib.sha256((output/'render_config.yaml').read_bytes()).hexdigest(),
        source_sha256={name:hashlib.sha256((source/name).read_bytes()).hexdigest()
                       for name in ('report.json', 'config.yaml', 'physical_trace.npz')})
    if report.get('preparation'):
        result['controlled_preparation_included'] = start_frame == 0
        result['unassisted_gravity_start_s'] = report['preparation'].get('release_seconds')
    if arm_samples:
        arm_review = dict(scope='Arm links 0 through 7, at one-second intervals and recorded phase transitions; excludes the gripper and is not continuous collision certification',
                          links=sorted({geom.link.name for geom in arm_geoms}), samples=arm_samples,
                          minimum_clearance_m=min(row['minimum_distance_m'] for row in arm_samples))
        arm_review['passed'] = arm_review['minimum_clearance_m'] > 0
        (output/'robot_motion_review.json').write_text(json.dumps(arm_review, indent=2)+'\n')
        result['arm_clearance_review_passed'] = arm_review['passed']
    (output/'render_report.json').write_text(json.dumps(result, indent=2)+'\n')
    status = 'accepted external manipulation, not a robot execution' if external_approved else ('accepted robot execution' if approved else ('accepted initialization' if initial_approved else 'failed diagnostic attempt'))
    initialization = ('This is a fresh physical run from the selected landed shape with zero initial velocity; '
                      'it is not a dynamics continuation of the original recording.' if report.get('initial_state_restoration') else
                      'Initial procedural preparation, when present, uses bounded velocity control before release.')
    links = ([f'- [{name}.mp4]({name}.mp4)' for name in cameras] if not args.preview else
             [f'- [{index:05d} {name}]({index:05d}_{phases[index]}_{name}.jpg)' for index in keyframes for name in cameras])
    marker_description = ('Orange and green markers show the two recorded virtual grip centers.\n'
                          if result['grip_markers_enabled'] else 'Grip markers are not enabled in these cameras.\n')
    grasp_description = ('No robot. '+marker_description+
                         'Velocity-driven fixed material patches use material-coordinate selection; not frictional finger contact.\n'
                         if args.external else 'Robot grasps use local attachment after bilateral pad proximity checks.\n')
    (output/'README.md').write_text(f'Blanket flatten: {status}.\n\n'+
        'Exact replay of recorded states; no new physics steps during rendering.\n'+
        grasp_description+initialization+'\n\n'+
        '\n'.join(links)+'\n\n[Render evidence](render_report.json)\n')
    print(output, flush=True)


if __name__ == '__main__':
    main()
