"""Private reference adapter: passive policy -> checked IK -> public Session.step.

This module belongs to the oracle's private solution, never the public image.
It does not create/reset a scene, move objects, attach grasps, or change physics.
The caller's run-oracle recorder owns the complete public action trajectory.
"""
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation


def public_row(session, native):
    """Preserve omitted targets and reject a lossy native gripper conversion."""
    targets = session.env._robot.capture_state().targets
    row = session.hold_action().astype(np.float64)
    for side, group in session.env._robot.groups.items():
        target = dict(targets[side], **native.get(side, {}))
        row[session.robot.arm_slice[side]] = target['joint_position_rad']
        close = float(target[group.gripper_field])
        width = float(np.float32(session.robot.native_to_width(side, close)))
        if abs(session.robot.width_to_native(side, width)-close) > 1e-6:
            raise ValueError('Policy gripper target is not representable by public widths')
        row[session.robot.grip_index[side]] = width
    row = row.astype(np.float32)
    if not np.isfinite(row).all() or not np.array_equal(session.robot.clip(row), row):
        raise ValueError('Policy action would be clipped by the public adapter')
    return row


def run_feedback_policy(session, output):
    from topogym.assets.geometry.cast_keyhole import plate_assembly_transforms
    from topogym.assets.variation_resources import read_json
    from topogym.robot.control import action_spec, compile_action
    from topogym.utils.io import to_jsonable, write_json_atomic
    from .policy import PARTS
    from .simplified_policy import SimplifiedKeyholePolicy
    from .kinematics import preflight_simplified_pickup, preflight_simplified_goal

    if session.n_steps != 0 or session._resets != 0:
        raise ValueError('Feedback reference requires a fresh frozen Session')
    output = Path(output)
    task, robot = session.env._task, session.env._robot
    geometry = read_json(task.geometry_resource)
    built = json.loads((session.env._asset_build.root / 'geometry_report.json').read_text())
    origins = {body['name']: np.asarray(body['origin_m']) for body in built['bodies']}
    transforms = plate_assembly_transforms(geometry)
    # Task placement vertices already include the complete collision/visible
    # geometry in each link frame. Transform those existing vertices for planning.
    vertices = {side: Rotation.from_matrix(transforms[metal][:3, :3]).inv().apply(
        np.asarray(task.placement_vertices[PARTS[side]])+origins[PARTS[side]]-transforms[metal][:3, 3])
        for side, metal in [('left', 'gold'), ('right', 'silver')]}
    closed = {side: session.robot.width_to_native(side, 0.) for side in PARTS}
    if not np.isclose(closed['left'], closed['right'], atol=1e-12, rtol=0):
        raise ValueError('This reference requires matching ALOHA gripper adapters')
    class TableClearancePolicy(SimplifiedKeyholePolicy):
        # Small, bounded TCP planning offsets accommodate naturally settled
        # plate tilt. They never move a body or relax the collision audit.
        grasp_raise_m = 0.

        def grasp_targets(self, bodies):
            return {side: (position + [0., 0., self.grasp_raise_m], rotation)
                    for side, (position, rotation) in super().grasp_targets(bodies).items()}

    policy = TableClearancePolicy(geometry=geometry, variation=task.variation_id,
        body_origins=origins, goal_region=task.terminal_metadata()['goal_region'],
        mount_position=[0., 0., 0.], canonical_vertices=vertices,
        part='all', speed=1., gripper_closed_native_m=closed['left'])
    policy.initialize(dict(action_spec=action_spec(robot.description, 'EE_ABS'),
                           timing_spec=session.env.timing_spec))

    def observe():
        return dict(state=dict(sim_time_s=session.env._world.sim_time_s),
                    robot=robot.observe(), privileged=dict(world=session.env._world.read_state()))

    def submit(action):
        native = compile_action(robot, action, 'EE_ABS')
        return session.step(public_row(session, native))

    report = dict(status='running', public_actions_only=True, from_frozen_home=True,
        initial_state_sha=session.instance_sha, gripper_closed_native_m=closed['left'], phases=[],
        scope='feedback through public Session; independent open-loop grading still required')
    write_json_atomic(output/'feedback_report.json', report)
    try:
        for index in range(30):
            if submit({s: dict(gripper_position_m=.024) for s in PARTS} if index == 0 else {}):
                raise RuntimeError('Episode ended during initial settling')
        policy.obs = observe()
        attempts = []
        for raise_m in (0., .001, .002):
            policy.grasp_raise_m = raise_m
            plan = preflight_simplified_pickup(robot, session.env._world.entities, origins,
                                              geometry, policy, task.table_height_m)
            attempts.append(dict(grasp_raise_m=raise_m, passed=plan['passed'],
                                 failure=plan['failure'], collision_audit=plan['collision_audit']))
            if plan['passed']:
                break
        report['pickup_candidates'] = attempts
        report['grasp_raise_m'] = policy.grasp_raise_m
        write_json_atomic(output/'pickup_plan.json', plan)
        if not plan['passed']:
            raise RuntimeError('Frozen-session pickup preflight failed')
        policy.pickup_transit = plan['tcp_path']
        last_phase = None
        with (output/'feedback_states.jsonl').open('w', buffering=1) as states:
            while session.n_steps < session.max_steps:
                obs = observe()
                action = policy.act(obs)
                if policy.phase != last_phase:
                    report['phases'].append(dict(phase=policy.phase, sim_time_s=session.sim_time_s))
                    last_phase = policy.phase
                    if policy.phase == 'gold_raise_clear':
                        goal = preflight_simplified_goal(robot, session.env._world.entities, origins,
                                                        geometry, policy, task.table_height_m)
                        write_json_atomic(output/'goal_plan.json', goal)
                        if not goal['passed']:
                            raise RuntimeError('Frozen-session carried-piece goal preflight failed')
                    print(json.dumps(dict(oracle_phase=policy.phase, sim_time_s=session.sim_time_s)), flush=True)
                if session.n_steps % 20 == 0:
                    world = obs['privileged']['world']
                    states.write(json.dumps(to_jsonable(dict(row=session.n_steps, state=obs['state'],
                        robot=obs['robot'], bodies={n: world['bodies'][n] for n in PARTS.values()},
                        grasp=world['grasp'], diagnostics=policy.diagnostics)))+'\n')
                if action is None or submit(action):
                    break
                if session.n_steps % 200 == 0:
                    print(json.dumps(dict(oracle_row=session.n_steps, phase=policy.phase,
                                          sim_time_s=session.sim_time_s)), flush=True)
            report.update(status='passed' if session.success() else 'failed',
                          task_success=session.success(), session_status=session.status())
            if not session.success():
                raise RuntimeError('Feedback reference did not complete the Task')
    except BaseException as error:
        report.update(status='failed', error=repr(error), last_phase=policy.phase,
                      diagnostics=to_jsonable(policy.diagnostics), task_success=session.success())
        raise
    finally:
        report['task_result'] = to_jsonable(task.result)
        write_json_atomic(output/'feedback_report.json', report)
