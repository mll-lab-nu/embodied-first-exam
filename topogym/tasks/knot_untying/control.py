"""Bounded IK targets for force-driven ALOHA knot manipulation.

MuJoCo is used only for forward kinematics during target planning. Genesis
advances the robot and rope; no runtime joint or rope states are overwritten.
"""
import mujoco
import numpy as np
from types import SimpleNamespace
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

from topogym.robot.assets import robot_asset


class BoundedAlohaIK:
    def __init__(self, task, controller):
        self.controller = controller
        self.model = mujoco.MjModel.from_xml_path(robot_asset(controller.cfg))
        self.data = mujoco.MjData(self.model)
        self.indices = {side: [int(self.model.joint(f'{side}/{name}').qposadr[0])
                              for name in controller.cfg.robot.arm_joint_names]
                        for side in controller.arms}
        self.limits = np.asarray(controller.cfg.robot.arm_joint_limits)
        # Infer the source-to-world transform from a measured initial pose.
        for side, arm in controller.arms.items():
            self.data.qpos[self.indices[side]] = arm.arm_qpos()
        mujoco.mj_forward(self.model, self.data)
        arm = controller.left
        body = self.model.body('left/gripper_link').id
        measured = Rotation.from_quat(arm.hand_quat()[[1, 2, 3, 0]])
        self.mount_rotation = measured*Rotation.from_matrix(self.data.xmat[body].reshape(3, 3)).inv()
        self.mount_position = arm.hand_pos()-self.mount_rotation.apply(self.data.xpos[body])
        # A common mounting transform must explain both measured arms. This
        # rejects changed joint references masquerading as a different mount.
        self.initial_position_residual = self.initial_rotation_residual = 0.
        for side, arm in controller.arms.items():
            position, orientation = self.pose(side, arm.arm_qpos())
            measured = Rotation.from_quat(arm.hand_quat()[[1, 2, 3, 0]])
            self.initial_position_residual = max(self.initial_position_residual,
                float(np.linalg.norm(position-arm.hand_pos())))
            self.initial_rotation_residual = max(self.initial_rotation_residual,
                float((measured.inv()*orientation).magnitude()))
        if self.initial_position_residual > .0002 or self.initial_rotation_residual > .002:
            raise ValueError('Measured robot poses disagree with the original model joint references')
        self.previous = {side: arm.arm_qpos() for side, arm in controller.arms.items()}
        self.max_position_residual = self.max_rotation_residual = 0.

    def pose(self, side, q):
        self.data.qpos[self.indices[side]] = q
        mujoco.mj_forward(self.model, self.data)
        body = self.model.body(f'{side}/gripper_link').id
        return (self.mount_position+self.mount_rotation.apply(self.data.xpos[body]),
                self.mount_rotation*Rotation.from_matrix(self.data.xmat[body].reshape(3, 3)))

    def solve(self, side, position, quat, *, seed=None):
        target = Rotation.from_quat(np.asarray(quat)[[1, 2, 3, 0]])

        def residual(q):
            point, orientation = self.pose(side, q)
            return np.r_[10*(point-position), (target.inv()*orientation).as_rotvec()]

        initial = self.previous[side] if seed is None else np.asarray(seed)
        lower, upper = self.limits[:, 0]+1e-5, self.limits[:, 1]-1e-5
        result = least_squares(residual, np.clip(initial, lower, upper), bounds=(lower, upper),
                               max_nfev=160, ftol=1e-10, xtol=1e-10, gtol=1e-10)
        error = residual(result.x)
        position_error, rotation_error = np.linalg.norm(error[:3])/10, np.linalg.norm(error[3:])
        if position_error > .0002 or rotation_error > .002:
            raise ValueError(f'Unreachable {side} target: position {position_error:.6f} m, rotation {rotation_error:.6f} rad')
        self.max_position_residual = max(self.max_position_residual, float(position_error))
        self.max_rotation_residual = max(self.max_rotation_residual, float(rotation_error))
        self.previous[side] = result.x.copy()
        return result.x.copy()


def configure_initial_hover(cfg, material_positions, *, height=.08):
    """Declare an open, contact-free robot start above specified rope points.

    This changes only the initial configuration, before either solver builds.
    Both grasps and every subsequent movement still require physical execution.
    """
    model = mujoco.MjModel.from_xml_path(robot_asset(cfg.robot_control))
    data = mujoco.MjData(model)
    for side in ('left', 'right'):
        for name, value in zip(cfg.robot_control.robot.arm_joint_names, cfg.robot_control.home[side][:6]):
            data.qpos[int(model.joint(f'{side}/{name}').qposadr[0])] = value
    mujoco.mj_forward(model, data)
    mount_R = Rotation.from_euler('xyz', cfg.env.robot_mount.euler, degrees=True)
    mount_p = np.asarray(cfg.env.robot_mount.pos)
    arms = {}
    for side in ('left', 'right'):
        body = model.body(f'{side}/gripper_link').id
        pos = mount_p+mount_R.apply(data.xpos[body])
        quat = (mount_R*Rotation.from_matrix(data.xmat[body].reshape(3, 3))).as_quat()[[3, 0, 1, 2]]
        angles = np.asarray(cfg.robot_control.home[side][:6])
        arms[side] = SimpleNamespace(hand_pos=lambda p=pos: p, hand_quat=lambda q=quat: q,
                                     arm_qpos=lambda q=angles: q)
    ik = BoundedAlohaIK(None, SimpleNamespace(cfg=cfg.robot_control, arms=arms, left=arms['left']))
    from .robot_probe import TOOL_OFFSET, rotation
    poses = {}
    for side, (point, tangent) in material_positions.items():
        tangent = np.asarray(tangent).copy()
        tangent[2] = 0.
        tangent /= np.linalg.norm(tangent)
        options = []
        for z_axis in (tangent, -tangent):
            x_axis = np.array([0., 0., -1.])
            orientation = Rotation.from_matrix(np.column_stack((x_axis, np.cross(z_axis, x_axis), z_axis)))
            options.append(((rotation(arms[side].hand_quat()).inv()*orientation).magnitude(), orientation))
        orientation = min(options, key=lambda item: item[0])[1]
        tool = np.asarray(point)+[0, 0, height]
        angles = ik.solve(side, tool-orientation.apply(TOOL_OFFSET), orientation.as_quat()[[3, 0, 1, 2]])
        cfg.robot_control.home[side] = angles.tolist()+[float(cfg.robot_control.gripper.open_qpos)]*2
        poses[side] = dict(tool_position_m=tool.tolist(), arm_qpos=angles.tolist(), fingers_open=True)
    for side in ('left', 'right'):
        names = list(cfg.robot_control.robot.arm_joint_names)+list(cfg.robot_control.robot.finger_joint_names)
        for name, value in zip(names, cfg.robot_control.home[side]):
            data.qpos[int(model.joint(f'{side}/{name}').qposadr[0])] = value
    mujoco.mj_forward(model, data)
    if any(contact.dist < -.0005 for contact in data.contact):
        raise ValueError('Declared initial hover has a robot self-collision')
    return dict(kind='declared_initial_open_hover', height_above_initial_rope_m=height,
                poses=poses, includes_physical_grasp_from_open_fingers=True,
                neutral_to_hover_motion_recorded=False)
