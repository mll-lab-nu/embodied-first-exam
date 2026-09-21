"""Bimanual grasp-and-lift development witness, with an explicit pregrasp start.

This is not the full Orbits solution. Fixture preparation places the objects
between the jaws. Native contact is checked before grasp assistance is used;
an optional unassisted hold is recorded separately.
"""
from pathlib import Path
import json

import mujoco
import numpy as np
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation

from .dynamics import Probe
from .robot_runtime import RobotRuntime


def run(cfg, folder, *, bight_start=(.111, .085, .045), handle_start=(.3225, -.08, .06), left_rotation=None,
        right_rotation=None, left_opening=.015, left_closed=.009,
        friction_hold_s=.5, stages=None):
    if friction_hold_s < 0:
        raise ValueError('Friction hold duration must be nonnegative')
    folder = Path(folder)
    prepared = folder.parent / (folder.name+'_preparation')
    prepared.mkdir(parents=True, exist_ok=False)
    probe = Probe(prepared/'model.xml', spacing=.0075)
    probe.move('prepare_objects', bight_start, handle=handle_start, seconds=3.)
    probe.save(prepared)
    runtime = RobotRuntime(cfg, folder)
    OmegaConf.save(cfg, folder/'config.yaml', resolve=True)
    runtime.data.qpos[16:] = probe.data.qpos
    runtime.data.qvel[16:] = probe.data.qvel
    midpoint = len(probe.initial)//2
    handle_body = probe.model.body('handle').id
    position = probe.data.xpos[handle_body].copy()
    handle_rotation = probe.data.xmat[handle_body].reshape(3, 3)
    opening = handle_rotation[:, 1]
    angle = np.radians(225.)
    direction = np.cos(angle)*handle_rotation[:, 0]+np.sin(angle)*handle_rotation[:, 2]
    if right_rotation is None:
        right_rotation = runtime.checker.yaw*Rotation.from_matrix(
            np.column_stack([direction, opening, np.cross(direction, opening)]))
    rotations = {'left': Rotation.identity() if left_rotation is None else left_rotation,
                 'right': right_rotation}
    if stages is None:
        stages = [('left_lift', 'left', [.111, .085, .16]),
                  ('right_lift', 'right', [.3225, -.08, .11])]
    recipe = dict(bight_start=list(bight_start), handle_start=list(handle_start), left_opening=left_opening,
                  left_closed=left_closed, friction_hold_s=friction_hold_s, stages=stages,
                  left_rotation_xyzw=rotations['left'].as_quat().tolist(),
                  right_rotation_xyzw=rotations['right'].as_quat().tolist())
    (folder/'recipe.json').write_text(json.dumps(recipe, indent=2)+'\n')
    q = runtime.data.qpos[:16].copy()
    for side, point in [('left', probe.points()[midpoint]), ('right', position)]:
        q, bad = runtime.ik(side, point, rotations[side], seed=q)
        if bad:
            raise ValueError(f'Pregrasp arm collision for {side}: {bad}')
    q[[6, 7]] = left_opening
    q[[14, 15]] = .023
    runtime.data.qpos[:16] = q
    runtime.data.ctrl[:] = q[runtime.actuated_q]
    for name in ['grasp_bight', 'grasp_handle']:
        runtime.data.eq_active[runtime.model.equality(name).id] = True
    mujoco.mj_forward(runtime.model, runtime.data)
    runtime.frames = []
    runtime.record('supported_pregrasp_initialization')
    runtime.events.append(dict(event='pregrasp_initialization_support',
                               scope='objects placed between jaws; this is not a pickup from the table'))
    q[[6, 7]] = left_closed
    q[[14, 15]] = .0213
    try:
        runtime.joint_move('close_supported_fingers', q, .75)
        runtime.joint_move('supported_settle', q, .75)
        for name in ['grasp_bight', 'grasp_handle']:
            runtime.data.eq_active[runtime.model.equality(name).id] = False
        before = np.array([runtime.points()[midpoint], runtime.data.xpos[runtime.model.body('handle').id]])
        if friction_hold_s:
            runtime.joint_move('unsupported_friction_hold', q, friction_hold_s)
        after = np.array([runtime.points()[midpoint], runtime.data.xpos[runtime.model.body('handle').id]])
        runtime.events.append(dict(event='friction_hold_witness' if friction_hold_s else
                                  'unassisted_hold_not_tested', duration_s=friction_hold_s,
                                   translation_drift_m=(after-before).tolist(),
                                   left_contacts=runtime.grasp_contacts('left', 'cord', node=midpoint),
                                   right_contacts=runtime.grasp_contacts('right', 'handle')))
        runtime.engage_grasp('left', node=midpoint)
        runtime.engage_grasp('right')
        for stage in stages:
            name, side, point = stage[:3]
            if len(stage) >= 4 and stage[3] is not None:
                rotations[side] = Rotation.from_quat(stage[3])
            q, bad = runtime.ik(side, point, rotations[side])
            if bad:
                raise ValueError(f'{name} target collision: {bad}')
            runtime.joint_move(name, q, stage[4] if len(stage) >= 5 else 3.)
        runtime.joint_move('hold_both_lifted', q, 1.)
    finally:
        runtime.save()
        (folder/'scope.json').write_text(json.dumps(dict(
            scope='pregrasp_bimanual_grasp_and_lift_probe', full_solution=False,
            preparation=str(prepared), grasp_model='contact-gated point constraints after pregrasp initialization',
            bight_start=list(bight_start), handle_start=list(handle_start), left_opening=left_opening, left_closed=left_closed,
            unassisted_friction_hold_s=friction_hold_s,
            stages=stages, initial_rotations_xyzw={side:recipe[side+'_rotation_xyzw']
                                                  for side in rotations},
            final_rotations_xyzw={side:rotation.as_quat().tolist()
                                   for side, rotation in rotations.items()},
            starts_pregrasped=True), indent=2)+'\n')
    return runtime


if __name__ == '__main__':
    import argparse
    from hydra import compose, initialize_config_dir
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--recipe', type=Path, help='JSON parameters from a previous local probe')
    args = parser.parse_args()
    with initialize_config_dir(config_dir=str(Path(__file__).resolve().parents[3]/'configs'), version_base='1.3'):
        cfg = compose(config_name='orbits_preview')
    parameters = json.loads(args.recipe.read_text()) if args.recipe else {}
    for side in ('left', 'right'):
        key = side+'_rotation_xyzw'
        if key in parameters:
            parameters[side+'_rotation'] = Rotation.from_quat(parameters.pop(key))
    run(cfg, args.folder, **parameters)
