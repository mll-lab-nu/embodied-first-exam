"""Recorded GPU diagnostics for builder feedback, never a task-solvability claim."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
import traceback

import numpy as np

from topogym.utils.io import write_json_atomic, sha256_file, to_jsonable


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--tool', type=Path, required=True)
    parser.add_argument('--instance', type=Path)
    parser.add_argument('--task')
    parser.add_argument('--mode', choices=('hold', 'replay', 'seed', 'ik', 'lock', 'release', 'archive', 'arm_motion'), default='hold')
    parser.add_argument('--motion', choices=('hold', 'lift', 'axial'), default='hold')
    parser.add_argument('--motion-m', type=float, default=.01)
    parser.add_argument('--close-steps', type=int, default=160,
                        help='Maximum control steps to establish actual bilateral grasp contact')
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--seeded', action='store_true', help='Use the seeded scene draw for archive verification')
    parser.add_argument('--steps', type=int, default=40)
    parser.add_argument('--trajectory', type=Path)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--tier', choices=('easy', 'medium', 'hard'))
    parser.add_argument('--reference', type=Path, help='Preparation directory containing reference.npz and continuation.npz')
    args = parser.parse_args()
    implied_task = {'archive':'blanket_flatten', 'lock':'lock_picking', 'seed':'lock_picking',
                    'arm_motion':'interlocked_claws', 'ik':'interlocked_claws'}.get(args.mode)
    args.task = args.task or implied_task or 'interlocked_claws'
    if implied_task and args.task != implied_task:
        parser.error(f'--mode {args.mode} requires task {implied_task}')
    if args.mode == 'archive' and (args.tier is None or args.reference is None):
        parser.error('--mode archive requires --tier and --reference')
    if args.seeded and args.mode != 'archive':
        parser.error('--seeded is only supported for archive verification')
    if args.steps < 1 or args.close_steps < 1:
        parser.error('--steps and --close-steps must be positive')
    if not np.isfinite(args.motion_m) or args.motion_m <= 0:
        parser.error('--motion-m must be finite and positive')
    root = args.output.resolve(); root.mkdir(parents=True, exist_ok=False)
    import torch
    torch.set_num_threads(1)
    spec = importlib.util.spec_from_file_location('rcb_feedback_tool', args.tool)
    tool = importlib.util.module_from_spec(spec); sys.modules[spec.name] = tool; spec.loader.exec_module(tool)
    report = dict(status='running', mode=args.mode, task=args.task, source=__file__,
                  probe_sha256=sha256_file(__file__), tool_sha256=sha256_file(args.tool),
                  instance_sha256=sha256_file(args.instance) if args.instance else None,
                  solvability_proven=False, gpu=torch.cuda.get_device_name(),
                  config=vars(args), videos={}, physical=False)
    write_json_atomic(root/'report.json', report)
    session = media = None
    try:
        if args.mode == 'seed':
            from topogym.world.genesis_world import GenesisWorld
            from topogym.config.scene import load_scene_config
            from topogym.simulator.config import SimulatorConfig
            import genesis as gs
            import random
            config = SimulatorConfig(task_id='lock_picking', seed=args.seed, enable_rgb=False)
            scene = load_scene_config(config)
            assert not getattr(gs, '_initialized', False), 'seed probe must be a fresh process'
            world = GenesisWorld.from_tabletop(scene.env, scene.robot_control,
                compute_backend='cuda', precision=config.precision, seed=args.seed, cameras=False)
            # Construction can consume RNGs. Verify gs received the full seed by
            # separately reseeding with the same public call and comparing draws.
            gs.set_random_seed(args.seed)
            draws = dict(python=random.random(), numpy=float(np.random.random()), torch=float(torch.rand(())))
            gs.set_random_seed(args.seed)
            assert draws == dict(python=random.random(), numpy=float(np.random.random()), torch=float(torch.rand(())))
            report.update(status='passed', scene_seed=args.seed, engine_seed=args.seed & 0x7fffffff,
                          fresh_process=True, rng_draws=draws, scope='actual CUDA engine initialization; no scene step or RGB')
            world.close()
            return
        if args.mode == 'archive':
            parameters = (dict(initial_state_path=str(args.manifest), initial_state_sha256=sha256_file(args.manifest))
                          if args.manifest else {})
            session = tool.Session('blanket_flatten', variation_id='seeded' if args.seeded else 'blanket_flatten_'+args.tier,
                                   seed=args.seed, task_parameters=parameters)
        elif args.instance is None:
            parser.error('--instance is required for physical probes')
        else:
            session = tool.Session(args.task, instance=args.instance)
        def same_targets(a, b):
            return all(a[name][g.gripper_field] == b[name][g.gripper_field]
                       and np.allclose(a[name]['joint_position_rad'], b[name]['joint_position_rad'], atol=1e-6, rtol=0)
                       for name, g in session.robot.groups.items())
        from topogym.recording.segment import SegmentMedia
        media = SegmentMedia(root, 0, session.env.sensor_frame())
        report.update(physical=True, simulator_config=session.config, instance_matches=session.instance_matches,
                      objects_at_birth=session.objects())
        accepted = session.env._robot.capture_state().targets
        # Validate actual model limits without physically driving to extremes.
        for boundary in (session.robot.lo, session.robot.hi):
            session.robot.command(np.asarray(boundary, dtype=np.float32))
        report['float32_boundary_commands_valid'] = True
        if not same_targets(accepted, session.env._robot.capture_state().targets):
            raise ValueError('Command validation changed the accepted robot targets')
        ticks = []
        continuation_errors = []
        if args.mode == 'archive':
            from topogym.utils.arrays import to_numpy
            cloth = session.env._world.entities['blanket']
            reference = np.load(args.reference/'reference.npz')
            continuation = np.load(args.reference/'continuation.npz')
            positions = to_numpy(cloth.get_particles_pos()).reshape(-1,3)
            velocities = to_numpy(cloth.get_particles_vel()).reshape(-1,3)
            report.update(initial_state_restore=to_jsonable(session.env._initial_state_report),
                          archive_anchor_position_exact=np.array_equal(positions,reference['positions']),
                          archive_anchor_velocity_exact=np.array_equal(velocities,reference['velocities']))
        def capture(record):
            record = to_jsonable(record)
            ticks.append(record)
            if args.mode == 'archive' and len(ticks)<=5:
                i=len(ticks)-1
                continuation_errors.append(dict(tick=i+1,
                    position_max_abs_m=float(np.max(np.abs(to_numpy(cloth.get_particles_pos()).reshape(-1,3)-continuation['positions'][i]))),
                    velocity_max_abs_m_s=float(np.max(np.abs(to_numpy(cloth.get_particles_vel()).reshape(-1,3)-continuation['velocities'][i])))))
        remove = session.env.add_state_sink(capture)
        if args.mode == 'lock':
            from scipy.spatial.transform import Rotation
            remove_frames = session.env.add_frame_sink(media.append)
            p = session.primitives()
            session.record_start()
            phases = []
            def mark(name):
                from topogym.robot.grasp_geometry import read_grasp_geometry
                geometry = read_grasp_geometry(session.env._robot, 'arm')
                phases.append(dict(name=name, physics_step=session.env._world.physics_step,
                                   key=session.objects()['lock_key'], status=session.status(),
                                   robot=to_jsonable(session.env.tick_record()['robot']),
                                   finger_bounds=[dict(min_m=v.min(axis=0), max_m=v.max(axis=0))
                                                  for v, _ in geometry['surfaces']]))
                report['phases'] = phases
                write_json_atomic(root/'report.json', report)
            report['link_names'] = {str(link.idx): f'{name}/{link.name}'
                for name, entity in session.env._world.entities.items() if hasattr(entity, 'links')
                for link in entity.links}
            mark('home_on_open_supports')
            key_pos, key_quat = session.object_pose('lock_key')
            key_rot = Rotation.from_quat(np.roll(key_quat, -1))
            center = np.asarray(key_pos)+key_rot.apply([-.495, 0., 0.])
            orientation = p['top_down_quat'](np.pi/2)
            p['open_gripper']('arm', steps=5)
            p['move_ee']('arm', center+[0., 0., .20], orientation, steps=120)
            mark('above_handle')
            p['move_ee']('arm', center+[0., 0., .002], orientation, linear=10)
            mark('at_handle')
            for _ in range(args.close_steps):
                p['close_gripper']('arm', steps=1)
                grasp = to_jsonable(session.env.tick_record()['world']['grasp'])
                if grasp['hands']['arm']['phase'] in ('holding','lost') or session.episode_end:
                    break
            report['acquired_before_probe'] = grasp['hands']['arm']['phase']=='holding'
            mark('closed')
            if report['acquired_before_probe']:
                before_p, before_q = session.object_pose('lock_key')
                tcp_p, tcp_q = session.ee_pose('arm')
                direction = (np.array([0., 0., 1.]) if args.motion=='lift' else
                             -Rotation.from_quat(np.roll(before_q, -1)).apply([1., 0., 0.]))
                if args.motion=='hold':
                    p['hold'](steps=40)
                    displacement = np.zeros(3)
                else:
                    displacement = direction*args.motion_m
                    p['move_ee']('arm', np.asarray(tcp_p)+displacement, tcp_q, steps=80, linear=1)
                mark('after_'+args.motion)
                after_p, after_q = session.object_pose('lock_key')
                report.update(requested_displacement_m=displacement,
                    key_displacement_m=np.asarray(after_p)-before_p,
                    key_follow_error_m=float(np.linalg.norm(np.asarray(after_p)-before_p-displacement)),
                    key_world_rotation_rad=float((Rotation.from_quat(np.roll(before_q,-1)).inv()*
                                                  Rotation.from_quat(np.roll(after_q,-1))).magnitude()))
            remove(); remove_frames()
            trajectory=session.record_stop();session.save_trajectory(trajectory,root/'trajectory.npz')
            (root/'ticks.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in ticks))
            report.update(phases=phases, final_grasp=to_jsonable(session.env.tick_record()['world']['grasp']),
                          status_after_probe=session.status(), committed_physics_ticks=len(ticks),
                          scope='frozen-instance support pickup and small motion; no insertion or solve claim')
            report['media']=media.finish();media=None
            report['status']='diagnostic_complete' if report['acquired_before_probe'] else 'pickup_failed'
            return
        actions = np.load(args.trajectory)['actions'] if args.mode == 'replay' else None
        session.record_start()
        holds = []
        for index in range(len(actions) if actions is not None else args.steps):
            before = session.env._robot.capture_state().targets
            action = actions[index] if actions is not None else session.hold_action()
            session.step(action)
            after = session.env._robot.capture_state().targets
            holds.append(dict(step=index+1, targets_unchanged=same_targets(before, after),
                              grasp=to_jsonable(session.env.tick_record()['world'].get('grasp'))))
            media.append(session.env.sensor_frame())
            if session.episode_end:
                break
        hold_status = session.status()
        if args.mode == 'arm_motion':
            # A small coordinated Cartesian endpoint, reached by interpolating
            # both arms' joint targets together. This is a local grip check.
            current = session.hold_action()
            goal = current.copy()
            birth_objects = {name: session.object_pose(name)[0] for name in ('claw_0', 'claw_1')}
            errors = {}
            for arm in session.robot.arms:
                pos, quat = session.ee_pose(arm)
                q, ep, er = session.ik(arm, np.asarray(pos)+[0., 0., .03], quat)
                errors[arm] = dict(position_m=ep, angle_rad=er)
                if ep > .003 or er > .03:
                    raise ValueError(f'Coordinated 3 cm lift endpoint IK failed: {errors}')
                goal[session.robot.arm_slice[arm]] = q
            motion_holds = []
            for i in range(1, 81):
                session.step(current+(goal-current)*min(i/60., 1.))
                media.append(session.env.sensor_frame())
                hands = session.env.tick_record()['world']['grasp']['hands']
                motion_holds.append(all(h['phase']=='holding' and h['intent']=='close' for h in hands.values()))
                if session.episode_end:
                    break
            report.update(motion_ik=errors, motion_grasp_retained=all(motion_holds),
                          motion_control_steps=len(motion_holds), status_after_motion=session.status(),
                          motion_follow_error_m={name:float(np.linalg.norm(np.asarray(session.object_pose(name)[0])-
                              before-[0.,0.,.03])) for name,before in birth_objects.items()})
        if args.mode == 'release':
            opened = session.hold_action()
            for name in session.robot.arms:
                opened[session.robot.grip_index[name]] = session.robot.limits[session.robot.grip_index[name]][1]
            session.step(opened)
            media.append(session.env.sensor_frame())
            grasp = to_jsonable(session.env.tick_record()['world']['grasp'])
            report.update(opening_releases=all(h['intent']=='open' and h['binding'] is None for h in grasp['hands'].values()),
                          grasp_after_release=grasp, status_after_release=session.status())
        remove()
        trajectory = session.record_stop()
        session.save_trajectory(trajectory, root/'trajectory.npz')
        (root/'ticks.jsonl').write_text(''.join(json.dumps(row, ensure_ascii=False)+'\n' for row in ticks))
        report.update(holds=holds, status_after_hold=hold_status, committed_physics_ticks=len(ticks),
                      targets_unchanged=all(row['targets_unchanged'] for row in holds))
        report['media'] = media.finish(); media = None
        if args.task == 'interlocked_claws':
            report['grasp_retained'] = all(row['grasp'] and all(h['intent']=='close' and h['phase']=='holding'
                                          for h in row['grasp']['hands'].values()) for row in holds)
        else:
            report['grasp_retained'] = None
        if args.mode == 'ik':
            from scipy.spatial.transform import Rotation
            seed = session.robot.arm_q()
            birth = {name: session.robot.tcp(name) for name in session.robot.arms}
            pivot = np.mean([session.object_pose(name)[0] for name in ('claw_0', 'claw_1')], axis=0)
            searches = []
            for down in (.15, .25, .38):
                for dx in (0., -.10, .10):
                    for pitch in (0., -20., 20.):
                        targets = {}
                        rotation = Rotation.from_euler('y', pitch, degrees=True)
                        for name, (pos, quat) in birth.items():
                            rotated = rotation*Rotation.from_quat(np.roll(quat, -1))
                            position = pivot+rotation.apply(np.asarray(pos)-pivot)+[dx, 0., -down]
                            targets[session.robot.tcp_frames[name]] = np.r_[position, np.roll(rotated.as_quat(), 1)]
                        _, errors = session.robot.ik(targets, seed, .003, .03, 60)
                        searches.append(dict(down_m=down, dx_m=dx, pitch_deg=pitch, errors=errors,
                                             ik_passed=all(p<.003 and r<.03 for p,r in errors.values())))
            report.update(ik_search=searches, ik_pivot_m=pivot,
                          ik_scope='one common rigid transform of both TCPs about the assembly pivot; endpoint feasibility only, no swept collision or object-placement proof')
        # Reset is measured after retaining the original continuous video.
        session.reset()
        restored = session.env._robot.capture_state().targets
        session.step(session.hold_action())
        report['reset_hold_unchanged'] = same_targets(restored, session.env._robot.capture_state().targets)
        if args.mode == 'archive':
            report['continuation_errors']=continuation_errors
            report['archive_passed']=(report['archive_anchor_position_exact'] and report['archive_anchor_velocity_exact']
                and len(continuation_errors)==5 and all(r['position_max_abs_m']<=1e-6 and r['velocity_max_abs_m_s']<=1e-4 for r in continuation_errors))
        report['status'] = 'passed' if (report['targets_unchanged'] and report['reset_hold_unchanged']
                          and report['instance_matches']
                          and report['status_after_hold']['episode_end'] is None
                          and report['grasp_retained'] is not False and report.get('opening_releases',True)
                          and report.get('motion_grasp_retained',True)
                          and report.get('status_after_motion',{}).get('episode_end') is None
                          and report.get('archive_passed',True)) else 'failed'
    except Exception:
        report.update(status='error', traceback=traceback.format_exc())
        if session is not None:
            report['status_at_error'] = session.status()
            report['grasp_at_error'] = to_jsonable(session.env.tick_record()['world'].get('grasp'))
            if 'ticks' in locals():
                (root/'ticks.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in ticks))
            if session._recording is not None:
                session.save_trajectory(session.record_stop(), root/'partial_trajectory.npz')
        raise
    finally:
        if media is not None:
            # Retain the real prefix of a failed diagnostic, with its failure
            # status. A complete media file never implies a completed motion.
            try:
                report['partial_media'] = media.finish()
            except Exception as media_error:
                report['media_error'] = str(media_error)
                media.abort()
        write_json_atomic(root/'report.json', report)
        if session is not None:
            session.close()
    if report['status'] != 'passed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
