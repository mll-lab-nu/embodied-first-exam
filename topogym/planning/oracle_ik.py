"""Private, tier-scoped IK candidates; public solver tolerances stay unchanged.

An approximate pose is only a candidate. It must pass the current scene's
joint/geometry sweep before use. Task success and grasp health remain native.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path

import numpy as np

from topogym.solvers.genesis_kinematics import GenesisIKSolver
from topogym.utils.arrays import to_numpy


_SCOPE = ContextVar('below_easy_oracle_ik', default=None)
POSITION_BUDGET_M = .005
ROTATION_BUDGET_RAD = .1


def simplified_tier(env):
    task = getattr(env, '_task', None)
    variation = getattr(task, 'variation_id', '')
    for tier in ('very_easy', 'easier'):
        if variation == tier or variation.endswith('_' + tier):
            return tier
    return None


@dataclass
class CandidateScope:
    env: object
    records: list = field(default_factory=list)
    validator: object = None
    public_bounds: dict = field(default_factory=dict)

    def check_public_bounds(self, goal):
        robot = self.env._robot
        for side, bounds in self.public_bounds.items():
            joints = np.asarray(goal)[robot._q_indices[side][:len(robot.groups[side].arm_joints)]]
            if not np.isfinite(joints).all() or np.any(joints < bounds[:, 0]) or np.any(joints > bounds[:, 1]):
                return dict(passed=False, reason='public_joint_limits', side=side)
        return dict(passed=True)

    def check(self, start, goal):
        bounded = self.check_public_bounds(goal)
        if not bounded['passed']:
            return bounded
        if self.validator is None:
            from .oracle_path import SceneCandidateCheck
            self.validator = SceneCandidateCheck(self.env)
        return self.validator.check(start, goal)


@contextmanager
def below_easy_scope(env, output=None):
    """Nested scopes reuse evidence; exceptions always restore the old context."""
    if simplified_tier(env) is None:
        yield None
        return
    previous = _SCOPE.get()
    if previous is not None and previous.env is env:
        yield previous
        return
    scope = CandidateScope(env)
    token = _SCOPE.set(scope)
    try:
        yield scope
    finally:
        _SCOPE.reset(token)
        if output is not None and scope.records:
            from topogym.utils.io import write_json_atomic
            write_json_atomic(Path(output) / 'ik_candidates.json', dict(
                tier=simplified_tier(env), candidate_position_budget_m=POSITION_BUDGET_M,
                candidate_rotation_budget_rad=ROTATION_BUDGET_RAD, attempts=scope.records,
                scope='private IK and sampled actual geometry; not dynamic or Task success proof'))


def scoped_session_oracle(function):
    @wraps(function)
    def run(session, output, *args, **kwargs):
        with below_easy_scope(session.env, output) as scope:
            adapter = getattr(session, 'robot', None)
            if scope is not None and adapter is not None and hasattr(adapter, 'limits'):
                scope.public_bounds = {s: np.asarray(adapter.limits[span], float)
                                       for s, span in adapter.arm_slice.items()}
            return function(session, output, *args, **kwargs)
    return run


def active_scope(entity=None):
    scope = _SCOPE.get()
    if scope is None or (entity is not None and scope.env._robot.entity is not entity):
        return None
    return scope


def pose_from_grasp(tcp, offset_p, offset_r):
    """Actual rigid body pose from FK TCP and body-to-TCP grasp transform."""
    p, r = tcp
    body_r = r * offset_r.inv()
    return np.asarray(p) - body_r.apply(offset_p), body_r


def carried_bodies(robot, q, offsets):
    """Reconstruct each carried body's world pose from the complete joint candidate."""
    from scipy.spatial.transform import Rotation
    from topogym.solvers.genesis_kinematics import GenesisFKSolver
    frames = GenesisFKSolver(robot.entity).solve(q)
    p = np.asarray(frames['position_world_m']).reshape(-1, 3)
    r = Rotation.from_quat(np.asarray(frames['orientation_wxyz']).reshape(-1, 4)[:, [1, 2, 3, 0]])
    result = {}
    for side, offset in offsets.items():
        group = robot.groups[side]
        index = robot.entity.get_link(group.hand_link).idx_local
        tcp = (p[index] + r[index].apply(group.tcp_position_in_hand_m),
               r[index] * Rotation.from_quat(np.asarray(group.tcp_orientation_in_hand_wxyz)[[1, 2, 3, 0]]))
        result[side] = pose_from_grasp(tcp, *offset)
    return result


def accept_coupled_candidate(robot, start, goal, residuals, strict_limits):
    """Keep old-tier behavior; relaxed coupled results need actual swept geometry.

    Workspace residual is a posture preference in this opt-in scope. Joint
    bounds and the scene sweep still apply to the complete proposed motion.
    """
    residuals = np.asarray(residuals, float)
    if not np.isfinite(residuals).all() or not np.isfinite(goal).all():
        return False
    if np.all(residuals <= np.asarray(strict_limits)):
        return True
    scope = active_scope(robot.entity)
    if scope is None or residuals[0] > POSITION_BUDGET_M or residuals[1] > ROTATION_BUDGET_RAD:
        return False
    result = scope.check(start, goal)
    scope.records.append(dict(kind='coupled', residuals=residuals.tolist(), **result))
    return result['passed']


class OracleIKSolver(GenesisIKSolver):
    """Prefer the existing precise result, then search checked near-pose results."""
    def solve_checked(self, *, position_tolerance_m=1e-4, orientation_tolerance_rad=1e-3, **kwargs):
        try:
            q = super().solve_checked(position_tolerance_m=position_tolerance_m,
                orientation_tolerance_rad=orientation_tolerance_rad, **kwargs)
            return self._bounded_roundoff(q)
        except ValueError as error:
            scope = active_scope(self.entity)
            if scope is None or not str(error).startswith('Unreachable EE pose:'):
                raise
            original_error = str(error)
        robot = scope.env._robot
        start = np.asarray(kwargs.get('initial_qpos', to_numpy(self.entity.get_qpos())), float).reshape(-1).copy()
        indices = np.array([i for side, group in robot.groups.items()
            if group.hand_link == kwargs['link_name'] for i in robot._q_indices[side][:len(group.arm_joints)]], int)
        if not len(indices):
            raise ValueError(original_error)
        side = next(s for s, g in robot.groups.items() if g.hand_link == kwargs['link_name'])
        limits = np.asarray(robot.groups[side].arm_limits_rad, float)
        seeds = [start.copy()]
        # Keep the other arm and passive fingers fixed; deterministic restarts.
        for sign in (1., -1.):
            q = start.copy()
            q[indices] = np.clip(q[indices] + sign * np.resize([.15, -.25, .25, .3, -.15, .3], len(indices)),
                                limits[:, 0] + 1e-6, limits[:, 1] - 1e-6)
            seeds.append(q)
        failures, accepted = [], []
        for seed in seeds:
            options = dict(kwargs, initial_qpos=seed,
                           max_solver_iterations=max(300, kwargs.get('max_solver_iterations', 100)))
            try:
                q = super().solve_checked(position_tolerance_m=max(position_tolerance_m, POSITION_BUDGET_M),
                    orientation_tolerance_rad=max(orientation_tolerance_rad, ROTATION_BUDGET_RAD), **options)
                q = self._bounded_roundoff(q)
                check = scope.check(start, q)
                check.update(self._pose_error(q, kwargs))
                if (check['position_residual_m'] > max(position_tolerance_m, POSITION_BUDGET_M)
                        or check['orientation_residual_rad'] > max(orientation_tolerance_rad, ROTATION_BUDGET_RAD)):
                    check.update(passed=False, reason='pose_budget_after_roundoff')
                if check['passed']:
                    accepted.append((float(np.max(np.abs(q[indices] - start[indices]))), q.copy(), check))
                else:
                    failures.append(check)
            except ValueError as error:
                failures.append(dict(passed=False, reason=str(error)))
        if accepted:
            _, q, check = min(accepted, key=lambda item: item[0])
            scope.records.append(dict(kind='near_pose', link=kwargs['link_name'],
                precise_rejection=original_error, candidates=len(seeds), rejected=failures, **check))
            return q
        scope.records.append(dict(kind='near_pose', link=kwargs['link_name'], passed=False,
                                  precise_rejection=original_error, rejected=failures))
        raise ValueError(f'No checked IK candidate in the current search: {original_error}; {failures}')

    def _pose_error(self, q, target):
        from scipy.spatial.transform import Rotation
        from topogym.solvers.genesis_kinematics import GenesisFKSolver
        frames = GenesisFKSolver(self.entity).solve(q)
        index = self.entity.get_link(target['link_name']).idx_local
        p = np.asarray(frames['position_world_m']).reshape(-1, 3)[index]
        angle = 0.
        if target.get('orientation_wxyz') is not None:
            actual = np.asarray(frames['orientation_wxyz']).reshape(-1, 4)[index]
            angle = (Rotation.from_quat(actual[[1, 2, 3, 0]]).inv() *
                Rotation.from_quat(np.asarray(target['orientation_wxyz'])[[1, 2, 3, 0]])).magnitude()
        return dict(position_residual_m=float(np.linalg.norm(p-target['position_world_m'])),
                    orientation_residual_rad=float(angle))

    def _bounded_roundoff(self, q):
        scope = active_scope(self.entity)
        if scope is None:
            return q
        q = np.asarray(q, float).copy()
        robot = scope.env._robot
        for side, group in robot.groups.items():
            indices = robot._q_indices[side][:len(group.arm_joints)]
            bounds = np.asarray(group.arm_limits_rad)
            bounded = np.clip(q[indices], bounds[:, 0], bounds[:, 1])
            # Match the public EE compiler's numerical-stop normalization.
            # Substantive limit violations still fail the path/action checks.
            if np.max(np.abs(q[indices]-bounded), initial=0.) <= 1e-8:
                q[indices] = bounded
            # A representable command at a stop may round outward in float32.
            # Move only that rounding residue inward; never clip a substantive
            # request that exceeds either the model or the public action range.
            public = scope.public_bounds.get(side, bounds)
            lower, upper = np.maximum(bounds[:, 0], public[:, 0]), np.minimum(bounds[:, 1], public[:, 1])
            low32, high32 = lower.astype(np.float32), upper.astype(np.float32)
            low32 = np.where(low32.astype(float) < lower, np.nextafter(low32, np.float32(np.inf)), low32)
            high32 = np.where(high32.astype(float) > upper, np.nextafter(high32, np.float32(-np.inf)), high32)
            inner = np.clip(q[indices], low32.astype(float), high32.astype(float))
            residue = 2*np.finfo(np.float32).eps*np.maximum(1., np.abs(q[indices]))
            valid = (q[indices] >= bounds[:, 0]) & (q[indices] <= bounds[:, 1])
            q[indices] = np.where(valid & (np.abs(inner-q[indices]) <= residue), inner, q[indices])
        return q


def compile_oracle_action(env, action, mode):
    """Preserve public validation and accurate commands; fallback stays private.

    The public compiler validates the whole input before solving. Only its
    specific unreachable-pose error enters this already-validated EE fallback.
    """
    from topogym.robot.control import compile_action
    try:
        return compile_action(env._robot, action, mode)
    except ValueError as error:
        if active_scope(env._robot.entity) is None or mode not in ('EE_ABS', 'EE_DELTA') or not str(error).startswith('Unreachable EE pose:'):
            raise
    from scipy.spatial.transform import Rotation
    robot = env._robot
    observed = robot.observe()
    start = to_numpy(robot.entity.get_qpos()).reshape(-1).copy()
    q = start.copy()
    result = {}
    solver = OracleIKSolver(robot.entity)
    for side, command in action.items():
        group = robot.groups[side]
        out = result[side] = {k: v for k, v in command.items() if k == group.gripper_field}
        if not set(command) - {group.gripper_field}:
            continue
        p = np.asarray(observed[side]['tcp_position_world_m'], float).copy()
        r = Rotation.from_quat(np.asarray(observed[side]['tcp_orientation_wxyz'])[[1, 2, 3, 0]])
        if mode == 'EE_ABS':
            p = np.asarray(command['position_world_m'], float)
            r = Rotation.from_quat(np.asarray(command['orientation_wxyz'])[[1, 2, 3, 0]])
        else:
            p += np.asarray(command.get('translation_world_m', [0., 0., 0.]))
            r = Rotation.from_rotvec(command.get('rotation_world_rad', [0., 0., 0.])) * r
        hand = r * Rotation.from_quat(np.asarray(group.tcp_orientation_in_hand_wxyz)[[1, 2, 3, 0]]).inv()
        q = solver.solve_checked(link_name=group.hand_link,
            position_world_m=p - hand.apply(group.tcp_position_in_hand_m),
            orientation_wxyz=hand.as_quat()[[3, 0, 1, 2]], initial_qpos=q,
            joint_dof_indices=robot._indices[side][:len(group.arm_joints)])
        out['joint_position_rad'] = q[robot._q_indices[side][:len(group.arm_joints)]].tolist()
    check_oracle_command(env, result)
    return robot.validate_action(result)


def check_oracle_command(env, native):
    """Audit an approximate command from measured state, including held targets."""
    scope = active_scope(env._robot.entity)
    if scope is None:
        return
    robot = env._robot
    start = to_numpy(robot.entity.get_qpos()).reshape(-1).copy()
    q = start.copy()
    # Include the commanded fingers and all omitted, held controller targets.
    targets = robot.capture_state().targets
    for side, group in robot.groups.items():
        command = dict(targets[side], **native.get(side, {}))
        q[robot._q_indices[side][:len(group.arm_joints)]] = command['joint_position_rad']
        for name in group.finger_joints:
            q[robot.entity.get_joint(name).qs_idx_local[0]] = command[group.gripper_field]
    # Sequential arm IK is insufficient: validate their simultaneous motion.
    check = scope.check(start, q)
    scope.records.append(dict(kind='command_path', **check))
    if not check['passed']:
        raise ValueError(f'Combined oracle EE path rejected: {check}')
