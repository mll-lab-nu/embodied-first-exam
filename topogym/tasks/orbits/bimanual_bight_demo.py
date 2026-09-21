"""Local, contact-gated two-arm bight spreading experiment.

Both arms hold different material points. The handle is free. This is a
pregrasp development experiment, not a complete Orbits solution.
"""
import json
import hashlib
from pathlib import Path

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation

from .dynamics import Probe, natural_working_state
from .geometry import OrbitsLayout
from .robot_runtime import RobotRuntime
from .verification import threading_signature


def run(cfg, folder, *, cord_layout='natural_loop', handle_x_m=.60, prepared_state=None):
    folder = Path(folder)
    prepared = folder.parent/(folder.name+'_preparation')
    if prepared.exists() or folder.exists():
        raise FileExistsError('Use a new directory for each bight experiment')
    if cord_layout not in ('natural_loop', 'legacy_folded'):
        raise ValueError(f'Unknown working-cord layout: {cord_layout}')
    model_options = {}
    if cord_layout == 'natural_loop':
        points, handle = natural_working_state(OrbitsLayout().scaled(.75),
                                               handle_x_m=handle_x_m)
        model_options = dict(initial_points=points, handle_position=handle)
    span = .16
    probe = Probe(prepared/'model.xml', spacing=.0075, checkpoint_each_phase=True,
                  max_penetration_m=.0015, max_grasp_error_m=.015, **model_options)
    midpoint = len(probe.initial)//2
    nodes = {'left': midpoint+14, 'right': midpoint-14}
    if prepared_state is not None:
        source = Path(prepared_state)
        if hashlib.sha256((source/'model.xml').read_bytes()).digest() != hashlib.sha256(
                (prepared/'model.xml').read_bytes()).digest():
            raise ValueError('Prepared state must use the same cord and handle model')
        probe.restore(source)
        probe.events.append(dict(event='reuse_preparation_checkpoint', source=str(source)))
    else:
        probe.data.eq_active[probe.model.equality('grasp_handle').id] = False
        if cord_layout == 'natural_loop':
            probe.data.eq_active[probe.model.equality('grasp_bight').id] = False
            probe.move('free_handle_and_cord_settle', seconds=2.)
            probe.grasp_midpoint()
        probe.move('prepare_bight_above_lowest_ring', [.1, 0, .26], seconds=4.)
        probe.grasp_nodes(list(nodes.values()))
        probe.move('prepare_two_leg_grasps', [.1, 0, .24], span=span, seconds=4.)
    probe.save(prepared)

    runtime = RobotRuntime(cfg, folder, **model_options)
    runtime.data.qpos[16:] = probe.data.qpos
    runtime.data.qvel[16:] = probe.data.qvel
    rotations = {'left': Rotation.identity(), 'right': Rotation.from_euler('z', 180, degrees=True)}
    q = runtime.data.qpos[:16].copy()
    for side, node in nodes.items():
        q, bad = runtime.ik(side, probe.points()[node], rotations[side], seed=q)
        if bad:
            raise ValueError(f'Paired pregrasp collision: {side}: {bad}')
    q[[6, 7, 14, 15]] = .015
    bad = runtime.checker.violations(q)
    if bad:
        raise ValueError(f'Open paired pregrasp collision: {bad}')
    runtime.data.qpos[:16] = q
    runtime.data.ctrl[:] = q[runtime.actuated_q]
    for side, key in [('left', 'grasp_bight'), ('right', 'grasp_fold_1')]:
        e = runtime.model.equality(key).id
        runtime.model.eq_obj2id[e] = runtime.nodes[nodes[side]]
        runtime.data.eq_active[e] = True
    mujoco.mj_forward(runtime.model, runtime.data)
    runtime.frames = []
    runtime.record('supported_pregrasp_initialization')
    runtime.events.append(dict(event='pregrasp_initialization_support', nodes=nodes,
        scope='Two supported cord-leg grasps; handle free; not a table pickup'))
    q[[6, 7, 14, 15]] = .009
    scope = dict(scope='native_assisted_two_arm_bight_spreading_probe', full_task_success=False,
                 starts_pregrasped=True, initial_bight_already_lifted_through_ring4=True,
                 unassisted_hold_tested=False, leg_nodes=nodes,
                 span_m=span, preparation=str(prepared),
                 reused_preparation=None if prepared_state is None else str(prepared_state),
                 cord_layout=cord_layout,
                 rest_cord_length_m=float(np.linalg.norm(np.diff(probe.initial, axis=0), axis=1).sum()),
                 handle_initial_position_m=probe.model.body('handle').pos.tolist(),
                 handle_fixed=False,
                 initial_threading=threading_signature(probe.points(), probe.layout))
    (folder/'recipe.json').write_text(json.dumps(dict(
        entrypoint='topogym.tasks.orbits.bimanual_bight_demo', cord_layout=cord_layout,
        handle_x_m=handle_x_m,
        prepared_state=None if prepared_state is None else str(prepared_state)), indent=2)+'\n')
    (folder/'scope.json').write_text(json.dumps(scope, indent=2)+'\n')
    try:
        runtime.joint_move('close_supported_fingers', q, .75)
        runtime.joint_move('supported_settle', q, .75)
        for side, node in nodes.items():
            runtime.engage_grasp(side, node=node)
        for phase, center, seconds in [
            ('raise_open_bight', [.1, 0, .45], 5.),
            ('carry_open_bight_over_ball', [-.17, 0, .45], 5.),
            ('lower_bight_outside_first_ring', [-.19, 0, .27], 5.),
        ]:
            q = runtime.data.qpos[:16].copy()
            for side, sign in [('left', 1), ('right', -1)]:
                point = np.asarray(center)+[0, sign*span/2, 0]
                q, _ = runtime.ik(side, point, rotations[side], seed=q)
            bad = runtime.checker.violations(q)
            if bad:
                raise ValueError(f'{phase} paired target collision: {bad}')
            runtime.joint_move(phase, q, seconds)
            runtime.metrics[-1]['threading'] = threading_signature(runtime.points(), probe.layout)
        runtime.joint_move('hold_open_bight', q, 1.)
    finally:
        runtime.save()
        scope['final_threading'] = threading_signature(runtime.points(), probe.layout)
        (folder/'scope.json').write_text(json.dumps(scope, indent=2)+'\n')
    return runtime


if __name__ == '__main__':
    import argparse
    from hydra import compose, initialize_config_dir
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--cord-layout', choices=['natural_loop', 'legacy_folded'],
                        default='natural_loop')
    parser.add_argument('--handle-x', type=float, default=.60)
    parser.add_argument('--prepared-state', type=Path)
    args = parser.parse_args()
    with initialize_config_dir(config_dir=str(Path(__file__).resolve().parents[3]/'configs'), version_base='1.3'):
        cfg = compose(config_name='orbits_preview')
    run(cfg, args.folder, cord_layout=args.cord_layout, handle_x_m=args.handle_x,
        prepared_state=args.prepared_state)
