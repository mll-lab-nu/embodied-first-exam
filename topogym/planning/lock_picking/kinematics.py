"""Lift a certified key route to read-only Genesis Panda/Robotiq IK queries."""
import math
import numpy as np
from scipy.spatial.transform import Rotation, Slerp

from topogym.solvers.genesis_kinematics import GenesisFKSolver
from topogym.planning.oracle_ik import OracleIKSolver as GenesisIKSolver
from topogym.utils.arrays import to_numpy
from .lock_picking_medium_planning import pickup_waypoints, rotation
from .object_route import sample_route


def lift_route(env, states, *, grasp_roll_deg=-45.):
    """Home approach, assumed rigid grasp, lift and full aligned insertion.

    No entity setter, control command, attach, rewind or physical tick occurs.
    This establishes sampled arm reachability, not collision/grasp qualification.
    """
    robot, g = env._robot, env._task.layout
    group = robot.groups["arm"]
    ik, fk = GenesisIKSolver(robot.entity), GenesisFKSolver(robot.entity)
    original = to_numpy(robot.entity.get_qpos()).reshape(-1).copy()
    seed = original.copy()
    qindices = robot._q_indices["arm"][:7]
    dofs = robot._indices["arm"][:7]
    bounds = np.asarray(group.arm_limits_rad)
    arm = robot.observe()["arm"]
    previous = (np.asarray(arm["tcp_position_world_m"]), rotation(arm["tcp_orientation_wxyz"]))
    key = env._world.read_state()["bodies"]["lock_key"]
    kp, kr = np.asarray(key["position_m"]), rotation(key["quaternion_wxyz"])
    grip_local = np.array([-g.grip_offset, 0., 0.])
    center = kp+kr.apply(grip_local)
    grasp = Rotation.from_euler("x", grasp_roll_deg, degrees=True)*Rotation.from_euler("y", 90., degrees=True)
    records = []
    report = dict(passed=False, grasp_roll_deg=grasp_roll_deg, from_default_home=True,
        assumed_key_to_tcp=dict(position_m=grip_local.tolist(), orientation_wxyz=grasp.as_quat()[[3,0,1,2]].tolist()),
        translation_step_m=.002, rotation_step_deg=1.,
        full_scene_collision_verified=False, grasp_verified=False, dynamics_verified=False,
        native_task_success=False, scope="Sampled arm IK/FK, joint limits and continuity; nominal rigid grasp")

    def solve(p, r, phase, **metadata):
        nonlocal seed, previous
        target = p-r.apply(group.tcp_position_in_hand_m)
        q = ik.solve_checked(link_name=group.hand_link, position_world_m=target,
            orientation_wxyz=r.as_quat()[[3,0,1,2]], joint_dof_indices=dofs,
            initial_qpos=seed, max_solver_iterations=200)
        margin = float(np.minimum(q[qindices]-bounds[:, 0], bounds[:, 1]-q[qindices]).min())
        change = float(np.max(abs(q[qindices]-seed[qindices])))
        if margin < -1e-8 or change > .12:
            raise ValueError(f"IK limit/continuity rejected: margin={margin}, adjacent change={change}")
        actual = fk.solve(q)
        idx = robot.entity.get_link(group.hand_link).idx_local
        ap = np.asarray(actual["position_world_m"]).reshape(-1,3)[idx]
        ar = rotation(np.asarray(actual["orientation_wxyz"]).reshape(-1,4)[idx])
        records.append(dict(phase=phase, tcp_position_m=p.tolist(), tcp_orientation_wxyz=r.as_quat()[[3,0,1,2]].tolist(),
            robot_qpos=q.tolist(), arm_joint_position_rad=q[qindices].tolist(),
            position_error_m=float(np.linalg.norm(ap-target)), orientation_error_rad=float((ar.inv()*r).magnitude()),
            joint_limit_margin_rad=margin, adjacent_joint_change_rad=change, **metadata))
        seed, previous = q, (p.copy(), r)

    def transit(p, r, phase):
        p0, r0 = previous
        n = max(1, math.ceil(np.linalg.norm(p-p0)/.002),
                math.ceil(np.degrees((r0.inv()*r).magnitude())))
        rotations = Slerp([0., 1.], Rotation.from_quat([r0.as_quat(), r.as_quat()]))
        for u in np.linspace(0., 1., n+1)[1:]:
            solve(p0+u*(p-p0), rotations(u), phase)

    phase = "home"
    try:
        solve(*previous, phase)
        for p, r, _, phase in pickup_waypoints(*previous, center, kr*grasp, "side"):
            transit(p, r, phase)
        phase = "center_nominal_grasp"
        transit(center, kr*grasp, phase)
        phase = "lift_key_to_axis"
        transit(g.grip_pos(0.), grasp, phase)
        for sample in sample_route(g, states):
            phase = sample["phase"]
            key_r = Rotation.from_euler("x", -sample["key_deg"], degrees=True)
            solve(g.grip_pos(sample["depth"]), key_r*grasp, phase,
                  key_depth=sample["depth"], key_deg=sample["key_deg"], disc_deg=sample["disc_deg"])
        report["passed"] = True
    except ValueError as error:
        report.update(failed_phase=phase, error=str(error))
    if not np.array_equal(original, to_numpy(robot.entity.get_qpos()).reshape(-1)) or env._world.physics_step != 0:
        raise RuntimeError("A read-only IK query changed the episode")
    report.update(samples=len(records), physical_ticks=env._world.physics_step,
        robot_state_unchanged=True,
        maximum_position_error_m=max((r["position_error_m"] for r in records), default=None),
        maximum_orientation_error_rad=max((r["orientation_error_rad"] for r in records), default=None),
        minimum_joint_limit_margin_rad=min((r["joint_limit_margin_rad"] for r in records), default=None),
        maximum_adjacent_joint_change_rad=max((r["adjacent_joint_change_rad"] for r in records), default=None))
    return report, records
