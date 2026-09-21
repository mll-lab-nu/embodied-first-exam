"""Collision-checked Cartesian paths and exact-state Orbits continuation.

Checks finite path samples; native contact monitoring remains necessary.
Neither a valid path nor checkpoint continuation certifies puzzle completion.
"""
import json
from pathlib import Path

import mujoco
import numpy as np
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation, Slerp

from .dynamics import natural_working_state
from .geometry import OrbitsLayout
from .robot_runtime import RobotRuntime


def continue_run(source, folder):
    source = Path(source)
    cfg = OmegaConf.load(source/'config.yaml')
    scope = json.loads((source/'scope.json').read_text())
    if scope.get('cord_layout') != 'natural_loop':
        raise ValueError('Continuation currently supports the natural-loop model only')
    layout = OrbitsLayout(**OmegaConf.to_container(cfg.task.geometry)).scaled(float(cfg.task.scale))
    points, handle = natural_working_state(layout,
                                          handle_x_m=scope['handle_initial_position_m'][0])
    r = RobotRuntime(cfg, folder, initial_points=points, handle_position=handle)
    r.restore_checkpoint(source/'checkpoint.npz')
    resume_event = r.events[-1]
    with np.load(source/'trajectory.npz') as a:
        if abs(float(a['time_s'][-1])-r.data.time) > 1e-10:
            raise ValueError('Prefix trajectory does not end at the continuation checkpoint')
        np.testing.assert_allclose(a['qpos'][-1], r.data.qpos, atol=1e-12, rtol=0)
        r.frames = [(float(t), str(p), q.copy(), x.copy(), c.copy())
                    for t, p, q, x, c in zip(a['time_s'], a['phase'], a['qpos'],
                                            a['points'], a['ctrl'])]
    report = json.loads((source/'report.json').read_text())
    r.metrics = report['metrics']
    # Old checkpoint paths belong to the immutable source directory.
    for metric in r.metrics:
        if 'checkpoint' in metric:
            metric['checkpoint_source'] = str(source/metric.pop('checkpoint'))
    r.events = report['events']+[resume_event]
    scope.update(full_task_success=False, exact_state_continuation_of=str(source))
    (r.folder/'scope.json').write_text(json.dumps(scope, indent=2)+'\n')
    return r


def cartesian_path(runtime, side, point, rotation=None, *, opening=None,
                   position_step_m=.004, rotation_step_rad=.04):
    """Solve the whole sampled segment before issuing any actuator command."""
    if side not in ('left', 'right'):
        raise ValueError(f'Unknown arm {side}')
    r = runtime
    mujoco.mj_kinematics(r.model, r.data)
    start = r.data.site_xpos[r.model.site(side+'_tcp').id].copy()
    body = r.model.body(side+'/gripper_link').id
    start_rotation = r.checker.yaw*Rotation.from_matrix(r.data.xmat[body].reshape(3, 3))
    rotation = start_rotation if rotation is None else rotation
    point = np.asarray(point, dtype=float)
    angle = (rotation*start_rotation.inv()).magnitude()
    count = max(2, int(np.ceil(np.linalg.norm(point-start)/position_step_m)),
                int(np.ceil(angle/rotation_step_rad)))
    slerp = Slerp([0, 1], Rotation.from_quat([start_rotation.as_quat(), rotation.as_quat()]))
    q = r.data.qpos[:16].copy()
    q[[6, 7]] = r.data.ctrl[6]
    q[[14, 15]] = r.data.ctrl[13]
    if opening is not None:
        q[[6, 7] if side == 'left' else [14, 15]] = opening
    result, diagnostics = [], []
    for fraction in np.linspace(0, 1, count+1)[1:]:
        local = start+fraction*(point-start)
        world = r.checker.yaw.apply(local)+r.checker.origin
        candidate, pe, re = r.checker.solve(side, world, slerp(fraction), q)
        if pe > .0005 or re > .005:
            raise ValueError(f'{side} continuous IK at {fraction:.3f}: {pe:.6f} m, {re:.6f} rad')
        if np.max(np.abs(candidate[r.checker.indices[side]]-q[r.checker.indices[side]])) > .2:
            raise ValueError('Discontinuous inverse-kinematics branch')
        bad = r.checker.violations(candidate)
        if bad:
            raise ValueError(f'{side} path collision at {fraction:.3f}: {bad}')
        result.append(candidate.copy())
        diagnostics.append(dict(fraction=float(fraction), position_error_m=pe,
                                rotation_error_rad=re))
        q = candidate
    return np.asarray(result), diagnostics


def move(runtime, phase, side, point, rotation=None, *, seconds=3., opening=None):
    path, errors = cartesian_path(runtime, side, point, rotation, opening=opening)
    folder = runtime.folder/'planned_paths'; folder.mkdir(exist_ok=True)
    np.savez_compressed(folder/f'{phase}.npz', qpos=path)
    (folder/f'{phase}.json').write_text(json.dumps(dict(side=side, target_task_m=list(point),
        seconds=seconds, checked_samples=errors, position_sample_spacing_m=.004,
        rotation_sample_spacing_rad=.04, continuous_collision_proof=False), indent=2)+'\n')
    runtime.joint_path(phase, path, seconds, max_penetration_m=.0015)


def acquire_strand(r, node=100):
    """Acquire the selected material region after the right arm has released."""
    if not 0 <= node < len(r.nodes):
        raise ValueError(f'Cord node out of range: {node}')
    point = r.points()[node]
    move(r, 'right_fold_approach', 'right', point+[0, -.05, 0], seconds=3.)
    point = r.points()[node]
    move(r, 'right_fold_contact', 'right', point, seconds=2.)
    q = r.data.qpos[:16].copy(); q[[14, 15]] = .009
    r.joint_move('right_fold_close', q, .75)
    candidates = [i for i in range(max(0, node-3), min(len(r.nodes), node+4))
                  if len(r.grasp_contacts('right', 'cord', node=i)) == 2]
    if not candidates:
        raise ValueError('Regrasp did not establish bilateral contact on the intended strand')
    selected = min(candidates, key=lambda i: abs(i-node))
    r.engage_grasp('right', node=selected)
    r.joint_move('hold_new_fold_grasp', r.data.qpos[:16], 1.)
    return selected


def handover_probe(source, folder):
    """Release one leg and acquire an interior strand, retaining the other arm."""
    r = continue_run(source, folder)
    try:
        r.release_grasp('right')
        q = r.data.qpos[:16].copy(); q[[14, 15]] = .018
        r.joint_move('release_right_leg', q, .75)
        point = r.data.site_xpos[r.model.site('right_tcp').id].copy()+[0, -.07, 0]
        move(r, 'right_retract_before_regrasp', 'right', point, seconds=2.)
        r.joint_move('strand_settle', r.data.qpos[:16], 1.)
        acquire_strand(r)
    finally:
        r.save()
    return r


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('folder', type=Path)
    args = parser.parse_args()
    handover_probe(args.source, args.folder)
