"""CPU reachability of the authored initial grasp and nominal first draw.

This checks robot kinematics at discrete poses. It is not a rope simulation,
continuous collision certificate, or evidence that a knot can be untied.
"""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation

from topogym.robot.assets import robot_asset
from .control import BoundedAlohaIK
from .family_actions import ROUTES, configure_family_start, initial_grasp_sites, route_for_config
from .physics_probe import make_config
from .robot_probe import TOOL_OFFSET


def check_initial_route(cfg, *, nominal_draw_m=None, draw_waypoints_m=None):
    route = route_for_config(cfg)
    if nominal_draw_m is None:
        nominal_draw_m = route.stroke_m*route.maximum_strokes_per_grasp
    if not 0. < nominal_draw_m <= .50:
        raise ValueError('CPU nominal draw must be in (0, 0.50] m')
    family = str(cfg.task.geometry.family)
    points, arc, indices = initial_grasp_sites(cfg)
    initial = configure_family_start(cfg)
    model = mujoco.MjModel.from_xml_path(robot_asset(cfg.robot_control))
    data = mujoco.MjData(model)
    names = list(cfg.robot_control.robot.arm_joint_names)
    for side in ('left', 'right'):
        for name, value in zip(names+list(cfg.robot_control.robot.finger_joint_names), cfg.robot_control.home[side]):
            data.qpos[model.joint(f'{side}/{name}').qposadr[0]] = value
    mujoco.mj_forward(model, data)
    mount = Rotation.from_euler('xyz', cfg.env.robot_mount.euler, degrees=True)
    origin = np.asarray(cfg.env.robot_mount.pos)
    arms, quats = {}, {}
    for side in ('left', 'right'):
        body = model.body(f'{side}/gripper_link').id
        p = origin+mount.apply(data.xpos[body])
        q = (mount*Rotation.from_matrix(data.xmat[body].reshape(3, 3))).as_quat()[[3, 0, 1, 2]]
        joints = np.asarray(cfg.robot_control.home[side][:6])
        arms[side] = SimpleNamespace(hand_pos=lambda p=p: p, hand_quat=lambda q=q: q,
                                    arm_qpos=lambda joints=joints: joints)
        quats[side] = q
    ik = BoundedAlohaIK(None, SimpleNamespace(cfg=cfg.robot_control, arms=arms, left=arms['left']))
    left, right = points[indices].copy()
    direction = (points[indices[0]+1]-points[indices[0]-1])*(1 if route.working_end == 0 else -1)
    direction[2] = 0.
    direction /= np.linalg.norm(direction)
    feed = left-right
    feed[2] = 0.
    feed *= .012/np.linalg.norm(feed)
    samples = []

    def solve_pose(stage, targets):
        for side, target in zip(('left', 'right'), targets):
            quat = quats[side]
            try:
                q = ik.solve(side, target-Rotation.from_quat(quat[[1, 2, 3, 0]]).apply(TOOL_OFFSET), quat)
            except ValueError as exc:
                raise ValueError(f'{stage}: {exc}') from exc
            for name, value in zip(names, q):
                data.qpos[model.joint(f'{side}/{name}').qposadr[0]] = value
            if route.approach_finger_qpos_m is not None:
                finger_qpos = (float(cfg.robot_control.gripper.open_qpos)
                               if side == 'left' and stage == 'right_lower'
                               else route.approach_finger_qpos_m)
                if route.preopen_upper_with_tail_anchor:
                    if side == 'left':
                        finger_qpos = (route.approach_finger_qpos_m
                                       if stage in ('anchor_lower', 'anchor_withdraw') else .013)
                    elif stage in ('anchor_lower', 'anchor_lift'):
                        finger_qpos = float(cfg.robot_control.gripper.open_qpos)
                    else:
                        finger_qpos = route.approach_finger_qpos_m if stage == 'right_lower' else .013
                for name in cfg.robot_control.robot.finger_joint_names:
                    data.qpos[model.joint(f'{side}/{name}').qposadr[0]] = finger_qpos
        mujoco.mj_forward(model, data)
        penetration = max([max(0., -float(c.dist)) for c in data.contact], default=0.)
        if penetration > .0005:
            contact = min(data.contact, key=lambda c: float(c.dist))
            bodies = [model.body(int(model.geom_bodyid[g])).name for g in (contact.geom1, contact.geom2)]
            raise ValueError(f'{stage}: sampled robot penetration {penetration:.6f} m between {bodies}; '
                             f'tool targets {np.asarray(targets).tolist()}')
        samples.append(dict(stage=stage, targets_m=np.asarray(targets).tolist(),
                            joint_positions=data.qpos.tolist(), robot_penetration_m=penetration))

    # Follow the actual side order. Use the approach aperture as an open-jaw
    # envelope; actual contact closure and FEM are outside this CPU check.
    if route.preopen_upper_with_tail_anchor:
        for z in np.linspace(.04, 0., 17):
            solve_pose('anchor_lower', (left+[0, 0, z], right+[0, 0, .04]))
        for fraction in np.linspace(0., 1., 7):
            solve_pose('anchor_lift', (left+[0, 0, .012*fraction], right+[0, 0, .04]))
        for z in np.linspace(.04, 0., 17):
            solve_pose('right_lower', (left+[0, 0, .012], right+[0, 0, z]))
        for z in np.linspace(0., route.preopen_lift_m, 25):
            solve_pose('open_upper_lift', (left+[0, 0, .012], right+[0, 0, z]))
        shift = np.asarray(route.preopen_shift_m)
        for fraction in np.linspace(0., 1., 33):
            solve_pose('open_upper_shift', (left+[0, 0, .012],
                right+[0, 0, route.preopen_lift_m]+shift*fraction))
        if route.preopen_maximum_extra_lift_m:
            steps = max(1, int(np.ceil(route.preopen_maximum_extra_lift_m/.005)))
            for extra in np.linspace(0., route.preopen_maximum_extra_lift_m, steps+1):
                solve_pose('open_upper_clearance', (left+[0, 0, .012],
                    right+[0, 0, route.preopen_lift_m+extra]+shift))
        maximum_opening_lift = route.preopen_lift_m+route.preopen_maximum_extra_lift_m
        clearance_shift = np.asarray(route.preopen_clearance_shift_m)
        if np.linalg.norm(clearance_shift):
            for fraction in np.linspace(0., 1., max(2, int(np.ceil(np.linalg.norm(clearance_shift)/.005)))+1):
                solve_pose('open_upper_clearance_shift', (left+[0, 0, .012],
                    right+[0, 0, maximum_opening_lift]+shift+clearance_shift*fraction))
        for fraction in np.linspace(0., 1., 33):
            solve_pose('anchor_withdraw', (left+[0, 0, .012]+np.asarray(route.preopen_anchor_withdraw_m)*fraction,
                right+[0, 0, maximum_opening_lift]+shift+clearance_shift))
        return dict(passed=True,
            scope='discrete CPU prefix only: tail anchor, upper-strand lift/shift, anchor withdrawal',
            family=family, route_id=route.route_id, route_profile=cfg.task.get('route_profile'),
            world_yaw_deg=float(cfg.task.yaw_deg), initial_robot_pose=initial,
            grasp_arc_m=arc[indices].tolist(), samples=samples,
            maximum_ik_position_residual_m=ik.max_position_residual,
            maximum_ik_rotation_residual_rad=ik.max_rotation_residual,
            approach_finger_qpos_m=route.approach_finger_qpos_m,
            maximum_opening_lift_checked_m=float(maximum_opening_lift),
            extra_opening_lift_checked_after_shift_m=float(route.preopen_maximum_extra_lift_m),
            final_clearance_shift_checked_m=clearance_shift.tolist(),
            physics_qualified=False, untying_verified=False, swept_collision_checked=False,
            regrasp_path_checked=False, nominal_draw_checked=False,
            limitation='The under-strand grasp and subsequent draw must be planned from the physically opened state')
    for z in np.linspace(.04, 0., 17):
        solve_pose('right_lower', (left+[0, 0, .04], right+[0, 0, z]))
    for z in np.linspace(.04, 0., 17):
        solve_pose('left_lower', (left+[0, 0, z], right))
    for fraction in np.linspace(0., 1., 7):
        solve_pose('lift', (left+[0, 0, .015*fraction], right+[0, 0, .012*fraction]))
    for fraction in np.linspace(0., 1., 7):
        solve_pose('feed', (left+[0, 0, .015], right+[0, 0, .012]+feed*fraction))
    if draw_waypoints_m is None:
        offsets = np.array([[0., 0., 0.], direction*nominal_draw_m])
        if route.lateral_clearance_m:
            lateral = np.cross([0., 0., 1.], direction)*route.lateral_clearance_m
            if lateral @ (left-right) < 0:
                lateral *= -1
            offsets = np.array([[0., 0., 0.], lateral, lateral+direction*nominal_draw_m])
    else:
        offsets = np.asarray(draw_waypoints_m, dtype=float)
    if offsets.ndim != 2 or offsets.shape[1] != 3 or len(offsets) < 2 or not np.isfinite(offsets).all():
        raise ValueError('CPU draw waypoints must be a finite N by 3 array')
    if not np.allclose(offsets[0], 0.):
        raise ValueError('CPU draw waypoints must begin at the end of the initial lift')
    for start, end in zip(offsets[:-1], offsets[1:]):
        steps = max(1, int(np.ceil(np.linalg.norm(end-start)/.005)))
        for fraction in np.linspace(0., 1., steps+1):
            offset = start+fraction*(end-start)
            solve_pose('nominal_draw', (left+[0, 0, .015]+offset, right+[0, 0, .012]+feed))
    if route.spread_before_first_regrasp_m:
        fixed_left = left+[0, 0, .015]+offsets[-1]
        start_right = right+[0, 0, .012]+feed
        spread = start_right-fixed_left
        spread[2] = 0.
        spread *= route.spread_before_first_regrasp_m/np.linalg.norm(spread)
        length = abs(arc[indices[0]]-arc[indices[1]])
        if np.linalg.norm(start_right+spread-fixed_left) > .96*length:
            raise ValueError('Nominal support spread would exhaust the material slack bound')
        for fraction in np.linspace(0., 1., int(np.ceil(np.linalg.norm(spread)/.005))+1):
            solve_pose('nominal_support_spread', (fixed_left, start_right+spread*fraction))
    return dict(passed=True, scope='discrete CPU robot IK/self-collision preflight only',
                family=family, route_id=ROUTES[family].route_id, world_yaw_deg=float(cfg.task.yaw_deg),
                initial_robot_pose=initial, grasp_arc_m=arc[indices].tolist(),
                initial_draw_direction=direction.tolist(), samples=samples,
                nominal_draw_m=float(nominal_draw_m),
                draw_waypoints_m=offsets.tolist(),
                approach_finger_qpos_m=route.approach_finger_qpos_m,
                nominal_support_spread_m=route.spread_before_first_regrasp_m,
                maximum_ik_position_residual_m=ik.max_position_residual,
                maximum_ik_rotation_residual_rad=ik.max_rotation_residual,
                physics_qualified=False, untying_verified=False,
                swept_collision_checked=False, regrasp_path_checked=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--family', choices=tuple(ROUTES), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--appearance-seed', type=int)
    from .families import ROUTE_PROFILES
    parser.add_argument('--route-profile', choices=tuple(ROUTE_PROFILES))
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    cfg = make_config(SimpleNamespace(family=args.family, appearance_seed=args.appearance_seed,
        route_profile=args.route_profile,
        robot='aloha', robot_coupling='external_articulation', dt=.005, x_offset=0.,
        y_offset=0., yaw=0., refined=False, tighter=False, friction_eps=.001))
    try:
        report = check_initial_route(cfg)
    except Exception as exc:
        report = dict(passed=False, family=args.family, physics_qualified=False,
                      untying_verified=False, error=f'{type(exc).__name__}: {exc}')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'samples'}, indent=2))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
