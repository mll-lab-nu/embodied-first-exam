"""Owner-side read-only IK/FK evidence for every Cartesian policy action."""
import json
import numpy as np

from topogym.solvers.genesis_kinematics import GenesisFKSolver
from topogym.planning.oracle_ik import OracleIKSolver as GenesisIKSolver
from topogym.utils.arrays import to_numpy
from .lock_picking_medium_planning import rotation


class RecordedIKPolicy:
    """Return the original ordinary action after verifying its arm target.

    Simulator still owns compilation and execution; this adapter never sets
    robot/key state or a grasp. Actual passive finger coordinates are retained.
    """
    def __init__(self, policy, robot, stream):
        self.policy, self.robot, self.stream = policy, robot, stream
        self.ik, self.fk = GenesisIKSolver(robot.entity), GenesisFKSolver(robot.entity)

    def __getattr__(self, name):
        return getattr(self.policy, name)

    def act(self, observation):
        action = self.policy.act(observation)
        if action is None:
            return None
        group = self.robot.groups["arm"]
        seed = to_numpy(self.robot.entity.get_qpos()).reshape(-1).copy()
        entry = dict(state=observation["state"], phase=self.policy.phase,
                     action=action, measured_robot_qpos=seed.tolist(), ik_requested=False)
        values = action.get("arm", {})
        if "position_world_m" in values:
            r = rotation(values["orientation_wxyz"])
            target = np.asarray(values["position_world_m"])-r.apply(group.tcp_position_in_hand_m)
            q = self.ik.solve_checked(link_name=group.hand_link, position_world_m=target,
                orientation_wxyz=values["orientation_wxyz"],
                joint_dof_indices=self.robot._indices["arm"][:7], initial_qpos=seed)
            indices = self.robot._q_indices["arm"][:7]
            limits = np.asarray(group.arm_limits_rad)
            margin = float(np.minimum(q[indices]-limits[:,0], limits[:,1]-q[indices]).min())
            if margin < -1e-8:
                raise ValueError("IK candidate exceeds arm limits")
            poses = self.fk.solve(q)
            link = self.robot.entity.get_link(group.hand_link).idx_local
            p = np.asarray(poses["position_world_m"]).reshape(-1,3)[link]
            actual = rotation(np.asarray(poses["orientation_wxyz"]).reshape(-1,4)[link])
            entry.update(ik_requested=True, candidate_robot_qpos=q.tolist(),
                arm_joint_position_rad=q[indices].tolist(), joint_limit_margin_rad=margin,
                maximum_change_from_measured_rad=float(np.max(abs(q[indices]-seed[indices]))),
                position_error_m=float(np.linalg.norm(p-target)),
                orientation_error_rad=float((actual.inv()*r).magnitude()))
        from topogym.utils.io import to_jsonable
        self.stream.write(json.dumps(to_jsonable(entry), allow_nan=False)+"\n")
        self.stream.flush()
        return action
