"""Shared control-mode targets for local policy rollouts; no test-suite imports."""

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.solvers.genesis_kinematics import GenesisFKSolver
from topogym.utils.arrays import to_numpy
from topogym.utils.io import to_jsonable


def rotation(quaternion):
    return Rotation.from_quat(np.asarray(quaternion)[[1, 2, 3, 0]])


def targets_and_action(env, mode):
    measured = env.privileged.get("robot")
    q = to_numpy(env._robot.entity.get_qpos()).reshape(-1).copy()
    goals = {}
    for index, name in enumerate(env.action_spec["arms"]):
        group = env._robot.groups[name]
        target = np.array(measured[name]["joint_position_rad"], copy=True)
        target[0] += .02 if index == 0 else -.02
        q[env._robot._q_indices[name][:len(group.arm_joints)]] = target
        low, high = group.gripper_limits
        goals[name] = {"joint_position_rad": target,
                       group.gripper_field: low + .35 * (high - low)}
    pose = GenesisFKSolver(env._robot.entity).solve(q)
    action = {}
    for name, goal in goals.items():
        group = env._robot.groups[name]
        link = env._robot.entity.get_link(group.hand_link).idx_local
        hand_r = rotation(pose["orientation_wxyz"][link])
        tcp_r = hand_r * rotation(group.tcp_orientation_in_hand_wxyz)
        goal["position_world_m"] = (pose["position_world_m"][link]
                                    + hand_r.apply(group.tcp_position_in_hand_m))
        goal["orientation_wxyz"] = tcp_r.as_quat()[[3, 0, 1, 2]]
        command = {group.gripper_field: goal[group.gripper_field]}
        if mode == "JOINT_ABS":
            command["joint_position_rad"] = goal["joint_position_rad"]
        elif mode == "JOINT_DELTA":
            command["joint_delta_rad"] = (goal["joint_position_rad"]
                                            - measured[name]["joint_position_rad"])
        elif mode == "EE_ABS":
            command.update({key: goal[key] for key in
                            ("position_world_m", "orientation_wxyz")})
        else:
            command["translation_world_m"] = (goal["position_world_m"]
                                                - measured[name]["tcp_position_world_m"])
            command["rotation_world_rad"] = (
                tcp_r * rotation(measured[name]["tcp_orientation_wxyz"]).inv()
            ).as_rotvec()
        action[name] = command
    return goals, to_jsonable(action)
