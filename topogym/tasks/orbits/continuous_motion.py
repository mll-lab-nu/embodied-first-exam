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
from .workspace import PAD_CENTER


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
                   position_step_m=.004, rotation_step_rad=.04, tool_offset=None):
    """Solve the whole sampled segment before issuing any actuator command."""
    if side not in ('left', 'right'):
        raise ValueError(f'Unknown arm {side}')
    r = runtime
    mujoco.mj_kinematics(r.model, r.data)
    body = r.model.body(side+'/gripper_link').id
    offset = PAD_CENTER if tool_offset is None else np.asarray(tool_offset, dtype=float)
    if offset.shape != (3,) or not np.isfinite(offset).all():
        raise ValueError('Tool offset must be a finite gripper-local point')
    start = r.data.xpos[body]+r.data.xmat[body].reshape(3, 3)@offset
    start_rotation = r.checker.yaw*Rotation.from_matrix(r.data.xmat[body].reshape(3, 3))
    rotation = start_rotation if rotation is None else rotation
    point = np.asarray(point, dtype=float)
    angle = (rotation*start_rotation.inv()).magnitude()
    count = max(2, int(np.ceil(np.linalg.norm(point-start)/position_step_m)),
                int(np.ceil(angle/rotation_step_rad)))
    slerp = Slerp([0, 1], Rotation.from_quat([start_rotation.as_quat(), rotation.as_quat()]))
    q = r.data.qpos[:16].copy()
    finger_commands = {"left": r.data.ctrl[6], "right": r.data.ctrl[13]}
    if opening is not None:
        finger_commands[side] = opening
    # A squeezed cord keeps the physical jaws wider than the servo target.
    # Check that measured envelope; retain the squeezing command in playback.
    for hand, fingers in (("left", [6, 7]), ("right", [14, 15])):
        q[fingers] = np.maximum(q[fingers], finger_commands[hand])
    result, diagnostics = [], []
    for fraction in np.linspace(0, 1, count+1)[1:]:
        local = start+fraction*(point-start)
        desired_rotation = slerp(fraction)
        world = (r.checker.yaw.apply(local)+r.checker.origin+
                 desired_rotation.apply(PAD_CENTER-offset))
        candidate, pe, re = r.checker.solve(side, world, desired_rotation, q)
        if pe > .0005 or re > .005:
            raise ValueError(f'{side} continuous IK at {fraction:.3f}: {pe:.6f} m, {re:.6f} rad')
        if np.max(np.abs(candidate[r.checker.indices[side]]-q[r.checker.indices[side]])) > .2:
            raise ValueError('Discontinuous inverse-kinematics branch')
        bad = r.checker.violations(candidate)
        if bad:
            raise ValueError(f'{side} path collision at {fraction:.3f}: {bad}')
        command = candidate.copy()
        command[[6, 7]] = finger_commands['left']
        command[[14, 15]] = finger_commands['right']
        result.append(command)
        diagnostics.append(dict(fraction=float(fraction), position_error_m=pe,
                                rotation_error_rad=re))
        q = candidate
    return np.asarray(result), diagnostics


def move(runtime, phase, side, point, rotation=None, *, seconds=3., opening=None,
         held_point=False):
    offset = None
    if held_point:
        names = ('grasp_bight', 'grasp_fold_0') if side == 'left' else ('grasp_handle', 'grasp_fold_1')
        active = [runtime.model.equality(name).id for name in names
                  if runtime.data.eq_active[runtime.model.equality(name).id]]
        if len(active) != 1:
            raise ValueError('Held-point motion requires exactly one active grasp on the arm')
        offset = runtime.model.site_pos[runtime.model.eq_obj1id[active[0]]].copy()
    path, errors = cartesian_path(runtime, side, point, rotation, opening=opening,
                                  tool_offset=offset)
    folder = runtime.folder/'planned_paths'; folder.mkdir(exist_ok=True)
    np.savez_compressed(folder/f'{phase}.npz', qpos=path)
    (folder/f'{phase}.json').write_text(json.dumps(dict(side=side, target_task_m=list(point),
        seconds=seconds, held_point=held_point, checked_samples=errors, position_sample_spacing_m=.004,
        rotation_sample_spacing_rad=.04, continuous_collision_proof=False), indent=2)+'\n')
    runtime.joint_path(phase, path, seconds, max_penetration_m=.0015)


def joint_transfer_path(runtime, side, target, *, seed=0, iterations=3000,
                        step_rad=.15, sample_rad=.025):
    """Plan a free-space arm transfer, checking both arms and the fixture.

    This changes the TCP route, so it must not replace a specified threading
    segment. Cord contacts are checked during native execution, not by FCL.
    Planning does not change the simulation's qpos, qvel, controls or time.
    """
    if side not in ('left', 'right'):
        raise ValueError(f'Unknown arm {side}')
    r = runtime
    indices = r.checker.indices[side]
    base = r.data.qpos[:16].copy()
    target = np.asarray(target, dtype=float)
    if target.shape != (16,) or not np.isfinite(target).all():
        raise ValueError('Joint transfer target must contain 16 finite joints')
    start, goal = base[indices], target[indices]
    low, high = r.checker.limits.T
    if np.any(goal < low) or np.any(goal > high):
        raise ValueError('Joint transfer target exceeds arm limits')

    def valid(angles):
        q = base.copy(); q[indices] = angles
        return not r.checker.violations(q)

    def edge(a, b):
        count = max(1, int(np.ceil(np.max(np.abs(b-a))/sample_rad)))
        return all(valid(a+(b-a)*t) for t in np.linspace(0, 1, count+1)[1:])

    if not valid(start) or not valid(goal):
        raise ValueError('Joint transfer start or goal collides')
    path = None
    if edge(start, goal):
        path = [start, goal]
    else:
        rng = np.random.default_rng(seed)
        trees = [([start.copy()], [-1]), ([goal.copy()], [-1])]

        def extend(tree, sample):
            nodes, parents = tree
            nearest = int(np.argmin(np.linalg.norm(np.asarray(nodes)-sample, axis=1)))
            delta = sample-nodes[nearest]
            distance = np.linalg.norm(delta)
            point = sample.copy() if distance <= step_rad else nodes[nearest]+delta*step_rad/distance
            if distance < 1e-10:
                return nearest, True
            if not edge(nodes[nearest], point):
                return None, False
            nodes.append(point); parents.append(nearest)
            return len(nodes)-1, distance <= step_rad

        def branch(tree, i):
            result = []
            while i >= 0:
                result.append(tree[0][i]); i = tree[1][i]
            return result[::-1]

        for iteration in range(iterations):
            first = iteration % 2
            a, b = trees[first], trees[1-first]
            sample = b[0][0] if rng.random() < .15 else rng.uniform(low, high)
            i, _ = extend(a, sample)
            if i is None:
                continue
            for _ in range(100):
                j, reached = extend(b, a[0][i])
                if j is None:
                    break
                if reached:
                    pa, pb = branch(a, i), branch(b, j)
                    path = pa+pb[-2::-1] if first == 0 else pb+pa[-2::-1]
                    break
            if path is not None:
                break
        if path is None:
            raise ValueError('No collision-free joint transfer found within the search budget')
        # Remove unnecessary detours, preserving sampled collision checks.
        for _ in range(100):
            if len(path) <= 2:
                break
            i, j = sorted(rng.choice(len(path), 2, replace=False))
            if j > i+1 and edge(path[i], path[j]):
                path = path[:i+1]+path[j:]
    result = []
    for a, b in zip(path[:-1], path[1:]):
        count = max(1, int(np.ceil(np.max(np.abs(b-a))/sample_rad)))
        for fraction in np.linspace(0, 1, count+1)[1:]:
            q = base.copy(); q[indices] = a+fraction*(b-a)
            q[[6, 7]] = r.data.ctrl[6]
            q[[14, 15]] = r.data.ctrl[13]
            result.append(q)
    return np.asarray(result)


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
