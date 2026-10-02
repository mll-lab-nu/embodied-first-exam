"""Checked transport of two separately held shoes toward table support.

The input is only a geometric guide. Passive bodies remain unconstrained in
physics, and the ordinary-action workflow guards every executed tick.
"""
import numpy as np

from topogym.planning.rigid_reference.feedback import body_pose, relative_pose, tcp_pose
from topogym.planning.rigid_reference.geometry import interpolate, pose_dict
from topogym.utils.io import write_json_atomic


def plan_table_support(planner, observation, guide):
    if not guide.get('passed') or len(guide.get('poses', ())) < 2:
        raise ValueError('Table support requires a checked guide')
    hands = observation['privileged']['world']['grasp']['hands']
    for side in ('left', 'right'):
        binding = hands[side]['binding']
        if not binding or binding['target'][0] != 'horseshoe_' + side:
            raise ValueError('Table transport requires separately held shoes')
    bodies, q = planner.observed(observation)
    anchor = bodies['horseshoe_right']
    source_anchor = body_pose(guide['observed_bodies']['horseshoe_right'])
    local = {name: relative_pose(anchor, pose) for name, pose in bodies.items()}
    offsets = {side: relative_pose(bodies['horseshoe_' + side],
                                 tcp_pose(observation['robot'][side]))
               for side in ('left', 'right')}
    knots = [anchor]
    for row in guide['poses'][1:]:
        p, r = relative_pose(source_anchor, body_pose(row['shoes']['right']))
        knots.append((anchor[0] + anchor[1].apply(p), anchor[1] * r))
    radius = max(float(np.linalg.norm(r.apply(planner.task.placement_vertices[name]) + p,
                                      axis=1).max()) for name, (p, r) in local.items())
    rows = []
    samples = 0
    minimum_table = float('inf')
    maximum_ordinary = maximum_held = 0.
    for edge, (a, b) in enumerate(zip(knots[:-1], knots[1:])):
        motion = np.linalg.norm(b[0] - a[0]) + radius * (b[1] * a[1].inv()).magnitude()
        count = max(1, int(np.ceil(motion / .00075)))
        for fraction in np.linspace(0., 1., count + 1):
            p, r = interpolate(a, b, fraction)
            poses = {name: (p + r.apply(lp), r * lr) for name, (lp, lr) in local.items()}
            gap = min(float((br.apply(planner.task.placement_vertices[name]) + bp)[:, 2].min())
                      - planner.checker.table_height for name, (bp, br) in poses.items())
            if gap < .0005:
                raise ValueError(f'Table guide reaches the table margin at edge {edge}')
            previous = q.copy()
            for side, (op, orot) in offsets.items():
                bp, br = poses['horseshoe_' + side]
                q = planner.checker.solve(side, (bp + br.apply(op), br * orot), q)
            checked = planner.checker.check(q, body_poses=poses)
            if not checked['passed']:
                raise ValueError(f'Table guide collision at edge {edge}: {checked}')
            if np.abs(q - previous).max() > .15:
                raise ValueError(f'Table guide IK branch change at edge {edge}')
            minimum_table = min(minimum_table, gap)
            maximum_ordinary = max(maximum_ordinary, checked['ordinary_depth_m'])
            maximum_held = max(maximum_held, checked['held_finger_depth_m'])
            samples += 1
        rows.append(dict(shoes={side: pose_dict(poses['horseshoe_' + side])
                                for side in offsets}, qpos=q.tolist()))
    result = dict(passed=True, poses=rows, samples=samples,
                  maximum_material_sample_step_m=.00075,
                  minimum_rigid_task_table_gap_m=minimum_table,
                  maximum_ordinary_robot_task_depth_m=maximum_ordinary,
                  maximum_qualified_finger_depth_m=maximum_held,
                  observed_state=observation['state'],
                  scope='Rebased rigid-assembly IK/contact screening; passive table dynamics unvalidated')
    write_json_atomic(planner.directory / 'table_support_plan.json', result)
    return result


def execute_table_support(policy, guide, *, tracking_m=.0015):
    if not np.isfinite(tracking_m) or not .0005<=tracking_m<=.0015:
        raise ValueError('Table tracking tolerance must be within 0.5 and 1.5 mm')
    policy.phase = 'plan_table_support'
    plan = plan_table_support(policy.planner, policy.obs, guide)
    for index, row in enumerate(plan['poses']):
        target = {side: body_pose(pose) for side, pose in row['shoes'].items()}
        actual = policy.bodies()
        motion = max(float(np.linalg.norm(target[side][0] - actual[side][0]) +
                           .15 * (target[side][1] * actual[side][1].inv()).magnitude())
                     for side in target)
        gap = min(float((r.apply(policy.planner.task.placement_vertices['horseshoe_' + side])
                         + p)[:, 2].min()) - policy.planner.checker.table_height
                  for side, (p, r) in target.items())
        near_table = gap < .015
        yield from policy.follow_bodies(
            target, max(.15, motion / (.002 if near_table else .006)),
            f'transport_to_table_{index}', tracking_m=tracking_m if near_table else .0015,
            position_bias_limit_m=.06, position_integral_gain_s_inv=2.,
            position_velocity_gain_s=.25, position_velocity_filter_s=.1,
            tracking_stall_timeout_s=10.)
    yield from policy.follow_bodies(target, 2., 'hold_at_table', tracking_m=tracking_m,
                                   position_bias_limit_m=.06, position_velocity_gain_s=.25,
                                   position_velocity_filter_s=.1, tracking_stall_timeout_s=10.)
    actual = policy.bodies()
    errors = {side: float(np.linalg.norm(actual[side][0] - p) +
                         .10 * (actual[side][1] * r.inv()).magnitude())
              for side, (p, r) in target.items()}
    policy.table_support_result = dict(passed=max(errors.values()) < tracking_m,
                                       tracking_limit_m=tracking_m,
                                       body_target_errors_m=errors, state=policy.obs['state'],
                                       scope='Measured transport endpoint with both shoes still held')
    write_json_atomic(policy.planner.directory / 'table_support_result.json', policy.table_support_result)
    write_json_atomic(policy.planner.directory / 'table_observation.json', policy.obs)
    policy.phase = 'table_transport_complete'
